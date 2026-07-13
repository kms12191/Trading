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

ORDER_CREATION_PATTERNS = (
    "매매 제안",
    "매매요청",
    "매매 요청",
    "매수 제안",
    "매도 제안",
    "주문 만들어",
    "주문해",
    *ORDER_KEYWORDS,
)

ORDER_READ_PATTERNS = (
    "주문내역",
    "주문 내역",
    "미체결 주문",
    "열린 주문",
)

ORDER_STRATEGY_PATTERNS = (
    "전략",
    "타이밍",
    "비중",
    "시나리오",
    "리밸런싱",
)

DIRECT_ORDER_CREATION_PATTERNS = (
    "매매 제안",
    "매매요청",
    "매매 요청",
    "매수 제안",
    "매도 제안",
    "주문 만들어",
    "주문해",
    "사줘",
    "사자",
    "구매",
    "팔아줘",
    "팔자",
    "처분",
)

BUY_KEYWORDS = ("사줘", "사자", "매수", "구매", "담아")
SELL_KEYWORDS = ("팔아줘", "팔자", "매도", "처분", "정리")
BUY_DEFAULT_PATTERNS = ("매매요청", "매매 요청", "매매 제안")
COMMAND_WORDS = (
    *ORDER_CREATION_PATTERNS,
    "제안",
    "만들어줘",
    "만들어",
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
    "토스",
    "TOSS",
    "한국투자",
    "한투",
    "KIS",
    "코인원",
    "COINONE",
    "바이낸스",
    "BINANCE",
)

KRW_UNIT_MULTIPLIERS = {
    "원": 1.0,
    "천원": 1000.0,
    "만원": 10000.0,
    "만": 10000.0,
}


def parse_order_intent(message: str) -> ParsedOrderIntent:
    text = _normalize_krw_spacing(str(message or "").strip())
    if not text or any(pattern in text for pattern in ORDER_READ_PATTERNS):
        return ParsedOrderIntent(is_order_request=False)
    if (
        any(pattern in text for pattern in ORDER_STRATEGY_PATTERNS)
        and not any(pattern in text for pattern in DIRECT_ORDER_CREATION_PATTERNS)
    ):
        return ParsedOrderIntent(is_order_request=False)
    if not any(pattern in text for pattern in ORDER_CREATION_PATTERNS):
        return ParsedOrderIntent(is_order_request=False)

    side = _detect_side(text)
    quantity = _extract_quantity(text)
    price = _extract_price(text)
    symbol_query = _extract_symbol_query(text)
    amount_krw = _extract_amount_krw(text)
    sell_ratio = _extract_sell_ratio(text) if side == "SELL" else None
    order_type = "LIMIT" if price and price > 0 else "MARKET"

    return ParsedOrderIntent(
        is_order_request=True,
        side=side,
        symbol_query=symbol_query,
        quantity=quantity,
        amount_krw=amount_krw,
        price=price,
        order_type=order_type,
        broker_env=_detect_broker_env(text),
        sell_ratio=sell_ratio,
    )


def _normalize_krw_spacing(text: str) -> str:
    return re.sub(
        r"(\d+(?:\.\d+)?|[일한이삼사오육칠팔구십백천만]+)\s*(천|만)\s+원",
        r"\1\2원",
        text,
    )


def _detect_side(text: str) -> str | None:
    if any(keyword in text for keyword in SELL_KEYWORDS):
        return "SELL"
    if any(keyword in text for keyword in BUY_KEYWORDS):
        return "BUY"
    if any(keyword in text for keyword in BUY_DEFAULT_PATTERNS) and (
        _extract_quantity(text) is not None
        or _extract_price(text) is not None
        or _extract_amount_krw(text) is not None
    ):
        return "BUY"
    return None


def _detect_broker_env(text: str) -> str | None:
    upper_text = text.upper()
    if "모의" in text or "MOCK" in upper_text:
        return "MOCK"
    if "실거래" in text or "실전" in text or "REAL" in upper_text:
        return "REAL"
    return None


def _extract_symbol_query(text: str) -> str:
    if _looks_like_multi_symbol_choice(text):
        return ""
    cleaned = text
    cleaned = re.sub(r"\d+(?:\.\d+)?\s*(?:주|개|수량|원|만원|천원|만)", " ", cleaned)
    cleaned = re.sub(r"[일한이삼사오육칠팔구십백천만]+\s*(?:원|만원|천원|만)\s*(?:어치)?", " ", cleaned)
    for word in COMMAND_WORDS:
        cleaned = cleaned.replace(word, " ")
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    if not cleaned:
        return ""
    token = _strip_korean_particle(cleaned.split()[0].strip())
    if token in {"에", "에서", "로", "으로"}:
        return ""
    return token


def _looks_like_multi_symbol_choice(text: str) -> bool:
    return bool(re.search(r"\S+(?:랑|와|과|하고)\s+\S+\s*중", text))


def _strip_korean_particle(token: str) -> str:
    for suffix in ("으로", "로", "에게", "에는", "에서", "까지", "부터", "을", "를", "이", "가", "은", "는"):
        if token.endswith(suffix) and len(token) > len(suffix):
            return token[: -len(suffix)]
    return token


def _extract_quantity(text: str) -> float | None:
    match = re.search(r"(\d+(?:\.\d+)?)\s*(?:주|개|수량)", text)
    if not match:
        return None
    return _to_float(match.group(1))


def _extract_amount_krw(text: str) -> float | None:
    text = _remove_explicit_price_phrase(text)
    match = re.search(
        r"(\d+(?:\.\d+)?)\s*(만원|천원|원|만)(?!원?\s*에)\s*(?:어치)?",
        text,
    )
    if match:
        return _parse_krw_value(match.group(1), match.group(2))

    korean_match = re.search(
        r"([일한이삼사오육칠팔구십백천만]+)\s*(만원|천원|원|만)"
        r"(?!원?\s*에)\s*(?:어치)?",
        text,
    )
    if korean_match:
        return _parse_krw_value(korean_match.group(1), korean_match.group(2))
    return None


def _extract_price(text: str) -> float | None:
    explicit_match = re.search(r"(?:지정가|가격)\s*(\d[\d,]*(?:\.\d+)?)\s*(만원|천원|원|만)(?!\s*어치)", text)
    if explicit_match:
        return _parse_krw_value(explicit_match.group(1), explicit_match.group(2))

    explicit_korean_match = re.search(
        r"(?:지정가|가격)\s*([일한이삼사오육칠팔구십백천만]+)\s*(만원|천원|원|만)(?!\s*어치)",
        text,
    )
    if explicit_korean_match:
        return _parse_krw_value(explicit_korean_match.group(1), explicit_korean_match.group(2))

    match = re.search(r"(\d[\d,]*(?:\.\d+)?)\s*(만원|천원|원|만)\s*에", text)
    if match:
        return _parse_krw_value(match.group(1), match.group(2))

    reverse_limit_match = re.search(
        r"(\d[\d,]*(?:\.\d+)?)\s*(만원|천원|원|만)\s*(?:지정가|가격)",
        text,
    )
    if reverse_limit_match:
        return _parse_krw_value(reverse_limit_match.group(1), reverse_limit_match.group(2))

    korean_match = re.search(
        r"([일한이삼사오육칠팔구십백천만]+)\s*(만원|천원|원|만)\s*에",
        text,
    )
    if korean_match:
        return _parse_krw_value(korean_match.group(1), korean_match.group(2))
    return None


def _remove_explicit_price_phrase(text: str) -> str:
    text = re.sub(r"(?:지정가|가격)\s*\d[\d,]*(?:\.\d+)?\s*(?:만원|천원|원|만)(?!\s*어치)", " ", text)
    text = re.sub(
        r"(?:지정가|가격)\s*[일한이삼사오육칠팔구십백천만]+\s*(?:만원|천원|원|만)(?!\s*어치)",
        " ",
        text,
    )
    return re.sub(
        r"\d[\d,]*(?:\.\d+)?\s*(?:만원|천원|원|만)\s*(?:지정가|가격)",
        " ",
        text,
    )


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


def _parse_krw_value(value: str, unit: str) -> float | None:
    if re.fullmatch(r"\d[\d,]*(?:\.\d+)?", str(value)):
        parsed = _to_float(value)
    else:
        parsed = _parse_korean_amount(value)
    amount = parsed * KRW_UNIT_MULTIPLIERS.get(unit, 0)
    return amount if amount > 0 else None


def _to_float(value: str) -> float:
    return float(str(value).replace(",", ""))
