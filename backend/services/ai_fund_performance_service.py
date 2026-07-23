"""AI 위탁운용 원장을 사용자별 성과 보고로 제공합니다."""

from __future__ import annotations

from typing import Any, Callable

from backend.services.ai_fund_performance import build_performance_report
from backend.services.supabase_client import safe_query_supabase_as_service_role


class AiFundPerformanceService:
    """포지션과 주문 원장을 현재가 기준 성과로 집계합니다."""

    def get_report(
        self,
        user_id: str,
        exchange_type: str,
        price_resolver: Callable[[str], float | None],
    ) -> dict[str, Any]:
        exchange = exchange_type.lower()
        positions = self._fetch_rows("ai_fund_positions", user_id, exchange)
        orders = self._fetch_rows("ai_fund_orders", user_id, exchange)
        prices = {
            str(position.get("symbol") or "").upper(): price_resolver(str(position.get("symbol") or "").upper())
            for position in positions
            if position.get("symbol")
        }
        return build_performance_report(positions, orders, prices)

    @staticmethod
    def _fetch_rows(table: str, user_id: str, exchange_type: str) -> list[dict[str, Any]]:
        rows = safe_query_supabase_as_service_role(
            table,
            params={
                "user_id": f"eq.{user_id}",
                "exchange_type": f"eq.{exchange_type}",
            },
        ) or []
        return rows if isinstance(rows, list) else []
