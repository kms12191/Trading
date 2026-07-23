import json
import logging
import os
import re
from datetime import datetime
from typing import Callable
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from flask import current_app, has_app_context

from backend.services.chatbot.conversation_repository import ChatbotConversationRepository
from backend.services.chatbot.function_calling import FUNCTION_SCHEMAS
from backend.services.chatbot.llm_client import ChatbotLLMClient
from backend.services.chatbot.market_context_followup import (
    MARKET_CONTEXT_ACTION,
    build_market_context_followup_result,
    build_market_context_payload,
    is_market_context_data,
    is_market_context_followup,
)
from backend.services.chatbot.memory_service import ChatbotMemoryService
from backend.services.chatbot.prompt_registry import build_system_prompt
from backend.services.chatbot.rag_service import ChatbotRAGService
from backend.services.chatbot.tool_registry import (
    add_watchlist_item,
    get_asset_candles,
    get_asset_krw_conversion,
    get_asset_orderbook,
    get_asset_outlook,
    get_asset_price,
    get_crypto_market_context,
    get_exchange_rate,
    get_holdings,
    get_home_market_rankings,
    get_market_calendar,
    get_portfolio_summary,
    list_available_tools,
    list_open_orders,
    remove_watchlist_item,
    run_chatbot_tool,
    search_trade_history,
    search_web,
    _is_asset_price_request,
)
from backend.services.chatbot.order_parser import parse_order_intent
from backend.services.chatbot.order_form_policy import build_order_form_redirect
from backend.services.chatbot.safety_guard import enforce_tool_safety
from backend.services.chatbot.user_context_lookup import (
    UserLookupContext,
    build_favorite_memory_result,
    build_user_note_result,
    is_favorite_memory_query,
    is_user_note_query,
    is_watchlist_focus_request,
)
from backend.services.knowledge_repository import KnowledgeRepository
from backend.services.supabase_client import safe_query_supabase


INVESTMENT_PROFILE_GUIDES = {
    "안정형": "원금 보전, 낮은 변동성, 손절 기준, 현금 비중과 분산 투자를 우선해서 설명합니다.",
    "안정추구형": "안정성을 우선하되 제한적인 수익 기회를 함께 검토하고 과도한 집중 투자를 피하도록 설명합니다.",
    "위험중립형": "기대수익과 리스크의 균형, 분할 매수/매도, 포트폴리오 비중 조절을 함께 설명합니다.",
    "적극투자형": "성장성과 수익 기회를 검토하되 변동성, 손실 가능성, 익절/손절 시나리오를 함께 설명합니다.",
    "공격투자형": "높은 변동성과 손실 가능성을 명확히 경고하면서 성장 모멘텀과 수익 시나리오를 함께 설명합니다.",
}

CONFIRMATION_PHRASES = (
    "조회해도 돼",
    "조회해줘",
    "진행해",
    "진행해줘",
    "응",
    "맞아",
    "맞습니다",
    "맞어",
    "네",
    "그래",
    "좋아",
    "해줘",
    "생성해줘",
    "해봐",
    "시작해",
    "해죠",
    "ㄱㄱ",
    "고고",
    "오키",
)

PENDING_ACTION_TTL_SECONDS = 300
CHAT_HISTORY_MAXLEN = 12
DEFAULT_CHATBOT_TIMEZONE = "Asia/Seoul"
TraceCallback = Callable[[dict], None]
logger = logging.getLogger(__name__)


def build_tool_trace_steps(tool_result_data: dict | None) -> list[dict]:
    data = tool_result_data if isinstance(tool_result_data, dict) else {}
    source = str(data.get("source") or "").upper()
    citations = data.get("citations") if isinstance(data.get("citations"), list) else []
    raw_order_payload = data.get("raw_order_payload") if isinstance(data.get("raw_order_payload"), dict) else {}
    steps = []
    seen = set()

    def add(kind: str, label: str) -> None:
        if kind in seen:
            return
        seen.add(kind)
        steps.append({"kind": kind, "label": label})

    if source in {"ML_ACTIVE_SIGNAL"}:
        add("ml", "ML 신호")
    if source in {"TAVILY", "TAVILY_FALLBACK", "TAVILY_API"}:
        add("tavily", "Tavily 웹검색")
    if source in {"DISCLOSURE_DB", "NEWS_DB", "VECTOR_DB", "HOME_MARKET", "OPEN_ORDERS", "MARKET_CALENDAR_DB", "MARKET_CALENDAR_TOSS"}:
        add("db", "Supabase DB 조회")
    if source in {"VECTOR_DB"} or citations:
        add("rag", "RAG 벡터검색")
    if any(str(row.get("source_type") or "").upper() == "DISCLOSURE" for row in citations if isinstance(row, dict)):
        add("disclosure", "DART 공시")
    if raw_order_payload.get("precheck") or raw_order_payload.get("precheck_status"):
        add("precheck", "주문 사전검증")

    return steps


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
        "- 사용자가 오늘, 어제, 최근, 이번 주, 지난달 같은 상대 날짜를 말하면 반드시 이 날짜를 기준으로 해석합니다.",
        "- 날짜가 중요한 뉴스, 공시, 거래내역, 차트 요청은 가능한 경우 해석한 start_date와 end_date 범위를 도구 호출이나 답변에 반영합니다.",
        "- 답변에서는 필요한 경우 'YYYY-MM-DD 기준'처럼 해석한 날짜 기준을 표시합니다.",
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
    guide = INVESTMENT_PROFILE_GUIDES.get(
        invest_type,
        "해당 투자성향에 맞춰 위험 설명과 제안 강도를 보수적으로 조절합니다.",
    )
    score_text = f" / 점수: {score}" if score is not None else ""

    return "\n".join(
        [
            "로그인 사용자 투자성향 문맥:",
            f"- 투자성향: {invest_type}{score_text}",
            f"- 제안 기준: {guide}",
            "- 매매 제안 때 사용자의 투자성향에 맞지 않는 과도한 위험은 먼저 경고하고, 가능한 대안을 함께 제시합니다.",
        ]
    )


class ChatbotService:
    """AE trading chatbot first-pass service."""

    def __init__(self):
        self.system_prompt = build_system_prompt()
        self.llm_client = ChatbotLLMClient()
        self.rag_service = ChatbotRAGService()
        self.knowledge_repository = KnowledgeRepository()
        self.memory_service = ChatbotMemoryService(self.knowledge_repository)
        self.conversation_repository = ChatbotConversationRepository()

        # LangGraph Agent 초기화
        from backend.services.chatbot.llm_provider import create_chatbot_llm, get_chatbot_config
        from backend.services.chatbot.agent import create_chatbot_agent

        self._chatbot_config = get_chatbot_config()
        try:
            self._llm = create_chatbot_llm()
            self.agent = create_chatbot_agent(self._llm)
        except Exception as error:
            logger.warning("LangGraph Agent 초기화 실패. 레거시 LLM 클라이언트를 사용합니다. error=%s", str(error))
            self._llm = None
            self.agent = None

    @staticmethod
    def _log_repository_failure(message: str) -> None:
        if has_app_context():
            current_app.logger.exception(message)
            return
        logger.exception(message)

    def _load_recent_history(
        self,
        auth_header: str | None,
        user_id: str | None,
    ) -> list[dict]:
        if not auth_header or not user_id:
            return []
        try:
            return self.conversation_repository.load_recent_history(
                auth_header,
                user_id,
                CHAT_HISTORY_MAXLEN,
            )
        except Exception:
            self._log_repository_failure("챗봇 대화 이력 조회에 실패했습니다.")
            return []

    def _record_exchange(
        self,
        auth_header: str | None,
        user_id: str | None,
        user_message: str,
        assistant_message: str,
    ) -> None:
        if not user_id:
            return

        if auth_header:
            try:
                self.conversation_repository.record_exchange(
                    auth_header,
                    user_id,
                    user_message,
                    assistant_message,
                )
            except Exception:
                self._log_repository_failure("챗봇 대화 저장에 실패했습니다.")
        try:
            self.memory_service.capture_from_exchange(
                auth_header=auth_header,
                user_id=user_id,
                user_message=user_message,
                assistant_message=assistant_message,
            )
        except Exception:
            pass

    def _set_pending_action(
        self,
        auth_header: str | None,
        user_id: str | None,
        action: str,
        payload: dict | None = None,
    ) -> None:
        if not auth_header or not user_id:
            return
        try:
            self.conversation_repository.set_pending_action(
                auth_header,
                user_id,
                action,
                payload=payload,
                ttl_seconds=PENDING_ACTION_TTL_SECONDS,
            )
        except Exception:
            self._log_repository_failure("챗봇 대기 작업 저장에 실패했습니다.")

    def _consume_pending_action(
        self,
        auth_header: str | None,
        user_id: str | None,
    ) -> tuple[str | None, dict]:
        if not auth_header or not user_id:
            return None, {}
        try:
            return self.conversation_repository.consume_pending_action(
                auth_header,
                user_id,
            )
        except Exception:
            self._log_repository_failure("챗봇 대기 작업 조회에 실패했습니다.")
            return None, {}

    def _peek_pending_action(
        self,
        auth_header: str | None,
        user_id: str | None,
    ) -> str | None:
        if not auth_header or not user_id:
            return None
        try:
            return self.conversation_repository.peek_pending_action(
                auth_header,
                user_id,
            )
        except Exception:
            self._log_repository_failure("챗봇 대기 작업 조회에 실패했습니다.")
            return None

    def _discard_trade_pending_action(
        self,
        auth_header: str | None,
        user_id: str | None,
    ) -> None:
        pending_action = self._peek_pending_action(auth_header, user_id)
        if str(pending_action or "").startswith("trade_proposal_missing_"):
            self._consume_pending_action(auth_header, user_id)

    @staticmethod
    def _is_simple_greeting(text: str) -> bool:
        normalized = str(text or "").replace(" ", "").replace("!", "").replace("~", "").replace("?", "").strip()
        return normalized in {
            "안녕", "안녕하세요", "안뇽", "반가워", "반갑습니다", "하이", "hi", "hello", "오하요", "니하오", "방가"
        }

    @staticmethod
    def _clean_json_reply(text: str) -> str:
        """만약 LLM이 오작동하여 [{'type': 'text', 'text': '...'}] 형태의 JSON 문자열을 생성했을 경우 자연어 텍스트만 추출합니다."""
        trimmed = str(text or "").strip()
        if trimmed.startswith("[") and trimmed.endswith("]"):
            try:
                import ast
                parsed = ast.literal_eval(trimmed)
                if isinstance(parsed, list) and len(parsed) > 0:
                    item = parsed[0]
                    if isinstance(item, dict) and "text" in item:
                        return str(item["text"]).strip()
            except Exception:
                pass
        return text

    def _build_prompt_for_user(
        self,
        auth_header: str | None,
        user_id: str | None,
        user_message: str = "",
        user_timezone: str | None = None,
        trace_callback: TraceCallback | None = None,
    ) -> str:
        prompt_parts = [
            self.system_prompt,
            build_current_datetime_context(user_timezone),
        ]
        profile_context = load_user_investment_profile_context(auth_header, user_id)
        if profile_context:
            prompt_parts.append(profile_context)

        memory_context = ""
        if auth_header and user_id:
            try:
                memory_context = self.knowledge_repository.list_chatbot_memory_context(auth_header, user_id)
            except Exception:
                memory_context = ""
        if memory_context:
            prompt_parts.append(memory_context)

        # 단순 인사말일 경우 RAG 참고자료 조회를 건너뛰어 불필요한 노이즈 유입을 방지합니다.
        if self._is_simple_greeting(user_message):
            return "\n\n".join(prompt_parts)

        self._emit_trace(trace_callback, "rag", "RAG 벡터검색")
        rag_context, _ = self.rag_service.build_context(auth_header, user_id, user_message)
        if rag_context:
            self._emit_trace(trace_callback, "rag_context", "RAG 참고자료 반영")
            prompt_parts.append(rag_context)

        return "\n\n".join(prompt_parts)

    @staticmethod
    def _emit_trace(trace_callback: TraceCallback | None, kind: str, label: str, **extra) -> None:
        if not trace_callback:
            return
        trace_callback({"kind": kind, "label": label, **extra})

    def _emit_tool_trace_steps(self, trace_callback: TraceCallback | None, tool_data: dict | None) -> list[dict]:
        steps = build_tool_trace_steps(tool_data)
        for step in steps:
            self._emit_trace(trace_callback, step.get("kind") or "tool", step.get("label") or "도구 처리")
        return steps

    def _is_confirmation(self, text: str) -> bool:
        normalized = str(text or "").replace(" ", "").strip()
        if not normalized:
            return False
        normalized_phrases = {phrase.replace(" ", "") for phrase in CONFIRMATION_PHRASES}
        if normalized in normalized_phrases:
            return True
        prefix_phrases = {
            phrase
            for phrase in normalized_phrases
            if len(phrase) >= 2 or phrase in {"응"}
        }
        return any(normalized.startswith(phrase) for phrase in prefix_phrases)

    def _build_missing_quantity_reply(
        self,
        auth_header: str | None,
        user_id: str | None,
    ) -> dict:
        return {
            "reply": "매매 제안을 만들 수량을 숫자로 알려주세요. 예: 1주, 1개",
            "actions": [],
            "meta": {
                "user_id": user_id,
                "available_tools": list_available_tools(),
                "pending_action": "trade_proposal_missing_quantity",
                "source": "PROJECT_TOOL_PENDING",
            },
        }

    def _build_missing_order_detail_reply(
        self,
        user_id: str | None,
        action: str,
    ) -> dict:
        if action == "trade_proposal_missing_intent":
            reply = "매매 제안을 만들 종목, 방향, 수량과 금액을 함께 알려주세요. 예: 도지코인 5개 코인원 지정가 100원 매매요청"
        elif action == "trade_proposal_missing_env_and_price":
            reply = "계좌 환경과 지정가 금액을 함께 알려주세요. 예: 실거래 지정가 3,500원"
        elif action == "trade_proposal_missing_env":
            reply = "계좌 환경을 알려주세요. 예: 실거래 또는 모의"
        elif action == "trade_proposal_missing_exchange":
            reply = "매매 제안을 만들 거래소를 알려주세요. 예: 토스, KIS, 코인원, 바이낸스"
        else:
            reply = "매매 제안에 사용할 지정가 금액을 알려주세요. 예: 지정가 3,500원"
        return {
            "reply": reply,
            "actions": [],
            "meta": {
                "user_id": user_id,
                "available_tools": list_available_tools(),
                "pending_action": action,
                "source": "PROJECT_TOOL_PENDING",
            },
        }

    @staticmethod
    def _has_trade_env(text: str) -> bool:
        upper_text = str(text or "").upper()
        return any(keyword in str(text or "") for keyword in ["실거래", "실전", "모의"]) or any(
            keyword in upper_text for keyword in ["REAL", "MOCK"]
        )

    @staticmethod
    def _has_exchange_text(text: str) -> bool:
        upper_text = str(text or "").upper()
        return any(keyword in str(text or "") for keyword in ["토스", "한국투자", "한투", "코인원", "바이낸스"]) or any(
            keyword in upper_text for keyword in ["TOSS", "KIS", "COINONE", "BINANCE"]
        )

    @staticmethod
    def _has_price_text(text: str) -> bool:
        return bool(re.search(r"(\d+(?:\.\d+)?|[일한이삼사오육칠팔구십백천만]+)\s*(만원|천원|원|만)", str(text or "")))

    def _normalize_price_completion(self, text: str) -> str:
        value = str(text or "").strip()
        if not value:
            return ""
        if "지정가" in value or "가격" in value or value.endswith("에"):
            return value
        if self._has_price_text(value):
            return f"지정가 {value}에"
        return value

    def _normalize_env_price_completion(self, text: str) -> str:
        value = str(text or "").strip()
        env = ""
        if any(keyword in value for keyword in ["실거래", "실전"]) or "REAL" in value.upper():
            env = "실거래"
        elif "모의" in value or "MOCK" in value.upper():
            env = "모의"
        price_text = re.sub(r"\b(?:REAL|MOCK)\b", " ", value, flags=re.IGNORECASE)
        price_text = re.sub(r"(실거래|실전|모의)", " ", price_text).strip()
        price_part = self._normalize_price_completion(price_text)
        return " ".join(part for part in [env, price_part] if part).strip()

    def _maybe_set_pending_from_reply(
        self,
        auth_header: str | None,
        user_id: str | None,
        user_text: str,
        assistant_reply: str,
    ) -> None:
        combined = f"{user_text}\n{assistant_reply}"
        is_trade_proposal_context = any(keyword in combined for keyword in ["매매 제안", "투자 제안", "종목 추천", "매수", "매도"])
        asks_portfolio_lookup = any(keyword in combined for keyword in ["포트폴리오 요약", "보유자산", "평가 자산", "주문 가능 현금"])
        asks_permission = any(keyword in assistant_reply for keyword in ["조회해도", "확인해도", "조회부터", "확인부터"])

        if is_trade_proposal_context and asks_portfolio_lookup and asks_permission:
            self._set_pending_action(auth_header, user_id, "portfolio_summary")

    def _maybe_set_pending_from_tool_result(
        self,
        auth_header: str | None,
        user_id: str | None,
        user_text: str,
        tool_data: dict | None,
    ) -> None:
        data = tool_data if isinstance(tool_data, dict) else {}
        if data.get("source") == "ASSET_PRICE" and data.get("symbol"):
            self._set_pending_action(
                auth_header,
                user_id,
                "last_asset_price_context",
                {
                    "symbol": data.get("symbol"),
                    "display_name": data.get("display_name"),
                    "asset_type": data.get("asset_type"),
                    "market": data.get("market"),
                    "exchange": data.get("exchange"),
                    "broker_env": data.get("broker_env"),
                    "current_price": data.get("current_price"),
                    "currency": data.get("currency"),
                    "message": user_text,
                },
            )
            return
        if is_market_context_data(data):
            self._set_pending_action(
                auth_header,
                user_id,
                MARKET_CONTEXT_ACTION,
                build_market_context_payload(user_text, data),
            )
            return
        if data.get("source") != "CHATBOT_ORDER_PARSER":
            return
        reason_to_action = {
            "missing_order_intent": "trade_proposal_missing_intent",
            "missing_quantity": "trade_proposal_missing_quantity",
            "missing_order_price": "trade_proposal_missing_price",
            "missing_order_env": "trade_proposal_missing_env",
            "missing_order_env_and_price": "trade_proposal_missing_env_and_price",
            "missing_exchange": "trade_proposal_missing_exchange",
        }
        action = reason_to_action.get(str(data.get("reason") or ""))
        if not action:
            return
        self._set_pending_action(
            auth_header,
            user_id,
            action,
            {"message": user_text},
        )

    def _run_pending_action(
        self,
        action: str,
        auth_header: str | None,
        text: str,
        payload: dict | None = None,
    ) -> dict | None:
        if action == "portfolio_summary":
            return get_portfolio_summary(auth_header, text or "평가 자산 요약해줘")
        if action == "trade_proposal_missing_intent":
            pending_payload = payload if isinstance(payload, dict) else {}
            original_message = str(pending_payload.get("message") or "").strip()
            merged_message = f"{original_message} {text}".strip() if original_message else str(text or "").strip()
            return run_chatbot_tool(auth_header, merged_message)
        if action == "trade_proposal_missing_quantity":
            pending_payload = payload if isinstance(payload, dict) else {}
            original_message = str(pending_payload.get("message") or "").strip()
            if not original_message:
                return None
            return run_chatbot_tool(auth_header, f"{original_message} {text}".strip())
        if action in {"trade_proposal_missing_price", "trade_proposal_missing_env", "trade_proposal_missing_env_and_price", "trade_proposal_missing_exchange"}:
            pending_payload = payload if isinstance(payload, dict) else {}
            original_message = str(pending_payload.get("message") or "").strip()
            if not original_message:
                return None
            if action == "trade_proposal_missing_price":
                completion = self._normalize_price_completion(text)
            elif action == "trade_proposal_missing_env_and_price":
                completion = self._normalize_env_price_completion(text)
            else:
                completion = str(text or "").strip()
            return run_chatbot_tool(auth_header, f"{original_message} {completion}".strip())
        if action == "trade_order_confirmation":
            pending_payload = payload if isinstance(payload, dict) else {}
            original_message = str(pending_payload.get("message") or "").strip()
            if not original_message:
                return {
                    "reply": "확인할 매매 요청 내용을 찾지 못했습니다. 종목, 수량, 매수/매도 방향을 다시 입력해 주세요.",
                    "data": {
                        "source": "CHATBOT_ORDER_CONFIRMATION",
                        "reason": "missing_pending_order_message",
                    },
                }
            return build_order_form_redirect(original_message)
        if action == "trade_proposal_retry":
            pending_payload = payload if isinstance(payload, dict) else {}
            original_message = str(pending_payload.get("message") or "").strip()
            if not original_message:
                return None
            confirmation_text = str(text or "").strip()
            if self._is_confirmation(confirmation_text) or any(k in confirmation_text for k in ["다시", "재시도", "진행"]):
                return build_order_form_redirect(original_message)
            return None
        if action == "last_asset_price_context":
            pending_payload = payload if isinstance(payload, dict) else {}
            symbol_name = str(pending_payload.get("display_name") or pending_payload.get("symbol") or "").strip()
            current_text = str(text or "").strip()
            if not symbol_name or not current_text:
                return None
            if any(keyword in current_text for keyword in ["환율 계산", "환율계산", "원화", "한화", "원으로", "원화로", "한화로", "원화 환산", "한화 환산"]):
                return get_asset_krw_conversion(auth_header, current_text, pending_payload)
            intent = parse_order_intent(current_text)
            if not intent.is_order_request or intent.symbol_query:
                return None
            return run_chatbot_tool(auth_header, f"{symbol_name} {current_text}".strip())
        return None

    @staticmethod
    def _is_direct_disclosure_lookup(text: str) -> bool:
        value = str(text or "")
        return "공시" in value and any(
            keyword in value
            for keyword in ["보여줘", "조회", "알려줘", "요약", "찾아줘", "최신", "최근"]
        )

    @staticmethod
    def _is_direct_content_lookup(text: str) -> bool:
        value = str(text or "").strip()
        content_terms = ("뉴스", "공시", "사업보고서", "반기보고서", "분기보고서", "전자공시", "DART")
        if not value or _is_asset_price_request(value) or not any(term in value for term in content_terms):
            return False

        action_terms = ("보여줘", "조회", "들려줘", "요약", "찾아줘", "최신", "최근")
        if any(term in value for term in action_terms):
            return True

        return any(value.split(term, 1)[0].strip() for term in content_terms if term in value)

    def _tool_message_from_arguments(self, tool_name: str, arguments: dict, fallback_text: str) -> str:
        if tool_name in {"search_web", "add_watchlist_item", "get_asset_outlook", "remove_watchlist_item"}:
            return str(arguments.get("query") or fallback_text)
        if tool_name == "get_crypto_market_context":
            query = str(arguments.get("query") or fallback_text).strip()
            return f"{query} 코인 분석해줘"
        if tool_name == "search_trade_history":
            parts = ["거래내역"]
            if arguments.get("symbol"):
                parts.append(str(arguments["symbol"]))
            return " ".join(parts)
        if tool_name == "list_open_orders":
            parts = ["미체결 주문"]
            if arguments.get("symbol"):
                parts.append(str(arguments["symbol"]))
            return " ".join(parts)
        if tool_name == "get_exchange_rate":
            base = str(arguments.get("base_currency") or "").strip()
            quote = str(arguments.get("quote_currency") or "KRW").strip()
            return f"{base}/{quote} 환율 알려줘".strip()
        if tool_name == "get_asset_krw_conversion":
            query = str(arguments.get("query") or fallback_text).strip()
            quantity = arguments.get("quantity")
            quantity_text = f"{quantity}주" if quantity else ""
            return " ".join(part for part in [query, quantity_text, "원화로 계산해줘"] if part)
        if tool_name == "get_market_calendar":
            date = str(arguments.get("date") or "").strip()
            market_country = str(arguments.get("market_country") or "").strip().upper()
            market_text = "한국장" if market_country == "KR" else "미국장" if market_country == "US" else ""
            return " ".join(part for part in [date, market_text, "장 운영 여부 알려줘"] if part)
        if tool_name == "get_asset_price":
            query = str(arguments.get("query") or fallback_text).strip()
            return f"{query} 현재가 알려줘"
        if tool_name == "get_asset_orderbook":
            query = str(arguments.get("query") or fallback_text).strip()
            return f"{query} 호가 알려줘"
        if tool_name == "get_asset_candles":
            query = str(arguments.get("query") or fallback_text).strip()
            return f"{query} 캔들 흐름 알려줘"
        if tool_name == "get_home_market_rankings":
            asset_type = str(arguments.get("asset_type") or "").upper()
            asset_text = "코인" if asset_type == "CRYPTO" else "국내주식" if asset_type == "STOCK" else ""
            ranking = arguments.get("ranking") or "상승률"
            return f"{asset_text} {ranking} 순위"
        return fallback_text

    def _run_llm_tool_call(self, auth_header: str | None, tool_call: dict, fallback_text: str) -> dict | None:
        if not auth_header:
            return None

        function_info = tool_call.get("function") or {}
        tool_name = function_info.get("name")
        raw_arguments = function_info.get("arguments") or "{}"
        try:
            arguments = json.loads(raw_arguments) if isinstance(raw_arguments, str) else dict(raw_arguments)
        except (TypeError, ValueError):
            arguments = {}

        enforce_tool_safety(tool_name, arguments)
        tool_map = {
            "get_home_market_rankings": get_home_market_rankings,
            "get_portfolio_summary": get_portfolio_summary,
            "add_watchlist_item": add_watchlist_item,
            "remove_watchlist_item": remove_watchlist_item,
            "get_holdings": get_holdings,
            "search_trade_history": search_trade_history,
            "list_open_orders": list_open_orders,
            "get_exchange_rate": get_exchange_rate,
            "get_asset_krw_conversion": get_asset_krw_conversion,
            "get_market_calendar": get_market_calendar,
            "get_asset_price": get_asset_price,
            "get_asset_orderbook": get_asset_orderbook,
            "get_asset_candles": get_asset_candles,
            "get_asset_outlook": get_asset_outlook,
            "get_crypto_market_context": get_crypto_market_context,
            "search_web": search_web,
        }
        tool_func = tool_map.get(tool_name)
        if not tool_func:
            return None

        tool_message = self._tool_message_from_arguments(tool_name, arguments, fallback_text)
        return tool_func(auth_header, tool_message, **arguments)

    def _synthesize_llm_tool_reply(
        self,
        system_prompt: str,
        user_message: str,
        tool_call: dict,
        tool_result: dict,
        user_id: str | None,
        auth_header: str | None,
        request_id: str | None = None,
    ) -> str:
        function_info = tool_call.get("function") or {}
        synthesis_arguments = {
            "system_prompt": system_prompt,
            "user_message": user_message,
            "tool_name": function_info.get("name"),
            "tool_reply": str(tool_result.get("reply") or ""),
            "tool_data": tool_result.get("data") if isinstance(tool_result.get("data"), dict) else None,
            "user_id": user_id,
            "auth_header": auth_header,
        }
        if request_id:
            synthesis_arguments["request_id"] = request_id
        synthesis = self.llm_client.synthesize_tool_result_reply(
            **synthesis_arguments,
        )
        synthesized_reply = str((synthesis or {}).get("reply") or "").strip()
        return synthesized_reply or str(tool_result.get("reply") or "")

    def _run_agent(
        self,
        text: str,
        user_id: str | None,
        auth_header: str | None,
        user_timezone: str | None = None,
        trace_callback: TraceCallback | None = None,
        delta_callback: Callable[[str], None] | None = None,
        request_id: str | None = None,
    ) -> dict:
        """Run LangGraph agent for the given user message."""
        from backend.services.chatbot.agent import run_agent, stream_agent

        self._emit_trace(trace_callback, "history", "대화 이력 확인")
        history = self._load_recent_history(auth_header, user_id)

        self._emit_trace(trace_callback, "llm", "LLM 답변 준비")
        system_prompt = self._build_prompt_for_user(
            auth_header, user_id, text, user_timezone, trace_callback,
        )

        agent_kwargs = {
            "system_prompt": system_prompt,
            "user_message": text,
            "history": history,
            "user_id": user_id or "",
            "auth_header": auth_header or "",
            "request_id": request_id or "",
        }

        if delta_callback:
            self._emit_trace(trace_callback, "agent", "Agent 스트리밍 실행")
            result = stream_agent(
                self.agent,
                **agent_kwargs,
                on_delta=delta_callback,
                on_trace=lambda step: self._emit_trace(
                    trace_callback, step.get("kind", "tool"), step.get("label", "도구 처리")
                ),
            )
        else:
            self._emit_trace(trace_callback, "agent", "Agent 실행")
            result = run_agent(self.agent, **agent_kwargs)

        # 토큰 사용량 로깅 추가
        meta = result.get("meta") or {}
        usage = meta.get("usage")
        model = meta.get("model")
        if usage:
            try:
                self.llm_client._record_actual_usage(
                    auth_header=auth_header,
                    user_id=user_id,
                    usage=usage,
                    request_type="agent_chat",
                    request_id=request_id,
                    model=model,
                )
            except Exception:
                logger.exception("LangGraph Agent 토큰 사용량 로깅 실패")

        reply_text = result.get("reply") or ""
        reply_text = self._clean_json_reply(reply_text)
        result["reply"] = reply_text
        self._record_exchange(auth_header, user_id, text, reply_text)

        return result

    def reply(
        self,
        message: str,
        user_id: str | None = None,
        auth_header: str | None = None,
        user_timezone: str | None = None,
        trace_callback: TraceCallback | None = None,
        delta_callback: Callable[[str], None] | None = None,
        request_id: str | None = None,
        structured_order: dict | None = None,
    ) -> dict:
        # 0. 구조화 주문(주문 폼 UI) 처리 분기
        if structured_order and isinstance(structured_order, dict) and structured_order.get("is_structured_order"):
            self._emit_trace(trace_callback, "pending_action", "구조화 주문 폼 분석")
            if structured_order.get("is_conditional"):
                return {
                    "reply": "조건감시는 기본 매매 요청에서 등록할 수 없습니다. 보유 자산의 조건감시 설정을 이용해 주세요.",
                    "actions": [],
                    "data": {"source": "ORDER_ENTRY", "reason": "conditional_order_not_supported"},
                }
            return self._create_proposal_from_structured(auth_header, user_id, structured_order)

        text = str(message or "").strip()
        if not text:
            return {
                "reply": "궁금한 내용을 입력해 주세요. 예: 보유자산 요약해줘, XRP 시세 알려줘",
                "actions": [],
            }

        order_form_redirect = build_order_form_redirect(text)
        if order_form_redirect:
            self._discard_trade_pending_action(auth_header, user_id)
            tool_data = order_form_redirect["data"]
            trace_steps = self._emit_tool_trace_steps(trace_callback, tool_data)
            self._record_exchange(auth_header, user_id, text, order_form_redirect["reply"])
            return {
                "reply": order_form_redirect["reply"],
                "actions": order_form_redirect["actions"],
                "meta": {
                    "user_id": user_id,
                    "available_tools": list_available_tools(),
                    "tool_result": tool_data,
                    "trace_steps": trace_steps,
                    "source": "ORDER_ENTRY_REQUIRED",
                },
            }

        pending_peek = self._peek_pending_action(auth_header, user_id)
        trade_detail_pending_actions = {
            "trade_proposal_missing_intent",
            "trade_proposal_missing_quantity",
            "trade_proposal_missing_price",
            "trade_proposal_missing_env",
            "trade_proposal_missing_env_and_price",
            "trade_proposal_missing_exchange",
        }
        if pending_peek in trade_detail_pending_actions:
            if self._is_confirmation(text):
                if pending_peek == "trade_proposal_missing_quantity":
                    return self._build_missing_quantity_reply(auth_header, user_id)
                return self._build_missing_order_detail_reply(user_id, pending_peek)
            if pending_peek == "trade_proposal_missing_exchange" and not self._has_exchange_text(text):
                return self._build_missing_order_detail_reply(user_id, pending_peek)
            if pending_peek == "trade_proposal_missing_env_and_price" and not self._has_trade_env(text):
                return self._build_missing_order_detail_reply(user_id, pending_peek)
            if pending_peek == "trade_proposal_missing_price" and not self._has_price_text(text):
                return self._build_missing_order_detail_reply(user_id, pending_peek)
            self._emit_trace(trace_callback, "pending_action", "대기 작업 확인")
            pending_action, pending_payload = self._consume_pending_action(
                auth_header,
                user_id,
            )
            if pending_action:
                self._emit_trace(trace_callback, "tool", "대기 작업 실행")
                tool_result = self._run_pending_action(pending_action, auth_header, text, pending_payload)
                if tool_result:
                    tool_data = tool_result.get("data")
                    trace_steps = self._emit_tool_trace_steps(trace_callback, tool_data)
                    self._record_exchange(auth_header, user_id, text, tool_result["reply"])
                    self._maybe_set_pending_from_tool_result(auth_header, user_id, f"{str(pending_payload.get('message') or '').strip()} {text}".strip(), tool_data)
                    return {
                        "reply": tool_result["reply"],
                        "actions": tool_result.get("actions") or [],
                        "meta": {
                            "user_id": user_id,
                            "available_tools": list_available_tools(),
                            "tool_result": tool_data,
                            "trace_steps": trace_steps,
                            "pending_action": pending_action,
                            "source": "PROJECT_TOOL_PENDING",
                        },
                    }

        if pending_peek == "last_asset_price_context":
            pending_action, pending_payload = self._consume_pending_action(
                auth_header,
                user_id,
            )
            if pending_action:
                tool_result = self._run_pending_action(pending_action, auth_header, text, pending_payload)
                if tool_result:
                    tool_data = tool_result.get("data")
                    trace_steps = self._emit_tool_trace_steps(trace_callback, tool_data)
                    self._record_exchange(auth_header, user_id, text, tool_result["reply"])
                    self._maybe_set_pending_from_tool_result(auth_header, user_id, text, tool_data)
                    return {
                        "reply": tool_result["reply"],
                        "actions": tool_result.get("actions") or [],
                        "meta": {
                            "user_id": user_id,
                            "available_tools": list_available_tools(),
                            "tool_result": tool_data,
                            "trace_steps": trace_steps,
                            "pending_action": pending_action,
                            "source": "PROJECT_TOOL_PENDING",
                        },
                    }

        if pending_peek == MARKET_CONTEXT_ACTION and is_market_context_followup(text):
            pending_action, pending_payload = self._consume_pending_action(
                auth_header,
                user_id,
            )
            if pending_action:
                tool_result = build_market_context_followup_result(pending_payload, text)
                if tool_result:
                    tool_data = tool_result.get("data")
                    trace_steps = self._emit_tool_trace_steps(trace_callback, tool_data)
                    self._record_exchange(auth_header, user_id, text, tool_result["reply"])
                    self._set_pending_action(
                        auth_header,
                        user_id,
                        MARKET_CONTEXT_ACTION,
                        pending_payload,
                    )
                    return {
                        "reply": tool_result["reply"],
                        "actions": tool_result.get("actions") or [],
                        "meta": {
                            "user_id": user_id,
                            "available_tools": list_available_tools(),
                            "tool_result": tool_data,
                            "trace_steps": trace_steps,
                            "pending_action": pending_action,
                            "source": "MARKET_CONTEXT_FOLLOWUP",
                        },
                    }

        if self._is_confirmation(text):
            self._emit_trace(trace_callback, "pending_action", "대기 작업 확인")
            pending_action, _pending_payload = self._consume_pending_action(
                auth_header,
                user_id,
            )
            if pending_action:
                self._emit_trace(trace_callback, "tool", "대기 작업 실행")
                tool_result = self._run_pending_action(pending_action, auth_header, text, _pending_payload)
                if tool_result:
                    tool_data = tool_result.get("data")
                    trace_steps = self._emit_tool_trace_steps(trace_callback, tool_data)
                    self._record_exchange(auth_header, user_id, text, tool_result["reply"])
                    self._maybe_set_pending_from_tool_result(auth_header, user_id, text, tool_data)
                    return {
                        "reply": tool_result["reply"],
                        "actions": tool_result.get("actions") or [],
                        "meta": {
                            "user_id": user_id,
                            "available_tools": list_available_tools(),
                            "tool_result": tool_data,
                            "trace_steps": trace_steps,
                            "pending_action": pending_action,
                            "source": "PROJECT_TOOL_PENDING",
                        },
                }

        if self._is_direct_content_lookup(text):
            self._emit_trace(trace_callback, "tool_routing", "content_lookup")
            tool_result = search_web(auth_header, text) if auth_header else None
            if tool_result:
                tool_data = tool_result.get("data")
                trace_steps = self._emit_tool_trace_steps(trace_callback, tool_data)
                self._record_exchange(auth_header, user_id, text, tool_result["reply"])
                self._maybe_set_pending_from_tool_result(auth_header, user_id, text, tool_data)
                return {
                    "reply": tool_result["reply"],
                    "actions": tool_result.get("actions") or [],
                    "meta": {
                        "user_id": user_id,
                        "available_tools": list_available_tools(),
                        "tool_result": tool_data,
                        "trace_steps": trace_steps,
                        "source": "PROJECT_TOOL_CONTENT_LOOKUP",
                    },
                }

        if self.agent is not None:
            return self._run_agent(
                text, user_id, auth_header, user_timezone,
                trace_callback, delta_callback, request_id,
            )

        user_lookup_context = UserLookupContext(
            auth_header=auth_header,
            user_id=user_id,
            text=text,
            knowledge_repository=self.knowledge_repository,
        )
        if is_user_note_query(text):
            self._emit_trace(trace_callback, "db", "투자노트 조회")
            tool_result = build_user_note_result(user_lookup_context)
            if tool_result:
                tool_data = tool_result.get("data")
                trace_steps = self._emit_tool_trace_steps(trace_callback, tool_data)
                self._record_exchange(auth_header, user_id, text, tool_result["reply"])
                self._maybe_set_pending_from_tool_result(auth_header, user_id, text, tool_data)
                return {
                    "reply": tool_result["reply"],
                    "actions": tool_result.get("actions") or [],
                    "meta": {
                        "user_id": user_id,
                        "available_tools": list_available_tools(),
                        "tool_result": tool_data,
                        "trace_steps": trace_steps,
                        "source": "USER_KNOWLEDGE_NOTES",
                    },
                }

        if is_favorite_memory_query(text) or is_watchlist_focus_request(text):
            self._emit_trace(trace_callback, "db", "자동메모리 조회")
            tool_result = build_favorite_memory_result(user_lookup_context)
            if tool_result:
                tool_data = tool_result.get("data")
                source = str(tool_data.get("source") or "USER_MEMORY_FACTS") if isinstance(tool_data, dict) else "USER_MEMORY_FACTS"
                trace_steps = self._emit_tool_trace_steps(trace_callback, tool_data)
                self._record_exchange(auth_header, user_id, text, tool_result["reply"])
                return {
                    "reply": tool_result["reply"],
                    "actions": tool_result.get("actions") or [],
                    "meta": {
                        "user_id": user_id,
                        "available_tools": list_available_tools(),
                        "tool_result": tool_data,
                        "trace_steps": trace_steps,
                        "source": source,
                    },
                }

        if self._is_direct_disclosure_lookup(text) and not _is_asset_price_request(text):
            self._emit_trace(trace_callback, "tool_routing", "도구 확인")
            tool_result = search_web(auth_header, text) if auth_header else None
            if tool_result:
                tool_data = tool_result.get("data")
                trace_steps = self._emit_tool_trace_steps(trace_callback, tool_data)
                self._record_exchange(auth_header, user_id, text, tool_result["reply"])
                self._maybe_set_pending_from_tool_result(auth_header, user_id, text, tool_data)
                return {
                    "reply": tool_result["reply"],
                    "actions": tool_result.get("actions") or [],
                    "meta": {
                        "user_id": user_id,
                        "available_tools": list_available_tools(),
                        "tool_result": tool_data,
                        "trace_steps": trace_steps,
                        "source": "PROJECT_TOOL_DISCLOSURE",
                    },
                }

        self._emit_trace(trace_callback, "tool_routing", "도구 확인")
        tool_result = run_chatbot_tool(auth_header, text)
        if tool_result:
            tool_data = tool_result.get("data")
            trace_steps = self._emit_tool_trace_steps(trace_callback, tool_data)
            self._record_exchange(auth_header, user_id, text, tool_result["reply"])
            self._maybe_set_pending_from_tool_result(auth_header, user_id, text, tool_data)
            return {
                "reply": tool_result["reply"],
                "actions": tool_result.get("actions") or [],
                "meta": {
                    "user_id": user_id,
                    "available_tools": list_available_tools(),
                    "tool_result": tool_data,
                    "trace_steps": trace_steps,
                    "source": "PROJECT_TOOL",
                },
            }

        self._emit_trace(trace_callback, "history", "대화 이력 확인")
        history = self._load_recent_history(auth_header, user_id)
        self._emit_trace(trace_callback, "llm", "LLM 답변 준비")
        system_prompt = self._build_prompt_for_user(
            auth_header,
            user_id,
            text,
            user_timezone,
            trace_callback,
        )
        llm_arguments = {
            "system_prompt": system_prompt,
            "user_message": text,
            "user_id": user_id,
            "auth_header": auth_header,
            "function_schemas": FUNCTION_SCHEMAS,
            "history": history,
        }
        if request_id:
            llm_arguments["request_id"] = request_id
        if delta_callback:
            result = self.llm_client.stream_reply(
                **llm_arguments,
                on_delta=delta_callback,
            )
        else:
            result = self.llm_client.generate_reply(**llm_arguments)

        for tool_call in result.get("tool_calls") or []:
            self._emit_trace(trace_callback, "openai_tool_call", "OpenAI 도구 호출")
            tool_result = self._run_llm_tool_call(auth_header, tool_call, text)
            if tool_result:
                tool_data = tool_result.get("data")
                trace_steps = self._emit_tool_trace_steps(trace_callback, tool_data)
                final_reply = str(tool_result.get("reply") or "")
                try:
                    final_reply = self._synthesize_llm_tool_reply(
                        system_prompt,
                        text,
                        tool_call,
                        tool_result,
                        user_id,
                        auth_header,
                        request_id,
                    )
                except Exception:
                    self._log_repository_failure("OpenAI 도구 결과 재합성에 실패했습니다.")
                self._record_exchange(auth_header, user_id, text, final_reply)
                self._maybe_set_pending_from_tool_result(auth_header, user_id, text, tool_data)
                return {
                    "reply": final_reply,
                    "actions": tool_result.get("actions") or [],
                    "meta": {
                        "user_id": user_id,
                        "available_tools": list_available_tools(),
                        "tool_result": tool_data,
                        "trace_steps": trace_steps,
                        "tool_call": tool_call,
                        "source": "OPENAI_TOOL_CALL",
                    },
                }

        reply_text = result["reply"]
        reply_text = self._clean_json_reply(reply_text)
        result["reply"] = reply_text
        self._record_exchange(auth_header, user_id, text, reply_text)
        self._maybe_set_pending_from_reply(auth_header, user_id, text, reply_text)

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
                "pending_action": self._peek_pending_action(auth_header, user_id),
            },
        }

    def _create_proposal_from_structured(self, auth_header: str, user_id: str, structured_order: dict) -> dict:
        from backend.services.chatbot.tool_registry import create_trade_proposal
        from backend.services.order_entry_service import normalize_order_request, verify_precheck_token

        try:
            order = normalize_order_request(structured_order)
        except ValueError as error:
            return {
                "reply": str(error),
                "actions": [],
                "data": {"source": "ORDER_ENTRY", "reason": "invalid_structured_order"},
            }

        precheck_token = str(structured_order.get("precheck_token") or "").strip()
        if not precheck_token:
            return {
                "reply": "사전검증 결과가 없습니다. 주문 조건을 다시 검증해 주세요.",
                "actions": [],
                "data": {"source": "ORDER_ENTRY", "reason": "precheck_required"},
            }

        signing_secret = current_app.config.get("SECRET_KEY") if has_app_context() else None
        signing_secret = os.getenv("ORDER_PRECHECK_SIGNING_SECRET") or signing_secret
        if not signing_secret:
            return {
                "reply": "사전검증 보안 설정을 확인할 수 없습니다. 관리자에게 문의해 주세요.",
                "actions": [],
                "data": {"source": "ORDER_ENTRY", "reason": "precheck_configuration_missing"},
            }

        try:
            verified = verify_precheck_token(
                precheck_token,
                user_id,
                order,
                str(signing_secret),
            )
        except ValueError as error:
            return {
                "reply": str(error),
                "actions": [],
                "data": {"source": "ORDER_ENTRY", "reason": "precheck_invalid"},
            }

        precheck = verified["precheck"]
        asset_type = "STOCK" if order["asset_type"] == "STOCK" else "CRYPTO"
        market_country = "US" if asset_type == "STOCK" and any(char.isalpha() for char in order["symbol"]) else "KR"
        currency = "USDT" if order["exchange"] in {"BINANCE", "BINANCE_UM_FUTURES"} else (
            "USD" if market_country == "US" else "KRW"
        )
        futures_options = precheck.get("futures_options") or {}
        return create_trade_proposal(auth_header, {
            "idempotency_key": order["idempotency_key"],
            "exchange": order["exchange"],
            "asset_type": asset_type,
            "symbol": order["symbol"],
            "side": futures_options.get("side") or order["side"],
            "order_type": order["order_type"],
            "broker_env": order["broker_env"],
            "quantity": order["quantity"],
            "price": order["price"],
            "market_country": market_country,
            "currency": currency,
            "position_side": futures_options.get("position_side"),
            "reduce_only": futures_options.get("reduce_only", False),
            "leverage": futures_options.get("leverage"),
            "margin_type": futures_options.get("margin_type"),
            "raw_order_payload": {
                "source": "ORDER_ENTRY",
                "precheck_status": "OK",
                "precheck": precheck,
                "order_hash": verified["order_hash"],
                "proposal_idempotency_key": order["idempotency_key"],
                "intent": order["intent"],
                "account_id": order["account_id"],
                "futures_options": futures_options,
            },
        })
