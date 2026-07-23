from datetime import datetime, timezone

from backend.services.ai_fund_strategy_service import AiFundStrategyService


def test_dca_strategy_creates_pending_intent_and_updates_state(monkeypatch):
    writes = []

    def fake_query(endpoint, method="GET", json_data=None, **_kwargs):
        writes.append((endpoint, method, json_data))
        return [json_data] if json_data else []

    monkeypatch.setattr(
        "backend.services.ai_fund_strategy_service.safe_query_supabase_as_service_role",
        fake_query,
    )
    service = AiFundStrategyService()
    strategy = {
        "id": "strategy-1",
        "user_id": "user-1",
        "exchange_type": "coinone",
        "strategy_type": "DCA",
        "symbol": "BTC",
        "config": {
            "reference_price": 100.0,
            "trigger_drawdown_pct": 5.0,
            "max_entries": 3,
            "entry_amount": 100.0,
            "min_interval_seconds": 0,
            "max_strategy_loss_pct": -20.0,
        },
        "state": {"entry_count": 0},
    }

    result = service.evaluate_strategy(strategy, current_price=95.0, now=datetime.now(timezone.utc))

    assert result is True
    intent_write = next(item for item in writes if item[0] == "ai_fund_trade_intents")
    state_write = next(item for item in writes if item[0] == "ai_fund_strategies?id=eq.strategy-1")
    assert intent_write[2]["strategy_id"] == "dca"
    assert intent_write[2]["status"] == "PENDING"
    assert state_write[2]["state"]["entry_count"] == 1


def test_run_active_strategies_evaluates_each_running_symbol(monkeypatch):
    service = AiFundStrategyService()
    service._fetch_running = lambda *_args: [
        {"id": "dca-1", "symbol": "BTC"},
        {"id": "grid-1", "symbol": "ETH"},
    ]
    evaluated = []
    service.evaluate_strategy = lambda strategy, current_price: evaluated.append((strategy["id"], current_price)) or True

    count = service.run_active_strategies("user-1", "coinone", lambda symbol: {"BTC": 100.0, "ETH": 200.0}[symbol])

    assert count == 2
    assert evaluated == [("dca-1", 100.0), ("grid-1", 200.0)]
