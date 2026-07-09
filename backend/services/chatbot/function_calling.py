"""챗봇 function calling 도구 스키마입니다."""

FUNCTION_SCHEMAS = [
    {
        "name": "get_home_market_rankings",
        "description": "홈 화면 필터 기준으로 주식 또는 코인 순위를 조회합니다.",
        "parameters": {
            "type": "object",
            "properties": {
                "asset_type": {"type": "string", "enum": ["STOCK", "CRYPTO"]},
                "market_segment": {"type": "string", "description": "KR, US, ALL"},
                "ranking": {"type": "string", "description": "거래대금, 거래량, 상승률, 하락률"},
                "limit": {"type": "number"},
            },
        },
    },
    {
        "name": "get_portfolio_summary",
        "description": "로그인한 사용자의 평가 자산과 주문가능 현금 요약을 조회합니다.",
        "parameters": {
            "type": "object",
            "properties": {
                "exchange": {"type": "string", "description": "TOSS, KIS, COINONE, BINANCE 등"},
                "broker_env": {"type": "string", "enum": ["REAL", "MOCK"]},
            },
        },
    },
    {
        "name": "add_watchlist_item",
        "description": "로그인한 사용자의 관심종목에 종목을 추가합니다.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "종목명 또는 종목코드"},
            },
            "required": ["query"],
        },
    },
    {
        "name": "get_holdings",
        "description": "로그인한 사용자의 보유 주식 또는 코인 현황을 조회합니다.",
        "parameters": {
            "type": "object",
            "properties": {
                "exchange": {"type": "string", "description": "TOSS, KIS, COINONE, BINANCE 등"},
                "broker_env": {"type": "string", "enum": ["REAL", "MOCK"]},
            },
        },
    },
    {
        "name": "search_trade_history",
        "description": "거래금액 또는 종목 조건으로 거래내역을 조회합니다.",
        "parameters": {
            "type": "object",
            "properties": {
                "symbol": {"type": "string"},
                "min_amount": {"type": "number"},
                "limit": {"type": "number"},
            },
        },
    },
    {
        "name": "get_exchange_rate",
        "description": "달러, 엔화, 유로, 위안, 테더(USDT) 등 주요 통화의 환율을 조회합니다.",
        "parameters": {
            "type": "object",
            "properties": {
                "base_currency": {"type": "string", "description": "USD, USDT, JPY, EUR, CNY 등 기준 통화"},
                "quote_currency": {"type": "string", "description": "KRW, USD 등 상대 통화"},
            },
        },
    },
    {
        "name": "search_web",
        "description": "내부 RAG, DB, 기존 뉴스/공시 API를 우선 확인하고 부족할 때 Tavily로 최신 웹 검색을 수행합니다.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "검색할 문장 또는 키워드"},
                "limit": {"type": "number", "description": "검색 결과 개수"},
            },
            "required": ["query"],
        },
    },
]
