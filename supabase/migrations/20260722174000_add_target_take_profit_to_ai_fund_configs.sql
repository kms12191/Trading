-- Migration: add target_take_profit_pct to admin_ai_fund_configs
-- Applied: 2026-07-22

ALTER TABLE public.admin_ai_fund_configs
  ADD COLUMN IF NOT EXISTS target_take_profit_pct NUMERIC DEFAULT 5.0;

COMMENT ON COLUMN public.admin_ai_fund_configs.target_take_profit_pct
  IS '목표 익절 비율 (%). 예: 5.0 = +5% 달성 시 자동 매도';
