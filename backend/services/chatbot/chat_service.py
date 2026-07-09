from collections import defaultdict, deque
from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from backend.services.chatbot.function_calling import FUNCTION_SCHEMAS
from backend.services.chatbot.llm_client import ChatbotLLMClient
from backend.services.chatbot.prompt_registry import build_system_prompt
from backend.services.chatbot.rag_service import ChatbotRAGService
from backend.services.chatbot.tool_registry import get_portfolio_summary, list_available_tools, run_chatbot_tool
from backend.services.supabase_client import safe_query_supabase


INVESTMENT_PROFILE_GUIDES = {
    "안정형": "원금 보전, 낮은 변동성, 손절 기준, 현금 비중과 분산 투자를 우선해서 설명합니다.",
    "안정추구형": "안정성을 우선하되 제한적인 수익 기회를 함께 검토하고, 과도한 집중 투자를 피하도록 설명합니다.",
    "위험중립형": "기대수익과 리스크의 균형, 분할 매수·매도, 포트폴리오 비중 조절을 함께 설명합니다.",
    "적극투자형": "성장성과 수익 기회를 검토하되 변동성, 손실 가능성, 익절·손절 시나리오를 함께 설명합니다.",
    "공격투자형": "높은 변동성과 손실 가능성을 명확히 경고하면서 성장성, 모멘텀, 손익 시나리오를 함께 설명합니다.",
}

CONFIRMATION_PHRASES = (
    "조회해도 돼",
    "조회해줘",
    "진행해",
    "진행해줘",
    "응",
    "그래",
    "좋아",
    "해줘",
    "시작해",
)

PENDING_ACTION_TTL_SECONDS = 300
CHAT_HISTORY_MAXLEN = 12
DEFAULT_CHATBOT_TIMEZONE = "Asia/Seoul"


def build_current_datetime_context(user_timezone: str | None = None) -> str:
    """챗봇이 상대 날짜를 추측하지 않도록 요청 시점의 시간 문맥을 만듭니다."""
    timezone_name = str(user_timezone or DEFAULT_CHATBOT_TIMEZONE).strip() or DEFAULT_CHATBOT_TIMEZONE
    try:
        timezone = ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError:
        timezone_name = DEFAULT_CHATBOT_TIMEZONE
        timezone = ZoneInfo(DEFAULT_CHATBOT_TIMEZONE)

    now = datetime.now(timezone)
    weekday = ["월요일", "화요일", "수요일", "목요일", "금요일", "토요일", "일요일"][now.weekday()]
    return "\n".join([
        "현재 날짜/시간 기준:",
        f"- 기준 시간대: {timezone_name}",
        f"- 오늘 날짜: {now:%Y년 %m월 %d일} {weekday}",
        f"- ISO 날짜: {now:%Y-%m-%d}",
        f"- 현재 시각: {now:%H:%M:%S}",
        "- 사용자가 오늘, 어제, 최근, 이번 주, 지난달 같은 상대 날짜를 말하면 반드시 위 날짜를 기준으로 해석합니다.",
        "- 날짜가 중요한 뉴스, 공시, 거래내역, 차트 요청은 가능한 경우 해석한 start_date와 end_date 범위를 도구 호출이나 답변에 반영합니다.",
        "- 답변에서도 필요하면 'YYYY-MM-DD 기준'처럼 해석한 날짜 기준을 표시합니다.",
    ])


def load_user_investment_profile_context(auth_header: str | None, user_id: str | None = None) -> str:
    """로그인 사용자의 투자성향을 시스템 프롬프트에 붙일 문맥으로 변환합니다."""
    if not auth_header or not user_id:
        return ""

    rows = safe_query_supabase(
        auth_header,
        "profiles",
        "GET",
        params={
            "id": f"eq.{user_id}",
            "select": "invest_type,invest_score",
            "limit": "1",
        },
    ) or []
    if not rows:
        return ""

    profile = rows[0] or {}
    invest_type = str(profile.get("invest_type") or "").strip()
    if not invest_type or invest_type == "미정":
        return ""

    score = profile.get("invest_score")
    guide = INVESTMENT_PROFILE_GUIDES.get(invest_type, "해당 투자성향에 맞춰 위험 설명과 제안 강도를 보수적으로 조절합니다.")
    score_text = f" / 점수: {score}" if score is not None else ""

    return "\n".join(
        [
            "로그인 사용자 투자성향 문맥:",
            f"- 투자성향: {invest_type}{score_text}",
            f"- 제안 기준: {guide}",
            "- 매매 제안 시 사용자의 투자성향에 맞지 않는 과도한 위험은 먼저 경고하고, 가능한 대안을 함께 제시합니다.",
        ]
    )


class ChatbotService:
    """AE trading chatbot first-pass service."""

    def __init__(self):
        self.system_prompt = build_system_prompt()
        self.llm_client = ChatbotLLMClient()
        self.rag_service = ChatbotRAGService()
        self._history_by_user = defaultdict(lambda: deque(maxlen=CHAT_HISTORY_MAXLEN))
        self._pending_actions = {}

    def _conversation_key(self, user_id: str | None) -> str:
        return user_id or "anonymous"

    def _get_recent_history(self, user_id: str | None) -> list[dict]:
        return list(self._history_by_user[self._conversation_key(user_id)])

    def _append_history(self, user_id: str | None, role: str, content: str) -> None:
        text = str(content or "").strip()
        if not text:
            return
        self._history_by_user[self._conversation_key(user_id)].append({
            "role": role,
            "content": text,
        })

    def _set_pending_action(self, user_id: str | None, action: str) -> None:
        import time

        self._pending_actions[self._conversation_key(user_id)] = {
            "action": action,
            "expires_at": time.time() + PENDING_ACTION_TTL_SECONDS,
        }

    def _pop_pending_action(self, user_id: str | None) -> str | None:
        import time

        key = self._conversation_key(user_id)
        pending = self._pending_actions.get(key)
        if not pending:
            return None
        if pending.get("expires_at", 0) < time.time():
            self._pending_actions.pop(key, None)
            return None
        self._pending_actions.pop(key, None)
        return pending.get("action")

    def _peek_pending_action(self, user_id: str | None) -> str | None:
        import time

        key = self._conversation_key(user_id)
        pending = self._pending_actions.get(key)
        if not pending:
            return None
        if pending.get("expires_at", 0) < time.time():
            self._pending_actions.pop(key, None)
            return None
        return pending.get("action")

    def _build_prompt_for_user(
        self,
        auth_header: str | None,
        user_id: str | None,
        user_message: str = "",
        user_timezone: str | None = None,
    ) -> str:
        prompt_parts = [
            self.system_prompt,
            build_current_datetime_context(user_timezone),
        ]
        profile_context = load_user_investment_profile_context(auth_header, user_id)
        if profile_context:
            prompt_parts.append(profile_context)

        rag_context, _ = self.rag_service.build_context(auth_header, user_id, user_message)
        if rag_context:
            prompt_parts.append(rag_context)

        return "\n\n".join(prompt_parts)

    def _is_confirmation(self, text: str) -> bool:
        normalized = str(text or "").replace(" ", "").strip()
        if not normalized:
            return False
        return any(phrase.replace(" ", "") in normalized for phrase in CONFIRMATION_PHRASES)

    def _maybe_set_pending_from_reply(self, user_id: str | None, user_text: str, assistant_reply: str) -> None:
        combined = f"{user_text}\n{assistant_reply}"
        is_trade_proposal_context = any(keyword in combined for keyword in ["매매 제안", "투자 제안", "종목 추천", "매수", "매도"])
        asks_portfolio_lookup = any(keyword in combined for keyword in ["포트폴리오 요약", "보유자산", "평가 자산", "주문 가능 현금"])
        asks_permission = any(keyword in assistant_reply for keyword in ["조회해도", "확인해도", "조회부터", "확인부터"])

        if is_trade_proposal_context and asks_portfolio_lookup and asks_permission:
            self._set_pending_action(user_id, "portfolio_summary")

    def _run_pending_action(self, action: str, auth_header: str | None, text: str) -> dict | None:
        if action == "portfolio_summary":
            return get_portfolio_summary(auth_header, text or "평가 자산 요약해줘")
        return None

    def reply(
        self,
        message: str,
        user_id: str | None = None,
        auth_header: str | None = None,
        user_timezone: str | None = None,
    ) -> dict:
        text = str(message or "").strip()
        if not text:
            return {
                "reply": "궁금한 내용을 입력해 주세요. 예: 내 보유자산 요약해줘, XRP 시세 알려줘",
                "actions": [],
            }

        if self._is_confirmation(text):
            pending_action = self._pop_pending_action(user_id)
            if pending_action:
                tool_result = self._run_pending_action(pending_action, auth_header, text)
                if tool_result:
                    self._append_history(user_id, "user", text)
                    self._append_history(user_id, "assistant", tool_result["reply"])
                    return {
                        "reply": tool_result["reply"],
                        "actions": [],
                        "meta": {
                            "user_id": user_id,
                            "available_tools": list_available_tools(),
                            "tool_result": tool_result.get("data"),
                            "pending_action": pending_action,
                            "source": "PROJECT_TOOL_PENDING",
                        },
                    }

        tool_result = run_chatbot_tool(auth_header, text)
        if tool_result:
            self._append_history(user_id, "user", text)
            self._append_history(user_id, "assistant", tool_result["reply"])
            return {
                "reply": tool_result["reply"],
                "actions": [],
                "meta": {
                    "user_id": user_id,
                    "available_tools": list_available_tools(),
                    "tool_result": tool_result.get("data"),
                    "source": "PROJECT_TOOL",
                },
            }

        result = self.llm_client.generate_reply(
            system_prompt=self._build_prompt_for_user(auth_header, user_id, text, user_timezone),
            user_message=text,
            user_id=user_id,
            function_schemas=FUNCTION_SCHEMAS,
            history=self._get_recent_history(user_id),
        )

        reply_text = result["reply"]
        self._append_history(user_id, "user", text)
        self._append_history(user_id, "assistant", reply_text)
        self._maybe_set_pending_from_reply(user_id, text, reply_text)

        return {
            "reply": reply_text,
            "actions": [],
            "meta": {
                "user_id": user_id,
                "available_tools": list_available_tools(),
                "function_schemas": FUNCTION_SCHEMAS,
                "model": result.get("model"),
                "usage": result.get("usage"),
                "tool_calls": result.get("tool_calls"),
                "pending_action": self._peek_pending_action(user_id),
            },
        }
