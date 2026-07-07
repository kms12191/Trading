from pathlib import Path

import pandas as pd
import pytest

from ml.src.build_features import apply_optional_features, build_features


def test_apply_optional_features_merges_configured_dart_features(tmp_path: Path):
    dart_path = tmp_path / "dart_features.csv"
    dart_path.write_text(
        "\n".join(
            [
                "symbol,date,dart_disclosure_count_3d,dart_sentiment_sum_3d,dart_negative_count_3d,dart_positive_count_3d,dart_caution_count_3d,dart_disclosure_count_7d,dart_sentiment_sum_7d,dart_negative_count_7d,dart_positive_count_7d,dart_caution_count_7d,dart_disclosure_count_20d,dart_sentiment_sum_20d,dart_negative_count_20d,dart_positive_count_20d,dart_caution_count_20d,dart_ai_analyzed_count_20d,dart_contract_flag_20d,dart_financing_flag_20d,dart_shareholder_return_flag_20d,dart_risk_event_flag_20d,dart_earnings_flag_20d",
                "005930,2026-07-08,1,1,0,1,0,1,1,0,1,0,1,1,0,1,0,1,1,0,0,0,0",
            ]
        ),
        encoding="utf-8",
    )
    features = pd.DataFrame(
        {
            "symbol": ["005930"],
            "date_merge_key": ["2026-07-08"],
        }
    )
    config = {
        "model": {"asset_type": "STOCK", "version": "lgbm_kr_stock_v1"},
        "data": {
            "raw_candles_path": "ml/data/raw/kr_stock_sample.csv",
            "features_path": "ml/data/features/kr_stock_sample_features.csv",
        },
        "optional_features": {"dart_features_path": str(dart_path)},
    }

    merged = apply_optional_features(features, config)

    assert merged.loc[0, "dart_disclosure_count_3d"] == 1
    assert merged.loc[0, "dart_contract_flag_20d"] == 1


def test_apply_optional_features_allows_explicit_kr_market_scope(tmp_path: Path):
    dart_path = tmp_path / "dart_features.csv"
    dart_path.write_text(
        "\n".join(
            [
                "symbol,date,dart_disclosure_count_3d,dart_contract_flag_20d",
                "005930,2026-07-08,1,1",
            ]
        ),
        encoding="utf-8",
    )
    features = pd.DataFrame(
        {
            "symbol": ["005930"],
            "date_merge_key": ["2026-07-08"],
        }
    )
    config = {
        "market_scope": "KR",
        "model": {"asset_type": "STOCK", "version": "lgbm_stock_signal_v11"},
        "data": {
            "raw_candles_path": "ml/data/raw/stock_candles.csv",
            "features_path": "ml/data/processed/stock_features_lgbm_v11.csv",
        },
        "optional_features": {"dart_features_path": str(dart_path)},
    }

    merged = apply_optional_features(features, config)

    assert merged.loc[0, "dart_disclosure_count_3d"] == 1


def test_apply_optional_features_does_not_add_dart_columns_without_path():
    features = pd.DataFrame(
        {
            "symbol": ["005930"],
            "date_merge_key": ["2026-07-08"],
        }
    )
    config = {"model": {"asset_type": "STOCK"}}

    merged = apply_optional_features(features, config)

    assert "dart_disclosure_count_3d" not in merged.columns


def test_build_features_without_dart_path_does_not_create_dart_columns():
    candles = pd.DataFrame(
        {
            "symbol": ["005930", "005930", "005930"],
            "date": ["2026-07-08", "2026-07-09", "2026-07-10"],
            "open": [100.0, 101.0, 102.0],
            "high": [101.0, 102.0, 103.0],
            "low": [99.0, 100.0, 101.0],
            "close": [100.5, 101.5, 102.5],
            "volume": [1000.0, 1100.0, 1200.0],
        }
    )
    config = {
        "model": {
            "asset_type": "STOCK",
            "version": "lgbm_kr_stock_v1",
            "horizon_periods": 1,
            "up_return_threshold": 0.01,
            "risk_return_threshold": -0.01,
            "feature_columns": ["return_1", "warning_flag"],
        },
        "labels": {
            "neutral_zone_abs_return": 0.0,
            "drop_neutral_samples": False,
        },
        "data": {
            "raw_candles_path": "ml/data/raw/kr_stock_sample.csv",
            "features_path": "ml/data/features/kr_stock_sample_features.csv",
        },
    }

    built = build_features(candles, config, include_unlabeled=True)

    assert "dart_disclosure_count_3d" not in built.columns


def test_apply_optional_features_rejects_us_stock_dart_config(tmp_path: Path):
    dart_path = tmp_path / "dart_features.csv"
    dart_path.write_text(
        "\n".join(
            [
                "symbol,date,dart_disclosure_count_3d",
                "AAPL,2026-07-08,1",
            ]
        ),
        encoding="utf-8",
    )
    features = pd.DataFrame(
        {
            "symbol": ["AAPL"],
            "date_merge_key": ["2026-07-08"],
        }
    )
    config = {
        "model": {"asset_type": "STOCK", "version": "lgbm_us_stock_v1"},
        "data": {
            "raw_candles_path": "ml/data/raw/us_stock_sample.csv",
            "features_path": "ml/data/features/us_stock_sample_features.csv",
        },
        "optional_features": {"dart_features_path": str(dart_path)},
    }

    with pytest.raises(ValueError, match="DART 피처는 국내 주식 KR 설정에서만 사용할 수 있습니다"):
        apply_optional_features(features, config)
