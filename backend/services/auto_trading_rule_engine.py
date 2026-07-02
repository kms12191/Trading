import os
import threading
import time
import uuid
from datetime import datetime, timezone

from backend.services.binance_client import BinanceClient, BinanceFuturesClient
from backend.services.coinone_client import CoinoneClient
from backend.services.kis_client import KISClient
from backend.services.lock_service import distributed_lock
from backend.services.supabase_client import query_supabase_as_service_role
from backend.services.toss_client import TossClient
from backend.utils.crypto_helper import CryptoHelper


REAL_ORDER_LIMIT_KRW = 100000.0
USD_KRW_FALLBACK = 1500.0
SUPPORTED_EXCHANGES = {"TOSS", "KIS", "COINONE", "BINANCE", "BINANCE_UM_FUTURES"}


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize_execution_mode(value: str | None) -> str:
    mode = str(value or "PROPOSAL").upper()
    return "AUTO" if mode == "AUTO" else "PROPOSAL"


def _extract_price(price_payload: dict) -> float:
    for key in ("current_price", "price", "close"):
        value = price_payload.get(key)
        if value is not None:
            return float(value)
    raw = price_payload.get("raw") or {}
    for key in ("price", "stck_prpr", "lastPrice"):
        value = raw.get(key)
        if value is not None:
            return float(value)
    raise ValueError("현재가 응답에서 가격을 확인할 수 없습니다.")


def _is_krw_market(exchange: str, symbol: str) -> bool:
    return exchange == "COINONE" or (exchange in ("TOSS", "KIS") and str(symbol).isdigit())


def _estimate_amount_krw(exchange: str, symbol: str, price: float, quantity: float) -> float:
    notional = float(price) * float(quantity)
    if _is_krw_market(exchange, symbol):
        return notional
    return notional * USD_KRW_FALLBACK


class AutoTradingRuleEngine:
    """
    auto_trading_rules의 익절/손절 조건을 감시하고 매도 제안 또는 자동 매도를 수행합니다.
    """

    def __init__(self):
        encryption_key = os.getenv("ENCRYPTION_KEY", "default-dev-encryption-key-32bytes!")
        self.crypto = CryptoHelper(encryption_key)

    def run_once(self, limit: int = 50) -> dict:
        rules = self._fetch_running_rules(limit=limit)
        checked = 0
        triggered = 0
        failed = 0

        for rule in rules:
            checked += 1
            try:
                did_trigger = self._process_rule(rule)
                if did_trigger:
                    triggered += 1
            except Exception as exc:
                failed += 1
                self._update_rule(
                    rule["id"],
                    {
                        "last_checked_at": _utc_now_iso(),
                        "last_error": str(exc)[:500],
                    },
                )

        return {"checked": checked, "triggered": triggered, "failed": failed}

    def _fetch_running_rules(self, limit: int) -> list[dict]:
        return query_supabase_as_service_role(
            "auto_trading_rules",
            "GET",
            params={
                "status": "eq.RUNNING",
                "order": "created_at.asc",
                "limit": str(limit),
            },
        ) or []

    def _process_rule(self, rule: dict) -> bool:
        exchange = str(rule.get("exchange") or "").upper()
        if exchange not in SUPPORTED_EXCHANGES:
            raise ValueError(f"지원하지 않는 조건감시 거래소입니다: {exchange}")

        symbol = str(rule.get("symbol") or rule.get("ticker") or "").upper()
        broker_env = str(rule.get("broker_env") or "REAL").upper()
        client = self._build_client(rule, exchange, broker_env)
        current_price = _extract_price(client.get_price(symbol))

        entry_price = float(rule.get("entry_price") or 0)
        if entry_price <= 0:
            raise ValueError("조건감시 규칙의 진입가가 올바르지 않습니다.")

        target_rate = float(rule.get("target_profit_rate") or 0)
        stop_rate = float(rule.get("stop_loss_rate") or 0)
        target_price = entry_price * (1 + target_rate / 100)
        stop_price = entry_price * (1 + stop_rate / 100)

        trigger_side = None
        if current_price >= target_price:
            trigger_side = "TAKE_PROFIT"
        elif current_price <= stop_price:
            trigger_side = "STOP_LOSS"

        if not trigger_side:
            self._update_rule(
                rule["id"],
                {
                    "last_checked_at": _utc_now_iso(),
                    "last_error": None,
                },
            )
            return False

        quantity = self._resolve_exit_quantity(rule, entry_price)
        execution_mode = _normalize_execution_mode(rule.get("execution_mode"))
        should_execute = execution_mode == "AUTO"
        estimated_amount_krw = _estimate_amount_krw(exchange, symbol, current_price, quantity)

        if broker_env == "REAL" and estimated_amount_krw > REAL_ORDER_LIMIT_KRW:
            should_execute = False

        proposal_id = str(uuid.uuid4())
        proposal_payload = self._build_exit_proposal_payload(
            proposal_id=proposal_id,
            rule=rule,
            exchange=exchange,
            broker_env=broker_env,
            symbol=symbol,
            price=current_price,
            quantity=quantity,
            trigger_side=trigger_side,
            requested_execution_mode=execution_mode,
            actual_execution_mode="AUTO" if should_execute else "PROPOSAL",
            estimated_amount_krw=estimated_amount_krw,
        )

        order_result = None
        if should_execute:
            order_result = self._place_exit_order(client, exchange, symbol, quantity, current_price)
            proposal_payload["status"] = self._normalize_order_status(order_result)
            proposal_payload["external_order_id"] = order_result.get("order_id")
            proposal_payload["client_order_id"] = order_result.get("client_order_id")
            proposal_payload["raw_order_payload"]["order"] = order_result.get("raw") or order_result

        query_supabase_as_service_role("trade_proposals", "POST", json_data=proposal_payload)
        self._update_rule(
            rule["id"],
            {
                "status": "COMPLETED",
                "trigger_side": trigger_side,
                "trigger_price": current_price,
                "triggered_at": _utc_now_iso(),
                "last_checked_at": _utc_now_iso(),
                "last_error": None,
                "exit_order_proposal_id": proposal_id,
                "exit_order_payload": order_result or proposal_payload,
            },
        )
        return True

    def _build_client(self, rule: dict, exchange: str, broker_env: str):
        user_id = rule.get("user_id")
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

        if exchange == "TOSS":
            return TossClient(
                client_id=access_key,
                client_secret=secret_key,
                account_seq=record.get("toss_account_seq"),
                env=broker_env,
                user_id=record.get("user_id"),
            )
        if exchange == "KIS":
            return KISClient(
                appkey=access_key,
                appsecret=secret_key,
                cano=record.get("kis_account_no"),
                acnt_prdt_cd=record.get("kis_account_code", "01"),
                env=broker_env,
                user_id=record.get("user_id"),
            )
        if exchange == "COINONE":
            return CoinoneClient(access_token=access_key, secret_key=secret_key)
        if exchange == "BINANCE":
            return BinanceClient(api_key=access_key, secret_key=secret_key, env=broker_env)
        if exchange == "BINANCE_UM_FUTURES":
            return BinanceFuturesClient(api_key=access_key, secret_key=secret_key, env=broker_env)
        raise ValueError(f"지원하지 않는 거래소입니다: {exchange}")

    def _resolve_exit_quantity(self, rule: dict, entry_price: float) -> float:
        quantity = float(rule.get("quantity") or 0)
        if quantity > 0:
            return quantity
        investment_amount = float(rule.get("investment_amount") or 0)
        if investment_amount <= 0:
            raise ValueError("자동매도 수량을 계산할 투자금 또는 수량이 없습니다.")
        return investment_amount / entry_price

    def _build_exit_proposal_payload(
        self,
        proposal_id: str,
        rule: dict,
        exchange: str,
        broker_env: str,
        symbol: str,
        price: float,
        quantity: float,
        trigger_side: str,
        requested_execution_mode: str,
        actual_execution_mode: str,
        estimated_amount_krw: float,
    ) -> dict:
        currency = "KRW" if _is_krw_market(exchange, symbol) else "USD"
        return {
            "id": proposal_id,
            "user_id": rule.get("user_id"),
            "exchange": exchange,
            "asset_type": rule.get("asset_type") or ("STOCK" if exchange in ("TOSS", "KIS") else "CRYPTO"),
            "ticker": rule.get("ticker") or symbol,
            "symbol": symbol,
            "broker_env": broker_env,
            "side": "SELL",
            "price": price,
            "volume": quantity,
            "ord_type": "LIMIT",
            "market_country": rule.get("market_country"),
            "currency": currency,
            "status": "PENDING",
            "raw_order_payload": {
                "source": "AUTO_TRADING_RULE",
                "rule_id": rule.get("id"),
                "trigger_side": trigger_side,
                "requested_execution_mode": requested_execution_mode,
                "actual_execution_mode": actual_execution_mode,
                "estimated_amount_krw": estimated_amount_krw,
            },
        }

    def _place_exit_order(self, client, exchange: str, symbol: str, quantity: float, price: float) -> dict:
        if exchange == "BINANCE_UM_FUTURES":
            return client.place_order(
                symbol=symbol,
                qty=quantity,
                side="SELL",
                ord_type="LIMIT",
                price=price,
                position_side="BOTH",
                reduce_only=True,
            )
        return client.place_order(symbol=symbol, qty=quantity, side="SELL", ord_type="LIMIT", price=price)

    def _normalize_order_status(self, order_result: dict) -> str:
        status = str(order_result.get("status") or "").upper()
        if status in ("FILLED", "EXECUTED"):
            return "EXECUTED"
        if status in ("FAILED", "REJECTED"):
            return "FAILED"
        return "APPROVED"

    def _update_rule(self, rule_id: str, payload: dict):
        query_supabase_as_service_role(
            f"auto_trading_rules?id=eq.{rule_id}",
            "PATCH",
            json_data=payload,
        )


def start_auto_trading_rule_scheduler(enabled: bool, interval_seconds: int = 30):
    if not enabled:
        print("[AutoTradingRuleScheduler] 비활성화되어 기동하지 않습니다.")
        return None

    engine = AutoTradingRuleEngine()
    interval = max(5, int(interval_seconds or 30))

    def loop():
        print(f"[AutoTradingRuleScheduler] 조건감시 자동매도 스케줄러 시작: {interval}초 주기")
        while True:
            try:
                with distributed_lock("auto_trading_rules", max(interval * 2, 60)) as locked:
                    if locked:
                        result = engine.run_once()
                        if result.get("checked"):
                            print(
                                "[AutoTradingRuleScheduler] 감시 완료: "
                                f"{result['checked']}개 확인, {result['triggered']}개 조건 도달, {result['failed']}개 실패"
                            )
            except Exception as exc:
                print(f"[AutoTradingRuleScheduler] 실행 실패: {exc}")
            time.sleep(interval)

    thread = threading.Thread(target=loop, daemon=True, name="auto_trading_rule_scheduler")
    thread.start()
    return thread
