from unittest.mock import MagicMock

from backend.services.ai_fund_reconciliation import AiFundReconciliationService


def test_reconcile_marks_missing_exchange_order_as_needs_review(monkeypatch):
    writes = []
    monkeypatch.setattr(
        "backend.services.ai_fund_reconciliation.safe_query_supabase_as_service_role",
        lambda endpoint, method="GET", json_data=None, params=None: (
            [{
                "id": "ledger-order-1",
                "exchange_order_id": "exchange-order-1",
                "client_order_id": "client-order-1",
                "symbol": "BTC",
                "side": "BUY",
                "order_type": "LIMIT",
                "requested_qty": 1.0,
                "requested_price": 100.0,
            }] if method == "GET" else writes.append((endpoint, json_data)) or []
        ),
    )
    ledger = MagicMock()
    ledger.apply_new_fill.return_value = 25000000.0
    client = MagicMock()
    client.get_order_status.return_value = None

    result = AiFundReconciliationService(ledger).reconcile_config(
        {"id": "config-1", "user_id": "user-1", "exchange_type": "coinone"},
        client,
    )

    assert result.needs_review_count == 1
    assert any(write[1].get("status") == "NEEDS_REVIEW" for write in writes)
    ledger.apply_new_fill.assert_not_called()


def test_reconcile_applies_only_new_partial_fill(monkeypatch):
    updates = []
    monkeypatch.setattr(
        "backend.services.ai_fund_reconciliation.safe_query_supabase_as_service_role",
        lambda endpoint, method="GET", json_data=None, params=None: (
            [{
                "id": "ledger-order-1",
                "exchange_order_id": "exchange-order-1",
                "client_order_id": "client-order-1",
                "symbol": "BTC",
                "side": "BUY",
                "order_type": "LIMIT",
                "requested_qty": 1.0,
                "requested_price": 100.0,
            }] if method == "GET" else updates.append(json_data) or []
        ),
    )
    ledger = MagicMock()
    ledger.apply_new_fill.return_value = 0.4
    client = MagicMock()
    client.get_order_status.return_value = {
        "order_id": "exchange-order-1",
        "status": "PARTIALLY_FILLED",
        "executed_qty": 0.4,
        "price": 100.0,
    }

    result = AiFundReconciliationService(ledger).reconcile_config(
        {"id": "config-1", "user_id": "user-1", "exchange_type": "coinone"},
        client,
    )

    assert result.updated_count == 1
    assert updates[0]["status"] == "PARTIALLY_FILLED"
    ledger.apply_new_fill.assert_called_once()
    assert any(
        payload.get("symbol") == "BTC" and payload.get("executed_qty") == 0.4
        for payload in updates
    )


def test_reconcile_recovers_needs_review_order_with_exchange_order_id(monkeypatch):
    updates = []
    pending_review_order = {
        "id": "ledger-order-1",
        "exchange_order_id": "exchange-order-1",
        "client_order_id": "client-order-1",
        "symbol": "BTT",
        "side": "BUY",
        "order_type": "LIMIT",
        "requested_qty": 25000000.0,
        "requested_price": 0.000402,
        "status": "NEEDS_REVIEW",
    }

    def query(endpoint, method="GET", json_data=None, params=None):
        if method == "GET":
            return [pending_review_order] if "NEEDS_REVIEW" in params["status"] else []
        updates.append(json_data)
        return []

    monkeypatch.setattr(
        "backend.services.ai_fund_reconciliation.safe_query_supabase_as_service_role",
        query,
    )
    ledger = MagicMock()
    ledger.apply_new_fill.return_value = 25000000.0
    client = MagicMock()
    client.get_order_status.return_value = {
        "order_id": "exchange-order-1",
        "status": "FILLED",
        "executed_qty": 25000000.0,
        "average_fill_price": 0.0004,
    }

    result = AiFundReconciliationService(ledger).reconcile_config(
        {"id": "config-1", "user_id": "user-1", "exchange_type": "coinone"},
        client,
    )

    assert result.updated_count == 1
    assert updates[0]["status"] == "FILLED"
    assert updates[0]["filled_qty"] == 25000000.0
    ledger.apply_new_fill.assert_called_once()
