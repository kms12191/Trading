import os
from datetime import datetime, timedelta

from backend.services.supabase_client import (
    query_supabase_as_service_role,
    safe_query_supabase_as_service_role,
)
from backend.utils.crypto_helper import CryptoHelper

ENCRYPTION_KEY = os.getenv("ENCRYPTION_KEY", "default-dev-encryption-key-32bytes!")
crypto = CryptoHelper(ENCRYPTION_KEY)


def get_db_token_with_status(
    exchange: str,
    env: str,
    user_id: str | None = None,
    credential_hash: str | None = None,
) -> dict:
    """
    Returns a DB token together with cache metadata.
    """
    result = {
        "token": None,
        "cache_status": "MISS",
        "token_status": "REFRESHED",
        "error_message": None,
        "expired_at": None,
    }

    exchange_upper = exchange.upper()
    env_upper = env.upper()

    params = {
        "exchange": f"eq.{exchange_upper}",
        "broker_env": f"eq.{env_upper}",
    }
    if user_id:
        params["user_id"] = f"eq.{user_id}"
        params["credential_hash"] = "is.null"
    elif credential_hash:
        params["user_id"] = "is.null"
        params["credential_hash"] = f"eq.{credential_hash}"
    else:
        params["user_id"] = "is.null"
        params["credential_hash"] = "is.null"

    try:
        records = safe_query_supabase_as_service_role("token_caches", "GET", params=params)
        if not records:
            return result

        record = records[0]
        encrypted_token = record.get("encrypted_access_token")
        expired_at_str = record.get("expired_at")
        if not encrypted_token or not expired_at_str:
            return result

        expired_at_str_clean = expired_at_str.replace("Z", "+00:00")
        expired_at = datetime.fromisoformat(expired_at_str_clean)
        if expired_at.tzinfo is not None:
            now = datetime.now(expired_at.tzinfo)
        else:
            now = datetime.now()

        # 만료 5분 이내 토큰은 재사용하지 않고 새로 발급하도록 둔다.
        # 실제 만료 직전까지 쓰면 요청 실패가 잦아져서, 완충 구간을 남겨 둔 것이다.
        if (expired_at - now).total_seconds() <= 300:
            return result

        result["token"] = crypto.decrypt(encrypted_token)
        result["cache_status"] = "HIT"
        result["token_status"] = "REUSED"
        result["expired_at"] = expired_at.isoformat()
        return result
    except Exception as exc:
        result["error_message"] = str(exc)
        return result


def get_db_token(
    exchange: str,
    env: str,
    user_id: str | None = None,
    credential_hash: str | None = None,
) -> str | None:
    """
    Returns a valid token from Supabase token_caches.
    """
    # 기존 호출부는 토큰 값만 필요하므로 기존 반환형을 유지한다.
    # 새 메타데이터가 필요하면 get_db_token_with_status를 직접 쓰면 된다.
    return get_db_token_with_status(exchange, env, user_id, credential_hash).get("token")


def set_db_token(
    exchange: str,
    env: str,
    token: str,
    expires_in: int,
    user_id: str | None = None,
    credential_hash: str | None = None,
) -> None:
    """
    Store the freshly issued token into Supabase token_caches.
    """
    exchange_upper = exchange.upper()
    env_upper = env.upper()

    encrypted_token = crypto.encrypt(token)
    expired_at = datetime.utcnow() + timedelta(seconds=expires_in)
    expired_at_str = expired_at.isoformat() + "Z"

    payload = {
        "exchange": exchange_upper,
        "broker_env": env_upper,
        "encrypted_access_token": encrypted_token,
        "expired_at": expired_at_str,
        "updated_at": datetime.utcnow().isoformat() + "Z",
    }
    if user_id:
        payload["user_id"] = user_id
        payload["credential_hash"] = None
    elif credential_hash:
        payload["user_id"] = None
        payload["credential_hash"] = credential_hash
    else:
        payload["user_id"] = None
        payload["credential_hash"] = None

    params = {
        "exchange": f"eq.{exchange_upper}",
        "broker_env": f"eq.{env_upper}",
    }
    if user_id:
        params["user_id"] = f"eq.{user_id}"
        params["credential_hash"] = "is.null"
    elif credential_hash:
        params["user_id"] = "is.null"
        params["credential_hash"] = f"eq.{credential_hash}"
    else:
        params["user_id"] = "is.null"
        params["credential_hash"] = "is.null"

    existing = safe_query_supabase_as_service_role("token_caches", "GET", params=params)
    if existing and len(existing) > 0:
        record_id = existing[0]["id"]
        query_supabase_as_service_role(f"token_caches?id=eq.{record_id}", "PATCH", json_data=payload)
    else:
        query_supabase_as_service_role("token_caches", "POST", json_data=payload)


def clear_db_token(
    exchange: str,
    env: str,
    user_id: str | None = None,
    credential_hash: str | None = None,
) -> None:
    """
    Force-expire a stored token so the next request refreshes it.
    """
    exchange_upper = exchange.upper()
    env_upper = env.upper()

    params = {
        "exchange": f"eq.{exchange_upper}",
        "broker_env": f"eq.{env_upper}",
    }
    if user_id:
        params["user_id"] = f"eq.{user_id}"
        params["credential_hash"] = "is.null"
    elif credential_hash:
        params["user_id"] = "is.null"
        params["credential_hash"] = f"eq.{credential_hash}"
    else:
        params["user_id"] = "is.null"
        params["credential_hash"] = "is.null"

    existing = safe_query_supabase_as_service_role("token_caches", "GET", params=params)
    if existing and len(existing) > 0:
        record_id = existing[0]["id"]
        payload = {
            "expired_at": "1970-01-01T00:00:00Z",
            "updated_at": datetime.utcnow().isoformat() + "Z",
        }
        query_supabase_as_service_role(f"token_caches?id=eq.{record_id}", "PATCH", json_data=payload)
