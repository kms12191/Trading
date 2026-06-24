import argparse
from pathlib import Path

import numpy as np
import pandas as pd
import yaml


def load_config(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as file:
        return yaml.safe_load(file)


def calculate_rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.rolling(period, min_periods=period).mean()
    avg_loss = loss.rolling(period, min_periods=period).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    rename_map = {
        "candle_date": "date",
        "candle_time": "date",
        "open_price": "open",
        "high_price": "high",
        "low_price": "low",
        "close_price": "close",
    }
    return df.rename(columns={key: value for key, value in rename_map.items() if key in df.columns})


def build_features(candles: pd.DataFrame, config: dict) -> pd.DataFrame:
    required_columns = {"symbol", "date", "open", "high", "low", "close", "volume"}
    missing_columns = required_columns - set(candles.columns)
    if missing_columns:
        raise ValueError(f"필수 컬럼이 없습니다: {sorted(missing_columns)}")

    horizon_periods = int(config["model"]["horizon_periods"])
    up_threshold = float(config["model"]["up_return_threshold"])
    risk_threshold = float(config["model"]["risk_return_threshold"])

    candles = candles.copy()
    candles["date"] = pd.to_datetime(candles["date"])
    candles = candles.sort_values(["symbol", "date"]).reset_index(drop=True)

    frames = []
    for symbol, group in candles.groupby("symbol", sort=False):
        group = group.sort_values("date").copy()
        close = group["close"].astype(float)
        volume = group["volume"].astype(float)

        for period in [1, 3, 4, 5, 10, 12, 20, 24]:
            group[f"return_{period}"] = close.pct_change(period)

        for period in [4, 5, 20, 24]:
            group[f"ma_{period}_gap"] = close / close.rolling(period, min_periods=period).mean() - 1
            group[f"volume_ratio_{period}"] = volume / volume.rolling(period, min_periods=period).mean()
            group[f"volatility_{period}"] = group["return_1"].rolling(period, min_periods=period).std()

        group["rsi_14"] = calculate_rsi(close, 14)
        future_close = close.shift(-horizon_periods)
        group["future_return"] = future_close / close - 1
        group["up_label"] = (group["future_return"] >= up_threshold).astype(int)
        group["risk_label"] = (group["future_return"] <= risk_threshold).astype(int)
        group["horizon_periods"] = horizon_periods
        group["symbol"] = symbol
        frames.append(group)

    features = pd.concat(frames, ignore_index=True)
    feature_columns = config["model"]["feature_columns"]
    output_columns = [
        "exchange",
        "asset_type",
        "market_country",
        "currency",
        "symbol",
        "date",
        "horizon_periods",
        "future_return",
        "up_label",
        "risk_label",
        *feature_columns,
    ]
    output_columns = [column for column in output_columns if column in features.columns]
    features = features[output_columns].dropna().reset_index(drop=True)
    features["date"] = pd.to_datetime(features["date"]).dt.strftime("%Y-%m-%d %H:%M:%S")
    return features


def main() -> None:
    parser = argparse.ArgumentParser(description="LightGBM 피처와 라벨을 생성합니다.")
    parser.add_argument("--config", default="configs/lgbm_stock_v1.yaml", help="학습 설정 파일 경로")
    args = parser.parse_args()

    config = load_config(args.config)
    raw_path = Path(config["data"]["raw_candles_path"])
    output_path = Path(config["data"]["features_path"])

    candles = pd.read_csv(raw_path)
    candles = normalize_columns(candles)
    features = build_features(candles, config)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    features.to_csv(output_path, index=False)
    print(f"피처 파일 생성 완료: {output_path} ({len(features):,} rows)")


if __name__ == "__main__":
    main()
