from backend.services.ai_fund_performance_service import AiFundPerformanceService


def test_performance_service_loads_ledger_rows_and_resolves_prices(monkeypatch):
    def fake_query(endpoint, **_kwargs):
        if endpoint == "ai_fund_positions":
            return [{"strategy_id": "dca", "symbol": "BTC", "quantity": 2.0, "average_entry_price": 100.0, "realized_pnl": 5.0}]
        return [{"strategy_id": "dca", "status": "SUBMITTED"}]

    monkeypatch.setattr(
        "backend.services.ai_fund_performance_service.safe_query_supabase_as_service_role",
        fake_query,
    )

    report = AiFundPerformanceService().get_report("user-1", "coinone", lambda _symbol: 120.0)

    assert report["position_value"] == 240.0
    assert report["total_pnl"] == 45.0
    assert report["pending_order_count"] == 1
