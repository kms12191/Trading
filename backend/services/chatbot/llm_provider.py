"""Chatbot LLM provider with Gemini -> GPT failover chain."""
import os
import logging
import time
from uuid import UUID

from langchain_core.language_models import BaseChatModel
from langchain_core.callbacks import BaseCallbackHandler

logger = logging.getLogger(__name__)


class ChatModelLoggingCallbackHandler(BaseCallbackHandler):
    def __init__(self, model_name: str, provider: str):
        self.model_name = model_name
        self.provider = provider
        self.start_times = {}

    def on_llm_start(self, serialized, prompts, *, run_id: UUID, **kwargs):
        self.start_times[run_id] = time.time()
        logger.info(
            "[LLM Call Start] Provider: %s, Model: %s, RunID: %s",
            self.provider,
            self.model_name,
            run_id,
        )

    def on_llm_end(self, response, *, run_id: UUID, **kwargs):
        start_time = self.start_times.pop(run_id, None)
        duration = time.time() - start_time if start_time else 0.0
        logger.info(
            "[LLM Call Success] Provider: %s, Model: %s, Duration: %.2fs, RunID: %s",
            self.provider,
            self.model_name,
            duration,
            run_id,
        )

    def on_llm_error(self, error, *, run_id: UUID, **kwargs):
        start_time = self.start_times.pop(run_id, None)
        duration = time.time() - start_time if start_time else 0.0
        logger.error(
            "[LLM Call Error] Provider: %s, Model: %s, Duration: %.2fs, Error: %s, RunID: %s",
            self.provider,
            self.model_name,
            duration,
            str(error),
            run_id,
        )


def _read_int_env(name: str, default: int) -> int:
    try:
        value = int(os.getenv(name, default))
        return value if value > 0 else default
    except (TypeError, ValueError):
        return default


def get_chatbot_config() -> dict:
    """Return chatbot configuration from environment variables."""
    return {
        "gemini_api_key": os.getenv("GEMINI_API_KEY", "").strip(),
        "openai_api_key": os.getenv("OPENAI_API_KEY", "").strip(),
        "primary_model": os.getenv("CHATBOT_PRIMARY_MODEL", "gpt-4.1-mini").strip(),
        "secondary_model": os.getenv("CHATBOT_SECONDARY_MODEL", "gemini-3.1-flash-lite").strip(),
        "tertiary_model": os.getenv("CHATBOT_TERTIARY_MODEL", "gemini-3.5-flash").strip(),
        "fallback_model": os.getenv("CHATBOT_FALLBACK_MODEL", "gemini-3-flash-preview").strip(),
        "primary_provider": os.getenv("CHATBOT_PRIMARY_PROVIDER", "openai").strip().lower(),
        "secondary_provider": os.getenv("CHATBOT_SECONDARY_PROVIDER", "gemini").strip().lower(),
        "tertiary_provider": os.getenv("CHATBOT_TERTIARY_PROVIDER", "gemini").strip().lower(),
        "fallback_provider": os.getenv("CHATBOT_FALLBACK_PROVIDER", "gemini").strip().lower(),
        "temperature": float(os.getenv("CHATBOT_TEMPERATURE", "0.3")),
        "max_output_tokens": _read_int_env("CHATBOT_MAX_OUTPUT_TOKENS", 2048),
        "max_history_messages": _read_int_env("CHATBOT_MAX_HISTORY_MESSAGES", 50),
        "max_tool_rounds": _read_int_env("CHATBOT_MAX_TOOL_ROUNDS", 5),
        "max_input_chars": _read_int_env("CHATBOT_MAX_INPUT_CHARS", 50000),
        "daily_request_limit": _read_int_env("CHATBOT_DAILY_REQUEST_LIMIT", 500),
        "daily_token_limit": _read_int_env("CHATBOT_DAILY_TOKEN_LIMIT", 500000),
    }


def _create_model(provider: str, model_name: str, api_key: str, config: dict) -> BaseChatModel | None:
    """Create a single LLM instance for the given provider."""
    if not api_key:
        return None
    callbacks = [ChatModelLoggingCallbackHandler(model_name, provider)]
    if provider == "gemini":
        from langchain_google_genai import ChatGoogleGenerativeAI
        return ChatGoogleGenerativeAI(
            model=model_name,
            google_api_key=api_key,
            temperature=config["temperature"],
            max_output_tokens=config["max_output_tokens"],
            callbacks=callbacks,
        )
    if provider == "openai":
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(
            model=model_name,
            api_key=api_key,
            temperature=config["temperature"],
            max_tokens=config["max_output_tokens"],
            callbacks=callbacks,
        )
    return None


def create_chatbot_llm() -> BaseChatModel:
    """Create the chatbot LLM with Gemini -> GPT failover chain.

    Returns a BaseChatModel with .with_fallbacks() applied.
    Failover order: primary -> secondary -> fallback.
    """
    config = get_chatbot_config()
    models: list[BaseChatModel] = []

    for key_prefix in ("primary", "secondary", "tertiary", "fallback"):
        provider = config[f"{key_prefix}_provider"]
        model_name = config[f"{key_prefix}_model"]
        api_key = config["gemini_api_key"] if provider == "gemini" else config["openai_api_key"]
        model = _create_model(provider, model_name, api_key, config)
        if model is not None:
            models.append(model)

    if not models:
        raise RuntimeError(
            "챗봇 LLM을 생성할 수 없습니다. GEMINI_API_KEY 또는 OPENAI_API_KEY를 설정해 주세요."
        )

    primary = models[0]
    fallbacks = models[1:]
    if fallbacks:
        return primary.with_fallbacks(fallbacks)
    return primary
