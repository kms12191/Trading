ALTER TABLE public.admin_ai_fund_configs
  ADD COLUMN IF NOT EXISTS stop_loss_pct NUMERIC(5, 2) NOT NULL DEFAULT -2.0;

COMMENT ON COLUMN public.admin_ai_fund_configs.stop_loss_pct
  IS '포지션별 손절 기준 (%). 예: -2.0 = -2% 도달 시 청산';
