ALTER TABLE public.auto_trading_rules 
ADD COLUMN IF NOT EXISTS entry_order_proposal_id UUID REFERENCES public.trade_proposals(id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS idx_auto_trading_rules_entry_proposal
ON public.auto_trading_rules (entry_order_proposal_id)
WHERE entry_order_proposal_id IS NOT NULL;
