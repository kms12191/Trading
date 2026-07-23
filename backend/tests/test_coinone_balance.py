import pytest

from backend.services.coinone_client import CoinoneClient


def test_get_order_status_flattens_coinone_nested_order_payload(monkeypatch):
    client = CoinoneClient("access-token", "secret-key")
    monkeypatch.setattr(
        client,
        "_private_post",
        lambda *_args, **_kwargs: {
            "result": "success",
            "order": {
                "order_id": "order-1",
                "status": "FILLED",
                "executed_qty": "25000000",
                "average_executed_price": "0.0004",
                "fee": "2",
            },
        },
    )

    status = client.get_order_status("order-1", symbol="BTT")

    assert status == {
        "order_id": "order-1",
        "status": "FILLED",
        "executed_qty": "25000000",
        "average_fill_price": "0.0004",
        "fee": "2",
        "raw": {
            "result": "success",
            "order": {
                "order_id": "order-1",
                "status": "FILLED",
                "executed_qty": "25000000",
                "average_executed_price": "0.0004",
                "fee": "2",
            },
        },
    }


def test_coinone_balance_excludes_locked_withdrawal_quantity_from_holdings():
    client = CoinoneClient("access", "secret")

    def fake_private_post(path, payload):
        return {
            "result": "success",
            "balances": [
                {
                    "currency": "DOGE",
                    "available": "0",
                    "limit": "50",
                    "average_price": "110",
                },
                {
                    "currency": "KRW",
                    "available": "1000",
                    "limit": "0",
                },
            ],
        }

    client._private_post = fake_private_post
    client._get_tickers = lambda: {"DOGE": 110.0}

    balance = client.get_balance()

    assert balance["holdings"] == []
    assert balance["total_evaluation"] == pytest.approx(1000.0)


def test_coinone_balance_preserves_locked_quantity_metadata_for_visible_holdings():
    client = CoinoneClient("access", "secret")

    def fake_private_post(path, payload):
        return {
            "result": "success",
            "balances": [
                {
                    "currency": "DOGE",
                    "available": "30",
                    "limit": "20",
                    "average_price": "110",
                },
            ],
        }

    client._private_post = fake_private_post
    client._get_tickers = lambda: {"DOGE": 120.0}

    balance = client.get_balance()
    holding = balance["holdings"][0]

    assert holding["qty"] == pytest.approx(30.0)
    assert holding["available_qty"] == pytest.approx(30.0)
    assert holding["locked_qty"] == pytest.approx(20.0)
    assert holding["total_qty"] == pytest.approx(50.0)
    assert holding["profit"] == pytest.approx(300.0)
