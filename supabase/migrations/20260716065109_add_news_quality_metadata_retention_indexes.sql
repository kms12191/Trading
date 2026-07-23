ALTER TABLE public.news_articles
    ADD COLUMN IF NOT EXISTS relevance_score INTEGER,
    ADD COLUMN IF NOT EXISTS quality_status TEXT,
    ADD COLUMN IF NOT EXISTS excluded_reason TEXT,
    ADD COLUMN IF NOT EXISTS quality_checked_at TIMESTAMPTZ;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'news_articles_quality_status_check'
          AND conrelid = 'public.news_articles'::regclass
    ) THEN
        ALTER TABLE public.news_articles
            ADD CONSTRAINT news_articles_quality_status_check
            CHECK (
                quality_status IS NULL
                OR quality_status IN ('PASS', 'HIGH_QUALITY', 'LOW_CONFIDENCE', 'REJECTED')
            );
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_news_articles_quality_status_published_at
    ON public.news_articles (quality_status, published_at);

CREATE INDEX IF NOT EXISTS idx_news_articles_symbol_quality_status_published_at
    ON public.news_articles (symbol, quality_status, published_at DESC);

CREATE INDEX IF NOT EXISTS idx_news_fetch_logs_started_at
    ON public.news_fetch_logs (started_at);
