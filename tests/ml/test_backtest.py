import pandas as pd
import numpy as np
import pytest
from ml.src.backtest_signals import build_daily_backtest

def test_build_daily_backtest_applies_variable_slippage():
    # 2개 종목의 동일 시점 가상 매매 데이터 생성
    # LONG_VOL: 유동성 풍부, SMALL_VOL: 유동성 부족
    # 둘 다 10%의 수익(future_return = 0.10)을 냈다고 가정
    valid_df = pd.DataFrame({
        "date": ["2025-01-01", "2025-01-01"],
        "symbol": ["LONG_VOL", "SMALL_VOL"],
        "future_return": [0.10, 0.10],
        "signal_score": [2.0, 1.0], 
        "up_probability": [0.70, 0.60],
        "risk_probability": [0.10, 0.20],
        "asset_type": ["STOCK", "STOCK"],
        "position": ["LONG", "LONG"]
    })
    
    # 최근 20일 거래대금 중간값 매핑
    # LONG_VOL = 10억 (1,000,000,000)
    # SMALL_VOL = 100만 (1,000,000)
    volumes_cache = {
        "LONG_VOL": 1000000000.0,
        "SMALL_VOL": 1000000.0
    }
    
    # 1. LONG_VOL 매매 백테스트 (top_n = 1로 설정하여 상위 1개만 매매)
    daily_df_long, _ = build_daily_backtest(
        valid_df[valid_df["symbol"] == "LONG_VOL"],
        top_n=1,
        fee_bps=10,       # 수수료 10 bps (0.1%)
        slippage_bps=5,   # 고정 값은 이제 가변 값에 의해 덮어씌워짐
        volumes_cache=volumes_cache
    )
    
    # 2. SMALL_VOL 매매 백테스트
    daily_df_small, _ = build_daily_backtest(
        valid_df[valid_df["symbol"] == "SMALL_VOL"],
        top_n=1,
        fee_bps=10,
        slippage_bps=5,
        volumes_cache=volumes_cache
    )
    
    # 두 거래의 순수익률 추출
    net_ret_long = daily_df_long["top_avg_future_return_net"].iloc[0]
    net_ret_small = daily_df_small["top_avg_future_return_net"].iloc[0]
    
    # 검증: 거래대금이 작은 SMALL_VOL의 순수익률이 LONG_VOL보다 낮아야 함 (슬리피지 비용이 크게 잡히므로)
    assert net_ret_long > net_ret_small
    
    # 두 순수익률의 차이가 대략 비용 차이(약 45 bps = 0.0045)와 일치하는지 확인
    expected_diff = 0.0045
    actual_diff = net_ret_long - net_ret_small
    print("ACTUAL DIFF:", actual_diff)
    assert np.isclose(actual_diff, expected_diff, atol=0.0001)

if __name__ == "__main__":
    test_build_daily_backtest_applies_variable_slippage()
    print("ALL PASSED!")
