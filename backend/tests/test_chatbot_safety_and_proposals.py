import pytest

from backend.app import app
from backend.services.chatbot.safety_guard import (
    RiskLevel,
    SafetyGuardError,
    assess_tool_risk,
    enforce_tool_safety,
)
from backend.services.chatbot import tool_registry
from backend.services.chatbot.function_calling import FUNCTION_SCHEMAS
from backend.services.chatbot.tool_registry import create_trade_proposal, run_chatbot_tool
from backend.routes.trade import _resolve_proposal_order_data


def _valid_precheck(reference_price=800, estimated_amount_krw=8000, **overrides):
    precheck = {
        "reference_price": reference_price,
        "estimated_amount_krw": estimated_amount_krw,
        "available_cash": 1000000,
        "holding_qty": 100,
        "balance_check_failed": False,
        "is_market_closed": False,
        "insufficient_cash": False,
        "insufficient_holding": False,
        "insufficient_permission": False,
        "futures_real_blocked": False,
        "exceeds_real_order_limit": False,
    }
    precheck.update(overrides)
    return precheck


def test_safety_guard_separates_read_write_proposal_and_order_risks():
    assert assess_tool_risk("get_holdings") == RiskLevel.READ
    assert assess_tool_risk("add_watchlist_item") == RiskLevel.WRITE
    assert assess_tool_risk("create_trade_proposal") == RiskLevel.PROPOSAL
    assert assess_tool_risk("place_order") == RiskLevel.ORDER


def test_safety_guard_blocks_order_tool_before_execution():
    with pytest.raises(SafetyGuardError):
        enforce_tool_safety("place_order", {})


def test_holdings_summary_routes_to_amount_summary_before_detail(monkeypatch):
    monkeypatch.setattr(
        tool_registry,
        "get_portfolio_summary",
        lambda auth_header, message: {
            "reply": "실거래 평가자산 합계: 1,000,000원",
            "data": {"source": "PORTFOLIO_SUMMARY"},
        },
    )
    monkeypatch.setattr(
        tool_registry,
        "get_holdings",
        lambda *args: (_ for _ in ()).throw(AssertionError("상세 holdings 라우팅 금지")),
    )

    result = run_chatbot_tool("Bearer test", "내 보유자산 요약해줘")

    assert result["data"]["source"] == "PORTFOLIO_SUMMARY"


def test_portfolio_summary_limits_errors_without_raw_exception(monkeypatch):
    monkeypatch.setattr(
        tool_registry,
        "_post_internal",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            RuntimeError("secret raw credential detail")
        ),
    )

    result = tool_registry.get_portfolio_summary("Bearer test", "내 자산 요약")

    assert len(result["data"]["errors"]) == 5
    assert result["reply"].count("계좌 조회 실패") == 3
    assert "secret raw credential detail" not in result["reply"]


def test_get_holdings_keeps_detailed_quantity_role(monkeypatch):
    monkeypatch.setattr(
        tool_registry,
        "get_portfolio_summary",
        lambda *args: {
            "data": {
                "summaries": [
                    {
                        "exchange": "KIS",
                        "env": "REAL",
                        "holdings": [
                            {"name": "삼성전자", "symbol": "005930", "qty": 3},
                        ],
                    },
                ],
            },
        },
    )

    result = tool_registry.get_holdings("Bearer test", "내 주식 보여줘")

    assert "보유 현황입니다" in result["reply"]
    assert "삼성전자" in result["reply"]
    assert ": 3" in result["reply"]


def test_llm_schema_does_not_expose_trade_proposal_creation():
    assert "create_trade_proposal" not in {schema["name"] for schema in FUNCTION_SCHEMAS}


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
            "exchange": "BINANCE",
            "asset_type": "CRYPTO",
            "symbol": "XRP",
            "side": "BUY",
            "order_type": "LIMIT",
            "quantity": 10,
            "price": 800,
            "broker_env": "MOCK",
            "raw_order_payload": {
                "precheck_status": "OK",
                "precheck": _valid_precheck(),
                "source": "CHATBOT_ORDER_PARSER",
            },
        },
    )

    assert result["data"]["status"] == "PENDING"
    assert calls[0]["endpoint"] == "trade_proposals"
    assert calls[0]["method"] == "POST"
    assert calls[0]["json_data"]["status"] == "PENDING"


def test_create_trade_proposal_rejects_coinone_mock_before_insert(monkeypatch):
    monkeypatch.setattr(tool_registry, "get_user_id_from_header", lambda auth_header: ("user-1", "test"))
    monkeypatch.setattr(tool_registry, "query_supabase", lambda *args, **kwargs: (_ for _ in ()).throw(
        AssertionError("지원하지 않는 모의 환경은 insert 금지")
    ))

    with pytest.raises(ValueError, match="모의 계좌 환경"):
        create_trade_proposal(
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
                "raw_order_payload": {
                    "precheck_status": "OK",
                    "precheck": _valid_precheck(),
                    "source": "CHATBOT_ORDER_PARSER",
                },
            },
        )


def test_create_trade_proposal_rejects_missing_precheck(monkeypatch):
    monkeypatch.setattr(tool_registry, "get_user_id_from_header", lambda auth_header: ("user-1", "test"))
    monkeypatch.setattr(tool_registry, "query_supabase", lambda *args, **kwargs: (_ for _ in ()).throw(
        AssertionError("검증 없는 insert 금지")
    ))

    with pytest.raises(ValueError, match="사전검증"):
        create_trade_proposal(
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


def test_create_trade_proposal_rejects_precheck_blocker(monkeypatch):
    monkeypatch.setattr(tool_registry, "get_user_id_from_header", lambda auth_header: ("user-1", "test"))
    monkeypatch.setattr(tool_registry, "query_supabase", lambda *args, **kwargs: (_ for _ in ()).throw(
        AssertionError("차단 사유가 있는 insert 금지")
    ))

    with pytest.raises(ValueError, match="현금"):
        create_trade_proposal(
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
                "raw_order_payload": {
                    "precheck_status": "OK",
                    "precheck": _valid_precheck(insufficient_cash=True),
                },
            },
        )


def test_create_trade_proposal_rejects_unverified_balance(monkeypatch):
    monkeypatch.setattr(tool_registry, "get_user_id_from_header", lambda auth_header: ("user-1", "test"))
    monkeypatch.setattr(tool_registry, "query_supabase", lambda *args, **kwargs: (_ for _ in ()).throw(
        AssertionError("잔고 미검증 제안 insert 금지")
    ))

    with pytest.raises(ValueError, match="잔고"):
        create_trade_proposal(
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
                "raw_order_payload": {
                    "precheck_status": "OK",
                    "precheck": _valid_precheck(
                        available_cash=None,
                        balance_check_failed=True,
                    ),
                },
            },
        )


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
        "backend.routes.trade._reject_pending_trade_proposal",
        lambda auth_header, user_id, proposal_id: {"id": proposal_id, "status": "REJECTED"},
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
    monkeypatch.setattr(
        "backend.services.chatbot.tool_registry._run_chatbot_precheck",
        lambda **kwargs: _valid_precheck(),
        raising=False,
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
    monkeypatch.setattr(
        "backend.services.chatbot.tool_registry._run_chatbot_precheck",
        lambda **kwargs: _valid_precheck(70000, 70000),
        raising=False,
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
        assert body["exchange"] == "TOSS"
        assert body["symbol"] == "005930"
        assert body["action"] == "BUY"
        return {
            "success": True,
            "data": {
                "reference_price": 70000,
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


def test_run_chatbot_tool_asks_confirmation_before_plain_order_precheck(monkeypatch):
    pending = {}

    def fake_set_pending_action(auth_header, user_id, action, payload=None, ttl_seconds=300):
        pending.update({
            "auth_header": auth_header,
            "user_id": user_id,
            "action": action,
            "payload": payload,
            "ttl_seconds": ttl_seconds,
        })

    monkeypatch.setattr(tool_registry, "get_user_id_from_header", lambda auth_header: ("user-1", "test"))
    monkeypatch.setattr(tool_registry._conversation_repository, "set_pending_action", fake_set_pending_action)
    monkeypatch.setattr(
        tool_registry,
        "_resolve_symbol",
        lambda auth_header, query: {
            "symbol": "005930",
            "display_name": "삼성전자",
            "asset_type": "STOCK",
            "market": "KR",
        },
    )
    monkeypatch.setattr(
        tool_registry,
        "_run_chatbot_precheck",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("확인 전 사전검증 금지")),
        raising=False,
    )

    result = run_chatbot_tool("Bearer test", "삼성전자 1주 사줘")

    assert result["data"]["source"] == "CHATBOT_ORDER_CONFIRMATION"
    assert result["data"]["status"] == "PENDING_CONFIRMATION"
    assert pending["action"] == "trade_order_confirmation"
    assert pending["payload"]["message"] == "삼성전자 1주 사줘"
    assert "삼성전자" in result["reply"]
    assert "1주" in result["reply"]
    assert "맞" in result["reply"]


def test_run_chatbot_tool_does_not_confirm_order_without_quantity(monkeypatch):
    pending_calls = []

    monkeypatch.setattr(tool_registry, "get_user_id_from_header", lambda auth_header: ("user-1", "test"))
    monkeypatch.setattr(
        tool_registry._conversation_repository,
        "set_pending_action",
        lambda *args, **kwargs: pending_calls.append((args, kwargs)),
    )
    monkeypatch.setattr(
        tool_registry,
        "_resolve_symbol",
        lambda auth_header, query: {
            "symbol": "462350",
            "display_name": "이노스페이스",
            "asset_type": "STOCK",
            "market": "KR",
        },
    )

    result = run_chatbot_tool("Bearer test", "이노스페이스 매수하고 싶어")

    assert pending_calls == []
    assert result["data"]["reason"] == "missing_quantity"
    assert "수량" in result["reply"]


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
    conversation_state = {}

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
        if endpoint == "chatbot_conversation_states":
            params = params or {}
            user_id = str(params.get("user_id") or "").removeprefix("eq.")
            if method == "GET":
                return [dict(conversation_state)] if conversation_state else []
            if method == "POST":
                conversation_state.update(json_data or {})
                return [dict(conversation_state)]
            if method == "PATCH":
                conversation_state.update(json_data or {})
                return [dict(conversation_state)]
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
    monkeypatch.setattr(
        tool_registry,
        "_run_chatbot_precheck",
        lambda **kwargs: _valid_precheck(70000, 70000),
        raising=False,
    )
    monkeypatch.setattr(tool_registry, "query_supabase", fake_query)
    monkeypatch.setattr(
        "backend.services.chatbot.conversation_repository.query_supabase",
        fake_query,
    )

    run_chatbot_tool("Bearer test", "국내 주식 추천해줘")
    result = run_chatbot_tool("Bearer test", "1번으로 10만원어치 매수 제안 만들어줘")

    assert result["data"]["status"] == "PENDING"
    assert calls[0]["json_data"]["symbol"] == "005930"
    assert calls[0]["json_data"]["side"] == "BUY"
    assert calls[0]["json_data"]["volume"] == 1


def test_run_chatbot_tool_requires_recent_recommendation_for_number_reference(monkeypatch):
    monkeypatch.setattr(tool_registry, "get_user_id_from_header", lambda auth_header: ("user-1", "test"))
    monkeypatch.setattr(
        "backend.services.chatbot.conversation_repository.query_supabase",
        lambda *args, **kwargs: [],
    )

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
                        "exchange": "TOSS",
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
    monkeypatch.setattr(
        "backend.services.chatbot.tool_registry._run_chatbot_precheck",
        lambda **kwargs: _valid_precheck(150000, 600000),
        raising=False,
    )

    result = run_chatbot_tool("Bearer test", "하이닉스 절반 팔아줘")

    assert result["data"]["status"] == "PENDING"
    assert calls[0]["json_data"]["symbol"] == "000660"
    assert calls[0]["json_data"]["side"] == "SELL"
    assert calls[0]["json_data"]["volume"] == 4
    assert calls[0]["json_data"]["price"] == 150000


def test_incomplete_proposal_request_never_calls_llm_or_inserts(monkeypatch):
    inserted = []
    monkeypatch.setattr(tool_registry, "query_supabase", lambda *args, **kwargs: inserted.append(kwargs))

    result = run_chatbot_tool("Bearer test", "매매 제안 만들어줘")

    assert result["data"]["reason"] == "missing_order_intent"
    assert "종목" in result["reply"]
    assert inserted == []


def test_multi_symbol_trade_request_never_prechecks_or_inserts(monkeypatch):
    monkeypatch.setattr(
        tool_registry,
        "_resolve_symbol",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("모호한 복수 종목 해석 금지")),
    )
    monkeypatch.setattr(
        tool_registry,
        "_run_chatbot_precheck",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("모호한 복수 종목 사전검증 금지")),
        raising=False,
    )
    monkeypatch.setattr(
        tool_registry,
        "query_supabase",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("모호한 복수 종목 insert 금지")),
    )

    result = run_chatbot_tool("Bearer test", "삼성전자랑 하이닉스 중 1주 매수 제안해줘")

    assert result["data"]["reason"] == "missing_order_intent"
    assert "종목" in result["reply"]


def test_precheck_failure_does_not_insert_pending_proposal(monkeypatch):
    monkeypatch.setattr(tool_registry, "_resolve_symbol", lambda *args: {
        "symbol": "DOGE", "asset_type": "CRYPTO", "market": "KR",
    })
    monkeypatch.setattr(tool_registry, "_run_chatbot_precheck", lambda **kwargs: (_ for _ in ()).throw(
        ValueError("등록된 COINONE (REAL) API 키가 없습니다.")
    ))
    monkeypatch.setattr(tool_registry, "query_supabase", lambda *args, **kwargs: (_ for _ in ()).throw(
        AssertionError("검증 실패 후 insert 금지")
    ))

    result = run_chatbot_tool("Bearer test", "도지 10개 100원에 실거래로 팔아줘")

    assert result["data"]["reason"] == "precheck_failed"
    assert "API 키" in result["reply"]


def test_run_chatbot_precheck_requires_reference_price_and_estimated_amount(monkeypatch):
    monkeypatch.setattr(
        tool_registry,
        "_post_internal",
        lambda *args, **kwargs: {"success": True, "data": {"estimated_amount_krw": 8000}},
    )

    with pytest.raises(ValueError, match="현재가와 예상 주문금액"):
        tool_registry._run_chatbot_precheck(
            auth_header="Bearer test",
            exchange="COINONE",
            symbol="XRP",
            side="BUY",
            order_type="LIMIT",
            quantity=10,
            price=800,
            broker_env="MOCK",
        )


def test_run_chatbot_precheck_requires_relevant_balance(monkeypatch):
    monkeypatch.setattr(
        tool_registry,
        "_post_internal",
        lambda *args, **kwargs: {
            "success": True,
            "data": {
                "reference_price": 800,
                "estimated_amount_krw": 8000,
                "available_cash": None,
                "balance_check_failed": True,
            },
        },
    )

    with pytest.raises(ValueError, match="잔고"):
        tool_registry._run_chatbot_precheck(
            auth_header="Bearer test",
            exchange="COINONE",
            symbol="XRP",
            side="BUY",
            order_type="LIMIT",
            quantity=10,
            price=800,
            broker_env="MOCK",
        )


def test_precheck_blockers_apply_real_order_limit_only_to_real_environment():
    precheck = _valid_precheck(
        is_market_closed=True,
        insufficient_cash=True,
        insufficient_holding=True,
        insufficient_permission=True,
        futures_real_blocked=True,
        exceeds_real_order_limit=True,
    )

    mock_blockers = tool_registry._collect_precheck_blockers(precheck, "MOCK")
    real_blockers = tool_registry._collect_precheck_blockers(precheck, "REAL")

    assert len(mock_blockers) == 5
    assert len(real_blockers) == 6
    assert all("100,000원" not in blocker for blocker in mock_blockers)
    assert any("100,000원" in blocker for blocker in real_blockers)


def test_coinone_market_order_returns_limit_order_guide_without_insert(monkeypatch):
    monkeypatch.setattr(tool_registry, "_resolve_symbol", lambda *args: {
        "symbol": "XRP", "asset_type": "CRYPTO", "market": "KR",
    })
    monkeypatch.setattr(tool_registry, "get_user_id_from_header", lambda auth_header: ("user-1", "test"))
    monkeypatch.setattr(tool_registry, "_post_internal", lambda *args, **kwargs: (_ for _ in ()).throw(
        AssertionError("지원하지 않는 주문유형은 사전검증 호출 금지")
    ))
    monkeypatch.setattr(tool_registry, "query_supabase", lambda *args, **kwargs: (_ for _ in ()).throw(
        AssertionError("지원하지 않는 주문유형 insert 금지")
    ))

    result = run_chatbot_tool("Bearer test", "XRP 10개 모의로 사줘")

    assert result["data"]["reason"] == "unsupported_order_type"
    assert "지정가" in result["reply"]
    assert "800원에" in result["reply"]


def test_coinone_amount_market_proposal_returns_limit_order_guide_without_insert(monkeypatch):
    monkeypatch.setattr(tool_registry, "_resolve_symbol", lambda *args: {
        "symbol": "BTC", "asset_type": "CRYPTO", "market": "KR",
    })
    monkeypatch.setattr(tool_registry, "get_user_id_from_header", lambda auth_header: ("user-1", "test"))
    monkeypatch.setattr(tool_registry, "_post_internal", lambda *args, **kwargs: (_ for _ in ()).throw(
        AssertionError("지원하지 않는 코인원 시장가성 금액 주문은 사전검증 호출 금지")
    ))
    monkeypatch.setattr(tool_registry, "query_supabase", lambda *args, **kwargs: (_ for _ in ()).throw(
        AssertionError("지원하지 않는 코인원 시장가성 금액 주문 insert 금지")
    ))

    result = run_chatbot_tool("Bearer test", "비트코인 8000만원 매수 제안해줘")

    assert result["data"]["reason"] == "unsupported_order_type"
    assert result["data"]["symbol"] == "BTC"
    assert "지정가" in result["reply"]


@pytest.mark.parametrize(
    ("message", "expected_env"),
    [
        ("XRP 10개 800원에 사줘", "MOCK"),
        ("XRP 10개 800원에 실거래로 사줘", "REAL"),
    ],
)
def test_order_environment_defaults_to_mock_and_keeps_explicit_real(monkeypatch, message, expected_env):
    calls = []
    monkeypatch.setattr(tool_registry, "_resolve_symbol", lambda *args: {
        "symbol": "XRP", "asset_type": "CRYPTO", "market": "KR",
    })
    monkeypatch.setattr(
        tool_registry,
        "_run_chatbot_precheck",
        lambda **kwargs: calls.append(kwargs) or _valid_precheck(),
        raising=False,
    )
    monkeypatch.setattr(tool_registry, "get_user_id_from_header", lambda auth_header: ("user-1", "test"))
    monkeypatch.setattr(
        tool_registry,
        "query_supabase",
        lambda *args, **kwargs: [{"id": "proposal-env", "status": "PENDING"}],
    )

    result = run_chatbot_tool("Bearer test", message)

    assert result["data"]["broker_env"] == expected_env
    assert calls[0]["broker_env"] == expected_env


def test_crypto_amount_quantity_is_floored_to_eight_decimals():
    quantity = tool_registry._quantity_from_amount(1, 6, "CRYPTO")

    assert quantity == 0.16666666


def test_crypto_explicit_quantity_is_floored_before_precheck_and_insert(monkeypatch):
    calls = []

    def fake_query(auth_header, endpoint, method="GET", json_data=None, params=None):
        calls.append({"endpoint": endpoint, "json_data": json_data})
        if endpoint == "trade_proposals":
            return [{"id": "proposal-crypto-precision", "status": "PENDING"}]
        raise AssertionError(f"unexpected endpoint: {endpoint}")

    monkeypatch.setattr(tool_registry, "_resolve_symbol", lambda *args: {
        "symbol": "XRP", "asset_type": "CRYPTO", "market": "KR",
    })
    monkeypatch.setattr(
        tool_registry,
        "_run_chatbot_precheck",
        lambda **kwargs: calls.append({"endpoint": "precheck", "json_data": kwargs}) or _valid_precheck(),
        raising=False,
    )
    monkeypatch.setattr(tool_registry, "get_user_id_from_header", lambda auth_header: ("user-1", "test"))
    monkeypatch.setattr(tool_registry, "query_supabase", fake_query)

    result = run_chatbot_tool("Bearer test", "XRP 0.123456789개 800원에 모의로 사줘")

    assert result["data"]["status"] == "PENDING"
    assert calls[0]["json_data"]["quantity"] == 0.12345678
    assert calls[1]["json_data"]["volume"] == 0.12345678


def test_chatbot_proposal_uses_exchange_normalized_precheck_quantity(monkeypatch):
    calls = []

    def fake_query(auth_header, endpoint, method="GET", json_data=None, params=None):
        calls.append({"endpoint": endpoint, "json_data": json_data})
        if endpoint == "trade_proposals":
            return [{"id": "proposal-normalized-qty", "status": "PENDING"}]
        raise AssertionError(f"unexpected endpoint: {endpoint}")

    monkeypatch.setattr(tool_registry, "_resolve_symbol", lambda *args: {
        "symbol": "XRP", "asset_type": "CRYPTO", "market": "KR",
    })
    monkeypatch.setattr(
        tool_registry,
        "_run_chatbot_precheck",
        lambda **kwargs: _valid_precheck(quantity=0.1234, estimated_amount_krw=98.72),
        raising=False,
    )
    monkeypatch.setattr(tool_registry, "get_user_id_from_header", lambda auth_header: ("user-1", "test"))
    monkeypatch.setattr(tool_registry, "query_supabase", fake_query)

    result = run_chatbot_tool("Bearer test", "XRP 0.12345678개 800원에 모의로 사줘")

    assert result["data"]["status"] == "PENDING"
    assert calls[0]["json_data"]["volume"] == 0.1234
    assert calls[0]["json_data"]["raw_order_payload"]["precheck"]["quantity"] == 0.1234
