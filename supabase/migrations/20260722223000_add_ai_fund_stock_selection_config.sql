ALTER TABLE public.admin_ai_fund_configs
    ADD COLUMN IF NOT EXISTS asset_scope VARCHAR(8) NOT NULL DEFAULT 'ALL',
    ADD COLUMN IF NOT EXISTS max_open_positions INTEGER NOT NULL DEFAULT 3,
    ADD COLUMN IF NOT EXISTS kr_allocation_pct NUMERIC(5, 2) NOT NULL DEFAULT 50.00,
    ADD COLUMN IF NOT EXISTS us_allocation_pct NUMERIC(5, 2) NOT NULL DEFAULT 50.00,
    ADD COLUMN IF NOT EXISTS selection_refresh_minutes INTEGER NOT NULL DEFAULT 60;

ALTER TABLE public.admin_ai_fund_configs
    DROP CONSTRAINT IF EXISTS chk_admin_ai_fund_asset_scope;

ALTER TABLE public.admin_ai_fund_configs
    ADD CONSTRAINT chk_admin_ai_fund_asset_scope
    CHECK (asset_scope IN ('KR', 'US', 'ALL'));

ALTER TABLE public.admin_ai_fund_configs
    DROP CONSTRAINT IF EXISTS chk_admin_ai_fund_max_open_positions;

ALTER TABLE public.admin_ai_fund_configs
    ADD CONSTRAINT chk_admin_ai_fund_max_open_positions
    CHECK (max_open_positions BETWEEN 1 AND 20);
