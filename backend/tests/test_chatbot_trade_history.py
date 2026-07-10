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
    assert tool_registry._extract_symbol_query("테슬라 거래내역 보여줘") == "TSLA"
    assert tool_registry._extract_symbol_query("삼성전자 거래내역 보여줘") == "삼성전자"
    assert tool_registry._extract_symbol_query("오천원이상 거래내역 보여줘") == ""
    assert tool_registry._extract_symbol_query("만원이상 거래내역 보여줘") == ""
    assert tool_registry._extract_symbol_query("30만원 이상 거래내역 보여줘") == ""

def test_extract_symbol_query_keeps_stock_and_crypto_alias_names():
    assert tool_registry._extract_symbol_query("삼성전기 관심종목 추가") == "삼성전기"
    assert tool_registry._extract_symbol_query("리플 관심종목 추가") == "XRP"
    assert tool_registry._extract_symbol_query("도지코인 뉴스 보여줘") == "DOGE"
    assert tool_registry._extract_symbol_query("테더 환율 알려줘") == "USDT"


def test_extract_symbol_query_uses_ml_training_universe_symbols():
    assert tool_registry._extract_symbol_query("XRPUSDT 관심종목 추가") == "XRP"
    assert tool_registry._extract_symbol_query("SUIUSDT 뉴스 보여줘") == "SUI"
    assert tool_registry._extract_symbol_query("AAPL 뉴스 보여줘") == "AAPL"
    assert tool_registry._extract_symbol_query("009150 관심종목 추가") == "009150"


def test_extract_symbol_query_normalizes_common_us_stock_korean_aliases():
    assert tool_registry._extract_symbol_query("아마존 관심종목 추가") == "AMZN"
    assert tool_registry._extract_symbol_query("애플 관심종목 추가") == "AAPL"
    assert tool_registry._extract_symbol_query("엔비디아 뉴스 보여줘") == "NVDA"
    assert tool_registry._extract_symbol_query("테슬라 거래내역 보여줘") == "TSLA"


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


def test_add_watchlist_item_saves_price_snapshot(monkeypatch):
    writes = []
    monkeypatch.setattr(tool_registry, "get_user_id_from_header", lambda auth_header: ("user-1", "token"))
    monkeypatch.setattr(
        tool_registry,
        "_resolve_symbol",
        lambda auth_header, query: {
            "symbol": "AAPL",
            "display_name": "애플",
            "asset_type": "STOCK",
            "market": "US",
        },
    )

    def fake_get_internal(path, auth_header, params=None):
        assert path == "/api/chart/quote"
        assert params == {"exchange": "TOSS", "symbol": "AAPL", "broker_env": "REAL"}
        return {
            "data": {
                "current_price": 210.5,
                "change_rate": 1.25,
            }
        }

    def fake_query_supabase(auth_header, endpoint, method="GET", json_data=None, params=None):
        if method == "GET":
            return []
        writes.append({"endpoint": endpoint, "method": method, "json_data": json_data})
        return [json_data]

    monkeypatch.setattr(tool_registry, "_get_internal", fake_get_internal)
    monkeypatch.setattr(tool_registry, "query_supabase", fake_query_supabase)

    result = tool_registry.add_watchlist_item("Bearer test", "애플 관심종목 추가")

    assert result["data"]["latest_price"] == 210.5
    assert result["data"]["average_price"] == 210.5
    assert result["data"]["change_rate"] == 1.25
    assert writes[0]["json_data"]["latest_price"] == 210.5
    assert writes[0]["json_data"]["average_price"] == 210.5
    assert writes[0]["json_data"]["change_rate"] == 1.25


def test_add_watchlist_item_uses_candle_close_when_quote_has_no_current_price(monkeypatch):
    writes = []
    monkeypatch.setattr(tool_registry, "get_user_id_from_header", lambda auth_header: ("user-1", "token"))
    monkeypatch.setattr(
        tool_registry,
        "_resolve_symbol",
        lambda auth_header, query: {
            "symbol": "009150",
            "display_name": "삼성전기",
            "asset_type": "STOCK",
            "market": "KR",
        },
    )

    def fake_get_internal(path, auth_header, params=None):
        if path == "/api/chart/quote":
            return {"data": {"change_rate": -0.75}}
        assert path == "/api/chart/candles"
        assert params == {"exchange": "KIS", "symbol": "009150", "interval": "1d", "count": 2, "broker_env": "REAL"}
        return {"data": [{"close": 123000}, {"close": 124500}]}

    def fake_query_supabase(auth_header, endpoint, method="GET", json_data=None, params=None):
        if method == "GET":
            return []
        writes.append(json_data)
        return [json_data]

    monkeypatch.setattr(tool_registry, "_get_internal", fake_get_internal)
    monkeypatch.setattr(tool_registry, "query_supabase", fake_query_supabase)

    result = tool_registry.add_watchlist_item("Bearer test", "삼성전기 관심종목 추가")

    assert result["data"]["latest_price"] == 124500
    assert result["data"]["average_price"] == 124500
    assert result["data"]["change_rate"] == -0.75
    assert writes[0]["latest_price"] == 124500


def test_remove_watchlist_item_deletes_existing_record(monkeypatch):
    calls = []
    monkeypatch.setattr(tool_registry, "get_user_id_from_header", lambda auth_header: ("user-1", "token"))
    monkeypatch.setattr(
        tool_registry,
        "_resolve_symbol",
        lambda auth_header, query: {
            "symbol": "AMZN",
            "display_name": "아마존",
            "asset_type": "STOCK",
            "market": "US",
        },
    )

    def fake_query_supabase(auth_header, endpoint, method="GET", json_data=None, params=None):
        calls.append({"endpoint": endpoint, "method": method, "params": params})
        if method == "GET":
            return [{"id": "watch-1", "name": "아마존"}]
        return []

    monkeypatch.setattr(tool_registry, "query_supabase", fake_query_supabase)

    result = tool_registry.remove_watchlist_item("Bearer test", "아마존 관심종목 해제")

    assert "해제했습니다" in result["reply"]
    assert result["data"]["symbol"] == "AMZN"
    assert calls[0]["endpoint"] == "user_watchlist"
    assert calls[1] == {
        "endpoint": "user_watchlist?id=eq.watch-1",
        "method": "DELETE",
        "params": None,
    }


def test_run_chatbot_tool_routes_watchlist_remove(monkeypatch):
    monkeypatch.setattr(
        tool_registry,
        "remove_watchlist_item",
        lambda auth_header, text: {"reply": "removed", "data": {"message": text}},
    )

    result = tool_registry.run_chatbot_tool("Bearer test", "아마존 관심종목 해제")

    assert result["reply"] == "removed"
    assert result["data"]["message"] == "아마존 관심종목 해제"


def test_strategy_request_with_holdings_keyword_does_not_route_to_holdings_tool():
    result = tool_registry.run_chatbot_tool(
        "Bearer test",
        "현재 관심 종목이나 보유 종목을 기준으로 구체적인 매수 타이밍과 비중 조절 전략도 함께 제안해줘",
    )

    assert result is None


def test_investment_profile_reanalysis_routes_to_settings_guide():
    result = tool_registry.run_chatbot_tool("Bearer test", "투자성향 재분석 하고싶어")

    assert result is not None
    assert "설정 메뉴" in result["reply"]
    assert "투자 성향 재분석" in result["reply"]
    assert result["actions"][0]["type"] == "navigate"
    assert result["actions"][0]["to"] == "/settings"
    assert result["data"]["source"] == "SETTINGS_INVESTMENT_PROFILE_GUIDE"


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


def test_web_search_routes_to_tavily(monkeypatch):
    class FakeTavilyClient:
        def search(self, query, max_results=5):
            return {
                "answer": "삼성전자 관련 최신 이슈 요약입니다.",
                "results": [
                    {
                        "title": "삼성전자 뉴스",
                        "url": "https://example.com/samsung",
                        "content": "삼성전자 시장 이슈 요약",
                    }
                ],
            }

    monkeypatch.setattr(tool_registry, "TavilyClient", FakeTavilyClient)

    result = tool_registry.run_chatbot_tool("Bearer test", "삼성전자 최신 뉴스 찾아줘")

    assert result is not None
    assert "Tavily 웹 검색 결과입니다." in result["reply"]
    assert "삼성전자 관련 최신 이슈 요약입니다." in result["reply"]
    assert "출처: Tavily" in result["reply"]
    assert result["data"]["source"] == "TAVILY"


def test_web_search_routes_to_tavily(monkeypatch):
    class FakeWebFallbackSearchService:
        def search(self, auth_header=None, user_id=None, query="", limit=None):
            return {
                "reply": "내부 지식/DB/API 결과가 부족해 Tavily를 최후 fallback으로 사용했습니다.\n출처: Tavily + OpenAI 요약",
                "data": {"source": "TAVILY_FALLBACK", "query": query},
            }

    monkeypatch.setattr(tool_registry, "ChatbotWebFallbackSearchService", FakeWebFallbackSearchService)
    monkeypatch.setattr(tool_registry, "get_user_id_from_header", lambda auth_header: ("user-1", "token"))

    result = tool_registry.run_chatbot_tool("Bearer test", "삼성전자 최신 뉴스 찾아줘")

    assert result is not None
    assert "Tavily" in result["reply"]
    assert result["data"]["source"] == "TAVILY_FALLBACK"
