import pandas as pd

from ml.src.backtest_signals import build_daily_backtest


def test_short_backtest_flips_return_and_deducts_funding_cost():
    valid_df = pd.DataFrame(
        [
            {
                "date": "2026-07-01",
                "symbol": "BTCUSDT",
                "asset_type": "CRYPTO",
                "future_return": -0.03,
                "up_probability": 0.2,
                "risk_probability": 0.8,
                "signal_score": 80.0,
                "position": "SHORT",
            }
        ]
    )

    _, summary = build_daily_backtest(
        valid_df,
        top_n=1,
        fee_bps=5,
        slippage_bps=0,
        funding_bps_per_horizon=10,
        volumes_cache={"BTCUSDT": 1_000_000_000},
    )

    assert summary["top_avg_future_return"] == 0.03
    assert summary["top_avg_future_return_net"] == 0.027
    assert summary["selection_win_rate"] == 1.0
    assert summary["funding_bps_per_horizon"] == 10.0
