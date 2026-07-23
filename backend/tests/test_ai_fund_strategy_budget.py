from contextlib import contextmanager
from unittest.mock import MagicMock

import pytest

from backend.services.admin_ai_managed_trader import AdminAiManagedTrader, AdminAiRiskViolation


@contextmanager
def acquired_lock(*_args, **_kwargs):
    yield True


def test_buy_is_blocked_when_strategy_exposure_would_exceed_budget(monkeypatch):
    ledger = MagicMock()
    ledger.get_strategy_exposure.return_value = 90.0
    monkeypatch.setattr("backend.services.admin_ai_managed_trader.AiFundLedger", lambda *_args: ledger)
    monkeypatch.setattr("backend.services.admin_ai_managed_trader.distributed_lock", acquired_lock)
    trader = AdminAiManagedTrader(user_id="user-1", exchange_type="coinone")
    trader._get_fund_config = MagicMock(return_value={
        "is_active": True,
        "allocated_capital": 1_000.0,
        "max_position_size": 50.0,
        "min_signal_confidence": 0.75,
        "daily_mdd_limit_pct": -2.0,
        "strategy_budgets": {"ml_signal": 100.0},
    })
    trader._get_daily_pnl_pct = MagicMock(return_value=0.0)
    trader._get_open_position = MagicMock(return_value=None)
    trader.is_symbol_tradable_on_exchange = MagicMock(return_value=True)

    with pytest.raises(AdminAiRiskViolation, match="Strategy budget"):
        trader.evaluate_and_execute_signal(
            symbol="BTC",
            signal_type="BUY",
            confidence_score=0.9,
            current_price=10.0,
            exchange_client=MagicMock(),
            strategy_id="ml_signal",
        )


def test_buy_uses_independent_strategy_budget(monkeypatch):
    ledger = MagicMock()
    ledger.get_strategy_exposure.return_value = 0.0
    monkeypatch.setattr("backend.services.admin_ai_managed_trader.AiFundLedger", lambda *_args: ledger)
    monkeypatch.setattr("backend.services.admin_ai_managed_trader.distributed_lock", acquired_lock)
    trader = AdminAiManagedTrader(user_id="user-1", exchange_type="coinone")
    trader._get_fund_config = MagicMock(return_value={
        "is_active": True,
        "allocated_capital": 1_000.0,
        "max_position_size": 50.0,
        "min_signal_confidence": 0.75,
        "daily_mdd_limit_pct": -2.0,
        "operation_mode": "PAPER",
        "strategy_budgets": {"grid": 100.0},
    })
    trader._get_daily_pnl_pct = MagicMock(return_value=0.0)
    trader._get_open_position = MagicMock(return_value=None)
    trader.is_symbol_tradable_on_exchange = MagicMock(return_value=True)
    trader._create_pending_order = MagicMock(return_value="order-1")
    trader._update_ledger_order = MagicMock()
    trader._log_trade_execution = MagicMock()

    result = trader.evaluate_and_execute_signal(
        symbol="BTC",
        signal_type="BUY",
        confidence_score=0.9,
        current_price=10.0,
        exchange_client=MagicMock(),
        strategy_id="grid",
    )

    assert result["paper"] is True
    ledger.get_strategy_exposure.assert_called_once()
