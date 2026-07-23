import json

from backend.services.ai_fund_crypto_short_performance import AiFundCryptoShortPerformanceService


def test_short_performance_holds_live_trading_when_backtest_is_not_profitable(tmp_path):
    metrics_path = tmp_path / "metrics.json"
    backtest_path = tmp_path / "backtest.json"
    metrics_path.write_text(json.dumps({"roc_auc": 0.63}), encoding="utf-8")
    backtest_path.write_text(
        json.dumps(
            {
                "model_version": "lgbm_crypto_short_v1",
                "top_avg_future_return_net": -0.001,
                "selection_win_rate_net": 0.55,
                "max_drawdown_net": -0.1,
                "selected_rows": 30,
            }
        ),
        encoding="utf-8",
    )

    snapshot = AiFundCryptoShortPerformanceService(metrics_path, backtest_path).get_snapshot()

    assert snapshot["status"] == "LIVE_TRADING_HOLD"


def test_short_performance_converts_nan_metrics_to_json_null(tmp_path):
    metrics_path = tmp_path / "metrics.json"
    backtest_path = tmp_path / "backtest.json"
    metrics_path.write_text('{"roc_auc": NaN, "time_series_cv": [{"precision_at_top_10pct": NaN}]}', encoding="utf-8")
    backtest_path.write_text(json.dumps({"selected_rows": 0}), encoding="utf-8")

    snapshot = AiFundCryptoShortPerformanceService(metrics_path, backtest_path).get_snapshot()

    assert snapshot["metrics"]["roc_auc"] is None
    assert snapshot["metrics"]["time_series_cv"][0]["precision_at_top_10pct"] is None
    assert "NaN" not in json.dumps(snapshot, allow_nan=False)
