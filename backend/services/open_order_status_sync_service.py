import os
import threading
import time
from datetime import datetime

from backend.services.binance_client import BinanceClient, BinanceFuturesClient
from backend.services.coinone_client import CoinoneClient
from backend.services.kis_client import KISClient
from backend.services.toss_client import TossClient
from backend.services.lock_service import distributed_lock
from backend.services.supabase_client import query_supabase_as_service_role
from backend.utils.crypto_helper import CryptoHelper


ACTIONABLE_STATUSES = ("PENDING", "APPROVED", "MODIFIED")
SUPPORTED_SYNC_EXCHANGES = ("KIS", "COINONE", "BINANCE", "BINANCE_UM_FUTURES", "TOSS")
SCHEMA_FALLBACK_COLUMNS = {
    "broker_env",
    "raw_order_payload",
    "canceled_at",
}


def _utc_now_iso() -> str:
    return datetime.utcnow().isoformat() + "Z"


def _as_float(value, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _resolve_broker_env(proposal: dict) -> str:
    return str(proposal.get("broker_env") or "REAL").upper()


def _is_supabase_schema_error(error: Exception) -> bool:
    text = str(error).lower()
    return any(
        token in text
        for token in (
            "pgrst204",
            "schema cache",
            "could not find",
            "raw_order_payload",
            "canceled_at",
            "broker_env",
        )
    )


def _normalize_external_status(raw_status: str, executed_qty: float = 0.0, requested_qty: float = 0.0) -> str:
    normalized = str(raw_status or "").upper()
    if normalized in {"FILLED", "EXECUTED", "DONE", "COMPLETED"}:
        return "EXECUTED"
    if requested_qty > 0 and executed_qty >= requested_qty:
        return "EXECUTED"
    if normalized in {"CANCELED", "CANCELLED"}:
        return "CANCELED"
    if normalized in {"REJECTED", "FAILED", "EXPIRED"}:
        return "FAILED"
    if normalized in {"PARTIALLY_FILLED", "PARTIAL"} or executed_qty > 0:
        return "APPROVED"
    return "APPROVED"


class OpenOrderStatusSyncService:
    """
    전체 사용자의 미완료 주문 상태를 거래소 API 기준으로 보정하는 워커 전용 서비스입니다.
    """

    def __init__(self):
        encryption_key = os.getenv("ENCRYPTION_KEY", "default-dev-encryption-key-32bytes!")
        self.crypto = CryptoHelper(encryption_key)

    def run_once(self, limit: int = 100) -> dict:
        proposals = self._fetch_actionable_proposals(limit=limit)
        checked = 0
        synced = 0
        failed = 0
        errors = []
        clients = {}

        for proposal in proposals:
            exchange = str(proposal.get("exchange") or "").upper()
            if exchange not in SUPPORTED_SYNC_EXCHANGES:
                continue

            proposal_id = proposal.get("id")
            symbol = proposal.get("symbol") or proposal.get("ticker")
            order_id = proposal.get("external_order_id")
            if not proposal_id or not symbol or not order_id:
                continue

            try:
                client_key = self._build_client_key(proposal)
                if client_key not in clients:
                    clients[client_key] = self._build_client(proposal)
                client = clients[client_key]

                checked += 1
                current_order = self._fetch_order_status(client, exchange, order_id, symbol)
                next_status = self._resolve_next_status(current_order, proposal)
                self._patch_proposal(proposal, current_order, next_status)
                synced += 1
            except Exception as exc:
                failed += 1
                if len(errors) < 10:
                    errors.append(f"{exchange} {symbol}: {str(exc)[:500]}")

        return {
            "fetched": len(proposals),
            "checked": checked,
            "synced": synced,
            "failed": failed,
            "errors": errors,
        }

    def _fetch_actionable_proposals(self, limit: int) -> list[dict]:
        return query_supabase_as_service_role(
            "trade_proposals",
            "GET",
            params={
                "exchange": f"in.({','.join(SUPPORTED_SYNC_EXCHANGES)})",
                "status": f"in.({','.join(ACTIONABLE_STATUSES)})",
                "external_order_id": "not.is.null",
                "order": "created_at.desc",
                "limit": str(max(1, int(limit or 100))),
            },
        ) or []

    def _build_client_key(self, proposal: dict) -> str:
        user_id = proposal.get("user_id")
        exchange = str(proposal.get("exchange") or "").upper()
        broker_env = _resolve_broker_env(proposal)
        return f"{user_id}:{exchange}:{broker_env}"

    def _build_client(self, proposal: dict):
        user_id = proposal.get("user_id")
        exchange = str(proposal.get("exchange") or "").upper()
        broker_env = _resolve_broker_env(proposal)
        credential_exchange = "BINANCE" if exchange == "BINANCE_UM_FUTURES" else exchange
        records = query_supabase_as_service_role(
            "user_api_keys",
            "GET",
            params={
                "user_id": f"eq.{user_id}",
                "exchange": f"eq.{credential_exchange}",
                "broker_env": f"eq.{broker_env}",
                "limit": "1",
            },
        ) or []
        if not records:
            raise ValueError(f"등록된 {credential_exchange} ({broker_env}) API 키가 없습니다.")

        record = records[0]
        access_key = self.crypto.decrypt(record.get("encrypted_access_key"))
        secret_key = self.crypto.decrypt(record.get("encrypted_secret_key"))

        if exchange == "KIS":
            return KISClient(
                appkey=access_key,
                appsecret=secret_key,
                cano=record.get("kis_account_no"),
                acnt_prdt_cd=record.get("kis_account_code", "01"),
                env=broker_env,
                user_id=user_id,
            )
        if exchange == "TOSS":
            return TossClient(
                client_id=access_key,
                client_secret=secret_key,
                account_seq=record.get("toss_account_seq"),
                env=broker_env,
                user_id=user_id,
            )
        if exchange == "COINONE":
            return CoinoneClient(access_token=access_key, secret_key=secret_key)
        if exchange == "BINANCE":
            return BinanceClient(api_key=access_key, secret_key=secret_key, env=broker_env)
        if exchange == "BINANCE_UM_FUTURES":
            return BinanceFuturesClient(api_key=access_key, secret_key=secret_key, env=broker_env)
        raise ValueError(f"지원하지 않는 주문 상태 동기화 거래소입니다: {exchange}")

    def _fetch_order_status(self, client, exchange: str, order_id: str, symbol: str) -> dict:
        if exchange == "KIS":
            return client.get_order_execution_status(order_id or "", symbol=symbol, lookback_days=30)
        return client.get_order_status(order_id, symbol=symbol)

    def _resolve_next_status(self, current_order: dict, proposal: dict) -> str:
        raw_status = current_order.get("status") or current_order.get("raw_status")
        executed_qty = _as_float(current_order.get("executed_qty") or current_order.get("filled_qty"))
        requested_qty = _as_float(proposal.get("volume"))
        return _normalize_external_status(raw_status, executed_qty=executed_qty, requested_qty=requested_qty)

    def _patch_proposal(self, proposal: dict, current_order: dict, next_status: str):
        proposal_id = proposal["id"]
        exchange = str(proposal.get("exchange") or "").upper()
        raw_status = str(current_order.get("status") or current_order.get("raw_status") or "").upper()
        payload = {
            "status": next_status,
            "broker_env": _resolve_broker_env(proposal),
            "failure_reason": None,
            "raw_order_payload": {
                "worker_status_sync": {
                    "synced_at": _utc_now_iso(),
                    "exchange": exchange,
                    "order_status": current_order,
                    "normalized_status": next_status,
                }
            },
        }
        if next_status == "CANCELED":
            payload["canceled_at"] = _utc_now_iso()
        if next_status == "FAILED":
            payload["failure_reason"] = f"{exchange} order status: {raw_status or 'FAILED'}"

        try:
            query_supabase_as_service_role(
                f"trade_proposals?id=eq.{proposal_id}",
                "PATCH",
                json_data=payload,
            )
        except Exception as exc:
            if not _is_supabase_schema_error(exc):
                raise
            fallback_payload = {
                key: value
                for key, value in payload.items()
                if key not in SCHEMA_FALLBACK_COLUMNS
            }
            query_supabase_as_service_role(
                f"trade_proposals?id=eq.{proposal_id}",
                "PATCH",
                json_data=fallback_payload,
            )

        if next_status == "EXECUTED":
            try:
                self._update_associated_auto_trading_rule(proposal, current_order)
            except Exception as exc:
                print(f"[OpenOrderStatusSyncService] 자동감시 진입가 보정 실패: {exc}")

        if next_status in ("EXECUTED", "CANCELED", "FAILED"):
            try:
                self._handle_partial_filled_exit_order(proposal, current_order, next_status)
            except Exception as exc:
                print(f"[OpenOrderStatusSyncService] 부분 체결 감시 복구 처리 실패: {exc}")

    def _handle_partial_filled_exit_order(self, proposal: dict, current_order: dict, next_status: str):
        proposal_id = proposal.get("id")
        
        # 1. exit_order_proposal_id가 proposal_id인 규칙 조회
        rules = query_supabase_as_service_role(
            "auto_trading_rules",
            "GET",
            params={
                "exit_order_proposal_id": f"eq.{proposal_id}",
                "limit": "1"
            }
        ) or []
        if not rules:
            return
            
        rule = rules[0]
        
        # 2. 부분 체결량 및 남은 수량 계산
        executed_qty = _as_float(current_order.get("executed_qty") or current_order.get("filled_qty"))
        requested_qty = _as_float(proposal.get("volume"))
        
        # 부분 체결인 경우 (0 초과, 요청량 미만)
        if 0.0 < executed_qty < requested_qty:
            remaining_qty = requested_qty - executed_qty
            if remaining_qty > 1e-6:
                auto_restart = rule.get("auto_restart_on_partial_fill", True)
                if auto_restart:
                    rule_id = rule["id"]
                    entry_price = _as_float(rule.get("entry_price") or 0.0)
                    
                    # 규칙 복구 (상태 -> RUNNING, 수량 차감, exit_proposal 비움)
                    patch_data = {
                        "status": "RUNNING",
                        "quantity": remaining_qty,
                        "investment_amount": entry_price * remaining_qty if entry_price > 0 else rule.get("investment_amount"),
                        "exit_order_proposal_id": None, # 새로운 매도 주문 등록이 가능하도록 비움
                        "updated_at": _utc_now_iso(),
                        "last_error": f"부분 체결 완료 감지: {executed_qty}개 체결. 남은 {remaining_qty}개 재감시 시작 (상태: {next_status})."
                    }
                    query_supabase_as_service_role(
                        f"auto_trading_rules?id=eq.{rule_id}",
                        "PATCH",
                        json_data=patch_data
                    )
                    print(f"[OpenOrderStatusSyncService] 조건감시 규칙 {rule_id} 복구 완료. 잔여 {remaining_qty}개 재감시 기동.")

    def _update_associated_auto_trading_rule(self, proposal: dict, current_order: dict):
        proposal_id = proposal.get("id")
        exchange = str(proposal.get("exchange") or "").upper()
        
        # 1. entry_order_proposal_id가 proposal_id인 활성 감시 규칙 조회
        rules = query_supabase_as_service_role(
            "auto_trading_rules",
            "GET",
            params={
                "entry_order_proposal_id": f"eq.{proposal_id}",
                "status": "eq.RUNNING"
            }
        ) or []
        if not rules:
            return

        # 2. 거래소별 평균체결단가 추출
        avg_price = 0.0
        if exchange == "TOSS":
            raw_result = current_order.get("raw", {}).get("result", {})
            execution = raw_result.get("execution") or {}
            avg_price = _as_float(
                raw_result.get("averageFilledPrice")
                or execution.get("averageFilledPrice")
            )
        elif exchange == "KIS":
            # KIS matched 이력의 avg_price 취함
            raw_matched = current_order.get("raw", [])
            if isinstance(raw_matched, list) and len(raw_matched) > 0:
                avg_price = _as_float(raw_matched[0].get("avg_price"))
        elif exchange == "COINONE":
            raw_data = current_order.get("raw", {})
            avg_price = _as_float(raw_data.get("average_price"))
        elif exchange in ("BINANCE", "BINANCE_UM_FUTURES"):
            raw_data = current_order.get("raw", {})
            avg_price = _as_float(raw_data.get("price") or raw_data.get("avgPrice"))
            
        if avg_price <= 0.0:
            avg_price = _as_float(proposal.get("price")) # Fallback to order price

        if avg_price <= 0.0:
            return

        # 3. DB 업데이트
        for rule in rules:
            rule_id = rule["id"]
            qty = _as_float(rule.get("quantity")) or _as_float(proposal.get("volume"))
            patch_data = {
                "entry_price": avg_price,
                "investment_amount": avg_price * qty,
                "updated_at": _utc_now_iso()
            }
            query_supabase_as_service_role(
                f"auto_trading_rules?id=eq.{rule_id}",
                "PATCH",
                json_data=patch_data
            )


def start_open_order_status_sync_scheduler(enabled: bool, interval_seconds: int = 60, limit: int = 100):
    if not enabled:
        print("[OpenOrderStatusSyncScheduler] 비활성화되어 기동하지 않습니다.")
        return None

    service = OpenOrderStatusSyncService()
    interval = max(15, int(interval_seconds or 60))
    batch_limit = max(1, int(limit or 100))

    def loop():
        print(f"[OpenOrderStatusSyncScheduler] 미완료 주문 상태 동기화 시작: {interval}초 주기, 최대 {batch_limit}건")
        while True:
            try:
                with distributed_lock("open_order_status_sync", max(interval * 2, 60)) as locked:
                    if locked:
                        result = service.run_once(limit=batch_limit)
                        if result.get("checked") or result.get("failed"):
                            print(
                                "[OpenOrderStatusSyncScheduler] 동기화 완료: "
                                f"{result['checked']}개 확인, {result['synced']}개 반영, {result['failed']}개 실패"
                            )
                            if result.get("errors"):
                                print(
                                    "[OpenOrderStatusSyncScheduler] 오류 샘플: "
                                    + " | ".join(result["errors"][:3])
                                )
            except Exception as exc:
                print(f"[OpenOrderStatusSyncScheduler] 실행 실패: {exc}")
            time.sleep(interval)

    thread = threading.Thread(target=loop, daemon=True, name="open_order_status_sync_scheduler")
    thread.start()
    return thread
