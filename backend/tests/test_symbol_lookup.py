from flask import Flask

from backend.routes import trade
from backend.services.symbol_reconciliation_service import filter_symbol_results


def test_lookup_symbol_falls_back_to_turnover_latest_name(monkeypatch):
    app = Flask(__name__)
    apple_name = "\uc560\ud50c"

    class FakeMarketRepository:
        def search_stock_master(self, query, limit=5):
            return []

    def fake_safe_query_supabase_as_service_role(table, method="GET", json_data=None, params=None):
        if table != "kis_stock_turnover_latest":
            return []
        if json_data is not None:
            return []
        assert method == "GET"
        assert f"name.ilike.*{apple_name}*" in params["or"]
        return [
            {
                "symbol": "AAPL",
                "name": apple_name,
                "market_country": "US",
            }
        ]

    monkeypatch.setattr("backend.services.market_repository.MarketRepository", FakeMarketRepository)
    monkeypatch.setattr(
        "backend.services.supabase_client.safe_query_supabase_as_service_role",
        fake_safe_query_supabase_as_service_role,
    )
    monkeypatch.setattr(trade, "_auto_backfill_stock_from_turnover", lambda query_symbol: None)

    with app.test_request_context(f"/api/symbol/lookup?query={apple_name}"):
        response = trade.lookup_symbol()
    if isinstance(response, tuple):
        response, _ = response

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["success"] is True
    assert payload["data"] == {
        "symbol": "AAPL",
        "display_name": apple_name,
        "asset_type": "STOCK",
        "market": "US",
    }


def test_filter_symbol_results_hides_temporary_symbol_when_canonical_exists():
    rows = filter_symbol_results([
        {"symbol": "SKHYV", "display_name": "SK하이닉스(ADR)", "asset_type": "STOCK", "market": "US"},
        {"symbol": "SKHY", "display_name": "SK하이닉스(ADR)", "asset_type": "STOCK", "market": "US"},
    ])

    assert [row["symbol"] for row in rows] == ["SKHY"]


def test_filter_symbol_results_marks_temporary_symbol_when_canonical_missing():
    rows = filter_symbol_results([
        {"symbol": "SKHYV", "display_name": "SK하이닉스(ADR)", "asset_type": "STOCK", "market": "US"},
    ])

    assert rows == [{
        "symbol": "SKHYV",
        "display_name": "SK하이닉스(ADR)",
        "asset_type": "STOCK",
        "market": "US",
        "is_temporary_symbol": True,
        "canonical_symbol": "SKHY",
        "symbol_badge": "임시코드",
    }]
