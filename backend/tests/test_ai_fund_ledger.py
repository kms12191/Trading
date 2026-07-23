from backend.services.ai_fund_exchange import ExchangeOrder
from backend.services.ai_fund_ledger import AiFundLedger


def test_apply_new_buy_fill_updates_position_and_sellable_quantity(monkeypatch):
    writes = []

    def fake_query(endpoint, method="GET", json_data=None, params=None, **_kwargs):
        if method == "GET" and endpoint == "ai_fund_positions":
            return []
        writes.append((endpoint, method, json_data, params))
        return [json_data] if json_data else []

    monkeypatch.setattr(
        "backend.services.ai_fund_ledger.safe_query_supabase_as_service_role",
        fake_query,
    )
    ledger = AiFundLedger("user-1", "coinone")
    order = ExchangeOrder(
        exchange_order_id="exchange-1",
        client_order_id="client-1",
        symbol="BTC",
        side="BUY",
        requested_qty=1.0,
        filled_qty=0.4,
        average_fill_price=100.0,
        status="PARTIALLY_FILLED",
        fee=1.0,
    )

    ledger.apply_new_fill(order)

    position_write = next(item for item in writes if item[0] == "ai_fund_positions")
    assert position_write[2]["quantity"] == 0.4
    assert position_write[2]["average_entry_price"] == 100.0


def test_apply_new_fill_requests_insert_representation_before_updating_position(monkeypatch):
    fill_insert_headers = []

    def fake_query(endpoint, method="GET", json_data=None, params=None, extra_headers=None, **_kwargs):
        if endpoint == "ai_fund_positions" and method == "GET":
            return []
        if endpoint == "ai_fund_fills" and method == "GET":
            return []
        if endpoint == "ai_fund_fills" and method == "POST":
            fill_insert_headers.append(extra_headers)
            return [json_data]
        return [json_data] if json_data else []

    monkeypatch.setattr("backend.services.ai_fund_ledger.safe_query_supabase_as_service_role", fake_query)
    ledger = AiFundLedger("user-1", "coinone")
    order = ExchangeOrder(
        exchange_order_id="exchange-1",
        client_order_id="client-1",
        symbol="BTC",
        side="BUY",
        requested_qty=1.0,
        filled_qty=0.4,
        average_fill_price=100.0,
        status="PARTIALLY_FILLED",
        fee=1.0,
    )

    assert ledger.apply_new_fill(order, order_id="ledger-order-1") == 0.4
    assert fill_insert_headers == [{"Prefer": "return=representation"}]


def test_sellable_quantity_subtracts_open_sell_reservations(monkeypatch):
    monkeypatch.setattr(
        "backend.services.ai_fund_ledger.safe_query_supabase_as_service_role",
        lambda endpoint, method="GET", **_kwargs: (
            [{"quantity": 1.0}] if endpoint == "ai_fund_positions" else
            [{"requested_qty": 0.3}] if endpoint == "ai_fund_orders" else []
        ),
    )
    ledger = AiFundLedger("user-1", "coinone")

    assert ledger.get_sellable_quantity("BTC") == 0.7


def test_failed_fill_insert_does_not_update_position(monkeypatch):
    writes = []

    def fake_query(endpoint, method="GET", json_data=None, params=None, **_kwargs):
        if endpoint == "ai_fund_positions" and method == "GET":
            return []
        if endpoint == "ai_fund_fills" and method == "GET":
            return []
        if endpoint == "ai_fund_fills" and method == "POST":
            return []
        writes.append((endpoint, method, json_data, params))
        return [json_data] if json_data else []

    monkeypatch.setattr(
        "backend.services.ai_fund_ledger.safe_query_supabase_as_service_role",
        fake_query,
    )
    ledger = AiFundLedger("user-1", "coinone")
    order = ExchangeOrder(
        exchange_order_id="exchange-1",
        client_order_id="client-1",
        symbol="BTC",
        side="BUY",
        requested_qty=1.0,
        filled_qty=0.4,
        average_fill_price=100.0,
        status="PARTIALLY_FILLED",
        fee=1.0,
    )

    applied_quantity = ledger.apply_new_fill(order, order_id="ledger-order-1")

    assert applied_quantity == 0.0
    assert all(endpoint != "ai_fund_positions" for endpoint, *_ in writes)


def test_update_exit_policy_patches_only_matching_position(monkeypatch):
    writes = []

    def fake_query(endpoint, method="GET", json_data=None, params=None, **_kwargs):
        writes.append((endpoint, method, json_data, params))
        return [json_data] if json_data else []

    monkeypatch.setattr(
        "backend.services.ai_fund_ledger.safe_query_supabase_as_service_role",
        fake_query,
    )
    ledger = AiFundLedger("user-1", "coinone")

    ledger.update_exit_policy("btc", {"highest_price": 110.0})

    assert writes == [
        (
            "ai_fund_positions?user_id=eq.user-1&exchange_type=eq.coinone&strategy_id=eq.ml_signal&symbol=eq.BTC",
            "PATCH",
            {"exit_policy": {"highest_price": 110.0}},
            None,
        )
    ]
