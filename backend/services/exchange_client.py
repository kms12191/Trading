from abc import ABC, abstractmethod

from backend.services.ai_fund_exchange import ExchangeCapability


MARKET_CLOSED_ORDER_MESSAGE = "주문 전송 실패\n정규장이 마감되었습니다."


class MarketClosedError(Exception):
    """거래소가 장 마감 또는 주문 불가 시간으로 주문을 거절했을 때 사용합니다."""

    def __init__(self, message: str = MARKET_CLOSED_ORDER_MESSAGE):
        super().__init__(message)


def is_market_closed_order_error(message: str | None) -> bool:
    text = str(message or "").lower()
    return any(keyword in text for keyword in (
        "장 마감",
        "장마감",
        "장 종료",
        "장종료",
        "장운영",
        "거래시간",
        "주문 가능 시간",
        "주문가능시간",
        "주문 가능한 시간",
        "주문가능한시간",
        "주문 시간이 아닙니다",
        "주문시간이 아닙니다",
        "주문 가능한 시간이 아닙니다",
        "주문가능한시간이아닙니다",
        "거래 가능 시간",
        "거래가능시간",
        "거래 가능한 시간이 아닙니다",
        "거래가능한시간이아닙니다",
        "주문 불가 시간",
        "주문불가시간",
        "거래 불가 시간",
        "거래불가시간",
        "market-closed",
        "market_closed",
        "not-trading-hours",
        "not_trading_hours",
        "market closed",
        "market is closed",
        "not trading hours",
        "outside trading hours",
    ))


class ExchangeClient(ABC):
    def get_capabilities(self) -> ExchangeCapability:
        """기존 클라이언트와 호환되는 기본 현물 주문 capability를 반환합니다."""
        return ExchangeCapability(
            supports_spot=True,
            supports_order_lookup=True,
            supports_cancel=callable(getattr(self, "cancel_order", None)),
            supports_market_order=False,
        )

    @abstractmethod
    def get_price(self, symbol: str) -> dict:
        """
        지정한 종목의 현재가, 전일대비 변동률 등을 조회합니다.
        반환값:
            dict: { "current_price": float, "change_rate": float, "raw": dict }
        """
        pass

    @abstractmethod
    def get_balance(self) -> dict:
        """
        총 평가금액, 가용 예수금 및 현재 보유 중인 자산 목록을 조회합니다.
        반환값:
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
        매수 또는 매도 주문을 접수합니다.
        반환값:
            dict: { "order_id": str, "status": str, "raw": dict }
        """
        pass

    @abstractmethod
    def get_order_status(self, order_id: str) -> dict:
        """
        접수된 주문의 체결 상태를 확인합니다.
        반환값:
            dict: { "order_id": str, "status": str, "qty": float, "executed_qty": float, "raw": dict }
        """
        pass
