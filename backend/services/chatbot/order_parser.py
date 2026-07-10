from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ParsedOrderIntent:
    is_order_request: bool
    side: str | None = None
    symbol_query: str = ""
    quantity: float | None = None
    amount_krw: float | None = None
    price: float | None = None
    order_type: str = "MARKET"
    broker_env: str | None = None
    sell_ratio: float | None = None


ORDER_KEYWORDS = (
    "사줘",
    "사자",
    "매수",
    "구매",
    "팔아줘",
    "팔자",
    "매도",
    "처분",
)

BUY_KEYWORDS = ("사줘", "사자", "매수", "구매", "담아")
SELL_KEYWORDS = ("팔아줘", "팔자", "매도", "처분", "정리")
COMMAND_WORDS = (
    *ORDER_KEYWORDS,
    "모의",
    "실거래",
    "실전",
    "시장가",
    "지정가",
    "어치",
    "원어치",
    "만원어치",
    "전량",
    "절반",
    "반",
    "반만",
)


def parse_order_intent(message: str) -> ParsedOrderIntent:
    text = str(message or "").strip()
    if not text or not any(keyword in text for keyword in ORDER_KEYWORDS):
        return ParsedOrderIntent(is_order_request=False)

    side = _detect_side(text)
    symbol_query = _extract_symbol_query(text)
    quantity = _extract_quantity(text)
    amount_krw = _extract_amount_krw(text)
    price = _extract_price(text)
    sell_ratio = _extract_sell_ratio(text) if side == "SELL" else None
    order_type = "LIMIT" if price and price > 0 else "MARKET"

    has_order_size = quantity is not None or amount_krw is not None or sell_ratio is not None
    return ParsedOrderIntent(
        is_order_request=bool(side and symbol_query and (has_order_size or _has_direct_order_phrase(text))),
        side=side,
        symbol_query=symbol_query,
        quantity=quantity,
        amount_krw=amount_krw,
        price=price,
        order_type=order_type,
        broker_env=_detect_broker_env(text),
        sell_ratio=sell_ratio,
    )


def _detect_side(text: str) -> str | None:
    if any(keyword in text for keyword in SELL_KEYWORDS):
        return "SELL"
    if any(keyword in text for keyword in BUY_KEYWORDS):
        return "BUY"
    return None


def _has_direct_order_phrase(text: str) -> bool:
    return any(
        keyword in text
        for keyword in (
            "사줘",
            "사자",
            "팔아줘",
            "팔자",
            "매수해",
            "매수해줘",
            "매도해",
            "매도해줘",
            "구매해",
            "구매해줘",
        )
    )


def _detect_broker_env(text: str) -> str | None:
    upper_text = text.upper()
    if "모의" in text or "MOCK" in upper_text:
        return "MOCK"
    if "실거래" in text or "실전" in text or "REAL" in upper_text:
        return "REAL"
    return None


def _extract_symbol_query(text: str) -> str:
    cleaned = text
    cleaned = re.sub(r"\d+(?:\.\d+)?\s*(?:주|개|수량|원|만원|천원|만)", " ", cleaned)
    cleaned = re.sub(r"[일한이삼사오육칠팔구십백천만]+\s*(?:원|만원|천원|만)\s*(?:어치)?", " ", cleaned)
    for word in COMMAND_WORDS:
        cleaned = cleaned.replace(word, " ")
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    if not cleaned:
        return ""
    return cleaned.split()[0].strip()


def _extract_quantity(text: str) -> float | None:
    match = re.search(r"(\d+(?:\.\d+)?)\s*(?:주|개|수량)", text)
    if not match:
        return None
    return _to_float(match.group(1))


def _extract_amount_krw(text: str) -> float | None:
    match = re.search(r"(\d+(?:\.\d+)?)\s*(만원|천원|원|만)\s*(?:어치)?", text)
    if match:
        amount = _to_float(match.group(1))
        unit = match.group(2)
        if unit in {"만원", "만"}:
            return amount * 10000
        if unit == "천원":
            return amount * 1000
        return amount

    korean_match = re.search(r"([일한이삼사오육칠팔구십백천만]+)\s*(원|만원|천원|만)\s*(?:어치)?", text)
    if korean_match:
        parsed = _parse_korean_amount(korean_match.group(1))
        return parsed if parsed > 0 else None
    return None


def _extract_price(text: str) -> float | None:
    match = re.search(r"(\d+(?:\.\d+)?)\s*원\s*에", text)
    if not match:
        return None
    return _to_float(match.group(1))


def _extract_sell_ratio(text: str) -> float | None:
    if any(keyword in text for keyword in ["전량", "전부", "전체", "다 팔"]):
        return 1.0
    if any(keyword in text for keyword in ["절반", "반만", "반 팔"]):
        return 0.5
    percent_match = re.search(r"(\d+(?:\.\d+)?)\s*%", text)
    if percent_match:
        return min(max(_to_float(percent_match.group(1)) / 100, 0), 1)
    return None


def _parse_korean_amount(value: str) -> float:
    digits = {
        "일": 1,
        "한": 1,
        "이": 2,
        "삼": 3,
        "사": 4,
        "오": 5,
        "육": 6,
        "칠": 7,
        "팔": 8,
        "구": 9,
    }
    units = {"십": 10, "백": 100, "천": 1000}
    normalized = str(value or "").strip()
    if not normalized:
        return 0.0

    def parse_section(section: str) -> int:
        total = 0
        current = 0
        for char in section:
            if char in digits:
                current = digits[char]
            elif char in units:
                total += (current or 1) * units[char]
                current = 0
        return total + current

    if "만" in normalized:
        left, right = normalized.split("만", 1)
        return float((parse_section(left) or 1) * 10000 + parse_section(right))
    return float(parse_section(normalized))


def _to_float(value: str) -> float:
    return float(str(value).replace(",", ""))
