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


def test_parse_comma_separated_limit_price():
    intent = parse_order_intent("삼성전자 1주 70,000원에 사줘")

    assert intent.is_order_request is True
    assert intent.side == "BUY"
    assert intent.symbol_query == "삼성전자"
    assert intent.quantity == 1
    assert intent.price == 70000
    assert intent.amount_krw is None
    assert intent.order_type == "LIMIT"


def test_parse_price_before_limit_keyword_as_limit_price():
    intent = parse_order_intent("도지코인 5개 100원 지정가 코인원 매매요청")

    assert intent.is_order_request is True
    assert intent.side == "BUY"
    assert intent.symbol_query == "도지코인"
    assert intent.quantity == 5
    assert intent.price == 100
    assert intent.amount_krw is None
    assert intent.order_type == "LIMIT"


def test_parse_amount_trade_request_defaults_to_buy():
    intent = parse_order_intent("비트코인 10만원어치 코인원 매매요청")

    assert intent.is_order_request is True
    assert intent.side == "BUY"
    assert intent.symbol_query == "비트코인"
    assert intent.amount_krw == 100000


def test_incomplete_trade_proposal_phrase_routes_to_safe_clarification():
    intent = parse_order_intent("매매 제안 만들어줘")

    assert intent.is_order_request is True
    assert intent.side is None
    assert intent.symbol_query == ""


def test_order_history_query_is_not_order_creation():
    assert parse_order_intent("최근 주문내역 보여줘").is_order_request is False


def test_symbol_choice_question_is_not_direct_order_creation():
    assert parse_order_intent("삼성전자랑 하이닉스 중 뭐 살까?").is_order_request is False


def test_price_token_is_not_parsed_as_order_budget():
    intent = parse_order_intent("XRP 10개 800원에 모의로 사줘")

    assert intent.quantity == 10
    assert intent.price == 800
    assert intent.amount_krw is None


def test_manwon_price_is_not_parsed_as_order_budget():
    intent = parse_order_intent("삼성전자 1주 10만원에 모의로 사줘")

    assert intent.price == 100000
    assert intent.amount_krw is None


def test_spaced_manwon_price_is_not_parsed_as_order_budget():
    intent = parse_order_intent("삼성전자 1주 10만 원에 모의로 사줘")

    assert intent.price == 100000
    assert intent.amount_krw is None


def test_spaced_korean_manwon_price_is_not_parsed_as_order_budget():
    intent = parse_order_intent("삼성전자 1주 십만 원에 모의로 사줘")

    assert intent.price == 100000
    assert intent.amount_krw is None


def test_korean_manwon_price_is_not_parsed_as_order_budget():
    intent = parse_order_intent("삼성전자 1주 십만원에 모의로 사줘")

    assert intent.price == 100000
    assert intent.amount_krw is None


def test_manwon_budget_remains_an_order_amount():
    intent = parse_order_intent("삼성전자 10만원어치 모의로 사줘")

    assert intent.amount_krw == 100000
    assert intent.price is None


def test_spaced_manwon_budget_remains_an_order_amount():
    intent = parse_order_intent("삼성전자 10만 원어치 모의로 사줘")

    assert intent.amount_krw == 100000
    assert intent.price is None


def test_korean_manwon_budget_remains_an_order_amount():
    intent = parse_order_intent("삼성전자 십만원어치 모의로 사줘")

    assert intent.amount_krw == 100000
    assert intent.price is None


def test_multiple_symbol_choice_requires_clarification():
    intent = parse_order_intent("삼성전자랑 하이닉스 중 1주 매수 제안해줘")

    assert intent.is_order_request is True
    assert intent.side == "BUY"
    assert intent.symbol_query == ""
    assert intent.quantity == 1


def test_korean_object_particle_is_removed_from_symbol_query():
    intent = parse_order_intent("삼성전자를 1주 사줘")

    assert intent.symbol_query == "삼성전자"
    assert intent.quantity == 1


def test_korean_subject_particle_is_removed_from_symbol_query():
    intent = parse_order_intent("이더리움이 1개 매수 제안")

    assert intent.symbol_query == "이더리움"
    assert intent.quantity == 1


def test_exchange_name_is_not_parsed_as_symbol_query():
    intent = parse_order_intent("바이낸스 비트코인 지정가 80000000원 1개 매수 제안해줘")

    assert intent.symbol_query == "비트코인"
    assert intent.price == 80000000
    assert intent.order_type == "LIMIT"
