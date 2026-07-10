import pytest

from backend.app import app
from backend.services.chatbot.safety_guard import (
    RiskLevel,
    SafetyGuardError,
    assess_tool_risk,
    enforce_tool_safety,
)
from backend.services.chatbot import tool_registry
from backend.services.chatbot.tool_registry import create_trade_proposal, run_chatbot_tool
from backend.routes.trade import _resolve_proposal_order_data


def test_safety_guard_separates_read_write_proposal_and_order_risks():
    assert assess_tool_risk("get_holdings") == RiskLevel.READ
    assert assess_tool_risk("add_watchlist_item") == RiskLevel.WRITE
    assert assess_tool_risk("create_trade_proposal") == RiskLevel.PROPOSAL
    assert assess_tool_risk("place_order") == RiskLevel.ORDER


def test_safety_guard_blocks_order_tool_before_execution():
    with pytest.raises(SafetyGuardError):
        enforce_tool_safety("place_order", {})


def test_create_trade_proposal_only_inserts_pending_record(monkeypatch):
    calls = []

    def fake_query(auth_header, endpoint, method="GET", json_data=None, params=None):
        calls.append({
            "auth_header": auth_header,
            "endpoint": endpoint,
            "method": method,
            "json_data": json_data,
            "params": params,
        })
        return [{"id": "proposal-1", "status": "PENDING"}]

    monkeypatch.setattr(
        "backend.services.chatbot.tool_registry.query_supabase",
        fake_query,
    )
    monkeypatch.setattr(
        "backend.services.chatbot.tool_registry.get_user_id_from_header",
        lambda auth_header: ("user-1", "test"),
    )

    result = create_trade_proposal(
        "Bearer test",
        {
            "exchange": "COINONE",
            "asset_type": "CRYPTO",
            "symbol": "XRP",
            "side": "BUY",
            "order_type": "LIMIT",
            "quantity": 10,
            "price": 800,
            "broker_env": "MOCK",
        },
    )

    assert result["data"]["status"] == "PENDING"
    assert calls[0]["endpoint"] == "trade_proposals"
    assert calls[0]["method"] == "POST"
    assert calls[0]["json_data"]["status"] == "PENDING"


def test_approval_order_uses_server_side_pending_proposal_fields(monkeypatch):
    monkeypatch.setattr(
        "backend.routes.trade._load_user_trade_proposal",
        lambda auth_header, user_id, proposal_id: {
            "id": proposal_id,
            "status": "PENDING",
            "exchange": "COINONE",
            "symbol": "XRP",
            "side": "BUY",
            "ord_type": "LIMIT",
            "price": 800,
            "volume": 10,
            "broker_env": "MOCK",
        },
    )

    resolved, proposal = _resolve_proposal_order_data(
        "Bearer test",
        "user-1",
        {
            "proposal_id": "proposal-1",
            "exchange": "BINANCE",
            "symbol": "BTCUSDT",
            "action": "SELL",
            "price": 1,
            "quantity": 1,
        },
    )

    assert proposal["id"] == "proposal-1"
    assert resolved["exchange"] == "COINONE"
    assert resolved["symbol"] == "XRP"
    assert resolved["action"] == "BUY"
    assert resolved["price"] == 800
    assert resolved["quantity"] == 10


def test_reject_endpoint_changes_only_pending_proposal(monkeypatch):
    monkeypatch.setattr(
        "backend.routes.trade.get_user_id_from_header",
        lambda auth_header: ("user-1", "test"),
    )
    monkeypatch.setattr(
        "backend.routes.trade._load_user_trade_proposal",
        lambda auth_header, user_id, proposal_id: {"id": proposal_id, "status": "PENDING"},
    )
    monkeypatch.setattr(
        "backend.routes.trade._patch_trade_proposal",
        lambda auth_header, proposal_id, payload: {"id": proposal_id, **payload},
    )

    response = app.test_client().post(
        "/api/trade/proposal/reject",
        headers={"Authorization": "Bearer test"},
        json={"proposal_id": "proposal-1"},
    )

    assert response.status_code == 200
    assert response.get_json()["data"]["status"] == "REJECTED"


def test_run_chatbot_tool_creates_pending_proposal_from_limit_order_message(monkeypatch):
    calls = []

    def fake_query(auth_header, endpoint, method="GET", json_data=None, params=None):
        calls.append({
            "auth_header": auth_header,
            "endpoint": endpoint,
            "method": method,
            "json_data": json_data,
            "params": params,
        })
        if endpoint == "trade_proposals":
            return [{"id": "proposal-1", "status": "PENDING"}]
        raise AssertionError(f"unexpected endpoint: {endpoint}")

    monkeypatch.setattr(
        "backend.services.chatbot.tool_registry.query_supabase",
        fake_query,
    )
    monkeypatch.setattr(
        "backend.services.chatbot.tool_registry.get_user_id_from_header",
        lambda auth_header: ("user-1", "test"),
    )
    monkeypatch.setattr(
        "backend.services.chatbot.tool_registry._resolve_symbol",
        lambda auth_header, query: {
            "symbol": "XRP",
            "asset_type": "CRYPTO",
            "market": "KR",
        },
    )

    result = run_chatbot_tool("Bearer test", "XRP 10개 800원에 모의로 사줘")

    assert result["data"]["status"] == "PENDING"
    assert calls[0]["endpoint"] == "trade_proposals"
    assert calls[0]["json_data"]["symbol"] == "XRP"
    assert calls[0]["json_data"]["side"] == "BUY"
    assert calls[0]["json_data"]["volume"] == 10
    assert calls[0]["json_data"]["price"] == 800
    assert calls[0]["json_data"]["broker_env"] == "MOCK"


def test_run_chatbot_tool_calculates_quantity_for_amount_order(monkeypatch):
    calls = []

    def fake_query(auth_header, endpoint, method="GET", json_data=None, params=None):
        calls.append({
            "endpoint": endpoint,
            "method": method,
            "json_data": json_data,
            "params": params,
        })
        if endpoint == "trade_proposals":
            return [{"id": "proposal-amount", "status": "PENDING"}]
        raise AssertionError(f"unexpected endpoint: {endpoint}")

    monkeypatch.setattr(
        "backend.services.chatbot.tool_registry._resolve_symbol",
        lambda auth_header, query: {
            "symbol": "005930",
            "asset_type": "STOCK",
            "market": "KR",
        },
    )
    monkeypatch.setattr(
        "backend.services.chatbot.tool_registry._get_internal",
        lambda path, auth_header, params=None: {
            "success": True,
            "data": {"current_price": 70000},
        },
    )
    monkeypatch.setattr(
        "backend.services.chatbot.tool_registry.query_supabase",
        fake_query,
    )
    monkeypatch.setattr(
        "backend.services.chatbot.tool_registry.get_user_id_from_header",
        lambda auth_header: ("user-1", "test"),
    )

    result = run_chatbot_tool("Bearer test", "삼성전자 10만원어치 사줘")

    assert result["data"]["status"] == "PENDING"
    assert calls[0]["json_data"]["symbol"] == "005930"
    assert calls[0]["json_data"]["volume"] == 1
    assert calls[0]["json_data"]["price"] == 70000
    assert calls[0]["json_data"]["ord_type"] == "LIMIT"


def test_run_chatbot_tool_stores_precheck_payload_on_proposal(monkeypatch):
    calls = []

    def fake_query(auth_header, endpoint, method="GET", json_data=None, params=None):
        calls.append({
            "endpoint": endpoint,
            "method": method,
            "json_data": json_data,
            "params": params,
        })
        if endpoint == "trade_proposals":
            return [{"id": "proposal-precheck", "status": "PENDING"}]
        raise AssertionError(f"unexpected endpoint: {endpoint}")

    def fake_get_internal(path, auth_header, params=None):
        return {"success": True, "data": {"current_price": 70000}}

    def fake_post_internal(path, auth_header, body=None):
        assert path == "/api/trade/precheck"
        assert body["exchange"] == "KIS"
        assert body["symbol"] == "005930"
        assert body["action"] == "BUY"
        return {
            "success": True,
            "data": {
                "estimated_amount_krw": 70000,
                "available_cash": 200000,
                "insufficient_cash": False,
                "insufficient_holding": False,
                "is_market_closed": False,
                "warnings": [],
            },
        }

    monkeypatch.setattr(
        "backend.services.chatbot.tool_registry._resolve_symbol",
        lambda auth_header, query: {
            "symbol": "005930",
            "asset_type": "STOCK",
            "market": "KR",
        },
    )
    monkeypatch.setattr("backend.services.chatbot.tool_registry._get_internal", fake_get_internal)
    monkeypatch.setattr("backend.services.chatbot.tool_registry._post_internal", fake_post_internal)
    monkeypatch.setattr("backend.services.chatbot.tool_registry.query_supabase", fake_query)
    monkeypatch.setattr(
        "backend.services.chatbot.tool_registry.get_user_id_from_header",
        lambda auth_header: ("user-1", "test"),
    )

    result = run_chatbot_tool("Bearer test", "삼성전자 10만원어치 사줘")

    assert result["data"]["status"] == "PENDING"
    assert calls[0]["json_data"]["raw_order_payload"]["precheck"]["estimated_amount_krw"] == 70000
    assert calls[0]["json_data"]["raw_order_payload"]["precheck"]["insufficient_cash"] is False


def test_run_chatbot_tool_routes_recommendation_request_to_recommendation_service(monkeypatch):
    class FakeRecommendationService:
        def recommend(self, auth_header, message):
            assert auth_header == "Bearer test"
            assert "추천" in message
            return {
                "reply": "활성 ML 신호 기준 추천 후보입니다.\n1. 삼성전자(005930)",
                "data": {"source": "ML_ACTIVE_SIGNAL", "items": [{"symbol": "005930"}]},
            }

    monkeypatch.setattr(
        "backend.services.chatbot.tool_registry.ChatbotRecommendationService",
        FakeRecommendationService,
    )

    result = run_chatbot_tool("Bearer test", "국내 주식 추천해줘")

    assert result["data"]["source"] == "ML_ACTIVE_SIGNAL"
    assert "삼성전자" in result["reply"]


def test_run_chatbot_tool_creates_proposal_from_last_recommendation_reference(monkeypatch):
    calls = []
    tool_registry._last_recommendations_by_user.clear()

    class FakeRecommendationService:
        def recommend(self, auth_header, message):
            return {
                "reply": "활성 ML 신호 기준 추천 후보입니다.\n1. 삼성전자(005930)\n2. SK하이닉스(000660)",
                "data": {
                    "source": "ML_ACTIVE_SIGNAL",
                    "items": [
                        {
                            "symbol": "005930",
                            "display_name": "삼성전자",
                            "asset_type": "STOCK",
                            "market": "KR",
                        },
                        {
                            "symbol": "000660",
                            "display_name": "SK하이닉스",
                            "asset_type": "STOCK",
                            "market": "KR",
                        },
                    ],
                },
            }

    def fake_query(auth_header, endpoint, method="GET", json_data=None, params=None):
        calls.append({"endpoint": endpoint, "method": method, "json_data": json_data, "params": params})
        if endpoint == "trade_proposals":
            return [{"id": "proposal-from-recommendation", "status": "PENDING"}]
        raise AssertionError(f"unexpected endpoint: {endpoint}")

    monkeypatch.setattr(tool_registry, "ChatbotRecommendationService", FakeRecommendationService)
    monkeypatch.setattr(tool_registry, "get_user_id_from_header", lambda auth_header: ("user-1", "test"))
    monkeypatch.setattr(
        tool_registry,
        "_resolve_symbol",
        lambda auth_header, query: {"symbol": query, "asset_type": "STOCK", "market": "KR"},
    )
    monkeypatch.setattr(
        tool_registry,
        "_get_internal",
        lambda path, auth_header, params=None: {"success": True, "data": {"current_price": 70000}},
    )
    monkeypatch.setattr(tool_registry, "_post_internal", lambda path, auth_header, body=None: {"success": True, "data": {}})
    monkeypatch.setattr(tool_registry, "query_supabase", fake_query)

    run_chatbot_tool("Bearer test", "국내 주식 추천해줘")
    result = run_chatbot_tool("Bearer test", "1번으로 10만원어치 매수 제안 만들어줘")

    assert result["data"]["status"] == "PENDING"
    assert calls[0]["json_data"]["symbol"] == "005930"
    assert calls[0]["json_data"]["side"] == "BUY"
    assert calls[0]["json_data"]["volume"] == 1


def test_run_chatbot_tool_requires_recent_recommendation_for_number_reference(monkeypatch):
    tool_registry._last_recommendations_by_user.clear()
    monkeypatch.setattr(tool_registry, "get_user_id_from_header", lambda auth_header: ("user-1", "test"))

    result = run_chatbot_tool("Bearer test", "1번으로 10만원어치 매수 제안 만들어줘")

    assert result["data"]["reason"] == "missing_recent_recommendation"
    assert "추천 후보를 먼저" in result["reply"]


def test_run_chatbot_tool_calculates_quantity_for_ratio_sell(monkeypatch):
    calls = []

    def fake_query(auth_header, endpoint, method="GET", json_data=None, params=None):
        calls.append({
            "endpoint": endpoint,
            "method": method,
            "json_data": json_data,
            "params": params,
        })
        if endpoint == "trade_proposals":
            return [{"id": "proposal-ratio", "status": "PENDING"}]
        raise AssertionError(f"unexpected endpoint: {endpoint}")

    monkeypatch.setattr(
        "backend.services.chatbot.tool_registry._resolve_symbol",
        lambda auth_header, query: {
            "symbol": "000660",
            "asset_type": "STOCK",
            "market": "KR",
        },
    )
    monkeypatch.setattr(
        "backend.services.chatbot.tool_registry.get_portfolio_summary",
        lambda auth_header, message: {
            "data": {
                "summaries": [
                    {
                        "exchange": "KIS",
                        "env": "MOCK",
                        "holdings": [
                            {"symbol": "000660", "qty": 8},
                        ],
                    }
                ]
            }
        },
    )
    monkeypatch.setattr(
        "backend.services.chatbot.tool_registry._get_internal",
        lambda path, auth_header, params=None: {
            "success": True,
            "data": {"current_price": 150000},
        },
    )
    monkeypatch.setattr(
        "backend.services.chatbot.tool_registry.query_supabase",
        fake_query,
    )
    monkeypatch.setattr(
        "backend.services.chatbot.tool_registry.get_user_id_from_header",
        lambda auth_header: ("user-1", "test"),
    )

    result = run_chatbot_tool("Bearer test", "하이닉스 절반 팔아줘")

    assert result["data"]["status"] == "PENDING"
    assert calls[0]["json_data"]["symbol"] == "000660"
    assert calls[0]["json_data"]["side"] == "SELL"
    assert calls[0]["json_data"]["volume"] == 4
    assert calls[0]["json_data"]["price"] == 150000
