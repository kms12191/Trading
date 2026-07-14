from flask import current_app

from backend.app import app
from backend.services.auth_service import validate_access_token


def test_chatbot_route_requires_authentication():
    client = app.test_client()

    response = client.post(
        "/api/chatbot/message",
        json={"message": "시세 알려줘"},
    )

    assert response.status_code == 401
    assert response.get_json()["success"] is False


def test_chatbot_route_rejects_malformed_authentication_header():
    client = app.test_client()

    response = client.post(
        "/api/chatbot/message",
        headers={"Authorization": "Basic invalid"},
        json={"message": "시세 알려줘"},
    )

    assert response.status_code == 401
    assert response.get_json()["success"] is False


def test_chatbot_route_rejects_token_not_validated_by_supabase(monkeypatch):
    def reject_token(_auth_header):
        raise ValueError("Supabase access token 검증에 실패했습니다.")

    monkeypatch.setattr("backend.routes.chatbot.validate_access_token", reject_token)
    client = app.test_client()

    response = client.post(
        "/api/chatbot/message",
        headers={"Authorization": "Bearer structurally.valid.jwt"},
        json={"message": "시세 알려줘"},
    )

    assert response.status_code == 401
    assert response.get_json()["success"] is False


def test_chatbot_message_route_records_qa_event(monkeypatch):
    monkeypatch.setattr(
        "backend.routes.chatbot.validate_access_token",
        lambda auth_header: ("user-1", "token"),
    )
    monkeypatch.setattr(
        "backend.routes.chatbot.chatbot_service.reply",
        lambda message, **kwargs: {
            "reply": "삼성전자 현재가는 80,000원입니다.",
            "actions": [],
            "meta": {
                "source": "PROJECT_TOOL",
                "tool_result": {"source": "ASSET_PRICE", "symbol": "005930"},
                "trace_steps": [{"kind": "db", "label": "Supabase DB 조회"}],
            },
        },
    )
    inserted = []
    monkeypatch.setattr(
        "backend.services.supabase_client.safe_query_supabase_as_service_role",
        lambda endpoint, method="GET", json_data=None, params=None: inserted.append({
            "endpoint": endpoint,
            "method": method,
            "json_data": json_data,
            "params": params,
        }) or [{"id": "event-1"}],
    )

    response = app.test_client().post(
        "/api/chatbot/message",
        headers={"Authorization": "Bearer valid"},
        json={"message": "삼성전자 현재가 알려줘"},
    )

    assert response.status_code == 200
    assert len(inserted) == 1
    assert inserted[0]["endpoint"] == "chatbot_qa_events"
    assert inserted[0]["method"] == "POST"
    assert inserted[0]["params"] is None
    payload = inserted[0]["json_data"]
    assert payload["event_type"] == "TOOL_RESULT"
    assert payload["user_id"] == "user-1"
    assert payload["request_id"]
    assert payload["event_payload"]["tool_source"] == "ASSET_PRICE"
    assert payload["event_payload"]["symbol"] == "005930"
    assert payload["event_payload"]["user_message_preview"] == "삼성전자 현재가 알려줘"
    assert payload["event_payload"]["assistant_message_preview"] == "삼성전자 현재가는 80,000원입니다."
    assert isinstance(payload["event_payload"]["latency_ms"], int)


def test_chatbot_stream_route_emits_trace_delta_and_done_events(monkeypatch):
    monkeypatch.setattr(
        "backend.routes.chatbot.validate_access_token",
        lambda auth_header: ("user-1", "token"),
    )
    monkeypatch.setattr(
        "backend.routes.chatbot.chatbot_service.reply",
        lambda message, user_id=None, auth_header=None, user_timezone=None, trace_callback=None, delta_callback=None, request_id=None: {
            "reply": "추천 후보입니다.",
            "actions": [],
            "meta": {
                "source": "PROJECT_TOOL",
                "tool_result": {"source": "ML_ACTIVE_SIGNAL"},
                "trace_steps": [{"kind": "ml", "label": "ML 신호"}],
            },
        },
    )
    client = app.test_client()

    response = client.post(
        "/api/chatbot/stream",
        headers={"Authorization": "Bearer valid"},
        json={"message": "국내 주식 추천해줘", "timezone": "Asia/Seoul"},
    )

    body = response.get_data(as_text=True)

    assert response.status_code == 200
    assert response.mimetype == "text/event-stream"
    assert "event: trace" in body
    assert '"label": "요청 분석"' in body
    assert '"label": "ML 신호"' in body
    assert "event: delta" in body
    assert '"text": "추천 후보입니다."' in body
    assert "event: done" in body
    assert '"source": "PROJECT_TOOL"' in body
    assert '"request_id"' in body


def test_chatbot_stream_forwards_live_deltas_without_rechunking(monkeypatch):
    monkeypatch.setattr(
        "backend.routes.chatbot.validate_access_token",
        lambda auth_header: ("user-1", "token"),
    )

    def fake_reply(
        message,
        user_id=None,
        auth_header=None,
        user_timezone=None,
        trace_callback=None,
        delta_callback=None,
        request_id=None,
    ):
        delta_callback("첫 ")
        delta_callback("답변")
        return {"reply": "첫 답변", "actions": [], "meta": {"source": "OPENAI"}}

    monkeypatch.setattr("backend.routes.chatbot.chatbot_service.reply", fake_reply)
    response = app.test_client().post(
        "/api/chatbot/stream",
        headers={"Authorization": "Bearer valid"},
        json={"message": "질문"},
    )
    body = response.get_data(as_text=True)

    assert body.count("event: delta") == 2
    assert '"text": "첫 "' in body
    assert '"text": "답변"' in body
    assert body.index("event: trace") < body.index("event: delta") < body.index("event: done")
    assert '"request_id"' in body


def test_chatbot_stream_route_emits_live_trace_callback_events(monkeypatch):
    monkeypatch.setattr(
        "backend.routes.chatbot.validate_access_token",
        lambda auth_header: ("user-1", "token"),
    )

    def fake_reply(
        message,
        user_id=None,
        auth_header=None,
        user_timezone=None,
        trace_callback=None,
        delta_callback=None,
        request_id=None,
    ):
        trace_callback({"kind": "tool_routing", "label": "도구 확인"})
        trace_callback({"kind": "ml", "label": "ML 신호 조회 중"})
        return {
            "reply": "추천 후보입니다.",
            "actions": [],
            "meta": {
                "source": "PROJECT_TOOL",
                "tool_result": {"source": "ML_ACTIVE_SIGNAL"},
                "trace_steps": [{"kind": "ml", "label": "ML 신호"}],
            },
        }

    monkeypatch.setattr("backend.routes.chatbot.chatbot_service.reply", fake_reply)
    client = app.test_client()

    response = client.post(
        "/api/chatbot/stream",
        headers={"Authorization": "Bearer valid"},
        json={"message": "국내 주식 추천해줘"},
    )

    body = response.get_data(as_text=True)

    assert body.index('"label": "도구 확인"') < body.index('"text": "추천 후보입니다."')
    assert '"label": "ML 신호 조회 중"' in body


def test_chatbot_stream_worker_has_app_context_and_logs_request_id(monkeypatch):
    monkeypatch.setattr(
        "backend.routes.chatbot.validate_access_token",
        lambda auth_header: ("user-1", "token"),
    )
    logged = []

    def fake_reply(
        message,
        user_id=None,
        auth_header=None,
        user_timezone=None,
        trace_callback=None,
        delta_callback=None,
        request_id=None,
    ):
        assert current_app.name == app.name
        assert request_id
        raise RuntimeError("stream failed")

    monkeypatch.setattr("backend.routes.chatbot.chatbot_service.reply", fake_reply)
    monkeypatch.setattr(
        app.logger,
        "exception",
        lambda message, *args: logged.append((message, args)),
    )

    response = app.test_client().post(
        "/api/chatbot/stream",
        headers={"Authorization": "Bearer valid"},
        json={"message": "질문"},
    )
    body = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "event: error" in body
    assert '"request_id"' in body
    assert len(logged) == 1
    assert logged[0][0] == "챗봇 스트림 생성 실패: request_id=%s user_id=%s"
    assert logged[0][1][1] == "user-1"


def test_chatbot_stream_partial_delta_ends_with_error_not_done(monkeypatch):
    monkeypatch.setattr(
        "backend.routes.chatbot.validate_access_token",
        lambda auth_header: ("user-1", "token"),
    )

    def fake_reply(
        message,
        user_id=None,
        auth_header=None,
        user_timezone=None,
        trace_callback=None,
        delta_callback=None,
        request_id=None,
    ):
        delta_callback("부분 답변")
        raise RuntimeError("stream failed")

    monkeypatch.setattr("backend.routes.chatbot.chatbot_service.reply", fake_reply)
    response = app.test_client().post(
        "/api/chatbot/stream",
        headers={"Authorization": "Bearer valid"},
        json={"message": "질문"},
    )
    body = response.get_data(as_text=True)

    assert '"text": "부분 답변"' in body
    assert "event: error" in body
    assert "event: done" not in body
    assert '"request_id"' in body


def test_validate_access_token_matches_supabase_user(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_ANON_KEY", "anon-key")

    class FakeResponse:
        status_code = 200

        @staticmethod
        def json():
            return {"id": "user-1"}

    requests_seen = []

    def fake_get(url, headers, timeout):
        requests_seen.append({"url": url, "headers": headers, "timeout": timeout})
        return FakeResponse()

    monkeypatch.setattr("backend.services.auth_service.requests.get", fake_get)

    user_id, token = validate_access_token(
        "Bearer eyJhbGciOiJub25lIiwidHlwIjoiSldUIn0.eyJzdWIiOiJ1c2VyLTEifQ.c2lnbmF0dXJl"
    )

    assert user_id == "user-1"
    assert token.startswith("eyJ")
    assert requests_seen[0]["url"] == "https://example.supabase.co/auth/v1/user"
    assert requests_seen[0]["headers"]["apikey"] == "anon-key"
