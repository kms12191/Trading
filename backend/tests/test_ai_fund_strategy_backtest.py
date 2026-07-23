from backend.services.ai_fund_strategy_backtest import run_strategy_backtest


def test_dca_backtest_reuses_live_template_and_calculates_net_return():
    result = run_strategy_backtest(
        {
            "id": "dca-btc",
            "strategy_type": "DCA",
            "symbol": "BTC",
            "config": {
                "reference_price": 100.0,
                "trigger_drawdown_pct": 5.0,
                "entry_amount": 10.0,
                "max_entries": 2,
                "min_interval_seconds": 0,
            },
        },
        [
            {"timestamp": "2026-01-01T00:00:00Z", "close": 100.0},
            {"timestamp": "2026-01-01T01:00:00Z", "close": 90.0},
            {"timestamp": "2026-01-01T02:00:00Z", "close": 80.0},
            {"timestamp": "2026-01-01T03:00:00Z", "close": 100.0},
        ],
        fee_bps=10.0,
    )

    assert result["trade_count"] == 2
    assert result["invested_notional"] == 20.0
    assert result["final_value"] > 23.0
    assert result["net_return_pct"] > 15.0
    assert result["max_drawdown_pct"] < 0.0


def test_grid_backtest_does_not_buy_the_same_grid_level_twice():
    result = run_strategy_backtest(
        {
            "id": "grid-btc",
            "strategy_type": "GRID",
            "symbol": "BTC",
            "config": {"lower_price": 80.0, "upper_price": 120.0, "grid_count": 4, "order_amount": 10.0},
        },
        [
            {"timestamp": "2026-01-01T00:00:00Z", "close": 90.0},
            {"timestamp": "2026-01-01T01:00:00Z", "close": 90.0},
            {"timestamp": "2026-01-01T02:00:00Z", "close": 100.0},
        ],
    )

    assert result["trade_count"] == 2
    assert [trade["reason"] for trade in result["trades"]] == ["GRID_BUY_1", "GRID_BUY_2"]
