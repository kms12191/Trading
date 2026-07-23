CREATE TABLE IF NOT EXISTS public.ai_fund_trade_intents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    exchange_type VARCHAR(32) NOT NULL,
    strategy_id VARCHAR(64) NOT NULL DEFAULT 'ml_signal',
    source VARCHAR(16) NOT NULL CHECK (source IN ('AI', 'RULE', 'WEBHOOK', 'MANUAL')),
    source_id VARCHAR(128) NOT NULL,
    idempotency_key VARCHAR(256) NOT NULL UNIQUE,
    symbol VARCHAR(32) NOT NULL,
    side VARCHAR(8) NOT NULL CHECK (side IN ('BUY', 'SELL')),
    confidence NUMERIC(5, 4),
    expires_at TIMESTAMPTZ,
    status VARCHAR(16) NOT NULL CHECK (status IN ('PENDING', 'APPROVED', 'REJECTED', 'EXECUTED', 'EXPIRED')),
    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_ai_fund_trade_intents_pending
    ON public.ai_fund_trade_intents (user_id, exchange_type, status, created_at ASC);

ALTER TABLE public.ai_fund_trade_intents ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Admin access to ai_fund_trade_intents" ON public.ai_fund_trade_intents
    FOR ALL TO authenticated
    USING (EXISTS (
        SELECT 1 FROM public.profiles
        WHERE profiles.id = (SELECT auth.uid()) AND profiles.role = 'ADMIN'
    ))
    WITH CHECK (EXISTS (
        SELECT 1 FROM public.profiles
        WHERE profiles.id = (SELECT auth.uid()) AND profiles.role = 'ADMIN'
    ));
