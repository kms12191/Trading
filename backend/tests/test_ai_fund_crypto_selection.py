import hashlib
import json
from datetime import datetime, timedelta, timezone

from backend.services.ai_fund_crypto_selection import AiFundCryptoSelectionService
from backend.services.ml_release_service import MlReleaseService


def _write_crypto_release(root, *, created_at: datetime):
    release = root / "releases" / "crypto-test"
    predictions_dir = release / "predictions"
    predictions_dir.mkdir(parents=True)
    predictions = predictions_dir / "crypto_predictions_lgbm_v10.csv"
    predictions.write_text(
        "exchange,symbol,position,signal_score,model_version,date\n"
        f"BINANCE,BTCUSDT,LONG,45,lgbm_crypto_signal_v10,{created_at.isoformat()}\n",
        encoding="utf-8",
    )
    manifest = {
        "asset_key": "crypto",
        "created_at": created_at.isoformat(),
        "files": [
            {
                "role": "predictions_snapshot",
                "required": True,
                "package_path": "predictions/crypto_predictions_lgbm_v10.csv",
                "sha256": hashlib.sha256(predictions.read_bytes()).hexdigest(),
            }
        ],
    }
    (release / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    current_dir = root / "current"
    current_dir.mkdir()
    (current_dir / "crypto").symlink_to(release)


def test_crypto_candidates_use_current_release_predictions_when_release_is_required(tmp_path):
    now = datetime.now(timezone.utc)
    _write_crypto_release(tmp_path, created_at=now)
    fallback_predictions = tmp_path / "fallback.csv"
    fallback_predictions.write_text("symbol\nBTTUSDT\n", encoding="utf-8")

    snapshot = AiFundCryptoSelectionService(
        fallback_predictions,
        release_service=MlReleaseService(tmp_path),
        require_release=True,
    ).get_snapshot(min_confidence_score=0.3)

    assert [candidate["symbol"] for candidate in snapshot["candidates"]] == ["BTCUSDT"]
    assert snapshot["availability"]["status"] == "READY"


def test_crypto_candidates_are_withheld_when_current_release_is_stale(tmp_path):
    _write_crypto_release(tmp_path, created_at=datetime.now(timezone.utc) - timedelta(minutes=91))

    snapshot = AiFundCryptoSelectionService(
        tmp_path / "fallback.csv",
        release_service=MlReleaseService(tmp_path),
        require_release=True,
    ).get_snapshot(min_confidence_score=0.3)

    assert snapshot["candidates"] == []
    assert snapshot["availability"]["status"] == "STALE_RELEASE"
    assert snapshot["availability"]["message"] == "최신 ML 릴리스 시간이 지나 신규 매수를 보류했습니다."


def test_crypto_candidates_use_the_same_long_signal_threshold_as_the_scheduler(tmp_path):
    predictions = tmp_path / "crypto_predictions.csv"
    now = datetime.now(timezone.utc).isoformat()
    predictions.write_text(
        "exchange,symbol,position,signal_score,model_version,date\n"
        f"BINANCE,BTCUSDT,LONG,82,lgbm_crypto_signal_v10,{now}\n"
        f"BINANCE,ETHUSDT,LONG,70,lgbm_crypto_signal_v10,{now}\n",
        encoding="utf-8",
    )
    service = AiFundCryptoSelectionService(predictions)

    snapshot = service.get_snapshot(min_confidence_score=0.75)

    assert [candidate["symbol"] for candidate in snapshot["candidates"]] == ["BTCUSDT"]
    assert snapshot["availability"]["status"] == "READY"
    assert snapshot["candidates"][0]["selection_reason"] == "상승 신호와 확신도 기준을 통과했습니다."


def test_crypto_snapshot_explains_korean_hold_reason_when_no_long_signal_exists(tmp_path):
    predictions = tmp_path / "crypto_predictions.csv"
    predictions.write_text(
        "exchange,symbol,position,signal_score,model_version,date\n"
        "BINANCE,BTCUSDT,HOLD,0,lgbm_crypto_signal_v10,2026-07-22\n",
        encoding="utf-8",
    )
    service = AiFundCryptoSelectionService(predictions)

    snapshot = service.get_snapshot(min_confidence_score=0.75)

    assert snapshot["candidates"] == []
    assert snapshot["availability"] == {
        "status": "NO_LONG_SIGNAL",
        "message": "현재 모델이 매수 신호를 내지 않아 코인 후보를 보류했습니다.",
        "total_count": 1,
        "long_count": 0,
        "fresh_long_count": 0,
        "stale_count": 0,
        "qualified_count": 0,
    }


def test_crypto_candidates_exclude_stale_prediction_rows_from_trade_candidates(tmp_path):
    predictions = tmp_path / "crypto_predictions.csv"
    predictions.write_text(
        "exchange,symbol,position,signal_score,model_version,date\n"
        "BINANCE,BTTUSDT,LONG,99,lgbm_crypto_signal_v10,2022-01-17 03:30:00\n"
        "BINANCE,ADAUSDT,LONG,35,lgbm_crypto_signal_v10,2026-07-23T00:45:00+00:00\n",
        encoding="utf-8",
    )
    service = AiFundCryptoSelectionService(predictions)

    snapshot = service.get_snapshot(min_confidence_score=0.3)

    assert [candidate["symbol"] for candidate in snapshot["candidates"]] == ["ADAUSDT"]
    assert snapshot["availability"]["stale_count"] == 1
