import json
from pathlib import Path

from backend.services import ml_serving_package_service


def test_build_serving_manifest_contains_runtime_contract(tmp_path, monkeypatch):
    model_path = tmp_path / "lgbm_kr_stock_signal_v1.joblib"
    risk_model_path = tmp_path / "lgbm_kr_stock_risk_v1.joblib"
    metrics_path = tmp_path / "lgbm_kr_stock_signal_v1.metrics.json"
    risk_metrics_path = tmp_path / "lgbm_kr_stock_risk_v1.metrics.json"
    config_path = tmp_path / "lgbm_kr_stock_v1.yaml"
    predictions_path = tmp_path / "kr_stock_predictions_lgbm_v1.csv"

    for path in (model_path, risk_model_path, metrics_path, risk_metrics_path, predictions_path):
        path.write_text("artifact", encoding="utf-8")

    config_path.write_text(
        """
model:
  model_version: lgbm_kr_stock_signal_v1
  feature_columns:
    - close
    - dart_disclosure_count_20d
prediction:
  policy_version: kr_policy_constrained_20260714_v1
  long_threshold: 0.55
""".strip(),
        encoding="utf-8",
    )

    monkeypatch.setattr(
        ml_serving_package_service,
        "resolve_active_model_selection",
        lambda asset_key, auth_header: {
            "selection_status": "serving",
            "serving_version": "v1",
            "recommended_version": None,
            "latest_version": "v1",
            "active_result": {
                "version": "v1",
                "asset_type": "STOCK_KR",
                "config_path": str(config_path),
                "metrics_path": str(metrics_path),
                "risk_metrics_path": str(risk_metrics_path),
                "predictions_path": str(predictions_path),
                "metrics": {
                    "model_version": "lgbm_kr_stock_signal_v1",
                    "feature_columns": ["close", "dart_disclosure_count_20d"],
                    "valid_end_date": "2026-07-14 00:00:00",
                },
                "risk_metrics": {
                    "model_version": "lgbm_kr_stock_risk_v1",
                    "feature_columns": ["close", "dart_disclosure_count_20d"],
                },
                "backtests": {
                    "composite": {
                        "data": {
                            "excess_return_net": 0.0101,
                            "precision_at_top_n": 0.5217,
                            "max_drawdown_net": -0.1281,
                        }
                    }
                },
            },
        },
    )

    manifest = ml_serving_package_service.build_serving_manifest("kr_stock", None)

    assert manifest["schema_version"] == 1
    assert manifest["asset_key"] == "kr_stock"
    assert manifest["asset_type"] == "STOCK_KR"
    assert manifest["model_version"] == "lgbm_kr_stock_signal_v1"
    assert manifest["risk_model_version"] == "lgbm_kr_stock_risk_v1"
    assert manifest["policy_version"] == "kr_policy_constrained_20260714_v1"
    assert manifest["feature_columns"] == ["close", "dart_disclosure_count_20d"]
    assert manifest["data_end_date"] == "2026-07-14 00:00:00"
    assert manifest["selection_status"] == "serving"
    assert manifest["performance"]["composite_excess_return_net"] == 0.0101

    roles = {item["role"]: item for item in manifest["files"]}
    assert roles["model"]["required"] is True
    assert roles["risk_model"]["required"] is True
    assert roles["config"]["required"] is True
    assert roles["predictions_snapshot"]["required"] is False
    assert roles["model"]["source_path"] == str(model_path)
    assert roles["risk_model"]["source_path"] == str(risk_model_path)
    assert all("/data/raw/" not in item["package_path"] for item in manifest["files"])


def test_export_serving_package_copies_only_manifest_files(tmp_path, monkeypatch):
    source_dir = tmp_path / "source"
    source_dir.mkdir()
    model_path = source_dir / "model.joblib"
    config_path = source_dir / "config.yaml"
    raw_path = source_dir / "raw.csv"
    model_path.write_text("model", encoding="utf-8")
    config_path.write_text("config", encoding="utf-8")
    raw_path.write_text("raw", encoding="utf-8")

    monkeypatch.setattr(
        ml_serving_package_service,
        "build_serving_manifest",
        lambda asset_key, auth_header, include_predictions=True: {
            "schema_version": 1,
            "asset_key": asset_key,
            "model_version": "test_model",
            "package_name": "kr_stock-test_model",
            "feature_columns": ["close"],
            "files": [
                {
                    "role": "model",
                    "source_path": str(model_path),
                    "package_path": "models/model.joblib",
                    "required": True,
                    "exists": True,
                },
                {
                    "role": "config",
                    "source_path": str(config_path),
                    "package_path": "configs/config.yaml",
                    "required": True,
                    "exists": True,
                },
            ],
        },
    )

    result = ml_serving_package_service.export_serving_package(
        "kr_stock",
        None,
        output_root=tmp_path / "packages",
    )

    package_dir = Path(result["package_dir"])
    manifest = json.loads((package_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["asset_key"] == "kr_stock"
    assert (package_dir / "models" / "model.joblib").read_text(encoding="utf-8") == "model"
    assert (package_dir / "configs" / "config.yaml").read_text(encoding="utf-8") == "config"
    assert not (package_dir / "raw.csv").exists()


def test_export_serving_package_can_create_archive(tmp_path, monkeypatch):
    source_dir = tmp_path / "source"
    source_dir.mkdir()
    model_path = source_dir / "model.joblib"
    model_path.write_text("model", encoding="utf-8")

    monkeypatch.setattr(
        ml_serving_package_service,
        "build_serving_manifest",
        lambda asset_key, auth_header, include_predictions=True: {
            "schema_version": 1,
            "asset_key": asset_key,
            "model_version": "test_model",
            "package_name": "kr_stock-test_model",
            "feature_columns": ["close"],
            "files": [
                {
                    "role": "model",
                    "source_path": str(model_path),
                    "package_path": "models/model.joblib",
                    "required": True,
                    "exists": True,
                },
            ],
        },
    )

    result = ml_serving_package_service.export_serving_package(
        "kr_stock",
        None,
        output_root=tmp_path / "packages",
        create_archive=True,
    )

    assert result["archive_path"].endswith(".tar.gz")
    assert Path(result["archive_path"]).exists()
