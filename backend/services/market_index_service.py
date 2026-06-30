import json
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any

from backend.services.kis_client import KISClient
from backend.services.toss_client import TossClient


KST = timezone(timedelta(hours=9))
logger = logging.getLogger(__name__)
MARKET_INDEX_OPEN_STALE_SECONDS = int(os.getenv("MARKET_INDEX_OPEN_STALE_SECONDS", "180"))
MARKET_INDEX_CLOSED_STALE_SECONDS = int(os.getenv("MARKET_INDEX_CLOSED_STALE_SECONDS", "1800"))
_MARKET_INDEX_CACHE: list[dict[str, Any]] = []

KIS_INDEX_DEFINITIONS = [
    {
        "symbol": "USDKRW",
        "label": "USD/KRW",
        "currency": "KRW",
        "market_country": "KR",
        "display_order": 10,
        "kind": "fx",
        "code": "FX@KRWKFTC",
        "env": "REAL",
    },
    {
        "symbol": "KOSPI",
        "label": "KOSPI",
        "currency": "KRW",
        "market_country": "KR",
        "display_order": 20,
        "kind": "domestic",
        "code": "0001",
        "env": "REAL",
    },
    {
        "symbol": "KOSDAQ",
        "label": "KOSDAQ",
        "currency": "KRW",
        "market_country": "KR",
        "display_order": 30,
        "kind": "domestic",
        "code": "1001",
        "env": "REAL",
    },
    {
        "symbol": "NASDAQ100_F",
        "label": "나스닥 100 선물",
        "currency": "USD",
        "market_country": "US",
        "display_order": 50,
        "kind": "overseas",
        "code": "NDX",
        "env": "REAL",
    },
    {
        "symbol": "SP500",
        "label": "S&P 500",
        "currency": "USD",
        "market_country": "US",
        "display_order": 60,
        "kind": "overseas",
        "code": "SPX",
        "env": "REAL",
    },
]
CONFIGURED_INDEX_SYMBOLS = [item["symbol"] for item in KIS_INDEX_DEFINITIONS]
CONFIGURED_INDEX_SYMBOL_SET = set(CONFIGURED_INDEX_SYMBOLS)
INDEX_DEFINITION_BY_SYMBOL = {item["symbol"]: item for item in KIS_INDEX_DEFINITIONS}


def _log_collection_stage(stage: str, symbol: str, payload: Any) -> None:
    if stage == "error":
        logger.warning(
            "[MarketIndex][%s] symbol=%s errorMessage=%s",
            stage,
            symbol,
            payload.get("errorMessage") if isinstance(payload, dict) else str(payload),
        )
        return

    if isinstance(payload, dict):
        logger.info(
            "[MarketIndex][%s] symbol=%s source=%s cacheStatus=%s tokenStatus=%s",
            stage,
            symbol,
            payload.get("source"),
            payload.get("cacheStatus"),
            payload.get("tokenStatus"),
        )
    else:
        logger.info("[MarketIndex][%s] symbol=%s", stage, symbol)


def set_market_index_cache(rows: list[dict[str, Any]]) -> None:
    global _MARKET_INDEX_CACHE
    _MARKET_INDEX_CACHE = list(rows or [])
    logger.info(
        "[MarketIndex][cache-save] memory count=%s symbols=%s",
        len(_MARKET_INDEX_CACHE),
        ",".join(str(row.get("symbol") or "") for row in _MARKET_INDEX_CACHE),
    )


def get_market_index_cache() -> list[dict[str, Any]]:
    rows = list(_MARKET_INDEX_CACHE)
    logger.info(
        "[MarketIndex][cache-load] memory count=%s symbols=%s",
        len(rows),
        ",".join(str(row.get("symbol") or "") for row in rows),
    )
    return rows


def _configured_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    latest_by_symbol: dict[str, dict[str, Any]] = {}
    for row in rows:
        symbol = str(row.get("symbol") or "").upper()
        if symbol not in CONFIGURED_INDEX_SYMBOL_SET:
            continue
        if symbol not in latest_by_symbol:
            latest_by_symbol[symbol] = row

    ordered_rows: list[dict[str, Any]] = []
    for symbol in CONFIGURED_INDEX_SYMBOLS:
        row = latest_by_symbol.get(symbol)
        if row:
            ordered_rows.append(row)
    return ordered_rows


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


def get_kis_market_index_client(env: str) -> KISClient | None:
    appkey = os.getenv("KIS_APPKEY", "") or os.getenv("KIS_APP_KEY", "")
    appsecret = os.getenv("KIS_APPSECRET", "") or os.getenv("KIS_APP_SECRET", "")
    if not appkey or not appsecret:
        return None

    return KISClient(
        appkey=appkey,
        appsecret=appsecret,
        cano=os.getenv("KIS_CANO", ""),
        acnt_prdt_cd=os.getenv("KIS_ACNT_PRDT_CD", "01"),
        env=env,
    )


def get_toss_market_index_client() -> TossClient | None:
    client_id = os.getenv("TOSS_API_KEY", "")
    client_secret = os.getenv("TOSS_SECRET_KEY", "")
    if not client_id or not client_secret:
        return None
    # 지수 수집의 1차 소스는 Toss로 두고, 자격 증명이 있을 때만 클라이언트를 만든다.
    # 이렇게 해두면 설정이 없는 환경에서는 곧바로 폴백 경로로 넘어갈 수 있다.
    return TossClient(client_id=client_id, client_secret=client_secret, env="REAL")


def _diagnostics(
    source: str,
    primary_status: str,
    fallback_status: str,
    cache_status: str,
    token_status: str,
    error_message: str | None,
) -> dict[str, Any]:
    return {
        "source": source,
        "primaryStatus": primary_status,
        "fallbackStatus": fallback_status,
        "cacheStatus": cache_status,
        "tokenStatus": token_status,
        "errorMessage": error_message,
    }


def _attach_diagnostics(row: dict[str, Any], diagnostics: dict[str, Any]) -> dict[str, Any]:
    raw_payload = row.get("raw_payload") if isinstance(row.get("raw_payload"), dict) else {}
    # 원본 payload 안에 진단 정보를 같이 넣어 후속 저장/응답에서 추적할 수 있게 한다.
    # 저장소와 API 응답 양쪽에서 같은 문제를 다시 추적할 수 있도록 하는 용도다.
    return {
        **row,
        "raw_payload": {
            **raw_payload,
            "diagnostics": diagnostics,
        },
    }


def _calculate_market_change(current_price: float, previous_close: float) -> tuple[float, float]:
    # 전일 종가 기준으로만 등락을 계산한다.
    if not previous_close:
        return 0.0, 0.0
    change_price = current_price - previous_close
    change_rate = (change_price / previous_close) * 100
    return change_price, change_rate


def _resolve_change_rate(
    current_price: float,
    previous_close: float,
    change_price: float | None = None,
    change_rate: float | None = None,
) -> tuple[float, float]:
    # 저장된 등락률이 있으면 우선 활용하고, 없을 때만 현재가/전일종가로 재계산한다.
    if change_rate not in (None, ""):
        try:
            resolved_rate = float(change_rate)
        except (TypeError, ValueError):
            resolved_rate = 0.0
        resolved_change_price = float(change_price or 0.0)
        if resolved_rate or previous_close:
            return resolved_change_price, resolved_rate

    resolved_previous_close = float(previous_close or 0.0)
    if resolved_previous_close:
        return _calculate_market_change(current_price, resolved_previous_close)

    return float(change_price or 0.0), 0.0


def _canonical_market_label(symbol: str, fallback_label: str | None = None) -> str:
    if str(symbol).upper() == "NASDAQ100_F":
        return "나스닥 100 선물"
    return fallback_label or str(symbol)


def _normalize_market_index_row(row: dict[str, Any], definition: dict[str, Any]) -> dict[str, Any]:
    # 새 컬럼(current_price/change_price 등)과 기존 컬럼(current_value/change_value 등)을 동시에 받아서 호환성을 유지한다.
    current_price = float(row.get("current_price") or row.get("current_value") or 0)
    previous_close = float(row.get("previous_close") or 0)
    change_price, change_rate = _resolve_change_rate(
        current_price=current_price,
        previous_close=previous_close,
        change_price=row.get("change_price") or row.get("change_value"),
        change_rate=row.get("change_rate") or row.get("change_percent"),
    )

    synced_at = row.get("synced_at") or row.get("as_of")
    raw_payload = row.get("raw_payload") if isinstance(row.get("raw_payload"), dict) else {}

    normalized = {
        "symbol": row.get("symbol") or definition["symbol"],
        "label": _canonical_market_label(row.get("symbol") or definition["symbol"], row.get("label") or definition["label"]),
        "source": row.get("source") or "UNKNOWN",
        "market_country": row.get("market_country") or definition["market_country"],
        "ticker": row.get("ticker") or definition.get("code") or definition["symbol"],
        "current_price": current_price,
        "previous_close": previous_close,
        "change_price": change_price,
        "change_rate": change_rate,
        "current_value": current_price,
        "change_value": change_price,
        "change_percent": change_rate,
        "currency": row.get("currency") or definition["currency"],
        "display_order": row.get("display_order") or definition["display_order"],
        "as_of": synced_at,
        "synced_at": synced_at,
        "raw_payload": raw_payload,
    }
    return normalized


def _log_market_index_row(row: dict[str, Any], diagnostics: dict[str, Any]) -> None:
    logger.debug(
        "[MarketIndex][row] symbol=%s source=%s currentPrice=%s previousClose=%s changePrice=%s changeRate=%s cacheStatus=%s tokenStatus=%s primaryStatus=%s fallbackStatus=%s errorMessage=%s",
        row.get("symbol"),
        diagnostics.get("source"),
        row.get("current_price"),
        row.get("previous_close"),
        row.get("change_price"),
        row.get("change_rate"),
        diagnostics.get("cacheStatus"),
        diagnostics.get("tokenStatus"),
        diagnostics.get("primaryStatus"),
        diagnostics.get("fallbackStatus"),
        diagnostics.get("errorMessage"),
    )


def _token_cache_info(client: Any | None) -> dict[str, Any]:
    if client is None or not hasattr(client, "get_token_cache_info"):
        return {"cacheStatus": "MISS", "tokenStatus": "REFRESHED", "errorMessage": None}
    return client.get_token_cache_info()


def collect_market_index_rows() -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    rows: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    clients_by_env: dict[str, KISClient | None] = {}
    target_date = datetime.now(KST).date().isoformat()
    logger.info(
        "[MarketIndex][collect-start] targetDate=%s symbolCount=%s symbols=%s",
        target_date,
        len(KIS_INDEX_DEFINITIONS),
        ",".join(CONFIGURED_INDEX_SYMBOLS),
    )
    # Toss -> DB 캐시 -> KIS 순서로 안전하게 시도한다.
    # 1차 수집에 실패해도 2차, 3차 경로가 이어서 동작하도록 설계한 구조다.
    toss_client = get_toss_market_index_client()

    for definition in KIS_INDEX_DEFINITIONS:
        symbol = definition["symbol"]
        primary_error: str | None = None
        fallback_errors: list[str] = []

        try:
            if toss_client is None:
                raise RuntimeError("Toss market index credentials are not configured.")

            row = _normalize_market_index_row(toss_client.get_market_index_snapshot(definition), definition)
            token_info = _token_cache_info(toss_client)
            diagnostics = _diagnostics(
                source=row.get("source") or "TOSS_OPEN_API",
                primary_status="Toss (Success)",
                fallback_status="NotUsed",
                cache_status=token_info.get("cacheStatus", "MISS"),
                token_status=token_info.get("tokenStatus", "REFRESHED"),
                error_message=None,
            )
            row = _attach_diagnostics(row, diagnostics)
            rows.append(row)
            _log_market_index_row(row, diagnostics)
            _log_collection_stage("summary", symbol, diagnostics)
            continue
        except Exception as error:
            primary_error = str(error)
            logger.warning(
                "[MarketIndex][collect-primary-failed] symbol=%s reason=%s",
                symbol,
                primary_error,
                exc_info=True,
            )

        if definition["kind"] == "fx":
            try:
                from backend.services.market_index_repository import MarketIndexRepository

                repository = MarketIndexRepository()
                cached_rows = repository.list_latest() if repository.is_configured else []
                cached_row = next(
                    (row for row in cached_rows if str(row.get("symbol") or "").upper() == definition["symbol"]),
                    None,
                )
                if cached_row:
                    row = _normalize_market_index_row({
                        "symbol": cached_row.get("symbol"),
                        "label": cached_row.get("label") or definition["label"],
                        "source": cached_row.get("source") or "supabase.market_indices_latest",
                        "market_country": cached_row.get("market_country") or definition["market_country"],
                        "ticker": cached_row.get("ticker") or "USD/KRW",
                        "current_price": cached_row.get("current_price") or cached_row.get("current_value"),
                        "previous_close": cached_row.get("previous_close"),
                        "change_price": cached_row.get("change_price") or cached_row.get("change_value"),
                        "change_rate": cached_row.get("change_rate") or cached_row.get("change_percent"),
                        "currency": cached_row.get("currency") or definition["currency"],
                        "display_order": cached_row.get("display_order") or definition["display_order"],
                        "as_of": cached_row.get("synced_at") or cached_row.get("as_of"),
                        "synced_at": cached_row.get("synced_at") or cached_row.get("as_of"),
                        "raw_payload": cached_row.get("raw_payload") or {},
                    }, definition)
                    diagnostics = _diagnostics(
                        source=row.get("source") or "supabase.market_indices_latest",
                        primary_status="Toss Exchange Rate (Failed)",
                        fallback_status="DB Cache (Success)",
                        cache_status="HIT",
                        token_status="REUSED",
                        error_message=primary_error,
                    )
                    row = _attach_diagnostics(row, diagnostics)
                    rows.append(row)
                    _log_market_index_row(row, diagnostics)
                    _log_collection_stage("summary", symbol, diagnostics)
                    continue
            except Exception as error:
                fallback_errors.append(f"DB Cache: {error}")
                logger.warning(
                    "[MarketIndex][collect-db-cache-failed] symbol=%s reason=%s",
                    symbol,
                    error,
                    exc_info=True,
                )

        if definition["kind"] == "fx":
            try:
                fallback_client = clients_by_env.get(definition.get("env", "REAL"))
                if fallback_client is None:
                    fallback_client = get_kis_market_index_client(definition.get("env", "REAL"))
                    clients_by_env[definition.get("env", "REAL")] = fallback_client
                if fallback_client is None:
                    raise RuntimeError("KIS market index credentials are not configured.")
                row = _normalize_market_index_row(fallback_client.get_market_index_snapshot(definition), definition)
                token_info = _token_cache_info(fallback_client)
                diagnostics = _diagnostics(
                    source=row.get("source") or "KIS_OPEN_API",
                    primary_status="Toss Exchange Rate (Failed)",
                    fallback_status="KIS (Success)",
                    cache_status=token_info.get("cacheStatus", "MISS"),
                    token_status=token_info.get("tokenStatus", "REFRESHED"),
                    error_message=primary_error,
                )
                row = _attach_diagnostics(row, diagnostics)
                rows.append(row)
                _log_market_index_row(row, diagnostics)
                _log_collection_stage("summary", symbol, diagnostics)
                continue
            except Exception as error:
                fallback_errors.append(f"KIS: {error}")
                logger.warning(
                    "[MarketIndex][collect-fx-kis-failed] symbol=%s reason=%s",
                    symbol,
                    error,
                    exc_info=True,
                )

        if definition["kind"] != "fx":
            try:
                env = definition.get("env", "REAL")
                if env not in clients_by_env:
                    clients_by_env[env] = get_kis_market_index_client(env)
                client = clients_by_env[env]
                if client is None:
                    raise RuntimeError("KIS market index credentials are not configured.")
                row = _normalize_market_index_row(client.get_market_index_snapshot(definition), definition)
                token_info = _token_cache_info(client)
                diagnostics = _diagnostics(
                    source=row.get("source") or "KIS_OPEN_API",
                    primary_status="Toss (Failed)",
                    fallback_status="KIS (Success)",
                    cache_status=token_info.get("cacheStatus", "MISS"),
                    token_status=token_info.get("tokenStatus", "REFRESHED"),
                    error_message=primary_error,
                )
                row = _attach_diagnostics(row, diagnostics)
                rows.append(row)
                _log_market_index_row(row, diagnostics)
                _log_collection_stage("summary", symbol, diagnostics)
            except Exception as error:
                fallback_errors.append(f"KIS: {error}")
                logger.warning(
                    "[MarketIndex][collect-kis-failed] symbol=%s reason=%s",
                    symbol,
                    error,
                    exc_info=True,
                )
                message = "; ".join([item for item in [primary_error, *fallback_errors] if item])
                errors.append({
                    "symbol": symbol,
                    "message": message,
                })
                diagnostics = _diagnostics(
                    source="NONE",
                    primary_status="Toss (Failed)",
                    fallback_status="KIS (Failed)",
                    cache_status="MISS",
                    token_status="REFRESHED",
                    error_message=message,
                )
                _log_collection_stage("error", symbol, diagnostics)

    logger.info(
        "[MarketIndex][collect-complete] targetDate=%s collected=%s errors=%s",
        target_date,
        len(rows),
        len(errors),
    )
    return rows, errors


def serialize_market_index_rows(rows: list[dict[str, Any]]) -> dict[str, Any]:
    rows = _configured_rows(rows)
    open_market = is_korean_market_open()
    stale_seconds = MARKET_INDEX_OPEN_STALE_SECONDS if open_market else MARKET_INDEX_CLOSED_STALE_SECONDS

    items: list[dict[str, Any]] = []
    diagnostics: list[dict[str, Any]] = []
    latest_updated_at: datetime | None = None

    for row in rows:
        as_of = parse_datetime(row.get("as_of"))
        if as_of and (latest_updated_at is None or as_of > latest_updated_at):
            latest_updated_at = as_of

        age_seconds = None
        if as_of:
            age_seconds = (datetime.now(timezone.utc) - as_of.astimezone(timezone.utc)).total_seconds()

        raw_payload = row.get("raw_payload") if isinstance(row.get("raw_payload"), dict) else {}
        row_diagnostics = raw_payload.get("diagnostics")
        if isinstance(row_diagnostics, dict):
            diagnostics.append({"symbol": row.get("symbol"), **row_diagnostics})

        current_price = float(row.get("current_price") or row.get("current_value") or 0)
        previous_close = float(row.get("previous_close") or 0)
        change_price, change_rate = _resolve_change_rate(
            current_price=current_price,
            previous_close=previous_close,
            change_price=row.get("change_price") or row.get("change_value"),
            change_rate=row.get("change_rate") or row.get("change_percent"),
        )
        synced_at = row.get("synced_at") or row.get("as_of")
        # 프론트와 기존 DB 스키마가 같이 읽을 수 있도록 신/구 필드를 함께 내려준다.
        # 이 단계에서 한번 맞춰두면 화면과 저장소 양쪽의 분기 코드가 줄어든다.
        items.append({
            "key": row.get("symbol"),
            "label": _canonical_market_label(row.get("symbol"), row.get("label") or row.get("symbol")),
            "value": current_price,
            "currentPrice": current_price,
            "current_price": current_price,
            "previousClose": previous_close,
            "previous_close": previous_close,
            "change": change_price,
            "changePrice": change_price,
            "change_price": change_price,
            "changePercent": change_rate,
            "changeRate": change_rate,
            "change_rate": change_rate,
            "direction": "up" if change_price > 0 else "down" if change_price < 0 else "flat",
            "updatedAt": synced_at,
            "syncedAt": synced_at,
            "currency": row.get("currency") or "USD",
            "source": row.get("source") or "UNKNOWN",
            "primaryStatus": row_diagnostics.get("primaryStatus") if isinstance(row_diagnostics, dict) else None,
            "fallbackStatus": row_diagnostics.get("fallbackStatus") if isinstance(row_diagnostics, dict) else None,
            "cacheStatus": row_diagnostics.get("cacheStatus") if isinstance(row_diagnostics, dict) else None,
            "tokenStatus": row_diagnostics.get("tokenStatus") if isinstance(row_diagnostics, dict) else None,
            "errorMessage": row_diagnostics.get("errorMessage") if isinstance(row_diagnostics, dict) else None,
            "stale": bool(age_seconds is None or age_seconds > stale_seconds),
        })

    return {
        "items": items,
        "fetchedAt": latest_updated_at.astimezone(timezone.utc).isoformat().replace("+00:00", "Z") if latest_updated_at else None,
        "source": "supabase.market_indices_latest",
        "diagnostics": diagnostics,
    }


def market_index_rows_need_refresh(rows: list[dict[str, Any]]) -> bool:
    rows = _configured_rows(rows)
    if not rows:
        return True

    row_symbols = {str(row.get("symbol") or "").upper() for row in rows}
    if row_symbols != CONFIGURED_INDEX_SYMBOL_SET:
        return True

    payload = serialize_market_index_rows(rows)
    items = payload.get("items") or []
    if not items:
        return True

    return any(bool(item.get("stale")) for item in items)
