import argparse
from pathlib import Path

import joblib
import pandas as pd
import yaml


def load_config(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as file:
        return yaml.safe_load(file)


def main() -> None:
    parser = argparse.ArgumentParser(description="저장된 LightGBM 모델로 최신 피처를 예측합니다.")
    parser.add_argument("--config", default="configs/lgbm_stock_v1.yaml", help="학습 설정 파일 경로")
    parser.add_argument("--model", default=None, help="모델 파일 경로")
    args = parser.parse_args()

    config = load_config(args.config)
    model_path = Path(args.model or config["model"]["output_path"])
    features_path = Path(config["data"]["features_path"])
    predictions_path = Path(config["data"]["predictions_path"])

    payload = joblib.load(model_path)
    model = payload["model"]
    model_config = payload["config"]
    feature_columns = model_config["model"]["feature_columns"]

    df = pd.read_csv(features_path)
    df["date"] = pd.to_datetime(df["date"])
    latest_df = df.sort_values(["symbol", "date"]).groupby("symbol", as_index=False).tail(1).copy()
    probabilities = model.predict_proba(latest_df[feature_columns])[:, 1]

    latest_df["up_probability"] = probabilities
    latest_df["risk_probability"] = 1 - latest_df["up_probability"]
    latest_df["signal_score"] = (latest_df["up_probability"] * 100).round(2)
    latest_df["model_version"] = model_config["model"]["version"]

    output_columns = [
        "exchange",
        "asset_type",
        "symbol",
        "date",
        "horizon_periods",
        "up_probability",
        "risk_probability",
        "signal_score",
        "model_version",
    ]
    output_columns = [column for column in output_columns if column in latest_df.columns]
    predictions = latest_df[output_columns].sort_values("signal_score", ascending=False)
    predictions_path.parent.mkdir(parents=True, exist_ok=True)
    predictions.to_csv(predictions_path, index=False)
    print(f"예측 파일 생성 완료: {predictions_path} ({len(predictions):,} rows)")


if __name__ == "__main__":
    main()
