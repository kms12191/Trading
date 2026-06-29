import os
import argparse
import json
import sys
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import yaml

os.environ.setdefault("LOKY_MAX_CPU_COUNT", str(os.cpu_count() or 1))

from lightgbm import LGBMClassifier
from sklearn.linear_model import LogisticRegression, Ridge

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


def read_features_csv(path: Path) -> pd.DataFrame:
    """종목코드 문자열 보존을 위해 symbol dtype을 고정합니다."""
    return pd.read_csv(path, dtype={"symbol": "string"}, low_memory=False)


def main() -> None:
    parser = argparse.ArgumentParser(description="LightGBM 신호 모델을 학습합니다.")
    parser.add_argument("--config", default="configs/lgbm_stock_v1.yaml", help="학습 설정 파일 경로")
    args = parser.parse_args()

    config = load_config(args.config)
    features_path = resolve_ml_path(args.config, config["data"]["features_path"])
    model_path = resolve_ml_path(args.config, config["model"]["output_path"])
    metrics_path = model_path.with_suffix(".metrics.json")

    df = read_features_csv(features_path)
    feature_columns = config["model"]["feature_columns"]
    target_column = config["model"]["target_column"]
    train_df, valid_df = split_by_time(df, float(config["model"]["validation_ratio"]))

    training_options = config.get("training", {})
    class_weight_mode = str(training_options.get("class_weight_mode", "none"))
    balance_symbols = bool(training_options.get("balance_symbol_weights", False))
    calibration_enabled = bool(training_options.get("enable_probability_calibration", False))
    calibration_ratio = float(training_options.get("calibration_ratio", 0.1))
    cv_splits = int(training_options.get("time_series_cv_splits", 0))
    # 앙상블 설정: Ridge + LightGBM 가중 평균 (v8+)
    use_ensemble = bool(training_options.get("use_ensemble", False))
    ensemble_lgbm_weight = float(training_options.get("ensemble_lgbm_weight", 0.7))
    ensemble_ridge_weight = float(training_options.get("ensemble_ridge_weight", 0.3))

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

    # Ridge 앙상블 학습: 피처 스케일 정규화 후 L2 선형 모델 학습 (v8+)
    ridge_model = None
    if use_ensemble:
        try:
            from sklearn.preprocessing import StandardScaler
            scaler = StandardScaler()
            x_scaled = scaler.fit_transform(fit_df[feature_columns].fillna(0.0))
            ridge_model = Ridge(
                alpha=1.0,
                random_state=int(config["model"]["random_state"]),
            )
            ridge_model.fit(x_scaled, fit_df[target_column].astype(float))
            # Ridge 스케일러도 함께 저장해야 예측 시 동일 변환 적용 가능
            ridge_model._feature_scaler = scaler
        except Exception:
            ridge_model = None

    calibrator = None
    calibration_rows = 0
    if calibration_enabled and not calibration_df.empty:
        calibration_prob = model.predict_proba(calibration_df[feature_columns])[:, 1]
        # 앙상블 활성화 시: Ridge 예측도 가중 평균에 포함한 뒤 보정기 학습
        if use_ensemble and ridge_model is not None:
            try:
                scaler = ridge_model._feature_scaler
                x_cal_scaled = scaler.transform(calibration_df[feature_columns].fillna(0.0))
                ridge_prob = np.clip(ridge_model.predict(x_cal_scaled), 0.0, 1.0)
                calibration_prob = (
                    ensemble_lgbm_weight * calibration_prob
                    + ensemble_ridge_weight * ridge_prob
                )
            except Exception:
                pass
        calibrator = LogisticRegression(random_state=int(config["model"]["random_state"]), max_iter=1000)
        calibrator.fit(calibration_prob.reshape(-1, 1), calibration_df[target_column])
        calibration_rows = int(len(calibration_df))

    valid_prob = model.predict_proba(valid_df[feature_columns])[:, 1]
    # 앙상블 활성화 시: 검증 확률에도 Ridge 가중 평균 적용
    if use_ensemble and ridge_model is not None:
        try:
            scaler = ridge_model._feature_scaler
            x_val_scaled = scaler.transform(valid_df[feature_columns].fillna(0.0))
            ridge_valid_prob = np.clip(ridge_model.predict(x_val_scaled), 0.0, 1.0)
            valid_prob = (
                ensemble_lgbm_weight * valid_prob
                + ensemble_ridge_weight * ridge_valid_prob
            )
        except Exception:
            pass
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
    metrics["use_ensemble"] = use_ensemble
    metrics["ensemble_lgbm_weight"] = ensemble_lgbm_weight if use_ensemble else None
    metrics["ensemble_ridge_weight"] = ensemble_ridge_weight if use_ensemble else None
    metrics["ridge_model_trained"] = bool(use_ensemble and ridge_model is not None)

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
            # 앙상블 Ridge 모델 포함 저장 (use_ensemble=false 시 None)
            "ridge_model": ridge_model,
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
