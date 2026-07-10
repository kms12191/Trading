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


def test_chatbot_stream_route_emits_trace_delta_and_done_events(monkeypatch):
    monkeypatch.setattr(
        "backend.routes.chatbot.validate_access_token",
        lambda auth_header: ("user-1", "token"),
    )
    monkeypatch.setattr(
        "backend.routes.chatbot.chatbot_service.reply",
        lambda message, user_id=None, auth_header=None, user_timezone=None, trace_callback=None: {
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


def test_chatbot_stream_route_emits_live_trace_callback_events(monkeypatch):
    monkeypatch.setattr(
        "backend.routes.chatbot.validate_access_token",
        lambda auth_header: ("user-1", "token"),
    )

    def fake_reply(message, user_id=None, auth_header=None, user_timezone=None, trace_callback=None):
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
