"""AI 위탁운용 원장 데이터를 전략별 성과 지표로 집계합니다."""

from __future__ import annotations

from typing import Any


OPEN_ORDER_STATUSES = {"PENDING_SUBMIT", "SUBMITTED", "PARTIALLY_FILLED", "CANCEL_REQUESTED", "NEEDS_REVIEW"}


def build_performance_report(
    positions: list[dict[str, Any]],
    orders: list[dict[str, Any]],
    prices: dict[str, Any],
) -> dict[str, Any]:
    """실현손익, 평가손익, 평가액과 미체결 주문을 전략별로 반환합니다."""
    strategies: dict[str, dict[str, float | int]] = {}
    total_position_value = 0.0
    total_realized_pnl = 0.0
    total_unrealized_pnl = 0.0
    for position in positions:
        strategy_id = str(position.get("strategy_id") or "ml_signal")
        symbol = str(position.get("symbol") or "").upper()
        quantity = _float(position.get("quantity"))
        entry_price = _float(position.get("average_entry_price"))
        current_price = _float(prices.get(symbol))
        realized_pnl = _float(position.get("realized_pnl"))
        position_value = quantity * current_price
        unrealized_pnl = (current_price - entry_price) * quantity
        metrics = strategies.setdefault(strategy_id, _empty_metrics())
        metrics["position_value"] += position_value
        metrics["realized_pnl"] += realized_pnl
        metrics["unrealized_pnl"] += unrealized_pnl
        total_position_value += position_value
        total_realized_pnl += realized_pnl
        total_unrealized_pnl += unrealized_pnl

    pending_order_count = 0
    for order in orders:
        strategy_id = str(order.get("strategy_id") or "ml_signal")
        metrics = strategies.setdefault(strategy_id, _empty_metrics())
        if str(order.get("status") or "").upper() in OPEN_ORDER_STATUSES:
            metrics["pending_order_count"] += 1
            pending_order_count += 1

    finalized_strategies = {
        strategy_id: _finalize_metrics(metrics)
        for strategy_id, metrics in sorted(strategies.items())
    }
    return {
        "position_value": round(total_position_value, 10),
        "realized_pnl": round(total_realized_pnl, 10),
        "unrealized_pnl": round(total_unrealized_pnl, 10),
        "total_pnl": round(total_realized_pnl + total_unrealized_pnl, 10),
        "pending_order_count": pending_order_count,
        "strategies": finalized_strategies,
    }


def _empty_metrics() -> dict[str, float | int]:
    return {
        "position_value": 0.0,
        "realized_pnl": 0.0,
        "unrealized_pnl": 0.0,
        "pending_order_count": 0,
    }


def _finalize_metrics(metrics: dict[str, float | int]) -> dict[str, float | int]:
    realized_pnl = float(metrics["realized_pnl"])
    unrealized_pnl = float(metrics["unrealized_pnl"])
    return {
        "position_value": round(float(metrics["position_value"]), 10),
        "realized_pnl": round(realized_pnl, 10),
        "unrealized_pnl": round(unrealized_pnl, 10),
        "total_pnl": round(realized_pnl + unrealized_pnl, 10),
        "pending_order_count": int(metrics["pending_order_count"]),
    }


def _float(value: Any) -> float:
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0
