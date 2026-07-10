CREATE TABLE IF NOT EXISTS public.chatbot_usage_counters (
    user_id UUID NOT NULL REFERENCES public.profiles(id) ON DELETE CASCADE,
    usage_date DATE NOT NULL,
    request_count INTEGER NOT NULL DEFAULT 0 CHECK (request_count >= 0),
    token_count BIGINT NOT NULL DEFAULT 0 CHECK (token_count >= 0),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT timezone('utc'::text, now()),
    PRIMARY KEY (user_id, usage_date)
);

ALTER TABLE public.chatbot_usage_counters ENABLE ROW LEVEL SECURITY;

CREATE POLICY "사용자는 자신의 챗봇 사용량만 조회 가능"
    ON public.chatbot_usage_counters
    FOR SELECT
    TO authenticated
    USING ((select auth.uid()) = user_id);

CREATE POLICY "사용자는 자신의 챗봇 사용량만 생성 가능"
    ON public.chatbot_usage_counters
    FOR INSERT
    TO authenticated
    WITH CHECK ((select auth.uid()) = user_id);

CREATE POLICY "사용자는 자신의 챗봇 사용량만 갱신 가능"
    ON public.chatbot_usage_counters
    FOR UPDATE
    TO authenticated
    USING ((select auth.uid()) = user_id)
    WITH CHECK ((select auth.uid()) = user_id);

CREATE OR REPLACE FUNCTION public.consume_chatbot_usage(
    p_user_id UUID,
    p_usage_date DATE,
    p_request_increment INTEGER,
    p_token_increment BIGINT,
    p_request_limit INTEGER,
    p_token_limit BIGINT
)
RETURNS TABLE (
    allowed BOOLEAN,
    request_count INTEGER,
    token_count BIGINT
)
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path = public
AS $$
DECLARE
    current_request_count INTEGER;
    current_token_count BIGINT;
BEGIN
    IF p_request_increment < 0 OR p_token_increment < 0 THEN
        RAISE EXCEPTION '사용량 증가량은 음수일 수 없습니다.';
    END IF;

    PERFORM pg_advisory_xact_lock(
        hashtextextended(p_user_id::TEXT || ':' || p_usage_date::TEXT, 0)
    );

    SELECT u.request_count, u.token_count
      INTO current_request_count, current_token_count
      FROM public.chatbot_usage_counters AS u
     WHERE u.user_id = p_user_id
       AND u.usage_date = p_usage_date
     FOR UPDATE;

    current_request_count := COALESCE(current_request_count, 0);
    current_token_count := COALESCE(current_token_count, 0);

    IF current_request_count + p_request_increment > p_request_limit
       OR current_token_count + p_token_increment > p_token_limit THEN
        RETURN QUERY SELECT FALSE, current_request_count, current_token_count;
        RETURN;
    END IF;

    INSERT INTO public.chatbot_usage_counters (
        user_id, usage_date, request_count, token_count, updated_at
    ) VALUES (
        p_user_id, p_usage_date, current_request_count + p_request_increment,
        current_token_count + p_token_increment, timezone('utc'::text, now())
    )
    ON CONFLICT (user_id, usage_date) DO UPDATE SET
        request_count = EXCLUDED.request_count,
        token_count = EXCLUDED.token_count,
        updated_at = EXCLUDED.updated_at;

    RETURN QUERY
    SELECT TRUE,
           current_request_count + p_request_increment,
           current_token_count + p_token_increment;
END;
$$;

GRANT EXECUTE ON FUNCTION public.consume_chatbot_usage(UUID, DATE, INTEGER, BIGINT, INTEGER, BIGINT)
    TO authenticated;
