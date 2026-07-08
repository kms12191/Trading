from backend.services.chatbot.function_calling import FUNCTION_SCHEMAS
from backend.services.chatbot.llm_client import ChatbotLLMClient
from backend.services.chatbot.prompt_registry import build_system_prompt
from backend.services.chatbot.tool_registry import list_available_tools


class ChatbotService:
    """AE trading chatbot first-pass service."""

    def __init__(self):
        self.system_prompt = build_system_prompt()
        self.llm_client = ChatbotLLMClient()

    def reply(self, message: str, user_id: str | None = None) -> dict:
        text = str(message or "").strip()
        if not text:
            return {
                "reply": "궁금한 내용을 입력해 주세요. 예: 내 보유자산 요약해줘, XRP 시세 알려줘",
                "actions": [],
            }

        result = self.llm_client.generate_reply(
            system_prompt=self.system_prompt,
            user_message=text,
            user_id=user_id,
            function_schemas=FUNCTION_SCHEMAS,
        )

        return {
            "reply": result["reply"],
            "actions": [],
            "meta": {
                "user_id": user_id,
                "available_tools": list_available_tools(),
                "function_schemas": FUNCTION_SCHEMAS,
                "model": result.get("model"),
                "usage": result.get("usage"),
                "tool_calls": result.get("tool_calls"),
            },
        }
