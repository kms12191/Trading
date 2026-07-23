import json
from pathlib import Path
from backend.services.coinone_client import CoinoneClient
from backend.services.symbol_metadata import COIN_DISPLAY_NAMES

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def test_coinone_get_krw_markets_returns_list():
    markets = CoinoneClient.get_krw_markets()
    assert isinstance(markets, list)
    if len(markets) > 0:
        first = markets[0]
        assert "target_currency" in first
        assert "quote_currency" in first


def test_active_universe_crypto_symbols_count():
    active_path = PROJECT_ROOT / "ml" / "configs" / "active_universe.json"
    assert active_path.exists()
    
    with open(active_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    crypto_symbols = data.get("crypto", [])
    assert isinstance(crypto_symbols, list)
    assert len(crypto_symbols) >= 200, f"Expected >= 200 crypto symbols, got {len(crypto_symbols)}"


def test_coin_display_names_mapping():
    assert "BTC" in COIN_DISPLAY_NAMES
    assert "SUI" in COIN_DISPLAY_NAMES
    assert "WLD" in COIN_DISPLAY_NAMES
    assert COIN_DISPLAY_NAMES["SUI"] == "수이"
