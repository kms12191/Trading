from backend.services.chatbot.tool_symbol_model import (
    build_symbol_choice_response,
    extract_symbol_query,
    normalize_symbol_alias,
    normalize_symbol_result,
)


def test_extract_symbol_query_normalizes_alias_and_removes_command_words():
    assert extract_symbol_query("아마존 관심종목 추가") == "AMZN"
    assert extract_symbol_query("현대건설우 전망은?") == "000725"
    assert extract_symbol_query("삼성전기 관심종목 추가") == "삼성전기"


def test_normalize_symbol_alias_strips_usdt_training_suffix():
    assert normalize_symbol_alias("XRPUSDT") == "XRP"
    assert normalize_symbol_alias("AAPL") == "AAPL"


def test_normalize_symbol_result_fills_display_fields():
    result = normalize_symbol_result({"symbol": " aapl ", "name": "Apple", "market_country": "us"})

    assert result["symbol"] == "AAPL"
    assert result["display_name"] == "Apple"
    assert result["asset_type"] == "STOCK"
    assert result["market"] == "US"


def test_build_symbol_choice_response_contains_navigation_actions():
    result = build_symbol_choice_response(
        "현대건설",
        [
            {"symbol": "000720", "display_name": "현대건설", "asset_type": "STOCK", "market": "KR"},
            {"symbol": "000725", "display_name": "현대건설우", "asset_type": "STOCK", "market": "KR"},
        ],
    )

    assert result["data"]["source"] == "SYMBOL_DISAMBIGUATION"
    assert "어떤 종목을 말하나요?" in result["reply"]
    assert result["actions"][0] == {
        "type": "navigate",
        "label": "현대건설(000720) 조회",
        "to": "/asset/STOCK/000720",
    }
