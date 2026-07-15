import re
import os
import json
import math
import uuid
import time
import threading
import requests
from decimal import Decimal, InvalidOperation, ROUND_DOWN
from datetime import datetime, timezone
from flask import Blueprint, request, jsonify, current_app
from backend.services.supabase_client import query_supabase
from backend.services.auth_service import get_user_id_from_header
from backend.services.broker_order_history_service import (
    list_broker_order_history,
    sync_toss_broker_orders,
)
from backend.services.toss_client import TossClient
from backend.services.kis_client import KISClient
from backend.services.coinone_client import CoinoneClient
from backend.services.binance_client import BinanceClient, BinanceFuturesClient
from backend.services.crypto_cost_basis_service import get_transfer_source_amount
from backend.services.error_message_service import format_error_payload
from backend.services.exchange_client import MARKET_CLOSED_ORDER_MESSAGE, MarketClosedError, is_market_closed_order_error
from backend.services.order_entry_service import (
    issue_precheck_token,
    normalize_order_request,
    order_request_hash,
    resolve_futures_execution,
    resolve_service_leverage_limit,
)

# 단기 인메모리 시세 캐시 정의 (Rate limit 방지용)
CANDLE_CACHE = {}
ORDERBOOK_CACHE = {}
TRADES_CACHE = {}
PRICE_CHANGE_CACHE = {}
PRICE_CHANGE_CACHE_TTL = 10
CACHE_TTL_SECONDS = 10  # 기본값 10초 유효
LEVEL2_CACHE_TTL_SECONDS = 10
REAL_ORDER_LIMIT_KRW = 100000.0
USD_KRW_FALLBACK = 1500.0
SUPPORTED_TRADE_EXCHANGES = {"TOSS", "KIS", "COINONE", "BINANCE", "BINANCE_UM_FUTURES"}
CRYPTO_EXCHANGES = {"COINONE", "BINANCE", "BINANCE_UM_FUTURES"}
BINANCE_SPOT_QUOTE_ASSETS = (
    "FDUSD",
    "USDT",
    "BUSD",
    "USDC",
    "TUSD",
    "EUR",
    "TRY",
    "BRL",
    "GBP",
    "AUD",
    "BTC",
    "ETH",
    "BNB",
)

def determine_market_country(symbol: str) -> str:
    """
    주식 종목의 국내/해외 여부를 판별합니다.
    1. SYMBOL_METADATA 캐시를 먼저 조회합니다.
    2. 캐시에 없을 경우, 6~7자리 영숫자 조합(ETF/ETN 등 포함)은 국내 주식(KR), 그 외는 해외 주식(US)으로 판정합니다.
    """
    from backend.services.symbol_metadata import SYMBOL_METADATA
    symbol_upper = str(symbol).strip().upper()
    if symbol_upper in SYMBOL_METADATA:
        market = SYMBOL_METADATA[symbol_upper].get("market")
        if market in ("KR", "US"):
            return market

    if re.match(r"^[0-9A-Z]{6,7}$", symbol_upper):
        return "KR"
    return "US"


def get_cached_change_rate(exchange, symbol, broker_env, auth_header):
    is_us_stock = any(c.isalpha() for c in symbol)
    if is_us_stock and exchange == "KIS":
        exchange = "TOSS"

    cache_key = (exchange, symbol, broker_env)
    now = time.time()
    if cache_key in PRICE_CHANGE_CACHE:
        expire, val = PRICE_CHANGE_CACHE[cache_key]
        if now < expire:
            return val

    change_rate = 0.0
    try:
        if exchange == "TOSS" and auth_header:
            user_id, token = get_user_id_from_header(auth_header)
            crypto_helper = current_app.crypto
            records = _get_quote_records_with_env_fallback(auth_header, user_id, "TOSS", broker_env)
            if records:
                try:
                    access_key = crypto_helper.decrypt(records[0].get("encrypted_access_key"))
                    secret_key = crypto_helper.decrypt(records[0].get("encrypted_secret_key"))
                    toss_account_seq = records[0].get("toss_account_seq")
                    client = TossClient(client_id=access_key, client_secret=secret_key, account_seq=toss_account_seq, env=broker_env, user_id=user_id)
                    price_data = client.get_price(symbol)
                    change_rate = float(price_data.get("change_rate") or 0.0)
                except Exception as toss_err:
                    if not is_us_stock:
                        current_app.logger.warning(f"TOSS get_price failed in get_cached_change_rate: {str(toss_err)}. KIS 폴백을 시도합니다.")
                    else:
                        current_app.logger.warning(f"TOSS get_price failed for US stock in get_cached_change_rate: {str(toss_err)}.")
                    records = []

            # TOSS 키가 없거나 호출이 실패한 경우 KIS 키로 폴백하여 시세 및 전일대비율을 구합니다 (해외주식 제외).
            if not records and not is_us_stock:
                records_kis = _get_quote_records_with_env_fallback(auth_header, user_id, "KIS", broker_env)
                if records_kis:
                    access_key = crypto_helper.decrypt(records_kis[0].get("encrypted_access_key"))
                    secret_key = crypto_helper.decrypt(records_kis[0].get("encrypted_secret_key"))
                    cano = records_kis[0].get("kis_account_no")
                    acnt_prdt_cd = records_kis[0].get("kis_account_code", "01")
                    kis_env = records_kis[0].get("broker_env", "MOCK")
                    client = KISClient(appkey=access_key, appsecret=secret_key, cano=cano, acnt_prdt_cd=acnt_prdt_cd, env=kis_env, user_id=user_id)
                    price_data = client.get_price(symbol)
                    change_rate = float(price_data.get("change_rate") or 0.0)

        elif exchange == "KIS" and auth_header:
            if is_us_stock:
                raise Exception("해외 주식 시세는 KIS로 조회할 수 없습니다.")
            user_id, token = get_user_id_from_header(auth_header)
            crypto_helper = current_app.crypto
            records = _get_quote_records_with_env_fallback(auth_header, user_id, "KIS", broker_env)
            if records:
                try:
                    access_key = crypto_helper.decrypt(records[0].get("encrypted_access_key"))
                    secret_key = crypto_helper.decrypt(records[0].get("encrypted_secret_key"))
                    cano = records[0].get("kis_account_no")
                    acnt_prdt_cd = records[0].get("kis_account_code", "01")
                    kis_env = records[0].get("broker_env", "MOCK")
                    client = KISClient(appkey=access_key, appsecret=secret_key, cano=cano, acnt_prdt_cd=acnt_prdt_cd, env=kis_env, user_id=user_id)
                    price_data = client.get_price(symbol)
                    change_rate = float(price_data.get("change_rate") or 0.0)
                except Exception as kis_err:
                    current_app.logger.warning(f"KIS get_price failed in get_cached_change_rate: {str(kis_err)}. TOSS 폴백을 시도합니다.")
                    records = []

            # KIS 키가 없거나 호출이 실패한 경우 TOSS 키로 폴백하여 시세 및 전일대비율을 구합니다.
            if not records:
                records_toss = _get_quote_records_with_env_fallback(auth_header, user_id, "TOSS", broker_env)
                if records_toss:
                    access_key = crypto_helper.decrypt(records_toss[0].get("encrypted_access_key"))
                    secret_key = crypto_helper.decrypt(records_toss[0].get("encrypted_secret_key"))
                    toss_account_seq = records_toss[0].get("toss_account_seq")
                    client = TossClient(client_id=access_key, client_secret=secret_key, account_seq=toss_account_seq, env=broker_env, user_id=user_id)
                    price_data = client.get_price(symbol)
                    change_rate = float(price_data.get("change_rate") or 0.0)

        elif exchange == "COINONE":
            url = f"https://api.coinone.co.kr/public/v2/ticker/KRW/{symbol.upper()}"
            res = requests.get(url, timeout=3)
            if res.status_code == 200:
                data = res.json()
                if data.get("result") == "success":
                    if isinstance(data.get("data"), dict):
                        ticker = data["data"]
                    elif isinstance(data.get("tickers"), list) and data["tickers"]:
                        ticker = data["tickers"][0]
                    else:
                        ticker = {}

                    if ticker.get("change_rate_24h") is not None:
                        change_rate = float(ticker.get("change_rate_24h") or 0.0)
                    else:
                        last = float(ticker.get("last") or ticker.get("close") or ticker.get("close_24h") or 0.0)
                        yesterday_last = float(ticker.get("yesterday_last") or ticker.get("open_24h") or last)
                        if yesterday_last > 0:
                            change_rate = ((last - yesterday_last) / yesterday_last) * 100
        elif exchange in ("BINANCE", "BINANCE_UM_FUTURES"):
            url = "https://api.binance.com/api/v3/ticker/24hr"
            res = requests.get(url, params={"symbol": symbol.upper()}, timeout=3)
            if res.status_code == 200:
                data = res.json()
                change_rate = float(data.get("priceChangePercent") or 0.0)
    except Exception:
        pass

    PRICE_CHANGE_CACHE[cache_key] = (now + PRICE_CHANGE_CACHE_TTL, change_rate)
    return change_rate

from datetime import timedelta, timezone as datetime_timezone

def _is_us_regular_market_open(client=None) -> bool:
    """
    현재 미국 정규장(Regular Market)이 열려 있는지 여부를 판단합니다.
    """
    import datetime

    utc_now = datetime.datetime.now(datetime_timezone.utc)
    month = utc_now.month
    est_offset = timedelta(hours=-4) if 3 <= month <= 10 else timedelta(hours=-5)
    est_now = utc_now.astimezone(datetime_timezone(est_offset))

    if client and hasattr(client, "get_market_calendar"):
        try:
            calendar = client.get_market_calendar("US")
            today_data = calendar.get("today")
            if not today_data:
                return False

            integrated = today_data.get("integrated") or {}
            session = integrated.get("regularMarket")
            if session:
                start_str = session.get("startTime")
                end_str = session.get("endTime")
                if start_str and end_str:
                    try:
                        start_dt = datetime.datetime.fromisoformat(start_str)
                        end_dt = datetime.datetime.fromisoformat(end_str)
                        current_time = datetime.datetime.now(datetime.timezone.utc)
                        if start_dt <= current_time <= end_dt:
                            return True
                    except Exception:
                        pass
            return False
        except Exception:
            pass

    if est_now.weekday() >= 5:
        return False
    start_time = est_now.replace(hour=9, minute=30, second=0, microsecond=0)
    end_time = est_now.replace(hour=16, minute=0, second=0, microsecond=0)
    return start_time <= est_now <= end_time

def is_kr_market_open(client=None, symbol: str = None) -> bool:
    """
    현재 한국 장(KRX/NXT)이 열려 있는지 여부를 판단합니다.
    client와 symbol이 주어지면 토스 장 캘린더 API 및 종목 NXT 지원 여부를 참고하여 정교하게 판단합니다.
    """
    import datetime
    from flask import current_app

    kst_now = datetime.datetime.now(datetime_timezone(timedelta(hours=9)))

    # 1. client가 캘린더 조회를 지원하지 않는 경우 보조 공용 토스 클라이언트 빌드
    calendar_client = client
    if not calendar_client or not hasattr(calendar_client, "get_market_calendar"):
        user_id = getattr(client, "user_id", None)
        env = getattr(client, "env", "REAL")
        calendar_client = _get_shared_toss_client(user_id=user_id, broker_env=env)

    if calendar_client and hasattr(calendar_client, "get_market_calendar"):
        try:
            calendar = calendar_client.get_market_calendar("KR")
            today_data = calendar.get("today")
            if not today_data:
                return False

            integrated = today_data.get("integrated") or {}
            if not integrated:
                return False

            # 세션별 운영 시간 검증
            is_nxt_supported = False
            if symbol and hasattr(calendar_client, "get_stock_info"):
                try:
                    stock_info = calendar_client.get_stock_info(symbol)
                    if stock_info and isinstance(stock_info, dict):
                        korean_detail = stock_info.get("korean_market_detail") or {}
                        is_nxt_supported = bool(korean_detail.get("nxt_supported"))
                except Exception:
                    pass

            # 허용할 세션 수집 (정규장은 기본 허용, NXT 지원 시 프리/애프터 대체거래도 허용)
            allowed_sessions = ["regularMarket"]
            if is_nxt_supported:
                allowed_sessions.extend(["preMarket", "afterMarket"])

            # 현재 시각(KST)이 허용된 세션 범위 내에 있는지 비교
            for session_key in allowed_sessions:
                session = integrated.get(session_key)
                if not session:
                    continue

                start_str = session.get("startTime")
                end_str = session.get("endTime")
                if start_str and end_str:
                    try:
                        # ISO 8601 시간 파싱 (파이썬 3.7+ fromisoformat)
                        start_dt = datetime.datetime.fromisoformat(start_str)
                        end_dt = datetime.datetime.fromisoformat(end_str)

                        if start_dt <= kst_now <= end_dt:
                            return True
                    except Exception as ex:
                        current_app.logger.error(f"KST ISO 시간 파싱 실패: {start_str}, {end_str} -> {str(ex)}")
            return False
        except Exception as e:
            current_app.logger.warning(f"KR 캘린더 API 조회 실패, 하드코딩 룰로 폴백: {str(e)}")

    # 2. 폴백: 기본 정규장 및 대체거래소 시간 비교 (평일 08:00 ~ 20:00 KST)
    if kst_now.weekday() >= 5:
        return False
    start_time = kst_now.replace(hour=8, minute=0, second=0, microsecond=0)
    end_time = kst_now.replace(hour=20, minute=0, second=0, microsecond=0)
    return start_time <= kst_now <= end_time

def is_us_market_open(client=None) -> bool:
    """
    현재 미국 주식 시장이 열려 있는지 여부를 판단합니다. (미동부 통합 운영 04:00 ~ 20:00 EST/EDT)
    client가 주어지면 토스 장 캘린더 API를 참고하여 정교하게 판단합니다.
    """
    import datetime
    from flask import current_app

    utc_now = datetime.datetime.now(datetime_timezone.utc)
    month = utc_now.month
    est_offset = timedelta(hours=-4) if 3 <= month <= 10 else timedelta(hours=-5)
    est_now = utc_now.astimezone(datetime_timezone(est_offset))

    # 1. client가 주어진 경우 토스 캘린더 API 조회
    if client and hasattr(client, "get_market_calendar"):
        try:
            calendar = client.get_market_calendar("US")
            today_data = calendar.get("today")
            if not today_data:
                return False

            integrated = today_data.get("integrated") or {}
            if not integrated:
                return False

            # 미국은 모든 세션 허용 (프리/정규/애프터)
            allowed_sessions = ["regularMarket", "preMarket", "afterMarket"]
            current_time = datetime.datetime.now(datetime.timezone.utc)

            for session_key in allowed_sessions:
                session = integrated.get(session_key)
                if not session:
                    continue

                start_str = session.get("startTime")
                end_str = session.get("endTime")
                if start_str and end_str:
                    try:
                        start_dt = datetime.datetime.fromisoformat(start_str)
                        end_dt = datetime.datetime.fromisoformat(end_str)

                        if start_dt <= current_time <= end_dt:
                            return True
                    except Exception as ex:
                        current_app.logger.error(f"US ISO 시간 파싱 실패: {start_str}, {end_str} -> {str(ex)}")
            return False
        except Exception as e:
            current_app.logger.warning(f"US 캘린더 API 조회 실패, 하드코딩 룰로 폴백: {str(e)}")

    # 2. 폴백: 기본 통합 운영 시간 비교
    if est_now.weekday() >= 5:
        return False

    start_time = est_now.replace(hour=4, minute=0, second=0, microsecond=0)
    end_time = est_now.replace(hour=20, minute=0, second=0, microsecond=0)
    return start_time <= est_now <= end_time

def is_stock_order_market_open(exchange: str, symbol: str) -> bool:
    """
    주식 주문 실패가 거래소 원문 없이 fallback으로 빠질 때 장외 시간 여부를 보정합니다.
    """
    if str(exchange or "").upper() not in ("KIS", "TOSS"):
        return True
    return is_us_market_open() if determine_market_country(symbol) == "US" else is_kr_market_open()

def get_dynamic_ttl(exchange: str, symbol: str, interval: str) -> int:
    """
    거래소, 종목 심볼, 주기에 맞춰 최적화된 동적 캐시 TTL을 반환합니다.
    """
    exchange_upper = exchange.upper()

    if exchange_upper in ("COINONE", "BINANCE", "BINANCE_UM_FUTURES"):
        is_market_open = True  # 가상자산은 24시간 가동
    else:
        # 주식인 경우 숫자 심볼이면 한국 주식, 영문자가 섞여 있으면 미국 주식으로 판별
        is_us_stock = any(c.isalpha() for c in symbol)
        if is_us_stock:
            is_market_open = is_us_market_open()
        else:
            is_market_open = is_kr_market_open()

    # 장외 시간(주말/야간 등)에는 12시간(43200초) 캐시
    if not is_market_open:
        return 43200

    # 장내 시간
    interval_lower = interval.lower()
    if interval_lower == "1m":
        return 10  # 1분봉: 10초
    elif interval_lower in ("5m", "15m", "30m"):
        return 60  # 5분~30분봉: 1분
    elif interval_lower in ("60m", "1h"):
        return 300  # 1시간봉: 5분
    else:
        return 600  # 일봉 이상: 10분

# API 호출 동시성 제어를 위한 Lock 딕셔너리 (Request Collapsing용)
_api_locks = {}
_api_locks_lock = threading.Lock()

def _get_api_lock(cache_key):
    """
    동일한 캐시 키로 들어오는 동시 호출을 제어하기 위해 락을 반환합니다.
    """
    with _api_locks_lock:
        if cache_key not in _api_locks:
            _api_locks[cache_key] = threading.Lock()
        return _api_locks[cache_key]


trade_bp = Blueprint("trade", __name__)


def _load_user_exchange_record(auth_header: str, user_id: str, exchange: str, broker_env: str) -> tuple[dict, str, str]:
    """
    사용자 거래소 크리덴셜을 로드하고 복호화합니다.
    """
    crypto_helper = current_app.crypto
    credential_exchange = "BINANCE" if exchange == "BINANCE_UM_FUTURES" else exchange
    params = {
        "user_id": f"eq.{user_id}",
        "exchange": f"eq.{credential_exchange}",
        "broker_env": f"eq.{broker_env}"
    }
    records = query_supabase(auth_header, "user_api_keys", "GET", params=params)
    if not records:
        raise ValueError(f"등록된 {credential_exchange} ({broker_env}) API 키 정보가 없습니다.")

    record = records[0]
    access_key = crypto_helper.decrypt(record.get("encrypted_access_key"))
    secret_key = crypto_helper.decrypt(record.get("encrypted_secret_key"))
    return record, access_key, secret_key


def _format_user_value_error_message(error: ValueError) -> str:
    """
    내부 구현 용어가 사용자 화면에 노출되지 않도록 ValueError 메시지를 정규화합니다.
    """
    return str(error).replace("API 크리덴셜 정보", "API 키 정보").replace("API 크리덴셜", "API 키")


def _currency_for_quote(exchange: str, symbol: str) -> str:
    normalized_exchange = str(exchange or "").upper()
    if normalized_exchange in {"BINANCE", "BINANCE_UM_FUTURES"}:
        return "USDT"
    if normalized_exchange == "COINONE":
        return "KRW"
    return "USD" if determine_market_country(symbol) == "US" else "KRW"


def _query_user_exchange_records(auth_header: str, user_id: str, exchange: str, broker_env: str | None = None) -> list[dict]:
    """
    사용자 거래소 크리덴셜 레코드를 조회합니다.
    broker_env가 없으면 해당 거래소의 전체 레코드를 반환합니다.
    """
    params = {"user_id": f"eq.{user_id}"}
    if exchange:
        params["exchange"] = f"eq.{exchange}"
    if broker_env:
        params["broker_env"] = f"eq.{broker_env}"
    return query_supabase(auth_header, "user_api_keys", "GET", params=params)


def _get_quote_records_with_env_fallback(auth_header: str, user_id: str, exchange: str, broker_env: str) -> list[dict]:
    """
    시세/호가/체결 조회용으로 우선 요청 env를 찾고, 없으면 같은 거래소의 다른 env 레코드로 폴백합니다.
    """
    records = _query_user_exchange_records(auth_header, user_id, exchange, broker_env)
    if records:
        return records
    return _query_user_exchange_records(auth_header, user_id, exchange)


def _compact_degraded_reason(prefix: str, reasons: list[str]) -> str:
    """
    Mock 폴백 시 사용자에게 보여줄 축약 사유 문자열을 생성합니다.
    """
    filtered = [str(reason).strip() for reason in reasons if str(reason).strip()]
    if not filtered:
        return prefix
    return f"{prefix}:{' | '.join(filtered[:3])}"


def _get_cached_level2_snapshot(cache_store: dict, cache_key: tuple):
    """
    호가/체결 스냅샷 캐시를 반환합니다.
    """
    now = time.time()
    cached = cache_store.get(cache_key)
    if not cached:
        return None
    expire_time, payload = cached
    if now >= expire_time:
        return None
    return payload


def _set_cached_level2_snapshot(cache_store: dict, cache_key: tuple, data: dict | list):
    """
    호가/체결 스냅샷 캐시를 저장합니다.
    """
    cache_store[cache_key] = (time.time() + LEVEL2_CACHE_TTL_SECONDS, data)


def _build_exchange_client(exchange: str, broker_env: str, record: dict, access_key: str, secret_key: str):
    """
    거래소별 클라이언트를 생성합니다.
    """
    if exchange == "TOSS":
        return TossClient(
            client_id=access_key,
            client_secret=secret_key,
            account_seq=record.get("toss_account_seq"),
            env=broker_env,
            user_id=record.get("user_id"),
        )
    if exchange == "KIS":
        return KISClient(
            appkey=access_key,
            appsecret=secret_key,
            cano=record.get("kis_account_no"),
            acnt_prdt_cd=record.get("kis_account_code", "01"),
            env=broker_env,
            user_id=record.get("user_id"),
        )
    if exchange == "COINONE":
        return CoinoneClient(
            access_token=access_key,
            secret_key=secret_key,
        )
    if exchange == "BINANCE":
        return BinanceClient(
            api_key=access_key,
            secret_key=secret_key,
            env=broker_env,
        )
    if exchange == "BINANCE_UM_FUTURES":
        return BinanceFuturesClient(
            api_key=access_key,
            secret_key=secret_key,
            env=broker_env,
        )
    return None


def _get_shared_toss_client(user_id=None, broker_env="REAL"):
    """
    한투(KIS) 거래 시에도 캘린더 및 종목 정보를 얻기 위해 보조적으로 사용할 수 있는
    공용 또는 사용자 본인의 TossClient 인스턴스를 빌드하여 반환합니다.
    """
    import os
    from backend.services.toss_client import TossClient

    # 1. 만약 user_id가 주어지고, 해당 유저가 이미 본인의 토스 키를 등록해 둔 상태라면 그것을 우선 사용
    if user_id:
        try:
            from backend.services.supabase_client import query_supabase_as_service_role
            keys = query_supabase_as_service_role(
                "user_api_keys",
                "GET",
                params={
                    "user_id": f"eq.{user_id}",
                    "exchange": "eq.TOSS",
                    "broker_env": f"eq.{broker_env}"
                }
            )
            if keys and isinstance(keys, list) and len(keys) > 0:
                record = keys[0]
                from backend.utils.crypto_helper import CryptoHelper
                encryption_key = os.getenv("ENCRYPTION_KEY", "default-dev-encryption-key-32bytes!")
                crypto = CryptoHelper(encryption_key)
                access_key = crypto.decrypt(record["encrypted_access_key"])
                secret_key = crypto.decrypt(record["encrypted_secret_key"])
                return TossClient(
                    client_id=access_key,
                    client_secret=secret_key,
                    account_seq=record.get("toss_account_seq"),
                    env=broker_env,
                    user_id=user_id
                )
        except Exception:
            pass

    # 2. 백엔드 시스템 환경 변수에 토스 공용 키가 등록되어 있는 경우 사용
    shared_client_id = os.getenv("SHARED_TOSS_CLIENT_ID") or os.getenv("TOSS_CLIENT_ID") or os.getenv("TOSS_API_KEY")
    shared_client_secret = os.getenv("SHARED_TOSS_CLIENT_SECRET") or os.getenv("TOSS_CLIENT_SECRET") or os.getenv("TOSS_SECRET_KEY")
    shared_account_seq = os.getenv("SHARED_TOSS_ACCOUNT_SEQ") or os.getenv("TOSS_ACCOUNT_SEQ") or os.getenv("TOSS_ACCOUNT_SEQ")

    if shared_client_id and shared_client_secret:
        try:
            return TossClient(
                client_id=shared_client_id,
                client_secret=shared_client_secret,
                account_seq=shared_account_seq,
                env=broker_env,
                user_id="shared_system"
            )
        except Exception:
            pass

    # 3. 최후의 폴백: MOCK 환경의 공용 TossClient를 생성하여 평일 및 세션 시각 판단 데이터를 공용 가이드로 제공
    return TossClient(
        client_id="mock_id",
        client_secret="mock_secret",
        account_seq="123",
        env="MOCK",
        user_id="shared_mock"
    )


def _load_user_trade_proposal(auth_header: str, user_id: str, proposal_id: str) -> dict:
    """
    로그인 사용자의 주문 제안/이력 레코드를 단건 조회합니다.
    """
    records = query_supabase(
        auth_header,
        "trade_proposals",
        "GET",
        params={
            "id": f"eq.{proposal_id}",
            "user_id": f"eq.{user_id}",
            "limit": "1",
        },
    )
    if not records:
        raise ValueError("해당 거래내역을 찾을 수 없거나 접근 권한이 없습니다.")
    return records[0]


def _claim_trade_proposal_for_execution(
    auth_header: str,
    proposal_id: str,
) -> dict | None:
    """PENDING 매매 제안을 원자적으로 승인 선점합니다."""
    use_service_role = False
    try:
        from flask import current_app
        if current_app and (current_app.config.get("TESTING") or current_app.debug):
            use_service_role = True
    except Exception:
        pass

    if use_service_role:
        from datetime import datetime, timezone
        user_id, _ = get_user_id_from_header(auth_header)
        rows = query_supabase(
            auth_header,
            "trade_proposals",
            "PATCH",
            json_data={
                "status": "APPROVED",
                "approved_at": datetime.now(timezone.utc).isoformat(),
                "failure_reason": None,
            },
            params={
                "id": f"eq.{proposal_id}",
                "user_id": f"eq.{user_id}",
                "status": "eq.PENDING",
            },
            extra_headers={"Prefer": "return=representation"},
        ) or []
        return rows[0] if isinstance(rows, list) and rows else None

    rows = query_supabase(
        auth_header,
        "rpc/claim_trade_proposal_for_execution",
        "POST",
        json_data={"p_proposal_id": proposal_id},
    ) or []
    return rows[0] if isinstance(rows, list) and rows else None


def _reject_pending_trade_proposal(
    auth_header: str,
    user_id: str,
    proposal_id: str,
) -> dict | None:
    """PENDING 매매 제안만 조건부 갱신하여 승인과의 경쟁을 차단합니다."""
    rows = query_supabase(
        auth_header,
        "trade_proposals",
        "PATCH",
        json_data={"status": "REJECTED"},
        params={
            "id": f"eq.{proposal_id}",
            "user_id": f"eq.{user_id}",
            "status": "eq.PENDING",
        },
        extra_headers={"Prefer": "return=representation"},
    ) or []
    return rows[0] if isinstance(rows, list) and rows else None


def _resolve_proposal_order_data(auth_header: str, user_id: str, data: dict) -> tuple[dict, dict | None]:
    """승인 카드 실행 시 PENDING 제안의 주문 필드를 서버 기준으로 고정합니다."""
    proposal_id = str(data.get("proposal_id") or "").strip()
    if not proposal_id:
        return data, None

    proposal = _load_user_trade_proposal(auth_header, user_id, proposal_id)
    if str(proposal.get("status") or "").upper() != "PENDING":
        raise ValueError("대기 중인 매매 제안만 승인할 수 있습니다.")

    raw_order_payload = proposal.get("raw_order_payload") or {}
    futures_options = raw_order_payload.get("futures_options") or {}
    resolved = {
        **data,
        "exchange": proposal.get("exchange"),
        "symbol": proposal.get("symbol") or proposal.get("ticker"),
        "action": proposal.get("side"),
        "order_type": proposal.get("ord_type") or proposal.get("order_type"),
        "price": proposal.get("price"),
        "quantity": proposal.get("volume") or proposal.get("quantity"),
        "broker_env": proposal.get("broker_env") or "REAL",
        "intent": raw_order_payload.get("intent"),
        "position_side": futures_options.get("position_side"),
        "reduce_only": futures_options.get("reduce_only", False),
        "leverage": futures_options.get("leverage"),
        "margin_type": futures_options.get("margin_type"),
    }
    return resolved, proposal


def _patch_trade_proposal(auth_header: str, proposal_id: str, payload: dict):
    """
    trade_proposals 레코드를 부분 업데이트합니다.
    """
    return query_supabase(auth_header, f"trade_proposals?id=eq.{proposal_id}", "PATCH", json_data=payload)


def _patch_trade_proposal_returning(
    auth_header: str,
    user_id: str,
    proposal_id: str,
    payload: dict,
) -> dict:
    """주문 접수 결과를 갱신하고 정확히 1행이 반영됐는지 검증합니다."""
    rows = query_supabase(
        auth_header,
        "trade_proposals",
        "PATCH",
        json_data=payload,
        params={
            "id": f"eq.{proposal_id}",
            "user_id": f"eq.{user_id}",
        },
        extra_headers={"Prefer": "return=representation"},
    )
    if (
        not isinstance(rows, list)
        or len(rows) != 1
        or not isinstance(rows[0], dict)
    ):
        raise RuntimeError("주문 접수 결과는 정확히 1행 갱신되어야 합니다.")
    return rows[0]


def _normalize_manual_order_idempotency_key(value) -> str:
    """수동 주문 멱등성 키를 trade_proposals UUID 형식으로 정규화합니다."""
    try:
        return str(uuid.UUID(str(value or "").strip()))
    except (AttributeError, TypeError, ValueError):
        raise ValueError("수동 주문에는 유효한 UUID 형식의 idempotency_key가 필요합니다.")


def _is_unique_constraint_error(error: Exception) -> bool:
    normalized = str(error or "").casefold()
    return "23505" in normalized or "duplicate key" in normalized or "unique constraint" in normalized


def _manual_order_execution_fingerprint(order_data: dict) -> str:
    def normalize_number(value):
        if value in (None, ""):
            return None
        return float(value)

    def normalize_boolean(value):
        if isinstance(value, bool):
            return value
        return str(value or "").strip().casefold() in {"true", "1", "yes", "on"}

    normalized = {
        "exchange": str(order_data.get("exchange") or "").upper(),
        "symbol": str(order_data.get("symbol") or "").upper(),
        "action": str(order_data.get("action") or "").upper(),
        "order_type": str(order_data.get("order_type") or "").upper(),
        "broker_env": str(order_data.get("broker_env") or "REAL").upper(),
        "quantity": normalize_number(order_data.get("quantity")),
        "price": normalize_number(order_data.get("price")),
        "auto_exit": normalize_boolean(order_data.get("auto_exit")),
        "target_profit_rate": normalize_number(order_data.get("target_profit_rate")),
        "stop_loss_rate": normalize_number(order_data.get("stop_loss_rate")),
        "auto_exit_execution_mode": str(
            order_data.get("auto_exit_execution_mode") or "PROPOSAL"
        ).upper(),
        "auto_restart_on_partial_fill": normalize_boolean(
            order_data.get("auto_restart_on_partial_fill")
        ),
        "position_side": str(order_data.get("position_side") or "").upper(),
        "reduce_only": normalize_boolean(order_data.get("reduce_only")),
        "leverage": normalize_number(order_data.get("leverage")),
        "margin_type": str(order_data.get("margin_type") or "").upper(),
    }
    return json.dumps(normalized, sort_keys=True, separators=(",", ":"))


def _manual_order_matches_existing(existing: dict, order_data: dict) -> bool:
    stored_fingerprint = str(
        ((existing.get("raw_order_payload") or {}).get("idempotency_fingerprint"))
        or ""
    )
    if stored_fingerprint:
        return stored_fingerprint == _manual_order_execution_fingerprint(order_data)

    text_fields = {
        "exchange": str(order_data.get("exchange") or "").upper(),
        "symbol": str(order_data.get("symbol") or "").upper(),
        "side": str(order_data.get("action") or "").upper(),
        "ord_type": str(order_data.get("order_type") or "").upper(),
        "broker_env": str(order_data.get("broker_env") or "REAL").upper(),
    }
    for field, expected in text_fields.items():
        actual = existing.get(field)
        if field == "symbol":
            actual = actual or existing.get("ticker")
        if str(actual or "").upper() != expected:
            return False

    try:
        existing_volume = float(existing.get("volume"))
        requested_volume = float(order_data.get("quantity"))
        existing_price = float(existing.get("price"))
        requested_price = float(order_data.get("price"))
    except (TypeError, ValueError):
        return False
    return math.isclose(existing_volume, requested_volume) and math.isclose(
        existing_price,
        requested_price,
    )


def _merge_manual_order_payload_marker(proposal: dict | None, payload: dict | None) -> dict:
    """수동 주문 식별자는 주문 결과 저장 중에도 유지합니다."""
    merged = dict(payload or {})
    source_payload = (proposal or {}).get("raw_order_payload") or {}
    if not isinstance(source_payload, dict):
        return merged
    for key in ("source", "idempotency_fingerprint"):
        if source_payload.get(key) and not merged.get(key):
            merged[key] = source_payload[key]
    return merged


def _create_or_load_manual_order_proposal(
    auth_header: str,
    user_id: str,
    idempotency_key: str,
    order_data: dict,
) -> tuple[dict, bool]:
    """수동 주문을 외부 전송 전 PENDING 상태로 기록하고 재전송을 차단합니다."""
    normalized_key = _normalize_manual_order_idempotency_key(idempotency_key)
    exchange = str(order_data.get("exchange") or "").upper()
    symbol = str(order_data.get("symbol") or "").upper()
    asset_type = "STOCK" if exchange in {"TOSS", "KIS"} else "CRYPTO"
    payload = {
        "id": normalized_key,
        "user_id": user_id,
        "exchange": exchange,
        "asset_type": asset_type,
        "ticker": symbol,
        "symbol": symbol,
        "side": str(order_data.get("action") or "").upper(),
        "price": order_data.get("price"),
        "volume": order_data.get("quantity"),
        "ord_type": str(order_data.get("order_type") or "").upper(),
        "broker_env": str(order_data.get("broker_env") or "REAL").upper(),
        "status": "PENDING",
        "raw_order_payload": {
            "source": "MANUAL_ORDER",
            "idempotency_fingerprint": _manual_order_execution_fingerprint(order_data),
        },
    }
    try:
        rows = query_supabase(
            auth_header,
            "trade_proposals",
            "POST",
            json_data=payload,
            extra_headers={"Prefer": "return=representation"},
        )
        if not isinstance(rows, list) or len(rows) != 1 or not isinstance(rows[0], dict):
            raise RuntimeError("수동 주문 멱등성 레코드가 정확히 1행 생성되어야 합니다.")
        return rows[0], True
    except Exception as error:
        if not _is_unique_constraint_error(error):
            raise

    existing = _load_user_trade_proposal(auth_header, user_id, normalized_key)
    if not _manual_order_matches_existing(existing, order_data):
        raise ValueError("같은 idempotency_key를 다른 주문에 재사용할 수 없습니다.")
    return existing, False


def _insert_trade_proposal_with_schema_fallback(auth_header: str, payload: dict):
    """
    최신 스키마 컬럼이 아직 적용되지 않은 DB에서도 주문 이력 저장이 깨지지 않도록 폴백합니다.
    """
    try:
        return query_supabase(auth_header, "trade_proposals", "POST", json_data=payload)
    except Exception:
        legacy_payload = {
            key: value
            for key, value in payload.items()
            if key not in {
                "broker_env",
                "external_order_org_no",
                "raw_order_payload",
                "replaced_from_id",
                "modified_at",
                "canceled_at",
            }
        }
        return query_supabase(auth_header, "trade_proposals", "POST", json_data=legacy_payload)


def _recover_order_receipt(
    auth_header: str,
    user_id: str,
    proposal_data: dict,
) -> bool:
    """상세 주문 이력 저장 실패 시 상태와 외부 식별자만 최소 복구합니다."""
    recovery_fields = {
        "status",
        "failure_reason",
        "client_order_id",
        "external_order_org_no",
        "external_order_id",
    }
    recovery_update = {
        key: value
        for key, value in proposal_data.items()
        if key in recovery_fields
    }
    recovery_update["failure_reason"] = (
        proposal_data.get("failure_reason")
        or "주문 접수 후 상세 응답 저장에 실패해 기본 주문 식별자만 복구했습니다."
    )
    rows = query_supabase(
        auth_header,
        "trade_proposals",
        "PATCH",
        json_data=recovery_update,
        params={
            "id": f"eq.{proposal_data['id']}",
            "user_id": f"eq.{user_id}",
        },
        extra_headers={"Prefer": "return=representation"},
    ) or []
    if isinstance(rows, list) and rows:
        return True

    recovery_insert_fields = {
        "id",
        "user_id",
        "exchange",
        "asset_type",
        "ticker",
        "symbol",
        "broker_env",
        "side",
        "price",
        "volume",
        "ord_type",
        "market_country",
        "currency",
        *recovery_fields,
    }
    recovery_insert = {
        key: value
        for key, value in proposal_data.items()
        if key in recovery_insert_fields
    }
    recovery_insert["failure_reason"] = recovery_update["failure_reason"]
    _insert_trade_proposal_with_schema_fallback(auth_header, recovery_insert)
    return True


def _is_terminal_order_status(status: str | None) -> bool:
    """
    거래소 주문 상태가 더 이상 정정/취소될 수 없는 상태인지 판단합니다.
    """
    normalized = str(status or "").upper()
    return normalized in {
        "EXECUTED",
        "FILLED",
        "COMPLETED",
        "DONE",
        "CANCELED",
        "CANCELLED",
        "REJECTED",
        "FAILED",
        "EXPIRED",
        "EXPIRED_IN_MATCH",
        "REPLACED",
    }


def _infer_trade_status_from_order_status(order_status: dict | None, fallback: str = "EXECUTED") -> str:
    normalized = str((order_status or {}).get("status") or "").upper()
    if normalized in {"CANCELED", "CANCELLED"}:
        return "CANCELED"
    if normalized in {"REJECTED", "FAILED", "EXPIRED", "EXPIRED_IN_MATCH"}:
        return "FAILED"
    if normalized in {"EXECUTED", "FILLED", "COMPLETED", "DONE"}:
        return "EXECUTED"
    return fallback


def _as_float(value, default: float = 0.0) -> float:
    try:
        if value in (None, ""):
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _recalculate_change_rate(current_price, previous_close) -> float:
    current = _as_float(current_price)
    previous = _as_float(previous_close)
    if current <= 0 or previous <= 0:
        return 0.0
    return round(((current - previous) / previous) * 100.0, 4)


def _normalize_live_quote_prices(live_quote: dict | None) -> tuple[float | None, float | None, float | None]:
    quote = live_quote if isinstance(live_quote, dict) else {}
    current_price = _as_float(
        quote.get("current_price")
        or quote.get("price")
        or quote.get("last")
        or quote.get("close")
    )
    previous_close = _as_float(
        quote.get("previous_close")
        or quote.get("prev_close")
        or quote.get("prev_close_price")
        or quote.get("base_price")
        or quote.get("open_price")
    )
    price_change = _as_float(
        quote.get("price_change")
        or quote.get("change_price")
        or quote.get("priceChange")
    )
    price_change_sign = str(quote.get("price_change_sign") or quote.get("change_sign") or "").strip()
    if price_change_sign in {"4", "5"} and price_change > 0:
        price_change = -price_change
    elif price_change_sign in {"1", "2"} and price_change < 0:
        price_change = abs(price_change)
    if current_price > 0 and previous_close <= 0 and price_change:
        previous_close = current_price - price_change

    change_rate = None
    if current_price > 0 and previous_close > 0:
        change_rate = _recalculate_change_rate(current_price, previous_close)
    elif quote.get("change_rate") is not None:
        change_rate = _as_float(quote.get("change_rate"))

    return (
        current_price if current_price > 0 else None,
        previous_close if previous_close > 0 else None,
        change_rate,
    )


def _is_domestic_stock_symbol(symbol: str) -> bool:
    return bool(re.fullmatch(r"\d{6}", str(symbol or "").strip()))


def _load_kis_previous_close_for_quote(auth_header: str, user_id: str, symbol: str, broker_env: str) -> tuple[float | None, str | None]:
    """
    Toss 국내주식 시세에서 전일종가가 기준가처럼 내려오는 경우가 있어,
    국내 6자리 종목은 KIS의 명시적인 전일종가를 보조 기준으로 사용합니다.
    """
    env_candidates = []
    for env in (broker_env, "REAL", "MOCK"):
        normalized_env = str(env or "").upper()
        if normalized_env and normalized_env not in env_candidates:
            env_candidates.append(normalized_env)

    for env in env_candidates:
        try:
            record, access_key, secret_key = _load_user_exchange_record(auth_header, user_id, "KIS", env)
            client = _build_exchange_client("KIS", env, record, access_key, secret_key)
            quote = client.get_price(symbol) if client and hasattr(client, "get_price") else {}
            _, previous_close, _ = _normalize_live_quote_prices(quote)
            if previous_close:
                return previous_close, env
        except Exception as error:
            current_app.logger.debug(f"KIS 전일종가 보강 실패: symbol={symbol} env={env} reason={str(error)}")
    return None, None


def _pick_nested_value(data: dict | None, keys: tuple[str, ...]):
    if not isinstance(data, dict):
        return None
    for key in keys:
        if key in data and data.get(key) not in (None, ""):
            return data.get(key)
    for value in data.values():
        if isinstance(value, dict):
            nested = _pick_nested_value(value, keys)
            if nested not in (None, ""):
                return nested
    return None


def _normalize_coinone_synced_status(order_status: dict | None, requested_qty: float = 0.0) -> tuple[str, dict]:
    raw = (order_status or {}).get("raw") if isinstance(order_status, dict) else {}
    if not isinstance(raw, dict):
        raw = {}

    raw_status = (
        (order_status or {}).get("status")
        or _pick_nested_value(raw, ("status", "order_status", "state", "orderState"))
        or ""
    )
    normalized = str(raw_status).upper()
    filled_qty = _as_float(_pick_nested_value(raw, (
        "filled_qty",
        "filled_quantity",
        "executed_qty",
        "executed_quantity",
        "executed_volume",
        "filledAmount",
    )))
    remaining_qty = _as_float(_pick_nested_value(raw, (
        "remaining_qty",
        "remain_qty",
        "remaining_quantity",
        "left_qty",
        "unfilled_qty",
    )), default=-1.0)
    requested_qty = _as_float(requested_qty)

    detail = {
        "raw_status": raw_status,
        "filled_qty": filled_qty,
        "remaining_qty": remaining_qty,
    }

    if normalized in {"CANCELED", "CANCELLED", "CANCEL", "CANCEL_DONE"}:
        return "CANCELED", detail
    if normalized in {"REJECTED", "FAILED", "FAIL", "ERROR", "EXPIRED", "EXPIRE"}:
        return "FAILED", detail
    if normalized in {"EXECUTED", "FILLED", "COMPLETED", "COMPLETE", "DONE"}:
        return "EXECUTED", detail
    if requested_qty > 0 and filled_qty >= requested_qty:
        return "EXECUTED", detail
    if filled_qty > 0 and remaining_qty == 0:
        return "EXECUTED", detail
    if normalized in {"ORDERED", "RECEIVED", "ACCEPTED"}:
        return "APPROVED", detail
    return "PENDING", detail


def _patch_proposal_as_not_actionable(auth_header: str, proposal_id: str, order_status: dict | None, reason: str):
    status = _infer_trade_status_from_order_status(order_status, fallback="EXECUTED")
    payload = {
        "status": status,
        "failure_reason": reason,
        "raw_order_payload": {"last_order_status": order_status or {}, "action_restricted_reason": reason},
    }
    if status == "CANCELED":
        payload["canceled_at"] = datetime.utcnow().isoformat() + "Z"
    _patch_trade_proposal(auth_header, proposal_id, payload)
    return payload


def _is_toss_action_restricted_error(error: Exception, code: str) -> bool:
    text = str(error)
    return code in text or "가능수량이 부족" in text


def _is_already_canceled_order_error(error: Exception) -> bool:
    """
    거래소에서 이미 취소/종료된 주문을 다시 취소하려고 할 때 내려주는 문구를 감지합니다.
    """
    text = str(error or "").lower()
    keywords = (
        "이미 취소",
        "취소된 주문",
        "취소 완료",
        "취소완료",
        "cancelled",
        "canceled",
        "already cancel",
        "already cancelled",
        "already canceled",
        "cancel-restricted",
        "취소 가능수량이 부족",
        "취소 가능 수량이 부족",
        "취소할 수량이 없습니다",
        "취소 가능수량이 없습니다",
    )
    return any(keyword.lower() in text for keyword in keywords)


def _resolve_proposal_broker_env(proposal: dict, fallback: str | None = None) -> str:
    """
    거래내역 레코드에 저장된 broker_env를 우선 사용하고, 과거 레코드는 요청값 또는 REAL로 보정합니다.
    """
    return str(proposal.get("broker_env") or fallback or "REAL").upper()


def _mask_account_no(value: str | None) -> str:
    """
    화면 표시용 계좌번호를 마스킹합니다.
    """
    raw = str(value or "").strip()
    if not raw:
        return ""
    return f"****{raw[-4:]}" if len(raw) > 4 else raw


def _build_trade_account_meta(exchange: str, record: dict | None = None, broker_env: str | None = None) -> dict:
    """
    실제 API 키 레코드 기준으로 거래 계좌 표시 정보를 구성합니다.
    """
    exchange_upper = str(exchange or "").upper()
    env = str((record or {}).get("broker_env") or broker_env or "").upper()
    if exchange_upper == "KIS":
        masked_account = _mask_account_no((record or {}).get("kis_account_no"))
        label = f"KIS {'모의' if env == 'MOCK' else '실전'}"
        if masked_account:
            label = f"{label} {masked_account}"
        return {
            "exchange": exchange_upper,
            "env": env,
            "account_label": label,
            "account_key": f"{exchange_upper}:{env}:{masked_account or 'UNKNOWN'}",
            "record": record,
        }
    if exchange_upper == "TOSS":
        masked_account = _mask_account_no((record or {}).get("toss_account_no"))
        label = f"TOSS {'모의' if env == 'MOCK' else '실전'}"
        if masked_account:
            label = f"{label} {masked_account}"
        return {
            "exchange": exchange_upper,
            "env": env,
            "account_label": label,
            "account_key": f"{exchange_upper}:{env}:{(record or {}).get('toss_account_seq') or masked_account or 'UNKNOWN'}",
            "record": record,
        }
    return {
        "exchange": exchange_upper,
        "env": env or "REAL",
        "account_label": exchange_upper,
        "account_key": f"{exchange_upper}:{env or 'REAL'}",
        "record": record,
    }


def _get_trade_account_candidates(auth_header: str, user_id: str, exchange: str, row: dict) -> list[dict]:
    """
    거래내역 행에 명시된 계좌 환경을 우선 사용하고, 없을 때만 등록 계좌 목록을 확인합니다.
    """
    exchange_upper = str(exchange or row.get("exchange") or "").upper()
    broker_env = str(row.get("broker_env") or "").upper()
    if not exchange_upper:
        return []

    try:
        records = _query_user_exchange_records(
            auth_header,
            user_id,
            exchange_upper,
            None if exchange_upper == "KIS" else (broker_env or None),
        )
    except Exception:
        records = []

    if records:
        metas = [_build_trade_account_meta(exchange_upper, record) for record in records]
        if broker_env:
            metas.sort(key=lambda item: 0 if item.get("env") == broker_env else 1)
        return metas

    if broker_env:
        return [_build_trade_account_meta(exchange_upper, None, broker_env)]

    if exchange_upper in {"COINONE", "BINANCE"}:
        return [_build_trade_account_meta(exchange_upper, None, "REAL")]

    return []


TRANSFER_NON_DEDUCTIBLE_STATUSES = {"FAILED", "CANCELED", "CANCELLED", "REJECTED", "EXPIRED"}


def _get_transfer_deduction_amount(row: dict) -> float:
    status = str(row.get("status") or "").upper()
    if status in TRANSFER_NON_DEDUCTIBLE_STATUSES:
        return 0.0
    return get_transfer_source_amount(row)


def _build_crypto_transfer_deductions(rows: list[dict]) -> dict[str, float]:
    deductions = {}
    for row in rows or []:
        from_exchange = str(row.get("from_exchange") or "").upper()
        to_exchange = str(row.get("to_exchange") or "").upper()
        currency = str(row.get("currency") or "").strip().upper()
        amount = _get_transfer_deduction_amount(row)
        if "COINONE" not in from_exchange or "BINANCE" not in to_exchange or not currency or amount <= 0:
            continue
        deductions[currency] = deductions.get(currency, 0.0) + amount
    return deductions


def _apply_crypto_transfer_deductions(grouped: dict, deductions: dict[str, float]) -> None:
    if not deductions:
        return
    for item in grouped.values():
        exchange = str(item.get("raw_exchange") or item.get("exchange") or "").upper()
        symbol = str(item.get("symbol") or "").upper()
        if exchange != "COINONE" or symbol not in deductions:
            continue
        deduct_qty = min(_as_float(item.get("qty")), deductions[symbol])
        if deduct_qty <= 0:
            continue
        item["qty"] = _as_float(item.get("qty")) - deduct_qty
        item["transfer_deducted_qty"] = _as_float(item.get("transfer_deducted_qty")) + deduct_qty


def _extract_synced_account_meta(row: dict, candidates: list[dict]) -> dict | None:
    """
    이전 동기화에서 실제 확인된 계좌 정보가 있으면 그 계좌를 우선 사용합니다.
    """
    payload = row.get("raw_order_payload") or {}
    if not isinstance(payload, dict):
        return None
    sync_account = (
        (payload.get("sync_status_check") or {}).get("account")
        or (payload.get("post_order_status_check") or {}).get("account")
        or {}
    )
    synced_env = str(sync_account.get("broker_env") or "").upper()
    if not synced_env:
        return None
    for candidate in candidates:
        if candidate.get("env") == synced_env:
            return candidate
    return None


def _select_kis_account_meta_for_trade(row: dict, candidates: list[dict], clients: dict) -> dict | None:
    """
    KIS 체결 조회로 거래가 실제 발생한 계좌를 확인합니다.
    """
    if not candidates:
        return None

    synced_meta = _extract_synced_account_meta(row, candidates)
    if synced_meta:
        return synced_meta

    if len(candidates) == 1:
        return candidates[0]

    symbol = str(row.get("symbol") or row.get("ticker") or "").strip().upper()
    order_id = str(row.get("external_order_id") or "").strip()
    if not symbol or not order_id:
        return None

    for candidate in candidates:
        record = candidate.get("record")
        broker_env = candidate.get("env")
        account_key = candidate.get("account_key")
        if not record or not broker_env:
            continue
        try:
            if account_key not in clients:
                access_key = current_app.crypto.decrypt(record.get("encrypted_access_key"))
                secret_key = current_app.crypto.decrypt(record.get("encrypted_secret_key"))
                clients[account_key] = _build_exchange_client("KIS", broker_env, record, access_key, secret_key)
            status = clients[account_key].get_order_execution_status(order_id, symbol=symbol, lookback_days=30)
            if status.get("status") in {"EXECUTED", "PARTIALLY_FILLED", "CANCELED"} or float(status.get("executed_qty") or 0) > 0:
                return candidate
        except Exception:
            continue

    return None


def _lookup_trade_symbol_name(symbol: str, fallback: str = "") -> str:
    """
    기존 종목 검색과 같은 기준으로 종목코드의 표시명을 찾습니다.
    """
    symbol = str(symbol or "").strip().upper()
    if not symbol:
        return fallback or symbol

    try:
        from backend.services.symbol_metadata import SYMBOL_METADATA
        meta = SYMBOL_METADATA.get(symbol)
        if meta and meta.get("display_name"):
            return meta.get("display_name")
    except Exception:
        pass

    try:
        from backend.services.market_repository import MarketRepository
        repo = MarketRepository()
        for row in repo.search_stock_master(symbol, limit=5):
            if str(row.get("symbol") or "").upper() == symbol:
                return re.sub(r"^KR\d{10}", "", row.get("name") or "").strip() or fallback or symbol
    except Exception:
        pass

    return fallback or symbol


def _resolve_order_org_no(proposal: dict) -> str:
    """
    KIS 정정/취소에 필요한 원주문 조직번호를 조회합니다.
    """
    return str(proposal.get("external_order_org_no") or proposal.get("client_order_id") or "")


def _mark_kis_order_closed(auth_header: str, proposal_id: str, detail: dict | None = None) -> dict:
    """
    KIS 정정/취소 가능 잔량이 없으면 DB 거래내역을 종료 상태로 동기화합니다.
    """
    patch_payload = {
        "status": "EXECUTED",
        "failure_reason": None,
    }
    if detail:
        patch_payload["raw_order_payload"] = detail
    _patch_trade_proposal(auth_header, proposal_id, patch_payload)
    return patch_payload


def _ensure_kis_order_modifiable(auth_header: str, proposal_id: str, proposal: dict, client) -> dict:
    """
    KIS 실제 미체결 잔량을 확인하고 정정/취소 불가 주문이면 차단합니다.
    """
    try:
        current_order = client.get_modifiable_order(
            proposal.get("external_order_id"),
            order_org_no=_resolve_order_org_no(proposal),
        )
    except Exception as exc:
        if getattr(client, "env", "") == "MOCK" and "해당업무가 제공되지 않습니다" in str(exc):
            return {
                "order_id": proposal.get("external_order_id"),
                "order_org_no": _resolve_order_org_no(proposal),
                "symbol": proposal.get("symbol") or proposal.get("ticker"),
                "remaining_qty": float(proposal.get("volume") or 0),
                "is_modifiable": True,
                "raw": {
                    "precheck_skipped": True,
                    "reason": "KIS 모의투자 정정/취소 가능 주문 조회 API 미지원",
                },
            }
        raise
    if current_order.get("is_modifiable"):
        return current_order

    _mark_kis_order_closed(auth_header, proposal_id, current_order)
    raise ValueError("이미 체결되어 정정/취소할 수 없습니다.")

def _get_holding_info_from_balance(client, symbol: str) -> dict | None:
    """
    잔고 API에서 특정 종목의 현재 보유 수량과 평균단가를 조회합니다.
    """
    try:
        balance = client.get_balance() or {}
    except Exception:
        return None

    target_symbol = str(symbol or "").strip().upper()
    for item in balance.get("holdings", []) or []:
        holding_symbol = str(item.get("symbol") or "").strip().upper()
        if holding_symbol == target_symbol:
            return {
                "qty": float(item.get("qty") or 0.0),
                "avg_price": float(item.get("avg_price") or 0.0)
            }
    return {"qty": 0.0, "avg_price": 0.0}


def _get_holding_qty_from_balance(client, symbol: str) -> float | None:
    """
    잔고 API에서 특정 종목의 현재 보유 수량을 조회합니다.
    """
    try:
        balance = client.get_balance() or {}
    except Exception:
        return None

    target_symbol = str(symbol or "").strip().upper()
    for item in balance.get("holdings", []) or []:
        holding_symbol = str(item.get("symbol") or "").strip().upper()
        if holding_symbol != target_symbol:
            continue
        try:
            return float(item.get("qty") or 0)
        except (TypeError, ValueError):
            return None
    return 0.0


def _resolve_kis_submission_status(client, symbol: str, side: str, qty: float, previous_holding_qty, order_res: dict) -> tuple[str, dict]:
    """
    KIS 주문 접수 직후 실제 미체결 목록과 잔고를 확인해 DB 저장 상태를 보정합니다.
    """
    order_id = order_res.get("order_id")
    order_org_no = order_res.get("order_org_no")
    detail = {"order": order_res}

    try:
        current_order = client.get_modifiable_order(order_id, order_org_no=order_org_no)
        detail["modifiable_order"] = current_order
        if current_order.get("is_modifiable"):
            return "APPROVED", detail
    except Exception as exc:
        detail["modifiable_lookup_error"] = str(exc)[:300]

    try:
        execution_status = client.get_order_execution_status(order_id, symbol=symbol)
        detail["execution_status"] = execution_status
        if execution_status.get("status") == "CANCELED":
            return "CANCELED", detail
        if execution_status.get("status") == "EXECUTED" or execution_status.get("executed_qty", 0) >= float(qty) > 0:
            return "EXECUTED", detail
    except Exception as exc:
        detail["execution_lookup_error"] = str(exc)[:300]

    current_holding_qty = _get_holding_qty_from_balance(client, symbol)
    detail["current_holding_qty"] = current_holding_qty

    try:
        previous_qty = float(previous_holding_qty or 0)
    except (TypeError, ValueError):
        previous_qty = 0.0

    side_upper = str(side or "").upper()
    if current_holding_qty is not None:
        if side_upper == "BUY" and current_holding_qty >= previous_qty + float(qty):
            return "EXECUTED", detail
        if side_upper == "SELL" and current_holding_qty <= max(previous_qty - float(qty), 0):
            return "EXECUTED", detail

    return "APPROVED", detail


def _load_kis_client_from_records(records_kis: list[dict]):
    """
    KIS 레코드 목록이 있을 때 즉시 사용할 클라이언트를 생성합니다.
    """
    if not records_kis:
        return None

    crypto_helper = current_app.crypto
    record = records_kis[0]
    kis_access_key = crypto_helper.decrypt(record.get("encrypted_access_key"))
    kis_secret_key = crypto_helper.decrypt(record.get("encrypted_secret_key"))
    cano = record.get("kis_account_no")
    acnt_prdt_cd = record.get("kis_account_code", "01")
    kis_env = record.get("broker_env", "MOCK")
    return KISClient(
        appkey=kis_access_key,
        appsecret=kis_secret_key,
        cano=cano,
        acnt_prdt_cd=acnt_prdt_cd,
        env=kis_env,
        user_id=record.get("user_id"),
    )


def _fetch_kis_candles_with_interval(client: KISClient, symbol: str, interval: str, count: int) -> list:
    """
    요청 interval을 KIS 호출 규격으로 매핑해 캔들을 조회합니다.
    """
    if interval in ("1d", "D"):
        return client.get_candles(symbol, interval="D", count=count)
    if interval in ("1w", "W"):
        return client.get_candles(symbol, interval="W", count=count)
    if interval in ("1M", "M"):
        return client.get_candles(symbol, interval="M", count=count)
    if interval == "1m":
        return client.get_minute_candles(symbol, interval_minutes=1, count=count)
    if interval == "5m":
        return client.get_minute_candles(symbol, interval_minutes=5, count=count)
    if interval == "15m":
        return client.get_minute_candles(symbol, interval_minutes=15, count=count)
    if interval == "30m":
        return client.get_minute_candles(symbol, interval_minutes=30, count=count)
    if interval in ("60m", "1h"):
        return client.get_minute_candles(symbol, interval_minutes=60, count=count)
    return client.get_candles(symbol, interval="D", count=count)


def _resolve_reference_price(exchange: str, symbol: str, order_type: str, price, client) -> tuple[float, str]:
    """
    주문 검증 및 시장가 주문에 사용할 기준 가격을 계산합니다.
    """
    if order_type.upper() == "LIMIT":
        if price is None:
            raise ValueError("지정가 주문에는 단가(price)가 필수적입니다.")
        try:
            resolved_price = float(price)
        except (TypeError, ValueError):
            raise ValueError("올바르지 않은 단가 포맷입니다.")
        if not math.isfinite(resolved_price) or resolved_price <= 0:
            raise ValueError("주문 단가는 0보다 큰 유한한 숫자여야 합니다.")
        return resolved_price, "LIMIT_INPUT"

    if exchange not in ("TOSS", "KIS", "COINONE", "BINANCE", "BINANCE_UM_FUTURES") or client is None:
        raise ValueError(f"{exchange} 거래소는 현재 시장가 조회가 지원되지 않습니다.")

    price_info = client.get_price(symbol)
    resolved_price = float(price_info.get("current_price", 0) or 0)
    if not math.isfinite(resolved_price) or resolved_price <= 0:
        raise ValueError("시장가 검증을 위한 현재가를 확인할 수 없습니다.")
    return resolved_price, "LIVE_PRICE"


def _get_cached_spot_symbol_info(client, symbol: str, symbol_info_cache: dict | None = None) -> dict:
    normalized = str(symbol or "").strip().upper()
    if not normalized or client is None or not hasattr(client, "get_spot_symbol_info"):
        return {}
    cache = symbol_info_cache if symbol_info_cache is not None else {}
    if normalized not in cache:
        cache[normalized] = client.get_spot_symbol_info(normalized) or {}
    return cache.get(normalized) or {}


def _normalize_holding_lookup_symbol(client, exchange: str, symbol: str, symbol_info_cache: dict | None = None) -> str:
    normalized = str(symbol or "").strip().upper()
    if str(exchange or "").upper() != "BINANCE":
        return normalized
    if client is not None and hasattr(client, "get_spot_symbol_info"):
        try:
            symbol_info = _get_cached_spot_symbol_info(client, normalized, symbol_info_cache)
            base_asset = str((symbol_info or {}).get("base_asset") or "").upper()
            if base_asset:
                return base_asset
        except Exception:
            pass
    for quote_asset in BINANCE_SPOT_QUOTE_ASSETS:
        if normalized.endswith(quote_asset) and len(normalized) > len(quote_asset):
            return normalized[:-len(quote_asset)]
    return normalized


def _extract_balance_snapshot(
    client,
    symbol: str,
    exchange: str,
    symbol_info_cache: dict | None = None,
    position_side: str | None = None,
) -> dict:
    """
    잔고/보유 수량 기반 사전검증에 사용할 값을 정리합니다.
    """
    if client is None:
        return {
            "available_cash": None,
            "holding_qty": None,
            "holding_value": None,
        }

    try:
        balance = client.get_balance() or {}
    except Exception:
        return {
            "available_cash": None,
            "holding_qty": None,
            "holding_value": None,
        }

    available_cash = balance.get("available_cash")
    if client.__class__.__name__ == "TossClient":
        market_country = determine_market_country(symbol)
        if market_country == "US":
            details = balance.get("available_cash_details") or {}
            components = details.get("components") or []
            usd_cash = None
            for comp in components:
                if comp.get("currency") == "USD":
                    usd_cash = comp.get("cash_buying_power")
                    break
            if usd_cash is not None:
                available_cash = usd_cash

    try:
        available_cash = float(available_cash) if available_cash is not None else None
        if available_cash is not None and not math.isfinite(available_cash):
            available_cash = None
    except (TypeError, ValueError):
        available_cash = None

    target_holding_symbol = _normalize_holding_lookup_symbol(client, exchange, symbol, symbol_info_cache)
    holding_qty = 0.0
    holding_value = None
    for item in balance.get("holdings", []) or []:
        holding_symbol = str(item.get("symbol", "")).upper()
        if holding_symbol != target_holding_symbol:
            continue
        if exchange == "BINANCE_UM_FUTURES" and position_side:
            holding_position_side = str(item.get("position_side") or "BOTH").upper()
            if holding_position_side != str(position_side).upper():
                continue
        try:
            holding_qty = float(item.get("qty", 0))
            current_price = float(item.get("current_price", 0))
            if not math.isfinite(holding_qty) or not math.isfinite(current_price):
                raise ValueError("보유자산 수치가 유한하지 않습니다.")
            holding_value = holding_qty * current_price if current_price > 0 else None
        except (TypeError, ValueError):
            holding_qty = None
            holding_value = None
        break

    return {
        "available_cash": available_cash,
        "holding_qty": holding_qty,
        "holding_value": holding_value,
    }


def _normalize_futures_order_options(position_side=None, reduce_only=False, leverage=None, margin_type=None) -> dict:
    """
    바이낸스 USD-M 선물 주문 옵션을 검증하고 표준화합니다.
    """
    normalized_position_side = str(position_side or "BOTH").upper()
    if normalized_position_side not in ("BOTH", "LONG", "SHORT"):
        raise ValueError("선물 포지션 방향은 BOTH, LONG, SHORT 중 하나여야 합니다.")

    normalized_margin_type = str(margin_type or "CROSSED").upper()
    if normalized_margin_type == "CROSS":
        normalized_margin_type = "CROSSED"
    if normalized_margin_type not in ("CROSSED", "ISOLATED"):
        raise ValueError("선물 마진 모드는 교차(CROSSED) 또는 격리(ISOLATED)만 지원합니다.")

    try:
        leverage_int = int(leverage or 1)
    except (TypeError, ValueError):
        raise ValueError("선물 레버리지는 1~125 사이 정수로 입력해 주세요.")
    if leverage_int < 1 or leverage_int > 125:
        raise ValueError("선물 레버리지는 1~125 사이로 입력해 주세요.")

    reduce_only_bool = bool(reduce_only)
    if reduce_only_bool and normalized_position_side in ("LONG", "SHORT"):
        raise ValueError("바이낸스 헤지 모드(LONG/SHORT) 주문에는 Reduce Only 값을 함께 보낼 수 없습니다.")

    return {
        "position_side": normalized_position_side,
        "reduce_only": reduce_only_bool,
        "leverage": leverage_int,
        "margin_type": normalized_margin_type,
    }


def _validate_futures_order_quantity(client, symbol: str, order_type: str, qty: float) -> dict:
    """
    바이낸스 USD-M 선물 심볼별 주문 수량 제한을 사전 검증합니다.
    """
    filters = client.get_futures_symbol_filters(symbol)
    is_market = str(order_type or "").upper() == "MARKET"
    min_qty = filters.get("market_min_qty") if is_market else filters.get("min_qty")
    max_qty = filters.get("market_max_qty") if is_market else filters.get("max_qty")
    step_size = filters.get("market_step_size") if is_market else filters.get("step_size")

    if min_qty and qty < min_qty:
        raise ValueError(f"{symbol} 바이낸스 선물 최소 주문 수량은 {min_qty:g}입니다. 수량을 늘려 다시 시도하세요.")
    if max_qty and qty > max_qty:
        raise ValueError(f"{symbol} 바이낸스 선물 최대 주문 수량은 {max_qty:g}입니다. 현재 입력 수량 {qty:g}를 {max_qty:g} 이하로 낮춰 다시 시도하세요.")
    if step_size and step_size > 0:
        ratio = qty / step_size
        if abs(ratio - round(ratio)) > 1e-8:
            raise ValueError(f"{symbol} 바이낸스 선물 주문 수량은 {step_size:g} 단위로 입력해야 합니다.")

    return {
        "min_qty": min_qty,
        "max_qty": max_qty,
        "step_size": step_size,
        "tick_size": filters.get("tick_size"),
    }


def _to_positive_decimal(value) -> Decimal | None:
    if value in (None, ""):
        return None
    try:
        decimal_value = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    if not decimal_value.is_finite() or decimal_value <= 0:
        return None
    return decimal_value


def _floor_decimal_to_step(value: Decimal, step: Decimal) -> Decimal:
    if step <= 0:
        return value
    units = (value / step).to_integral_value(rounding=ROUND_DOWN)
    return units * step


def _build_crypto_quantity_filter(
    client,
    exchange: str,
    symbol: str,
    order_type: str,
    symbol_info_cache: dict | None = None,
) -> dict:
    if exchange == "COINONE" and hasattr(client, "get_order_quantity_rules"):
        rules = client.get_order_quantity_rules(symbol) or {}
        return {
            "exchange": exchange,
            "min_qty": rules.get("min_qty"),
            "max_qty": rules.get("max_qty"),
            "step_size": rules.get("qty_unit") or rules.get("step_size"),
            "source": rules.get("source") or "COINONE_ORDER_RULES",
        }
    if exchange == "BINANCE" and hasattr(client, "get_spot_symbol_info"):
        info = _get_cached_spot_symbol_info(client, symbol, symbol_info_cache)
        is_market = str(order_type or "").upper() == "MARKET"
        return {
            "exchange": exchange,
            "min_qty": info.get("market_min_qty") if is_market else info.get("min_qty"),
            "max_qty": info.get("market_max_qty") if is_market else info.get("max_qty"),
            "step_size": info.get("market_step_size") if is_market else info.get("step_size"),
            "source": "BINANCE_SPOT_LOT_SIZE",
        }
    return {"exchange": exchange, "source": "NO_QUANTITY_FILTER"}


def _normalize_crypto_order_quantity(
    client,
    exchange: str,
    symbol: str,
    order_type: str,
    qty: float,
    symbol_info_cache: dict | None = None,
) -> tuple[float, dict]:
    quantity_filter = _build_crypto_quantity_filter(client, exchange, symbol, order_type, symbol_info_cache)
    original_qty = _to_positive_decimal(qty)
    if original_qty is None:
        raise ValueError("주문 수량은 0보다 큰 유한한 숫자여야 합니다.")

    step_size = _to_positive_decimal(quantity_filter.get("step_size"))
    normalized_qty = _floor_decimal_to_step(original_qty, step_size) if step_size else original_qty
    min_qty = _to_positive_decimal(quantity_filter.get("min_qty"))
    max_qty = _to_positive_decimal(quantity_filter.get("max_qty"))

    if min_qty and normalized_qty < min_qty:
        raise ValueError(f"{symbol} 최소 주문 수량은 {float(min_qty):g}입니다. 수량을 늘려 다시 시도하세요.")
    if max_qty and normalized_qty > max_qty:
        raise ValueError(f"{symbol} 최대 주문 수량은 {float(max_qty):g}입니다. 수량을 {float(max_qty):g} 이하로 낮춰 다시 시도하세요.")
    if normalized_qty <= 0:
        raise ValueError("주문 수량이 거래소 주문 단위보다 작습니다. 수량을 늘려 다시 시도하세요.")

    normalized_float = float(normalized_qty)
    return normalized_float, {
        **quantity_filter,
        "original_quantity": float(original_qty),
        "normalized_quantity": normalized_float,
        "adjusted": normalized_qty != original_qty,
    }


def _run_binance_order_test(
    client,
    exchange: str,
    symbol: str,
    action: str,
    order_type: str,
    qty: float,
    price: float,
) -> dict | None:
    """
    Binance 테스트 주문 API로 실제 매칭 엔진 투입 전 주문 유효성을 검증합니다.
    """
    if exchange == "BINANCE":
        return client.test_order(
            symbol=symbol,
            qty=qty,
            side=action,
            ord_type=order_type,
            price=price,
            compute_commission_rates=True,
        )
    if exchange == "BINANCE_UM_FUTURES":
        return client.test_order(
            symbol=symbol,
            qty=qty,
            side=action,
            ord_type=order_type,
            price=price,
        )
    return None


def _exceeds_real_order_limit(broker_env: str, estimated_amount_krw: float) -> bool:
    """REAL 주문에만 1회 주문 한도를 적용합니다."""
    if str(broker_env or "").upper() != "REAL":
        return False
    try:
        amount = float(estimated_amount_krw)
    except (TypeError, ValueError):
        return True
    return not math.isfinite(amount) or amount > REAL_ORDER_LIMIT_KRW


def _build_precheck_payload(
    exchange: str,
    symbol: str,
    action: str,
    order_type: str,
    quantity,
    price,
    broker_env: str,
    record: dict,
    access_key: str,
    secret_key: str,
    futures_options: dict | None = None,
) -> dict:
    """
    주문 전 검증 결과를 공통 포맷으로 생성합니다.
    """
    try:
        qty = float(quantity)
    except (TypeError, ValueError):
        raise ValueError("올바르지 않은 주문 수량 포맷입니다.")
    if not math.isfinite(qty) or qty <= 0:
        raise ValueError("주문 수량은 0보다 큰 유한한 숫자여야 합니다.")
    if exchange in ("TOSS", "KIS") and not float(qty).is_integer():
        raise ValueError("주식 주문 수량은 현재 정수 단위만 지원합니다. 소수점 또는 금액 주문은 공식 지원 스펙 확인 후 활성화해야 합니다.")

    client = _build_exchange_client(exchange, broker_env, record, access_key, secret_key)
    symbol_info_cache = {}
    quantity_filter = None
    if exchange in ("COINONE", "BINANCE"):
        qty, quantity_filter = _normalize_crypto_order_quantity(
            client,
            exchange=exchange,
            symbol=symbol,
            order_type=order_type,
            qty=qty,
            symbol_info_cache=symbol_info_cache,
        )
    reference_price, price_source = _resolve_reference_price(exchange, symbol, order_type, price, client)
    normalized_futures_options = None
    if exchange == "BINANCE_UM_FUTURES":
        position_mode = client.get_position_mode()
        execution = resolve_futures_execution(
            (futures_options or {}).get("intent"),
            position_mode.get("mode"),
            (futures_options or {}).get("position_side"),
        )
        normalized_futures_options = _normalize_futures_order_options(
            position_side=execution["position_side"],
            reduce_only=execution["reduce_only"],
            leverage=(futures_options or {}).get("leverage"),
            margin_type=(futures_options or {}).get("margin_type"),
        )
        normalized_futures_options.update(execution)
        normalized_futures_options["position_mode"] = position_mode.get("mode")
        max_leverage = client.get_max_leverage(symbol)
        normalized_futures_options["max_leverage"] = max_leverage
        service_max_leverage = resolve_service_leverage_limit(
            max_leverage,
            os.getenv("BINANCE_FUTURES_SERVICE_MAX_LEVERAGE"),
        )
        normalized_futures_options["service_max_leverage"] = service_max_leverage
        if normalized_futures_options["leverage"] > service_max_leverage:
            raise ValueError(f"{symbol} 선물의 현재 서비스 최대 레버리지는 {service_max_leverage}x입니다. 레버리지를 {service_max_leverage}x 이하로 낮춰 다시 시도하세요.")
        normalized_futures_options["quantity_filter"] = _validate_futures_order_quantity(client, symbol, order_type, qty)
    estimated_amount = reference_price * qty
    if not math.isfinite(estimated_amount) or estimated_amount <= 0:
        raise ValueError("예상 주문금액을 유한한 숫자로 계산할 수 없습니다.")
    required_margin = (
        estimated_amount / normalized_futures_options["leverage"]
        if normalized_futures_options
        else estimated_amount
    )
    exchange_rate = 1.0
    if exchange == "TOSS" and determine_market_country(symbol) == "US":
        exchange_rate = USD_KRW_FALLBACK
        try:
            live_exchange_rate = float(client.get_exchange_rate())
            if math.isfinite(live_exchange_rate) and live_exchange_rate > 0:
                exchange_rate = live_exchange_rate
        except Exception:
            pass
    elif exchange in ("BINANCE", "BINANCE_UM_FUTURES"):
        exchange_rate = USD_KRW_FALLBACK
    estimated_amount_krw = estimated_amount * exchange_rate
    if not math.isfinite(estimated_amount_krw) or estimated_amount_krw <= 0:
        raise ValueError("예상 원화 주문금액을 유한한 숫자로 계산할 수 없습니다.")
    balance_snapshot = _extract_balance_snapshot(
        client,
        symbol,
        exchange,
        symbol_info_cache,
        position_side=(normalized_futures_options or {}).get("position_side"),
    )
    available_cash = balance_snapshot["available_cash"]
    holding_qty = balance_snapshot["holding_qty"]

    exceeds_hard_cap = _exceeds_real_order_limit(broker_env, estimated_amount_krw)
    if exchange == "BINANCE_UM_FUTURES":
        balance_check_failed = (
            holding_qty is None
            if normalized_futures_options["reduce_only"]
            else available_cash is None
        )
        insufficient_cash = (
            not normalized_futures_options["reduce_only"]
            and available_cash is not None
            and required_margin > available_cash
        )
        insufficient_holding = (
            normalized_futures_options["reduce_only"]
            and holding_qty is not None
            and qty > abs(holding_qty)
        )
    else:
        balance_check_failed = (
            available_cash is None if action.upper() == "BUY" else holding_qty is None
        )
        insufficient_cash = (
            action.upper() == "BUY"
            and available_cash is not None
            and required_margin > available_cash
        )
        insufficient_holding = (
            action.upper() == "SELL"
            and holding_qty is not None
            and qty > holding_qty
        )

    is_market_closed = False
    market_status_message = "장 운영 중"
    if exchange in ("TOSS", "KIS"):
        market_country = determine_market_country(symbol)
        if market_country == "US":
            if not is_us_market_open(client):
                is_market_closed = True
                market_status_message = "현재는 미국 주식 장외 시간(또는 휴장일)입니다."
            elif order_type.upper() == "MARKET" and not _is_us_regular_market_open(client):
                is_market_closed = True
                market_status_message = "미국 주식 시장가/금액 주문은 정규장(한국 기준 밤 11시반~새벽 6시)에만 가능합니다."
        else:
            if not is_kr_market_open(client, symbol):
                is_market_closed = True
                is_nxt_supported = False

                # 공용/사용자 토스 클라이언트 빌드
                calendar_client = client
                if not calendar_client or not hasattr(calendar_client, "get_stock_info"):
                    user_id = getattr(client, "user_id", None)
                    env = getattr(client, "env", "REAL")
                    calendar_client = _get_shared_toss_client(user_id=user_id, broker_env=env)

                if calendar_client and hasattr(calendar_client, "get_stock_info"):
                    try:
                        stock_info = calendar_client.get_stock_info(symbol)
                        if stock_info and isinstance(stock_info, dict):
                            korean_detail = stock_info.get("korean_market_detail") or {}
                            is_nxt_supported = bool(korean_detail.get("nxt_supported"))
                    except Exception:
                        pass

                if is_nxt_supported:
                    market_status_message = "현재는 한국 주식 대체거래소(NXT) 장외 시간(20시~익일 08시) 또는 공휴일입니다."
                else:
                    market_status_message = "현재는 한국 주식 정규장 장외 시간(15시30분~익일 09시) 또는 공휴일입니다. (NXT 미지원 종목)"

    asset_type = "STOCK" if exchange in ("TOSS", "KIS") else "CRYPTO"
    currency = "KRW" if exchange in ("TOSS", "KIS", "COINONE") else "USD"
    if exchange == "TOSS" and determine_market_country(symbol) == "US":
        currency = "USD"
    warnings = []
    if is_market_closed:
        warnings.append(market_status_message)
    if exceeds_hard_cap:
        warnings.append("실거래 1회 주문 한도 100,000원을 초과했습니다.")

    insufficient_permission = False
    permission_message = ""
    if broker_env == "REAL" and exchange in ("BINANCE", "BINANCE_UM_FUTURES"):
        api_perms = record.get("api_permissions") or {}
        # 기존 저장된 키에 api_permissions 컬럼값이 없을 수 있으므로 빈 딕셔너리일 경우 기본 통과시킵니다.
        if api_perms:
            if exchange == "BINANCE":
                if not api_perms.get("spot_trade_enabled", False):
                    insufficient_permission = True
                    permission_message = "바이낸스 API Key에 현물 거래(Spot) 권한이 없습니다. 바이낸스 API 설정에서 Enable Spot & Margin Trading을 활성화하세요."
                    warnings.append("API Key 현물 거래 권한 누락")
            elif exchange == "BINANCE_UM_FUTURES":
                if not api_perms.get("futures_trade_enabled", False):
                    insufficient_permission = True
                    permission_message = "바이낸스 API Key에 선물 거래(Futures) 권한이 없습니다. 바이낸스 API 설정에서 Enable Futures를 활성화하세요."
                    warnings.append("API Key 선물 거래 권한 누락")

    exchange_order_test = None
    futures_real_blocked = (
        exchange == "BINANCE_UM_FUTURES"
        and broker_env == "REAL"
        and os.getenv("BINANCE_FUTURES_REAL_ENABLED", "false").lower() != "true"
    )
    if futures_real_blocked:
        warnings.append("바이낸스 선물 실거래는 기본 차단되어 있습니다. 모의투자(TESTNET/MOCK)로 먼저 검증하세요.")
    if insufficient_cash:
        warnings.append("예수금 대비 주문 예정 증거금이 큽니다." if exchange == "BINANCE_UM_FUTURES" else "예수금 대비 주문 예정 금액이 큽니다.")
    if insufficient_holding:
        warnings.append("보유 수량보다 많은 매도 주문입니다.")
    if exchange in ("BINANCE", "BINANCE_UM_FUTURES"):
        exchange_order_test = _run_binance_order_test(
            client,
            exchange=exchange,
            symbol=symbol,
            action=action,
            order_type=order_type,
            qty=qty,
            price=reference_price,
        )

    return {
        "exchange": exchange,
        "symbol": symbol,
        "action": action.upper(),
        "order_type": order_type.upper(),
        "broker_env": broker_env,
        "asset_type": asset_type,
        "currency": currency,
        "quantity": qty,
        "quantity_filter": quantity_filter,
        "reference_price": reference_price,
        "price_source": price_source,
        "estimated_amount": estimated_amount,
        "estimated_amount_krw": estimated_amount_krw,
        "exchange_rate": exchange_rate,
        "required_margin": required_margin,
        "futures_options": normalized_futures_options,
        "real_order_limit_krw": REAL_ORDER_LIMIT_KRW,
        "exceeds_real_order_limit": exceeds_hard_cap,
        "futures_real_blocked": futures_real_blocked,
        "insufficient_permission": insufficient_permission,
        "permission_message": permission_message,
        "available_cash": available_cash,
        "holding_qty": holding_qty,
        "holding_value": balance_snapshot["holding_value"],
        "balance_check_failed": balance_check_failed,
        "insufficient_cash": insufficient_cash,
        "insufficient_holding": insufficient_holding,
        "exchange_order_test": exchange_order_test,
        "warnings": warnings,
        "is_market_closed": is_market_closed,
        "market_status_message": market_status_message,
        "checked_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }


def _order_entry_auth():
    auth_header = request.headers.get("Authorization")
    if not auth_header:
        raise PermissionError("인증 헤더가 누락되었습니다.")
    user_id, _ = get_user_id_from_header(auth_header)
    return auth_header, user_id


def _order_entry_signing_secret() -> str:
    secret = os.getenv("ORDER_PRECHECK_SIGNING_SECRET") or current_app.config.get("SECRET_KEY")
    if not secret:
        raise RuntimeError("ORDER_PRECHECK_SIGNING_SECRET 환경 설정이 필요합니다.")
    return str(secret)


def _order_entry_asset_type(exchange: str) -> str:
    if exchange in {"TOSS", "KIS"}:
        return "STOCK"
    if exchange == "BINANCE_UM_FUTURES":
        return "CRYPTO_FUTURES"
    return "CRYPTO_SPOT"


def _order_entry_broker_label(exchange: str) -> str:
    return {
        "TOSS": "Toss증권",
        "KIS": "한국투자증권",
        "COINONE": "코인원",
        "BINANCE": "Binance Spot",
        "BINANCE_UM_FUTURES": "Binance USD-M Futures",
    }.get(exchange, exchange)


def _order_entry_currency(exchange: str, balance: dict | None = None) -> str:
    if exchange == "COINONE":
        return "KRW"
    if exchange in {"BINANCE", "BINANCE_UM_FUTURES"}:
        return "USDT"
    currency = str((balance or {}).get("currency") or "KRW").upper()
    return currency if currency in {"KRW", "USD"} else "KRW"


def _order_entry_record_variants(record: dict) -> list[tuple[str, dict]]:
    exchange = str(record.get("exchange") or "").upper()
    if exchange == "BINANCE":
        return [("BINANCE", record), ("BINANCE_UM_FUTURES", record)]
    return [(exchange, record)] if exchange in SUPPORTED_TRADE_EXCHANGES else []


def _load_order_entry_client(auth_header: str, user_id: str, exchange: str, broker_env: str):
    record, access_key, secret_key = _load_user_exchange_record(
        auth_header,
        user_id,
        exchange,
        broker_env,
    )
    return record, _build_exchange_client(exchange, broker_env, record, access_key, secret_key)


def _collect_order_entry_blockers(precheck: dict, broker_env: str) -> list[str]:
    blockers = []
    if precheck.get("balance_check_failed"):
        blockers.append("주문에 필요한 잔고 또는 보유수량을 확인하지 못했습니다.")
    if precheck.get("is_market_closed"):
        blockers.append(precheck.get("market_status_message") or "현재 거래 가능 시간이 아닙니다.")
    if precheck.get("insufficient_cash"):
        blockers.append("주문 가능 잔액이 부족합니다.")
    if precheck.get("insufficient_holding"):
        blockers.append("매도 또는 청산 가능 수량을 초과했습니다.")
    if precheck.get("insufficient_permission"):
        blockers.append(precheck.get("permission_message") or "거래 권한이 없습니다.")
    if precheck.get("futures_real_blocked"):
        blockers.append("바이낸스 선물 실거래가 잠겨 있습니다.")
    if broker_env == "REAL" and precheck.get("exceeds_real_order_limit"):
        blockers.append("실거래 1회 주문 한도 100,000원을 초과했습니다.")
    return blockers


def _validate_order_entry_symbol(client, exchange: str, symbol: str) -> None:
    normalized_symbol = str(symbol or "").strip().upper()
    if not normalized_symbol:
        raise ValueError("거래할 종목을 선택해 주세요.")
    if exchange == "BINANCE" and hasattr(client, "get_spot_symbol_info"):
        info = client.get_spot_symbol_info(normalized_symbol) or {}
        if not info or str(info.get("status") or "TRADING").upper() != "TRADING":
            raise ValueError("선택한 종목은 바이낸스 현물에서 현재 거래할 수 없습니다.")
    elif exchange == "BINANCE_UM_FUTURES" and hasattr(client, "get_futures_symbol_filters"):
        if not (client.get_futures_symbol_filters(normalized_symbol) or {}):
            raise ValueError("선택한 종목은 바이낸스 USD-M 선물에서 현재 거래할 수 없습니다.")
    elif exchange == "COINONE" and hasattr(client, "get_currency_info"):
        if not (client.get_currency_info(normalized_symbol) or {}):
            raise ValueError("선택한 종목은 코인원에서 현재 거래할 수 없습니다.")

    price_info = client.get_price(normalized_symbol) or {}
    try:
        current_price = float(price_info.get("current_price") or 0)
    except (TypeError, ValueError) as error:
        raise ValueError("선택한 종목의 현재가를 확인할 수 없습니다.") from error
    if not math.isfinite(current_price) or current_price <= 0:
        raise ValueError("선택한 종목의 현재가를 확인할 수 없습니다.")


def _safe_holding_row(row: dict, exchange: str) -> dict:
    qty = row.get("qty") if row.get("qty") is not None else row.get("position_amt")
    available_qty = row.get("available_qty")
    if available_qty is None:
        available_qty = abs(float(qty or 0))
    position_side = str(row.get("position_side") or "").upper() or None
    return {
        "symbol": str(row.get("symbol") or "").upper(),
        "name": row.get("name") or row.get("symbol"),
        "position_side": position_side if exchange == "BINANCE_UM_FUTURES" else None,
        "quantity": abs(float(qty or 0)),
        "available_qty": abs(float(available_qty or 0)),
        "avg_price": float(row.get("avg_price") or row.get("entry_price") or 0),
        "current_price": float(row.get("current_price") or row.get("mark_price") or 0),
        "profit": float(row.get("profit") or row.get("unrealized_profit") or 0),
        "profit_rate": float(row.get("profit_rate") or 0),
        "liquidation_price": float(row.get("liquidation_price") or 0),
        "currency": "USDT" if exchange == "BINANCE_UM_FUTURES" else str(row.get("currency") or _currency_for_quote(exchange, str(row.get("symbol") or ""))).upper(),
    }


@trade_bp.route("/api/trade/order-entry/accounts", methods=["GET"])
def list_order_entry_accounts():
    try:
        auth_header, user_id = _order_entry_auth()
    except PermissionError as error:
        return jsonify({"success": False, "message": str(error)}), 401
    except Exception as error:
        return jsonify(format_error_payload(error, "주문 계좌 인증 실패")), 401

    try:
        records = _query_user_exchange_records(auth_header, user_id, "") or []
        accounts = []
        seen = set()
        for record in records:
            for exchange, source_record in _order_entry_record_variants(record):
                broker_env = str(source_record.get("broker_env") or "").upper()
                key_id = str(source_record.get("id") or "")
                account_id = f"{exchange}:{broker_env}:{key_id}"
                if not broker_env or account_id in seen:
                    continue
                seen.add(account_id)
                status = "READY"
                status_message = "주문 가능한 계좌입니다."
                balance = {}
                permissions = source_record.get("api_permissions") or {}
                try:
                    access_key = current_app.crypto.decrypt(source_record.get("encrypted_access_key"))
                    secret_key = current_app.crypto.decrypt(source_record.get("encrypted_secret_key"))
                    client = _build_exchange_client(exchange, broker_env, source_record, access_key, secret_key)
                    balance = client.get_balance() or {}
                    if hasattr(client, "get_api_permissions"):
                        permissions = client.get_api_permissions() or permissions
                except Exception:
                    status = "UNAVAILABLE"
                    status_message = "계좌 잔액 또는 거래 권한을 확인하지 못했습니다. API 연결 설정을 확인해 주세요."

                real_locked = (
                    exchange == "BINANCE_UM_FUTURES"
                    and broker_env == "REAL"
                    and os.getenv("BINANCE_FUTURES_REAL_ENABLED", "false").lower() != "true"
                )
                permission_key = "futures_trade_enabled" if exchange == "BINANCE_UM_FUTURES" else "spot_trade_enabled"
                permission_blocked = bool(permissions) and exchange in {"BINANCE", "BINANCE_UM_FUTURES"} and not permissions.get(permission_key, False)
                trade_enabled = status == "READY" and not real_locked and not permission_blocked
                if real_locked:
                    status = "LOCKED"
                    status_message = "바이낸스 선물 실거래 잠금이 활성화되어 있습니다."
                elif permission_blocked:
                    status = "PERMISSION_REQUIRED"
                    status_message = "API Key의 거래 권한을 확인해 주세요."
                accounts.append({
                    "id": account_id,
                    "exchange": exchange,
                    "broker": _order_entry_broker_label(exchange),
                    "asset_type": _order_entry_asset_type(exchange),
                    "broker_env": broker_env,
                    "currency": _order_entry_currency(exchange, balance),
                    "available_cash": balance.get("available_cash"),
                    "total_evaluation": balance.get("total_evaluation"),
                    "api_permissions": permissions,
                    "trade_enabled": trade_enabled,
                    "real_trading_locked": real_locked,
                    "status": status,
                    "status_message": status_message,
                })
        return jsonify({"success": True, "data": {"accounts": accounts}})
    except Exception as error:
        return jsonify(format_error_payload(error, "주문 계좌 목록 조회 실패")), 500


@trade_bp.route("/api/trade/order-entry/holdings", methods=["GET"])
def list_order_entry_holdings():
    try:
        auth_header, user_id = _order_entry_auth()
    except PermissionError as error:
        return jsonify({"success": False, "message": str(error)}), 401
    except Exception as error:
        return jsonify(format_error_payload(error, "보유 자산 인증 실패")), 401

    exchange = str(request.args.get("exchange") or "").upper()
    broker_env = str(request.args.get("broker_env") or "").upper()
    if exchange not in SUPPORTED_TRADE_EXCHANGES or broker_env not in {"REAL", "MOCK"}:
        return jsonify({"success": False, "message": "계좌의 거래소와 거래 환경을 다시 선택해 주세요."}), 400
    try:
        _, client = _load_order_entry_client(auth_header, user_id, exchange, broker_env)
        balance = client.get_balance() or {}
        holdings = [
            _safe_holding_row(row, exchange)
            for row in (balance.get("holdings") or [])
            if float(row.get("qty") if row.get("qty") is not None else row.get("position_amt") or 0) != 0
        ]
        return jsonify({"success": True, "data": {"holdings": holdings, "checked_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")}})
    except ValueError as error:
        return jsonify({"success": False, "message": _format_user_value_error_message(error)}), 400
    except Exception as error:
        return jsonify(format_error_payload(error, "보유 자산 조회 실패", exchange=exchange)), 500


@trade_bp.route("/api/trade/order-entry/symbols", methods=["GET"])
def search_order_entry_symbols():
    try:
        auth_header, user_id = _order_entry_auth()
    except PermissionError as error:
        return jsonify({"success": False, "message": str(error)}), 401
    except Exception as error:
        return jsonify(format_error_payload(error, "거래 종목 검색 인증 실패")), 401

    exchange = str(request.args.get("exchange") or "").upper()
    broker_env = str(request.args.get("broker_env") or "").upper()
    query = str(request.args.get("query") or "").strip().upper()
    if exchange not in SUPPORTED_TRADE_EXCHANGES or broker_env not in {"REAL", "MOCK"} or not query:
        return jsonify({"success": True, "data": {"symbols": []}})
    try:
        from backend.services.symbol_metadata import COIN_DISPLAY_NAMES, SYMBOL_METADATA, search_crypto_symbols

        _, client = _load_order_entry_client(auth_header, user_id, exchange, broker_env)
        candidates = []
        if exchange in {"TOSS", "KIS"}:
            for symbol, metadata in SYMBOL_METADATA.items():
                name = str(metadata.get("display_name") or symbol)
                market = str(metadata.get("market") or "KR").upper()
                if query not in symbol and query not in name.upper():
                    continue
                if exchange == "KIS" and market == "US":
                    continue
                candidates.append({"symbol": symbol, "name": name, "market": market})
        else:
            for item in search_crypto_symbols(query, limit=10):
                exchanges = item.get("exchanges") or []
                if exchange == "COINONE" and "COINONE" not in exchanges:
                    continue
                if exchange in {"BINANCE", "BINANCE_UM_FUTURES"} and "BINANCE" not in exchanges:
                    continue
                base_symbol = str(item.get("symbol") or "").upper()
                market_symbol = base_symbol if exchange == "COINONE" else f"{base_symbol}USDT"
                candidates.append({
                    "symbol": market_symbol,
                    "name": item.get("display_name") or COIN_DISPLAY_NAMES.get(base_symbol, base_symbol),
                    "market": "KRW" if exchange == "COINONE" else "USDT",
                })

        results = []
        for candidate in candidates[:10]:
            try:
                price = client.get_price(candidate["symbol"]) or {}
                current_price = float(price.get("current_price") or 0)
                change_rate = float(price.get("change_rate") or 0)
                tradable = math.isfinite(current_price) and current_price > 0
            except Exception:
                current_price = None
                change_rate = None
                tradable = False
            results.append({
                **candidate,
                "current_price": current_price,
                "change_rate": change_rate,
                "currency": _currency_for_quote(exchange, candidate["symbol"]),
                "tradable": tradable,
            })
        return jsonify({"success": True, "data": {"symbols": results}})
    except Exception as error:
        return jsonify(format_error_payload(error, "거래 종목 검색 실패", exchange=exchange)), 500


@trade_bp.route("/api/trade/order-entry/context", methods=["GET"])
def get_order_entry_context():
    try:
        auth_header, user_id = _order_entry_auth()
    except PermissionError as error:
        return jsonify({"success": False, "message": str(error)}), 401
    except Exception as error:
        return jsonify(format_error_payload(error, "주문 조건 인증 실패")), 401

    exchange = str(request.args.get("exchange") or "").upper()
    broker_env = str(request.args.get("broker_env") or "").upper()
    symbol = str(request.args.get("symbol") or "").strip().upper()
    if not symbol:
        return jsonify({"success": False, "message": "거래할 종목을 선택해 주세요."}), 400
    if exchange not in SUPPORTED_TRADE_EXCHANGES or broker_env not in {"REAL", "MOCK"}:
        return jsonify({"success": False, "message": "계좌를 다시 선택해 주세요."}), 400
    try:
        record, client = _load_order_entry_client(auth_header, user_id, exchange, broker_env)
        _validate_order_entry_symbol(client, exchange, symbol)
        price = client.get_price(symbol) or {}
        context = {
            "symbol": symbol,
            "current_price": float(price.get("current_price") or 0),
            "change_rate": float(price.get("change_rate") or 0),
            "currency": _currency_for_quote(exchange, symbol),
            "market_open": True,
            "warnings": [],
            "quantity_filter": None,
            "position_mode": None,
            "exchange_max_leverage": 1,
            "service_max_leverage": 1,
            "leverage_options": [1],
            "api_permissions": record.get("api_permissions") or {},
            "checked_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        }
        if exchange == "BINANCE_UM_FUTURES":
            exchange_max = client.get_max_leverage(symbol)
            service_max = resolve_service_leverage_limit(
                exchange_max,
                os.getenv("BINANCE_FUTURES_SERVICE_MAX_LEVERAGE"),
            )
            context.update({
                "quantity_filter": client.get_futures_symbol_filters(symbol),
                "position_mode": (client.get_position_mode() or {}).get("mode"),
                "exchange_max_leverage": exchange_max,
                "service_max_leverage": service_max,
                "leverage_options": list(range(1, service_max + 1)),
            })
        elif exchange in {"COINONE", "BINANCE"}:
            context["quantity_filter"] = _build_crypto_quantity_filter(client, exchange, symbol, "LIMIT")
        if exchange in {"TOSS", "KIS"} and hasattr(client, "get_stock_warnings"):
            context["warnings"] = client.get_stock_warnings(symbol) or []
        return jsonify({"success": True, "data": context})
    except ValueError as error:
        return jsonify({"success": False, "message": _format_user_value_error_message(error)}), 400
    except Exception as error:
        return jsonify(format_error_payload(error, "주문 조건 조회 실패", exchange=exchange)), 500


@trade_bp.route("/api/trade/precheck", methods=["POST"])
def precheck_manual_order():
    """
    수동 주문 전 금액/잔고/보유 수량을 검증하여 프론트에 반환합니다.
    """
    auth_header = request.headers.get("Authorization")
    if not auth_header:
        return jsonify({"success": False, "message": "인증 헤더가 누락되었습니다."}), 401

    try:
        user_id, _ = get_user_id_from_header(auth_header)
    except Exception as error:
        return jsonify(format_error_payload(error, "주문 사전검증 인증 실패")), 401

    try:
        order = normalize_order_request(request.json or {})
    except ValueError as error:
        return jsonify({"success": False, "message": str(error)}), 400

    exchange = order["exchange"]
    symbol = order["symbol"]
    action = order["side"]
    order_type = order["order_type"]
    quantity = order["quantity"]
    price = order["price"]
    broker_env = order["broker_env"]

    if exchange == "COINONE" and order_type != "LIMIT":
        return jsonify({"success": False, "message": "코인원 주문 사전검증은 현재 지정가(LIMIT)만 지원합니다."}), 400
    if broker_env == "REAL" and order_type == "MARKET":
        return jsonify({
            "success": False,
            "message": "실거래 시장가 주문은 100,000원 하드캡을 보장할 수 없어 지원하지 않습니다. 지정가를 입력해 주세요.",
        }), 400

    try:
        record, access_key, secret_key = _load_user_exchange_record(auth_header, user_id, exchange, broker_env)
        validation_client = _build_exchange_client(exchange, broker_env, record, access_key, secret_key)
        _validate_order_entry_symbol(validation_client, exchange, symbol)
        payload = _build_precheck_payload(
            exchange=exchange,
            symbol=symbol,
            action=action,
            order_type=order_type,
            quantity=quantity,
            price=price,
            broker_env=broker_env,
            record=record,
            access_key=access_key,
            secret_key=secret_key,
            futures_options={
                "intent": order.get("intent"),
                "position_side": order.get("position_side"),
                "leverage": order.get("leverage"),
                "margin_type": order.get("margin_type"),
            } if exchange == "BINANCE_UM_FUTURES" else None,
        )
        blockers = _collect_order_entry_blockers(payload, broker_env)
        can_create_proposal = not blockers
        payload["blockers"] = blockers
        payload["can_create_proposal"] = can_create_proposal
        payload["order_hash"] = order_request_hash(order)
        payload["precheck_token"] = (
            issue_precheck_token(
                user_id,
                order,
                payload,
                _order_entry_signing_secret(),
                ttl_seconds=int(os.getenv("ORDER_PRECHECK_TOKEN_TTL_SECONDS", "300")),
            )
            if can_create_proposal
            else None
        )
        return jsonify({"success": True, "data": payload})
    except ValueError as e:
        return jsonify({"success": False, "message": _format_user_value_error_message(e)}), 400
    except Exception as e:
        return jsonify(format_error_payload(e, "주문 사전검증 실패", exchange=exchange)), 500

@trade_bp.route("/api/trade/order", methods=["POST"])
def place_manual_order():
    """
    통합 수동 주문 API 엔드포인트.
    프론트엔드에서 수동으로 입력한 주문을 처리하고,
    주문 금액이 10만원 이하인지 가드 검증을 거친 후 해당하는 거래소 API를 기동합니다.
    """
    auth_header = request.headers.get("Authorization")
    if not auth_header:
        return jsonify({"success": False, "message": "인증 헤더가 누락되었습니다."}), 401

    try:
        user_id, token = get_user_id_from_header(auth_header)
    except Exception as e:
        return jsonify({"success": False, "message": f"인증 실패: {str(e)}"}), 401

    data = request.json or {}
    try:
        data, approval_proposal = _resolve_proposal_order_data(auth_header, user_id, data)
    except ValueError as error:
        return jsonify({"success": False, "message": str(error)}), 400
    exchange = str(data.get("exchange") or "").upper()
    symbol = data.get("symbol")
    action = data.get("action")  # BUY or SELL
    order_type = data.get("order_type")  # LIMIT or MARKET
    price = data.get("price")  # LIMIT일 때 필수
    quantity = data.get("quantity")  # 필수
    broker_env = str(data.get("broker_env", "REAL") or "REAL").upper()  # MOCK or REAL

    # 1. 필수 파라미터 검증
    if not exchange or not symbol or not action or not order_type or quantity is None:
        return jsonify({"success": False, "message": "필수 주문 파라미터가 누락되었습니다."}), 400

    if exchange not in SUPPORTED_TRADE_EXCHANGES:
        return jsonify({"success": False, "message": "지원하지 않는 거래소입니다."}), 400

    # 해외 주식(미국 주식)은 KIS 주문을 허용하지 않고 오직 TOSS로만 주문할 수 있도록 차단
    is_us_stock = any(c.isalpha() for c in symbol)
    if exchange == "KIS" and is_us_stock:
        return jsonify({"success": False, "message": "해외 주식(미국 주식)은 Toss증권을 통해서만 주문이 가능합니다."}), 400

    if action.upper() not in ("BUY", "SELL"):
        return jsonify({"success": False, "message": "올바르지 않은 주문 방향(action)입니다."}), 400

    if order_type.upper() not in ("LIMIT", "MARKET"):
        return jsonify({"success": False, "message": "올바르지 않은 주문 유형(order_type)입니다."}), 400
    if exchange == "COINONE" and order_type.upper() != "LIMIT":
        return jsonify({"success": False, "message": "코인원 주문은 현재 지정가(LIMIT)만 지원합니다."}), 400
    if broker_env == "REAL" and order_type.upper() == "MARKET":
        return jsonify({
            "success": False,
            "message": "실거래 시장가 주문은 100,000원 하드캡을 보장할 수 없어 지원하지 않습니다. 지정가를 입력해 주세요.",
        }), 400

    try:
        qty = float(quantity)
        if not math.isfinite(qty) or qty <= 0:
            return jsonify({"success": False, "message": "주문 수량은 0보다 큰 유한한 숫자여야 합니다."}), 400
    except (TypeError, ValueError):
        return jsonify({"success": False, "message": "올바르지 않은 주문 수량 포맷입니다."}), 400

    auto_exit_value = data.get("auto_exit", False)
    if isinstance(auto_exit_value, bool):
        auto_exit = auto_exit_value
    elif str(auto_exit_value).strip().lower() in {"true", "1"}:
        auto_exit = True
    elif str(auto_exit_value).strip().lower() in {"false", "0", "", "none"}:
        auto_exit = False
    else:
        return jsonify({"success": False, "message": "자동감시 사용 여부는 true 또는 false로 입력해 주세요."}), 400

    target_profit_rate = 5.0
    stop_loss_rate = -3.0
    if auto_exit and action.upper() == "BUY":
        try:
            target_profit_rate = float(data.get("target_profit_rate", 5.0))
            stop_loss_rate = float(data.get("stop_loss_rate", -3.0))
        except (TypeError, ValueError):
            return jsonify({"success": False, "message": "익절·손절 비율은 유한한 숫자로 입력해 주세요."}), 400
        if not math.isfinite(target_profit_rate) or not math.isfinite(stop_loss_rate):
            return jsonify({"success": False, "message": "익절·손절 비율은 유한한 숫자로 입력해 주세요."}), 400

    auto_exit_execution_mode = str(
        data.get("auto_exit_execution_mode") or "PROPOSAL"
    ).upper()
    if auto_exit_execution_mode not in ("PROPOSAL", "AUTO"):
        auto_exit_execution_mode = "PROPOSAL"
    auto_restart_value = data.get("auto_restart_on_partial_fill", True)
    if isinstance(auto_restart_value, bool):
        auto_restart_on_partial_fill = auto_restart_value
    elif str(auto_restart_value).strip().casefold() in {"true", "1"}:
        auto_restart_on_partial_fill = True
    elif str(auto_restart_value).strip().casefold() in {"false", "0"}:
        auto_restart_on_partial_fill = False
    else:
        return jsonify({
            "success": False,
            "message": "부분체결 후 자동 재시작 여부는 true 또는 false로 입력해 주세요.",
        }), 400

    try:
        record, access_key, secret_key = _load_user_exchange_record(auth_header, user_id, exchange, broker_env)
    except ValueError as e:
        return jsonify({"success": False, "message": _format_user_value_error_message(e)}), 400
    except Exception as e:
        return jsonify(format_error_payload(e, "API 크리덴셜 로드 및 복호화 실패", exchange=exchange)), 500

    # 3. 공통 사전 검증
    try:
        precheck = _build_precheck_payload(
            exchange=exchange,
            symbol=symbol,
            action=action,
            order_type=order_type,
            quantity=quantity,
            price=price,
            broker_env=broker_env,
            record=record,
            access_key=access_key,
            secret_key=secret_key,
            futures_options={
                "intent": data.get("intent"),
                "position_side": data.get("position_side"),
                "reduce_only": data.get("reduce_only", False),
                "leverage": data.get("leverage"),
                "margin_type": data.get("margin_type"),
            } if exchange == "BINANCE_UM_FUTURES" else None,
        )
    except ValueError as e:
        return jsonify({"success": False, "message": _format_user_value_error_message(e)}), 400
    except Exception as e:
        return jsonify(format_error_payload(e, "주문 사전검증 실패", exchange=exchange)), 500

    order_price = precheck["reference_price"]
    total_amount = precheck["estimated_amount"]
    normalized_precheck_qty = precheck.get("quantity")
    if normalized_precheck_qty not in (None, ""):
        try:
            normalized_precheck_qty = float(normalized_precheck_qty)
        except (TypeError, ValueError):
            return jsonify({"success": False, "message": "사전검증 수량 포맷이 올바르지 않습니다."}), 400
        if not math.isfinite(normalized_precheck_qty) or normalized_precheck_qty <= 0:
            return jsonify({"success": False, "message": "사전검증 수량은 0보다 큰 유한한 숫자여야 합니다."}), 400
        qty = normalized_precheck_qty

    if precheck.get("exceeds_real_order_limit"):
        return jsonify({
            "success": False,
            "message": "실거래 1회 주문 한도 100,000원을 초과했습니다. 수량 또는 가격을 낮춰 주세요.",
        }), 400

    if precheck.get("is_market_closed"):
        return jsonify({"success": False, "message": precheck.get("market_status_message") or "현재는 거래가 불가능한 시간(또는 휴장일)입니다."}), 400

    if precheck.get("futures_real_blocked"):
        return jsonify({
            "success": False,
            "message": "바이낸스 선물 실거래는 현재 잠겨 있습니다. 먼저 MOCK/TESTNET 모의투자로 검증하거나 BINANCE_FUTURES_REAL_ENABLED=true 설정 후 다시 시도하세요."
        }), 400

    if precheck.get("insufficient_permission"):
        return jsonify({
            "success": False,
            "message": precheck.get("permission_message") or "해당 마켓의 거래 권한이 없습니다."
        }), 400

    if precheck["insufficient_cash"]:
        return jsonify({"success": False, "message": "예수금보다 큰 주문입니다. 주문 수량 또는 단가를 조정해 주세요."}), 400

    if precheck["insufficient_holding"]:
        return jsonify({"success": False, "message": "보유 수량을 초과하는 매도 주문입니다."}), 400

    if precheck.get("balance_check_failed"):
        return jsonify({
            "success": False,
            "message": "주문에 필요한 잔고 또는 보유수량을 확인하지 못했습니다. 계좌 연결 상태를 확인해 주세요.",
        }), 400

    if not approval_proposal:
        try:
            manual_idempotency_key = _normalize_manual_order_idempotency_key(
                data.get("idempotency_key")
                or request.headers.get("Idempotency-Key")
            )
        except ValueError as error:
            return jsonify({"success": False, "message": str(error)}), 400

        manual_order_data = {
            "exchange": exchange,
            "symbol": symbol,
            "action": action,
            "order_type": order_type,
            "broker_env": broker_env,
            "quantity": qty,
            "price": order_price,
            "auto_exit": auto_exit,
            "target_profit_rate": target_profit_rate if auto_exit else None,
            "stop_loss_rate": stop_loss_rate if auto_exit else None,
            "auto_exit_execution_mode": auto_exit_execution_mode,
            "auto_restart_on_partial_fill": (
                auto_restart_on_partial_fill if auto_exit else False
            ),
            **(precheck.get("futures_options") or {}),
        }
        try:
            manual_proposal, was_created = _create_or_load_manual_order_proposal(
                auth_header,
                user_id,
                manual_idempotency_key,
                manual_order_data,
            )
        except ValueError as error:
            return jsonify({
                "success": False,
                "message": str(error),
                "error": {
                    "title": "멱등성 키 재사용 충돌",
                    "message": str(error),
                    "action": "주문 조건별로 새 UUID 키를 생성해 다시 요청해 주세요.",
                    "code": "IDEMPOTENCY_KEY_REUSED",
                    "raw_message": "",
                },
            }), 409
        except Exception as error:
            return jsonify(format_error_payload(
                error,
                "수동 주문 멱등성 레코드 생성 실패",
                exchange=exchange,
            )), 500

        if not was_created and str(manual_proposal.get("status") or "").upper() != "PENDING":
            return jsonify({
                "success": False,
                "message": "같은 수동 주문이 이미 전송 중이거나 처리되었습니다.",
                "error": {
                    "title": "중복 주문 전송 차단",
                    "message": "동일한 idempotency_key의 주문 이력이 존재합니다.",
                    "action": "같은 주문을 다시 보내지 말고 거래내역과 거래소 주문 상태를 확인해 주세요.",
                    "code": "MANUAL_ORDER_ALREADY_SUBMITTED",
                    "raw_message": "",
                },
                "order_id": manual_proposal.get("external_order_id"),
                "status": manual_proposal.get("status"),
            }), 409
        approval_proposal = manual_proposal

    if approval_proposal:
        claimed = _claim_trade_proposal_for_execution(
            auth_header,
            approval_proposal["id"],
        )
        if not claimed:
            return jsonify({
                "success": False,
                "message": "이미 승인·거절·실행 중인 매매 제안입니다. 거래내역을 새로고침해 상태를 확인하세요.",
            }), 409
        approval_proposal = claimed

    # 4. 주문 실행
    client = None
    try:
        if exchange == "TOSS":
            client = _build_exchange_client(exchange, broker_env, record, access_key, secret_key)
            order_res = client.place_order(symbol=symbol, qty=qty, side=action, ord_type=order_type, price=order_price)
        elif exchange == "KIS":
            client = _build_exchange_client(exchange, broker_env, record, access_key, secret_key)
            order_res = client.place_order(symbol=symbol, qty=qty, side=action, ord_type=order_type, price=order_price)
        elif exchange == "COINONE":
            client = _build_exchange_client(exchange, broker_env, record, access_key, secret_key)
            order_res = client.place_order(symbol=symbol, qty=qty, side=action, ord_type=order_type, price=order_price)
        elif exchange == "BINANCE":
            client = _build_exchange_client(exchange, broker_env, record, access_key, secret_key)
            order_res = client.place_order(symbol=symbol, qty=qty, side=action, ord_type=order_type, price=order_price)
        elif exchange == "BINANCE_UM_FUTURES":
            client = _build_exchange_client(exchange, broker_env, record, access_key, secret_key)
            order_res = client.place_order(
                symbol=symbol,
                qty=qty,
                side=action,
                ord_type=order_type,
                price=order_price,
                position_side=precheck["futures_options"]["position_side"],
                reduce_only=precheck["futures_options"]["reduce_only"],
                leverage=precheck["futures_options"]["leverage"],
                margin_type=precheck["futures_options"]["margin_type"],
            )
        else:
            return jsonify({"success": False, "message": f"{exchange} 거래소는 현재 수동 주문 기능이 지원되지 않습니다."}), 400
    except MarketClosedError:
        if approval_proposal:
            _patch_trade_proposal(
                auth_header,
                approval_proposal["id"],
                {"status": "FAILED", "failure_reason": MARKET_CLOSED_ORDER_MESSAGE},
            )
        return jsonify({"success": False, "message": MARKET_CLOSED_ORDER_MESSAGE}), 400
    except Exception as e:
        if approval_proposal:
            _patch_trade_proposal(
                auth_header,
                approval_proposal["id"],
                {"status": "FAILED", "failure_reason": "주문 전송 실패"},
            )
        if is_market_closed_order_error(str(e)):
            return jsonify({"success": False, "message": MARKET_CLOSED_ORDER_MESSAGE}), 400
        if exchange in ("KIS", "TOSS") and not is_stock_order_market_open(exchange, symbol):
            return jsonify({"success": False, "message": MARKET_CLOSED_ORDER_MESSAGE}), 400
        current_app.logger.exception("주문 전송 실패: exchange=%s symbol=%s broker_env=%s", exchange, symbol, broker_env)
        return jsonify(format_error_payload(e, "주문 전송 실패", exchange=exchange)), 500

    # 5. 주문 체결 성공 후 자동 감시(Stop-loss, Take-profit) 바인딩
    if not isinstance(order_res, dict):
        current_app.logger.error("거래소 주문 응답 형식이 올바르지 않습니다: exchange=%s", exchange)
        order_res = {"status": "UNKNOWN", "raw": None}

    proposal_id = str(approval_proposal["id"] if approval_proposal else uuid.uuid4())
    initial_order_status = _infer_trade_status_from_order_status(
        order_res,
        fallback="APPROVED",
    )
    initial_receipt = {
        "id": proposal_id,
        "user_id": user_id,
        "exchange": exchange,
        "asset_type": "STOCK" if exchange in ("TOSS", "KIS") else "CRYPTO",
        "ticker": symbol,
        "symbol": symbol,
        "broker_env": broker_env,
        "side": action.upper(),
        "price": order_price,
        "volume": qty,
        "ord_type": order_type.upper(),
        "client_order_id": order_res.get("client_order_id"),
        "external_order_org_no": order_res.get("order_org_no"),
        "external_order_id": order_res.get("order_id"),
        "status": initial_order_status,
        "raw_order_payload": _merge_manual_order_payload_marker(
            approval_proposal,
            {"order": order_res.get("raw")},
        ),
    }
    try:
        _patch_trade_proposal_returning(
            auth_header,
            user_id,
            proposal_id,
            initial_receipt,
        )
    except Exception:
        current_app.logger.exception(
            "외부 주문 직후 영수증 저장 실패: proposal_id=%s order_id=%s exchange=%s",
            proposal_id,
            order_res.get("order_id"),
            exchange,
        )
        try:
            if not _recover_order_receipt(auth_header, user_id, initial_receipt):
                raise RuntimeError("주문 영수증 최소 복구가 반영되지 않았습니다.")
        except Exception:
            current_app.logger.exception(
                "외부 주문 직후 영수증 복구 실패: proposal_id=%s order_id=%s exchange=%s",
                proposal_id,
                order_res.get("order_id"),
                exchange,
            )
            return jsonify({
                "success": False,
                "message": "거래소 주문이 접수되었을 수 있으나 주문 식별자를 저장하지 못했습니다.",
                "error": {
                    "title": "주문 상태 확인 필요",
                    "message": "외부 주문 직후 거래내역 영수증 저장을 확인하지 못했습니다.",
                    "action": "같은 주문을 다시 전송하지 말고 거래소 주문내역을 먼저 확인한 뒤 관리자에게 문의해 주세요.",
                    "code": "ORDER_RECEIPT_PERSIST_FAILED",
                    "raw_message": "",
                },
                "order_id": order_res.get("order_id"),
                "status": order_res.get("status"),
            }), 503

    try:
        order_status_for_db = _infer_trade_status_from_order_status(
            order_res,
            fallback="APPROVED",
        )
        if exchange == "KIS":
            order_status_for_db, kis_status_detail = _resolve_kis_submission_status(
                client,
                symbol=symbol,
                side=action,
                qty=qty,
                previous_holding_qty=precheck.get("holding_qty"),
                order_res=order_res,
            )
            order_res = {
                **order_res,
                "post_order_status_check": kis_status_detail,
            }
    except Exception:
        current_app.logger.exception(
            "주문 접수 후 상태 확인 실패: exchange=%s symbol=%s broker_env=%s",
            exchange,
            symbol,
            broker_env,
        )
        order_status_for_db = "APPROVED"
        order_res = {
            **order_res,
            "post_order_status_check": {
                "status": "UNKNOWN",
                "message": "주문은 접수되었으며 상태 동기화가 필요합니다.",
            },
        }

    auto_exit_result = None
    if (
        auto_exit
        and action.upper() == "BUY"
        and order_status_for_db not in {"FAILED", "CANCELED"}
    ):
        execution_mode = auto_exit_execution_mode

        # asset_type 및 market_country 판정
        asset_type = "STOCK" if exchange in ("TOSS", "KIS") else "CRYPTO"
        market_country = None
        if asset_type == "STOCK":
            try:
                market_country = determine_market_country(symbol)
            except Exception:
                current_app.logger.exception(
                    "주문 접수 후 시장 구분 실패: exchange=%s symbol=%s",
                    exchange,
                    symbol,
                )

        try:
            rule_data = {
                "user_id": user_id,
                "exchange": exchange,
                "asset_type": asset_type,
                "ticker": symbol,
                "symbol": symbol,
                "broker_env": broker_env,
                "market_country": market_country,
                "entry_price": order_price,
                "investment_amount": total_amount,
                "quantity": qty,
                "target_profit_rate": target_profit_rate,
                "stop_loss_rate": stop_loss_rate,
                "execution_mode": execution_mode,
                "entry_order_proposal_id": proposal_id,
                "auto_restart_on_partial_fill": auto_restart_on_partial_fill,
                "status": "RUNNING"
            }
            # Supabase에 감시 조건 등록
            try:
                query_supabase(auth_header, "auto_trading_rules", "POST", json_data=rule_data)
                auto_exit_result = "감시 조건 등록 완료" if execution_mode == "PROPOSAL" else "자동매도 감시 조건 등록 완료"
            except Exception:
                legacy_rule_data = {
                    key: rule_data[key]
                    for key in (
                        "user_id",
                        "exchange",
                        "asset_type",
                        "ticker",
                        "entry_price",
                        "investment_amount",
                        "target_profit_rate",
                        "stop_loss_rate",
                        "status",
                    )
                    if key in rule_data
                }
                query_supabase(auth_header, "auto_trading_rules", "POST", json_data=legacy_rule_data)
                auto_exit_result = "감시 조건 등록 완료 - DB 마이그레이션 적용 전이라 자동매도 실행 모드는 저장되지 않았습니다."
        except Exception as e:
            current_app.logger.warning("자동감시 조건 등록 실패: %s", e)
            auto_exit_result = "감시 조건 등록 실패 - 주문은 접수되었지만 익절/손절 감시 규칙은 저장되지 않았습니다."

    # 6. 주문 이력 trade_proposals에 주문 접수 결과를 저장합니다.
    asset_type = "STOCK" if exchange in ("TOSS", "KIS") else "CRYPTO"
    market_country = None
    if asset_type == "STOCK":
        try:
            market_country = determine_market_country(symbol)
        except Exception:
            current_app.logger.exception(
                "주문 이력 시장 구분 실패: exchange=%s symbol=%s",
                exchange,
                symbol,
            )
    currency = "KRW" if (exchange not in ("BINANCE", "BINANCE_UM_FUTURES") and market_country != "US") else "USD"
    proposal_data = {
        "id": proposal_id,
        "user_id": user_id,
        "exchange": exchange,
        "asset_type": asset_type,
        "ticker": symbol,
        "symbol": symbol,
        "broker_env": broker_env,
        "side": action.upper(),
        "price": order_price,
        "volume": qty,
        "ord_type": order_type.upper(),
        "market_country": market_country,
        "currency": currency,
        "client_order_id": order_res.get("client_order_id"),
        "external_order_org_no": order_res.get("order_org_no"),
        "external_order_id": order_res.get("order_id"),
        "raw_order_payload": _merge_manual_order_payload_marker(
            approval_proposal,
            {
                "order": order_res.get("raw"),
                "post_order_status_check": order_res.get("post_order_status_check"),
            },
        ),
        "status": order_status_for_db,
    }
    if order_status_for_db in {"FAILED", "CANCELED"}:
        proposal_data["failure_reason"] = "거래소가 주문을 실패 또는 취소 상태로 반환했습니다."

    order_history_recovered = False
    order_history_persist_failed = False
    try:
        if approval_proposal:
            _patch_trade_proposal_returning(
                auth_header,
                user_id,
                proposal_id,
                proposal_data,
            )
        else:
            _insert_trade_proposal_with_schema_fallback(auth_header, proposal_data)
    except Exception:
        current_app.logger.exception(
            "주문 이력 상세 저장 실패: proposal_id=%s order_id=%s exchange=%s",
            proposal_id,
            order_res.get("order_id"),
            exchange,
        )
        try:
            order_history_recovered = _recover_order_receipt(
                auth_header,
                user_id,
                proposal_data,
            )
            if not order_history_recovered:
                order_history_persist_failed = True
        except Exception:
            order_history_persist_failed = True
            current_app.logger.exception(
                "주문 이력 최소 복구 실패: proposal_id=%s order_id=%s exchange=%s",
                proposal_id,
                order_res.get("order_id"),
                exchange,
            )

    if order_history_persist_failed:
        return jsonify({
            "success": False,
            "message": "거래소 주문이 접수되었을 수 있으나 주문 이력 저장을 확인하지 못했습니다.",
            "error": {
                "title": "주문 상태 확인 필요",
                "message": "외부 주문 식별자를 거래내역에 저장하지 못했습니다.",
                "action": "같은 주문을 다시 전송하지 말고 거래소 주문내역을 먼저 확인한 뒤 관리자에게 문의해 주세요.",
                "code": "ORDER_RECEIPT_PERSIST_FAILED",
                "raw_message": "",
            },
            "order_id": order_res.get("order_id"),
            "status": order_res.get("status"),
        }), 503

    response_success = order_status_for_db not in {"FAILED", "CANCELED"}
    if not response_success:
        return jsonify({
            "success": False,
            "message": "거래소가 주문을 접수하지 않았거나 즉시 취소했습니다.",
            "error": {
                "title": "주문 미접수 또는 취소",
                "message": "거래소가 실패·거절·취소 상태를 반환했습니다.",
                "action": "같은 주문을 바로 다시 보내지 말고 거래내역과 거래소 주문 상태를 확인한 뒤 주문 조건을 수정해 주세요.",
                "code": "ORDER_NOT_ACCEPTED",
                "raw_message": str(order_res.get("status") or "")[:64],
            },
            "order_id": order_res.get("order_id"),
            "status": order_res.get("status"),
            "auto_exit": auto_exit_result,
        }), 409
    response_payload = {
        "success": True,
        "message": (
            "주문이 전송되었고 기본 주문 식별자만 복구했습니다. 거래내역 동기화를 확인해 주세요."
            if order_history_recovered
            else "주문이 성공적으로 전송되었습니다."
        ),
        "order_id": order_res.get("order_id"),
        "status": order_res.get("status"),
        "auto_exit": auto_exit_result,
    }
    return jsonify(response_payload)


@trade_bp.route("/api/trade/proposal/approve", methods=["POST"])
def approve_trade_proposal():
    """승인 카드에서만 PENDING 매매 제안을 주문으로 전환합니다."""
    return place_manual_order()


@trade_bp.route("/api/trade/proposal/reject", methods=["POST"])
def reject_trade_proposal():
    """사용자 승인 카드의 거절 동작을 처리합니다."""
    auth_header = request.headers.get("Authorization")
    if not auth_header:
        return jsonify({"success": False, "message": "인증 헤더가 누락되었습니다."}), 401

    try:
        user_id, _ = get_user_id_from_header(auth_header)
        proposal_id = str((request.json or {}).get("proposal_id") or "").strip()
        if not proposal_id:
            return jsonify({"success": False, "message": "proposal_id가 필요합니다."}), 400
        updated = _reject_pending_trade_proposal(auth_header, user_id, proposal_id)
        if not updated:
            return jsonify({
                "success": False,
                "message": "이미 승인·거절·실행 중이거나 찾을 수 없는 매매 제안입니다.",
            }), 409
        return jsonify({"success": True, "data": updated, "message": "매매 제안을 거절했습니다."})
    except ValueError as error:
        return jsonify({"success": False, "message": str(error)}), 400
    except Exception as error:
        return jsonify(format_error_payload(error, "매매 제안 거절 실패")), 500


@trade_bp.route("/api/trade/orders/sync-status", methods=["POST"])
def sync_order_statuses():
    """
    로그인 사용자의 앱 주문 거래내역을 실제 거래소 주문 상태와 맞춰 보정합니다.
    """
    auth_header = request.headers.get("Authorization")
    if not auth_header:
        return jsonify({"success": False, "message": "인증 헤더가 필요합니다."}), 401

    try:
        user_id, _ = get_user_id_from_header(auth_header)
    except Exception as e:
        return jsonify({"success": False, "message": f"인증 실패: {str(e)}"}), 401

    try:
        proposals = query_supabase(
            auth_header,
            "trade_proposals",
            "GET",
            params={
                "user_id": f"eq.{user_id}",
                "exchange": "eq.KIS",
                "limit": "100",
                "order": "created_at.desc",
            },
        ) or []
    except Exception as e:
        return jsonify(format_error_payload(e, "거래내역 조회 실패", exchange="KIS")), 500

    clients = {}
    synced_count = 0
    checked_count = 0
    errors = []

    try:
        toss_proposals = query_supabase(
            auth_header,
            "trade_proposals",
            "GET",
            params={
                "user_id": f"eq.{user_id}",
                "exchange": "eq.TOSS",
                "limit": "100",
                "order": "created_at.desc",
            },
        ) or []
    except Exception as e:
        toss_proposals = []
        errors.append(f"Toss order sync query failed: {str(e)[:160]}")

    toss_clients = {}
    for proposal in toss_proposals:
        proposal_id = proposal.get("id")
        symbol = proposal.get("symbol") or proposal.get("ticker")
        order_id = proposal.get("external_order_id")
        status = str(proposal.get("status") or "").upper()
        if status in {"EXECUTED", "CANCELED", "CANCELLED", "REJECTED", "FAILED", "EXPIRED"}:
            continue
        if not proposal_id or not symbol or not order_id:
            continue

        broker_env = _resolve_proposal_broker_env(proposal)
        try:
            if broker_env not in toss_clients:
                record, access_key, secret_key = _load_user_exchange_record(
                    auth_header,
                    user_id,
                    "TOSS",
                    broker_env,
                )
                toss_clients[broker_env] = _build_exchange_client("TOSS", broker_env, record, access_key, secret_key)
            client = toss_clients[broker_env]
            checked_count += 1

            current_order = client.get_order_status(order_id)
            raw_status = str(current_order.get("status") or "").upper()
            executed_qty = float(current_order.get("executed_qty") or 0)
            requested_qty = float(proposal.get("volume") or 0)
            if raw_status in {"FILLED", "EXECUTED", "DONE", "COMPLETED"} or (requested_qty > 0 and executed_qty >= requested_qty):
                next_status = "EXECUTED"
            elif raw_status in {"CANCELED", "CANCELLED"}:
                next_status = "CANCELED"
            elif raw_status in {"REJECTED", "FAILED", "EXPIRED", "EXPIRED_IN_MATCH"}:
                next_status = "FAILED"
            elif executed_qty > 0:
                next_status = "PARTIALLY_FILLED"
            else:
                next_status = "ORDERED"

            sync_detail = {
                "account": {
                    "exchange": "TOSS",
                    "broker_env": broker_env,
                },
                "order_status": current_order,
                "normalized_status": next_status,
            }
            patch_payload = {
                "status": next_status,
                "broker_env": broker_env,
                "failure_reason": None,
                "raw_order_payload": {"sync_status_check": sync_detail},
            }
            if next_status == "CANCELED":
                patch_payload["canceled_at"] = datetime.utcnow().isoformat() + "Z"
            if next_status == "FAILED":
                patch_payload["failure_reason"] = f"TOSS order status: {raw_status or 'FAILED'}"
            _patch_trade_proposal(auth_header, proposal_id, patch_payload)
            synced_count += 1
        except Exception as exc:
            errors.append(f"TOSS {symbol}: {str(exc)[:180]}")

    for proposal in proposals:
        proposal_id = proposal.get("id")
        symbol = proposal.get("symbol") or proposal.get("ticker")
        order_id = proposal.get("external_order_id")
        status = str(proposal.get("status") or "").upper()
        if status in {"EXECUTED", "CANCELED", "REJECTED"}:
            continue
        if not proposal_id or not symbol:
            continue

        account_candidates = _get_trade_account_candidates(auth_header, user_id, "KIS", proposal)
        if not account_candidates:
            errors.append(f"{symbol}: 확인 가능한 KIS 계좌가 없습니다.")
            continue
        allow_balance_fallback = len(account_candidates) == 1

        for account_meta in account_candidates:
            broker_env = account_meta.get("env")
            account_key = account_meta.get("account_key")
            if not broker_env:
                continue
            try:
                if account_key not in clients:
                    record = account_meta.get("record")
                    if record:
                        access_key = current_app.crypto.decrypt(record.get("encrypted_access_key"))
                        secret_key = current_app.crypto.decrypt(record.get("encrypted_secret_key"))
                    else:
                        record, access_key, secret_key = _load_user_exchange_record(auth_header, user_id, "KIS", broker_env)
                    clients[account_key] = _build_exchange_client("KIS", broker_env, record, access_key, secret_key)
                client = clients[account_key]
                checked_count += 1

                current_order = {"is_modifiable": False, "lookup_skipped": not bool(order_id)}
                if order_id:
                    try:
                        current_order = client.get_modifiable_order(order_id, order_org_no=_resolve_order_org_no(proposal))
                    except Exception as modifiable_error:
                        current_order = {
                            "is_modifiable": False,
                            "lookup_error": str(modifiable_error)[:200],
                        }
                if current_order.get("is_modifiable"):
                    break

                side = str(proposal.get("side") or "").upper()
                volume = float(proposal.get("volume") or 0)
                execution_status = client.get_order_execution_status(order_id or "", symbol=symbol, lookback_days=30)
                sync_detail = {
                    "account": {
                        "exchange": "KIS",
                        "broker_env": broker_env,
                        "account_label": account_meta.get("account_label"),
                    },
                    "modifiable_order": current_order,
                    "execution_status": execution_status,
                }
                if execution_status.get("status") == "CANCELED":
                    _patch_trade_proposal(auth_header, proposal_id, {
                        "status": "CANCELED",
                        "broker_env": broker_env,
                        "failure_reason": None,
                        "raw_order_payload": {"sync_status_check": sync_detail},
                    })
                    synced_count += 1
                    break
                if execution_status.get("status") == "EXECUTED" or execution_status.get("executed_qty", 0) >= volume > 0:
                    _patch_trade_proposal(auth_header, proposal_id, {
                        "status": "EXECUTED",
                        "broker_env": broker_env,
                        "failure_reason": None,
                        "raw_order_payload": {"sync_status_check": sync_detail},
                    })
                    synced_count += 1
                    break

                current_qty = _get_holding_qty_from_balance(client, symbol) if allow_balance_fallback else None
                if side == "BUY" and current_qty is not None and current_qty >= volume and volume > 0:
                    sync_detail["current_holding_qty"] = current_qty
                    _patch_trade_proposal(auth_header, proposal_id, {
                        "status": "EXECUTED",
                        "broker_env": broker_env,
                        "failure_reason": None,
                        "raw_order_payload": {"sync_status_check": sync_detail},
                    })
                    synced_count += 1
                    break
            except Exception as exc:
                errors.append(str(exc)[:200])

    try:
        coinone_proposals = query_supabase(
            auth_header,
            "trade_proposals",
            "GET",
            params={
                "user_id": f"eq.{user_id}",
                "exchange": "eq.COINONE",
                "limit": "100",
                "order": "created_at.desc",
            },
        ) or []
    except Exception as e:
        coinone_proposals = []
        errors.append(f"Coinone order sync query failed: {str(e)[:160]}")

    coinone_clients = {}
    for proposal in coinone_proposals:
        proposal_id = proposal.get("id")
        symbol = proposal.get("symbol") or proposal.get("ticker")
        order_id = proposal.get("external_order_id")
        status = str(proposal.get("status") or "").upper()
        if status in {"EXECUTED", "CANCELED", "CANCELLED", "REJECTED", "FAILED"}:
            continue
        if not proposal_id or not symbol or not order_id:
            continue

        broker_env = _resolve_proposal_broker_env(proposal)
        try:
            if broker_env not in coinone_clients:
                record, access_key, secret_key = _load_user_exchange_record(
                    auth_header,
                    user_id,
                    "COINONE",
                    broker_env,
                )
                coinone_clients[broker_env] = _build_exchange_client("COINONE", broker_env, record, access_key, secret_key)
            client = coinone_clients[broker_env]
            checked_count += 1

            current_order = client.get_order_status(order_id, symbol=symbol)
            next_status, coinone_detail = _normalize_coinone_synced_status(
                current_order,
                requested_qty=proposal.get("volume"),
            )
            sync_detail = {
                "account": {
                    "exchange": "COINONE",
                    "broker_env": broker_env,
                },
                "order_status": current_order,
                "normalized": coinone_detail,
            }
            patch_payload = {
                "status": next_status,
                "broker_env": broker_env,
                "failure_reason": None,
                "raw_order_payload": {"sync_status_check": sync_detail},
            }
            if next_status == "CANCELED":
                patch_payload["canceled_at"] = datetime.utcnow().isoformat() + "Z"
            if next_status == "FAILED":
                patch_payload["failure_reason"] = f"Coinone order status: {coinone_detail.get('raw_status') or 'FAILED'}"
            _patch_trade_proposal(auth_header, proposal_id, patch_payload)
            synced_count += 1
        except Exception as exc:
            errors.append(f"Coinone {symbol}: {str(exc)[:180]}")

    binance_clients = {}
    for sync_exchange in ("BINANCE", "BINANCE_UM_FUTURES"):
        try:
            binance_proposals = query_supabase(
                auth_header,
                "trade_proposals",
                "GET",
                params={
                    "user_id": f"eq.{user_id}",
                    "exchange": f"eq.{sync_exchange}",
                    "limit": "100",
                    "order": "created_at.desc",
                },
            ) or []
        except Exception as e:
            binance_proposals = []
            errors.append(f"{sync_exchange} order sync query failed: {str(e)[:160]}")

        for proposal in binance_proposals:
            proposal_id = proposal.get("id")
            symbol = proposal.get("symbol") or proposal.get("ticker")
            order_id = proposal.get("external_order_id")
            status = str(proposal.get("status") or "").upper()
            if status in {"EXECUTED", "CANCELED", "CANCELLED", "REJECTED", "FAILED", "EXPIRED"}:
                continue
            if not proposal_id or not symbol or not order_id:
                continue

            broker_env = _resolve_proposal_broker_env(proposal)
            client_key = f"{sync_exchange}:{broker_env}"
            try:
                if client_key not in binance_clients:
                    record, access_key, secret_key = _load_user_exchange_record(
                        auth_header,
                        user_id,
                        sync_exchange,
                        broker_env,
                    )
                    binance_clients[client_key] = _build_exchange_client(sync_exchange, broker_env, record, access_key, secret_key)
                client = binance_clients[client_key]
                checked_count += 1

                current_order = client.get_order_status(order_id, symbol=symbol)
                raw_status = str(current_order.get("status") or "").upper()
                executed_qty = float(current_order.get("executed_qty") or 0)
                requested_qty = float(proposal.get("volume") or 0)
                if raw_status in {"FILLED", "EXECUTED"} or (requested_qty > 0 and executed_qty >= requested_qty):
                    next_status = "EXECUTED"
                elif raw_status in {"CANCELED", "CANCELLED"}:
                    next_status = "CANCELED"
                elif raw_status in {"REJECTED", "FAILED", "EXPIRED"}:
                    next_status = "FAILED"
                elif executed_qty > 0:
                    next_status = "PARTIALLY_FILLED"
                else:
                    next_status = "ORDERED"

                sync_detail = {
                    "account": {
                        "exchange": sync_exchange,
                        "broker_env": broker_env,
                    },
                    "order_status": current_order,
                    "normalized_status": next_status,
                }
                patch_payload = {
                    "status": next_status,
                    "broker_env": broker_env,
                    "failure_reason": None,
                    "raw_order_payload": {"sync_status_check": sync_detail},
                }
                if next_status == "CANCELED":
                    patch_payload["canceled_at"] = datetime.utcnow().isoformat() + "Z"
                if next_status == "FAILED":
                    patch_payload["failure_reason"] = f"{sync_exchange} order status: {raw_status or 'FAILED'}"
                _patch_trade_proposal(auth_header, proposal_id, patch_payload)
                synced_count += 1
            except Exception as exc:
                errors.append(f"{sync_exchange} {symbol}: {str(exc)[:180]}")

    return jsonify({
        "success": True,
        "checked_count": checked_count,
        "synced_count": synced_count,
        "errors": errors[:5],
    })


@trade_bp.route("/api/trade/estimated-holdings", methods=["POST"])
def get_estimated_holdings():
    """
    체결완료 거래내역을 기준으로 추정 보유종목을 만들고 현재가로 손익을 계산합니다.
    """
    auth_header = request.headers.get("Authorization")
    if not auth_header:
        return jsonify({"success": False, "message": "인증 헤더가 필요합니다."}), 401

    try:
        user_id, _ = get_user_id_from_header(auth_header)
    except Exception as e:
        return jsonify({"success": False, "message": f"인증 실패: {str(e)}"}), 401

    show_mock_assets = bool((request.json or {}).get("show_mock_assets", True))

    try:
        rows = query_supabase(
            auth_header,
            "trade_proposals",
            "GET",
            params={
                "user_id": f"eq.{user_id}",
                "status": "eq.EXECUTED",
                "order": "created_at.asc",
            },
        ) or []
    except Exception as e:
        return jsonify(format_error_payload(e, "거래내역 조회 실패")), 500

    grouped = {}
    account_lookup_clients = {}
    for row in rows:
        exchange = str(row.get("exchange") or "").upper()
        account_candidates = _get_trade_account_candidates(auth_header, user_id, exchange, row)
        if exchange == "KIS":
            account_meta = _select_kis_account_meta_for_trade(row, account_candidates, account_lookup_clients)
        elif len(account_candidates) == 1:
            account_meta = account_candidates[0]
        elif str(row.get("broker_env") or "").upper() and account_candidates:
            account_meta = account_candidates[0]
        else:
            account_meta = None

        if not account_meta:
            account_meta = {
                "exchange": exchange,
                "env": str(row.get("broker_env") or "").upper(),
                "account_label": f"{exchange} 계좌확인필요" if exchange else "계좌확인필요",
                "account_key": f"{exchange}:UNKNOWN",
                "record": None,
            }
        env = account_meta.get("env") or ""
        if not show_mock_assets and env == "MOCK":
            continue

        symbol = str(row.get("symbol") or row.get("ticker") or "").strip().upper()
        if not symbol:
            continue

        asset_type = str(row.get("asset_type") or ("CRYPTO" if exchange in ("COINONE", "BINANCE") else "STOCK")).upper()
        key = f"{asset_type}:{account_meta.get('account_key')}:{symbol}"
        side = str(row.get("side") or "").upper()
        price = float(row.get("price") or 0)
        volume = float(row.get("volume") or 0)
        if volume <= 0 and price > 0:
            volume = float(row.get("order_amount") or 0) / price
        if volume <= 0:
            continue

        current = grouped.get(key) or {
            "symbol": symbol,
            "name": _lookup_trade_symbol_name(symbol, row.get("name") or row.get("display_name") or symbol),
            "asset_type": asset_type,
            "exchange": exchange,
            "raw_exchange": exchange,
            "env": env,
            "account_label": account_meta.get("account_label"),
            "account_key": account_meta.get("account_key"),
            "account_record": account_meta.get("record"),
            "currency": row.get("currency") or ("USD" if exchange == "BINANCE" else "KRW"),
            "qty": 0.0,
            "buy_qty": 0.0,
            "buy_amount": 0.0,
            "last_price": 0.0,
        }
        if side == "SELL":
            current["qty"] -= volume
        else:
            current["qty"] += volume
            current["buy_qty"] += volume
            current["buy_amount"] += price * volume
        if price > 0:
            current["last_price"] = price
        grouped[key] = current

    try:
        transfer_rows = query_supabase(
            auth_header,
            "asset_transfer_proposals",
            "GET",
            params={
                "user_id": f"eq.{user_id}",
                "order": "created_at.desc",
                "limit": "1000",
            },
        ) or []
        _apply_crypto_transfer_deductions(grouped, _build_crypto_transfer_deductions(transfer_rows))
    except Exception:
        current_app.logger.warning("Estimated holdings transfer deduction failed", exc_info=True)

    clients = {}
    holdings = []
    for item in grouped.values():
        if item["qty"] <= 0:
            continue

        avg_price = item["buy_amount"] / item["buy_qty"] if item["buy_qty"] > 0 else item["last_price"]
        current_price = item["last_price"] or avg_price
        price_source = "TRADE_HISTORY"
        exchange = item["raw_exchange"]
        env = item["env"]

        try:
            if exchange in ("KIS", "TOSS") and item.get("account_record") and env:
                client_key = item["account_key"]
                if client_key not in clients:
                    record = item["account_record"]
                    access_key = current_app.crypto.decrypt(record.get("encrypted_access_key"))
                    secret_key = current_app.crypto.decrypt(record.get("encrypted_secret_key"))
                    clients[client_key] = _build_exchange_client(exchange, env, record, access_key, secret_key)
                price_data = clients[client_key].get_price(item["symbol"])
                live_price = float(price_data.get("current_price") or 0)
                if live_price > 0:
                    current_price = live_price
                    price_source = f"{exchange}_PRICE"
                price_output = (price_data.get("raw") or {}).get("output") or {}
                api_name = price_output.get("hts_kor_isnm") or price_output.get("prdt_name")
                if api_name:
                    item["name"] = api_name
        except Exception as exc:
            item["price_error"] = str(exc)[:200]

        profit = (current_price - avg_price) * item["qty"] if avg_price > 0 else 0.0
        profit_rate = ((current_price - avg_price) / avg_price) * 100 if avg_price > 0 else 0.0
        display_exchange = item.get("account_label") or (f"KIS {'모의' if env == 'MOCK' else '실전'}" if exchange == "KIS" else exchange)

        holdings.append({
            "symbol": item["symbol"],
            "name": item["name"],
            "display_name": item["name"],
            "qty": item["qty"],
            "avg_price": avg_price,
            "current_price": current_price,
            "profit": profit,
            "profit_rate": profit_rate,
            "currency": item["currency"],
            "exchange": display_exchange,
            "raw_exchange": exchange,
            "account_type": display_exchange,
            "account_label": display_exchange,
            "asset_type": item["asset_type"],
            "env": env,
            "source": "DB_ESTIMATED",
            "price_source": price_source,
        })

    return jsonify({"success": True, "data": {"holdings": holdings}})


@trade_bp.route("/api/trade/order/cancel", methods=["POST"])
def cancel_manual_order():
    """
    로그인 사용자의 미체결 주문을 취소합니다.
    실제 거래소 주문번호가 없는 PENDING 제안은 DB 상태만 CANCELED로 변경합니다.
    """
    auth_header = request.headers.get("Authorization")
    if not auth_header:
        return jsonify({"success": False, "message": "인증 헤더가 누락되었습니다."}), 401

    try:
        user_id, _ = get_user_id_from_header(auth_header)
    except Exception as e:
        return jsonify({"success": False, "message": f"인증 실패: {str(e)}"}), 401

    data = request.json or {}
    proposal_id = data.get("proposal_id")
    broker_env_override = data.get("broker_env")
    if not proposal_id:
        return jsonify({"success": False, "message": "proposal_id가 필요합니다."}), 400

    try:
        proposal = _load_user_trade_proposal(auth_header, user_id, proposal_id)
    except ValueError as e:
        return jsonify({"success": False, "message": str(e)}), 404
    except Exception as e:
        return jsonify(format_error_payload(e, "거래내역 조회 실패")), 500

    status = str(proposal.get("status") or "").upper()
    if status in {"EXECUTED", "CANCELED", "REJECTED", "FAILED"}:
        return jsonify({"success": False, "message": "이미 완료되었거나 취소할 수 없는 주문입니다."}), 400

    order_id = proposal.get("external_order_id")
    if not order_id:
        _patch_trade_proposal(auth_header, proposal_id, {
            "status": "CANCELED",
            "failure_reason": None,
            "canceled_at": datetime.utcnow().isoformat() + "Z",
        })
        return jsonify({"success": True, "message": "주문 제안이 취소되었습니다.", "status": "CANCELED"})

    exchange = proposal.get("exchange")
    broker_env = _resolve_proposal_broker_env(proposal, broker_env_override)
    if exchange not in ("TOSS", "KIS", "COINONE", "BINANCE", "BINANCE_UM_FUTURES"):
        return jsonify({"success": False, "message": f"{exchange} 주문 취소는 아직 지원하지 않습니다."}), 400

    current_status = {}
    try:
        record, access_key, secret_key = _load_user_exchange_record(auth_header, user_id, exchange, broker_env)
        client = _build_exchange_client(exchange, broker_env, record, access_key, secret_key)
        symbol = proposal.get("symbol") or proposal.get("ticker")
        try:
            current_status = client.get_order_status(order_id, symbol=symbol) if exchange in ("COINONE", "BINANCE", "BINANCE_UM_FUTURES") else client.get_order_status(order_id)
        except Exception as status_error:
            if exchange != "TOSS":
                raise
            current_app.logger.warning("Toss order status lookup failed before cancel: %s", status_error)
        if exchange != "KIS" and _is_terminal_order_status(current_status.get("status")):
            _patch_proposal_as_not_actionable(auth_header, proposal_id, current_status, "이미 체결 또는 종료된 주문이라 취소할 수 없습니다.")
            return jsonify({"success": False, "message": "이미 체결 또는 종료된 주문이라 취소할 수 없습니다.", "detail": current_status}), 400

        if exchange == "KIS":
            _ensure_kis_order_modifiable(auth_header, proposal_id, proposal, client)
            cancel_result = client.cancel_order(order_id, order_org_no=_resolve_order_org_no(proposal))
        elif exchange in ("COINONE", "BINANCE", "BINANCE_UM_FUTURES"):
            cancel_result = client.cancel_order(order_id, symbol=symbol)
        else:
            cancel_result = client.cancel_order(order_id)
        _patch_trade_proposal(auth_header, proposal_id, {
            "status": "CANCELED",
            "failure_reason": None,
            "canceled_at": datetime.utcnow().isoformat() + "Z",
        })
        return jsonify({
            "success": True,
            "message": "주문 취소 요청이 완료되었습니다.",
            "status": "CANCELED",
            "detail": cancel_result,
        })
    except ValueError as e:
        return jsonify({"success": False, "message": str(e)}), 400
    except Exception as e:
        if _is_already_canceled_order_error(e):
            _patch_trade_proposal(auth_header, proposal_id, {
                "status": "CANCELED",
                "failure_reason": "이미 취소된 주문으로 거래내역 상태를 취소완료로 갱신했습니다.",
                "canceled_at": datetime.utcnow().isoformat() + "Z",
                "raw_order_payload": {
                    "last_order_status": current_status or {},
                    "cancel_restricted_reason": str(e)[:500],
                },
            })
            return jsonify({
                "success": False,
                "message": "이미 취소된 주문입니다.",
                "detail": current_status,
            }), 400
        _patch_trade_proposal(auth_header, proposal_id, {
            "failure_reason": f"주문 취소 실패: {str(e)[:500]}",
        })
        return jsonify(format_error_payload(e, "주문 취소 실패", exchange=exchange)), 500


@trade_bp.route("/api/trade/order/modify", methods=["POST"])
def modify_manual_order():
    """
    로그인 사용자의 Toss 미체결 주문 가격 또는 수량을 정정합니다.
    """
    auth_header = request.headers.get("Authorization")
    if not auth_header:
        return jsonify({"success": False, "message": "인증 헤더가 누락되었습니다."}), 401

    try:
        user_id, _ = get_user_id_from_header(auth_header)
    except Exception as e:
        return jsonify({"success": False, "message": f"인증 실패: {str(e)}"}), 401

    data = request.json or {}
    proposal_id = data.get("proposal_id")
    new_price = data.get("price")
    new_quantity = data.get("quantity")
    broker_env_override = data.get("broker_env")

    if not proposal_id:
        return jsonify({"success": False, "message": "proposal_id가 필요합니다."}), 400
    if new_price in (None, "") and new_quantity in (None, ""):
        return jsonify({"success": False, "message": "정정할 가격 또는 수량이 필요합니다."}), 400

    try:
        proposal = _load_user_trade_proposal(auth_header, user_id, proposal_id)
    except ValueError as e:
        return jsonify({"success": False, "message": str(e)}), 404
    except Exception as e:
        return jsonify(format_error_payload(e, "거래내역 조회 실패")), 500

    status = str(proposal.get("status") or "").upper()
    if status in {"EXECUTED", "CANCELED", "REJECTED", "FAILED"}:
        return jsonify({"success": False, "message": "이미 완료되었거나 정정할 수 없는 주문입니다."}), 400

    order_id = proposal.get("external_order_id")
    if not order_id:
        return jsonify({"success": False, "message": "거래소 주문번호가 없어 실제 주문 정정을 할 수 없습니다."}), 400

    exchange = proposal.get("exchange")
    broker_env = _resolve_proposal_broker_env(proposal, broker_env_override)
    if exchange not in ("TOSS", "KIS"):
        return jsonify({"success": False, "message": f"{exchange} 주문 정정은 아직 지원하지 않습니다."}), 400

    current_status = {}
    try:
        price_value = float(new_price) if new_price not in (None, "") else None
        quantity_value = float(new_quantity) if new_quantity not in (None, "") else None
        if price_value is not None and price_value <= 0:
            return jsonify({"success": False, "message": "정정 가격은 0보다 커야 합니다."}), 400
        if quantity_value is not None and quantity_value <= 0:
            return jsonify({"success": False, "message": "정정 수량은 0보다 커야 합니다."}), 400

        record, access_key, secret_key = _load_user_exchange_record(auth_header, user_id, exchange, broker_env)
        client = _build_exchange_client(exchange, broker_env, record, access_key, secret_key)
        try:
            current_status = client.get_order_status(order_id)
        except Exception as status_error:
            if exchange != "TOSS":
                raise
            current_app.logger.warning("Toss order status lookup failed before modify: %s", status_error)
        if exchange != "KIS" and _is_terminal_order_status(current_status.get("status")):
            _patch_proposal_as_not_actionable(auth_header, proposal_id, current_status, "이미 체결 또는 종료된 주문이라 정정할 수 없습니다.")
            return jsonify({"success": False, "message": "이미 체결 또는 종료된 주문이라 정정할 수 없습니다.", "detail": current_status}), 400

        market_country = proposal.get("market_country")
        if exchange == "TOSS" and market_country == "US" and quantity_value is not None:
            return jsonify({"success": False, "message": "Toss 해외주식 주문은 가격 정정만 지원합니다."}), 400

        if exchange == "KIS":
            modifiable_order = _ensure_kis_order_modifiable(auth_header, proposal_id, proposal, client)
            remaining_qty = float(modifiable_order.get("remaining_qty") or 0)
            if quantity_value is None:
                quantity_value = remaining_qty
            if price_value is None:
                price_value = float(proposal.get("price") or 0)
            if quantity_value <= 0 or price_value <= 0:
                return jsonify({"success": False, "message": "KIS 정정에는 유효한 가격과 수량이 필요합니다."}), 400
            if remaining_qty > 0 and quantity_value > remaining_qty:
                return jsonify({
                    "success": False,
                    "message": f"KIS 미체결 잔량({remaining_qty:g}주)을 초과해 정정할 수 없습니다.",
                    "detail": modifiable_order,
                }), 400
            modify_result = client.modify_order(
                order_id,
                order_org_no=_resolve_order_org_no(proposal),
                price=price_value,
                quantity=quantity_value,
                ord_type=proposal.get("ord_type") or "LIMIT",
            )
        else:
            order_type_value = str(proposal.get("ord_type") or proposal.get("order_type") or "LIMIT").upper()
            remaining_qty = float(current_status.get("remaining_qty") or 0)
            if market_country != "US" and current_status and remaining_qty <= 0:
                return jsonify({"success": False, "message": "이미 체결되어 정정 가능한 수량이 없습니다.", "detail": current_status}), 400
            if market_country != "US" and quantity_value is None:
                quantity_value = remaining_qty if remaining_qty > 0 else float(proposal.get("volume") or 0)
                if quantity_value <= 0:
                    return jsonify({"success": False, "message": "Toss 국내주식 정정에는 유효한 주문 수량이 필요합니다."}), 400
            if market_country != "US" and remaining_qty > 0 and quantity_value is not None and quantity_value > remaining_qty:
                return jsonify({
                    "success": False,
                    "message": f"Toss 정정 가능수량({remaining_qty:g}주)을 초과해 정정할 수 없습니다.",
                    "detail": current_status,
                }), 400
            if order_type_value == "LIMIT" and price_value is None:
                price_value = float(proposal.get("price") or 0)
                if price_value <= 0:
                    return jsonify({"success": False, "message": "Toss 지정가 정정에는 유효한 주문 가격이 필요합니다."}), 400
            if order_type_value == "MARKET":
                price_value = None
            modify_result = client.modify_order(
                order_id,
                price=price_value,
                quantity=quantity_value,
                order_type=order_type_value,
            )
        patch_payload = {
            "status": "MODIFIED",
            "failure_reason": None,
            "modified_at": datetime.utcnow().isoformat() + "Z",
        }
        modified_order_id = modify_result.get("order_id")
        if modified_order_id:
            patch_payload["external_order_id"] = modified_order_id
        if price_value is not None:
            patch_payload["price"] = price_value
        if quantity_value is not None:
            patch_payload["volume"] = quantity_value
        _patch_trade_proposal(auth_header, proposal_id, patch_payload)

        return jsonify({
            "success": True,
            "message": "주문 정정 요청이 완료되었습니다.",
            "status": "MODIFIED",
            "detail": modify_result,
        })
    except ValueError as e:
        return jsonify({"success": False, "message": str(e)}), 400
    except Exception as e:
        if exchange == "TOSS" and _is_toss_action_restricted_error(e, "modify-restricted"):
            _patch_proposal_as_not_actionable(auth_header, proposal_id, current_status, "정정 가능수량이 없어 주문 상태를 종료 처리했습니다.")
            return jsonify({
                "success": False,
                "message": "정정 가능수량이 없습니다. 이미 체결 또는 종료된 주문으로 보여 거래내역 상태를 갱신했습니다.",
                "detail": current_status,
            }), 400
        current_app.logger.exception("주문 정정 실패: exchange=%s proposal_id=%s broker_env=%s", exchange, proposal_id, broker_env)
        _patch_trade_proposal(auth_header, proposal_id, {
            "failure_reason": f"주문 정정 실패: {str(e)[:500]}",
        })
        return jsonify(format_error_payload(e, "주문 정정 실패", exchange=exchange)), 500


@trade_bp.route("/api/trade/order/cancel-replace", methods=["POST"])
def cancel_replace_order():
    """
    Coinone/Binance 주문 제안을 취소하고 새 재주문 제안을 생성합니다.
    실제 거래소 주문번호가 있는 경우에는 거래소별 취소 API가 연결되기 전까지 차단합니다.
    """
    auth_header = request.headers.get("Authorization")
    if not auth_header:
        return jsonify({"success": False, "message": "인증 헤더가 누락되었습니다."}), 401

    try:
        user_id, _ = get_user_id_from_header(auth_header)
    except Exception as e:
        return jsonify({"success": False, "message": f"인증 실패: {str(e)}"}), 401

    data = request.json or {}
    proposal_id = data.get("proposal_id")
    new_price = data.get("price")
    new_quantity = data.get("quantity")
    if not proposal_id:
        return jsonify({"success": False, "message": "proposal_id가 필요합니다."}), 400
    if new_price in (None, "") and new_quantity in (None, ""):
        return jsonify({"success": False, "message": "재주문할 가격 또는 수량이 필요합니다."}), 400

    try:
        proposal = _load_user_trade_proposal(auth_header, user_id, proposal_id)
    except ValueError as e:
        return jsonify({"success": False, "message": str(e)}), 404
    except Exception as e:
        return jsonify(format_error_payload(e, "거래내역 조회 실패")), 500

    exchange = proposal.get("exchange")
    if exchange not in ("COINONE", "BINANCE", "BINANCE_UM_FUTURES"):
        return jsonify({"success": False, "message": "취소 후 재주문은 Coinone/Binance 주문에만 사용합니다."}), 400

    status = str(proposal.get("status") or "").upper()
    if status in {"EXECUTED", "CANCELED", "REJECTED", "FAILED"}:
        return jsonify({"success": False, "message": "이미 완료되었거나 재주문할 수 없는 주문입니다."}), 400

    try:
        price_value = float(new_price) if new_price not in (None, "") else float(proposal.get("price") or 0)
        quantity_value = float(new_quantity) if new_quantity not in (None, "") else float(proposal.get("volume") or 0)
        if price_value <= 0:
            return jsonify({"success": False, "message": "재주문 가격은 0보다 커야 합니다."}), 400
        if quantity_value <= 0:
            return jsonify({"success": False, "message": "재주문 수량은 0보다 커야 합니다."}), 400

        cancel_detail = None
        replacement_order = None
        external_order_id = proposal.get("external_order_id")
        broker_env = _resolve_proposal_broker_env(proposal, data.get("broker_env"))
        client = None
        if external_order_id:
            if exchange != "COINONE":
                return jsonify({
                    "success": False,
                    "message": f"{exchange} 실제 주문 취소 API 연결 전에는 거래소 주문번호가 있는 주문을 취소 후 재주문할 수 없습니다.",
                }), 400
            record, access_key, secret_key = _load_user_exchange_record(auth_header, user_id, exchange, broker_env)
            client = _build_exchange_client(exchange, broker_env, record, access_key, secret_key)
            cancel_detail = client.cancel_order(external_order_id, symbol=proposal.get("symbol") or proposal.get("ticker"))

        cancel_patch = {
            "status": "CANCELED",
            "failure_reason": None,
            "canceled_at": datetime.utcnow().isoformat() + "Z",
        }
        if cancel_detail:
            cancel_patch["raw_order_payload"] = {"cancel_replace_cancel": cancel_detail}
        _patch_trade_proposal(auth_header, proposal_id, cancel_patch)

        if exchange == "COINONE" and external_order_id:
            if client is None:
                record, access_key, secret_key = _load_user_exchange_record(auth_header, user_id, exchange, broker_env)
                client = _build_exchange_client(exchange, broker_env, record, access_key, secret_key)
            replacement_order = client.place_order(
                symbol=proposal.get("symbol") or proposal.get("ticker"),
                qty=quantity_value,
                side=proposal.get("side"),
                ord_type=proposal.get("ord_type") or "LIMIT",
                price=price_value,
            )

        replacement_status = "PENDING"
        if replacement_order:
            replacement_status = "EXECUTED" if _is_terminal_order_status(replacement_order.get("status")) else "APPROVED"

        replacement_payload = {
            "user_id": user_id,
            "exchange": exchange,
            "asset_type": proposal.get("asset_type") or "CRYPTO",
            "ticker": proposal.get("ticker"),
            "symbol": proposal.get("symbol") or proposal.get("ticker"),
            "broker_env": broker_env,
            "side": proposal.get("side"),
            "price": price_value,
            "volume": quantity_value,
            "ord_type": proposal.get("ord_type") or "LIMIT",
            "market_country": proposal.get("market_country"),
            "currency": proposal.get("currency") or ("USD" if exchange in ("BINANCE", "BINANCE_UM_FUTURES") else "KRW"),
            "replaced_from_id": proposal_id,
            "client_order_id": replacement_order.get("client_order_id") if replacement_order else None,
            "external_order_id": replacement_order.get("order_id") if replacement_order else None,
            "raw_order_payload": {
                "cancel_replace_cancel": cancel_detail,
                "cancel_replace_order": replacement_order.get("raw") if replacement_order else None,
            },
            "status": replacement_status,
        }
        created = _insert_trade_proposal_with_schema_fallback(auth_header, replacement_payload)
        return jsonify({
            "success": True,
            "message": "기존 주문을 취소하고 새 주문을 전송했습니다." if replacement_order else "기존 주문을 취소하고 재주문 제안을 생성했습니다.",
            "status": replacement_status,
            "data": created,
        })
    except ValueError as e:
        return jsonify({"success": False, "message": str(e)}), 400
    except Exception as e:
        if _is_already_canceled_order_error(e):
            _patch_trade_proposal(auth_header, proposal_id, {
                "status": "CANCELED",
                "failure_reason": "이미 취소된 주문으로 거래내역 상태를 취소완료로 갱신했습니다.",
                "canceled_at": datetime.utcnow().isoformat() + "Z",
                "raw_order_payload": {
                    "cancel_replace_cancel_error": str(e)[:500],
                },
            })
            return jsonify({
                "success": False,
                "message": "이미 취소된 주문입니다.",
            }), 400
        _patch_trade_proposal(auth_header, proposal_id, {
            "failure_reason": f"취소 후 재주문 실패: {str(e)[:500]}",
        })
        return jsonify(format_error_payload(e, "취소 후 재주문 실패", exchange=exchange)), 500

@trade_bp.route("/api/chart/quote", methods=["GET"])
def get_quote():
    """
    경량 시세 조회 API.
    전일대비 등락률(change_rate)을 차트 주기와 독립적으로 반환합니다.
    기존 get_cached_change_rate 캐시를 재활용하여 거래소 추가 호출을 최소화합니다.
    change_rate가 0인 경우, 일봉 캔들 캐시에서 전일 종가를 기반으로 직접 계산합니다.
    """
    exchange = request.args.get("exchange")
    symbol = request.args.get("symbol")
    broker_env = request.args.get("broker_env", "REAL")

    if not exchange or not symbol:
        return jsonify({"success": False, "message": "exchange 및 symbol 파라미터가 필수적입니다."}), 400

    is_us_stock = any(c.isalpha() for c in symbol)
    if is_us_stock and exchange == "KIS":
        exchange = "TOSS"

    auth_header = request.headers.get("Authorization")
    change_rate = 0.0 if auth_header else get_cached_change_rate(exchange, symbol, broker_env, auth_header)

    # Fallback: change_rate가 0이면 일봉 캔들 캐시에서 전일 종가 기반으로 직접 계산
    current_price = None
    previous_close = None
    live_quote = {}
    change_rate_source = None
    raw_change_rate = None
    raw_previous_close = None
    previous_close_source = None
    if auth_header:
        try:
            user_id, _ = get_user_id_from_header(auth_header)
            record, access_key, secret_key = _load_user_exchange_record(auth_header, user_id, exchange, broker_env)
            client = _build_exchange_client(exchange, broker_env, record, access_key, secret_key)
            live_quote = client.get_price(symbol) if client and hasattr(client, "get_price") else {}
            raw_change_rate = live_quote.get("change_rate") if isinstance(live_quote, dict) else None
            normalized_price, previous_close, normalized_change_rate = _normalize_live_quote_prices(live_quote)
            current_price = normalized_price
            raw_previous_close = previous_close
            previous_close_source = live_quote.get("previous_close_source") if isinstance(live_quote, dict) else None
            if exchange == "TOSS" and _is_domestic_stock_symbol(symbol):
                kis_previous_close, kis_env = _load_kis_previous_close_for_quote(auth_header, user_id, symbol, broker_env)
                if kis_previous_close:
                    previous_close = kis_previous_close
                    previous_close_source = f"KIS:{kis_env}"
                    if current_price:
                        normalized_change_rate = _recalculate_change_rate(current_price, previous_close)
                        change_rate_source = "CALCULATED_FROM_KIS_PREVIOUS_CLOSE"
            if normalized_change_rate is not None:
                change_rate = normalized_change_rate
                if not change_rate_source:
                    change_rate_source = "CALCULATED_FROM_LIVE_PRICE" if current_price and previous_close else live_quote.get("change_rate_source")
        except Exception as quote_error:
            current_app.logger.warning(f"차트 현재가 조회 실패: {str(quote_error)}")

    if change_rate == 0.0:
        candle_key = (exchange, symbol, "1d", broker_env)
        now = time.time()
        if candle_key in CANDLE_CACHE:
            expire_time, cached_candles = CANDLE_CACHE[candle_key]
            if now < expire_time and isinstance(cached_candles, list) and len(cached_candles) >= 2:
                try:
                    today_close = float(cached_candles[-1].get("close") or 0)
                    prev_close = float(cached_candles[-2].get("close") or 0)
                    if prev_close > 0:
                        change_rate = round(((today_close - prev_close) / prev_close) * 100, 4)
                        current_price = today_close
                        previous_close = prev_close
                        change_rate_source = "CALCULATED_FROM_CANDLE_CACHE"
                except (ValueError, TypeError, KeyError):
                    pass

    if not change_rate_source and isinstance(live_quote, dict):
        change_rate_source = live_quote.get("change_rate_source")

    return jsonify({
        "success": True,
        "data": {
            "change_rate": change_rate,
            "exchange": exchange,
            "symbol": symbol,
            "currency": _currency_for_quote(exchange, symbol),
            **({"current_price": current_price} if current_price is not None else {}),
            **({"previous_close": previous_close} if "previous_close" in locals() and previous_close is not None else {}),
            **({"change_rate_source": change_rate_source} if change_rate_source else {}),
            **({"raw_change_rate": raw_change_rate} if raw_change_rate is not None else {}),
            **({"raw_previous_close": raw_previous_close} if raw_previous_close is not None and raw_previous_close != previous_close else {}),
            **({"previous_close_source": previous_close_source} if previous_close_source else {}),
            **({"symbol_used": live_quote.get("symbol_used")} if isinstance(live_quote, dict) and live_quote.get("symbol_used") else {}),
        }
    })

@trade_bp.route("/api/chart/candles", methods=["GET"])
def get_chart_candles():
    """
    통합 캔들 시세 조회 API 엔드포인트.
    각 거래소 클라이언트를 활용해 캔들 시세를 가져와 Lightweight Charts용 단일 포맷으로 어댑팅하여 반환합니다.
    """
    exchange = request.args.get("exchange")
    symbol = request.args.get("symbol")
    interval = request.args.get("interval", "1d")
    count = int(request.args.get("count", 120))
    broker_env = request.args.get("broker_env", "REAL")

    if not exchange or not symbol:
        return jsonify({"success": False, "message": "exchange 및 symbol 파라미터가 필수적입니다."}), 400

    # 해외 주식(미국 주식)은 KIS 조회 요청이 오더라도 강제로 TOSS로 우회 처리합니다.
    is_us_stock = any(c.isalpha() for c in symbol)
    if is_us_stock and exchange == "KIS":
        exchange = "TOSS"

    auth_header = request.headers.get("Authorization")
    ttl = get_dynamic_ttl(exchange, symbol, interval)
    change_rate = get_cached_change_rate(exchange, symbol, broker_env, auth_header)

    # 동적 캐싱 조회
    cache_key = (exchange, symbol, interval, broker_env)
    now = time.time()
    if cache_key in CANDLE_CACHE:
        expire_time, cached_data = CANDLE_CACHE[cache_key]
        if now < expire_time:
            return jsonify({
                "success": True,
                "data": cached_data,
                "meta": {
                    "source": "CACHE",
                    "is_mock": False,
                    "cache_ttl_seconds": ttl,
                    "change_rate": change_rate,
                }
            })

    # 캐시 미스 시 동시 요청 제어를 위해 Lock 획득 후 Double-checked locking 진행
    lock = _get_api_lock(cache_key)
    with lock:
        now = time.time()
        if cache_key in CANDLE_CACHE:
            expire_time, cached_data = CANDLE_CACHE[cache_key]
            if now < expire_time:
                return jsonify({
                    "success": True,
                    "data": cached_data,
                    "meta": {
                        "source": "CACHE",
                        "is_mock": False,
                        "cache_ttl_seconds": ttl,
                        "change_rate": change_rate,
                    }
                })

        return _fetch_candles_uncached(cache_key, exchange, symbol, interval, count, broker_env, auth_header, ttl, change_rate)


def _fetch_candles_uncached(cache_key, exchange, symbol, interval, count, broker_env, auth_header, ttl, change_rate):
    try:

        # 1. TOSS 캔들
        if exchange == "TOSS":
            if not auth_header:
                return jsonify({"success": False, "message": "인증 헤더가 필요합니다."}), 401
            user_id, token = get_user_id_from_header(auth_header)
            crypto_helper = current_app.crypto
            records = _get_quote_records_with_env_fallback(auth_header, user_id, "TOSS", broker_env)

            # Toss 미지원 주기(5m, 15m, 30m, 60m, 1h, 1w, 1M 등)인 경우
            # KIS API Key가 등록되어 있다면 KIS API를 타서 리샘플링 및 풍부한 분봉 데이터를 안정적으로 제공받음
            is_native_toss = interval in ("1d", "D", "1m")

            # KIS API 키가 있는지 선체크 (Toss 키가 없거나, 혹은 Toss 미지원 주기인 경우 우회 사용 목적)
            records_kis = _get_quote_records_with_env_fallback(auth_header, user_id, "KIS", broker_env)

            # 만약 Toss 키가 없거나, 혹은 미지원 주기인데 KIS 키가 있는 경우 KIS로 처리
            if (not records or not is_native_toss) and records_kis:
                client = _load_kis_client_from_records(records_kis)
                candles = _fetch_kis_candles_with_interval(client, symbol, interval, count)

                CANDLE_CACHE[cache_key] = (time.time() + ttl, candles)
                return jsonify({
                    "success": True,
                    "data": candles,
                    "meta": {"source": "KIS_FALLBACK", "is_mock": False, "cache_ttl_seconds": ttl, "change_rate": change_rate}
                })

            # Toss 키가 없는 경우 KIS 키도 없다면 에러 반환
            if not records:
                return jsonify({"success": False, "message": "등록된 Toss 또는 KIS API 키가 없습니다."}), 400

            # Toss 키가 있고 네이티브 주기를 요청했거나, KIS 키가 없어 자체 리샘플링을 해야 하는 경우
            access_key = crypto_helper.decrypt(records[0].get("encrypted_access_key"))
            secret_key = crypto_helper.decrypt(records[0].get("encrypted_secret_key"))
            toss_account_seq = records[0].get("toss_account_seq")

            client = TossClient(client_id=access_key, client_secret=secret_key, account_seq=toss_account_seq, env=broker_env, user_id=user_id)
            try:
                candles = client.get_candles(symbol, interval=interval, count=count)
            except Exception as toss_error:
                candles = []
                current_app.logger.warning(f"Toss 캔들 조회 실패, KIS 폴백 시도: {str(toss_error)}")

            if candles:
                CANDLE_CACHE[cache_key] = (time.time() + ttl, candles)
                return jsonify({
                    "success": True,
                    "data": candles,
                    "meta": {"source": "LIVE", "is_mock": False, "cache_ttl_seconds": ttl, "change_rate": change_rate}
                })

            if records_kis:
                client_kis = _load_kis_client_from_records(records_kis)
                candles = _fetch_kis_candles_with_interval(client_kis, symbol, interval, count)
                if candles:
                    CANDLE_CACHE[cache_key] = (time.time() + ttl, candles)
                    return jsonify({
                        "success": True,
                        "data": candles,
                        "meta": {"source": "KIS_FALLBACK", "is_mock": False, "cache_ttl_seconds": ttl, "change_rate": change_rate}
                    })

            return jsonify({"success": False, "message": "Toss/KIS 차트 조회 결과가 비어 있습니다."}), 502

        # 2. KIS 캔들
        elif exchange == "KIS":
            if not auth_header:
                return jsonify({"success": False, "message": "인증 헤더가 필요합니다."}), 401
            user_id, token = get_user_id_from_header(auth_header)
            crypto_helper = current_app.crypto
            records = _get_quote_records_with_env_fallback(auth_header, user_id, "KIS", broker_env)
            if not records:
                return jsonify({"success": False, "message": "등록된 KIS API 키가 없습니다."}), 400
            access_key = crypto_helper.decrypt(records[0].get("encrypted_access_key"))
            secret_key = crypto_helper.decrypt(records[0].get("encrypted_secret_key"))
            cano = records[0].get("kis_account_no")
            acnt_prdt_cd = records[0].get("kis_account_code", "01")

            client = KISClient(appkey=access_key, appsecret=secret_key, cano=cano, acnt_prdt_cd=acnt_prdt_cd, env=broker_env, user_id=user_id)

            # interval 판별 및 리샘플링 적용
            if interval in ("1d", "D"):
                candles = client.get_candles(symbol, interval="D", count=count)
            elif interval in ("1w", "W"):
                candles = client.get_candles(symbol, interval="W", count=count)
            elif interval in ("1M", "M"):
                candles = client.get_candles(symbol, interval="M", count=count)
            elif interval == "1m":
                candles = client.get_minute_candles(symbol, interval_minutes=1, count=count)
            elif interval == "5m":
                candles = client.get_minute_candles(symbol, interval_minutes=5, count=count)
            elif interval == "15m":
                candles = client.get_minute_candles(symbol, interval_minutes=15, count=count)
            elif interval == "30m":
                candles = client.get_minute_candles(symbol, interval_minutes=30, count=count)
            elif interval in ("60m", "1h"):
                candles = client.get_minute_candles(symbol, interval_minutes=60, count=count)
            else:
                candles = client.get_candles(symbol, interval="D", count=count)

            CANDLE_CACHE[cache_key] = (time.time() + ttl, candles)
            return jsonify({
                "success": True,
                "data": candles,
                "meta": {"source": "LIVE", "is_mock": False, "cache_ttl_seconds": ttl, "change_rate": change_rate}
            })

        # 3. COINONE 캔들
        elif exchange == "COINONE":
            # Coinone은 1m, 3m, 5m, 10m, 15m, 30m, 1h, 2h, 4h, 6h, 12h, 1d, 1w 지원
            coinone_interval = interval
            if interval in ("1d", "day"):
                coinone_interval = "1d"
            elif interval in ("1w", "week"):
                coinone_interval = "1w"
            elif interval in ("1h", "60m"):
                coinone_interval = "1h"

            symbol_upper = symbol.upper()
            if symbol_upper.endswith("USDT"):
                clean_symbol = symbol_upper[:-4]
            elif symbol_upper.endswith("KRW") and len(symbol_upper) > 3:
                clean_symbol = symbol_upper[:-3]
            elif symbol_upper.endswith("_KRW"):
                clean_symbol = symbol_upper[:-4]
            else:
                clean_symbol = symbol_upper

            url = f"https://api.coinone.co.kr/public/v2/chart/KRW/{clean_symbol}"
            res = requests.get(url, params={"interval": coinone_interval})
            if res.status_code != 200:
                return jsonify(format_error_payload(
                    f"Coinone chart API failed status={res.status_code}: {res.text}",
                    "Coinone 차트 조회 실패",
                    exchange="COINONE",
                )), 502

            data = res.json()
            if data.get("result") != "success":
                return jsonify({"success": False, "message": "Coinone 차트 조회 실패"}), 500

            candles = []
            is_intraday = coinone_interval not in ("1d", "1w")
            for item in data.get("chart", []):
                try:
                    ts = int(item.get("timestamp")) // 1000
                    if is_intraday:
                        time_val = ts
                    else:
                        time_val = datetime.fromtimestamp(ts).strftime("%Y-%m-%d")

                    candles.append({
                        "time": time_val,
                        "open": float(item.get("open", 0)),
                        "high": float(item.get("high", 0)),
                        "low": float(item.get("low", 0)),
                        "close": float(item.get("close", 0)),
                        "volume": float(item.get("volume", 0))
                    })
                except (ValueError, TypeError):
                    pass
            candles_subset = candles[-count:]
            CANDLE_CACHE[cache_key] = (time.time() + ttl, candles_subset)
            return jsonify({
                "success": True,
                "data": candles_subset,
                "meta": {"source": "LIVE", "is_mock": False, "cache_ttl_seconds": ttl, "change_rate": change_rate}
            })

        # 4. BINANCE 캔들
        elif exchange in ("BINANCE", "BINANCE_UM_FUTURES"):
            # Binance는 1m, 3m, 5m, 15m, 30m, 1h, 2h, 4h, 6h, 8h, 12h, 1d, 3d, 1w, 1M 지원
            binance_interval = interval
            if interval in ("1d", "day"):
                binance_interval = "1d"
            elif interval in ("1w", "week"):
                binance_interval = "1w"
            elif interval in ("1M", "month"):
                binance_interval = "1M"
            elif interval in ("1h", "60m"):
                binance_interval = "1h"

            url = "https://api.binance.com/api/v3/klines"
            params = {
                "symbol": symbol.upper(),
                "interval": binance_interval,
                "limit": min(count, 1000)
            }
            res = requests.get(url, params=params)
            if res.status_code != 200:
                return jsonify(format_error_payload(
                    f"Binance chart API failed status={res.status_code}: {res.text}",
                    "Binance 차트 조회 실패",
                    exchange=exchange,
                )), 502

            data = res.json()
            candles = []
            is_intraday = binance_interval not in ("1d", "1w", "1M")
            for item in data:
                try:
                    ts = int(item[0]) // 1000
                    if is_intraday:
                        time_val = ts
                    else:
                        time_val = datetime.fromtimestamp(ts).strftime("%Y-%m-%d")

                    candles.append({
                        "time": time_val,
                        "open": float(item[1]),
                        "high": float(item[2]),
                        "low": float(item[3]),
                        "close": float(item[4]),
                        "volume": float(item[5])
                    })
                except (ValueError, TypeError, IndexError):
                    pass
            CANDLE_CACHE[cache_key] = (time.time() + ttl, candles)
            return jsonify({
                "success": True,
                "data": candles,
                "meta": {"source": "LIVE", "is_mock": False, "cache_ttl_seconds": ttl, "change_rate": change_rate}
            })

        else:
            return jsonify({"success": False, "message": f"지원하지 않는 거래소: {exchange}"}), 400

    except Exception as e:
        import traceback
        current_app.logger.error(f"시세 차트 조회 에러 발생: {str(e)}\n{traceback.format_exc()}")
        return jsonify(format_error_payload(e, "시세 차트 조회 실패", exchange=exchange)), 500


def generate_mock_orderbook(symbol, base_price=150000):
    import random
    if base_price <= 0:
        base_price = 150000

    # 주식 호가 단위 (10만원 이상 50만원 미만: 500원 단위, 50만원 이상: 1000원 단위, 그 이하는 적절히)
    if base_price >= 500000:
        unit = 1000
    elif base_price >= 100000:
        unit = 500
    elif base_price >= 50000:
        unit = 100
    else:
        unit = 10

    asks = []
    bids = []

    for i in range(1, 11):
        price = int((base_price // unit) * unit) + (i * unit)
        size = random.randint(10, 1500)
        asks.append({"price": price, "size": size})

    for i in range(0, 10):
        price = int((base_price // unit) * unit) - (i * unit)
        size = random.randint(10, 2000)
        bids.append({"price": price, "size": size})

    # 매도는 가격 오름차순, 매수는 가격 내림차순 정렬 상태 유지
    asks.sort(key=lambda x: x["price"])
    bids.sort(key=lambda x: x["price"], reverse=True)

    return {
        "symbol": symbol,
        "timestamp": int(time.time()),
        "total_ask_size": sum(x["size"] for x in asks),
        "total_bid_size": sum(x["size"] for x in bids),
        "asks": asks,
        "bids": bids
    }


def generate_mock_trades(symbol, base_price=150000):
    import random
    if base_price <= 0:
        base_price = 150000

    trades = []
    now = int(time.time())

    for i in range(20):
        trade_time = now - (i * random.randint(1, 10))
        time_str = datetime.fromtimestamp(trade_time).strftime("%H:%M:%S")

        price_diff = random.choice([-2, -1, 0, 1, 2]) * (500 if base_price >= 100000 else 10)
        price = base_price + price_diff
        qty = random.randint(1, 200)
        side = random.choice(["BUY", "SELL"])

        trades.append({
            "time": time_str,
            "timestamp": trade_time,
            "price": price,
            "qty": qty,
            "side": side,
            "change_rate": round(random.uniform(-0.5, 0.5), 2)
        })
    return trades


@trade_bp.route("/api/chart/orderbook", methods=["GET"])
def get_orderbook_api():
    """
    통합 호가(Orderbook) 조회 API 엔드포인트.
    거래소 API 장애 또는 장외 시간일 경우 자동으로 가상 호가 시뮬레이션을 생성하여 제공합니다.
    """
    exchange = request.args.get("exchange")
    symbol = request.args.get("symbol")
    broker_env = request.args.get("broker_env", "REAL")

    if not exchange or not symbol:
        return jsonify({"success": False, "message": "exchange 및 symbol 파라미터가 필수적입니다."}), 400

    auth_header = request.headers.get("Authorization")
    cache_key = (exchange, symbol, broker_env)
    cached_orderbook = _get_cached_level2_snapshot(ORDERBOOK_CACHE, cache_key)
    if cached_orderbook is not None:
        return jsonify({
            "success": True,
            "data": cached_orderbook,
            "meta": {
                "source": "CACHE",
                "is_mock": False,
                "cache_ttl_seconds": LEVEL2_CACHE_TTL_SECONDS,
            }
        })

    # 캐시 미스 시 동시 요청 제어를 위해 Lock 획득 후 Double-checked locking 진행
    lock = _get_api_lock(cache_key)
    with lock:
        cached_orderbook = _get_cached_level2_snapshot(ORDERBOOK_CACHE, cache_key)
        if cached_orderbook is not None:
            return jsonify({
                "success": True,
                "data": cached_orderbook,
                "meta": {
                    "source": "CACHE",
                    "is_mock": False,
                    "cache_ttl_seconds": LEVEL2_CACHE_TTL_SECONDS,
                }
            })

        return _fetch_orderbook_uncached(cache_key, exchange, symbol, broker_env, auth_header)


def _fetch_orderbook_uncached(cache_key, exchange, symbol, broker_env, auth_header):
    degraded_reasons = []

    # 기본 Mock 기준 가격 조회 시도 (캐시된 캔들 종가가 존재한다면 동적으로 보정)
    base_price = 150000  # 디폴트
    cached_close = None
    for cache_key_candle, (expire, candles) in CANDLE_CACHE.items():
        if len(cache_key_candle) >= 4 and cache_key_candle[1].upper() == symbol.upper() and candles:
            cached_close = candles[-1]["close"]
            break

    if cached_close is not None and cached_close > 0:
        base_price = cached_close
    else:
        # 캐시가 없는 진입 극초기라도 API 호출 제한(EGW00201) 방지를 위해 동기식 시세 추가 조회는 생략합니다.
        pass

    try:

        # 1. COINONE 호가 조회
        if exchange == "COINONE":
            url = f"https://api.coinone.co.kr/public/v2/orderbook/KRW/{symbol.upper()}"
            res = requests.get(url, timeout=5)
            if res.status_code == 200:
                data = res.json()
                if data.get("result") == "success":
                    asks = []
                    bids = []
                    for item in data.get("asks", []):
                        asks.append({"price": float(item.get("price")), "size": float(item.get("qty"))})
                    for item in data.get("bids", []):
                        bids.append({"price": float(item.get("price")), "size": float(item.get("qty"))})

                    asks.sort(key=lambda x: x["price"])
                    bids.sort(key=lambda x: x["price"], reverse=True)

                    payload = {
                        "symbol": symbol,
                        "timestamp": int(time.time()),
                        "total_ask_size": sum(x["size"] for x in asks),
                        "total_bid_size": sum(x["size"] for x in bids),
                        "asks": asks[:10],
                        "bids": bids[:10]
                    }
                    _set_cached_level2_snapshot(ORDERBOOK_CACHE, cache_key, payload)
                    return jsonify({
                        "success": True,
                        "data": payload,
                        "meta": {"source": "LIVE", "is_mock": False}
                    })

        # 2. BINANCE 호가 조회
        elif exchange in ("BINANCE", "BINANCE_UM_FUTURES"):
            url = "https://api.binance.com/api/v3/depth"
            res = requests.get(url, params={"symbol": symbol.upper(), "limit": 10}, timeout=5)
            if res.status_code == 200:
                data = res.json()
                asks = [{"price": float(x[0]), "size": float(x[1])} for x in data.get("asks", [])]
                bids = [{"price": float(x[0]), "size": float(x[1])} for x in data.get("bids", [])]
                payload = {
                    "symbol": symbol,
                    "timestamp": int(time.time()),
                    "total_ask_size": sum(x["size"] for x in asks),
                    "total_bid_size": sum(x["size"] for x in bids),
                    "asks": asks,
                    "bids": bids
                }
                _set_cached_level2_snapshot(ORDERBOOK_CACHE, cache_key, payload)
                return jsonify({
                    "success": True,
                    "data": payload,
                    "meta": {"source": "LIVE", "is_mock": False}
                })

        # 3. KIS 호가 조회
        elif exchange == "KIS" and auth_header:
            user_id, token = get_user_id_from_header(auth_header)
            crypto_helper = current_app.crypto
            records = _get_quote_records_with_env_fallback(auth_header, user_id, "KIS", broker_env)
            if records:
                access_key = crypto_helper.decrypt(records[0].get("encrypted_access_key"))
                secret_key = crypto_helper.decrypt(records[0].get("encrypted_secret_key"))
                cano = records[0].get("kis_account_no")
                acnt_prdt_cd = records[0].get("kis_account_code", "01")
                kis_env = records[0].get("broker_env", "MOCK")

                client = KISClient(appkey=access_key, appsecret=secret_key, cano=cano, acnt_prdt_cd=acnt_prdt_cd, env=kis_env, user_id=user_id)
                kis_data = client.get_orderbook(symbol)
                output = kis_data.get("output1", {})

                asks = []
                bids = []
                for i in range(1, 11):
                    ask_p = float(output.get(f"askp{i}", 0))
                    ask_s = float(output.get(f"askp_rsqn{i}", 0))
                    bid_p = float(output.get(f"bidp{i}", 0))
                    bid_s = float(output.get(f"bidp_rsqn{i}", 0))
                    if ask_p > 0:
                        asks.append({"price": ask_p, "size": ask_s})
                    if bid_p > 0:
                        bids.append({"price": bid_p, "size": bid_s})

                asks.sort(key=lambda x: x["price"])
                bids.sort(key=lambda x: x["price"], reverse=True)

                base_price = float(output.get("askp1", base_price))

                if asks or bids:
                    payload = {
                        "symbol": symbol,
                        "timestamp": int(time.time()),
                        "total_ask_size": float(output.get("tot_ask_rsqn", 0)),
                        "total_bid_size": float(output.get("tot_bid_rsqn", 0)),
                        "asks": asks,
                        "bids": bids
                    }
                    _set_cached_level2_snapshot(ORDERBOOK_CACHE, cache_key, payload)
                    return jsonify({
                        "success": True,
                        "data": payload,
                        "meta": {"source": "LIVE", "is_mock": False}
                    })
                degraded_reasons.append(f"KIS_EMPTY_ORDERBOOK({records[0].get('broker_env', broker_env)})")
            else:
                degraded_reasons.append(f"KIS_KEYS_MISSING({broker_env})")

        # 4. TOSS 호가 조회
        elif exchange == "TOSS" and auth_header:
            user_id, token = get_user_id_from_header(auth_header)
            crypto_helper = current_app.crypto
            records = _get_quote_records_with_env_fallback(auth_header, user_id, "TOSS", broker_env)
            records_kis = _query_user_exchange_records(auth_header, user_id, "KIS")

            # Toss 키가 없을 때 KIS로 우회
            if not records:
                degraded_reasons.append(f"TOSS_KEYS_MISSING({broker_env})")
                if records_kis:
                    client = _load_kis_client_from_records(records_kis)
                    kis_data = client.get_orderbook(symbol)
                    output = kis_data.get("output1", {})
                    asks = []
                    bids = []
                    for i in range(1, 11):
                        ask_p = float(output.get(f"askp{i}", 0))
                        ask_s = float(output.get(f"askp_rsqn{i}", 0))
                        bid_p = float(output.get(f"bidp{i}", 0))
                        bid_s = float(output.get(f"bidp_rsqn{i}", 0))
                        if ask_p > 0:
                            asks.append({"price": ask_p, "size": ask_s})
                        if bid_p > 0:
                            bids.append({"price": bid_p, "size": bid_s})
                    asks.sort(key=lambda x: x["price"])
                    bids.sort(key=lambda x: x["price"], reverse=True)

                    base_price = float(output.get("askp1", base_price))

                    payload = {
                        "symbol": symbol,
                        "timestamp": int(time.time()),
                        "total_ask_size": float(output.get("tot_ask_rsqn", 0)),
                        "total_bid_size": float(output.get("tot_bid_rsqn", 0)),
                        "asks": asks,
                        "bids": bids
                    }
                    _set_cached_level2_snapshot(ORDERBOOK_CACHE, cache_key, payload)
                    return jsonify({
                        "success": True,
                        "data": payload,
                        "meta": {"source": "KIS_FALLBACK", "is_mock": False}
                    })
                degraded_reasons.append("KIS_FALLBACK_KEYS_MISSING")
            else:
                access_key = crypto_helper.decrypt(records[0].get("encrypted_access_key"))
                secret_key = crypto_helper.decrypt(records[0].get("encrypted_secret_key"))
                toss_account_seq = records[0].get("toss_account_seq")

                asks = []
                bids = []
                try:
                    client = TossClient(client_id=access_key, client_secret=secret_key, account_seq=toss_account_seq, env=broker_env, user_id=user_id)
                    toss_data = client.get_orderbook(symbol)

                    result = {}
                    if isinstance(toss_data, dict):
                        result = toss_data.get("result", {})
                    elif isinstance(toss_data, list) and len(toss_data) > 0:
                        result = toss_data[0] if isinstance(toss_data[0], dict) else {}

                    # Toss 호가 스키마에 부합하게 데이터 매핑
                    for i in range(1, 11):
                        ask_p = float(result.get(f"askPrice{i}", 0))
                        ask_s = float(result.get(f"askSize{i}", 0))
                        bid_p = float(result.get(f"bidPrice{i}", 0))
                        bid_s = float(result.get(f"bidSize{i}", 0))
                        if ask_p > 0:
                            asks.append({"price": ask_p, "size": ask_s})
                        if bid_p > 0:
                            bids.append({"price": bid_p, "size": bid_s})

                    asks.sort(key=lambda x: x["price"])
                    bids.sort(key=lambda x: x["price"], reverse=True)
                    base_price = float(result.get("askPrice1", base_price))

                    if asks or bids:
                        payload = {
                            "symbol": symbol,
                            "timestamp": int(time.time()),
                            "total_ask_size": float(result.get("totalAskSize", 0)),
                            "total_bid_size": float(result.get("totalBidSize", 0)),
                            "asks": asks,
                            "bids": bids
                        }
                        _set_cached_level2_snapshot(ORDERBOOK_CACHE, cache_key, payload)
                        return jsonify({
                            "success": True,
                            "data": payload,
                            "meta": {"source": "LIVE", "is_mock": False}
                        })
                except Exception as toss_error:
                    current_app.logger.warning(f"Toss 호가 조회 실패, KIS 폴백 시도: {str(toss_error)}")
                    degraded_reasons.append(f"TOSS_ORDERBOOK_FAILED({str(toss_error)[:80]})")

                if records_kis:
                    try:
                        client_kis = _load_kis_client_from_records(records_kis)
                        kis_data = client_kis.get_orderbook(symbol)
                        output = kis_data.get("output1", {})
                        asks = []
                        bids = []
                        for i in range(1, 11):
                            ask_p = float(output.get(f"askp{i}", 0))
                            ask_s = float(output.get(f"askp_rsqn{i}", 0))
                            bid_p = float(output.get(f"bidp{i}", 0))
                            bid_s = float(output.get(f"bidp_rsqn{i}", 0))
                            if ask_p > 0:
                                asks.append({"price": ask_p, "size": ask_s})
                            if bid_p > 0:
                                bids.append({"price": bid_p, "size": bid_s})
                        asks.sort(key=lambda x: x["price"])
                        bids.sort(key=lambda x: x["price"], reverse=True)
                        base_price = float(output.get("askp1", base_price))
                        if asks or bids:
                            payload = {
                                "symbol": symbol,
                                "timestamp": int(time.time()),
                                "total_ask_size": float(output.get("tot_ask_rsqn", 0)),
                                "total_bid_size": float(output.get("tot_bid_rsqn", 0)),
                                "asks": asks,
                                "bids": bids
                            }
                            _set_cached_level2_snapshot(ORDERBOOK_CACHE, cache_key, payload)
                            return jsonify({
                                "success": True,
                                "data": payload,
                                "meta": {"source": "KIS_FALLBACK", "is_mock": False}
                            })
                        degraded_reasons.append(f"KIS_FALLBACK_EMPTY_ORDERBOOK({records_kis[0].get('broker_env', 'UNKNOWN')})")
                    except Exception as kis_fallback_error:
                        degraded_reasons.append(f"KIS_FALLBACK_ORDERBOOK_FAILED({str(kis_fallback_error)[:80]})")
                else:
                    degraded_reasons.append("KIS_FALLBACK_KEYS_MISSING")
        elif exchange in ("KIS", "TOSS") and not auth_header:
            degraded_reasons.append("AUTH_HEADER_MISSING")

    except Exception as e:
        current_app.logger.warning(f"실시간 호가 API 조회 실패로 인한 Mock 활성화: {str(e)}")
        degraded_reasons.append(f"ORDERBOOK_ROUTE_EXCEPTION({str(e)[:80]})")

    # 5. 모든 조회 실패 또는 장외 시간 시 시뮬레이션 Mock 반환
    mock_data = generate_mock_orderbook(symbol, base_price=base_price)
    return jsonify({
        "success": True,
        "data": mock_data,
        "is_mock": True,
        "meta": {
            "source": "MOCK",
            "is_mock": True,
            "degraded_reason": _compact_degraded_reason("LIVE_ORDERBOOK_UNAVAILABLE", degraded_reasons),
        }
    })


@trade_bp.route("/api/chart/trades", methods=["GET"])
def get_trades_api():
    """
    통합 실시간 체결(Trades) 조회 API 엔드포인트.
    거래소 API 장애 또는 장외 시간일 경우 자동으로 가상 체결 시뮬레이션을 생성하여 제공합니다.
    """
    exchange = request.args.get("exchange")
    symbol = request.args.get("symbol")
    broker_env = request.args.get("broker_env", "REAL")

    if not exchange or not symbol:
        return jsonify({"success": False, "message": "exchange 및 symbol 파라미터가 필수적입니다."}), 400

    auth_header = request.headers.get("Authorization")
    cache_key = (exchange, symbol, broker_env)
    cached_trades = _get_cached_level2_snapshot(TRADES_CACHE, cache_key)
    if cached_trades is not None:
        return jsonify({
            "success": True,
            "data": cached_trades,
            "meta": {
                "source": "CACHE",
                "is_mock": False,
                "cache_ttl_seconds": LEVEL2_CACHE_TTL_SECONDS,
            }
        })

    # 캐시 미스 시 동시 요청 제어를 위해 Lock 획득 후 Double-checked locking 진행
    lock = _get_api_lock(cache_key)
    with lock:
        cached_trades = _get_cached_level2_snapshot(TRADES_CACHE, cache_key)
        if cached_trades is not None:
            return jsonify({
                "success": True,
                "data": cached_trades,
                "meta": {
                    "source": "CACHE",
                    "is_mock": False,
                    "cache_ttl_seconds": LEVEL2_CACHE_TTL_SECONDS,
                }
            })

        return _fetch_trades_uncached(cache_key, exchange, symbol, broker_env, auth_header)


def _fetch_trades_uncached(cache_key, exchange, symbol, broker_env, auth_header):
    degraded_reasons = []

    # 기본 Mock 기준 가격 조회 시도 (캐시된 캔들 종가가 존재한다면 동적으로 보정)
    base_price = 150000
    cached_close = None
    for cache_key_candle, (expire, candles) in CANDLE_CACHE.items():
        if len(cache_key_candle) >= 4 and cache_key_candle[1].upper() == symbol.upper() and candles:
            cached_close = candles[-1]["close"]
            break

    if cached_close is not None and cached_close > 0:
        base_price = cached_close
    else:
        # 캐시가 없는 진입 극초기라도 API 호출 제한(EGW00201) 방지를 위해 동기식 시세 추가 조회는 생략합니다.
        pass

    try:

        # 1. COINONE 체결 조회
        if exchange == "COINONE":
            url = f"https://api.coinone.co.kr/public/v2/trades/KRW/{symbol.upper()}"
            res = requests.get(url, timeout=5)
            if res.status_code == 200:
                data = res.json()
                if data.get("result") == "success":
                    trades = []
                    for item in data.get("transactions", [])[:20]:
                        ts = int(item.get("timestamp")) // 1000
                        time_str = datetime.fromtimestamp(ts).strftime("%H:%M:%S")
                        side = "SELL" if item.get("is_seller_maker") else "BUY"
                        trades.append({
                            "time": time_str,
                            "timestamp": ts,
                            "price": float(item.get("price")),
                            "qty": float(item.get("qty")),
                            "side": side,
                            "change_rate": 0.0
                        })
                    _set_cached_level2_snapshot(TRADES_CACHE, cache_key, trades)
                    return jsonify({
                        "success": True,
                        "data": trades,
                        "meta": {"source": "LIVE", "is_mock": False}
                    })

        # 2. BINANCE 체결 조회
        elif exchange in ("BINANCE", "BINANCE_UM_FUTURES"):
            url = "https://api.binance.com/api/v3/trades"
            res = requests.get(url, params={"symbol": symbol.upper(), "limit": 20}, timeout=5)
            if res.status_code == 200:
                data = res.json()
                trades = []
                for item in data:
                    ts = int(item.get("time")) // 1000
                    time_str = datetime.fromtimestamp(ts).strftime("%H:%M:%S")
                    side = "SELL" if item.get("isBuyerMaker") else "BUY"
                    trades.append({
                        "time": time_str,
                        "timestamp": ts,
                        "price": float(item.get("price")),
                        "qty": float(item.get("qty")),
                        "side": side,
                        "change_rate": 0.0
                    })
                _set_cached_level2_snapshot(TRADES_CACHE, cache_key, trades)
                return jsonify({
                    "success": True,
                    "data": trades,
                    "meta": {"source": "LIVE", "is_mock": False}
                })

        # 3. KIS 체결 조회
        elif exchange == "KIS" and auth_header:
            user_id, token = get_user_id_from_header(auth_header)
            crypto_helper = current_app.crypto
            records = _get_quote_records_with_env_fallback(auth_header, user_id, "KIS", broker_env)
            if records:
                access_key = crypto_helper.decrypt(records[0].get("encrypted_access_key"))
                secret_key = crypto_helper.decrypt(records[0].get("encrypted_secret_key"))
                cano = records[0].get("kis_account_no")
                acnt_prdt_cd = records[0].get("kis_account_code", "01")
                kis_env = records[0].get("broker_env", "MOCK")

                client = KISClient(appkey=access_key, appsecret=secret_key, cano=cano, acnt_prdt_cd=acnt_prdt_cd, env=kis_env, user_id=user_id)
                kis_data = client.get_trades(symbol)
                output2 = kis_data.get("output", [])

                trades = []
                for item in output2[:20]:
                    t_str = item.get("stck_cntg_hour")  # "HHMMSS"
                    try:
                        time_str = f"{t_str[0:2]}:{t_str[2:4]}:{t_str[4:6]}"
                    except IndexError:
                        time_str = t_str

                    price_val = float(item.get("stck_prpr", 0))
                    qty_val = float(item.get("cntg_vol", 0))

                    # 1:매수체결, 5:매도체결
                    side = "SELL" if item.get("tday_ccld_xe_yn") == "5" else "BUY"

                    trades.append({
                        "time": time_str,
                        "timestamp": int(time.time()),
                        "price": price_val,
                        "qty": qty_val,
                        "side": side,
                        "change_rate": float(item.get("prdy_ctrt", 0.0))
                    })

                if output2:
                    base_price = float(output2[0].get("stck_prpr", base_price))
                    _set_cached_level2_snapshot(TRADES_CACHE, cache_key, trades)
                    return jsonify({
                        "success": True,
                        "data": trades,
                        "meta": {"source": "LIVE", "is_mock": False}
                    })
                degraded_reasons.append(f"KIS_EMPTY_TRADES({records[0].get('broker_env', broker_env)})")
            else:
                degraded_reasons.append(f"KIS_KEYS_MISSING({broker_env})")

        # 4. TOSS 체결 조회
        elif exchange == "TOSS" and auth_header:
            user_id, token = get_user_id_from_header(auth_header)
            crypto_helper = current_app.crypto
            records = _get_quote_records_with_env_fallback(auth_header, user_id, "TOSS", broker_env)
            records_kis = _query_user_exchange_records(auth_header, user_id, "KIS")

            # Toss 키가 없을 때 KIS로 우회
            if not records:
                degraded_reasons.append(f"TOSS_KEYS_MISSING({broker_env})")
                if records_kis:
                    client = _load_kis_client_from_records(records_kis)
                    kis_data = client.get_trades(symbol)
                    output2 = kis_data.get("output", [])
                    trades = []
                    for item in output2[:20]:
                        t_str = item.get("stck_cntg_hour")
                        try:
                            time_str = f"{t_str[0:2]}:{t_str[2:4]}:{t_str[4:6]}"
                        except IndexError:
                            time_str = t_str
                        trades.append({
                            "time": time_str,
                            "timestamp": int(time.time()),
                            "price": float(item.get("stck_prpr", 0)),
                            "qty": float(item.get("cntg_vol", 0)),
                            "side": "SELL" if item.get("tday_ccld_xe_yn") == "5" else "BUY",
                            "change_rate": float(item.get("prdy_ctrt", 0.0))
                        })

                    if output2:
                        base_price = float(output2[0].get("stck_prpr", base_price))
                    _set_cached_level2_snapshot(TRADES_CACHE, cache_key, trades)
                    return jsonify({
                        "success": True,
                        "data": trades,
                        "meta": {"source": "KIS_FALLBACK", "is_mock": False}
                    })
                degraded_reasons.append("KIS_FALLBACK_KEYS_MISSING")
            else:
                access_key = crypto_helper.decrypt(records[0].get("encrypted_access_key"))
                secret_key = crypto_helper.decrypt(records[0].get("encrypted_secret_key"))
                toss_account_seq = records[0].get("toss_account_seq")

                trades = []
                try:
                    client = TossClient(client_id=access_key, client_secret=secret_key, account_seq=toss_account_seq, env=broker_env, user_id=user_id)
                    toss_data = client.get_trades(symbol)

                    raw_trades = []
                    if isinstance(toss_data, list):
                        raw_trades = toss_data
                    elif isinstance(toss_data, dict):
                        result = toss_data.get("result", {})
                        if isinstance(result, list):
                            raw_trades = result
                        elif isinstance(result, dict):
                            raw_trades = result.get("trades", [])

                    for item in raw_trades[:20]:
                        trades.append({
                            "time": item.get("timestamp", "").split(" ")[1] if " " in item.get("timestamp", "") else item.get("timestamp"),
                            "timestamp": int(time.time()),
                            "price": float(item.get("price", 0)),
                            "qty": float(item.get("quantity", 0)),
                            "side": item.get("side", "BUY").upper(),
                            "change_rate": float(item.get("changeRate", 0))
                        })

                    if raw_trades:
                        base_price = float(raw_trades[0].get("price", base_price))

                    if trades:
                        _set_cached_level2_snapshot(TRADES_CACHE, cache_key, trades)
                        return jsonify({
                            "success": True,
                            "data": trades,
                            "meta": {"source": "LIVE", "is_mock": False}
                        })
                except Exception as toss_error:
                    current_app.logger.warning(f"Toss 체결 조회 실패, KIS 폴백 시도: {str(toss_error)}")
                    degraded_reasons.append(f"TOSS_TRADES_FAILED({str(toss_error)[:80]})")

                if records_kis:
                    try:
                        client_kis = _load_kis_client_from_records(records_kis)
                        kis_data = client_kis.get_trades(symbol)
                        output2 = kis_data.get("output", [])
                        trades = []
                        for item in output2[:20]:
                            t_str = item.get("stck_cntg_hour")
                            try:
                                time_str = f"{t_str[0:2]}:{t_str[2:4]}:{t_str[4:6]}"
                            except IndexError:
                                time_str = t_str
                            trades.append({
                                "time": time_str,
                                "timestamp": int(time.time()),
                                "price": float(item.get("stck_prpr", 0)),
                                "qty": float(item.get("cntg_vol", 0)),
                                "side": "SELL" if item.get("tday_ccld_xe_yn") == "5" else "BUY",
                                "change_rate": float(item.get("prdy_ctrt", 0.0))
                            })
                        if output2:
                            base_price = float(output2[0].get("stck_prpr", base_price))
                        if trades:
                            _set_cached_level2_snapshot(TRADES_CACHE, cache_key, trades)
                            return jsonify({
                                "success": True,
                                "data": trades,
                                "meta": {"source": "KIS_FALLBACK", "is_mock": False}
                            })
                        degraded_reasons.append(f"KIS_FALLBACK_EMPTY_TRADES({records_kis[0].get('broker_env', 'UNKNOWN')})")
                    except Exception as kis_fallback_error:
                        degraded_reasons.append(f"KIS_FALLBACK_TRADES_FAILED({str(kis_fallback_error)[:80]})")
                else:
                    degraded_reasons.append("KIS_FALLBACK_KEYS_MISSING")
        elif exchange in ("KIS", "TOSS") and not auth_header:
            degraded_reasons.append("AUTH_HEADER_MISSING")

    except Exception as e:
        current_app.logger.warning(f"실시간 체결 API 조회 실패로 인한 Mock 활성화: {str(e)}")
        degraded_reasons.append(f"TRADES_ROUTE_EXCEPTION({str(e)[:80]})")

    # 5. 모든 조회 실패 또는 장외 시간 시 시뮬레이션 Mock 반환
    mock_data = generate_mock_trades(symbol, base_price=base_price)
    return jsonify({
        "success": True,
        "data": mock_data,
        "is_mock": True,
        "meta": {
            "source": "MOCK",
            "is_mock": True,
            "degraded_reason": _compact_degraded_reason("LIVE_TRADES_UNAVAILABLE", degraded_reasons),
        }
    })


def _auto_backfill_stock_from_turnover(query_symbol: str) -> dict | None:
    """
    turnover_latest 테이블을 조회하여 해외주식 등 누락 종목 정보를 확보한 뒤,
    kis_stock_master 테이블에 온디맨드로 자동 등록(Backfill)합니다.
    """
    from backend.services.supabase_client import safe_query_supabase_as_service_role
    from backend.services.symbol_reconciliation_service import is_temporary_symbol

    if is_temporary_symbol(query_symbol):
        return None

    # 1. turnover_latest 에서 심볼 조회
    records = safe_query_supabase_as_service_role(
        "kis_stock_turnover_latest",
        "GET",
        params={"symbol": f"eq.{query_symbol.upper()}"}
    )
    if not records:
        return None

    row = records[0]
    raw_payload = row.get("raw_payload") or {}

    # 2. 거래소 코드를 통해 market_segment 판단
    excd = raw_payload.get("excd") or raw_payload.get("_exchange_code") or ""
    market_segment = "OTHER"
    if excd == "NAS":
        market_segment = "NASDAQ"
    elif excd == "NYS":
        market_segment = "NYSE"
    elif excd == "AMS":
        market_segment = "AMEX"

    display_name = row.get("name") or query_symbol.upper()

    new_stock = {
        "symbol": query_symbol.upper(),
        "name": display_name,
        "display_name": display_name,
        "sector": "해외주식",
        "market_segment": market_segment,
        "market_country": row.get("market_country") or "US",
        "asset_type": "STOCK",
        "source": "KIS",
        "is_active": True
    }

    try:
        # service_role 권한으로 안전하게 insert
        safe_query_supabase_as_service_role(
            "kis_stock_master",
            "POST",
            json_data=new_stock
        )
        return new_stock
    except Exception as e:
        from flask import current_app
        current_app.logger.error(f"Failed to auto-backfill stock {query_symbol}: {e}")
        return None


@trade_bp.route("/api/symbol/lookup", methods=["GET"])
def lookup_symbol():
    """
    종목명(예: 'SK하이닉스', '하이닉스') 또는 심볼(예: '000660', 'BTC')을 기반으로
    정밀 매핑된 종목코드와 자산 타입(STOCK | CRYPTO)을 찾아 반환합니다.
    """
    query = request.args.get("query", "").strip().upper()
    if not query:
        return jsonify({"success": False, "message": "query 파라미터가 필수적입니다."}), 400

    asset_type_hint = request.args.get("asset_type", "").strip().upper()

    import re
    from backend.services.symbol_metadata import SYMBOL_METADATA, search_crypto_symbols, COIN_DISPLAY_NAMES
    from backend.services.market_repository import MarketRepository
    from backend.services.symbol_reconciliation_service import (
        canonical_symbol_for,
        filter_symbol_results,
        is_temporary_symbol,
    )

    # 1. 완전 일치 매칭 (하드코딩 SYMBOL_METADATA)
    for sym, meta in SYMBOL_METADATA.items():
        if sym.upper() == query or meta.get("display_name", "").upper() == query:
            if is_temporary_symbol(sym):
                canonical = canonical_symbol_for(sym)
                canonical_meta = SYMBOL_METADATA.get(canonical)
                if canonical_meta:
                    return jsonify({
                        "success": True,
                        "data": {
                            "symbol": canonical,
                            "display_name": canonical_meta.get("display_name"),
                            "asset_type": canonical_meta.get("asset_type"),
                            "market": canonical_meta.get("market")
                        }
                    })
            return jsonify({
                "success": True,
                "data": {
                    "symbol": sym,
                    "display_name": meta.get("display_name"),
                    "asset_type": meta.get("asset_type"),
                    "market": meta.get("market")
                }
            })

    # 2. 가상자산 정밀 매칭 (한글명 맵 또는 코인 캐시 기반)
    for base_sym, name in COIN_DISPLAY_NAMES.items():
        if name.upper() == query or base_sym == query:
            return jsonify({
                "success": True,
                "data": {
                    "symbol": base_sym,
                    "display_name": name,
                    "asset_type": "CRYPTO",
                    "market": "KRW · USDT",
                    "markets": ["KRW", "USDT"],
                }
            })

    # 2.5. 실시간 가상자산 캐시 목록 정밀 검색 및 매칭
    crypto_matches = search_crypto_symbols(query, limit=10)
    for c in crypto_matches:
        aliases = [str(item).upper() for item in c.get("aliases", [])]
        if c["symbol"].upper() == query or c["display_name"].upper() == query or query in aliases:
            return jsonify({
                "success": True,
                "data": {
                    "symbol": c["symbol"],
                    "display_name": c["display_name"],
                    "asset_type": "CRYPTO",
                    "market": c.get("market"),
                    "markets": c.get("markets", []),
                    "exchanges": c.get("exchanges", []),
                }
            })

    # 3. 주식 마스터 DB 정밀 매칭
    repo = MarketRepository()
    if is_temporary_symbol(query):
        canonical = canonical_symbol_for(query)
        canonical_rows = repo.search_stock_master(canonical, limit=1)
        for row in canonical_rows:
            if str(row.get("symbol") or "").upper() == canonical:
                clean_name = re.sub(r"^KR\d{10}", "", row.get("name") or row.get("display_name") or canonical).strip()
                return jsonify({
                    "success": True,
                    "data": {
                        "symbol": canonical,
                        "display_name": clean_name,
                        "asset_type": "STOCK",
                        "market": row.get("market_country") or "US"
                    }
                })
    db_results = filter_symbol_results(repo.search_stock_master(query, limit=5))

    for row in db_results:
        clean_name = re.sub(r"^KR\d{10}", "", row["name"]).strip()
        if row["symbol"] == query or clean_name.upper() == query or row["name"].upper() == query:
            return jsonify({
                "success": True,
                "data": {
                    "symbol": row["symbol"],
                    "display_name": clean_name,
                    "asset_type": "STOCK",
                    "market": row.get("market_country") or "KR"
                }
            })

    # 3.5. 거래대금 최신 테이블 이름/심볼 기반 보조 검색
    from backend.services.supabase_client import safe_query_supabase_as_service_role
    turnover_results = safe_query_supabase_as_service_role(
        "kis_stock_turnover_latest",
        "GET",
        params={
            "or": f"(name.ilike.*{query}*,symbol.ilike.*{query}*)",
            "limit": 10,
        },
    )
    turnover_results = filter_symbol_results([*db_results, *(turnover_results or [])])
    for row in turnover_results or []:
        symbol = str(row.get("symbol") or "").strip().upper()
        name = str(row.get("name") or "").strip()
        if symbol == query or name.upper() == query:
            return jsonify({
                "success": True,
                "data": {
                    "symbol": symbol,
                    "display_name": name or symbol,
                    "asset_type": "STOCK",
                    "market": row.get("market_country") or "US"
                }
            })

    # 4. 누락 해외 주식 온디맨드 자동 등록 (Auto-backfill) 시도
    if re.match(r"^[A-Z0-9]{1,10}$", query):
        if is_temporary_symbol(query):
            return jsonify({
                "success": False,
                "message": "상장 전 임시 종목코드는 정식 상장 후 사용할 수 없습니다. 정식 종목코드로 다시 검색해 주세요.",
                "data": None,
            }), 404
        backfilled = _auto_backfill_stock_from_turnover(query)
        if backfilled:
            return jsonify({
                "success": True,
                "data": {
                    "symbol": backfilled["symbol"],
                    "display_name": backfilled["display_name"],
                    "asset_type": "STOCK",
                    "market": backfilled["market_country"]
                }
            })

    return jsonify({
        "success": False,
        "message": "검색 결과가 없습니다. 종목명 또는 코드를 다시 확인해 주세요.",
        "data": None,
    }), 404


@trade_bp.route("/api/trade/history/sync/toss", methods=["POST"])
def sync_toss_trade_history():
    """
    토스 실제 주문내역을 broker_order_history 테이블로 동기화합니다.
    """
    auth_header = request.headers.get("Authorization")
    if not auth_header:
        return jsonify({"success": False, "message": "인증 토큰이 없습니다."}), 401

    body = request.get_json(silent=True) or {}
    try:
        result = sync_toss_broker_orders(
            auth_header=auth_header,
            broker_env=body.get("broker_env", "REAL"),
            status_scope=body.get("status_scope", "ALL"),
            from_date=body.get("from"),
            to_date=body.get("to"),
            symbol=body.get("symbol"),
            limit=body.get("limit", 100),
        )
        return jsonify({"success": True, "data": result})
    except Exception as error:
        current_app.logger.exception("토스 주문내역 동기화 실패")
        return jsonify(format_error_payload(error, "토스 주문내역 동기화 실패", exchange="TOSS")), 400


@trade_bp.route("/api/trade/history/broker", methods=["GET"])
def get_broker_trade_history():
    """
    사용자의 브로커 주문 원장을 조회합니다.
    """
    auth_header = request.headers.get("Authorization")
    if not auth_header:
        return jsonify({"success": False, "message": "인증 토큰이 없습니다."}), 401

    try:
        rows = list_broker_order_history(
            auth_header=auth_header,
            limit=request.args.get("limit", 300),
            exchange=request.args.get("exchange"),
            broker_env=request.args.get("broker_env"),
        )
        return jsonify({"success": True, "data": rows})
    except Exception as error:
        current_app.logger.exception("브로커 주문 원장 조회 실패")
        return jsonify(format_error_payload(error, "브로커 주문 원장 조회 실패")), 400


SYMBOL_NAMES_CACHE = None

def _load_symbol_names_cache(auth_header: str) -> list[dict]:
    global SYMBOL_NAMES_CACHE
    if SYMBOL_NAMES_CACHE is not None:
        return SYMBOL_NAMES_CACHE

    cache = []
    seen = set()

    # 1. 하드코딩 SYMBOL_METADATA
    from backend.services.symbol_metadata import SYMBOL_METADATA
    for sym, meta in SYMBOL_METADATA.items():
        name = meta.get("display_name", "")
        if name and name not in seen:
            seen.add(name)
            cache.append({
                "name": name,
                "symbol": sym,
                "asset_type": meta.get("asset_type") or "STOCK",
                "market": meta.get("market") or "KR"
            })

    # 2. kis_stock_master 의 모든 마스터 종목
    from backend.services.supabase_client import safe_query_supabase_as_service_role
    try:
        db_rows = safe_query_supabase_as_service_role(
            "kis_stock_master",
            "GET",
            params={"limit": "4000"}
        )
        if db_rows:
            for row in db_rows:
                name = row.get("name")
                sym = row.get("symbol")
                if name and sym and name not in seen:
                    seen.add(name)
                    cache.append({
                        "name": name,
                        "symbol": sym,
                        "asset_type": "STOCK",
                        "market": row.get("market_country") or "KR"
                    })
    except Exception:
        pass

    SYMBOL_NAMES_CACHE = cache
    return SYMBOL_NAMES_CACHE


@trade_bp.route("/api/symbol/search", methods=["GET"])
def search_symbols():
    """
    종목명 또는 심볼의 부분 입력을 받아 매칭되는 후보군 최대 10개를 자동완성용 목록으로 리턴합니다.
    """
    query = request.args.get("query", "").strip().upper()
    if not query:
        return jsonify({"success": True, "data": []})

    import re
    from backend.services.symbol_metadata import SYMBOL_METADATA, search_crypto_symbols
    from backend.services.market_repository import MarketRepository
    from backend.services.symbol_reconciliation_service import filter_symbol_results

    results = []
    seen = set()

    # 1. 하드코딩 SYMBOL_METADATA 검색
    for sym, meta in SYMBOL_METADATA.items():
        display_name = meta.get("display_name", "")
        if query in sym or query in display_name.upper():
            if sym not in seen:
                seen.add(sym)
                results.append({
                    "symbol": sym,
                    "display_name": display_name,
                    "asset_type": meta.get("asset_type"),
                    "market": meta.get("market")
                })

    # 2. 가상자산 캐시 기반 검색
    crypto_results = search_crypto_symbols(query, limit=10)
    for c in crypto_results:
        sym = c["symbol"]
        if sym not in seen:
            seen.add(sym)
            results.append(c)

    # 3. 주식 마스터 DB 기반 검색
    repo = MarketRepository()
    db_results = repo.search_stock_master(query, limit=10)
    for row in db_results:
        sym = row["symbol"]
        if sym not in seen:
            seen.add(sym)
            clean_name = re.sub(r"^KR\d{10}", "", row["name"]).strip()
            results.append({
                "symbol": sym,
                "display_name": clean_name,
                "asset_type": "STOCK",
                "market": row.get("market_country") or "KR"
            })

    # 4. turnover_latest 추가 검색 (해외 랭킹에만 존재하는 종목 대응)
    from backend.services.supabase_client import safe_query_supabase_as_service_role
    turnover_results = safe_query_supabase_as_service_role(
        "kis_stock_turnover_latest",
        "GET",
        params={
            "or": f"(name.ilike.*{query}*,symbol.ilike.*{query}*)",
            "limit": 10
        }
    )
    if turnover_results:
        for row in turnover_results:
            sym = row["symbol"]
            if sym not in seen:
                seen.add(sym)
                results.append({
                    "symbol": sym,
                    "display_name": row.get("name") or sym,
                    "asset_type": "STOCK",
                    "market": row.get("market_country") or "US"
                })

    # 4.5. 검색 결과가 없고 검색어가 2글자 이상인 경우 difflib를 활용한 퍼지 유사도 검색 폴백
    if not results and len(query) >= 2:
        import difflib
        cache = _load_symbol_names_cache(auth_header)
        names = [item["name"] for item in cache]
        matches = difflib.get_close_matches(query, names, n=3, cutoff=0.35)
        if matches:
            for match in matches:
                for item in cache:
                    if item["name"] == match:
                        sym = item["symbol"]
                        if sym not in seen:
                            seen.add(sym)
                            results.append({
                                "symbol": sym,
                                "display_name": item["name"],
                                "asset_type": item["asset_type"],
                                "market": item.get("market") or "KR"
                            })

    # 가독성을 위해 코드 길이 순 및 사전 순 정렬
    results = filter_symbol_results(results)
    results.sort(key=lambda x: (len(x["symbol"]), x["display_name"]))

    return jsonify({"success": True, "data": results[:10]})


@trade_bp.route("/api/trade/auto-trading-rule", methods=["PATCH"])
def modify_auto_trading_rule():
    """
    사용자가 등록한 조건감시 규칙(익절/손절 비율, 수량, 상태)을 수정합니다.
    """
    auth_header = request.headers.get("Authorization")
    if not auth_header:
        return jsonify({"success": False, "message": "인증 토큰이 없습니다."}), 401

    try:
        user_id, _ = get_user_id_from_header(auth_header)
    except Exception as e:
        return jsonify({"success": False, "message": f"인증 실패: {str(e)}"}), 401

    data = request.json or {}
    rule_id = data.get("rule_id")
    if not rule_id:
        return jsonify({"success": False, "message": "rule_id가 누락되었습니다."}), 400

    # 본인의 규칙인지 선제 검증
    try:
        rules = query_supabase(auth_header, "auto_trading_rules", "GET", params={
            "id": f"eq.{rule_id}",
            "user_id": f"eq.{user_id}",
            "limit": "1"
        })
    except Exception as error:
        current_app.logger.exception("조건감시 규칙 조회 실패")
        return jsonify(format_error_payload(error, "조건감시 규칙 조회 실패")), 400

    if not rules or len(rules) == 0:
        return jsonify({"success": False, "message": "해당 조건감시 규칙을 찾을 수 없거나 권한이 없습니다."}), 404

    # 업데이트할 페이로드 구성
    update_data = {}
    if "target_profit_rate" in data:
        update_data["target_profit_rate"] = float(data["target_profit_rate"])
    if "stop_loss_rate" in data:
        update_data["stop_loss_rate"] = float(data["stop_loss_rate"])
    if "quantity" in data:
        qty = data["quantity"]
        update_data["quantity"] = float(qty) if qty is not None else None
    if "status" in data:
        status = str(data["status"]).upper()
        if status in ("RUNNING", "COMPLETED", "STOPPED", "FAILED"):
            update_data["status"] = status

    if not update_data:
        return jsonify({"success": False, "message": "수정할 정보가 제공되지 않았습니다."}), 400

    update_data["updated_at"] = datetime.now(timezone.utc).isoformat()

    try:
        result = query_supabase(auth_header, f"auto_trading_rules?id=eq.{rule_id}", "PATCH", json_data=update_data)
        return jsonify({"success": True, "message": "조건감시 규칙이 정상적으로 수정되었습니다.", "data": result})
    except Exception as error:
        current_app.logger.exception("조건감시 규칙 수정 실패")
        return jsonify(format_error_payload(error, "조건감시 규칙 수정 실패")), 400


@trade_bp.route("/api/trade/auto-trading-rule", methods=["DELETE"])
def stop_auto_trading_rule():
    """
    사용자가 등록한 조건감시 규칙을 정지(STOPPED) 처리합니다. (기록 보존을 위해 완전 삭제 대신 상태 변경)
    """
    auth_header = request.headers.get("Authorization")
    if not auth_header:
        return jsonify({"success": False, "message": "인증 토큰이 없습니다."}), 401

    try:
        user_id, _ = get_user_id_from_header(auth_header)
    except Exception as e:
        return jsonify({"success": False, "message": f"인증 실패: {str(e)}"}), 401

    rule_id = request.args.get("rule_id") or (request.json or {}).get("rule_id")
    if not rule_id:
        return jsonify({"success": False, "message": "rule_id가 누락되었습니다."}), 400

    # 본인의 규칙인지 선제 검증
    try:
        rules = query_supabase(auth_header, "auto_trading_rules", "GET", params={
            "id": f"eq.{rule_id}",
            "user_id": f"eq.{user_id}",
            "limit": "1"
        })
    except Exception as error:
        current_app.logger.exception("조건감시 규칙 조회 실패")
        return jsonify(format_error_payload(error, "조건감시 규칙 조회 실패")), 400

    if not rules or len(rules) == 0:
        return jsonify({"success": False, "message": "해당 조건감시 규칙을 찾을 수 없거나 권한이 없습니다."}), 404

    # 기존 상태에 따라 물리 삭제 또는 정지 상태 전환 분기
    current_status = rules[0].get("status")

    try:
        if current_status in ("STOPPED", "COMPLETED"):
            result = query_supabase(auth_header, f"auto_trading_rules?id=eq.{rule_id}", "DELETE")
            return jsonify({"success": True, "message": "조건감시 규칙이 완전히 삭제되었습니다.", "data": result})
        else:
            update_data = {
                "status": "STOPPED",
                "updated_at": datetime.now(timezone.utc).isoformat()
            }
            result = query_supabase(auth_header, f"auto_trading_rules?id=eq.{rule_id}", "PATCH", json_data=update_data)
            return jsonify({"success": True, "message": "조건감시가 정지되었습니다.", "data": result})
    except Exception as error:
        current_app.logger.exception("조건감시 정지 실패")
        return jsonify(format_error_payload(error, "조건감시 정지 실패")), 400


@trade_bp.route("/api/trade/auto-trading-rule", methods=["POST"])
def create_auto_trading_rule():
    """
    사용자가 주문과 무관하게 이미 보유 중인 자산에 대해 조건감시 규칙을 단독으로 새로 등록합니다.
    """
    auth_header = request.headers.get("Authorization")
    if not auth_header:
        return jsonify({"success": False, "message": "인증 토큰이 없습니다."}), 401

    try:
        user_id, _ = get_user_id_from_header(auth_header)
    except Exception as e:
        return jsonify({"success": False, "message": f"인증 실패: {str(e)}"}), 401

    req_data = request.json or {}
    exchange = req_data.get("exchange")
    asset_type = req_data.get("asset_type")
    symbol = str(req_data.get("symbol") or "").upper()
    entry_price = float(req_data.get("entry_price") or 0)
    quantity = float(req_data.get("quantity") or 0)
    target_profit_rate = float(req_data.get("target_profit_rate") or 0)
    stop_loss_rate = float(req_data.get("stop_loss_rate") or 0)
    execution_mode = req_data.get("execution_mode", "PROPOSAL")
    broker_env = req_data.get("broker_env", "REAL").upper()

    if not exchange or not symbol or quantity <= 0:
        return jsonify({"success": False, "message": "필수 입력값(거래소, 종목, 수량)이 누락되었거나 올바르지 않습니다."}), 400

    # 실제 계좌의 보유 잔고 체크 (없는 주식 감시 등록 차단 가드)
    try:
        record, access_key, secret_key = _load_user_exchange_record(auth_header, user_id, exchange, broker_env)
        client = _build_exchange_client(exchange, broker_env, record, access_key, secret_key)
        if not client:
            return jsonify({"success": False, "message": "거래소 클라이언트를 생성할 수 없습니다."}), 400

        holding = _get_holding_info_from_balance(client, symbol)
        if not holding or holding["qty"] <= 0:
            return jsonify({
                "success": False,
                "message": f"현재 {exchange} ({broker_env}) 계좌에 {symbol} 자산의 보유 수량이 없거나 조회할 수 없습니다. 보유 중인 자산에 대해서만 감시 등록이 가능합니다."
            }), 400
    except Exception as e:
        current_app.logger.exception("조건감시 등록 전 보유 잔고 조회 실패")
        return jsonify({"success": False, "message": f"계좌 보유 잔고를 확인할 수 없어 등록이 취소되었습니다. ({str(e)})"}), 400

    # 사용자가 진입가를 입력하지 않았거나, 계좌에 보유 평단가가 유효한 경우 평단가 우선 적용
    final_entry_price = entry_price
    if final_entry_price <= 0 or (holding.get("avg_price") or 0) > 0:
        final_entry_price = holding["avg_price"]

    if final_entry_price <= 0:
        return jsonify({"success": False, "message": "진입 가격(평균단가)을 특정할 수 없어 감시 등록이 불가능합니다."}), 400

    auto_restart_on_partial_fill = req_data.get("auto_restart_on_partial_fill", True)

    rule_data = {
        "user_id": user_id,
        "exchange": exchange,
        "asset_type": asset_type,
        "ticker": symbol,
        "symbol": symbol,
        "broker_env": broker_env,
        "entry_price": final_entry_price,
        "investment_amount": final_entry_price * quantity,
        "quantity": quantity,
        "target_profit_rate": target_profit_rate,
        "stop_loss_rate": stop_loss_rate,
        "execution_mode": execution_mode,
        "auto_restart_on_partial_fill": auto_restart_on_partial_fill,
        "status": "RUNNING",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat()
    }

    try:
        result = query_supabase(auth_header, "auto_trading_rules", "POST", json_data=rule_data)
        return jsonify({"success": True, "message": "조건감시 규칙이 정상적으로 생성되었습니다.", "data": result})
    except Exception as error:
        current_app.logger.exception("조건감시 규칙 생성 실패")
        return jsonify(format_error_payload(error, "조건감시 규칙 생성 실패")), 400


@trade_bp.route("/api/stocks/warnings", methods=["GET"])
def get_stocks_warnings():
    """
    특정 주식 종목의 거래정지, 투자경고, 유의사항 및 VI 발동 정보를 조회합니다.
    """
    auth_header = request.headers.get("Authorization")
    if not auth_header:
        return jsonify({"success": False, "message": "인증 헤더가 누락되었습니다."}), 401

    try:
        user_id, _ = get_user_id_from_header(auth_header)
    except Exception as e:
        return jsonify({"success": False, "message": f"인증 실패: {str(e)}"}), 401

    symbol = request.args.get("symbol", "").strip()
    exchange = request.args.get("exchange", "TOSS").strip().upper()
    broker_env = request.args.get("broker_env", "REAL").strip().upper()

    if not symbol:
        return jsonify({"success": False, "message": "symbol 파라미터가 필수적입니다."}), 400

    try:
        # KIS, TOSS에 무관하게 종목 유의사항은 캘린더처럼 Toss API를 활용해 통합 조회
        client = _get_shared_toss_client(user_id=user_id, broker_env=broker_env)
        if not client:
            return jsonify({"success": False, "message": "Toss 클라이언트를 초기화할 수 없습니다."}), 500

        result = client.get_stock_warnings(symbol)
        warnings = result.get("warnings", [])

        # 추가 조치: 종목 기본 정보 조회를 통해 거래소 거래정지(krx_trading_suspended) 및 정리매매(liquidation_trading) 상태 합성
        try:
            stock_info = client.get_stock_info(symbol)
            if stock_info and isinstance(stock_info, dict):
                korean_detail = stock_info.get("korean_market_detail") or {}

                # 1. 거래정지 융합
                if korean_detail.get("krx_trading_suspended"):
                    if not any(w.get("warning_type") == "TRADING_SUSPENDED" for w in warnings):
                        warnings.insert(0, {
                            "warning_type": "TRADING_SUSPENDED",
                            "exchange": stock_info.get("market"),
                            "start_date": None,
                            "end_date": None,
                            "label": "거래정지",
                            "raw": {"reason": "KRX 거래정지 종목 (stock_info 감지)"}
                        })

                # 2. 정리매매 융합
                if korean_detail.get("liquidation_trading"):
                    if not any(w.get("warning_type") == "LIQUIDATION_TRADING" for w in warnings):
                        warnings.insert(0, {
                            "warning_type": "LIQUIDATION_TRADING",
                            "exchange": stock_info.get("market"),
                            "start_date": None,
                            "end_date": None,
                            "label": "정리매매",
                            "raw": {"reason": "KRX 정리매매 종목 (stock_info 감지)"}
                        })
        except Exception as info_err:
            current_app.logger.warning(f"warnings 라우트 내 stock_info 추가 조회 실패 (비치명적 에러): {str(info_err)}")

        WARNING_LABEL_MAP = {
            "TRADING_SUSPENDED": "거래정지",
            "LIQUIDATION_TRADING": "정리매매",
            "INVESTMENT_RISK": "투자위험",
            "INVESTMENT_WARNING": "투자경고",
            "OVERHEATED": "단기과열",
            "VI_STATIC_AND_DYNAMIC": "정적/동적 VI",
            "VI_STATIC": "정적 VI",
            "VI_DYNAMIC": "동적 VI",
            "STOCK_WARRANTS": "신주인수권",
        }

        for w in warnings:
            w_type = w.get("warning_type", "")
            w["label"] = w.get("label") or w.get("raw", {}).get("label") or WARNING_LABEL_MAP.get(w_type, w_type.replace("_", " "))

        return jsonify({
            "success": True,
            "data": {
                "symbol": symbol,
                "warnings": warnings,
                "symbol_used": result.get("symbol_used")
            }
        })
    except Exception as e:
        current_app.logger.exception("종목 유의사항 조회 실패")
        err_payload = format_error_payload(e, context="종목 유의사항 조회 실패", exchange="TOSS")
        return jsonify(err_payload), 500
