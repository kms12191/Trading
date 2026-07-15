import base64
import hashlib
import hmac
import json
import math
import time
import uuid


SUPPORTED_EXCHANGES = {"TOSS", "KIS", "COINONE", "BINANCE", "BINANCE_UM_FUTURES"}
SUPPORTED_ASSET_TYPES = {"STOCK", "CRYPTO_SPOT", "CRYPTO_FUTURES"}
SUPPORTED_BROKER_ENVS = {"REAL", "MOCK"}
SUPPORTED_ORDER_TYPES = {"LIMIT", "MARKET"}
SPOT_INTENTS = {"BUY", "SELL"}
FUTURES_INTENTS = {"OPEN_LONG", "OPEN_SHORT", "CLOSE_POSITION"}
FUTURES_POSITION_SIDES = {"LONG", "SHORT"}
FUTURES_MARGIN_TYPES = {"ISOLATED", "CROSSED"}
SERVICE_LEVERAGE_LIMIT = 10
PRECHECK_TOKEN_TTL_SECONDS = 300


def _required_text(values: dict, field: str) -> str:
    value = str(values.get(field) or "").strip()
    if not value:
        raise ValueError(f"필수 주문값 {field}이(가) 누락되었습니다.")
    return value


def _positive_number(value, field: str) -> float:
    try:
        normalized = float(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{field}은(는) 0보다 큰 숫자여야 합니다.") from error
    if not math.isfinite(normalized) or normalized <= 0:
        raise ValueError(f"{field}은(는) 0보다 큰 유한한 숫자여야 합니다.")
    return normalized


def _normalize_uuid(value, field: str) -> str:
    try:
        return str(uuid.UUID(str(value or "").strip()))
    except (AttributeError, TypeError, ValueError) as error:
        raise ValueError(f"{field}에는 유효한 UUID가 필요합니다.") from error


def normalize_order_request(values: dict) -> dict:
    """기본값 보정 없이 구조화 주문 요청을 표준화합니다."""
    if not isinstance(values, dict):
        raise ValueError("구조화 주문 요청 형식이 올바르지 않습니다.")

    account_id = _required_text(values, "account_id")
    exchange = _required_text(values, "exchange").upper()
    asset_type = _required_text(values, "asset_type").upper()
    broker_env = _required_text(values, "broker_env").upper()
    intent = _required_text(values, "intent").upper()
    symbol = _required_text(values, "symbol").upper()
    order_type = _required_text(values, "order_type").upper()
    if values.get("quantity") is None:
        raise ValueError("필수 주문값 quantity이(가) 누락되었습니다.")
    if values.get("idempotency_key") in (None, ""):
        raise ValueError("필수 주문값 idempotency_key이(가) 누락되었습니다.")

    if exchange not in SUPPORTED_EXCHANGES:
        raise ValueError("지원하지 않는 거래소입니다.")
    if asset_type not in SUPPORTED_ASSET_TYPES:
        raise ValueError("지원하지 않는 자산 유형입니다.")
    if broker_env not in SUPPORTED_BROKER_ENVS:
        raise ValueError("거래 환경은 REAL 또는 MOCK이어야 합니다.")
    if order_type not in SUPPORTED_ORDER_TYPES:
        raise ValueError("주문 유형은 LIMIT 또는 MARKET이어야 합니다.")
    if values.get("symbol_selected") is not True:
        raise ValueError("거래 가능 종목 검색 결과에서 종목을 선택해 주세요.")

    is_futures = exchange == "BINANCE_UM_FUTURES"
    if is_futures:
        if asset_type != "CRYPTO_FUTURES" or intent not in FUTURES_INTENTS:
            raise ValueError("선물 주문의 자산 유형 또는 거래 목적이 올바르지 않습니다.")
    else:
        expected_asset_type = "STOCK" if exchange in {"TOSS", "KIS"} else "CRYPTO_SPOT"
        if asset_type != expected_asset_type or intent not in SPOT_INTENTS:
            raise ValueError("계좌와 거래 목적에 맞지 않는 주문입니다.")

    quantity = _positive_number(values.get("quantity"), "주문 수량")
    price = None
    if order_type == "LIMIT":
        if values.get("price") in (None, ""):
            raise ValueError("지정가 주문에는 0보다 큰 가격이 필요합니다.")
        price = _positive_number(values.get("price"), "지정가")
    elif values.get("price") not in (None, ""):
        price = _positive_number(values.get("price"), "주문 가격")

    normalized = {
        "account_id": account_id,
        "exchange": exchange,
        "asset_type": asset_type,
        "broker_env": broker_env,
        "intent": intent,
        "symbol": symbol,
        "symbol_selected": True,
        "quantity": quantity,
        "order_type": order_type,
        "price": price,
        "idempotency_key": _normalize_uuid(values.get("idempotency_key"), "idempotency_key"),
    }

    if is_futures:
        try:
            leverage = int(values.get("leverage") or 1)
        except (TypeError, ValueError) as error:
            raise ValueError("레버리지는 1 이상의 정수여야 합니다.") from error
        if leverage < 1:
            raise ValueError("레버리지는 1 이상의 정수여야 합니다.")
        margin_type = str(values.get("margin_type") or "ISOLATED").strip().upper()
        if margin_type == "CROSS":
            margin_type = "CROSSED"
        if margin_type not in FUTURES_MARGIN_TYPES:
            raise ValueError("마진 모드는 ISOLATED 또는 CROSSED여야 합니다.")
        position_side = str(values.get("position_side") or "").strip().upper() or None
        if position_side and position_side not in FUTURES_POSITION_SIDES:
            raise ValueError("포지션 방향은 LONG 또는 SHORT여야 합니다.")
        if intent == "CLOSE_POSITION" and not position_side:
            raise ValueError("청산할 포지션 방향을 선택해 주세요.")
        normalized.update({
            "leverage": leverage,
            "margin_type": margin_type,
            "position_side": position_side,
            "side": "BUY" if intent in {"OPEN_LONG"} or position_side == "SHORT" else "SELL",
        })
    else:
        normalized["side"] = intent

    return normalized


def resolve_futures_execution(intent: str, position_mode: str, position_side: str | None) -> dict:
    """사용자 거래 목적을 바이낸스 One-way/Hedge 주문 필드로 변환합니다."""
    normalized_intent = str(intent or "").strip().upper()
    normalized_mode = str(position_mode or "").strip().upper().replace("-", "_")
    normalized_side = str(position_side or "").strip().upper() or None
    if normalized_intent not in FUTURES_INTENTS:
        raise ValueError("지원하지 않는 선물 거래 목적입니다.")
    if normalized_mode not in {"ONE_WAY", "HEDGE"}:
        raise ValueError("바이낸스 포지션 모드를 확인할 수 없습니다.")
    if normalized_intent == "CLOSE_POSITION" and normalized_side not in FUTURES_POSITION_SIDES:
        raise ValueError("청산할 포지션 방향을 선택해 주세요.")

    if normalized_intent == "OPEN_LONG":
        side = "BUY"
        target_side = "LONG"
    elif normalized_intent == "OPEN_SHORT":
        side = "SELL"
        target_side = "SHORT"
    else:
        side = "SELL" if normalized_side == "LONG" else "BUY"
        target_side = normalized_side

    if normalized_mode == "ONE_WAY":
        return {
            "side": side,
            "position_side": "BOTH",
            "reduce_only": normalized_intent == "CLOSE_POSITION",
        }
    return {
        "side": side,
        "position_side": target_side,
        "reduce_only": False,
    }


def resolve_service_leverage_limit(exchange_limit: int | None, configured_limit: str | None) -> int:
    """거래소 상한, 서비스 10배 상한, 운영 설정 중 가장 낮은 값을 반환합니다."""
    try:
        configured = int(configured_limit or SERVICE_LEVERAGE_LIMIT)
    except (TypeError, ValueError):
        configured = SERVICE_LEVERAGE_LIMIT
    service_limit = min(max(configured, 1), SERVICE_LEVERAGE_LIMIT)
    if exchange_limit in (None, ""):
        return service_limit
    try:
        return min(service_limit, max(int(exchange_limit), 1))
    except (TypeError, ValueError):
        return service_limit


def _canonical_json(value: dict) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def order_request_hash(values: dict) -> str:
    """정규화 주문 전체의 변경 감지용 SHA-256 해시를 생성합니다."""
    return hashlib.sha256(_canonical_json(values)).hexdigest()


def _b64encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _b64decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(f"{value}{padding}".encode("ascii"))


def issue_precheck_token(
    user_id: str,
    order: dict,
    precheck: dict,
    secret: str,
    now: int | None = None,
    ttl_seconds: int = PRECHECK_TOKEN_TTL_SECONDS,
) -> str:
    """사용자·주문·사전검증 스냅샷을 묶은 단기 HMAC 토큰을 발급합니다."""
    issued_at = int(time.time() if now is None else now)
    payload = {
        "version": 1,
        "user_id": str(user_id),
        "issued_at": issued_at,
        "expires_at": issued_at + int(ttl_seconds),
        "order_hash": order_request_hash(order),
        "precheck": precheck,
    }
    encoded_payload = _b64encode(_canonical_json(payload))
    signature = hmac.new(str(secret).encode("utf-8"), encoded_payload.encode("ascii"), hashlib.sha256).digest()
    return f"{encoded_payload}.{_b64encode(signature)}"


def verify_precheck_token(
    token: str,
    user_id: str,
    order: dict,
    secret: str,
    now: int | None = None,
) -> dict:
    """사전검증 토큰의 서명, 사용자, 만료, 주문 해시를 검증합니다."""
    try:
        encoded_payload, encoded_signature = str(token or "").split(".", 1)
        provided_signature = _b64decode(encoded_signature)
    except (TypeError, ValueError, UnicodeError) as error:
        raise ValueError("사전검증 토큰 서명이 올바르지 않습니다.") from error

    expected_signature = hmac.new(
        str(secret).encode("utf-8"),
        encoded_payload.encode("ascii"),
        hashlib.sha256,
    ).digest()
    if not hmac.compare_digest(provided_signature, expected_signature):
        raise ValueError("사전검증 토큰 서명이 올바르지 않습니다.")

    try:
        payload = json.loads(_b64decode(encoded_payload).decode("utf-8"))
    except (ValueError, UnicodeError, json.JSONDecodeError) as error:
        raise ValueError("사전검증 토큰 내용을 읽을 수 없습니다.") from error

    current_time = int(time.time() if now is None else now)
    if current_time > int(payload.get("expires_at") or 0):
        raise ValueError("사전검증 토큰이 만료되었습니다. 다시 검증해 주세요.")
    if str(payload.get("user_id") or "") != str(user_id):
        raise ValueError("사전검증 토큰의 사용자가 일치하지 않습니다.")
    if str(payload.get("order_hash") or "") != order_request_hash(order):
        raise ValueError("사전검증 토큰과 현재 주문 조건이 일치하지 않습니다.")
    if not isinstance(payload.get("precheck"), dict):
        raise ValueError("사전검증 토큰에 검증 결과가 없습니다.")
    return payload
