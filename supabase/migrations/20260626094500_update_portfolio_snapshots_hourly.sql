ALTER TABLE public.portfolio_snapshots
  ADD COLUMN IF NOT EXISTS snapshot_at timestamptz;

UPDATE public.portfolio_snapshots
SET snapshot_at = COALESCE(snapshot_at, snapshot_date::timestamptz)
WHERE snapshot_at IS NULL;

ALTER TABLE public.portfolio_snapshots
  ALTER COLUMN snapshot_at SET NOT NULL;

ALTER TABLE public.portfolio_snapshots
  DROP CONSTRAINT IF EXISTS portfolio_snapshots_user_id_snapshot_date_key;

CREATE UNIQUE INDEX IF NOT EXISTS portfolio_snapshots_user_id_snapshot_at_key
  ON public.portfolio_snapshots (user_id, snapshot_at);

