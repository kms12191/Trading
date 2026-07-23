import hashlib
import json
import os
from datetime import datetime, timezone

import pytest

from backend.services.ml_release_service import MlReleaseService, activate_release


def _write_current_release(
    root,
    *,
    asset_key: str,
    created_at: str,
    invalid_hash: bool = False,
):
    release = root / "releases" / f"{asset_key}-release"
    release.mkdir(parents=True)
    predictions = release / "predictions.csv"
    predictions.write_text("symbol,signal_score\nBTCUSDT,31.3\n", encoding="utf-8")
    digest = hashlib.sha256(predictions.read_bytes()).hexdigest()
    manifest = {
        "asset_key": asset_key,
        "created_at": created_at,
        "files": [
            {
                "package_path": "predictions.csv",
                "required": True,
                "sha256": "invalid" if invalid_hash else digest,
            }
        ],
    }
    (release / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    current = root / "current"
    current.mkdir(exist_ok=True)
    (current / asset_key).symlink_to(release)


def test_crypto_release_is_fresh_within_ninety_minutes(tmp_path):
    _write_current_release(
        tmp_path,
        asset_key="crypto",
        created_at="2026-07-23T00:00:00+00:00",
    )

    is_fresh, status = MlReleaseService(tmp_path).is_asset_fresh(
        "crypto",
        datetime(2026, 7, 23, 1, 29, tzinfo=timezone.utc),
    )

    assert is_fresh is True
    assert status == "READY"


def test_crypto_release_is_stale_after_ninety_minutes(tmp_path):
    _write_current_release(
        tmp_path,
        asset_key="crypto",
        created_at="2026-07-23T00:00:00+00:00",
    )

    is_fresh, status = MlReleaseService(tmp_path).is_asset_fresh(
        "crypto",
        datetime(2026, 7, 23, 1, 31, tzinfo=timezone.utc),
    )

    assert is_fresh is False
    assert status == "STALE_RELEASE"


def test_crypto_release_is_rejected_when_prediction_data_is_stale_even_if_release_is_new(tmp_path):
    _write_current_release(
        tmp_path,
        asset_key="crypto",
        created_at="2026-07-23T01:29:00+00:00",
    )
    manifest_path = tmp_path / "current" / "crypto" / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["prediction_data_at"] = "2026-07-22T23:00:00+00:00"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    is_fresh, status = MlReleaseService(tmp_path).is_asset_fresh(
        "crypto",
        datetime(2026, 7, 23, 1, 30, tzinfo=timezone.utc),
    )

    assert is_fresh is False
    assert status == "STALE_PREDICTION_DATA"


def test_release_with_invalid_file_hash_is_rejected(tmp_path):
    _write_current_release(
        tmp_path,
        asset_key="crypto",
        created_at="2026-07-23T00:00:00+00:00",
        invalid_hash=True,
    )

    assert MlReleaseService(tmp_path).load_current_manifest("crypto") is None


def test_stock_release_is_stale_after_thirty_six_hours(tmp_path):
    _write_current_release(
        tmp_path,
        asset_key="kr_stock",
        created_at="2026-07-21T00:00:00+00:00",
    )

    is_fresh, status = MlReleaseService(tmp_path).is_asset_fresh(
        "kr_stock",
        datetime(2026, 7, 22, 12, 1, tzinfo=timezone.utc),
    )

    assert is_fresh is False
    assert status == "STALE_RELEASE"


def test_activate_release_replaces_current_only_after_manifest_validation(tmp_path):
    release = tmp_path / "releases" / "crypto" / "20260723T000000Z"
    predictions = release / "predictions.csv"
    release.mkdir(parents=True)
    predictions.write_text("symbol\nBTCUSDT\n", encoding="utf-8")
    (release / "manifest.json").write_text(
        json.dumps(
            {
                "asset_key": "crypto",
                "created_at": "2026-07-23T00:00:00+00:00",
                "files": [
                    {
                        "package_path": "predictions.csv",
                        "required": True,
                        "sha256": hashlib.sha256(predictions.read_bytes()).hexdigest(),
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    activated = activate_release(tmp_path, "crypto", "20260723T000000Z")

    assert activated == release.resolve()
    assert (tmp_path / "current" / "crypto").resolve() == release.resolve()
    assert not os.readlink(tmp_path / "current" / "crypto").startswith("/")


def test_activate_release_keeps_existing_current_when_release_is_invalid(tmp_path):
    _write_current_release(
        tmp_path,
        asset_key="crypto",
        created_at="2026-07-23T00:00:00+00:00",
    )
    before = (tmp_path / "current" / "crypto").resolve()
    invalid = tmp_path / "releases" / "crypto" / "invalid"
    invalid.mkdir(parents=True)
    (invalid / "manifest.json").write_text("{}", encoding="utf-8")

    with pytest.raises(ValueError):
        activate_release(tmp_path, "crypto", "invalid")

    assert (tmp_path / "current" / "crypto").resolve() == before
