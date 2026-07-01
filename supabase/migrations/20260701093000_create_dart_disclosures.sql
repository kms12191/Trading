CREATE TABLE IF NOT EXISTS public.dart_corp_codes (
    corp_code TEXT PRIMARY KEY,
    corp_name TEXT NOT NULL,
    stock_code TEXT NOT NULL UNIQUE,
    modify_date DATE,
    market_country TEXT NOT NULL DEFAULT 'KR' CHECK (market_country IN ('KR')),
    raw_payload JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_dart_corp_codes_stock_code
    ON public.dart_corp_codes (stock_code);

CREATE INDEX IF NOT EXISTS idx_dart_corp_codes_corp_name
    ON public.dart_corp_codes (corp_name);

ALTER TABLE public.dart_corp_codes ENABLE ROW LEVEL SECURITY;

CREATE TABLE IF NOT EXISTS public.dart_disclosures (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    rcept_no TEXT NOT NULL UNIQUE,
    corp_code TEXT NOT NULL,
    stock_code TEXT NOT NULL,
    corp_name TEXT NOT NULL,
    corp_cls TEXT,
    report_nm TEXT NOT NULL,
    flr_nm TEXT,
    rcept_dt DATE NOT NULL,
    rm TEXT,
    url TEXT NOT NULL,
    summary TEXT,
    is_active BOOLEAN NOT NULL DEFAULT true,
    fetched_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    raw_payload JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_dart_disclosures_stock_date
    ON public.dart_disclosures (stock_code, rcept_dt DESC);

CREATE INDEX IF NOT EXISTS idx_dart_disclosures_corp_code
    ON public.dart_disclosures (corp_code);

CREATE INDEX IF NOT EXISTS idx_dart_disclosures_rcept_dt
    ON public.dart_disclosures (rcept_dt DESC);

CREATE INDEX IF NOT EXISTS idx_dart_disclosures_report_nm
    ON public.dart_disclosures (report_nm);

ALTER TABLE public.dart_disclosures ENABLE ROW LEVEL SECURITY;

CREATE TABLE IF NOT EXISTS public.dart_fetch_logs (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    source TEXT NOT NULL DEFAULT 'OPENDART',
    query_key TEXT NOT NULL,
    query_category TEXT,
    query_text TEXT,
    status TEXT NOT NULL CHECK (status IN ('SUCCESS', 'FAILED', 'SKIPPED')),
    fetched_count INTEGER NOT NULL DEFAULT 0,
    inserted_count INTEGER NOT NULL DEFAULT 0,
    request_count INTEGER NOT NULL DEFAULT 0,
    skipped_reason TEXT,
    error_message TEXT,
    started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_dart_fetch_logs_started
    ON public.dart_fetch_logs (started_at DESC);

CREATE INDEX IF NOT EXISTS idx_dart_fetch_logs_query_key_started
    ON public.dart_fetch_logs (query_key, started_at DESC);

ALTER TABLE public.dart_fetch_logs ENABLE ROW LEVEL SECURITY;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE schemaname = 'public'
          AND tablename = 'dart_corp_codes'
          AND policyname = 'public_can_read_dart_corp_codes'
    ) THEN
        CREATE POLICY public_can_read_dart_corp_codes ON public.dart_corp_codes
            FOR SELECT
            USING (true);
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE schemaname = 'public'
          AND tablename = 'dart_corp_codes'
          AND policyname = 'service_role_can_manage_dart_corp_codes'
    ) THEN
        CREATE POLICY service_role_can_manage_dart_corp_codes ON public.dart_corp_codes
            FOR ALL
            USING (auth.role() = 'service_role')
            WITH CHECK (auth.role() = 'service_role');
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE schemaname = 'public'
          AND tablename = 'dart_disclosures'
          AND policyname = 'public_can_read_active_dart_disclosures'
    ) THEN
        CREATE POLICY public_can_read_active_dart_disclosures ON public.dart_disclosures
            FOR SELECT
            USING (is_active = true);
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE schemaname = 'public'
          AND tablename = 'dart_disclosures'
          AND policyname = 'service_role_can_manage_dart_disclosures'
    ) THEN
        CREATE POLICY service_role_can_manage_dart_disclosures ON public.dart_disclosures
            FOR ALL
            USING (auth.role() = 'service_role')
            WITH CHECK (auth.role() = 'service_role');
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE schemaname = 'public'
          AND tablename = 'dart_fetch_logs'
          AND policyname = 'service_role_can_manage_dart_fetch_logs'
    ) THEN
        CREATE POLICY service_role_can_manage_dart_fetch_logs ON public.dart_fetch_logs
            FOR ALL
            USING (auth.role() = 'service_role')
            WITH CHECK (auth.role() = 'service_role');
    END IF;
END $$;
