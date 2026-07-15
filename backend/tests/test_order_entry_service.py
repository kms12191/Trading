import uuid

import pytest

from backend.services.order_entry_service import (
    issue_precheck_token,
    normalize_order_request,
    order_request_hash,
    resolve_futures_execution,
    resolve_service_leverage_limit,
    verify_precheck_token,
)


BASE_ORDER = {
    "account_id": "BINANCE_UM_FUTURES:MOCK",
    "exchange": "BINANCE_UM_FUTURES",
    "asset_type": "CRYPTO_FUTURES",
    "broker_env": "MOCK",
    "intent": "OPEN_LONG",
    "symbol": "BTCUSDT",
    "symbol_selected": True,
    "quantity": 0.001,
    "order_type": "LIMIT",
    "price": 50000,
    "leverage": 2,
    "margin_type": "ISOLATED",
    "idempotency_key": str(uuid.UUID("11111111-1111-4111-8111-111111111111")),
}

BASE_PRECHECK = {
    "reference_price": 50000.0,
    "estimated_amount_krw": 75000.0,
    "available_cash": 1000.0,
    "warnings": [],
}


@pytest.mark.parametrize("missing_field", [
    "account_id",
    "exchange",
    "asset_type",
    "broker_env",
    "intent",
    "symbol",
    "quantity",
    "order_type",
    "idempotency_key",
])
def test_normalize_order_request_rejects_missing_fields_without_defaults(missing_field):
    values = {key: value for key, value in BASE_ORDER.items() if key != missing_field}

    with pytest.raises(ValueError, match="누락"):
        normalize_order_request(values)


def test_normalize_order_request_requires_limit_price():
    with pytest.raises(ValueError, match="지정가"):
        normalize_order_request({**BASE_ORDER, "price": None})


def test_normalize_order_request_rejects_unselected_symbol():
    with pytest.raises(ValueError, match="검색 결과"):
        normalize_order_request({**BASE_ORDER, "symbol_selected": False})


def test_normalize_order_request_keeps_explicit_futures_defaults_only():
    order = normalize_order_request({
        **BASE_ORDER,
        "leverage": None,
        "margin_type": None,
    })

    assert order["leverage"] == 1
    assert order["margin_type"] == "ISOLATED"
    assert order["side"] == "BUY"


@pytest.mark.parametrize(
    ("intent", "position_mode", "position_side", "expected"),
    [
        ("OPEN_LONG", "ONE_WAY", None, {"side": "BUY", "position_side": "BOTH", "reduce_only": False}),
        ("OPEN_SHORT", "ONE_WAY", None, {"side": "SELL", "position_side": "BOTH", "reduce_only": False}),
        ("CLOSE_POSITION", "ONE_WAY", "LONG", {"side": "SELL", "position_side": "BOTH", "reduce_only": True}),
        ("CLOSE_POSITION", "ONE_WAY", "SHORT", {"side": "BUY", "position_side": "BOTH", "reduce_only": True}),
        ("OPEN_LONG", "HEDGE", None, {"side": "BUY", "position_side": "LONG", "reduce_only": False}),
        ("OPEN_SHORT", "HEDGE", None, {"side": "SELL", "position_side": "SHORT", "reduce_only": False}),
        ("CLOSE_POSITION", "HEDGE", "LONG", {"side": "SELL", "position_side": "LONG", "reduce_only": False}),
        ("CLOSE_POSITION", "HEDGE", "SHORT", {"side": "BUY", "position_side": "SHORT", "reduce_only": False}),
    ],
)
def test_resolve_futures_execution_matrix(intent, position_mode, position_side, expected):
    assert resolve_futures_execution(intent, position_mode, position_side) == expected


def test_resolve_futures_execution_requires_position_side_for_close():
    with pytest.raises(ValueError, match="청산할 포지션"):
        resolve_futures_execution("CLOSE_POSITION", "HEDGE", None)


@pytest.mark.parametrize(
    ("exchange_limit", "configured_limit", "expected"),
    [
        (125, None, 10),
        (5, None, 5),
        (125, "7", 7),
        (5, "7", 5),
        (125, "50", 10),
    ],
)
def test_resolve_service_leverage_limit_uses_lowest_limit(exchange_limit, configured_limit, expected):
    assert resolve_service_leverage_limit(exchange_limit, configured_limit) == expected


def test_precheck_token_round_trip_preserves_signed_snapshot():
    order = normalize_order_request(BASE_ORDER)
    token = issue_precheck_token("user-1", order, BASE_PRECHECK, "secret", now=100)

    verified = verify_precheck_token(token, "user-1", order, "secret", now=120)

    assert verified["order_hash"] == order_request_hash(order)
    assert verified["precheck"] == BASE_PRECHECK


def test_precheck_token_rejects_changed_order():
    order = normalize_order_request(BASE_ORDER)
    token = issue_precheck_token("user-1", order, BASE_PRECHECK, "secret", now=100)

    with pytest.raises(ValueError, match="일치"):
        verify_precheck_token(token, "user-1", {**order, "quantity": 0.002}, "secret", now=120)


def test_precheck_token_rejects_tampering():
    order = normalize_order_request(BASE_ORDER)
    token = issue_precheck_token("user-1", order, BASE_PRECHECK, "secret", now=100)
    tampered = f"{token[:-1]}{'A' if token[-1] != 'A' else 'B'}"

    with pytest.raises(ValueError, match="서명"):
        verify_precheck_token(tampered, "user-1", order, "secret", now=120)


def test_precheck_token_rejects_expiration():
    order = normalize_order_request(BASE_ORDER)
    token = issue_precheck_token("user-1", order, BASE_PRECHECK, "secret", now=100, ttl_seconds=300)

    with pytest.raises(ValueError, match="만료"):
        verify_precheck_token(token, "user-1", order, "secret", now=401)
