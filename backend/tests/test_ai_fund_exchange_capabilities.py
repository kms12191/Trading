from backend.services.binance_client import BinanceClient
from backend.services.coinone_client import CoinoneClient
from backend.services.toss_client import TossClient


def test_coinone_capability_declares_limit_only_spot_orders():
    capability = CoinoneClient("access", "secret").get_capabilities()

    assert capability.supports_spot is True
    assert capability.supports_market_order is False
    assert capability.supports_order_lookup is True
    assert capability.supports_cancel is True


def test_binance_capability_declares_market_order_support():
    capability = BinanceClient("api", "secret").get_capabilities()

    assert capability.supports_spot is True
    assert capability.supports_market_order is True
    assert capability.supports_order_lookup is True
    assert capability.supports_cancel is True


def test_toss_capability_declares_order_lookup_and_cancel_support():
    capability = TossClient("client", "secret", account_seq="account", env="MOCK").get_capabilities()

    assert capability.supports_spot is True
    assert capability.supports_order_lookup is True
    assert capability.supports_cancel is True
