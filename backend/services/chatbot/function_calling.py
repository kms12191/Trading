"""Basic function-calling schemas for the chatbot."""

FUNCTION_SCHEMAS = [
    {
        "name": "get_price",
        "description": "거래소와 심볼 기준으로 현재가를 조회합니다.",
        "parameters": {
            "type": "object",
            "properties": {
                "exchange": {"type": "string", "description": "TOSS, KIS, COINONE, BINANCE 등"},
                "symbol": {"type": "string", "description": "Asset symbol"},
            },
            "required": ["exchange", "symbol"],
        },
    },
    {
        "name": "get_holdings",
        "description": "로그인한 사용자의 보유 자산 요약을 조회합니다.",
        "parameters": {
            "type": "object",
            "properties": {
                "include_mock": {"type": "boolean", "description": "Include mock accounts"},
            },
        },
    },
    {
        "name": "create_trade_proposal",
        "description": "사용자 승인이 필요한 매매 제안을 생성합니다. 실제 주문 실행은 하지 않습니다.",
        "parameters": {
            "type": "object",
            "properties": {
                "exchange": {"type": "string"},
                "symbol": {"type": "string"},
                "side": {"type": "string", "enum": ["BUY", "SELL"]},
                "quantity": {"type": "number"},
                "price": {"type": "number"},
                "broker_env": {"type": "string", "enum": ["REAL", "MOCK"]},
            },
            "required": ["exchange", "symbol", "side", "quantity"],
        },
    },
]
