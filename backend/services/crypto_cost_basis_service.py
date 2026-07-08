TRANSFER_NON_DEDUCTIBLE_STATUSES = {"FAILED", "CANCELED", "CANCELLED", "REJECTED", "EXPIRED"}


def _to_float(value, default: float = 0.0) -> float:
    try:
        if value in (None, ""):
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _get_transfer_fee(row: dict) -> float:
    precheck_payload = row.get("precheck_payload") or {}
    fee = _to_float(row.get("withdraw_fee"))
    if fee <= 0:
        fee = _to_float(row.get("withdrawal_fee"))
    if fee <= 0 and isinstance(precheck_payload, dict):
        fee = _to_float(precheck_payload.get("withdrawal_fee"))
    return fee


def get_transfer_received_amount(row: dict) -> float:
    precheck_payload = row.get("precheck_payload") or {}
    received_amount = _to_float(row.get("received_amount"))
    if received_amount <= 0:
        received_amount = _to_float(row.get("expected_receive_amount"))
    if received_amount <= 0 and isinstance(precheck_payload, dict):
        received_amount = _to_float(precheck_payload.get("estimated_receive_amount"))
    if received_amount <= 0:
        received_amount = _to_float(row.get("amount"))
    return received_amount


def get_transfer_source_amount(row: dict) -> float:
    requested_amount = _to_float(row.get("amount"))
    received_amount = get_transfer_received_amount(row)
    fee = _get_transfer_fee(row)

    if requested_amount > 0 and received_amount > 0 and requested_amount > received_amount:
        return requested_amount
    if received_amount > 0:
        return received_amount + fee
    return requested_amount + fee


def _get_transfer_usdt_krw_rate(row: dict, default_rate: float = 0.0) -> tuple[float, str]:
    precheck_payload = row.get("precheck_payload") or {}
    if isinstance(precheck_payload, dict):
        rate = _to_float(precheck_payload.get("usdt_krw_rate"))
        if rate > 0:
            return rate, str(precheck_payload.get("usdt_krw_rate_source") or "COINONE_USDT_KRW")
        rate = _to_float(precheck_payload.get("tether_krw_rate"))
        if rate > 0:
            return rate, str(precheck_payload.get("tether_krw_rate_source") or "COINONE_USDT_KRW")

    rate = _to_float(row.get("usdt_krw_rate"))
    if rate > 0:
        return rate, str(row.get("usdt_krw_rate_source") or "COINONE_USDT_KRW")
    return default_rate, "DEFAULT_USDT_KRW" if default_rate > 0 else "UNAVAILABLE"


def _get_transfer_source_average_krw(row: dict, source_average_prices: dict[str, float]) -> float:
    precheck_payload = row.get("precheck_payload") or {}
    if isinstance(precheck_payload, dict):
        source_average = _to_float(precheck_payload.get("source_avg_price_krw"))
        if source_average > 0:
            return source_average
    currency = str(row.get("currency") or "").strip().upper()
    return source_average_prices.get(currency, 0.0)


def _get_trade_volume(row: dict, price: float) -> float:
    volume = _to_float(row.get("volume"))
    if volume <= 0 and price > 0:
        volume = _to_float(row.get("order_amount")) / price
    return volume


def build_crypto_average_prices(rows: list[dict], exchange: str = "COINONE") -> dict[str, float]:
    target_exchange = exchange.upper()
    positions: dict[str, dict[str, float]] = {}
    last_buy_prices: dict[str, float] = {}

    for row in rows or []:
        if str(row.get("status") or "").upper() != "EXECUTED":
            continue
        if str(row.get("exchange") or "").upper() != target_exchange:
            continue
        asset_type = str(row.get("asset_type") or "CRYPTO").upper()
        if asset_type != "CRYPTO":
            continue

        symbol = str(row.get("symbol") or row.get("ticker") or "").strip().upper()
        price = _to_float(row.get("price"))
        volume = _get_trade_volume(row, price)
        if not symbol or price <= 0 or volume <= 0:
            continue

        current = positions.setdefault(symbol, {"qty": 0.0, "cost": 0.0})
        side = str(row.get("side") or "").upper()
        if side == "SELL":
            average = current["cost"] / current["qty"] if current["qty"] > 0 else 0.0
            sold_qty = min(volume, current["qty"])
            current["qty"] = max(0.0, current["qty"] - sold_qty)
            current["cost"] = max(0.0, current["cost"] - average * sold_qty)
            continue

        current["qty"] += volume
        current["cost"] += price * volume
        last_buy_prices[symbol] = price

    averages: dict[str, float] = {}
    for symbol, position in positions.items():
        if position["qty"] > 0:
            averages[symbol] = position["cost"] / position["qty"]
        elif symbol in last_buy_prices:
            averages[symbol] = last_buy_prices[symbol]
    return averages


def build_transfer_cost_basis(
    rows: list[dict],
    source_average_prices: dict[str, float],
    default_usdt_krw_rate: float = 0.0,
) -> dict[str, dict[str, float | str]]:
    totals: dict[str, dict[str, float | str]] = {}

    for row in rows or []:
        status = str(row.get("status") or "").upper()
        if status in TRANSFER_NON_DEDUCTIBLE_STATUSES:
            continue

        from_exchange = str(row.get("from_exchange") or "").upper()
        to_exchange = str(row.get("to_exchange") or "").upper()
        symbol = str(row.get("currency") or "").strip().upper()
        if "COINONE" not in from_exchange or "BINANCE" not in to_exchange or not symbol:
            continue

        source_average_krw = _get_transfer_source_average_krw(row, source_average_prices)
        source_qty = get_transfer_source_amount(row)
        received_qty = get_transfer_received_amount(row)
        usdt_krw_rate, rate_source = _get_transfer_usdt_krw_rate(row, default_usdt_krw_rate)
        if source_average_krw <= 0 or source_qty <= 0 or received_qty <= 0 or usdt_krw_rate <= 0:
            continue

        cost_krw = source_average_krw * received_qty
        cost_usdt = cost_krw / usdt_krw_rate
        current = totals.setdefault(symbol, {
            "qty": 0.0,
            "cost_krw": 0.0,
            "cost_usdt": 0.0,
            "usdt_krw_rate": usdt_krw_rate,
            "rate_source": rate_source,
            "source": "TRANSFER_COST_BASIS",
        })
        current["qty"] = _to_float(current.get("qty")) + received_qty
        current["cost_krw"] = _to_float(current.get("cost_krw")) + cost_krw
        current["cost_usdt"] = _to_float(current.get("cost_usdt")) + cost_usdt

    for current in totals.values():
        qty = _to_float(current.get("qty"))
        if qty <= 0:
            continue
        current["avg_price_krw"] = _to_float(current.get("cost_krw")) / qty
        current["avg_price_usdt"] = _to_float(current.get("cost_usdt")) / qty

    return totals


def apply_binance_transfer_cost_basis(balance: dict, cost_basis: dict[str, dict[str, float | str]]) -> None:
    holdings = balance.get("holdings")
    if not isinstance(holdings, list):
        return

    for holding in holdings:
        if not isinstance(holding, dict):
            continue
        symbol = str(holding.get("symbol") or "").strip().upper()
        basis = cost_basis.get(symbol)
        if not basis:
            continue

        avg_price = _to_float(basis.get("avg_price_usdt"))
        current_price = _to_float(holding.get("current_price"))
        qty = _to_float(holding.get("qty"))
        if avg_price <= 0 or qty <= 0:
            continue

        holding["avg_price"] = avg_price
        holding["currency"] = "USDT"
        holding["profit"] = (current_price - avg_price) * qty if current_price > 0 else 0.0
        holding["profit_rate"] = ((current_price - avg_price) / avg_price) * 100 if current_price > 0 else 0.0
        holding["avg_price_source"] = str(basis.get("source") or "TRANSFER_COST_BASIS")
        holding["avg_price_krw"] = _to_float(basis.get("avg_price_krw"))
        holding["usdt_krw_rate"] = _to_float(basis.get("usdt_krw_rate"))
        holding["usdt_krw_rate_source"] = str(basis.get("rate_source") or "")
