-- 1. user_api_keys 테이블 exchange CHECK 제약 갱신
ALTER TABLE public.user_api_keys DROP CONSTRAINT IF EXISTS user_api_keys_exchange_check;
ALTER TABLE public.user_api_keys ADD CONSTRAINT user_api_keys_exchange_check CHECK (exchange IN ('UPBIT', 'KIS', 'TOSS'));

-- 2. Toss 전용 계좌 식별 컬럼 추가
ALTER TABLE public.user_api_keys ADD COLUMN IF NOT EXISTS toss_account_seq TEXT;
ALTER TABLE public.user_api_keys ADD COLUMN IF NOT EXISTS toss_account_no TEXT;

-- 3. kis_env -> broker_env 변경
-- 기존 컬럼이 존재할 경우에만 RENAME 하도록 처리 (오류 방지)
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 
        FROM information_schema.columns 
        WHERE table_schema = 'public' 
          AND table_name = 'user_api_keys' 
          AND column_name = 'kis_env'
    ) THEN
        ALTER TABLE public.user_api_keys RENAME COLUMN kis_env TO broker_env;
    END IF;
END $$;

-- 4. broker_env CHECK 제약 갱신
ALTER TABLE public.user_api_keys DROP CONSTRAINT IF EXISTS user_api_keys_kis_env_check;
ALTER TABLE public.user_api_keys DROP CONSTRAINT IF EXISTS user_api_keys_broker_env_check;
ALTER TABLE public.user_api_keys ADD CONSTRAINT user_api_keys_broker_env_check CHECK (broker_env IN ('MOCK', 'REAL'));

-- 5. UNIQUE 제약조건 갱신
ALTER TABLE public.user_api_keys DROP CONSTRAINT IF EXISTS user_api_keys_user_id_exchange_kis_env_key;
ALTER TABLE public.user_api_keys DROP CONSTRAINT IF EXISTS user_api_keys_user_id_exchange_broker_env_key;
ALTER TABLE public.user_api_keys ADD CONSTRAINT user_api_keys_user_id_exchange_broker_env_key UNIQUE (user_id, exchange, broker_env);
