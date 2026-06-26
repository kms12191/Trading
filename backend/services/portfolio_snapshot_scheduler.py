import os
import threading
import time
from datetime import datetime, timedelta, timezone
from typing import Any

import requests

from backend.services.binance_client import BinanceClient
from backend.services.coinone_client import CoinoneClient
from backend.services.kis_client import KISClient
from backend.services.toss_client import TossClient

KST = timezone(timedelta(hours=9))
SUPPORTED_EXCHANGES = {"TOSS", "KIS", "COINONE", "BINANCE"}


def to_number(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def calculate_portfolio_profit_rate(balance: dict) -> float:
    holdings = balance.get("holdings") or []
    total_profit = 0.0
    invested_amount = 0.0

    for item in holdings:
        qty = to_number(item.get("qty"))
        avg_price = to_number(item.get("avg_price"))
        current_price = to_number(item.get("current_price"))
        profit = to_number(item.get("profit"))
        total_profit += profit
        invested_amount += avg_price * qty if avg_price > 0 else max(0.0, current_price * qty - profit)

    if invested_amount <= 0:
        return 0.0
    return (total_profit / invested_amount) * 100


class PortfolioSnapshotScheduler:
    def __init__(self, crypto_helper) -> None:
        self.crypto_helper = crypto_helper
        self.supabase_url = os.getenv("SUPABASE_URL", "").rstrip("/")
        self.supabase_service_role_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")

    @property
    def is_configured(self) -> bool:
        return bool(self.supabase_url and self.supabase_service_role_key)

    def run_once(self) -> dict:
        records = self._list_user_api_keys()
        balances_by_user: dict[str, list[dict]] = {}
        failures = 0

        for record in records:
            exchange = str(record.get("exchange") or "").upper()
            user_id = record.get("user_id")
            if not user_id or exchange not in SUPPORTED_EXCHANGES:
                continue

            try:
                balance = self._fetch_balance(record)
                balance["exchange"] = exchange
                balances_by_user.setdefault(user_id, []).append(balance)
            except Exception:
                failures += 1

        snapshots = []
        now = datetime.now(KST).replace(minute=0, second=0, microsecond=0)
        snapshot_at = now.isoformat()
        snapshot_date = now.date().isoformat()
        for user_id, balances in balances_by_user.items():
            snapshots.append(self._build_snapshot(user_id, snapshot_at, snapshot_date, balances))

        self._upsert_snapshots(snapshots)
        return {
            "user_count": len(snapshots),
            "key_count": len(records),
            "failure_count": failures,
            "snapshot_date": snapshot_date,
        }

    def _fetch_balance(self, record: dict) -> dict:
        exchange = str(record.get("exchange") or "").upper()
        broker_env = record.get("broker_env") or ("MOCK" if exchange == "KIS" else "REAL")
        access_key = self.crypto_helper.decrypt(record.get("encrypted_access_key"))
        secret_key = self.crypto_helper.decrypt(record.get("encrypted_secret_key"))

        if exchange == "TOSS":
            client = TossClient(
                client_id=access_key,
                client_secret=secret_key,
                account_seq=record.get("toss_account_seq"),
                env=broker_env,
            )
            return client.get_balance()

        if exchange == "KIS":
            client = KISClient(
                appkey=access_key,
                appsecret=secret_key,
                cano=record.get("kis_account_no"),
                acnt_prdt_cd=record.get("kis_account_code", "01"),
                env=broker_env,
            )
            return client.get_balance()

        if exchange == "COINONE":
            client = CoinoneClient(access_token=access_key, secret_key=secret_key)
            return client.get_balance()

        if exchange == "BINANCE":
            client = BinanceClient(api_key=access_key, secret_key=secret_key)
            return client.get_balance()

        raise ValueError(f"Unsupported exchange: {exchange}")

    def _build_snapshot(self, user_id: str, snapshot_at: str, snapshot_date: str, balances: list[dict]) -> dict:
        holdings = []
        for balance in balances:
            holdings.extend(balance.get("holdings") or [])

        merged_balance = {
            "holdings": holdings,
            "total_evaluation": sum(to_number(item.get("total_evaluation")) for item in balances),
            "available_cash": sum(to_number(item.get("available_cash")) for item in balances),
        }

        return {
            "user_id": user_id,
            "snapshot_at": snapshot_at,
            "snapshot_date": snapshot_date,
            "total_evaluation": merged_balance["total_evaluation"],
            "available_cash": merged_balance["available_cash"],
            "portfolio_profit_rate": calculate_portfolio_profit_rate(merged_balance),
            "updated_at": datetime.utcnow().isoformat(),
        }

    def _list_user_api_keys(self) -> list[dict]:
        response = requests.get(
            f"{self.supabase_url}/rest/v1/user_api_keys",
            headers=self._service_read_headers(),
            params={
                "select": (
                    "user_id,exchange,broker_env,encrypted_access_key,encrypted_secret_key,"
                    "toss_account_seq,kis_account_no,kis_account_code"
                ),
            },
            timeout=30,
        )
        response.raise_for_status()
        return response.json()

    def _upsert_snapshots(self, snapshots: list[dict]) -> None:
        if not snapshots:
            return

        response = requests.post(
            f"{self.supabase_url}/rest/v1/portfolio_snapshots?on_conflict=user_id,snapshot_at",
            headers=self._service_write_headers(),
            json=snapshots,
            timeout=30,
        )
        response.raise_for_status()

    def _service_read_headers(self) -> dict[str, str]:
        return {
            "apikey": self.supabase_service_role_key,
            "Authorization": f"Bearer {self.supabase_service_role_key}",
            "Content-Type": "application/json",
        }

    def _service_write_headers(self) -> dict[str, str]:
        return {
            **self._service_read_headers(),
            "Prefer": "resolution=merge-duplicates,return=minimal",
        }


def start_portfolio_snapshot_scheduler(
    crypto_helper,
    enabled: bool,
    interval_seconds: int = 60,
    run_on_start: bool = False,
) -> None:
    if not enabled:
        return

    scheduler = PortfolioSnapshotScheduler(crypto_helper)
    if not scheduler.is_configured:
        print("[PortfolioSnapshotScheduler] Supabase service role 설정이 없어 자동 자산 스냅샷을 건너뜁니다.")
        return

    def _loop() -> None:
        last_snapshot_hour = None

        if run_on_start:
            try:
                result = scheduler.run_once()
                last_snapshot_hour = datetime.now(KST).replace(minute=0, second=0, microsecond=0).isoformat()
                print(
                    "[PortfolioSnapshotScheduler] "
                    f"시작 시 자산 스냅샷 저장 완료: {result.get('user_count', 0)}명"
                )
            except Exception as error:
                print(f"[PortfolioSnapshotScheduler] 시작 시 자산 스냅샷 저장 실패: {error}")

        while True:
            now = datetime.now(KST)
            current_hour = now.replace(minute=0, second=0, microsecond=0).isoformat()

            if now.minute == 0 and last_snapshot_hour != current_hour:
                try:
                    result = scheduler.run_once()
                    last_snapshot_hour = current_hour
                    print(
                        "[PortfolioSnapshotScheduler] "
                        f"정각 자산 스냅샷 저장 완료: {result.get('user_count', 0)}명, "
                        f"실패 {result.get('failure_count', 0)}건"
                    )
                except Exception as error:
                    print(f"[PortfolioSnapshotScheduler] 정각 자산 스냅샷 저장 실패: {error}")

            next_hour = (now + timedelta(hours=1)).replace(minute=0, second=0, microsecond=0)
            sleep_seconds = max(1, min(interval_seconds, (next_hour - now).total_seconds()))
            time.sleep(sleep_seconds)

    thread = threading.Thread(target=_loop, daemon=True)
    thread.start()
