from backend.services.ai_fund_performance import build_performance_report


def test_performance_report_separates_realized_unrealized_and_pending_by_strategy():
    report = build_performance_report(
        positions=[
            {"strategy_id": "dca", "symbol": "BTC", "quantity": 2.0, "average_entry_price": 100.0, "realized_pnl": 10.0},
            {"strategy_id": "grid", "symbol": "ETH", "quantity": 3.0, "average_entry_price": 50.0, "realized_pnl": -2.0},
        ],
        orders=[
            {"strategy_id": "dca", "status": "SUBMITTED"},
            {"strategy_id": "grid", "status": "FILLED"},
        ],
        prices={"BTC": 120.0, "ETH": 40.0},
    )

    assert report["realized_pnl"] == 8.0
    assert report["unrealized_pnl"] == 10.0
    assert report["position_value"] == 360.0
    assert report["pending_order_count"] == 1
    assert report["strategies"]["dca"]["total_pnl"] == 50.0
    assert report["strategies"]["grid"]["total_pnl"] == -32.0
