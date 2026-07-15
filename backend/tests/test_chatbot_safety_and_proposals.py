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


def test_stock_trade_status_sentence_marks_trading_suspended():
    sentence = tool_registry._format_stock_trade_status_sentence(
        "동양(001520)",
        {
            "warnings": [{"warning_type": "TRADING_SUSPENDED"}],
            "status_lookup_failed": False,
        },
    )

    assert sentence == "현재 동양(001520)은/는 거래정지 상태입니다."


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



def test_crypto_amount_quantity_is_floored_to_eight_decimals():
    quantity = tool_registry._quantity_from_amount(1, 6, "CRYPTO")

    assert quantity == 0.16666666
