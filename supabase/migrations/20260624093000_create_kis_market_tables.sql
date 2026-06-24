CREATE TABLE IF NOT EXISTS public.kis_stock_master (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    symbol TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    market_segment TEXT NOT NULL CHECK (market_segment IN ('KOSPI', 'KOSDAQ', 'KONEX', 'ETF', 'ETN', 'OTHER')),
    market_country TEXT NOT NULL DEFAULT 'KR' CHECK (market_country IN ('KR')),
    asset_type TEXT NOT NULL DEFAULT 'STOCK' CHECK (asset_type IN ('STOCK')),
    source TEXT NOT NULL DEFAULT 'KIS',
    source_file_row JSONB,
    listed_at DATE,
    is_active BOOLEAN NOT NULL DEFAULT true,
    created_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc'::text, now()),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc'::text, now())
);

CREATE INDEX IF NOT EXISTS idx_kis_stock_master_segment_active
    ON public.kis_stock_master (market_segment, is_active, symbol);

ALTER TABLE public.kis_stock_master ENABLE ROW LEVEL SECURITY;

CREATE TABLE IF NOT EXISTS public.kis_stock_turnover_latest (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    symbol TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    market_segment TEXT NOT NULL CHECK (market_segment IN ('KOSPI', 'KOSDAQ', 'KONEX', 'ETF', 'ETN', 'OTHER')),
    market_country TEXT NOT NULL DEFAULT 'KR' CHECK (market_country IN ('KR')),
    current_price NUMERIC NOT NULL DEFAULT 0,
    change_rate NUMERIC NOT NULL DEFAULT 0,
    trading_volume NUMERIC NOT NULL DEFAULT 0,
    trading_value NUMERIC NOT NULL DEFAULT 0,
    as_of TIMESTAMPTZ NOT NULL DEFAULT timezone('utc'::text, now()),
    raw_payload JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc'::text, now()),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc'::text, now())
);

CREATE INDEX IF NOT EXISTS idx_kis_stock_turnover_latest_rank
    ON public.kis_stock_turnover_latest (market_segment, trading_value DESC, symbol);

ALTER TABLE public.kis_stock_turnover_latest ENABLE ROW LEVEL SECURITY;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE schemaname = 'public'
          AND tablename = 'kis_stock_master'
          AND policyname = 'service_role_can_manage_kis_stock_master'
    ) THEN
        CREATE POLICY service_role_can_manage_kis_stock_master ON public.kis_stock_master
            FOR ALL
            USING (auth.role() = 'service_role')
            WITH CHECK (auth.role() = 'service_role');
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE schemaname = 'public'
          AND tablename = 'kis_stock_turnover_latest'
          AND policyname = 'public_can_read_kis_stock_turnover_latest'
    ) THEN
        CREATE POLICY public_can_read_kis_stock_turnover_latest ON public.kis_stock_turnover_latest
            FOR SELECT
            USING (true);
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE schemaname = 'public'
          AND tablename = 'kis_stock_turnover_latest'
          AND policyname = 'service_role_can_manage_kis_stock_turnover_latest'
    ) THEN
        CREATE POLICY service_role_can_manage_kis_stock_turnover_latest ON public.kis_stock_turnover_latest
            FOR ALL
            USING (auth.role() = 'service_role')
            WITH CHECK (auth.role() = 'service_role');
    END IF;
END $$;
