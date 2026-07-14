from typing import Any


MARKET_CONTEXT_ACTION = "last_market_context"
MARKET_CONTEXT_SOURCES = {
    "NAVER_API",
    "FINNHUB",
    "TAVILY",
    "TAVILY_API",
    "TAVILY_FALLBACK",
    "NEWS_DB",
    "DISCLOSURE_DB",
    "VECTOR_DB",
    "NEWS_DISCLOSURE_COMBINED",
}


def is_market_context_data(tool_data: dict | None) -> bool:
    data = tool_data if isinstance(tool_data, dict) else {}
    source = str(data.get("source") or "").upper()
    if source in MARKET_CONTEXT_SOURCES:
        return True
    return any(isinstance(data.get(key), dict) for key in ["news", "disclosure"])


def is_market_context_followup(text: str) -> bool:
    value = str(text or "").strip()
    if not value:
        return False
    has_pointer = any(keyword in value for keyword in ["이 뉴스", "이 기사", "이 공시", "방금", "위 내용", "이 내용"])
    has_decision = any(
        keyword in value
        for keyword in [
            "사야",
            "살까",
            "매수",
            "팔아",
            "매도",
            "진입",
            "들어가",
            "투자",
            "좋아",
            "괜찮",
        ]
    )
    return has_pointer and has_decision


def build_market_context_payload(user_text: str, tool_data: dict | None) -> dict:
    data = tool_data if isinstance(tool_data, dict) else {}
    return {
        "message": str(user_text or "").strip(),
        "tool_data": data,
    }


def build_market_context_followup_result(payload: dict | None, text: str) -> dict | None:
    context = payload if isinstance(payload, dict) else {}
    tool_data = context.get("tool_data")
    data = tool_data if isinstance(tool_data, dict) else {}
    if not data:
        return None

    title = _primary_title(data)
    summary = _primary_summary(data)
    subject = _primary_subject(data)
    basis = title or subject or "직전 뉴스/공시"
    context_source = str(data.get("source") or "MARKET_CONTEXT").upper()
    summary_line = f"핵심 내용: {summary}" if summary else "핵심 내용: 직전 자료만으로는 가격 반영 여부를 확정하기 어렵습니다."
    reply = "\n".join(
        [
            "잘 모르겠습니다. 지금 바로 매수/매도 여부를 이 뉴스만으로 단정하면 위험합니다.",
            f"기준 자료: {basis}",
            summary_line,
            "",
            "확인할 것:",
            "1. 이미 주가에 반영됐는지: 당일 상승률, 거래량, 장중 고점 대비 위치를 먼저 봐야 합니다.",
            "2. 실적/공시로 이어지는지: 단순 지수 동반 상승인지, 회사 실적이나 수주 같은 확정 재료인지 구분해야 합니다.",
            "3. 내 기준과 맞는지: 보유 비중, 손절선, 분할 진입 가능 금액을 정한 뒤 판단하는 게 안전합니다.",
            "",
            "결론: 바로 추격 매수보다는 관심종목으로 두고 가격·거래량·관련 공시를 함께 확인한 뒤 분할 접근 여부를 판단하세요.",
        ]
    )
    return {
        "reply": reply,
        "actions": [],
        "data": {
            "source": "MARKET_CONTEXT_FOLLOWUP",
            "context_source": context_source,
            "context_basis": basis,
            "followup_question": str(text or "").strip(),
            "original_context": data,
        },
    }


def _primary_title(data: dict[str, Any]) -> str:
    item = _primary_item(data)
    return str(item.get("title") or item.get("report_nm") or item.get("headline") or "").strip()


def _primary_summary(data: dict[str, Any]) -> str:
    item = _primary_item(data)
    return str(
        item.get("summary")
        or item.get("ai_summary")
        or item.get("plain_summary")
        or item.get("description")
        or ""
    ).strip()


def _primary_subject(data: dict[str, Any]) -> str:
    item = _primary_item(data)
    keywords = item.get("related_keywords")
    if isinstance(keywords, list) and keywords:
        return str(keywords[0] or "").strip()
    return str(item.get("corp_name") or item.get("symbol") or "").strip()


def _primary_item(data: dict[str, Any]) -> dict[str, Any]:
    items = data.get("items")
    if isinstance(items, list) and items and isinstance(items[0], dict):
        return items[0]
    for key in ["news", "disclosure"]:
        nested = data.get(key)
        if isinstance(nested, dict):
            nested_items = nested.get("items")
            if isinstance(nested_items, list) and nested_items and isinstance(nested_items[0], dict):
                return nested_items[0]
    return data
