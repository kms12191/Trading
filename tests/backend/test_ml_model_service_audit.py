from backend.services import ml_model_service


def test_infer_asset_key_for_split_stock_models():
    assert (
        ml_model_service.infer_asset_key_for_model(
            "STOCK",
            "ml/configs/lgbm_kr_stock_v1.yaml",
            "lgbm_kr_stock_signal_v1",
        )
        == "kr_stock"
    )
    assert (
        ml_model_service.infer_asset_key_for_model(
            "STOCK",
            "ml/configs/lgbm_us_stock_v1.yaml",
            "lgbm_us_stock_signal_v1",
        )
        == "us_stock"
    )
    assert ml_model_service.infer_asset_key_for_model("STOCK", "ml/configs/lgbm_stock_v11.yaml", "lgbm_stock_signal_v11") == "stock"
    assert ml_model_service.infer_asset_key_for_model("CRYPTO", "ml/configs/lgbm_crypto_v9.yaml", "lgbm_crypto_signal_v9") == "crypto"


def test_training_audit_bundle_routes_kr_stock_to_split_asset_key(monkeypatch):
    captured = {}

    def fake_guard(asset_key, auth_header, model_version):
        captured["asset_key"] = asset_key
        captured["model_version"] = model_version
        return {"passed": True}

    monkeypatch.setattr(ml_model_service, "build_promotion_guard_report", fake_guard)
    monkeypatch.setattr(ml_model_service, "build_serving_audit_report", lambda auth_header: {"status": "healthy"})

    result = ml_model_service.build_training_audit_bundle(
        auth_header="Bearer test",
        asset_type="STOCK",
        config_path="ml/configs/lgbm_kr_stock_v1.yaml",
        model_version="lgbm_kr_stock_signal_v1",
    )

    assert result["asset_key"] == "kr_stock"
    assert captured == {
        "asset_key": "kr_stock",
        "model_version": "lgbm_kr_stock_signal_v1",
    }


def test_promotion_candidate_accepts_zero_max_drawdown():
    candidate = {
        "version": "v1",
        "metrics": {
            "valid_rows": 1000,
            "time_series_cv_average": {
                "roc_auc": 0.6,
                "precision_at_top_10pct": 0.5,
            },
        },
        "risk_metrics": {
            "time_series_cv_average": {
                "roc_auc": 0.6,
            },
        },
        "backtests": {
            "composite": {
                "data": {
                    "excess_return_net": 0.01,
                    "precision_at_top_n": 0.6,
                    "max_drawdown_net": 0.0,
                }
            }
        },
    }
    dataset_quality = {"status": "healthy"}

    result = ml_model_service.evaluate_promotion_candidate(
        "stock",
        candidate,
        dataset_quality=dataset_quality,
    )

    max_drawdown_check = next(check for check in result["checks"] if check["name"] == "max_drawdown_net")
    assert max_drawdown_check["passed"] is True
    assert max_drawdown_check["actual"] == 0.0
