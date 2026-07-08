-- 저장된 투자노트를 RAG 검색 단위로 분할해 보관합니다.
-- embedding은 다음 단계에서 pgvector 임베딩 생성 후 채웁니다.

CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS public.knowledge_chunks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES auth.users(id) ON DELETE CASCADE,
    source_type TEXT NOT NULL,
    source_id TEXT NOT NULL,
    symbol TEXT,
    market TEXT,
    chunk_index INTEGER NOT NULL DEFAULT 0,
    chunk_text TEXT NOT NULL,
    embedding VECTOR(1536),
    embedding_status TEXT NOT NULL DEFAULT 'PENDING',
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    importance_score NUMERIC NOT NULL DEFAULT 0.5,
    freshness_score NUMERIC NOT NULL DEFAULT 0.5,
    content_hash TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT knowledge_chunks_source_type_check CHECK (source_type IN ('OBSIDIAN', 'APP_NOTE', 'AUTO_MEMORY', 'NEWS', 'DISCLOSURE')),
    CONSTRAINT knowledge_chunks_embedding_status_check CHECK (embedding_status IN ('PENDING', 'EMBEDDED', 'FAILED')),
    CONSTRAINT knowledge_chunks_scores_check CHECK (
        importance_score >= 0 AND importance_score <= 1 AND freshness_score >= 0 AND freshness_score <= 1
    ),
    CONSTRAINT knowledge_chunks_unique_source_chunk UNIQUE (source_type, source_id, chunk_index, content_hash)
);

CREATE INDEX IF NOT EXISTS idx_knowledge_chunks_user_source
    ON public.knowledge_chunks(user_id, source_type);

CREATE INDEX IF NOT EXISTS idx_knowledge_chunks_symbol_market
    ON public.knowledge_chunks(symbol, market);

CREATE INDEX IF NOT EXISTS idx_knowledge_chunks_embedding_status
    ON public.knowledge_chunks(user_id, embedding_status);

ALTER TABLE public.knowledge_chunks ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "knowledge_chunks_owner_select" ON public.knowledge_chunks;
CREATE POLICY "knowledge_chunks_owner_select"
    ON public.knowledge_chunks
    FOR SELECT
    TO authenticated
    USING (user_id IS NULL OR (select auth.uid()) = user_id);

DROP POLICY IF EXISTS "knowledge_chunks_owner_insert" ON public.knowledge_chunks;
CREATE POLICY "knowledge_chunks_owner_insert"
    ON public.knowledge_chunks
    FOR INSERT
    TO authenticated
    WITH CHECK (user_id IS NULL OR (select auth.uid()) = user_id);

DROP POLICY IF EXISTS "knowledge_chunks_owner_update" ON public.knowledge_chunks;
CREATE POLICY "knowledge_chunks_owner_update"
    ON public.knowledge_chunks
    FOR UPDATE
    TO authenticated
    USING (user_id IS NULL OR (select auth.uid()) = user_id)
    WITH CHECK (user_id IS NULL OR (select auth.uid()) = user_id);

DROP POLICY IF EXISTS "knowledge_chunks_owner_delete" ON public.knowledge_chunks;
CREATE POLICY "knowledge_chunks_owner_delete"
    ON public.knowledge_chunks
    FOR DELETE
    TO authenticated
    USING (user_id IS NULL OR (select auth.uid()) = user_id);
