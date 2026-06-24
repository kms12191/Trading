import argparse
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(PROJECT_ROOT))

from backend.services.kis_client import KISClient
from backend.services.kis_market_universe import KISMarketUniverseService


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="KIS 종목 정보 파일을 Supabase에 적재하고 거래대금 스냅샷을 갱신합니다.")
    parser.add_argument("--file-path", action="append", dest="file_paths", help="KIS 종목 정보 파일 경로(CSV/JSON/.mst). 여러 번 지정 가능")
    parser.add_argument("--refresh-quotes", action="store_true", help="종목 마스터 저장 후 현재가/거래대금도 같이 갱신")
    parser.add_argument("--quote-limit", type=int, default=300, help="현재가 갱신할 종목 수")
    parser.add_argument("--max-workers", type=int, default=4, help="현재가 조회 동시성")
    return parser


def main() -> int:
    load_dotenv(PROJECT_ROOT / "backend" / ".env")
    load_dotenv(PROJECT_ROOT / ".env")

    args = build_parser().parse_args()
    service = KISMarketUniverseService()

    file_paths = [str(path).strip() for path in (args.file_paths or []) if str(path).strip()]
    if not file_paths:
        raise SystemExit("At least one --file-path value is required.")

    kis_client = KISClient(
        appkey=os.getenv("KIS_APPKEY", ""),
        appsecret=os.getenv("KIS_APPSECRET", ""),
        cano=os.getenv("KIS_CANO", ""),
        acnt_prdt_cd=os.getenv("KIS_ACNT_PRDT_CD", "01"),
        env=os.getenv("KIS_ENV", "MOCK"),
    )

    result = service.sync_from_files(
        file_paths=file_paths,
        kis_client=kis_client,
        refresh_quotes=args.refresh_quotes,
        max_workers=args.max_workers,
        quote_limit=args.quote_limit,
    )

    print(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
