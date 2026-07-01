-- 코인원에서 바이낸스로 이동하는 가상자산 출금 제안 및 상태 추적 테이블
CREATE TABLE IF NOT EXISTS public.asset_transfer_proposals (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    user_id UUID REFERENCES public.profiles(id) ON DELETE CASCADE NOT NULL,
    from_exchange TEXT NOT NULL CHECK (from_exchange IN ('COINONE')),
    to_exchange TEXT NOT NULL CHECK (to_exchange IN ('BINANCE')),
    currency TEXT NOT NULL,
    network TEXT NOT NULL,
    amount NUMERIC NOT NULL CHECK (amount > 0),
    address TEXT NOT NULL,
    secondary_address TEXT,
    status TEXT NOT NULL DEFAULT 'PENDING' CHECK (
        status IN (
            'PENDING',
            'APPROVED',
            'SUBMITTED',
            'WITHDRAWAL_REGISTER',
            'WITHDRAWAL_WAIT',
            'COMPLETED',
            'FAILED',
            'CANCELED',
            'NEEDS_REVIEW'
        )
    ),
    external_transaction_id TEXT,
    raw_request JSONB NOT NULL DEFAULT '{}'::jsonb,
    precheck_payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    raw_response JSONB NOT NULL DEFAULT '{}'::jsonb,
    binance_deposit_payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    failure_reason TEXT,
    approved_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now()),
    submitted_at TIMESTAMP WITH TIME ZONE,
    completed_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now()) NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now()) NOT NULL
);

CREATE INDEX IF NOT EXISTS asset_transfer_proposals_user_created_idx
    ON public.asset_transfer_proposals (user_id, created_at DESC);

CREATE INDEX IF NOT EXISTS asset_transfer_proposals_user_status_idx
    ON public.asset_transfer_proposals (user_id, status);

ALTER TABLE public.asset_transfer_proposals ENABLE ROW LEVEL SECURITY;

GRANT USAGE ON SCHEMA public TO authenticated;
GRANT USAGE ON SCHEMA public TO service_role;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.asset_transfer_proposals TO authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.asset_transfer_proposals TO service_role;

DROP POLICY IF EXISTS "사용자는 자신의 자산 출금 제안만 조회 및 관리 가능" ON public.asset_transfer_proposals;
CREATE POLICY "사용자는 자신의 자산 출금 제안만 조회 및 관리 가능" ON public.asset_transfer_proposals
    FOR ALL
    TO authenticated
    USING ((SELECT auth.uid()) = user_id)
    WITH CHECK ((SELECT auth.uid()) = user_id);

ALTER publication supabase_realtime ADD TABLE public.asset_transfer_proposals;
