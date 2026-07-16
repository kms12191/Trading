"""챗봇 function calling 도구 스키마입니다."""

FUNCTION_SCHEMAS = [
    {
        "name": "get_home_market_rankings",
        "description": "홈 화면 필터 기준으로 주식 또는 코인 순위를 프로젝트 내부 DB/API 기준으로 조회합니다.",
        "parameters": {
            "type": "object",
            "properties": {
                "asset_type": {
                    "type": "string",
                    "enum": ["STOCK", "CRYPTO"],
                    "description": "자산 유형. STOCK(주식) 또는 CRYPTO(가상자산)"
                },
                "market_segment": {
                    "type": "string",
                    "enum": ["KR", "US", "ALL"],
                    "description": "시장 분류. KR(국내장), US(미국장), ALL(전체)"
                },
                "ranking": {
                    "type": "string",
                    "enum": ["거래대금", "거래량", "상승률", "하락률"],
                    "description": "정렬 기준. 상승률, 하락률, 거래량, 거래대금 중 하나"
                },
                "limit": {
                    "type": "number",
                    "description": "조회할 상위 종목 개수. 기본값은 5, 최대 20"
                },
            },
        },
    },
    {
        "name": "get_portfolio_summary",
        "description": "로그인한 사용자의 개인 거래소 API와 DB를 사용해 평가 자산과 주문가능 현금 요약을 조회합니다.",
        "parameters": {
            "type": "object",
            "properties": {
                "exchange": {
                    "type": "string",
                    "enum": ["TOSS", "KIS", "COINONE", "BINANCE"],
                    "description": "거래소 이름. 지정하지 않으면 사용 가능한 모든 거래소 계좌를 통합하여 조회합니다."
                },
                "broker_env": {
                    "type": "string",
                    "enum": ["REAL", "MOCK"],
                    "description": "계좌 환경. REAL(실전계좌) 또는 MOCK(모의계좌). 지정하지 않으면 사용자의 기본 설정을 사용합니다."
                },
            },
        },
    },
    {
        "name": "add_watchlist_item",
        "description": "로그인한 사용자의 Supabase DB 관심종목에 특정 주식 또는 코인을 추가합니다.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "추가할 종목명 또는 종목코드. 예: 삼성전자, 005930, 비트코인, BTC"
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "remove_watchlist_item",
        "description": "로그인한 사용자의 Supabase DB 관심종목에서 특정 주식 또는 코인을 해제(삭제)합니다.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "삭제할 종목명 또는 종목코드. 예: 이노스페이스, 461350, 리플, XRP"
                },
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
                "exchange": {
                    "type": "string",
                    "enum": ["TOSS", "KIS", "COINONE", "BINANCE"],
                    "description": "거래소 이름. 지정하지 않으면 사용 가능한 모든 거래소 계좌의 보유 종목을 조회합니다."
                },
                "broker_env": {
                    "type": "string",
                    "enum": ["REAL", "MOCK"],
                    "description": "계좌 환경. REAL(실전계좌) 또는 MOCK(모의계좌)"
                },
            },
        },
    },
    {
        "name": "search_trade_history",
        "description": "로그인한 사용자의 Supabase DB 및 거래소 동기화 데이터를 기준으로 거래금액 또는 종목 조건의 거래내역을 조회합니다.",
        "parameters": {
            "type": "object",
            "properties": {
                "symbol": {
                    "type": "string",
                    "description": "조회할 종목명 또는 종목코드. 지정하지 않으면 전체 거래내역을 조회합니다."
                },
                "min_amount": {
                    "type": "number",
                    "description": "조회할 최소 정산 금액(원화 기준). 설정된 금액 이상의 거래만 필터링합니다."
                },
                "limit": {
                    "type": "number",
                    "description": "조회할 내역 개수. 기본값은 20"
                },
            },
        },
    },
    {
        "name": "list_open_orders",
        "description": "로그인한 사용자의 DB와 거래소 주문 상태 동기화 데이터를 기준으로 미체결 주문 목록을 조회합니다.",
        "parameters": {
            "type": "object",
            "properties": {
                "symbol": {
                    "type": "string",
                    "description": "조회할 종목명 또는 종목코드. 지정하지 않으면 전체 미체결 주문을 조회합니다."
                },
                "exchange": {
                    "type": "string",
                    "enum": ["TOSS", "KIS", "COINONE", "BINANCE"],
                    "description": "특정 거래소로 필터링할 경우 지정합니다."
                },
                "broker_env": {
                    "type": "string",
                    "enum": ["REAL", "MOCK"],
                    "description": "계좌 환경. REAL(실전) 또는 MOCK(모의)"
                },
                "limit": {
                    "type": "number",
                    "description": "조회할 주문 개수. 기본값 20, 최대 50"
                },
            },
        },
    },
    {
        "name": "get_exchange_rate",
        "description": "프로젝트 환율 API와 거래소/시세 API를 우선 사용해 달러, 엔화, 유로, 위안, 테더(USDT) 등 주요 통화의 환율을 조회합니다.",
        "parameters": {
            "type": "object",
            "properties": {
                "base_currency": {
                    "type": "string",
                    "description": "기준 통화. USD, USDT, JPY, EUR, CNY 등. 지정하지 않으면 기본값은 USD입니다."
                },
                "quote_currency": {
                    "type": "string",
                    "description": "상대 통화. KRW, USD 등. 지정하지 않으면 기본값은 KRW입니다."
                },
            },
        },
    },
    {
        "name": "get_asset_krw_conversion",
        "description": "해외주식 USD 현재가를 USD/KRW 환율로 원화 환산합니다. '애플 원화로 얼마야', 'AAPL 2주 한화로 계산해줘' 같은 요청에 사용합니다.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "원화로 환산할 종목명 또는 티커. 예: 애플, AAPL, 테슬라"
                },
                "quantity": {
                    "type": "number",
                    "description": "환산할 주식 수. 지정하지 않으면 기본값은 1입니다."
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "get_market_calendar",
        "description": "한국장 또는 미국장의 개장, 휴장, 정규장 운영 여부를 Toss 캘린더 API와 Supabase 캘린더 DB 기준으로 조회합니다. OpenAI 일반 지식으로 휴장 여부를 추측하지 않습니다.",
        "parameters": {
            "type": "object",
            "properties": {
                "market_country": {
                    "type": "string",
                    "enum": ["KR", "US"],
                    "description": "시장 국가. KR은 한국장, US는 미국장"
                },
                "date": {
                    "type": "string",
                    "description": "조회할 날짜. ISO 포맷 (YYYY-MM-DD). 지정하지 않으면 오늘 날짜를 기준으로 합니다."
                },
            },
        },
    },
    {
        "name": "get_asset_price",
        "description": "특정 주식 또는 코인의 현재가와 등락률을 Toss/KIS/Coinone/Binance API 기준으로 조회합니다. OpenAI 일반 지식으로 가격을 답하지 않습니다.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "종목명, 티커 또는 심볼. 예: Reddit, RDDT, 삼성전자, BTC, 리플"
                },
                "exchange": {
                    "type": "string",
                    "enum": ["TOSS", "KIS", "COINONE", "BINANCE"],
                    "description": "거래소 이름. 지정하지 않으면 가상자산은 기본적으로 COINONE, 주식은 기본적으로 TOSS를 사용합니다."
                },
                "broker_env": {
                    "type": "string",
                    "enum": ["REAL", "MOCK"],
                    "description": "계좌 환경. REAL(실전계좌) 또는 MOCK(모의계좌)"
                },
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
                "query": {
                    "type": "string",
                    "description": "종목명, 티커 또는 심볼. 예: 삼성전자, 005930, BTC"
                },
                "exchange": {
                    "type": "string",
                    "enum": ["TOSS", "KIS", "COINONE", "BINANCE"],
                    "description": "거래소 이름. 지정하지 않으면 가상자산은 기본적으로 COINONE, 주식은 기본적으로 TOSS를 사용합니다."
                },
                "broker_env": {
                    "type": "string",
                    "enum": ["REAL", "MOCK"],
                    "description": "계좌 환경. REAL(실전계좌) 또는 MOCK(모의계좌)"
                },
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
                "query": {
                    "type": "string",
                    "description": "종목명, 티커 또는 심볼. 예: 삼성전자, 005930, BTC"
                },
                "exchange": {
                    "type": "string",
                    "enum": ["TOSS", "KIS", "COINONE", "BINANCE"],
                    "description": "거래소 이름. 지정하지 않으면 가상자산은 기본적으로 COINONE, 주식은 기본적으로 TOSS를 사용합니다."
                },
                "broker_env": {
                    "type": "string",
                    "enum": ["REAL", "MOCK"],
                    "description": "계좌 환경. REAL(실전계좌) 또는 MOCK(모의계좌)"
                },
                "interval": {
                    "type": "string",
                    "enum": ["1m", "5m", "15m", "30m", "1h", "4h", "1d", "1w", "1M"],
                    "description": "캔들 간격. 지정하지 않으면 종목 성격에 맞춰 자동 감지됩니다."
                },
                "count": {
                    "type": "number",
                    "description": "조회할 최근 캔들 개수. 기본값은 20"
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "get_crypto_market_context",
        "description": "특정 코인의 현재가, 호가, 최근 캔들 흐름, ML 활성 신호, 거래소별 주의사항을 통합 조회합니다. 코인 분석, 단타, 진입 타이밍 질문에 우선 사용합니다.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "코인명 또는 심볼. 예: 리플, XRP, 비트코인, BTC"
                },
                "exchange": {
                    "type": "string",
                    "enum": ["COINONE", "BINANCE"],
                    "description": "거래소 이름. 지정하지 않으면 기본값은 COINONE입니다."
                },
                "broker_env": {
                    "type": "string",
                    "enum": ["REAL", "MOCK"],
                    "description": "계좌 환경. REAL(실전계좌) 또는 MOCK(모의계좌)"
                },
                "interval": {
                    "type": "string",
                    "enum": ["1m", "5m", "15m", "30m", "1h", "4h", "1d"],
                    "description": "캔들 간격. 기본값은 1h입니다."
                },
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
                "query": {
                    "type": "string",
                    "description": "전망을 분석할 종목명, 별칭 또는 종목코드. 예: 현대건설우, GST, 리플"
                },
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
                "query": {
                    "type": "string",
                    "description": "검색할 문장 또는 키워드"
                },
                "limit": {
                    "type": "number",
                    "description": "검색 결과 개수. 기본값 5"
                },
            },
            "required": ["query"],
        },
    },
]
