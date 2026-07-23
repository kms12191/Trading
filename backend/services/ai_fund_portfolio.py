"""AI 위탁운용 포트폴리오 목표 비중과 리밸런싱 의도를 계산합니다."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


RISK_PRESETS = {
    "conservative": {
        "max_position_ratio": 0.20,
        "daily_mdd_limit_pct": -1.0,
        "min_signal_confidence": 0.85,
        "rebalance_threshold_pct": 3.0,
    },
    "neutral": {
        "max_position_ratio": 0.35,
        "daily_mdd_limit_pct": -2.0,
        "min_signal_confidence": 0.75,
        "rebalance_threshold_pct": 5.0,
    },
    "aggressive": {
        "max_position_ratio": 0.50,
        "daily_mdd_limit_pct": -4.0,
        "min_signal_confidence": 0.65,
        "rebalance_threshold_pct": 8.0,
    },
}


@dataclass(frozen=True)
class RebalanceIntent:
    symbol: str
    side: str
    notional: float
    current_value: float
    target_value: float


def apply_risk_preset(config: dict[str, Any]) -> dict[str, Any]:
    """위험 성향에 따른 누락된 운용 한도를 채워 반환합니다."""
    updated = dict(config)
    preset_name = str(updated.get("risk_preset") or "neutral").lower()
    if preset_name == "custom":
        updated["risk_preset"] = preset_name
        return updated
    preset = RISK_PRESETS.get(preset_name)
    if not preset:
        raise ValueError("risk_preset은 conservative, neutral, aggressive, custom 중 하나여야 합니다.")
    updated["risk_preset"] = preset_name
    allocated_capital = _non_negative_float(updated.get("allocated_capital"))
    if "max_position_size" not in updated and allocated_capital:
        updated["max_position_size"] = allocated_capital * preset["max_position_ratio"]
    for key in ("daily_mdd_limit_pct", "min_signal_confidence", "rebalance_threshold_pct"):
        updated.setdefault(key, preset[key])
    return updated


def plan_rebalance(
    allocated_capital: float,
    target_allocations: dict[str, Any],
    positions: list[dict[str, Any]],
    prices: dict[str, Any],
    rebalance_threshold_pct: float,
) -> list[RebalanceIntent]:
    """목표 대비 편차가 임계값을 넘는 심볼의 리밸런싱 의도를 반환합니다."""
    capital = _positive_float(allocated_capital)
    threshold_pct = _non_negative_float(rebalance_threshold_pct)
    targets = normalize_target_allocations(target_allocations)
    if not capital or threshold_pct is None or not targets:
        return []

    position_values = _position_values(positions, prices)
    sells: list[RebalanceIntent] = []
    buys: list[RebalanceIntent] = []
    for symbol in sorted(targets):
        target_value = capital * targets[symbol]
        current_value = position_values.get(symbol, 0.0)
        difference = current_value - target_value
        if (abs(difference) / capital) * 100.0 <= threshold_pct:
            continue
        intent = RebalanceIntent(
            symbol=symbol,
            side="SELL" if difference > 0 else "BUY",
            notional=round(abs(difference), 10),
            current_value=round(current_value, 10),
            target_value=round(target_value, 10),
        )
        (sells if intent.side == "SELL" else buys).append(intent)
    return sells + buys


def normalize_target_allocations(target_allocations: dict[str, Any]) -> dict[str, float]:
    if not isinstance(target_allocations, dict) or not target_allocations:
        return {}
    normalized: dict[str, float] = {}
    for symbol, value in target_allocations.items():
        weight = _positive_float(value)
        symbol_text = str(symbol or "").upper().strip()
        if not symbol_text or not weight:
            return {}
        normalized[symbol_text] = weight
    total = sum(normalized.values())
    if abs(total - 1.0) > 0.0001:
        return {}
    return normalized


def _position_values(positions: list[dict[str, Any]], prices: dict[str, Any]) -> dict[str, float]:
    values: dict[str, float] = {}
    for position in positions:
        symbol = str(position.get("symbol") or "").upper().strip()
        quantity = _non_negative_float(position.get("quantity"))
        price = _positive_float(prices.get(symbol))
        if not symbol or quantity is None or not price:
            continue
        values[symbol] = values.get(symbol, 0.0) + (quantity * price)
    return values


def _positive_float(value: Any) -> float | None:
    parsed = _non_negative_float(value)
    return parsed if parsed and parsed > 0 else None


def _non_negative_float(value: Any) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed >= 0 else None
