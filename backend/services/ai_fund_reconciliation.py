"""AI 위탁운용 내부 주문 원장과 거래소 주문 상태를 대사합니다."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from backend.services.ai_fund_exchange import OrderRequest, normalize_exchange_order
from backend.services.ai_fund_ledger import AiFundLedger
from backend.services.supabase_client import safe_query_supabase_as_service_role


OPEN_ORDER_STATUSES = "PENDING_SUBMIT,SUBMITTED,PARTIALLY_FILLED,CANCEL_REQUESTED,NEEDS_REVIEW"


@dataclass(frozen=True)
class ReconciliationResult:
    updated_count: int = 0
    needs_review_count: int = 0


class AiFundReconciliationService:
    """거래소 주문 상태를 조회해 내부 원장의 미확정 주문을 복구합니다."""

    def __init__(self, ledger: AiFundLedger):
        self.ledger = ledger

    def reconcile_config(self, config: dict[str, Any], exchange_client: Any) -> ReconciliationResult:
        exchange_type = str(config.get("exchange_type") or "").lower()
        orders = self._query(
            "ai_fund_orders",
            params={
                "user_id": f"eq.{config['user_id']}",
                "exchange_type": f"eq.{exchange_type}",
                "status": f"in.({OPEN_ORDER_STATUSES})",
                "order": "created_at.asc",
            },
        )
        updated_count = 0
        needs_review_count = 0
        for row in orders:
            outcome = self._reconcile_order(config, exchange_type, row, exchange_client)
            if outcome == "UPDATED":
                updated_count += 1
            elif outcome == "NEEDS_REVIEW":
                needs_review_count += 1
        return ReconciliationResult(updated_count=updated_count, needs_review_count=needs_review_count)

    def _reconcile_order(
        self,
        config: dict[str, Any],
        exchange_type: str,
        row: dict[str, Any],
        exchange_client: Any,
    ) -> str:
        exchange_order_id = row.get("exchange_order_id")
        if not exchange_order_id:
            self._mark_needs_review(row["id"], "거래소 주문 식별자가 없습니다.")
            return "NEEDS_REVIEW"

        try:
            payload = self._get_order_status(exchange_client, str(exchange_order_id), str(row.get("symbol") or ""))
        except Exception as exc:
            self._mark_needs_review(row["id"], f"거래소 주문 조회 실패: {exc}")
            return "NEEDS_REVIEW"
        if not payload:
            self._mark_needs_review(row["id"], "거래소에서 주문 상태를 찾을 수 없습니다.")
            return "NEEDS_REVIEW"

        request = OrderRequest(
            symbol=str(row["symbol"]),
            side=str(row["side"]),
            quantity=float(row["requested_qty"]),
            client_order_id=str(row["client_order_id"]),
            order_type=str(row["order_type"]),
            price=_to_optional_float(row.get("requested_price")),
        )
        order = normalize_exchange_order(exchange_type, payload, request)
        self._query(
            f"ai_fund_orders?id=eq.{row['id']}",
            method="PATCH",
            json_data={
                "status": order.status,
                "exchange_order_id": order.exchange_order_id,
                "filled_qty": order.filled_qty,
                "average_fill_price": order.average_fill_price,
                "fee_amount": order.fee,
                "last_synced_at": datetime.now(timezone.utc).isoformat(),
            },
        )
        if order.filled_qty > 0:
            new_fill_quantity = self.ledger.apply_new_fill(
                order,
                order_id=str(row["id"]),
                position_direction=str(row.get("position_direction") or "LONG"),
            )
            if new_fill_quantity > 0:
                self._record_trade_execution(config, row, order, new_fill_quantity)
        return "UPDATED"

    def _record_trade_execution(
        self,
        config: dict[str, Any],
        row: dict[str, Any],
        order: Any,
        new_fill_quantity: float,
    ) -> None:
        raw_response = row.get("raw_response") if isinstance(row.get("raw_response"), dict) else {}
        confidence_score = _to_optional_float(raw_response.get("confidence_score")) or 0.0
        executed_price = float(order.average_fill_price or 0.0)
        if executed_price <= 0:
            return
        self._query(
            "admin_ai_trade_logs",
            method="POST",
            json_data={
                "user_id": config["user_id"],
                "exchange_type": str(config.get("exchange_type") or "").lower(),
                "symbol": order.symbol,
                "side": order.side,
                "confidence_score": confidence_score,
                "executed_price": executed_price,
                "executed_qty": new_fill_quantity,
                "total_amount": executed_price * new_fill_quantity,
                "order_id": order.exchange_order_id or row.get("exchange_order_id"),
                "status": "SUCCESS",
            },
        )

    @staticmethod
    def _get_order_status(exchange_client: Any, order_id: str, symbol: str) -> dict[str, Any] | None:
        try:
            return exchange_client.get_order_status(order_id, symbol=symbol)
        except TypeError:
            return exchange_client.get_order_status(order_id)

    def _mark_needs_review(self, order_id: str, reason: str) -> None:
        self._query(
            f"ai_fund_orders?id=eq.{order_id}",
            method="PATCH",
            json_data={
                "status": "NEEDS_REVIEW",
                "failure_reason": reason,
                "last_synced_at": datetime.now(timezone.utc).isoformat(),
            },
        )

    @staticmethod
    def _query(endpoint: str, method: str = "GET", **kwargs: Any) -> list[dict[str, Any]]:
        result = safe_query_supabase_as_service_role(endpoint, method=method, **kwargs) or []
        return result if isinstance(result, list) else []


def _to_optional_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
