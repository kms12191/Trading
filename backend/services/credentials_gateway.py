import time
import os
from flask import current_app
from backend.services.supabase_client import query_supabase
from backend.utils.crypto_helper import CryptoHelper

class CredentialsGateway:
    _instance = None

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = super().__new__(cls)
            cls._instance._key_cache = {}
            cls._instance._key_ttl_seconds = 60
        return cls._instance

    def _get_crypto_helper(self):
        try:
            if current_app and hasattr(current_app, "crypto"):
                return current_app.crypto
        except RuntimeError:
            pass
        return CryptoHelper(os.getenv("ENCRYPTION_KEY", "temporary-key-for-test"))

    def _check_system_key_match(self, exchange: str, decrypted_access_key: str) -> str | None:
        if exchange == "TOSS":
            sys_key = os.getenv("TOSS_API_KEY")
            if sys_key and sys_key.strip() == decrypted_access_key.strip():
                return "system_toss"
        elif exchange == "KIS":
            sys_key = os.getenv("KIS_APPKEY")
            if sys_key and sys_key.strip() == decrypted_access_key.strip():
                return "system_kis"
        return None

    def _resolve_cache_key(self, user_id: str, exchange: str, broker_env: str) -> tuple[str, str, str]:
        return (user_id, exchange, broker_env)

    def get_credentials(self, auth_header: str, user_id: str, exchange: str, broker_env: str) -> dict:
        now = time.time()
        
        # 1차 일반 캐시 탐색
        normal_key = self._resolve_cache_key(user_id, exchange, broker_env)
        if normal_key in self._key_cache:
            entry = self._key_cache[normal_key]
            if now - entry["cached_at"] < self._key_ttl_seconds:
                return entry["data"]

        # 캐시가 없다면 DB에서 조회 및 복호화
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
        crypto = self._get_crypto_helper()
        access_key = crypto.decrypt(record.get("encrypted_access_key"))
        secret_key = crypto.decrypt(record.get("encrypted_secret_key"))

        # 시스템 키와 동일한지 체크하여 캐시 식별자 결정
        matched_system_user = self._check_system_key_match(exchange, access_key)
        final_user_id = matched_system_user if matched_system_user else user_id
        final_key = (final_user_id, exchange, broker_env)

        # 시스템 키 캐시 히트 검사
        if final_key in self._key_cache:
            entry = self._key_cache[final_key]
            if now - entry["cached_at"] < self._key_ttl_seconds:
                # 일반 키 영역에도 링크 캐싱
                self._key_cache[normal_key] = entry
                return entry["data"]

        data = {
            "id": record.get("id"),
            "access_key": access_key,
            "secret_key": secret_key,
            "toss_account_seq": record.get("toss_account_seq"),
            "toss_account_no": record.get("toss_account_no"),
            "kis_account_no": record.get("kis_account_no"),
            "kis_account_code": record.get("kis_account_code", "01"),
        }

        entry_data = {
            "data": data,
            "cached_at": now
        }
        
        self._key_cache[final_key] = entry_data
        self._key_cache[normal_key] = entry_data
        return data

    def invalidate_cache(self, user_id: str, exchange: str, broker_env: str) -> None:
        normal_key = self._resolve_cache_key(user_id, exchange, broker_env)
        if normal_key in self._key_cache:
            del self._key_cache[normal_key]
            
        # 시스템 매핑 캐시도 함께 무효화 유도
        for matched in ["system_toss", "system_kis"]:
            sys_key = (matched, exchange, broker_env)
            if sys_key in self._key_cache:
                del self._key_cache[sys_key]
