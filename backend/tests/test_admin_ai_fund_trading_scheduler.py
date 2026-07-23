from unittest.mock import MagicMock

import pytest

import backend.services.admin_ai_fund_trading_scheduler as scheduler


@pytest.fixture(autouse=True)
def bypass_approved_intent_execution(monkeypatch):
    class NoopReconciliationService:
        def __init__(self, *_args, **_kwargs):
            pass

        def reconcile_config(self, *_args, **_kwargs):
            return MagicMock(needs_review_count=0)

    class NoopOperationsService:
        def record_failure(self, *_args, **_kwargs):
            return False

        def record_success(self, *_args, **_kwargs):
            return None

    monkeypatch.setattr(scheduler, "_execute_approved_intents_for_config", lambda *_args: 0, raising=False)
    monkeypatch.setattr(scheduler, "_run_portfolio_rebalance_for_config", lambda *_args: 0, raising=False)
    monkeypatch.setattr(
        "backend.services.ai_fund_reconciliation.AiFundReconciliationService",
        NoopReconciliationService,
    )
    monkeypatch.setattr("backend.services.ai_fund_operations.AiFundOperationsService", NoopOperationsService)


def test_build_coinone_client_uses_user_api_key_credentials(monkeypatch):
    captured = {}

    class FakeCryptoHelper:
        def decrypt(self, value):
            return f"plain-{value}"

    class FakeCoinoneClient:
        def __init__(self, access_token, secret_key):
            captured["access_token"] = access_token
            captured["secret_key"] = secret_key

    monkeypatch.setattr(scheduler, "CryptoHelper", lambda *_args, **_kwargs: FakeCryptoHelper())
    monkeypatch.setattr(
        scheduler,
        "safe_query_supabase_as_service_role",
        lambda *_args, **_kwargs: [{
            "encrypted_access_key": "access",
            "encrypted_secret_key": "secret",
        }],
    )
    monkeypatch.setattr("backend.services.coinone_client.CoinoneClient", FakeCoinoneClient)

    client = scheduler._build_exchange_client("coinone", {"user_id": "admin-123"})

    assert isinstance(client, FakeCoinoneClient)
    assert captured == {
        "access_token": "plain-access",
        "secret_key": "plain-secret",
    }


def test_normalize_crypto_symbol_for_exchange_uses_coinone_currency_code():
    assert scheduler._normalize_crypto_symbol_for_exchange("coinone", "MKRUSDT") == "MKR"
    assert scheduler._normalize_crypto_symbol_for_exchange("coinone", "BTC") == "BTC"
    assert scheduler._normalize_crypto_symbol_for_exchange("binance", "MKRUSDT") == "MKRUSDT"


def test_build_binance_client_uses_user_api_key_credentials(monkeypatch):
    captured = {}

    class FakeCryptoHelper:
        def decrypt(self, value):
            return f"plain-{value}"

    class FakeBinanceClient:
        def __init__(self, api_key, secret_key, env):
            captured.update(api_key=api_key, secret_key=secret_key, env=env)

    monkeypatch.setattr(scheduler, "CryptoHelper", lambda *_args, **_kwargs: FakeCryptoHelper())
    monkeypatch.setattr(
        scheduler,
        "safe_query_supabase_as_service_role",
        lambda *_args, **_kwargs: [{"encrypted_access_key": "access", "encrypted_secret_key": "secret"}],
    )
    monkeypatch.setattr("backend.services.binance_client.BinanceClient", FakeBinanceClient)

    client = scheduler._build_exchange_client("binance", {"user_id": "admin-123", "broker_env": "MOCK"})

    assert isinstance(client, FakeBinanceClient)
    assert captured == {"api_key": "plain-access", "secret_key": "plain-secret", "env": "MOCK"}


def test_build_toss_client_uses_user_credentials_and_account_sequence(monkeypatch):
    captured = {}

    class FakeCryptoHelper:
        def decrypt(self, value):
            return f"plain-{value}"

    class FakeTossClient:
        def __init__(self, client_id, client_secret, account_seq, env, user_id):
            captured.update(
                client_id=client_id,
                client_secret=client_secret,
                account_seq=account_seq,
                env=env,
                user_id=user_id,
            )

    monkeypatch.setattr(scheduler, "CryptoHelper", lambda *_args, **_kwargs: FakeCryptoHelper())
    monkeypatch.setattr(
        scheduler,
        "safe_query_supabase_as_service_role",
        lambda *_args, **_kwargs: [{
            "encrypted_access_key": "access",
            "encrypted_secret_key": "secret",
            "toss_account_seq": "account-1",
        }],
    )
    monkeypatch.setattr("backend.services.toss_client.TossClient", FakeTossClient)

    client = scheduler._build_exchange_client("toss", {"user_id": "admin-123", "broker_env": "MOCK"})

    assert isinstance(client, FakeTossClient)
    assert captured == {
        "client_id": "plain-access",
        "client_secret": "plain-secret",
        "account_seq": "account-1",
        "env": "MOCK",
        "user_id": "admin-123",
    }


def test_strategy_templates_use_existing_binance_client_for_current_price(monkeypatch):
    prices = []

    class StrategyService:
        def run_active_strategies(self, _user_id, _exchange_type, price_resolver):
            prices.append(price_resolver("BTC"))
            return 1

    client = MagicMock()
    client.get_price.return_value = {"current_price": 123.0}
    monkeypatch.setattr("backend.services.ai_fund_strategy_service.AiFundStrategyService", StrategyService)

    created = scheduler._run_strategy_templates_for_config(
        {"user_id": "user-1", "exchange_type": "binance"},
        client,
    )

    assert created == 1
    assert prices == [123.0]


def test_run_ai_fund_cycle_reuses_signal_reads_per_threshold(monkeypatch):
    signal_reads = []
    executions = []

    class FakeTrader:
        def __init__(self, user_id, exchange_type):
            self.user_id = user_id
            self.exchange_type = exchange_type

        def evaluate_exit_signal(self, *_args, **_kwargs):
            return None

        def evaluate_and_execute_signal(self, **kwargs):
            executions.append((self.user_id, self.exchange_type, kwargs["symbol"]))
            return {"order_id": f"ord-{self.user_id}"}

    monkeypatch.setattr(
        scheduler,
        "_load_active_configs",
        lambda: [
            {"user_id": "admin-1", "exchange_type": "coinone", "min_signal_confidence": 0.75, "max_position_size": 100000},
            {"user_id": "admin-2", "exchange_type": "coinone", "min_signal_confidence": 0.75, "max_position_size": 100000},
        ],
    )
    monkeypatch.setattr(
        scheduler,
        "_read_crypto_signals",
        lambda min_confidence: signal_reads.append(min_confidence) or [{"symbol": "BTC", "confidence_score": 0.90}],
    )
    monkeypatch.setattr(scheduler, "_build_exchange_client", lambda *_args, **_kwargs: MagicMock())
    monkeypatch.setattr(scheduler, "_get_current_price_coinone", lambda _symbol: 50000000.0)
    monkeypatch.setattr("backend.services.admin_ai_managed_trader.AdminAiManagedTrader", FakeTrader)

    scheduler._run_ai_fund_cycle()

    assert signal_reads == [0.75]
    assert executions == [
        ("admin-1", "coinone", "BTC"),
        ("admin-2", "coinone", "BTC"),
    ]


def test_coinone_cycle_skips_unlisted_candidate_before_current_price_lookup(monkeypatch):
    price_lookups = []

    class FakeTrader:
        def __init__(self, *_args, **_kwargs):
            pass

        def list_open_positions(self):
            return []

        def is_symbol_tradable_on_exchange(self, symbol):
            assert symbol == "MKR"
            return False

        def evaluate_and_execute_signal(self, **_kwargs):
            pytest.fail("상장되지 않은 코인원 후보는 주문 평가를 하면 안 됩니다.")

    monkeypatch.setattr(scheduler, "_load_active_configs", lambda: [{
        "user_id": "user-1", "exchange_type": "coinone", "max_position_size": 10000, "min_signal_confidence": 0.3,
    }])
    monkeypatch.setattr(scheduler, "_read_crypto_signals", lambda *_args: [{"symbol": "MKRUSDT", "confidence_score": 0.31}])
    monkeypatch.setattr(scheduler, "_build_exchange_client", lambda *_args: MagicMock())
    monkeypatch.setattr(scheduler, "_resolve_current_price", lambda *_args: price_lookups.append(_args) or 100.0)
    monkeypatch.setattr("backend.services.admin_ai_managed_trader.AdminAiManagedTrader", FakeTrader)

    scheduler._run_ai_fund_cycle()

    assert price_lookups == []


def test_coinone_cycle_uses_next_listed_candidate_after_unlisted_top_signal(monkeypatch):
    executions = []
    price_lookups = []

    class FakeTrader:
        def __init__(self, *_args, **_kwargs):
            pass

        def list_open_positions(self):
            return []

        def is_symbol_tradable_on_exchange(self, symbol):
            return symbol == "BTC"

        def evaluate_and_execute_signal(self, **kwargs):
            executions.append(kwargs["symbol"])
            return {"order_id": "coinone-order"}

    monkeypatch.setattr(scheduler, "_load_active_configs", lambda: [{
        "user_id": "user-1", "exchange_type": "coinone", "max_position_size": 10000, "min_signal_confidence": 0.3,
    }])
    monkeypatch.setattr(scheduler, "_read_crypto_signals", lambda *_args: [
        {"symbol": "MKRUSDT", "confidence_score": 0.31},
        {"symbol": "BTCUSDT", "confidence_score": 0.30},
    ])
    monkeypatch.setattr(scheduler, "_build_exchange_client", lambda *_args: MagicMock())
    monkeypatch.setattr(scheduler, "_resolve_current_price", lambda _exchange, symbol, _client: price_lookups.append(symbol) or 100.0)
    monkeypatch.setattr("backend.services.admin_ai_managed_trader.AdminAiManagedTrader", FakeTrader)

    scheduler._run_ai_fund_cycle()

    assert price_lookups == ["BTC"]
    assert executions == ["BTC"]


def test_run_ai_fund_cycle_does_not_dry_run_when_supported_exchange_has_no_credentials(monkeypatch):
    writes = []

    monkeypatch.setattr(
        scheduler,
        "_load_active_configs",
        lambda: [
            {"user_id": "admin-1", "exchange_type": "coinone", "min_signal_confidence": 0.75, "max_position_size": 100000},
        ],
    )
    monkeypatch.setattr(
        scheduler,
        "_read_crypto_signals",
        lambda _min_confidence: [{"symbol": "BTC", "confidence_score": 0.90}],
    )
    monkeypatch.setattr(scheduler, "_build_exchange_client", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        "backend.services.supabase_client.safe_query_supabase_as_service_role",
        lambda *args, **kwargs: writes.append((args, kwargs)),
    )

    scheduler._run_ai_fund_cycle()

    assert writes == []


def test_run_ai_fund_cycle_records_exchange_client_failure_for_circuit_breaker(monkeypatch):
    failures = []

    class OperationsService:
        def record_failure(self, config, message):
            failures.append((config["id"], message))
            return False

        def record_success(self, *_args):
            return None

    monkeypatch.setattr(scheduler, "_load_active_configs", lambda: [
        {"id": "config-1", "user_id": "user-1", "exchange_type": "coinone", "max_position_size": 100.0}
    ])
    monkeypatch.setattr(scheduler, "_build_exchange_client", lambda *_args: None)
    monkeypatch.setattr("backend.services.ai_fund_operations.AiFundOperationsService", OperationsService)

    scheduler._run_ai_fund_cycle()

    assert failures == [("config-1", "거래소 주문 클라이언트를 생성할 수 없습니다.")]


def test_toss_cycle_uses_stock_candidates_without_reading_crypto_signals(monkeypatch):
    executions = []

    class FakeTrader:
        def __init__(self, user_id, exchange_type):
            self.user_id = user_id
            self.exchange_type = exchange_type

        def list_open_positions(self):
            return []

        def evaluate_exit_signal(self, *_args, **_kwargs):
            return None

        def evaluate_and_execute_signal(self, **kwargs):
            executions.append(kwargs)
            return {"order_id": "toss-order"}

    monkeypatch.setattr(
        scheduler,
        "_load_active_configs",
        lambda: [{
            "user_id": "user-1",
            "exchange_type": "toss",
            "max_position_size": 100000,
            "min_signal_confidence": 0.75,
            "asset_scope": "ALL",
            "max_open_positions": 2,
        }],
    )
    monkeypatch.setattr(scheduler, "_read_crypto_signals", lambda *_args: pytest.fail("토스는 코인 신호를 읽으면 안 됩니다."))
    monkeypatch.setattr(scheduler, "_build_exchange_client", lambda *_args: MagicMock())
    monkeypatch.setattr(scheduler, "_resolve_current_price", lambda *_args: 200.0)
    monkeypatch.setattr(scheduler, "_run_strategy_templates_for_config", lambda *_args: 0)
    monkeypatch.setattr(
        "backend.services.ai_fund_stock_selection.AiFundStockSelectionService.select_candidates",
        lambda *_args, **_kwargs: [{
            "symbol": "AAPL",
            "confidence_score": 0.91,
            "signal_id": "stock:US:v1:2026-07-22:AAPL",
        }],
    )
    monkeypatch.setattr("backend.services.admin_ai_managed_trader.AdminAiManagedTrader", FakeTrader)

    scheduler._run_ai_fund_cycle()

    assert [(item["symbol"], item["signal_type"]) for item in executions] == [("AAPL", "BUY")]


def test_run_ai_fund_cycle_checks_exit_positions_before_buy_signals(monkeypatch):
    executions = []

    class FakeTrader:
        def __init__(self, user_id, exchange_type):
            self.user_id = user_id
            self.exchange_type = exchange_type

        def list_open_positions(self):
            return [{"symbol": "ETH"}]

        def evaluate_exit_signal(self, symbol, current_price):
            if symbol == "ETH" and current_price == 3200000.0:
                return {"symbol": "ETH", "signal_type": "SELL", "reason": "TAKE_PROFIT", "quantity": 0.5}
            return None

        def evaluate_and_execute_signal(self, **kwargs):
            executions.append((kwargs["signal_type"], kwargs["symbol"]))
            return {"order_id": "sell-eth"}

    monkeypatch.setattr(
        scheduler,
        "_load_active_configs",
        lambda: [
            {"user_id": "admin-1", "exchange_type": "coinone", "min_signal_confidence": 0.75, "max_position_size": 100000},
        ],
    )
    monkeypatch.setattr(
        scheduler,
        "_read_crypto_signals",
        lambda _min_confidence: [{"symbol": "BTC", "confidence_score": 0.90}],
    )
    monkeypatch.setattr(scheduler, "_build_exchange_client", lambda *_args, **_kwargs: MagicMock())
    monkeypatch.setattr(
        scheduler,
        "_get_current_price_coinone",
        lambda symbol: 3200000.0 if symbol == "ETH" else 50000000.0,
    )
    monkeypatch.setattr("backend.services.admin_ai_managed_trader.AdminAiManagedTrader", FakeTrader)

    scheduler._run_ai_fund_cycle()

    assert executions[0] == ("SELL", "ETH")


def test_run_ai_fund_cycle_persists_exit_policy_after_exit_order(monkeypatch):
    recorded_policies = []

    class Trader:
        def __init__(self, *_args, **_kwargs):
            pass

        def list_open_positions(self):
            return [{"symbol": "ETH"}]

        def evaluate_exit_signal(self, symbol, current_price):
            return {
                "symbol": symbol,
                "signal_type": "SELL",
                "reason": "TAKE_PROFIT_1",
                "quantity": 0.5,
                "next_policy": {"completed_take_profit_steps": [0]},
            }

        def evaluate_and_execute_signal(self, **_kwargs):
            return {"status": "SUBMITTED"}

        def record_exit_policy(self, symbol, policy):
            recorded_policies.append((symbol, policy))

    monkeypatch.setattr("backend.services.admin_ai_managed_trader.AdminAiManagedTrader", Trader)
    monkeypatch.setattr(scheduler, "_load_active_configs", lambda: [
        {"user_id": "user-1", "exchange_type": "coinone", "is_active": True, "min_signal_confidence": 0.75, "max_position_size": 100.0}
    ])
    monkeypatch.setattr(scheduler, "_build_exchange_client", lambda *_args: MagicMock())
    monkeypatch.setattr(scheduler, "_get_current_price_coinone", lambda *_args: 100.0)
    monkeypatch.setattr("backend.services.ai_fund_reconciliation.AiFundReconciliationService", MagicMock())
    monkeypatch.setattr("backend.services.ai_fund_ledger.AiFundLedger", MagicMock())

    scheduler._run_ai_fund_cycle()

    assert recorded_policies == [("ETH", {"completed_take_profit_steps": [0]})]


def test_run_ai_fund_cycle_evaluates_strategy_templates_before_ml_buy(monkeypatch):
    evaluated = []

    class FakeTrader:
        def __init__(self, *_args, **_kwargs):
            pass

        def list_open_positions(self):
            return []

        def evaluate_and_execute_signal(self, **_kwargs):
            return None

    monkeypatch.setattr(scheduler, "_load_active_configs", lambda: [
        {"user_id": "user-1", "exchange_type": "coinone", "min_signal_confidence": 0.75, "max_position_size": 100.0}
    ])
    monkeypatch.setattr(scheduler, "_build_exchange_client", lambda *_args: MagicMock())
    monkeypatch.setattr(scheduler, "_read_crypto_signals", lambda *_args: [])
    monkeypatch.setattr(scheduler, "_run_strategy_templates_for_config", lambda config, *_args: evaluated.append(config["user_id"]) or 1)
    monkeypatch.setattr("backend.services.admin_ai_managed_trader.AdminAiManagedTrader", FakeTrader)
    reconciliation = MagicMock()
    reconciliation.return_value.reconcile_config.return_value = MagicMock(needs_review_count=0)
    monkeypatch.setattr("backend.services.ai_fund_reconciliation.AiFundReconciliationService", reconciliation)

    scheduler._run_ai_fund_cycle()

    assert evaluated == ["user-1"]


def test_run_ai_fund_cycle_executes_approved_intents_after_strategy_evaluation(monkeypatch):
    events = []

    class FakeTrader:
        def __init__(self, *_args, **_kwargs):
            pass

        def list_open_positions(self):
            return []

        def evaluate_and_execute_signal(self, **_kwargs):
            events.append("ml_buy")
            return None

    monkeypatch.setattr(scheduler, "_load_active_configs", lambda: [
        {"user_id": "user-1", "exchange_type": "coinone", "min_signal_confidence": 0.75, "max_position_size": 100.0}
    ])
    monkeypatch.setattr(scheduler, "_build_exchange_client", lambda *_args: MagicMock())
    monkeypatch.setattr(scheduler, "_read_crypto_signals", lambda *_args: [{"symbol": "BTC", "confidence_score": 0.9}])
    monkeypatch.setattr(scheduler, "_get_current_price_coinone", lambda *_args: 100.0)
    monkeypatch.setattr(scheduler, "_run_strategy_templates_for_config", lambda _config, *_args: events.append("strategy") or 1)
    monkeypatch.setattr(
        scheduler,
        "_execute_approved_intents_for_config",
        lambda _config, _client: events.append("approved") or 1,
        raising=False,
    )
    monkeypatch.setattr("backend.services.admin_ai_managed_trader.AdminAiManagedTrader", FakeTrader)
    reconciliation = MagicMock()
    reconciliation.return_value.reconcile_config.return_value = MagicMock(needs_review_count=0)
    monkeypatch.setattr("backend.services.ai_fund_reconciliation.AiFundReconciliationService", reconciliation)

    scheduler._run_ai_fund_cycle()

    assert events[:2] == ["strategy", "approved"]


def test_run_ai_fund_cycle_plans_rebalance_before_approved_intent_execution(monkeypatch):
    events = []

    class FakeTrader:
        def __init__(self, *_args, **_kwargs):
            pass

        def list_open_positions(self):
            return []

        def evaluate_and_execute_signal(self, **_kwargs):
            return None

    monkeypatch.setattr(scheduler, "_load_active_configs", lambda: [
        {"user_id": "user-1", "exchange_type": "coinone", "min_signal_confidence": 0.75, "max_position_size": 100.0}
    ])
    monkeypatch.setattr(scheduler, "_build_exchange_client", lambda *_args: MagicMock())
    monkeypatch.setattr(scheduler, "_read_crypto_signals", lambda *_args: [])
    monkeypatch.setattr(scheduler, "_run_strategy_templates_for_config", lambda _config, *_args: events.append("strategy") or 0)
    monkeypatch.setattr(scheduler, "_run_portfolio_rebalance_for_config", lambda _config, *_args: events.append("rebalance") or 1, raising=False)
    monkeypatch.setattr(scheduler, "_execute_approved_intents_for_config", lambda *_args: events.append("approved") or 0)
    monkeypatch.setattr("backend.services.admin_ai_managed_trader.AdminAiManagedTrader", FakeTrader)

    scheduler._run_ai_fund_cycle()

    assert events == ["strategy", "rebalance", "approved"]


def test_run_ai_fund_cycle_reconciles_orders_before_reading_buy_signals(monkeypatch):
    events = []

    class FakeTrader:
        def __init__(self, *_args, **_kwargs):
            pass

        def list_open_positions(self):
            return []

        def evaluate_and_execute_signal(self, **_kwargs):
            events.append("buy")
            return None

    class FakeReconciliationService:
        def __init__(self, _ledger):
            pass

        def reconcile_config(self, _config, _client):
            events.append("reconcile")

    monkeypatch.setattr(
        scheduler,
        "_load_active_configs",
        lambda: [{"user_id": "admin-1", "exchange_type": "coinone", "min_signal_confidence": 0.75, "max_position_size": 100000}],
    )
    monkeypatch.setattr(scheduler, "_read_crypto_signals", lambda _score: [{"symbol": "BTC", "confidence_score": 0.9}])
    monkeypatch.setattr(scheduler, "_build_exchange_client", lambda *_args: MagicMock())
    monkeypatch.setattr(scheduler, "_get_current_price_coinone", lambda _symbol: 50000000.0)
    monkeypatch.setattr("backend.services.admin_ai_managed_trader.AdminAiManagedTrader", FakeTrader)
    monkeypatch.setattr("backend.services.ai_fund_reconciliation.AiFundReconciliationService", FakeReconciliationService)
    monkeypatch.setattr("backend.services.ai_fund_ledger.AiFundLedger", MagicMock())

    scheduler._run_ai_fund_cycle()

    assert events[:2] == ["reconcile", "buy"]
