import pandas as pd
import numpy as np
import pytest
from ml.src.build_features import build_features

def test_build_features_cleans_and_filters_correctly():
    # Mock config
    config = {
        "model": {
            "horizon_periods": 3,
            "up_return_threshold": 0.01,
            "risk_return_threshold": -0.01,
            "asset_type": "STOCK",
            "min_listing_days": 5, # 테스트를 위해 5일로 설정
            "feature_columns": ["rsi_14", "atr_14"]
        }
    }
    
    # 2일치만 있는 종목 (필터링되어야 함)
    short_dates = pd.date_range(start="2025-01-01", periods=2)
    # 6일치 데이터가 있지만 결측(NaN)이 포함된 종목 (ffill로 보정되어 살아남아야 함)
    long_dates = pd.date_range(start="2025-01-01", periods=6)
    
    df = pd.DataFrame({
        "date": list(short_dates) + list(long_dates),
        "symbol": ["SHORT"]*2 + ["LONG"]*6,
        "open": [100, 101] + [200, 201, np.nan, 203, 204, 205],
        "high": [105, 106] + [205, 206, np.nan, 208, 209, 210],
        "low": [95, 96] + [195, 196, np.nan, 198, 199, 200],
        "close": [102, 103] + [202, 203, np.nan, 204, 205, 206],
        "volume": [1000, 1100] + [5000, 5100, 5200, 5300, 5400, 5500]
    })
    
    # include_unlabeled=True로 설정하여 라벨이 없더라도 중간 피처가 생성된 프레임 반환
    features = build_features(df, config, include_unlabeled=True)
    
    # 검증 1: 5일 영업일 미달인 'SHORT' 종목은 제거되어야 함
    assert "SHORT" not in features["symbol"].unique()
    
    # 검증 2: 'LONG' 종목은 살아남아야 함
    assert "LONG" in features["symbol"].unique()
    
    # 검증 3: 'LONG' 종목의 rsi_14, atr_14 피처에 NaN이 없어야 함 (ffill 정상 동작)
    long_features = features[features["symbol"] == "LONG"].sort_values("date")
    assert long_features["rsi_14"].isna().sum() == 0
    assert long_features["atr_14"].isna().sum() == 0

if __name__ == "__main__":
    test_build_features_cleans_and_filters_correctly()
    print("ALL PASSED!")
