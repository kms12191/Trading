from backend.services.ai_fund_portfolio_service import AiFundPortfolioService


def test_portfolio_service_creates_pending_rebalance_intents(monkeypatch):
    writes = []

    def fake_query(endpoint, method="GET", json_data=None, **_kwargs):
        if method == "GET":
            return [{"symbol": "BTC", "quantity": 8.0}, {"symbol": "ETH", "quantity": 1.0}]
        writes.append((endpoint, method, json_data))
        return [json_data]

    monkeypatch.setattr(
        "backend.services.ai_fund_portfolio_service.safe_query_supabase_as_service_role",
        fake_query,
    )
    config = {
        "id": "config-1",
        "user_id": "user-1",
        "exchange_type": "coinone",
        "allocated_capital": 1000.0,
        "target_allocations": {"BTC": 0.5, "ETH": 0.5},
        "rebalance_threshold_pct": 5.0,
    }

    created = AiFundPortfolioService().create_rebalance_intents(
        config,
        lambda symbol: {"BTC": 100.0, "ETH": 100.0}.get(symbol),
    )

    assert created == 2
    assert [write[2]["side"] for write in writes] == ["SELL", "BUY"]
    assert all(write[2]["status"] == "PENDING" for write in writes)
