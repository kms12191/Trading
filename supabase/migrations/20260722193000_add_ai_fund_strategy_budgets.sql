ALTER TABLE public.admin_ai_fund_configs
    ADD COLUMN IF NOT EXISTS strategy_budgets JSONB NOT NULL DEFAULT '{}'::jsonb;

ALTER TABLE public.ai_fund_orders
    ADD COLUMN IF NOT EXISTS strategy_id VARCHAR(64) NOT NULL DEFAULT 'ml_signal';

ALTER TABLE public.ai_fund_fills
    ADD COLUMN IF NOT EXISTS strategy_id VARCHAR(64) NOT NULL DEFAULT 'ml_signal';

ALTER TABLE public.ai_fund_positions
    ADD COLUMN IF NOT EXISTS strategy_id VARCHAR(64) NOT NULL DEFAULT 'ml_signal';

ALTER TABLE public.admin_ai_trade_logs
    ADD COLUMN IF NOT EXISTS strategy_id VARCHAR(64) NOT NULL DEFAULT 'ml_signal';

ALTER TABLE public.ai_fund_positions
    DROP CONSTRAINT IF EXISTS uq_ai_fund_position;

ALTER TABLE public.ai_fund_positions
    ADD CONSTRAINT uq_ai_fund_position_strategy UNIQUE (user_id, exchange_type, strategy_id, symbol);

CREATE INDEX IF NOT EXISTS idx_ai_fund_orders_strategy_open
    ON public.ai_fund_orders (user_id, exchange_type, strategy_id, status, created_at DESC);
