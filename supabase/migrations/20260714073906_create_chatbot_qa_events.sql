CREATE TABLE IF NOT EXISTS public.chatbot_qa_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES public.profiles(id) ON DELETE CASCADE,
    request_id TEXT,
    event_type TEXT NOT NULL,
    event_payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT timezone('utc'::text, now()),
    CONSTRAINT chatbot_qa_events_event_type_not_blank CHECK (length(trim(event_type)) > 0),
    CONSTRAINT chatbot_qa_events_payload_object CHECK (jsonb_typeof(event_payload) = 'object')
);

CREATE INDEX IF NOT EXISTS chatbot_qa_events_user_created_idx
    ON public.chatbot_qa_events (user_id, created_at DESC);

CREATE INDEX IF NOT EXISTS chatbot_qa_events_request_idx
    ON public.chatbot_qa_events (request_id)
    WHERE request_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS chatbot_qa_events_event_type_idx
    ON public.chatbot_qa_events (event_type, created_at DESC);

ALTER TABLE public.chatbot_qa_events ENABLE ROW LEVEL SECURITY;

REVOKE ALL ON TABLE public.chatbot_qa_events FROM anon;
REVOKE ALL ON TABLE public.chatbot_qa_events FROM authenticated;
GRANT SELECT, INSERT, DELETE ON TABLE public.chatbot_qa_events TO service_role;

CREATE OR REPLACE VIEW public.v_chatbot_qa_logs
WITH (security_invoker = true)
AS
WITH user_messages AS (
    SELECT
        ch.id,
        ch.user_id,
        ch.message,
        ch.created_at
    FROM public.chat_history AS ch
    WHERE ch.role = 'user'
)
SELECT
    u.created_at AS qa_at,
    (u.created_at AT TIME ZONE 'Asia/Seoul')::date AS qa_date_kst,
    u.user_id,
    COALESCE(p.email, '') AS tester_email,
    COALESCE(p.nickname, '') AS tester_nickname,
    u.id AS user_message_id,
    u.message AS user_message,
    a.id AS assistant_message_id,
    a.message AS assistant_message,
    CASE
        WHEN a.created_at IS NOT NULL
            THEN ROUND(EXTRACT(EPOCH FROM (a.created_at - u.created_at))::numeric, 3)
        ELSE NULL
    END AS response_seconds,
    e.request_id,
    e.event_type,
    e.event_payload ->> 'source' AS event_source,
    e.event_payload ->> 'tool_source' AS tool_source,
    e.event_payload -> 'trace_kinds' AS trace_kinds,
    e.event_payload ->> 'pending_action' AS event_pending_action,
    s.pending_action AS current_pending_action,
    NULLIF(e.event_payload ->> 'latency_ms', '')::integer AS latency_ms,
    e.event_payload ->> 'error_title' AS error_title,
    e.event_payload ->> 'error_code' AS error_code,
    COALESCE(e.event_payload ->> 'model', t.model) AS model,
    COALESCE(NULLIF(e.event_payload ->> 'prompt_tokens', '')::integer, t.prompt_tokens) AS prompt_tokens,
    COALESCE(NULLIF(e.event_payload ->> 'completion_tokens', '')::integer, t.completion_tokens) AS completion_tokens,
    COALESCE(NULLIF(e.event_payload ->> 'total_tokens', '')::integer, t.total_tokens) AS total_tokens,
    t.request_type AS token_request_type,
    tp.id AS proposal_id,
    tp.exchange,
    tp.asset_type,
    COALESCE(tp.symbol, tp.ticker) AS symbol_or_ticker,
    tp.side,
    tp.status AS proposal_status,
    tp.order_amount,
    tp.price,
    tp.volume,
    tp.broker_env,
    tp.failure_reason,
    jsonb_build_object(
        'hasError', e.event_type = 'CHATBOT_ERROR'
            OR COALESCE(e.event_payload ->> 'error_title', '') <> ''
            OR COALESCE(tp.status, '') IN ('FAILED', 'REJECTED', 'EXPIRED'),
        'hasProposal', tp.id IS NOT NULL,
        'hasPendingAction', COALESCE(e.event_payload ->> 'pending_action', s.pending_action, '') <> '',
        'slowResponse', COALESCE(NULLIF(e.event_payload ->> 'latency_ms', '')::integer, 0) >= 8000
            OR (
                a.created_at IS NOT NULL
                AND EXTRACT(EPOCH FROM (a.created_at - u.created_at)) >= 8
            ),
        'highTokenUsage', COALESCE(NULLIF(e.event_payload ->> 'total_tokens', '')::integer, t.total_tokens, 0) >= 4000,
        'shortAssistantReply', length(COALESCE(a.message, '')) > 0
            AND length(COALESCE(a.message, '')) < 20,
        'failurePhrase', COALESCE(a.message, '') LIKE '%오류%'
            OR COALESCE(a.message, '') LIKE '%실패%'
            OR COALESCE(a.message, '') LIKE '%확인할 수 없습니다%'
            OR COALESCE(a.message, '') LIKE '%죄송%'
    ) AS qa_flags
FROM user_messages AS u
LEFT JOIN public.profiles AS p
    ON p.id = u.user_id
LEFT JOIN LATERAL (
    SELECT ch.id, ch.message, ch.created_at
    FROM public.chat_history AS ch
    WHERE ch.user_id = u.user_id
      AND ch.role = 'assistant'
      AND (
          ch.created_at > u.created_at
          OR (ch.created_at = u.created_at AND ch.id > u.id)
      )
    ORDER BY ch.created_at ASC, ch.id ASC
    LIMIT 1
) AS a ON TRUE
LEFT JOIN LATERAL (
    SELECT ev.*
    FROM public.chatbot_qa_events AS ev
    WHERE ev.user_id = u.user_id
      AND ev.created_at >= u.created_at - INTERVAL '5 seconds'
      AND ev.created_at <= COALESCE(a.created_at, u.created_at + INTERVAL '10 minutes') + INTERVAL '5 seconds'
    ORDER BY ev.created_at ASC
    LIMIT 1
) AS e ON TRUE
LEFT JOIN LATERAL (
    SELECT log.*
    FROM public.chatbot_token_usage_logs AS log
    WHERE log.user_id = u.user_id
      AND log.created_at >= u.created_at - INTERVAL '5 seconds'
      AND log.created_at <= COALESCE(a.created_at, u.created_at + INTERVAL '10 minutes') + INTERVAL '5 seconds'
    ORDER BY log.created_at DESC
    LIMIT 1
) AS t ON TRUE
LEFT JOIN LATERAL (
    SELECT proposal.*
    FROM public.trade_proposals AS proposal
    WHERE proposal.user_id = u.user_id
      AND proposal.created_at >= u.created_at - INTERVAL '5 seconds'
      AND proposal.created_at <= COALESCE(a.created_at, u.created_at + INTERVAL '10 minutes') + INTERVAL '10 seconds'
    ORDER BY proposal.created_at ASC
    LIMIT 1
) AS tp ON TRUE
LEFT JOIN public.chatbot_conversation_states AS s
    ON s.user_id = u.user_id;

REVOKE ALL ON TABLE public.v_chatbot_qa_logs FROM anon;
REVOKE ALL ON TABLE public.v_chatbot_qa_logs FROM authenticated;
GRANT SELECT ON TABLE public.v_chatbot_qa_logs TO service_role;
