import logging
from typing import Any, Dict, Optional

from backend.services.lock_service import distributed_lock
from backend.services.supabase_client import safe_query_supabase_as_service_role, query_supabase_as_service_role

logger = logging.getLogger(__name__)


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


            max_pos_size = float(config.get("max_position_size", 0.0))
            if max_pos_size <= 0:
                raise AdminAiRiskViolation("Max position size is zero or invalid.")

            quantity = max_pos_size / current_price if current_price > 0 else 0
            if quantity <= 0:
                raise AdminAiRiskViolation("Calculated trade quantity is invalid.")

            logger.info(
                f"[AdminAiTrader] EXECUTING {signal_type} for {symbol} | Qty: {quantity:.6f} @ {current_price}"
            )

            order_result = exchange_client.place_order(
                symbol=symbol,
                side=signal_type.lower(),
                order_type="market",
                quantity=quantity,
                price=current_price
            )

            self._log_trade_execution(
                symbol=symbol,
                side=signal_type,
                confidence_score=confidence_score,
                executed_price=current_price,
                executed_qty=quantity,
                order_id=order_result.get("order_id") if isinstance(order_result, dict) else None
            )

            return order_result

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
            if markets:
                target_currencies = {m.get("target_currency", "").upper() for m in markets}
                return clean_target in target_currencies
        return True

