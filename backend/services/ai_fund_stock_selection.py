"""토스 주식 위탁운용을 위한 ML 후보 선별 서비스."""

from __future__ import annotations

import os
from typing import Any

from backend.services.ml_model_service import build_active_signal_payload
from backend.services.ml_release_service import MlReleaseService


_MARKET_MODEL_KEYS = {
    "KR": "kr_stock",
    "US": "us_stock",
}


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {"1", "true", "t", "yes"}


class AiFundStockSelectionService:
    """국내·미국 활성 ML 신호를 주문 가능한 주식 후보로 정리한다."""

    def __init__(
        self,
        release_service: MlReleaseService | None = None,
        require_release: bool | None = None,
    ):
        self.release_service = release_service or MlReleaseService()
        self.require_release = (
            require_release
            if require_release is not None
            else os.getenv("ML_RELEASE_REQUIRED", "false").strip().lower() == "true"
        )

    def select_candidates(
        self,
        config: dict,
        held_symbols: set[str] | None = None,
        auth_header: str | None = None,
    ) -> list[dict]:
        held = {str(symbol).upper() for symbol in (held_symbols or set())}
        scope = str(config.get("asset_scope") or "ALL").upper()
        markets = [market for market in ("KR", "US") if scope in {"ALL", market}]
        if not markets:
            return []

        available_slots = max(
            0,
            int(_as_float(config.get("max_open_positions"), 3)) - len(held),
        )
        if available_slots == 0:
            return []

        candidates_by_market = {
            market: [
                self._to_candidate(row, market, config)
                for row in self._load_active_predictions(market, auth_header)
                if self._eligible(row, held, config)
            ]
            for market in markets
        }
        for market in markets:
            if not self._is_market_release_ready(market):
                candidates_by_market[market] = []
        for candidates in candidates_by_market.values():
            candidates.sort(key=lambda candidate: candidate["confidence_score"], reverse=True)

        allocations = self._market_allocations(config, markets)
        quotas = self._market_quotas(available_slots, allocations)
        selected: list[dict] = []
        for market in markets:
            for candidate in candidates_by_market[market][: quotas[market]]:
                candidate["market_allocation_pct"] = allocations[market]
                selected.append(candidate)

        selected_symbols = {candidate["symbol"].upper() for candidate in selected}
        remaining = [
            candidate
            for market in markets
            for candidate in candidates_by_market[market]
            if candidate["symbol"].upper() not in selected_symbols
        ]
        remaining.sort(key=lambda candidate: candidate["confidence_score"], reverse=True)
        for candidate in remaining:
            if len(selected) >= available_slots:
                break
            candidate["market_allocation_pct"] = allocations[candidate["market"]]
            selected.append(candidate)

        return sorted(selected, key=lambda candidate: candidate["confidence_score"], reverse=True)

    def _load_active_predictions(self, market: str, auth_header: str | None) -> list[dict]:
        return self._load_market_predictions(market, auth_header, position="LONG")

    def _load_market_predictions(
        self,
        market: str,
        auth_header: str | None,
        position: str | None = None,
    ) -> list[dict]:
        asset_key = _MARKET_MODEL_KEYS[market]
        payload = build_active_signal_payload(
            asset_key=asset_key,
            auth_header=auth_header,
            position=position,
            min_signal_score=0,
            limit=200,
        )
        return list((payload or {}).get("predictions") or [])

    def get_availability(self, config: dict, auth_header: str | None = None) -> dict[str, dict]:
        """화면에 표시할 시장별 후보 부재 사유를 활성 예측 행에서 계산한다."""
        scope = str(config.get("asset_scope") or "ALL").upper()
        markets = [market for market in ("KR", "US") if scope in {"ALL", market}]
        availability: dict[str, dict] = {}
        for market in markets:
            release_ready, release_status = self._market_release_status(market)
            if not release_ready:
                availability[market] = {
                    "status": release_status,
                    "message": self._release_status_message(release_status),
                    "total_count": 0,
                    "long_count": 0,
                    "blocked_count": 0,
                    "market_regimes": [],
                }
                continue
            rows = self._load_market_predictions(market, auth_header)
            total_count = len(rows)
            long_count = sum(str(row.get("position") or "").upper() == "LONG" for row in rows)
            blocked_count = sum(_as_bool(row.get("policy_blocked")) for row in rows)
            regimes = sorted({str(row.get("market_regime_state") or "").strip() for row in rows if row.get("market_regime_state")})
            if not total_count:
                status, message = "NO_PREDICTIONS", "활성 ML 예측 결과를 찾지 못했습니다."
            elif long_count == 0 and blocked_count == total_count:
                status, message = "POLICY_BLOCKED", "시장 위험 정책이 모든 후보를 보류했습니다."
            elif long_count == 0:
                status, message = "NO_LONG_SIGNAL", "현재 모델이 매수 신호를 내지 않아 후보를 보류했습니다."
            else:
                status, message = "READY", "주문 검토 가능한 매수 후보가 있습니다."
            availability[market] = {
                "status": status,
                "message": message,
                "total_count": total_count,
                "long_count": long_count,
                "blocked_count": blocked_count,
                "market_regimes": regimes,
            }
        return availability

    def _is_market_release_ready(self, market: str) -> bool:
        return self._market_release_status(market)[0]

    def _market_release_status(self, market: str) -> tuple[bool, str]:
        if not self.require_release:
            return True, "READY"
        return self.release_service.is_asset_fresh(_MARKET_MODEL_KEYS[market])

    @staticmethod
    def _release_status_message(status: str) -> str:
        messages = {
            "RELEASE_UNAVAILABLE": "검증된 ML 릴리스를 찾지 못해 신규 매수를 보류했습니다.",
            "STALE_RELEASE": "최신 ML 릴리스 시간이 지나 신규 매수를 보류했습니다.",
            "RELEASE_INVALID": "ML 릴리스 정보가 올바르지 않아 신규 매수를 보류했습니다.",
        }
        return messages.get(status, "ML 릴리스를 확인하지 못해 신규 매수를 보류했습니다.")

    def _eligible(self, row: dict, held_symbols: set[str], config: dict) -> bool:
        symbol = str(row.get("symbol") or "").upper()
        confidence = _as_float(row.get("signal_score")) / 100.0
        minimum = _as_float(config.get("min_signal_confidence"), 0.75)
        return bool(symbol) and symbol not in held_symbols and str(row.get("position") or "").upper() == "LONG" and not _as_bool(row.get("policy_blocked")) and confidence >= minimum

    def _to_candidate(self, row: dict, market: str, config: dict) -> dict:
        confidence = min(1.0, max(0.0, _as_float(row.get("signal_score")) / 100.0))
        symbol = str(row.get("symbol") or "").upper()
        model_version = str(row.get("model_version") or "")
        prediction_date = str(row.get("date") or row.get("generated_at") or "")
        return {
            "market": market,
            "symbol": symbol,
            "confidence_score": confidence,
            "signal_id": f"stock:{market}:{model_version}:{prediction_date}:{symbol}",
            "model_version": model_version,
            "selection_reason": f"{market} 활성 모델 LONG 신호 {confidence * 100:.1f}점",
        }

    def _market_allocations(self, config: dict, markets: list[str]) -> dict[str, float]:
        raw = {
            "KR": max(0.0, _as_float(config.get("kr_allocation_pct"), 50.0)),
            "US": max(0.0, _as_float(config.get("us_allocation_pct"), 50.0)),
        }
        total = sum(raw[market] for market in markets)
        if total <= 0:
            return {market: 100.0 / len(markets) for market in markets}
        return {market: raw[market] * 100.0 / total for market in markets}

    def _market_quotas(self, slots: int, allocations: dict[str, float]) -> dict[str, int]:
        quotas = {market: int(slots * allocation / 100.0) for market, allocation in allocations.items()}
        remaining = slots - sum(quotas.values())
        for market in sorted(allocations, key=lambda item: (slots * allocations[item] / 100.0) % 1, reverse=True):
            if remaining <= 0:
                break
            quotas[market] += 1
            remaining -= 1
        return quotas
