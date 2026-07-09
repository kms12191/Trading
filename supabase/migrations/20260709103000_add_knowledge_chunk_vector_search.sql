CREATE INDEX IF NOT EXISTS idx_knowledge_chunks_embedding_hnsw
    ON public.knowledge_chunks
    USING hnsw (embedding vector_cosine_ops)
    WHERE embedding_status = 'EMBEDDED';

CREATE OR REPLACE FUNCTION public.match_knowledge_chunks(
    query_embedding vector(1536),
    match_user_id uuid DEFAULT NULL,
    match_symbol text DEFAULT NULL,
    match_market text DEFAULT NULL,
    match_source_types text[] DEFAULT NULL,
    match_count int DEFAULT 12
)
RETURNS TABLE (
    source_type text,
    source_id text,
    chunk_text text,
    similarity double precision,
    rank_score double precision,
    metadata jsonb
)
LANGUAGE sql
STABLE
SECURITY INVOKER
AS $$
    SELECT
        chunk.source_type,
        chunk.source_id,
        chunk.chunk_text,
        1 - (chunk.embedding <=> query_embedding) AS similarity,
        (
            (1 - (chunk.embedding <=> query_embedding)) * 0.72
            + chunk.importance_score::double precision * 0.18
            + chunk.freshness_score::double precision * 0.10
        ) AS rank_score,
        chunk.metadata
    FROM public.knowledge_chunks AS chunk
    WHERE chunk.embedding_status = 'EMBEDDED'
      AND chunk.embedding IS NOT NULL
      AND (match_user_id IS NULL OR chunk.user_id IS NULL OR chunk.user_id = match_user_id)
      AND (match_symbol IS NULL OR chunk.symbol = match_symbol OR chunk.symbol IS NULL)
      AND (match_market IS NULL OR chunk.market = match_market OR chunk.market IS NULL)
      AND (match_source_types IS NULL OR chunk.source_type = ANY(match_source_types))
    ORDER BY rank_score DESC
    LIMIT LEAST(GREATEST(match_count, 1), 50);
$$;

GRANT EXECUTE ON FUNCTION public.match_knowledge_chunks(
    vector(1536),
    uuid,
    text,
    text,
    text[],
    int
) TO authenticated, service_role;
