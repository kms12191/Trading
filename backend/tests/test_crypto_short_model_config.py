from pathlib import Path

import yaml

from backend.services.ml_automation_service import resolve_automation_preset

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def test_crypto_short_config_has_dedicated_model_and_backtest_paths():
    config_path = PROJECT_ROOT / "ml" / "configs" / "lgbm_crypto_short_v1.yaml"
    assert config_path.exists()

    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))

    assert config["model"]["version"] == "lgbm_crypto_short_v1"
    assert config["model"]["target_column"] == "residual_risk_label"
    assert config["prediction"]["short_entry_threshold"] > 0
    assert config["backtest"]["funding_bps_per_horizon"] >= 0
    assert config["data"]["backtest_short_summary_path"].endswith(".json")


def test_crypto_v10_automation_preset_includes_short_model():
    preset = resolve_automation_preset("crypto-v10-full")

    assert preset["training"]["short_config"] == "ml/configs/lgbm_crypto_short_v1.yaml"
