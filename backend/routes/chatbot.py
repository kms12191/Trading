import json
import queue
import threading
from time import perf_counter
from uuid import uuid4

from flask import Blueprint, Response, current_app, jsonify, request, stream_with_context

from backend.services.auth_service import validate_access_token
from backend.services.chatbot.chat_service import ChatbotService
from backend.services.chatbot.qa_event_repository import ChatbotQAEventRepository
from backend.services.error_message_service import format_error_payload


chatbot_bp = Blueprint("chatbot", __name__)
chatbot_service = ChatbotService()
qa_event_repository = ChatbotQAEventRepository()


def _format_sse_event(event: str, payload: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"


def _chunk_reply_text(text: str, chunk_size: int = 80) -> list[str]:
    value = str(text or "")
    if not value:
        return [""]
    chunks = []
    start = 0
    while start < len(value):
        next_index = min(start + chunk_size, len(value))
        if next_index < len(value):
            newline_index = value.find("\n", start + 1, next_index + 20)
            if newline_index != -1:
                next_index = newline_index + 1
            else:
                sentence_candidates = [
                    value.find("다.", start + 1, next_index + 20),
                    value.find("요.", start + 1, next_index + 20),
                    value.find(". ", start + 1, next_index + 20),
                ]
                sentence_candidates = [index for index in sentence_candidates if index != -1]
                if sentence_candidates:
                    next_index = min(sentence_candidates) + 2
        chunks.append(value[start:next_index])
        start = next_index
    return chunks


def _resolve_qa_event_type(result: dict | None) -> str:
    meta = (result or {}).get("meta") if isinstance(result, dict) else {}
    if isinstance(meta, dict) and meta.get("tool_result"):
        return "TOOL_RESULT"
    if isinstance(meta, dict) and meta.get("tool_calls"):
        return "OPENAI_TOOL_CALL"
    return "CHATBOT_REPLY"


def _record_chatbot_qa_event(
    *,
    event_type: str,
    user_id: str,
    request_id: str,
    message: str,
    result: dict | None = None,
    error_payload: dict | None = None,
    latency_ms: int | None = None,
) -> None:
    result = result if isinstance(result, dict) else {}
    meta = dict(result.get("meta") or {})
    if latency_ms is not None:
        meta["latency_ms"] = latency_ms
    if isinstance(error_payload, dict):
        error = error_payload.get("error") if isinstance(error_payload.get("error"), dict) else {}
        meta.update({
            "source": "ROUTE_ERROR",
            "error_title": error.get("title") or error_payload.get("message"),
            "error_code": error.get("code"),
        })
    qa_event_repository.record_event(
        event_type=event_type,
        user_id=user_id,
        request_id=request_id,
        user_message=message,
        assistant_message=result.get("reply") or "",
        meta=meta,
    )


@chatbot_bp.route("/api/chatbot/message", methods=["POST"])
def send_chatbot_message():
    auth_header = request.headers.get("Authorization")
    try:
        user_id, _ = validate_access_token(auth_header)
    except Exception as error:
        return jsonify(format_error_payload(error, "챗봇 인증 실패")), 401

    try:
        data = request.json or {}
        request_id = uuid4().hex[:16]
        started_at = perf_counter()
        result = chatbot_service.reply(
            data.get("message"),
            user_id=user_id,
            auth_header=auth_header,
            user_timezone=data.get("timezone"),
            structured_order=data.get("structured_order"),
            request_id=request_id,
        )
        _record_chatbot_qa_event(
            event_type=_resolve_qa_event_type(result),
            user_id=user_id,
            request_id=request_id,
            message=data.get("message"),
            result=result,
            latency_ms=int((perf_counter() - started_at) * 1000),
        )
        return jsonify({"success": True, "data": result})
    except Exception as error:
        payload = format_error_payload(error, "챗봇 응답 생성 실패")
        try:
            _record_chatbot_qa_event(
                event_type="CHATBOT_ERROR",
                user_id=user_id,
                request_id=locals().get("request_id") or uuid4().hex[:16],
                message=(locals().get("data") or {}).get("message"),
                error_payload=payload,
                latency_ms=int((perf_counter() - locals().get("started_at", perf_counter())) * 1000),
            )
        except Exception:
            current_app.logger.exception("챗봇 QA 에러 이벤트 저장 실패")
        return jsonify(payload), 500


@chatbot_bp.route("/api/chatbot/stream", methods=["POST"])
def stream_chatbot_message():
    auth_header = request.headers.get("Authorization")
    try:
        user_id, _ = validate_access_token(auth_header)
    except Exception as error:
        return jsonify(format_error_payload(error, "챗봇 인증 실패")), 401

    data = request.json or {}
    app = current_app._get_current_object()
    request_id = uuid4().hex[:16]

    def generate():
        event_queue: queue.Queue[tuple[str, dict]] = queue.Queue()

        def publish_trace(step: dict) -> None:
            event_queue.put(("trace", step))

        def publish_delta(text: str) -> None:
            event_queue.put(("delta", {"text": text}))

        def run_reply() -> None:
            with app.app_context():
                try:
                    started_at = perf_counter()
                    reply_arguments = {
                        "user_id": user_id,
                        "auth_header": auth_header,
                        "user_timezone": data.get("timezone"),
                        "trace_callback": publish_trace,
                        "delta_callback": publish_delta,
                        "request_id": request_id,
                    }
                    if data.get("structured_order"):
                        reply_arguments["structured_order"] = data.get("structured_order")
                    result = chatbot_service.reply(data.get("message"), **reply_arguments)
                    _record_chatbot_qa_event(
                        event_type=_resolve_qa_event_type(result),
                        user_id=user_id,
                        request_id=request_id,
                        message=data.get("message"),
                        result=result,
                        latency_ms=int((perf_counter() - started_at) * 1000),
                    )
                    event_queue.put(("result", result))
                except Exception as error:
                    app.logger.exception(
                        "챗봇 스트림 생성 실패: request_id=%s user_id=%s",
                        request_id,
                        user_id,
                    )
                    payload = format_error_payload(error, "챗봇 스트림 생성 실패")
                    payload["meta"] = {"request_id": request_id}
                    try:
                        _record_chatbot_qa_event(
                            event_type="CHATBOT_ERROR",
                            user_id=user_id,
                            request_id=request_id,
                            message=data.get("message"),
                            error_payload=payload,
                        )
                    except Exception:
                        app.logger.exception("챗봇 스트림 QA 에러 이벤트 저장 실패")
                    event_queue.put(("error", payload))

        yield _format_sse_event("trace", {"kind": "request", "label": "요청 분석"})
        worker = threading.Thread(target=run_reply, daemon=True)
        worker.start()
        emitted_trace_keys = {("request", "요청 분석")}
        emitted_live_delta = False

        while True:
            event, payload = event_queue.get()
            if event == "trace":
                trace_key = (payload.get("kind"), payload.get("label"))
                if trace_key in emitted_trace_keys:
                    continue
                emitted_trace_keys.add(trace_key)
                yield _format_sse_event("trace", payload)
                continue

            if event == "delta":
                emitted_live_delta = True
                yield _format_sse_event("delta", payload)
                continue

            if event == "error":
                yield _format_sse_event("error", payload)
                break

            result = payload
            meta = {
                **(result.get("meta") or {}),
                "request_id": request_id,
            }
            for step in meta.get("trace_steps") or []:
                if isinstance(step, dict):
                    trace_key = (step.get("kind"), step.get("label"))
                    if trace_key not in emitted_trace_keys:
                        emitted_trace_keys.add(trace_key)
                        yield _format_sse_event("trace", step)
            yield _format_sse_event("trace", {"kind": "compose", "label": "답변 작성"})
            if not emitted_live_delta:
                for chunk in _chunk_reply_text(result.get("reply") or ""):
                    yield _format_sse_event("delta", {"text": chunk})
            yield _format_sse_event(
                "done",
                {
                    "reply": result.get("reply") or "",
                    "actions": result.get("actions") or [],
                    "meta": meta,
                },
            )
            break

        worker.join(timeout=0.1)

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
