ALTER TABLE public.news_articles
    ADD COLUMN IF NOT EXISTS ai_summary TEXT,
    ADD COLUMN IF NOT EXISTS ai_summary_model TEXT,
    ADD COLUMN IF NOT EXISTS ai_summary_generated_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS ai_summary_prompt_version TEXT DEFAULT 'v1';

CREATE INDEX IF NOT EXISTS idx_news_articles_ai_summary_generated_at
    ON public.news_articles (ai_summary_generated_at DESC);
