import os
import re
from datetime import datetime
from urllib.parse import urlencode

import requests

from backend.services.auth_service import get_user_id_from_header
from backend.services.supabase_client import query_supabase, safe_query_supabase
from backend.services.symbol_metadata import enrich_symbol
from backend.services.chatbot.web_fallback_search_service import ChatbotWebFallbackSearchService


API_BASE_URL = os.getenv("CHATBOT_INTERNAL_API_BASE_URL", "http://localhost:5050")


def list_available_tools() -> list[str]:
    return [
        "get_home_market_rankings",
        "get_portfolio_summary",
        "add_watchlist_item",
        "get_holdings",
        "search_trade_history",
        "get_exchange_rate",
        "search_web",
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


def _extract_symbol_query(text: str) -> str:
    cleaned = re.sub(r"(관심\s*종목|관심종목|설정해줘|추가해줘|등록해줘|보여줘|조회해줘|거래내역|거래\s*내역|주문내역|주문\s*내역|뉴스|공시)", " ", text)
    cleaned = re.sub(r"\d+(?:\.\d+)?\s*(만원|천원|원|만)", " ", cleaned)
    cleaned = re.sub(r"[일한이삼사오육칠팔구십백천만]+\s*(원|이상|이하|초과|미만|넘는|넘어|부터)?", " ", cleaned)
    cleaned = re.sub(r"(이상|이하|초과|미만|넘는|넘어|부터|전체|최근|상태|매수|매도|취소|체결|완료|실패)", " ", cleaned)
    cleaned = re.sub(r"[^0-9A-Za-z가-힣._-]+", " ", cleaned)
    candidates = [part.strip() for part in cleaned.split() if part.strip()]
    if not candidates:
        return ""
    return candidates[0]


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
                summaries.append({
                    "exchange": exchange,
                    "env": env,
                    "total_evaluation": _to_float(balance.get("total_evaluation") or balance.get("total_asset") or balance.get("total_balance")),
                    "available_cash": _to_float(balance.get("available_cash") or balance.get("cash") or balance.get("krw_balance")),
                    "exchange_rate": balance.get("exchange_rate"),
                    "holdings": balance.get("holdings") or [],
                })
            except Exception as exc:
                errors.append(f"{exchange} {env}: {str(exc)[:80]}")

    total_eval = sum(item["total_evaluation"] for item in summaries)
    total_cash = sum(item["available_cash"] for item in summaries)
    lines = [
        f"평가 자산 합계: {_format_money(total_eval)}",
        f"추정 현금/주문가능금액 합계: {_format_money(total_cash)}",
    ]
    for item in summaries:
        lines.append(
            f"- {item['exchange']} {item['env']}: 평가 {_format_money(item['total_evaluation'])}, 현금 {_format_money(item['available_cash'])}"
        )
    if errors and not summaries:
        lines.append("조회 가능한 계좌가 없습니다. 설정의 API 키와 거래소 계정 상태를 확인해 주세요.")

    return {
        "reply": "\n".join(lines),
        "data": {"summaries": summaries, "errors": errors[:5]},
    }


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
            symbol = symbol_query.upper()

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


def search_web(auth_header: str, message: str) -> dict:
    user_id, _ = get_user_id_from_header(auth_header)
    return ChatbotWebFallbackSearchService().search(
        auth_header=auth_header,
        user_id=user_id,
        query=message,
        limit=_detect_limit(message, default=5, maximum=5),
    )


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


def run_chatbot_tool(auth_header: str | None, message: str) -> dict | None:
    if not auth_header:
        return None

    text = str(message or "")
    is_strategy_request = any(keyword in text for keyword in ["전략", "제안", "추천", "타이밍", "비중", "시나리오", "리밸런싱"])
    is_direct_read_request = any(keyword in text for keyword in ["보여줘", "조회", "알려줘", "뽑아줘", "요약", "뭐뭐 있어", "얼마"])
    if "투자성향" in text and any(keyword in text for keyword in ["재분석", "다시", "변경", "수정"]):
        return get_investment_profile_reanalysis_guide()
    if any(keyword in text for keyword in ["환율", "환전", "달러", "미달러", "엔화", "유로", "위안", "테더", "USDT"]):
        return get_exchange_rate(auth_header, text)
    if any(keyword in text for keyword in ["순위", "랭킹", "상위", "필터"]):
        return get_home_market_rankings(auth_header, text)
    if any(keyword in text for keyword in ["관심종목", "관심 종목"]) and any(keyword in text for keyword in ["설정", "추가", "등록"]):
        return add_watchlist_item(auth_header, text)
    if any(keyword in text for keyword in ["거래내역", "거래 내역", "주문내역", "주문 내역"]):
        return search_trade_history(auth_header, text)
    if not is_strategy_request and any(keyword in text for keyword in ["보유", "내 주식", "뭐뭐 있어", "들고"]):
        return get_holdings(auth_header, text)
    if (not is_strategy_request or is_direct_read_request) and any(keyword in text for keyword in ["평가 자산", "평가자산", "내 돈", "얼마 있어", "자산 얼마"]):
        return get_portfolio_summary(auth_header, text)
    if _is_web_search_request(text):
        return search_web(auth_header, text)
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
