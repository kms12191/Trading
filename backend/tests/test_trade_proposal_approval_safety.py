import pytest

from backend.app import app
from backend.routes import trade
from backend.services import binance_client as binance_module
from backend.services.binance_client import BinanceClient
from backend.routes.trade import (
    _claim_trade_proposal_for_execution,
    _create_or_load_manual_order_proposal,
    _exceeds_real_order_limit,
)


MANUAL_ORDER_KEY = "11111111-1111-4111-8111-111111111111"


def _safe_precheck(**overrides):
    payload = {
        "reference_price": 800.0,
        "estimated_amount": 8000.0,
        "estimated_amount_krw": 8000.0,
        "available_cash": 100000.0,
        "holding_qty": 100.0,
        "balance_check_failed": False,
        "exceeds_real_order_limit": False,
        "is_market_closed": False,
        "futures_real_blocked": False,
        "insufficient_permission": False,
        "insufficient_cash": False,
        "insufficient_holding": False,
    }
    payload.update(overrides)
    return payload


class FakeOrderClient:
    def __init__(self, status="OPEN"):
        self.place_order_calls = 0
        self.status = status
        self.last_order_kwargs = None

    def place_order(self, **kwargs):
        self.place_order_calls += 1
        self.last_order_kwargs = kwargs
        return {
            "status": self.status,
            "order_id": "order-1",
            "client_order_id": "client-1",
            "raw": {},
        }


class TossClient(FakeOrderClient):
    def get_exchange_rate(self):
        return 1500.0

    def get_balance(self):
        return {
            "available_cash": 10000.0,
            "available_cash_details": {
                "components": [
                    {"currency": "USD", "cash_buying_power": 10000.0},
                ],
            },
            "holdings": [],
        }


class BalanceOrderClient(FakeOrderClient):
    def __init__(
        self,
        *,
        available_cash=1000.0,
        holding_qty=2.0,
        holding_symbol="XRP",
        base_asset=None,
        fail_balance=False,
    ):
        super().__init__()
        self.available_cash = available_cash
        self.holding_qty = holding_qty
        self.holding_symbol = holding_symbol
        self.base_asset = base_asset
        self.fail_balance = fail_balance
        self.symbol_info_calls = []
        self.coinone_order_rules = None
        self.binance_symbol_info = None

    def get_balance(self):
        if self.fail_balance:
            raise RuntimeError("balance unavailable")
        return {
            "available_cash": self.available_cash,
            "holdings": [
                {"symbol": self.holding_symbol, "qty": self.holding_qty, "current_price": 800.0},
            ],
        }

    def test_order(self, **kwargs):
        return {"success": True}

    def get_spot_symbol_info(self, symbol):
        self.symbol_info_calls.append(symbol)
        return self.binance_symbol_info or {
            "symbol": symbol,
            "base_asset": self.base_asset or self.holding_symbol,
            "quote_asset": "EUR",
        }

    def get_order_quantity_rules(self, symbol):
        if self.coinone_order_rules is None:
            return {}
        return dict(self.coinone_order_rules)


def test_real_order_limit_applies_only_to_real_orders():
    assert _exceeds_real_order_limit("REAL", 100001) is True
    assert _exceeds_real_order_limit("REAL", 100000) is False
    assert _exceeds_real_order_limit("MOCK", 5000000) is False


def test_real_order_limit_rejects_non_finite_amounts():
    assert _exceeds_real_order_limit("REAL", float("nan")) is True
    assert _exceeds_real_order_limit("REAL", float("inf")) is True


def test_claim_trade_proposal_returns_none_after_first_claim(monkeypatch):
    calls = []

    def fake_query(auth_header, endpoint, method="GET", json_data=None, params=None):
        assert endpoint == "rpc/claim_trade_proposal_for_execution"
        calls.append(json_data["p_proposal_id"])
        if len(calls) == 1:
            return [{"id": "proposal-1", "status": "APPROVED"}]
        return []

    monkeypatch.setattr("backend.routes.trade.query_supabase", fake_query)

    assert _claim_trade_proposal_for_execution("Bearer test", "proposal-1")["status"] == "APPROVED"
    assert _claim_trade_proposal_for_execution("Bearer test", "proposal-1") is None


def test_manual_order_idempotency_creates_pending_proposal_before_execution(monkeypatch):
    calls = []

    def fake_query(
        auth_header,
        endpoint,
        method="GET",
        json_data=None,
        params=None,
        extra_headers=None,
    ):
        calls.append((endpoint, method, json_data, extra_headers))
        return [{**json_data}]

    monkeypatch.setattr(trade, "query_supabase", fake_query)

    proposal, created = _create_or_load_manual_order_proposal(
        "Bearer test",
        "user-1",
        MANUAL_ORDER_KEY,
        {
            "exchange": "COINONE",
            "symbol": "XRP",
            "action": "BUY",
            "order_type": "LIMIT",
            "broker_env": "MOCK",
            "quantity": 10,
            "price": 800,
        },
    )

    assert created is True
    assert proposal["id"] == MANUAL_ORDER_KEY
    assert proposal["status"] == "PENDING"
    assert calls[0][0:2] == ("trade_proposals", "POST")
    assert calls[0][3] == {"Prefer": "return=representation"}


def test_manual_order_duplicate_loads_existing_proposal_without_new_insert(monkeypatch):
    existing = {
        "id": MANUAL_ORDER_KEY,
        "user_id": "user-1",
        "exchange": "COINONE",
        "symbol": "XRP",
        "side": "BUY",
        "ord_type": "LIMIT",
        "broker_env": "MOCK",
        "volume": "10",
        "price": "800",
        "status": "APPROVED",
    }

    def fake_query(*args, **kwargs):
        raise RuntimeError("duplicate key value violates unique constraint (23505)")

    monkeypatch.setattr(trade, "query_supabase", fake_query)
    monkeypatch.setattr(trade, "_load_user_trade_proposal", lambda *args: existing)

    proposal, created = _create_or_load_manual_order_proposal(
        "Bearer test",
        "user-1",
        MANUAL_ORDER_KEY,
        {
            "exchange": "COINONE",
            "symbol": "XRP",
            "action": "BUY",
            "order_type": "LIMIT",
            "broker_env": "MOCK",
            "quantity": 10,
            "price": 800,
        },
    )

    assert created is False
    assert proposal is existing


def test_manual_order_duplicate_rejects_idempotency_key_reuse_for_different_order(monkeypatch):
    existing = {
        "id": MANUAL_ORDER_KEY,
        "user_id": "user-1",
        "exchange": "COINONE",
        "symbol": "XRP",
        "side": "BUY",
        "ord_type": "LIMIT",
        "broker_env": "MOCK",
        "volume": "9",
        "price": "800",
        "status": "PENDING",
    }
    monkeypatch.setattr(
        trade,
        "query_supabase",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            RuntimeError("duplicate key value violates unique constraint (23505)")
        ),
    )
    monkeypatch.setattr(trade, "_load_user_trade_proposal", lambda *args: existing)

    with pytest.raises(ValueError, match="다른 주문"):
        _create_or_load_manual_order_proposal(
            "Bearer test",
            "user-1",
            MANUAL_ORDER_KEY,
            {
                "exchange": "COINONE",
                "symbol": "XRP",
                "action": "BUY",
                "order_type": "LIMIT",
                "broker_env": "MOCK",
                "quantity": 10,
                "price": 800,
            },
        )


def test_manual_order_duplicate_rejects_changed_futures_execution_options(monkeypatch):
    created_rows = []

    def create_query(
        auth_header,
        endpoint,
        method="GET",
        json_data=None,
        params=None,
        extra_headers=None,
    ):
        created_rows.append({**json_data})
        return [{**json_data}]

    monkeypatch.setattr(trade, "query_supabase", create_query)
    original = {
        "exchange": "BINANCE_UM_FUTURES",
        "symbol": "BTCUSDT",
        "action": "SELL",
        "order_type": "LIMIT",
        "broker_env": "MOCK",
        "quantity": 0.01,
        "price": 50000,
        "position_side": "BOTH",
        "reduce_only": True,
        "leverage": 3,
        "margin_type": "ISOLATED",
    }
    _create_or_load_manual_order_proposal(
        "Bearer test",
        "user-1",
        MANUAL_ORDER_KEY,
        original,
    )

    monkeypatch.setattr(
        trade,
        "query_supabase",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            RuntimeError("duplicate key value violates unique constraint (23505)")
        ),
    )
    monkeypatch.setattr(trade, "_load_user_trade_proposal", lambda *args: created_rows[0])

    with pytest.raises(ValueError, match="다른 주문"):
        _create_or_load_manual_order_proposal(
            "Bearer test",
            "user-1",
            MANUAL_ORDER_KEY,
            {**original, "reduce_only": False},
        )


def test_reject_pending_proposal_uses_atomic_status_filter(monkeypatch):
    calls = []

    def fake_query(
        auth_header,
        endpoint,
        method="GET",
        json_data=None,
        params=None,
        extra_headers=None,
    ):
        calls.append({
            "endpoint": endpoint,
            "method": method,
            "json_data": json_data,
            "params": params,
            "extra_headers": extra_headers,
        })
        return [{"id": "proposal-1", "status": "REJECTED"}]

    monkeypatch.setattr(trade, "query_supabase", fake_query)

    rejected = trade._reject_pending_trade_proposal(
        "Bearer test",
        "user-1",
        "proposal-1",
    )

    assert rejected["status"] == "REJECTED"
    assert calls == [{
        "endpoint": "trade_proposals",
        "method": "PATCH",
        "json_data": {"status": "REJECTED"},
        "params": {
            "id": "eq.proposal-1",
            "user_id": "eq.user-1",
            "status": "eq.PENDING",
        },
        "extra_headers": {"Prefer": "return=representation"},
    }]


def test_order_receipt_patch_requires_exactly_one_updated_row(monkeypatch):
    monkeypatch.setattr(trade, "query_supabase", lambda *args, **kwargs: [])

    with pytest.raises(RuntimeError, match="정확히 1행"):
        trade._patch_trade_proposal_returning(
            "Bearer test",
            "user-1",
            "proposal-1",
            {"status": "APPROVED", "external_order_id": "order-1"},
        )


def test_reject_endpoint_returns_conflict_when_pending_claim_is_lost(monkeypatch):
    monkeypatch.setattr(trade, "get_user_id_from_header", lambda auth_header: ("user-1", "token"))
    monkeypatch.setattr(
        trade,
        "_reject_pending_trade_proposal",
        lambda *args: None,
        raising=False,
    )

    response = app.test_client().post(
        "/api/trade/proposal/reject",
        headers={"Authorization": "Bearer test"},
        json={"proposal_id": "proposal-1"},
    )

    assert response.status_code == 409


def test_same_proposal_is_sent_to_exchange_only_once(monkeypatch):
    order_client = FakeOrderClient()
    claims = iter([
        {"id": "proposal-1", "status": "APPROVED"},
        None,
    ])
    proposal = {
        "id": "proposal-1",
        "status": "PENDING",
        "exchange": "COINONE",
        "symbol": "XRP",
        "side": "BUY",
        "ord_type": "LIMIT",
        "price": 800,
        "volume": 10,
        "broker_env": "MOCK",
    }

    monkeypatch.setattr(trade, "get_user_id_from_header", lambda auth_header: ("user-1", "token"))
    monkeypatch.setattr(trade, "_load_user_trade_proposal", lambda *args: dict(proposal))
    monkeypatch.setattr(trade, "_load_user_exchange_record", lambda *args: ({}, "access", "secret"))
    monkeypatch.setattr(trade, "_build_precheck_payload", lambda **kwargs: _safe_precheck())
    monkeypatch.setattr(trade, "_claim_trade_proposal_for_execution", lambda *args: next(claims))
    monkeypatch.setattr(trade, "_build_exchange_client", lambda *args: order_client)
    monkeypatch.setattr(
        trade,
        "_patch_trade_proposal_returning",
        lambda *args, **kwargs: {"id": "proposal-1"},
    )

    client = app.test_client()
    first = client.post(
        "/api/trade/proposal/approve",
        headers={"Authorization": "Bearer test"},
        json={"proposal_id": "proposal-1"},
    )
    second = client.post(
        "/api/trade/proposal/approve",
        headers={"Authorization": "Bearer test"},
        json={"proposal_id": "proposal-1"},
    )

    assert first.status_code == 200
    assert second.status_code == 409
    assert order_client.place_order_calls == 1


def test_manual_real_order_limit_blocks_before_exchange_order(monkeypatch):
    order_client = FakeOrderClient()
    monkeypatch.setattr(trade, "get_user_id_from_header", lambda auth_header: ("user-1", "token"))
    monkeypatch.setattr(trade, "_load_user_exchange_record", lambda *args: ({}, "access", "secret"))
    monkeypatch.setattr(
        trade,
        "_build_precheck_payload",
        lambda **kwargs: _safe_precheck(
            estimated_amount=100001.0,
            estimated_amount_krw=100001.0,
            exceeds_real_order_limit=True,
        ),
    )
    monkeypatch.setattr(trade, "_build_exchange_client", lambda *args: order_client)
    monkeypatch.setattr(trade, "_insert_trade_proposal_with_schema_fallback", lambda *args: None)

    response = app.test_client().post(
        "/api/trade/order",
        headers={"Authorization": "Bearer test"},
        json={
            "exchange": "COINONE",
            "symbol": "XRP",
            "action": "BUY",
            "order_type": "LIMIT",
            "price": 100001,
            "quantity": 1,
            "broker_env": "REAL",
        },
    )

    assert response.status_code == 400
    assert "100,000원" in response.get_json()["message"]
    assert order_client.place_order_calls == 0


def test_manual_order_requires_idempotency_key_before_exchange_order(monkeypatch):
    order_client = FakeOrderClient()
    monkeypatch.setattr(trade, "get_user_id_from_header", lambda auth_header: ("user-1", "token"))
    monkeypatch.setattr(trade, "_load_user_exchange_record", lambda *args: ({}, "access", "secret"))
    monkeypatch.setattr(trade, "_build_precheck_payload", lambda **kwargs: _safe_precheck())
    monkeypatch.setattr(trade, "_build_exchange_client", lambda *args: order_client)

    response = app.test_client().post(
        "/api/trade/order",
        headers={"Authorization": "Bearer test"},
        json={
            "exchange": "COINONE",
            "symbol": "XRP",
            "action": "BUY",
            "order_type": "LIMIT",
            "price": 800,
            "quantity": 10,
            "broker_env": "MOCK",
        },
    )

    assert response.status_code == 400
    assert "idempotency_key" in response.get_json()["message"]
    assert order_client.place_order_calls == 0


def test_manual_order_missing_api_key_returns_user_friendly_message_before_precheck(monkeypatch):
    order_client = FakeOrderClient()
    monkeypatch.setattr(trade, "get_user_id_from_header", lambda auth_header: ("user-1", "token"))
    monkeypatch.setattr(
        trade,
        "_load_user_exchange_record",
        lambda *args: (_ for _ in ()).throw(
            ValueError("등록된 COINONE (REAL) API 크리덴셜 정보가 없습니다.")
        ),
    )
    monkeypatch.setattr(
        trade,
        "_build_precheck_payload",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("API 키 없음은 사전검증 전에 차단되어야 합니다.")),
    )
    monkeypatch.setattr(trade, "_build_exchange_client", lambda *args: order_client)

    response = app.test_client().post(
        "/api/trade/order",
        headers={"Authorization": "Bearer test"},
        json={
            "exchange": "COINONE",
            "symbol": "XRP",
            "action": "BUY",
            "order_type": "LIMIT",
            "price": 800,
            "quantity": 10,
            "broker_env": "REAL",
            "idempotency_key": MANUAL_ORDER_KEY,
        },
    )

    assert response.status_code == 400
    assert "API 키" in response.get_json()["message"]
    assert order_client.place_order_calls == 0


def test_same_manual_order_idempotency_key_is_sent_to_exchange_only_once(monkeypatch):
    order_client = FakeOrderClient()
    claims = iter([
        {"id": MANUAL_ORDER_KEY, "status": "APPROVED"},
        None,
    ])
    pending = {
        "id": MANUAL_ORDER_KEY,
        "status": "PENDING",
        "exchange": "COINONE",
        "symbol": "XRP",
        "side": "BUY",
        "ord_type": "LIMIT",
        "price": 800,
        "volume": 10,
        "broker_env": "MOCK",
    }
    monkeypatch.setattr(trade, "get_user_id_from_header", lambda auth_header: ("user-1", "token"))
    monkeypatch.setattr(trade, "_load_user_exchange_record", lambda *args: ({}, "access", "secret"))
    monkeypatch.setattr(trade, "_build_precheck_payload", lambda **kwargs: _safe_precheck())
    monkeypatch.setattr(
        trade,
        "_create_or_load_manual_order_proposal",
        lambda *args, **kwargs: (dict(pending), True),
    )
    monkeypatch.setattr(trade, "_claim_trade_proposal_for_execution", lambda *args: next(claims))
    monkeypatch.setattr(trade, "_build_exchange_client", lambda *args: order_client)
    monkeypatch.setattr(
        trade,
        "_patch_trade_proposal_returning",
        lambda *args, **kwargs: {"id": MANUAL_ORDER_KEY},
    )

    payload = {
        "idempotency_key": MANUAL_ORDER_KEY,
        "exchange": "COINONE",
        "symbol": "XRP",
        "action": "BUY",
        "order_type": "LIMIT",
        "price": 800,
        "quantity": 10,
        "broker_env": "MOCK",
    }
    client = app.test_client()
    first = client.post(
        "/api/trade/order",
        headers={"Authorization": "Bearer test"},
        json=payload,
    )
    second = client.post(
        "/api/trade/order",
        headers={"Authorization": "Bearer test"},
        json=payload,
    )

    assert first.status_code == 200
    assert second.status_code == 409
    assert order_client.place_order_calls == 1


@pytest.mark.parametrize("side", ["BUY", "SELL"])
def test_manual_order_source_is_preserved_after_order_receipt_update(monkeypatch, side):
    order_client = FakeOrderClient(status="OPEN")
    patched_payloads = []
    manual_proposal = {
        "id": MANUAL_ORDER_KEY,
        "status": "PENDING",
        "exchange": "COINONE",
        "symbol": "XRP",
        "side": side,
        "ord_type": "LIMIT",
        "price": 800,
        "volume": 10,
        "broker_env": "MOCK",
        "raw_order_payload": {
            "source": "MANUAL_ORDER",
            "idempotency_fingerprint": "fingerprint-1",
        },
    }

    monkeypatch.setattr(trade, "get_user_id_from_header", lambda auth_header: ("user-1", "token"))
    monkeypatch.setattr(trade, "_load_user_exchange_record", lambda *args: ({}, "access", "secret"))
    monkeypatch.setattr(trade, "_build_precheck_payload", lambda **kwargs: _safe_precheck())
    monkeypatch.setattr(trade, "_build_exchange_client", lambda *args: order_client)
    monkeypatch.setattr(
        trade,
        "_create_or_load_manual_order_proposal",
        lambda *args, **kwargs: (dict(manual_proposal), True),
    )
    monkeypatch.setattr(
        trade,
        "_claim_trade_proposal_for_execution",
        lambda *args: {**manual_proposal, "status": "APPROVED"},
    )
    monkeypatch.setattr(
        trade,
        "_patch_trade_proposal_returning",
        lambda auth_header, user_id, proposal_id, payload: patched_payloads.append(payload)
        or {"id": proposal_id},
    )

    response = app.test_client().post(
        "/api/trade/order",
        headers={"Authorization": "Bearer test"},
        json={
            "idempotency_key": MANUAL_ORDER_KEY,
            "exchange": "COINONE",
            "symbol": "XRP",
            "action": side,
            "order_type": "LIMIT",
            "price": 800,
            "quantity": 10,
            "broker_env": "MOCK",
        },
    )

    assert response.status_code == 200
    assert len(patched_payloads) >= 2
    for payload in patched_payloads:
        assert payload["raw_order_payload"]["source"] == "MANUAL_ORDER"


def test_mock_precheck_keeps_cash_and_holding_safety_gates(monkeypatch):
    order_client = BalanceOrderClient(available_cash=1000.0, holding_qty=2.0)
    monkeypatch.setattr(trade, "_build_exchange_client", lambda *args: order_client)

    buy_precheck = trade._build_precheck_payload(
        exchange="COINONE",
        symbol="XRP",
        action="BUY",
        order_type="LIMIT",
        quantity=10,
        price=800,
        broker_env="MOCK",
        record={},
        access_key="access",
        secret_key="secret",
    )
    sell_precheck = trade._build_precheck_payload(
        exchange="COINONE",
        symbol="XRP",
        action="SELL",
        order_type="LIMIT",
        quantity=3,
        price=800,
        broker_env="MOCK",
        record={},
        access_key="access",
        secret_key="secret",
    )

    assert buy_precheck["balance_check_failed"] is False
    assert buy_precheck["insufficient_cash"] is True
    assert sell_precheck["balance_check_failed"] is False
    assert sell_precheck["insufficient_holding"] is True


def test_precheck_marks_balance_lookup_failure_as_blocker(monkeypatch):
    order_client = BalanceOrderClient(fail_balance=True)
    monkeypatch.setattr(trade, "_build_exchange_client", lambda *args: order_client)

    precheck = trade._build_precheck_payload(
        exchange="COINONE",
        symbol="XRP",
        action="BUY",
        order_type="LIMIT",
        quantity=1,
        price=800,
        broker_env="MOCK",
        record={},
        access_key="access",
        secret_key="secret",
    )

    assert precheck["balance_check_failed"] is True


@pytest.mark.parametrize("exchange", ["TOSS", "KIS"])
def test_stock_precheck_rejects_fractional_quantity_without_verified_fractional_order_support(monkeypatch, exchange):
    order_client = TossClient() if exchange == "TOSS" else BalanceOrderClient()
    monkeypatch.setattr(trade, "_build_exchange_client", lambda *args: order_client)
    monkeypatch.setattr(trade, "is_kr_market_open", lambda *args: True)

    with pytest.raises(ValueError, match="정수"):
        trade._build_precheck_payload(
            exchange=exchange,
            symbol="005930",
            action="BUY",
            order_type="LIMIT",
            quantity=0.5,
            price=70000,
            broker_env="MOCK",
            record={},
            access_key="access",
            secret_key="secret",
        )


def test_coinone_precheck_floors_quantity_to_qty_unit(monkeypatch):
    order_client = BalanceOrderClient(available_cash=1000.0, holding_qty=2.0)
    order_client.coinone_order_rules = {
        "min_qty": 0.01,
        "max_qty": 10,
        "qty_unit": 0.0001,
    }
    monkeypatch.setattr(trade, "_build_exchange_client", lambda *args: order_client)

    precheck = trade._build_precheck_payload(
        exchange="COINONE",
        symbol="XRP",
        action="BUY",
        order_type="LIMIT",
        quantity=0.123456,
        price=800,
        broker_env="MOCK",
        record={},
        access_key="access",
        secret_key="secret",
    )

    assert precheck["quantity"] == 0.1234
    assert precheck["quantity_filter"]["step_size"] == 0.0001
    assert precheck["quantity_filter"]["adjusted"] is True
    assert precheck["estimated_amount"] == pytest.approx(98.72)


def test_coinone_precheck_rejects_quantity_below_min_after_floor(monkeypatch):
    order_client = BalanceOrderClient(available_cash=1000.0, holding_qty=2.0)
    order_client.coinone_order_rules = {
        "min_qty": 0.01,
        "max_qty": 10,
        "qty_unit": 0.0001,
    }
    monkeypatch.setattr(trade, "_build_exchange_client", lambda *args: order_client)

    with pytest.raises(ValueError, match="최소 주문 수량"):
        trade._build_precheck_payload(
            exchange="COINONE",
            symbol="XRP",
            action="BUY",
            order_type="LIMIT",
            quantity=0.00999,
            price=800,
            broker_env="MOCK",
            record={},
            access_key="access",
            secret_key="secret",
        )


def test_binance_spot_precheck_floors_quantity_to_lot_step(monkeypatch):
    order_client = BalanceOrderClient(available_cash=1000.0, holding_qty=2.0, holding_symbol="BTC")
    order_client.binance_symbol_info = {
        "symbol": "BTCUSDT",
        "base_asset": "BTC",
        "quote_asset": "USDT",
        "min_qty": 0.001,
        "max_qty": 100,
        "step_size": 0.001,
    }
    monkeypatch.setattr(trade, "_build_exchange_client", lambda *args: order_client)

    precheck = trade._build_precheck_payload(
        exchange="BINANCE",
        symbol="BTCUSDT",
        action="SELL",
        order_type="LIMIT",
        quantity=0.123456,
        price=30000,
        broker_env="MOCK",
        record={},
        access_key="access",
        secret_key="secret",
    )

    assert precheck["quantity"] == 0.123
    assert precheck["quantity_filter"]["step_size"] == 0.001
    assert precheck["quantity_filter"]["adjusted"] is True
    assert order_client.symbol_info_calls == ["BTCUSDT"]


def test_binance_mock_sell_matches_base_asset_holding(monkeypatch):
    order_client = BalanceOrderClient(
        available_cash=1000.0,
        holding_qty=2.0,
        holding_symbol="BTC",
        base_asset="BTC",
    )
    monkeypatch.setattr(trade, "_build_exchange_client", lambda *args: order_client)

    precheck = trade._build_precheck_payload(
        exchange="BINANCE",
        symbol="BTCEUR",
        action="SELL",
        order_type="LIMIT",
        quantity=1,
        price=30000,
        broker_env="MOCK",
        record={},
        access_key="access",
        secret_key="secret",
    )

    assert precheck["holding_qty"] == 2
    assert precheck["balance_check_failed"] is False
    assert precheck["insufficient_holding"] is False
    assert order_client.symbol_info_calls == ["BTCEUR"]


def test_binance_spot_symbol_info_returns_exchange_base_asset(monkeypatch):
    class FakeResponse:
        status_code = 200

        @staticmethod
        def json():
            return {
                "symbols": [
                    {
                        "symbol": "BTCEUR",
                        "baseAsset": "BTC",
                        "quoteAsset": "EUR",
                        "filters": [
                            {
                                "filterType": "LOT_SIZE",
                                "minQty": "0.00100000",
                                "maxQty": "100.00000000",
                                "stepSize": "0.00100000",
                            },
                            {
                                "filterType": "MARKET_LOT_SIZE",
                                "minQty": "0.00200000",
                                "maxQty": "50.00000000",
                                "stepSize": "0.00200000",
                            },
                        ],
                    }
                ]
            }

    binance_module._SPOT_SYMBOL_INFO_CACHE.clear()
    monkeypatch.setattr(binance_module.requests, "get", lambda *args, **kwargs: FakeResponse())

    info = BinanceClient("api-key", "secret-key", env="MOCK").get_spot_symbol_info("BTC/EUR")

    assert info == {
        "symbol": "BTCEUR",
        "base_asset": "BTC",
        "quote_asset": "EUR",
        "min_qty": 0.001,
        "max_qty": 100.0,
        "step_size": 0.001,
        "market_min_qty": 0.002,
        "market_max_qty": 50.0,
        "market_step_size": 0.002,
        "tick_size": 0.0,
    }


def test_precheck_rejects_non_finite_limit_price(monkeypatch):
    monkeypatch.setattr(trade, "_build_exchange_client", lambda *args: BalanceOrderClient())

    with pytest.raises(ValueError, match="유한"):
        trade._build_precheck_payload(
            exchange="COINONE",
            symbol="XRP",
            action="BUY",
            order_type="LIMIT",
            quantity=1,
            price=float("nan"),
            broker_env="MOCK",
            record={},
            access_key="access",
            secret_key="secret",
        )


def test_manual_order_rejects_nan_quantity_before_precheck(monkeypatch):
    monkeypatch.setattr(trade, "get_user_id_from_header", lambda auth_header: ("user-1", "token"))
    monkeypatch.setattr(
        trade,
        "_load_user_exchange_record",
        lambda *args: (_ for _ in ()).throw(AssertionError("NaN은 크리덴셜 조회 전에 차단되어야 합니다.")),
    )

    response = app.test_client().post(
        "/api/trade/order",
        headers={"Authorization": "Bearer test"},
        json={
            "exchange": "COINONE",
            "symbol": "XRP",
            "action": "BUY",
            "order_type": "LIMIT",
            "price": 800,
            "quantity": "NaN",
            "broker_env": "REAL",
        },
    )

    assert response.status_code == 400
    assert "유한" in response.get_json()["message"]


def test_real_market_order_is_blocked_when_hard_cap_cannot_be_guaranteed(monkeypatch):
    monkeypatch.setattr(trade, "get_user_id_from_header", lambda auth_header: ("user-1", "token"))
    monkeypatch.setattr(
        trade,
        "_load_user_exchange_record",
        lambda *args: (_ for _ in ()).throw(AssertionError("REAL 시장가는 크리덴셜 조회 전에 차단되어야 합니다.")),
    )

    response = app.test_client().post(
        "/api/trade/order",
        headers={"Authorization": "Bearer test"},
        json={
            "exchange": "TOSS",
            "symbol": "005930",
            "action": "BUY",
            "order_type": "MARKET",
            "quantity": 1,
            "broker_env": "REAL",
        },
    )

    assert response.status_code == 400
    assert "지정가" in response.get_json()["message"]


def test_invalid_auto_exit_numbers_are_rejected_before_external_order(monkeypatch):
    order_client = FakeOrderClient()
    monkeypatch.setattr(trade, "get_user_id_from_header", lambda auth_header: ("user-1", "token"))
    monkeypatch.setattr(trade, "_load_user_exchange_record", lambda *args: ({}, "access", "secret"))
    monkeypatch.setattr(trade, "_build_precheck_payload", lambda **kwargs: _safe_precheck())
    monkeypatch.setattr(trade, "_build_exchange_client", lambda *args: order_client)

    response = app.test_client().post(
        "/api/trade/order",
        headers={"Authorization": "Bearer test"},
        json={
            "exchange": "COINONE",
            "symbol": "XRP",
            "action": "BUY",
            "order_type": "LIMIT",
            "price": 800,
            "quantity": 10,
            "broker_env": "MOCK",
            "auto_exit": True,
            "target_profit_rate": "not-a-number",
        },
    )

    assert response.status_code == 400
    assert order_client.place_order_calls == 0


def test_order_execution_uses_precheck_normalized_quantity(monkeypatch):
    order_client = FakeOrderClient()
    monkeypatch.setattr(trade, "get_user_id_from_header", lambda auth_header: ("user-1", "token"))
    monkeypatch.setattr(trade, "_load_user_exchange_record", lambda *args: ({}, "access", "secret"))
    monkeypatch.setattr(
        trade,
        "_build_precheck_payload",
        lambda **kwargs: _safe_precheck(quantity=0.1234, estimated_amount=98.72, estimated_amount_krw=98.72),
    )
    monkeypatch.setattr(trade, "_build_exchange_client", lambda *args: order_client)
    monkeypatch.setattr(trade, "_create_or_load_manual_order_proposal", lambda *args: ({
        "id": "manual-normalized-qty",
        "status": "PENDING",
    }, True))
    monkeypatch.setattr(trade, "_claim_trade_proposal_for_execution", lambda *args: {
        "id": "manual-normalized-qty",
        "status": "APPROVED",
    })
    monkeypatch.setattr(trade, "_patch_trade_proposal_returning", lambda *args, **kwargs: {"id": "manual-normalized-qty"})
    monkeypatch.setattr(trade, "_patch_trade_proposal", lambda *args, **kwargs: None)

    response = app.test_client().post(
        "/api/trade/order",
        headers={"Authorization": "Bearer test"},
        json={
            "exchange": "COINONE",
            "symbol": "XRP",
            "action": "BUY",
            "order_type": "LIMIT",
            "price": 800,
            "quantity": 0.123456,
            "broker_env": "MOCK",
            "idempotency_key": MANUAL_ORDER_KEY,
        },
    )

    assert response.status_code == 200
    assert order_client.last_order_kwargs["qty"] == 0.1234


def test_post_order_status_failure_preserves_submitted_proposal(monkeypatch):
    order_client = FakeOrderClient()
    patched_payloads = []
    proposal = {
        "id": "proposal-1",
        "status": "PENDING",
        "exchange": "COINONE",
        "symbol": "XRP",
        "side": "BUY",
        "ord_type": "LIMIT",
        "price": 800,
        "volume": 10,
        "broker_env": "MOCK",
    }

    monkeypatch.setattr(trade, "get_user_id_from_header", lambda auth_header: ("user-1", "token"))
    monkeypatch.setattr(trade, "_load_user_trade_proposal", lambda *args: dict(proposal))
    monkeypatch.setattr(trade, "_load_user_exchange_record", lambda *args: ({}, "access", "secret"))
    monkeypatch.setattr(trade, "_build_precheck_payload", lambda **kwargs: _safe_precheck())
    monkeypatch.setattr(
        trade,
        "_claim_trade_proposal_for_execution",
        lambda *args: {"id": "proposal-1", "status": "APPROVED"},
    )
    monkeypatch.setattr(trade, "_build_exchange_client", lambda *args: order_client)
    monkeypatch.setattr(
        trade,
        "_is_terminal_order_status",
        lambda *args: (_ for _ in ()).throw(RuntimeError("status parser failed")),
    )
    monkeypatch.setattr(
        trade,
        "_patch_trade_proposal_returning",
        lambda auth_header, user_id, proposal_id, payload: patched_payloads.append(payload)
        or {"id": proposal_id},
    )

    response = app.test_client().post(
        "/api/trade/proposal/approve",
        headers={"Authorization": "Bearer test"},
        json={"proposal_id": "proposal-1"},
    )

    assert response.status_code == 200
    assert order_client.place_order_calls == 1
    assert patched_payloads[0]["external_order_id"] == "order-1"
    assert patched_payloads[0]["status"] == "APPROVED"
    assert patched_payloads[-1]["status"] == "APPROVED"
    assert patched_payloads[-1]["external_order_id"] == "order-1"


def test_order_history_failure_returns_do_not_retry_error(monkeypatch):
    order_client = FakeOrderClient()
    proposal = {
        "id": "proposal-1",
        "status": "PENDING",
        "exchange": "COINONE",
        "symbol": "XRP",
        "side": "BUY",
        "ord_type": "LIMIT",
        "price": 800,
        "volume": 10,
        "broker_env": "MOCK",
    }

    monkeypatch.setattr(trade, "get_user_id_from_header", lambda auth_header: ("user-1", "token"))
    monkeypatch.setattr(trade, "_load_user_trade_proposal", lambda *args: dict(proposal))
    monkeypatch.setattr(trade, "_load_user_exchange_record", lambda *args: ({}, "access", "secret"))
    monkeypatch.setattr(trade, "_build_precheck_payload", lambda **kwargs: _safe_precheck())
    monkeypatch.setattr(
        trade,
        "_claim_trade_proposal_for_execution",
        lambda *args: {"id": "proposal-1", "status": "APPROVED"},
    )
    monkeypatch.setattr(trade, "_build_exchange_client", lambda *args: order_client)
    monkeypatch.setattr(
        trade,
        "_patch_trade_proposal_returning",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("database unavailable")),
    )
    monkeypatch.setattr(
        trade,
        "_recover_order_receipt",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("recovery unavailable")),
        raising=False,
    )

    response = app.test_client().post(
        "/api/trade/proposal/approve",
        headers={"Authorization": "Bearer test"},
        json={"proposal_id": "proposal-1"},
    )

    assert response.status_code == 503
    assert response.get_json()["success"] is False
    assert "다시 전송하지" in response.get_json()["error"]["action"]
    assert response.get_json()["order_id"] == "order-1"
    assert order_client.place_order_calls == 1


def test_order_history_full_write_falls_back_to_minimal_receipt(monkeypatch):
    order_client = FakeOrderClient()
    recovered_payloads = []
    proposal = {
        "id": "proposal-1",
        "status": "PENDING",
        "exchange": "COINONE",
        "symbol": "XRP",
        "side": "BUY",
        "ord_type": "LIMIT",
        "price": 800,
        "volume": 10,
        "broker_env": "MOCK",
    }

    monkeypatch.setattr(trade, "get_user_id_from_header", lambda auth_header: ("user-1", "token"))
    monkeypatch.setattr(trade, "_load_user_trade_proposal", lambda *args: dict(proposal))
    monkeypatch.setattr(trade, "_load_user_exchange_record", lambda *args: ({}, "access", "secret"))
    monkeypatch.setattr(trade, "_build_precheck_payload", lambda **kwargs: _safe_precheck())
    monkeypatch.setattr(
        trade,
        "_claim_trade_proposal_for_execution",
        lambda *args: {"id": "proposal-1", "status": "APPROVED"},
    )
    monkeypatch.setattr(trade, "_build_exchange_client", lambda *args: order_client)
    monkeypatch.setattr(
        trade,
        "_patch_trade_proposal_returning",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("full write failed")),
    )
    monkeypatch.setattr(
        trade,
        "_recover_order_receipt",
        lambda auth_header, user_id, payload: recovered_payloads.append(payload) or True,
        raising=False,
    )

    response = app.test_client().post(
        "/api/trade/proposal/approve",
        headers={"Authorization": "Bearer test"},
        json={"proposal_id": "proposal-1"},
    )

    assert response.status_code == 200
    assert response.get_json()["success"] is True
    assert "기본 주문 식별자" in response.get_json()["message"]
    assert recovered_payloads[-1]["external_order_id"] == "order-1"


def test_recover_order_receipt_updates_existing_proposal_with_identifiers(monkeypatch):
    calls = []

    def fake_query(
        auth_header,
        endpoint,
        method="GET",
        json_data=None,
        params=None,
        extra_headers=None,
    ):
        calls.append({
            "endpoint": endpoint,
            "method": method,
            "json_data": json_data,
            "params": params,
            "extra_headers": extra_headers,
        })
        return [{"id": "proposal-1", **(json_data or {})}]

    monkeypatch.setattr(trade, "query_supabase", fake_query)
    monkeypatch.setattr(
        trade,
        "_insert_trade_proposal_with_schema_fallback",
        lambda *args: (_ for _ in ()).throw(AssertionError("기존 제안은 새로 insert하면 안 됩니다.")),
    )

    recovered = trade._recover_order_receipt(
        "Bearer test",
        "user-1",
        {
            "id": "proposal-1",
            "user_id": "user-1",
            "exchange": "COINONE",
            "asset_type": "CRYPTO",
            "ticker": "XRP",
            "symbol": "XRP",
            "broker_env": "MOCK",
            "side": "BUY",
            "price": 800,
            "volume": 10,
            "ord_type": "LIMIT",
            "status": "APPROVED",
            "client_order_id": "client-1",
            "external_order_id": "order-1",
            "raw_order_payload": {"secret": "제외 대상"},
        },
    )

    assert recovered is True
    assert calls[0]["params"] == {
        "id": "eq.proposal-1",
        "user_id": "eq.user-1",
    }
    assert calls[0]["extra_headers"] == {"Prefer": "return=representation"}
    assert calls[0]["json_data"]["external_order_id"] == "order-1"
    assert "raw_order_payload" not in calls[0]["json_data"]


@pytest.mark.parametrize(
    ("broker_status", "expected_status", "expected_http_status"),
    [
        ("FAILED", "FAILED", 409),
        ("REJECTED", "FAILED", 409),
        ("EXPIRED_IN_MATCH", "FAILED", 409),
        ("CANCELED", "CANCELED", 409),
        ("FILLED", "EXECUTED", 200),
        ("OPEN", "APPROVED", 200),
    ],
)
def test_broker_response_status_is_persisted_without_false_execution(
    monkeypatch,
    broker_status,
    expected_status,
    expected_http_status,
):
    order_client = FakeOrderClient(status=broker_status)
    inserted_payloads = []
    monkeypatch.setattr(trade, "get_user_id_from_header", lambda auth_header: ("user-1", "token"))
    monkeypatch.setattr(trade, "_load_user_exchange_record", lambda *args: ({}, "access", "secret"))
    monkeypatch.setattr(trade, "_build_precheck_payload", lambda **kwargs: _safe_precheck())
    monkeypatch.setattr(trade, "_build_exchange_client", lambda *args: order_client)
    monkeypatch.setattr(
        trade,
        "_create_or_load_manual_order_proposal",
        lambda *args, **kwargs: ({"id": MANUAL_ORDER_KEY, "status": "PENDING"}, True),
    )
    monkeypatch.setattr(
        trade,
        "_claim_trade_proposal_for_execution",
        lambda *args: {"id": MANUAL_ORDER_KEY, "status": "APPROVED"},
    )
    monkeypatch.setattr(
        trade,
        "_patch_trade_proposal_returning",
        lambda auth_header, user_id, proposal_id, payload: inserted_payloads.append(payload)
        or {"id": proposal_id},
    )

    response = app.test_client().post(
        "/api/trade/order",
        headers={"Authorization": "Bearer test"},
        json={
            "idempotency_key": MANUAL_ORDER_KEY,
            "exchange": "COINONE",
            "symbol": "XRP",
            "action": "BUY",
            "order_type": "LIMIT",
            "price": 800,
            "quantity": 10,
            "broker_env": "MOCK",
        },
    )

    assert response.status_code == expected_http_status
    assert response.get_json()["success"] is (expected_http_status == 200)
    assert inserted_payloads[-1]["status"] == expected_status
    if expected_http_status == 409:
        assert "detail" not in response.get_json()
        assert response.get_json()["error"]["code"] == "ORDER_NOT_ACCEPTED"
    else:
        assert "detail" not in response.get_json()


def test_toss_us_precheck_converts_order_amount_to_krw(monkeypatch):
    order_client = TossClient()
    monkeypatch.setattr(trade, "_build_exchange_client", lambda *args: order_client)
    monkeypatch.setattr(trade, "is_us_market_open", lambda client: True)

    precheck = trade._build_precheck_payload(
        exchange="TOSS",
        symbol="AAPL",
        action="BUY",
        order_type="LIMIT",
        quantity=1,
        price=70,
        broker_env="REAL",
        record={},
        access_key="access",
        secret_key="secret",
    )

    assert precheck["currency"] == "USD"
    assert precheck["estimated_amount_krw"] == 105000
    assert precheck["exceeds_real_order_limit"] is True


def test_toss_us_real_order_limit_blocks_before_exchange_order(monkeypatch):
    order_client = TossClient()
    monkeypatch.setattr(trade, "get_user_id_from_header", lambda auth_header: ("user-1", "token"))
    monkeypatch.setattr(trade, "_load_user_exchange_record", lambda *args: ({}, "access", "secret"))
    monkeypatch.setattr(trade, "_build_exchange_client", lambda *args: order_client)
    monkeypatch.setattr(trade, "is_us_market_open", lambda client: True)
    monkeypatch.setattr(trade, "_insert_trade_proposal_with_schema_fallback", lambda *args: None)

    response = app.test_client().post(
        "/api/trade/order",
        headers={"Authorization": "Bearer test"},
        json={
            "exchange": "TOSS",
            "symbol": "AAPL",
            "action": "BUY",
            "order_type": "LIMIT",
            "price": 70,
            "quantity": 1,
            "broker_env": "REAL",
        },
    )

    assert response.status_code == 400
    assert "100,000원" in response.get_json()["message"]
    assert order_client.place_order_calls == 0
