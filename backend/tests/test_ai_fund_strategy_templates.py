from datetime import datetime, timedelta, timezone

from backend.services.ai_fund_strategy_templates import evaluate_dca, evaluate_grid


def test_dca_emits_buy_only_after_drawdown_and_minimum_interval():
    now = datetime.now(timezone.utc)
    intent = evaluate_dca(
        symbol="BTC",
        current_price=95.0,
        config={
            "reference_price": 100.0,
            "trigger_drawdown_pct": 5.0,
            "max_entries": 3,
            "entry_amount": 100.0,
            "min_interval_seconds": 300,
            "max_strategy_loss_pct": -20.0,
        },
        state={"entry_count": 1, "last_entry_at": (now - timedelta(seconds=301)).isoformat(), "strategy_pnl_pct": -5.0},
        now=now,
    )

    assert intent is not None
    assert intent.side == "BUY"
    assert intent.notional == 100.0


def test_dca_stops_when_entry_limit_or_loss_limit_is_reached():
    now = datetime.now(timezone.utc)
    config = {
        "reference_price": 100.0,
        "trigger_drawdown_pct": 5.0,
        "max_entries": 2,
        "entry_amount": 100.0,
        "min_interval_seconds": 0,
        "max_strategy_loss_pct": -20.0,
    }

    assert evaluate_dca("BTC", 90.0, config, {"entry_count": 2}, now) is None
    assert evaluate_dca("BTC", 90.0, config, {"entry_count": 0, "strategy_pnl_pct": -21.0}, now) is None


def test_grid_emits_level_buy_and_pauses_outside_range():
    buy = evaluate_grid(
        symbol="BTC",
        current_price=95.0,
        config={"lower_price": 90.0, "upper_price": 110.0, "grid_count": 4, "order_amount": 50.0, "out_of_range_policy": "PAUSE"},
        state={"filled_buy_levels": []},
    )
    paused = evaluate_grid(
        symbol="BTC",
        current_price=89.0,
        config={"lower_price": 90.0, "upper_price": 110.0, "grid_count": 4, "order_amount": 50.0, "out_of_range_policy": "PAUSE"},
        state={"filled_buy_levels": []},
    )

    assert buy is not None
    assert buy.side == "BUY"
    assert paused is None
