CREATE TABLE IF NOT EXISTS public.market_indices_latest (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    symbol TEXT NOT NULL UNIQUE,
    label TEXT NOT NULL,
    source TEXT NOT NULL,
    market_country TEXT NOT NULL DEFAULT 'GLOBAL',
    ticker TEXT NOT NULL,
    current_value NUMERIC NOT NULL DEFAULT 0,
    change_value NUMERIC NOT NULL DEFAULT 0,
    change_percent NUMERIC NOT NULL DEFAULT 0,
    currency TEXT NOT NULL DEFAULT 'USD',
    display_order INTEGER NOT NULL DEFAULT 0,
    as_of TIMESTAMPTZ NOT NULL DEFAULT timezone('utc'::text, now()),
    raw_payload JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc'::text, now()),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc'::text, now())
);

CREATE INDEX IF NOT EXISTS idx_market_indices_latest_display_order
    ON public.market_indices_latest (display_order, as_of DESC);

GRANT SELECT ON TABLE public.market_indices_latest TO anon;
GRANT SELECT ON TABLE public.market_indices_latest TO authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public.market_indices_latest TO service_role;

ALTER TABLE public.market_indices_latest ENABLE ROW LEVEL SECURITY;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_policies
        WHERE schemaname = 'public'
          AND tablename = 'market_indices_latest'
          AND policyname = 'public_can_read_market_indices_latest'
    ) THEN
        CREATE POLICY public_can_read_market_indices_latest
            ON public.market_indices_latest
            FOR SELECT
            TO anon, authenticated
            USING (true);
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM pg_policies
        WHERE schemaname = 'public'
          AND tablename = 'market_indices_latest'
          AND policyname = 'service_role_can_manage_market_indices_latest'
    ) THEN
        CREATE POLICY service_role_can_manage_market_indices_latest
            ON public.market_indices_latest
            FOR ALL
            TO service_role
            USING (true)
            WITH CHECK (true);
    END IF;
END $$;
