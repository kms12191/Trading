CREATE OR REPLACE FUNCTION public.admin_list_user_token_usage(
    p_query TEXT DEFAULT '',
    p_sort TEXT DEFAULT 'tokens_30d',
    p_order TEXT DEFAULT 'desc',
    p_limit INTEGER DEFAULT 50,
    p_offset INTEGER DEFAULT 0
)
RETURNS JSONB
LANGUAGE plpgsql
STABLE
SECURITY DEFINER
SET search_path = ''
AS $$
DECLARE
    v_now TIMESTAMPTZ := CURRENT_TIMESTAMP;
    v_query TEXT := trim(COALESCE(p_query, ''));
    v_sort TEXT := CASE
        WHEN p_sort IN ('today_tokens', 'tokens_7d', 'tokens_30d', 'total_tokens', 'recent_used_at', 'created_at')
            THEN p_sort
        ELSE 'tokens_30d'
    END;
    v_order TEXT := CASE WHEN lower(p_order) = 'asc' THEN 'asc' ELSE 'desc' END;
    v_limit INTEGER := LEAST(GREATEST(COALESCE(p_limit, 50), 1), 200);
    v_offset INTEGER := LEAST(GREATEST(COALESCE(p_offset, 0), 0), 1000000);
    v_result JSONB;
BEGIN
    WITH auth_profile_rows AS MATERIALIZED (
        SELECT
            u.id,
            COALESCE(NULLIF(p.email, ''), u.email, '') AS email,
            COALESCE(NULLIF(p.nickname, ''), u.raw_user_meta_data->>'nickname', '') AS nickname,
            COALESCE(p.role, 'USER') AS role,
            COALESCE(p.updated_at, u.updated_at, u.created_at) AS updated_at
        FROM auth.users AS u
        LEFT JOIN public.profiles AS p ON p.id = u.id
        WHERE v_query = ''
           OR COALESCE(NULLIF(p.email, ''), u.email, '') ILIKE '%' || v_query || '%'
           OR COALESCE(NULLIF(p.nickname, ''), u.raw_user_meta_data->>'nickname', '') ILIKE '%' || v_query || '%'
    ),
    usage_rows AS MATERIALIZED (
        SELECT
            p.id,
            p.email,
            p.nickname,
            p.role,
            p.updated_at,
            COALESCE(SUM(l.total_tokens) FILTER (
                WHERE l.created_at >= date_trunc('day', v_now AT TIME ZONE 'UTC') AT TIME ZONE 'UTC'
            ), 0) AS today_tokens,
            COALESCE(SUM(l.total_tokens) FILTER (
                WHERE l.created_at >= v_now - INTERVAL '7 days'
            ), 0) AS tokens_7d,
            COALESCE(SUM(l.total_tokens) FILTER (
                WHERE l.created_at >= v_now - INTERVAL '30 days'
            ), 0) AS tokens_30d,
            COALESCE(SUM(l.total_tokens), 0) AS total_tokens,
            COUNT(l.id) FILTER (
                WHERE l.created_at >= date_trunc('day', v_now AT TIME ZONE 'UTC') AT TIME ZONE 'UTC'
            ) AS today_requests,
            COUNT(l.id) FILTER (
                WHERE l.created_at >= v_now - INTERVAL '30 days'
            ) AS requests_30d,
            MAX(l.created_at) AS recent_used_at
        FROM auth_profile_rows AS p
        LEFT JOIN public.chatbot_token_usage_logs AS l ON l.user_id = p.id
        GROUP BY p.id, p.email, p.nickname, p.role, p.updated_at
    ),
    ranked_rows AS MATERIALIZED (
        SELECT
            usage_rows.*,
            row_number() OVER (
                ORDER BY
                    CASE WHEN v_sort = 'today_tokens' AND v_order = 'asc' THEN today_tokens END ASC,
                    CASE WHEN v_sort = 'today_tokens' AND v_order = 'desc' THEN today_tokens END DESC,
                    CASE WHEN v_sort = 'tokens_7d' AND v_order = 'asc' THEN tokens_7d END ASC,
                    CASE WHEN v_sort = 'tokens_7d' AND v_order = 'desc' THEN tokens_7d END DESC,
                    CASE WHEN v_sort = 'tokens_30d' AND v_order = 'asc' THEN tokens_30d END ASC,
                    CASE WHEN v_sort = 'tokens_30d' AND v_order = 'desc' THEN tokens_30d END DESC,
                    CASE WHEN v_sort = 'total_tokens' AND v_order = 'asc' THEN total_tokens END ASC,
                    CASE WHEN v_sort = 'total_tokens' AND v_order = 'desc' THEN total_tokens END DESC,
                    CASE WHEN v_sort = 'recent_used_at' AND v_order = 'asc' THEN recent_used_at END ASC NULLS LAST,
                    CASE WHEN v_sort = 'recent_used_at' AND v_order = 'desc' THEN recent_used_at END DESC NULLS LAST,
                    CASE WHEN v_sort = 'created_at' AND v_order = 'asc' THEN updated_at END ASC NULLS LAST,
                    CASE WHEN v_sort = 'created_at' AND v_order = 'desc' THEN updated_at END DESC NULLS LAST,
                    id ASC
            ) AS sort_position
        FROM usage_rows
    ),
    page_json AS (
        SELECT COALESCE(
            jsonb_agg(
                jsonb_build_object(
                    'id', id,
                    'email', email,
                    'nickname', nickname,
                    'role', role,
                    'updatedAt', updated_at,
                    'usage', jsonb_build_object(
                        'todayTokens', today_tokens,
                        'tokens7d', tokens_7d,
                        'tokens30d', tokens_30d,
                        'totalTokens', total_tokens,
                        'todayRequests', today_requests,
                        'requests30d', requests_30d,
                        'recentUsedAt', recent_used_at
                    )
                )
                ORDER BY sort_position
            ),
            '[]'::jsonb
        ) AS data
        FROM ranked_rows
        WHERE sort_position > v_offset
          AND sort_position <= v_offset + v_limit
    ),
    summary_json AS (
        SELECT jsonb_build_object(
            'totalUsers', COUNT(*),
            'todayTokens', COALESCE(SUM(today_tokens), 0),
            'tokens30d', COALESCE(SUM(tokens_30d), 0),
            'totalTokens', COALESCE(SUM(total_tokens), 0),
            'activeUsers24h', COUNT(*) FILTER (
                WHERE recent_used_at >= v_now - INTERVAL '24 hours'
            )
        ) AS summary
        FROM usage_rows
    )
    SELECT jsonb_build_object('data', page_json.data, 'summary', summary_json.summary)
    INTO v_result
    FROM page_json
    CROSS JOIN summary_json;

    RETURN v_result;
END;
$$;

REVOKE ALL ON FUNCTION public.admin_list_user_token_usage(TEXT, TEXT, TEXT, INTEGER, INTEGER)
    FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.admin_list_user_token_usage(TEXT, TEXT, TEXT, INTEGER, INTEGER)
    TO service_role;
