from pathlib import Path


def test_toss_is_in_user_triggered_order_status_sync():
    source = Path("backend/routes/trade.py").read_text()
    sync_route = source.split('@trade_bp.route("/api/trade/orders/sync-status"', 1)[1]

    assert 'exchange": "eq.TOSS"' in sync_route
    assert 'get_order_status(order_id)' in sync_route
    assert '"exchange": "TOSS"' in sync_route
    assert '"normalized_status": next_status' in sync_route


def test_order_status_sync_name_is_not_kis_only():
    source = Path("backend/routes/trade.py").read_text()

    assert "def sync_order_statuses" in source
    assert "def sync_kis_order_statuses" not in source
