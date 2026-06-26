import os
from datetime import datetime, timedelta, timezone
from typing import Any

import requests


KST = timezone(timedelta(hours=9))
MARKET_INDEX_OPEN_STALE_SECONDS = int(os.getenv("MARKET_INDEX_OPEN_STALE_SECONDS", "180"))
MARKET_INDEX_CLOSED_STALE_SECONDS = int(os.getenv("MARKET_INDEX_CLOSED_STALE_SECONDS", "1800"))

INDEX_DEFINITIONS = [
    {
        "symbol": "USDKRW",
        "label": "USD/KRW",
        "ticker": "USDKRW=X",
        "currency": "KRW",
        "market_country": "KR",
        "display_order": 10,
    },
    {
        "symbol": "KOSPI",
        "label": "KOSPI",
        "ticker": "^KS11",
        "currency": "KRW",
        "market_country": "KR",
        "display_order": 20,
    },
    {
        "symbol": "KOSDAQ",
        "label": "KOSDAQ",
        "ticker": "^KQ11",
        "currency": "KRW",
        "market_country": "KR",
        "display_order": 30,
    },
    {
        "symbol": "NASDAQ",
        "label": "NASDAQ",
        "ticker": "^IXIC",
        "currency": "USD",
        "market_country": "US",
        "display_order": 40,
    },
    {
        "symbol": "NASDAQ100_F",
        "label": "NASDAQ 100 Futures",
        "ticker": "NQ=F",
        "currency": "USD",
        "market_country": "US",
        "display_order": 50,
    },
    {
        "symbol": "SP500",
        "label": "S&P 500",
        "ticker": "^GSPC",
        "currency": "USD",
        "market_country": "US",
        "display_order": 60,
    },
]


def is_korean_market_open(now: datetime | None = None) -> bool:
    current = now or datetime.now(KST)
    if current.weekday() >= 5:
        return False
    minutes = current.hour * 60 + current.minute
    return 9 * 60 <= minutes <= 15 * 60 + 30


def parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        normalized = str(value).replace("Z", "+00:00")
        parsed = datetime.fromisoformat(normalized)
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed
    except ValueError:
        return None


def fetch_yahoo_index_snapshot(definition: dict[str, Any]) -> dict[str, Any]:
    response = requests.get(
        f"https://query1.finance.yahoo.com/v8/finance/chart/{definition['ticker']}",
        params={
            "range": "5d",
            "interval": "1d",
            "includePrePost": "true",
            "events": "div,splits",
        },
        headers={
            "User-Agent": "Mozilla/5.0",
            "Accept": "application/json",
        },
        timeout=20,
    )
    response.raise_for_status()
    payload = response.json()
    result = ((payload.get("chart") or {}).get("result") or [None])[0]
    if not result:
        raise RuntimeError(f"Yahoo response missing result for {definition['ticker']}")

    meta = result.get("meta") or {}
    price = meta.get("regularMarketPrice")
    previous_close = meta.get("previousClose") or meta.get("chartPreviousClose")
    market_time = meta.get("regularMarketTime")
    currency = meta.get("currency") or definition["currency"]

    if price is None or previous_close in (None, 0):
        closes = (((result.get("indicators") or {}).get("quote") or [{}])[0]).get("close") or []
        closes = [float(item) for item in closes if item is not None]
        if len(closes) < 2:
            raise RuntimeError(f"Not enough close prices for {definition['ticker']}")
        price = closes[-1]
        previous_close = closes[-2]

    price = float(price)
    previous_close = float(previous_close)
    change_value = price - previous_close
    change_percent = (change_value / previous_close * 100) if previous_close else 0.0
    as_of = (
        datetime.fromtimestamp(int(market_time), tz=timezone.utc).isoformat()
        if market_time
        else datetime.now(timezone.utc).isoformat()
    )

    return {
        "symbol": definition["symbol"],
        "label": definition["label"],
        "source": "YAHOO_FINANCE",
        "market_country": definition["market_country"],
        "ticker": definition["ticker"],
        "current_value": price,
        "change_value": change_value,
        "change_percent": change_percent,
        "currency": currency,
        "display_order": definition["display_order"],
        "as_of": as_of,
        "raw_payload": payload,
    }


def collect_market_index_rows() -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    rows: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []

    for definition in INDEX_DEFINITIONS:
        try:
            rows.append(fetch_yahoo_index_snapshot(definition))
        except Exception as error:
            errors.append({
                "symbol": definition["symbol"],
                "message": str(error),
            })

    return rows, errors


def serialize_market_index_rows(rows: list[dict[str, Any]]) -> dict[str, Any]:
    open_market = is_korean_market_open()
    stale_seconds = MARKET_INDEX_OPEN_STALE_SECONDS if open_market else MARKET_INDEX_CLOSED_STALE_SECONDS

    items: list[dict[str, Any]] = []
    latest_updated_at: datetime | None = None

    for row in rows:
        as_of = parse_datetime(row.get("as_of"))
        if as_of and (latest_updated_at is None or as_of > latest_updated_at):
            latest_updated_at = as_of

        age_seconds = None
        if as_of:
            age_seconds = (datetime.now(timezone.utc) - as_of.astimezone(timezone.utc)).total_seconds()

        change_value = float(row.get("change_value") or 0)
        items.append({
            "key": row.get("symbol"),
            "label": row.get("label") or row.get("symbol"),
            "value": float(row.get("current_value") or 0),
            "change": change_value,
            "changePercent": float(row.get("change_percent") or 0),
            "direction": "up" if change_value > 0 else "down" if change_value < 0 else "flat",
            "updatedAt": row.get("as_of"),
            "currency": row.get("currency") or "USD",
            "stale": bool(age_seconds is None or age_seconds > stale_seconds),
        })

    return {
        "items": items,
        "fetchedAt": latest_updated_at.astimezone(timezone.utc).isoformat().replace("+00:00", "Z") if latest_updated_at else None,
        "source": "supabase.market_indices_latest",
    }
