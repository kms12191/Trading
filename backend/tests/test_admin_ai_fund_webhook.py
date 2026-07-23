import hashlib
import hmac
import json

import pytest

from backend.app import app
import backend.routes.admin_ai_fund as admin_ai_fund_route


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("AI_FUND_WEBHOOK_SECRET", "webhook-test-secret")
    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client


def _signature(payload):
    raw = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    return hmac.new(b"webhook-test-secret", raw, hashlib.sha256).hexdigest(), raw


def test_webhook_rejects_invalid_signature(client):
    response = client.post(
        "/api/admin/ai-fund/webhooks/intents",
        json={"source": "WEBHOOK"},
        headers={"X-AI-Fund-Signature": "invalid"},
    )

    assert response.status_code == 401


def test_webhook_stores_verified_idempotent_intent(client, monkeypatch):
    writes = []

    def fake_query(endpoint, method="GET", json_data=None, **_kwargs):
        writes.append((endpoint, method, json_data))
        return [{"id": "intent-1"}]

    monkeypatch.setattr(admin_ai_fund_route, "safe_query_supabase_as_service_role", fake_query)
    payload = {
        "user_id": "00000000-0000-0000-0000-000000000001",
        "exchange_type": "coinone",
        "source": "WEBHOOK",
        "source_id": "partner-a",
        "idempotency_key": "partner-a:btc:1",
        "symbol": "BTC",
        "side": "BUY",
        "confidence": 0.9,
        "allowed_symbols": ["BTC"],
        "strategy_id": "grid",
    }
    signature, raw = _signature(payload)

    response = client.post(
        "/api/admin/ai-fund/webhooks/intents",
        data=raw,
        content_type="application/json",
        headers={"X-AI-Fund-Signature": signature},
    )

    assert response.status_code == 202
    assert writes[0][0] == "ai_fund_trade_intents"
    assert writes[0][2]["idempotency_key"] == "partner-a:btc:1"
    assert writes[0][2]["status"] == "PENDING"
