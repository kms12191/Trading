from backend.routes import trade
from backend.services.kis_client import KISClient
from backend.services.toss_client import TossClient


class _FakeKISResponse:
    status_code = 200
    text = ""

    def json(self):
        return {
            "rt_cd": "0",
            "output": {
                "stck_prpr": "1909000",
                "stck_sdpr": "1800000",
                "stck_prdy_clpr": "1900000",
                "prdy_clpr": "1890000",
                "base_pric": "1880000",
                "prdy_vrss": "9000",
                "prdy_ctrt": "0.47",
                "acml_vol": "10",
                "acml_tr_pbmn": "19090000",
            },
        }


class _FakeTossResponse:
    status_code = 200
    text = ""

    def json(self):
        return {
            "result": {
                "lastPrice": "1909000",
                "changeRate": "0.47",
                "previousClosePrice": "1900000",
            },
        }


class _FakeTossResponseWithoutExplicitChangeRate:
    status_code = 200
    text = ""

    def json(self):
        return {
            "result": {
                "lastPrice": "254500",
                "previousClosePrice": "257500",
            },
        }


def test_recalculate_change_rate_from_current_and_previous_close():
    assert trade._recalculate_change_rate(1909000, 1900000) == 0.4737


def test_load_kis_previous_close_for_toss_kr_quote(monkeypatch):
    class FakeKISClient:
        def get_price(self, symbol):
            assert symbol == "005930"
            return {
                "current_price": 268000,
                "previous_close": 260700,
                "change_rate": 2.8,
            }

    monkeypatch.setattr(
        trade,
        "_load_user_exchange_record",
        lambda auth_header, user_id, exchange, broker_env: ({"user_id": user_id}, "access", "secret"),
    )
    monkeypatch.setattr(
        trade,
        "_build_exchange_client",
        lambda exchange, broker_env, record, access_key, secret_key: FakeKISClient(),
    )

    previous_close, env = trade._load_kis_previous_close_for_quote("Bearer token", "user-1", "005930", "REAL")

    assert previous_close == 260700
    assert env == "REAL"


def test_extract_previous_close_from_quote_payload_direct_field():
    quote = {
        "current_price": 1909000,
        "previous_close": 1900000,
        "change_rate": -0.05,
    }

    current_price, previous_close, change_rate = trade._normalize_live_quote_prices(quote)

    assert current_price == 1909000
    assert previous_close == 1900000
    assert change_rate == 0.4737


def test_toss_price_source_recalculates_change_rate_from_live_price_and_previous_close():
    quote = {
        "current_price": 1909000,
        "previous_close": 1900000,
        "change_rate": -12.08,
        "change_rate_source": "TOSS_PRICE",
    }

    current_price, previous_close, change_rate = trade._normalize_live_quote_prices(quote)

    assert current_price == 1909000
    assert previous_close == 1900000
    assert change_rate == 0.4737


def test_extract_previous_close_from_kis_price_difference():
    quote = {
        "current_price": 1909000,
        "price_change": 9000,
        "change_rate": -0.05,
    }

    current_price, previous_close, change_rate = trade._normalize_live_quote_prices(quote)

    assert current_price == 1909000
    assert previous_close == 1900000
    assert change_rate == 0.4737


def test_extract_previous_close_from_kis_signed_down_price_difference():
    quote = {
        "current_price": 1891000,
        "price_change": 9000,
        "price_change_sign": "5",
        "change_rate": 0.05,
    }

    current_price, previous_close, change_rate = trade._normalize_live_quote_prices(quote)

    assert current_price == 1891000
    assert previous_close == 1900000
    assert change_rate == -0.4737


def test_kis_price_prefers_previous_close_before_standard_price(monkeypatch):
    client = KISClient("appkey", "appsecret", "cano", env="REAL")

    def fake_request(*args, **kwargs):
        return _FakeKISResponse()

    monkeypatch.setattr(client, "_request_with_token_retry", fake_request)

    quote = client.get_price("000660")

    assert quote["previous_close"] == 1900000
    assert round(quote["change_rate"], 4) == 0.4737


def test_toss_price_keeps_percent_change_rate_scale(monkeypatch):
    client = TossClient("client-id", "client-secret", env="REAL")

    monkeypatch.setattr(client, "_get_cached_token", lambda: "token")
    monkeypatch.setattr(client, "_send_request", lambda *args, **kwargs: _FakeTossResponse())

    quote = client.get_price("005930")

    assert quote["current_price"] == 1909000
    assert quote["previous_close"] == 1900000
    assert quote["change_rate"] == 0.47
    assert quote["raw_change_rate"] == 0.47


def test_toss_price_does_not_calculate_change_rate_from_ambiguous_previous_close(monkeypatch):
    client = TossClient("client-id", "client-secret", env="REAL")

    monkeypatch.setattr(client, "_get_cached_token", lambda: "token")
    monkeypatch.setattr(client, "_send_request", lambda *args, **kwargs: _FakeTossResponseWithoutExplicitChangeRate())

    quote = client.get_price("005930")

    assert quote["current_price"] == 254500
    assert quote["change_rate"] == 0.0
