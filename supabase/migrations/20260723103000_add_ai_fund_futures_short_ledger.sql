ALTER TABLE public.admin_ai_fund_configs
    ADD COLUMN IF NOT EXISTS futures_leverage INTEGER NOT NULL DEFAULT 1
        CHECK (futures_leverage BETWEEN 1 AND 10),
    ADD COLUMN IF NOT EXISTS futures_margin_type VARCHAR(16) NOT NULL DEFAULT 'ISOLATED'
        CHECK (futures_margin_type IN ('ISOLATED', 'CROSSED')),
    ADD COLUMN IF NOT EXISTS futures_live_enabled BOOLEAN NOT NULL DEFAULT FALSE;

ALTER TABLE public.ai_fund_orders
    ADD COLUMN IF NOT EXISTS position_direction VARCHAR(8) NOT NULL DEFAULT 'LONG'
        CHECK (position_direction IN ('LONG', 'SHORT')),
    ADD COLUMN IF NOT EXISTS position_side VARCHAR(8),
    ADD COLUMN IF NOT EXISTS leverage INTEGER,
    ADD COLUMN IF NOT EXISTS margin_type VARCHAR(16);

ALTER TABLE public.ai_fund_positions
    ADD COLUMN IF NOT EXISTS position_direction VARCHAR(8) NOT NULL DEFAULT 'LONG'
        CHECK (position_direction IN ('LONG', 'SHORT'));

ALTER TABLE public.ai_fund_positions
    DROP CONSTRAINT IF EXISTS uq_ai_fund_position_strategy;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conrelid = 'public.ai_fund_positions'::regclass
          AND conname = 'uq_ai_fund_position_strategy_direction'
    ) THEN
        ALTER TABLE public.ai_fund_positions
            ADD CONSTRAINT uq_ai_fund_position_strategy_direction
            UNIQUE (user_id, exchange_type, strategy_id, symbol, position_direction);
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_ai_fund_positions_direction
    ON public.ai_fund_positions (user_id, exchange_type, strategy_id, position_direction, symbol);
