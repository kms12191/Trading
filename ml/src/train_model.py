import argparse
import json
import sys
from pathlib import Path

import joblib
import pandas as pd
import yaml
from lightgbm import LGBMClassifier
from sklearn.linear_model import LogisticRegression

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))

from ml.src.model_utils import (
    apply_probability_calibration,
    build_sample_weights,
    build_time_series_folds,
    calculate_metrics,
    compute_scale_pos_weight,
    split_by_time,
    split_train_calibration,
)


def load_config(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as file:
        return yaml.safe_load(file)


def resolve_ml_path(config_path: str, target_path: str) -> Path:
    base_dir = Path(config_path).resolve().parent.parent
    path = Path(target_path)
    return path if path.is_absolute() else base_dir / path


def main() -> None:
    parser = argparse.ArgumentParser(description="LightGBM 신호 모델을 학습합니다.")
    parser.add_argument("--config", default="configs/lgbm_stock_v1.yaml", help="학습 설정 파일 경로")
    args = parser.parse_args()

    config = load_config(args.config)
    features_path = resolve_ml_path(args.config, config["data"]["features_path"])
    model_path = resolve_ml_path(args.config, config["model"]["output_path"])
    metrics_path = model_path.with_suffix(".metrics.json")

    df = pd.read_csv(features_path)
    feature_columns = config["model"]["feature_columns"]
    target_column = config["model"]["target_column"]
    train_df, valid_df = split_by_time(df, float(config["model"]["validation_ratio"]))

    training_options = config.get("training", {})
    class_weight_mode = str(training_options.get("class_weight_mode", "none"))
    balance_symbols = bool(training_options.get("balance_symbol_weights", False))
    calibration_enabled = bool(training_options.get("enable_probability_calibration", False))
    calibration_ratio = float(training_options.get("calibration_ratio", 0.1))
    cv_splits = int(training_options.get("time_series_cv_splits", 0))

    base_train_df, calibration_df = split_train_calibration(train_df, calibration_ratio if calibration_enabled else 0.0)
    fit_df = base_train_df if not base_train_df.empty else train_df

    lightgbm_params = dict(config["lightgbm"])
    if training_options.get("use_scale_pos_weight"):
        lightgbm_params["scale_pos_weight"] = compute_scale_pos_weight(fit_df[target_column])

    sample_weights = build_sample_weights(
        fit_df,
        target_column=target_column,
        class_weight_mode=class_weight_mode,
        balance_symbols=balance_symbols,
    )

    model = LGBMClassifier(
        random_state=int(config["model"]["random_state"]),
        **lightgbm_params,
    )
    model.fit(
        fit_df[feature_columns],
        fit_df[target_column],
        sample_weight=sample_weights,
    )

    calibrator = None
    calibration_rows = 0
    if calibration_enabled and not calibration_df.empty:
        calibration_prob = model.predict_proba(calibration_df[feature_columns])[:, 1]
        calibrator = LogisticRegression(random_state=int(config["model"]["random_state"]), max_iter=1000)
        calibrator.fit(calibration_prob.reshape(-1, 1), calibration_df[target_column])
        calibration_rows = int(len(calibration_df))

    valid_prob = model.predict_proba(valid_df[feature_columns])[:, 1]
    valid_prob = apply_probability_calibration(valid_prob, calibrator)
    valid_prob = pd.Series(valid_prob, index=valid_df.index)
    metrics = calculate_metrics(valid_df[target_column], valid_prob)
    metrics["model_version"] = config["model"]["version"]
    metrics["asset_type"] = config["model"]["asset_type"]
    metrics["target_column"] = target_column
    metrics["train_rows"] = int(len(fit_df))
    metrics["train_rows_before_calibration_split"] = int(len(train_df))
    metrics["calibration_rows"] = calibration_rows
    metrics["valid_rows"] = int(len(valid_df))
    metrics["train_start_date"] = str(fit_df["date"].min())
    metrics["train_end_date"] = str(fit_df["date"].max())
    metrics["valid_start_date"] = str(valid_df["date"].min())
    metrics["valid_end_date"] = str(valid_df["date"].max())
    metrics["feature_columns"] = feature_columns
    metrics["class_weight_mode"] = class_weight_mode
    metrics["balance_symbol_weights"] = balance_symbols
    metrics["used_scale_pos_weight"] = bool(training_options.get("use_scale_pos_weight"))
    metrics["probability_calibration"] = bool(calibrator is not None)

    cv_metrics: list[dict] = []
    for fold_number, (train_dates, fold_valid_dates) in enumerate(
        build_time_series_folds(df["date"], cv_splits),
        start=1,
    ):
        fold_train_df = df[pd.to_datetime(df["date"]).isin(train_dates)].copy()
        fold_valid_df = df[pd.to_datetime(df["date"]).isin(fold_valid_dates)].copy()
        if fold_train_df.empty or fold_valid_df.empty:
            continue

        fold_model = LGBMClassifier(
            random_state=int(config["model"]["random_state"]),
            **lightgbm_params,
        )
        fold_weights = build_sample_weights(
            fold_train_df,
            target_column=target_column,
            class_weight_mode=class_weight_mode,
            balance_symbols=balance_symbols,
        )
        fold_model.fit(
            fold_train_df[feature_columns],
            fold_train_df[target_column],
            sample_weight=fold_weights,
        )
        fold_prob = fold_model.predict_proba(fold_valid_df[feature_columns])[:, 1]
        fold_metric = calculate_metrics(fold_valid_df[target_column], pd.Series(fold_prob))
        fold_metric["fold"] = fold_number
        fold_metric["train_rows"] = int(len(fold_train_df))
        fold_metric["valid_rows"] = int(len(fold_valid_df))
        fold_metric["valid_start_date"] = str(fold_valid_df["date"].min())
        fold_metric["valid_end_date"] = str(fold_valid_df["date"].max())
        cv_metrics.append(fold_metric)

    if cv_metrics:
        cv_frame = pd.DataFrame(cv_metrics)
        metrics["time_series_cv"] = cv_metrics
        metrics["time_series_cv_average"] = {
            "accuracy": float(cv_frame["accuracy"].mean()),
            "average_precision": float(cv_frame["average_precision"].mean()),
            "precision": float(cv_frame["precision"].mean()),
            "recall": float(cv_frame["recall"].mean()),
            "precision_at_top_10pct": float(cv_frame["precision_at_top_10pct"].mean()),
            "roc_auc": float(cv_frame["roc_auc"].dropna().mean()) if cv_frame["roc_auc"].notna().any() else None,
        }

    model_path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(
        {
            "model": model,
            "calibrator": calibrator,
            "config": config,
            "metrics": metrics,
        },
        model_path,
    )
    metrics_path.write_text(json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"모델 저장 완료: {model_path}")
    print(json.dumps(metrics, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
