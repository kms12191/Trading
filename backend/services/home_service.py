import os
import re
import requests
from datetime import datetime

from backend.services.kis_client import KISClient
from backend.services.toss_client import TossClient

COINONE_HOME_LIMIT = int(os.getenv("COINONE_HOME_LIMIT", "20"))
KIS_APPKEY = os.getenv("KIS_APPKEY")
KIS_APPSECRET = os.getenv("KIS_APPSECRET")
KIS_CANO = os.getenv("KIS_CANO")
KIS_ACNT_PRDT_CD = os.getenv("KIS_ACNT_PRDT_CD")
KIS_ENV = os.getenv("KIS_ENV", "MOCK")
TOSS_API_KEY = os.getenv("TOSS_API_KEY", "")
TOSS_SECRET_KEY = os.getenv("TOSS_SECRET_KEY", "")

DEFAULT_STOCK_UNIVERSE = [
    {"rank": 1, "name": "SK하이닉스", "code": "000660", "value": "540억"},
    {"rank": 2, "name": "삼성전자", "code": "005930", "value": "318억"},
    {"rank": 3, "name": "NAVER", "code": "035420", "value": "287억"},
    {"rank": 4, "name": "LG에너지솔루션", "code": "373220", "value": "251억"},
    {"rank": 5, "name": "현대차", "code": "005380", "value": "219억"},
    {"rank": 6, "name": "삼성바이오로직스", "code": "207940", "value": "193억"},
    {"rank": 7, "name": "기아", "code": "000270", "value": "182억"},
    {"rank": 8, "name": "KB금융", "code": "105560", "value": "166억"},
    {"rank": 9, "name": "셀트리온", "code": "068270", "value": "158억"},
    {"rank": 10, "name": "신한지주", "code": "055550", "value": "145억"},
]


def to_float(value, default=0.0):
    try:
        if value is None or value == "":
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def normalize_coinone_ticker(symbol: str, ticker: dict) -> dict:
    last = to_float(
        ticker.get("last")
        or ticker.get("close")
        or ticker.get("price")
        or ticker.get("last_price")
    )
    first = to_float(
        ticker.get("first")
        or ticker.get("open")
        or ticker.get("yesterday_price")
        or ticker.get("prev_close")
    )
    high = to_float(ticker.get("high"))
    low = to_float(ticker.get("low"))
    change_rate = to_float(
        ticker.get("change_rate")
        or ticker.get("rate")
        or ticker.get("change")
        or ticker.get("price_change_percent")
    )
    trading_volume = to_float(
        ticker.get("volume")
        or ticker.get("trading_volume")
        or ticker.get("quote_volume")
        or ticker.get("acc_volume")
    )
    trading_value = to_float(
        ticker.get("quote_volume")
        or ticker.get("trading_value")
        or ticker.get("acc_trading_value")
    )

    if not change_rate and first:
        change_rate = ((last - first) / first) * 100 if first else 0.0

    if not first:
        first = last

    if not trading_value and last and trading_volume:
        trading_value = last * trading_volume

    return {
        "symbol": symbol,
        "name": symbol,
        "price": last,
        "open": first,
        "high": high,
        "low": low,
        "change_rate": change_rate,
        "trading_volume": trading_volume,
        "trading_value": trading_value,
    }


def fetch_coinone_overview(limit=COINONE_HOME_LIMIT) -> list[dict]:
    url = "https://api.coinone.co.kr/public/v2/ticker_new/KRW"
    response = requests.get(url, params={"additional_data": "true"}, timeout=10)
    response.raise_for_status()
    payload = response.json()
    if payload.get("result") not in (None, "success"):
        raise Exception(payload.get("error_message") or payload.get("message") or "Coinone API error")

    rows = []
    for ticker in payload.get("tickers", []):
        symbol = str(
            ticker.get("target_currency")
            or ticker.get("currency")
            or ticker.get("symbol")
            or ""
        ).upper().strip()
        if not symbol:
            continue
        rows.append(normalize_coinone_ticker(symbol, ticker))

    rows.sort(key=lambda item: (item.get("trading_value", 0.0), abs(item.get("change_rate", 0.0))), reverse=True)
    return rows[:limit]


def split_kis_holdings(holdings: list[dict]) -> tuple[list[dict], list[dict]]:
    domestic = []
    foreign = []

    for stock in holdings or []:
        symbol = str(stock.get("symbol", "")).strip()
        row = {
            "symbol": symbol,
            "name": stock.get("name", symbol),
            "qty": to_float(stock.get("qty")),
            "avg_price": to_float(stock.get("avg_price")),
            "current_price": to_float(stock.get("current_price")),
            "profit": to_float(stock.get("profit")),
            "profit_rate": to_float(stock.get("profit_rate")),
        }

        if re.search(r"[A-Za-z]", symbol):
            foreign.append(row)
        else:
            domestic.append(row)

    domestic.sort(key=lambda item: abs(item["profit_rate"]), reverse=True)
    foreign.sort(key=lambda item: abs(item["profit_rate"]), reverse=True)
    return domestic, foreign


def resolve_kis_credentials(data: dict) -> dict:
    return {
        "appkey": data.get("appkey") or KIS_APPKEY,
        "appsecret": data.get("appsecret") or KIS_APPSECRET,
        "cano": data.get("cano") or KIS_CANO,
        "acnt_prdt_cd": data.get("acnt_prdt_cd") or KIS_ACNT_PRDT_CD,
        "env": (data.get("env") or KIS_ENV or "MOCK").upper(),
    }


def fetch_toss_price(symbol: str) -> dict:
    if not (TOSS_API_KEY and TOSS_SECRET_KEY):
        raise Exception("TOSS_API_KEY 또는 TOSS_SECRET_KEY가 설정되지 않았습니다.")

    client = TossClient(
        client_id=TOSS_API_KEY,
        client_secret=TOSS_SECRET_KEY,
        env="REAL",
    )
    return client.get_price(symbol)


def enrich_stock_rows_with_toss(rows: list[dict]) -> list[dict]:
    enriched_rows = []

    for row in rows or []:
        symbol = str(row.get("code") or row.get("symbol") or "").strip()
        enriched = dict(row)

        if symbol:
            try:
                quote = fetch_toss_price(symbol)
                current_price = to_float(quote.get("current_price"))
                prev_close = to_float(quote.get("previous_close"))
                change_rate = to_float(quote.get("change_rate"))

                if current_price and prev_close:
                    change_rate = ((current_price - prev_close) / prev_close) * 100 if prev_close else 0.0

                if current_price:
                    enriched["price"] = f"{current_price:,.0f}"
                prefix = "+" if change_rate > 0 else ""
                enriched["change"] = f"{prefix}{change_rate:.2f}%"
                enriched["live_symbol_used"] = quote.get("symbol_used", symbol)
                enriched["live_price"] = current_price
                enriched["live_prev_close"] = prev_close
                enriched["live_change_rate"] = change_rate
                enriched["live_raw"] = quote.get("raw")
                raw_quote = quote.get("raw")
                if not current_price and not change_rate and isinstance(raw_quote, dict):
                    error_obj = raw_quote.get("error")
                    if error_obj:
                        enriched["live_error"] = error_obj if isinstance(error_obj, str) else str(error_obj)
            except Exception:
                pass

        enriched_rows.append(enriched)

    return enriched_rows


def build_home_overview(data: dict) -> dict:
    kis = resolve_kis_credentials(data)
    appkey = kis["appkey"]
    appsecret = kis["appsecret"]
    cano = kis["cano"]
    acnt_prdt_cd = kis["acnt_prdt_cd"]
    env = kis["env"]

    result = {
        "kis": None,
        "coins": [],
        "stocks": [],
        "toss_debug": [],
        "updated_at": datetime.utcnow().isoformat() + "Z",
        "message": "",
    }

    try:
        result["coins"] = fetch_coinone_overview()
    except Exception as coin_error:
        result["message"] = f"Coinone 조회 실패: {str(coin_error)}"

    stock_rows = data.get("stock_rows") or DEFAULT_STOCK_UNIVERSE
    result["stocks"] = enrich_stock_rows_with_toss(stock_rows)
    result["toss_debug"] = [
        {
            "symbol": row.get("code") or row.get("symbol"),
            "used_symbol": row.get("live_symbol_used"),
            "price": row.get("live_price"),
            "prev_close": row.get("live_prev_close"),
            "change_rate": row.get("live_change_rate"),
            "error": row.get("live_error"),
            "raw": row.get("live_raw"),
            }
            for row in result["stocks"]
            if row.get("live_symbol_used")
        ]

    if not (appkey and appsecret and cano):
        if not result["message"]:
            result["message"] = "KIS 환경변수가 없어 국내/해외 보유 종목은 비어 있습니다."
        return result

    client = KISClient(
        appkey=appkey,
        appsecret=appsecret,
        cano=cano,
        acnt_prdt_cd=acnt_prdt_cd,
        env=env,
    )

    balance = client.get_balance()
    domestic_holdings, foreign_holdings = split_kis_holdings(balance.get("holdings", []))

    result["kis"] = {
        "total_evaluation": to_float(balance.get("total_evaluation")),
        "available_cash": to_float(balance.get("available_cash")),
        "domestic": domestic_holdings,
        "foreign": foreign_holdings,
    }
    return result
