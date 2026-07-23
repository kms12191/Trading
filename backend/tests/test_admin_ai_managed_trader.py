from contextlib import contextmanager
from unittest.mock import MagicMock, patch
import pytest
from backend.services.admin_ai_managed_trader import AdminAiManagedTrader, AdminAiRiskViolation


@contextmanager
def acquired_lock(*args, **kwargs):
    yield True


def active_config(**overrides):
    config = {
        "is_active": True,
        "allocated_capital": 1000000.0,
        "min_signal_confidence": 0.75,
        "max_position_size": 100000.0,
        "daily_mdd_limit_pct": -2.0,
        "target_take_profit_pct": 5.0,
        "stop_loss_pct": -2.0,
    }
    config.update(overrides)
    return config



def test_evaluate_signal_skips_when_inactive():
    """Ensure signal evaluation returns None if fund trading is inactive."""
    trader = AdminAiManagedTrader(user_id="admin-123", exchange_type="coinone")
    trader._get_fund_config = MagicMock(return_value={"is_active": False})

    result = trader.evaluate_and_execute_signal(
        symbol="BTC",
        signal_type="BUY",
        confidence_score=0.85,
        current_price=50000000.0,
        exchange_client=MagicMock()
    )
    assert result is None


def test_evaluate_signal_executes_when_valid():
    """Ensure valid signal executes trade and logs to database."""
    trader = AdminAiManagedTrader(user_id="admin-123", exchange_type="coinone")
    trader._get_fund_config = MagicMock(return_value=active_config(max_position_size=500000.0))
    trader._get_daily_pnl_pct = MagicMock(return_value=0.0)
    trader._get_open_position = MagicMock(return_value=None)
    trader.is_symbol_tradable_on_exchange = MagicMock(return_value=True)
    trader._log_trade_execution = MagicMock()

    mock_exchange = MagicMock()
    mock_exchange.place_order.return_value = {"order_id": "ord-999", "status": "filled"}

    with patch("backend.services.admin_ai_managed_trader.distributed_lock", acquired_lock):
        result = trader.evaluate_and_execute_signal(
            symbol="BTC",
            signal_type="BUY",
            confidence_score=0.85,
            current_price=50000000.0,
            exchange_client=mock_exchange
        )
    assert result == {"order_id": "ord-999", "status": "filled"}
    mock_exchange.place_order.assert_called_once()


def test_evaluate_signal_uses_requested_quantity_for_strategy_intent():
    trader = AdminAiManagedTrader(user_id="admin-123", exchange_type="coinone")
    trader._get_fund_config = MagicMock(return_value=active_config(max_position_size=500000.0))
    trader._get_daily_pnl_pct = MagicMock(return_value=0.0)
    trader._get_open_position = MagicMock(return_value=None)
    trader.is_symbol_tradable_on_exchange = MagicMock(return_value=True)
    trader._log_trade_execution = MagicMock()
    trader._find_order_by_client_order_id = MagicMock(return_value=None)
    trader._create_pending_order = MagicMock(return_value="ledger-order-1")
    trader._update_ledger_order = MagicMock()

    mock_exchange = MagicMock()
    mock_exchange.place_order.return_value = {"order_id": "ord-grid", "status": "filled"}

    with patch("backend.services.admin_ai_managed_trader.distributed_lock", acquired_lock):
        trader.evaluate_and_execute_signal(
            symbol="BTC",
            signal_type="BUY",
            confidence_score=0.85,
            current_price=100.0,
            exchange_client=mock_exchange,
            requested_quantity=12.5,
            strategy_id="grid",
        )

    assert mock_exchange.place_order.call_args.kwargs["qty"] == 12.5


def test_evaluate_signal_blocks_when_daily_mdd_limit_reached():
    trader = AdminAiManagedTrader(user_id="admin-123", exchange_type="coinone")
    trader._get_fund_config = MagicMock(return_value=active_config(daily_mdd_limit_pct=-2.0))
    trader._get_daily_pnl_pct = MagicMock(return_value=-2.1)
    trader.is_symbol_tradable_on_exchange = MagicMock(return_value=True)

    with patch("backend.services.admin_ai_managed_trader.distributed_lock", acquired_lock):
        with pytest.raises(AdminAiRiskViolation, match="Daily MDD"):
            trader.evaluate_and_execute_signal(
                symbol="BTC",
                signal_type="BUY",
                confidence_score=0.90,
                current_price=50000000.0,
                exchange_client=MagicMock()
            )


def test_evaluate_signal_blocks_when_buy_exceeds_allocated_capital():
    trader = AdminAiManagedTrader(user_id="admin-123", exchange_type="coinone")
    trader._get_fund_config = MagicMock(return_value=active_config(
        allocated_capital=100000.0,
        max_position_size=150000.0,
    ))
    trader._get_daily_pnl_pct = MagicMock(return_value=0.0)
    trader._get_open_position = MagicMock(return_value=None)
    trader.is_symbol_tradable_on_exchange = MagicMock(return_value=True)

    with patch("backend.services.admin_ai_managed_trader.distributed_lock", acquired_lock):
        with pytest.raises(AdminAiRiskViolation, match="allocated capital"):
            trader.evaluate_and_execute_signal(
                symbol="BTC",
                signal_type="BUY",
                confidence_score=0.90,
                current_price=50000000.0,
                exchange_client=MagicMock()
            )


def test_evaluate_signal_skips_duplicate_buy_when_position_open():
    trader = AdminAiManagedTrader(user_id="admin-123", exchange_type="coinone")
    trader._get_fund_config = MagicMock(return_value=active_config())
    trader._get_daily_pnl_pct = MagicMock(return_value=0.0)
    trader._get_open_position = MagicMock(return_value={
        "symbol": "BTC",
        "executed_qty": 0.01,
        "executed_price": 50000000.0,
    })
    trader.is_symbol_tradable_on_exchange = MagicMock(return_value=True)
    mock_exchange = MagicMock()

    with patch("backend.services.admin_ai_managed_trader.distributed_lock", acquired_lock):
        result = trader.evaluate_and_execute_signal(
            symbol="BTC",
            signal_type="BUY",
            confidence_score=0.90,
            current_price=51000000.0,
            exchange_client=mock_exchange
        )

    assert result is None
    mock_exchange.place_order.assert_not_called()


def test_evaluate_exit_signal_sells_when_take_profit_reached(monkeypatch):
    ledger = MagicMock()
    ledger.get_position.return_value = None
    monkeypatch.setattr("backend.services.admin_ai_managed_trader.AiFundLedger", lambda *_args: ledger)
    trader = AdminAiManagedTrader(user_id="admin-123", exchange_type="coinone")
    trader._get_fund_config = MagicMock(return_value=active_config(target_take_profit_pct=5.0))
    trader._get_open_position = MagicMock(return_value={
        "symbol": "BTC",
        "executed_qty": 0.01,
        "executed_price": 50000000.0,
    })

    signal = trader.evaluate_exit_signal("BTC", current_price=52600000.0)

    assert signal["symbol"] == "BTC"
    assert signal["signal_type"] == "SELL"
    assert signal["reason"] == "TAKE_PROFIT"
    assert signal["quantity"] == 0.01
    assert signal["next_policy"]["completed_take_profit_steps"] == [0]


def test_evaluate_exit_signal_uses_position_policy_for_partial_take_profit(monkeypatch):
    ledger = MagicMock()
    ledger.get_position.return_value = {
        "symbol": "BTC",
        "quantity": 10.0,
        "average_entry_price": 100.0,
        "exit_policy": {
            "take_profit_steps": [{"target_pct": 5.0, "sell_ratio": 0.5}],
            "break_even_after_first_target": True,
        },
    }
    monkeypatch.setattr("backend.services.admin_ai_managed_trader.AiFundLedger", lambda *_args: ledger)
    trader = AdminAiManagedTrader(user_id="admin-123", exchange_type="coinone")
    trader._get_fund_config = MagicMock(return_value=active_config())

    signal = trader.evaluate_exit_signal("BTC", current_price=105.0)

    assert signal["reason"] == "TAKE_PROFIT_1"
    assert signal["quantity"] == 5.0
    assert signal["next_policy"]["break_even_armed"] is True


def test_record_exit_policy_persists_only_the_matching_ledger_position(monkeypatch):
    ledger = MagicMock()
    monkeypatch.setattr("backend.services.admin_ai_managed_trader.AiFundLedger", lambda *_args: ledger)
    trader = AdminAiManagedTrader(user_id="admin-123", exchange_type="coinone")

    trader.record_exit_policy("BTC", {"break_even_armed": True})

    ledger.update_exit_policy.assert_called_once_with("BTC", {"break_even_armed": True})


def test_daily_pnl_does_not_count_buy_amount_as_loss():
    trader = AdminAiManagedTrader(user_id="admin-123", exchange_type="coinone")
    trader._get_trade_logs = MagicMock(return_value=[
        {
            "symbol": "BTC",
            "side": "BUY",
            "executed_price": 50000000.0,
            "executed_qty": 0.01,
            "total_amount": 500000.0,
            "created_at": "2026-07-22T01:00:00+00:00",
        }
    ])

    assert trader._get_daily_pnl_pct(active_config(allocated_capital=1000000.0)) == 0.0


def test_emergency_kill_switch():
    """Verify emergency kill switch deactivates active configurations."""
    trader = AdminAiManagedTrader(user_id="00000000-0000-0000-0000-000000000123", exchange_type="coinone")
    with patch(
        "backend.services.admin_ai_managed_trader.query_supabase_as_service_role",
        return_value=[{"is_active": False}]
    ):
        success = trader.emergency_kill_switch()
        assert success is True


def test_is_symbol_tradable_on_exchange():
    trader = AdminAiManagedTrader(user_id="00000000-0000-0000-0000-000000000123", exchange_type="coinone")
    with patch("backend.services.coinone_client.CoinoneClient.get_krw_markets", return_value=[{"target_currency": "btc"}, {"target_currency": "eth"}]):
        assert trader.is_symbol_tradable_on_exchange("BTCUSDT") is True
        assert trader.is_symbol_tradable_on_exchange("ETHUSDT") is True
        assert trader.is_symbol_tradable_on_exchange("UNLISTEDUSDT") is False


def test_coinone_symbol_check_blocks_orders_when_market_list_is_unavailable():
    trader = AdminAiManagedTrader(user_id="00000000-0000-0000-0000-000000000123", exchange_type="coinone")

    with patch("backend.services.coinone_client.CoinoneClient.get_krw_markets", return_value=[]):
        assert trader.is_symbol_tradable_on_exchange("MKRUSDT") is False


def test_exchange_timeout_marks_order_needs_review_without_success_log():
    trader = AdminAiManagedTrader(user_id="admin-123", exchange_type="coinone")
    trader._get_fund_config = MagicMock(return_value=active_config(operation_mode="LIVE"))
    trader._get_daily_pnl_pct = MagicMock(return_value=0.0)
    trader._get_open_position = MagicMock(return_value=None)
    trader.is_symbol_tradable_on_exchange = MagicMock(return_value=True)
    trader._log_trade_execution = MagicMock()
    trader._create_pending_order = MagicMock(return_value="ledger-order-1")
    trader._update_ledger_order = MagicMock()
    exchange_client = MagicMock()
    exchange_client.place_order.side_effect = TimeoutError("timeout")

    with patch("backend.services.admin_ai_managed_trader.distributed_lock", acquired_lock):
        result = trader.evaluate_and_execute_signal(
            symbol="BTC",
            signal_type="BUY",
            confidence_score=0.9,
            current_price=100.0,
            exchange_client=exchange_client,
        )

    assert result["status"] == "NEEDS_REVIEW"
    assert exchange_client.place_order.call_count == 1
    trader._log_trade_execution.assert_not_called()
    trader._update_ledger_order.assert_called_once_with(
        "ledger-order-1",
        status="NEEDS_REVIEW",
        failure_reason="timeout",
    )


def test_unresolved_buy_order_blocks_a_second_buy_submission():
    trader = AdminAiManagedTrader(user_id="admin-123", exchange_type="coinone")
    trader._get_fund_config = MagicMock(return_value=active_config(operation_mode="LIVE"))
    trader._get_daily_pnl_pct = MagicMock(return_value=0.0)
    trader._get_open_position = MagicMock(return_value=None)
    trader.is_symbol_tradable_on_exchange = MagicMock(return_value=True)
    trader._find_unresolved_order_for_symbol = MagicMock(
        return_value={"id": "review-order-1", "status": "NEEDS_REVIEW"}
    )
    exchange_client = MagicMock()

    with patch("backend.services.admin_ai_managed_trader.distributed_lock", acquired_lock):
        result = trader.evaluate_and_execute_signal(
            symbol="BTT",
            signal_type="BUY",
            confidence_score=0.9,
            current_price=0.0004,
            exchange_client=exchange_client,
        )

    assert result == {"order_id": "review-order-1", "status": "NEEDS_REVIEW", "blocked": True}
    exchange_client.place_order.assert_not_called()


def test_canary_mode_limits_order_amount(monkeypatch):
    trader = AdminAiManagedTrader(user_id="admin-123", exchange_type="coinone")
    trader._get_fund_config = MagicMock(return_value=active_config(
        operation_mode="CANARY",
        canary_max_order_amount=100.0,
        max_position_size=500.0,
    ))
    trader._get_daily_pnl_pct = MagicMock(return_value=0.0)
    trader._get_open_position = MagicMock(return_value=None)
    trader.is_symbol_tradable_on_exchange = MagicMock(return_value=True)
    trader._create_pending_order = MagicMock(return_value="ledger-order-1")
    trader._update_ledger_order = MagicMock()
    exchange_client = MagicMock()
    exchange_client.place_order.return_value = {"order_id": "order-1", "status": "ORDERED"}

    with patch("backend.services.admin_ai_managed_trader.distributed_lock", acquired_lock):
        trader.evaluate_and_execute_signal(
            symbol="BTC",
            signal_type="BUY",
            confidence_score=0.9,
            current_price=100.0,
            exchange_client=exchange_client,
        )

    assert exchange_client.place_order.call_args.kwargs["qty"] == 1.0


def test_immediate_partial_fill_is_applied_to_ai_fund_ledger(monkeypatch):
    ledger = MagicMock()
    monkeypatch.setattr("backend.services.admin_ai_managed_trader.AiFundLedger", lambda *_args: ledger)
    trader = AdminAiManagedTrader(user_id="admin-123", exchange_type="coinone")
    trader._get_fund_config = MagicMock(return_value=active_config())
    trader._get_daily_pnl_pct = MagicMock(return_value=0.0)
    trader._get_open_position = MagicMock(return_value=None)
    trader.is_symbol_tradable_on_exchange = MagicMock(return_value=True)
    trader._create_pending_order = MagicMock(return_value="ledger-order-1")
    trader._update_ledger_order = MagicMock()
    exchange_client = MagicMock()
    exchange_client.place_order.return_value = {
        "order_id": "exchange-order-1",
        "status": "PARTIALLY_FILLED",
        "executed_qty": 0.2,
        "price": 100.0,
    }

    with patch("backend.services.admin_ai_managed_trader.distributed_lock", acquired_lock):
        trader.evaluate_and_execute_signal(
            symbol="BTC",
            signal_type="BUY",
            confidence_score=0.9,
            current_price=100.0,
            exchange_client=exchange_client,
        )

    ledger.apply_new_fill.assert_called_once()
    assert ledger.apply_new_fill.call_args.kwargs["order_id"] == "ledger-order-1"


def test_same_signal_id_does_not_submit_a_duplicate_order(monkeypatch):
    trader = AdminAiManagedTrader(user_id="admin-123", exchange_type="coinone")
    trader._get_fund_config = MagicMock(return_value=active_config(id="config-1"))
    trader._get_daily_pnl_pct = MagicMock(return_value=0.0)
    trader._get_open_position = MagicMock(return_value=None)
    trader.is_symbol_tradable_on_exchange = MagicMock(return_value=True)
    trader._find_order_by_client_order_id = MagicMock(return_value={"id": "ledger-order-1", "status": "SUBMITTED"})
    exchange_client = MagicMock()

    with patch("backend.services.admin_ai_managed_trader.distributed_lock", acquired_lock):
        result = trader.evaluate_and_execute_signal(
            symbol="BTC",
            signal_type="BUY",
            confidence_score=0.9,
            current_price=100.0,
            exchange_client=exchange_client,
            signal_id="prediction-20260722T010000Z",
        )

    assert result == {"order_id": "ledger-order-1", "status": "SUBMITTED", "idempotent": True}
    exchange_client.place_order.assert_not_called()
