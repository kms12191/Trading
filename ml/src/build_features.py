import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

# 프로젝트 루트를 sys.path에 추가 (symbol_metadata 로드를 위해)
PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))

try:
    from backend.services.symbol_metadata import SYMBOL_METADATA
except ImportError:
    SYMBOL_METADATA = {}


def load_config(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as file:
        return yaml.safe_load(file)


def resolve_ml_path(config_path: str, target_path: str) -> Path:
    base_dir = Path(config_path).resolve().parent.parent
    path = Path(target_path)
    return path if path.is_absolute() else base_dir / path


def calculate_rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.rolling(period, min_periods=period).mean()
    avg_loss = loss.rolling(period, min_periods=period).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def calculate_atr(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.Series:
    prev_close = close.shift(1)
    true_range = pd.concat(
        [
            (high - low).abs(),
            (high - prev_close).abs(),
            (low - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    atr = true_range.rolling(period, min_periods=1).mean()
    return atr / close.replace(0, np.nan)


def calculate_bollinger_position(close: pd.Series, period: int = 20, num_std: float = 2.0) -> pd.Series:
    moving_average = close.rolling(period, min_periods=1).mean()
    moving_std = close.rolling(period, min_periods=1).std().fillna(0.0)
    upper_band = moving_average + (moving_std * num_std)
    lower_band = moving_average - (moving_std * num_std)
    band_width = (upper_band - lower_band).replace(0, np.nan)
    return ((close - lower_band) / band_width).clip(lower=0, upper=1)


def calculate_macd(close: pd.Series) -> tuple[pd.Series, pd.Series, pd.Series]:
    ema_12 = close.ewm(span=12, adjust=False).mean()
    ema_26 = close.ewm(span=26, adjust=False).mean()
    macd_line = ema_12 - ema_26
    signal_line = macd_line.ewm(span=9, adjust=False).mean()
    histogram = macd_line - signal_line
    return macd_line, signal_line, histogram


def rolling_zscore(series: pd.Series, window: int) -> pd.Series:
    rolling_mean = series.rolling(window, min_periods=1).mean()
    rolling_std = series.rolling(window, min_periods=1).std().replace(0, np.nan)
    return (series - rolling_mean) / rolling_std


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


def load_optional_feature_source(path: Path, asset_type: str, default_columns: list[str]) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame(columns=["symbol", "date_merge_key", *default_columns])

    raw_df = pd.read_csv(path)
    if raw_df.empty:
        return pd.DataFrame(columns=["symbol", "date_merge_key", *default_columns])

    raw_df = normalize_columns(raw_df)
    if "date" not in raw_df.columns:
        raise ValueError(f"선택 피처 파일에 date 컬럼이 없습니다: {path}")

    raw_df["date"] = pd.to_datetime(raw_df["date"])
    if "symbol" not in raw_df.columns:
        raw_df["symbol"] = "__ALL__"

    if asset_type.upper() == "CRYPTO":
        raw_df["date_merge_key"] = raw_df["date"].dt.floor("h").dt.strftime("%Y-%m-%d %H:00:00")
    else:
        raw_df["date_merge_key"] = raw_df["date"].dt.strftime("%Y-%m-%d")

    keep_columns = ["symbol", "date_merge_key", *[column for column in default_columns if column in raw_df.columns]]
    return raw_df[keep_columns].drop_duplicates(subset=["symbol", "date_merge_key"], keep="last")


def build_macro_features() -> pd.DataFrame:
    macro_path = PROJECT_ROOT / "ml" / "data" / "raw" / "macro_indices.csv"
    if not macro_path.exists():
        return pd.DataFrame()

    macro_raw = pd.read_csv(macro_path)
    if macro_raw.empty:
        return pd.DataFrame()

    macro_raw["date"] = pd.to_datetime(macro_raw["date"])
    macro_raw["date_ymd"] = macro_raw["date"].dt.strftime("%Y-%m-%d")
    macro_frames = []
    for macro_symbol, group in macro_raw.groupby("symbol"):
        group = group.sort_values("date").copy()
        close = group["close"].astype(float)
        group[f"macro_{macro_symbol}_return_1"] = close.pct_change(1)
        group[f"macro_{macro_symbol}_return_3"] = close.pct_change(3)
        group[f"macro_{macro_symbol}_return_5"] = close.pct_change(5)
        group[f"macro_{macro_symbol}_return_10"] = close.pct_change(10)
        group[f"macro_{macro_symbol}_ma_20_gap"] = close / close.rolling(20, min_periods=1).mean() - 1
        keep_columns = [
            "date_ymd",
            f"macro_{macro_symbol}_return_1",
            f"macro_{macro_symbol}_return_3",
            f"macro_{macro_symbol}_return_5",
            f"macro_{macro_symbol}_return_10",
            f"macro_{macro_symbol}_ma_20_gap",
        ]
        macro_frames.append(group[keep_columns].drop_duplicates(subset=["date_ymd"], keep="last").set_index("date_ymd"))
    return pd.concat(macro_frames, axis=1).reset_index() if macro_frames else pd.DataFrame()


def apply_optional_features(features: pd.DataFrame, config: dict) -> pd.DataFrame:
    asset_type = str(config["model"]["asset_type"]).upper()

    news_defaults = [
        "news_sentiment",
        "news_article_count_24h",
        "news_burst_zscore",
        "negative_keyword_ratio",
    ]
    news_path = PROJECT_ROOT / "ml" / "data" / "raw" / "news_features.csv"
    news_df = load_optional_feature_source(news_path, asset_type, news_defaults)
    if not news_df.empty:
        merged = pd.merge(
            features,
            news_df,
            on=["symbol", "date_merge_key"],
            how="left",
        )
        features = merged

        global_news_df = news_df[news_df["symbol"] == "__ALL__"]
        if not global_news_df.empty:
            global_news_df = global_news_df.rename(
                columns={column: f"market_{column}" for column in news_defaults if column in global_news_df.columns}
            )
            features = pd.merge(
                features,
                global_news_df.drop(columns=["symbol"]),
                on="date_merge_key",
                how="left",
            )

    if asset_type == "CRYPTO":
        crypto_defaults = [
            "funding_rate",
            "open_interest",
            "open_interest_change_24h",
            "coinone_binance_spread",
            "kimchi_premium",
            "leader_btc_dominance_proxy",
        ]
        crypto_path = PROJECT_ROOT / "ml" / "data" / "raw" / "crypto_market_features.csv"
        crypto_df = load_optional_feature_source(crypto_path, asset_type, crypto_defaults)
        if not crypto_df.empty:
            features = pd.merge(features, crypto_df, on=["symbol", "date_merge_key"], how="left")

    if asset_type == "STOCK":
        stock_defaults = [
            "warning_flag",
            "price_limit_proximity",
            "turnover_ratio",
            "market_open_flag",
        ]
        stock_path = PROJECT_ROOT / "ml" / "data" / "raw" / "stock_event_features.csv"
        stock_df = load_optional_feature_source(stock_path, asset_type, stock_defaults)
        if not stock_df.empty:
            features = pd.merge(features, stock_df, on=["symbol", "date_merge_key"], how="left")

    return features


def build_features(candles: pd.DataFrame, config: dict) -> pd.DataFrame:
    required_columns = {"symbol", "date", "open", "high", "low", "close", "volume"}
    missing_columns = required_columns - set(candles.columns)
    if missing_columns:
        raise ValueError(f"필수 컬럼이 없습니다: {sorted(missing_columns)}")

    horizon_periods = int(config["model"]["horizon_periods"])
    up_threshold = float(config["model"]["up_return_threshold"])
    risk_threshold = float(config["model"]["risk_return_threshold"])
    neutral_zone_abs_return = float(config.get("labels", {}).get("neutral_zone_abs_return", 0.0))
    drop_neutral_samples = bool(config.get("labels", {}).get("drop_neutral_samples", False))

    candles = candles.copy()
    candles["date"] = pd.to_datetime(candles["date"])
    candles = candles.sort_values(["symbol", "date"]).reset_index(drop=True)
    candles["date_ymd"] = candles["date"].dt.strftime("%Y-%m-%d")
    asset_type = str(config["model"]["asset_type"]).upper()
    candles["date_merge_key"] = (
        candles["date"].dt.floor("h").dt.strftime("%Y-%m-%d %H:00:00")
        if asset_type == "CRYPTO"
        else candles["date"].dt.strftime("%Y-%m-%d")
    )

    macro_df = build_macro_features()

    frames = []
    for symbol, group in candles.groupby("symbol", sort=False):
        group = group.sort_values("date").copy()
        close = group["close"].astype(float)
        open_price = group["open"].astype(float)
        high = group["high"].astype(float)
        low = group["low"].astype(float)
        volume = group["volume"].astype(float)

        for period in [1, 3, 4, 5, 10, 12, 20, 24]:
            group[f"return_{period}"] = close.pct_change(period)

        for period in [4, 5, 20, 24]:
            group[f"ma_{period}_gap"] = close / close.rolling(period, min_periods=1).mean() - 1
            group[f"volume_ratio_{period}"] = volume / volume.rolling(period, min_periods=1).mean()
            group[f"volatility_{period}"] = group["return_1"].rolling(period, min_periods=1).std()

        group["rsi_14"] = calculate_rsi(close, 14)
        group["atr_14"] = calculate_atr(high, low, close, 14)
        group["bollinger_position_20"] = calculate_bollinger_position(close, 20)
        group["range_ratio_1"] = (high - low) / close.replace(0, np.nan)
        group["close_to_high_20"] = close / high.rolling(20, min_periods=1).max() - 1
        group["close_to_low_20"] = close / low.rolling(20, min_periods=1).min() - 1
        group["body_ratio_1"] = (close - open_price).abs() / close.replace(0, np.nan)
        group["upper_wick_ratio_1"] = (high - np.maximum(open_price, close)) / close.replace(0, np.nan)
        group["lower_wick_ratio_1"] = (np.minimum(open_price, close) - low) / close.replace(0, np.nan)
        group["intraday_return"] = close / open_price.replace(0, np.nan) - 1

        amount = close * volume
        group["amount_zscore_20"] = rolling_zscore(amount, 20)
        group["amount_zscore_24"] = rolling_zscore(amount, 24)
        group["volume_zscore_20"] = rolling_zscore(volume, 20)
        group["volume_zscore_24"] = rolling_zscore(volume, 24)

        macd_line, macd_signal, macd_hist = calculate_macd(close)
        group["macd_line"] = macd_line / close.replace(0, np.nan)
        group["macd_signal"] = macd_signal / close.replace(0, np.nan)
        group["macd_hist"] = macd_hist / close.replace(0, np.nan)

        future_close = close.shift(-horizon_periods)
        group["future_return"] = future_close / close - 1
        group["up_label"] = (group["future_return"] >= up_threshold).astype(int)
        group["risk_label"] = (group["future_return"] <= risk_threshold).astype(int)
        group["neutral_label"] = (group["future_return"].abs() < neutral_zone_abs_return).astype(int)
        group["horizon_periods"] = horizon_periods
        group["symbol"] = symbol

        if asset_type == "CRYPTO":
            group["hour_of_day"] = group["date"].dt.hour
            group["day_of_week"] = group["date"].dt.dayofweek
            group["is_weekend"] = group["day_of_week"].isin([5, 6]).astype(int)
        else:
            group["day_of_week"] = group["date"].dt.dayofweek
            group["is_us_asset"] = int(symbol.isalpha())
            group["is_kr_asset"] = int(not symbol.isalpha())

        frames.append(group)

    features = pd.concat(frames, ignore_index=True)

    if not macro_df.empty:
        features = pd.merge(features, macro_df, on="date_ymd", how="left")
    for period in [3, 5, 10]:
        if f"macro_USDKRW_return_{period}" not in features.columns:
            features[f"macro_USDKRW_return_{period}"] = np.nan
        features[f"usdkrw_return_{period}"] = features[f"macro_USDKRW_return_{period}"]

        def calc_relative_return(row: pd.Series) -> float:
            symbol = row["symbol"]
            country = row.get("market_country") or ("US" if symbol.isalpha() else "KR")
            market_index = "NASDAQ" if country == "US" else "KOSPI"
            macro_ret_col = f"macro_{market_index}_return_{period}"
            if macro_ret_col in row and pd.notna(row[macro_ret_col]):
                return row[f"return_{period}"] - row[macro_ret_col]
            return np.nan

        features[f"relative_return_{period}"] = features.apply(calc_relative_return, axis=1)

    features["sector"] = features["symbol"].map(lambda sym: SYMBOL_METADATA.get(sym, {}).get("sector", "Unknown"))
    sector_means = (
        features.groupby(["date_ymd", "sector"])[["return_1", "return_3", "return_5", "return_10"]]
        .mean()
        .reset_index()
        .rename(
            columns={
                "return_1": "sector_return_1_mean",
                "return_3": "sector_return_3_mean",
                "return_5": "sector_return_5_mean",
                "return_10": "sector_return_10_mean",
            }
        )
    )
    features = pd.merge(features, sector_means, on=["date_ymd", "sector"], how="left")
    for period in [3, 5, 10]:
        features[f"sector_relative_return_{period}"] = features[f"return_{period}"] - features[f"sector_return_{period}_mean"]

    features = apply_optional_features(features, config)

    for column in [
        "news_sentiment",
        "news_article_count_24h",
        "news_burst_zscore",
        "negative_keyword_ratio",
        "market_news_sentiment",
        "market_news_article_count_24h",
        "market_news_burst_zscore",
        "market_negative_keyword_ratio",
        "funding_rate",
        "open_interest",
        "open_interest_change_24h",
        "coinone_binance_spread",
        "kimchi_premium",
        "leader_btc_dominance_proxy",
        "warning_flag",
        "price_limit_proximity",
        "turnover_ratio",
        "market_open_flag",
    ]:
        if column not in features.columns:
            features[column] = 0.0

    if asset_type == "CRYPTO":
        leader_symbols = {
            "BTCUSDT": [1, 4, 24],
            "ETHUSDT": [1, 4, 24],
        }

        for leader_symbol, periods in leader_symbols.items():
            leader_df = features[features["symbol"] == leader_symbol][["date", *[f"return_{period}" for period in periods]]].copy()
            rename_map = {f"return_{period}": f"{leader_symbol.lower()}_return_{period}" for period in periods}
            leader_df = leader_df.rename(columns=rename_map)
            features = pd.merge(features, leader_df, on="date", how="left")

        for column in ["btcusdt_return_4", "ethusdt_return_4", "btcusdt_return_1", "ethusdt_return_1", "btcusdt_return_24"]:
            if column not in features.columns:
                features[column] = 0.0

        features["relative_to_btc_return_4"] = features["return_4"] - features["btcusdt_return_4"]
        features["relative_to_eth_return_4"] = features["return_4"] - features["ethusdt_return_4"]
        market_returns = features.groupby("date")[["return_4", "return_24"]].mean().reset_index().rename(
            columns={
                "return_4": "crypto_market_return_4",
                "return_24": "crypto_market_return_24",
            }
        )
        features = pd.merge(features, market_returns, on="date", how="left")
        features["relative_to_market_return_4"] = features["return_4"] - features["crypto_market_return_4"]
        features["relative_to_market_return_24"] = features["return_24"] - features["crypto_market_return_24"]

    if drop_neutral_samples and neutral_zone_abs_return > 0:
        features = features[features["neutral_label"] == 0].copy()

    feature_columns = config["model"]["feature_columns"]
    for feature_column in feature_columns:
        if feature_column not in features.columns:
            features[feature_column] = 0.0
    features[feature_columns] = features[feature_columns].replace([np.inf, -np.inf], np.nan).fillna(0.0)

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
        "neutral_label",
        *feature_columns,
    ]
    output_columns = [column for column in output_columns if column in features.columns]
    features = features[output_columns].dropna(subset=["future_return"]).reset_index(drop=True)
    features["date"] = pd.to_datetime(features["date"]).dt.strftime("%Y-%m-%d %H:%M:%S")
    return features


def main() -> None:
    parser = argparse.ArgumentParser(description="LightGBM 피처와 라벨을 생성합니다.")
    parser.add_argument("--config", default="configs/lgbm_stock_v1.yaml", help="학습 설정 파일 경로")
    args = parser.parse_args()

    config = load_config(args.config)
    raw_path = resolve_ml_path(args.config, config["data"]["raw_candles_path"])
    output_path = resolve_ml_path(args.config, config["data"]["features_path"])

    candles = pd.read_csv(raw_path)
    candles = normalize_columns(candles)
    features = build_features(candles, config)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    features.to_csv(output_path, index=False)
    print(f"피처 파일 생성 완료: {output_path} ({len(features):,} rows)")


if __name__ == "__main__":
    main()
