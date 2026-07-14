import logging
from typing import Any

from backend.services import supabase_client


logger = logging.getLogger(__name__)

MAX_MESSAGE_PREVIEW_LENGTH = 500


def _trim_text(value: Any, max_length: int = MAX_MESSAGE_PREVIEW_LENGTH) -> str:
    text = str(value or "").strip()
    if len(text) <= max_length:
        return text
    return f"{text[:max_length]}..."


def _extract_trace_kinds(trace_steps: Any) -> list[str]:
    if not isinstance(trace_steps, list):
        return []
    kinds = []
    seen = set()
    for step in trace_steps:
        if not isinstance(step, dict):
            continue
        kind = str(step.get("kind") or "").strip()
        if not kind or kind in seen:
            continue
        seen.add(kind)
        kinds.append(kind)
    return kinds


def _summarize_tool_result(tool_result: Any) -> dict:
    if not isinstance(tool_result, dict):
        return {}

    summary = {}
    for key in (
        "source",
        "reason",
        "symbol",
        "symbols",
        "asset_type",
        "exchange",
        "broker_env",
        "side",
        "status",
        "proposal_id",
    ):
        value = tool_result.get(key)
        if value not in (None, "", [], {}):
            summary[key if key != "source" else "tool_source"] = value

    items = tool_result.get("items")
    citations = tool_result.get("citations")
    actions = tool_result.get("actions")
    if isinstance(items, list):
        summary["item_count"] = len(items)
    if isinstance(citations, list):
        summary["citation_count"] = len(citations)
    if isinstance(actions, list):
        summary["action_count"] = len(actions)

    precheck_status = tool_result.get("precheck_status")
    if precheck_status:
        summary["precheck_status"] = precheck_status
    raw_order_payload = tool_result.get("raw_order_payload")
    if isinstance(raw_order_payload, dict):
        precheck = raw_order_payload.get("precheck")
        summary["has_precheck"] = bool(precheck)
        if raw_order_payload.get("precheck_status"):
            summary["precheck_status"] = raw_order_payload.get("precheck_status")

    return summary


def build_qa_event_payload(
    *,
    event_type: str,
    user_id: str,
    request_id: str | None = None,
    user_message: str | None = None,
    assistant_message: str | None = None,
    meta: dict | None = None,
) -> dict:
    meta = meta if isinstance(meta, dict) else {}
    tool_result = meta.get("tool_result")
    trace_steps = meta.get("trace_steps")
    usage = meta.get("usage") if isinstance(meta.get("usage"), dict) else {}

    event_payload = {
        "source": meta.get("source"),
        "pending_action": meta.get("pending_action"),
        "model": meta.get("model"),
        "latency_ms": meta.get("latency_ms"),
        "error_title": meta.get("error_title"),
        "error_code": meta.get("error_code"),
        "user_message_preview": _trim_text(user_message),
        "assistant_message_preview": _trim_text(assistant_message),
        "message_length": len(str(user_message or "")),
        "reply_length": len(str(assistant_message or "")),
        "trace_kinds": _extract_trace_kinds(trace_steps),
        "prompt_tokens": usage.get("prompt_tokens"),
        "completion_tokens": usage.get("completion_tokens"),
        "total_tokens": usage.get("total_tokens"),
    }
    event_payload.update(_summarize_tool_result(tool_result))
    event_payload = {key: value for key, value in event_payload.items() if value not in (None, "", [], {})}

    payload = {
        "user_id": user_id,
        "event_type": str(event_type or "CHATBOT_REPLY").strip().upper(),
        "event_payload": event_payload,
    }
    if request_id:
        payload["request_id"] = str(request_id)
    return payload


class ChatbotQAEventRepository:
    def record_event(
        self,
        *,
        event_type: str,
        user_id: str,
        request_id: str | None = None,
        user_message: str | None = None,
        assistant_message: str | None = None,
        meta: dict | None = None,
    ) -> None:
        payload = build_qa_event_payload(
            event_type=event_type,
            user_id=user_id,
            request_id=request_id,
            user_message=user_message,
            assistant_message=assistant_message,
            meta=meta,
        )
        result = supabase_client.safe_query_supabase_as_service_role(
            "chatbot_qa_events",
            "POST",
            json_data=payload,
        )
        if result is None:
            safe_user_id = str(user_id or "").replace("\r", "").replace("\n", "")[:128]
            logger.warning("챗봇 QA 이벤트 저장 실패: user_id=%s event_type=%s", safe_user_id, event_type)
