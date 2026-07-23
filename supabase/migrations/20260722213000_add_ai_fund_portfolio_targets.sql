ALTER TABLE public.admin_ai_fund_configs
    ADD COLUMN IF NOT EXISTS target_allocations JSONB NOT NULL DEFAULT '{}'::jsonb,
    ADD COLUMN IF NOT EXISTS rebalance_threshold_pct NUMERIC(6, 3) NOT NULL DEFAULT 5.0
        CHECK (rebalance_threshold_pct >= 0 AND rebalance_threshold_pct <= 100);
