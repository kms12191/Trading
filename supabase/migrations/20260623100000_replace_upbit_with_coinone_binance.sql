-- 1. user_api_keys 테이블 exchange CHECK 제약 갱신 (UPBIT 제거, COINONE & BINANCE 추가)
ALTER TABLE public.user_api_keys DROP CONSTRAINT IF EXISTS user_api_keys_exchange_check;
ALTER TABLE public.user_api_keys ADD CONSTRAINT user_api_keys_exchange_check CHECK (exchange IN ('COINONE', 'BINANCE', 'KIS', 'TOSS'));

-- 2. trade_proposals 테이블 exchange CHECK 제약 갱신
ALTER TABLE public.trade_proposals DROP CONSTRAINT IF EXISTS trade_proposals_exchange_check;
ALTER TABLE public.trade_proposals ADD CONSTRAINT trade_proposals_exchange_check CHECK (exchange IN ('COINONE', 'BINANCE', 'KIS', 'TOSS'));

-- 3. auto_trading_rules 테이블 exchange CHECK 제약 갱신
ALTER TABLE public.auto_trading_rules DROP CONSTRAINT IF EXISTS auto_trading_rules_exchange_check;
ALTER TABLE public.auto_trading_rules ADD CONSTRAINT auto_trading_rules_exchange_check CHECK (exchange IN ('COINONE', 'BINANCE', 'KIS', 'TOSS'));
