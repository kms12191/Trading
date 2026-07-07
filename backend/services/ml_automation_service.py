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
            "chunk_size": 0,
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
    # v8: 30분 캔들(5000개 = 약 104일) + 잔차 수익률 라벨 + Ridge 앙상블
    "crypto-v8-full": {
        "label": "코인 v8 자동 수집+학습 (30m)",
        "dataset": {
            "asset_type": "CRYPTO",
            "exchange": "BINANCE",
            "preset": "crypto_core_30",
            "symbols": [],
            "interval": "30m",
            "count": 5000,
            "sleep_seconds": 0.3,
            "retry": 2,
            "retry_wait_seconds": 10.0,
            "append": True,
            "include_macro": False,
            "chunk_size": 10,
            "chunk_index": 1,
            # 기존 1h 데이터(crypto_candles.csv)와 혼재 방지를 위해 별도 파일 사용
            "raw_output": "crypto_candles_30m.csv",
        },
        "training": {
            "config": "ml/configs/lgbm_crypto_v8.yaml",
            "risk_config": "ml/configs/lgbm_crypto_risk_v8.yaml",
            "summary_output": "ml/data/processed/crypto_v8_summary.json",
            "skip_build_features": False,
        },
    },
    # v8: 잔차 수익률 라벨 + Ridge 앙상블 (KOSPI/NASDAQ 시장 수익률 차감 후 알파 예측)
    "stock-v8-full": {
        "label": "주식 v8 자동 수집+학습",
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
            "chunk_size": 0,
            "chunk_index": 1,
        },
        "training": {
            "config": "ml/configs/lgbm_stock_v8.yaml",
            "risk_config": "ml/configs/lgbm_stock_risk_v8.yaml",
            "summary_output": "ml/data/processed/stock_v8_summary.json",
            "skip_build_features": False,
        },
    },
    "kr-stock-v1-full": {
        "label": "국내주식 v1 자동 수집+학습 (DART shadow)",
        "dataset": {
            "asset_type": "STOCK",
            "exchange": "TOSS",
            "preset": "stock_kr_core_45",
            "symbols": [],
            "interval": "1d",
            "count": 700,
            "sleep_seconds": 2.0,
            "retry": 3,
            "retry_wait_seconds": 60.0,
            "append": True,
            "include_macro": True,
            "chunk_size": 0,
            "chunk_index": 1,
            "raw_output": "kr_stock_candles.csv",
        },
        "training": {
            "config": "ml/configs/lgbm_kr_stock_v1.yaml",
            "risk_config": "ml/configs/lgbm_kr_stock_risk_v1.yaml",
            "summary_output": "ml/data/processed/kr_stock_v1_summary.json",
            "skip_build_features": False,
            "pre_build_commands": [
                [
                    "python",
                    "backend/scripts/export_dart_features.py",
                    "--dates-source-path",
                    "ml/data/raw/kr_stock_candles.csv",
                    "--output",
                    "ml/data/raw/dart_features.csv",
                ]
            ],
        },
    },
    "us-stock-v1-full": {
        "label": "해외주식 v1 자동 수집+학습 (shadow)",
        "dataset": {
            "asset_type": "STOCK",
            "exchange": "TOSS",
            "preset": "stock_us_core_45",
            "symbols": [],
            "interval": "1d",
            "count": 700,
            "sleep_seconds": 2.0,
            "retry": 3,
            "retry_wait_seconds": 60.0,
            "append": True,
            "include_macro": True,
            "chunk_size": 0,
            "chunk_index": 1,
            "raw_output": "us_stock_candles.csv",
        },
        "training": {
            "config": "ml/configs/lgbm_us_stock_v1.yaml",
            "risk_config": "ml/configs/lgbm_us_stock_risk_v1.yaml",
            "summary_output": "ml/data/processed/us_stock_v1_summary.json",
            "skip_build_features": False,
        },
    },
    # v9: 30분 캔들 + 잔차 수익률 라벨 — 현재 serving 코인 모델과 동일 config
    "crypto-v9-full": {
        "label": "코인 v9 자동 수집+학습 (30m)",
        "dataset": {
            "asset_type": "CRYPTO",
            "exchange": "BINANCE",
            "preset": "crypto_core_30",
            "symbols": [],
            "interval": "30m",
            "count": 5000,
            "sleep_seconds": 0.3,
            "retry": 2,
            "retry_wait_seconds": 10.0,
            "append": True,
            "include_macro": False,
            "chunk_size": 10,
            "chunk_index": 1,
            "raw_output": "crypto_candles_30m.csv",
        },
        "training": {
            "config": "ml/configs/lgbm_crypto_v9.yaml",
            "risk_config": "ml/configs/lgbm_crypto_risk_v9.yaml",
            "summary_output": "ml/data/processed/crypto_v9_summary.json",
            "skip_build_features": False,
        },
    },
    # v11: 잔차 수익률 라벨 + Ridge 앙상블 — 현재 serving 주식 모델과 동일 config
    "stock-v11-full": {
        "label": "주식 v11 자동 수집+학습",
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
            "chunk_size": 0,
            "chunk_index": 1,
        },
        "training": {
            "config": "ml/configs/lgbm_stock_v11.yaml",
            "risk_config": "ml/configs/lgbm_stock_risk_v11.yaml",
            "summary_output": "ml/data/processed/stock_v11_summary.json",
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
