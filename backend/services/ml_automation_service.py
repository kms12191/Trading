from copy import deepcopy


AUTOMATION_PRESETS = {
    "stock-v7-full": {
        "label": "주식 v7 자동 수집+학습",
        "dataset": {
            "asset_type": "STOCK",
            "exchange": "TOSS",
            "preset": "stock_core_90",
            "symbols": [],
            "interval": "1d",
            "count": 700,
            "sleep_seconds": 2.0,
            "retry": 3,
            "retry_wait_seconds": 60.0,
            "append": True,
            "include_macro": True,
            "chunk_size": 10,
            "chunk_index": 1,
        },
        "training": {
            "config": "ml/configs/lgbm_stock_v7.yaml",
            "risk_config": "ml/configs/lgbm_stock_risk_v7.yaml",
            "summary_output": "ml/data/processed/stock_v7_summary.json",
            "skip_build_features": False,
        },
    },
    "crypto-v7-full": {
        "label": "코인 v7 자동 수집+학습",
        "dataset": {
            "asset_type": "CRYPTO",
            "exchange": "BINANCE",
            "preset": "crypto_core_30",
            "symbols": [],
            "interval": "1h",
            "count": 2500,
            "sleep_seconds": 0.2,
            "retry": 2,
            "retry_wait_seconds": 10.0,
            "append": True,
            "include_macro": False,
            "chunk_size": 10,
            "chunk_index": 1,
        },
        "training": {
            "config": "ml/configs/lgbm_crypto_v7.yaml",
            "risk_config": "ml/configs/lgbm_crypto_risk_v7.yaml",
            "summary_output": "ml/data/processed/crypto_v7_summary.json",
            "skip_build_features": False,
        },
    },
}


def list_automation_presets() -> list[dict]:
    return [{"key": key, **deepcopy(value)} for key, value in AUTOMATION_PRESETS.items()]


def resolve_automation_preset(key: str) -> dict:
    preset = AUTOMATION_PRESETS.get(key)
    if not preset:
        raise ValueError(f"알 수 없는 자동화 프리셋입니다: {key}")
    return deepcopy(preset)
