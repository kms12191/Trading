"""승인된 AI 위탁운용 TradeIntent만 실제 주문 흐름으로 전달합니다."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Callable

from backend.services.supabase_client import safe_query_supabase_as_service_role


class AiFundIntentExecutor:
    """승인 전 의도와 실제 주문 실행을 분리하는 실행기입니다."""

    def __init__(self, trader: Any):
        self.trader = trader

    def run(
        self,
        user_id: str,
        exchange_type: str,
        exchange_client: Any,
        price_resolver: Callable[[str], float | None],
    ) -> int:
        """승인되고 유효한 주문 의도를 실행한 횟수를 반환합니다."""
        executed_count = 0
        for intent in self._fetch_approved(user_id, exchange_type):
            intent_id = str(intent.get("id") or "")
            if not intent_id:
                continue
            if self._is_expired(intent.get("expires_at")):
                self._update_status(intent_id, "EXPIRED")
                continue

            symbol = str(intent.get("symbol") or "").upper()
            current_price = price_resolver(symbol)
            if not current_price or current_price <= 0:
                continue

            requested_quantity = self._requested_quantity(intent.get("payload"), float(current_price))
            result = self.trader.evaluate_and_execute_signal(
                symbol=symbol,
                side=str(intent.get("side") or "").upper(),
                confidence=float(intent.get("confidence") or 1.0),
                current_price=float(current_price),
                exchange_client=exchange_client,
                signal_id=str(intent.get("idempotency_key") or intent_id),
                requested_quantity=requested_quantity,
                strategy_id=str(intent.get("strategy_id") or "ml_signal"),
            )
            if result:
                self._update_status(intent_id, "EXECUTED")
                executed_count += 1
        return executed_count

    @staticmethod
    def _fetch_approved(user_id: str, exchange_type: str) -> list[dict[str, Any]]:
        rows = safe_query_supabase_as_service_role(
            "ai_fund_trade_intents",
            params={
                "user_id": f"eq.{user_id}",
                "exchange_type": f"eq.{exchange_type.lower()}",
                "status": "eq.APPROVED",
                "order": "created_at.asc",
                "limit": "50",
            },
        ) or []
        return rows if isinstance(rows, list) else []

    @staticmethod
    def _update_status(intent_id: str, status: str) -> None:
        safe_query_supabase_as_service_role(
            f"ai_fund_trade_intents?id=eq.{intent_id}",
            method="PATCH",
            json_data={"status": status, "updated_at": datetime.now(timezone.utc).isoformat()},
        )

    @staticmethod
    def _requested_quantity(payload: Any, current_price: float) -> float | None:
        if not isinstance(payload, dict):
            return None
        try:
            notional = float(payload.get("notional") or 0)
        except (TypeError, ValueError):
            return None
        if notional <= 0:
            return None
        return notional / current_price

    @staticmethod
    def _is_expired(value: Any) -> bool:
        if not value:
            return False
        try:
            expires_at = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError:
            return True
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        return expires_at.astimezone(timezone.utc) <= datetime.now(timezone.utc)
