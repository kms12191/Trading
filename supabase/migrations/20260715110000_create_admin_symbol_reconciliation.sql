CREATE TABLE IF NOT EXISTS public.admin_symbol_reconciliation_runs (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    started_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc'::text, now()),
    finished_at TIMESTAMPTZ,
    status TEXT NOT NULL DEFAULT 'RUNNING' CHECK (status IN ('RUNNING', 'COMPLETED', 'FAILED')),
    checked_count INTEGER NOT NULL DEFAULT 0,
    normal_count INTEGER NOT NULL DEFAULT 0,
    suspicious_count INTEGER NOT NULL DEFAULT 0,
    deactivation_candidate_count INTEGER NOT NULL DEFAULT 0,
    deletable_count INTEGER NOT NULL DEFAULT 0,
    raw_summary JSONB,
    created_by UUID REFERENCES public.profiles(id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc'::text, now())
);

CREATE TABLE IF NOT EXISTS public.admin_symbol_reconciliation_items (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    run_id UUID NOT NULL REFERENCES public.admin_symbol_reconciliation_runs(id) ON DELETE CASCADE,
    symbol TEXT NOT NULL,
    name TEXT,
    source_table TEXT NOT NULL CHECK (source_table IN ('kis_stock_master', 'kis_stock_turnover_latest')),
    market_country TEXT,
    market_segment TEXT,
    status TEXT NOT NULL CHECK (status IN ('NORMAL', 'SUSPICIOUS', 'DEACTIVATION_CANDIDATE', 'INACTIVE', 'DELETABLE')),
    reason TEXT,
    suggested_action TEXT NOT NULL DEFAULT 'NONE' CHECK (suggested_action IN ('NONE', 'REVIEW', 'DEACTIVATE', 'DELETE_CACHE', 'DELETE_MASTER', 'RESTORE')),
    broker_check_result JSONB,
    reference_count INTEGER NOT NULL DEFAULT 0,
    last_seen_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc'::text, now())
);

CREATE TABLE IF NOT EXISTS public.symbol_aliases (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    alias_symbol TEXT NOT NULL UNIQUE,
    canonical_symbol TEXT NOT NULL,
    alias_type TEXT NOT NULL DEFAULT 'TEMPORARY' CHECK (alias_type IN ('TEMPORARY', 'RENAMED', 'DELISTED', 'MANUAL')),
    label TEXT,
    reason TEXT,
    market_country TEXT,
    source TEXT NOT NULL DEFAULT 'ADMIN',
    is_active BOOLEAN NOT NULL DEFAULT true,
    created_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc'::text, now()),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc'::text, now())
);

CREATE INDEX IF NOT EXISTS idx_admin_symbol_reconciliation_runs_started
    ON public.admin_symbol_reconciliation_runs (started_at DESC);

CREATE INDEX IF NOT EXISTS idx_admin_symbol_reconciliation_items_run_status
    ON public.admin_symbol_reconciliation_items (run_id, status, symbol);

CREATE INDEX IF NOT EXISTS idx_symbol_aliases_active_type
    ON public.symbol_aliases (is_active, alias_type, alias_symbol);

ALTER TABLE public.admin_symbol_reconciliation_runs ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.admin_symbol_reconciliation_items ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.symbol_aliases ENABLE ROW LEVEL SECURITY;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE schemaname = 'public'
          AND tablename = 'admin_symbol_reconciliation_runs'
          AND policyname = 'service_role_can_manage_admin_symbol_reconciliation_runs'
    ) THEN
        CREATE POLICY service_role_can_manage_admin_symbol_reconciliation_runs
            ON public.admin_symbol_reconciliation_runs
            FOR ALL
            USING (auth.role() = 'service_role')
            WITH CHECK (auth.role() = 'service_role');
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE schemaname = 'public'
          AND tablename = 'admin_symbol_reconciliation_items'
          AND policyname = 'service_role_can_manage_admin_symbol_reconciliation_items'
    ) THEN
        CREATE POLICY service_role_can_manage_admin_symbol_reconciliation_items
            ON public.admin_symbol_reconciliation_items
            FOR ALL
            USING (auth.role() = 'service_role')
            WITH CHECK (auth.role() = 'service_role');
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE schemaname = 'public'
          AND tablename = 'symbol_aliases'
          AND policyname = 'service_role_can_manage_symbol_aliases'
    ) THEN
        CREATE POLICY service_role_can_manage_symbol_aliases
            ON public.symbol_aliases
            FOR ALL
            USING (auth.role() = 'service_role')
            WITH CHECK (auth.role() = 'service_role');
    END IF;
END $$;

INSERT INTO public.symbol_aliases (
    alias_symbol,
    canonical_symbol,
    alias_type,
    label,
    reason,
    market_country,
    source,
    is_active
)
VALUES (
    'SKHYV',
    'SKHY',
    'TEMPORARY',
    '임시코드',
    'SK하이닉스 ADR 정식 상장 전 사용된 임시 해외주식 심볼',
    'US',
    'ADMIN',
    true
)
ON CONFLICT (alias_symbol) DO UPDATE
SET canonical_symbol = EXCLUDED.canonical_symbol,
    alias_type = EXCLUDED.alias_type,
    label = EXCLUDED.label,
    reason = EXCLUDED.reason,
    market_country = EXCLUDED.market_country,
    source = EXCLUDED.source,
    is_active = EXCLUDED.is_active,
    updated_at = timezone('utc'::text, now());
