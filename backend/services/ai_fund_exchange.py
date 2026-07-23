"""AI 위탁운용에서 거래소별 주문 응답을 공통 형태로 다루기 위한 모델입니다."""

from dataclasses import dataclass, field
from typing import Any


ORDER_STATUS_ALIASES = {
    "SUCCESS": "SUBMITTED",
    "ORDERED": "SUBMITTED",
    "OPEN": "SUBMITTED",
    "NEW": "SUBMITTED",
    "PARTIALLY_FILLED": "PARTIALLY_FILLED",
    "PARTIALLY EXECUTED": "PARTIALLY_FILLED",
    "FILLED": "FILLED",
    "EXECUTED": "FILLED",
    "DONE": "FILLED",
    "CANCELED": "CANCELED",
    "CANCELLED": "CANCELED",
    "REJECTED": "REJECTED",
    "FAILED": "FAILED",
}


@dataclass(frozen=True)
class ExchangeCapability:
    """거래소별 현물 주문 지원 범위와 기본 주문 제약입니다."""

    supports_spot: bool
    supports_order_lookup: bool
    supports_cancel: bool
    supports_market_order: bool
    min_order_amount: float = 0.0

    def supports_order_type(self, order_type: str) -> bool:
        return order_type.upper() == "LIMIT" or self.supports_market_order


@dataclass(frozen=True)
class OrderRequest:
    """거래소에 제출하기 전 AI 위탁운용이 확정한 주문 요청입니다."""

    symbol: str
    side: str
    quantity: float
    client_order_id: str
    order_type: str = "LIMIT"
    price: float | None = None


@dataclass(frozen=True)
class ExchangeOrder:
    """거래소별 응답을 통일한 주문 상태입니다."""

    exchange_order_id: str | None
    client_order_id: str
    symbol: str
    side: str
    requested_qty: float
    filled_qty: float
    average_fill_price: float | None
    status: str
    fee: float
    raw: dict[str, Any] = field(default_factory=dict)


def normalize_exchange_order(
    exchange_type: str,
    payload: dict[str, Any] | None,
    request: OrderRequest,
) -> ExchangeOrder:
    """기존 거래소 클라이언트의 주문 응답을 공통 주문 상태로 변환합니다."""
    raw = dict(payload or {})
    status_raw = str(raw.get("status") or "SUBMITTED").upper()
    status = ORDER_STATUS_ALIASES.get(status_raw, "NEEDS_REVIEW")
    filled_qty = _to_float(
        raw.get("filled_qty", raw.get("executed_qty", raw.get("executed_volume", 0.0)))
    )
    average_fill_price = _to_optional_float(
        raw.get("average_fill_price", raw.get("executed_price", raw.get("price", request.price)))
    )
    return ExchangeOrder(
        exchange_order_id=_first_text(raw, "exchange_order_id", "order_id", "id"),
        client_order_id=request.client_order_id,
        symbol=request.symbol.upper(),
        side=request.side.upper(),
        requested_qty=request.quantity,
        filled_qty=filled_qty,
        average_fill_price=average_fill_price,
        status=status,
        fee=_to_float(raw.get("fee", raw.get("paid_fee", 0.0))),
        raw={"exchange_type": exchange_type.lower(), **raw},
    )


def _first_text(payload: dict[str, Any], *keys: str) -> str | None:
    for key in keys:
        value = payload.get(key)
        if value is not None and str(value):
            return str(value)
    return None


def _to_float(value: Any) -> float:
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _to_optional_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    return _to_float(value)
