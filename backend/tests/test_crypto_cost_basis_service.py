import pytest

from backend.services.crypto_cost_basis_service import (
    apply_binance_transfer_cost_basis,
    build_crypto_average_prices,
    build_transfer_cost_basis,
    get_transfer_received_amount,
    get_transfer_source_amount,
)


def test_transfer_amounts_use_received_amount_when_present():
    row = {
        "amount": 50.0,
        "received_amount": 30.0,
        "withdraw_fee": 20.0,
    }

    assert get_transfer_source_amount(row) == pytest.approx(50.0)
    assert get_transfer_received_amount(row) == pytest.approx(30.0)


def test_transfer_amounts_support_legacy_amount_as_received_quantity():
    row = {
        "amount": 30.0,
        "withdraw_fee": 20.0,
    }

    assert get_transfer_source_amount(row) == pytest.approx(50.0)
    assert get_transfer_received_amount(row) == pytest.approx(30.0)


def test_transfer_cost_basis_excludes_fee_from_received_binance_lot():
    trade_rows = [
        {
            "exchange": "COINONE",
            "asset_type": "CRYPTO",
            "symbol": "DOGE",
            "side": "BUY",
            "price": 110.0,
            "volume": 50.0,
            "status": "EXECUTED",
        },
    ]
    transfer_rows = [
        {
            "from_exchange": "COINONE",
            "to_exchange": "BINANCE",
            "currency": "DOGE",
            "amount": 50.0,
            "received_amount": 30.0,
            "withdraw_fee": 20.0,
            "status": "COMPLETED",
            "precheck_payload": {
                "usdt_krw_rate": 1400.0,
            },
        },
    ]

    source_average_prices = build_crypto_average_prices(trade_rows, exchange="COINONE")
    cost_basis = build_transfer_cost_basis(transfer_rows, source_average_prices)

    assert cost_basis["DOGE"]["avg_price_krw"] == pytest.approx(110.0)
    assert cost_basis["DOGE"]["avg_price_usdt"] == pytest.approx(0.07857142857)
    assert cost_basis["DOGE"]["qty"] == pytest.approx(30.0)


def test_apply_binance_transfer_cost_basis_updates_profit_fields():
    balance = {
        "holdings": [
            {
                "symbol": "DOGE",
                "qty": 30.0,
                "avg_price": 0.0,
                "current_price": 0.072,
                "profit": 0.0,
                "profit_rate": 0.0,
            },
        ],
    }
    cost_basis = {
        "DOGE": {
            "avg_price_usdt": 0.07857142857,
            "avg_price_krw": 110.0,
            "qty": 30.0,
            "source": "TRANSFER_COST_BASIS",
            "rate_source": "COINONE_USDT_KRW",
            "usdt_krw_rate": 1400.0,
        },
    }

    apply_binance_transfer_cost_basis(balance, cost_basis)

    holding = balance["holdings"][0]
    assert holding["avg_price"] == pytest.approx(0.07857142857)
    assert holding["currency"] == "USDT"
    assert holding["profit"] == pytest.approx(-0.1971428571)
    assert holding["profit_rate"] == pytest.approx(-8.36363636)
    assert holding["avg_price_source"] == "TRANSFER_COST_BASIS"
