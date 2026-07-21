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

DART_FEATURE_COLUMNS = [
    "dart_disclosure_count_3d",
    "dart_sentiment_sum_3d",
    "dart_negative_count_3d",
    "dart_positive_count_3d",
    "dart_caution_count_3d",
    "dart_summary_available_count_3d",
    "dart_summary_length_sum_3d",
    "dart_key_point_count_3d",
    "dart_risk_point_count_3d",
    "dart_check_item_count_3d",
    "dart_metric_count_3d",
    "dart_confidence_score_sum_3d",
    "dart_text_risk_keyword_count_3d",
    "dart_disclosure_count_7d",
    "dart_sentiment_sum_7d",
    "dart_negative_count_7d",
    "dart_positive_count_7d",
    "dart_caution_count_7d",
    "dart_summary_available_count_7d",
    "dart_summary_length_sum_7d",
    "dart_key_point_count_7d",
    "dart_risk_point_count_7d",
    "dart_check_item_count_7d",
    "dart_metric_count_7d",
    "dart_confidence_score_sum_7d",
    "dart_text_risk_keyword_count_7d",
    "dart_disclosure_count_20d",
    "dart_sentiment_sum_20d",
    "dart_negative_count_20d",
    "dart_positive_count_20d",
    "dart_caution_count_20d",
    "dart_summary_available_count_20d",
    "dart_summary_length_sum_20d",
    "dart_key_point_count_20d",
    "dart_risk_point_count_20d",
    "dart_check_item_count_20d",
    "dart_metric_count_20d",
    "dart_confidence_score_sum_20d",
    "dart_text_risk_keyword_count_20d",
    "dart_ai_analyzed_count_20d",
    "dart_contract_flag_20d",
    "dart_financing_flag_20d",
    "dart_shareholder_return_flag_20d",
    "dart_risk_event_flag_20d",
    "dart_earnings_flag_20d",
]


def load_config(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as file:
        return yaml.safe_load(file)


def resolve_ml_path(config_path: str, target_path: str) -> Path:
    base_dir = Path(config_path).resolve().parent.parent
    path = Path(target_path)
    return path if path.is_absolute() else base_dir / path


def normalize_symbol(symbol: object) -> str:
    if pd.isna(symbol):
        return ""
    text = str(symbol).strip().upper()
    if text.endswith(".0") and text[:-2].isdigit():
        text = text[:-2]
    if text.isdigit() and len(text) <= 6:
        return text.zfill(6)
    return text


def calculate_stochastic(high: pd.Series, low: pd.Series, close: pd.Series, k_period: int = 14, d_period: int = 3) -> tuple[pd.Series, pd.Series]:
    lowest_low = low.rolling(k_period, min_periods=k_period).min()
    highest_high = high.rolling(k_period, min_periods=k_period).max()
    denominator = highest_high - lowest_low
    stoch_k = 100 * (close - lowest_low) / denominator.replace(0, np.nan)
    stoch_k = stoch_k.fillna(50.0)
    stoch_d = stoch_k.rolling(d_period, min_periods=d_period).mean().fillna(50.0)
    return stoch_k, stoch_d


def calculate_obv(close: pd.Series, volume: pd.Series) -> pd.Series:
    close_diff = close.diff()
    direction = np.sign(close_diff).fillna(0.0)
    obv = (direction * volume).cumsum()
    return obv


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


def calculate_price_range_ratio(high: pd.Series, low: pd.Series, close: pd.Series, window: int) -> pd.Series:
    highest_high = high.rolling(window, min_periods=1).max()
    lowest_low = low.rolling(window, min_periods=1).min()
    return (highest_high - lowest_low) / close.replace(0, np.nan)


def calculate_consecutive_contraction_streak(series: pd.Series) -> pd.Series:
    streak_values: list[float] = []
    streak = 0
    previous_value = np.nan
    for value in series.tolist():
        if pd.notna(value) and pd.notna(previous_value) and value < previous_value:
            streak += 1
        else:
            streak = 0
        streak_values.append(float(streak))
        previous_value = value
    return pd.Series(streak_values, index=series.index, dtype=float)


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
    raw_df["symbol"] = raw_df["symbol"].map(normalize_symbol)

    if asset_type.upper() == "CRYPTO":
        raw_df["date_merge_key"] = raw_df["date"].dt.floor("h").dt.strftime("%Y-%m-%d %H:00:00")
    else:
        raw_df["date_merge_key"] = raw_df["date"].dt.strftime("%Y-%m-%d")

    keep_columns = ["symbol", "date_merge_key", *[column for column in default_columns if column in raw_df.columns]]
    return raw_df[keep_columns].drop_duplicates(subset=["symbol", "date_merge_key"], keep="last")


def resolve_optional_feature_path(config: dict, key: str, default_relative_path: str) -> Path:
    configured_path = (config.get("optional_features") or {}).get(key)
    if configured_path:
        path = Path(str(configured_path))
        return path if path.is_absolute() else PROJECT_ROOT / path
    return PROJECT_ROOT / default_relative_path


def is_kr_stock_dart_config(config: dict) -> bool:
    asset_type = str(config.get("model", {}).get("asset_type", "")).upper()
    optional_features = config.get("optional_features") or {}
    dart_features_path = optional_features.get("dart_features_path")
    if not dart_features_path:
        return False
    if asset_type != "STOCK":
        raise ValueError("DART 피처는 국내 주식(STOCK) 설정에서만 사용할 수 있습니다.")

    market_scope = str(
        config.get("market_scope")
        or config.get("data", {}).get("market_scope")
        or config.get("model", {}).get("market_scope")
        or config.get("market_country")
        or config.get("data", {}).get("market_country")
        or ""
    ).upper()
    if market_scope in {"KR", "KOREA", "DOMESTIC"}:
        return True
    if market_scope in {"US", "USA", "OVERSEAS", "GLOBAL"}:
        raise ValueError("DART 피처는 국내 주식 KR 설정에서만 사용할 수 있습니다.")

    model_version = str(config.get("model", {}).get("version", "")).lower()
    raw_candles_path = str(config.get("data", {}).get("raw_candles_path", "")).lower()
    features_path = str(config.get("data", {}).get("features_path", "")).lower()
    marker_values = [model_version, raw_candles_path, features_path]
    if any(marker in value for marker in ("us_stock", "overseas_stock") for value in marker_values):
        raise ValueError("DART 피처는 국내 주식 KR 설정에서만 사용할 수 있습니다.")
    return True


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
        return_1 = close.pct_change(1)
        group[f"macro_{macro_symbol}_return_1"] = close.pct_change(1)
        group[f"macro_{macro_symbol}_return_3"] = close.pct_change(3)
        group[f"macro_{macro_symbol}_return_5"] = close.pct_change(5)
        group[f"macro_{macro_symbol}_return_10"] = close.pct_change(10)
        group[f"macro_{macro_symbol}_return_20"] = close.pct_change(20)
        group[f"macro_{macro_symbol}_return_60"] = close.pct_change(60)
        group[f"macro_{macro_symbol}_ma_20_gap"] = close / close.rolling(20, min_periods=1).mean() - 1
        group[f"macro_{macro_symbol}_ma_60_gap"] = close / close.rolling(60, min_periods=1).mean() - 1
        group[f"macro_{macro_symbol}_volatility_20"] = return_1.rolling(20, min_periods=1).std()
        group[f"macro_{macro_symbol}_drawdown_60"] = close / close.rolling(60, min_periods=1).max() - 1
        keep_columns = [
            "date_ymd",
            f"macro_{macro_symbol}_return_1",
            f"macro_{macro_symbol}_return_3",
            f"macro_{macro_symbol}_return_5",
            f"macro_{macro_symbol}_return_10",
            f"macro_{macro_symbol}_return_20",
            f"macro_{macro_symbol}_return_60",
            f"macro_{macro_symbol}_ma_20_gap",
            f"macro_{macro_symbol}_ma_60_gap",
            f"macro_{macro_symbol}_volatility_20",
            f"macro_{macro_symbol}_drawdown_60",
        ]
        macro_frames.append(group[keep_columns].drop_duplicates(subset=["date_ymd"], keep="last").set_index("date_ymd"))
    return pd.concat(macro_frames, axis=1).reset_index() if macro_frames else pd.DataFrame()


def apply_optional_features(features: pd.DataFrame, config: dict) -> pd.DataFrame:
    asset_type = str(config["model"]["asset_type"]).upper()
    use_dart_features = is_kr_stock_dart_config(config)

    news_defaults = [
        "news_sentiment",
        "news_article_count_24h",
        "news_burst_zscore",
        "negative_keyword_ratio",
    ]
    news_path = resolve_optional_feature_path(config, "news_features_path", "ml/data/raw/news_features.csv")
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
        crypto_path = resolve_optional_feature_path(config, "crypto_market_features_path", "ml/data/raw/crypto_market_features.csv")
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
        stock_path = resolve_optional_feature_path(config, "stock_event_features_path", "ml/data/raw/stock_event_features.csv")
        stock_df = load_optional_feature_source(stock_path, asset_type, stock_defaults)
        if not stock_df.empty:
            features = pd.merge(features, stock_df, on=["symbol", "date_merge_key"], how="left")

        if use_dart_features:
            dart_path = resolve_optional_feature_path(config, "dart_features_path", "ml/data/raw/dart_features.csv")
            dart_df = load_optional_feature_source(dart_path, asset_type, DART_FEATURE_COLUMNS)
            if not dart_df.empty:
                features = pd.merge(features, dart_df, on=["symbol", "date_merge_key"], how="left")

    return features


def build_features(candles: pd.DataFrame, config: dict, include_unlabeled: bool = False) -> pd.DataFrame:
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
    candles["symbol"] = candles["symbol"].map(normalize_symbol)
    if "market_country" in candles.columns:
        candles["market_country"] = candles["market_country"].astype(str).str.upper()
    candles = candles.sort_values(["symbol", "date"]).reset_index(drop=True)
    
    # 상장 연한 필터 (최소 영업일 730일 이상 확보된 종목만 남김)
    min_days = int(config.get("model", {}).get("min_listing_days", 730))
    symbol_counts = candles.groupby("symbol")["date"].count()
    valid_symbols = symbol_counts[symbol_counts >= min_days].index
    if len(valid_symbols) > 0:
        candles = candles[candles["symbol"].isin(valid_symbols)].copy()
    else:
        sys.stderr.write(f"Warning: All symbols filtered out by min_listing_days ({min_days}). Skipping filter to preserve data.\n")

    candles["date_ymd"] = candles["date"].dt.strftime("%Y-%m-%d")
    asset_type = str(config["model"]["asset_type"]).upper()
    # 30분 캔들 지원: CRYPTO는 30분 단위 내림으로 병합 키 생성 (1h 캔들도 호환)
    candles["date_merge_key"] = (
        candles["date"].dt.floor("30min").dt.strftime("%Y-%m-%d %H:%M:00")
        if asset_type == "CRYPTO"
        else candles["date"].dt.strftime("%Y-%m-%d")
    )

    macro_df = build_macro_features()

    frames = []
    for symbol, group in candles.groupby("symbol", sort=False):
        group = group.sort_values("date").copy()
        
        # 캔들 가격 데이터 결측치 전방 채움 (거래 정지 등 대비)
        group[["open", "high", "low", "close"]] = group[["open", "high", "low", "close"]].ffill()
        
        close = group["close"].astype(float)
        open_price = group["open"].astype(float)
        high = group["high"].astype(float)
        low = group["low"].astype(float)
        volume = group["volume"].astype(float)
        prev_close = close.shift(1)

        # horizon_periods를 명시적으로 포함해 라벨과 리더/시장 동조 피처의 시간축을 맞춥니다.
        for period in sorted({1, 3, 4, 5, horizon_periods, 10, 12, 20, 24, 48, 60}):
            group[f"return_{period}"] = close.pct_change(period)

        for period in [4, 5, 20, 24, 60]:
            group[f"ma_{period}_gap"] = close / close.rolling(period, min_periods=1).mean() - 1
            group[f"volume_ratio_{period}"] = volume / volume.rolling(period, min_periods=1).mean()
            group[f"volatility_{period}"] = group["return_1"].rolling(period, min_periods=1).std()

        group["rsi_14"] = calculate_rsi(close, 14)
        group["atr_14"] = calculate_atr(high, low, close, 14)
        group["bollinger_position_20"] = calculate_bollinger_position(close, 20)
        group["range_ratio_1"] = (high - low) / close.replace(0, np.nan)
        group["stoch_k_14"], group["stoch_d_3"] = calculate_stochastic(high, low, close, 14, 3)
        obv = calculate_obv(close, volume)
        group["obv_zscore_20"] = rolling_zscore(obv, 20)
        group["close_to_high_20"] = close / high.rolling(20, min_periods=1).max() - 1
        group["close_to_low_20"] = close / low.rolling(20, min_periods=1).min() - 1
        group["body_ratio_1"] = (close - open_price).abs() / close.replace(0, np.nan)
        group["upper_wick_ratio_1"] = (high - np.maximum(open_price, close)) / close.replace(0, np.nan)
        group["lower_wick_ratio_1"] = (np.minimum(open_price, close) - low) / close.replace(0, np.nan)
        group["intraday_return"] = close / open_price.replace(0, np.nan) - 1
        group["overnight_gap"] = open_price / prev_close.replace(0, np.nan) - 1
        prior_high_20 = high.shift(1).rolling(20, min_periods=1).max()
        prior_low_20 = low.shift(1).rolling(20, min_periods=1).min()
        group["breakout_strength_20"] = close / prior_high_20.replace(0, np.nan) - 1
        group["breakdown_strength_20"] = close / prior_low_20.replace(0, np.nan) - 1
        avg_range_20 = (high - low).rolling(20, min_periods=1).mean()
        group["abnormal_range_ratio_20"] = (high - low) / avg_range_20.replace(0, np.nan)
        group["reversal_strength_1"] = group["intraday_return"] - group["overnight_gap"]

        amount = close * volume
        group["amount_zscore_20"] = rolling_zscore(amount, 20)
        group["amount_zscore_24"] = rolling_zscore(amount, 24)
        group["volume_zscore_20"] = rolling_zscore(volume, 20)
        group["volume_zscore_24"] = rolling_zscore(volume, 24)

        range_ratio_5 = calculate_price_range_ratio(high, low, close, 5)
        range_ratio_10 = calculate_price_range_ratio(high, low, close, 10)
        range_ratio_20 = calculate_price_range_ratio(high, low, close, 20)
        range_ratio_40 = calculate_price_range_ratio(high, low, close, 40)
        group["vcp_contraction_ratio_5_20"] = range_ratio_5 / range_ratio_20.replace(0, np.nan)
        group["vcp_contraction_ratio_10_40"] = range_ratio_10 / range_ratio_40.replace(0, np.nan)
        group["vcp_volatility_ratio_10_40"] = (
            group["return_1"].rolling(10, min_periods=1).std()
            / group["return_1"].rolling(40, min_periods=1).std().replace(0, np.nan)
        )
        volume_ma_5 = volume.rolling(5, min_periods=1).mean()
        volume_ma_10 = volume.rolling(10, min_periods=1).mean()
        volume_ma_20 = volume.rolling(20, min_periods=1).mean()
        volume_ma_40 = volume.rolling(40, min_periods=1).mean()
        group["vcp_volume_dryup_ratio_5_20"] = volume_ma_5 / volume_ma_20.replace(0, np.nan)
        group["vcp_volume_dryup_ratio_10_40"] = volume_ma_10 / volume_ma_40.replace(0, np.nan)
        intraday_range = (high - low).replace(0, np.nan)
        close_location = ((close - low) / intraday_range).clip(lower=0, upper=1)
        group["vcp_tight_close_ratio_10"] = (close_location >= 0.7).astype(float).rolling(10, min_periods=1).mean()
        group["vcp_breakout_proximity_20"] = close / high.rolling(20, min_periods=1).max().replace(0, np.nan)
        group["vcp_contraction_streak"] = calculate_consecutive_contraction_streak(range_ratio_5)

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
        # 잔차 수익률 라벨은 market 수익률 차감 후 apply_residual_labels()에서 후처리 적용
        group["residual_up_label"] = group["up_label"]   # 임시: 나중에 잔차 기반으로 덮어씀
        group["residual_risk_label"] = group["risk_label"]  # 임시: 나중에 잔차 기반으로 덮어씀

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

    def resolve_symbol_metadata(symbol: object) -> dict:
        return SYMBOL_METADATA.get(normalize_symbol(symbol), {})

    features["market_country_group"] = features.apply(
        lambda row: (
            str(row.get("market_country", "")).upper()
            if str(row.get("market_country", "")).upper() in {"KR", "US"}
            else ("US" if str(row["symbol"]).isalpha() else "KR")
        ),
        axis=1,
    )
    features["sector"] = features["symbol"].map(lambda sym: resolve_symbol_metadata(sym).get("sector", "Unknown"))
    sector_means = (
        features.groupby(["date_ymd", "sector"])[["return_1", "return_3", "return_5", "return_10", "return_20"]]
        .mean()
        .reset_index()
        .rename(
            columns={
                "return_1": "sector_return_1_mean",
                "return_3": "sector_return_3_mean",
                "return_5": "sector_return_5_mean",
                "return_10": "sector_return_10_mean",
                "return_20": "sector_return_20_mean",
            }
        )
    )
    features = pd.merge(features, sector_means, on=["date_ymd", "sector"], how="left")
    for period in [3, 5, 10, 20]:
        features[f"sector_relative_return_{period}"] = features[f"return_{period}"] - features[f"sector_return_{period}_mean"]

    sector_context = (
        features.groupby(["date_ymd", "sector"])
        .agg(
            sector_breadth_1=("return_1", lambda values: float((values > 0).mean())),
            sector_breadth_3=("return_3", lambda values: float((values > 0).mean())),
            sector_breadth_5=("return_5", lambda values: float((values > 0).mean())),
            sector_above_ma20_ratio=("ma_20_gap", lambda values: float((values > 0).mean())),
            sector_breakout_ratio_20=("close_to_high_20", lambda values: float((values > -0.03).mean())),
            sector_volume_thrust_ratio=("volume_zscore_20", lambda values: float((values > 1.0).mean())),
        )
        .reset_index()
    )
    features = pd.merge(features, sector_context, on=["date_ymd", "sector"], how="left")
    features["sector_rank_pct_5"] = features.groupby("date_ymd")["sector_return_5_mean"].rank(pct=True, method="average")
    features["sector_rank_pct_20"] = features.groupby("date_ymd")["sector_return_20_mean"].rank(pct=True, method="average")

    market_context = (
        features.groupby(["date_ymd", "market_country_group"])
        .agg(
            market_avg_return_1=("return_1", "mean"),
            market_avg_return_3=("return_3", "mean"),
            market_avg_return_5=("return_5", "mean"),
            market_avg_return_10=("return_10", "mean"),
            market_avg_return_20=("return_20", "mean"),
            market_breadth_1=("return_1", lambda values: float((values > 0).mean())),
            market_breadth_3=("return_3", lambda values: float((values > 0).mean())),
            market_breadth_5=("return_5", lambda values: float((values > 0).mean())),
            market_above_ma20_ratio=("ma_20_gap", lambda values: float((values > 0).mean())),
            market_breakout_ratio_20=("close_to_high_20", lambda values: float((values > -0.03).mean())),
            market_volume_thrust_ratio=("volume_zscore_20", lambda values: float((values > 1.0).mean())),
        )
        .reset_index()
    )
    features = pd.merge(features, market_context, on=["date_ymd", "market_country_group"], how="left")

    for period in [3, 5, 10, 20]:
        features[f"market_excess_return_{period}"] = features[f"return_{period}"] - features[f"market_avg_return_{period}"]

    def select_market_column(row: pd.Series, suffix: str) -> float:
        market_symbol = "NASDAQ" if row["market_country_group"] == "US" else "KOSPI"
        return row.get(f"macro_{market_symbol}_{suffix}", np.nan)

    for suffix in [
        "return_3",
        "return_5",
        "return_10",
        "return_20",
        "ma_20_gap",
        "ma_60_gap",
        "volatility_20",
        "drawdown_60",
    ]:
        features[f"primary_market_{suffix}"] = features.apply(select_market_column, axis=1, suffix=suffix)

    features["market_regime_score"] = (
        (features["primary_market_ma_20_gap"] > 0).astype(float)
        + (features["primary_market_ma_60_gap"] > 0).astype(float)
        + (features["primary_market_return_20"] > 0).astype(float)
        + (features["market_breadth_5"] > 0.5).astype(float)
        + (features["sector_breadth_5"] > 0.5).astype(float)
        - (features["macro_USDKRW_ma_20_gap"] > 0).astype(float)
        - (features["primary_market_drawdown_60"] < -0.08).astype(float)
    )
    features["market_risk_off_flag"] = (
        (features["market_regime_score"] <= 0)
        | (features["primary_market_drawdown_60"] < -0.10)
        | (features["market_breadth_5"] < 0.45)
    ).astype(float)
    features["sector_strength_score"] = (
        features["sector_rank_pct_5"].fillna(0.5)
        + features["sector_breadth_5"].fillna(0.5)
        + features["sector_above_ma20_ratio"].fillna(0.5)
        + features["sector_breakout_ratio_20"].fillna(0.5)
    ) / 4.0
    features["relative_return_5_x_market_breadth"] = features["relative_return_5"] * features["market_breadth_5"]
    features["relative_return_10_x_market_breadth"] = features["relative_return_10"] * features["market_breadth_5"]
    features["sector_relative_return_5_x_sector_breadth"] = features["sector_relative_return_5"] * features["sector_breadth_5"]
    features["sector_relative_return_20_x_sector_rank"] = features["sector_relative_return_20"] * features["sector_rank_pct_20"]
    features["vcp_breakout_x_sector"] = features["vcp_breakout_proximity_20"] * features["sector_breakout_ratio_20"]

    use_dart_features = is_kr_stock_dart_config(config)
    features = apply_optional_features(features, config)

    # 외부 피처 병합 후 NaN 방어: 시계열 순서 내 인접 값으로 임시 대체 (최대 2칸 이내)
    optional_ffill_columns = [
        "news_sentiment", "news_article_count_24h", "news_burst_zscore",
        "negative_keyword_ratio", "market_news_sentiment", "market_news_article_count_24h",
        "market_news_burst_zscore", "market_negative_keyword_ratio",
        "funding_rate", "open_interest", "open_interest_change_24h",
        "coinone_binance_spread", "kimchi_premium", "leader_btc_dominance_proxy",
        "warning_flag", "price_limit_proximity", "turnover_ratio", "market_open_flag",
    ]
    if use_dart_features:
        optional_ffill_columns.extend(DART_FEATURE_COLUMNS)
    for col in optional_ffill_columns:
        if col in features.columns:
            features[col] = (
                features.groupby("symbol")[col].transform(
                    lambda x: x.ffill(limit=2)
                )
            )

    default_zero_columns = [
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
        "stoch_k_14",
        "stoch_d_3",
        "obv_zscore_20",
        "vcp_contraction_ratio_5_20",
        "vcp_contraction_ratio_10_40",
        "vcp_volatility_ratio_10_40",
        "vcp_volume_dryup_ratio_5_20",
        "vcp_volume_dryup_ratio_10_40",
        "vcp_tight_close_ratio_10",
        "vcp_breakout_proximity_20",
        "vcp_contraction_streak",
        "return_60",
        "ma_60_gap",
        "volatility_60",
        "overnight_gap",
        "breakout_strength_20",
        "breakdown_strength_20",
        "abnormal_range_ratio_20",
        "reversal_strength_1",
        "sector_return_20_mean",
        "sector_relative_return_20",
        "sector_breadth_1",
        "sector_breadth_3",
        "sector_breadth_5",
        "sector_above_ma20_ratio",
        "sector_breakout_ratio_20",
        "sector_volume_thrust_ratio",
        "sector_rank_pct_5",
        "sector_rank_pct_20",
        "sector_strength_score",
        "market_avg_return_1",
        "market_avg_return_3",
        "market_avg_return_5",
        "market_avg_return_10",
        "market_breadth_1",
        "market_breadth_3",
        "market_breadth_5",
        "market_above_ma20_ratio",
        "market_breakout_ratio_20",
        "market_volume_thrust_ratio",
        "market_excess_return_3",
        "market_excess_return_5",
        "market_excess_return_10",
        "market_excess_return_20",
        "primary_market_return_3",
        "primary_market_return_5",
        "primary_market_return_10",
        "primary_market_return_20",
        "primary_market_ma_20_gap",
        "primary_market_ma_60_gap",
        "primary_market_volatility_20",
        "primary_market_drawdown_60",
        "market_regime_score",
        "market_risk_off_flag",
        "relative_return_5_x_market_breadth",
        "relative_return_10_x_market_breadth",
        "sector_relative_return_5_x_sector_breadth",
        "sector_relative_return_20_x_sector_rank",
        "vcp_breakout_x_sector",
    ]
    if use_dart_features:
        default_zero_columns.extend(DART_FEATURE_COLUMNS)
    for column in default_zero_columns:
        if column not in features.columns:
            features[column] = 0.0

    features["news_presence_flag"] = (features["news_article_count_24h"] > 0).astype(float)
    features["market_news_presence_flag"] = (features["market_news_article_count_24h"] > 0).astype(float)
    features["news_sentiment_abs"] = features["news_sentiment"].abs()
    features["news_sentiment_x_burst"] = features["news_sentiment"] * features["news_burst_zscore"].clip(lower=-3, upper=3)
    features["positive_news_shock"] = features["news_sentiment"].clip(lower=0) * (1 + features["news_burst_zscore"].clip(lower=0))
    features["negative_news_shock"] = (-features["news_sentiment"]).clip(lower=0) * (
        1 + features["news_burst_zscore"].clip(lower=0)
    ) * (1 + features["negative_keyword_ratio"].clip(lower=0))
    features["news_vs_market_sentiment_gap"] = features["news_sentiment"] - features["market_news_sentiment"]
    features["news_attention_ratio"] = features["news_article_count_24h"] / (features["market_news_article_count_24h"] + 1.0)
    features["market_news_stress_score"] = (-features["market_news_sentiment"]).clip(lower=0) * (
        1 + features["market_news_burst_zscore"].clip(lower=0)
    )
    features["warning_news_combo"] = features["warning_flag"] * features["negative_news_shock"]
    features["turnover_event_pressure"] = features["turnover_ratio"] * (
        1 + features["news_presence_flag"] + features["market_news_presence_flag"]
    )

    if asset_type == "CRYPTO":
        horizon = int(config["model"]["horizon_periods"])
        leader_periods = sorted({1, 4, horizon, 12, 24})
        leader_symbols = {
            "BTCUSDT": leader_periods,
            "ETHUSDT": leader_periods,
        }

        for leader_symbol, periods in leader_symbols.items():
            leader_df = features[features["symbol"] == leader_symbol][["date", *[f"return_{period}" for period in periods]]].copy()
            rename_map = {f"return_{period}": f"{leader_symbol.lower()}_return_{period}" for period in periods}
            leader_df = leader_df.rename(columns=rename_map)
            features = pd.merge(features, leader_df, on="date", how="left")

        for period in leader_periods:
            for leader in ["btcusdt", "ethusdt"]:
                column = f"{leader}_return_{period}"
                if column not in features.columns:
                    features[column] = 0.0

        for column in ["btcusdt_return_4", "ethusdt_return_4", "btcusdt_return_1", "ethusdt_return_1", "btcusdt_return_24"]:
            if column not in features.columns:
                features[column] = 0.0

        features["relative_to_btc_return_4"] = features["return_4"] - features["btcusdt_return_4"]
        features["relative_to_eth_return_4"] = features["return_4"] - features["ethusdt_return_4"]
        features[f"relative_to_btc_return_{horizon}"] = features[f"return_{horizon}"] - features[f"btcusdt_return_{horizon}"]
        features[f"relative_to_eth_return_{horizon}"] = features[f"return_{horizon}"] - features[f"ethusdt_return_{horizon}"]
        market_return_periods = sorted({4, horizon, 24})
        market_returns = (
            features.groupby("date")[[f"return_{period}" for period in market_return_periods]]
            .mean()
            .reset_index()
            .rename(columns={f"return_{period}": f"crypto_market_return_{period}" for period in market_return_periods})
        )
        features = pd.merge(features, market_returns, on="date", how="left")
        features["relative_to_market_return_4"] = features["return_4"] - features["crypto_market_return_4"]
        features["relative_to_market_return_24"] = features["return_24"] - features["crypto_market_return_24"]
        features[f"relative_to_market_return_{horizon}"] = (
            features[f"return_{horizon}"] - features[f"crypto_market_return_{horizon}"]
        )

        # 잔차 수익률 라벨: BTC 시장 동조 노이즈 제거 후 개별 알파 예측 (v8+)
        # config에 use_residual_label: true 설정 시 활성화
        label_config = config.get("labels", {})
        if label_config.get("use_residual_label", False):
            market_symbol = str(label_config.get("residual_market_symbol", "BTCUSDT")).upper()
            btc_col = f"{market_symbol.lower()}_return_{horizon}"
            if btc_col not in features.columns:
                # horizon_periods 봉 수익률 BTC 컬럼이 없으면 가장 근접한 것을 사용
                btc_col = "btcusdt_return_24" if "btcusdt_return_24" in features.columns else None
            if btc_col and btc_col in features.columns:
                residual_return = features["future_return"] - features[btc_col].fillna(0.0)
                up_threshold_r = float(config["model"]["up_return_threshold"])
                risk_threshold_r = float(config["model"]["risk_return_threshold"])
                features["residual_up_label"] = (residual_return >= up_threshold_r).astype(int)
                features["residual_risk_label"] = (residual_return <= risk_threshold_r).astype(int)

    if asset_type == "STOCK":
        # 주식 잔차 수익률 라벨: 국가별 지수(KOSPI/NASDAQ) 수익률 차감 (v8+)
        label_config = config.get("labels", {})
        if label_config.get("use_residual_label", False):
            horizon = int(config["model"]["horizon_periods"])
            up_threshold_r = float(config["model"]["up_return_threshold"])
            risk_threshold_r = float(config["model"]["risk_return_threshold"])
            residual_return = features["future_return"].copy()
            kr_col = f"macro_KOSPI_return_{horizon}"
            us_col = f"macro_NASDAQ_return_{horizon}"
            if kr_col not in features.columns:
                kr_col = "macro_KOSPI_return_3" if "macro_KOSPI_return_3" in features.columns else None
            if us_col not in features.columns:
                us_col = "macro_NASDAQ_return_3" if "macro_NASDAQ_return_3" in features.columns else None
            if kr_col and us_col:
                market_ret = np.where(
                    features.get("is_kr_asset", pd.Series(1, index=features.index)) == 1,
                    features[kr_col].fillna(0.0),
                    features[us_col].fillna(0.0),
                )
                residual_return = features["future_return"] - market_ret
            features["residual_up_label"] = (residual_return >= up_threshold_r).astype(int)
            features["residual_risk_label"] = (residual_return <= risk_threshold_r).astype(int)

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
        # 잔차 수익률 라벨: 시장 동조 노이즈 차감 후 개별 알파 예측용 (v8+)
        "residual_up_label",
        "residual_risk_label",
        *feature_columns,
    ]
    output_columns = [column for column in output_columns if column in features.columns]
    features = features[output_columns]
    if not include_unlabeled:
        features = features.dropna(subset=["future_return"])
    features = features.reset_index(drop=True)
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
