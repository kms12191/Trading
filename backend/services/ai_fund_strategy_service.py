"""저장된 DCA·그리드 전략을 공통 TradeIntent로 변환합니다."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from backend.services.ai_fund_strategy_templates import evaluate_dca, evaluate_grid
from backend.services.supabase_client import safe_query_supabase_as_service_role


class AiFundStrategyService:
    """전략 템플릿의 결과를 주문이 아닌 보류 의도로 기록합니다."""

    def run_active_strategies(
        self,
        user_id: str,
        exchange_type: str,
        price_resolver: Any,
    ) -> int:
        """활성 전략을 평가해 생성한 보류 의도 수를 반환합니다."""
        created_count = 0
        for strategy in self._fetch_running(user_id, exchange_type):
            price = price_resolver(str(strategy.get("symbol") or ""))
            if not price or price <= 0:
                continue
            if self.evaluate_strategy(strategy, float(price)):
                created_count += 1
        return created_count

    def evaluate_strategy(self, strategy: dict[str, Any], current_price: float, now: datetime | None = None) -> bool:
        now = now or datetime.now(timezone.utc)
        strategy_type = str(strategy.get("strategy_type") or "").upper()
        config = strategy.get("config") if isinstance(strategy.get("config"), dict) else {}
        state = strategy.get("state") if isinstance(strategy.get("state"), dict) else {}
        symbol = str(strategy.get("symbol") or "")
        if strategy_type == "DCA":
            generated = evaluate_dca(symbol, current_price, config, state, now)
        elif strategy_type == "GRID":
            generated = evaluate_grid(symbol, current_price, config, state)
        else:
            return False
        if not generated:
            return False
        intent_key = f"strategy:{strategy['id']}:{generated.reason}:{now.replace(microsecond=0).isoformat()}"
        created = safe_query_supabase_as_service_role(
            "ai_fund_trade_intents",
            method="POST",
            json_data={
                "user_id": strategy["user_id"],
                "exchange_type": str(strategy["exchange_type"]).lower(),
                "strategy_id": generated.strategy_id,
                "source": "RULE",
                "source_id": str(strategy["id"]),
                "idempotency_key": intent_key,
                "symbol": generated.symbol,
                "side": generated.side,
                "status": "PENDING",
                "payload": {"notional": generated.notional, "reason": generated.reason},
            },
            extra_headers={"Prefer": "resolution=ignore-duplicates,return=representation"},
        )
        if not created:
            return False
        next_state = dict(state)
        if strategy_type == "DCA":
            next_state["entry_count"] = int(state.get("entry_count") or 0) + 1
            next_state["last_entry_at"] = now.isoformat()
        self._update_state(str(strategy["id"]), next_state)
        return True

    @staticmethod
    def _update_state(strategy_id: str, state: dict[str, Any]) -> None:
        safe_query_supabase_as_service_role(
            f"ai_fund_strategies?id=eq.{strategy_id}",
            method="PATCH",
            json_data={"state": state, "updated_at": datetime.now(timezone.utc).isoformat()},
        )

    @staticmethod
    def _fetch_running(user_id: str, exchange_type: str) -> list[dict[str, Any]]:
        rows = safe_query_supabase_as_service_role(
            "ai_fund_strategies",
            params={
                "user_id": f"eq.{user_id}",
                "exchange_type": f"eq.{exchange_type}",
                "status": "eq.RUNNING",
                "order": "created_at.asc",
            },
        ) or []
        return rows if isinstance(rows, list) else []
