import logging
import threading
import time
from datetime import datetime, timedelta, timezone

from backend.services.market_index_service import (
    CONFIGURED_INDEX_SYMBOLS,
    collect_market_index_rows,
    is_korean_market_open,
    set_market_index_cache,
)

KST = timezone(timedelta(hours=9))
logger = logging.getLogger(__name__)


def start_market_index_scheduler(
    market_index_repository,
    enabled: bool,
    open_interval_seconds: int = 60,
    closed_interval_seconds: int = 600,
) -> None:
    if not enabled:
        logger.info("[MarketIndexScheduler] disabled")
        return

    if not market_index_repository.is_configured:
        logger.warning("[MarketIndexScheduler] Supabase is not configured. Memory cache warming only.")

    def _loop() -> None:
        while True:
            interval = open_interval_seconds if is_korean_market_open() else closed_interval_seconds
            target_date = datetime.now(KST).date().isoformat()
            try:
                logger.info(
                    "[MarketIndexScheduler] cache generation start targetDate=%s symbolCount=%s symbols=%s",
                    target_date,
                    len(CONFIGURED_INDEX_SYMBOLS),
                    ",".join(CONFIGURED_INDEX_SYMBOLS),
                )

                rows, errors = collect_market_index_rows()
                logger.info(
                    "[MarketIndexScheduler] data collection complete targetDate=%s rowCount=%s errorCount=%s",
                    target_date,
                    len(rows),
                    len(errors),
                )

                if rows:
                    # 수집 완료 즉시 메모리 캐시에 반영해 역전바가 바로 읽을 수 있게 한다.
                    set_market_index_cache(rows)
                    logger.info("[MarketIndexScheduler] memory cache save success count=%s", len(rows))
                    if market_index_repository.is_configured:
                        market_index_repository.upsert_latest(rows)
                        logger.info("[MarketIndexScheduler] DB cache save success count=%s", len(rows))
                else:
                    logger.warning("[MarketIndexScheduler] cache query failed reason=empty collection result")

                for err in errors:
                    logger.warning(
                        "[MarketIndexScheduler] cache query failed symbol=%s reason=%s",
                        err.get("symbol"),
                        err.get("message"),
                    )

                logger.info("[MarketIndexScheduler] next run in %ss", interval)
            except Exception as error:
                logger.exception("[MarketIndexScheduler] update failed: %s", error)

            time.sleep(interval)

    thread = threading.Thread(target=_loop, daemon=True)
    thread.start()
