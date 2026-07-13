import json
import math
import os
import re
from decimal import Decimal, InvalidOperation, ROUND_DOWN
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from urllib.parse import urlencode

import requests

from backend.services.auth_service import get_user_id_from_header
from backend.services.chatbot.conversation_repository import ChatbotConversationRepository
from backend.services.supabase_client import query_supabase, safe_query_supabase
from backend.services.symbol_metadata import enrich_symbol
from backend.services.chatbot.web_fallback_search_service import ChatbotWebFallbackSearchService
from backend.services.chatbot.safety_guard import enforce_tool_safety
from backend.services.chatbot.order_parser import ParsedOrderIntent, parse_order_intent
from backend.services.chatbot.portfolio_summary_service import (
    build_portfolio_totals,
    format_portfolio_reply,
    normalize_account_summary,
)
from backend.services.chatbot.recommendation_service import ChatbotRecommendationService


API_BASE_URL = os.getenv("CHATBOT_INTERNAL_API_BASE_URL", "http://localhost:5050")
OPEN_ORDER_STATUSES = ("PENDING", "APPROVED", "ORDERED", "OPEN", "PARTIALLY_FILLED", "MODIFIED")
_conversation_repository = ChatbotConversationRepository()

SYMBOL_QUERY_ALIASES = {
    "삼전": "삼성전자",
    "하닉": "SK하이닉스",
    "하이닉스": "SK하이닉스",
    "애플": "AAPL",
    "마이크로소프트": "MSFT",
    "마소": "MSFT",
    "엔비디아": "NVDA",
    "아마존": "AMZN",
    "구글": "GOOGL",
    "알파벳": "GOOGL",
    "메타": "META",
    "테슬라": "TSLA",
    "브로드컴": "AVGO",
    "넷플릭스": "NFLX",
    "코스트코": "COST",
    "오라클": "ORCL",
    "어도비": "ADBE",
    "레딧": "RDDT",
    "REDDIT": "RDDT",
    "퀄컴": "QCOM",
    "인텔": "INTC",
    "팔란티어": "PLTR",
    "우버": "UBER",
    "비트": "BTC",
    "비트코인": "BTC",
    "이더": "ETH",
    "이더리움": "ETH",
    "리플": "XRP",
    "엑스알피": "XRP",
    "도지": "DOGE",
    "도지코인": "DOGE",
    "테더": "USDT",
    "솔라나": "SOL",
    "에이다": "ADA",
    "트론": "TRX",
}

SYMBOL_COMMAND_PATTERN = re.compile(
    r"(관심\s*종목|관심종목|설정해줘|추가해줘|등록해줘|보여줘|조회해줘|알려줘|"
    r"거래내역|거래\s*내역|주문내역|주문\s*내역|뉴스|공시|시세|환율|"
    r"설정|추가|등록|해제|삭제|조회|검색)"
)

KOREAN_MONEY_NUMBER_PATTERN = re.compile(
    r"[일한이삼사오육칠팔구십백천만]+\s*(?:만원|천원|원|만)"
)


@lru_cache(maxsize=1)
def _load_training_universe_symbols() -> set[str]:
    universe_path = Path(__file__).resolve().parents[3] / "ml" / "data" / "reference" / "training_universes.json"
    try:
        payload = json.loads(universe_path.read_text(encoding="utf-8"))
    except Exception:
        return set()

    symbols: set[str] = set()
    for values in payload.values() if isinstance(payload, dict) else []:
        if not isinstance(values, list):
            continue
        for value in values:
            symbol = str(value or "").strip().upper()
            if symbol:
                symbols.add(symbol)
    return symbols


def _normalize_symbol_candidate(candidate: str) -> str:
    symbol = str(candidate or "").strip()
    if not symbol:
        return ""

    alias = SYMBOL_QUERY_ALIASES.get(symbol) or SYMBOL_QUERY_ALIASES.get(symbol.upper())
    if alias:
        return alias

    upper_symbol = symbol.upper()
    training_symbols = _load_training_universe_symbols()
    if upper_symbol in training_symbols and upper_symbol.endswith("USDT") and len(upper_symbol) > 4:
        return upper_symbol[:-4]
    if upper_symbol in training_symbols:
        return upper_symbol
    return symbol


def list_available_tools() -> list[str]:
    return [
        "get_home_market_rankings",
        "get_portfolio_summary",
        "add_watchlist_item",
        "get_holdings",
        "search_trade_history",
        "list_open_orders",
        "get_exchange_rate",
        "get_asset_price",
        "search_web",
        "get_asset_outlook",
    ]


def _auth_headers(auth_header: str) -> dict:
    return {
        "Authorization": auth_header,
        "Content-Type": "application/json",
    }


def _post_internal(path: str, auth_header: str, body: dict | None = None) -> dict:
    response = requests.post(
        f"{API_BASE_URL}{path}",
        headers=_auth_headers(auth_header),
        json=body or {},
        timeout=30,
    )
    payload = response.json() if response.text else {}
    if response.status_code >= 400 or payload.get("success") is False:
        raise RuntimeError(payload.get("message") or payload.get("error", {}).get("title") or "내부 API 호출에 실패했습니다.")
    return payload


def _get_internal(path: str, auth_header: str, params: dict | None = None) -> dict:
    query = f"?{urlencode(params)}" if params else ""
    response = requests.get(
        f"{API_BASE_URL}{path}{query}",
        headers={"Authorization": auth_header},
        timeout=30,
    )
    payload = response.json() if response.text else {}
    if response.status_code >= 400 or payload.get("success") is False:
        raise RuntimeError(payload.get("message") or payload.get("error", {}).get("title") or "내부 API 호출에 실패했습니다.")
    return payload


def _to_float(value, default: float = 0.0) -> float:
    try:
        return float(str(value).replace(",", ""))
    except (TypeError, ValueError):
        return default


def _format_money(value, currency: str = "KRW") -> str:
    amount = _to_float(value)
    if currency == "USD":
        return f"${amount:,.2f}"
    if currency in {"USDT", "BTC", "ETH"}:
        return f"{amount:,.4f} {currency}"
    return f"{amount:,.0f}원"


def _format_quantity(value) -> str:
    qty = _to_float(value)
    if qty == int(qty):
        return f"{int(qty):,}"
    return f"{qty:,.8f}".rstrip("0").rstrip(".")


def _extract_symbol_query(text: str) -> str:
    ticker_match = re.search(r"(?<![A-Za-z0-9._-])([A-Za-z][A-Za-z0-9._-]{1,11})(?:의|은|는|이|가|을|를|에|에서)?", text)
    if ticker_match:
        return _normalize_symbol_candidate(ticker_match.group(1))

    cleaned = SYMBOL_COMMAND_PATTERN.sub(" ", text)
    cleaned = re.sub(r"\d+(?:\.\d+)?\s*(만원|천원|원|만)", " ", cleaned)
    cleaned = KOREAN_MONEY_NUMBER_PATTERN.sub(" ", cleaned)
    cleaned = re.sub(r"(?<![가-힣])만원\s*(이상|이하|초과|미만|넘는|넘어|부터)?", " ", cleaned)
    cleaned = re.sub(r"(이상|이하|초과|미만|넘는|넘어|부터|전체|최근|상태|매수|매도|취소|체결|완료|실패|조회|검색|확인|내|나의|내가|내역|목록|전망|분석|어때|오를까|괜찮아|살까)", " ", cleaned)
    cleaned = re.sub(r"(?<=\S)(의|은|는|이|가|을|를)$", " ", cleaned)
    cleaned = re.sub(r"[^0-9A-Za-z가-힣._-]+", " ", cleaned)
    candidates = [part.strip() for part in cleaned.split() if part.strip()]
    if not candidates:
        return ""
    candidate = candidates[0]
    return _normalize_symbol_candidate(candidate)


def _is_likely_symbol_token(value: str) -> bool:
    token = str(value or "").strip().upper()
    return bool(re.fullmatch(r"[A-Z0-9._-]{2,12}", token))


def _resolve_symbol(auth_header: str, query: str) -> dict:
    if not query:
        raise ValueError("종목명 또는 종목코드가 필요합니다.")
    payload = _get_internal("/api/symbol/lookup", auth_header, params={"query": query})
    data = payload.get("data") or {}
    if not data.get("symbol"):
        raise ValueError("종목을 찾지 못했습니다.")
    return data


def _detect_exchange(text: str) -> str | None:
    normalized = text.upper()
    if "토스" in text or "TOSS" in normalized:
        return "TOSS"
    if "KIS" in normalized or "한국투자" in text or "한투" in text:
        return "KIS"
    if "코인원" in text or "COINONE" in normalized:
        return "COINONE"
    if "바이낸스" in text or "BINANCE" in normalized:
        return "BINANCE"
    return None


def _default_exchange_for_asset(asset_type: str, market: str) -> str:
    if str(asset_type or "").upper() == "CRYPTO":
        return "COINONE"
    return "TOSS"


def _detect_env(text: str) -> str | None:
    if "모의" in text or "MOCK" in text.upper():
        return "MOCK"
    if "실전" in text or "실거래" in text or "REAL" in text.upper():
        return "REAL"
    return None


def _detect_ranking(text: str) -> str:
    if "상승" in text:
        return "상승률"
    if "하락" in text:
        return "하락률"
    if "거래량" in text:
        return "거래량"
    return "거래대금"


def _detect_market_segment(text: str) -> str:
    upper_text = text.upper()
    if "코인" in text or "CRYPTO" in upper_text:
        return "CRYPTO"
    if "해외" in text or "미국" in text or "US" in upper_text:
        return "해외"
    if "국내" in text or "한국" in text or "KR" in upper_text:
        return "국내"
    return "국내"


def _detect_limit(text: str, default: int = 5, maximum: int = 20) -> int:
    match = re.search(r"(\d+)\s*(개|건|위)", text)
    if not match:
        return default
    return min(max(int(match.group(1)), 1), maximum)


def _is_foreign_market_row(row: dict) -> bool:
    market_text = str(
        row.get("market_segment")
        or row.get("market_country")
        or row.get("region")
        or row.get("country")
        or ""
    ).upper()
    asset_type = str(row.get("asset_type") or row.get("assetType") or "").upper()
    symbol = str(row.get("symbol") or row.get("code") or row.get("ticker") or "").upper()
    explicit_foreign = any(token in market_text for token in ["US", "USA", "NASDAQ", "NYSE", "AMEX", "해외"])
    return explicit_foreign or (asset_type == "STOCK" and bool(re.match(r"^[A-Z.\-]+$", symbol)))


def _numeric_change(row: dict) -> float:
    raw = (
        row.get("change_rate")
        or row.get("changeRate")
        or row.get("change_percent")
        or row.get("changePercent")
        or row.get("live_change_rate")
        or row.get("change")
    )
    try:
        return float(str(raw or "").replace("%", "").replace("+", "").replace(",", ""))
    except ValueError:
        return 0.0


def _numeric_metric(row: dict, ranking: str) -> float:
    raw = (row.get("trading_volume") or row.get("volume")) if ranking == "거래량" else (row.get("trading_value") or row.get("value"))
    text = str(raw or "").replace(",", "").strip()
    try:
        number_part = float(re.sub(r"[^0-9.-]", "", text))
    except ValueError:
        return 0.0
    if "조" in text:
        return number_part * 1_000_000_000_000
    if "억" in text:
        return number_part * 100_000_000
    if "만" in text:
        return number_part * 10_000
    return number_part


def _apply_home_market_filters(rows: list[dict], region: str, ranking: str) -> list[dict]:
    if region in {"국내", "해외"}:
        filtered = [
            row for row in rows
            if (_is_foreign_market_row(row) if region == "해외" else not _is_foreign_market_row(row))
        ]
    else:
        filtered = list(rows)

    if ranking == "상승률":
        filtered.sort(key=_numeric_change, reverse=True)
    elif ranking == "하락률":
        filtered.sort(key=_numeric_change)
    else:
        filtered.sort(key=lambda row: _numeric_metric(row, ranking), reverse=True)

    return [{**row, "rank": index + 1} for index, row in enumerate(filtered)]


def get_home_market_rankings(auth_header: str, message: str) -> dict:
    ranking = _detect_ranking(message)
    segment = _detect_market_segment(message)
    limit = _detect_limit(message)
    region = "국내" if segment == "CRYPTO" else segment

    if segment == "CRYPTO":
        payload = _get_internal(
            "/api/market/rankings",
            auth_header,
            params={
                "asset_type": "CRYPTO",
                "ranking": ranking,
                "limit": limit,
            },
        )
        data = payload.get("data") or {}
        items = data.get("items") or []
        lines = []
        for index, item in enumerate(items[:limit], start=1):
            name = item.get("display_name") or item.get("name") or item.get("symbol") or "-"
            symbol = item.get("symbol") or item.get("code") or "-"
            change = _numeric_change(item)
            suffix = f", 등락률 {change:+.2f}%" if ranking in {"상승률", "하락률"} else ""
            lines.append(f"{index}. {name}({symbol}){suffix}")

        return {
            "reply": f"홈 화면 코인 {ranking} 기준 상위 {len(lines)}개입니다.\n" + ("\n".join(lines) if lines else "조회된 순위가 없습니다."),
            "data": {"items": items, "source": "COINONE_MARKET_RANKINGS", "raw": data},
        }

    payload = _post_internal(
        "/api/home/market",
        auth_header,
        {
            "filters": {
                "region": region,
                "ranking": ranking,
                "horizon": "실시간",
            },
        },
    )
    data = payload.get("data") or {}
    source_rows = data.get("coins") if segment == "CRYPTO" else data.get("stocks")
    items = _apply_home_market_filters(source_rows or [], region, ranking)[:limit]
    lines = []
    for index, item in enumerate(items[:limit], start=1):
        name = item.get("display_name") or item.get("name") or item.get("symbol") or "-"
        symbol = item.get("symbol") or item.get("code") or "-"
        change = _numeric_change(item)
        suffix = f", 등락률 {change:+.2f}%" if ranking in {"상승률", "하락률"} else ""
        lines.append(f"{index}. {name}({symbol}){suffix}")

    return {
        "reply": f"홈 화면 {region if segment != 'CRYPTO' else '코인'} {ranking} 기준 상위 {len(lines)}개입니다.\n" + ("\n".join(lines) if lines else "조회된 순위가 없습니다."),
        "data": {"items": items, "source": "HOME_MARKET", "raw": data},
    }


def get_portfolio_summary(auth_header: str, message: str) -> dict:
    exchange_filter = _detect_exchange(message)
    env_filter = _detect_env(message)
    exchanges = [exchange_filter] if exchange_filter else ["TOSS", "KIS", "COINONE", "BINANCE"]
    envs = [env_filter] if env_filter else ["REAL", "MOCK"]
    summaries = []
    errors = []

    for exchange in exchanges:
        for env in envs:
            try:
                payload = _post_internal("/api/dashboard/balance", auth_header, {"exchange": exchange, "env": env})
                balance = payload.get("data") or {}
                summaries.append(normalize_account_summary(exchange, env, balance))
            except Exception as error:
                if not env_filter and _is_missing_optional_account_error(error):
                    continue
                errors.append(f"{exchange} {env} 계좌 조회 실패")

    totals_by_env = build_portfolio_totals(summaries)

    return {
        "reply": format_portfolio_reply(totals_by_env, summaries, errors),
        "data": {
            "summaries": summaries,
            "totals_by_env": totals_by_env,
            "errors": errors[:5],
            "source": "PORTFOLIO_SUMMARY",
        },
    }


def _is_missing_optional_account_error(error: Exception) -> bool:
    text = str(error or "")
    missing_markers = [
        "등록된",
        "API 키",
        "API키",
        "API key",
        "credentials",
        "credential",
    ]
    return any(marker in text for marker in missing_markers)


def get_exchange_rate(auth_header: str, message: str) -> dict:
    base_currency, quote_currency = _detect_currency_pair(message)
    env = _detect_env(message) or "REAL"
    payload = _get_internal(
        "/api/market/exchange-rate",
        auth_header,
        params={
            "base": base_currency,
            "quote": quote_currency,
            "broker_env": env,
        },
    )
    data = payload.get("data") or {}
    rate = _to_float(data.get("rate"))
    base = data.get("base_currency") or base_currency
    quote = data.get("quote_currency") or quote_currency
    source = data.get("source") or "TOSS"
    captured_at = str(data.get("captured_at") or "")[:10]

    return {
        "reply": f"{captured_at} 기준\n{base}/{quote} 환율은 1 {base} = {rate:,.2f} {quote}입니다.\n출처: {source}",
        "data": data,
    }


def get_asset_price(auth_header: str, message: str) -> dict:
    symbol_query = _extract_symbol_query(message)
    if not symbol_query:
        return {
            "reply": "현재가를 확인할 종목명이나 종목코드를 알려주세요.",
            "data": {"source": "ASSET_PRICE", "reason": "missing_symbol"},
        }

    try:
        symbol_data = _resolve_symbol(auth_header, symbol_query)
    except Exception:
        if not _is_likely_symbol_token(symbol_query):
            return {
                "reply": f"{symbol_query} 종목을 찾지 못했습니다.\n종목명이나 종목코드를 다시 확인해 주세요.",
                "data": {"source": "ASSET_PRICE", "query": symbol_query, "reason": "symbol_not_found"},
            }
        symbol_data = {}

    symbol = str(symbol_data.get("symbol") or symbol_query).upper()
    display_name = str(symbol_data.get("display_name") or symbol).strip()
    asset_type = str(symbol_data.get("asset_type") or "").upper()
    market = str(symbol_data.get("market") or "").strip().upper()
    exchange = _detect_exchange(message) or _default_exchange_for_asset(asset_type, market)
    broker_env = _detect_env(message) or "REAL"
    payload = _get_internal(
        "/api/chart/quote",
        auth_header,
        params={
            "exchange": exchange,
            "symbol": symbol,
            "broker_env": broker_env,
        },
    )
    data = payload.get("data") or {}
    current_price = _to_float(
        data.get("current_price")
        or data.get("price")
        or data.get("last")
        or data.get("close")
    )
    change_rate = _to_float(data.get("change_rate"))
    currency = str(data.get("currency") or ("USD" if market == "US" else "KRW")).upper()
    label = f"{display_name}({symbol})" if display_name and display_name.upper() != symbol else symbol

    if current_price <= 0:
        return {
            "reply": f"{label} 현재가를 확인하지 못했습니다.\n거래소 API 키, 허용 IP, 장 운영 상태를 확인해 주세요.",
            "data": {
                "source": "ASSET_PRICE",
                "symbol": symbol,
                "exchange": exchange,
                "reason": "missing_price",
            },
        }

    return {
        "reply": f"{label} 현재가는 {_format_money(current_price, currency)}입니다.\n등락률은 {change_rate:+.2f}%입니다.",
        "data": {
            "source": "ASSET_PRICE",
            "symbol": symbol,
            "display_name": display_name,
            "asset_type": asset_type,
            "market": market,
            "exchange": exchange,
            "broker_env": broker_env,
            "current_price": current_price,
            "change_rate": change_rate,
            "currency": currency,
        },
    }


def get_investment_profile_reanalysis_guide() -> dict:
    return {
        "reply": (
            "투자성향 재분석은 설정 메뉴에서 진행할 수 있습니다.\n"
            "설정 메뉴로 이동한 뒤, 하단의 '투자 성향 재분석' 버튼을 이용해 주세요."
        ),
        "actions": [
            {
                "type": "navigate",
                "label": "설정탭으로 이동",
                "to": "/settings",
            }
        ],
        "data": {"source": "SETTINGS_INVESTMENT_PROFILE_GUIDE"},
    }


def _get_watchlist_price_snapshot(auth_header: str, exchange: str, symbol: str) -> dict:
    snapshot = {}
    try:
        payload = _get_internal(
            "/api/chart/quote",
            auth_header,
            params={
                "exchange": exchange,
                "symbol": symbol,
                "broker_env": "REAL",
            },
        )
    except Exception:
        payload = {}

    data = payload.get("data") or {}
    current_price = _to_float(data.get("current_price"))
    change_rate = _to_float(data.get("change_rate"))
    if current_price <= 0:
        try:
            candle_payload = _get_internal(
                "/api/chart/candles",
                auth_header,
                params={
                    "exchange": exchange,
                    "symbol": symbol,
                    "interval": "1d",
                    "count": 2,
                    "broker_env": "REAL",
                },
            )
            candles = candle_payload.get("data") or []
            if candles:
                current_price = _to_float(candles[-1].get("close"))
        except Exception:
            current_price = 0.0

    if current_price > 0:
        snapshot["latest_price"] = current_price
        snapshot["average_price"] = current_price
    if data.get("change_rate") is not None:
        snapshot["change_rate"] = change_rate
    return snapshot




def add_watchlist_item(auth_header: str, message: str) -> dict:
    user_id, _ = get_user_id_from_header(auth_header)
    symbol_query = _extract_symbol_query(message)
    symbol_data = _resolve_symbol(auth_header, symbol_query)
    symbol = str(symbol_data.get("symbol") or "").upper()
    asset_type = str(symbol_data.get("asset_type") or "STOCK").upper()
    market = str(symbol_data.get("market") or "").upper()
    exchange = "COINONE" if asset_type == "CRYPTO" else ("TOSS" if market == "US" else "KIS")

    existing = query_supabase(
        auth_header,
        "user_watchlist",
        "GET",
        params={
            "user_id": f"eq.{user_id}",
            "symbol": f"eq.{symbol}",
            "asset_type": f"eq.{asset_type}",
            "exchange": f"eq.{exchange}",
        },
    ) or []
    payload = {
        "user_id": user_id,
        "symbol": symbol,
        "name": symbol_data.get("display_name") or symbol,
        "exchange": exchange,
        "asset_type": asset_type,
        "market_country": "KR" if asset_type == "CRYPTO" else (market or "KR"),
        "currency": "KRW" if asset_type == "CRYPTO" or market != "US" else "USD",
        "updated_at": datetime.utcnow().isoformat() + "Z",
    }
    payload.update(_get_watchlist_price_snapshot(auth_header, exchange, symbol))

    if existing:
        record_id = existing[0]["id"]
        query_supabase(auth_header, f"user_watchlist?id=eq.{record_id}", "PATCH", json_data=payload)
        action = "이미 있던 관심종목을 최신 정보로 갱신했습니다."
    else:
        payload["sort_order"] = 1
        query_supabase(auth_header, "user_watchlist", "POST", json_data=payload)
        action = "관심종목에 추가했습니다."

    return {
        "reply": f"{payload['name']}({symbol}) {action}",
        "data": payload,
    }


def remove_watchlist_item(auth_header: str, message: str) -> dict:
    user_id, _ = get_user_id_from_header(auth_header)
    symbol_query = _extract_symbol_query(message)
    symbol_data = _resolve_symbol(auth_header, symbol_query)
    symbol = str(symbol_data.get("symbol") or "").upper()
    asset_type = str(symbol_data.get("asset_type") or "STOCK").upper()
    market = str(symbol_data.get("market") or "").upper()
    exchange = "COINONE" if asset_type == "CRYPTO" else ("TOSS" if market == "US" else "KIS")

    existing = query_supabase(
        auth_header,
        "user_watchlist",
        "GET",
        params={
            "user_id": f"eq.{user_id}",
            "symbol": f"eq.{symbol}",
            "asset_type": f"eq.{asset_type}",
            "exchange": f"eq.{exchange}",
        },
    ) or []
    display_name = symbol_data.get("display_name") or symbol
    if not existing:
        return {
            "reply": f"{display_name}({symbol})은 관심종목에 등록되어 있지 않습니다.",
            "data": {"symbol": symbol, "asset_type": asset_type, "exchange": exchange, "removed": False},
        }

    record_id = existing[0]["id"]
    query_supabase(auth_header, f"user_watchlist?id=eq.{record_id}", "DELETE")
    return {
        "reply": f"{display_name}({symbol}) 관심종목을 해제했습니다.",
        "data": {"symbol": symbol, "asset_type": asset_type, "exchange": exchange, "removed": True},
    }


def get_holdings(auth_header: str, message: str) -> dict:
    exchange = _detect_exchange(message)
    env = _detect_env(message)
    summary = get_portfolio_summary(auth_header, message)
    summaries = (summary.get("data") or {}).get("summaries") or []
    if exchange:
        summaries = [item for item in summaries if item["exchange"] == exchange]
    if env:
        summaries = [item for item in summaries if item["env"] == env]

    holdings = []
    for item in summaries:
        for holding in item.get("holdings") or []:
            qty = holding.get("qty") or holding.get("quantity") or holding.get("balance") or 0
            name = holding.get("name") or holding.get("display_name") or holding.get("symbol") or holding.get("currency") or "-"
            symbol = holding.get("symbol") or holding.get("currency") or ""
            holdings.append(f"- {item['exchange']} {item['env']} / {name} {f'({symbol})' if symbol else ''}: {qty}")

    if not holdings:
        return {
            "reply": "현재 조회된 보유 종목이 없습니다.\nAPI 키 권한, 계좌 환경, 모의/실전 선택을 확인해 주세요.",
            "data": {"summaries": summaries},
        }

    return {
        "reply": "보유 현황입니다.\n" + "\n".join(holdings[:20]),
        "data": {"summaries": summaries},
    }


def _collect_precheck_blockers(precheck: dict, broker_env: str) -> list[str]:
    blockers = []
    if precheck.get("balance_check_failed"):
        blockers.append("주문에 필요한 잔고 또는 보유수량을 확인하지 못했습니다.")
    if precheck.get("is_market_closed"):
        blockers.append(precheck.get("market_status_message") or "현재 거래 가능 시간이 아닙니다.")
    if precheck.get("insufficient_cash"):
        blockers.append("주문 가능 현금이 부족합니다.")
    if precheck.get("insufficient_holding"):
        blockers.append("보유 수량보다 많은 매도 주문입니다.")
    if precheck.get("insufficient_permission"):
        blockers.append(precheck.get("permission_message") or "거래 권한이 없습니다.")
    if precheck.get("futures_real_blocked"):
        blockers.append("바이낸스 선물 실거래가 잠겨 있습니다.")
    if broker_env == "REAL" and precheck.get("exceeds_real_order_limit"):
        blockers.append("실거래 1회 주문 한도 100,000원을 초과했습니다.")
    return blockers


def _exchange_has_mock_env(exchange: str) -> bool:
    return str(exchange or "").upper() not in {"TOSS", "COINONE"}


def _build_missing_order_price_result(
    symbol: str,
    side: str | None,
    exchange: str,
    broker_env: str,
) -> dict:
    return {
        "reply": (
            f"{symbol} {side or ''} 매매 제안은 지정가 금액이 필요합니다.\n"
            f"{exchange}는 모의 계좌 없이 {broker_env} 계좌 기준으로 진행하므로, "
            "1주/1개당 지정가를 알려주세요. 예: '지정가 3,500원'"
        ),
        "data": {
            "source": "CHATBOT_ORDER_PARSER",
            "reason": "missing_order_price",
            "exchange": exchange,
            "symbol": symbol,
            "side": side,
            "broker_env": broker_env,
        },
    }


def _build_missing_order_env_and_price_result(
    symbol: str,
    side: str | None,
    exchange: str,
) -> dict:
    return {
        "reply": (
            f"{symbol} {side or ''} 매매 제안을 만들 계좌 환경과 지정가 금액을 알려주세요.\n"
            "예: '실거래 지정가 3,500원' 또는 '모의 지정가 3,500원'"
        ),
        "data": {
            "source": "CHATBOT_ORDER_PARSER",
            "reason": "missing_order_env_and_price",
            "exchange": exchange,
            "symbol": symbol,
            "side": side,
        },
    }


def create_trade_proposal(auth_header: str, arguments: dict) -> dict:
    """사용자 승인 전 상태인 PENDING 매매 제안만 생성합니다."""
    enforce_tool_safety("create_trade_proposal", arguments)
    user_id, _ = get_user_id_from_header(auth_header)
    values = arguments if isinstance(arguments, dict) else {}
    exchange = str(values.get("exchange") or "").strip().upper()
    asset_type = str(values.get("asset_type") or "").strip().upper()
    symbol = str(values.get("symbol") or values.get("ticker") or "").strip().upper()
    side = str(values.get("side") or "").strip().upper()
    order_type = str(values.get("order_type") or values.get("ord_type") or "LIMIT").strip().upper()
    broker_env = str(values.get("broker_env") or "MOCK").strip().upper()

    if exchange not in {"TOSS", "KIS", "COINONE", "BINANCE", "BINANCE_UM_FUTURES"}:
        raise ValueError("지원하지 않는 거래소입니다.")
    if asset_type not in {"STOCK", "CRYPTO"}:
        raise ValueError("asset_type은 STOCK 또는 CRYPTO여야 합니다.")
    if not symbol:
        raise ValueError("매매 제안 종목이 필요합니다.")
    if side not in {"BUY", "SELL"}:
        raise ValueError("매매 제안 방향은 BUY 또는 SELL이어야 합니다.")
    if order_type not in {"LIMIT", "MARKET"}:
        raise ValueError("주문 유형은 LIMIT 또는 MARKET이어야 합니다.")
    if exchange == "COINONE" and order_type == "MARKET":
        raise ValueError("코인원 매매 제안은 지정가 주문만 지원합니다.")
    if broker_env not in {"MOCK", "REAL"}:
        raise ValueError("broker_env는 MOCK 또는 REAL이어야 합니다.")

    try:
        quantity = float(values.get("quantity") or values.get("volume"))
    except (TypeError, ValueError) as error:
        raise ValueError("매매 제안 수량이 올바르지 않습니다.") from error
    if not math.isfinite(quantity) or quantity <= 0:
        raise ValueError("매매 제안 수량은 0보다 커야 합니다.")

    price_value = values.get("price")
    try:
        price = float(price_value) if price_value not in (None, "") else None
    except (TypeError, ValueError) as error:
        raise ValueError("매매 제안 가격이 올바르지 않습니다.") from error
    if price is not None and not math.isfinite(price):
        raise ValueError("매매 제안 가격은 유한한 숫자여야 합니다.")
    if order_type == "LIMIT" and (price is None or price <= 0):
        raise ValueError("지정가 매매 제안에는 0보다 큰 가격이 필요합니다.")

    raw_order_payload = values.get("raw_order_payload") or {}
    if not isinstance(raw_order_payload, dict):
        raw_order_payload = {}
    precheck = raw_order_payload.get("precheck") or {}
    if not isinstance(precheck, dict):
        precheck = {}
    try:
        reference_price = float(precheck.get("reference_price"))
        estimated_amount_krw = float(precheck.get("estimated_amount_krw"))
    except (TypeError, ValueError):
        reference_price = 0.0
        estimated_amount_krw = 0.0
    if (
        raw_order_payload.get("precheck_status") != "OK"
        or not precheck
        or not math.isfinite(reference_price)
        or reference_price <= 0
        or not math.isfinite(estimated_amount_krw)
        or estimated_amount_krw <= 0
    ):
        raise ValueError("주문 사전검증을 통과한 제안만 생성할 수 있습니다.")
    blockers = _collect_precheck_blockers(precheck, broker_env)
    relevant_balance = precheck.get("available_cash") if side == "BUY" else precheck.get("holding_qty")
    if relevant_balance is None:
        blockers.append("주문에 필요한 잔고 또는 보유수량을 확인하지 못했습니다.")
    if blockers:
        raise ValueError(" ".join(blockers))

    market_country = str(values.get("market_country") or ("US" if exchange == "TOSS" and asset_type == "STOCK" else "KR")).upper()
    currency = str(values.get("currency") or ("USD" if market_country == "US" or exchange in {"BINANCE", "BINANCE_UM_FUTURES"} else "KRW")).upper()
    payload = {
        "user_id": user_id,
        "exchange": exchange,
        "asset_type": asset_type,
        "ticker": symbol,
        "symbol": symbol,
        "side": side,
        "price": price,
        "volume": quantity,
        "order_amount": quantity * price if price is not None else None,
        "ord_type": order_type,
        "broker_env": broker_env,
        "market_country": market_country,
        "currency": currency,
        "status": "PENDING",
        "raw_order_payload": raw_order_payload,
    }
    created = query_supabase(auth_header, "trade_proposals", "POST", json_data=payload)
    record = (created[0] if isinstance(created, list) and created else created) or payload
    return {
        "reply": f"{symbol} {side} 매매 제안을 생성했습니다. 승인 카드에서 실행 여부를 선택해 주세요.",
        "data": {**payload, **(record if isinstance(record, dict) else {})},
    }


def create_trade_proposal_from_message(auth_header: str, message: str, intent: ParsedOrderIntent | None = None) -> dict:
    parsed = intent or parse_order_intent(message)
    if not parsed.is_order_request or not parsed.side or not parsed.symbol_query:
        return {
            "reply": "매매 제안을 만들 종목, 방향, 수량 또는 금액을 함께 알려주세요.",
            "data": {"source": "CHATBOT_ORDER_PARSER", "reason": "missing_order_intent"},
        }

    symbol_data = _resolve_symbol(auth_header, parsed.symbol_query)
    symbol = str(symbol_data.get("symbol") or parsed.symbol_query).upper()
    asset_type = str(symbol_data.get("asset_type") or "STOCK").upper()
    market = str(symbol_data.get("market") or "").upper()
    exchange = _detect_exchange(message)
    if not exchange:
        exchange = _default_exchange_for_asset(asset_type, market)
    price = parsed.price
    if parsed.broker_env:
        broker_env = parsed.broker_env
    elif _exchange_has_mock_env(exchange):
        if price is None:
            return _build_missing_order_env_and_price_result(symbol, parsed.side, exchange)
        return {
            "reply": f"{symbol} 매매 제안을 만들 계좌 환경을 알려주세요. 예: '실거래' 또는 '모의'",
            "data": {
                "source": "CHATBOT_ORDER_PARSER",
                "reason": "missing_order_env",
                "exchange": exchange,
                "symbol": symbol,
                "side": parsed.side,
            },
        }
    else:
        broker_env = "REAL"

    if price is None and exchange in {"TOSS", "COINONE"}:
        return _build_missing_order_price_result(symbol, parsed.side, exchange, broker_env)

    if exchange == "COINONE" and parsed.order_type == "MARKET":
        return {
            "reply": (
                "코인원 챗봇 매매 제안은 현재 지정가만 지원합니다. "
                "예: 'XRP 10개 800원에 모의로 사줘'처럼 가격을 함께 입력해 주세요."
            ),
            "data": {
                "source": "CHATBOT_ORDER_PARSER",
                "reason": "unsupported_order_type",
                "exchange": exchange,
                "symbol": symbol,
            },
        }

    if price is None and (parsed.amount_krw or parsed.sell_ratio):
        price = _lookup_current_price(auth_header, exchange, symbol, broker_env)

    quantity = parsed.quantity
    if quantity is None and parsed.amount_krw:
        quantity = _quantity_from_amount(parsed.amount_krw, price, asset_type)
        if quantity <= 0:
            return {
                "reply": f"{symbol} 현재가 기준으로 {parsed.amount_krw:,.0f}원어치는 최소 주문 수량보다 작습니다.",
                "data": {
                    "source": "CHATBOT_ORDER_PARSER",
                    "reason": "amount_too_small",
                    "symbol": symbol,
                    "side": parsed.side,
                    "amount_krw": parsed.amount_krw,
                    "price": price,
                },
            }
    if quantity is None and parsed.sell_ratio:
        holding_qty = _lookup_holding_quantity(auth_header, message, symbol, exchange, broker_env)
        quantity = _quantity_from_ratio(holding_qty, parsed.sell_ratio, asset_type)
        if quantity <= 0:
            return {
                "reply": f"{symbol} 매도 제안을 만들 보유 수량을 찾지 못했습니다. 보유자산 조회 후 수량을 직접 입력해 주세요.",
                "data": {
                    "source": "CHATBOT_ORDER_PARSER",
                    "reason": "holding_quantity_not_found",
                    "symbol": symbol,
                    "side": parsed.side,
                    "sell_ratio": parsed.sell_ratio,
                },
            }

    if quantity is None:
        if parsed.amount_krw:
            return {
                "reply": (
                    f"{symbol} {parsed.amount_krw:,.0f}원어치 {parsed.side} 제안을 만들려면 현재가 기준 수량 계산이 필요합니다.\n"
                    "다음 단계에서 시세 조회와 사전검증을 붙여 자동 계산하도록 연결하겠습니다. 지금은 수량을 함께 입력해 주세요."
                ),
                "data": {
                    "source": "CHATBOT_ORDER_PARSER",
                    "reason": "quantity_required_for_amount_order",
                    "symbol": symbol,
                    "side": parsed.side,
                    "amount_krw": parsed.amount_krw,
                },
            }
        if parsed.sell_ratio:
            return {
                "reply": (
                    f"{symbol} 보유 수량의 {parsed.sell_ratio * 100:.0f}% 매도 제안을 만들려면 보유수량 조회가 필요합니다.\n"
                    "다음 단계에서 보유자산 조회와 연결하겠습니다. 지금은 매도 수량을 함께 입력해 주세요."
                ),
                "data": {
                    "source": "CHATBOT_ORDER_PARSER",
                    "reason": "quantity_required_for_ratio_sell",
                    "symbol": symbol,
                    "side": parsed.side,
                    "sell_ratio": parsed.sell_ratio,
                },
            }
        return {
            "reply": f"{symbol} {parsed.side} 매매 제안을 만들 수량을 알려주세요.",
            "data": {"source": "CHATBOT_ORDER_PARSER", "reason": "missing_quantity", "symbol": symbol},
        }
    quantity = _normalize_order_quantity(quantity, asset_type)
    if quantity <= 0:
        return {
            "reply": f"{symbol} 매매 제안을 만들 수량이 최소 주문 단위보다 작습니다. 수량을 늘려 다시 입력해 주세요.",
            "data": {
                "source": "CHATBOT_ORDER_PARSER",
                "reason": "quantity_too_small_after_normalization",
                "symbol": symbol,
                "side": parsed.side,
            },
        }

    market_country = "KR" if asset_type == "CRYPTO" else (market or "KR")
    currency = "KRW" if asset_type == "CRYPTO" or market_country != "US" else "USD"
    order_type = "LIMIT" if price and price > 0 else parsed.order_type
    try:
        precheck = _run_chatbot_precheck(
            auth_header=auth_header,
            exchange=exchange,
            symbol=symbol,
            side=parsed.side,
            order_type=order_type,
            quantity=quantity,
            price=price,
            broker_env=broker_env,
        )
    except Exception as error:
        error_text = str(error)
        if "API 키" in error_text or "API키" in error_text:
            action = "거래소 API 키가 없거나 권한이 부족할 수 있습니다. API 키 등록과 계좌 환경을 확인한 뒤 다시 시도해 주세요."
        elif "실거래 시장가" in error_text or "하드캡" in error_text:
            action = (
                "실거래 시장가 제안은 만들 수 없습니다. "
                "10만원 하드캡을 보장하려면 지정가를 함께 입력해 주세요. "
                "예: 'RDDT 195달러에 1주 실거래 매수 제안'. "
                "단, 예상 원화 주문금액이 10만원을 넘으면 실거래 제안은 차단됩니다."
            )
        elif "현재가" in error_text or "주문금액" in error_text:
            action = "현재가와 예상 주문금액을 확인하지 못했습니다. 시세 연결 상태를 확인한 뒤 다시 시도해 주세요."
        else:
            action = "시세, 잔고, 거래 가능 시간, API 연결 상태를 확인한 뒤 다시 시도해 주세요."
        return {
            "reply": f"매매 제안 사전검증을 완료하지 못했습니다. {action}",
            "data": {
                "source": "CHATBOT_ORDER_PARSER",
                "reason": "precheck_failed",
                "exchange": exchange,
                "symbol": symbol,
            },
        }

    blockers = _collect_precheck_blockers(precheck, broker_env)
    if blockers:
        return {
            "reply": f"매매 제안을 만들 수 없습니다. {' '.join(blockers)} 조건을 확인한 뒤 다시 시도해 주세요.",
            "data": {
                "source": "CHATBOT_ORDER_PARSER",
                "reason": "precheck_failed",
                "exchange": exchange,
                "symbol": symbol,
                "blockers": blockers,
            },
        }
    normalized_quantity = _to_float(precheck.get("quantity"))
    if normalized_quantity > 0:
        quantity = normalized_quantity
    if quantity <= 0:
        return {
            "reply": f"{symbol} 매매 제안을 만들 수량이 거래소 주문 단위보다 작습니다. 수량을 늘려 다시 입력해 주세요.",
            "data": {
                "source": "CHATBOT_ORDER_PARSER",
                "reason": "quantity_too_small_after_precheck",
                "exchange": exchange,
                "symbol": symbol,
                "side": parsed.side,
            },
        }

    return create_trade_proposal(
        auth_header,
        {
            "exchange": exchange,
            "asset_type": asset_type,
            "symbol": symbol,
            "side": parsed.side,
            "order_type": order_type,
            "quantity": quantity,
            "price": price,
            "broker_env": broker_env,
            "market_country": market_country,
            "currency": currency,
            "raw_order_payload": {
                "precheck_status": "OK",
                "precheck": precheck,
                "source": "CHATBOT_ORDER_PARSER",
            },
        },
    )


def _store_last_recommendations(auth_header: str, result: dict) -> None:
    data = result.get("data") or {}
    items = [
        item
        for item in (data.get("items") or [])
        if isinstance(item, dict) and item.get("symbol")
    ][:10]
    if not items:
        return
    try:
        user_id, _ = get_user_id_from_header(auth_header)
    except Exception:
        return
    _conversation_repository.store_recommendations(
        auth_header,
        user_id,
        items,
        data.get("source"),
        ttl_seconds=600,
    )


def _extract_recommendation_reference_index(text: str) -> int | None:
    normalized = str(text or "").strip()
    if not normalized:
        return None
    match = re.search(r"(\d+)\s*(?:번|번째)", normalized)
    if match:
        return int(match.group(1)) - 1
    word_ordinals = {
        "첫": 0,
        "첫번째": 0,
        "첫 번째": 0,
        "두번째": 1,
        "두 번째": 1,
        "세번째": 2,
        "세 번째": 2,
    }
    for keyword, index in word_ordinals.items():
        if keyword in normalized:
            return index
    if any(keyword in normalized for keyword in ["그걸로", "그거로", "그 종목", "추천한거", "추천한 것"]):
        return 0
    return None


def _is_recommendation_reference_order(text: str) -> bool:
    if _extract_recommendation_reference_index(text) is None:
        return False
    return any(keyword in text for keyword in ["매수", "구매", "사줘", "제안", "주문"])


def _with_referenced_recommendation_symbol(auth_header: str, message: str) -> tuple[str | None, dict | None]:
    reference_index = _extract_recommendation_reference_index(message)
    if reference_index is None:
        return None, None

    user_id, _ = get_user_id_from_header(auth_header)
    items = _conversation_repository.load_recommendations(
        auth_header,
        user_id,
    )
    if not items:
        return None, {
            "reply": "추천 후보를 먼저 조회한 뒤, 예: '1번으로 10만원어치 매수 제안'처럼 말해 주세요.",
            "data": {"source": "CHATBOT_RECOMMENDATION_REFERENCE", "reason": "missing_recent_recommendation"},
        }
    if reference_index < 0 or reference_index >= len(items):
        return None, {
            "reply": "해당 번호의 추천 후보를 찾지 못했습니다. 추천 후보를 먼저 다시 조회해 주세요.",
            "data": {
                "source": "CHATBOT_RECOMMENDATION_REFERENCE",
                "reason": "recommendation_index_not_found",
                "requested_index": reference_index + 1,
                "available_count": len(items),
            },
        }

    item = items[reference_index]
    symbol = str(item.get("symbol") or "").strip().upper()
    if not symbol:
        return None, {
            "reply": "추천 후보의 종목코드를 확인하지 못했습니다. 추천 후보를 먼저 다시 조회해 주세요.",
            "data": {"source": "CHATBOT_RECOMMENDATION_REFERENCE", "reason": "missing_symbol"},
        }
    env_text = "" if _detect_env(message) else "실거래 "
    return f"{symbol} {env_text}{message}", None


def create_trade_proposal_from_recommendation_reference(auth_header: str, message: str) -> dict:
    rewritten_message, error_result = _with_referenced_recommendation_symbol(auth_header, message)
    if error_result:
        return error_result
    if not rewritten_message:
        return {
            "reply": "추천 후보를 먼저 조회한 뒤, 예: '1번으로 10만원어치 매수 제안'처럼 말해 주세요.",
            "data": {"source": "CHATBOT_RECOMMENDATION_REFERENCE", "reason": "missing_recent_recommendation"},
        }

    parsed = parse_order_intent(rewritten_message)
    if not parsed.is_order_request:
        return {
            "reply": "추천 후보로 매매 제안을 만들 금액이나 수량, 방향을 함께 알려주세요.",
            "data": {"source": "CHATBOT_RECOMMENDATION_REFERENCE", "reason": "missing_order_size"},
        }
    return create_trade_proposal_from_message(auth_header, rewritten_message, parsed)


def _run_chatbot_precheck(
    auth_header: str,
    exchange: str,
    symbol: str,
    side: str,
    order_type: str,
    quantity: float,
    price: float | None,
    broker_env: str,
) -> dict:
    response = _post_internal(
        "/api/trade/precheck",
        auth_header,
        {
            "exchange": exchange,
            "symbol": symbol,
            "action": side,
            "order_type": order_type,
            "quantity": quantity,
            "price": price,
            "broker_env": broker_env,
        },
    )
    precheck = response.get("data") or {}
    try:
        reference_price = float(precheck.get("reference_price"))
        estimated_amount_krw = float(precheck.get("estimated_amount_krw"))
    except (TypeError, ValueError):
        reference_price = 0.0
        estimated_amount_krw = 0.0
    if (
        not math.isfinite(reference_price)
        or reference_price <= 0
        or not math.isfinite(estimated_amount_krw)
        or estimated_amount_krw <= 0
    ):
        raise ValueError("현재가와 예상 주문금액을 확인하지 못했습니다.")
    relevant_balance = precheck.get("available_cash") if side == "BUY" else precheck.get("holding_qty")
    if precheck.get("balance_check_failed") or relevant_balance is None:
        raise ValueError("주문에 필요한 잔고 또는 보유수량을 확인하지 못했습니다.")
    return precheck


def _lookup_current_price(auth_header: str, exchange: str, symbol: str, broker_env: str) -> float | None:
    payload = _get_internal(
        "/api/chart/quote",
        auth_header,
        params={
            "exchange": exchange,
            "symbol": symbol,
            "broker_env": broker_env,
        },
    )
    data = payload.get("data") or {}
    price = _to_float(
        data.get("current_price")
        or data.get("price")
        or data.get("last")
        or data.get("close")
    )
    return price if price > 0 else None


def _quantity_from_amount(amount: float, price: float | None, asset_type: str) -> float:
    if not price or price <= 0:
        return 0.0
    raw_quantity = amount / price
    return _normalize_order_quantity(raw_quantity, asset_type)


def _normalize_order_quantity(quantity: float, asset_type: str) -> float:
    if not math.isfinite(float(quantity)) or float(quantity) <= 0:
        return 0.0
    if asset_type == "STOCK":
        return float(math.floor(float(quantity)))
    return _floor_quantity(quantity, 8)


def _floor_quantity(quantity: float, precision: int) -> float:
    try:
        decimal_quantity = Decimal(str(quantity))
    except (InvalidOperation, ValueError):
        return 0.0
    step = Decimal("1").scaleb(-precision)
    floored = decimal_quantity.quantize(step, rounding=ROUND_DOWN)
    return float(floored)


def _lookup_holding_quantity(
    auth_header: str,
    message: str,
    symbol: str,
    exchange: str,
    broker_env: str | None,
) -> float:
    summary = get_portfolio_summary(auth_header, message)
    summaries = (summary.get("data") or {}).get("summaries") or []
    for item in summaries:
        if exchange and str(item.get("exchange") or "").upper() != exchange:
            continue
        if broker_env and str(item.get("env") or "").upper() != broker_env:
            continue
        for holding in item.get("holdings") or []:
            holding_symbol = str(holding.get("symbol") or holding.get("currency") or "").upper()
            if holding_symbol != symbol:
                continue
            return _to_float(
                holding.get("qty")
                or holding.get("quantity")
                or holding.get("balance")
                or holding.get("available_qty")
            )
    return 0.0


def _quantity_from_ratio(holding_quantity: float, ratio: float, asset_type: str) -> float:
    raw_quantity = max(holding_quantity, 0) * min(max(ratio, 0), 1)
    return _normalize_order_quantity(raw_quantity, asset_type)


def _match_min_amount(text: str) -> float:
    match = re.search(r"(\d+(?:\.\d+)?)\s*(만원|천원|원|만)", text)
    if match:
        value = float(match.group(1))
        unit = match.group(2)
        if unit in {"만원", "만"}:
            return value * 10000
        if unit == "천원":
            return value * 1000
        return value

    korean_match = re.search(r"([일한이삼사오육칠팔구십백천만]+)\s*(원|이상|초과|넘는|넘어|부터)", text)
    if korean_match:
        amount = _parse_korean_amount(korean_match.group(1))
        if amount > 0:
            return amount

    if re.search(r"(?<![0-9일한이삼사오육칠팔구십백천])만원\s*(이상|초과|넘는|넘어|부터)?", text):
        return 10000.0

    return 0.0


def _parse_korean_amount(value: str) -> float:
    digits = {
        "일": 1,
        "한": 1,
        "이": 2,
        "삼": 3,
        "사": 4,
        "오": 5,
        "육": 6,
        "칠": 7,
        "팔": 8,
        "구": 9,
    }
    units = {"십": 10, "백": 100, "천": 1000}

    def parse_section(section: str) -> int:
        total = 0
        current = 0
        for char in section:
            if char in digits:
                current = digits[char]
            elif char in units:
                total += (current or 1) * units[char]
                current = 0
        return total + current

    normalized = str(value or "").strip()
    if not normalized:
        return 0.0
    if "만" in normalized:
        left, right = normalized.split("만", 1)
        return float((parse_section(left) or 1) * 10000 + parse_section(right))
    return float(parse_section(normalized))


def _format_trade_asset_name(row: dict) -> str:
    symbol = str(row.get("symbol") or row.get("ticker") or "").strip().upper()
    fallback_name = str(
        row.get("display_name")
        or row.get("name")
        or row.get("company_name")
        or row.get("asset_name")
        or ""
    ).strip()
    if fallback_name and fallback_name.upper() != symbol:
        return fallback_name
    if not symbol:
        return fallback_name or "-"

    enriched = enrich_symbol({"symbol": symbol})
    display_name = str(enriched.get("display_name") or "").strip()
    if display_name and display_name.upper() != symbol:
        return display_name
    return symbol


def search_trade_history(auth_header: str, message: str) -> dict:
    user_id, _ = get_user_id_from_header(auth_header)
    min_amount = _match_min_amount(message)
    symbol_query = _extract_symbol_query(message)
    symbol = ""
    if symbol_query:
        try:
            symbol = _resolve_symbol(auth_header, symbol_query).get("symbol") or ""
        except Exception:
            symbol = symbol_query.upper() if _is_likely_symbol_token(symbol_query) else ""

    proposal_params = {
        "user_id": f"eq.{user_id}",
        "order": "created_at.desc",
        "limit": "200",
    }
    if symbol:
        proposal_params["symbol"] = f"eq.{symbol}"

    proposals = safe_query_supabase(auth_header, "trade_proposals", "GET", params=proposal_params) or []
    broker_rows = safe_query_supabase(
        auth_header,
        "broker_order_history",
        "GET",
        params={"user_id": f"eq.{user_id}", "order": "ordered_at.desc", "limit": "200"},
    ) or []

    rows = []
    for row in proposals:
        price = _to_float(row.get("price"))
        volume = _to_float(row.get("volume") or row.get("quantity"))
        amount = _to_float(row.get("order_amount")) or price * volume
        if min_amount and amount < min_amount:
            continue
        rows.append({
            "date": str(row.get("created_at") or "")[:10],
            "exchange": row.get("exchange"),
            "symbol": row.get("symbol"),
            "asset_name": _format_trade_asset_name(row),
            "side": row.get("side"),
            "status": row.get("status"),
            "amount": amount,
        })

    for row in broker_rows:
        row_symbol = row.get("symbol") or row.get("ticker")
        if symbol and str(row_symbol).upper() != str(symbol).upper():
            continue
        amount = _to_float(row.get("order_amount") or row.get("executed_amount") or row.get("amount"))
        if min_amount and amount < min_amount:
            continue
        rows.append({
            "date": str(row.get("ordered_at") or row.get("created_at") or "")[:10],
            "exchange": row.get("exchange"),
            "symbol": row_symbol,
            "asset_name": _format_trade_asset_name({**row, "symbol": row_symbol}),
            "side": row.get("side"),
            "status": row.get("status"),
            "amount": amount,
        })

    rows = sorted(rows, key=lambda item: item.get("date") or "", reverse=True)[:20]
    if not rows:
        return {"reply": "조건에 맞는 거래내역을 찾지 못했습니다.", "data": {"items": []}}

    lines = [
        f"- {row['date']} / {row.get('exchange') or '-'} / {row.get('asset_name') or row.get('symbol') or '-'} / {row.get('side') or '-'} / {row.get('status') or '-'} / {_format_money(row.get('amount'))}"
        for row in rows
    ]
    return {
        "reply": f"조건에 맞는 거래내역 {len(rows)}건입니다.\n" + "\n".join(lines),
        "data": {"items": rows},
    }


def list_open_orders(auth_header: str, message: str) -> dict:
    user_id, _ = get_user_id_from_header(auth_header)
    exchange = _detect_exchange(message)
    env = _detect_env(message)
    symbol_query = _extract_symbol_query(message)
    symbol = ""
    if symbol_query:
        try:
            symbol = _resolve_symbol(auth_header, symbol_query).get("symbol") or ""
        except Exception:
            symbol = symbol_query.upper() if _is_likely_symbol_token(symbol_query) else ""

    params = {
        "user_id": f"eq.{user_id}",
        "status": f"in.({','.join(OPEN_ORDER_STATUSES)})",
        "order": "created_at.desc",
        "limit": str(_detect_limit(message, default=20, maximum=50)),
    }
    if exchange:
        params["exchange"] = f"eq.{exchange}"
    if env:
        params["broker_env"] = f"eq.{env}"
    if symbol:
        params["symbol"] = f"eq.{symbol}"

    rows = safe_query_supabase(auth_header, "trade_proposals", "GET", params=params) or []
    if not rows:
        return {
            "reply": "현재 조회된 미체결 주문이 없습니다.",
            "data": {
                "source": "OPEN_ORDERS",
                "items": [],
                "filters": {"exchange": exchange, "broker_env": env, "symbol": symbol},
            },
        }

    items = []
    for row in rows:
        price = _to_float(row.get("price"))
        qty = _to_float(row.get("volume") or row.get("quantity"))
        amount = _to_float(row.get("order_amount")) or price * qty
        symbol_value = str(row.get("symbol") or row.get("ticker") or "").upper()
        asset_name = _format_trade_asset_name({**row, "symbol": symbol_value})
        item = {
            "id": row.get("id"),
            "date": str(row.get("created_at") or "")[:10],
            "exchange": row.get("exchange"),
            "broker_env": row.get("broker_env"),
            "symbol": symbol_value,
            "asset_name": asset_name,
            "side": row.get("side"),
            "status": row.get("status"),
            "price": price,
            "quantity": qty,
            "amount": amount,
            "ord_type": row.get("ord_type"),
            "external_order_id": row.get("external_order_id"),
        }
        items.append(item)

    lines = []
    for item in items:
        env_text = f" {item['broker_env']}" if item.get("broker_env") else ""
        side_text = "매도" if str(item.get("side") or "").upper() == "SELL" else "매수"
        qty_text = _format_quantity(item.get("quantity"))
        price_text = _format_money(item.get("price"))
        amount_text = _format_money(item.get("amount"))
        lines.append(
            f"- {item['date']} / {item.get('exchange') or '-'}{env_text} / "
            f"{item.get('asset_name') or item.get('symbol') or '-'} / {side_text} / "
            f"{qty_text}개 / 지정가 {price_text} / 주문금액 {amount_text} / 상태 {item.get('status') or '-'}"
        )

    return {
        "reply": f"미체결 주문 {len(items)}건입니다.\n" + "\n".join(lines),
        "data": {
            "source": "OPEN_ORDERS",
            "items": items,
            "filters": {"exchange": exchange, "broker_env": env, "symbol": symbol},
        },
    }


def search_web(auth_header: str, message: str) -> dict:
    user_id, _ = get_user_id_from_header(auth_header)
    return ChatbotWebFallbackSearchService().search(
        auth_header=auth_header,
        user_id=user_id,
        query=message,
        limit=_detect_limit(message, default=5, maximum=5),
    )


def get_asset_outlook(auth_header: str, message: str) -> dict:
    user_id, _ = get_user_id_from_header(auth_header)
    symbol_query = _extract_symbol_query(message)
    if not symbol_query:
        return {
            "reply": "전망을 확인할 종목명이나 종목코드를 알려주세요.",
            "data": {"source": "ASSET_OUTLOOK", "reason": "missing_symbol"},
        }

    symbol_data = {}
    try:
        symbol_data = _resolve_symbol(auth_header, symbol_query)
    except Exception:
        if not _is_likely_symbol_token(symbol_query):
            return {
                "reply": f"{symbol_query} 종목을 찾지 못했습니다.\n종목명이나 종목코드를 다시 확인해 주세요.",
                "data": {"source": "ASSET_OUTLOOK", "query": symbol_query, "reason": "symbol_not_found"},
            }

    symbol = str(symbol_data.get("symbol") or symbol_query).upper()
    display_name = str(symbol_data.get("display_name") or symbol).strip()
    asset_type = str(symbol_data.get("asset_type") or "").upper()
    market = str(symbol_data.get("market") or "").strip()
    lookup_label = f"{display_name}({symbol})" if display_name and display_name.upper() != symbol else symbol
    context_parts = [lookup_label, "최근 뉴스 공시 시세 전망 리스크"]
    if asset_type:
        context_parts.append(asset_type)
    if market:
        context_parts.append(market)

    result = ChatbotWebFallbackSearchService().search(
        auth_header=auth_header,
        user_id=user_id,
        query=" ".join(context_parts),
        limit=5,
    )
    result_data = result.get("data") or {}
    result["data"] = {
        **result_data,
        "source": result_data.get("source") or "ASSET_OUTLOOK",
        "symbol": symbol,
        "display_name": display_name,
        "asset_type": asset_type,
        "market": market,
    }
    if result.get("reply"):
        result["reply"] = f"{lookup_label} 기준으로 확인한 전망 참고자료입니다.\n" + result["reply"]
    return result


def get_recommendation_candidates(auth_header: str, message: str) -> dict:
    result = ChatbotRecommendationService().recommend(auth_header, message)
    _store_last_recommendations(auth_header, result)
    return result


def _is_web_search_request(text: str) -> bool:
    normalized = str(text or "").upper()
    web_keywords = [
        "웹검색",
        "웹 검색",
        "검색해",
        "찾아줘",
        "찾아봐",
        "최신",
        "최근 뉴스",
        "뉴스",
        "공시",
        "구글",
        "TAVILY",
    ]
    return any(keyword.upper() in normalized for keyword in web_keywords)


def _is_asset_outlook_request(text: str) -> bool:
    outlook_keywords = ["전망", "분석", "오를까", "어때", "괜찮아", "살까", "투자해도"]
    return any(keyword in str(text or "") for keyword in outlook_keywords)


def _is_asset_price_request(text: str) -> bool:
    value = str(text or "")
    if any(keyword in value for keyword in ["얼마 있어", "자산 얼마", "내 돈", "평가 자산", "평가자산"]):
        return False
    price_keywords = ["현재가", "시세", "얼마", "가격", "주가"]
    if not any(keyword in value for keyword in price_keywords):
        return False
    return bool(_extract_symbol_query(value))


def run_chatbot_tool(auth_header: str | None, message: str) -> dict | None:
    if not auth_header:
        return None

    text = str(message or "")
    if _is_recommendation_reference_order(text):
        enforce_tool_safety("create_trade_proposal", {"message": text})
        return create_trade_proposal_from_recommendation_reference(auth_header, text)

    order_intent = parse_order_intent(text)
    if order_intent.is_order_request:
        enforce_tool_safety("create_trade_proposal", {"message": text})
        return create_trade_proposal_from_message(auth_header, text, order_intent)

    def guarded(tool_name: str, tool_func):
        enforce_tool_safety(tool_name, {"message": text})
        return tool_func(auth_header, text)

    is_strategy_request = any(keyword in text for keyword in ["전략", "제안", "추천", "타이밍", "비중", "시나리오", "리밸런싱"])
    is_direct_read_request = any(keyword in text for keyword in ["보여줘", "조회", "알려줘", "뽑아줘", "요약", "뭐뭐 있어", "얼마"])
    if "투자성향" in text and any(keyword in text for keyword in ["재분석", "다시", "변경", "수정"]):
        return get_investment_profile_reanalysis_guide()
    if any(keyword in text for keyword in ["환율", "환전", "달러", "미달러", "엔화", "유로", "위안", "테더", "USDT"]):
        return guarded("get_exchange_rate", get_exchange_rate)
    if _is_asset_price_request(text):
        return guarded("get_asset_price", get_asset_price)
    if any(keyword in text for keyword in ["순위", "랭킹", "상위", "필터"]):
        return guarded("get_home_market_rankings", get_home_market_rankings)
    if any(keyword in text for keyword in ["관심종목", "관심 종목"]) and any(keyword in text for keyword in ["해제", "삭제", "제거", "빼줘", "빼", "없애"]):
        return guarded("remove_watchlist_item", remove_watchlist_item)
    if any(keyword in text for keyword in ["관심종목", "관심 종목"]) and any(keyword in text for keyword in ["설정", "추가", "등록", "넣어", "넣어줘"]):
        return guarded("add_watchlist_item", add_watchlist_item)
    if any(keyword in text for keyword in ["미체결", "열린 주문", "오픈 주문", "대기 주문"]) and any(keyword in text for keyword in ["주문", "보여줘", "조회", "알려줘", "목록"]):
        return guarded("list_open_orders", list_open_orders)
    if any(keyword in text for keyword in ["거래내역", "거래 내역", "주문내역", "주문 내역"]):
        return guarded("search_trade_history", search_trade_history)
    if any(keyword in text for keyword in ["추천", "뭐 사", "뭐살", "후보", "살만한", "매수 후보"]):
        return guarded("get_asset_outlook", get_recommendation_candidates)
    if _is_asset_outlook_request(text):
        return guarded("get_asset_outlook", get_asset_outlook)
    is_portfolio_summary_request = (
        "요약" in text
        and any(keyword in text for keyword in ["보유", "자산", "포트폴리오", "계좌"])
    )
    if is_portfolio_summary_request:
        return guarded("get_portfolio_summary", get_portfolio_summary)
    if not is_strategy_request and any(keyword in text for keyword in ["보유", "내 주식", "뭐뭐 있어", "들고"]):
        return guarded("get_holdings", get_holdings)
    if (not is_strategy_request or is_direct_read_request) and any(keyword in text for keyword in ["평가 자산", "평가자산", "내 돈", "얼마 있어", "자산 얼마"]):
        return guarded("get_portfolio_summary", get_portfolio_summary)
    if _is_web_search_request(text):
        return guarded("search_web", search_web)
    return None


CURRENCY_ALIASES = {
    "달러": "USD",
    "미국달러": "USD",
    "미달러": "USD",
    "USD": "USD",
    "테더": "USDT",
    "테더달러": "USDT",
    "TETHER": "USDT",
    "USDT": "USDT",
    "원": "KRW",
    "원화": "KRW",
    "KRW": "KRW",
    "엔": "JPY",
    "엔화": "JPY",
    "JPY": "JPY",
    "유로": "EUR",
    "EUR": "EUR",
    "위안": "CNY",
    "위안화": "CNY",
    "CNY": "CNY",
    "파운드": "GBP",
    "GBP": "GBP",
    "호주달러": "AUD",
    "AUD": "AUD",
    "캐나다달러": "CAD",
    "CAD": "CAD",
    "홍콩달러": "HKD",
    "HKD": "HKD",
    "스위스프랑": "CHF",
    "CHF": "CHF",
    "싱가포르달러": "SGD",
    "SGD": "SGD",
}


def _detect_currency_pair(text: str) -> tuple[str, str]:
    upper_text = str(text or "").upper()
    detected = []
    for alias, code in CURRENCY_ALIASES.items():
        haystack = upper_text if alias.isascii() else text
        needle = alias.upper() if alias.isascii() else alias
        if needle in haystack and code not in detected:
            detected.append(code)

    non_krw = [code for code in detected if code != "KRW"]
    if len(non_krw) >= 2:
        return non_krw[0], non_krw[1]
    if non_krw:
        return non_krw[0], "KRW"
    return "USD", "KRW"
