CREATE TABLE IF NOT EXISTS public.ai_fund_orders (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    config_id UUID REFERENCES public.admin_ai_fund_configs(id) ON DELETE SET NULL,
    exchange_type VARCHAR(32) NOT NULL,
    client_order_id VARCHAR(128) NOT NULL UNIQUE,
    exchange_order_id VARCHAR(128),
    symbol VARCHAR(32) NOT NULL,
    side VARCHAR(8) NOT NULL CHECK (side IN ('BUY', 'SELL')),
    order_type VARCHAR(16) NOT NULL,
    requested_qty NUMERIC(28, 12) NOT NULL CHECK (requested_qty > 0),
    requested_price NUMERIC(28, 12),
    filled_qty NUMERIC(28, 12) NOT NULL DEFAULT 0 CHECK (filled_qty >= 0),
    average_fill_price NUMERIC(28, 12),
    fee_amount NUMERIC(28, 12) NOT NULL DEFAULT 0,
    status VARCHAR(32) NOT NULL CHECK (status IN (
        'PENDING_SUBMIT', 'SUBMITTED', 'PARTIALLY_FILLED', 'FILLED',
        'CANCEL_REQUESTED', 'CANCELED', 'REJECTED', 'FAILED', 'NEEDS_REVIEW'
    )),
    failure_reason TEXT,
    raw_response JSONB NOT NULL DEFAULT '{}'::jsonb,
    last_synced_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS public.ai_fund_fills (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    order_id UUID NOT NULL REFERENCES public.ai_fund_orders(id) ON DELETE CASCADE,
    exchange_type VARCHAR(32) NOT NULL,
    exchange_fill_id VARCHAR(128),
    symbol VARCHAR(32) NOT NULL,
    side VARCHAR(8) NOT NULL CHECK (side IN ('BUY', 'SELL')),
    quantity NUMERIC(28, 12) NOT NULL CHECK (quantity > 0),
    price NUMERIC(28, 12) NOT NULL CHECK (price >= 0),
    fee_amount NUMERIC(28, 12) NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_ai_fund_exchange_fill UNIQUE NULLS NOT DISTINCT (exchange_type, exchange_fill_id)
);

CREATE TABLE IF NOT EXISTS public.ai_fund_positions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    exchange_type VARCHAR(32) NOT NULL,
    symbol VARCHAR(32) NOT NULL,
    quantity NUMERIC(28, 12) NOT NULL DEFAULT 0 CHECK (quantity >= 0),
    average_entry_price NUMERIC(28, 12) NOT NULL DEFAULT 0 CHECK (average_entry_price >= 0),
    realized_pnl NUMERIC(28, 12) NOT NULL DEFAULT 0,
    last_reconciled_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_ai_fund_position UNIQUE (user_id, exchange_type, symbol)
);

CREATE TABLE IF NOT EXISTS public.ai_fund_reconciliation_runs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    config_id UUID REFERENCES public.admin_ai_fund_configs(id) ON DELETE SET NULL,
    exchange_type VARCHAR(32) NOT NULL,
    status VARCHAR(16) NOT NULL CHECK (status IN ('STARTED', 'COMPLETED', 'FAILED', 'NEEDS_REVIEW')),
    mismatch_count INTEGER NOT NULL DEFAULT 0 CHECK (mismatch_count >= 0),
    details JSONB NOT NULL DEFAULT '{}'::jsonb,
    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_ai_fund_orders_open
    ON public.ai_fund_orders (user_id, exchange_type, status, updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_ai_fund_positions_lookup
    ON public.ai_fund_positions (user_id, exchange_type, symbol);
CREATE INDEX IF NOT EXISTS idx_ai_fund_fills_order
    ON public.ai_fund_fills (order_id, created_at);

ALTER TABLE public.ai_fund_orders ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.ai_fund_fills ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.ai_fund_positions ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.ai_fund_reconciliation_runs ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Admin access to ai_fund_orders" ON public.ai_fund_orders
    FOR ALL TO authenticated
    USING (EXISTS (
        SELECT 1 FROM public.profiles
        WHERE profiles.id = (SELECT auth.uid()) AND profiles.role = 'ADMIN'
    ))
    WITH CHECK (EXISTS (
        SELECT 1 FROM public.profiles
        WHERE profiles.id = (SELECT auth.uid()) AND profiles.role = 'ADMIN'
    ));

CREATE POLICY "Admin access to ai_fund_fills" ON public.ai_fund_fills
    FOR ALL TO authenticated
    USING (EXISTS (
        SELECT 1 FROM public.profiles
        WHERE profiles.id = (SELECT auth.uid()) AND profiles.role = 'ADMIN'
    ))
    WITH CHECK (EXISTS (
        SELECT 1 FROM public.profiles
        WHERE profiles.id = (SELECT auth.uid()) AND profiles.role = 'ADMIN'
    ));

CREATE POLICY "Admin access to ai_fund_positions" ON public.ai_fund_positions
    FOR ALL TO authenticated
    USING (EXISTS (
        SELECT 1 FROM public.profiles
        WHERE profiles.id = (SELECT auth.uid()) AND profiles.role = 'ADMIN'
    ))
    WITH CHECK (EXISTS (
        SELECT 1 FROM public.profiles
        WHERE profiles.id = (SELECT auth.uid()) AND profiles.role = 'ADMIN'
    ));

CREATE POLICY "Admin access to ai_fund_reconciliation_runs" ON public.ai_fund_reconciliation_runs
    FOR ALL TO authenticated
    USING (EXISTS (
        SELECT 1 FROM public.profiles
        WHERE profiles.id = (SELECT auth.uid()) AND profiles.role = 'ADMIN'
    ))
    WITH CHECK (EXISTS (
        SELECT 1 FROM public.profiles
        WHERE profiles.id = (SELECT auth.uid()) AND profiles.role = 'ADMIN'
    ));
