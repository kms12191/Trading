import pytest

from backend.routes import trade


def test_crypto_transfer_deduction_removes_coinone_holding_with_fee():
    grouped = {
        "CRYPTO:COINONE:REAL:DOGE": {
            "symbol": "DOGE",
            "raw_exchange": "COINONE",
            "qty": 50.0,
        },
    }
    transfers = [
        {
            "from_exchange": "COINONE",
            "to_exchange": "BINANCE",
            "currency": "DOGE",
            "amount": 30.0,
            "withdraw_fee": 20.0,
            "status": "COMPLETED",
        },
    ]

    trade._apply_crypto_transfer_deductions(
        grouped,
        trade._build_crypto_transfer_deductions(transfers),
    )

    assert grouped["CRYPTO:COINONE:REAL:DOGE"]["qty"] == pytest.approx(0.0)
    assert grouped["CRYPTO:COINONE:REAL:DOGE"]["transfer_deducted_qty"] == pytest.approx(50.0)


def test_crypto_transfer_deduction_ignores_failed_transfers():
    grouped = {
        "CRYPTO:COINONE:REAL:DOGE": {
            "symbol": "DOGE",
            "raw_exchange": "COINONE",
            "qty": 50.0,
        },
    }
    transfers = [
        {
            "from_exchange": "COINONE",
            "to_exchange": "BINANCE",
            "currency": "DOGE",
            "amount": 30.0,
            "withdraw_fee": 20.0,
            "status": "FAILED",
        },
    ]

    trade._apply_crypto_transfer_deductions(
        grouped,
        trade._build_crypto_transfer_deductions(transfers),
    )

    assert grouped["CRYPTO:COINONE:REAL:DOGE"]["qty"] == pytest.approx(50.0)
