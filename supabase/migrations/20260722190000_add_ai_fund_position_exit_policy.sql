ALTER TABLE public.ai_fund_positions
    ADD COLUMN IF NOT EXISTS exit_policy JSONB NOT NULL DEFAULT '{}'::jsonb;

COMMENT ON COLUMN public.ai_fund_positions.exit_policy
    IS '부분 익절, 본전 손절, 트레일링 손절의 설정 및 실행 상태';
