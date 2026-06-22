from abc import ABC, abstractmethod

class ExchangeClient(ABC):
    @abstractmethod
    def get_price(self, symbol: str) -> dict:
        """
        Get current price, change rate, etc. for a given symbol.
        Returns:
            dict: { "current_price": float, "change_rate": float, "raw": dict }
        """
        pass

    @abstractmethod
    def get_balance(self) -> dict:
        """
        Get total balance, available cash, and currently held assets.
        Returns:
            dict: {
                "total_evaluation": float,
                "available_cash": float,
                "holdings": list of dict (symbol, name, qty, avg_price, current_price, profit, profit_rate)
            }
        """
        pass

    @abstractmethod
    def place_order(self, symbol: str, qty: float, side: str, ord_type: str, price: float = None) -> dict:
        """
        Place a buy or sell order.
        Returns:
            dict: { "order_id": str, "status": str, "raw": dict }
        """
        pass

    @abstractmethod
    def get_order_status(self, order_id: str) -> dict:
        """
        Get status of a placed order.
        Returns:
            dict: { "order_id": str, "status": str, "qty": float, "executed_qty": float, "raw": dict }
        """
        pass
