from datetime import datetime, timedelta, timezone

import pytest

from backend.services.ai_fund_trade_intent import TradeIntent, TradeIntentValidationError


def test_trade_intent_normalizes_valid_webhook_payload():
    intent = TradeIntent.from_payload({
        "source": "webhook",
        "source_id": "partner-a",
        "idempotency_key": "partner-a:btc:001",
        "symbol": "btc",
        "side": "buy",
        "confidence": 0.85,
        "expires_at": (datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat(),
    })

    assert intent.source == "WEBHOOK"
    assert intent.symbol == "BTC"
    assert intent.side == "BUY"


def test_trade_intent_rejects_expired_or_unsupported_symbol():
    with pytest.raises(TradeIntentValidationError, match="유효 기간"):
        TradeIntent.from_payload({
            "source": "WEBHOOK",
            "source_id": "partner-a",
            "idempotency_key": "expired-1",
            "symbol": "BTC",
            "side": "BUY",
            "expires_at": (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat(),
        })

    with pytest.raises(TradeIntentValidationError, match="허용 심볼"):
        TradeIntent.from_payload({
            "source": "WEBHOOK",
            "source_id": "partner-a",
            "idempotency_key": "symbol-1",
            "symbol": "DOGE",
            "side": "BUY",
            "allowed_symbols": ["BTC", "ETH"],
        })
