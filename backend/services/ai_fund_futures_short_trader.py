from __future__ import annotations

import hashlib
import os
import uuid
from contextlib import suppress
from datetime import datetime, timezone
from typing import Any

from backend.services.lock_service import distributed_lock
from backend.services.order_entry_service import resolve_futures_execution, resolve_service_leverage_limit
from backend.services.supabase_client import safe_query_supabase_as_service_role


class AiFundFuturesShortTrader:
    def __init__(self, user_id: str):
        self.user_id = user_id

    def open_short(
        self,
        config: dict[str, Any],
        client: Any,
        candidate: dict[str, Any],
        current_price: float,
    ) -> dict[str, Any] | None:
        symbol = str(candidate.get("symbol") or "").upper()
        confidence = _to_float(candidate.get("confidence_score"))
        lock_key = f"ai_fund_futures_short:{self.user_id}:{symbol}"
        with distributed_lock(lock_key, duration_seconds=15) as acquired:
            if not acquired or not self._is_ready(config, symbol, confidence, current_price):
                return None
            operation_mode = str(config.get("operation_mode") or "PAPER").upper()
            if operation_mode == "LIVE" and not self._live_ready(config):
                return None

            position_mode = client.get_position_mode()
            execution = resolve_futures_execution("OPEN_SHORT", position_mode.get("mode"), None)
            leverage = self._resolve_leverage(config, client, symbol)
            quantity = self._quantity(config, client, symbol, current_price, operation_mode)
            if quantity is None:
                return None

            client_order_id = self._client_order_id(config, symbol, str(candidate.get("signal_id") or ""))
            existing = self._find_existing_order(client_order_id)
            if existing:
                return {"order_id": existing.get("id"), "status": existing.get("status"), "idempotent": True}

            order_id = str(uuid.uuid4())
            self._insert_order(
                order_id,
                config,
                symbol,
                client_order_id,
                quantity,
                current_price,
                execution,
                leverage,
                confidence,
            )
            if operation_mode == "PAPER":
                self._mark_filled(order_id, f"paper-{client_order_id}", quantity, current_price)
                self._upsert_short_position(symbol, quantity, current_price)
                return {"order_id": order_id, "status": "FILLED", "paper": True}

            try:
                response = client.place_order(
                    symbol=symbol,
                    side=execution["side"],
                    ord_type="LIMIT",
                    qty=quantity,
                    price=round(current_price * 0.995, 6),
                    position_side=execution["position_side"],
                    reduce_only=execution["reduce_only"],
                    leverage=leverage,
                    margin_type=str(config.get("futures_margin_type") or "ISOLATED"),
                    client_order_id=client_order_id,
                )
            except Exception as error:
                self._mark_needs_review(order_id, str(error))
                return {"order_id": order_id, "status": "NEEDS_REVIEW"}
            self._mark_submitted(order_id, response, {"confidence_score": confidence, "intent": "OPEN_SHORT"})
            return {"order_id": order_id, "status": "SUBMITTED", "paper": False}

    def close_short(
        self,
        config: dict[str, Any],
        client: Any,
        symbol: str,
        quantity: float,
        current_price: float,
        reason: str,
    ) -> dict[str, Any] | None:
        normalized_symbol = str(symbol or "").upper()
        if not normalized_symbol or quantity <= 0 or current_price <= 0:
            return None
        with distributed_lock(f"ai_fund_futures_short:{self.user_id}:{normalized_symbol}", duration_seconds=15) as acquired:
            if not acquired or not config.get("is_active"):
                return None
            operation_mode = str(config.get("operation_mode") or "PAPER").upper()
            if operation_mode == "LIVE" and not self._live_ready(config):
                return None
            execution = resolve_futures_execution("CLOSE_POSITION", client.get_position_mode().get("mode"), "SHORT")
            client_order_id = self._client_order_id(config, normalized_symbol, f"close:{reason}")
            existing = self._find_existing_order(client_order_id)
            if existing:
                return {"order_id": existing.get("id"), "status": existing.get("status"), "idempotent": True}
            order_id = str(uuid.uuid4())
            self._insert_order(
                order_id, config, normalized_symbol, client_order_id, quantity, current_price,
                execution, self._resolve_leverage(config, client, normalized_symbol), 1.0,
                intent="CLOSE_SHORT", order_type="MARKET", reason=reason,
            )
            if operation_mode == "PAPER":
                self._mark_filled(order_id, f"paper-{client_order_id}", quantity, current_price)
                self._reduce_short_position(normalized_symbol, quantity)
                return {"order_id": order_id, "status": "FILLED", "paper": True}
            try:
                response = client.place_order(
                    symbol=normalized_symbol, side=execution["side"], ord_type="MARKET", qty=quantity,
                    position_side=execution["position_side"], reduce_only=execution["reduce_only"],
                    leverage=self._resolve_leverage(config, client, normalized_symbol),
                    margin_type=str(config.get("futures_margin_type") or "ISOLATED"), client_order_id=client_order_id,
                )
            except Exception as error:
                self._mark_needs_review(order_id, str(error))
                return {"order_id": order_id, "status": "NEEDS_REVIEW"}
            self._mark_submitted(order_id, response, {"confidence_score": 1.0, "intent": "CLOSE_SHORT", "reason": reason})
            return {"order_id": order_id, "status": "SUBMITTED", "paper": False}

    def list_short_positions(self) -> list[dict[str, Any]]:
        return safe_query_supabase_as_service_role(
            "ai_fund_positions",
            params={"user_id": f"eq.{self.user_id}", "exchange_type": "eq.binance_um_futures", "strategy_id": "eq.ml_short_signal", "position_direction": "eq.SHORT", "quantity": "gt.0"},
        ) or []

    def should_stop_short(self, position: dict[str, Any], current_price: float, config: dict[str, Any]) -> bool:
        entry_price = _to_float(position.get("average_entry_price"))
        stop_loss_pct = abs(_to_float(config.get("stop_loss_pct")))
        return entry_price > 0 and stop_loss_pct > 0 and current_price >= entry_price * (1 + (stop_loss_pct / 100))

    def _is_ready(self, config: dict[str, Any], symbol: str, confidence: float, current_price: float) -> bool:
        return bool(config.get("is_active")) and bool(symbol) and current_price > 0 and confidence >= _to_float(config.get("min_signal_confidence"))

    @staticmethod
    def _live_ready(config: dict[str, Any]) -> bool:
        server_enabled = os.getenv("AI_FUND_FUTURES_LIVE_ENABLED", "").strip().lower() == "true"
        margin_type = str(config.get("futures_margin_type") or "ISOLATED").upper()
        stop_loss_pct = _to_float(config.get("stop_loss_pct"))
        return server_enabled and bool(config.get("futures_live_enabled")) and margin_type == "ISOLATED" and stop_loss_pct < 0

    def _resolve_leverage(self, config: dict[str, Any], client: Any, symbol: str) -> int:
        requested = int(_to_float(config.get("futures_leverage")) or 1)
        exchange_limit = client.get_max_leverage(symbol)
        return resolve_service_leverage_limit(exchange_limit, str(requested))

    def _quantity(self, config: dict[str, Any], client: Any, symbol: str, current_price: float, operation_mode: str) -> float | None:
        max_position = _to_float(config.get("max_position_size"))
        allocated_capital = _to_float(config.get("allocated_capital"))
        notional = min(max_position, allocated_capital) if allocated_capital > 0 else max_position
        open_notional = sum(
            _to_float(position.get("quantity")) * _to_float(position.get("average_entry_price"))
            for position in self.list_short_positions()
        )
        if allocated_capital > 0:
            notional = min(notional, max(allocated_capital - open_notional, 0.0))
        if operation_mode == "CANARY":
            notional = min(notional, _to_float(config.get("canary_max_order_amount")))
        if notional <= 0:
            return None
        filters = client.get_futures_symbol_filters(symbol)
        if notional < _to_float(filters.get("min_notional")):
            return None
        return notional / current_price

    def _insert_order(self, order_id: str, config: dict[str, Any], symbol: str, client_order_id: str, quantity: float, current_price: float, execution: dict[str, Any], leverage: int, confidence: float, intent: str = "OPEN_SHORT", order_type: str = "LIMIT", reason: str | None = None) -> None:
        safe_query_supabase_as_service_role(
            "ai_fund_orders",
            method="POST",
            json_data={
                "id": order_id, "user_id": self.user_id, "config_id": config.get("id"),
                "exchange_type": "binance_um_futures", "strategy_id": "ml_short_signal",
                "client_order_id": client_order_id, "symbol": symbol, "side": execution["side"],
                "order_type": order_type, "requested_qty": quantity, "requested_price": round(current_price * 0.995, 6) if order_type == "LIMIT" else None,
                "status": "PENDING_SUBMIT", "position_direction": "SHORT", "position_side": execution["position_side"],
                "leverage": leverage, "margin_type": str(config.get("futures_margin_type") or "ISOLATED"),
                "raw_response": {"confidence_score": confidence, "intent": intent, "reason": reason},
            },
        )

    def _upsert_short_position(self, symbol: str, quantity: float, price: float) -> None:
        positions = safe_query_supabase_as_service_role(
            "ai_fund_positions",
            params={"user_id": f"eq.{self.user_id}", "exchange_type": "eq.binance_um_futures", "strategy_id": "eq.ml_short_signal", "symbol": f"eq.{symbol}", "position_direction": "eq.SHORT", "limit": "1"},
        ) or []
        position = positions[0] if positions else None
        previous_quantity = _to_float((position or {}).get("quantity"))
        previous_price = _to_float((position or {}).get("average_entry_price"))
        next_quantity = previous_quantity + quantity
        average_price = ((previous_quantity * previous_price) + (quantity * price)) / next_quantity
        payload = {"user_id": self.user_id, "exchange_type": "binance_um_futures", "strategy_id": "ml_short_signal", "symbol": symbol, "position_direction": "SHORT", "quantity": next_quantity, "average_entry_price": average_price}
        if position and position.get("id"):
            safe_query_supabase_as_service_role(f"ai_fund_positions?id=eq.{position['id']}", method="PATCH", json_data=payload)
        else:
            safe_query_supabase_as_service_role("ai_fund_positions", method="POST", json_data=payload)

    def _reduce_short_position(self, symbol: str, quantity: float) -> None:
        positions = self.list_short_positions()
        position = next((item for item in positions if item.get("symbol") == symbol), None)
        if not position or not position.get("id"):
            return
        remaining = max(_to_float(position.get("quantity")) - quantity, 0.0)
        safe_query_supabase_as_service_role(
            f"ai_fund_positions?id=eq.{position['id']}", method="PATCH",
            json_data={"quantity": remaining, "average_entry_price": _to_float(position.get("average_entry_price")) if remaining else 0.0},
        )

    @staticmethod
    def _mark_filled(order_id: str, exchange_order_id: str, quantity: float, price: float) -> None:
        safe_query_supabase_as_service_role(f"ai_fund_orders?id=eq.{order_id}", method="PATCH", json_data={"status": "FILLED", "exchange_order_id": exchange_order_id, "filled_qty": quantity, "average_fill_price": price, "last_synced_at": datetime.now(timezone.utc).isoformat()})

    @staticmethod
    def _mark_needs_review(order_id: str, reason: str) -> None:
        safe_query_supabase_as_service_role(f"ai_fund_orders?id=eq.{order_id}", method="PATCH", json_data={"status": "NEEDS_REVIEW", "failure_reason": reason})

    @staticmethod
    def _mark_submitted(order_id: str, response: dict[str, Any], metadata: dict[str, Any]) -> None:
        raw_response = {**metadata, "exchange_response": response}
        safe_query_supabase_as_service_role(f"ai_fund_orders?id=eq.{order_id}", method="PATCH", json_data={"status": "SUBMITTED", "exchange_order_id": response.get("order_id"), "raw_response": raw_response, "last_synced_at": datetime.now(timezone.utc).isoformat()})

    @staticmethod
    def _find_existing_order(client_order_id: str) -> dict[str, Any] | None:
        rows = safe_query_supabase_as_service_role("ai_fund_orders", params={"client_order_id": f"eq.{client_order_id}", "limit": "1"}) or []
        return rows[0] if rows else None

    def _client_order_id(self, config: dict[str, Any], symbol: str, signal_id: str) -> str:
        digest = hashlib.sha256(f"{config.get('id')}:{self.user_id}:{symbol}:{signal_id}".encode()).hexdigest()
        return f"short-{digest[:48]}"


def _to_float(value: Any) -> float:
    with suppress(TypeError, ValueError):
        return float(value or 0.0)
    return 0.0
