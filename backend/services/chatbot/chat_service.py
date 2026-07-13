import json
import logging
import re
from datetime import datetime
from typing import Callable
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from flask import current_app, has_app_context

from backend.services.chatbot.conversation_repository import ChatbotConversationRepository
from backend.services.chatbot.function_calling import FUNCTION_SCHEMAS
from backend.services.chatbot.llm_client import ChatbotLLMClient
from backend.services.chatbot.memory_service import ChatbotMemoryService
from backend.services.chatbot.prompt_registry import build_system_prompt
from backend.services.chatbot.rag_service import ChatbotRAGService
from backend.services.chatbot.tool_registry import (
    add_watchlist_item,
    create_trade_proposal_from_message,
    get_asset_outlook,
    get_asset_price,
    get_exchange_rate,
    get_holdings,
    get_home_market_rankings,
    get_portfolio_summary,
    list_available_tools,
    list_open_orders,
    run_chatbot_tool,
    search_trade_history,
    search_web,
)
from backend.services.chatbot.safety_guard import enforce_tool_safety
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
    if source in {"DISCLOSURE_DB", "NEWS_DB", "VECTOR_DB", "HOME_MARKET", "OPEN_ORDERS"}:
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
        if action == "trade_proposal_missing_env_and_price":
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
        if data.get("source") != "CHATBOT_ORDER_PARSER":
            return
        reason_to_action = {
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
            confirmation_text = str(text or "").strip()
            merged_message = (
                f"{original_message} {confirmation_text}"
                if confirmation_text
                else original_message
            )
            return create_trade_proposal_from_message(auth_header, merged_message)
        return None

    @staticmethod
    def _is_direct_disclosure_lookup(text: str) -> bool:
        value = str(text or "")
        return "공시" in value and any(
            keyword in value
            for keyword in ["보여줘", "조회", "알려줘", "요약", "찾아줘", "최신", "최근"]
        )

    def _tool_message_from_arguments(self, tool_name: str, arguments: dict, fallback_text: str) -> str:
        if tool_name in {"search_web", "add_watchlist_item", "get_asset_outlook"}:
            return str(arguments.get("query") or fallback_text)
        if tool_name == "search_trade_history":
            parts = ["거래내역"]
            if arguments.get("symbol"):
                parts.append(str(arguments["symbol"]))
            if arguments.get("min_amount"):
                parts.append(f"{arguments['min_amount']}원 이상")
            if arguments.get("limit"):
                parts.append(f"상위 {arguments['limit']}개")
            return " ".join(parts)
        if tool_name == "list_open_orders":
            parts = ["미체결 주문"]
            if arguments.get("symbol"):
                parts.append(str(arguments["symbol"]))
            if arguments.get("exchange"):
                parts.append(str(arguments["exchange"]))
            if arguments.get("broker_env"):
                parts.append(str(arguments["broker_env"]))
            if arguments.get("limit"):
                parts.append(f"{arguments['limit']}개")
            return " ".join(parts)
        if tool_name == "get_exchange_rate":
            base = str(arguments.get("base_currency") or "").strip()
            quote = str(arguments.get("quote_currency") or "KRW").strip()
            return f"{base}/{quote} 환율 알려줘".strip()
        if tool_name == "get_asset_price":
            query = str(arguments.get("query") or fallback_text).strip()
            exchange = str(arguments.get("exchange") or "").strip()
            broker_env = str(arguments.get("broker_env") or "").strip()
            return " ".join(part for part in [query, exchange, broker_env, "현재가 알려줘"] if part)
        if tool_name == "get_home_market_rankings":
            asset_type = str(arguments.get("asset_type") or "").upper()
            asset_text = "코인" if asset_type == "CRYPTO" else "국내주식" if asset_type == "STOCK" else ""
            ranking = arguments.get("ranking") or "상승률"
            limit = arguments.get("limit") or 5
            return f"{asset_text} {ranking} 순위 상위 {limit}개"
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
            "get_holdings": get_holdings,
            "search_trade_history": search_trade_history,
            "list_open_orders": list_open_orders,
            "get_exchange_rate": get_exchange_rate,
            "get_asset_price": get_asset_price,
            "get_asset_outlook": get_asset_outlook,
            "search_web": search_web,
        }
        tool_func = tool_map.get(tool_name)
        if not tool_func:
            return None

        tool_message = self._tool_message_from_arguments(tool_name, arguments, fallback_text)
        return tool_func(auth_header, tool_message)

    def reply(
        self,
        message: str,
        user_id: str | None = None,
        auth_header: str | None = None,
        user_timezone: str | None = None,
        trace_callback: TraceCallback | None = None,
        delta_callback: Callable[[str], None] | None = None,
    ) -> dict:
        text = str(message or "").strip()
        if not text:
            return {
                "reply": "궁금한 내용을 입력해 주세요. 예: 보유자산 요약해줘, XRP 시세 알려줘",
                "actions": [],
            }

        pending_peek = self._peek_pending_action(auth_header, user_id)
        trade_detail_pending_actions = {
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

        if self._is_direct_disclosure_lookup(text):
            self._emit_trace(trace_callback, "tool_routing", "도구 확인")
            tool_result = search_web(auth_header, text) if auth_header else None
            if tool_result:
                tool_data = tool_result.get("data")
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
        llm_arguments = {
            "system_prompt": self._build_prompt_for_user(
                auth_header,
                user_id,
                text,
                user_timezone,
                trace_callback,
            ),
            "user_message": text,
            "user_id": user_id,
            "auth_header": auth_header,
            "function_schemas": FUNCTION_SCHEMAS,
            "history": history,
        }
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
                self._record_exchange(auth_header, user_id, text, tool_result["reply"])
                return {
                    "reply": tool_result["reply"],
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
