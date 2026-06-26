import threading
import time
from datetime import datetime, timedelta, timezone

from backend.services.kis_client import KISClient

KST = timezone(timedelta(hours=9))


def is_korean_market_open(now: datetime | None = None) -> bool:
    current = now or datetime.now(KST)
    if current.weekday() >= 5:
        return False
    minutes = current.hour * 60 + current.minute
    return 9 * 60 <= minutes <= 15 * 60 + 30


def start_market_snapshot_scheduler(
    kis_market_universe_service,
    enabled: bool,
    kis_config: dict,
    open_interval_seconds: int = 60,
    closed_interval_seconds: int = 600,
    quote_limit: int = 300,
    max_workers: int = 2,
) -> None:
    if not enabled:
        return
    if not kis_market_universe_service.repository.is_configured:
        print("[MarketSnapshotScheduler] Supabase 설정이 없어 스냅샷 갱신을 건너뜁니다.")
        return
    if not (kis_config.get("appkey") and kis_config.get("appsecret")):
        print("[MarketSnapshotScheduler] KIS 키가 없어 스냅샷 갱신을 건너뜁니다.")
        return

    def _loop() -> None:
        while True:
            interval = open_interval_seconds if is_korean_market_open() else closed_interval_seconds
            try:
                client = KISClient(
                    appkey=kis_config.get("appkey", ""),
                    appsecret=kis_config.get("appsecret", ""),
                    cano=kis_config.get("cano", ""),
                    acnt_prdt_cd=kis_config.get("acnt_prdt_cd", "01"),
                    env=kis_config.get("env", "REAL"),
                )
                result = kis_market_universe_service.refresh_turnover_snapshots(
                    kis_client=client,
                    quote_limit=quote_limit,
                    max_workers=max_workers,
                )
                print(
                    "[MarketSnapshotScheduler] "
                    f"스냅샷 갱신 완료: {result.get('quote_count', 0)}건, "
                    f"다음 주기 {interval}초"
                )
            except Exception as error:
                print(f"[MarketSnapshotScheduler] 스냅샷 갱신 실패: {error}")

            time.sleep(interval)

    thread = threading.Thread(target=_loop, daemon=True)
    thread.start()
