-- migration: 20260709120000_add_auto_restart_to_rules.sql
-- auto_trading_rules 테이블에 부분 체결 시 자동 재감시 처리 옵션 추가

ALTER TABLE public.auto_trading_rules
ADD COLUMN auto_restart_on_partial_fill BOOLEAN DEFAULT TRUE NOT NULL;

-- 인덱스 추가 (필요에 따라 조회 성능 향상 목적)
CREATE INDEX IF NOT EXISTS idx_auto_trading_rules_restart ON public.auto_trading_rules(auto_restart_on_partial_fill);
