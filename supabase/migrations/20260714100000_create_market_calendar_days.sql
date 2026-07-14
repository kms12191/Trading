CREATE TABLE IF NOT EXISTS public.market_calendar_days (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    market_country TEXT NOT NULL CHECK (market_country IN ('KR', 'US')),
    trade_date DATE NOT NULL,
    is_open BOOLEAN NOT NULL DEFAULT false,
    holiday_name TEXT,
    regular_open_at TIMESTAMPTZ,
    regular_close_at TIMESTAMPTZ,
    source TEXT NOT NULL DEFAULT 'TOSS',
    raw_payload JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc'::text, now()),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc'::text, now()),
    UNIQUE (market_country, trade_date)
);

CREATE INDEX IF NOT EXISTS idx_market_calendar_days_country_date
    ON public.market_calendar_days (market_country, trade_date);

ALTER TABLE public.market_calendar_days ENABLE ROW LEVEL SECURITY;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_policies
        WHERE schemaname = 'public'
          AND tablename = 'market_calendar_days'
          AND policyname = 'authenticated_can_read_market_calendar_days'
    ) THEN
        CREATE POLICY authenticated_can_read_market_calendar_days
            ON public.market_calendar_days
            FOR SELECT
            TO authenticated
            USING (true);
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM pg_policies
        WHERE schemaname = 'public'
          AND tablename = 'market_calendar_days'
          AND policyname = 'service_role_can_manage_market_calendar_days'
    ) THEN
        CREATE POLICY service_role_can_manage_market_calendar_days
            ON public.market_calendar_days
            FOR ALL
            TO service_role
            USING (true)
            WITH CHECK (true);
    END IF;
END $$;
