from backend.services.ai_fund_exchange import (
    ExchangeCapability,
    OrderRequest,
    normalize_exchange_order,
)


def test_normalize_exchange_order_preserves_client_order_id_and_partial_fill():
    request = OrderRequest(
        symbol="BTC",
        side="BUY",
        quantity=1.0,
        client_order_id="fund-order-1",
        price=100.0,
    )

    order = normalize_exchange_order(
        exchange_type="coinone",
        payload={
            "order_id": "coinone-1",
            "status": "PARTIALLY_FILLED",
            "executed_qty": 0.2,
            "price": 100.0,
        },
        request=request,
    )

    assert order.exchange_order_id == "coinone-1"
    assert order.client_order_id == "fund-order-1"
    assert order.status == "PARTIALLY_FILLED"
    assert order.filled_qty == 0.2
    assert order.average_fill_price == 100.0


def test_capability_rejects_unsupported_market_order():
    capability = ExchangeCapability(
        supports_spot=True,
        supports_order_lookup=True,
        supports_cancel=True,
        supports_market_order=False,
        min_order_amount=5000.0,
    )

    assert capability.supports_order_type("MARKET") is False
    assert capability.supports_order_type("LIMIT") is True
