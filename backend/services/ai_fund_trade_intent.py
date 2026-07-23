"""AI 위탁운용의 모든 주문 신호가 공유하는 표준 계약입니다."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any


VALID_SOURCES = {"AI", "RULE", "WEBHOOK", "MANUAL"}
VALID_SIDES = {"BUY", "SELL"}


class TradeIntentValidationError(ValueError):
    """표준 주문 신호 입력값이 정책을 충족하지 않을 때 발생합니다."""


@dataclass(frozen=True)
class TradeIntent:
    source: str
    source_id: str
    idempotency_key: str
    symbol: str
    side: str
    confidence: float | None
    expires_at: datetime | None
    strategy_id: str

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "TradeIntent":
        source = str(payload.get("source") or "").upper()
        source_id = str(payload.get("source_id") or "").strip()
        idempotency_key = str(payload.get("idempotency_key") or "").strip()
        symbol = str(payload.get("symbol") or "").upper().strip()
        side = str(payload.get("side") or "").upper()
        strategy_id = str(payload.get("strategy_id") or "ml_signal").strip().lower() or "ml_signal"
        if source not in VALID_SOURCES:
            raise TradeIntentValidationError("지원하지 않는 신호 출처입니다.")
        if not source_id or not idempotency_key:
            raise TradeIntentValidationError("출처 식별자와 멱등 키는 필수입니다.")
        if side not in VALID_SIDES:
            raise TradeIntentValidationError("주문 방향은 BUY 또는 SELL이어야 합니다.")
        allowed_symbols = payload.get("allowed_symbols")
        if isinstance(allowed_symbols, list) and symbol not in {str(item).upper() for item in allowed_symbols}:
            raise TradeIntentValidationError("허용 심볼이 아닙니다.")
        if not symbol:
            raise TradeIntentValidationError("심볼은 필수입니다.")
        expires_at = _parse_datetime(payload.get("expires_at"))
        if expires_at and expires_at <= datetime.now(timezone.utc):
            raise TradeIntentValidationError("신호 유효 기간이 만료되었습니다.")
        confidence = _optional_confidence(payload.get("confidence"))
        return cls(
            source=source,
            source_id=source_id,
            idempotency_key=idempotency_key,
            symbol=symbol,
            side=side,
            confidence=confidence,
            expires_at=expires_at,
            strategy_id=strategy_id,
        )


def _parse_datetime(value: Any) -> datetime | None:
    if value in (None, ""):
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError as exc:
        raise TradeIntentValidationError("유효 기간 형식이 올바르지 않습니다.") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _optional_confidence(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        confidence = float(value)
    except (TypeError, ValueError) as exc:
        raise TradeIntentValidationError("신뢰도 값이 올바르지 않습니다.") from exc
    if not 0 <= confidence <= 1:
        raise TradeIntentValidationError("신뢰도는 0과 1 사이여야 합니다.")
    return confidence
