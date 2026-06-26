CREATE TABLE IF NOT EXISTS public.portfolio_snapshots (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id uuid NOT NULL REFERENCES public.profiles(id) ON DELETE CASCADE,
  snapshot_at timestamptz NOT NULL,
  snapshot_date date NOT NULL,
  total_evaluation numeric NOT NULL DEFAULT 0,
  available_cash numeric NOT NULL DEFAULT 0,
  portfolio_profit_rate numeric NOT NULL DEFAULT 0,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (user_id, snapshot_at)
);

ALTER TABLE public.portfolio_snapshots ENABLE ROW LEVEL SECURITY;

CREATE POLICY "사용자는 자신의 자산 스냅샷만 조회 가능" ON public.portfolio_snapshots
  FOR SELECT USING (auth.uid() = user_id);

CREATE POLICY "사용자는 자신의 자산 스냅샷만 저장 가능" ON public.portfolio_snapshots
  FOR INSERT WITH CHECK (auth.uid() = user_id);

CREATE POLICY "사용자는 자신의 자산 스냅샷만 수정 가능" ON public.portfolio_snapshots
  FOR UPDATE USING (auth.uid() = user_id)
  WITH CHECK (auth.uid() = user_id);
