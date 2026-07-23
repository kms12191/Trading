"""라이브 DCA·그리드 템플릿을 재사용하는 결정론적 전략 백테스트입니다."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from backend.services.ai_fund_strategy_templates import StrategyIntent, evaluate_dca, evaluate_grid


def run_strategy_backtest(
    strategy: dict[str, Any],
    candles: list[dict[str, Any]],
    fee_bps: float = 0.0,
) -> dict[str, Any]:
    """캔들 종가 기준으로 전략 의도와 순성과를 재현합니다."""
    strategy_type = str(strategy.get("strategy_type") or "").upper()
    symbol = str(strategy.get("symbol") or "").upper()
    config = strategy.get("config") if isinstance(strategy.get("config"), dict) else {}
    state: dict[str, Any] = {}
    fee_rate = max(float(fee_bps), 0.0) / 10000.0
    quantity = 0.0
    invested_notional = 0.0
    trades: list[dict[str, Any]] = []
    equity_values: list[float] = []
    last_price = 0.0

    for candle in candles:
        price = _positive_float(candle.get("close"))
        if not price:
            continue
        last_price = price
        now = _parse_timestamp(candle.get("timestamp"))
        intent = _evaluate(strategy_type, symbol, price, config, state, now)
        if intent:
            filled_quantity = (intent.notional * (1.0 - fee_rate)) / price
            quantity += filled_quantity
            invested_notional += intent.notional
            _apply_intent_to_state(strategy_type, intent, state, now)
            trades.append(
                {
                    "timestamp": now.isoformat(),
                    "symbol": intent.symbol,
                    "side": intent.side,
                    "reason": intent.reason,
                    "notional": intent.notional,
                    "price": price,
                    "quantity": filled_quantity,
                }
            )
        if invested_notional > 0:
            equity_values.append((quantity * price) / invested_notional)

    final_value = (quantity * last_price) if last_price else 0.0
    net_return_pct = ((final_value / invested_notional) - 1.0) * 100.0 if invested_notional else 0.0
    return {
        "strategy_id": str(strategy.get("id") or ""),
        "strategy_type": strategy_type,
        "symbol": symbol,
        "trade_count": len(trades),
        "invested_notional": round(invested_notional, 10),
        "final_value": round(final_value, 10),
        "net_return_pct": round(net_return_pct, 8),
        "max_drawdown_pct": round(_max_drawdown_pct(equity_values), 8),
        "trades": trades,
    }


def _evaluate(
    strategy_type: str,
    symbol: str,
    price: float,
    config: dict[str, Any],
    state: dict[str, Any],
    now: datetime,
) -> StrategyIntent | None:
    if strategy_type == "DCA":
        return evaluate_dca(symbol, price, config, state, now)
    if strategy_type == "GRID":
        return evaluate_grid(symbol, price, config, state)
    return None


def _apply_intent_to_state(
    strategy_type: str,
    intent: StrategyIntent,
    state: dict[str, Any],
    now: datetime,
) -> None:
    if strategy_type == "DCA":
        state["entry_count"] = int(state.get("entry_count") or 0) + 1
        state["last_entry_at"] = now.isoformat()
        return
    if strategy_type == "GRID":
        level = _grid_level_from_reason(intent.reason)
        if level is None:
            return
        levels = {int(item) for item in state.get("filled_buy_levels", []) if isinstance(item, int)}
        levels.add(level)
        state["filled_buy_levels"] = sorted(levels)


def _grid_level_from_reason(reason: str) -> int | None:
    if not reason.startswith("GRID_BUY_"):
        return None
    try:
        return int(reason.rsplit("_", 1)[1])
    except ValueError:
        return None


def _parse_timestamp(value: Any) -> datetime:
    if value:
        try:
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                return parsed.replace(tzinfo=timezone.utc)
            return parsed.astimezone(timezone.utc)
        except ValueError:
            pass
    return datetime.now(timezone.utc)


def _positive_float(value: Any) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def _max_drawdown_pct(equity_values: list[float]) -> float:
    peak = 0.0
    drawdown = 0.0
    for equity in equity_values:
        peak = max(peak, equity)
        if peak > 0:
            drawdown = min(drawdown, ((equity - peak) / peak) * 100.0)
        elif equity < 0:
            drawdown = min(drawdown, equity)
    return drawdown
