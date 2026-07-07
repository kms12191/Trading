ALTER TABLE public.asset_transfer_proposals
  ADD COLUMN IF NOT EXISTS withdraw_fee NUMERIC,
  ADD COLUMN IF NOT EXISTS expected_receive_amount NUMERIC,
  ADD COLUMN IF NOT EXISTS received_amount NUMERIC,
  ADD COLUMN IF NOT EXISTS fee_currency TEXT;

