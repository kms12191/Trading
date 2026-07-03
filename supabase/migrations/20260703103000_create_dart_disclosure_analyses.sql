CREATE TABLE IF NOT EXISTS public.dart_disclosure_analyses (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    rcept_no TEXT NOT NULL UNIQUE,
    category TEXT NOT NULL,
    sentiment TEXT NOT NULL CHECK (sentiment IN ('positive', 'negative', 'caution', 'info')),
    sentiment_label TEXT NOT NULL,
    sentiment_message TEXT NOT NULL,
    confidence TEXT NOT NULL CHECK (confidence IN ('high', 'medium', 'low')),
    headline TEXT NOT NULL,
    key_points JSONB NOT NULL DEFAULT '[]'::jsonb,
    risk_points JSONB NOT NULL DEFAULT '[]'::jsonb,
    metrics JSONB NOT NULL DEFAULT '[]'::jsonb,
    analysis_source TEXT NOT NULL DEFAULT 'OPENDART_DOCUMENT',
    raw_payload JSONB,
    analyzed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_dart_disclosure_analyses_rcept_no
    ON public.dart_disclosure_analyses (rcept_no);

CREATE INDEX IF NOT EXISTS idx_dart_disclosure_analyses_sentiment
    ON public.dart_disclosure_analyses (sentiment);

ALTER TABLE public.dart_disclosure_analyses ENABLE ROW LEVEL SECURITY;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE schemaname = 'public'
          AND tablename = 'dart_disclosure_analyses'
          AND policyname = 'public_can_read_dart_disclosure_analyses'
    ) THEN
        CREATE POLICY public_can_read_dart_disclosure_analyses ON public.dart_disclosure_analyses
            FOR SELECT
            USING (true);
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE schemaname = 'public'
          AND tablename = 'dart_disclosure_analyses'
          AND policyname = 'service_role_can_manage_dart_disclosure_analyses'
    ) THEN
        CREATE POLICY service_role_can_manage_dart_disclosure_analyses ON public.dart_disclosure_analyses
            FOR ALL
            USING (auth.role() = 'service_role')
            WITH CHECK (auth.role() = 'service_role');
    END IF;
END $$;
