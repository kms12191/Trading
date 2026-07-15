from backend.services.chatbot.order_parser import parse_order_intent


def build_order_form_redirect(message: str) -> dict | None:
    intent = parse_order_intent(message)
    if not intent.is_order_request:
        return None

    return {
        "reply": "주문은 상단의 매매 요청에서 직접 입력해 주세요.",
        "actions": [],
        "data": {"source": "ORDER_ENTRY_REQUIRED"},
    }
