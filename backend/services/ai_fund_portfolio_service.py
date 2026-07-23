"""포트폴리오 목표 배분을 승인 대기 TradeIntent로 변환합니다."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Callable

from backend.services.ai_fund_portfolio import plan_rebalance
from backend.services.supabase_client import safe_query_supabase_as_service_role


class AiFundPortfolioService:
    """전략별 원장 포지션을 통합해 포트폴리오 리밸런싱을 계획합니다."""

    def create_rebalance_intents(
        self,
        config: dict[str, Any],
        price_resolver: Callable[[str], float | None],
        now: datetime | None = None,
    ) -> int:
        targets = config.get("target_allocations")
        if not isinstance(targets, dict) or not targets:
            return 0
        user_id = str(config.get("user_id") or "")
        exchange_type = str(config.get("exchange_type") or "").lower()
        if not user_id or not exchange_type:
            return 0
        symbols = {str(symbol).upper() for symbol in targets}
        positions = self._fetch_positions(user_id, exchange_type)
        symbols.update(str(position.get("symbol") or "").upper() for position in positions)
        prices = {symbol: price_resolver(symbol) for symbol in symbols if symbol}
        intents = plan_rebalance(
            float(config.get("allocated_capital") or 0.0),
            targets,
            positions,
            prices,
            float(config.get("rebalance_threshold_pct") or 0.0),
        )
        bucket = (now or datetime.now(timezone.utc)).strftime("%Y%m%d%H")
        created_count = 0
        for intent in intents:
            created = safe_query_supabase_as_service_role(
                "ai_fund_trade_intents",
                method="POST",
                json_data={
                    "user_id": user_id,
                    "exchange_type": exchange_type,
                    "strategy_id": "portfolio_rebalance",
                    "source": "RULE",
                    "source_id": str(config.get("id") or "portfolio"),
                    "idempotency_key": f"rebalance:{config.get('id') or user_id}:{bucket}:{intent.symbol}:{intent.side}",
                    "symbol": intent.symbol,
                    "side": intent.side,
                    "status": "PENDING",
                    "payload": {
                        "notional": intent.notional,
                        "current_value": intent.current_value,
                        "target_value": intent.target_value,
                        "reason": "PORTFOLIO_REBALANCE",
                    },
                },
                extra_headers={"Prefer": "resolution=ignore-duplicates,return=representation"},
            )
            if created:
                created_count += 1
        return created_count

    @staticmethod
    def _fetch_positions(user_id: str, exchange_type: str) -> list[dict[str, Any]]:
        rows = safe_query_supabase_as_service_role(
            "ai_fund_positions",
            params={
                "user_id": f"eq.{user_id}",
                "exchange_type": f"eq.{exchange_type}",
                "select": "symbol,quantity",
            },
        ) or []
        return rows if isinstance(rows, list) else []
