-- 1. token_caches 테이블에 credential_hash 컬럼 추가
ALTER TABLE public.token_caches 
ADD COLUMN IF NOT EXISTS credential_hash TEXT;

-- 2. 기존 user_id IS NULL 기반의 단일 공용 고유 인덱스 삭제
DROP INDEX IF EXISTS public.token_caches_null_user_id_exchange_broker_env_idx;

-- 3. 새로운 API Key 해시 기반 공용 고유 인덱스 생성
CREATE UNIQUE INDEX IF NOT EXISTS token_caches_credential_hash_exchange_broker_env_idx 
ON public.token_caches (credential_hash, exchange, broker_env) 
WHERE user_id IS NULL AND credential_hash IS NOT NULL;

-- 4. 혼선 방지를 위한 기존 user_id가 없고 credential_hash가 없는 레코드 정리 (만료 처리)
DELETE FROM public.token_caches 
WHERE user_id IS NULL AND credential_hash IS NULL;
