from unittest.mock import MagicMock

from backend.services.ai_fund_intent_executor import AiFundIntentExecutor


def test_executor_runs_only_approved_unexpired_intent(monkeypatch):
    writes = []

    def fake_query(endpoint, method="GET", json_data=None, **_kwargs):
        if method == "GET":
            return [{
                "id": "intent-1",
                "symbol": "BTC",
                "side": "BUY",
                "confidence": 0.9,
                "strategy_id": "grid",
                "idempotency_key": "grid-1",
                "payload": {"notional": 100.0},
            }]
        writes.append((endpoint, method, json_data))
        return [json_data]

    monkeypatch.setattr("backend.services.ai_fund_intent_executor.safe_query_supabase_as_service_role", fake_query)
    trader = MagicMock()
    trader.evaluate_and_execute_signal.return_value = {"status": "SUBMITTED"}

    executed = AiFundIntentExecutor(trader).run("user-1", "coinone", MagicMock(), lambda _symbol: 10.0)

    assert executed == 1
    assert trader.evaluate_and_execute_signal.call_args.kwargs["requested_quantity"] == 10.0
    assert any(item[2]["status"] == "EXECUTED" for item in writes)
