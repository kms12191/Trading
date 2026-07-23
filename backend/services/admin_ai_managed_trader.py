import logging
import uuid
import hashlib
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from backend.services.ai_fund_exchange import OrderRequest, normalize_exchange_order
from backend.services.ai_fund_exit_policy import evaluate_exit_policy
from backend.services.ai_fund_ledger import AiFundLedger
from backend.services.lock_service import distributed_lock
from backend.services.supabase_client import safe_query_supabase_as_service_role, query_supabase_as_service_role

logger = logging.getLogger(__name__)

SUCCESS_STATUSES = {"SUCCESS", "EXECUTED", "ORDERED"}


class AdminAiRiskViolation(Exception):
    """Raised when an AI trade violates defined admin risk limits."""
    pass


class AdminAiManagedTrader:
    """Core execution engine for handling discretionary AI auto-trading for Admins."""

    def __init__(self, user_id: str, exchange_type: str):
        self.user_id = user_id
        self.exchange_type = exchange_type

    def evaluate_and_execute_signal(
        self,
        symbol: str,
        signal_type: str,  # 'BUY' | 'SELL'
        confidence_score: float,
        current_price: float,
        exchange_client: Any,
        signal_id: str | None = None,
        requested_quantity: float | None = None,
        strategy_id: str = "ml_signal",
    ) -> Optional[Dict[str, Any]]:
        """Evaluates ML signal against Admin risk guardrails and executes order if compliant."""
        lock_key = f"admin_ai_trade_{self.user_id}_{self.exchange_type}_{symbol}"
        
        with distributed_lock(lock_key, duration_seconds=15) as acquired:
            if not acquired:
                logger.warning(f"[AdminAiTrader] Distributed lock acquisition failed for {symbol}")
                return None

            config = self._get_fund_config()
            if not config or not config.get("is_active"):
                logger.info(f"[AdminAiTrader] Fund trading is inactive for user {self.user_id}")
                return None

            if not self.is_symbol_tradable_on_exchange(symbol):
                logger.warning(
                    f"[AdminAiTrader] Skipping {symbol}: Not listed/tradable on target exchange '{self.exchange_type}'"
                )
                return None

            min_score = float(config.get("min_signal_confidence", 0.75))
            if confidence_score < min_score:
                logger.info(f"[AdminAiTrader] Confidence score {confidence_score} < threshold {min_score}")
                return None

            daily_pnl_pct = self._get_daily_pnl_pct(config)
            daily_mdd_limit_pct = float(config.get("daily_mdd_limit_pct", -2.0))
            if daily_pnl_pct <= daily_mdd_limit_pct:
                raise AdminAiRiskViolation(
                    f"Daily MDD limit reached: {daily_pnl_pct:.2f}% <= {daily_mdd_limit_pct:.2f}%."
                )

            side_upper = signal_type.upper()
            normalized_strategy_id = strategy_id.strip().lower() or "ml_signal"
            strategy_ledger = AiFundLedger(
                self.user_id,
                self.exchange_type,
                normalized_strategy_id,
            )
            open_position = self._get_open_position(symbol)
            if side_upper == "BUY" and open_position:
                logger.info(f"[AdminAiTrader] Existing open position found for {symbol}; skipping duplicate BUY")
                return None
            if side_upper == "BUY":
                unresolved_order = self._find_unresolved_order_for_symbol(symbol, normalized_strategy_id)
                if unresolved_order:
                    logger.warning(
                        "[AdminAiTrader] Unresolved BUY order found for %s; blocking another submission (order=%s)",
                        symbol,
                        unresolved_order.get("id"),
                    )
                    return {
                        "order_id": unresolved_order.get("id"),
                        "status": unresolved_order.get("status"),
                        "blocked": True,
                    }

            max_pos_size = float(config.get("max_position_size", 0.0))
            if max_pos_size <= 0:
                raise AdminAiRiskViolation("Max position size is zero or invalid.")

            allocated_capital = float(config.get("allocated_capital", 0.0))
            if allocated_capital > 0 and max_pos_size > allocated_capital:
                raise AdminAiRiskViolation("Max position size exceeds allocated capital.")

            quantity = max_pos_size / current_price if current_price > 0 else 0
            if side_upper == "BUY":
                if requested_quantity is not None:
                    quantity = min(quantity, max(float(requested_quantity), 0.0))
                self._assert_strategy_budget(
                    config,
                    strategy_ledger,
                    normalized_strategy_id,
                    quantity * current_price,
                )
            if side_upper == "SELL":
                if not open_position:
                    logger.info(f"[AdminAiTrader] No open position found for {symbol}; skipping SELL")
                    return None
                quantity = float(open_position.get("executed_qty") or 0.0)
                if requested_quantity is not None:
                    sellable_quantity = strategy_ledger.get_sellable_quantity(symbol)
                    quantity = min(quantity, max(float(requested_quantity), 0.0), sellable_quantity)
            if quantity <= 0:
                raise AdminAiRiskViolation("Calculated trade quantity is invalid.")

            operation_mode = str(config.get("operation_mode") or "LIVE").upper()
            if operation_mode not in {"PAPER", "CANARY", "LIVE"}:
                raise AdminAiRiskViolation(f"Unsupported operation mode: {operation_mode}.")
            if operation_mode == "CANARY" and side_upper == "BUY":
                canary_max_order_amount = float(config.get("canary_max_order_amount") or 0.0)
                if canary_max_order_amount <= 0:
                    raise AdminAiRiskViolation("CANARY mode requires a positive max order amount.")
                quantity = min(quantity, canary_max_order_amount / current_price)

            capability_getter = getattr(exchange_client, "get_capabilities", None)
            if callable(capability_getter):
                capability = capability_getter()
                if not capability.supports_spot or not capability.supports_order_type("LIMIT"):
                    raise AdminAiRiskViolation("Target exchange does not support the required spot limit order.")

            # 슬리피지 허용을 위해 현재가 +0.5% 지정가 주문 (LIMIT 주문만 지원)
            limit_price = round(current_price * 1.005, 6) if side_upper == "BUY" else round(current_price * 0.995, 6)

            logger.info(
                f"[AdminAiTrader] EXECUTING {signal_type} for {symbol} | "
                f"Qty: {quantity:.6f} @ limit {limit_price} (spot: {current_price})"
            )

            request = OrderRequest(
                symbol=symbol,
                side=side_upper,
                quantity=quantity,
                client_order_id=self._build_client_order_id(config, symbol, side_upper, signal_id),
                order_type="LIMIT",
                price=limit_price,
            )
            existing_order = self._find_order_by_client_order_id(request.client_order_id)
            if existing_order:
                return {
                    "order_id": existing_order.get("id"),
                    "status": existing_order.get("status"),
                    "idempotent": True,
                }
            ledger_order_id = self._create_pending_order(config, request, normalized_strategy_id)
            if operation_mode == "PAPER":
                simulated_order = normalize_exchange_order(
                    self.exchange_type,
                    {
                        "order_id": f"paper-{request.client_order_id}",
                        "status": "FILLED",
                        "executed_qty": quantity,
                        "executed_price": current_price,
                    },
                    request,
                )
                self._update_ledger_order(
                    ledger_order_id,
                    status=simulated_order.status,
                    exchange_order_id=simulated_order.exchange_order_id,
                    filled_qty=simulated_order.filled_qty,
                    average_fill_price=simulated_order.average_fill_price,
                )
                self._log_trade_execution(
                    symbol=symbol,
                    side=signal_type,
                    confidence_score=confidence_score,
                    executed_price=current_price,
                    executed_qty=quantity,
                    order_id=simulated_order.exchange_order_id,
                )
                strategy_ledger.apply_new_fill(
                    simulated_order,
                    order_id=ledger_order_id,
                )
                return {"order_id": simulated_order.exchange_order_id, "status": "FILLED", "paper": True}

            try:
                order_result = exchange_client.place_order(
                    symbol=symbol,
                    side=side_upper,
                    ord_type="LIMIT",
                    qty=quantity,
                    price=limit_price,
                )
            except Exception as exc:
                logger.warning("[AdminAiTrader] 주문 제출 결과를 확인할 수 없습니다: %s", exc)
                self._update_ledger_order(
                    ledger_order_id,
                    status="NEEDS_REVIEW",
                    failure_reason=str(exc),
                )
                return {"order_id": ledger_order_id, "status": "NEEDS_REVIEW"}

            exchange_order = normalize_exchange_order(self.exchange_type, order_result, request)
            self._update_ledger_order(
                ledger_order_id,
                status=exchange_order.status,
                exchange_order_id=exchange_order.exchange_order_id,
                filled_qty=exchange_order.filled_qty,
                average_fill_price=exchange_order.average_fill_price,
            )
            if exchange_order.filled_qty > 0 and exchange_order.average_fill_price is not None:
                strategy_ledger.apply_new_fill(
                    exchange_order,
                    order_id=ledger_order_id,
                )
                self._log_trade_execution(
                    symbol=symbol,
                    side=signal_type,
                    confidence_score=confidence_score,
                    executed_price=exchange_order.average_fill_price,
                    executed_qty=exchange_order.filled_qty,
                    order_id=exchange_order.exchange_order_id,
                )

            return order_result

    def evaluate_exit_signal(self, symbol: str, current_price: float) -> Optional[Dict[str, Any]]:
        """원장 기반 종료 정책을 평가해 필요한 SELL 신호를 반환합니다."""
        config = self._get_fund_config()
        if not config or not config.get("is_active"):
            return None

        ledger = AiFundLedger(self.user_id, self.exchange_type)
        position = ledger.get_position(symbol) or self._get_open_position(symbol)
        if not position:
            return None

        entry_price = float(position.get("average_entry_price", position.get("executed_price", 0.0)) or 0.0)
        quantity = float(position.get("quantity", position.get("executed_qty", 0.0)) or 0.0)
        if entry_price <= 0 or current_price <= 0 or quantity <= 0:
            return None

        exit_policy = position.get("exit_policy")
        legacy_policy = not isinstance(exit_policy, dict) or not exit_policy
        if legacy_policy:
            exit_policy = {
                "take_profit_steps": [{
                    "target_pct": float(config.get("target_take_profit_pct", 5.0)),
                    "sell_ratio": 1.0,
                }],
                "stop_loss_pct": float(config.get("stop_loss_pct", config.get("daily_mdd_limit_pct", -2.0))),
                "break_even_after_first_target": False,
            }

        evaluation = evaluate_exit_policy(
            entry_price=entry_price,
            quantity=quantity,
            current_price=current_price,
            policy=exit_policy,
        )
        if evaluation.decision is None:
            if evaluation.next_policy != exit_policy:
                ledger.update_exit_policy(symbol, evaluation.next_policy)
            return None

        reason = evaluation.decision.reason
        if legacy_policy and reason == "TAKE_PROFIT_1":
            reason = "TAKE_PROFIT"
        return {
            "symbol": symbol,
            "signal_type": "SELL",
            "reason": reason,
            "quantity": evaluation.decision.quantity,
            "next_policy": evaluation.next_policy,
        }

    def record_exit_policy(self, symbol: str, policy: dict[str, Any]) -> None:
        """접수된 종료 주문이 반영할 다음 포지션 정책 상태를 저장합니다."""
        AiFundLedger(self.user_id, self.exchange_type).update_exit_policy(symbol, policy)

    def emergency_kill_switch(self) -> bool:
        """Deactivates active AI fund configuration immediately."""
        try:
            res = query_supabase_as_service_role(
                f"admin_ai_fund_configs?user_id=eq.{self.user_id}&exchange_type=eq.{self.exchange_type}",
                method="PATCH",
                json_data={"is_active": False}
            )
            return res is not None
        except Exception:
            logger.exception("Failed to execute emergency kill switch")
            return False

    def _get_fund_config(self) -> Optional[Dict[str, Any]]:
        res = safe_query_supabase_as_service_role(
            "admin_ai_fund_configs",
            params={
                "user_id": f"eq.{self.user_id}",
                "exchange_type": f"eq.{self.exchange_type}"
            }
        )
        if isinstance(res, list) and len(res) > 0:
            return res[0]
        return None

    def _build_client_order_id(
        self,
        config: Dict[str, Any],
        symbol: str,
        side: str,
        signal_id: str | None,
    ) -> str:
        if not signal_id:
            return f"fund-{self.user_id[:8]}-{self.exchange_type}-{symbol.upper()}-{side}-{uuid.uuid4().hex[:12]}"
        identity = ":".join((
            str(config.get("id") or self.user_id),
            self.exchange_type,
            symbol.upper(),
            side,
            str(signal_id),
        ))
        digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()
        return f"fund-{digest[:48]}"

    def _find_order_by_client_order_id(self, client_order_id: str) -> Optional[Dict[str, Any]]:
        rows = safe_query_supabase_as_service_role(
            "ai_fund_orders",
            params={"client_order_id": f"eq.{client_order_id}", "limit": "1"},
        ) or []
        return rows[0] if isinstance(rows, list) and rows else None

    def _find_unresolved_order_for_symbol(
        self,
        symbol: str,
        strategy_id: str,
    ) -> Optional[Dict[str, Any]]:
        rows = safe_query_supabase_as_service_role(
            "ai_fund_orders",
            params={
                "user_id": f"eq.{self.user_id}",
                "exchange_type": f"eq.{self.exchange_type}",
                "strategy_id": f"eq.{strategy_id}",
                "symbol": f"eq.{symbol.upper()}",
                "side": "eq.BUY",
                "status": "in.(PENDING_SUBMIT,SUBMITTED,PARTIALLY_FILLED,CANCEL_REQUESTED,NEEDS_REVIEW)",
                "order": "created_at.desc",
                "limit": "1",
            },
        ) or []
        return rows[0] if isinstance(rows, list) and rows else None

    def _create_pending_order(
        self,
        config: Dict[str, Any],
        request: OrderRequest,
        strategy_id: str = "ml_signal",
    ) -> str:
        order_id = str(uuid.uuid4())
        safe_query_supabase_as_service_role(
            "ai_fund_orders",
            method="POST",
            json_data={
                "id": order_id,
                "user_id": self.user_id,
                "config_id": config.get("id"),
                "exchange_type": self.exchange_type,
                "strategy_id": strategy_id,
                "client_order_id": request.client_order_id,
                "symbol": request.symbol,
                "side": request.side,
                "order_type": request.order_type,
                "requested_qty": request.quantity,
                "requested_price": request.price,
                "status": "PENDING_SUBMIT",
            },
        )
        return order_id

    @staticmethod
    def _assert_strategy_budget(
        config: Dict[str, Any],
        ledger: AiFundLedger,
        strategy_id: str,
        requested_notional: float,
    ) -> None:
        budgets = config.get("strategy_budgets")
        if not isinstance(budgets, dict):
            return
        try:
            budget = float(budgets.get(strategy_id, 0.0) or 0.0)
        except (TypeError, ValueError):
            budget = 0.0
        if budget > 0 and ledger.get_strategy_exposure() + requested_notional > budget:
            raise AdminAiRiskViolation(f"Strategy budget exceeded: {strategy_id}.")

    def _update_ledger_order(
        self,
        order_id: str,
        *,
        status: str,
        exchange_order_id: str | None = None,
        filled_qty: float | None = None,
        average_fill_price: float | None = None,
        failure_reason: str | None = None,
    ) -> None:
        payload: Dict[str, Any] = {"status": status, "last_synced_at": datetime.now(timezone.utc).isoformat()}
        if exchange_order_id is not None:
            payload["exchange_order_id"] = exchange_order_id
        if filled_qty is not None:
            payload["filled_qty"] = filled_qty
        if average_fill_price is not None:
            payload["average_fill_price"] = average_fill_price
        if failure_reason is not None:
            payload["failure_reason"] = failure_reason
        safe_query_supabase_as_service_role(
            f"ai_fund_orders?id=eq.{order_id}",
            method="PATCH",
            json_data=payload,
        )

    def _get_trade_logs(self, params: dict) -> list[dict]:
        res = safe_query_supabase_as_service_role("admin_ai_trade_logs", params=params) or []
        return res if isinstance(res, list) else []

    def _get_daily_pnl_pct(self, config: Dict[str, Any]) -> float:
        allocated_capital = float(config.get("allocated_capital", 0.0))
        if allocated_capital <= 0:
            return 0.0

        today = datetime.now(timezone.utc).date().isoformat()
        logs = self._get_trade_logs({
            "user_id": f"eq.{self.user_id}",
            "exchange_type": f"eq.{self.exchange_type}",
            "status": f"in.({','.join(sorted(SUCCESS_STATUSES))})",
            "order": "created_at.asc",
            "limit": "500",
        })

        realized = 0.0
        positions: dict[str, dict[str, float]] = {}
        for row in logs:
            symbol = str(row.get("symbol") or "").upper()
            if not symbol:
                continue
            side = str(row.get("side") or "").upper()
            qty = float(row.get("executed_qty") or 0.0)
            total_amount = float(row.get("total_amount") or 0.0)
            if side == "SELL":
                position = positions.get(symbol, {"qty": 0.0, "cost": 0.0})
                avg_cost = position["cost"] / position["qty"] if position["qty"] > 0 else 0.0
                sell_cost = avg_cost * qty
                if str(row.get("created_at") or "").startswith(today):
                    realized += total_amount - sell_cost
                if position["qty"] > 0:
                    reduce_qty = min(qty, position["qty"])
                    position["cost"] *= max(position["qty"] - reduce_qty, 0.0) / position["qty"]
                    position["qty"] = max(position["qty"] - qty, 0.0)
                    positions[symbol] = position
            elif side == "BUY":
                position = positions.setdefault(symbol, {"qty": 0.0, "cost": 0.0})
                position["qty"] += qty
                position["cost"] += total_amount
        return (realized / allocated_capital) * 100.0

    def _get_open_position(self, symbol: str) -> Optional[Dict[str, Any]]:
        logs = self._get_trade_logs({
            "user_id": f"eq.{self.user_id}",
            "exchange_type": f"eq.{self.exchange_type}",
            "symbol": f"eq.{symbol}",
            "status": f"in.({','.join(sorted(SUCCESS_STATUSES))})",
            "order": "created_at.asc",
            "limit": "100",
        })

        net_qty = 0.0
        buy_cost = 0.0
        for row in logs:
            side = str(row.get("side") or "").upper()
            qty = float(row.get("executed_qty") or 0.0)
            amount = float(row.get("total_amount") or 0.0)
            if side == "BUY":
                net_qty += qty
                buy_cost += amount
            elif side == "SELL":
                reduce_qty = min(qty, net_qty)
                if net_qty > 0 and reduce_qty > 0:
                    buy_cost *= max(net_qty - reduce_qty, 0.0) / net_qty
                net_qty = max(net_qty - qty, 0.0)

        if net_qty <= 0:
            return None
        return {
            "symbol": symbol,
            "executed_qty": net_qty,
            "executed_price": buy_cost / net_qty if buy_cost > 0 else 0.0,
        }

    def list_open_positions(self) -> list[Dict[str, Any]]:
        logs = self._get_trade_logs({
            "user_id": f"eq.{self.user_id}",
            "exchange_type": f"eq.{self.exchange_type}",
            "status": f"in.({','.join(sorted(SUCCESS_STATUSES))})",
            "order": "created_at.asc",
            "limit": "500",
        })

        positions: dict[str, dict[str, float]] = {}
        for row in logs:
            symbol = str(row.get("symbol") or "").upper()
            if not symbol:
                continue
            side = str(row.get("side") or "").upper()
            qty = float(row.get("executed_qty") or 0.0)
            amount = float(row.get("total_amount") or 0.0)
            position = positions.setdefault(symbol, {"qty": 0.0, "cost": 0.0})
            if side == "BUY":
                position["qty"] += qty
                position["cost"] += amount
            elif side == "SELL":
                reduce_qty = min(qty, position["qty"])
                if position["qty"] > 0 and reduce_qty > 0:
                    position["cost"] *= max(position["qty"] - reduce_qty, 0.0) / position["qty"]
                position["qty"] = max(position["qty"] - qty, 0.0)

        open_positions = []
        for symbol, position in positions.items():
            if position["qty"] <= 0:
                continue
            open_positions.append({
                "symbol": symbol,
                "executed_qty": position["qty"],
                "executed_price": position["cost"] / position["qty"] if position["cost"] > 0 else 0.0,
            })
        return open_positions

    def _log_trade_execution(
        self,
        symbol: str,
        side: str,
        confidence_score: float,
        executed_price: float,
        executed_qty: float,
        order_id: Optional[str]
    ) -> None:
        payload = {
            "user_id": self.user_id,
            "exchange_type": self.exchange_type,
            "symbol": symbol,
            "side": side,
            "confidence_score": confidence_score,
            "executed_price": executed_price,
            "executed_qty": executed_qty,
            "total_amount": executed_price * executed_qty,
            "order_id": order_id,
            "status": "SUCCESS"
        }
        safe_query_supabase_as_service_role(
            "admin_ai_trade_logs",
            method="POST",
            json_data=payload
        )

    def is_symbol_tradable_on_exchange(self, symbol: str) -> bool:
        """Verifies if symbol is listed and tradable on the configured target exchange."""
        clean_target = symbol.replace("USDT", "").replace("-", "").replace("/", "").upper()
        if not clean_target:
            return False

        if self.exchange_type == "coinone":
            from backend.services.coinone_client import CoinoneClient
            markets = CoinoneClient.get_krw_markets()
            if not markets:
                return False
            target_currencies = {m.get("target_currency", "").upper() for m in markets}
            return clean_target in target_currencies
        return True
