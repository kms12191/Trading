from unittest.mock import MagicMock, patch
import pytest
from backend.services.admin_ai_managed_trader import AdminAiManagedTrader, AdminAiRiskViolation



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
    trader._get_fund_config = MagicMock(return_value={
        "is_active": True,
        "min_signal_confidence": 0.75,
        "max_position_size": 500000.0
    })
    trader._log_trade_execution = MagicMock()

    mock_exchange = MagicMock()
    mock_exchange.place_order.return_value = {"order_id": "ord-999", "status": "filled"}

    result = trader.evaluate_and_execute_signal(
        symbol="BTC",
        signal_type="BUY",
        confidence_score=0.85,
        current_price=50000000.0,
        exchange_client=mock_exchange
    )
    assert result == {"order_id": "ord-999", "status": "filled"}
    mock_exchange.place_order.assert_called_once()

 


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



