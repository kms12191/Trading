import pytest

from backend.services.ai_fund_portfolio import apply_risk_preset, plan_rebalance


def test_plan_rebalance_generates_sell_then_buy_for_material_target_deviation():
    intents = plan_rebalance(
        allocated_capital=1000.0,
        target_allocations={"BTC": 0.5, "ETH": 0.5},
        positions=[
            {"symbol": "BTC", "quantity": 8.0},
            {"symbol": "ETH", "quantity": 1.0},
        ],
        prices={"BTC": 100.0, "ETH": 100.0},
        rebalance_threshold_pct=5.0,
    )

    assert [(intent.symbol, intent.side, intent.notional) for intent in intents] == [
        ("BTC", "SELL", 300.0),
        ("ETH", "BUY", 400.0),
    ]


def test_plan_rebalance_skips_small_deviation_and_invalid_targets():
    intents = plan_rebalance(
        allocated_capital=1000.0,
        target_allocations={"BTC": 0.5, "ETH": 0.6},
        positions=[{"symbol": "BTC", "quantity": 5.2}],
        prices={"BTC": 100.0, "ETH": 100.0},
        rebalance_threshold_pct=5.0,
    )

    assert intents == []


def test_apply_risk_preset_sets_operational_defaults_without_overwriting_explicit_limits():
    config = apply_risk_preset({"risk_preset": "conservative", "allocated_capital": 1000.0})

    assert config["max_position_size"] == 200.0
    assert config["daily_mdd_limit_pct"] == -1.0
    assert config["min_signal_confidence"] == 0.85
    assert config["rebalance_threshold_pct"] == 3.0
    assert apply_risk_preset({"risk_preset": "neutral", "max_position_size": 77.0})["max_position_size"] == 77.0


def test_apply_risk_preset_rejects_unknown_preset():
    with pytest.raises(ValueError, match="risk_preset"):
        apply_risk_preset({"risk_preset": "unknown"})
