from backend.services.chatbot import tool_registry


def test_search_trade_history_displays_crypto_name_instead_of_symbol(monkeypatch):
    monkeypatch.setattr(tool_registry, "get_user_id_from_header", lambda auth_header: ("user-1", "token"))

    def fake_safe_query_supabase(auth_header, endpoint, method="GET", json_data=None, params=None):
        if endpoint == "trade_proposals":
            return [
                {
                    "created_at": "2026-07-02T10:00:00Z",
                    "exchange": "COINONE",
                    "symbol": "DOGE",
                    "side": "BUY",
                    "status": "CANCELED",
                    "order_amount": 11440,
                }
            ]
        return []

    monkeypatch.setattr(tool_registry, "safe_query_supabase", fake_safe_query_supabase)

    result = tool_registry.search_trade_history("Bearer test", "거래내역 보여줘")

    assert "도지코인" in result["reply"]
    assert "/ DOGE /" not in result["reply"]


def test_match_min_amount_treats_bare_manwon_as_ten_thousand_won():
    assert tool_registry._match_min_amount("만원이상 거래내역 보여줘") == 10000
    assert tool_registry._match_min_amount("만원 이상 거래내역 보여줘") == 10000
    assert tool_registry._match_min_amount("1만원 이상 거래내역 보여줘") == 10000
    assert tool_registry._match_min_amount("30만원 이상 거래내역 보여줘") == 300000


def test_match_min_amount_parses_korean_number_amounts():
    assert tool_registry._match_min_amount("오천원이상 거래내역 보여줘") == 5000
    assert tool_registry._match_min_amount("오천 원 이상 거래내역 보여줘") == 5000
    assert tool_registry._match_min_amount("오만원 이상 거래내역 보여줘") == 50000
    assert tool_registry._match_min_amount("삼십만원 이상 거래내역 보여줘") == 300000


def test_extract_symbol_query_keeps_stock_names_and_ignores_amount_only_queries():
    assert tool_registry._extract_symbol_query("테슬라 거래내역 보여줘") == "테슬라"
    assert tool_registry._extract_symbol_query("삼성전자 거래내역 보여줘") == "삼성전자"
    assert tool_registry._extract_symbol_query("오천원이상 거래내역 보여줘") == ""
    assert tool_registry._extract_symbol_query("만원이상 거래내역 보여줘") == ""
    assert tool_registry._extract_symbol_query("30만원 이상 거래내역 보여줘") == ""


def test_search_trade_history_filters_by_symbol_name(monkeypatch):
    captured_params = {}
    monkeypatch.setattr(tool_registry, "get_user_id_from_header", lambda auth_header: ("user-1", "token"))
    monkeypatch.setattr(tool_registry, "_resolve_symbol", lambda auth_header, query: {"symbol": "TSLA"})

    def fake_safe_query_supabase(auth_header, endpoint, method="GET", json_data=None, params=None):
        if endpoint == "trade_proposals":
            captured_params.update(params or {})
        return []

    monkeypatch.setattr(tool_registry, "safe_query_supabase", fake_safe_query_supabase)

    tool_registry.search_trade_history("Bearer test", "테슬라 거래내역 보여줘")

    assert captured_params["symbol"] == "eq.TSLA"


def test_strategy_request_with_holdings_keyword_does_not_route_to_holdings_tool():
    result = tool_registry.run_chatbot_tool(
        "Bearer test",
        "현재 관심 종목이나 보유 종목을 기준으로 구체적인 매수 타이밍과 비중 조절 전략도 함께 제안해줘",
    )

    assert result is None


def test_exchange_rate_routes_currency_pair_to_internal_api(monkeypatch):
    captured = {}

    def fake_get_internal(path, auth_header, params=None):
        captured["path"] = path
        captured["params"] = params
        return {
            "data": {
                "base_currency": "JPY",
                "quote_currency": "KRW",
                "rate": 9.1234,
                "source": "TOSS",
                "captured_at": "2026-07-09T03:00:00Z",
            }
        }

    monkeypatch.setattr(tool_registry, "_get_internal", fake_get_internal)

    result = tool_registry.run_chatbot_tool("Bearer test", "엔화 환율 알려줘")

    assert captured["path"] == "/api/market/exchange-rate"
    assert captured["params"]["base"] == "JPY"
    assert captured["params"]["quote"] == "KRW"
    assert "JPY/KRW" in result["reply"]
    assert "2026-07-09 기준\nJPY/KRW 환율은 1 JPY = 9.12 KRW입니다.\n출처: TOSS" in result["reply"]


def test_tether_exchange_rate_routes_to_usdt_krw(monkeypatch):
    captured = {}

    def fake_get_internal(path, auth_header, params=None):
        captured["path"] = path
        captured["params"] = params
        return {
            "data": {
                "base_currency": "USDT",
                "quote_currency": "KRW",
                "rate": 1388.5,
                "source": "COINONE_USDT_KRW",
                "captured_at": "2026-07-09T03:00:00Z",
            }
        }

    monkeypatch.setattr(tool_registry, "_get_internal", fake_get_internal)

    result = tool_registry.run_chatbot_tool("Bearer test", "테더 환율 조회해줘")

    assert captured["path"] == "/api/market/exchange-rate"
    assert captured["params"]["base"] == "USDT"
    assert captured["params"]["quote"] == "KRW"
    assert "USDT/KRW" in result["reply"]
    assert "1 USDT = 1,388.50 KRW" in result["reply"]
