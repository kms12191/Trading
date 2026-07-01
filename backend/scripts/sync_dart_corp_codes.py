import argparse
import sys
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[2]
BACKEND_DIR = PROJECT_ROOT / "backend"
load_dotenv(BACKEND_DIR / ".env")
sys.path.append(str(PROJECT_ROOT))

from backend.services.dart_ingest import DartIngestService


def main() -> None:
    parser = argparse.ArgumentParser(description="CORPCODE.xml의 상장사 고유번호를 Supabase에 동기화합니다.")
    parser.add_argument("--xml-path", default=str(PROJECT_ROOT / "CORPCODE.xml"))
    parser.add_argument("--dry-run", action="store_true", help="DB 저장 없이 XML 파싱 건수만 확인합니다.")
    args = parser.parse_args()

    result = DartIngestService().sync_corp_codes_from_xml(args.xml_path, dry_run=args.dry_run)
    print(result)


if __name__ == "__main__":
    main()
