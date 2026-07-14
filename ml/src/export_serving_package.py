from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from backend.services.ml_serving_package_service import export_serving_package as export_package


def build_parser() -> argparse.ArgumentParser:
    """EC2 배포용 ML 서빙 패키지 export CLI 파서를 생성합니다."""
    parser = argparse.ArgumentParser(description="EC2 배포용 ML 서빙 패키지를 생성합니다.")
    parser.add_argument(
        "--asset-key",
        required=True,
        choices=["stock", "kr_stock", "us_stock", "crypto"],
        help="패키지로 만들 자산 모델 그룹입니다.",
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=None,
        help="패키지 출력 루트입니다. 기본값은 ml/serving_packages 입니다.",
    )
    parser.add_argument(
        "--auth-header",
        default=None,
        help="Supabase registry 조회가 필요할 때 사용할 Authorization 헤더입니다.",
    )
    parser.add_argument(
        "--no-predictions",
        action="store_true",
        help="예측 CSV 스냅샷을 패키지에서 제외합니다.",
    )
    parser.add_argument(
        "--archive",
        action="store_true",
        help="패키지 디렉터리와 함께 tar.gz 아카이브를 생성합니다.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """CLI 진입점입니다."""
    parser = build_parser()
    args = parser.parse_args(argv)
    result = export_package(
        args.asset_key,
        args.auth_header,
        output_root=args.output_root,
        include_predictions=not args.no_predictions,
        create_archive=args.archive,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
