import importlib
import uuid

import pytest
from flask import Flask

from backend.services.chatbot import chat_service
from backend.services.chatbot import tool_registry
from backend.services.chatbot.chat_service import ChatbotService
from backend.services.order_entry_service import issue_precheck_token, normalize_order_request


def _build_service() -> ChatbotService:
    return ChatbotService()


def test_plain_order_returns_top_button_guidance_without_action_or_prefill(monkeypatch):
    service = _build_service()
    monkeypatch.setattr(
        chat_service,
        "run_chatbot_tool",
        lambda *args, **kwargs: {
            "reply": "주문 제안이 생성되었습니다.",
            "data": {"source": "TRADE_PROPOSAL"},
        },
    )

    result = service.reply("코인원 XRP 10개 800원에 사줘", user_id=None, auth_header=None)

    assert result["reply"] == "주문은 상단의 매매 요청에서 직접 입력해 주세요."
    assert result["actions"] == []
    assert result["meta"]["tool_result"] == {"source": "ORDER_ENTRY_REQUIRED"}


def test_order_form_policy_does_not_extract_or_store_order_fields():
    policy = importlib.import_module("backend.services.chatbot.order_form_policy")

    result = policy.build_order_form_redirect("삼성전자 10주 사줘")

    assert result is not None
    assert result == {
        "reply": "주문은 상단의 매매 요청에서 직접 입력해 주세요.",
        "actions": [],
        "data": {"source": "ORDER_ENTRY_REQUIRED"},
    }


def test_structured_order_keeps_existing_proposal_path(monkeypatch):
    service = _build_service()
    expected = {"reply": "구조화 주문 제안", "actions": [], "data": {"source": "STRUCTURED_ORDER"}}
    monkeypatch.setattr(
        service,
        "_create_proposal_from_structured",
        lambda auth_header, user_id, structured_order: expected,
    )

    result = service.reply(
        "[주문 폼 전송]",
        user_id="user-1",
        auth_header="Bearer test",
        structured_order={
            "is_structured_order": True,
            "exchange": "TOSS",
            "broker_env": "REAL",
            "symbol_query": "삼성전자",
            "side": "BUY",
            "quantity": 1,
            "order_type": "LIMIT",
            "price": 70000,
        },
    )

    assert result == expected


def _valid_structured_order():
    return {
        "is_structured_order": True,
        "account_id": "TOSS:REAL:key-1",
        "exchange": "TOSS",
        "asset_type": "STOCK",
        "broker_env": "REAL",
        "intent": "BUY",
        "symbol": "005930",
        "symbol_selected": True,
        "quantity": 1,
        "order_type": "LIMIT",
        "price": 70000,
        "idempotency_key": str(uuid.UUID("44444444-4444-4444-8444-444444444444")),
    }


def test_structured_order_without_precheck_token_is_rejected(monkeypatch):
    service = _build_service()
    monkeypatch.setattr(
        tool_registry,
        "create_trade_proposal",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("검증 없는 제안 생성 금지")),
    )

    result = service._create_proposal_from_structured(
        "Bearer test",
        "user-1",
        _valid_structured_order(),
    )

    assert result["data"]["reason"] == "precheck_required"


def test_structured_order_uses_signed_precheck_snapshot(monkeypatch):
    service = _build_service()
    order = normalize_order_request(_valid_structured_order())
    precheck = {
        "reference_price": 70000.0,
        "estimated_amount_krw": 70000.0,
        "available_cash": 200000.0,
        "holding_qty": 0.0,
        "warnings": [],
        "balance_check_failed": False,
        "is_market_closed": False,
        "insufficient_cash": False,
        "insufficient_holding": False,
        "insufficient_permission": False,
        "futures_real_blocked": False,
        "exceeds_real_order_limit": False,
    }
    structured = {
        **_valid_structured_order(),
        "precheck_token": issue_precheck_token("user-1", order, precheck, "test-secret"),
    }
    captured = {}
    monkeypatch.setattr(
        tool_registry,
        "create_trade_proposal",
        lambda auth_header, arguments: captured.update({"auth_header": auth_header, "arguments": arguments}) or {
            "reply": "제안을 생성했습니다.",
            "data": {"id": structured["idempotency_key"]},
        },
    )
    app = Flask(__name__)
    app.config["SECRET_KEY"] = "test-secret"

    with app.app_context():
        result = service._create_proposal_from_structured("Bearer test", "user-1", structured)

    assert result["data"]["id"] == structured["idempotency_key"]
    assert captured["arguments"]["symbol"] == "005930"
    assert captured["arguments"]["raw_order_payload"]["source"] == "ORDER_ENTRY"
    assert captured["arguments"]["raw_order_payload"]["precheck"] == precheck
    assert captured["arguments"]["raw_order_payload"]["precheck_status"] == "OK"


@pytest.mark.parametrize(
    "message",
    [
        "삼성전자 10주 사줘",
        "XRP 전량 팔아줘",
        "1번 추천 종목 매수 제안해줘",
        "비트코인 조건매도 등록해줘",
    ],
)
def test_all_plain_order_messages_are_redirected_to_form(message):
    policy = importlib.import_module("backend.services.chatbot.order_form_policy")

    result = policy.build_order_form_redirect(message)

    assert result is not None
    assert result["data"]["source"] == "ORDER_ENTRY_REQUIRED"


def test_investment_question_does_not_open_order_form():
    policy = importlib.import_module("backend.services.chatbot.order_form_policy")

    assert policy.build_order_form_redirect("비트코인 지금 살까?") is None


def test_direct_tool_routing_cannot_create_plain_order(monkeypatch):
    monkeypatch.setattr(
        tool_registry,
        "_resolve_symbol",
        lambda auth_header, query: {
            "symbol": "005930",
            "display_name": "삼성전자",
            "asset_type": "STOCK_KR",
            "market": "KR",
        },
    )
    monkeypatch.setattr(tool_registry, "_is_plain_order_requiring_confirmation", lambda message, parsed: False)
    monkeypatch.setattr(
        tool_registry,
        "create_trade_proposal_from_message",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("일반 도구 라우팅에서 제안 생성 금지")),
    )

    result = tool_registry.run_chatbot_tool("Bearer test", "삼성전자 10주 사줘")

    assert result is not None
    assert result["data"]["source"] == "ORDER_ENTRY_REQUIRED"


@pytest.mark.parametrize("pending_action", ["trade_order_confirmation", "trade_proposal_retry"])
def test_legacy_pending_order_confirmation_redirects_to_form(monkeypatch, pending_action):
    service = _build_service()
    monkeypatch.setattr(
        tool_registry,
        "create_trade_proposal_from_message",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("기존 대기 작업에서 제안 생성 금지")),
    )

    result = service._run_pending_action(
        pending_action,
        "Bearer test",
        "응 진행해줘",
        {"message": "삼성전자 10주 사줘"},
    )

    assert result is not None
    assert result["data"]["source"] == "ORDER_ENTRY_REQUIRED"
