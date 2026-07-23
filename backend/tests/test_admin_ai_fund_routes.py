import pytest
from backend.app import app
import backend.routes.admin_ai_fund as admin_ai_fund_route


@pytest.fixture
def client():
    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client


def test_get_ai_fund_configs_requires_auth(client):
    res = client.get("/api/admin/ai-fund/configs")
    assert res.status_code == 401


def test_kill_switch_requires_auth(client):
    res = client.post("/api/admin/ai-fund/kill-switch", json={"exchange_type": "coinone"})
    assert res.status_code == 401


def test_upsert_ai_fund_config_rejects_canary_without_positive_limit(client):
    res = client.post(
        "/api/admin/ai-fund/configs",
        headers={"Authorization": "Bearer test-token"},
        json={
            "user_id": "00000000-0000-0000-0000-000000000001",
            "exchange_type": "coinone",
            "operation_mode": "CANARY",
            "canary_max_order_amount": 0,
        },
    )

    assert res.status_code == 400
    assert res.get_json()["success"] is False


def test_upsert_ai_fund_config_rejects_invalid_target_allocations(client):
    res = client.post(
        "/api/admin/ai-fund/configs",
        headers={"Authorization": "Bearer test-token"},
        json={
            "user_id": "00000000-0000-0000-0000-000000000001",
            "exchange_type": "coinone",
            "target_allocations": {"BTC": 0.7, "ETH": 0.5},
        },
    )

    assert res.status_code == 400


def test_upsert_ai_fund_config_normalizes_operation_mode_and_forwards_upsert_header(client, monkeypatch):
    captured = {}

    def fake_query(endpoint, method="GET", json_data=None, params=None, extra_headers=None):
        captured.update(
            endpoint=endpoint,
            method=method,
            json_data=json_data,
            params=params,
            extra_headers=extra_headers,
        )
        return [{"id": "config-1"}]

    monkeypatch.setattr(admin_ai_fund_route, "safe_query_supabase_as_service_role", fake_query)
    res = client.post(
        "/api/admin/ai-fund/configs",
        headers={"Authorization": "Bearer test-token"},
        json={
            "user_id": "00000000-0000-0000-0000-000000000001",
            "exchange_type": "coinone",
            "operation_mode": "canary",
            "canary_max_order_amount": 10000,
        },
    )

    assert res.status_code == 200
    assert captured["json_data"]["operation_mode"] == "CANARY"
    assert captured["extra_headers"] == {"Prefer": "resolution=merge-duplicates"}


def test_stock_candidates_returns_auto_selected_rows(client, monkeypatch):
    monkeypatch.setattr(
        admin_ai_fund_route,
        "safe_query_supabase_as_service_role",
        lambda *_args, **_kwargs: [{"user_id": "user-1", "exchange_type": "toss", "asset_scope": "ALL"}],
    )
    monkeypatch.setattr(
        admin_ai_fund_route,
        "AiFundStockSelectionService",
        lambda: type("Service", (), {
            "select_candidates": lambda *_args, **_kwargs: [
                {"symbol": "005930", "market": "KR", "confidence_score": 0.92}
            ],
            "get_availability": lambda *_args, **_kwargs: {
                "KR": {"status": "READY", "message": "주문 검토 가능한 매수 후보가 있습니다."}
            },
        })(),
    )
    monkeypatch.setattr(
        admin_ai_fund_route,
        "AdminAiManagedTrader",
        lambda *_args, **_kwargs: type("Trader", (), {"list_open_positions": lambda *_args: []})(),
    )

    response = client.get(
        "/api/admin/ai-fund/stock-candidates?user_id=user-1",
        headers={"Authorization": "Bearer test-token"},
    )

    assert response.status_code == 200
    assert response.get_json()["candidates"] == [
        {"symbol": "005930", "market": "KR", "confidence_score": 0.92}
    ]
    assert response.get_json()["availability"]["KR"]["status"] == "READY"


def test_crypto_candidates_returns_korean_availability_reason(client, monkeypatch):
    monkeypatch.setattr(
        admin_ai_fund_route,
        "safe_query_supabase_as_service_role",
        lambda *_args, **_kwargs: [{"user_id": "user-1", "exchange_type": "coinone", "min_signal_confidence": 0.75}],
    )
    monkeypatch.setattr(
        admin_ai_fund_route,
        "AiFundCryptoSelectionService",
        lambda *_args, **_kwargs: type("Service", (), {
            "get_snapshot": lambda *_args, **_kwargs: {
                "candidates": [],
                "availability": {"status": "NO_LONG_SIGNAL", "message": "현재 모델이 매수 신호를 내지 않아 코인 후보를 보류했습니다."},
            }
        })(),
    )

    response = client.get(
        "/api/admin/ai-fund/crypto-candidates?user_id=user-1&exchange_type=coinone",
        headers={"Authorization": "Bearer test-token"},
    )

    assert response.status_code == 200
    assert response.get_json()["availability"]["message"] == "현재 모델이 매수 신호를 내지 않아 코인 후보를 보류했습니다."


def test_crypto_short_performance_returns_research_only_status(client, monkeypatch):
    monkeypatch.setattr(
        admin_ai_fund_route,
        "AiFundCryptoShortPerformanceService",
        lambda: type("Service", (), {
            "get_snapshot": lambda *_args: {
                "status": "LIVE_TRADING_HOLD",
                "message": "검증 기준을 충족하지 않아 실거래 연결을 보류합니다.",
                "model_version": "lgbm_crypto_short_v1",
                "metrics": {"roc_auc": 0.61},
                "backtest": {"selected_rows": 20},
            }
        })(),
    )

    response = client.get(
        "/api/admin/ai-fund/crypto-short-performance",
        headers={"Authorization": "Bearer test-token"},
    )

    assert response.status_code == 200
    assert response.get_json()["status"] == "LIVE_TRADING_HOLD"



def test_upsert_toss_config_rejects_invalid_stock_market_allocation(client, monkeypatch):
    monkeypatch.setattr(admin_ai_fund_route, "safe_query_supabase_as_service_role", lambda *_args, **_kwargs: [])
    response = client.post(
        "/api/admin/ai-fund/configs",
        headers={"Authorization": "Bearer test-token"},
        json={
            "user_id": "00000000-0000-0000-0000-000000000001",
            "exchange_type": "toss",
            "asset_scope": "ALL",
            "kr_allocation_pct": 70,
            "us_allocation_pct": 20,
            "max_open_positions": 3,
        },
    )

    assert response.status_code == 400


def test_update_trade_intent_status_approves_or_rejects_pending_intent(client, monkeypatch):
    writes = []

    def fake_query(endpoint, method="GET", json_data=None, **_kwargs):
        writes.append((endpoint, method, json_data))
        return [{"id": "intent-1", "status": json_data["status"]}]

    monkeypatch.setattr(admin_ai_fund_route, "safe_query_supabase_as_service_role", fake_query)

    response = client.post(
        "/api/admin/ai-fund/intents/intent-1/approve",
        headers={"Authorization": "Bearer test-token"},
    )

    assert response.status_code == 200
    assert writes == [
        ("ai_fund_trade_intents?id=eq.intent-1&status=eq.PENDING", "PATCH", {"status": "APPROVED"})
    ]


def test_run_strategy_backtest_persists_result(client, monkeypatch):
    writes = []

    def fake_query(endpoint, method="GET", json_data=None, **_kwargs):
        writes.append((endpoint, method, json_data))
        if endpoint == "ai_fund_strategies":
            return [{
                "id": "strategy-1",
                "user_id": "user-1",
                "exchange_type": "coinone",
                "strategy_type": "DCA",
                "symbol": "BTC",
                "config": {
                    "reference_price": 100.0,
                    "trigger_drawdown_pct": 5.0,
                    "entry_amount": 10.0,
                    "max_entries": 1,
                },
            }]
        return [{"id": "backtest-1"}]

    monkeypatch.setattr(admin_ai_fund_route, "safe_query_supabase_as_service_role", fake_query)
    response = client.post(
        "/api/admin/ai-fund/strategies/strategy-1/backtests",
        headers={"Authorization": "Bearer test-token"},
        json={
            "candles": [
                {"timestamp": "2026-01-01T00:00:00Z", "close": 90.0},
                {"timestamp": "2026-01-01T01:00:00Z", "close": 100.0},
            ],
            "fee_bps": 10.0,
        },
    )

    assert response.status_code == 201
    assert writes[1][0] == "ai_fund_strategy_backtests"
    assert writes[1][2]["strategy_id"] == "strategy-1"
    assert writes[1][2]["result"]["trade_count"] == 1


def test_get_ai_fund_performance_returns_ledger_report(client, monkeypatch):
    service = type("Service", (), {"get_report": lambda *_args: {"total_pnl": 12.5, "pending_order_count": 1}})
    monkeypatch.setattr(admin_ai_fund_route, "AiFundPerformanceService", service)

    response = client.get(
        "/api/admin/ai-fund/performance?user_id=user-1&exchange_type=coinone",
        headers={"Authorization": "Bearer test-token"},
    )

    assert response.status_code == 200
    assert response.get_json()["performance"]["total_pnl"] == 12.5


def test_resume_ai_fund_operations_reactivates_circuit_breaker_config(client, monkeypatch):
    resumed = []

    class OperationsService:
        def resume(self, config_id):
            resumed.append(config_id)

    monkeypatch.setattr(admin_ai_fund_route, "AiFundOperationsService", OperationsService)
    response = client.post(
        "/api/admin/ai-fund/operations/config-1/resume",
        headers={"Authorization": "Bearer test-token"},
    )

    assert response.status_code == 200
    assert resumed == ["config-1"]


def test_get_ai_fund_operation_events_returns_config_audit_history(client, monkeypatch):
    monkeypatch.setattr(
        admin_ai_fund_route,
        "safe_query_supabase_as_service_role",
        lambda endpoint, **_kwargs: [{"event_type": "HALTED", "message": "대사 실패"}] if endpoint == "ai_fund_operation_events" else [],
    )

    response = client.get(
        "/api/admin/ai-fund/operations/config-1/events",
        headers={"Authorization": "Bearer test-token"},
    )

    assert response.status_code == 200
    assert response.get_json()["events"][0]["event_type"] == "HALTED"


def test_create_and_list_ai_fund_strategy(client, monkeypatch):
    writes = []

    def fake_query(endpoint, method="GET", json_data=None, **_kwargs):
        writes.append((endpoint, method, json_data))
        if method == "GET":
            return [{"id": "strategy-1", "strategy_type": "DCA", "symbol": "BTC", "status": "PAUSED"}]
        return [{"id": "strategy-1", **json_data}]

    monkeypatch.setattr(admin_ai_fund_route, "safe_query_supabase_as_service_role", fake_query)
    create_response = client.post(
        "/api/admin/ai-fund/strategies",
        headers={"Authorization": "Bearer test-token"},
        json={
            "user_id": "user-1",
            "exchange_type": "coinone",
            "strategy_type": "DCA",
            "symbol": "BTC",
            "config": {
                "reference_price": 100.0,
                "trigger_drawdown_pct": 5.0,
                "entry_amount": 10.0,
                "max_entries": 3,
            },
        },
    )
    list_response = client.get(
        "/api/admin/ai-fund/strategies?user_id=user-1&exchange_type=coinone",
        headers={"Authorization": "Bearer test-token"},
    )

    assert create_response.status_code == 201
    assert writes[0][2]["status"] == "PAUSED"
    assert list_response.status_code == 200
    assert list_response.get_json()["strategies"][0]["id"] == "strategy-1"


def test_update_strategy_status_and_list_pending_trade_intents(client, monkeypatch):
    writes = []

    def fake_query(endpoint, method="GET", json_data=None, **_kwargs):
        writes.append((endpoint, method, json_data))
        if endpoint == "ai_fund_trade_intents":
            return [{"id": "intent-1", "status": "PENDING", "symbol": "BTC"}]
        return [{"id": "strategy-1", "status": json_data["status"]}]

    monkeypatch.setattr(admin_ai_fund_route, "safe_query_supabase_as_service_role", fake_query)
    status_response = client.post(
        "/api/admin/ai-fund/strategies/strategy-1/status",
        headers={"Authorization": "Bearer test-token"},
        json={"status": "RUNNING"},
    )
    intents_response = client.get(
        "/api/admin/ai-fund/intents?user_id=user-1&exchange_type=coinone&status=PENDING",
        headers={"Authorization": "Bearer test-token"},
    )

    assert status_response.status_code == 200
    assert writes[0] == ("ai_fund_strategies?id=eq.strategy-1", "PATCH", {"status": "RUNNING"})
    assert intents_response.status_code == 200
    assert intents_response.get_json()["intents"][0]["status"] == "PENDING"
