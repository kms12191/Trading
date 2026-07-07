from pathlib import Path

import yaml


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def load_config(name: str) -> dict:
    return yaml.safe_load((PROJECT_ROOT / "ml" / "configs" / name).read_text(encoding="utf-8"))


def test_kr_stock_config_uses_separate_paths_and_dart_features():
    config = load_config("lgbm_kr_stock_v1.yaml")
    risk_config = load_config("lgbm_kr_stock_risk_v1.yaml")

    assert config["data"]["raw_candles_path"] == "data/raw/kr_stock_candles.csv"
    assert config["data"]["features_path"] == "data/processed/kr_stock_features_lgbm_v1.csv"
    assert config["model"]["version"] == "lgbm_kr_stock_signal_v1"
    assert config["model"]["asset_type"] == "STOCK"
    assert config["optional_features"]["dart_features_path"] == "ml/data/raw/dart_features.csv"
    assert "dart_disclosure_count_20d" in config["model"]["feature_columns"]
    assert "dart_risk_point_count_20d" in config["model"]["feature_columns"]
    assert "dart_text_risk_keyword_count_20d" in config["model"]["feature_columns"]
    assert risk_config["model"]["version"] == "lgbm_kr_stock_risk_v1"
    assert risk_config["data"]["features_path"] == config["data"]["features_path"]
    assert "dart_risk_point_count_20d" in risk_config["model"]["feature_columns"]


def test_us_stock_config_uses_separate_paths_and_excludes_dart_features():
    config = load_config("lgbm_us_stock_v1.yaml")
    risk_config = load_config("lgbm_us_stock_risk_v1.yaml")

    assert config["data"]["raw_candles_path"] == "data/raw/us_stock_candles.csv"
    assert config["data"]["features_path"] == "data/processed/us_stock_features_lgbm_v1.csv"
    assert config["model"]["version"] == "lgbm_us_stock_signal_v1"
    assert config["model"]["asset_type"] == "STOCK"
    assert "dart_features_path" not in config.get("optional_features", {})
    assert "dart_disclosure_count_20d" not in config["model"]["feature_columns"]
    assert risk_config["model"]["version"] == "lgbm_us_stock_risk_v1"
    assert risk_config["data"]["features_path"] == config["data"]["features_path"]
