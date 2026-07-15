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

FOLLOWUP_POINTER_KEYWORDS = (
    "\uc774 \ub274\uc2a4",
    "\uc774 \uae30\uc0ac",
    "\uc774 \uacf5\uc2dc",
    "\ubc29\uae08",
    "\uc774 \ub0b4\uc6a9",
    "\uc704 \ub0b4\uc6a9",
    "\uc774\uac70",
    "\uc774\uac78",
    "\uadf8\uac70",
    "\uadf8 \ub0b4\uc6a9",
    "\ubc29\uae08 \ubcf8",
)
FOLLOWUP_DECISION_KEYWORDS = (
    "\uc0ac\uc57c",
    "\uc0b4\uae4c",
    "\ub9e4\uc218",
    "\ud314\uc544",
    "\ub9e4\ub3c4",
    "\uc9c4\uc785",
    "\ub4e4\uc5b4\uac00",
    "\uc0ac\uc790",
    "\uc88b\uc544",
    "\uad1c\ucc2e",
    "\uc704\ud5d8",
    "\ub9ac\uc2a4\ud06c",
    "\uad1c\ucc2e\uc744\uae4c",
    "\uc88b\uc744\uae4c",
)


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
    has_pointer = any(keyword in value for keyword in FOLLOWUP_POINTER_KEYWORDS)
    has_decision = any(keyword in value for keyword in FOLLOWUP_DECISION_KEYWORDS)
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
    basis = title or subject or "\uc9c1\uc804 \ub274\uc2a4/\uacf5\uc2dc"
    context_source = str(data.get("source") or "MARKET_CONTEXT").upper()
    summary_line = (
        f"\ud575\uc2ec \ub0b4\uc6a9: {summary}"
        if summary
        else "\ud575\uc2ec \ub0b4\uc6a9: \uc9c1\uc804 \uc790\ub8cc\ub9cc\uc73c\ub85c\ub294 "
        "\uac00\uaca9 \ubc18\uc601 \uc5ec\ubd80\ub97c \ud655\uc815\ud558\uae30 \uc5b4\ub835\uc2b5\ub2c8\ub2e4."
    )
    reply = "\n".join(
        [
            "\uc798 \ubaa8\ub974\uaca0\uc2b5\ub2c8\ub2e4. \uc9c0\uae08 \ubc14\ub85c "
            "\ub9e4\uc218/\ub9e4\ub3c4 \uc5ec\ubd80\ub97c \uc774 \ub274\uc2a4/\uacf5\uc2dc\ub9cc\uc73c\ub85c "
            "\ub2e8\uc815\ud558\uba74 \uc704\ud5d8\ud569\ub2c8\ub2e4.",
            f"\uae30\uc900 \uc790\ub8cc: {basis}",
            summary_line,
            "",
            "\ud655\uc778\ud560 \uac83",
            "1. \uc774\ubbf8 \uc8fc\uac00\uc5d0 \ubc18\uc601\ub410\ub294\uc9c0: "
            "\ub2f9\uc77c \uc0c1\uc2b9\ub960, \uac70\ub798\ub7c9, \uc9c1\uc804 \uace0\uc810 "
            "\ub300\ube44 \uc704\uce58\ub97c \uba3c\uc800 \ubd10\uc57c \ud569\ub2c8\ub2e4.",
            "2. \uc2e4\uc801/\uacf5\uc2dc\ub85c \uc774\uc5b4\uc9c0\ub294\uc9c0: "
            "\ub2e8\uc21c \uae30\ub300\uac10\uc778\uc9c0, \ud68c\uc0ac \uc2e4\uc801\uc774\ub098 "
            "\uc218\uc8fc \uac19\uc740 \ud655\uc815 \uc7ac\ub8cc\uc778\uc9c0 \uad6c\ubd84\ud574\uc57c \ud569\ub2c8\ub2e4.",
            "3. \ub0b4 \uae30\uc900\uacfc \ub9de\ub294\uc9c0: \ubcf4\uc720 \ube44\uc911, "
            "\uc190\uc808\uc120, \ubd84\ud560 \uc9c4\uc785 \uac00\ub2a5 \uae08\uc561\uc744 "
            "\uc815\ud55c \ub4a4 \ud310\ub2e8\ud558\ub294 \uac8c \uc548\uc804\ud569\ub2c8\ub2e4.",
            "",
            "\uacb0\ub860: \ubc14\ub85c \ucd94\uaca9 \ub9e4\uc218\ubcf4\ub2e4\ub294 "
            "\uad00\uc2ec\uc885\ubaa9\uc73c\ub85c \ub450\uace0 \uac00\uaca9\u00b7\uac70\ub798\ub7c9\u00b7"
            "\uad00\ub828 \uacf5\uc2dc\ub97c \ud568\uaed8 \ud655\uc778\ud55c \ub4a4 "
            "\ubd84\ud560 \uc811\uadfc \uc5ec\ubd80\ub97c \ud310\ub2e8\ud558\uc138\uc694.",
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
