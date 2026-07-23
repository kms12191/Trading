"""가상자산 위탁운용의 ML 후보와 보류 사유를 구성한다."""

from __future__ import annotations

import csv
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from backend.services.ml_release_service import MlReleaseService


MAX_PREDICTION_AGE = timedelta(hours=2)


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


class AiFundCryptoSelectionService:
    """스케줄러와 운영 화면이 공통으로 쓰는 코인 ML 후보 조회 서비스."""

    def __init__(
        self,
        predictions_path: Path,
        release_service: MlReleaseService | None = None,
        require_release: bool | None = None,
    ):
        self.predictions_path = predictions_path
        self.release_service = release_service or MlReleaseService()
        self.require_release = (
            require_release
            if require_release is not None
            else os.getenv("ML_RELEASE_REQUIRED", "false").strip().lower() == "true"
        )

    def get_snapshot(self, min_confidence_score: float, limit: int = 20) -> dict:
        release_status = "READY"
        predictions_path = self.predictions_path
        if self.require_release:
            is_fresh, release_status = self.release_service.is_asset_fresh("crypto")
            predictions_path = self.release_service.get_current_predictions_path("crypto")
            if not is_fresh or predictions_path is None:
                return self._release_unavailable_snapshot(release_status)

        rows = self._load_rows(predictions_path)
        threshold_score = min_confidence_score * 100.0
        long_rows = [row for row in rows if str(row.get("position") or "").upper() == "LONG"]
        fresh_long_rows = long_rows if self.require_release else [row for row in long_rows if self._is_fresh_prediction(row)]
        qualified_rows = [row for row in fresh_long_rows if _as_float(row.get("signal_score")) >= threshold_score]
        qualified_rows.sort(key=lambda row: _as_float(row.get("signal_score")), reverse=True)
        stale_count = len(long_rows) - len(fresh_long_rows)

        candidates = [self._to_candidate(row) for row in qualified_rows[:limit]]
        if not rows:
            status, message = "NO_PREDICTIONS", "코인 ML 예측 결과를 찾지 못했습니다."
        elif not long_rows:
            status, message = "NO_LONG_SIGNAL", "현재 모델이 매수 신호를 내지 않아 코인 후보를 보류했습니다."
        elif not fresh_long_rows:
            status, message = "STALE_PREDICTIONS", "최신 예측 시간이 지나 코인 후보를 보류했습니다."
        elif not qualified_rows:
            status, message = "LOW_CONFIDENCE", f"상승 신호는 있으나 설정 확신도 {min_confidence_score * 100:.0f}%에 미달해 보류했습니다."
        else:
            status, message = "READY", "상승 신호와 확신도 기준을 통과한 코인 후보가 있습니다."

        return {
            "candidates": candidates,
            "availability": {
                "status": status,
                "message": message,
                "total_count": len(rows),
                "long_count": len(long_rows),
                "fresh_long_count": len(fresh_long_rows),
                "stale_count": stale_count,
                "qualified_count": len(qualified_rows),
            },
        }

    @staticmethod
    def _release_unavailable_snapshot(status: str) -> dict:
        messages = {
            "STALE_RELEASE": "최신 ML 릴리스 시간이 지나 신규 매수를 보류했습니다.",
            "STALE_PREDICTION_DATA": "예측의 원본 시장 데이터 시간이 지나 신규 매수를 보류했습니다.",
            "RELEASE_INVALID": "ML 릴리스 정보가 올바르지 않아 신규 매수를 보류했습니다.",
            "RELEASE_UNAVAILABLE": "검증된 ML 릴리스를 찾지 못해 신규 매수를 보류했습니다.",
        }
        return {
            "candidates": [],
            "availability": {
                "status": status,
                "message": messages.get(status, "ML 릴리스를 확인하지 못해 신규 매수를 보류했습니다."),
                "total_count": 0,
                "long_count": 0,
                "fresh_long_count": 0,
                "stale_count": 0,
                "qualified_count": 0,
            },
        }

    @staticmethod
    def _is_fresh_prediction(row: dict) -> bool:
        value = str(row.get("date") or "").strip()
        if not value:
            return False
        try:
            prediction_time = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return False
        if prediction_time.tzinfo is None:
            prediction_time = prediction_time.replace(tzinfo=timezone.utc)
        age = datetime.now(timezone.utc) - prediction_time.astimezone(timezone.utc)
        return timedelta(0) <= age <= MAX_PREDICTION_AGE

    def _load_rows(self, predictions_path: Path) -> list[dict]:
        if not predictions_path.exists():
            return []
        with predictions_path.open(encoding="utf-8", newline="") as file:
            return list(csv.DictReader(file))

    def _to_candidate(self, row: dict) -> dict:
        score = _as_float(row.get("signal_score"))
        symbol = str(row.get("symbol") or "").upper()
        model_version = str(row.get("model_version") or "")
        prediction_date = str(row.get("date") or "")
        return {
            "symbol": symbol,
            "confidence_score": min(1.0, max(0.0, score / 100.0)),
            "source_exchange": str(row.get("exchange") or "").upper(),
            "model_version": model_version,
            "signal_id": f"crypto:{model_version}:{prediction_date}:{symbol}:{score}",
            "selection_reason": "상승 신호와 확신도 기준을 통과했습니다.",
        }
