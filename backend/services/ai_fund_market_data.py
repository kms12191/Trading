"""AI 위탁운용의 거래소별 현재가 조회를 공통 계약으로 제공합니다."""

from __future__ import annotations

from typing import Any


SUPPORTED_EXCHANGES = {"coinone", "binance", "toss"}


def get_current_price(exchange_type: str, symbol: str, exchange_client: Any | None = None) -> float | None:
    """거래소 클라이언트의 표준 get_price 응답에서 양수 현재가를 추출합니다."""
    exchange = str(exchange_type or "").lower()
    if exchange not in SUPPORTED_EXCHANGES or not symbol:
        return None
    client = exchange_client or _coinone_public_client() if exchange == "coinone" else exchange_client
    if client is None:
        return None
    try:
        payload = client.get_price(symbol)
        value = payload.get("current_price") if isinstance(payload, dict) else None
        price = float(value or 0.0)
        return price if price > 0 else None
    except Exception:
        return None


def _coinone_public_client() -> Any | None:
    try:
        from backend.services.coinone_client import CoinoneClient

        client = CoinoneClient.__new__(CoinoneClient)
        client.access_token = ""
        client.secret_key = b""
        client.base_url = "https://api.coinone.co.kr"
        return client
    except Exception:
        return None
