CREATE TABLE IF NOT EXISTS public.ai_fund_strategies (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    exchange_type VARCHAR(32) NOT NULL,
    strategy_type VARCHAR(16) NOT NULL CHECK (strategy_type IN ('DCA', 'GRID')),
    symbol VARCHAR(32) NOT NULL,
    status VARCHAR(16) NOT NULL DEFAULT 'PAUSED' CHECK (status IN ('RUNNING', 'PAUSED', 'HALTED')),
    config JSONB NOT NULL DEFAULT '{}'::jsonb,
    state JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_ai_fund_strategy UNIQUE (user_id, exchange_type, strategy_type, symbol)
);

CREATE INDEX IF NOT EXISTS idx_ai_fund_strategies_running
    ON public.ai_fund_strategies (status, exchange_type, created_at ASC);

ALTER TABLE public.ai_fund_strategies ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Admin access to ai_fund_strategies" ON public.ai_fund_strategies
    FOR ALL TO authenticated
    USING (EXISTS (
        SELECT 1 FROM public.profiles
        WHERE profiles.id = (SELECT auth.uid()) AND profiles.role = 'ADMIN'
    ))
    WITH CHECK (EXISTS (
        SELECT 1 FROM public.profiles
        WHERE profiles.id = (SELECT auth.uid()) AND profiles.role = 'ADMIN'
    ));
