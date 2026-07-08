import os
import time
from collections import defaultdict, deque

import requests


OPENAI_CHAT_COMPLETIONS_URL = "https://api.openai.com/v1/chat/completions"


class ChatbotLimitError(Exception):
    """챗봇 사용량 제한을 넘었을 때 발생하는 예외입니다."""


class ChatbotLLMClient:
    """OpenAI 챗봇 호출과 기본 사용량 제한을 담당합니다."""

    def __init__(self):
        self.api_key = os.getenv("OPENAI_API_KEY", "").strip()
        self.model = os.getenv("OPENAI_MODEL", "gpt-4.1-mini").strip()
        self.max_input_chars = self._read_int_env("CHATBOT_MAX_INPUT_CHARS", 2000)
        self.max_output_tokens = self._read_int_env("CHATBOT_MAX_OUTPUT_TOKENS", 1024)
        self.max_history_messages = self._read_int_env("CHATBOT_MAX_HISTORY_MESSAGES", 16)
        self.max_tool_calls = self._read_int_env("CHATBOT_MAX_TOOL_CALLS", 3)
        self.minute_request_limit = self._read_int_env("CHATBOT_MINUTE_REQUEST_LIMIT", 10)
        self.daily_token_limit = self._read_int_env("CHATBOT_DAILY_TOKEN_LIMIT", 50000)
        self.timeout_seconds = self._read_int_env("CHATBOT_OPENAI_TIMEOUT_SECONDS", 30)
        self._request_windows = defaultdict(deque)
        self._daily_usage = {}

    @staticmethod
    def _read_int_env(name: str, default: int) -> int:
        try:
            value = int(os.getenv(name, default))
            return value if value > 0 else default
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _estimate_tokens(text: str) -> int:
        return max(1, len(text or "") // 4)

    def _today_key(self) -> str:
        return time.strftime("%Y-%m-%d", time.localtime())

    def _rate_limit_key(self, user_id: str | None) -> str:
        return user_id or "anonymous"

    def _check_request_limit(self, user_id: str | None) -> None:
        key = self._rate_limit_key(user_id)
        now = time.time()
        window = self._request_windows[key]

        while window and now - window[0] > 60:
            window.popleft()

        if len(window) >= self.minute_request_limit:
            raise ChatbotLimitError("요청이 너무 많습니다. 잠시 후 다시 시도해주세요.")

        window.append(now)

    def _check_token_limit(self, user_id: str | None, estimated_tokens: int) -> None:
        key = (self._rate_limit_key(user_id), self._today_key())
        used_tokens = self._daily_usage.get(key, 0)

        if used_tokens + estimated_tokens > self.daily_token_limit:
            raise ChatbotLimitError("오늘 사용할 수 있는 챗봇 토큰 한도를 초과했습니다.")

    def _record_token_usage(self, user_id: str | None, used_tokens: int) -> None:
        key = (self._rate_limit_key(user_id), self._today_key())
        self._daily_usage[key] = self._daily_usage.get(key, 0) + max(0, used_tokens)

    def _to_openai_tools(self, function_schemas: list[dict] | None) -> list[dict]:
        tools = []
        for schema in (function_schemas or [])[: self.max_tool_calls]:
            tools.append({
                "type": "function",
                "function": schema,
            })
        return tools

    def generate_reply(
        self,
        *,
        system_prompt: str,
        user_message: str,
        user_id: str | None = None,
        function_schemas: list[dict] | None = None,
    ) -> dict:
        if not self.api_key:
            raise RuntimeError("OPENAI_API_KEY가 설정되어 있지 않습니다.")

        text = str(user_message or "").strip()
        if len(text) > self.max_input_chars:
            raise ChatbotLimitError(f"입력은 최대 {self.max_input_chars}자까지 가능합니다.")

        self._check_request_limit(user_id)
        estimated_tokens = (
            self._estimate_tokens(system_prompt)
            + self._estimate_tokens(text)
            + self.max_output_tokens
        )
        self._check_token_limit(user_id, estimated_tokens)

        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": text},
            ][-self.max_history_messages:],
            "temperature": 0.3,
            "max_tokens": self.max_output_tokens,
        }

        tools = self._to_openai_tools(function_schemas)
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"

        response = requests.post(
            OPENAI_CHAT_COMPLETIONS_URL,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=self.timeout_seconds,
        )

        if response.status_code >= 400:
            raise RuntimeError(f"OpenAI 챗봇 요청 실패: HTTP {response.status_code}")

        data = response.json()
        usage = data.get("usage") or {}
        used_tokens = int(usage.get("total_tokens") or estimated_tokens)
        self._record_token_usage(user_id, used_tokens)

        message = (data.get("choices") or [{}])[0].get("message") or {}
        content = (message.get("content") or "").strip()
        tool_calls = message.get("tool_calls") or []

        if not content and tool_calls:
            content = "필요한 기능 호출을 확인했습니다. 실제 기능 연결은 다음 단계에서 활성화할 수 있습니다."

        if not content:
            content = "응답을 만들지 못했습니다. 잠시 후 다시 시도해주세요."

        return {
            "reply": content,
            "usage": usage,
            "tool_calls": tool_calls[: self.max_tool_calls],
            "model": self.model,
        }
