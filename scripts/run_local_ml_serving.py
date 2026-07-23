#!/usr/bin/env python3
"""로컬에서 ML 예측 릴리스를 생성한다."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from backend.services.ml_job_service import resolve_ml_python, run_ml_pipeline
from backend.scripts.export_training_candles import (
    DEFAULT_UNIVERSE_PATH,
    fetch_binance_klines,
    load_preset_symbols,
    write_rows,
)


ASSETS = {
    "crypto": {
        "config": "ml/configs/lgbm_crypto_v10.yaml",
        "risk_config": "ml/configs/lgbm_crypto_risk_v10.yaml",
        "short_config": "ml/configs/lgbm_crypto_short_v1.yaml",
    },
    "kr_stock": {
        "config": "ml/configs/lgbm_kr_stock_v1.yaml",
        "risk_config": "ml/configs/lgbm_kr_stock_risk_v1.yaml",
    },
    "us_stock": {
        "config": "ml/configs/lgbm_us_stock_v1.yaml",
        "risk_config": "ml/configs/lgbm_us_stock_risk_v1.yaml",
    },
}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def resolve_config_path(config_path: Path, value: str) -> Path:
    candidate = Path(value)
    return candidate if candidate.is_absolute() else config_path.parent.parent / candidate


def load_config(config_path: Path) -> dict:
    return yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}


def run_prediction(config_path: Path) -> None:
    completed = subprocess.run(
        [resolve_ml_python(), "ml/src/predict.py", "--config", str(config_path)],
        cwd=PROJECT_ROOT,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(f"예측 생성 실패: {config_path}")


def refresh_crypto_candles(config_path: Path) -> None:
    config = load_config(config_path)
    data_config = config.get("data") or {}
    symbols = load_preset_symbols("crypto", DEFAULT_UNIVERSE_PATH)
    if not symbols:
        raise RuntimeError("코인 유니버스를 찾지 못했습니다.")
    rows, failures = fetch_binance_klines(
        symbols,
        "30m",
        240,
        sleep_seconds=0.15,
        retry=2,
        retry_wait_seconds=5.0,
    )
    successful_symbols = len({str(row.get("symbol") or "") for row in rows})
    if successful_symbols < max(1, int(len(symbols) * 0.8)):
        raise RuntimeError(f"코인 캔들 수집 성공률이 낮습니다: {successful_symbols}/{len(symbols)}, failures={len(failures)}")
    raw_path = resolve_config_path(config_path, str(data_config["raw_candles_path"]))
    write_rows(raw_path, rows, append=True)


def validate_predictions(path: Path) -> datetime:
    with path.open(encoding="utf-8", newline="") as file:
        rows = list(csv.DictReader(file))
    if not rows:
        raise ValueError(f"예측 행이 없습니다: {path}")
    required_columns = {"symbol", "position", "signal_score", "model_version", "date"}
    if not required_columns.issubset(set(rows[0])):
        raise ValueError(f"예측 필수 열이 없습니다: {path}")
    timestamps = []
    for row in rows:
        try:
            parsed = datetime.fromisoformat(str(row.get("date") or "").replace("Z", "+00:00"))
        except ValueError:
            continue
        timestamps.append(parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed.astimezone(timezone.utc))
    if not timestamps:
        raise ValueError(f"예측 데이터 시각이 없습니다: {path}")
    return max(timestamps)


def build_release(asset_key: str, config_path: Path, output_root: Path) -> Path:
    config = load_config(config_path)
    data_config = config.get("data") or {}
    model_config = config.get("model") or {}
    prediction_config = config.get("prediction") or {}
    predictions_path = resolve_config_path(config_path, str(data_config["predictions_path"]))
    model_path = resolve_config_path(config_path, str(model_config["output_path"]))
    risk_model_path = resolve_config_path(config_path, str(prediction_config["risk_model_path"]))
    for source in (predictions_path, model_path, risk_model_path):
        if not source.is_file():
            raise FileNotFoundError(f"릴리스 필수 파일이 없습니다: {source}")
    prediction_data_at = validate_predictions(predictions_path)

    created_at = datetime.now(timezone.utc)
    release_id = created_at.strftime("%Y%m%dT%H%M%SZ")
    release_dir = output_root / "releases" / asset_key / release_id
    if release_dir.exists():
        raise FileExistsError(f"동일 시각 릴리스가 이미 있습니다: {release_dir}")

    files = [
        ("model", model_path, f"models/{model_path.name}"),
        ("risk_model", risk_model_path, f"models/{risk_model_path.name}"),
        ("config", config_path, f"configs/{config_path.name}"),
        ("predictions_snapshot", predictions_path, f"predictions/{predictions_path.name}"),
    ]
    manifest_files = []
    for role, source, package_path in files:
        target = release_dir / package_path
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        manifest_files.append(
            {
                "role": role,
                "package_path": package_path,
                "required": True,
                "sha256": sha256_file(target),
            }
        )
    manifest = {
        "schema_version": 1,
        "asset_key": asset_key,
        "created_at": created_at.isoformat(),
        "prediction_data_at": prediction_data_at.isoformat(),
        "model_version": str(model_config.get("version") or ""),
        "files": manifest_files,
    }
    (release_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return release_dir


def main() -> int:
    parser = argparse.ArgumentParser(description="로컬 ML 예측 릴리스 생성기")
    parser.add_argument("--asset", required=True, choices=sorted(ASSETS))
    parser.add_argument("--train", action="store_true", help="예측 전 재학습을 실행합니다.")
    parser.add_argument(
        "--output-root",
        type=Path,
        default=PROJECT_ROOT / "ml" / "local_releases",
        help="로컬 릴리스 출력 루트",
    )
    args = parser.parse_args()

    asset = ASSETS[args.asset]
    config_path = PROJECT_ROOT / asset["config"]
    if args.asset == "crypto":
        refresh_crypto_candles(config_path)
    if args.train:
        result = run_ml_pipeline(
            config_path=asset["config"],
            risk_config_path=asset.get("risk_config"),
            short_config_path=asset.get("short_config"),
        )
        if not result["success"]:
            raise RuntimeError(result["stderr"][-4000:] or "ML 재학습 실패")
    else:
        run_prediction(config_path)

    release_dir = build_release(args.asset, config_path, args.output_root)
    print(release_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
