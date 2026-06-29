import threading
import time

from backend.services.market_index_service import collect_market_index_rows, is_korean_market_open


def start_market_index_scheduler(
    market_index_repository,
    enabled: bool,
    open_interval_seconds: int = 60,
    closed_interval_seconds: int = 600,
) -> None:
    if not enabled:
        return
    if not market_index_repository.is_configured:
        print("[MarketIndexScheduler] Supabase is not configured. Skipping index snapshots.")
        return

    def _loop() -> None:
        while True:
            interval = open_interval_seconds if is_korean_market_open() else closed_interval_seconds
            try:
                rows, errors = collect_market_index_rows()
                if rows:
                    market_index_repository.upsert_latest(rows)
                print(
                    "[MarketIndexScheduler] "
                    f"updated={len(rows)} errors={len(errors)} next={interval}s"
                )
                # 에러 상세 내용 출력 (원인 추적용)
                for err in errors:
                    print(f"[MarketIndexScheduler] 수집 실패 symbol={err.get('symbol')} reason={err.get('message')}")
            except Exception as error:
                print(f"[MarketIndexScheduler] update failed: {error}")

            time.sleep(interval)

    thread = threading.Thread(target=_loop, daemon=True)
    thread.start()
