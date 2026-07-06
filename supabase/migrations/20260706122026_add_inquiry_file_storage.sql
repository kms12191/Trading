ALTER TABLE public.inquiries
    ADD COLUMN IF NOT EXISTS mime_type TEXT,
    ADD COLUMN IF NOT EXISTS file_size BIGINT;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'inquiries_file_size_check'
          AND conrelid = 'public.inquiries'::regclass
    ) THEN
        ALTER TABLE public.inquiries
            ADD CONSTRAINT inquiries_file_size_check
            CHECK (file_size IS NULL OR (file_size >= 0 AND file_size <= 5242880));
    END IF;
END $$;

REVOKE ALL ON public.inquiries FROM anon;
GRANT SELECT ON public.inquiries TO authenticated;
GRANT INSERT (user_id, inquiry_type, title, content, file_name, attachment_path, mime_type, file_size)
    ON public.inquiries TO authenticated;
GRANT UPDATE (inquiry_type, title, content, file_name, attachment_path, mime_type, file_size)
    ON public.inquiries TO authenticated;
GRANT DELETE ON public.inquiries TO authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.inquiries TO service_role;

INSERT INTO storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
VALUES (
    'inquiry-files',
    'inquiry-files',
    false,
    5242880,
    ARRAY[
        'image/jpeg',
        'image/png',
        'application/pdf',
        'text/plain',
        'application/msword',
        'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
        'application/vnd.ms-excel',
        'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    ]
)
ON CONFLICT (id) DO UPDATE SET
    public = EXCLUDED.public,
    file_size_limit = EXCLUDED.file_size_limit,
    allowed_mime_types = EXCLUDED.allowed_mime_types;

GRANT SELECT, INSERT, UPDATE, DELETE ON storage.objects TO authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON storage.objects TO service_role;

DROP POLICY IF EXISTS users_can_read_own_inquiry_files ON storage.objects;
CREATE POLICY users_can_read_own_inquiry_files ON storage.objects
    FOR SELECT
    TO authenticated
    USING (
        bucket_id = 'inquiry-files'
        AND (storage.foldername(name))[1] = (SELECT auth.uid())::TEXT
        AND EXISTS (
            SELECT 1
            FROM public.inquiries inquiry
            WHERE inquiry.id::TEXT = (storage.foldername(name))[2]
              AND inquiry.user_id = (SELECT auth.uid())
        )
    );

DROP POLICY IF EXISTS users_can_upload_own_received_inquiry_files ON storage.objects;
CREATE POLICY users_can_upload_own_received_inquiry_files ON storage.objects
    FOR INSERT
    TO authenticated
    WITH CHECK (
        bucket_id = 'inquiry-files'
        AND (storage.foldername(name))[1] = (SELECT auth.uid())::TEXT
        AND EXISTS (
            SELECT 1
            FROM public.inquiries inquiry
            WHERE inquiry.id::TEXT = (storage.foldername(name))[2]
              AND inquiry.user_id = (SELECT auth.uid())
              AND inquiry.status = 'RECEIVED'
        )
    );

DROP POLICY IF EXISTS users_can_update_own_received_inquiry_files ON storage.objects;
CREATE POLICY users_can_update_own_received_inquiry_files ON storage.objects
    FOR UPDATE
    TO authenticated
    USING (
        bucket_id = 'inquiry-files'
        AND (storage.foldername(name))[1] = (SELECT auth.uid())::TEXT
        AND EXISTS (
            SELECT 1
            FROM public.inquiries inquiry
            WHERE inquiry.id::TEXT = (storage.foldername(name))[2]
              AND inquiry.user_id = (SELECT auth.uid())
              AND inquiry.status = 'RECEIVED'
        )
    )
    WITH CHECK (
        bucket_id = 'inquiry-files'
        AND (storage.foldername(name))[1] = (SELECT auth.uid())::TEXT
        AND EXISTS (
            SELECT 1
            FROM public.inquiries inquiry
            WHERE inquiry.id::TEXT = (storage.foldername(name))[2]
              AND inquiry.user_id = (SELECT auth.uid())
              AND inquiry.status = 'RECEIVED'
        )
    );

DROP POLICY IF EXISTS users_can_delete_own_received_inquiry_files ON storage.objects;
CREATE POLICY users_can_delete_own_received_inquiry_files ON storage.objects
    FOR DELETE
    TO authenticated
    USING (
        bucket_id = 'inquiry-files'
        AND (storage.foldername(name))[1] = (SELECT auth.uid())::TEXT
        AND EXISTS (
            SELECT 1
            FROM public.inquiries inquiry
            WHERE inquiry.id::TEXT = (storage.foldername(name))[2]
              AND inquiry.user_id = (SELECT auth.uid())
              AND inquiry.status = 'RECEIVED'
        )
    );

DROP POLICY IF EXISTS service_role_can_manage_inquiry_files ON storage.objects;
CREATE POLICY service_role_can_manage_inquiry_files ON storage.objects
    FOR ALL
    TO service_role
    USING (bucket_id = 'inquiry-files')
    WITH CHECK (bucket_id = 'inquiry-files');
