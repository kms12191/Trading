import argparse
import json
from pathlib import Path

import joblib


def main() -> None:
    parser = argparse.ArgumentParser(description="저장된 모델의 검증 지표를 출력합니다.")
    parser.add_argument("--model", default="models/lgbm_stock_signal_v1.joblib", help="모델 파일 경로")
    args = parser.parse_args()

    payload = joblib.load(Path(args.model))
    print(json.dumps(payload.get("metrics", {}), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
