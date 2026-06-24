import argparse
import sys
from pathlib import Path

import joblib
import pandas as pd
import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))

from ml.src.model_utils import apply_probability_calibration


def load_config(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as file:
        return yaml.safe_load(file)


def resolve_ml_path(config_path: str, target_path: str) -> Path:
    base_dir = Path(config_path).resolve().parent.parent
    path = Path(target_path)
    return path if path.is_absolute() else base_dir / path


def load_model_payload(path: Path) -> dict:
    return joblib.load(path)


def main() -> None:
    parser = argparse.ArgumentParser(description="저장된 LightGBM 모델로 최신 피처를 예측합니다.")
    parser.add_argument("--config", default="configs/lgbm_stock_v1.yaml", help="학습 설정 파일 경로")
    parser.add_argument("--model", default=None, help="모델 파일 경로")
    parser.add_argument("--risk-model", default=None, help="하락 위험 모델 파일 경로")
    args = parser.parse_args()

    config = load_config(args.config)
    model_path = resolve_ml_path(args.config, args.model or config["model"]["output_path"])
    features_path = resolve_ml_path(args.config, config["data"]["features_path"])
    predictions_path = resolve_ml_path(args.config, config["data"]["predictions_path"])

    payload = load_model_payload(model_path)
    model = payload["model"]
    calibrator = payload.get("calibrator")
    model_config = payload["config"]
    feature_columns = model_config["model"]["feature_columns"]

    risk_model_path = args.risk_model or config.get("prediction", {}).get("risk_model_path")
    risk_payload = None
    risk_model = None
    risk_calibrator = None
    risk_feature_columns: list[str] = []
    if risk_model_path:
        candidate_path = Path(risk_model_path)
        if not candidate_path.is_absolute():
            candidate_path = resolve_ml_path(args.config, str(candidate_path))
        if candidate_path.exists():
            risk_payload = load_model_payload(candidate_path)
            risk_model = risk_payload["model"]
            risk_calibrator = risk_payload.get("calibrator")
            risk_feature_columns = risk_payload["config"]["model"]["feature_columns"]

    df = pd.read_csv(features_path)
    df["date"] = pd.to_datetime(df["date"])
    latest_df = df.sort_values(["symbol", "date"]).groupby("symbol", as_index=False).tail(1).copy()
    up_probabilities = model.predict_proba(latest_df[feature_columns])[:, 1]
    up_probabilities = apply_probability_calibration(up_probabilities, calibrator)

    latest_df["up_probability"] = up_probabilities
    latest_df["up_signal_score"] = (latest_df["up_probability"] * 100).round(2)
    latest_df["up_model_version"] = model_config["model"]["version"]

    if risk_model is not None:
        risk_probabilities = risk_model.predict_proba(latest_df[risk_feature_columns])[:, 1]
        risk_probabilities = apply_probability_calibration(risk_probabilities, risk_calibrator)
        latest_df["risk_probability"] = risk_probabilities
        latest_df["risk_signal_score"] = (latest_df["risk_probability"] * 100).round(2)
        latest_df["risk_model_version"] = risk_payload["config"]["model"]["version"]
        latest_df["signal_score"] = ((latest_df["up_probability"] - latest_df["risk_probability"]) * 100).round(2)
        latest_df["scoring_strategy"] = "composite"
    else:
        latest_df["risk_probability"] = 1 - latest_df["up_probability"]
        latest_df["risk_signal_score"] = (latest_df["risk_probability"] * 100).round(2)
        latest_df["risk_model_version"] = ""
        latest_df["signal_score"] = latest_df["up_signal_score"]
        latest_df["scoring_strategy"] = "up_only"

    latest_df["model_version"] = model_config["model"]["version"]

    output_columns = [
        "exchange",
        "asset_type",
        "symbol",
        "date",
        "horizon_periods",
        "up_probability",
        "risk_probability",
        "up_signal_score",
        "risk_signal_score",
        "signal_score",
        "scoring_strategy",
        "up_model_version",
        "risk_model_version",
        "model_version",
    ]
    output_columns = [column for column in output_columns if column in latest_df.columns]
    predictions = latest_df[output_columns].sort_values("signal_score", ascending=False)
    predictions_path.parent.mkdir(parents=True, exist_ok=True)
    predictions.to_csv(predictions_path, index=False)
    print(f"예측 파일 생성 완료: {predictions_path} ({len(predictions):,} rows)")


if __name__ == "__main__":
    main()
