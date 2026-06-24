CREATE TABLE IF NOT EXISTS public.news_articles (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    market TEXT NOT NULL CHECK (market IN ('DOMESTIC', 'GLOBAL')),
    source TEXT NOT NULL,
    source_article_id TEXT,
    title TEXT NOT NULL,
    summary TEXT,
    url TEXT NOT NULL,
    published_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    fetched_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    company_name TEXT,
    symbol TEXT,
    language TEXT,
    sentiment JSONB,
    content_hash TEXT NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT true,
    raw_payload JSONB,
    ai_summary TEXT,
    ai_summary_model TEXT,
    ai_summary_generated_at TIMESTAMPTZ,
    ai_summary_prompt_version TEXT DEFAULT 'v1'
);

ALTER TABLE public.news_articles
    ADD COLUMN IF NOT EXISTS raw_payload JSONB,
    ADD COLUMN IF NOT EXISTS sentiment JSONB,
    ADD COLUMN IF NOT EXISTS is_active BOOLEAN NOT NULL DEFAULT true,
    ADD COLUMN IF NOT EXISTS ai_summary TEXT,
    ADD COLUMN IF NOT EXISTS ai_summary_model TEXT,
    ADD COLUMN IF NOT EXISTS ai_summary_generated_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS ai_summary_prompt_version TEXT DEFAULT 'v1';

CREATE UNIQUE INDEX IF NOT EXISTS news_articles_url_key
    ON public.news_articles (url);

CREATE INDEX IF NOT EXISTS idx_news_articles_published_at
    ON public.news_articles (published_at DESC);

CREATE INDEX IF NOT EXISTS idx_news_articles_market
    ON public.news_articles (market);

CREATE INDEX IF NOT EXISTS idx_news_articles_symbol
    ON public.news_articles (symbol);

CREATE INDEX IF NOT EXISTS idx_news_articles_content_hash
    ON public.news_articles (content_hash);

CREATE INDEX IF NOT EXISTS idx_news_articles_ai_summary_generated_at
    ON public.news_articles (ai_summary_generated_at DESC);

ALTER TABLE public.news_articles ENABLE ROW LEVEL SECURITY;

CREATE TABLE IF NOT EXISTS public.news_fetch_logs (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    source TEXT NOT NULL,
    query_key TEXT NOT NULL,
    query_category TEXT,
    query_text TEXT,
    status TEXT NOT NULL CHECK (status IN ('SUCCESS', 'FAILED', 'SKIPPED')),
    fetched_count INTEGER NOT NULL DEFAULT 0,
    request_count INTEGER NOT NULL DEFAULT 0,
    skipped_reason TEXT,
    error_message TEXT,
    started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at TIMESTAMPTZ
);

ALTER TABLE public.news_fetch_logs
    ADD COLUMN IF NOT EXISTS query_category TEXT,
    ADD COLUMN IF NOT EXISTS query_text TEXT,
    ADD COLUMN IF NOT EXISTS request_count INTEGER NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS skipped_reason TEXT;

ALTER TABLE public.news_fetch_logs
    DROP CONSTRAINT IF EXISTS news_fetch_logs_status_check;

ALTER TABLE public.news_fetch_logs
    ADD CONSTRAINT news_fetch_logs_status_check
    CHECK (status IN ('SUCCESS', 'FAILED', 'SKIPPED'));

CREATE INDEX IF NOT EXISTS idx_news_fetch_logs_source_started
    ON public.news_fetch_logs (source, started_at DESC);

CREATE INDEX IF NOT EXISTS idx_news_fetch_logs_query_key_started
    ON public.news_fetch_logs (query_key, started_at DESC);

ALTER TABLE public.news_fetch_logs ENABLE ROW LEVEL SECURITY;

CREATE TABLE IF NOT EXISTS public.watchlist_symbols (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    symbol TEXT NOT NULL,
    name TEXT,
    exchange TEXT CHECK (exchange IN ('TOSS', 'COINONE', 'BINANCE', 'KIS')),
    asset_type TEXT CHECK (asset_type IN ('CRYPTO', 'STOCK')),
    market_country TEXT CHECK (market_country IN ('KR', 'US')),
    currency TEXT,
    is_active BOOLEAN NOT NULL DEFAULT true,
    source TEXT NOT NULL DEFAULT 'ADMIN',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_watchlist_symbols_active_stock
    ON public.watchlist_symbols (is_active, asset_type, created_at DESC);

ALTER TABLE public.watchlist_symbols ENABLE ROW LEVEL SECURITY;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE schemaname = 'public'
          AND tablename = 'news_articles'
          AND policyname = 'public_can_read_active_news'
    ) THEN
        CREATE POLICY public_can_read_active_news ON public.news_articles
            FOR SELECT
            USING (is_active = true);
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE schemaname = 'public'
          AND tablename = 'news_articles'
          AND policyname = 'service_role_can_manage_news'
    ) THEN
        CREATE POLICY service_role_can_manage_news ON public.news_articles
            FOR ALL
            USING (auth.role() = 'service_role')
            WITH CHECK (auth.role() = 'service_role');
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE schemaname = 'public'
          AND tablename = 'news_fetch_logs'
          AND policyname = 'service_role_can_manage_news_fetch_logs'
    ) THEN
        CREATE POLICY service_role_can_manage_news_fetch_logs ON public.news_fetch_logs
            FOR ALL
            USING (auth.role() = 'service_role')
            WITH CHECK (auth.role() = 'service_role');
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE schemaname = 'public'
          AND tablename = 'watchlist_symbols'
          AND policyname = 'public_can_read_active_watchlist_symbols'
    ) THEN
        CREATE POLICY public_can_read_active_watchlist_symbols ON public.watchlist_symbols
            FOR SELECT
            USING (is_active = true);
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE schemaname = 'public'
          AND tablename = 'watchlist_symbols'
          AND policyname = 'service_role_can_manage_watchlist_symbols'
    ) THEN
        CREATE POLICY service_role_can_manage_watchlist_symbols ON public.watchlist_symbols
            FOR ALL
            USING (auth.role() = 'service_role')
            WITH CHECK (auth.role() = 'service_role');
    END IF;
END $$;
