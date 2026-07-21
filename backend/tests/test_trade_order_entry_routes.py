import uuid

import pytest
from flask import Flask

from backend.routes import trade


AUTH = {"Authorization": "Bearer test-token"}


class FakeCrypto:
    def decrypt(self, value):
        return f"decrypted-{value}"


class FakeClient:
    def get_balance(self):
        return {
            "available_cash": 250000.0,
            "currency": "KRW",
            "total_evaluation": 400000.0,
            "holdings": [
                {
                    "symbol": "005930",
                    "name": "삼성전자",
                    "qty": 3.0,
                    "available_qty": 2.0,
                    "avg_price": 70000.0,
                    "current_price": 75000.0,
                    "profit_rate": 7.14,
                    "currency": "KRW",
                }
            ],
        }

    def get_price(self, symbol):
        return {"current_price": 75000.0, "change_rate": 1.25, "symbol": symbol}


@pytest.fixture
def client():
    app = Flask(__name__)
    app.config.update(TESTING=True, SECRET_KEY="flask-secret")
    app.crypto = FakeCrypto()
    app.register_blueprint(trade.trade_bp)
    return app.test_client()


@pytest.fixture(autouse=True)
def authenticated_user(monkeypatch):
    monkeypatch.setattr(trade, "get_user_id_from_header", lambda _header: ("user-1", "test-token"))


def test_order_entry_accounts_requires_authentication(client):
    response = client.get("/api/trade/order-entry/accounts")

    assert response.status_code == 401


def test_order_entry_accounts_returns_safe_connected_accounts(client, monkeypatch):
    records = [{
        "id": "key-1",
        "user_id": "user-1",
        "exchange": "TOSS",
        "broker_env": "REAL",
        "encrypted_access_key": "access",
        "encrypted_secret_key": "secret",
        "toss_account_seq": "account-seq",
        "api_permissions": {"read_only": False},
    }]
    monkeypatch.setattr(trade, "_query_user_exchange_records", lambda *_args, **_kwargs: records)
    monkeypatch.setattr(trade, "_build_exchange_client", lambda *_args, **_kwargs: FakeClient())

    response = client.get("/api/trade/order-entry/accounts", headers=AUTH)

    assert response.status_code == 200
    payload = response.get_json()["data"]
    assert payload["accounts"] == [{
        "id": "TOSS:REAL:key-1",
        "exchange": "TOSS",
        "broker": "Toss증권",
        "asset_type": "STOCK",
        "broker_env": "REAL",
        "currency": "KRW",
        "available_cash": 250000.0,
        "total_evaluation": 400000.0,
        "api_permissions": {"read_only": False},
        "trade_enabled": True,
        "real_trading_locked": False,
        "status": "READY",
        "status_message": "주문 가능한 계좌입니다.",
    }]
    assert "encrypted_access_key" not in response.get_data(as_text=True)
    assert "decrypted-access" not in response.get_data(as_text=True)


def test_order_entry_holdings_returns_only_server_balance_rows(client, monkeypatch):
    monkeypatch.setattr(
        trade,
        "_load_user_exchange_record",
        lambda *_args, **_kwargs: ({"id": "key-1"}, "access", "secret"),
    )
    monkeypatch.setattr(trade, "_build_exchange_client", lambda *_args, **_kwargs: FakeClient())

    response = client.get(
        "/api/trade/order-entry/holdings?exchange=TOSS&broker_env=REAL&asset_type=STOCK",
        headers=AUTH,
    )

    assert response.status_code == 200
    holding = response.get_json()["data"]["holdings"][0]
    assert holding["symbol"] == "005930"
    assert holding["available_qty"] == 2.0
    assert holding["position_side"] is None


def test_order_entry_context_requires_selected_symbol(client):
    response = client.get(
        "/api/trade/order-entry/context?exchange=TOSS&broker_env=REAL",
        headers=AUTH,
    )

    assert response.status_code == 400
    assert "종목" in response.get_json()["message"]


def test_order_entry_symbols_filters_crypto_by_exchange_master(client, monkeypatch):
    monkeypatch.setattr(
        trade,
        "_load_order_entry_client",
        lambda *_args, **_kwargs: ({"id": "key-1"}, FakeClient()),
    )
    def fake_search_crypto_assets(query, limit=10):
        if query != "ALICE":
            return []
        return [{
            "symbol": "ALICE",
            "display_name": "Alice",
            "exchanges": ["BINANCE"],
            "coinone_tradable": False,
            "binance_tradable": True,
            "admin_trading_blocked": False,
        }]

    monkeypatch.setattr("backend.services.crypto_asset_service.search_crypto_assets", fake_search_crypto_assets)

    coinone_response = client.get(
        "/api/trade/order-entry/symbols?exchange=COINONE&broker_env=REAL&query=ALICE",
        headers=AUTH,
    )
    binance_response = client.get(
        "/api/trade/order-entry/symbols?exchange=BINANCE&broker_env=REAL&query=ALICE",
        headers=AUTH,
    )

    assert coinone_response.status_code == 200
    assert coinone_response.get_json()["data"]["symbols"] == []
    assert binance_response.status_code == 200
    assert binance_response.get_json()["data"]["symbols"][0]["symbol"] == "ALICEUSDT"


def test_order_entry_context_returns_live_price_and_service_leverage_limit(client, monkeypatch):
    monkeypatch.setattr(
        trade,
        "_load_user_exchange_record",
        lambda *_args, **_kwargs: ({"id": "key-1"}, "access", "secret"),
    )
    monkeypatch.setattr(trade, "_build_exchange_client", lambda *_args, **_kwargs: FakeClient())
    monkeypatch.setattr(trade, "_validate_order_entry_symbol", lambda *_args, **_kwargs: None)

    response = client.get(
        "/api/trade/order-entry/context?exchange=TOSS&broker_env=REAL&asset_type=STOCK&symbol=005930",
        headers=AUTH,
    )

    assert response.status_code == 200
    context = response.get_json()["data"]
    assert context["current_price"] == 75000.0
    assert context["currency"] == "KRW"
    assert context["service_max_leverage"] == 1
    assert context["checked_at"].endswith("Z")


def test_futures_balance_snapshot_uses_selected_hedge_position_side():
    class FakeFuturesClient:
        def get_balance(self):
            return {
                "available_cash": 1000.0,
                "holdings": [
                    {
                        "symbol": "BTCUSDT",
                        "qty": 0.4,
                        "current_price": 50000.0,
                        "position_side": "LONG",
                    },
                    {
                        "symbol": "BTCUSDT",
                        "qty": -0.2,
                        "current_price": 50000.0,
                        "position_side": "SHORT",
                    },
                ],
            }

    snapshot = trade._extract_balance_snapshot(
        FakeFuturesClient(),
        "BTCUSDT",
        "BINANCE_UM_FUTURES",
        position_side="SHORT",
    )

    assert snapshot["holding_qty"] == -0.2
    assert snapshot["holding_value"] == -10000.0


def test_precheck_returns_signed_token_without_creating_proposal(client, monkeypatch):
    order = {
        "account_id": "TOSS:REAL:key-1",
        "exchange": "TOSS",
        "asset_type": "STOCK",
        "broker_env": "REAL",
        "intent": "BUY",
        "symbol": "005930",
        "symbol_selected": True,
        "quantity": 1,
        "order_type": "LIMIT",
        "price": 75000,
        "idempotency_key": str(uuid.UUID("22222222-2222-4222-8222-222222222222")),
    }
    monkeypatch.setattr(
        trade,
        "_load_user_exchange_record",
        lambda *_args, **_kwargs: ({"id": "key-1"}, "access", "secret"),
    )
    monkeypatch.setattr(trade, "_validate_order_entry_symbol", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        trade,
        "_build_precheck_payload",
        lambda **_kwargs: {
            "reference_price": 75000.0,
            "estimated_amount_krw": 75000.0,
            "available_cash": 250000.0,
            "holding_qty": 0.0,
            "warnings": [],
            "balance_check_failed": False,
            "is_market_closed": False,
            "insufficient_cash": False,
            "insufficient_holding": False,
            "insufficient_permission": False,
            "futures_real_blocked": False,
            "exceeds_real_order_limit": False,
        },
    )
    writes = []
    monkeypatch.setattr(trade, "query_supabase", lambda *_args, **kwargs: writes.append(kwargs) or [])

    response = client.post("/api/trade/precheck", json=order, headers=AUTH)

    assert response.status_code == 200
    data = response.get_json()["data"]
    assert data["precheck_token"]
    assert len(data["order_hash"]) == 64
    assert data["can_create_proposal"] is True
    assert writes == []


def test_precheck_rejects_account_id_for_a_different_connected_account(client, monkeypatch):
    order = {
        "account_id": "TOSS:REAL:key-2",
        "exchange": "TOSS",
        "asset_type": "STOCK",
        "broker_env": "REAL",
        "intent": "BUY",
        "symbol": "005930",
        "symbol_selected": True,
        "quantity": 1,
        "order_type": "LIMIT",
        "price": 75000,
        "idempotency_key": str(uuid.UUID("66666666-6666-4666-8666-666666666666")),
    }
    monkeypatch.setattr(
        trade,
        "_load_user_exchange_record",
        lambda *_args, **_kwargs: ({"id": "key-1"}, "access", "secret"),
    )
    monkeypatch.setattr(trade, "_validate_order_entry_symbol", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        trade,
        "_build_precheck_payload",
        lambda **_kwargs: {
            "reference_price": 75000.0,
            "estimated_amount_krw": 75000.0,
            "available_cash": 250000.0,
            "holding_qty": 0.0,
            "warnings": [],
            "balance_check_failed": False,
            "is_market_closed": False,
            "insufficient_cash": False,
            "insufficient_holding": False,
            "insufficient_permission": False,
            "futures_real_blocked": False,
            "exceeds_real_order_limit": False,
        },
    )

    response = client.post("/api/trade/precheck", json=order, headers=AUTH)

    assert response.status_code == 400
    assert "계좌" in response.get_json()["message"]


def test_blocked_precheck_does_not_issue_proposal_token(client, monkeypatch):
    order = {
        "account_id": "TOSS:REAL:key-1",
        "exchange": "TOSS",
        "asset_type": "STOCK",
        "broker_env": "REAL",
        "intent": "BUY",
        "symbol": "005930",
        "symbol_selected": True,
        "quantity": 2,
        "order_type": "LIMIT",
        "price": 75000,
        "idempotency_key": str(uuid.UUID("33333333-3333-4333-8333-333333333333")),
    }
    monkeypatch.setattr(
        trade,
        "_load_user_exchange_record",
        lambda *_args, **_kwargs: ({"id": "key-1"}, "access", "secret"),
    )
    monkeypatch.setattr(trade, "_validate_order_entry_symbol", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        trade,
        "_build_precheck_payload",
        lambda **_kwargs: {
            "reference_price": 75000.0,
            "estimated_amount_krw": 150000.0,
            "available_cash": 250000.0,
            "holding_qty": 0.0,
            "warnings": ["실거래 1회 주문 한도 100,000원을 초과했습니다."],
            "balance_check_failed": False,
            "is_market_closed": False,
            "insufficient_cash": False,
            "insufficient_holding": False,
            "insufficient_permission": False,
            "futures_real_blocked": False,
            "exceeds_real_order_limit": True,
        },
    )

    response = client.post("/api/trade/precheck", json=order, headers=AUTH)

    assert response.status_code == 200
    data = response.get_json()["data"]
    assert data["precheck_token"] is None
    assert data["can_create_proposal"] is False
    assert data["blockers"] == ["실거래 1회 주문 한도 100,000원을 초과했습니다."]


def test_crypto_precheck_blocks_admin_blocked_asset_before_exchange_client(client, monkeypatch):
    order = {
        "account_id": "COINONE:REAL:key-1",
        "exchange": "COINONE",
        "asset_type": "CRYPTO_SPOT",
        "broker_env": "REAL",
        "intent": "BUY",
        "symbol": "H",
        "symbol_selected": True,
        "quantity": 2,
        "order_type": "LIMIT",
        "price": 100,
        "idempotency_key": str(uuid.UUID("55555555-5555-4555-8555-555555555555")),
    }
    client_loaded = {"value": False}

    def fail_policy(exchange, symbol):
        raise ValueError("휴머니티(H) 종목은 관리자에 의해 거래가 차단되었습니다.")

    def fake_load_client(*_args, **_kwargs):
        client_loaded["value"] = True
        return {"id": "key-1"}, "access", "secret"

    monkeypatch.setattr(trade, "_validate_crypto_asset_policy", fail_policy)
    monkeypatch.setattr(trade, "_load_user_exchange_record", fake_load_client)

    response = client.post("/api/trade/precheck", json=order, headers=AUTH)

    assert response.status_code == 400
    assert "관리자에 의해 거래가 차단" in response.get_json()["message"]
    assert client_loaded["value"] is False


def test_crypto_direct_order_blocks_admin_blocked_asset_before_exchange_client(client, monkeypatch):
    order = {
        "exchange": "COINONE",
        "symbol": "H",
        "action": "BUY",
        "order_type": "LIMIT",
        "quantity": 2,
        "price": 100,
        "broker_env": "REAL",
    }
    client_loaded = {"value": False}

    def fail_policy(exchange, symbol):
        raise ValueError("휴머니티(H) 종목은 관리자에 의해 거래가 차단되었습니다.")

    def fake_load_client(*_args, **_kwargs):
        client_loaded["value"] = True
        return {"id": "key-1"}, "access", "secret"

    monkeypatch.setattr(trade, "_validate_crypto_asset_policy", fail_policy)
    monkeypatch.setattr(trade, "_load_user_exchange_record", fake_load_client)

    response = client.post("/api/trade/order", json=order, headers=AUTH)

    assert response.status_code == 400
    assert "관리자에 의해 거래가 차단" in response.get_json()["message"]
    assert client_loaded["value"] is False


def test_approval_restores_server_signed_futures_options(monkeypatch):
    proposal = {
        "id": "proposal-1",
        "status": "PENDING",
        "exchange": "BINANCE_UM_FUTURES",
        "symbol": "BTCUSDT",
        "side": "BUY",
        "ord_type": "LIMIT",
        "price": 50000,
        "volume": 0.001,
        "broker_env": "MOCK",
        "raw_order_payload": {
            "intent": "CLOSE_POSITION",
            "futures_options": {
                "side": "BUY",
                "position_side": "SHORT",
                "reduce_only": False,
                "leverage": 3,
                "margin_type": "ISOLATED",
            },
        },
    }
    monkeypatch.setattr(trade, "_load_user_trade_proposal", lambda *_args, **_kwargs: proposal)

    resolved, loaded = trade._resolve_proposal_order_data(
        "Bearer test",
        "user-1",
        {"proposal_id": "proposal-1", "leverage": 100, "position_side": "LONG"},
    )

    assert loaded == proposal
    assert resolved["action"] == "BUY"
    assert resolved["intent"] == "CLOSE_POSITION"
    assert resolved["position_side"] == "SHORT"
    assert resolved["reduce_only"] is False
    assert resolved["leverage"] == 3
    assert resolved["margin_type"] == "ISOLATED"
