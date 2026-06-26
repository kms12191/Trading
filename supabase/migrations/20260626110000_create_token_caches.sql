-- public.token_caches 테이블 생성 (토스/KIS 공용 액세스 토큰 DB 캐시화)
CREATE TABLE IF NOT EXISTS public.token_caches (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    exchange TEXT NOT NULL CHECK (exchange IN ('TOSS', 'KIS')),
    broker_env TEXT NOT NULL CHECK (broker_env IN ('MOCK', 'REAL')),
    encrypted_access_token TEXT NOT NULL,
    expired_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (exchange, broker_env)
);

-- RLS 활성화 (보안 통제)
ALTER TABLE public.token_caches ENABLE ROW LEVEL SECURITY;

-- 일반 사용자(anon, authenticated) 접근 차단, 백엔드 관리자(service_role)만 전체 권한 허용
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_policies
        WHERE schemaname = 'public'
          AND tablename = 'token_caches'
          AND policyname = 'service_role_can_manage_token_caches'
    ) THEN
        CREATE POLICY service_role_can_manage_token_caches
            ON public.token_caches
            FOR ALL
            TO service_role
            USING (true)
            WITH CHECK (true);
    END IF;
END $$;


-- =========================================================================
-- 분산 락 (Distributed Lock) 시스템 테이블 및 RPC 함수 신설
-- =========================================================================

CREATE TABLE IF NOT EXISTS public.active_locks (
    lock_key TEXT PRIMARY KEY,
    owner_id TEXT NOT NULL,
    acquired_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at TIMESTAMPTZ NOT NULL
);

-- RLS 및 권한 설정
ALTER TABLE public.active_locks ENABLE ROW LEVEL SECURITY;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_policies
        WHERE schemaname = 'public'
          AND tablename = 'active_locks'
          AND policyname = 'service_role_can_manage_active_locks'
    ) THEN
        CREATE POLICY service_role_can_manage_active_locks
            ON public.active_locks
            FOR ALL
            TO service_role
            USING (true)
            WITH CHECK (true);
    END IF;
END $$;

-- 락 획득 RPC 함수 생성
CREATE OR REPLACE FUNCTION public.acquire_lock(
    p_lock_key TEXT,
    p_owner_id TEXT,
    p_duration_seconds INTEGER
)
RETURNS BOOLEAN
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
DECLARE
    v_now TIMESTAMPTZ := now();
    v_expires_at TIMESTAMPTZ := v_now + (p_duration_seconds || ' seconds')::INTERVAL;
    v_locked BOOLEAN := FALSE;
BEGIN
    -- 1. 만료된 락은 청소 (정리)
    DELETE FROM public.active_locks WHERE lock_key = p_lock_key AND expires_at < v_now;

    -- 2. 락 획득 시도 (Insert)
    BEGIN
        INSERT INTO public.active_locks (lock_key, owner_id, acquired_at, expires_at)
        VALUES (p_lock_key, p_owner_id, v_now, v_expires_at);
        v_locked := TRUE;
    EXCEPTION WHEN unique_violation THEN
        -- 이미 락이 활성 상태로 존재하면 획득 실패
        v_locked := FALSE;
    END;

    RETURN v_locked;
END;
$$;

-- 락 해제 RPC 함수 생성
CREATE OR REPLACE FUNCTION public.release_lock(
    p_lock_key TEXT,
    p_owner_id TEXT
)
RETURNS BOOLEAN
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
DECLARE
    v_released BOOLEAN := FALSE;
BEGIN
    DELETE FROM public.active_locks 
    WHERE lock_key = p_lock_key AND owner_id = p_owner_id;
    
    IF FOUND THEN
        v_released := TRUE;
    END IF;
    
    RETURN v_released;
END;
$$;
