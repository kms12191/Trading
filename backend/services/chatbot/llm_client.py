import os
from datetime import date

import requests

from backend.services.supabase_client import query_supabase


OPENAI_CHAT_COMPLETIONS_URL = "https://api.openai.com/v1/chat/completions"


class ChatbotLimitError(Exception):
    """챗봇 사용량 제한에 도달했을 때 발생하는 예외입니다."""


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

    def _consume_shared_usage(self, auth_header: str | None, user_id: str | None, estimated_tokens: int) -> None:
        if not auth_header or not user_id:
            raise ChatbotLimitError("로그인 사용자만 챗봇 사용량을 확인할 수 있습니다.")

        try:
            result = query_supabase(
                auth_header,
                "rpc/consume_chatbot_usage",
                "POST",
                json_data={
                    "p_user_id": user_id,
                    "p_usage_date": date.today().isoformat(),
                    "p_request_increment": 1,
                    "p_token_increment": estimated_tokens,
                    "p_request_limit": self.minute_request_limit,
                    "p_token_limit": self.daily_token_limit,
                },
            )
        except Exception as error:
            raise ChatbotLimitError("챗봇 사용량 제한 저장소를 확인하지 못했습니다. 잠시 후 다시 시도해 주세요.") from error

        row = result[0] if isinstance(result, list) and result else result
        if not isinstance(row, dict) or not row.get("allowed"):
            raise ChatbotLimitError("챗봇 사용량 제한에 도달했습니다. 잠시 후 다시 시도해 주세요.")

    def _to_openai_tools(self, function_schemas: list[dict] | None) -> list[dict]:
        tools = []
        for schema in (function_schemas or []):
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
        auth_header: str | None = None,
        function_schemas: list[dict] | None = None,
        history: list[dict] | None = None,
    ) -> dict:
        if not self.api_key:
            raise RuntimeError("OPENAI_API_KEY가 설정되어 있지 않습니다.")

        text = str(user_message or "").strip()
        if len(text) > self.max_input_chars:
            raise ChatbotLimitError(f"입력은 최대 {self.max_input_chars}자까지 가능합니다.")

        estimated_tokens = (
            self._estimate_tokens(system_prompt)
            + self._estimate_tokens(text)
            + self.max_output_tokens
        )
        self._consume_shared_usage(auth_header, user_id, estimated_tokens)

        history_messages = []
        for item in history or []:
            role = item.get("role")
            content = str(item.get("content") or "").strip()
            if role in {"user", "assistant"} and content:
                history_messages.append({"role": role, "content": content})

        messages = [
            {"role": "system", "content": system_prompt},
            *history_messages,
            {"role": "user", "content": text},
        ]

        if len(messages) > self.max_history_messages + 1:
            messages = [messages[0], *messages[-self.max_history_messages:]]

        payload = {
            "model": self.model,
            "messages": messages,
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
        message = (data.get("choices") or [{}])[0].get("message") or {}
        content = (message.get("content") or "").strip()
        tool_calls = message.get("tool_calls") or []

        if not content:
            content = "응답을 만들지 못했습니다. 잠시 후 다시 시도해 주세요."

        return {
            "reply": content,
            "usage": usage,
            "tool_calls": tool_calls[: self.max_tool_calls],
            "model": self.model,
        }
