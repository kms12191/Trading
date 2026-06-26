import os
from datetime import datetime, timedelta
from backend.services.supabase_client import query_supabase_as_service_role, safe_query_supabase_as_service_role
from backend.utils.crypto_helper import CryptoHelper

ENCRYPTION_KEY = os.getenv("ENCRYPTION_KEY", "default-dev-encryption-key-32bytes!")
crypto = CryptoHelper(ENCRYPTION_KEY)

def get_db_token(exchange: str, env: str) -> str | None:
    """
    Supabase DB의 token_caches 테이블로부터 만료되지 않은 유효한 토큰을 조회하여 복호화 후 반환합니다.
    """
    exchange_upper = exchange.upper()
    env_upper = env.upper()

    params = {
        "exchange": f"eq.{exchange_upper}",
        "broker_env": f"eq.{env_upper}"
    }
    
    # service_role 권한으로 token_caches 테이블 조회
    records = safe_query_supabase_as_service_role("token_caches", "GET", params=params)
    if not records or len(records) == 0:
        return None

    record = records[0]
    encrypted_token = record.get("encrypted_access_token")
    expired_at_str = record.get("expired_at")

    if not encrypted_token or not expired_at_str:
        return None

    try:
        # PostgreSQL timestamptz 형식 파싱 (e.g. "2026-06-26T15:24:30+00:00" 또는 "2026-06-26 15:24:30")
        # ISO 포맷 파싱을 위해 timezone Z/Offset 보정
        expired_at_str_clean = expired_at_str.replace("Z", "+00:00")
        expired_at = datetime.fromisoformat(expired_at_str_clean)
        
        # 만료 시각의 타임존 정보가 있으면 KST/UTC 상관없이 현재 시간(aware)과 비교
        # 없으면 기본 naive datetime으로 변환해 비교
        if expired_at.tzinfo is not None:
            now = datetime.now(expired_at.tzinfo)
        else:
            now = datetime.now()

        # 만료 5분(300초) 이상 넉넉히 남아있는 경우에만 기존 토큰 사용
        if (expired_at - now).total_seconds() > 300:
            return crypto.decrypt(encrypted_token)
    except Exception:
        pass

    return None

def set_db_token(exchange: str, env: str, token: str, expires_in: int) -> None:
    """
    새로 발급받은 토큰을 암호화하여 Supabase DB의 token_caches 테이블에 Upsert 처리합니다.
    """
    exchange_upper = exchange.upper()
    env_upper = env.upper()

    encrypted_token = crypto.encrypt(token)
    expired_at = datetime.utcnow() + timedelta(seconds=expires_in)
    expired_at_str = expired_at.isoformat() + "Z"  # UTC ISO 포맷 저장

    payload = {
        "exchange": exchange_upper,
        "broker_env": env_upper,
        "encrypted_access_token": encrypted_token,
        "expired_at": expired_at_str,
        "updated_at": datetime.utcnow().isoformat() + "Z"
    }

    params = {
        "exchange": f"eq.{exchange_upper}",
        "broker_env": f"eq.{env_upper}"
    }

    # 기존 캐시 여부 체크 (GET)
    existing = safe_query_supabase_as_service_role("token_caches", "GET", params=params)

    if existing and len(existing) > 0:
        # 존재하면 갱신 (PATCH)
        record_id = existing[0]["id"]
        query_supabase_as_service_role(f"token_caches?id=eq.{record_id}", "PATCH", json_data=payload)
    else:
        # 없으면 생성 (POST)
        query_supabase_as_service_role("token_caches", "POST", json_data=payload)

def clear_db_token(exchange: str, env: str) -> None:
    """
    토큰 만료나 인증 에러(401) 시, DB의 특정 거래소/환경의 토큰 수명을 과거 시각으로 강제 만료시킵니다.
    """
    exchange_upper = exchange.upper()
    env_upper = env.upper()

    params = {
        "exchange": f"eq.{exchange_upper}",
        "broker_env": f"eq.{env_upper}"
    }

    existing = safe_query_supabase_as_service_role("token_caches", "GET", params=params)
    if existing and len(existing) > 0:
        record_id = existing[0]["id"]
        # 만료 일시를 아주 과거(1970년)로 세팅하여 즉각 무효화 처리
        payload = {
            "expired_at": "1970-01-01T00:00:00Z",
            "updated_at": datetime.utcnow().isoformat() + "Z"
        }
        query_supabase_as_service_role(f"token_caches?id=eq.{record_id}", "PATCH", json_data=payload)
