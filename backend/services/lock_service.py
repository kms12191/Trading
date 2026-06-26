import os
import uuid
from contextlib import contextmanager
from backend.services.supabase_client import query_supabase_as_service_role

# 현재 백엔드 프로세스의 고유 식별자 생성
PROCESS_OWNER_ID = f"worker-{os.getpid()}-{uuid.uuid4().hex[:8]}"

@contextmanager
def distributed_lock(lock_key: str, duration_seconds: int = 1800):
    """
    Supabase DB 기반의 active_locks 테이블을 활용한 분산 락 컨텍스트 매니저입니다.
    Gunicorn 다중 Worker 및 다중 개발자 환경에서 중복 실행을 배타적으로 제어합니다.
    """
    acquired = False
    try:
        payload = {
            "p_lock_key": lock_key,
            "p_owner_id": PROCESS_OWNER_ID,
            "p_duration_seconds": duration_seconds
        }
        # RPC 락 획득 시도
        res = query_supabase_as_service_role("rpc/acquire_lock", "POST", json_data=payload)
        
        # PostgREST RPC 응답값은 단일 scalar 또는 boolean 결과
        acquired = bool(res)
        yield acquired
    except Exception as e:
        # 락 관련 조회 중 예외가 발생하더라도 프로세스 중단 없이 실패 처리로 유도
        yield False
    finally:
        # 락을 정상적으로 획득했었던 프로세스인 경우에만 락 해제
        if acquired:
            try:
                payload = {
                    "p_lock_key": lock_key,
                    "p_owner_id": PROCESS_OWNER_ID
                }
                query_supabase_as_service_role("rpc/release_lock", "POST", json_data=payload)
            except Exception:
                pass
