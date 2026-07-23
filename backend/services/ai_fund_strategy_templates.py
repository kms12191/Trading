"""DCA와 그리드 전략이 공통 실행 계층에 제출할 의도를 계산합니다."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any


@dataclass(frozen=True)
class StrategyIntent:
    symbol: str
    side: str
    notional: float
    strategy_id: str
    reason: str


def evaluate_dca(
    symbol: str,
    current_price: float,
    config: dict[str, Any],
    state: dict[str, Any],
    now: datetime | None = None,
) -> StrategyIntent | None:
    now = now or datetime.now(timezone.utc)
    reference_price = _positive(config.get("reference_price"))
    trigger_drawdown_pct = _positive(config.get("trigger_drawdown_pct"))
    entry_amount = _positive(config.get("entry_amount"))
    max_entries = int(config.get("max_entries") or 0)
    if not reference_price or not trigger_drawdown_pct or not entry_amount or max_entries < 1 or current_price <= 0:
        return None
    if int(state.get("entry_count") or 0) >= max_entries:
        return None
    if float(state.get("strategy_pnl_pct") or 0.0) <= float(config.get("max_strategy_loss_pct") or float("-inf")):
        return None
    drawdown_pct = ((current_price - reference_price) / reference_price) * 100.0
    if drawdown_pct > -trigger_drawdown_pct or not _elapsed(state.get("last_entry_at"), now, int(config.get("min_interval_seconds") or 0)):
        return None
    return StrategyIntent(symbol=symbol.upper(), side="BUY", notional=entry_amount, strategy_id="dca", reason="DCA_DRAWDOWN")


def evaluate_grid(
    symbol: str,
    current_price: float,
    config: dict[str, Any],
    state: dict[str, Any],
) -> StrategyIntent | None:
    lower = _positive(config.get("lower_price"))
    upper = _positive(config.get("upper_price"))
    order_amount = _positive(config.get("order_amount"))
    grid_count = int(config.get("grid_count") or 0)
    if not lower or not upper or not order_amount or grid_count < 2 or lower >= upper:
        return None
    if current_price < lower or current_price > upper:
        return None
    spacing = (upper - lower) / grid_count
    target_level = max(0, min(grid_count - 1, int((current_price - lower) / spacing)))
    filled_levels = {int(level) for level in state.get("filled_buy_levels", []) if isinstance(level, int)}
    if target_level in filled_levels:
        return None
    return StrategyIntent(symbol=symbol.upper(), side="BUY", notional=order_amount, strategy_id="grid", reason=f"GRID_BUY_{target_level}")


def _elapsed(value: Any, now: datetime, minimum_seconds: int) -> bool:
    if minimum_seconds <= 0 or not value:
        return True
    try:
        last = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return False
    if last.tzinfo is None:
        last = last.replace(tzinfo=timezone.utc)
    return (now - last.astimezone(timezone.utc)).total_seconds() >= minimum_seconds


def _positive(value: Any) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None
