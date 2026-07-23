ALTER TABLE public.admin_ai_fund_configs
    ADD COLUMN IF NOT EXISTS operation_mode VARCHAR(16) NOT NULL DEFAULT 'PAPER',
    ADD COLUMN IF NOT EXISTS canary_max_order_amount NUMERIC(18, 4);

ALTER TABLE public.admin_ai_fund_configs
    DROP CONSTRAINT IF EXISTS admin_ai_fund_configs_operation_mode_check;

ALTER TABLE public.admin_ai_fund_configs
    ADD CONSTRAINT admin_ai_fund_configs_operation_mode_check
    CHECK (operation_mode IN ('PAPER', 'CANARY', 'LIVE'));

ALTER TABLE public.admin_ai_fund_configs
    DROP CONSTRAINT IF EXISTS admin_ai_fund_configs_canary_limit_check;

ALTER TABLE public.admin_ai_fund_configs
    ADD CONSTRAINT admin_ai_fund_configs_canary_limit_check
    CHECK (
        operation_mode <> 'CANARY'
        OR canary_max_order_amount IS NOT NULL AND canary_max_order_amount > 0
    );

COMMENT ON COLUMN public.admin_ai_fund_configs.operation_mode
    IS 'AI 위탁운용 실행 모드: PAPER, CANARY, LIVE';
COMMENT ON COLUMN public.admin_ai_fund_configs.canary_max_order_amount
    IS 'CANARY 모드에서 허용할 주문당 최대 금액';
