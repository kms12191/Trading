import re
import time
import threading
import requests
from datetime import datetime
from flask import Blueprint, request, jsonify, current_app
from backend.services.supabase_client import query_supabase
from backend.services.auth_service import get_user_id_from_header
from backend.services.toss_client import TossClient
from backend.services.kis_client import KISClient

# 단기 인메모리 시세 캐시 정의 (Rate limit 방지용)
CANDLE_CACHE = {}
ORDERBOOK_CACHE = {}
TRADES_CACHE = {}
PRICE_CHANGE_CACHE = {}
PRICE_CHANGE_CACHE_TTL = 10
CACHE_TTL_SECONDS = 10  # 기본값 10초 유효
LEVEL2_CACHE_TTL_SECONDS = 10
REAL_ORDER_LIMIT_KRW = 100000.0

def get_cached_change_rate(exchange, symbol, broker_env, auth_header):
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
                    current_app.logger.warning(f"TOSS get_price failed in get_cached_change_rate: {str(toss_err)}. KIS 폴백을 시도합니다.")
                    records = []
            
            # TOSS 키가 없거나 호출이 실패한 경우 KIS 키로 폴백하여 시세 및 전일대비율을 구합니다.
            if not records:
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
                if data.get("result") == "success" and data.get("tickers"):
                    ticker = data["tickers"][0]
                    last = float(ticker.get("last", 0))
                    yesterday_last = float(ticker.get("yesterday_last", last))
                    if yesterday_last > 0:
                        change_rate = ((last - yesterday_last) / yesterday_last) * 100
        elif exchange == "BINANCE":
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

def is_kr_market_open() -> bool:
    """
    현재 한국 장(KRX)이 열려 있는지 여부를 판단합니다. (평일 09:00 ~ 15:30 KST)
    """
    kst_now = datetime.now(datetime_timezone(timedelta(hours=9)))
    if kst_now.weekday() >= 5:
        return False
    start_time = kst_now.replace(hour=9, minute=0, second=0, microsecond=0)
    end_time = kst_now.replace(hour=15, minute=30, second=0, microsecond=0)
    return start_time <= kst_now <= end_time

def is_us_market_open() -> bool:
    """
    현재 미국 주식 시장이 열려 있는지 여부를 판단합니다. (미동부 통합 운영 04:00 ~ 20:00 EST/EDT)
    """
    utc_now = datetime.now(datetime_timezone.utc)
    # 3~10월은 서머타임(EDT = UTC-4), 11~2월은 표준시(EST = UTC-5)로 대략적 추정
    month = utc_now.month
    est_offset = timedelta(hours=-4) if 3 <= month <= 10 else timedelta(hours=-5)
    est_now = utc_now.astimezone(datetime_timezone(est_offset))
    
    if est_now.weekday() >= 5:
        return False
        
    start_time = est_now.replace(hour=4, minute=0, second=0, microsecond=0)
    end_time = est_now.replace(hour=20, minute=0, second=0, microsecond=0)
    return start_time <= est_now <= end_time

def get_dynamic_ttl(exchange: str, symbol: str, interval: str) -> int:
    """
    거래소, 종목 심볼, 주기에 맞춰 최적화된 동적 캐시 TTL을 반환합니다.
    """
    exchange_upper = exchange.upper()
    
    if exchange_upper in ("COINONE", "BINANCE"):
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
    params = {
        "user_id": f"eq.{user_id}",
        "exchange": f"eq.{exchange}",
        "broker_env": f"eq.{broker_env}"
    }
    records = query_supabase(auth_header, "user_api_keys", "GET", params=params)
    if not records:
        raise ValueError(f"등록된 {exchange} ({broker_env}) API 크리덴셜 정보가 없습니다.")

    record = records[0]
    access_key = crypto_helper.decrypt(record.get("encrypted_access_key"))
    secret_key = crypto_helper.decrypt(record.get("encrypted_secret_key"))
    return record, access_key, secret_key


def _query_user_exchange_records(auth_header: str, user_id: str, exchange: str, broker_env: str | None = None) -> list[dict]:
    """
    사용자 거래소 크리덴셜 레코드를 조회합니다.
    broker_env가 없으면 해당 거래소의 전체 레코드를 반환합니다.
    """
    params = {
        "user_id": f"eq.{user_id}",
        "exchange": f"eq.{exchange}",
    }
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
    return None


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


def _patch_trade_proposal(auth_header: str, proposal_id: str, payload: dict):
    """
    trade_proposals 레코드를 부분 업데이트합니다.
    """
    return query_supabase(auth_header, f"trade_proposals?id=eq.{proposal_id}", "PATCH", json_data=payload)


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


def _is_terminal_order_status(status: str | None) -> bool:
    """
    거래소 주문 상태가 더 이상 정정/취소될 수 없는 상태인지 판단합니다.
    """
    normalized = str(status or "").upper()
    return normalized in {"EXECUTED", "FILLED", "COMPLETED", "DONE", "CANCELED", "CANCELLED", "REJECTED", "FAILED", "EXPIRED"}


def _resolve_proposal_broker_env(proposal: dict, fallback: str | None = None) -> str:
    """
    거래내역 레코드에 저장된 broker_env를 우선 사용하고, 과거 레코드는 요청값 또는 REAL로 보정합니다.
    """
    return str(proposal.get("broker_env") or fallback or "REAL").upper()


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
    current_order = client.get_modifiable_order(
        proposal.get("external_order_id"),
        order_org_no=_resolve_order_org_no(proposal),
    )
    if current_order.get("is_modifiable"):
        return current_order

    _mark_kis_order_closed(auth_header, proposal_id, current_order)
    raise ValueError("이미 체결되어 정정/취소할 수 없습니다.")


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
        if resolved_price <= 0:
            raise ValueError("주문 단가는 0보다 커야 합니다.")
        return resolved_price, "LIMIT_INPUT"

    if exchange not in ("TOSS", "KIS") or client is None:
        raise ValueError(f"{exchange} 거래소는 현재 시장가 조회가 지원되지 않습니다.")

    price_info = client.get_price(symbol)
    resolved_price = float(price_info.get("current_price", 0) or 0)
    if resolved_price <= 0:
        raise ValueError("시장가 검증을 위한 현재가를 확인할 수 없습니다.")
    return resolved_price, "LIVE_PRICE"


def _extract_balance_snapshot(client, symbol: str) -> dict:
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
    try:
        available_cash = float(available_cash) if available_cash is not None else None
    except (TypeError, ValueError):
        available_cash = None

    holding_qty = None
    holding_value = None
    for item in balance.get("holdings", []) or []:
        holding_symbol = str(item.get("symbol", "")).upper()
        if holding_symbol != str(symbol).upper():
            continue
        try:
            holding_qty = float(item.get("qty", 0))
            current_price = float(item.get("current_price", 0))
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
) -> dict:
    """
    주문 전 검증 결과를 공통 포맷으로 생성합니다.
    """
    try:
        qty = float(quantity)
    except (TypeError, ValueError):
        raise ValueError("올바르지 않은 주문 수량 포맷입니다.")
    if qty <= 0:
        raise ValueError("주문 수량은 0보다 커야 합니다.")

    client = _build_exchange_client(exchange, broker_env, record, access_key, secret_key)
    reference_price, price_source = _resolve_reference_price(exchange, symbol, order_type, price, client)
    estimated_amount = reference_price * qty
    estimated_amount_krw = estimated_amount * 1400.0 if exchange == "BINANCE" else estimated_amount
    balance_snapshot = _extract_balance_snapshot(client, symbol)
    available_cash = balance_snapshot["available_cash"]
    holding_qty = balance_snapshot["holding_qty"]

    exceeds_hard_cap = broker_env == "REAL" and estimated_amount_krw > REAL_ORDER_LIMIT_KRW
    insufficient_cash = (
        action.upper() == "BUY"
        and broker_env == "REAL"
        and available_cash is not None
        and estimated_amount > available_cash
    )
    insufficient_holding = (
        action.upper() == "SELL"
        and broker_env == "REAL"
        and holding_qty is not None
        and qty > holding_qty
    )

    asset_type = "STOCK" if exchange in ("TOSS", "KIS") else "CRYPTO"
    currency = "KRW" if exchange in ("TOSS", "KIS", "COINONE") else "USD"
    warnings = []
    if exceeds_hard_cap:
        warnings.append("실거래 1회 주문 한도 10만원을 초과합니다.")
    if insufficient_cash:
        warnings.append("예수금 대비 주문 예정 금액이 큽니다.")
    if insufficient_holding:
        warnings.append("보유 수량보다 많은 매도 주문입니다.")

    return {
        "exchange": exchange,
        "symbol": symbol,
        "action": action.upper(),
        "order_type": order_type.upper(),
        "broker_env": broker_env,
        "asset_type": asset_type,
        "currency": currency,
        "quantity": qty,
        "reference_price": reference_price,
        "price_source": price_source,
        "estimated_amount": estimated_amount,
        "estimated_amount_krw": estimated_amount_krw,
        "real_order_limit_krw": REAL_ORDER_LIMIT_KRW,
        "exceeds_real_order_limit": exceeds_hard_cap,
        "available_cash": available_cash,
        "holding_qty": holding_qty,
        "holding_value": balance_snapshot["holding_value"],
        "insufficient_cash": insufficient_cash,
        "insufficient_holding": insufficient_holding,
        "warnings": warnings,
        "checked_at": datetime.utcnow().isoformat() + "Z",
    }


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
    except Exception as e:
        return jsonify({"success": False, "message": f"인증 실패: {str(e)}"}), 401

    data = request.json or {}
    exchange = data.get("exchange")
    symbol = data.get("symbol")
    action = data.get("action")
    order_type = data.get("order_type")
    quantity = data.get("quantity")
    price = data.get("price")
    broker_env = data.get("broker_env", "REAL")

    if not exchange or not symbol or not action or not order_type or quantity is None:
        return jsonify({"success": False, "message": "필수 주문 파라미터가 누락되었습니다."}), 400
    if exchange not in ("TOSS", "KIS", "COINONE", "BINANCE"):
        return jsonify({"success": False, "message": "지원하지 않는 거래소입니다."}), 400
    if action.upper() not in ("BUY", "SELL"):
        return jsonify({"success": False, "message": "올바르지 않은 주문 방향(action)입니다."}), 400
    if order_type.upper() not in ("LIMIT", "MARKET"):
        return jsonify({"success": False, "message": "올바르지 않은 주문 유형(order_type)입니다."}), 400

    try:
        record, access_key, secret_key = _load_user_exchange_record(auth_header, user_id, exchange, broker_env)
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
        )
        return jsonify({"success": True, "data": payload})
    except ValueError as e:
        return jsonify({"success": False, "message": str(e)}), 400
    except Exception as e:
        return jsonify({"success": False, "message": f"주문 사전검증 실패: {str(e)}"}), 500

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
    exchange = data.get("exchange")
    symbol = data.get("symbol")
    action = data.get("action")  # BUY or SELL
    order_type = data.get("order_type")  # LIMIT or MARKET
    price = data.get("price")  # LIMIT일 때 필수
    quantity = data.get("quantity")  # 필수
    broker_env = data.get("broker_env", "REAL")  # MOCK or REAL
    
    # 1. 필수 파라미터 검증
    if not exchange or not symbol or not action or not order_type or quantity is None:
        return jsonify({"success": False, "message": "필수 주문 파라미터가 누락되었습니다."}), 400
    
    if exchange not in ("TOSS", "KIS", "COINONE", "BINANCE"):
        return jsonify({"success": False, "message": "지원하지 않는 거래소입니다."}), 400

    if action.upper() not in ("BUY", "SELL"):
        return jsonify({"success": False, "message": "올바르지 않은 주문 방향(action)입니다."}), 400

    if order_type.upper() not in ("LIMIT", "MARKET"):
        return jsonify({"success": False, "message": "올바르지 않은 주문 유형(order_type)입니다."}), 400

    try:
        qty = float(quantity)
        if qty <= 0:
            return jsonify({"success": False, "message": "주문 수량은 0보다 커야 합니다."}), 400
    except ValueError:
        return jsonify({"success": False, "message": "올바르지 않은 주문 수량 포맷입니다."}), 400

    try:
        record, access_key, secret_key = _load_user_exchange_record(auth_header, user_id, exchange, broker_env)
    except ValueError as e:
        return jsonify({"success": False, "message": str(e)}), 400
    except Exception as e:
        return jsonify({"success": False, "message": f"API 크리덴셜 로드 및 복호화 실패: {str(e)}"}), 500

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
        )
    except ValueError as e:
        return jsonify({"success": False, "message": str(e)}), 400
    except Exception as e:
        return jsonify({"success": False, "message": f"주문 사전검증 실패: {str(e)}"}), 500

    order_price = precheck["reference_price"]
    total_amount = precheck["estimated_amount"]
    total_amount_krw = precheck["estimated_amount_krw"]

    if precheck["exceeds_real_order_limit"]:
        return jsonify({
            "success": False,
            "message": f"실거래 1회 주문 한도(100,000원)를 초과할 수 없습니다. (신청 금액: {total_amount_krw:,.0f}원)"
        }), 400

    if precheck["insufficient_cash"]:
        return jsonify({"success": False, "message": "예수금보다 큰 주문입니다. 주문 수량 또는 단가를 조정해 주세요."}), 400

    if precheck["insufficient_holding"]:
        return jsonify({"success": False, "message": "보유 수량을 초과하는 매도 주문입니다."}), 400

    # 4. 주문 실행
    try:
        if exchange == "TOSS":
            client = _build_exchange_client(exchange, broker_env, record, access_key, secret_key)
            order_res = client.place_order(symbol=symbol, qty=qty, side=action, ord_type=order_type, price=order_price)
        elif exchange == "KIS":
            client = _build_exchange_client(exchange, broker_env, record, access_key, secret_key)
            order_res = client.place_order(symbol=symbol, qty=qty, side=action, ord_type=order_type, price=order_price)
        else:
            return jsonify({"success": False, "message": f"{exchange} 거래소는 현재 수동 주문 기능이 지원되지 않습니다."}), 400
    except Exception as e:
        return jsonify({"success": False, "message": f"주문 전송 실패: {str(e)}"}), 500

    # 5. 주문 체결 성공 후 자동 감시(Stop-loss, Take-profit) 바인딩
    auto_exit_result = None
    auto_exit = data.get("auto_exit", False)
    if auto_exit and action.upper() == "BUY":
        target_profit_rate = float(data.get("target_profit_rate", 5.0))
        stop_loss_rate = float(data.get("stop_loss_rate", -3.0))
        
        # asset_type 및 market_country 판정
        asset_type = "STOCK" if exchange in ("TOSS", "KIS") else "CRYPTO"
        market_country = None
        if asset_type == "STOCK":
            market_country = "KR" if re.match(r"^\d{6}$", symbol) else "US"

        try:
            rule_data = {
                "user_id": user_id,
                "exchange": exchange,
                "asset_type": asset_type,
                "ticker": symbol,
                "symbol": symbol,
                "market_country": market_country,
                "entry_price": order_price,
                "investment_amount": total_amount,
                "target_profit_rate": target_profit_rate,
                "stop_loss_rate": stop_loss_rate,
                "status": "RUNNING"
            }
            # Supabase에 감시 조건 등록
            query_supabase(auth_header, "auto_trading_rules", "POST", json_data=rule_data)
            auto_exit_result = "감시 조건 등록 완료"
        except Exception as e:
            auto_exit_result = f"감시 조건 등록 실패: {str(e)}"

    # 6. 주문 이력 trade_proposals에 EXECUTED 상태로 등록 (수동 거래 히스토리 기록용)
    try:
        asset_type = "STOCK" if exchange in ("TOSS", "KIS") else "CRYPTO"
        market_country = None
        if asset_type == "STOCK":
            market_country = "KR" if re.match(r"^\d{6}$", symbol) else "US"
        currency = "KRW" if (exchange != "BINANCE" and market_country != "US") else "USD"
        
        proposal_data = {
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
            "raw_order_payload": order_res.get("raw"),
            "status": "EXECUTED" if _is_terminal_order_status(order_res.get("status")) else "APPROVED"
        }
        _insert_trade_proposal_with_schema_fallback(auth_header, proposal_data)
    except Exception as e:
        current_app.logger.error(f"주문 이력 기록 실패: {str(e)}")

    return jsonify({
        "success": True,
        "message": "주문이 성공적으로 전송되었습니다.",
        "order_id": order_res.get("order_id"),
        "status": order_res.get("status"),
        "auto_exit": auto_exit_result,
        "detail": order_res
    })


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
        return jsonify({"success": False, "message": f"거래내역 조회 실패: {str(e)}"}), 500

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
    if exchange not in ("TOSS", "KIS"):
        return jsonify({"success": False, "message": f"{exchange} 주문 취소는 아직 지원하지 않습니다."}), 400

    try:
        record, access_key, secret_key = _load_user_exchange_record(auth_header, user_id, exchange, broker_env)
        client = _build_exchange_client(exchange, broker_env, record, access_key, secret_key)
        current_status = client.get_order_status(order_id)
        if exchange != "KIS" and _is_terminal_order_status(current_status.get("status")):
            return jsonify({"success": False, "message": "이미 체결 또는 종료된 주문이라 취소할 수 없습니다.", "detail": current_status}), 400

        if exchange == "KIS":
            _ensure_kis_order_modifiable(auth_header, proposal_id, proposal, client)
            cancel_result = client.cancel_order(order_id, order_org_no=_resolve_order_org_no(proposal))
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
        _patch_trade_proposal(auth_header, proposal_id, {
            "failure_reason": f"주문 취소 실패: {str(e)[:500]}",
        })
        return jsonify({"success": False, "message": f"주문 취소 실패: {str(e)}"}), 500


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
        return jsonify({"success": False, "message": f"거래내역 조회 실패: {str(e)}"}), 500

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

    try:
        price_value = float(new_price) if new_price not in (None, "") else None
        quantity_value = float(new_quantity) if new_quantity not in (None, "") else None
        if price_value is not None and price_value <= 0:
            return jsonify({"success": False, "message": "정정 가격은 0보다 커야 합니다."}), 400
        if quantity_value is not None and quantity_value <= 0:
            return jsonify({"success": False, "message": "정정 수량은 0보다 커야 합니다."}), 400

        record, access_key, secret_key = _load_user_exchange_record(auth_header, user_id, exchange, broker_env)
        client = _build_exchange_client(exchange, broker_env, record, access_key, secret_key)
        current_status = client.get_order_status(order_id)
        if exchange != "KIS" and _is_terminal_order_status(current_status.get("status")):
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
            modify_result = client.modify_order(order_id, price=price_value, quantity=quantity_value)
        patch_payload = {
            "status": "MODIFIED",
            "failure_reason": None,
            "modified_at": datetime.utcnow().isoformat() + "Z",
        }
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
        _patch_trade_proposal(auth_header, proposal_id, {
            "failure_reason": f"주문 정정 실패: {str(e)[:500]}",
        })
        return jsonify({"success": False, "message": f"주문 정정 실패: {str(e)}"}), 500


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
        return jsonify({"success": False, "message": f"거래내역 조회 실패: {str(e)}"}), 500

    exchange = proposal.get("exchange")
    if exchange not in ("COINONE", "BINANCE"):
        return jsonify({"success": False, "message": "취소 후 재주문은 Coinone/Binance 주문에만 사용합니다."}), 400

    status = str(proposal.get("status") or "").upper()
    if status in {"EXECUTED", "CANCELED", "REJECTED", "FAILED"}:
        return jsonify({"success": False, "message": "이미 완료되었거나 재주문할 수 없는 주문입니다."}), 400

    if proposal.get("external_order_id"):
        return jsonify({
            "success": False,
            "message": f"{exchange} 실제 주문 취소 API 연결 전에는 거래소 주문번호가 있는 주문을 취소 후 재주문할 수 없습니다.",
        }), 400

    try:
        price_value = float(new_price) if new_price not in (None, "") else float(proposal.get("price") or 0)
        quantity_value = float(new_quantity) if new_quantity not in (None, "") else float(proposal.get("volume") or 0)
        if price_value <= 0:
            return jsonify({"success": False, "message": "재주문 가격은 0보다 커야 합니다."}), 400
        if quantity_value <= 0:
            return jsonify({"success": False, "message": "재주문 수량은 0보다 커야 합니다."}), 400

        _patch_trade_proposal(auth_header, proposal_id, {
            "status": "CANCELED",
            "failure_reason": None,
            "canceled_at": datetime.utcnow().isoformat() + "Z",
        })

        replacement_payload = {
            "user_id": user_id,
            "exchange": exchange,
            "asset_type": proposal.get("asset_type") or "CRYPTO",
            "ticker": proposal.get("ticker"),
            "symbol": proposal.get("symbol") or proposal.get("ticker"),
            "broker_env": _resolve_proposal_broker_env(proposal, data.get("broker_env")),
            "side": proposal.get("side"),
            "price": price_value,
            "volume": quantity_value,
            "ord_type": proposal.get("ord_type") or "LIMIT",
            "market_country": proposal.get("market_country"),
            "currency": proposal.get("currency") or ("USD" if exchange == "BINANCE" else "KRW"),
            "replaced_from_id": proposal_id,
            "status": "PENDING",
        }
        created = _insert_trade_proposal_with_schema_fallback(auth_header, replacement_payload)
        return jsonify({
            "success": True,
            "message": "기존 주문 제안을 취소하고 재주문 제안을 생성했습니다.",
            "status": "PENDING",
            "data": created,
        })
    except ValueError as e:
        return jsonify({"success": False, "message": str(e)}), 400
    except Exception as e:
        _patch_trade_proposal(auth_header, proposal_id, {
            "failure_reason": f"취소 후 재주문 실패: {str(e)[:500]}",
        })
        return jsonify({"success": False, "message": f"취소 후 재주문 실패: {str(e)}"}), 500

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
                
            url = f"https://api.coinone.co.kr/public/v2/chart/KRW/{symbol.upper()}"
            res = requests.get(url, params={"interval": coinone_interval})
            if res.status_code != 200:
                return jsonify({"success": False, "message": f"Coinone 차트 조회 실패: {res.text}"}), 500
                
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
        elif exchange == "BINANCE":
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
                return jsonify({"success": False, "message": f"Binance 차트 조회 실패: {res.text}"}), 500
                
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
        return jsonify({"success": False, "message": f"시세 차트 조회 실패: {str(e)}"}), 500


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
        elif exchange == "BINANCE":
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
        elif exchange == "BINANCE":
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


@trade_bp.route("/api/symbol/lookup", methods=["GET"])
def lookup_symbol():
    """
    종목명(예: 'SK하이닉스', '하이닉스') 또는 심볼(예: '000660', 'BTC')을 기반으로
    정밀 매핑된 종목코드와 자산 타입(STOCK | CRYPTO)을 찾아 반환합니다.
    """
    query = request.args.get("query", "").strip().upper()
    if not query:
        return jsonify({"success": False, "message": "query 파라미터가 필수적입니다."}), 400

    import re
    from backend.services.symbol_metadata import SYMBOL_METADATA, search_crypto_symbols, COIN_DISPLAY_NAMES
    from backend.services.market_repository import MarketRepository

    # 1. 완전 일치 매칭 (하드코딩 SYMBOL_METADATA)
    for sym, meta in SYMBOL_METADATA.items():
        if sym.upper() == query or meta.get("display_name", "").upper() == query:
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
            symbol_to_use = f"{base_sym}USDT"
            return jsonify({
                "success": True,
                "data": {
                    "symbol": symbol_to_use,
                    "display_name": name,
                    "asset_type": "CRYPTO",
                    "market": "USDT"
                }
            })

    # 3. 주식 마스터 DB 정밀 매칭
    repo = MarketRepository()
    db_results = repo.search_stock_master(query, limit=5)
    
    for row in db_results:
        clean_name = re.sub(r"^KR\d{10}", "", row["name"]).strip()
        if row["symbol"] == query or clean_name.upper() == query or row["name"].upper() == query:
            return jsonify({
                "success": True,
                "data": {
                    "symbol": row["symbol"],
                    "display_name": clean_name,
                    "asset_type": "STOCK",
                    "market": "KR"
                }
            })

    # 4. 부분 일치 매칭 (SYMBOL_METADATA)
    for sym, meta in SYMBOL_METADATA.items():
        if query in meta.get("display_name", "").upper() or query in sym:
            return jsonify({
                "success": True,
                "data": {
                    "symbol": sym,
                    "display_name": meta.get("display_name"),
                    "asset_type": meta.get("asset_type"),
                    "market": meta.get("market")
                }
            })

    # 5. 주식 DB 부분 일치 매칭 폴백
    if db_results:
        best_match = db_results[0]
        clean_name = re.sub(r"^KR\d{10}", "", best_match["name"]).strip()
        return jsonify({
            "success": True,
            "data": {
                "symbol": best_match["symbol"],
                "display_name": clean_name,
                "asset_type": "STOCK",
                "market": "KR"
            }
        })

    # 6. 매칭 실패 시 기본값 반환 (Toss 등 신규 등록 주식/코인 대비)
    return jsonify({
        "success": True,
        "data": {
            "symbol": query,
            "display_name": query,
            "asset_type": "STOCK",
            "market": ""
        }
    })


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
                "market": "KR"
            })

    # 가독성을 위해 코드 길이 순 및 사전 순 정렬
    results.sort(key=lambda x: (len(x["symbol"]), x["display_name"]))

    return jsonify({"success": True, "data": results[:10]})
