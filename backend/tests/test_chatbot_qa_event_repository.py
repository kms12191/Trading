from backend.services import supabase_client
from backend.services.chatbot.qa_event_repository import (
    ChatbotQAEventRepository,
    build_qa_event_payload,
)


def test_build_qa_event_payload_redacts_tool_result_details():
    payload = build_qa_event_payload(
        event_type="TOOL_RESULT",
        user_id="user-1",
        request_id="req-1",
        user_message="삼성전자 현재가 알려줘",
        assistant_message="삼성전자 현재가는 80,000원입니다.",
        meta={
            "source": "PROJECT_TOOL",
            "tool_result": {
                "source": "ASSET_PRICE",
                "symbol": "005930",
                "raw_order_payload": {"account": "secret"},
                "raw": {"provider": "secret"},
                "items": [{"a": 1}, {"b": 2}],
            },
            "trace_steps": [{"kind": "db", "label": "Supabase DB 조회"}],
        },
    )

    assert payload["event_type"] == "TOOL_RESULT"
    assert payload["user_id"] == "user-1"
    assert payload["request_id"] == "req-1"
    assert payload["event_payload"]["source"] == "PROJECT_TOOL"
    assert payload["event_payload"]["tool_source"] == "ASSET_PRICE"
    assert payload["event_payload"]["symbol"] == "005930"
    assert payload["event_payload"]["item_count"] == 2
    assert payload["event_payload"]["trace_kinds"] == ["db"]
    assert "raw_order_payload" not in payload["event_payload"]
    assert "raw" not in payload["event_payload"]


def test_record_event_uses_service_role_best_effort(monkeypatch):
    captured = {}

    def fake_safe_query(endpoint, method="GET", json_data=None, params=None):
        captured["endpoint"] = endpoint
        captured["method"] = method
        captured["json_data"] = json_data
        captured["params"] = params
        return [{"id": "event-1"}]

    monkeypatch.setattr(
        supabase_client,
        "safe_query_supabase_as_service_role",
        fake_safe_query,
    )

    repository = ChatbotQAEventRepository()
    repository.record_event(
        event_type="CHATBOT_REPLY",
        user_id="user-1",
        request_id="req-1",
        user_message="질문",
        assistant_message="답변",
        meta={"source": "LLM"},
    )

    assert captured["endpoint"] == "chatbot_qa_events"
    assert captured["method"] == "POST"
    assert captured["params"] is None
    assert captured["json_data"]["event_type"] == "CHATBOT_REPLY"
    assert captured["json_data"]["event_payload"]["reply_length"] == 2


def test_record_event_logs_service_role_exception(monkeypatch, caplog):
    def fake_query(endpoint, method="GET", json_data=None, params=None):
        raise RuntimeError("missing chatbot_qa_events column")

    monkeypatch.setattr(
        supabase_client,
        "query_supabase_as_service_role",
        fake_query,
    )

    repository = ChatbotQAEventRepository()
    repository.record_event(
        event_type="TOOL_RESULT",
        user_id="user-1",
        request_id="req-1",
        user_message="질문",
        assistant_message="답변",
        meta={"source": "PROJECT_TOOL"},
    )

    assert "챗봇 QA 이벤트 저장 실패" in caplog.text
    assert "missing chatbot_qa_events column" in caplog.text


def test_build_qa_event_payload_keeps_latency_and_error_signal():
    payload = build_qa_event_payload(
        event_type="CHATBOT_ERROR",
        user_id="user-1",
        request_id="req-1",
        user_message="계좌 보여줘",
        assistant_message="",
        meta={
            "source": "ROUTE_ERROR",
            "latency_ms": 1234,
            "error_title": "챗봇 응답 생성 실패",
            "error_code": "CHATBOT_ERROR",
        },
    )

    assert payload["event_payload"]["latency_ms"] == 1234
    assert payload["event_payload"]["error_title"] == "챗봇 응답 생성 실패"
    assert payload["event_payload"]["error_code"] == "CHATBOT_ERROR"
