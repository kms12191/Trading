from backend.services.chatbot.order_parser import parse_order_intent


def test_parse_buy_amount_order_from_korean_money():
    intent = parse_order_intent("삼성전자 10만원어치 사줘")

    assert intent.is_order_request is True
    assert intent.side == "BUY"
    assert intent.symbol_query == "삼성전자"
    assert intent.amount_krw == 100000
    assert intent.quantity is None
    assert intent.order_type == "MARKET"


def test_parse_sell_ratio_order():
    intent = parse_order_intent("하이닉스 절반 팔아줘")

    assert intent.is_order_request is True
    assert intent.side == "SELL"
    assert intent.symbol_query == "하이닉스"
    assert intent.sell_ratio == 0.5
    assert intent.quantity is None


def test_parse_limit_quantity_mock_order():
    intent = parse_order_intent("XRP 10개 800원에 모의로 사줘")

    assert intent.is_order_request is True
    assert intent.side == "BUY"
    assert intent.symbol_query == "XRP"
    assert intent.quantity == 10
    assert intent.price == 800
    assert intent.order_type == "LIMIT"
    assert intent.broker_env == "MOCK"
