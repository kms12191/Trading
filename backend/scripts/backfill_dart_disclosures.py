import argparse
import sys
from datetime import date
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[2]
BACKEND_DIR = PROJECT_ROOT / "backend"
load_dotenv(BACKEND_DIR / ".env")
sys.path.append(str(PROJECT_ROOT))

from backend.services.dart_ingest import DartIngestService


def main() -> None:
    parser = argparse.ArgumentParser(description="최근 1년 OpenDART 공시를 stock_code가 있는 항목만 백필합니다.")
    parser.add_argument("--days", type=int, default=None, help="백필 일수. 기본값은 DART_BACKFILL_DAYS입니다.")
    parser.add_argument("--chunk-days", type=int, default=None, help="한 번에 조회할 날짜 구간입니다.")
    parser.add_argument("--start-date", default="", help="YYYY-MM-DD 형식의 시작일입니다.")
    parser.add_argument("--end-date", default="", help="YYYY-MM-DD 형식의 종료일입니다.")
    args = parser.parse_args()

    service = DartIngestService()
    if args.days is not None:
        service.backfill_days = args.days
    if args.chunk_days is not None:
        service.backfill_chunk_days = args.chunk_days

    if args.start_date or args.end_date:
        if not args.start_date or not args.end_date:
            raise ValueError("--start-date와 --end-date는 함께 지정해야 합니다.")
        start_date = date.fromisoformat(args.start_date)
        end_date = date.fromisoformat(args.end_date)
        result = {
            "fetched": 0,
            "saved": 0,
            "request_count": 0,
            "windows": 0,
            "failures": [],
        }
        cursor = start_date
        while cursor <= end_date:
            window_end = min(
                date.fromordinal(cursor.toordinal() + service.backfill_chunk_days - 1),
                end_date,
            )
            try:
                window_result = service.run_range(
                    start_date=cursor,
                    end_date=window_end,
                    query_key=f"backfill:{cursor.isoformat()}:{window_end.isoformat()}",
                )
                result["fetched"] += int(window_result.get("fetched", 0))
                result["saved"] += int(window_result.get("saved", 0))
                result["request_count"] += int(window_result.get("request_count", 0))
                result["windows"] += 1
            except Exception as error:
                result["failures"].append(
                    {
                        "start_date": cursor.isoformat(),
                        "end_date": window_end.isoformat(),
                        "error": str(error),
                    }
                )
            cursor = date.fromordinal(window_end.toordinal() + 1)
    else:
        result = service.run_backfill_recent_year()
    print(result)


if __name__ == "__main__":
    main()
