ALTER TABLE public.admin_ai_fund_configs
    ADD COLUMN IF NOT EXISTS consecutive_failure_count INTEGER NOT NULL DEFAULT 0
        CHECK (consecutive_failure_count >= 0),
    ADD COLUMN IF NOT EXISTS last_failure_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS last_heartbeat_at TIMESTAMPTZ;

CREATE TABLE IF NOT EXISTS public.ai_fund_operation_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    config_id UUID NOT NULL REFERENCES public.admin_ai_fund_configs(id) ON DELETE CASCADE,
    event_type VARCHAR(32) NOT NULL CHECK (event_type IN ('HEARTBEAT', 'FAILURE', 'HALTED', 'RESUMED')),
    message TEXT,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_ai_fund_operation_events_config_created
    ON public.ai_fund_operation_events (config_id, created_at DESC);

ALTER TABLE public.ai_fund_operation_events ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Admin access to ai_fund_operation_events" ON public.ai_fund_operation_events
    FOR ALL TO authenticated
    USING (EXISTS (
        SELECT 1 FROM public.profiles
        WHERE profiles.id = (SELECT auth.uid()) AND profiles.role = 'ADMIN'
    ))
    WITH CHECK (EXISTS (
        SELECT 1 FROM public.profiles
        WHERE profiles.id = (SELECT auth.uid()) AND profiles.role = 'ADMIN'
    ));
