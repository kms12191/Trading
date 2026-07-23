from unittest.mock import MagicMock

from backend.services.ai_fund_market_data import get_current_price


def test_current_price_uses_existing_exchange_client_for_supported_exchanges():
    client = MagicMock()
    client.get_price.return_value = {"current_price": "123.45"}

    price = get_current_price("binance", "BTC", client)

    assert price == 123.45
    client.get_price.assert_called_once_with("BTC")


def test_current_price_returns_none_for_invalid_or_unavailable_response():
    client = MagicMock()
    client.get_price.return_value = {"current_price": 0}

    assert get_current_price("toss", "AAPL", client) is None
    assert get_current_price("unknown", "BTC", client) is None
