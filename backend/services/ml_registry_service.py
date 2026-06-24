import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
OPS_DIR = PROJECT_ROOT / "ml" / "data" / "ops"
MODEL_REGISTRY_PATH = OPS_DIR / "model_registry.json"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def ensure_ops_dir() -> None:
    OPS_DIR.mkdir(parents=True, exist_ok=True)


def read_model_registry() -> list[dict[str, Any]]:
    ensure_ops_dir()
    if not MODEL_REGISTRY_PATH.exists():
        return []
    return json.loads(MODEL_REGISTRY_PATH.read_text(encoding="utf-8"))


def write_model_registry(rows: list[dict[str, Any]]) -> None:
    ensure_ops_dir()
    MODEL_REGISTRY_PATH.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")


def list_model_registry(asset_type: str | None = None) -> list[dict[str, Any]]:
    rows = read_model_registry()
    if asset_type:
        target = asset_type.upper()
        rows = [row for row in rows if str(row.get("asset_type", "")).upper() == target]
    return rows


def upsert_model_registry(row: dict[str, Any]) -> dict[str, Any]:
    rows = read_model_registry()
    asset_type = str(row.get("asset_type") or "").upper()
    model_version = str(row.get("model_version") or "")
    if not asset_type or not model_version:
        raise ValueError("asset_type과 model_version이 필요합니다.")

    target = None
    for item in rows:
        if str(item.get("asset_type", "")).upper() == asset_type and str(item.get("model_version", "")) == model_version:
            item.update(row)
            item["updated_at"] = utc_now_iso()
            target = item
            break

    if target is None:
        target = {
            "asset_type": asset_type,
            "model_version": model_version,
            "created_at": utc_now_iso(),
            "updated_at": utc_now_iso(),
            **row,
        }
        rows.append(target)

    write_model_registry(rows)
    return target


def set_serving_model(asset_type: str, model_version: str, approved_by: str | None = None) -> dict[str, Any]:
    asset_type = asset_type.upper()
    rows = read_model_registry()
    target = None
    for item in rows:
        if str(item.get("asset_type", "")).upper() != asset_type:
            continue
        item["is_serving"] = str(item.get("model_version", "")) == model_version
        item["updated_at"] = utc_now_iso()
        if item["is_serving"]:
            item["approved_by"] = approved_by
            item["approved_at"] = utc_now_iso()
            target = item

    if target is None:
        target = upsert_model_registry(
            {
                "asset_type": asset_type,
                "model_version": model_version,
                "is_latest": False,
                "is_recommended": False,
                "is_serving": True,
                "approved_by": approved_by,
                "approved_at": utc_now_iso(),
            }
        )
        return target

    write_model_registry(rows)
    return target
