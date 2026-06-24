-- ML 자동화 작업 추적용 테이블 추가

CREATE TABLE IF NOT EXISTS public.ml_dataset_jobs (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    user_id UUID REFERENCES public.profiles(id) ON DELETE CASCADE NOT NULL,
    asset_type TEXT NOT NULL CHECK (asset_type IN ('STOCK', 'CRYPTO')),
    exchange TEXT NOT NULL CHECK (exchange IN ('TOSS', 'COINONE', 'BINANCE', 'KIS')),
    preset_name TEXT,
    interval TEXT NOT NULL,
    count INTEGER NOT NULL CHECK (count > 0),
    chunk_size INTEGER,
    chunk_index INTEGER,
    symbols JSONB DEFAULT '[]'::jsonb NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('running', 'success', 'failed')),
    row_count INTEGER,
    failure_count INTEGER DEFAULT 0,
    output_path TEXT,
    failure_output_path TEXT,
    failures JSONB DEFAULT '[]'::jsonb NOT NULL,
    error_message TEXT,
    created_at TIMESTAMPTZ DEFAULT timezone('utc'::text, now()) NOT NULL,
    started_at TIMESTAMPTZ DEFAULT timezone('utc'::text, now()) NOT NULL,
    finished_at TIMESTAMPTZ
);

ALTER TABLE public.ml_dataset_jobs ENABLE ROW LEVEL SECURITY;

GRANT SELECT, INSERT, UPDATE ON TABLE public.ml_dataset_jobs TO authenticated;

CREATE POLICY "사용자는 자신의 ML 데이터셋 작업만 조회 가능" ON public.ml_dataset_jobs
    FOR SELECT
    TO authenticated
    USING ((select auth.uid()) = user_id);

CREATE POLICY "사용자는 자신의 ML 데이터셋 작업만 생성 가능" ON public.ml_dataset_jobs
    FOR INSERT
    TO authenticated
    WITH CHECK ((select auth.uid()) = user_id);

CREATE POLICY "사용자는 자신의 ML 데이터셋 작업만 수정 가능" ON public.ml_dataset_jobs
    FOR UPDATE
    TO authenticated
    USING ((select auth.uid()) = user_id)
    WITH CHECK ((select auth.uid()) = user_id);


CREATE TABLE IF NOT EXISTS public.ml_training_runs (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    user_id UUID REFERENCES public.profiles(id) ON DELETE CASCADE NOT NULL,
    label TEXT,
    asset_type TEXT CHECK (asset_type IN ('STOCK', 'CRYPTO')),
    config_path TEXT NOT NULL,
    risk_config_path TEXT,
    summary_output_path TEXT,
    skip_build_features BOOLEAN DEFAULT false NOT NULL,
    model_version TEXT,
    dataset_job_id UUID REFERENCES public.ml_dataset_jobs(id) ON DELETE SET NULL,
    status TEXT NOT NULL CHECK (status IN ('running', 'success', 'failed')),
    command JSONB DEFAULT '[]'::jsonb NOT NULL,
    returncode INTEGER,
    stdout_tail TEXT,
    stderr_tail TEXT,
    metrics_json JSONB,
    risk_metrics_json JSONB,
    backtest_up_only_json JSONB,
    backtest_composite_json JSONB,
    created_at TIMESTAMPTZ DEFAULT timezone('utc'::text, now()) NOT NULL,
    started_at TIMESTAMPTZ DEFAULT timezone('utc'::text, now()) NOT NULL,
    finished_at TIMESTAMPTZ
);

ALTER TABLE public.ml_training_runs ENABLE ROW LEVEL SECURITY;

GRANT SELECT, INSERT, UPDATE ON TABLE public.ml_training_runs TO authenticated;

CREATE POLICY "사용자는 자신의 ML 학습 실행만 조회 가능" ON public.ml_training_runs
    FOR SELECT
    TO authenticated
    USING ((select auth.uid()) = user_id);

CREATE POLICY "사용자는 자신의 ML 학습 실행만 생성 가능" ON public.ml_training_runs
    FOR INSERT
    TO authenticated
    WITH CHECK ((select auth.uid()) = user_id);

CREATE POLICY "사용자는 자신의 ML 학습 실행만 수정 가능" ON public.ml_training_runs
    FOR UPDATE
    TO authenticated
    USING ((select auth.uid()) = user_id)
    WITH CHECK ((select auth.uid()) = user_id);


CREATE TABLE IF NOT EXISTS public.ml_model_registry (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    asset_type TEXT NOT NULL CHECK (asset_type IN ('STOCK', 'CRYPTO')),
    model_version TEXT NOT NULL,
    model_path TEXT,
    metrics_path TEXT,
    summary_path TEXT,
    recommendation_reason TEXT,
    is_latest BOOLEAN DEFAULT false NOT NULL,
    is_recommended BOOLEAN DEFAULT false NOT NULL,
    is_serving BOOLEAN DEFAULT false NOT NULL,
    approved_by UUID REFERENCES public.profiles(id) ON DELETE SET NULL,
    approved_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT timezone('utc'::text, now()) NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT timezone('utc'::text, now()) NOT NULL,
    UNIQUE (asset_type, model_version)
);

ALTER TABLE public.ml_model_registry ENABLE ROW LEVEL SECURITY;

GRANT SELECT, INSERT, UPDATE ON TABLE public.ml_model_registry TO authenticated;

CREATE POLICY "인증 사용자는 ML 모델 레지스트리 조회 가능" ON public.ml_model_registry
    FOR SELECT
    TO authenticated
    USING (true);

CREATE POLICY "인증 사용자는 ML 모델 레지스트리 생성 가능" ON public.ml_model_registry
    FOR INSERT
    TO authenticated
    WITH CHECK (true);

CREATE POLICY "인증 사용자는 ML 모델 레지스트리 수정 가능" ON public.ml_model_registry
    FOR UPDATE
    TO authenticated
    USING (true)
    WITH CHECK (true);

CREATE INDEX IF NOT EXISTS idx_ml_dataset_jobs_user_created_at
    ON public.ml_dataset_jobs (user_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_ml_training_runs_user_created_at
    ON public.ml_training_runs (user_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_ml_model_registry_asset_type
    ON public.ml_model_registry (asset_type, is_serving DESC, is_recommended DESC, created_at DESC);
