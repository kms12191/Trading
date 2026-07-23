from pathlib import Path
import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def test_lgbm_crypto_v10_config_schema():
    config_path = PROJECT_ROOT / "ml" / "configs" / "lgbm_crypto_v10.yaml"
    assert config_path.exists()

    with open(config_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    assert config["model"]["version"] == "lgbm_crypto_signal_v10"
    assert config["model"]["asset_type"] == "CRYPTO"
    
    feature_columns = config["model"]["feature_columns"]
    assert "kimchi_premium_pct" in feature_columns
    assert "binance_funding_rate" in feature_columns
    assert 0 < config["prediction"]["long_threshold"] < 1


def test_lgbm_crypto_risk_v10_config_schema():
    config_path = PROJECT_ROOT / "ml" / "configs" / "lgbm_crypto_risk_v10.yaml"
    assert config_path.exists()

    with open(config_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    assert config["model"]["version"] == "lgbm_crypto_risk_v10"
    assert config["model"]["asset_type"] == "CRYPTO"
