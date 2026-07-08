import pytest

from backend.routes import transfer


class FakeCoinoneClient:
    def get_balance(self):
        return {
            "raw": {
                "balances": [
                    {"currency": "XRP", "available": "3.5"},
                ],
            },
        }

    def get_currency_info(self, currency):
        return {
            "symbol": currency,
            "withdraw_status": "normal",
            "withdrawal_fee": "0.2",
            "withdrawal_min_amount": "1",
            "max_precision": 6,
            "deposit_status": "normal",
        }

    def get_deposit_address(self, currency):
        return {
            "currency": currency,
            "address": "coinone-xrp-address",
            "secondary_address": "123456",
        }


class FakeBinanceClient:
    def get_balance(self):
        return {
            "raw": {
                "balances": [
                    {"asset": "XRP", "free": "5.25", "locked": "0"},
                ],
            },
        }

    def get_deposit_address(self, coin, network=None, amount=None):
        return {
            "coin": coin,
            "network": network,
            "address": "binance-xrp-address",
            "tag": "654321",
        }

    def get_withdraw_network_info(self, coin, network=None):
        return {
            "coin": coin,
            "network": network,
            "withdrawFee": "0.25",
            "withdrawMin": "1",
            "withdrawEnable": True,
        }


@pytest.fixture
def fake_clients(monkeypatch):
    clients = {
        "COINONE": FakeCoinoneClient(),
        "BINANCE": FakeBinanceClient(),
    }

    def load_client(auth_header, user_id, exchange):
        return clients[exchange]

    monkeypatch.setattr(transfer, "_load_exchange_client", load_client)
    monkeypatch.setattr(
        transfer,
        "_get_usdt_krw_rate_snapshot",
        lambda: {
            "usdt_krw_rate": 1400.0,
            "usdt_krw_rate_source": "COINONE_USDT_KRW",
            "usdt_krw_rate_captured_at": "2026-07-08T00:00:00+00:00",
        },
    )


def test_coinone_to_binance_precheck_includes_coinone_withdrawal_fee(fake_clients):
    result = transfer._build_precheck(
        "Bearer test",
        "user-1",
        {
            "currency": "XRP",
            "network": "XRP",
            "amount": 1.6,
            "address": "binance-xrp-address",
            "secondary_address": "654321",
        },
    )

    assert result["from_exchange"] == "COINONE"
    assert result["to_exchange"] == "BINANCE"
    assert result["withdrawal_fee"] == 0.2
    assert result["withdrawal_min_amount"] == 1.0
    assert result["estimated_receive_amount"] == pytest.approx(1.4)
    assert result["withdrawal_fee_source"] == "COINONE_PUBLIC_CURRENCIES"
    assert result["usdt_krw_rate"] == pytest.approx(1400.0)
    assert result["usdt_krw_rate_source"] == "COINONE_USDT_KRW"


def test_insert_transfer_proposal_stores_fee_fields(monkeypatch):
    captured = {}

    def fake_query(auth_header, table, method, json_data=None, params=None):
        captured["payload"] = json_data

    monkeypatch.setattr(transfer, "query_supabase", fake_query)

    transfer._insert_transfer_proposal(
        "Bearer test",
        "user-1",
        {
            "from_exchange": "COINONE",
            "to_exchange": "BINANCE",
            "currency": "DOGE",
            "network": "DOGE",
            "amount": 30.0,
            "address": "binance-doge-address",
            "estimated_receive_amount": 30.0,
            "withdrawal_fee": 20.0,
        },
        "APPROVED",
        {},
    )

    assert captured["payload"]["withdraw_fee"] == pytest.approx(20.0)
    assert captured["payload"]["expected_receive_amount"] == pytest.approx(30.0)
    assert captured["payload"]["fee_currency"] == "DOGE"


def test_transfer_amount_payload_preserves_known_coinone_fee():
    payload = transfer._build_transfer_amount_payload(
        {
            "currency": "DOGE",
            "amount": 30.0,
            "withdraw_fee": 20.0,
            "precheck_payload": {
                "withdrawal_fee": 20.0,
            },
        },
        {
            "amount": "30.0",
        },
    )

    assert payload["received_amount"] == pytest.approx(30.0)
    assert payload["withdraw_fee"] == pytest.approx(20.0)


def test_binance_to_coinone_xrp_precheck_uses_coinone_deposit_address_and_binance_fee(fake_clients):
    result = transfer._build_precheck(
        "Bearer test",
        "user-1",
        {
            "from_exchange": "BINANCE",
            "to_exchange": "COINONE",
            "currency": "XRP",
            "network": "XRP",
            "amount": 2.0,
            "address": "coinone-xrp-address",
            "secondary_address": "123456",
        },
    )

    assert result["from_exchange"] == "BINANCE"
    assert result["to_exchange"] == "COINONE"
    assert result["available_qty"] == pytest.approx(5.25)
    assert result["coinone_deposit_address"] == "coinone-xrp-address"
    assert result["coinone_deposit_tag"] == "123456"
    assert result["address_matches_destination"] is True
    assert result["tag_matches_destination"] is True
    assert result["withdrawal_fee"] == 0.25
    assert result["withdrawal_min_amount"] == 1.0
    assert result["estimated_receive_amount"] == pytest.approx(1.75)
    assert result["withdrawal_fee_source"] == "BINANCE_CAPITAL_CONFIG"


def test_coinone_deposit_address_falls_back_to_all_addresses_when_filtered_response_is_empty():
    class FakeResponse:
        status_code = 200
        text = ""

        def __init__(self, payload):
            self.payload = payload

        def json(self):
            return self.payload

    client = transfer.CoinoneClient("access", "secret")
    calls = []

    def fake_private_post(path, payload):
        calls.append((path, payload))
        if payload.get("currencies"):
            return {"result": "success", "deposit_addresses": []}
        return {
            "result": "success",
            "deposit_addresses": [
                {
                    "currency": "XRP",
                    "address": "coinone-xrp-address",
                    "secondary_address": "123456",
                },
            ],
        }

    client._private_post = fake_private_post

    result = client.get_deposit_address("XRP")

    assert result["address"] == "coinone-xrp-address"
    assert result["secondary_address"] == "123456"
    assert calls == [
        ("/v2.1/account/deposit_address", {"currencies": ["XRP"]}),
        ("/v2.1/account/deposit_address", {}),
    ]
