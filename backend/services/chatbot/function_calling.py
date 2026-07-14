"""챗봇 function calling 도구 스키마입니다."""

FUNCTION_SCHEMAS = [
    {
        "name": "get_home_market_rankings",
        "description": "홈 화면 필터 기준으로 주식 또는 코인 순위를 프로젝트 내부 DB/API 기준으로 조회합니다.",
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
        "description": "로그인한 사용자의 개인 거래소 API와 DB를 사용해 평가 자산과 주문가능 현금 요약을 조회합니다.",
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
        "description": "로그인한 사용자의 Supabase DB 관심종목에 종목을 추가합니다.",
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
        "description": "로그인한 사용자의 개인 Toss/KIS/Coinone/Binance API와 DB 기준으로 보유 주식 또는 코인 현황을 조회합니다.",
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
        "description": "로그인한 사용자의 Supabase DB 및 거래소 동기화 데이터를 기준으로 거래금액 또는 종목 조건의 거래내역을 조회합니다.",
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
        "name": "list_open_orders",
        "description": "로그인한 사용자의 DB와 거래소 주문 상태 동기화 데이터를 기준으로 미체결 주문 목록을 조회합니다.",
        "parameters": {
            "type": "object",
            "properties": {
                "symbol": {"type": "string", "description": "종목명 또는 종목코드"},
                "exchange": {"type": "string", "description": "TOSS, KIS, COINONE, BINANCE 등"},
                "broker_env": {"type": "string", "enum": ["REAL", "MOCK"]},
                "limit": {"type": "number", "description": "조회할 주문 개수"},
            },
        },
    },
    {
        "name": "get_exchange_rate",
        "description": "프로젝트 환율 API와 거래소/시세 API를 우선 사용해 달러, 엔화, 유로, 위안, 테더(USDT) 등 주요 통화의 환율을 조회합니다.",
        "parameters": {
            "type": "object",
            "properties": {
                "base_currency": {"type": "string", "description": "USD, USDT, JPY, EUR, CNY 등 기준 통화"},
                "quote_currency": {"type": "string", "description": "KRW, USD 등 상대 통화"},
            },
        },
    },
    {
        "name": "get_asset_price",
        "description": "특정 주식 또는 코인의 현재가와 등락률을 Toss/KIS/Coinone/Binance API 기준으로 조회합니다. OpenAI 일반 지식으로 가격을 답하지 않습니다.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "종목명 또는 종목코드. 예: Reddit, RDDT, 삼성전자, BTC"},
                "exchange": {"type": "string", "description": "TOSS, KIS, COINONE, BINANCE 등"},
                "broker_env": {"type": "string", "enum": ["REAL", "MOCK"]},
            },
            "required": ["query"],
        },
    },
    {
        "name": "get_asset_orderbook",
        "description": "특정 주식 또는 코인의 호가 정보를 프로젝트 호가 API 기준으로 조회합니다. 매도/매수 최우선 호가와 잔량을 반환합니다.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "종목명 또는 종목코드. 예: 삼성전자, 005930, BTC"},
                "exchange": {"type": "string", "description": "TOSS, KIS, COINONE, BINANCE 등"},
                "broker_env": {"type": "string", "enum": ["REAL", "MOCK"]},
            },
            "required": ["query"],
        },
    },
    {
        "name": "get_asset_candles",
        "description": "특정 주식 또는 코인의 최근 캔들 차트 데이터를 프로젝트 차트 API 기준으로 조회하고 흐름을 요약합니다. 단정적 예측은 하지 않습니다.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "종목명 또는 종목코드. 예: 삼성전자, 005930, BTC"},
                "exchange": {"type": "string", "description": "TOSS, KIS, COINONE, BINANCE 등"},
                "broker_env": {"type": "string", "enum": ["REAL", "MOCK"]},
                "interval": {"type": "string", "description": "1m, 5m, 15m, 30m, 1h, 4h, 1d, 1w, 1M"},
                "count": {"type": "number", "description": "조회할 최근 캔들 개수"},
            },
            "required": ["query"],
        },
    },
    {
        "name": "get_asset_outlook",
        "description": "특정 주식 또는 코인의 전망, 리스크, 최근 뉴스/공시 흐름을 내부 RAG/DB/API와 필요한 경우 웹 검색 결과 기준으로 조회합니다.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "종목명, 별칭 또는 종목코드. 예: 현대건설우, GST, 리플"},
            },
            "required": ["query"],
        },
    },
    {
        "name": "search_web",
        "description": "내부 RAG, DB, 기존 뉴스/공시 API를 우선 확인하고 부족할 때만 Tavily로 최신 웹 검색을 수행합니다. 검색 결과 요약에만 OpenAI를 사용합니다.",
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
