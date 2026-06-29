CREATE TABLE IF NOT EXISTS public.user_watchlist (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    symbol TEXT NOT NULL,
    name TEXT,
    exchange TEXT,
    asset_type TEXT CHECK (asset_type IN ('STOCK', 'CRYPTO')),
    market_country TEXT,
    currency TEXT,
    latest_price NUMERIC,
    change_rate NUMERIC,
    average_price NUMERIC,
    quantity NUMERIC,
    source_payload JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (user_id, symbol, asset_type, exchange)
);

CREATE INDEX IF NOT EXISTS idx_user_watchlist_user_updated
    ON public.user_watchlist (user_id, updated_at DESC);

ALTER TABLE public.user_watchlist ENABLE ROW LEVEL SECURITY;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE schemaname = 'public'
          AND tablename = 'user_watchlist'
          AND policyname = 'users_can_read_own_watchlist'
    ) THEN
        CREATE POLICY users_can_read_own_watchlist ON public.user_watchlist
            FOR SELECT
            USING (auth.uid() = user_id);
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE schemaname = 'public'
          AND tablename = 'user_watchlist'
          AND policyname = 'users_can_insert_own_watchlist'
    ) THEN
        CREATE POLICY users_can_insert_own_watchlist ON public.user_watchlist
            FOR INSERT
            WITH CHECK (auth.uid() = user_id);
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE schemaname = 'public'
          AND tablename = 'user_watchlist'
          AND policyname = 'users_can_update_own_watchlist'
    ) THEN
        CREATE POLICY users_can_update_own_watchlist ON public.user_watchlist
            FOR UPDATE
            USING (auth.uid() = user_id)
            WITH CHECK (auth.uid() = user_id);
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE schemaname = 'public'
          AND tablename = 'user_watchlist'
          AND policyname = 'users_can_delete_own_watchlist'
    ) THEN
        CREATE POLICY users_can_delete_own_watchlist ON public.user_watchlist
            FOR DELETE
            USING (auth.uid() = user_id);
    END IF;
END $$;
