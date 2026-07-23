CREATE TABLE IF NOT EXISTS public.ai_fund_strategy_backtests (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    strategy_id UUID NOT NULL REFERENCES public.ai_fund_strategies(id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    exchange_type VARCHAR(32) NOT NULL,
    strategy_type VARCHAR(16) NOT NULL CHECK (strategy_type IN ('DCA', 'GRID')),
    symbol VARCHAR(32) NOT NULL,
    candle_count INTEGER NOT NULL CHECK (candle_count > 0),
    fee_bps NUMERIC(12, 4) NOT NULL DEFAULT 0 CHECK (fee_bps >= 0),
    result JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_ai_fund_strategy_backtests_strategy_created
    ON public.ai_fund_strategy_backtests (strategy_id, created_at DESC);

ALTER TABLE public.ai_fund_strategy_backtests ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Admin access to ai_fund_strategy_backtests" ON public.ai_fund_strategy_backtests
    FOR ALL TO authenticated
    USING (EXISTS (
        SELECT 1 FROM public.profiles
        WHERE profiles.id = (SELECT auth.uid()) AND profiles.role = 'ADMIN'
    ))
    WITH CHECK (EXISTS (
        SELECT 1 FROM public.profiles
        WHERE profiles.id = (SELECT auth.uid()) AND profiles.role = 'ADMIN'
    ));
