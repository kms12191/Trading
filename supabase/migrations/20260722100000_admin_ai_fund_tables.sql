-- Create admin AI fund configurations and trade execution logs with RLS policies.
-- This version must precede dependent AI fund ledger and operation-mode migrations.

CREATE TABLE IF NOT EXISTS public.admin_ai_fund_configs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    exchange_type VARCHAR(32) NOT NULL,
    allocated_capital NUMERIC(18, 4) NOT NULL DEFAULT 0.0,
    max_position_size NUMERIC(18, 4) NOT NULL DEFAULT 0.0,
    risk_preset VARCHAR(16) NOT NULL DEFAULT 'neutral',
    daily_mdd_limit_pct NUMERIC(5, 2) NOT NULL DEFAULT -2.0,
    min_signal_confidence NUMERIC(4, 3) NOT NULL DEFAULT 0.750,
    is_active BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_admin_fund_user_exchange UNIQUE (user_id, exchange_type)
);

CREATE TABLE IF NOT EXISTS public.admin_ai_trade_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    exchange_type VARCHAR(32) NOT NULL,
    symbol VARCHAR(32) NOT NULL,
    side VARCHAR(8) NOT NULL,
    confidence_score NUMERIC(5, 4) NOT NULL,
    executed_price NUMERIC(18, 4) NOT NULL,
    executed_qty NUMERIC(18, 6) NOT NULL,
    total_amount NUMERIC(18, 4) NOT NULL,
    order_id VARCHAR(128),
    status VARCHAR(16) NOT NULL DEFAULT 'SUCCESS',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

ALTER TABLE public.admin_ai_fund_configs ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.admin_ai_trade_logs ENABLE ROW LEVEL SECURITY;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE schemaname = 'public'
          AND tablename = 'admin_ai_fund_configs'
          AND policyname = 'Admin access to admin_ai_fund_configs'
    ) THEN
        CREATE POLICY "Admin access to admin_ai_fund_configs" ON public.admin_ai_fund_configs
            FOR ALL USING (
                EXISTS (
                    SELECT 1 FROM public.profiles
                    WHERE profiles.id = auth.uid() AND profiles.role = 'ADMIN'
                )
            );
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE schemaname = 'public'
          AND tablename = 'admin_ai_trade_logs'
          AND policyname = 'Admin access to admin_ai_trade_logs'
    ) THEN
        CREATE POLICY "Admin access to admin_ai_trade_logs" ON public.admin_ai_trade_logs
            FOR ALL USING (
                EXISTS (
                    SELECT 1 FROM public.profiles
                    WHERE profiles.id = auth.uid() AND profiles.role = 'ADMIN'
                )
            );
    END IF;
END $$;
