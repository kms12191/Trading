# backend/tests/chatbot/test_llm_provider.py
import os
import pytest


def test_create_chatbot_llm_returns_model_with_fallbacks(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-gemini-key")
    monkeypatch.setenv("OPENAI_API_KEY", "test-openai-key")
    monkeypatch.setenv("CHATBOT_PRIMARY_MODEL", "gpt-4.1-mini")
    monkeypatch.setenv("CHATBOT_SECONDARY_MODEL", "gemini-3.1-flash-lite")
    monkeypatch.setenv("CHATBOT_TERTIARY_MODEL", "gemini-3.5-flash")
    monkeypatch.setenv("CHATBOT_FALLBACK_MODEL", "gemini-3-flash-preview")

    from backend.services.chatbot.llm_provider import create_chatbot_llm
    llm = create_chatbot_llm()
    assert llm is not None
    assert hasattr(llm, "invoke")


def test_create_chatbot_llm_gemini_only(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-gemini-key")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    from backend.services.chatbot.llm_provider import create_chatbot_llm
    llm = create_chatbot_llm()
    assert llm is not None


def test_create_chatbot_llm_openai_only(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "test-openai-key")

    from backend.services.chatbot.llm_provider import create_chatbot_llm
    llm = create_chatbot_llm()
    assert llm is not None


def test_create_chatbot_llm_no_keys_raises(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    from backend.services.chatbot.llm_provider import create_chatbot_llm
    with pytest.raises(RuntimeError, match="API"):
        create_chatbot_llm()


def test_get_chatbot_config_defaults(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "k")
    monkeypatch.setenv("OPENAI_API_KEY", "k")

    from backend.services.chatbot.llm_provider import get_chatbot_config
    config = get_chatbot_config()
    assert config["primary_model"] == "gpt-4.1-mini"
    assert config["secondary_model"] == "gemini-3.1-flash-lite"
    assert config["tertiary_model"] == "gemini-3.5-flash"
    assert config["fallback_model"] == "gemini-3-flash-preview"
    assert config["temperature"] == 0.3
    assert config["max_output_tokens"] >= 2048
    assert config["max_history_messages"] >= 50
    assert config["max_tool_rounds"] >= 5


def test_chat_model_logging_callback_handler(caplog):
    import logging
    from uuid import uuid4
    from backend.services.chatbot.llm_provider import ChatModelLoggingCallbackHandler

    handler = ChatModelLoggingCallbackHandler("test-model", "test-provider")
    run_id = uuid4()

    with caplog.at_level(logging.INFO):
        # 1. Start 호출 검증
        handler.on_llm_start(None, ["prompt"], run_id=run_id)
        assert "[LLM Call Start] Provider: test-provider, Model: test-model" in caplog.text

        # 2. End 호출 검증
        caplog.clear()
        handler.on_llm_end(None, run_id=run_id)
        assert "[LLM Call Success] Provider: test-provider, Model: test-model, Duration:" in caplog.text

        # 3. Error 호출 검증
        caplog.clear()
        handler.on_llm_start(None, ["prompt"], run_id=run_id)  # 재시작 시뮬레이션
        handler.on_llm_error(ValueError("mock error"), run_id=run_id)
        assert "[LLM Call Error] Provider: test-provider, Model: test-model" in caplog.text
        assert "Error: mock error" in caplog.text


def test_create_chatbot_llm_contains_logging_callbacks(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-gemini-key")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    from backend.services.chatbot.llm_provider import create_chatbot_llm, ChatModelLoggingCallbackHandler
    llm = create_chatbot_llm()
    assert llm is not None

    # 단일 모델로 반환되었거나 래퍼가 씌워져 있을 때 callbacks에 로깅 콜백이 등록되어 있는지 확인
    callbacks_attr = getattr(llm, "callbacks", None)
    if isinstance(callbacks_attr, list):
        handlers = callbacks_attr
    elif hasattr(callbacks_attr, "handlers"):
        handlers = callbacks_attr.handlers
    else:
        handlers = []

    has_logging_handler = any(isinstance(h, ChatModelLoggingCallbackHandler) for h in handlers)
    assert has_logging_handler, "Logging callback handler is not registered to the LLM model"

