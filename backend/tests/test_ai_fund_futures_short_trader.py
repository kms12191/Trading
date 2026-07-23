from contextlib import contextmanager

from backend.services.ai_fund_futures_short_trader import AiFundFuturesShortTrader


@contextmanager
def acquired_lock(*_args, **_kwargs):
    yield True


def test_open_short_in_paper_records_sell_order_and_short_position(monkeypatch):
    writes = []
    monkeypatch.setattr(
        "backend.services.ai_fund_futures_short_trader.distributed_lock",
        acquired_lock,
    )
    monkeypatch.setattr(
        "backend.services.ai_fund_futures_short_trader.safe_query_supabase_as_service_role",
        lambda endpoint, method="GET", json_data=None, **_kwargs: writes.append((endpoint, method, json_data)) or [],
    )
    client = type("Client", (), {
        "get_position_mode": lambda *_args: {"mode": "ONE_WAY"},
        "get_max_leverage": lambda *_args: 20,
        "get_futures_symbol_filters": lambda *_args: {"min_notional": 5.0},
    })()

    result = AiFundFuturesShortTrader("user-1").open_short(
        {
            "id": "config-1",
            "is_active": True,
            "operation_mode": "PAPER",
            "allocated_capital": 100.0,
            "max_position_size": 20.0,
            "min_signal_confidence": 0.70,
            "futures_leverage": 2,
            "futures_margin_type": "ISOLATED",
        },
        client,
        {"symbol": "BTCUSDT", "confidence_score": 0.76, "signal_id": "short-signal-1"},
        100.0,
    )

    assert result["status"] == "FILLED"
    assert result["paper"] is True
    order_write = next(payload for endpoint, method, payload in writes if endpoint == "ai_fund_orders" and method == "POST")
    assert order_write["side"] == "SELL"
    assert order_write["position_direction"] == "SHORT"
    position_write = next(payload for endpoint, method, payload in writes if endpoint == "ai_fund_positions" and method == "POST")
    assert position_write["position_direction"] == "SHORT"
    assert position_write["quantity"] == 0.2


def test_open_short_blocks_live_mode_without_both_live_approvals(monkeypatch):
    monkeypatch.setattr(
        "backend.services.ai_fund_futures_short_trader.distributed_lock",
        acquired_lock,
    )
    trader = AiFundFuturesShortTrader("user-1")

    result = trader.open_short(
        {"is_active": True, "operation_mode": "LIVE", "min_signal_confidence": 0.70},
        object(),
        {"symbol": "BTCUSDT", "confidence_score": 0.76},
        100.0,
    )

    assert result is None


def test_open_short_submits_live_order_with_exchange_client_order_id(monkeypatch):
    writes = []
    submitted = {}
    monkeypatch.setattr(
        "backend.services.ai_fund_futures_short_trader.distributed_lock",
        acquired_lock,
    )
    monkeypatch.setenv("AI_FUND_FUTURES_LIVE_ENABLED", "true")
    monkeypatch.setattr(
        "backend.services.ai_fund_futures_short_trader.safe_query_supabase_as_service_role",
        lambda endpoint, method="GET", json_data=None, **_kwargs: writes.append((endpoint, method, json_data)) or [],
    )

    def place_order(_self, **kwargs):
        submitted.update(kwargs)
        return {"order_id": "exchange-1", "status": "NEW", "raw": {}}

    client = type("Client", (), {
        "get_position_mode": lambda *_args: {"mode": "ONE_WAY"},
        "get_max_leverage": lambda *_args: 20,
        "get_futures_symbol_filters": lambda *_args: {"min_notional": 5.0},
        "place_order": place_order,
    })()

    result = AiFundFuturesShortTrader("user-1").open_short(
        {
            "id": "config-1",
            "is_active": True,
            "operation_mode": "LIVE",
            "futures_live_enabled": True,
            "allocated_capital": 100.0,
            "max_position_size": 20.0,
            "min_signal_confidence": 0.70,
            "futures_leverage": 2,
            "futures_margin_type": "ISOLATED",
            "stop_loss_pct": -2.0,
        },
        client,
        {"symbol": "BTCUSDT", "confidence_score": 0.76, "signal_id": "short-signal-1"},
        100.0,
    )

    assert result["status"] == "SUBMITTED"
    assert submitted["side"] == "SELL"
    assert submitted["client_order_id"].startswith("short-")
    assert submitted["margin_type"] == "ISOLATED"
    submitted_write = next(payload for endpoint, method, payload in writes if endpoint.startswith("ai_fund_orders?id=eq.") and method == "PATCH" and payload["status"] == "SUBMITTED")
    assert submitted_write["raw_response"]["confidence_score"] == 0.76
    assert submitted_write["raw_response"]["intent"] == "OPEN_SHORT"


def test_close_short_in_paper_uses_buy_and_reduces_position(monkeypatch):
    writes = []
    position = {
        "id": "position-1",
        "symbol": "BTCUSDT",
        "quantity": 0.2,
        "average_entry_price": 100.0,
    }
    monkeypatch.setattr(
        "backend.services.ai_fund_futures_short_trader.distributed_lock",
        acquired_lock,
    )

    def query(endpoint, method="GET", json_data=None, **_kwargs):
        writes.append((endpoint, method, json_data))
        if endpoint == "ai_fund_positions" and method == "GET":
            return [position]
        return []

    monkeypatch.setattr(
        "backend.services.ai_fund_futures_short_trader.safe_query_supabase_as_service_role",
        query,
    )
    client = type("Client", (), {
        "get_position_mode": lambda *_args: {"mode": "ONE_WAY"},
        "get_max_leverage": lambda *_args: 20,
    })()

    result = AiFundFuturesShortTrader("user-1").close_short(
        {"id": "config-1", "is_active": True, "operation_mode": "PAPER", "futures_leverage": 2},
        client,
        "BTCUSDT",
        0.2,
        102.0,
        "STOP_LOSS",
    )

    assert result["status"] == "FILLED"
    order_write = next(payload for endpoint, method, payload in writes if endpoint == "ai_fund_orders" and method == "POST")
    assert order_write["side"] == "BUY"
    assert order_write["order_type"] == "MARKET"
    reduction = next(payload for endpoint, method, payload in writes if endpoint == "ai_fund_positions?id=eq.position-1" and method == "PATCH")
    assert reduction["quantity"] == 0.0
