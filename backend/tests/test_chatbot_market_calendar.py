from backend.services.chatbot import tool_registry


def test_calendar_request_detects_korean_market_from_constitution_day():
    text = "2026년 7월 17일 제헌절 국내장 열려?"

    assert tool_registry._is_calendar_request(text)
    assert tool_registry._detect_market_country_for_calendar(text) == "KR"
    assert tool_registry._detect_calendar_date(text) == "2026-07-17"


def test_calendar_request_detects_us_market_from_us_keywords():
    text = "2026년 7월 17일 미국장 정규 거래 가능해?"

    assert tool_registry._is_calendar_request(text)
    assert tool_registry._detect_market_country_for_calendar(text) == "US"
    assert tool_registry._detect_calendar_date(text) == "2026-07-17"
