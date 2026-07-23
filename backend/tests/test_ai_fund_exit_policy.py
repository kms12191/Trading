from backend.services.ai_fund_exit_policy import evaluate_exit_policy


def test_first_target_sells_configured_ratio_and_arms_break_even():
    evaluation = evaluate_exit_policy(
        entry_price=100.0,
        quantity=10.0,
        current_price=105.0,
        policy={
            "take_profit_steps": [{"target_pct": 5.0, "sell_ratio": 0.5}],
            "break_even_after_first_target": True,
        },
    )

    assert evaluation.decision.reason == "TAKE_PROFIT_1"
    assert evaluation.decision.quantity == 5.0
    assert evaluation.next_policy["completed_take_profit_steps"] == [0]
    assert evaluation.next_policy["break_even_armed"] is True


def test_break_even_stop_has_priority_after_first_target():
    evaluation = evaluate_exit_policy(
        entry_price=100.0,
        quantity=5.0,
        current_price=100.0,
        policy={
            "stop_loss_pct": -5.0,
            "break_even_armed": True,
            "completed_take_profit_steps": [0],
        },
    )

    assert evaluation.decision.reason == "BREAK_EVEN_STOP"
    assert evaluation.decision.quantity == 5.0


def test_trailing_stop_sells_remaining_quantity_after_activation():
    evaluation = evaluate_exit_policy(
        entry_price=100.0,
        quantity=4.0,
        current_price=106.0,
        policy={
            "trailing": {"activation_pct": 5.0, "trail_pct": 3.0, "highest_price": 110.0},
        },
    )

    assert evaluation.decision.reason == "TRAILING_STOP"
    assert evaluation.decision.quantity == 4.0


def test_completed_target_does_not_trigger_twice():
    evaluation = evaluate_exit_policy(
        entry_price=100.0,
        quantity=5.0,
        current_price=106.0,
        policy={
            "take_profit_steps": [{"target_pct": 5.0, "sell_ratio": 0.5}],
            "completed_take_profit_steps": [0],
        },
    )

    assert evaluation.decision is None
