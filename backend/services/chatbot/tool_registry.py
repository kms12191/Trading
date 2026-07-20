import math
import os
import re
import uuid
from decimal import Decimal, InvalidOperation, ROUND_DOWN
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

import requests

from backend.services.auth_service import get_user_id_from_header
from backend.services.chatbot.conversation_repository import ChatbotConversationRepository
from backend.services.supabase_client import query_supabase, safe_query_supabase, safe_query_supabase_as_service_role
from backend.services.symbol_metadata import enrich_symbol
from backend.services.chatbot.web_fallback_search_service import ChatbotWebFallbackSearchService
from backend.services.chatbot.safety_guard import enforce_tool_safety
from backend.services.chatbot.order_parser import ParsedOrderIntent, parse_order_intent
from backend.services.chatbot.order_form_policy import build_order_form_redirect
from backend.services.chatbot.tool_symbol_model import (
    SYMBOL_QUERY_ALIASES,
    SymbolDisambiguationError,
    asset_route as _asset_route,
    build_symbol_choice_response as _build_symbol_choice_response,
    extract_symbol_query as _extract_symbol_query,
    load_training_universe_symbols as _load_training_universe_symbols,
    normalize_symbol_alias,
    normalize_symbol_result as _normalize_symbol_result,
)
from backend.services.chatbot.portfolio_summary_service import (
    build_portfolio_totals,
    format_portfolio_reply,
    normalize_account_summary,
)
from backend.services.chatbot.recommendation_service import ChatbotRecommendationService
from backend.services.chatbot.asset_ml_outlook import build_single_asset_ml_outlook
from backend.services.crypto_asset_service import find_crypto_asset_for_query, validate_crypto_asset_tradable
from backend.services.toss_client import TossClient
from backend.utils.crypto_helper import CryptoHelper


API_BASE_URL = os.getenv("CHATBOT_INTERNAL_API_BASE_URL", "http://localhost:5050")
OPEN_ORDER_STATUSES = ("PENDING", "APPROVED", "ORDERED", "OPEN", "PARTIALLY_FILLED", "MODIFIED")
_conversation_repository = ChatbotConversationRepository()

def list_available_tools() -> list[str]:
    return [
        "get_home_market_rankings",
        "get_portfolio_summary",
        "add_watchlist_item",
        "remove_watchlist_item",
        "get_holdings",
        "search_trade_history",
        "list_open_orders",
        "get_market_calendar",
        "get_exchange_rate",
        "get_asset_krw_conversion",
        "get_asset_price",
        "get_asset_orderbook",
        "get_asset_candles",
        "get_crypto_market_context",
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


def _search_symbol_candidates(auth_header: str, query: str, limit: int = 5) -> list[dict]:
    if not query:
        return []
    try:
        payload = _get_internal("/api/symbol/search", auth_header, params={"query": query})
    except Exception:
        return []

    candidates = []
    seen = set()
    for row in payload.get("data") or []:
        candidate = _normalize_symbol_result(row if isinstance(row, dict) else {})
        symbol = candidate.get("symbol")
        if not symbol:
            continue
        key = (candidate.get("asset_type"), symbol)
        if key in seen:
            continue
        seen.add(key)
        candidates.append(candidate)
        if len(candidates) >= limit:
            break
    return candidates


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


def _format_trade_datetime_parts(value) -> tuple[str, str]:
    text = str(value or "").strip()
    if not text:
        return "-", "-"
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        return parsed.date().isoformat(), parsed.strftime("%H:%M:%S")
    except ValueError:
        return text[:10] or "-", "-"


def _is_likely_symbol_token(value: str) -> bool:
    token = str(value or "").strip().upper()
    return bool(re.fullmatch(r"[A-Z0-9._-]{2,12}", token))


def _is_numeric_stock_code(value: str) -> bool:
    return bool(re.fullmatch(r"\d{4,7}", str(value or "").strip()))


def _resolve_symbol(auth_header: str, query: str) -> dict:
    normalized_query = normalize_symbol_alias(query)
    if not normalized_query:
        raise ValueError("종목명 또는 종목코드가 필요합니다.")
    try:
        payload = _get_internal("/api/symbol/lookup", auth_header, params={"query": normalized_query})
        data = payload.get("data") or {}
    except Exception as lookup_error:
        candidates = _search_symbol_candidates(auth_header, normalized_query)
        if len(candidates) == 1:
            return candidates[0]
        if len(candidates) > 1:
            raise SymbolDisambiguationError(normalized_query, candidates) from lookup_error
        raise ValueError("종목을 찾지 못했습니다.") from lookup_error

    if not data.get("symbol"):
        candidates = _search_symbol_candidates(auth_header, normalized_query)
        if len(candidates) == 1:
            return candidates[0]
        if len(candidates) > 1:
            raise SymbolDisambiguationError(normalized_query, candidates)
        raise ValueError("종목을 찾지 못했습니다.")
    return _normalize_symbol_result(data)


def _detect_exchange(text: str) -> str | None:
    normalized = text.upper()
    if "토스" in text or "TOSS" in normalized:
        return "TOSS"
    if "KIS" in normalized or "한국투자" in text or "한투" in text:
        return "KIS"
    if "코인원" in text or "COINONE" in normalized:
        return "COINONE"
    if "BINANCE_UM_FUTURES" in normalized or ("바이낸스" in text and "선물" in text):
        return "BINANCE_UM_FUTURES"
    if "바이낸스" in text or "BINANCE" in normalized:
        return "BINANCE"
    return None


def _default_exchange_for_asset(asset_type: str, market: str, symbol: str | None = None) -> str:
    if str(asset_type or "").upper() == "CRYPTO":
        crypto_asset = find_crypto_asset_for_query(symbol or "")
        if crypto_asset and crypto_asset.get("default_exchange"):
            return str(crypto_asset["default_exchange"]).upper()
        return "COINONE"
    return "TOSS"


def _crypto_asset_policy_error(symbol: str, exchange: str) -> str | None:
    try:
        validate_crypto_asset_tradable(symbol, exchange)
        return None
    except ValueError as error:
        return str(error)


def _detect_env(text: str) -> str | None:
    if "모의" in text or "MOCK" in text.upper():
        return "MOCK"
    if "실전" in text or "실거래" in text or "REAL" in text.upper():
        return "REAL"
    return None


def _detect_market_country_for_calendar(text: str) -> str | None:
    value = str(text or "")
    upper_value = value.upper()
    kr_keywords = [
        "한국장",
        "국내장",
        "국장",
        "한국 증시",
        "국내 증시",
        "코스피",
        "코스닥",
        "KRX",
        "KOSPI",
        "KOSDAQ",
        "제헌절",
        "한글날",
        "광복절",
        "개천절",
        "추석",
        "설날",
    ]
    us_keywords = [
        "미국장",
        "미장",
        "미국 증시",
        "나스닥",
        "뉴욕증시",
        "NYSE",
        "NASDAQ",
        "S&P",
        "에스앤피",
        "다우",
    ]
    if any(keyword.upper() in upper_value for keyword in us_keywords):
        return "US"
    if any(keyword.upper() in upper_value for keyword in kr_keywords):
        return "KR"
    return None


def _detect_calendar_date(text: str) -> str:
    value = str(text or "")
    now = datetime.now(timezone(timedelta(hours=9)))
    if "오늘" in value:
        return now.date().isoformat()
    if "내일" in value:
        return (now.date() + timedelta(days=1)).isoformat()
    if "어제" in value:
        return (now.date() - timedelta(days=1)).isoformat()

    iso_match = re.search(r"(20\d{2})[-./년\s]+(\d{1,2})[-./월\s]+(\d{1,2})", value)
    if iso_match:
        year, month, day = (int(part) for part in iso_match.groups())
        return datetime(year, month, day).date().isoformat()

    month_day_match = re.search(r"(\d{1,2})\s*월\s*(\d{1,2})\s*일", value)
    if month_day_match:
        month, day = (int(part) for part in month_day_match.groups())
        return datetime(now.year, month, day).date().isoformat()

    return now.date().isoformat()


def _is_calendar_request(text: str) -> bool:
    value = str(text or "")
    calendar_keywords = [
        "장 열",
        "장열",
        "개장",
        "휴장",
        "거래 가능",
        "정규거래",
        "정규 거래",
        "장 운영",
        "캘린더",
        "쉬는날",
        "쉬는 날",
    ]
    return any(keyword in value for keyword in calendar_keywords) and any(
        keyword in value
        for keyword in ["장", "증시", "거래", "시장", "한국", "국내", "미국", "제헌절", "휴장", "개장"]
    )


def _get_user_toss_calendar_client(auth_header: str, broker_env: str = "REAL") -> TossClient:
    user_id, _ = get_user_id_from_header(auth_header)
    try:
        from backend.services.credentials_gateway import CredentialsGateway
        gateway = CredentialsGateway()
        creds = gateway.get_credentials(auth_header, user_id, "TOSS", broker_env)
        return TossClient(
            client_id=creds["access_key"],
            client_secret=creds["secret_key"],
            account_seq=creds["toss_account_seq"],
            env=broker_env,
            user_id=user_id,
        )
    except Exception:
        pass

    client_id = os.getenv("SHARED_TOSS_CLIENT_ID") or os.getenv("TOSS_CLIENT_ID") or os.getenv("TOSS_API_KEY")
    client_secret = os.getenv("SHARED_TOSS_CLIENT_SECRET") or os.getenv("TOSS_CLIENT_SECRET") or os.getenv("TOSS_SECRET_KEY")
    account_seq = os.getenv("SHARED_TOSS_ACCOUNT_SEQ") or os.getenv("TOSS_ACCOUNT_SEQ")
    if client_id and client_secret:
        return TossClient(
            client_id=client_id,
            client_secret=client_secret,
            account_seq=account_seq,
            env=broker_env,
            user_id="shared_system",
        )

    return TossClient(client_id="", client_secret="", env="MOCK", user_id="mock_calendar")


def _calendar_session(raw: dict, key: str) -> dict:
    today = raw.get("today") if isinstance(raw, dict) else {}
    integrated = today.get("integrated") if isinstance(today, dict) else {}
    session = integrated.get(key) if isinstance(integrated, dict) else {}
    return session if isinstance(session, dict) else {}


def _normalize_calendar_row(market_country: str, trade_date: str, raw: dict, source: str) -> dict:
    today = raw.get("today") if isinstance(raw, dict) else {}
    regular = _calendar_session(raw, "regularMarket")
    regular_open_at = regular.get("startTime")
    regular_close_at = regular.get("endTime")
    is_open = bool(today and regular_open_at and regular_close_at)
    holiday_name = ""
    if isinstance(today, dict):
        holiday_name = str(today.get("holidayName") or today.get("name") or "").strip()
    if not is_open and not holiday_name:
        holiday_name = "휴장일"
    return {
        "market_country": market_country,
        "trade_date": trade_date,
        "is_open": is_open,
        "holiday_name": holiday_name or None,
        "regular_open_at": regular_open_at,
        "regular_close_at": regular_close_at,
        "source": source,
        "raw_payload": raw,
    }


def _fetch_calendar_row_from_db(market_country: str, trade_date: str) -> dict | None:
    rows = safe_query_supabase_as_service_role(
        "market_calendar_days",
        "GET",
        params={
            "market_country": f"eq.{market_country}",
            "trade_date": f"eq.{trade_date}",
            "select": "id,market_country,trade_date,is_open,holiday_name,regular_open_at,regular_close_at,source,raw_payload",
            "limit": "1",
        },
    ) or []
    return rows[0] if rows else None


def _upsert_calendar_row(row: dict) -> None:
    existing = _fetch_calendar_row_from_db(row["market_country"], row["trade_date"])
    if existing and existing.get("id"):
        safe_query_supabase_as_service_role(
            f"market_calendar_days?id=eq.{existing['id']}",
            "PATCH",
            json_data=row,
        )
        return
    safe_query_supabase_as_service_role("market_calendar_days", "POST", json_data=row)


def _format_calendar_reply(row: dict, requested_text: str) -> str:
    country = row.get("market_country")
    country_label = "한국장" if country == "KR" else "미국장"
    trade_date = row.get("trade_date")
    source = row.get("source") or "DB"
    if row.get("is_open"):
        open_at = str(row.get("regular_open_at") or "")
        close_at = str(row.get("regular_close_at") or "")
        session_text = ""
        if open_at and close_at:
            session_text = f"\n정규장 시간: {open_at} ~ {close_at}"
        return f"{trade_date} 기준\n{country_label}은 정규 거래일입니다.{session_text}\n출처: {source}"
    holiday = row.get("holiday_name") or "휴장일"
    return f"{trade_date} 기준\n{country_label}은 휴장일입니다.\n사유: {holiday}\n출처: {source}"


def get_market_calendar(auth_header: str, message: str, market_country: str = None, date: str = None, broker_env: str = None, **kwargs) -> dict:
    market_country = market_country or _detect_market_country_for_calendar(message)
    trade_date = date or _detect_calendar_date(message)
    if not market_country:
        return {
            "reply": "어느 시장의 장 운영 여부를 확인할까요?\n예: 한국장, 미국장",
            "data": {
                "source": "MARKET_CALENDAR",
                "reason": "missing_market_country",
                "trade_date": trade_date,
            },
        }

    cached_row = _fetch_calendar_row_from_db(market_country, trade_date)
    if cached_row:
        return {
            "reply": _format_calendar_reply(cached_row, message),
            "data": {
                "source": "MARKET_CALENDAR_DB",
                "market_country": market_country,
                "trade_date": trade_date,
                "row": cached_row,
            },
        }

    today = datetime.now(timezone(timedelta(hours=9))).date().isoformat()
    if trade_date != today:
        country_label = "한국장" if market_country == "KR" else "미국장"
        return {
            "reply": (
                f"{trade_date} 기준 {country_label} 장 운영 데이터가 아직 DB에 없습니다.\n"
                "특정 날짜의 개장/휴장 여부는 캘린더 DB 적재 후 확인할 수 있습니다.\n"
                "현재는 값을 추측하지 않습니다."
            ),
            "data": {
                "source": "MARKET_CALENDAR_DB_MISS",
                "market_country": market_country,
                "trade_date": trade_date,
            },
        }

    env = broker_env or _detect_env(message) or "REAL"
    try:
        client = _get_user_toss_calendar_client(auth_header, env)
        raw = client.get_market_calendar(market_country)
    except Exception as error:
        return {
            "reply": (
                "장 운영 캘린더를 조회하지 못했습니다.\n"
                "Toss API 키, 계좌 환경, API 허용 IP를 확인한 뒤 다시 시도해 주세요."
            ),
            "data": {
                "source": "MARKET_CALENDAR_ERROR",
                "market_country": market_country,
                "trade_date": trade_date,
                "error": str(error),
            },
        }

    row = _normalize_calendar_row(market_country, trade_date, raw, "TOSS")
    _upsert_calendar_row(row)
    return {
        "reply": _format_calendar_reply(row, message),
        "data": {
            "source": "MARKET_CALENDAR_TOSS",
            "market_country": market_country,
            "trade_date": trade_date,
            "row": row,
        },
    }


def _detect_candle_interval(text: str) -> str:
    value = str(text or "")
    normalized = value.upper()
    if "1분" in value or "1M" in normalized:
        return "1m"
    if "5분" in value or "5M" in normalized:
        return "5m"
    if "15분" in value or "15M" in normalized:
        return "15m"
    if "30분" in value or "30M" in normalized:
        return "30m"
    if "4시간" in value or "4H" in normalized:
        return "4h"
    if "1시간" in value or "시간봉" in value or "1H" in normalized:
        return "1h"
    if "주봉" in value or "1W" in normalized:
        return "1w"
    if "월봉" in value or "1MO" in normalized or "1MTH" in normalized:
        return "1M"
    return "1d"


def _format_candle_interval(interval: str) -> str:
    labels = {
        "1m": "1분봉",
        "5m": "5분봉",
        "15m": "15분봉",
        "30m": "30분봉",
        "1h": "1시간봉",
        "4h": "4시간봉",
        "1d": "일봉",
        "1w": "주봉",
        "1M": "월봉",
    }
    return labels.get(interval, interval)


def _is_plain_order_requiring_confirmation(message: str, parsed: ParsedOrderIntent) -> bool:
    """
    종목/방향/수량만 있는 첫 주문은 바로 사전검증하지 않고 사용자 확인을 먼저 받습니다.
    """
    if not parsed.symbol_query:
        return False
    if parsed.quantity is None or parsed.quantity <= 0:
        return False
    if parsed.price is not None or parsed.amount_krw is not None or parsed.sell_ratio is not None:
        return False
    if parsed.broker_env:
        return False
    return True


def _format_order_confirmation_reply(symbol_data: dict, parsed: ParsedOrderIntent, exchange: str, broker_env: str) -> str:
    symbol = str(symbol_data.get("symbol") or parsed.symbol_query).upper()
    display_name = str(symbol_data.get("display_name") or parsed.symbol_query or symbol).strip()
    asset_label = f"{display_name}({symbol})" if display_name and display_name.upper() != symbol else symbol
    side_label = "매수" if parsed.side == "BUY" else "매도"
    quantity_label = _format_quantity(parsed.quantity)
    env_label = "모의투자" if broker_env == "MOCK" else "실거래"
    return (
        f"{asset_label} {quantity_label}주 {side_label} 말씀하시는 건가요?\n"
        f"맞으면 '맞아' 또는 '응'이라고 답해 주세요. "
        f"확인 후 {exchange} {env_label} 기준으로 사전검증을 진행하겠습니다."
    )


def _store_order_confirmation(auth_header: str, message: str, parsed: ParsedOrderIntent, symbol_data: dict, exchange: str, broker_env: str) -> dict:
    user_id, _ = get_user_id_from_header(auth_header)
    _conversation_repository.set_pending_action(
        auth_header,
        user_id,
        "trade_order_confirmation",
        {
            "message": message,
            "symbol": str(symbol_data.get("symbol") or parsed.symbol_query).upper(),
            "symbol_query": parsed.symbol_query,
            "side": parsed.side,
            "quantity": parsed.quantity,
            "exchange": exchange,
            "broker_env": broker_env,
        },
        ttl_seconds=300,
    )
    return {
        "reply": _format_order_confirmation_reply(symbol_data, parsed, exchange, broker_env),
        "data": {
            "source": "CHATBOT_ORDER_CONFIRMATION",
            "status": "PENDING_CONFIRMATION",
            "exchange": exchange,
            "symbol": str(symbol_data.get("symbol") or parsed.symbol_query).upper(),
            "side": parsed.side,
            "quantity": parsed.quantity,
            "broker_env": broker_env,
        },
    }


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


def get_home_market_rankings(auth_header: str, message: str, asset_type: str = None, market_segment: str = None, ranking: str = None, limit: int = None, **kwargs) -> dict:
    ranking = ranking or _detect_ranking(message)
    segment = None
    if asset_type == "CRYPTO":
        segment = "CRYPTO"
    elif market_segment:
        segment = "국내" if market_segment == "KR" else "해외" if market_segment == "US" else "전체"
    
    segment = segment or _detect_market_segment(message)
    limit = int(limit) if limit else _detect_limit(message)
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


def get_portfolio_summary(auth_header: str, message: str, exchange: str = None, broker_env: str = None, **kwargs) -> dict:
    exchange_filter = exchange or _detect_exchange(message)
    env_filter = broker_env or _detect_env(message)
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
    ]
    return any(marker in text for marker in missing_markers)


def get_exchange_rate(auth_header: str, message: str, base_currency: str = None, quote_currency: str = None, broker_env: str = None, **kwargs) -> dict:
    base_detect, quote_detect = _detect_currency_pair(message)
    base_currency = base_currency or base_detect
    quote_currency = quote_currency or quote_detect
    env = broker_env or _detect_env(message) or "REAL"
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


KRW_CONVERSION_NOTICE = "실제 주문 금액은 환전 수수료, 주문 수수료, 체결가 변동에 따라 달라질 수 있습니다."


def _is_krw_conversion_request(text: str) -> bool:
    value = str(text or "")
    keywords = [
        "원화",
        "한화",
        "원으로",
        "KRW",
        "환율 계산",
        "환율계산",
        "원화 환산",
        "한화 환산",
        "원화로",
        "한화로",
    ]
    return any(keyword.upper() in value.upper() for keyword in keywords)


def _detect_share_quantity(text: str, default: float = 1.0) -> float:
    value = str(text or "")
    match = re.search(r"(\d+(?:\.\d+)?)\s*(?:주|株|shares?|SHARES?)", value, flags=re.IGNORECASE)
    if not match:
        return default
    quantity = _to_float(match.group(1), default)
    return quantity if quantity > 0 else default


def _get_usd_krw_rate(auth_header: str, broker_env: str = "REAL") -> dict:
    payload = _get_internal(
        "/api/market/exchange-rate",
        auth_header,
        params={
            "base": "USD",
            "quote": "KRW",
            "broker_env": broker_env,
        },
    )
    data = payload.get("data") or {}
    return {
        "rate": _to_float(data.get("rate")),
        "source": data.get("source") or "TOSS",
        "captured_at": str(data.get("captured_at") or "")[:10],
        "raw": data,
    }


def _resolve_asset_price_for_krw_conversion(auth_header: str, message: str, context: dict | None = None) -> dict:
    context_data = context if isinstance(context, dict) else {}
    symbol = str(context_data.get("symbol") or "").upper()
    display_name = str(context_data.get("display_name") or symbol).strip()
    asset_type = str(context_data.get("asset_type") or "").upper()
    market = str(context_data.get("market") or "").upper()
    exchange = str(context_data.get("exchange") or "").upper()
    broker_env = str(context_data.get("broker_env") or _detect_env(message) or "REAL").upper()
    current_price = _to_float(context_data.get("current_price"))
    currency = str(context_data.get("currency") or "").upper()

    if not symbol:
        symbol_query = _extract_symbol_query(message)
        if not symbol_query:
            return {"error": "missing_symbol"}
        try:
            symbol_data = _resolve_symbol(auth_header, symbol_query)
        except SymbolDisambiguationError as error:
            return {"disambiguation": _build_symbol_choice_response(error.query, error.candidates)}
        except Exception:
            return {"error": "symbol_not_found", "query": symbol_query}

        symbol = str(symbol_data.get("symbol") or symbol_query).upper()
        display_name = str(symbol_data.get("display_name") or symbol).strip()
        asset_type = str(symbol_data.get("asset_type") or "").upper()
        market = str(symbol_data.get("market") or "").upper()
        exchange = _detect_exchange(message) or _default_exchange_for_asset(asset_type, market, symbol)
        broker_env = _detect_env(message) or "REAL"

    if current_price <= 0 or not currency:
        payload = _get_internal(
            "/api/chart/quote",
            auth_header,
            params={
                "exchange": exchange or _default_exchange_for_asset(asset_type, market, symbol),
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
        currency = str(data.get("currency") or currency or ("USD" if market == "US" else "KRW")).upper()
        exchange = str(data.get("exchange") or exchange).upper()

    return {
        "symbol": symbol,
        "display_name": display_name,
        "asset_type": asset_type,
        "market": market,
        "exchange": exchange,
        "broker_env": broker_env,
        "current_price": current_price,
        "currency": currency,
    }


def get_asset_krw_conversion(auth_header: str, message: str, context: dict | None = None) -> dict:
    asset = _resolve_asset_price_for_krw_conversion(auth_header, message, context)
    if asset.get("disambiguation"):
        return asset["disambiguation"]
    if asset.get("error") == "missing_symbol":
        return {
            "reply": "어떤 해외주식을 원화로 계산할까요?\n예: 애플 원화로 얼마야, AAPL 1주 한화로 계산해줘",
            "data": {"source": "ASSET_KRW_CONVERSION", "reason": "missing_symbol"},
        }
    if asset.get("error") == "symbol_not_found":
        return {
            "reply": f"{asset.get('query')} 종목을 찾지 못했습니다.\n종목명이나 종목코드를 다시 확인해 주세요.",
            "data": {"source": "ASSET_KRW_CONVERSION", "reason": "symbol_not_found"},
        }

    symbol = asset["symbol"]
    display_name = asset.get("display_name") or symbol
    label = f"{display_name}({symbol})" if display_name and display_name.upper() != symbol else symbol
    current_price = _to_float(asset.get("current_price"))
    currency = str(asset.get("currency") or "").upper()
    broker_env = str(asset.get("broker_env") or "REAL").upper()
    quantity = _detect_share_quantity(message)

    if current_price <= 0:
        return {
            "reply": f"{label}의 현재가를 확인하지 못해 원화 환산을 진행할 수 없습니다.\n\n{KRW_CONVERSION_NOTICE}",
            "data": {"source": "ASSET_KRW_CONVERSION", "symbol": symbol, "reason": "missing_price"},
        }
    if currency == "KRW":
        return {
            "reply": f"{label}은/는 이미 원화 기준 종목입니다.\n현재가: {_format_money(current_price, 'KRW')}\n\n{KRW_CONVERSION_NOTICE}",
            "data": {
                "source": "ASSET_KRW_CONVERSION",
                "symbol": symbol,
                "current_price": current_price,
                "currency": currency,
                "reason": "already_krw",
            },
        }
    if currency != "USD":
        return {
            "reply": f"{label}의 통화가 {currency}라서 1차 원화 환산은 USD 종목만 지원합니다.\n\n{KRW_CONVERSION_NOTICE}",
            "data": {
                "source": "ASSET_KRW_CONVERSION",
                "symbol": symbol,
                "current_price": current_price,
                "currency": currency,
                "reason": "unsupported_currency",
            },
        }

    rate_data = _get_usd_krw_rate(auth_header, broker_env)
    rate = _to_float(rate_data.get("rate"))
    if rate <= 0:
        return {
            "reply": f"USD/KRW 환율을 확인하지 못해 {label}의 원화 환산을 진행할 수 없습니다.\n\n{KRW_CONVERSION_NOTICE}",
            "data": {"source": "ASSET_KRW_CONVERSION", "symbol": symbol, "reason": "missing_exchange_rate"},
        }

    converted_krw = current_price * rate * quantity
    quantity_label = _format_quantity(quantity)
    captured_at = rate_data.get("captured_at")
    basis_line = f"{captured_at} 기준" if captured_at else "현재 조회 기준"
    reply = "\n".join([
        f"{label} 원화 환산 금액입니다.",
        "",
        f"{quantity_label}주 현재가: {_format_money(current_price, 'USD')}",
        f"적용 환율: 1 USD = {rate:,.2f}원",
        f"계산식: {current_price:,.2f} × {rate:,.2f} × {quantity_label} = 약 {converted_krw:,.0f}원",
        f"출처: {rate_data.get('source') or 'TOSS'} / {basis_line}",
        "",
        KRW_CONVERSION_NOTICE,
    ])
    return {
        "reply": reply,
        "data": {
            "source": "ASSET_KRW_CONVERSION",
            "symbol": symbol,
            "display_name": display_name,
            "exchange": asset.get("exchange"),
            "broker_env": broker_env,
            "current_price": current_price,
            "currency": currency,
            "quantity": quantity,
            "exchange_rate": rate,
            "converted_krw": converted_krw,
            "exchange_rate_source": rate_data.get("source"),
            "captured_at": captured_at,
        },
    }


STOCK_WARNING_LABELS = {
    "TRADING_SUSPENDED": "거래정지",
    "LIQUIDATION_TRADING": "정리매매",
    "INVESTMENT_RISK": "투자위험",
    "INVESTMENT_WARNING": "투자경고",
    "INVESTMENT_ALERT": "투자주의",
    "OVERHEATED": "단기과열",
    "VI_STATIC_AND_DYNAMIC": "정적/동적 VI",
    "VI_STATIC": "정적 VI",
    "VI_DYNAMIC": "동적 VI",
}


def _is_stock_asset_for_status(asset_type: str, exchange: str) -> bool:
    normalized_asset_type = str(asset_type or "").upper()
    normalized_exchange = str(exchange or "").upper()
    return normalized_asset_type.startswith("STOCK") or normalized_exchange in {"TOSS", "KIS"}


def _format_stock_trade_status(warnings: list[dict] | None) -> str:
    if not warnings:
        return "거래상태: 특이사항 없음"

    labels = []
    for warning in warnings:
        if not isinstance(warning, dict):
            continue
        warning_type = str(warning.get("warning_type") or "").upper()
        label = STOCK_WARNING_LABELS.get(warning_type) or str(warning.get("label") or "").strip()
        if label and label not in labels:
            labels.append(label)

    if not labels:
        return "거래상태: 특이사항 있음"
    return f"거래상태: {', '.join(labels[:3])}"


def _extract_stock_warning_labels(warnings: list[dict] | None) -> list[str]:
    labels = []
    for warning in warnings or []:
        if not isinstance(warning, dict):
            continue
        warning_type = str(warning.get("warning_type") or "").upper()
        label = STOCK_WARNING_LABELS.get(warning_type) or str(warning.get("label") or "").strip()
        if label and label not in labels:
            labels.append(label)
    return labels


def _format_stock_trade_status_sentence(asset_label: str, trade_status: dict | None) -> str:
    if not trade_status:
        return ""
    if trade_status.get("status_lookup_failed"):
        return f"현재 {asset_label}은/는 거래상태를 확인하지 못했습니다."

    labels = trade_status.get("labels")
    if not isinstance(labels, list):
        labels = _extract_stock_warning_labels(trade_status.get("warnings") or [])

    if not labels:
        return f"현재 {asset_label}은/는 거래 관련 특이사항이 확인되지 않았습니다."

    if "거래정지" in labels:
        return f"현재 {asset_label}은/는 거래정지 상태입니다."
    if "정리매매" in labels:
        return f"현재 {asset_label}은/는 정리매매 상태입니다."
    return f"현재 {asset_label}은/는 {', '.join(labels[:3])} 상태입니다."


def _get_stock_trade_status(auth_header: str, symbol: str, broker_env: str) -> dict:
    try:
        payload = _get_internal(
            "/api/stocks/warnings",
            auth_header,
            params={
                "symbol": symbol,
                "exchange": "TOSS",
                "broker_env": broker_env,
            },
        )
        data = payload.get("data") or {}
        warnings = data.get("warnings") if isinstance(data, dict) else []
        warnings = warnings if isinstance(warnings, list) else []
        return {
            "status_text": _format_stock_trade_status(warnings),
            "status_sentence": "",
            "labels": _extract_stock_warning_labels(warnings),
            "warnings": warnings,
            "status_lookup_failed": False,
        }
    except Exception:
        return {
            "status_text": "거래상태: 확인 실패",
            "status_sentence": "",
            "labels": [],
            "warnings": [],
            "status_lookup_failed": True,
        }


def _is_asset_trade_status_request(text: str) -> bool:
    value = str(text or "")
    status_keywords = [
        "거래 가능",
        "거래가능",
        "거래정지",
        "거래 상태",
        "거래상태",
        "특이사항",
        "유의사항",
        "투자경고",
        "정리매매",
        "매수 가능",
        "매수가능",
        "매도 가능",
        "매도가능",
    ]
    return bool(_extract_symbol_query(value)) and any(keyword in value for keyword in status_keywords)


def get_asset_trade_status(auth_header: str, message: str) -> dict:
    symbol_query = _extract_symbol_query(message)
    if not symbol_query:
        return {
            "reply": "거래상태를 확인할 종목명이나 종목코드를 알려주세요.",
            "data": {"source": "STOCK_TRADE_STATUS", "reason": "missing_symbol"},
        }

    try:
        symbol_data = _resolve_symbol(auth_header, symbol_query)
    except SymbolDisambiguationError as error:
        return _build_symbol_choice_response(error.query, error.candidates)
    except ValueError:
        return {
            "reply": f"{symbol_query} 종목을 찾지 못했습니다.\n종목명이나 종목코드를 다시 확인해 주세요.",
            "data": {"source": "STOCK_TRADE_STATUS", "query": symbol_query, "reason": "symbol_not_found"},
        }

    symbol = str(symbol_data.get("symbol") or symbol_query).upper()
    display_name = str(symbol_data.get("display_name") or symbol).strip()
    asset_type = str(symbol_data.get("asset_type") or "STOCK").upper()
    market = str(symbol_data.get("market") or "").upper()
    exchange = _default_exchange_for_asset(asset_type, market, symbol)
    label = f"{display_name}({symbol})" if display_name and display_name.upper() != symbol else symbol

    if not _is_stock_asset_for_status(asset_type, exchange):
        return {
            "reply": f"{label}은/는 현재 주식 종목 거래상태 조회 대상이 아닙니다.",
            "data": {
                "source": "STOCK_TRADE_STATUS",
                "symbol": symbol,
                "display_name": display_name,
                "asset_type": asset_type,
                "market": market,
                "reason": "unsupported_asset_type",
            },
        }

    broker_env = _detect_env(message) or "REAL"
    trade_status = _get_stock_trade_status(auth_header, symbol, broker_env)
    status_text = str(trade_status.get("status_text") or "거래상태: 확인 실패")
    if trade_status.get("status_lookup_failed"):
        reply = f"{label}의 거래상태를 확인하지 못했습니다.\nToss API 키, 허용 IP, 계좌 연결 상태를 확인한 뒤 다시 시도해 주세요."
    else:
        reply = f"{label}의 {status_text}입니다."
    return {
        "reply": reply,
        "data": {
            "source": "STOCK_TRADE_STATUS",
            "symbol": symbol,
            "display_name": display_name,
            "asset_type": asset_type,
            "market": market,
            "broker_env": broker_env,
            "trade_status": trade_status,
        },
    }


def _append_trade_status_to_reply(reply: str, trade_status: dict | None, asset_label: str = "") -> str:
    status_text = _format_stock_trade_status_sentence(asset_label, trade_status) if asset_label else str((trade_status or {}).get("status_text") or "").strip()
    if not status_text:
        return reply
    return f"{str(reply or '').rstrip()}\n{status_text}"


def get_asset_price(auth_header: str, message: str, exchange: str = None, broker_env: str = None, **kwargs) -> dict:
    symbol_query = _extract_symbol_query(message)
    if not symbol_query:
        return {
            "reply": "현재가를 확인할 종목명이나 종목코드를 알려주세요.",
            "data": {"source": "ASSET_PRICE", "reason": "missing_symbol"},
        }

    try:
        symbol_data = _resolve_symbol(auth_header, symbol_query)
    except SymbolDisambiguationError as error:
        return _build_symbol_choice_response(error.query, error.candidates)
    except Exception:
        if _is_numeric_stock_code(symbol_query) or not _is_likely_symbol_token(symbol_query):
            return {
                "reply": f"{symbol_query} 종목을 찾지 못했습니다.\n종목명이나 종목코드를 다시 확인해 주세요.",
                "data": {"source": "ASSET_PRICE", "query": symbol_query, "reason": "symbol_not_found"},
            }
        symbol_data = {}

    symbol = str(symbol_data.get("symbol") or symbol_query).upper()
    display_name = str(symbol_data.get("display_name") or symbol).strip()
    asset_type = str(symbol_data.get("asset_type") or "").upper()
    market = str(symbol_data.get("market") or "").strip().upper()
    label = f"{display_name}({symbol})" if display_name and display_name.upper() != symbol else symbol
    exchange = exchange or _detect_exchange(message) or _default_exchange_for_asset(asset_type, market, symbol)
    broker_env = broker_env or _detect_env(message) or "REAL"
    try:
        payload = _get_internal(
            "/api/chart/quote",
            auth_header,
            params={
                "exchange": exchange,
                "symbol": symbol,
                "broker_env": broker_env,
            },
        )
    except Exception:
        return {
            "reply": f"{label} 현재가를 확인하지 못했습니다.\n거래소 시세 조회가 일시적으로 지연되고 있습니다.\n잠시 후 다시 시도해 주세요.",
            "data": {
                "source": "ASSET_PRICE",
                "symbol": symbol,
                "exchange": exchange,
                "broker_env": broker_env,
                "reason": "quote_api_failed",
            },
        }
    data = payload.get("data") or {}
    current_price = _to_float(
        data.get("current_price")
        or data.get("price")
        or data.get("last")
        or data.get("close")
    )
    change_rate = _to_float(data.get("change_rate"))
    currency = str(data.get("currency") or ("USD" if market == "US" else "KRW")).upper()

    if current_price <= 0:
        return {
            "reply": f"{label}의 현재가 정보를 거래소에서 실시간으로 가져오지 못했습니다. 거래소 미지원 종목이거나 일시적 지연 상태일 수 있습니다. (지정가 매매 제안 생성은 정상적으로 시도하실 수 있습니다.)",
            "data": {
                "source": "ASSET_PRICE",
                "symbol": symbol,
                "exchange": exchange,
                "broker_env": broker_env,
                "current_price": None,
                "change_rate": 0.0,
                "currency": currency,
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


_get_asset_price_base = get_asset_price


def get_asset_price(auth_header: str, message: str, exchange: str = None, broker_env: str = None, **kwargs) -> dict:
    result = _get_asset_price_base(auth_header, message, exchange=exchange, broker_env=broker_env, **kwargs)
    data = result.get("data") if isinstance(result, dict) else {}
    if not isinstance(data, dict) or data.get("source") != "ASSET_PRICE":
        return result

    symbol = str(data.get("symbol") or "").upper()
    exchange = str(data.get("exchange") or "").upper()
    asset_type = str(data.get("asset_type") or "").upper()
    broker_env = str(data.get("broker_env") or _detect_env(message) or "REAL").upper()
    if not symbol or not _is_stock_asset_for_status(asset_type, exchange):
        return result

    display_name = str(data.get("display_name") or symbol).strip()
    label = f"{display_name}({symbol})" if display_name and display_name.upper() != symbol else symbol
    trade_status = _get_stock_trade_status(auth_header, symbol, broker_env)
    data["trade_status"] = trade_status

    current_price = _to_float(data.get("current_price"))
    change_rate = _to_float(data.get("change_rate"))
    currency = str(data.get("currency") or "KRW").upper()
    if current_price > 0:
        result["reply"] = _append_trade_status_to_reply(
            f"{label} 현재가는 {_format_money(current_price, currency)}입니다.\n등락률은 {change_rate:+.2f}%입니다.",
            trade_status,
            label,
        )
    else:
        result["reply"] = _append_trade_status_to_reply(
            f"{label}의 현재가 정보를 거래소에서 실시간으로 가져오지 못했습니다.\n거래정지, 미지원 종목, 일시 지연 상태일 수 있습니다.",
            trade_status,
            label,
        )
    return result


def get_asset_orderbook(auth_header: str, message: str, exchange: str = None, broker_env: str = None, **kwargs) -> dict:
    symbol_query = _extract_symbol_query(message)
    if not symbol_query:
        return {
            "reply": "호가를 확인할 종목명이나 종목코드를 알려주세요.",
            "data": {"source": "ASSET_ORDERBOOK", "reason": "missing_symbol"},
        }

    try:
        symbol_data = _resolve_symbol(auth_header, symbol_query)
    except SymbolDisambiguationError as error:
        return _build_symbol_choice_response(error.query, error.candidates)
    except Exception:
        return {
            "reply": f"{symbol_query} 종목을 찾지 못했습니다.\n종목명이나 종목코드를 다시 확인해 주세요.",
            "data": {"source": "ASSET_ORDERBOOK", "query": symbol_query, "reason": "symbol_not_found"},
        }

    symbol = str(symbol_data.get("symbol") or symbol_query).upper()
    display_name = str(symbol_data.get("display_name") or symbol).strip()
    asset_type = str(symbol_data.get("asset_type") or "").upper()
    market = str(symbol_data.get("market") or "").strip().upper()
    label = f"{display_name}({symbol})" if display_name and display_name.upper() != symbol else symbol
    exchange = exchange or _detect_exchange(message) or _default_exchange_for_asset(asset_type, market, symbol)
    broker_env = broker_env or _detect_env(message) or "REAL"

    try:
        payload = _get_internal(
            "/api/chart/orderbook",
            auth_header,
            params={
                "exchange": exchange,
                "symbol": symbol,
                "broker_env": broker_env,
            },
        )
    except Exception:
        return {
            "reply": f"{label} 호가 정보를 조회하지 못했습니다.\n거래소 연결 상태, API 키 권한, 장 운영 상태를 확인해 주세요.",
            "data": {
                "source": "ASSET_ORDERBOOK",
                "symbol": symbol,
                "exchange": exchange,
                "broker_env": broker_env,
                "reason": "orderbook_api_failed",
            },
        }

    data = payload.get("data") or {}
    meta = payload.get("meta") or {}
    asks = data.get("asks") if isinstance(data.get("asks"), list) else []
    bids = data.get("bids") if isinstance(data.get("bids"), list) else []
    best_ask = asks[0] if asks else {}
    best_bid = bids[0] if bids else {}
    best_ask_price = _to_float(best_ask.get("price"))
    best_bid_price = _to_float(best_bid.get("price"))
    best_ask_size = _to_float(best_ask.get("size"))
    best_bid_size = _to_float(best_bid.get("size"))
    currency = "USD" if market == "US" else "KRW"

    if best_ask_price <= 0 and best_bid_price <= 0:
        return {
            "reply": f"{label} 호가 정보를 찾지 못했습니다.\n거래소 API 응답이 비어 있거나 장 운영 상태가 호가 제공 대상이 아닐 수 있습니다.",
            "data": {
                "source": "ASSET_ORDERBOOK",
                "symbol": symbol,
                "exchange": exchange,
                "broker_env": broker_env,
                "reason": "empty_orderbook",
            },
        }

    source_label = str(meta.get("source") or "LIVE").upper()
    mock_notice = "\n실시간 호가가 아닌 임시 호가일 수 있습니다." if meta.get("is_mock") or source_label == "MOCK" else ""
    reply_lines = [f"{label} 호가입니다."]
    if best_ask_price > 0:
        reply_lines.append(f"최우선 매도호가: {_format_money(best_ask_price, currency)} / 잔량 {_format_quantity(best_ask_size)}")
    if best_bid_price > 0:
        reply_lines.append(f"최우선 매수호가: {_format_money(best_bid_price, currency)} / 잔량 {_format_quantity(best_bid_size)}")
    reply_lines.append(f"출처: {source_label}{mock_notice}")

    return {
        "reply": "\n".join(reply_lines),
        "data": {
            "source": "ASSET_ORDERBOOK",
            "symbol": symbol,
            "display_name": display_name,
            "asset_type": asset_type,
            "market": market,
            "exchange": exchange,
            "broker_env": broker_env,
            "best_ask": best_ask,
            "best_bid": best_bid,
            "asks": asks[:5],
            "bids": bids[:5],
            "meta": meta,
        },
    }


def get_asset_candles(auth_header: str, message: str, exchange: str = None, broker_env: str = None, interval: str = None, count: int = None, **kwargs) -> dict:
    symbol_query = _extract_symbol_query(message)
    if not symbol_query:
        return {
            "reply": "캔들 흐름을 확인할 종목명이나 종목코드를 알려주세요.",
            "data": {"source": "ASSET_CANDLES", "reason": "missing_symbol"},
        }

    try:
        symbol_data = _resolve_symbol(auth_header, symbol_query)
    except SymbolDisambiguationError as error:
        return _build_symbol_choice_response(error.query, error.candidates)
    except Exception:
        return {
            "reply": f"{symbol_query} 종목을 찾지 못했습니다.\n종목명이나 종목코드를 다시 확인해 주세요.",
            "data": {"source": "ASSET_CANDLES", "query": symbol_query, "reason": "symbol_not_found"},
        }

    symbol = str(symbol_data.get("symbol") or symbol_query).upper()
    display_name = str(symbol_data.get("display_name") or symbol).strip()
    asset_type = str(symbol_data.get("asset_type") or "").upper()
    market = str(symbol_data.get("market") or "").strip().upper()
    label = f"{display_name}({symbol})" if display_name and display_name.upper() != symbol else symbol
    exchange = exchange or _detect_exchange(message) or _default_exchange_for_asset(asset_type, market, symbol)
    broker_env = broker_env or _detect_env(message) or "REAL"
    interval = interval or _detect_candle_interval(message)
    count = int(count) if count else 20

    try:
        payload = _get_internal(
            "/api/chart/candles",
            auth_header,
            params={
                "exchange": exchange,
                "symbol": symbol,
                "interval": interval,
                "count": count,
                "broker_env": broker_env,
            },
        )
    except Exception:
        return {
            "reply": (
                f"현재 {label}의 최근 캔들 차트 흐름을 확인할 수 없습니다.\n"
                "거래소 API 키, 허용 IP 설정 또는 장 운영 상태를 점검해 주세요.\n"
                "정확한 시세와 차트 정보가 필요하면 다시 요청해 주시기 바랍니다."
            ),
            "actions": [
                {
                    "type": "navigate",
                    "label": "상세보기",
                    "to": _asset_route(symbol_data),
                }
            ],
            "data": {
                "source": "ASSET_CANDLES",
                "symbol": symbol,
                "exchange": exchange,
                "broker_env": broker_env,
                "interval": interval,
                "reason": "candles_api_failed",
            },
        }

    candles = payload.get("data") or []
    candles = [candle for candle in candles if isinstance(candle, dict)]
    if not candles:
        return {
            "reply": (
                f"현재 {label}의 최근 캔들 차트 흐름을 확인할 수 없습니다.\n"
                "거래소 API 응답이 비어 있거나 장 운영 상태가 캔들 제공 대상이 아닐 수 있습니다.\n"
                "정확한 시세와 차트 정보가 필요하면 다시 요청해 주시기 바랍니다."
            ),
            "actions": [
                {
                    "type": "navigate",
                    "label": "상세보기",
                    "to": _asset_route(symbol_data),
                }
            ],
            "data": {
                "source": "ASSET_CANDLES",
                "symbol": symbol,
                "exchange": exchange,
                "broker_env": broker_env,
                "interval": interval,
                "reason": "empty_candles",
            },
        }

    recent = candles[-min(len(candles), 5):]
    first_close = _to_float(candles[0].get("close"))
    last_close = _to_float(candles[-1].get("close"))
    highs = [_to_float(candle.get("high")) for candle in recent if _to_float(candle.get("high")) > 0]
    lows = [_to_float(candle.get("low")) for candle in recent if _to_float(candle.get("low")) > 0]
    bullish_count = sum(1 for candle in recent if _to_float(candle.get("close")) >= _to_float(candle.get("open")))
    bearish_count = len(recent) - bullish_count
    change_rate = ((last_close - first_close) / first_close * 100) if first_close > 0 else 0.0
    currency = "USD" if market == "US" else "KRW"
    interval_label = _format_candle_interval(interval)

    reply_lines = [
        f"{label}의 최근 {len(candles)}개 {interval_label} 캔들 흐름입니다.",
        f"첫 종가 대비 마지막 종가는 {change_rate:+.2f}% 변화했습니다.",
    ]
    if last_close > 0:
        reply_lines.append(f"마지막 종가는 {_format_money(last_close, currency)}입니다.")
    if highs and lows:
        reply_lines.append(f"최근 {len(recent)}개 캔들의 고가/저가 범위는 {_format_money(max(highs), currency)} ~ {_format_money(min(lows), currency)}입니다.")
    reply_lines.append(f"최근 {len(recent)}개 기준 양봉 {bullish_count}개, 음봉 {bearish_count}개입니다.")
    reply_lines.append("캔들 흐름은 변동성 참고 자료이며, 단정적 예측으로 해석하면 안 됩니다.")

    return {
        "reply": "\n".join(reply_lines),
        "actions": [
            {
                "type": "navigate",
                "label": "상세보기",
                "to": _asset_route(symbol_data),
            }
        ],
        "data": {
            "source": "ASSET_CANDLES",
            "symbol": symbol,
            "display_name": display_name,
            "asset_type": asset_type,
            "market": market,
            "exchange": exchange,
            "broker_env": broker_env,
            "interval": interval,
            "candle_count": len(candles),
            "change_rate": change_rate,
            "last_close": last_close,
            "candles": recent,
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
    try:
        symbol_data = _resolve_symbol(auth_header, symbol_query)
    except SymbolDisambiguationError as error:
        return _build_symbol_choice_response(error.query, error.candidates)
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
    try:
        symbol_data = _resolve_symbol(auth_header, symbol_query)
    except SymbolDisambiguationError as error:
        return _build_symbol_choice_response(error.query, error.candidates)
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


def get_holdings(auth_header: str, message: str, exchange: str = None, broker_env: str = None, **kwargs) -> dict:
    exchange = exchange or _detect_exchange(message)
    env = broker_env or _detect_env(message)
    summary = get_portfolio_summary(auth_header, message, exchange=exchange, broker_env=env, **kwargs)
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


def _build_missing_exchange_result(symbol: str, side: str | None) -> dict:
    return {
        "reply": (
            f"{symbol} {side or ''} 매매 제안을 만들 거래소를 먼저 알려주세요.\n"
            "예: '토스', 'KIS', '코인원', '바이낸스'"
        ),
        "data": {
            "source": "CHATBOT_ORDER_PARSER",
            "reason": "missing_exchange",
            "symbol": symbol,
            "side": side,
        },
    }


def _build_unsupported_broker_env_result(exchange: str, broker_env: str, symbol: str) -> dict:
    env_label = "모의" if broker_env == "MOCK" else broker_env
    return {
        "reply": (
            f"{exchange}는 {env_label} 계좌 환경을 지원하지 않습니다.\n"
            "실거래 기준으로 진행하려면 '실거래'와 지정가를 함께 다시 입력해 주세요."
        ),
        "data": {
            "source": "CHATBOT_ORDER_PARSER",
            "reason": "unsupported_broker_env",
            "exchange": exchange,
            "broker_env": broker_env,
            "symbol": symbol,
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
    if broker_env == "MOCK" and not _exchange_has_mock_env(exchange):
        raise ValueError(f"{exchange}는 모의 계좌 환경을 지원하지 않습니다.")

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
    idempotency_key = str(values.get("idempotency_key") or "").strip()
    if idempotency_key:
        try:
            payload["id"] = str(uuid.UUID(idempotency_key))
        except (AttributeError, TypeError, ValueError) as error:
            raise ValueError("제안 생성 멱등성 키가 올바르지 않습니다.") from error
        existing = query_supabase(
            auth_header,
            "trade_proposals",
            "GET",
            params={"id": f"eq.{payload['id']}", "user_id": f"eq.{user_id}", "limit": 1},
        ) or []
        if existing:
            record = existing[0]
            existing_hash = str((record.get("raw_order_payload") or {}).get("order_hash") or "")
            requested_hash = str(raw_order_payload.get("order_hash") or "")
            if existing_hash != requested_hash:
                raise ValueError("같은 멱등성 키를 다른 매매 제안에 재사용할 수 없습니다.")
            return {
                "reply": f"{symbol} {side} 매매 제안이 이미 생성되어 있습니다. 승인 카드에서 실행 여부를 선택해 주세요.",
                "data": record,
            }
    try:
        created = query_supabase(auth_header, "trade_proposals", "POST", json_data=payload)
    except Exception as error:
        normalized_error = str(error).casefold()
        if not idempotency_key or not any(keyword in normalized_error for keyword in ("23505", "duplicate key", "unique constraint")):
            raise
        existing = query_supabase(
            auth_header,
            "trade_proposals",
            "GET",
            params={"id": f"eq.{payload['id']}", "user_id": f"eq.{user_id}", "limit": 1},
        ) or []
        if not existing:
            raise
        record = existing[0]
        if str((record.get("raw_order_payload") or {}).get("order_hash") or "") != str(raw_order_payload.get("order_hash") or ""):
            raise ValueError("같은 멱등성 키를 다른 매매 제안에 재사용할 수 없습니다.") from error
        return {
            "reply": f"{symbol} {side} 매매 제안이 이미 생성되어 있습니다. 승인 카드에서 실행 여부를 선택해 주세요.",
            "data": record,
        }
    record = (created[0] if isinstance(created, list) and created else created) or payload
    return {
        "reply": f"{symbol} {side} 매매 제안을 생성했습니다. 승인 카드에서 실행 여부를 선택해 주세요.",
        "data": {**payload, **(record if isinstance(record, dict) else {})},
    }


def create_trade_proposal_from_message(auth_header: str, message: str, intent: ParsedOrderIntent | None = None) -> dict:
    parsed = intent or parse_order_intent(message)
    if not parsed.is_order_request or not parsed.side or not parsed.symbol_query:
        return {
            "reply": "매매 제안을 만들 종목, 방향, 수량과 금액을 함께 알려주세요.",
            "data": {"source": "CHATBOT_ORDER_PARSER", "reason": "missing_order_intent"},
        }

    try:
        symbol_data = _resolve_symbol(auth_header, parsed.symbol_query)
    except SymbolDisambiguationError as error:
        return _build_symbol_choice_response(error.query, error.candidates)
    except (ValueError, RuntimeError) as error:
        return {
            "reply": f"'{parsed.symbol_query}' 종목을 찾지 못했습니다. 종목명 또는 코드가 올바른지 확인해 주세요.",
            "data": {
                "source": "CHATBOT_ORDER_PARSER",
                "reason": "symbol_not_found",
                "symbol_query": parsed.symbol_query,
                "error": str(error),
            },
        }
    symbol = str(symbol_data.get("symbol") or parsed.symbol_query).upper()
    display_name = str(symbol_data.get("display_name") or parsed.symbol_query or symbol).strip()
    asset_label = f"{display_name}({symbol})" if display_name and display_name.upper() != symbol else symbol
    asset_type = str(symbol_data.get("asset_type") or "STOCK").upper()
    market = str(symbol_data.get("market") or "").upper()
    explicit_exchange = _detect_exchange(message)
    exchange = explicit_exchange or _default_exchange_for_asset(asset_type, market, symbol)
    price = parsed.price
    if (
        not explicit_exchange
        and asset_type == "STOCK"
        and parsed.quantity is not None
        and price is None
        and not parsed.amount_krw
        and not parsed.sell_ratio
    ):
        return _build_missing_exchange_result(symbol, parsed.side)
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
        broker_env = "MOCK" if asset_type == "CRYPTO" and not explicit_exchange else "REAL"

    if asset_type == "CRYPTO":
        policy_error = _crypto_asset_policy_error(symbol, exchange)
        if policy_error:
            return {
                "reply": policy_error,
                "data": {
                    "source": "CHATBOT_ORDER_PARSER",
                    "reason": "crypto_asset_policy_blocked",
                    "exchange": exchange,
                    "symbol": symbol,
                },
            }

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

    if broker_env == "MOCK" and not _exchange_has_mock_env(exchange):
        return _build_unsupported_broker_env_result(exchange, broker_env, symbol)

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
            "reply": f"{asset_label} {'매수' if parsed.side == 'BUY' else '매도'} 제안을 만들 수량을 알려주세요.",
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

    if price is None and exchange in {"TOSS", "COINONE"}:
        return _build_missing_order_price_result(symbol, parsed.side, exchange, broker_env)

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

        try:
            user_id_val, _ = get_user_id_from_header(auth_header)
            _conversation_repository.set_pending_action(
                auth_header,
                user_id_val,
                "trade_proposal_retry",
                {
                    "message": message,
                    "exchange": exchange,
                    "symbol": symbol,
                    "broker_env": broker_env,
                },
                ttl_seconds=300
            )
        except Exception:
            pass

        return {
            "reply": f"매매 제안 사전검증을 완료하지 못했습니다. {action}\n(재시도를 원하시면 '재시도' 또는 '다시'라고 입력해 주세요.)",
            "data": {
                "source": "CHATBOT_ORDER_PARSER",
                "reason": "precheck_failed",
                "exchange": exchange,
                "symbol": symbol,
            },
        }

    blockers = _collect_precheck_blockers(precheck, broker_env)
    if blockers:
        try:
            user_id_val, _ = get_user_id_from_header(auth_header)
            _conversation_repository.set_pending_action(
                auth_header,
                user_id_val,
                "trade_proposal_retry",
                {
                    "message": message,
                    "exchange": exchange,
                    "symbol": symbol,
                    "broker_env": broker_env,
                },
                ttl_seconds=300
            )
        except Exception:
            pass

        return {
            "reply": f"매매 제안을 만들 수 없습니다. {' '.join(blockers)} 조건을 확인한 뒤 다시 시도해 주세요.\n(재시도를 원하시면 '재시도' 또는 '다시'라고 입력해 주세요.)",
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
    fallback_quantity = 0.0
    for item in summaries:
        if exchange and str(item.get("exchange") or "").upper() != exchange:
            continue
        for holding in item.get("holdings") or []:
            holding_symbol = str(holding.get("symbol") or holding.get("currency") or "").upper()
            if holding_symbol != symbol:
                continue
            quantity = _to_float(
                holding.get("qty")
                or holding.get("quantity")
                or holding.get("balance")
                or holding.get("available_qty")
            )
            if broker_env and str(item.get("env") or "").upper() != broker_env:
                fallback_quantity = fallback_quantity or quantity
                continue
            return quantity
    return fallback_quantity


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


def search_trade_history(auth_header: str, message: str, symbol: str = None, min_amount: float = None, limit: int = None, **kwargs) -> dict:
    user_id, _ = get_user_id_from_header(auth_header)
    min_amount = min_amount or _match_min_amount(message)
    symbol_query = symbol or _extract_symbol_query(message)
    symbol = ""
    if symbol_query:
        try:
            symbol = _resolve_symbol(auth_header, symbol_query).get("symbol") or ""
        except SymbolDisambiguationError as error:
            return _build_symbol_choice_response(error.query, error.candidates)
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
        date, time = _format_trade_datetime_parts(row.get("created_at"))
        rows.append({
            "date": date,
            "time": time,
            "exchange": row.get("exchange"),
            "symbol": row.get("symbol"),
            "asset_name": _format_trade_asset_name(row),
            "side": row.get("side"),
            "status": row.get("status"),
            "price": price,
            "quantity": volume,
            "amount": amount,
            "currency": row.get("currency") or ("USD" if row.get("market_country") == "US" else "KRW"),
            "source_type": "APP",
        })

    for row in broker_rows:
        row_symbol = row.get("symbol") or row.get("ticker")
        if symbol and str(row_symbol).upper() != str(symbol).upper():
            continue
        price = _to_float(row.get("average_filled_price") or row.get("price"))
        quantity = _to_float(row.get("filled_quantity") or row.get("quantity"))
        amount = _to_float(row.get("filled_amount") or row.get("order_amount") or row.get("executed_amount") or row.get("amount"))
        if min_amount and amount < min_amount:
            continue
        date, time = _format_trade_datetime_parts(row.get("ordered_at") or row.get("created_at"))
        rows.append({
            "date": date,
            "time": time,
            "exchange": row.get("exchange"),
            "symbol": row_symbol,
            "asset_name": _format_trade_asset_name({**row, "symbol": row_symbol}),
            "side": row.get("side"),
            "status": row.get("status"),
            "price": price,
            "quantity": quantity,
            "amount": amount,
            "currency": row.get("currency") or ("USD" if row.get("market_country") == "US" else "KRW"),
            "source_type": "BROKER",
        })

    history_limit = int(limit) if limit else 20
    rows = sorted(rows, key=lambda item: f"{item.get('date') or ''} {item.get('time') or ''}", reverse=True)[:history_limit]
    if not rows:
        return {"reply": "조건에 맞는 거래내역을 찾지 못했습니다.", "data": {"source": "TRADE_HISTORY", "items": []}}

    side_ko = {"BUY": "매수", "SELL": "매도"}
    status_ko = {
        "PENDING": "미체결",
        "APPROVED": "주문 완료",
        "ORDERED": "주문 완료",
        "OPEN": "미체결",
        "REJECTED": "구매실패",
        "CANCELED": "취소완료",
        "CANCELLED": "취소완료",
        "EXECUTED": "체결완료",
        "SUBMITTED": "주문제출",
        "FILLED": "체결완료",
        "FAILED": "구매실패",
        "PARTIALLY_FILLED": "미체결",
    }

    table_header = "| 일시 | 거래소 | 종목 | 구분 | 체결가 | 수량 | 정산금액 | 상태 |\n| :--- | :--- | :--- | :--- | :---: | :---: | :---: | :--- |"
    table_rows = []
    for row in rows:
        side_raw = str(row.get("side") or "").upper()
        side_text = side_ko.get(side_raw, side_raw or "-")
        status_raw = str(row.get("status") or "").upper()
        status_text = status_ko.get(status_raw, status_raw or "-")
        if status_raw in {"FAILED", "REJECTED", "EXPIRED"} and side_raw == "SELL":
            status_text = "판매실패"

        datetime_str = f"{row.get('date') or '-'} {row.get('time') or '-'}".strip()
        exchange_str = row.get('exchange') or '-'
        symbol_str = row.get('symbol') or '-'
        asset_str = row.get('asset_name') or symbol_str
        asset_cell = f"{asset_str} ({symbol_str})" if symbol_str != "-" and asset_str != symbol_str else asset_str
        currency = row.get("currency") or "KRW"
        price_str = _format_money(row.get('price'), currency)
        quantity_str = _format_quantity(row.get('quantity'))
        amount_str = _format_money(row.get('amount'), currency)

        table_rows.append(
            f"| {datetime_str} | {exchange_str} | {asset_cell} | {side_text} | {price_str} | {quantity_str} | {amount_str} | {status_text} |"
        )

    return {
        "reply": f"조건에 맞는 거래내역 {len(rows)}건입니다.\n\n" + table_header + "\n" + "\n".join(table_rows),
        "data": {"source": "TRADE_HISTORY", "items": rows},
    }


def list_open_orders(auth_header: str, message: str, symbol: str = None, exchange: str = None, broker_env: str = None, limit: int = None, **kwargs) -> dict:
    user_id, _ = get_user_id_from_header(auth_header)
    exchange = exchange or _detect_exchange(message)
    env = broker_env or _detect_env(message)
    symbol_query = symbol or _extract_symbol_query(message)
    symbol = ""
    if symbol_query:
        try:
            symbol = _resolve_symbol(auth_header, symbol_query).get("symbol") or ""
        except SymbolDisambiguationError as error:
            return _build_symbol_choice_response(error.query, error.candidates)
        except Exception:
            symbol = symbol_query.upper() if _is_likely_symbol_token(symbol_query) else ""

    order_limit = int(limit) if limit else _detect_limit(message, default=20, maximum=50)
    params = {
        "user_id": f"eq.{user_id}",
        "status": f"in.({','.join(OPEN_ORDER_STATUSES)})",
        "order": "created_at.desc",
        "limit": str(order_limit),
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

    status_ko = {
        "PENDING": "승인대기",
        "APPROVED": "승인됨",
        "REJECTED": "거절됨",
        "CANCELED": "취소됨",
        "EXECUTED": "체결완료",
        "SUBMITTED": "주문제출",
        "FILLED": "체결완료",
        "FAILED": "실패",
        "PARTIALLY_FILLED": "부분체결",
    }

    table_header = "| 날짜 | 거래소 | 종목 | 구분 | 수량 | 가격 | 주문금액 | 상태 |\n| :--- | :--- | :--- | :--- | :---: | :---: | :---: | :--- |"
    table_rows = []
    for item in items:
        env_text = f" ({item['broker_env']})" if item.get("broker_env") else ""
        exchange_str = f"{item.get('exchange') or '-'}{env_text}"
        side_text = "매도" if str(item.get("side") or "").upper() == "SELL" else "매수"
        qty_text = f"{_format_quantity(item.get('quantity'))}주"
        price_text = _format_money(item.get("price"))
        amount_text = _format_money(item.get("amount"))

        status_raw = str(item.get("status") or "").upper()
        status_text = status_ko.get(status_raw, status_raw or "-")

        table_rows.append(
            f"| {item['date']} | {exchange_str} | {item.get('asset_name') or item.get('symbol') or '-'} | {side_text} | {qty_text} | {price_text} | {amount_text} | {status_text} |"
        )

    return {
        "reply": f"미체결 주문 {len(items)}건입니다.\n\n" + table_header + "\n" + "\n".join(table_rows),
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
    symbol_query = _extract_symbol_query(message)
    if not symbol_query:
        return {
            "reply": "전망을 확인할 종목명이나 종목코드를 알려주세요.",
            "data": {"source": "ASSET_OUTLOOK", "reason": "missing_symbol"},
        }

    symbol_data = {}
    try:
        symbol_data = _resolve_symbol(auth_header, symbol_query)
    except SymbolDisambiguationError as error:
        return _build_symbol_choice_response(error.query, error.candidates)
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

    ml_result = build_single_asset_ml_outlook(auth_header, message, symbol_data)
    if ml_result:
        return ml_result

    if _is_general_price_outlook_request(message):
        return _build_price_based_outlook(auth_header, message, symbol, display_name)

    context_parts = [lookup_label, "최근 뉴스 공시 시세 전망 리스크"]
    if asset_type:
        context_parts.append(asset_type)
    if market:
        context_parts.append(market)

    user_id, _ = get_user_id_from_header(auth_header)
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


def _is_general_price_outlook_request(text: str) -> bool:
    value = str(text or "")
    if any(keyword in value for keyword in ["오를까", "내릴까", "살까", "팔까", "매수", "매도", "진입", "타이밍"]):
        return False
    return "전망" in value and any(keyword in value for keyword in ["어때", "어떨", "어떤", "알려줘"])


def _build_price_based_outlook(auth_header: str, message: str, symbol: str, display_name: str) -> dict:
    price_result = get_asset_price(auth_header, message)
    price_data = price_result.get("data") if isinstance(price_result.get("data"), dict) else {}
    if price_data.get("reason"):
        return price_result

    current_price = _to_float(price_data.get("current_price"))
    change_rate = _to_float(price_data.get("change_rate"))
    currency = str(price_data.get("currency") or "KRW").upper()
    label = f"{display_name}({symbol})" if display_name and display_name.upper() != symbol else symbol
    if current_price <= 0:
        return price_result

    reply = (
        f"{label}의 현재가는 {_format_money(current_price, currency)}이며, 오늘 등락률은 {change_rate:+.2f}%입니다.\n"
        f"{_price_outlook_sentence(change_rate)}\n"
        "손실 가능성도 항상 존재하니 분산 투자와 손절 기준 설정을 권장합니다."
    )
    return {
        "reply": reply,
        "actions": price_result.get("actions") or [],
        "data": {
            **price_data,
            "source": "ASSET_PRICE_OUTLOOK",
            "symbol": symbol,
            "display_name": display_name,
        },
    }


def _price_outlook_sentence(change_rate: float) -> str:
    if change_rate > 0:
        return "위 상승률은 단기적으로 긍정적 신호이나, 투자 결정 시 추가적인 재무 정보와 시장 상황을 함께 고려하시기 바랍니다."
    if change_rate < 0:
        return "위 하락률은 단기적으로 부담 신호일 수 있으나, 투자 결정 시 추가적인 재무 정보와 시장 상황을 함께 고려하시기 바랍니다."
    return "현재 등락률만으로 방향성을 단정하기는 어려우며, 투자 결정 시 추가적인 재무 정보와 시장 상황을 함께 고려하시기 바랍니다."


def get_crypto_market_context(auth_header: str, message: str, exchange: str = None, broker_env: str = None, interval: str = None, **kwargs) -> dict:
    symbol_query = _extract_symbol_query(message)
    if not symbol_query:
        return {
            "reply": "분석할 코인명이나 심볼을 알려주세요.\n예: BTC 코인 분석해줘, 리플 단기 흐름 알려줘",
            "data": {"source": "CRYPTO_MARKET_CONTEXT", "reason": "missing_symbol"},
        }

    try:
        symbol_data = _resolve_symbol(auth_header, symbol_query)
    except SymbolDisambiguationError as error:
        return _build_symbol_choice_response(error.query, error.candidates)
    except Exception:
        return {
            "reply": f"{symbol_query} 코인을 찾지 못했습니다.\n코인명이나 심볼을 다시 확인해 주세요.",
            "data": {"source": "CRYPTO_MARKET_CONTEXT", "query": symbol_query, "reason": "symbol_not_found"},
        }

    symbol = str(symbol_data.get("symbol") or symbol_query).upper()
    display_name = str(symbol_data.get("display_name") or symbol).strip()
    asset_type = str(symbol_data.get("asset_type") or "").upper()
    if asset_type and asset_type != "CRYPTO":
        return {
            "reply": f"{display_name}({symbol})은/는 코인으로 인식되지 않았습니다.\n주식 분석은 기존 종목 전망 도구를 사용해 주세요.",
            "data": {
                "source": "CRYPTO_MARKET_CONTEXT",
                "symbol": symbol,
                "display_name": display_name,
                "asset_type": asset_type,
                "reason": "not_crypto_asset",
            },
        }

    exchange = exchange or _detect_exchange(message) or "COINONE"
    broker_env = broker_env or _detect_env(message) or "REAL"
    interval = interval or _detect_candle_interval(message)
    if not interval and any(keyword in str(message or "") for keyword in ["분석", "단타", "흐름", "타이밍", "진입"]):
        interval = "1h"
    elif not interval:
        interval = "1h"
    elif interval == "1d" and any(keyword in str(message or "") for keyword in ["분석", "단타", "흐름", "타이밍", "진입"]):
        interval = "1h"
    label = f"{display_name}({symbol})" if display_name and display_name.upper() != symbol else symbol
    quote = _load_crypto_quote_context(auth_header, exchange, symbol, broker_env)
    orderbook = _load_crypto_orderbook_context(auth_header, exchange, symbol, broker_env)
    candles = _load_crypto_candle_context(auth_header, exchange, symbol, broker_env, interval)
    liquidity = _build_crypto_liquidity_context(orderbook, quote)
    holding = _load_crypto_holding_context(auth_header, exchange, broker_env, symbol, quote)
    premium = _load_crypto_premium_context(auth_header, exchange, symbol, quote)
    ml_result = build_single_asset_ml_outlook(auth_header, f"{symbol} 코인 살까", {**symbol_data, "asset_type": "CRYPTO", "exchange": exchange})
    ml_data = ml_result.get("data") if isinstance(ml_result, dict) else {}
    prediction = ml_data.get("prediction") if isinstance(ml_data, dict) and isinstance(ml_data.get("prediction"), dict) else {}

    reply_lines = [f"{label} 코인 통합 분석입니다."]
    if quote.get("current_price") is not None:
        reply_lines.append(
            f"- 현재가: {_format_money(quote.get('current_price'), quote.get('currency') or 'KRW')} / 등락률 {quote.get('change_rate', 0.0):+.2f}%"
        )
    else:
        reply_lines.append("- 현재가: 거래소 시세 조회 실패")

    if orderbook.get("best_ask") or orderbook.get("best_bid"):
        ask_price = _to_float((orderbook.get("best_ask") or {}).get("price"))
        bid_price = _to_float((orderbook.get("best_bid") or {}).get("price"))
        reply_lines.append(f"- 호가: 매도 {_format_money(ask_price, quote.get('currency') or 'KRW')} / 매수 {_format_money(bid_price, quote.get('currency') or 'KRW')}")
    else:
        reply_lines.append("- 호가: 조회된 최우선 호가가 없습니다.")

    if liquidity.get("spread_rate") is not None:
        reply_lines.append(
            f"- 유동성: 스프레드 {liquidity.get('spread_rate'):.2f}% / "
            f"예상 매수 슬리피지 {liquidity.get('estimated_buy_slippage_rate'):.2f}% / "
            f"예상 매도 슬리피지 {liquidity.get('estimated_sell_slippage_rate'):.2f}%"
        )
    else:
        reply_lines.append("- 유동성: 스프레드와 슬리피지를 계산할 호가가 부족합니다.")

    if candles.get("change_rate") is not None:
        reply_lines.append(
            f"- 최근 {candles.get('interval')} 캔들 {candles.get('count')}개 흐름: {candles.get('change_rate'):+.2f}%"
        )
    else:
        reply_lines.append(f"- 최근 {interval} 캔들 흐름: 조회 실패")

    if holding.get("found"):
        reply_lines.append(
            f"- 보유: {_format_quantity(holding.get('quantity'))} {symbol} / "
            f"평균단가 {_format_money(holding.get('avg_price'), quote.get('currency') or 'KRW')} / "
            f"수익률 {holding.get('profit_rate'):+.2f}% / "
            f"포트 비중 {holding.get('portfolio_weight_rate'):.2f}%"
        )
    elif _is_personal_crypto_context_request(message):
        reply_lines.append("- 보유: 해당 코인의 보유 수량을 찾지 못했습니다. API 키, 거래소, REAL/MOCK 환경을 확인해 주세요.")

    if premium.get("available"):
        reply_lines.append(
            f"- 김치프리미엄: {premium.get('premium_rate'):+.2f}% "
            f"(Coinone {_format_money(premium.get('coinone_price_krw'), 'KRW')} / "
            f"Binance 환산 {_format_money(premium.get('binance_price_krw'), 'KRW')})"
        )

    if prediction:
        reply_lines.append(
            "- ML 신호: "
            f"{_format_crypto_position(prediction.get('position'))} / "
            f"상승확률 {_format_percent_value(prediction.get('up_probability'))} / "
            f"위험확률 {_format_percent_value(prediction.get('risk_probability'))} / "
            f"모델 {prediction.get('model_version') or ml_data.get('model_version') or '-'}"
        )
    else:
        reply_lines.append("- ML 신호: 활성 예측값을 찾지 못했습니다.")

    reply_lines.append("- 시장 특성: 24시간 거래되는 가상자산이므로 장 마감 기준이 아니라 단기 변동성과 유동성을 함께 봐야 합니다.")
    reply_lines.append(f"- 거래소 주의: {_crypto_exchange_notice(exchange)}")
    reply_lines.append("주의: 이 분석은 매매 실행 신호가 아니라 참고용입니다. 실제 주문은 제안 생성과 사용자 승인 뒤에만 진행됩니다.")

    return {
        "reply": "\n".join(reply_lines),
        "actions": [
            {
                "type": "navigate",
                "label": "상세보기",
                "to": _asset_route({**symbol_data, "asset_type": "CRYPTO"}),
            }
        ],
        "data": {
            "source": "CRYPTO_MARKET_CONTEXT",
            "symbol": symbol,
            "display_name": display_name,
            "asset_type": "CRYPTO",
            "exchange": exchange,
            "broker_env": broker_env,
            "quote": quote,
            "orderbook": orderbook,
            "candles": candles,
            "liquidity": liquidity,
            "holding": holding,
            "premium": premium,
            "ml": ml_data if isinstance(ml_data, dict) else {},
        },
    }


def _load_crypto_quote_context(auth_header: str, exchange: str, symbol: str, broker_env: str) -> dict:
    try:
        payload = _get_internal(
            "/api/chart/quote",
            auth_header,
            params={"exchange": exchange, "symbol": symbol, "broker_env": broker_env},
        )
        data = payload.get("data") if isinstance(payload, dict) else {}
        current_price = _to_float(data.get("current_price") or data.get("price") or data.get("last") or data.get("close"), default=None)
        return {
            "current_price": current_price if current_price and current_price > 0 else None,
            "change_rate": _to_float(data.get("change_rate")),
            "currency": str(data.get("currency") or ("USD" if "BINANCE" in exchange else "KRW")).upper(),
            "raw": data,
        }
    except Exception:
        return {"current_price": None, "change_rate": 0.0, "currency": "USD" if "BINANCE" in exchange else "KRW", "reason": "quote_api_failed"}


def _load_crypto_orderbook_context(auth_header: str, exchange: str, symbol: str, broker_env: str) -> dict:
    try:
        payload = _get_internal(
            "/api/chart/orderbook",
            auth_header,
            params={"exchange": exchange, "symbol": symbol, "broker_env": broker_env},
        )
        data = payload.get("data") if isinstance(payload, dict) else {}
        asks = data.get("asks") if isinstance(data.get("asks"), list) else []
        bids = data.get("bids") if isinstance(data.get("bids"), list) else []
        return {
            "best_ask": asks[0] if asks else {},
            "best_bid": bids[0] if bids else {},
            "asks": asks[:5],
            "bids": bids[:5],
            "meta": payload.get("meta") if isinstance(payload.get("meta"), dict) else {},
        }
    except Exception:
        return {"best_ask": {}, "best_bid": {}, "asks": [], "bids": [], "reason": "orderbook_api_failed"}


def _load_crypto_candle_context(auth_header: str, exchange: str, symbol: str, broker_env: str, interval: str) -> dict:
    try:
        payload = _get_internal(
            "/api/chart/candles",
            auth_header,
            params={
                "exchange": exchange,
                "symbol": symbol,
                "interval": interval,
                "count": 24,
                "broker_env": broker_env,
            },
        )
        candles = [row for row in (payload.get("data") or []) if isinstance(row, dict)]
        first_close = _to_float(candles[0].get("close"), default=None) if candles else None
        last_close = _to_float(candles[-1].get("close"), default=None) if candles else None
        change_rate = None
        if first_close and first_close > 0 and last_close is not None:
            change_rate = ((last_close - first_close) / first_close) * 100
        return {
            "interval": interval,
            "count": len(candles),
            "change_rate": change_rate,
            "first_close": first_close,
            "last_close": last_close,
            "recent": candles[-5:],
        }
    except Exception:
        return {"interval": interval, "count": 0, "change_rate": None, "reason": "candles_api_failed"}


def _build_crypto_liquidity_context(orderbook: dict, quote: dict) -> dict:
    best_ask = orderbook.get("best_ask") if isinstance(orderbook.get("best_ask"), dict) else {}
    best_bid = orderbook.get("best_bid") if isinstance(orderbook.get("best_bid"), dict) else {}
    ask_price = _to_float(best_ask.get("price"), default=None)
    bid_price = _to_float(best_bid.get("price"), default=None)
    current_price = _to_float(quote.get("current_price"), default=None)
    ask_size = _to_float(best_ask.get("size") or best_ask.get("quantity"), default=0.0)
    bid_size = _to_float(best_bid.get("size") or best_bid.get("quantity"), default=0.0)
    if not ask_price or not bid_price or ask_price <= 0 or bid_price <= 0:
        return {
            "spread_rate": None,
            "estimated_buy_slippage_rate": None,
            "estimated_sell_slippage_rate": None,
            "liquidity_warning": "호가 데이터 부족",
        }

    mid_price = (ask_price + bid_price) / 2
    reference_price = current_price if current_price and current_price > 0 else mid_price
    spread_rate = ((ask_price - bid_price) / mid_price) * 100 if mid_price > 0 else None
    buy_slippage = max(((ask_price - reference_price) / reference_price) * 100, 0.0) if reference_price > 0 else None
    sell_slippage = max(((reference_price - bid_price) / reference_price) * 100, 0.0) if reference_price > 0 else None
    ask_depth = ask_price * ask_size
    bid_depth = bid_price * bid_size
    warning = ""
    if spread_rate is not None and spread_rate >= 1.0:
        warning = "스프레드가 넓어 지정가 분할 접근이 필요합니다."
    elif min(ask_depth, bid_depth) > 0 and min(ask_depth, bid_depth) < 1_000_000:
        warning = "최우선 호가 잔량이 얇아 체결 충격에 주의해야 합니다."

    return {
        "spread_rate": round(spread_rate, 2) if spread_rate is not None else None,
        "estimated_buy_slippage_rate": round(buy_slippage, 2) if buy_slippage is not None else None,
        "estimated_sell_slippage_rate": round(sell_slippage, 2) if sell_slippage is not None else None,
        "best_ask_depth": ask_depth,
        "best_bid_depth": bid_depth,
        "liquidity_warning": warning,
    }


def _load_crypto_holding_context(auth_header: str, exchange: str, broker_env: str, symbol: str, quote: dict) -> dict:
    try:
        summary = get_portfolio_summary(auth_header, f"{exchange} {broker_env} 보유 코인")
    except Exception:
        return {"found": False, "reason": "holding_lookup_failed"}

    summaries = (summary.get("data") or {}).get("summaries") or []
    current_price = _to_float(quote.get("current_price"), default=0.0)
    for account in summaries:
        if str(account.get("exchange") or "").upper() != exchange:
            continue
        if str(account.get("env") or "").upper() != broker_env:
            continue
        total_evaluation = _to_float(account.get("total_evaluation"))
        for holding in account.get("holdings") or []:
            holding_symbol = str(holding.get("symbol") or holding.get("currency") or "").upper()
            if holding_symbol != symbol:
                continue
            quantity = _to_float(
                holding.get("qty")
                or holding.get("quantity")
                or holding.get("balance")
                or holding.get("available")
            )
            avg_price = _to_float(
                holding.get("avg_price")
                or holding.get("average_price")
                or holding.get("average_buy_price")
            )
            evaluation = _to_float(
                holding.get("evaluation")
                or holding.get("valuation")
                or holding.get("market_value")
                or holding.get("amount")
            )
            if evaluation <= 0 and quantity > 0 and current_price > 0:
                evaluation = quantity * current_price
            profit_rate = _to_float(holding.get("profit_rate"), default=None)
            if profit_rate is None and avg_price > 0 and current_price > 0:
                profit_rate = ((current_price - avg_price) / avg_price) * 100
            portfolio_weight = (evaluation / total_evaluation * 100) if total_evaluation > 0 and evaluation > 0 else 0.0
            return {
                "found": True,
                "exchange": exchange,
                "broker_env": broker_env,
                "symbol": symbol,
                "quantity": quantity,
                "avg_price": avg_price,
                "evaluation": evaluation,
                "profit_rate": round(profit_rate or 0.0, 2),
                "portfolio_weight_rate": round(portfolio_weight, 2),
            }
    return {"found": False, "exchange": exchange, "broker_env": broker_env, "symbol": symbol}


def _load_crypto_premium_context(auth_header: str, exchange: str, symbol: str, quote: dict) -> dict:
    if str(exchange or "").upper() != "COINONE" or symbol not in {"BTC", "ETH"}:
        return {"available": False, "reason": "unsupported_premium_symbol"}
    coinone_price = _to_float(quote.get("current_price"), default=0.0)
    if coinone_price <= 0:
        return {"available": False, "reason": "missing_coinone_price"}
    try:
        binance_payload = _get_internal(
            "/api/chart/quote",
            auth_header,
            params={"exchange": "BINANCE", "symbol": symbol, "broker_env": "REAL"},
        )
        binance_data = binance_payload.get("data") if isinstance(binance_payload, dict) else {}
        binance_price = _to_float(binance_data.get("current_price") or binance_data.get("price"), default=0.0)
        rate_payload = _get_internal(
            "/api/market/exchange-rate",
            auth_header,
            params={"base": "USDT", "quote": "KRW", "broker_env": "REAL"},
        )
        rate_data = rate_payload.get("data") if isinstance(rate_payload, dict) else {}
        usdt_krw = _to_float(rate_data.get("rate"), default=0.0)
    except Exception:
        return {"available": False, "reason": "premium_lookup_failed"}

    binance_price_krw = binance_price * usdt_krw
    if binance_price_krw <= 0:
        return {"available": False, "reason": "missing_binance_reference"}
    premium_rate = ((coinone_price - binance_price_krw) / binance_price_krw) * 100
    return {
        "available": True,
        "symbol": symbol,
        "coinone_price_krw": coinone_price,
        "binance_price": binance_price,
        "usdt_krw": usdt_krw,
        "binance_price_krw": binance_price_krw,
        "premium_rate": round(premium_rate, 2),
    }


def _is_personal_crypto_context_request(message: str) -> bool:
    text = str(message or "")
    return any(keyword in text for keyword in ["내", "보유", "팔까", "매도", "수익", "손익", "비중"])


def _format_percent_value(value) -> str:
    number = _to_float(value, default=None)
    if number is None:
        return "-"
    if number <= 1:
        number *= 100
    return f"{number:.1f}%"


def _format_crypto_position(value) -> str:
    mapping = {
        "BUY": "매수 후보",
        "LONG": "매수 후보",
        "SELL": "매도 주의",
        "SHORT": "매도 주의",
        "HOLD": "보유",
        "WATCH": "관망",
        "NEUTRAL": "중립",
    }
    normalized = str(value or "").upper()
    return mapping.get(normalized, str(value or "알 수 없음"))


def _crypto_exchange_notice(exchange: str) -> str:
    normalized = str(exchange or "").upper()
    if normalized == "COINONE":
        return "Coinone는 KRW 현물 기준이며, 현재 프로젝트는 코인원 시장가 주문을 차단하고 지정가 제안 중심으로 처리합니다."
    if normalized == "BINANCE_UM_FUTURES":
        return "Binance USD-M 선물은 레버리지와 강제청산 위험이 있으며, 실거래는 별도 잠금 설정과 사용자 승인 없이는 진행하지 않습니다."
    if normalized == "BINANCE":
        return "Binance는 USDT/USD 기준 현물 시세이며, 원화 기준 손익은 환율 영향을 함께 받습니다."
    return "거래소별 주문 가능 방식, 수수료, 출금 제한을 별도로 확인해야 합니다."


_get_asset_outlook_base = get_asset_outlook


def get_asset_outlook(auth_header: str, message: str) -> dict:
    result = _get_asset_outlook_base(auth_header, message)
    data = result.get("data") if isinstance(result, dict) else {}
    if not isinstance(data, dict):
        return result

    symbol = str(data.get("symbol") or "").upper()
    asset_type = str(data.get("asset_type") or "").upper()
    market = str(data.get("market") or "").upper()
    if not symbol or not _is_stock_asset_for_status(asset_type, _default_exchange_for_asset(asset_type, market)):
        return result

    display_name = str(data.get("display_name") or symbol).strip()
    label = f"{display_name}({symbol})" if display_name and display_name.upper() != symbol else symbol
    trade_status = _get_stock_trade_status(auth_header, symbol, _detect_env(message) or "REAL")
    data["trade_status"] = trade_status
    if result.get("reply"):
        result["reply"] = _append_trade_status_to_reply(result["reply"], trade_status, label)
    return result


def get_recommendation_candidates(auth_header: str, message: str) -> dict:
    result = ChatbotRecommendationService().recommend(auth_header, message)
    data = result.get("data") if isinstance(result, dict) else {}
    if (
        isinstance(data, dict)
        and data.get("source") == "ML_ACTIVE_SIGNAL"
        and not (data.get("items") or [])
    ):
        reply = str(result.get("reply") or "").strip()
        fallback = (
            "대신 상승률/거래대금 순위나 관심종목 기준 뉴스·전망을 확인할 수 있습니다.\n"
            "예: '코인 상승률 순위 보여줘', '관심종목 전망 알려줘', '비트코인 최신 뉴스 보여줘'"
        )
        result["reply"] = f"{reply}\n\n{fallback}" if reply else fallback
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
    outlook_keywords = ["전망", "분석", "오를까", "어때", "괜찮아", "살까", "투자해도", "타이밍", "진입"]
    return any(keyword in str(text or "") for keyword in outlook_keywords)


def _is_asset_price_request(text: str) -> bool:
    value = str(text or "")
    if any(keyword in value for keyword in ["얼마 있어", "자산 얼마", "내 돈", "평가 자산", "평가자산"]):
        return False
    price_keywords = ["현재가", "시세", "얼마", "가격", "주가"]
    if not any(keyword in value for keyword in price_keywords):
        return False
    return bool(_extract_symbol_query(value))


def _is_asset_orderbook_request(text: str) -> bool:
    value = str(text or "")
    if not any(keyword in value for keyword in ["호가", "오더북", "orderbook", "ORDERBOOK"]):
        return False
    return bool(_extract_symbol_query(value))


def _is_asset_candle_request(text: str) -> bool:
    value = str(text or "")
    if not any(keyword in value for keyword in ["캔들", "차트 흐름", "봉 흐름", "일봉", "주봉", "월봉", "분봉", "시간봉"]):
        return False
    return bool(_extract_symbol_query(value))


def _is_crypto_market_context_request(text: str) -> bool:
    value = str(text or "")
    if not _extract_symbol_query(value):
        return False
    crypto_keywords = ["코인", "가상자산", "암호화폐", "크립토", "비트코인", "이더리움", "리플", "BTC", "ETH", "XRP"]
    analysis_keywords = ["분석", "전망", "단타", "진입", "타이밍", "흐름", "살까", "오를까", "내릴까", "리스크"]
    upper_value = value.upper()
    has_crypto_keyword = any(keyword.upper() in upper_value for keyword in crypto_keywords)
    has_analysis_keyword = any(keyword in value for keyword in analysis_keywords)
    return has_crypto_keyword and has_analysis_keyword


def _extract_multi_asset_symbol_queries(text: str) -> list[str]:
    value = str(text or "")
    matches = []
    for alias, symbol in SYMBOL_QUERY_ALIASES.items():
        alias_text = str(alias or "").strip()
        if not alias_text:
            continue
        start = value.find(alias_text)
        if start < 0:
            continue
        matches.append((start, len(alias_text), normalize_symbol_alias(symbol)))

    upper_value = value.upper()
    for symbol in sorted(_load_training_universe_symbols(), key=len, reverse=True):
        if len(symbol) < 2:
            continue
        start = upper_value.find(symbol)
        if start < 0:
            continue
        normalized = symbol[:-4] if symbol.endswith("USDT") and len(symbol) > 4 else symbol
        matches.append((start, len(symbol), normalized))

    matches.sort(key=lambda item: (item[0], -item[1]))
    selected = []
    occupied_until = -1
    seen = set()
    for start, length, symbol in matches:
        if start < occupied_until:
            continue
        occupied_until = start + length
        if symbol in seen:
            continue
        seen.add(symbol)
        selected.append(symbol)

    if len(selected) < 2:
        return []
    return selected


def _extract_multi_price_symbol_queries(text: str) -> list[str]:
    if not _is_asset_price_request(text):
        return []
    return _extract_multi_asset_symbol_queries(text)


def _has_concrete_symbol_query(text: str) -> bool:
    symbol_query = _extract_symbol_query(text)
    if not symbol_query:
        return False
    category_only_tokens = {
        "코인",
        "가상자산",
        "암호화폐",
        "크립토",
        "주식",
        "국내주식",
        "미국주식",
        "해외주식",
        "종목",
        "시장",
    }
    return symbol_query not in category_only_tokens


def _build_category_clarification_result(message: str) -> dict | None:
    text = str(message or "").strip()
    if not text or _has_concrete_symbol_query(text):
        return None

    price_keywords = ["현재가", "시세", "얼마", "가격", "주가"]
    crypto_category_keywords = ["코인", "가상자산", "암호화폐", "크립토"]
    if any(keyword in text for keyword in crypto_category_keywords) and any(keyword in text for keyword in price_keywords):
        return {
            "reply": "어떤 코인의 시세를 확인할까요?\n예: BTC 시세 알려줘, 비트코인 현재가 보여줘",
            "data": {
                "source": "CATEGORY_CLARIFICATION",
                "reason": "missing_crypto_symbol",
            },
        }

    if "공시" in text:
        return {
            "reply": "어떤 종목의 공시를 확인할까요?\n예: 삼성전자 공시 보여줘, AAPL 공시 알려줘",
            "data": {
                "source": "CATEGORY_CLARIFICATION",
                "reason": "missing_disclosure_symbol",
            },
        }

    if "뉴스" in text:
        return {
            "reply": "어떤 종목의 뉴스를 확인할까요?\n예: 삼성전자 뉴스 알려줘, 비트코인 최신 뉴스 보여줘",
            "data": {
                "source": "CATEGORY_CLARIFICATION",
                "reason": "missing_news_target",
            },
        }

    if _is_asset_outlook_request(text):
        if any(keyword in text for keyword in crypto_category_keywords):
            return {
                "reply": "어떤 코인의 전망을 확인할까요?\n예: BTC 전망 어때, 비트코인 분석해줘",
                "data": {
                    "source": "CATEGORY_CLARIFICATION",
                    "reason": "missing_crypto_symbol",
                },
            }
        return {
            "reply": "어떤 종목의 전망을 확인할까요?\n예: 삼성전자 전망 어때, AAPL 분석해줘",
            "data": {
                "source": "CATEGORY_CLARIFICATION",
                "reason": "missing_outlook_symbol",
            },
        }

    return None


def _run_multi_asset_price_tool(auth_header: str, message: str) -> dict | None:
    symbols = _extract_multi_price_symbol_queries(message)
    if len(symbols) < 2:
        return None

    results = []
    replies = []
    for symbol in symbols:
        enforce_tool_safety("get_asset_price", {"message": f"{symbol} 현재가 알려줘"})
        price_result = get_asset_price(auth_header, f"{symbol} 현재가 알려줘")
        data = price_result.get("data") if isinstance(price_result, dict) else {}
        results.append(data if isinstance(data, dict) else {})
        reply = str((price_result or {}).get("reply") or "").strip()
        if reply:
            replies.append(reply)

    return {
        "reply": "\n\n".join(replies),
        "data": {
            "source": "MULTI_ASSET_PRICE",
            "symbols": symbols,
            "results": results,
        },
    }


def _run_multi_asset_secondary_tool(auth_header: str, message: str) -> dict | None:
    text = str(message or "")
    symbols = _extract_multi_asset_symbol_queries(text)
    if len(symbols) < 2:
        return None

    if _is_asset_outlook_request(text):
        source = "MULTI_ASSET_OUTLOOK"
        suffix = "전망 알려줘"
        tool_name = "get_asset_outlook"
        tool_func = get_asset_outlook
    elif _is_web_search_request(text):
        source = "MULTI_ASSET_NEWS"
        suffix = "뉴스 알려줘"
        tool_name = "search_web"
        tool_func = search_web
    else:
        return None

    results = []
    replies = []
    for symbol in symbols:
        tool_message = f"{symbol} {suffix}"
        enforce_tool_safety(tool_name, {"message": tool_message})
        result = tool_func(auth_header, tool_message)
        data = result.get("data") if isinstance(result, dict) else {}
        results.append(data if isinstance(data, dict) else {})
        reply = str((result or {}).get("reply") or "").strip()
        if reply:
            replies.append(reply)

    return {
        "reply": "\n\n".join(replies),
        "data": {
            "source": source,
            "symbols": symbols,
            "results": results,
        },
    }


def _run_compound_info_tool(auth_header: str, message: str) -> dict | None:
    text = str(message or "")
    if not _is_asset_price_request(text):
        return None

    secondary_tool_name = None
    secondary_tool_func = None
    if _is_asset_outlook_request(text):
        secondary_tool_name = "get_asset_outlook"
        secondary_tool_func = get_asset_outlook
    elif _is_web_search_request(text):
        secondary_tool_name = "search_web"
        secondary_tool_func = search_web

    if not secondary_tool_func:
        return None

    enforce_tool_safety("get_asset_price", {"message": text})
    price_result = get_asset_price(auth_header, text)
    enforce_tool_safety(secondary_tool_name, {"message": text})
    secondary_result = secondary_tool_func(auth_header, text)
    price_data = price_result.get("data") or {}
    secondary_data = secondary_result.get("data") or {}
    price_source = price_data.get("source") or "ASSET_PRICE"
    secondary_source = secondary_data.get("source") or secondary_tool_name

    return {
        "reply": (
            f"현재가\n{price_result.get('reply') or ''}"
            f"\n\n추가 확인\n{secondary_result.get('reply') or ''}"
        ),
        "data": {
            "source": "COMPOUND_INFO",
            "components": [price_source, secondary_source],
            "price": price_data,
            "secondary": secondary_data,
        },
    }


def run_chatbot_tool(auth_header: str | None, message: str) -> dict | None:
    if not auth_header:
        return None

    text = str(message or "")
    order_form_redirect = build_order_form_redirect(text)
    if order_form_redirect:
        return order_form_redirect

    if _is_recommendation_reference_order(text):
        enforce_tool_safety("create_trade_proposal", {"message": text})
        return create_trade_proposal_from_recommendation_reference(auth_header, text)

    order_intent = parse_order_intent(text)
    if order_intent.is_order_request:
        enforce_tool_safety("create_trade_proposal", {"message": text})
        if _is_plain_order_requiring_confirmation(text, order_intent):
            symbol_data = _resolve_symbol(auth_header, order_intent.symbol_query)
            asset_type = str(symbol_data.get("asset_type") or "STOCK").upper()
            market = str(symbol_data.get("market") or "").upper()
            exchange = _default_exchange_for_asset(asset_type, market, str(symbol_data.get("symbol") or order_intent.symbol_query))
            broker_env = "MOCK"
            return _store_order_confirmation(
                auth_header,
                text,
                order_intent,
                symbol_data,
                exchange,
                broker_env,
            )
        return create_trade_proposal_from_message(auth_header, text, order_intent)

    clarification = _build_category_clarification_result(text)
    if clarification:
        return clarification

    multi_price_result = _run_multi_asset_price_tool(auth_header, text)
    if multi_price_result:
        return multi_price_result

    multi_secondary_result = _run_multi_asset_secondary_tool(auth_header, text)
    if multi_secondary_result:
        return multi_secondary_result

    compound_result = _run_compound_info_tool(auth_header, text)
    if compound_result:
        return compound_result

    def guarded(tool_name: str, tool_func):
        enforce_tool_safety(tool_name, {"message": text})
        return tool_func(auth_header, text)

    is_strategy_request = any(keyword in text for keyword in ["전략", "제안", "추천", "타이밍", "비중", "시나리오", "리밸런싱"])
    is_direct_read_request = any(keyword in text for keyword in ["보여줘", "조회", "알려줘", "뽑아줘", "요약", "뭐뭐 있어", "얼마"])
    if "투자성향" in text and any(keyword in text for keyword in ["재분석", "다시", "변경", "수정"]):
        return get_investment_profile_reanalysis_guide()
    if _is_asset_trade_status_request(text):
        return guarded("get_asset_trade_status", get_asset_trade_status)
    if _is_calendar_request(text):
        return guarded("get_market_calendar", get_market_calendar)
    if _is_krw_conversion_request(text) and _has_concrete_symbol_query(text):
        return guarded("get_asset_krw_conversion", get_asset_krw_conversion)
    if any(keyword in text for keyword in ["환율", "환전", "달러", "미달러", "엔화", "유로", "위안", "테더", "USDT"]):
        return guarded("get_exchange_rate", get_exchange_rate)
    if _is_asset_orderbook_request(text):
        return guarded("get_asset_orderbook", get_asset_orderbook)
    if _is_asset_candle_request(text):
        return guarded("get_asset_candles", get_asset_candles)
    if _is_crypto_market_context_request(text):
        return guarded("get_crypto_market_context", get_crypto_market_context)
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
    if is_strategy_request and any(keyword in text for keyword in ["관심 종목", "관심종목", "보유 종목", "보유종목"]):
        return None
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


def register_conditional_rule(
    auth_header: str,
    message: str,
    query: str,
    exchange: str = None,
    broker_env: str = None,
    target_profit_rate: float = None,
    stop_loss_rate: float = None,
    investment_amount: float = None,
    quantity: float = None,
    execution_mode: str = None,
    **kwargs,
) -> dict:
    """주식 혹은 코인에 대해 익절 또는 손절 조건감시 자동매도 규칙을 등록합니다.

    진입가(entry_price)를 알기 위해 현재 실시간 시세를 자동으로 조회하여 대입합니다.
    """
    symbol_data = _resolve_symbol(auth_header, query)
    symbol = str(symbol_data.get("symbol") or query).upper()
    ticker = str(symbol_data.get("ticker") or symbol).upper()
    asset_type = str(symbol_data.get("asset_type") or "STOCK").upper()
    market = str(symbol_data.get("market") or "").upper()
    display_name = str(symbol_data.get("name") or symbol)

    # 거래소 결정
    if not exchange:
        exchange = _default_exchange_for_asset(asset_type, market, symbol)
    exchange = exchange.upper()

    # 계좌 환경 결정 (TOSS, COINONE은 모의계좌가 없음)
    if not _exchange_has_mock_env(exchange):
        broker_env = "REAL"
    else:
        if not broker_env:
            broker_env = _detect_env(message) or "MOCK"
    broker_env = broker_env.upper()

    # 실행 모드 결정 (기본값 PROPOSAL - 안전지향)
    if not execution_mode:
        execution_mode = "AUTO" if any(keyword in message for keyword in ["자동", "자동매매"]) else "PROPOSAL"
    execution_mode = execution_mode.upper()

    # 현재가 조회 (진입 평단가로 설정)
    price_res = get_asset_price(auth_header, message, query=query, exchange=exchange, broker_env=broker_env)
    price_data = price_res.get("data") or {}
    entry_price = _to_float(price_data.get("current_price") or price_data.get("price"))

    if entry_price <= 0:
        return {
            "reply": f"'{display_name}'의 현재 시세를 조회할 수 없어 조건감시를 등록하지 못했습니다. 잠시 후 다시 시도해 주세요.",
            "data": {"error": "price_lookup_failed"},
        }

    # 투자 금액 및 수량 계산
    amount = _to_float(investment_amount)
    if amount <= 0:
        amount = 100000.0  # 기본값 10만원

    qty = _to_float(quantity)
    if qty <= 0:
        qty = amount / entry_price

    # 백분율 기재 변환
    tp_rate = _to_float(target_profit_rate)
    sl_rate = _to_float(stop_loss_rate)

    # Supabase RLS 정책 하에 사용자 ID를 가져옴
    from backend.services.auth_service import get_user_id_from_header
    try:
        user_id, _ = get_user_id_from_header(auth_header)
    except Exception:
        return {
            "reply": "인증 정보가 유효하지 않아 조건감시를 등록할 수 없습니다.",
            "data": {"error": "unauthorized"},
        }

    # DB 인서트
    row = {
        "user_id": user_id,
        "exchange": exchange,
        "broker_env": broker_env,
        "asset_type": asset_type,
        "symbol": symbol,
        "ticker": ticker,
        "entry_price": entry_price,
        "investment_amount": amount,
        "quantity": qty,
        "target_profit_rate": tp_rate if tp_rate > 0 else None,
        "stop_loss_rate": sl_rate if sl_rate > 0 else None,
        "execution_mode": execution_mode,
        "status": "RUNNING",
    }

    try:
        safe_query_supabase(
            auth_header,
            "auto_trading_rules",
            "POST",
            body=row,
        )
    except Exception as error:
        logger.exception("Failed to insert auto trading rule: %s", str(error))
        return {
            "reply": f"조건감시 데이터베이스 등록 중 오류가 발생했습니다: {str(error)[:100]}",
            "data": {"error": "db_insert_failed"},
        }

    # 유저 확인 텍스트 포맷
    cond_parts = []
    if tp_rate > 0:
        cond_parts.append(f"익절: +{tp_rate}% (목표가 약 {entry_price * (1 + tp_rate/100):,.0f}원)")
    if sl_rate > 0:
        cond_parts.append(f"손절: -{sl_rate}% (손절가 약 {entry_price * (1 - sl_rate/100):,.0f}원)")
    cond_text = ", ".join(cond_parts) if cond_parts else "설정된 조건 없음 (규칙이 등록되지 않았거나 비율이 0입니다)"

    mode_text = "즉시 자동 매도(AUTO)" if execution_mode == "AUTO" else "사용자 승인 대기 매도(PROPOSAL)"

    return {
        "reply": (
            f"✅ **조건감시 자동매도 규칙이 등록되었습니다.**\n\n"
            f"- **자산**: {display_name} ({symbol})\n"
            f"- **거래소 / 계좌**: {exchange} / {broker_env}\n"
            f"- **기준 현재가 (진입 평단가)**: {entry_price:,.0f}원\n"
            f"- **수량 / 투자금액**: {qty:,.4f}개 / {amount:,.0f}원\n"
            f"- **감시 조건**: {cond_text}\n"
            f"- **수행 동작**: {mode_text}\n\n"
            f"*백그라운드 워커가 10초 주기로 현재가를 감시하며 조건 도달 시 지정하신 동작을 수행합니다.*"
        ),
        "data": {
            "source": "REGISTER_CONDITIONAL_RULE",
            "rule": row,
        },
    }

