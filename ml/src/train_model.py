import argparse
import json
from pathlib import Path

import joblib
import pandas as pd
import yaml
from lightgbm import LGBMClassifier
from sklearn.metrics import accuracy_score, average_precision_score, roc_auc_score


def load_config(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as file:
        return yaml.safe_load(file)


def split_by_time(df: pd.DataFrame, validation_ratio: float) -> tuple[pd.DataFrame, pd.DataFrame]:
    dates = pd.Series(pd.to_datetime(df["date"]).sort_values().unique())
    split_index = max(1, int(len(dates) * (1 - validation_ratio)))
    split_date = dates.iloc[split_index - 1]
    train_df = df[pd.to_datetime(df["date"]) <= split_date].copy()
    valid_df = df[pd.to_datetime(df["date"]) > split_date].copy()
    if train_df.empty or valid_df.empty:
        raise ValueError("시계열 검증 분할 결과가 비어 있습니다. 데이터 기간을 늘려주세요.")
    return train_df, valid_df


def calculate_metrics(y_true: pd.Series, y_prob: pd.Series) -> dict:
    y_pred = (y_prob >= 0.5).astype(int)
    metrics = {
        "accuracy": float(accuracy_score(y_true, y_pred)),
        "average_precision": float(average_precision_score(y_true, y_prob)),
    }
    metrics["roc_auc"] = float(roc_auc_score(y_true, y_prob)) if y_true.nunique() > 1 else None
    return metrics


def main() -> None:
    parser = argparse.ArgumentParser(description="LightGBM 신호 모델을 학습합니다.")
    parser.add_argument("--config", default="configs/lgbm_stock_v1.yaml", help="학습 설정 파일 경로")
    args = parser.parse_args()

    config = load_config(args.config)
    features_path = Path(config["data"]["features_path"])
    model_path = Path(config["model"]["output_path"])
    metrics_path = model_path.with_suffix(".metrics.json")

    df = pd.read_csv(features_path)
    feature_columns = config["model"]["feature_columns"]
    target_column = config["model"]["target_column"]
    train_df, valid_df = split_by_time(df, float(config["model"]["validation_ratio"]))

    model = LGBMClassifier(
        random_state=int(config["model"]["random_state"]),
        **config["lightgbm"],
    )
    model.fit(train_df[feature_columns], train_df[target_column])

    valid_prob = pd.Series(model.predict_proba(valid_df[feature_columns])[:, 1], index=valid_df.index)
    metrics = calculate_metrics(valid_df[target_column], valid_prob)
    metrics["model_version"] = config["model"]["version"]
    metrics["asset_type"] = config["model"]["asset_type"]
    metrics["train_rows"] = int(len(train_df))
    metrics["valid_rows"] = int(len(valid_df))
    metrics["train_start_date"] = str(train_df["date"].min())
    metrics["train_end_date"] = str(train_df["date"].max())
    metrics["valid_start_date"] = str(valid_df["date"].min())
    metrics["valid_end_date"] = str(valid_df["date"].max())
    metrics["feature_columns"] = feature_columns

    model_path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump({"model": model, "config": config, "metrics": metrics}, model_path)
    metrics_path.write_text(json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"모델 저장 완료: {model_path}")
    print(json.dumps(metrics, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
