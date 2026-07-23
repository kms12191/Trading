"""AI 위탁 포지션의 종료 정책을 결정합니다."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ExitDecision:
    """현재 가격에서 실행할 단일 매도 결정입니다."""

    reason: str
    quantity: float


@dataclass(frozen=True)
class ExitPolicyEvaluation:
    """종료 결정과 재시작 복구에 필요한 다음 정책 상태입니다."""

    decision: ExitDecision | None
    next_policy: dict[str, Any]


def evaluate_exit_policy(
    *,
    entry_price: float,
    quantity: float,
    current_price: float,
    policy: dict[str, Any] | None,
) -> ExitPolicyEvaluation:
    """손실 제한, 트레일링, 본전 손절, 부분 익절 순으로 종료 조건을 평가합니다."""
    next_policy = deepcopy(policy or {})
    if entry_price <= 0 or quantity <= 0 or current_price <= 0:
        return ExitPolicyEvaluation(decision=None, next_policy=next_policy)

    pnl_pct = ((current_price - entry_price) / entry_price) * 100.0
    stop_loss_pct = _to_optional_float(next_policy.get("stop_loss_pct"))
    if stop_loss_pct is not None and pnl_pct <= stop_loss_pct:
        return _decision("STOP_LOSS", quantity, next_policy)

    trailing = _normalize_trailing(next_policy.get("trailing"))
    if trailing:
        activation_pct = trailing["activation_pct"]
        highest_price = trailing["highest_price"]
        if pnl_pct >= activation_pct:
            highest_price = max(highest_price, current_price)
            trailing["highest_price"] = highest_price
            next_policy["trailing"] = trailing
        if highest_price > 0 and current_price <= highest_price * (1 - trailing["trail_pct"] / 100.0):
            return _decision("TRAILING_STOP", quantity, next_policy)

    if bool(next_policy.get("break_even_armed")) and current_price <= entry_price:
        return _decision("BREAK_EVEN_STOP", quantity, next_policy)

    steps = _normalize_take_profit_steps(next_policy.get("take_profit_steps"))
    completed = _completed_step_indices(next_policy.get("completed_take_profit_steps"))
    initial_quantity = _positive_float(next_policy.get("initial_quantity")) or quantity
    if steps:
        next_policy["initial_quantity"] = initial_quantity
    for index, step in enumerate(steps):
        if index in completed or pnl_pct < step["target_pct"]:
            continue
        sell_quantity = min(quantity, initial_quantity * step["sell_ratio"])
        if sell_quantity <= 0:
            continue
        completed.append(index)
        next_policy["completed_take_profit_steps"] = completed
        if index == 0 and bool(next_policy.get("break_even_after_first_target", True)):
            next_policy["break_even_armed"] = True
        return _decision(f"TAKE_PROFIT_{index + 1}", sell_quantity, next_policy)

    return ExitPolicyEvaluation(decision=None, next_policy=next_policy)


def _decision(reason: str, quantity: float, next_policy: dict[str, Any]) -> ExitPolicyEvaluation:
    return ExitPolicyEvaluation(
        decision=ExitDecision(reason=reason, quantity=quantity),
        next_policy=next_policy,
    )


def _normalize_take_profit_steps(value: Any) -> list[dict[str, float]]:
    if not isinstance(value, list):
        return []
    steps: list[dict[str, float]] = []
    remaining_ratio = 1.0
    for raw_step in value[:3]:
        if not isinstance(raw_step, dict):
            continue
        target_pct = _positive_float(raw_step.get("target_pct"))
        sell_ratio = _positive_float(raw_step.get("sell_ratio"))
        if target_pct is None or sell_ratio is None or remaining_ratio <= 0:
            continue
        bounded_ratio = min(sell_ratio, remaining_ratio)
        steps.append({"target_pct": target_pct, "sell_ratio": bounded_ratio})
        remaining_ratio -= bounded_ratio
    return steps


def _normalize_trailing(value: Any) -> dict[str, float] | None:
    if not isinstance(value, dict):
        return None
    activation_pct = _positive_float(value.get("activation_pct"))
    trail_pct = _positive_float(value.get("trail_pct"))
    if activation_pct is None or trail_pct is None:
        return None
    return {
        "activation_pct": activation_pct,
        "trail_pct": trail_pct,
        "highest_price": max(_to_float(value.get("highest_price")), 0.0),
    }


def _completed_step_indices(value: Any) -> list[int]:
    if not isinstance(value, list):
        return []
    return sorted({item for item in value if isinstance(item, int) and item >= 0})


def _positive_float(value: Any) -> float | None:
    result = _to_float(value)
    return result if result > 0 else None


def _to_optional_float(value: Any) -> float | None:
    if value is None:
        return None
    return _to_float(value)


def _to_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0
