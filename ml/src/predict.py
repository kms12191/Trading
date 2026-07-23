import os
import argparse
import sys
from pathlib import Path

import joblib
import pandas as pd
import yaml

os.environ.setdefault("LOKY_MAX_CPU_COUNT", str(os.cpu_count() or 1))

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))

from ml.src.build_features import build_features, normalize_columns
from ml.src.policy_utils import apply_stock_policy_frame, predict_with_payload


def load_config(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as file:
        return yaml.safe_load(file)


def resolve_ml_path(config_path: str, target_path: str) -> Path:
    base_dir = Path(config_path).resolve().parent.parent
    path = Path(target_path)
    return path if path.is_absolute() else base_dir / path


def read_features_csv(path: Path) -> pd.DataFrame:
    """종목코드 문자열 보존을 위해 symbol dtype을 고정합니다."""
    return pd.read_csv(path, dtype={"symbol": "string"}, low_memory=False)


def load_model_payload(path: Path) -> dict:
    return joblib.load(path)


def annotate_watch_candidates(predictions: pd.DataFrame, asset_type: str, top_n: int) -> pd.DataFrame:
    result = predictions.copy()
    result["watch_candidate"] = 0
    result["watch_rank"] = 0
    result["recommendation_tier"] = result["position"]

    if asset_type != "STOCK" or result.empty:
        return result

    watch_top_n = max(top_n, 5)
    eligible_mask = (
        (result["position"] != "LONG")
        & result["adjusted_composite_spread"].notna()
        & (result["adjusted_composite_spread"] > 0)
    )
    sort_columns = ["adjusted_composite_spread", "up_probability"]
    ascending = [False, False]
    if "long_entry_distance" in result.columns:
        sort_columns = ["long_entry_distance", "adjusted_composite_spread", "up_probability"]
        ascending = [True, False, False]
    watch_df = result.loc[eligible_mask].sort_values(sort_columns, ascending=ascending).head(watch_top_n)
    if watch_df.empty:
        return result

    for rank, idx in enumerate(watch_df.index, start=1):
        result.at[idx, "watch_candidate"] = 1
        result.at[idx, "watch_rank"] = rank
        result.at[idx, "recommendation_tier"] = "WATCH"
    result.loc[result["position"] == "LONG", "recommendation_tier"] = "LONG"
    return result


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
    raw_candles_path = resolve_ml_path(args.config, config["data"]["raw_candles_path"])

    payload = load_model_payload(model_path)
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
            risk_feature_columns = risk_payload["config"]["model"]["feature_columns"]

    if raw_candles_path.exists():
        raw_df = normalize_columns(pd.read_csv(raw_candles_path))
        df = build_features(raw_df, config, include_unlabeled=True)
    else:
        df = read_features_csv(features_path)
    df["date"] = pd.to_datetime(df["date"])
    latest_df = df.sort_values(["symbol", "date"]).groupby("symbol", as_index=False).tail(1).copy()
    up_probabilities = predict_with_payload(payload, latest_df)

    latest_df["up_probability"] = up_probabilities
    latest_df["up_signal_score"] = (latest_df["up_probability"] * 100).round(2)
    latest_df["up_model_version"] = model_config["model"]["version"]

    asset_type = config["model"].get("asset_type", "STOCK").upper()
    prediction_config = config.get("prediction", {})
    long_threshold = float(prediction_config.get("long_threshold", 0.30))
    short_threshold = float(prediction_config.get("short_threshold", 0.70))

    if risk_payload is not None:
        risk_probabilities = predict_with_payload(risk_payload, latest_df)
        latest_df["risk_probability"] = risk_probabilities
        latest_df["risk_signal_score"] = (latest_df["risk_probability"] * 100).round(2)
        latest_df["risk_model_version"] = risk_payload["config"]["model"]["version"]
        if asset_type == "CRYPTO":
            min_composite_spread = float(prediction_config.get("min_composite_spread", 0.0))
            positions = []
            scores = []
            latest_df["composite_spread"] = latest_df["up_probability"] - latest_df["risk_probability"]
            for _, row in latest_df.iterrows():
                risk_p = row["risk_probability"]
                spread = row["composite_spread"]
                if risk_p < long_threshold and spread >= min_composite_spread:
                    positions.append("LONG")
                    scores.append(spread * 100)
                elif risk_p > short_threshold:
                    positions.append("SHORT")
                    scores.append(risk_p * 100)
                else:
                    positions.append("HOLD")
                    scores.append(0.0)
            latest_df["position"] = positions
            latest_df["signal_score"] = [round(score, 2) for score in scores]
            latest_df["scoring_strategy"] = "composite"
        else:
            latest_df = apply_stock_policy_frame(latest_df, prediction_config)
            latest_df["signal_score"] = latest_df["signal_score"].round(2)
            latest_df["scoring_strategy"] = "composite"
    else:
        latest_df["risk_probability"] = 1 - latest_df["up_probability"]
        latest_df["risk_signal_score"] = (latest_df["risk_probability"] * 100).round(2)
        latest_df["risk_model_version"] = ""
        latest_df["position"] = "LONG"
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
        "composite_spread",
        "adjusted_composite_spread",
        "risk_rank_pct",
        "policy_penalty",
        "risk_headroom",
        "spread_headroom",
        "long_entry_distance",
        "signal_score",
        "scoring_strategy",
        "position",
        "market_regime_state",
        "market_breadth_5",
        "sector_breadth_5",
        "sector_strength_score",
        "volume_ratio_5",
        "effective_long_threshold",
        "effective_min_spread",
        "policy_blocked",
        "policy_block_reason",
        "override_applied",
        "exception_entry_applied",
        "relative_risk_override_applied",
        "up_model_version",
        "risk_model_version",
        "model_version",
    ]
    output_columns = [column for column in output_columns if column in latest_df.columns]
    predictions = latest_df[output_columns].sort_values("signal_score", ascending=False)
    predictions = annotate_watch_candidates(predictions, asset_type, int(config.get("backtest", {}).get("top_n", 3)))
    predictions_path.parent.mkdir(parents=True, exist_ok=True)
    predictions.to_csv(predictions_path, index=False)
    print(f"예측 파일 생성 완료: {predictions_path} ({len(predictions):,} rows)")


if __name__ == "__main__":
    main()
