import json
import logging

import jwt

from backend.services import supabase_client
from backend.services.chatbot.llm_client import ChatbotLLMClient


class FakeResponse:
    status_code = 200

    @staticmethod
    def json():
        return {
            "choices": [{"message": {"content": "응답"}}],
            "usage": {
                "prompt_tokens": 11,
                "completion_tokens": 7,
                "total_tokens": 18,
            },
        }


class FakeStreamResponse:
    status_code = 200

    @staticmethod
    def iter_lines(decode_unicode=True):
        chunks = [
            {"choices": [{"delta": {"content": "스트림"}}]},
            {
                "choices": [],
                "usage": {
                    "prompt_tokens": 13,
                    "completion_tokens": 8,
                    "total_tokens": 21,
                },
            },
        ]
        return [
            *(f"data: {json.dumps(chunk)}" for chunk in chunks),
            "data: [DONE]",
        ]


def auth_header(user_id="user-1"):
    token = jwt.encode({"sub": user_id}, "test-secret", algorithm="HS256")
    return f"Bearer {token}"


def test_normalize_usage_requires_positive_total_tokens():
    client = ChatbotLLMClient()

    assert client._normalize_usage(None) is None
    assert client._normalize_usage({}) is None
    assert client._normalize_usage({"total_tokens": 0}) is None
    assert client._normalize_usage({
        "prompt_tokens": "4",
        "completion_tokens": 3,
        "total_tokens": 7,
    }) == {
        "prompt_tokens": 4,
        "completion_tokens": 3,
        "total_tokens": 7,
    }


def test_generate_reply_records_actual_usage_with_service_role(monkeypatch):
    usage_calls = []
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(
        "backend.services.chatbot.llm_client.requests.post",
        lambda *args, **kwargs: FakeResponse(),
    )

    monkeypatch.setattr(
        "backend.services.chatbot.llm_client.query_supabase",
        lambda *args, **kwargs: [{"allowed": True}],
    )

    def fake_service_query(endpoint, method="GET", json_data=None, params=None):
        usage_calls.append({
            "endpoint": endpoint,
            "method": method,
            "json_data": json_data,
        })
        return []

    monkeypatch.setattr(
        "backend.services.chatbot.llm_client.query_supabase_as_service_role",
        fake_service_query,
    )

    client = ChatbotLLMClient()
    result = client.generate_reply(
        system_prompt="시스템",
        user_message="질문",
        user_id="user-1",
        auth_header=auth_header(),
        request_id="request-1",
    )

    assert result["usage"]["total_tokens"] == 18
    assert usage_calls == [{
        "endpoint": "chatbot_token_usage_logs",
        "method": "POST",
        "json_data": {
            "user_id": "user-1",
            "request_id": "request-1",
            "request_type": "chat_reply",
            "model": client.model,
            "prompt_tokens": 11,
            "completion_tokens": 7,
            "total_tokens": 18,
        },
    }]


def test_tool_synthesis_records_actual_usage_with_request_id(monkeypatch):
    usage_calls = []
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(
        "backend.services.chatbot.llm_client.requests.post",
        lambda *args, **kwargs: FakeResponse(),
    )
    monkeypatch.setattr(
        "backend.services.chatbot.llm_client.query_supabase_as_service_role",
        lambda endpoint, method="GET", json_data=None, params=None: usage_calls.append({
            "endpoint": endpoint,
            "method": method,
            "json_data": json_data,
        }),
    )

    client = ChatbotLLMClient()
    result = client.synthesize_tool_result_reply(
        system_prompt="시스템",
        user_message="질문",
        tool_name="get_price",
        tool_reply="결과",
        tool_data={"price": 100},
        user_id="user-1",
        auth_header=auth_header(),
        request_id="request-tool",
    )

    assert result["usage"]["total_tokens"] == 18
    assert usage_calls[0]["json_data"] == {
        "user_id": "user-1",
        "request_id": "request-tool",
        "request_type": "tool_synthesis",
        "model": client.model,
        "prompt_tokens": 11,
        "completion_tokens": 7,
        "total_tokens": 18,
    }


def test_chat_stream_records_actual_usage_with_request_id(monkeypatch):
    usage_calls = []
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(
        "backend.services.chatbot.llm_client.requests.post",
        lambda *args, **kwargs: FakeStreamResponse(),
    )
    monkeypatch.setattr(
        "backend.services.chatbot.llm_client.query_supabase",
        lambda *args, **kwargs: [{"allowed": True}],
    )
    monkeypatch.setattr(
        "backend.services.chatbot.llm_client.query_supabase_as_service_role",
        lambda endpoint, method="GET", json_data=None, params=None: usage_calls.append({
            "endpoint": endpoint,
            "method": method,
            "json_data": json_data,
        }),
    )

    client = ChatbotLLMClient()
    result = client.stream_reply(
        system_prompt="시스템",
        user_message="질문",
        user_id="user-1",
        auth_header=auth_header(),
        function_schemas=[],
        history=[],
        on_delta=lambda text: None,
        request_id="request-stream",
    )

    assert result["usage"]["total_tokens"] == 21
    assert usage_calls[0]["json_data"] == {
        "user_id": "user-1",
        "request_id": "request-stream",
        "request_type": "chat_stream",
        "model": client.model,
        "prompt_tokens": 13,
        "completion_tokens": 8,
        "total_tokens": 21,
    }


def test_usage_logging_failure_warns_without_failing_reply(monkeypatch, caplog):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(
        "backend.services.chatbot.llm_client.requests.post",
        lambda *args, **kwargs: FakeResponse(),
    )

    monkeypatch.setattr(
        "backend.services.chatbot.llm_client.query_supabase",
        lambda *args, **kwargs: [{"allowed": True}],
    )
    monkeypatch.setattr(
        "backend.services.chatbot.llm_client.query_supabase_as_service_role",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("raw provider payload secret")),
    )

    client = ChatbotLLMClient()
    with caplog.at_level(logging.WARNING, logger="backend.services.chatbot.llm_client"):
        result = client.generate_reply(
            system_prompt="시스템",
            user_message="질문",
            user_id="user-1",
            auth_header=auth_header(),
            request_id="request-failure",
        )

    assert result["reply"] == "응답"
    assert result["usage"]["total_tokens"] == 18
    assert "request_type=chat_reply" in caplog.text
    assert "user_id=user-1" in caplog.text
    assert "request_id=request-failure" in caplog.text
    assert "raw provider payload secret" not in caplog.text


def test_usage_logging_rejects_user_id_that_does_not_match_authenticated_subject(monkeypatch):
    usage_calls = []
    monkeypatch.setattr(
        "backend.services.chatbot.llm_client.query_supabase_as_service_role",
        lambda *args, **kwargs: usage_calls.append((args, kwargs)),
    )

    client = ChatbotLLMClient()
    client._record_actual_usage(
        auth_header=auth_header("user-1"),
        user_id="user-2",
        usage={"prompt_tokens": 2, "completion_tokens": 1, "total_tokens": 3},
        request_type="chat_reply",
        request_id="request-mismatch",
    )

    assert usage_calls == []


def test_service_role_usage_write_has_timeout(monkeypatch):
    captured = {}

    class FakeResponse:
        status_code = 201
        text = ""

    monkeypatch.setattr(supabase_client, "SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "service-role-key")

    def fake_post(url, headers=None, json=None, params=None, timeout=None):
        captured["url"] = url
        captured["timeout"] = timeout
        captured["json"] = json
        return FakeResponse()

    monkeypatch.setattr("backend.services.supabase_client.requests.post", fake_post)

    supabase_client.query_supabase_as_service_role(
        "chatbot_token_usage_logs",
        "POST",
        json_data={"user_id": "user-1"},
    )

    assert captured["url"].endswith("/rest/v1/chatbot_token_usage_logs")
    assert captured["timeout"] == supabase_client.SERVICE_ROLE_TIMEOUT_SECONDS
    assert captured["json"] == {"user_id": "user-1"}
