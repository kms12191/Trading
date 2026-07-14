ALTER TABLE public.trade_proposals DROP CONSTRAINT IF EXISTS trade_proposals_status_check;

ALTER TABLE public.trade_proposals
    ADD CONSTRAINT trade_proposals_status_check
    CHECK (
        status IN (
            'PENDING',
            'APPROVED',
            'ORDERED',
            'OPEN',
            'PARTIALLY_FILLED',
            'MODIFIED',
            'REJECTED',
            'EXECUTED',
            'FAILED',
            'CANCELED',
            'EXPIRED'
        )
    );
