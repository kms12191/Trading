import os
import re
import requests
import time
from datetime import datetime, timedelta, timezone

from backend.services.kis_client import KISClient
from backend.services.kis_market_universe import build_turnover_snapshot_rows, clean_stock_name
from backend.services.market_repository import MarketRepository
from backend.services.symbol_metadata import SYMBOL_METADATA
from backend.services.toss_client import TossClient

COINONE_HOME_LIMIT = int(os.getenv("COINONE_HOME_LIMIT", "10"))
HOME_STOCK_LIMIT = int(os.getenv("HOME_STOCK_LIMIT", "10"))
HOME_STOCK_SCAN_LIMIT = int(os.getenv("HOME_STOCK_SCAN_LIMIT", "120"))
HOME_STOCK_SCAN_WORKERS = int(os.getenv("HOME_STOCK_SCAN_WORKERS", "4"))
HOME_STOCK_CACHE_TTL_SECONDS = int(os.getenv("HOME_STOCK_CACHE_TTL_SECONDS", "300"))
HOME_STOCK_STALE_SECONDS = int(os.getenv("HOME_STOCK_STALE_SECONDS", "120"))
HOME_STOCK_PRIORITY_SYMBOLS = [
    symbol.strip().upper()
    for symbol in os.getenv(
        "HOME_STOCK_PRIORITY_SYMBOLS",
        "000660,005930,009150,005380,000270,035420,035720,068270,373220,207940,"
        "006400,051910,066570,105560,055550,028260,012330,000810,086790,096770,"
        "003550,034020,329180,042660,010140,402340,267260,323410,259960,000720",
    ).split(",")
    if symbol.strip()
]
HOME_STOCK_TURNOVER_CACHE = {
    "expires_at": 0.0,
    "rows_by_key": {},
}
KST = timezone(timedelta(hours=9))
COIN_DISPLAY_NAMES = {
    "BTC": "Bitcoin",
    "ETH": "Ethereum",
    "XRP": "XRP",
    "SOL": "Solana",
    "USDT": "Tether",
    "USDC": "USD Coin",
    "DOGE": "Dogecoin",
    "ADA": "Cardano",
    "TRX": "TRON",
    "XLM": "Stellar",
    "SUI": "Sui",
    "WLD": "Worldcoin",
}


def get_kis_env_credentials() -> dict:
    return {
        "appkey": os.getenv("KIS_APPKEY") or os.getenv("APP_Key") or "",
        "appsecret": os.getenv("KIS_APPSECRET") or os.getenv("APP_Secret") or "",
        "cano": os.getenv("KIS_CANO") or os.getenv("CANO") or "",
        "acnt_prdt_cd": os.getenv("KIS_ACNT_PRDT_CD") or "01",
        "env": os.getenv("KIS_ENV", "MOCK").upper(),
    }


def get_toss_env_credentials() -> dict:
    return {
        "client_id": os.getenv("TOSS_API_KEY", ""),
        "client_secret": os.getenv("TOSS_SECRET_KEY", ""),
    }


def to_float(value, default=0.0):
    try:
        if value is None or value == "":
            return default
        return float(str(value).replace(",", "").replace("원", "").replace("%", "").strip())
    except (TypeError, ValueError):
        return default


def parse_change_rate(row: dict) -> float:
    return to_float(row.get("change_rate") or row.get("live_change_rate") or row.get("change"))


def format_krw_compact(value: float) -> str:
    if value >= 100_000_000_0000:
        return f"{value / 100_000_000_0000:,.1f}조"
    if value >= 100_000_000:
        return f"{value / 100_000_000:,.0f}억"
    if value >= 10_000:
        return f"{value / 10_000:,.0f}만"
    return f"{value:,.0f}"


def is_korean_market_open() -> bool:
    now = datetime.now(KST)
    if now.weekday() >= 5:
        return False
    minutes = now.hour * 60 + now.minute
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


def build_snapshot_meta(rows: list[dict]) -> dict:
    parsed_dates = [
        parsed
        for parsed in (parse_datetime(row.get("as_of")) for row in rows or [])
        if parsed is not None
    ]
    latest = max(parsed_dates) if parsed_dates else None
    age_seconds = (datetime.now(timezone.utc) - latest.astimezone(timezone.utc)).total_seconds() if latest else None
    open_market = is_korean_market_open()

    return {
        "source": "KIS_DB_SNAPSHOT",
        "as_of": latest.isoformat() if latest else None,
        "age_seconds": int(age_seconds) if age_seconds is not None else None,
        "stale": bool(age_seconds is None or age_seconds > HOME_STOCK_STALE_SECONDS),
        "market_open": open_market,
        "refresh_interval_seconds": 60 if open_market else 600,
    }


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
        "name": COIN_DISPLAY_NAMES.get(symbol, symbol),
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
    return [
        {**row, "rank": index}
        for index, row in enumerate(rows[:limit], start=1)
    ]


def normalize_market_segment(region: str | None) -> str:
    if region == "국내":
        return "KOSPI"
    if region == "해외":
        return "US"
    return "ALL"


def is_domestic_common_stock_row(row: dict) -> bool:
    symbol = str(row.get("symbol") or row.get("code") or "").strip().upper()
    return bool(re.fullmatch(r"\d{6}|[0-9A-Z]{6}", symbol))


def dedupe_market_rows(rows: list[dict]) -> list[dict]:
    seen = set()
    deduped = []
    for row in rows or []:
        symbol = str(row.get("symbol") or row.get("code") or "").strip().upper()
        if not symbol or symbol in seen:
            continue
        seen.add(symbol)
        updated = dict(row)
        updated["symbol"] = symbol
        if updated.get("name"):
            updated["name"] = clean_stock_name(updated.get("name"))
        deduped.append(updated)
    return deduped


def apply_stock_filters(rows: list[dict], filters: dict, limit: int = HOME_STOCK_LIMIT) -> list[dict]:
    ranking = filters.get("ranking") or filters.get("metric") or "거래대금"
    filtered = list(rows or [])

    if ranking == "거래량":
        filtered.sort(key=lambda row: to_float(row.get("trading_volume")), reverse=True)
    elif ranking == "상승률":
        filtered.sort(key=parse_change_rate, reverse=True)
    elif ranking == "하락률":
        filtered.sort(key=parse_change_rate)
    else:
        filtered.sort(key=lambda row: to_float(row.get("trading_value")), reverse=True)

    reranked = []
    for index, row in enumerate(filtered[:limit], start=1):
        updated = dict(row)
        updated["rank"] = index
        updated["change_rate"] = parse_change_rate(updated)
        reranked.append(updated)
    return reranked


def fetch_top_turnover_stock_rows(
    limit=HOME_STOCK_LIMIT,
    region: str = "전체",
    ranking: str = "거래대금",
    horizon: str = "실시간",
) -> list[dict]:
    now = time.time()
    market_segment = normalize_market_segment(region)
    if market_segment == "US":
        return []

    cache_key = f"{market_segment}:{ranking}:실시간:{limit}"
    cached_rows = HOME_STOCK_TURNOVER_CACHE["rows_by_key"].get(cache_key)
    if cached_rows and now < HOME_STOCK_TURNOVER_CACHE["expires_at"]:
        return cached_rows[:limit]

    repository = MarketRepository()
    lookup_limit = max(limit * 5, 50)
    rows = repository.list_turnover_rankings(
        market_segment=market_segment if market_segment != "US" else "ALL",
        limit=lookup_limit,
    )
    kis = get_kis_env_credentials()
    meta = build_snapshot_meta(rows)
    should_refresh = not rows or meta.get("stale")
    if should_refresh and kis["appkey"] and kis["appsecret"]:
        client = KISClient(
            appkey=kis["appkey"],
            appsecret=kis["appsecret"],
            cano=kis["cano"],
            acnt_prdt_cd=kis["acnt_prdt_cd"],
            env=kis["env"],
        )
        rank_rows = []
        try:
            rank_rows = client.get_turnover_rankings(limit=80)
        except Exception:
            rank_rows = []

        rank_symbols = {
            str(row.get("symbol") or "").strip().upper()
            for row in rank_rows
            if row.get("symbol")
        }
        master_rows = repository.list_symbols(HOME_STOCK_PRIORITY_SYMBOLS) if repository.is_configured else []
        master_by_symbol = {
            str(row.get("symbol") or "").strip().upper(): row
            for row in master_rows
        }
        priority_rows = [
            {
                "symbol": symbol,
                "name": (
                    clean_stock_name(master_by_symbol.get(symbol, {}).get("name"))
                    or SYMBOL_METADATA.get(symbol, {}).get("display_name")
                    or symbol
                ),
                "market_segment": master_by_symbol.get(symbol, {}).get("market_segment") or "KOSPI",
                "market_country": "KR",
            }
            for symbol in HOME_STOCK_PRIORITY_SYMBOLS
            if symbol not in rank_symbols
        ]
        stock_rows = [
            row for row in dedupe_market_rows(priority_rows)
            if is_domestic_common_stock_row(row)
        ]
        snapshot_rows, _ = build_turnover_snapshot_rows(
            stock_rows,
            client,
            max_workers=HOME_STOCK_SCAN_WORKERS,
        )
        rows = dedupe_market_rows(rank_rows + snapshot_rows)[:lookup_limit]
        if rows and repository.is_configured:
            repository.upsert_turnover_latest(rows)
        if repository.is_configured:
            stored_rows = repository.list_turnover_rankings(
                market_segment=market_segment if market_segment != "US" else "ALL",
                limit=lookup_limit,
            )
            if stored_rows:
                rows = stored_rows

    normalized_rows = []
    stock_only_rows = [row for row in rows if is_domestic_common_stock_row(row)]
    for index, row in enumerate(stock_only_rows[:lookup_limit], start=1):
        trading_value = to_float(row.get("trading_value"))
        change_rate = to_float(row.get("change_rate"))
        current_price = to_float(row.get("current_price"))
        prefix = "+" if change_rate > 0 else ""

        normalized_rows.append({
            "rank": index,
            "name": clean_stock_name(row.get("name")) or row.get("symbol"),
            "code": row.get("symbol"),
            "price": f"{current_price:,.0f}" if current_price else "-",
            "change": f"{prefix}{change_rate:.2f}%",
            "value": format_krw_compact(trading_value) if trading_value else "-",
            "trading_value": trading_value,
            "trading_volume": to_float(row.get("trading_volume")),
            "market_segment": row.get("market_segment"),
            "as_of": row.get("as_of"),
        })

    normalized_rows = apply_stock_filters(
        normalized_rows,
        {"ranking": ranking},
        limit=limit,
    )
    HOME_STOCK_TURNOVER_CACHE["rows_by_key"][cache_key] = normalized_rows
    HOME_STOCK_TURNOVER_CACHE["expires_at"] = time.time() + HOME_STOCK_CACHE_TTL_SECONDS
    return normalized_rows


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
    env_credentials = get_kis_env_credentials()
    return {
        "appkey": data.get("appkey") or env_credentials["appkey"],
        "appsecret": data.get("appsecret") or env_credentials["appsecret"],
        "cano": data.get("cano") or env_credentials["cano"],
        "acnt_prdt_cd": data.get("acnt_prdt_cd") or env_credentials["acnt_prdt_cd"],
        "env": (data.get("env") or env_credentials["env"] or "MOCK").upper(),
    }


def fetch_toss_price(symbol: str) -> dict:
    toss = get_toss_env_credentials()
    if not (toss["client_id"] and toss["client_secret"]):
        raise Exception("TOSS_API_KEY 또는 TOSS_SECRET_KEY가 설정되지 않았습니다.")

    client = TossClient(
        client_id=toss["client_id"],
        client_secret=toss["client_secret"],
        env="REAL",
    )
    return client.get_price(symbol)


def enrich_stock_rows_with_toss(rows: list[dict]) -> list[dict]:
    enriched_rows = []

    for row in rows or []:
        symbol = str(row.get("code") or row.get("symbol") or "").strip()
        enriched = dict(row)

        if enriched.get("price") and enriched.get("change") and enriched.get("value"):
            enriched["live_symbol_used"] = symbol
            enriched["live_price"] = to_float(enriched.get("current_price") or enriched.get("price"))
            enriched["live_change_rate"] = to_float(enriched.get("change_rate"))
            enriched_rows.append(enriched)
            continue

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
                if not enriched.get("value") and enriched.get("trading_value"):
                    enriched["value"] = format_krw_compact(to_float(enriched.get("trading_value")))
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
        "market_snapshot": {},
        "updated_at": datetime.utcnow().isoformat() + "Z",
        "message": "",
    }

    try:
        result["coins"] = fetch_coinone_overview()
    except Exception as coin_error:
        result["message"] = f"Coinone 조회 실패: {str(coin_error)}"

    try:
        filters = data.get("filters") or {}
        ranking = filters.get("ranking") or filters.get("metric") or "거래대금"
        stock_rows = data.get("stock_rows") or fetch_top_turnover_stock_rows(
            region=filters.get("region", "전체"),
            ranking=ranking,
            horizon=filters.get("horizon", "실시간"),
        )
        result["stocks"] = enrich_stock_rows_with_toss(stock_rows)
        result["market_snapshot"] = build_snapshot_meta(result["stocks"])
        if not result["stocks"]:
            empty_reason = "해외 주식 랭킹은 아직 지원하지 않습니다." if normalize_market_segment(filters.get("region")) == "US" else "주식 거래대금 스냅샷 데이터가 아직 없습니다."
            result["message"] = (result["message"] + " " if result["message"] else "") + empty_reason
    except Exception as stock_error:
        result["stocks"] = []
        result["message"] = (result["message"] + " " if result["message"] else "") + f"주식 거래대금 순위 조회 실패: {str(stock_error)}"

    if not (appkey and appsecret and cano):
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
