import math
from typing import Any

import numpy as np
import pandas as pd
from sklearn.metrics import (
    accuracy_score,
    average_precision_score,
    confusion_matrix,
    precision_score,
    recall_score,
    roc_auc_score,
)


def split_by_time(df: pd.DataFrame, validation_ratio: float) -> tuple[pd.DataFrame, pd.DataFrame]:
    dates = pd.Series(pd.to_datetime(df["date"]).sort_values().unique())
    split_index = max(1, int(len(dates) * (1 - validation_ratio)))
    split_date = dates.iloc[split_index - 1]
    train_df = df[pd.to_datetime(df["date"]) <= split_date].copy()
    valid_df = df[pd.to_datetime(df["date"]) > split_date].copy()
    if train_df.empty or valid_df.empty:
        raise ValueError("시계열 검증 분할 결과가 비어 있습니다. 데이터 기간을 늘려주세요.")
    return train_df, valid_df


def split_train_calibration(
    train_df: pd.DataFrame,
    calibration_ratio: float,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    if calibration_ratio <= 0:
        return train_df, pd.DataFrame()

    dates = pd.Series(pd.to_datetime(train_df["date"]).sort_values().unique())
    calibration_size = max(1, int(len(dates) * calibration_ratio))
    if calibration_size >= len(dates):
        calibration_size = max(1, len(dates) // 5)
    calibration_dates = set(dates.iloc[-calibration_size:])
    base_train_df = train_df[~pd.to_datetime(train_df["date"]).isin(calibration_dates)].copy()
    calibration_df = train_df[pd.to_datetime(train_df["date"]).isin(calibration_dates)].copy()
    if base_train_df.empty or calibration_df.empty:
        return train_df, pd.DataFrame()
    return base_train_df, calibration_df


def compute_scale_pos_weight(y: pd.Series) -> float:
    positives = int((y == 1).sum())
    negatives = int((y == 0).sum())
    if positives == 0 or negatives == 0:
        return 1.0
    return max(1.0, negatives / positives)


def build_sample_weights(
    df: pd.DataFrame,
    target_column: str,
    class_weight_mode: str = "none",
    balance_symbols: bool = False,
) -> np.ndarray | None:
    weights = np.ones(len(df), dtype=float)
    enabled = False

    if class_weight_mode == "balanced":
        positive_count = max(1, int((df[target_column] == 1).sum()))
        negative_count = max(1, int((df[target_column] == 0).sum()))
        total_count = positive_count + negative_count
        positive_weight = total_count / (2 * positive_count)
        negative_weight = total_count / (2 * negative_count)
        weights *= np.where(df[target_column].to_numpy() == 1, positive_weight, negative_weight)
        enabled = True

    if balance_symbols and "symbol" in df.columns:
        symbol_counts = df["symbol"].value_counts()
        symbol_weights = df["symbol"].map(lambda symbol: 1.0 / math.sqrt(float(symbol_counts.get(symbol, 1))))
        mean_weight = float(symbol_weights.mean()) if len(symbol_weights) else 1.0
        if mean_weight > 0:
            weights *= (symbol_weights / mean_weight).to_numpy()
            enabled = True

    return weights if enabled else None


def apply_probability_calibration(probabilities: np.ndarray, calibrator: Any | None) -> np.ndarray:
    if calibrator is None:
        return probabilities
    calibrated = calibrator.predict_proba(np.asarray(probabilities).reshape(-1, 1))[:, 1]
    return np.clip(calibrated, 1e-6, 1 - 1e-6)


def precision_at_top_k(y_true: pd.Series, y_prob: pd.Series, ratio: float = 0.1) -> float:
    if len(y_true) == 0:
        return 0.0
    k = max(1, int(math.ceil(len(y_true) * ratio)))
    ranked = pd.DataFrame({"y_true": y_true, "y_prob": y_prob}).sort_values("y_prob", ascending=False)
    return float(ranked.head(k)["y_true"].mean())


def calculate_metrics(y_true: pd.Series, y_prob: pd.Series) -> dict[str, Any]:
    y_pred = (y_prob >= 0.5).astype(int)
    tn, fp, fn, tp = confusion_matrix(y_true, y_pred, labels=[0, 1]).ravel()
    metrics = {
        "accuracy": float(accuracy_score(y_true, y_pred)),
        "average_precision": float(average_precision_score(y_true, y_prob)),
        "precision": float(precision_score(y_true, y_pred, zero_division=0)),
        "recall": float(recall_score(y_true, y_pred, zero_division=0)),
        "precision_at_top_10pct": precision_at_top_k(y_true, y_prob, 0.1),
        "confusion_matrix": {
            "tn": int(tn),
            "fp": int(fp),
            "fn": int(fn),
            "tp": int(tp),
        },
    }
    metrics["roc_auc"] = float(roc_auc_score(y_true, y_prob)) if y_true.nunique() > 1 else None
    return metrics


def build_time_series_folds(dates: pd.Series, n_splits: int) -> list[tuple[pd.Series, pd.Series]]:
    unique_dates = pd.Series(pd.to_datetime(dates).sort_values().unique())
    if len(unique_dates) < n_splits + 1:
        return []

    fold_size = max(1, len(unique_dates) // (n_splits + 1))
    folds: list[tuple[pd.Series, pd.Series]] = []
    for fold_index in range(1, n_splits + 1):
        train_end = fold_size * fold_index
        valid_end = fold_size * (fold_index + 1)
        train_dates = unique_dates.iloc[:train_end]
        valid_dates = unique_dates.iloc[train_end:valid_end]
        if train_dates.empty or valid_dates.empty:
            continue
        folds.append((train_dates, valid_dates))
    return folds


def calculate_max_drawdown(returns: pd.Series) -> float:
    if returns.empty:
        return 0.0
    cumulative = (1 + returns.fillna(0.0)).cumprod()
    rolling_peak = cumulative.cummax()
    drawdown = cumulative / rolling_peak - 1
    return float(drawdown.min())
