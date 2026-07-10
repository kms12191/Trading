import pytest

from backend.services.chatbot.llm_client import ChatbotLLMClient, ChatbotLimitError


class FakeResponse:
    status_code = 200

    @staticmethod
    def json():
        return {
            "choices": [{"message": {"content": "응답"}}],
            "usage": {"total_tokens": 12},
        }


def test_llm_client_consumes_shared_supabase_usage(monkeypatch):
    calls = []
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(
        "backend.services.chatbot.llm_client.query_supabase",
        lambda auth_header, endpoint, method, json_data: calls.append(json_data) or [{"allowed": True}],
    )
    monkeypatch.setattr(
        "backend.services.chatbot.llm_client.requests.post",
        lambda *args, **kwargs: FakeResponse(),
    )

    client = ChatbotLLMClient()
    result = client.generate_reply(
        system_prompt="시스템",
        user_message="질문",
        user_id="user-1",
        auth_header="Bearer test",
    )

    assert result["reply"] == "응답"
    assert calls[0]["p_user_id"] == "user-1"
    assert calls[0]["p_request_increment"] == 1
    assert calls[0]["p_token_increment"] > 0
    assert not hasattr(client, "_daily_usage")


def test_llm_client_blocks_when_shared_usage_store_denies(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(
        "backend.services.chatbot.llm_client.query_supabase",
        lambda *args, **kwargs: [{"allowed": False}],
    )

    client = ChatbotLLMClient()

    with pytest.raises(ChatbotLimitError):
        client.generate_reply(
            system_prompt="시스템",
            user_message="질문",
            user_id="user-1",
            auth_header="Bearer test",
        )
