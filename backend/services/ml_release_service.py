"""로컬에서 배포한 ML 릴리스의 무결성과 신선도를 검증한다."""

from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_RELEASES_ROOT = Path(os.getenv("ML_RELEASES_ROOT", PROJECT_ROOT / "ml" / "releases"))
CRYPTO_MAX_AGE = timedelta(minutes=90)
STOCK_MAX_AGE = timedelta(hours=36)


def _parse_utc(value: Any) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


class MlReleaseService:
    """AWS에서 자산별 현재 릴리스만 조회하도록 강제한다."""

    def __init__(self, releases_root: Path | str | None = None):
        self.releases_root = Path(releases_root or DEFAULT_RELEASES_ROOT)

    def get_current_release_dir(self, asset_key: str) -> Path | None:
        release_dir = self.releases_root / "current" / str(asset_key)
        if not release_dir.is_dir():
            return None
        return release_dir.resolve()

    def load_current_manifest(self, asset_key: str) -> dict[str, Any] | None:
        release_dir = self.get_current_release_dir(asset_key)
        if release_dir is None:
            return None
        return self.load_manifest_from_release(release_dir, asset_key)

    @classmethod
    def load_manifest_from_release(cls, release_dir: Path, asset_key: str) -> dict[str, Any] | None:
        manifest_path = release_dir / "manifest.json"
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, ValueError, json.JSONDecodeError):
            return None
        if not isinstance(manifest, dict) or manifest.get("asset_key") != asset_key:
            return None
        return manifest if cls._validate_files(release_dir, manifest) else None

    def get_current_predictions_path(self, asset_key: str) -> Path | None:
        release_dir = self.get_current_release_dir(asset_key)
        manifest = self.load_current_manifest(asset_key)
        if release_dir is None or manifest is None:
            return None
        for file_info in manifest.get("files") or []:
            if str(file_info.get("role") or "") != "predictions_snapshot":
                continue
            candidate = release_dir / str(file_info.get("package_path") or "")
            if candidate.is_file():
                return candidate
        for file_info in manifest.get("files") or []:
            candidate = release_dir / str(file_info.get("package_path") or "")
            if candidate.suffix.lower() == ".csv" and candidate.is_file():
                return candidate
        return None

    def is_asset_fresh(self, asset_key: str, now: datetime | None = None) -> tuple[bool, str]:
        manifest = self.load_current_manifest(asset_key)
        if manifest is None:
            return False, "RELEASE_UNAVAILABLE"
        created_at = _parse_utc(manifest.get("created_at"))
        if created_at is None:
            return False, "RELEASE_INVALID"
        current_time = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
        age = current_time - created_at
        if age < timedelta(0):
            return False, "RELEASE_INVALID"
        max_age = CRYPTO_MAX_AGE if asset_key == "crypto" else STOCK_MAX_AGE
        if age > max_age:
            return False, "STALE_RELEASE"
        if asset_key == "crypto" and manifest.get("prediction_data_at"):
            prediction_data_at = _parse_utc(manifest.get("prediction_data_at"))
            if prediction_data_at is None or current_time - prediction_data_at > CRYPTO_MAX_AGE:
                return False, "STALE_PREDICTION_DATA"
        return True, "READY"

    @staticmethod
    def _validate_files(release_dir: Path, manifest: dict[str, Any]) -> bool:
        files = manifest.get("files")
        if not isinstance(files, list):
            return False
        for file_info in files:
            if not isinstance(file_info, dict) or not file_info.get("required"):
                continue
            relative_path = str(file_info.get("package_path") or "")
            candidate = release_dir / relative_path
            expected_hash = str(file_info.get("sha256") or "")
            if not relative_path or not expected_hash or not candidate.is_file():
                return False
            if _sha256_file(candidate) != expected_hash:
                return False
        return True


def activate_release(releases_root: Path | str, asset_key: str, release_id: str) -> Path:
    """검증된 자산 릴리스를 원자적으로 current 링크에 반영한다."""
    root = Path(releases_root).resolve()
    normalized_asset = str(asset_key).strip()
    normalized_release_id = str(release_id).strip()
    if not normalized_asset or not normalized_release_id:
        raise ValueError("asset_key와 release_id가 필요합니다.")

    release_dir = (root / "releases" / normalized_asset / normalized_release_id).resolve()
    allowed_parent = (root / "releases" / normalized_asset).resolve()
    if not release_dir.is_relative_to(allowed_parent) or release_dir.parent != allowed_parent:
        raise ValueError("허용되지 않은 릴리스 경로입니다.")
    if MlReleaseService.load_manifest_from_release(release_dir, normalized_asset) is None:
        raise ValueError("ML 릴리스 매니페스트 또는 파일 해시 검증에 실패했습니다.")

    current_dir = root / "current"
    current_dir.mkdir(parents=True, exist_ok=True)
    target = current_dir / normalized_asset
    temporary = current_dir / f".{normalized_asset}.next"
    if temporary.exists() or temporary.is_symlink():
        temporary.unlink()
    temporary.symlink_to(os.path.relpath(release_dir, current_dir))
    temporary.replace(target)
    return release_dir
