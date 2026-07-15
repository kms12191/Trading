from backend.services.chatbot import tool_registry
from backend.services.chatbot.function_calling import FUNCTION_SCHEMAS
from flask import Flask

from backend.routes import trade


def test_price_question_routes_to_asset_price_lookup(monkeypatch):
    calls = []

    def fake_get_internal(path, auth_header, params=None):
        calls.append((path, params))
        if path == "/api/symbol/lookup":
            return {
                "data": {
                    "symbol": "RDDT",
                    "display_name": "Reddit",
                    "asset_type": "STOCK",
                    "market": "US",
                }
            }
        if path == "/api/chart/quote":
            return {
                "data": {
                    "symbol": "RDDT",
                    "exchange": "TOSS",
                    "current_price": 151.25,
                    "change_rate": 2.35,
                    "currency": "USD",
                }
            }
        if path == "/api/stocks/warnings":
            return {"data": {"warnings": []}}
        raise AssertionError(f"unexpected path: {path}")

    monkeypatch.setattr(tool_registry, "_get_internal", fake_get_internal)

    result = tool_registry.run_chatbot_tool("Bearer test", "Reddit 지금 얼마야")

    assert result is not None
    assert result["data"]["source"] == "ASSET_PRICE"
    assert result["data"]["symbol"] == "RDDT"
    assert "Reddit(RDDT) 현재가는 $151.25" in result["reply"]
    assert calls == [
        ("/api/symbol/lookup", {"query": "RDDT"}),
        ("/api/chart/quote", {"exchange": "TOSS", "symbol": "RDDT", "broker_env": "REAL"}),
        ("/api/stocks/warnings", {"symbol": "RDDT", "exchange": "TOSS", "broker_env": "REAL"}),
    ]


def test_chart_quote_includes_current_price_from_exchange_client(monkeypatch):
    class FakeClient:
        def get_price(self, symbol):
            assert symbol == "RDDT"
            return {"current_price": 151.25, "change_rate": 2.35}

    app = Flask(__name__)
    app.register_blueprint(trade.trade_bp)
    trade.PRICE_CHANGE_CACHE.clear()
    monkeypatch.setattr(trade, "get_cached_change_rate", lambda exchange, symbol, broker_env, auth_header: 2.35)
    monkeypatch.setattr(trade, "get_user_id_from_header", lambda auth_header: ("user-1", "token"))
    monkeypatch.setattr(
        trade,
        "_load_user_exchange_record",
        lambda auth_header, user_id, exchange, broker_env: ({"user_id": user_id}, "access", "secret"),
    )
    monkeypatch.setattr(
        trade,
        "_build_exchange_client",
        lambda exchange, broker_env, record, access_key, secret_key: FakeClient(),
    )

    response = app.test_client().get(
        "/api/chart/quote?exchange=TOSS&symbol=RDDT&broker_env=REAL",
        headers={"Authorization": "Bearer test"},
    )

    assert response.status_code == 200
    assert response.json["data"]["current_price"] == 151.25
    assert response.json["data"]["change_rate"] == 2.35


def test_invalid_numeric_stock_code_returns_symbol_not_found_before_quote(monkeypatch):
    calls = []

    def fake_get_internal(path, auth_header, params=None):
        calls.append((path, params))
        if path == "/api/symbol/lookup":
            raise RuntimeError("검색 결과가 없습니다.")
        if path == "/api/symbol/search":
            return {"data": {"items": []}}
        if path == "/api/chart/quote":
            raise AssertionError("invalid numeric stock code should not call quote API")
        raise AssertionError(f"unexpected path: {path}")

    monkeypatch.setattr(tool_registry, "_get_internal", fake_get_internal)

    result = tool_registry.get_asset_price("Bearer test", "999999 현재가 얼마야")

    assert result["data"]["reason"] == "symbol_not_found"
    assert result["data"]["query"] == "999999"
    assert [path for path, _ in calls] == ["/api/symbol/lookup", "/api/symbol/search"]


def test_orderbook_question_routes_to_orderbook_lookup(monkeypatch):
    calls = []

    def fake_get_internal(path, auth_header, params=None):
        calls.append((path, params))
        if path == "/api/symbol/lookup":
            return {
                "data": {
                    "symbol": "005930",
                    "display_name": "삼성전자",
                    "asset_type": "STOCK",
                    "market": "KR",
                }
            }
        if path == "/api/chart/orderbook":
            return {
                "data": {
                    "symbol": "005930",
                    "asks": [{"price": 75500, "size": 120}],
                    "bids": [{"price": 75400, "size": 95}],
                },
                "meta": {"source": "LIVE", "is_mock": False},
            }
        raise AssertionError(f"unexpected path: {path}")

    monkeypatch.setattr(tool_registry, "_get_internal", fake_get_internal)

    result = tool_registry.run_chatbot_tool("Bearer test", "삼성전자 호가 알려줘")

    assert result["data"]["source"] == "ASSET_ORDERBOOK"
    assert result["data"]["symbol"] == "005930"
    assert result["data"]["best_ask"]["price"] == 75500
    assert result["data"]["best_bid"]["price"] == 75400
    assert calls == [
        ("/api/symbol/lookup", {"query": "삼성전자"}),
        ("/api/chart/orderbook", {"exchange": "TOSS", "symbol": "005930", "broker_env": "REAL"}),
    ]


def test_portfolio_summary_omits_missing_optional_mock_accounts(monkeypatch):
    calls = []

    def fake_post_internal(path, auth_header, body=None):
        calls.append(body)
        exchange = body["exchange"]
        env = body["env"]
        if env == "MOCK" and exchange in {"TOSS", "COINONE"}:
            raise RuntimeError(f"등록된 {exchange} ({env}) API 키 정보가 없습니다.")
        return {
            "data": {
                "currency": "KRW",
                "total_evaluation": 1000,
                "available_cash": 100,
                "holdings": [],
            }
        }

    monkeypatch.setattr(tool_registry, "_post_internal", fake_post_internal)

    result = tool_registry.get_portfolio_summary("Bearer test", "내 자산 얼마 있어?")

    assert "TOSS MOCK 계좌 조회 실패" not in result["reply"]
    assert "COINONE MOCK 계좌 조회 실패" not in result["reply"]
    assert result["data"]["errors"] == []
    assert {"exchange": "TOSS", "env": "MOCK"} in calls


def test_recommendation_reference_defaults_to_real_when_env_is_not_explicit(monkeypatch):
    class FakeRepository:
        def load_recommendations(self, auth_header, user_id):
            return [{"symbol": "RDDT", "display_name": "Reddit"}]

    monkeypatch.setattr(tool_registry, "get_user_id_from_header", lambda auth_header: ("user-1", "token"))
    monkeypatch.setattr(tool_registry, "_conversation_repository", FakeRepository())

    rewritten, error = tool_registry._with_referenced_recommendation_symbol(
        "Bearer test",
        "1번 1주 매수 제안 만들어줘",
    )

    assert error is None
    assert rewritten == "RDDT 실거래 1번 1주 매수 제안 만들어줘"


def test_real_order_without_exchange_asks_exchange_before_price(monkeypatch):
    def fake_resolve_symbol(auth_header, query):
        assert query == "RDDT"
        return {
            "symbol": "RDDT",
            "display_name": "Reddit",
            "asset_type": "STOCK",
            "market": "US",
        }

    monkeypatch.setattr(tool_registry, "_resolve_symbol", fake_resolve_symbol)
    monkeypatch.setattr(
        tool_registry,
        "_run_chatbot_precheck",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("지정가 확인 전 사전검증 금지")),
    )

    result = tool_registry.create_trade_proposal_from_message(
        "Bearer test",
        "RDDT 실거래 1주 매수 제안 만들어줘",
    )

    assert result["data"]["reason"] == "missing_exchange"
    assert result["data"]["symbol"] == "RDDT"
    assert "거래소" in result["reply"]


def test_order_without_exchange_asks_for_exchange_before_price(monkeypatch):
    def fake_resolve_symbol(auth_header, query):
        assert query == "금호건설"
        return {
            "symbol": "002990",
            "display_name": "금호건설",
            "asset_type": "STOCK",
            "market": "KR",
        }

    monkeypatch.setattr(tool_registry, "_resolve_symbol", fake_resolve_symbol)
    monkeypatch.setattr(
        tool_registry,
        "_run_chatbot_precheck",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("가격 확인 전 사전검증 금지")),
    )

    result = tool_registry.create_trade_proposal_from_message(
        "Bearer test",
        "금호건설 1주사줘",
    )

    assert result["data"]["reason"] == "missing_exchange"
    assert result["data"]["symbol"] == "002990"
    assert "거래소" in result["reply"]
    assert "토스" in result["reply"]
    assert "KIS" in result["reply"]


def test_crypto_analysis_routes_to_market_context(monkeypatch):
    calls = []

    def fake_get_internal(path, auth_header, params=None):
        calls.append((path, params))
        if path == "/api/symbol/lookup":
            return {
                "data": {
                    "symbol": "XRP",
                    "display_name": "리플",
                    "asset_type": "CRYPTO",
                    "market": "KR",
                    "exchange": "COINONE",
                }
            }
        if path == "/api/chart/quote":
            return {
                "data": {
                    "symbol": "XRP",
                    "exchange": "COINONE",
                    "current_price": 4200,
                    "change_rate": 3.25,
                    "currency": "KRW",
                }
            }
        if path == "/api/chart/orderbook":
            return {
                "data": {
                    "asks": [{"price": 4210, "size": 1200}],
                    "bids": [{"price": 4195, "size": 950}],
                },
                "meta": {"source": "LIVE", "is_mock": False},
            }
        if path == "/api/chart/candles":
            return {
                "data": [
                    {"time": "2026-07-15T00:00:00+09:00", "open": 4000, "high": 4100, "low": 3980, "close": 4050},
                    {"time": "2026-07-15T01:00:00+09:00", "open": 4050, "high": 4220, "low": 4040, "close": 4200},
                ]
            }
        raise AssertionError(f"unexpected path: {path}")

    def fake_ml_outlook(auth_header, message, symbol_data):
        return {
            "reply": "리플(XRP) 질문은 ML 활성 신호 기준으로 보면 매수 후보입니다.",
            "data": {
                "source": "ML_ACTIVE_SIGNAL",
                "asset_key": "crypto",
                "symbol": "XRP",
                "prediction": {
                    "position": "LONG",
                    "signal_grade": "B",
                    "up_probability": 0.61,
                    "risk_probability": 0.18,
                    "signal_score": 0.43,
                    "model_version": "lgbm_crypto_signal_v9",
                },
            },
        }

    monkeypatch.setattr(tool_registry, "_get_internal", fake_get_internal)
    monkeypatch.setattr(tool_registry, "build_single_asset_ml_outlook", fake_ml_outlook)

    result = tool_registry.run_chatbot_tool("Bearer test", "리플 코인 분석해줘")

    assert result is not None
    assert result["data"]["source"] == "CRYPTO_MARKET_CONTEXT"
    assert result["data"]["symbol"] == "XRP"
    assert result["data"]["exchange"] == "COINONE"
    assert result["data"]["quote"]["current_price"] == 4200
    assert result["data"]["orderbook"]["best_ask"]["price"] == 4210
    assert result["data"]["liquidity"]["spread_rate"] == 0.36
    assert result["data"]["liquidity"]["estimated_buy_slippage_rate"] == 0.24
    assert result["data"]["candles"]["interval"] == "1h"
    assert result["data"]["ml"]["prediction"]["model_version"] == "lgbm_crypto_signal_v9"
    assert "24시간 거래되는 가상자산" in result["reply"]
    assert "스프레드" in result["reply"]
    assert "Coinone는 KRW 현물" in result["reply"]
    assert calls == [
        ("/api/symbol/lookup", {"query": "XRP"}),
        ("/api/chart/quote", {"exchange": "COINONE", "symbol": "XRP", "broker_env": "REAL"}),
        ("/api/chart/orderbook", {"exchange": "COINONE", "symbol": "XRP", "broker_env": "REAL"}),
        ("/api/chart/candles", {"exchange": "COINONE", "symbol": "XRP", "interval": "1h", "count": 24, "broker_env": "REAL"}),
    ]


def test_function_schemas_include_crypto_market_context():
    schema = next((item for item in FUNCTION_SCHEMAS if item["name"] == "get_crypto_market_context"), None)

    assert schema is not None
    assert schema["parameters"]["required"] == ["query"]
    assert "query" in schema["parameters"]["properties"]


def test_crypto_context_keeps_binance_futures_exchange(monkeypatch):
    requested_exchanges = []

    def fake_get_internal(path, auth_header, params=None):
        if path == "/api/symbol/lookup":
            return {
                "data": {
                    "symbol": "BTC",
                    "display_name": "비트코인",
                    "asset_type": "CRYPTO",
                    "market": "GLOBAL",
                }
            }
        if path in {"/api/chart/quote", "/api/chart/orderbook", "/api/chart/candles"}:
            requested_exchanges.append(params["exchange"])
        if path == "/api/chart/quote":
            return {"data": {"current_price": 120000, "change_rate": 1.2, "currency": "USD"}}
        if path == "/api/chart/orderbook":
            return {"data": {"asks": [{"price": 120010, "size": 1}], "bids": [{"price": 119990, "size": 1}]}}
        if path == "/api/chart/candles":
            return {"data": [{"close": 119000}, {"close": 120000}]}
        raise AssertionError(f"unexpected path: {path}")

    monkeypatch.setattr(tool_registry, "_get_internal", fake_get_internal)
    monkeypatch.setattr(tool_registry, "build_single_asset_ml_outlook", lambda auth_header, message, symbol_data: None)

    result = tool_registry.run_chatbot_tool("Bearer test", "바이낸스 선물 BTC 코인 분석해줘")

    assert result["data"]["exchange"] == "BINANCE_UM_FUTURES"
    assert requested_exchanges == ["BINANCE_UM_FUTURES", "BINANCE_UM_FUTURES", "BINANCE_UM_FUTURES"]
    assert "Binance USD-M 선물" in result["reply"]


def test_crypto_context_includes_user_holding_snapshot(monkeypatch):
    def fake_get_internal(path, auth_header, params=None):
        if path == "/api/symbol/lookup":
            return {"data": {"symbol": "XRP", "display_name": "리플", "asset_type": "CRYPTO"}}
        if path == "/api/chart/quote":
            return {"data": {"current_price": 4200, "change_rate": 1.5, "currency": "KRW"}}
        if path == "/api/chart/orderbook":
            return {"data": {"asks": [{"price": 4210, "size": 1200}], "bids": [{"price": 4190, "size": 1000}]}}
        if path == "/api/chart/candles":
            return {"data": [{"close": 4100}, {"close": 4200}]}
        raise AssertionError(f"unexpected path: {path}")

    def fake_post_internal(path, auth_header, body=None):
        assert path == "/api/dashboard/balance"
        if body == {"exchange": "COINONE", "env": "REAL"}:
            return {
                "data": {
                    "currency": "KRW",
                    "total_evaluation": 1_000_000,
                    "holdings": [
                        {
                            "symbol": "XRP",
                            "currency": "XRP",
                            "quantity": 100,
                            "avg_price": 4000,
                            "profit_rate": 5.0,
                            "evaluation": 420000,
                        }
                    ],
                }
            }
        raise RuntimeError("등록된 계좌가 없습니다.")

    monkeypatch.setattr(tool_registry, "_get_internal", fake_get_internal)
    monkeypatch.setattr(tool_registry, "_post_internal", fake_post_internal)
    monkeypatch.setattr(tool_registry, "build_single_asset_ml_outlook", lambda auth_header, message, symbol_data: None)

    result = tool_registry.run_chatbot_tool("Bearer test", "내 리플 코인 팔까 분석해줘")

    assert result["data"]["holding"]["quantity"] == 100
    assert result["data"]["holding"]["avg_price"] == 4000
    assert result["data"]["holding"]["profit_rate"] == 5.0
    assert result["data"]["holding"]["portfolio_weight_rate"] == 42.0
    assert "보유: 100 XRP" in result["reply"]


def test_crypto_context_includes_kimchi_premium_for_coinone(monkeypatch):
    def fake_get_internal(path, auth_header, params=None):
        if path == "/api/symbol/lookup":
            return {"data": {"symbol": "BTC", "display_name": "비트코인", "asset_type": "CRYPTO"}}
        if path == "/api/chart/quote" and params["exchange"] == "COINONE":
            return {"data": {"current_price": 100_000_000, "change_rate": 0.5, "currency": "KRW"}}
        if path == "/api/chart/quote" and params["exchange"] == "BINANCE":
            return {"data": {"current_price": 66_000, "change_rate": 0.4, "currency": "USD"}}
        if path == "/api/chart/orderbook":
            return {"data": {"asks": [{"price": 100_100_000, "size": 0.4}], "bids": [{"price": 99_900_000, "size": 0.3}]}}
        if path == "/api/chart/candles":
            return {"data": [{"close": 99_000_000}, {"close": 100_000_000}]}
        if path == "/api/market/exchange-rate":
            return {"data": {"rate": 1500.0, "base_currency": "USDT", "quote_currency": "KRW", "source": "COINONE_USDT_KRW"}}
        raise AssertionError(f"unexpected path: {path}")

    monkeypatch.setattr(tool_registry, "_get_internal", fake_get_internal)
    monkeypatch.setattr(tool_registry, "build_single_asset_ml_outlook", lambda auth_header, message, symbol_data: None)

    result = tool_registry.run_chatbot_tool("Bearer test", "비트코인 코인 분석해줘")

    assert result["data"]["premium"]["premium_rate"] == 1.01
    assert result["data"]["premium"]["coinone_price_krw"] == 100_000_000
    assert result["data"]["premium"]["binance_price_krw"] == 99_000_000
    assert "김치프리미엄" in result["reply"]


def test_toss_mock_order_is_blocked_before_precheck(monkeypatch):
    monkeypatch.setattr(tool_registry, "_resolve_symbol", lambda auth_header, query: {
        "symbol": "002990",
        "display_name": "금호건설",
        "asset_type": "STOCK",
        "market": "KR",
    })
    monkeypatch.setattr(
        tool_registry,
        "_run_chatbot_precheck",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("지원하지 않는 모의 환경은 사전검증 호출 금지")),
    )

    result = tool_registry.create_trade_proposal_from_message(
        "Bearer test",
        "토스 금호건설 1주 모의 지정가 3500원에 사줘",
    )

    assert result["data"]["reason"] == "unsupported_broker_env"
    assert result["data"]["exchange"] == "TOSS"
    assert result["data"]["broker_env"] == "MOCK"
    assert "모의" in result["reply"]
    assert "지원하지 않습니다" in result["reply"]


def test_coinone_mock_order_is_blocked_before_precheck(monkeypatch):
    monkeypatch.setattr(tool_registry, "_resolve_symbol", lambda auth_header, query: {
        "symbol": "XRP",
        "display_name": "XRP",
        "asset_type": "CRYPTO",
        "market": "KR",
    })
    monkeypatch.setattr(
        tool_registry,
        "_run_chatbot_precheck",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("지원하지 않는 모의 환경은 사전검증 호출 금지")),
    )

    result = tool_registry.create_trade_proposal_from_message(
        "Bearer test",
        "코인원 XRP 10개 모의 지정가 800원에 사줘",
    )

    assert result["data"]["reason"] == "unsupported_broker_env"
    assert result["data"]["exchange"] == "COINONE"
    assert result["data"]["broker_env"] == "MOCK"
    assert "모의" in result["reply"]
    assert "지원하지 않습니다" in result["reply"]


def test_non_toss_order_without_env_asks_env_and_price(monkeypatch):
    def fake_resolve_symbol(auth_header, query):
        assert query == "삼성전자"
        return {
            "symbol": "005930",
            "display_name": "삼성전자",
            "asset_type": "STOCK",
            "market": "KR",
        }

    monkeypatch.setattr(tool_registry, "_resolve_symbol", fake_resolve_symbol)
    monkeypatch.setattr(
        tool_registry,
        "_run_chatbot_precheck",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("환경 확인 전 사전검증 금지")),
    )

    result = tool_registry.create_trade_proposal_from_message(
        "Bearer test",
        "KIS 삼성전자 1주사줘",
    )

    assert result["data"]["reason"] == "missing_order_env_and_price"
    assert "실거래" in result["reply"]
    assert "모의" in result["reply"]
    assert "지정가" in result["reply"]
