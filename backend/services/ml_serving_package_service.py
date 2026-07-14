from __future__ import annotations

import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from backend.services.ml_model_service import PROJECT_ROOT, resolve_active_model_selection


DEFAULT_PACKAGE_ROOT = PROJECT_ROOT / "ml" / "serving_packages"


def utc_now_iso() -> str:
    """서빙 패키지 생성 시각을 UTC ISO 문자열로 반환합니다."""
    return datetime.now(timezone.utc).isoformat()


def resolve_path(path_text: str | None) -> Path | None:
    """프로젝트 상대 경로와 절대 경로를 모두 Path로 정규화합니다."""
    if not path_text:
        return None
    path = Path(str(path_text))
    return path if path.is_absolute() else PROJECT_ROOT / path


def sha256_file(path: Path) -> str | None:
    """파일 해시를 계산해 EC2 업로드 후 무결성 점검에 사용합니다."""
    if not path.exists() or not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def infer_joblib_path(metrics_path_text: str | None) -> Path | None:
    """metrics JSON 경로에서 짝이 되는 joblib 모델 파일 경로를 추론합니다."""
    metrics_path = resolve_path(metrics_path_text)
    if metrics_path is None:
        return None
    name = metrics_path.name
    if name.endswith(".metrics.json"):
        return metrics_path.with_name(name.replace(".metrics.json", ".joblib"))
    return metrics_path.with_suffix(".joblib")


def read_config(config_path: Path | None) -> dict[str, Any]:
    """모델 config YAML을 읽어 manifest에 필요한 정책/피처 정보를 추출합니다."""
    if config_path is None or not config_path.exists():
        return {}
    data = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    return data if isinstance(data, dict) else {}


def get_feature_columns(active_result: dict[str, Any], config: dict[str, Any]) -> list[str]:
    """metrics 우선, config 보조 순서로 서빙 입력 피처 순서를 확정합니다."""
    metrics = active_result.get("metrics") or {}
    feature_columns = metrics.get("feature_columns")
    if isinstance(feature_columns, list) and feature_columns:
        return [str(item) for item in feature_columns]

    model_config = config.get("model") or {}
    feature_columns = model_config.get("feature_columns")
    if isinstance(feature_columns, list):
        return [str(item) for item in feature_columns]
    return []


def build_file_entry(role: str, source_path: Path | None, package_path: str, required: bool) -> dict[str, Any]:
    """manifest의 파일 항목을 표준 형태로 생성합니다."""
    exists = bool(source_path and source_path.exists() and source_path.is_file())
    return {
        "role": role,
        "source_path": str(source_path) if source_path else None,
        "package_path": package_path,
        "required": required,
        "exists": exists,
        "sha256": sha256_file(source_path) if exists and source_path else None,
    }


def build_serving_manifest(
    asset_key: str,
    auth_header: str | None,
    include_predictions: bool = True,
) -> dict[str, Any]:
    """활성 모델을 EC2 서빙 패키지 단위로 고정하는 manifest를 생성합니다."""
    selection = resolve_active_model_selection(asset_key, auth_header)
    if selection is None:
        raise ValueError(f"{asset_key} 활성 모델을 찾을 수 없습니다.")

    active_result = selection["active_result"]
    metrics = active_result.get("metrics") or {}
    risk_metrics = active_result.get("risk_metrics") or {}
    config_path = resolve_path(active_result.get("config_path"))
    config = read_config(config_path)
    prediction_config = config.get("prediction") or {}

    model_path = infer_joblib_path(active_result.get("metrics_path"))
    risk_model_path = infer_joblib_path(active_result.get("risk_metrics_path"))
    predictions_path = resolve_path(active_result.get("predictions_path"))
    summary_path = resolve_path((active_result.get("registry") or {}).get("summary_path"))
    model_version = str(metrics.get("model_version") or active_result.get("version") or "").strip()
    risk_model_version = str(risk_metrics.get("model_version") or "").strip()
    policy_version = str(prediction_config.get("policy_version") or f"{model_version}:config-policy").strip()
    package_name = f"{asset_key}-{model_version or active_result.get('version')}"

    files = [
        build_file_entry("model", model_path, f"models/{model_path.name if model_path else 'model.joblib'}", True),
        build_file_entry("risk_model", risk_model_path, f"models/{risk_model_path.name if risk_model_path else 'risk_model.joblib'}", True),
        build_file_entry("config", config_path, f"configs/{config_path.name if config_path else 'model.yaml'}", True),
        build_file_entry(
            "metrics",
            resolve_path(active_result.get("metrics_path")),
            f"metadata/{Path(str(active_result.get('metrics_path') or 'metrics.json')).name}",
            True,
        ),
        build_file_entry(
            "risk_metrics",
            resolve_path(active_result.get("risk_metrics_path")),
            f"metadata/{Path(str(active_result.get('risk_metrics_path') or 'risk_metrics.json')).name}",
            True,
        ),
    ]
    if summary_path:
        files.append(build_file_entry("summary", summary_path, f"metadata/{summary_path.name}", False))
    if include_predictions:
        files.append(
            build_file_entry(
                "predictions_snapshot",
                predictions_path,
                f"predictions/{predictions_path.name if predictions_path else 'predictions.csv'}",
                False,
            )
        )

    composite_backtest = ((active_result.get("backtests") or {}).get("composite") or {}).get("data") or {}
    return {
        "schema_version": 1,
        "created_at": utc_now_iso(),
        "package_name": package_name,
        "asset_key": asset_key,
        "asset_type": active_result.get("asset_type"),
        "selection_status": selection.get("selection_status"),
        "serving_version": selection.get("serving_version"),
        "recommended_version": selection.get("recommended_version"),
        "latest_version": selection.get("latest_version"),
        "model_version": model_version,
        "risk_model_version": risk_model_version,
        "policy_version": policy_version,
        "data_end_date": metrics.get("valid_end_date") or metrics.get("train_end_date"),
        "feature_columns": get_feature_columns(active_result, config),
        "prediction_policy": prediction_config,
        "performance": {
            "cv_roc_auc": ((metrics.get("time_series_cv_average") or {}).get("roc_auc")),
            "precision_at_top_10pct": metrics.get("precision_at_top_10pct"),
            "risk_cv_roc_auc": ((risk_metrics.get("time_series_cv_average") or {}).get("roc_auc")),
            "composite_excess_return_net": composite_backtest.get("excess_return_net"),
            "composite_precision_at_top_n": composite_backtest.get("precision_at_top_n"),
            "composite_max_drawdown_net": composite_backtest.get("max_drawdown_net"),
            "composite_selected_rows": composite_backtest.get("selected_rows"),
        },
        "runtime_contract": {
            "load_model_from": "files[role=model].package_path",
            "load_risk_model_from": "files[role=risk_model].package_path",
            "feature_order_source": "feature_columns",
            "policy_source": "prediction_policy",
            "fail_closed_when": [
                "required file missing",
                "feature_columns empty",
                "prediction input lacks required feature",
                "prediction snapshot stale for UI recommendation cache",
            ],
        },
        "files": files,
    }


def validate_manifest_files(manifest: dict[str, Any]) -> None:
    """필수 파일 누락 시 패키지 생성을 중단합니다."""
    missing = [
        str(item.get("role"))
        for item in manifest.get("files", [])
        if item.get("required") and not item.get("exists")
    ]
    if missing:
        raise FileNotFoundError(f"서빙 패키지 필수 파일이 없습니다: {', '.join(missing)}")
    if not manifest.get("feature_columns"):
        raise ValueError("서빙 패키지 feature_columns가 비어 있습니다.")


def export_serving_package(
    asset_key: str,
    auth_header: str | None,
    output_root: Path | str | None = None,
    include_predictions: bool = True,
    create_archive: bool = False,
) -> dict[str, Any]:
    """EC2 배포에 필요한 서빙 파일만 별도 디렉터리로 복사합니다."""
    manifest = build_serving_manifest(asset_key, auth_header, include_predictions=include_predictions)
    validate_manifest_files(manifest)

    root = Path(output_root) if output_root else DEFAULT_PACKAGE_ROOT
    package_dir = root / str(manifest["package_name"])
    package_dir.mkdir(parents=True, exist_ok=True)

    copied_files = []
    for item in manifest["files"]:
        if not item.get("exists"):
            continue
        source_path = Path(str(item["source_path"]))
        target_path = package_dir / str(item["package_path"])
        target_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_path, target_path)
        copied_files.append(str(target_path))

    manifest_path = package_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    archive_path = None
    if create_archive:
        archive_path = shutil.make_archive(str(package_dir), "gztar", root_dir=root, base_dir=package_dir.name)

    return {
        "package_dir": str(package_dir),
        "manifest_path": str(manifest_path),
        "archive_path": archive_path,
        "copied_files": copied_files,
        "manifest": manifest,
    }
