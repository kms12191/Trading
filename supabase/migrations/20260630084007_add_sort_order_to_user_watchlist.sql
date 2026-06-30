-- user_watchlist 테이블에 sort_order 컬럼이 없을 경우 안전하게 추가합니다.
ALTER TABLE public.user_watchlist 
ADD COLUMN IF NOT EXISTS sort_order INTEGER;

-- 정렬 조회를 위한 인덱스를 생성합니다.
CREATE INDEX IF NOT EXISTS idx_user_watchlist_user_sort_order 
ON public.user_watchlist (user_id, sort_order ASC, updated_at DESC);
