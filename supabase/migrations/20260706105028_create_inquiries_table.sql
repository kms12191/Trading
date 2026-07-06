CREATE TABLE IF NOT EXISTS public.inquiries (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    user_id UUID REFERENCES public.profiles(id) ON DELETE CASCADE NOT NULL,
    inquiry_type TEXT NOT NULL,
    title TEXT NOT NULL,
    content TEXT NOT NULL,
    file_name TEXT,
    attachment_path TEXT,
    status TEXT NOT NULL DEFAULT 'RECEIVED' CHECK (
        status IN (
            'RECEIVED',
            'WAITING',
            'COMPLETED',
            'NEED_MORE',
            'CANCELED'
        )
    ),
    answer TEXT,
    answered_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now()) NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now()) NOT NULL
);

CREATE INDEX IF NOT EXISTS inquiries_user_created_idx
    ON public.inquiries (user_id, created_at DESC);

CREATE INDEX IF NOT EXISTS inquiries_user_status_idx
    ON public.inquiries (user_id, status);

CREATE OR REPLACE FUNCTION public.set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = timezone('utc'::text, now());
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS set_inquiries_updated_at ON public.inquiries;
CREATE TRIGGER set_inquiries_updated_at
    BEFORE UPDATE ON public.inquiries
    FOR EACH ROW
    EXECUTE FUNCTION public.set_updated_at();

ALTER TABLE public.inquiries ENABLE ROW LEVEL SECURITY;

GRANT USAGE ON SCHEMA public TO authenticated;
GRANT USAGE ON SCHEMA public TO service_role;

REVOKE ALL ON public.inquiries FROM anon;
REVOKE ALL ON public.inquiries FROM authenticated;

GRANT SELECT ON public.inquiries TO authenticated;
GRANT INSERT (user_id, inquiry_type, title, content, file_name, attachment_path)
    ON public.inquiries TO authenticated;
GRANT UPDATE (inquiry_type, title, content, file_name, attachment_path)
    ON public.inquiries TO authenticated;
GRANT DELETE ON public.inquiries TO authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.inquiries TO service_role;

DROP POLICY IF EXISTS users_can_read_own_inquiries ON public.inquiries;
CREATE POLICY users_can_read_own_inquiries ON public.inquiries
    FOR SELECT
    TO authenticated
    USING ((SELECT auth.uid()) = user_id);

DROP POLICY IF EXISTS users_can_insert_own_inquiries ON public.inquiries;
CREATE POLICY users_can_insert_own_inquiries ON public.inquiries
    FOR INSERT
    TO authenticated
    WITH CHECK (
        (SELECT auth.uid()) = user_id
        AND status = 'RECEIVED'
        AND answer IS NULL
        AND answered_at IS NULL
    );

DROP POLICY IF EXISTS users_can_update_own_received_inquiries ON public.inquiries;
CREATE POLICY users_can_update_own_received_inquiries ON public.inquiries
    FOR UPDATE
    TO authenticated
    USING ((SELECT auth.uid()) = user_id AND status = 'RECEIVED')
    WITH CHECK ((SELECT auth.uid()) = user_id AND status = 'RECEIVED');

DROP POLICY IF EXISTS users_can_delete_own_received_inquiries ON public.inquiries;
CREATE POLICY users_can_delete_own_received_inquiries ON public.inquiries
    FOR DELETE
    TO authenticated
    USING ((SELECT auth.uid()) = user_id AND status = 'RECEIVED');

DROP POLICY IF EXISTS service_role_can_manage_inquiries ON public.inquiries;
CREATE POLICY service_role_can_manage_inquiries ON public.inquiries
    FOR ALL
    TO service_role
    USING (true)
    WITH CHECK (true);
