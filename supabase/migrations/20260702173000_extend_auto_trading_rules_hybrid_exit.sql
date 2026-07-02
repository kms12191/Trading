ALTER TABLE public.auto_trading_rules ADD COLUMN IF NOT EXISTS symbol TEXT;
ALTER TABLE public.auto_trading_rules ADD COLUMN IF NOT EXISTS broker_env TEXT DEFAULT 'REAL';
ALTER TABLE public.auto_trading_rules ADD COLUMN IF NOT EXISTS market_country TEXT;
ALTER TABLE public.auto_trading_rules ADD COLUMN IF NOT EXISTS quantity NUMERIC;
ALTER TABLE public.auto_trading_rules ADD COLUMN IF NOT EXISTS execution_mode TEXT NOT NULL DEFAULT 'PROPOSAL';
ALTER TABLE public.auto_trading_rules ADD COLUMN IF NOT EXISTS trigger_side TEXT;
ALTER TABLE public.auto_trading_rules ADD COLUMN IF NOT EXISTS trigger_price NUMERIC;
ALTER TABLE public.auto_trading_rules ADD COLUMN IF NOT EXISTS triggered_at TIMESTAMP WITH TIME ZONE;
ALTER TABLE public.auto_trading_rules ADD COLUMN IF NOT EXISTS last_checked_at TIMESTAMP WITH TIME ZONE;
ALTER TABLE public.auto_trading_rules ADD COLUMN IF NOT EXISTS last_error TEXT;
ALTER TABLE public.auto_trading_rules ADD COLUMN IF NOT EXISTS exit_order_proposal_id UUID REFERENCES public.trade_proposals(id) ON DELETE SET NULL;
ALTER TABLE public.auto_trading_rules ADD COLUMN IF NOT EXISTS exit_order_payload JSONB;

UPDATE public.auto_trading_rules
SET symbol = COALESCE(symbol, ticker),
    broker_env = COALESCE(broker_env, 'REAL'),
    execution_mode = COALESCE(execution_mode, 'PROPOSAL')
WHERE symbol IS NULL
   OR broker_env IS NULL
   OR execution_mode IS NULL;

ALTER TABLE public.auto_trading_rules DROP CONSTRAINT IF EXISTS auto_trading_rules_exchange_check;
ALTER TABLE public.auto_trading_rules
    ADD CONSTRAINT auto_trading_rules_exchange_check
    CHECK (exchange IN ('COINONE', 'BINANCE', 'BINANCE_UM_FUTURES', 'KIS', 'TOSS'));

ALTER TABLE public.auto_trading_rules DROP CONSTRAINT IF EXISTS auto_trading_rules_broker_env_check;
ALTER TABLE public.auto_trading_rules
    ADD CONSTRAINT auto_trading_rules_broker_env_check
    CHECK (broker_env IN ('MOCK', 'REAL'));

ALTER TABLE public.auto_trading_rules DROP CONSTRAINT IF EXISTS auto_trading_rules_execution_mode_check;
ALTER TABLE public.auto_trading_rules
    ADD CONSTRAINT auto_trading_rules_execution_mode_check
    CHECK (execution_mode IN ('PROPOSAL', 'AUTO'));

ALTER TABLE public.auto_trading_rules DROP CONSTRAINT IF EXISTS auto_trading_rules_trigger_side_check;
ALTER TABLE public.auto_trading_rules
    ADD CONSTRAINT auto_trading_rules_trigger_side_check
    CHECK (trigger_side IS NULL OR trigger_side IN ('TAKE_PROFIT', 'STOP_LOSS'));

CREATE INDEX IF NOT EXISTS idx_auto_trading_rules_running
    ON public.auto_trading_rules (status, exchange, symbol, broker_env)
    WHERE status = 'RUNNING';

CREATE INDEX IF NOT EXISTS idx_auto_trading_rules_user_symbol
    ON public.auto_trading_rules (user_id, exchange, symbol, broker_env, created_at DESC);
