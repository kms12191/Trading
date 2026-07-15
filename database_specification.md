# 데이터베이스 사양서 (database_specification.md)

본 문서는 Toss증권 메인 트레이딩 MVP 시스템의 Supabase 데이터베이스 테이블 스펙 및 제약조건을 실제 마이그레이션 SQL과 백엔드 비즈니스 로직을 기준으로 상세히 정의한 표준 사양서입니다.

---

## 1. 데이터베이스 ER 다이어그램 (스키마 관계)

```mermaid
erDiagram
    profiles ||--o{ user_api_keys : "owns"
    profiles ||--o{ trade_proposals : "creates"
    profiles ||--o{ broker_order_history : "syncs"
    profiles ||--o{ auto_trading_rules : "defines"
    profiles ||--o{ user_watchlist : "favorites"
    profiles ||--o{ chat_history : "dialogues"
    profiles ||--o{ paper_portfolios : "paper_trading"
    profiles ||--|| public_profiles : "publishes"
    profiles ||--o{ community_posts : "writes"

    profiles ||--o{ ml_dataset_jobs : "executes"
    profiles ||--o{ ml_training_runs : "runs"
    profiles ||--o{ ml_model_registry : "approves"

    ml_dataset_jobs ||--o{ ml_training_runs : "feeds"
    user_api_keys ||--o{ token_caches : "caches_oauth"
```

---

## 2. 테이블별 상세 정의 (19개 핵심 테이블)

### 2.1 profiles
*   **용도**: 서비스 가입 사용자의 기본 정보와 인증 권한의 매핑 테이블 (Supabase Auth와 auth.uid() 연동)
*   **주요 컬럼**:
    *   `id` (UUID, PK) - `auth.users.id` 참조
    *   `email` (TEXT)
    *   `nickname` (TEXT)
    *   `phone` (TEXT)
    *   `role` (TEXT) - `USER`(일반 사용자) / `ADMIN`(관리자)
    *   `updated_at` (TIMESTAMPTZ)
*   **RLS (Row Level Security)**:
    *   `auth.uid() = id` 인 사용자만 자신의 프로필 조회 및 수정 가능.
    *   일반 사용자는 컬럼 권한상 `role`을 직접 수정할 수 없으며, 닉네임/연락처/투자성향 관련 컬럼만 갱신 가능.

### 2.1.1 public_profiles
*   **용도**: 커뮤니티 화면에서 공개해도 되는 최소 사용자 정보만 분리해 보관하는 공개 프로필 테이블입니다. `profiles.nickname` 또는 `profiles.role` 변경 시 트리거로 자동 동기화되어, 과거 커뮤니티 글도 최신 닉네임을 표시할 수 있습니다.
*   **주요 컬럼**:
    *   `id` (UUID, PK/FK) - `profiles.id` 참조
    *   `nickname` (TEXT) - 커뮤니티 표시용 닉네임
    *   `role` (TEXT) - `USER` / `ADMIN`
    *   `updated_at` (TIMESTAMPTZ)
*   **RLS**:
    *   로그인 사용자는 공개 프로필을 조회할 수 있습니다.
    *   생성/수정/삭제는 직접 허용하지 않고 `profiles` 동기화 트리거 또는 `service_role`만 수행합니다.

### 2.2 user_api_keys
*   **용도**: Toss증권, KIS(한국투자증권), 코인원, 바이낸스 등 연동 거래소의 API Access/Secret Key 및 계좌 정보를 평문 노출 방지를 위해 양방향 암호화(AES-256-GCM)하여 저장합니다.
*   **주요 컬럼**:
    *   `id` (UUID, PK)
    *   `user_id` (UUID, FK) - `profiles.id` 참조
    *   `exchange` (TEXT) - `TOSS`, `COINONE`, `BINANCE`, `KIS` 등 허용. 바이낸스 USD-M 선물도 별도 키 레코드를 만들지 않고 `BINANCE` 키를 재사용합니다.
    *   `broker_env` (TEXT) - `MOCK`(모의투자), `REAL`(실거래)
    *   `encrypted_access_key` (TEXT) - 암호화된 API Key / Client ID
    *   `encrypted_secret_key` (TEXT) - 암호화된 Secret Key / Client Secret
    *   `toss_account_seq` (TEXT) - Toss증권 계좌 고유 시퀀스
    *   `toss_account_no` (TEXT) - Toss증권 계좌번호
    *   `kis_account_no` (TEXT) - KIS 종합계좌번호 (8자리)
    *   `kis_account_code` (TEXT) - KIS 상품코드 (2자리, 기본 '01')
    *   `created_at` (TIMESTAMPTZ)
*   **제약조건**:
    *   `UNIQUE (user_id, exchange, broker_env)` 복합 유니크 키 적용
*   **RLS**:
    *   `auth.uid() = user_id` 조건으로 본인의 API 키 레코드만 관리 가능.

### 2.3 trade_proposals
*   **용도**: LLM 챗봇이 생성하여 제안하는 매매 제안 기록 및 사용자가 최종 승인하여 실행한 실거래/모의 주문 결과 로깅 테이블.
*   **주요 컬럼**:
    *   `id` (UUID, PK)
    *   `user_id` (UUID, FK) - `profiles.id` 참조
    *   `exchange` (TEXT) - `TOSS`, `COINONE`, `BINANCE`, `BINANCE_UM_FUTURES`, `KIS` 등. `BINANCE_UM_FUTURES`는 주문/이력 식별값이며 인증 키는 `user_api_keys.exchange=BINANCE`를 사용합니다.
    *   `asset_type` (TEXT) - `STOCK`(주식), `CRYPTO`(가상자산)
    *   `symbol` (TEXT) - 종목 코드 (예: 6자리 코드 또는 코인 식별명)
    *   `ticker` (TEXT) - KIS/Toss용 티커
    *   `side` (TEXT) - `BUY`(매수), `SELL`(매도)
    *   `price` (NUMERIC) - 지정가 주문 단가
    *   `volume` (NUMERIC) - 주문 수량
    *   `order_amount` (NUMERIC) - Toss 금액 주문용 원화 금액
    *   `ord_type` (TEXT) - `LIMIT`(지정가), `MARKET`(시장가)
    *   `status` (TEXT) - `PENDING`(승인대기), `APPROVED`/`ORDERED`(주문접수), `OPEN`(미체결), `PARTIALLY_FILLED`(부분체결), `MODIFIED`(정정접수), `REJECTED`/`FAILED`/`EXPIRED`(주문실패), `EXECUTED`(체결완료), `CANCELED`(취소완료)
    *   `failure_reason` (TEXT) - 외부 거래소 에러 코드 및 오류 내용
    *   `client_order_id` (UUID) - 멱등성 보장용 클라이언트 고유 주문 ID
    *   `external_order_id` (TEXT) - 거래소 체결 주문번호
    *   `raw_order_payload` (JSONB) - 거래소에서 반환한 응답 JSON 전문
    *   `broker_env` (TEXT) - `MOCK`(모의), `REAL`(실거래)
    *   `created_at` (TIMESTAMPTZ)
    *   `approved_at` (TIMESTAMPTZ) - 승인 실행 선점 시각
    *   `modified_at` (TIMESTAMPTZ) - 주문 정정 시점
    *   `canceled_at` (TIMESTAMPTZ) - 주문 취소 시점
*   **RLS & Realtime**:
    *   Supabase Realtime 구독이 활성화되어 있어 백엔드 생성 즉시 프론트엔드로 승인 팝업 노출.
    *   `auth.uid() = user_id` 사용자만 읽기 및 관리 가능.
*   **원자 승인·거절**:
    *   `claim_trade_proposal_for_execution(p_proposal_id uuid)`는 호출 사용자가 소유한 `PENDING` 제안만 `APPROVED`로 변경하고 `approved_at`을 기록합니다. 이미 선점된 제안은 반환되지 않습니다.
    *   함수는 `SECURITY INVOKER`로 실행하며 `authenticated`, `service_role`만 실행할 수 있습니다.
    *   거절은 `id`, `user_id`, `status=PENDING` 조건을 포함한 단일 `UPDATE ... RETURNING` 요청으로 처리하여 승인 선점과 경쟁해도 상태를 덮어쓰지 않습니다.
    *   종목 상세 수동 주문은 요청의 UUID `idempotency_key`를 `trade_proposals.id`로 사용해 외부 주문 전 `PENDING` 레코드를 생성합니다. 같은 키의 재요청은 기존 레코드를 조회하고 원자 선점에 성공한 요청만 거래소로 전송합니다.
*   **챗봇 제안 생성 규칙**:
    *   챗봇 경로의 `PENDING` 제안은 `raw_order_payload.precheck_status=OK`이고 현재가·예상 주문금액과 주문 방향에 필요한 잔고·보유수량을 확인했으며 장 운영, 거래 권한, 지원 주문유형, 실거래 한도 검증에 차단 사유가 없을 때만 생성합니다.
    *   MOCK은 10만 원 하드캡만 우회하고 잔고·보유수량 검증은 유지합니다. REAL 시장가는 슬리피지로 하드캡을 보장할 수 없어 차단합니다.
    *   Binance 현물 매도 검증은 `exchangeInfo.baseAsset`을 우선 조회해 `BTCUSDT`, `BTCEUR` 같은 주문 심볼을 잔고의 `BTC`와 비교하며, 메타데이터 장애 시에만 알려진 quote asset 접미사 제거로 폴백합니다.
    *   외부 주문 후 상세 payload 저장이 실패하면 `status`, `client_order_id`, `external_order_id`를 최소 복구하며, 복구 실패 시 성공 응답 대신 재전송 금지 안내를 반환합니다.
*   **현재 구현 메모**:
    *   `COINONE` 실주문은 백엔드 `trade` 라우트에서 지정가(`LIMIT`) 매수/매도와 미체결 주문 취소까지 연결되어 있습니다.
    *   `COINONE` 시장가(`MARKET`) 주문은 API 정책 검증 전까지 프론트엔드와 백엔드에서 차단합니다.
    *   `BINANCE` 현물 주문은 `REAL`과 `MOCK` 환경을 분리해 지원합니다. `MOCK`은 Binance Spot Demo API를 사용하며 실제 입출금성 API는 호출하지 않습니다.
    *   `BINANCE_UM_FUTURES`는 USD-M 선물 계좌/포지션 조회와 `MOCK` 주문을 지원합니다. 인증 키는 `BINANCE` 레코드를 재사용하며, 주문 전 레버리지(`1~125x`)와 마진 타입(`CROSSED`/`ISOLATED`)을 심볼 단위로 설정한 뒤 주문을 전송합니다. `REAL` 선물 주문은 `BINANCE_FUTURES_REAL_ENABLED=true` 환경변수 없이는 백엔드에서 차단합니다.

### 2.4 auto_trading_rules
*   **용도**: 사용자가 자연어로 설정하거나 명시적으로 승인한 감시 조건식(익절 %, 손절 % 등)을 보관하는 테이블.
*   **주요 컬럼**:
    *   `id` (UUID, PK)
    *   `user_id` (UUID, FK) - `profiles.id` 참조
    *   `exchange` (TEXT)
    *   `broker_env` (TEXT) - `MOCK`, `REAL`
    *   `asset_type` (TEXT) - `STOCK` / `CRYPTO`
    *   `symbol` (TEXT)
    *   `ticker` (TEXT)
    *   `entry_price` (NUMERIC) - 진입 가격 (기본 평단가)
    *   `investment_amount` (NUMERIC) - 할당 투자 금액
    *   `quantity` (NUMERIC) - 조건 도달 시 매도할 수량. 없으면 `investment_amount / entry_price`로 보정
    *   `target_profit_rate` (NUMERIC) - 익절 비율 백분율 (%)
    *   `stop_loss_rate` (NUMERIC) - 손절 비율 백분율 (%)
    *   `execution_mode` (TEXT) - `PROPOSAL`(매도 제안만 생성), `AUTO`(조건 도달 시 자동 매도 주문 전송)
    *   `trigger_side` (TEXT) - `TAKE_PROFIT`, `STOP_LOSS`
    *   `trigger_price` (NUMERIC) - 조건 도달 시 확인된 현재가
    *   `triggered_at` (TIMESTAMPTZ) - 조건 도달 시각
    *   `last_checked_at` (TIMESTAMPTZ) - 워커의 마지막 감시 확인 시각
    *   `last_error` (TEXT) - 최근 감시/주문 실패 사유
    *   `exit_order_proposal_id` (UUID) - 조건 도달 후 생성된 `trade_proposals.id`
    *   `exit_order_payload` (JSONB) - 자동매도 주문 응답 또는 제안 생성 메타데이터
    *   `status` (TEXT) - `RUNNING`(감시 중), `COMPLETED`(익손절 완료), `STOPPED`(정지)
    *   `created_at` (TIMESTAMPTZ)
    *   `updated_at` (TIMESTAMPTZ)
*   **RLS**:
    *   `auth.uid() = user_id` 기반 RLS 적용.
*   **실행 정책**:
    *   `backend/services/auto_trading_rule_engine.py`가 `RUNNING` 규칙을 조회해 현재가가 익절/손절 가격에 도달했는지 확인합니다.
    *   `execution_mode=PROPOSAL`이면 `trade_proposals`에 `PENDING` 매도 제안만 생성합니다.
    *   `execution_mode=AUTO`이면 워커가 매도 주문을 직접 전송하고 `trade_proposals`에 결과를 기록합니다. 단, 실거래(`REAL`) 주문 추정 원화 금액이 내부 1회 한도 10만 원을 초과하면 자동 주문 대신 제안 생성으로 우회합니다.

### 2.4.1 broker_order_history
*   **용도**: 외부 브로커(Toss/KIS/Coinone/Binance)의 실제 주문 원장을 주기적으로 동기화해 저장하는 테이블입니다. 앱 내부 제안 흐름(`trade_proposals`)과 분리하여 실제 미체결/부분체결/체결/취소 결과를 추적합니다.
*   **주요 컬럼**:
    *   `id` (UUID, PK)
    *   `user_id` (UUID, FK) - `profiles.id` 참조
    *   `exchange` (TEXT) - `TOSS`, `KIS`, `COINONE`, `BINANCE`, `BINANCE_UM_FUTURES`
    *   `broker_env` (TEXT) - `MOCK`, `REAL`
    *   `account_ref` (TEXT) - 브로커 계좌 식별값
    *   `external_order_id` (TEXT) - 거래소 원주문번호
    *   `client_order_id` (TEXT) - 클라이언트 멱등 주문번호
    *   `symbol` (TEXT) - 종목 코드/티커
    *   `market_country` (TEXT) - `KR` / `US`
    *   `side` (TEXT) - `BUY` / `SELL`
    *   `order_type` (TEXT)
    *   `time_in_force` (TEXT)
    *   `status` (TEXT) - 내부 정규화 상태값 (`OPEN`, `PARTIALLY_FILLED`, `EXECUTED`, `CANCELED`, `FAILED` 등)
    *   `raw_status` (TEXT) - 거래소 원본 상태값
    *   `currency` (TEXT) - `KRW` / `USD`
    *   `price` (NUMERIC)
    *   `quantity` (NUMERIC)
    *   `order_amount` (NUMERIC)
    *   `filled_quantity` (NUMERIC)
    *   `average_filled_price` (NUMERIC)
    *   `filled_amount` (NUMERIC)
    *   `commission` (NUMERIC)
    *   `tax` (NUMERIC)
    *   `ordered_at` (TIMESTAMPTZ)
    *   `filled_at` (TIMESTAMPTZ)
    *   `canceled_at` (TIMESTAMPTZ)
    *   `settlement_date` (DATE)
    *   `source_api` (TEXT)
    *   `raw_payload` (JSONB)
    *   `last_synced_at` (TIMESTAMPTZ)
    *   `created_at` (TIMESTAMPTZ)
    *   `updated_at` (TIMESTAMPTZ)
*   **제약조건**:
    *   `UNIQUE (user_id, exchange, broker_env, external_order_id)` 복합 유니크 키 적용
*   **RLS & Realtime**:
    *   `auth.uid() = user_id` 조건으로 사용자별 원장만 조회/관리 가능
    *   Supabase Realtime publication에 포함되어 거래내역 탭에서 즉시 반영 가능

### 2.4.2 asset_transfer_proposals
*   **용도**: 코인원 ↔ 바이낸스 가상자산 출금 요청의 사전검증, 사용자 승인, 외부 거래소 응답, 입금 확인 상태를 추적합니다. 현재 UI는 코인원 → 바이낸스와 XRP 기준 바이낸스 → 코인원 출금을 지원합니다.
*   **주요 컬럼**:
    *   `id` (UUID, PK)
    *   `user_id` (UUID, FK) - `profiles.id` 참조
    *   `from_exchange` (TEXT) - 현재 `COINONE` 또는 `BINANCE`
    *   `to_exchange` (TEXT) - 현재 `BINANCE` 또는 `COINONE`
    *   `currency` (TEXT) - 출금 코인 심볼
    *   `network` (TEXT) - 출금 네트워크
    *   `amount` (NUMERIC) - 출금 수량
    *   `withdraw_fee` (NUMERIC) - 출금 요청 수량과 바이낸스 실제 입금 수량 차이로 계산한 출금 수수료
    *   `expected_receive_amount` (NUMERIC) - 사전검증 또는 입금 확인 기준 도착 예상 수량
    *   `received_amount` (NUMERIC) - 바이낸스 입금내역에서 확인된 실제 입금 수량
    *   `fee_currency` (TEXT) - 출금 수수료 단위 코인 심볼
    *   `address` (TEXT) - 바이낸스 입금 주소
    *   `secondary_address` (TEXT) - XRP/XLM/EOS Destination Tag 또는 Memo
    *   `status` (TEXT) - `PENDING`, `APPROVED`, `SUBMITTED`, `COMPLETED`, `FAILED`, `NEEDS_REVIEW` 등
    *   `external_transaction_id` (TEXT) - 출발 거래소 출금 거래 식별 ID
    *   `raw_request` / `precheck_payload` / `raw_response` / `binance_deposit_payload` (JSONB)
    *   `failure_reason` (TEXT)
    *   `approved_at`, `submitted_at`, `completed_at`, `created_at`, `updated_at` (TIMESTAMPTZ)
*   **RLS & Realtime**:
    *   `auth.uid() = user_id` 조건으로 사용자별 출금 요청만 조회/관리 가능
    *   Supabase Realtime publication에 포함되어 상태 추적 UI에 즉시 반영 가능
*   **현재 구현 메모**:
    *   실제 출금 API는 `/api/transfer/withdraw/approve`에서만 호출됩니다.
    *   승인 단계에서 바이낸스 API 조회 입금 주소 및 Tag와 입력값이 다르면 출금을 차단합니다.
    *   `precheck_payload`에는 `withdrawal_fee`, `withdrawal_min_amount`, `estimated_receive_amount`, `withdrawal_fee_source`가 포함됩니다.
    *   자동 완료 판정은 현재 코인원 → 바이낸스 경로에서 바이낸스 입금 내역 조회 기준으로만 수행합니다.
    *   바이낸스 입금 완료가 확인되면 `received_amount`, `withdraw_fee`, `expected_receive_amount`를 갱신하고, 대시보드/내 자산은 바이낸스 실제 잔고가 아직 반영되지 않은 경우에만 이 완료 출금분을 보조 보유수량으로 표시합니다.


### 2.5 news_articles
*   **용도**: 실시간 수집된 뉴스 및 종목 키워드, 그리고 AI 요약(Sentiment, Summary) 정보를 적재하여 RAG 챗봇 및 종목 상세 뉴스에 데이터를 급지함.
*   **주요 컬럼**:
    *   `id` (UUID, PK)
    *   `market` (TEXT) - `KR` / `US`
    *   `source` (TEXT) - `NAVER`, `FINNHUB` 등
    *   `source_article_id` (TEXT)
    *   `title` (TEXT) - 뉴스 제목
    *   `summary` (TEXT) - 본문 요약문
    *   `url` (TEXT) - 원본 URL
    *   `published_at` (TIMESTAMPTZ) - 뉴스 발행 시각
    *   `fetched_at` (TIMESTAMPTZ) - 크롤러 수집 시각
    *   `symbol` (TEXT) - 연관 주식 종목코드
    *   `sentiment` (TEXT) - 감성 분석 결과 (`positive`, `negative`, `neutral`)
    *   `content_hash` (TEXT) - 중복 기사 적재 방지용 해시
    *   `ai_summary` (TEXT) - AI RAG용 정교한 기사 요약본
    *   `ai_summary_model` (TEXT)
    *   `ai_summary_generated_at` (TIMESTAMPTZ)
*   **RLS**:
    *   조회는 인증된 모든 사용자(`authenticated`) 가능.

### 2.6 news_fetch_logs
*   **용도**: 뉴스 수집 봇의 동작 상태 및 배치 결과를 기록하는 로깅 테이블.
*   **주요 컬럼**:
    *   `id` (UUID, PK)
    *   `source` (TEXT)
    *   `query_key` (TEXT) - 검색 키워드 또는 종목 코드
    *   `status` (TEXT) - `success` / `failed`
    *   `request_count` (INTEGER)
    *   `fetched_count` (INTEGER)
    *   `started_at` (TIMESTAMPTZ)
    *   `error_message` (TEXT)

### 2.6.1 dart_corp_codes
*   **용도**: OpenDART 고유번호(`corp_code`)와 국내 주식 종목코드(`stock_code`)를 매핑하는 상장사 사전 테이블입니다.
*   **주요 컬럼**:
    *   `corp_code` (TEXT, PK) - DART 기업 고유번호
    *   `corp_name` (TEXT) - 기업명
    *   `stock_code` (TEXT, UNIQUE) - 국내 주식 6자리 종목코드
    *   `modify_date` (DATE) - DART 사전 수정일
    *   `raw_payload` (JSONB) - 원본 사전 데이터
*   **RLS**:
    *   일반 조회는 허용하고, 생성/수정은 `service_role`만 수행합니다.

### 2.6.2 dart_disclosures
*   **용도**: OpenDART 전체 공시 목록 API에서 `stock_code`가 있는 상장사 공시만 수집해 저장하는 공시 캐시 테이블입니다.
*   **주요 컬럼**:
    *   `rcept_no` (TEXT, UNIQUE) - 공시 접수번호, 중복 upsert 기준
    *   `corp_code` (TEXT) - DART 기업 고유번호
    *   `stock_code` (TEXT) - 국내 주식 종목코드
    *   `corp_name` (TEXT) - 기업명
    *   `report_nm` (TEXT) - 공시명
    *   `flr_nm` (TEXT) - 제출인
    *   `rcept_dt` (DATE) - 접수일
    *   `url` (TEXT) - DART 원문 URL
    *   `summary` (TEXT) - 목록 기반 간단 요약
    *   `raw_payload` (JSONB) - OpenDART 원본 응답
*   **RLS**:
    *   활성 공시는 공개 조회 가능하고, 수집/수정은 `service_role`만 수행합니다.

### 2.6.3 dart_fetch_logs
*   **용도**: OpenDART 전체 공시 목록 수집 및 최근 1년 백필 작업의 실행 결과를 기록합니다.
*   **주요 컬럼**:
    *   `query_key` (TEXT) - `incremental` 또는 백필 날짜 구간
    *   `status` (TEXT) - `SUCCESS`, `FAILED`, `SKIPPED`
    *   `fetched_count` (INTEGER)
    *   `inserted_count` (INTEGER)
    *   `request_count` (INTEGER)
    *   `error_message` (TEXT)

### 2.7 user_watchlist
*   **용도**: 사용자가 개별적으로 "하트"를 눌러 즐겨찾기 목록에 등록한 관심 종목 보관 테이블.
*   **주요 컬럼**:
    *   `id` (UUID, PK)
    *   `user_id` (UUID, FK) - `profiles.id` 참조
    *   `symbol` (TEXT) - 관심 종목 코드
    *   `name` (TEXT) - 종목 한글 표시명
    *   `exchange` (TEXT) - `TOSS`, `COINONE`, `BINANCE`, `BINANCE_UM_FUTURES`, `KIS` 등. 바이낸스 선물 주문 이력은 `BINANCE_UM_FUTURES`로 남기되 키 저장은 `BINANCE`를 사용합니다.
    *   `asset_type` (TEXT) - `STOCK` 또는 `CRYPTO`
    *   `latest_price` (NUMERIC) - 최종 조회 시세 캐시
    *   `change_rate` (NUMERIC) - 당일 변동률
    *   `created_at` (TIMESTAMPTZ)
    *   `updated_at` (TIMESTAMPTZ)
*   **제약조건**:
    *   `UNIQUE (user_id, symbol, asset_type, exchange)` 적용으로 중복 등록 방지.
*   **RLS**:
    *   `auth.uid() = user_id` 조건으로 사용자 단위로 안전하게 격리되어 조회/추가/수정/삭제 가능.

### 2.8 token_caches
*   **용도**: Toss 및 KIS Open API 호출 시 사용하는 OAuth 2.0 Access Token 및 만료 기한의 공유 캐시 저장소.
*   **주요 컬럼**:
    *   `id` (UUID, PK)
    *   `user_id` (UUID) - 토큰 발급 소유 계정 ID (사용자 격리 지원)
    *   `exchange` (TEXT) - `TOSS`, `KIS` 등
    *   `broker_env` (TEXT) - `MOCK`, `REAL`
    *   `encrypted_token` (TEXT) - 암호화된 OAuth 토큰 문자열
    *   `expires_at` (TIMESTAMPTZ) - 토큰 만료 만기 시각
    *   `updated_at` (TIMESTAMPTZ)
*   **RLS**:
    *   `auth.uid() = user_id` 조건으로 본인의 토큰 정보에만 접근 가능.

### 2.9 active_locks
*   **용도**: 백그라운드 스레드 및 워커가 기동될 때 크론(뉴스 크롤러, ML 자동화 등)의 동시성 이중 구동을 막기 위한 PostgreSQL 분산 뮤텍스 락 테이블.
*   **주요 컬럼**:
    *   `key` (TEXT, PK) - 락 명칭 (예: `news_ingest`, `ml_automation`)
    *   `owner` (TEXT) - 락을 소유한 프로세스/스레드 정보
    *   `expires_at` (TIMESTAMPTZ) - 락 자동 릴리즈 시간
    *   `created_at` (TIMESTAMPTZ)

### 2.10 ml_dataset_jobs
*   **용도**: 머신러닝 학습 데이터를 추출하는 백그라운드 데이터 수집 작업 로그 정보.
*   **주요 컬럼**:
    *   `id` (UUID, PK)
    *   `user_id` (UUID, FK) - `profiles.id` 참조
    *   `parent_id` (UUID, FK, Nullable) - 원댓글 `community_posts.id` 참조. `NULL`이면 원댓글, 값이 있으면 1단계 답글
    *   `asset_type` (TEXT) - `STOCK` / `CRYPTO`
    *   `exchange` (TEXT)
    *   `status` (TEXT) - `running`, `success`, `failed`
    *   `symbols` (JSONB) - 수집 종목 배열
    *   `row_count` (INTEGER)
    *   `output_path` (TEXT) - 데이터셋 저장 파일 경로

### 2.11 ml_training_runs
*   **용도**: LightGBM 알고리즘 모델의 로컬 사전 학습 실행 세부 통계 지표와 평가(Metrics) 로깅 테이블.
*   **주요 컬럼**:
    *   `id` (UUID, PK)
    *   `user_id` (UUID, FK) - `profiles.id` 참조
    *   `model_version` (TEXT)
    *   `status` (TEXT) - `running`, `success`, `failed`
    *   `metrics_json` (JSONB) - 백테스트 수익률, MDD, CV Accuracy 등 평가지표

### 2.12 ml_model_registry
*   **용도**: 학습이 끝난 모델 파일의 메타데이터를 저장하고, 실제 추론에 기동되는 서빙(`Serving`) 모델을 승격 및 통제하기 위한 레지스트리.
*   **주요 컬럼**:
    *   `id` (UUID, PK)
    *   `asset_type` (TEXT)
    *   `model_version` (TEXT)
    *   `is_serving` (BOOLEAN) - 실시간 시세 예측 서빙 기동 여부
    *   `is_recommended` (BOOLEAN)
    *   `approved_by` (UUID) - 최종 승인 시니어 개발자 ID

### 2.13 kis_stock_master (종목 마스터 원천 DB)
*   **용도**: 국내 및 미국 상장 주식의 원천 정보 데이터베이스. 백엔드의 종목코드 자동완성 및 한글 종목명-종목코드 동적 치환 검색용 단일 원천(Single Source of Truth)으로 동작합니다.
*   **주요 컬럼**:
    *   `id` (UUID, PK)
    *   `symbol` (TEXT) - 종목 고유 코드 (국내는 6자리 예: `005930`, 미국은 티커 예: `AAPL`)
    *   `name` (TEXT) - 공식 종목명
    *   `display_name` (TEXT) - 접두사(`KR...`)와 공백을 깔끔하게 제거해 사용자가 읽을 수 있도록 정제한 표시명 (예: `이노스페이스`, `삼성전자`)
    *   `sector` (TEXT) - 주식 테마 분류 (예: `반도체`, `우주항공`, `빅테크`)
    *   `market_segment` (TEXT) - `KOSPI`, `KOSDAQ`, `KONEX`, `ETF`, `ETN`, `NASDAQ`, `NYSE`, `AMEX`, `OTHER` 허용
    *   `market_country` (TEXT) - `KR` (대한민국) / `US` (미국)
    *   `asset_type` (TEXT) - `STOCK` 고정
    *   `source` (TEXT) - `KIS` / `TOSS`
    *   `source_file_row` (JSONB) - 마스터 파일 파싱 정보 보관용
    *   `is_active` (BOOLEAN) - 거래 활성화 여부
    *   `created_at` (TIMESTAMPTZ)
    *   `updated_at` (TIMESTAMPTZ)
*   **제약조건**:
    *   `symbol` UNIQUE 제약 적용.
    *   `market_country IN ('KR', 'US')` 적용 (미국주식 완벽 대응).
    *   `market_segment IN ('KOSPI', 'KOSDAQ', 'KONEX', 'ETF', 'ETN', 'NASDAQ', 'NYSE', 'AMEX', 'OTHER')` 적용.
*   **RLS**:
    *   일반 사용자는 조회(SELECT)만 가능, 생성/수정/삭제 권한은 `service_role` 전용.

### 2.14 kis_stock_turnover_latest
*   **용도**: KIS 거래대금 및 시가총액 정보의 캐시를 저장하는 실시간 통계 테이블. 대시보드의 실시간 랭킹(거래량/상승률 등) 위젯에 사용됩니다.
*   **주요 컬럼**:
    *   `id` (UUID, PK)
    *   `symbol` (TEXT, UNIQUE) - 종목 코드
    *   `name` (TEXT)
    *   `market_segment` (TEXT)
    *   `market_country` (TEXT)
    *   `current_price` (NUMERIC) - 당일 현재가
    *   `change_rate` (NUMERIC) - 당일 대비 상승률 (%)
    *   `trading_volume` (NUMERIC) - 당일 거래량
    *   `trading_value` (NUMERIC) - 당일 거래대금
    *   `as_of` (TIMESTAMPTZ) - KIS 최종 동기화 시점
*   **RLS**:
    *   조회(SELECT)는 누구나 가능, 갱신(UPSERT)은 `service_role` 계정 전용.

### 2.14.1 market_calendar_days
*   **용도**: 한국장(`KR`)과 미국장(`US`)의 일자별 개장/휴장 및 정규장 운영 시간을 저장하는 캘린더 캐시 테이블입니다. 챗봇이 특정 날짜의 장 운영 여부를 일반 지식으로 추측하지 않고, DB 또는 Toss 장 운영 캘린더 API 결과를 기준으로 답변할 때 사용합니다.
*   **주요 컬럼**:
    *   `id` (UUID, PK)
    *   `market_country` (TEXT) - `KR` 또는 `US`
    *   `trade_date` (DATE) - 장 운영 여부를 확인할 기준 일자
    *   `is_open` (BOOLEAN) - 정규장 운영 여부
    *   `holiday_name` (TEXT) - 휴장 사유 또는 휴일명
    *   `regular_open_at` (TIMESTAMPTZ) - 정규장 시작 시각
    *   `regular_close_at` (TIMESTAMPTZ) - 정규장 종료 시각
    *   `source` (TEXT) - `TOSS`, `KRX`, `NYSE`, `NASDAQ` 등 데이터 출처
    *   `raw_payload` (JSONB) - 원본 캘린더 응답
    *   `created_at` (TIMESTAMPTZ)
    *   `updated_at` (TIMESTAMPTZ)
*   **제약조건**:
    *   `UNIQUE (market_country, trade_date)` 복합 제약조건 적용.
    *   `market_country IN ('KR', 'US')` 적용.
*   **RLS**:
    *   로그인 사용자는 조회(SELECT) 가능, 생성/수정/삭제는 `service_role` 전용.

---

### 2.15 paper_portfolios
*   **용도**: 모의투자(`MOCK` 환경) 모드 시 사용자의 모의 예수금 및 모의 매매 평단가/수량을 보관하여 가상 자산을 연산해 주는 테이블.
*   **주요 컬럼**:
    *   `id` (UUID, PK)
    *   `user_id` (UUID, FK) - `profiles.id` 참조
    *   `asset_type` (TEXT) - `CRYPTO` / `STOCK`
    *   `ticker` (TEXT) - 종목 티커/심볼
    *   `average_buy_price` (NUMERIC) - 모의 평단가
    *   `volume` (NUMERIC) - 모의 보유수량
    *   `virtual_cash` (NUMERIC) - 가상 원화 잔고 (기본 10,000,000원 제공)
    *   `updated_at` (TIMESTAMPTZ)
*   **제약조건**:
    *   `UNIQUE (user_id, asset_type, ticker)` 복합 제약조건 적용.
*   **RLS**:
    *   `auth.uid() = user_id` 인 사용자만 자신의 모의 잔고 조회 및 관리 가능.

### 2.16 chat_history
*   **용도**: 사용자와 트레이딩 챗봇(AI 비서) 간의 대화 이력을 데이터베이스에 저장하여, 페이지 새로고침 시에도 이전 대화 맥락을 즉시 로드해 복구하기 위한 테이블.
*   **주요 컬럼**:
    *   `id` (BIGINT, PK, Identity)
    *   `user_id` (UUID, FK) - `profiles.id` 참조
    *   `role` (TEXT) - `user`(사용자 입력) / `assistant`(AI 답변)
    *   `message` (TEXT) - 메시지 대화 본문
    *   `created_at` (TIMESTAMPTZ)
*   **RLS**:
    *   `auth.uid() = user_id` 조건으로 자신의 챗 로그에만 보안 격리 적용.
*   **챗봇 서비스 동작**:
    *   로그인 사용자의 최근 12개 메시지를 `created_at` 및 `id` 역순으로 읽어 LLM 문맥에 복원합니다.
    *   사용자 입력과 AI 답변은 한 번의 요청에서 각각 `user`, `assistant` 행으로 저장합니다.
    *   비로그인 요청은 API 인증 단계에서 차단하며, 익명 사용자용 공용 대화 키나 이력을 생성하지 않습니다.

### 2.16.1 chatbot_conversation_states
*   **용도**: 여러 Flask 워커가 공유해야 하는 챗봇 대기 작업과 최근 추천 후보를 사용자별로 저장합니다.
*   **주요 컬럼**:
    *   `user_id` (UUID, PK, FK) - `profiles.id`를 참조하며 사용자별 상태를 1행으로 유지합니다.
    *   `pending_action` (TEXT) - 추가 입력이나 확인을 기다리는 작업 이름
    *   `pending_payload` (JSONB) - 대기 작업의 구조화 데이터이며 JSON object만 허용합니다.
    *   `pending_expires_at` (TIMESTAMPTZ) - 대기 작업 만료 시각
    *   `recommendation_items` (JSONB) - 최근 추천 후보 배열이며 JSON array만 허용합니다.
    *   `recommendation_source` (TEXT) - 추천 후보 생성 출처
    *   `recommendation_expires_at` (TIMESTAMPTZ) - 최근 추천 후보 만료 시각
    *   `updated_at` (TIMESTAMPTZ)
*   **TTL**:
    *   기본 대기 작업은 300초, 최근 추천 후보는 600초 동안 유효하며 각 만료 시각이 지난 상태는 대화 해석에 사용하지 않습니다.
*   **RLS**:
    *   `authenticated` 역할에 조회·삽입·수정·삭제 권한을 부여하고 `anon` 권한은 회수합니다.
    *   사용자는 `auth.uid() = user_id`인 자신의 행만 접근할 수 있으며, `UPDATE` 정책은 `USING`과 `WITH CHECK`를 모두 적용합니다.

### 2.17 chatbot_usage_counters
*   **용도**: 여러 Flask 워커가 공유하는 챗봇 분당 요청 수와 일일 토큰 예약량을 원자적으로 관리합니다.
*   **주요 컬럼**:
    *   `user_id` (UUID, FK) - Supabase Auth 사용자
    *   `usage_date` (DATE) - 사용량 집계 기준일
    *   `request_count` (INTEGER) - 제한 윈도우 내 요청 수
    *   `token_count` (BIGINT) - 일일 예약 토큰 수
    *   `updated_at` (TIMESTAMPTZ)
*   **RPC**: `consume_chatbot_usage()`가 advisory lock으로 동시 요청을 직렬화하고 한도를 초과하면 증가 없이 `allowed=false`를 반환합니다.
*   **RLS**:
    *   `authenticated` 사용자는 `auth.uid() = user_id`인 자신의 카운터만 조회·생성·수정할 수 있습니다.
    *   한도 차감은 `consume_chatbot_usage()` RPC를 통해 원자적으로 처리합니다.

### 2.17.1 chatbot_token_usage_logs
*   **용도**: OpenAI Chat Completions 응답에서 반환된 실제 챗봇 토큰 사용량을 요청 단위로 저장합니다. 기존 `chatbot_usage_counters`는 한도 차감용 추정 카운터이며, 이 테이블은 관리자 관찰과 감사용 실제 사용량 로그입니다.
*   **주요 컬럼**:
    *   `id` (UUID, PK)
    *   `user_id` (UUID, FK) - `profiles.id` 참조
    *   `request_id` (TEXT) - Flask 요청 ID 또는 추적 식별자
    *   `request_type` (TEXT) - `chat_reply`, `chat_stream`, `tool_synthesis` 등 호출 유형
    *   `model` (TEXT) - OpenAI 모델명
    *   `prompt_tokens` (INTEGER) - 실제 입력 토큰 수
    *   `completion_tokens` (INTEGER) - 실제 출력 토큰 수
    *   `total_tokens` (INTEGER) - 실제 전체 토큰 수
    *   `created_at` (TIMESTAMPTZ)
*   **보안 원칙**:
    *   대화 원문, tool payload, 계좌 정보, API 키, 거래소 raw 응답은 저장하지 않습니다.
    *   실제 사용량 로그는 Flask가 인증된 `user_id`를 확인한 뒤 `service_role`로만 생성하는 서버 작성 감사 데이터입니다.
    *   관리자 전체 집계는 백엔드 service role 기반 `/api/admin/users` 계열 API에서만 제공합니다.
*   **관리자 RPC**:
    *   `admin_list_user_token_usage()`가 `auth.users` 전체를 기준으로 검색, 정렬, 전체 요약, 페이지 제한을 DB에서 처리합니다. summary에는 `todayTokens`, `tokens30d`, `totalTokens`가 포함됩니다.
    *   `admin_get_user_token_usage()`가 `auth.users` 기준 사용자 정보와 일별/요청 유형별 집계, 최근 로그 제한을 DB에서 처리합니다.
    *   두 RPC는 `SECURITY DEFINER`로 실행하며 `service_role`만 호출할 수 있습니다. `today` 및 일별 버킷은 UTC 날짜 경계를 사용합니다.
    *   `20260714134000_fix_admin_user_usage_auth_source.sql` migration은 과거 트리거 누락으로 빠진 `profiles` row를 `auth.users`에서 백필해 토큰 로그 FK 저장 실패를 방지합니다.
    *   `20260714065745_add_admin_user_usage_total_tokens_summary.sql` migration은 관리자 통산 예상 비용 표시를 위해 summary의 전체 누적 토큰(`totalTokens`)을 추가합니다.
*   **RLS**:
    *   `authenticated` 사용자는 `auth.uid() = user_id`인 자신의 실제 토큰 로그만 조회할 수 있습니다.
    *   일반 사용자의 삽입·수정·삭제 권한은 회수하며, 다른 사용자의 로그도 조회할 수 없습니다.

### 2.17.2 chatbot_qa_events
*   **용도**: 팀 QA와 회귀 분석을 위해 챗봇 요청 단위의 자동 관찰 이벤트를 저장합니다. 팀원이 별도 메모를 남기지 않아도 라우트가 응답 결과, 도구 결과 요약, trace 종류, 지연시간, 에러 신호를 service role로 기록합니다.
*   **주요 컬럼**:
    *   `id` (UUID, PK)
    *   `user_id` (UUID, FK) - `profiles.id` 참조
    *   `request_id` (TEXT) - Flask 챗봇 요청 추적 식별자
    *   `event_type` (TEXT) - `CHATBOT_REPLY`, `TOOL_RESULT`, `OPENAI_TOOL_CALL`, `CHATBOT_ERROR`
    *   `event_payload` (JSONB) - 민감 원문을 제외한 요약 이벤트. `source`, `tool_source`, `symbol`, `trace_kinds`, `latency_ms`, `error_title`, `error_code`, 토큰 요약 등을 포함할 수 있습니다.
    *   `created_at` (TIMESTAMPTZ)
*   **보안 원칙**:
    *   `raw_order_payload`, 거래소 raw 응답, 계좌 정보, API 키는 저장하지 않습니다.
    *   일반 사용자와 익명 사용자의 직접 접근 권한은 회수하고, 서버가 `service_role`로만 기록합니다.
*   **분석 View**:
    *   `v_chatbot_qa_logs`는 `chat_history` 사용자 메시지를 기준으로 직후 assistant 응답, 근처 QA 이벤트, 실제 토큰 로그, 근처 주문 제안, 현재 대기 상태를 한 줄로 묶습니다.
    *   `security_invoker = true`로 생성하며 일반 사용자 접근은 열지 않습니다.
    *   `qa_flags`에는 에러, 주문 제안 생성, pending action, 느린 응답, 토큰 과다 사용, 짧은 답변, 실패성 문구 포함 여부가 자동 플래그로 포함됩니다.

### 2.18 user_knowledge_notes
*   **용도**: 앱 내부 투자노트와 Obsidian 플러그인에서 동기화한 Markdown 노트를 사용자별로 저장합니다. 현재 1차 구현은 원문 저장과 해시 기반 변경 감지만 담당하며, 후속 단계에서 `knowledge_chunks`/vector 검색으로 확장합니다.
*   **주요 컬럼**:
    *   `id` (UUID, PK)
    *   `user_id` (UUID, FK) - Supabase Auth 사용자
    *   `vault_name` (TEXT) - Obsidian Vault 또는 앱 노트 공간 이름
    *   `file_path` (TEXT) - Vault 내부 Markdown 경로
    *   `title` (TEXT) - Markdown 첫 `#` 제목 또는 파일명 기반 제목
    *   `source` (TEXT) - `obsidian` / `app`
    *   `content` (TEXT) - frontmatter를 제외한 Markdown 본문
    *   `content_hash` (TEXT) - 원문 Markdown SHA-256 해시
    *   `frontmatter` (JSONB) - Obsidian YAML frontmatter
    *   `sync_status` (TEXT) - `SYNCED` / `FAILED`
    *   `modified_at`, `created_at`, `updated_at` (TIMESTAMPTZ)
*   **제약조건**:
    *   `UNIQUE (user_id, vault_name, file_path)`로 같은 노트는 업데이트 대상으로 취급합니다.
*   **RLS**:
    *   `auth.uid() = user_id` 조건으로 자신의 지식 노트만 조회/생성/수정 가능.

### 2.18 user_memory_facts
*   **용도**: 챗봇/앱 행동 로그에서 추출한 자동메모리 후보를 사용자별 fact로 저장합니다. 챗봇은 명시적인 사용자 선호, 리스크 회피 성향, 관심종목, 반복 실수, 답변 선호를 대화 종료 시 best-effort로 저장하고, 이후 시스템 프롬프트의 자동메모리 문맥과 Obsidian 플러그인의 `자동메모리 가져오기` marker 영역에 반영합니다.
*   **주요 컬럼**:
    *   `id` (UUID, PK)
    *   `user_id` (UUID, FK) - Supabase Auth 사용자
    *   `memory_type` (TEXT) - `favorite_symbol`, `repeated_mistake`, `risk_preference`, `answer_preference`, `investment_principle`
    *   `content` (TEXT) - 사용자에게 보여줄 자동메모리 문장
    *   `symbol` (TEXT, nullable) - 관련 종목/코인 심볼
    *   `confidence` (NUMERIC) - 0~1 신뢰도
    *   `evidence_count` (INTEGER) - 같은 패턴 근거 수
    *   `source` (TEXT) - `behavioral_event` 등 생성 근거
    *   `is_active` (BOOLEAN) - 챗봇/RAG 사용 여부
    *   `metadata` (JSONB)
    *   `created_at`, `updated_at` (TIMESTAMPTZ)
*   **RLS**:
    *   `auth.uid() = user_id` 조건으로 자신의 메모리 fact만 조회/생성/수정 가능.

### 2.19 knowledge_chunks
*   **용도**: Obsidian/앱 노트, 자동메모리, 뉴스, 공시 등을 RAG 검색에 사용할 수 있도록 문단 단위 chunk로 저장합니다. 1차 구현에서는 Obsidian 노트 동기화 시 `PENDING` 상태 chunk를 만들고, 다음 단계에서 `embedding` 값을 채워 벡터 검색에 사용합니다.
*   **주요 컬럼**:
    *   `id` (UUID, PK)
    *   `user_id` (UUID, FK, nullable) - 사용자 개인 지식이면 사용자 ID, 공용 지식이면 `NULL`
    *   `source_type` (TEXT) - `OBSIDIAN`, `APP_NOTE`, `AUTO_MEMORY`, `NEWS`, `DISCLOSURE`
    *   `source_id` (TEXT) - 원본 노트/문서 ID
    *   `symbol` (TEXT, nullable) - 관련 종목/코인 심볼
    *   `market` (TEXT, nullable) - 시장 구분
    *   `chunk_index` (INTEGER) - 원본 내 chunk 순서
    *   `chunk_text` (TEXT) - 검색 및 임베딩 대상 본문
    *   `embedding` (VECTOR(1536), nullable) - 후속 embedding 작업 결과
    *   `embedding_status` (TEXT) - `PENDING`, `EMBEDDED`, `FAILED`
    *   `metadata` (JSONB) - 제목, Vault 이름, 파일 경로 등 출처 정보
    *   `importance_score`, `freshness_score` (NUMERIC) - 검색 랭킹 보조 점수
    *   `content_hash` (TEXT)
    *   `created_at`, `updated_at` (TIMESTAMPTZ)
*   **RLS**:
    *   개인 chunk는 `auth.uid() = user_id` 사용자만 조회/생성/수정/삭제 가능.
    *   `user_id IS NULL` 공용 chunk는 로그인 사용자 조회를 허용합니다.

### 2.20 community_posts
*   **용도**: 종목 디테일 페이지의 커뮤니티 탭에서 종목별 사용자 글을 저장합니다. 작성자 표시명은 글에 스냅샷으로 저장하지 않고 `public_profiles.nickname`을 조회해 최신 닉네임으로 표시합니다.
*   **주요 컬럼**:
    *   `id` (UUID, PK)
    *   `user_id` (UUID, FK) - `profiles.id` 참조
    *   `asset_type` (TEXT) - `STOCK` / `CRYPTO`
    *   `symbol` (TEXT) - 종목 코드 또는 코인 심볼
    *   `exchange` (TEXT) - 표시/필터 보조용 거래소 코드
    *   `content` (TEXT) - 1~500자 커뮤니티 본문
    *   `status` (TEXT) - `ACTIVE`(표시), `DELETED`(작성자 삭제), `HIDDEN`(관리자 숨김)
    *   `created_at` (TIMESTAMPTZ)
    *   `updated_at` (TIMESTAMPTZ)
*   **RLS & Realtime**:
    *   로그인 사용자는 `ACTIVE` 글을 조회할 수 있습니다.
    *   작성자는 본인 댓글/답글을 작성하고 `DELETED`로 소프트 삭제할 수 있습니다.
    *   답글은 원댓글 아래 1단계까지만 UI에서 허용하며, `parent_id`가 자기 자신을 참조하지 못하도록 DB 제약조건을 둡니다.
    *   `profiles.role = 'ADMIN'` 사용자는 댓글/답글을 `HIDDEN` 처리할 수 있습니다.
    *   Supabase Realtime publication에 등록되어 종목별 새 글을 즉시 반영할 수 있습니다.

---

## 2026-07-09 disclosure summary RAG update

* `knowledge_chunks` now also stores public DART disclosure analysis summaries with `source_type = 'DISCLOSURE'`.
* Disclosure RAG chunks are built from `dart_disclosure_analyses` summary/classification fields and basic `dart_disclosures` metadata only.
* DART original body text and news articles are intentionally excluded from this disclosure RAG index.
* `embedding` uses `vector(1536)` and `embedding_status` tracks `PENDING`, `EMBEDDED`, or `FAILED`.
* `match_knowledge_chunks(...)` is the vector search RPC used by the backend retrieval service.
* The vector index is created only for `embedding_status = 'EMBEDDED'` rows to keep retrieval focused on ready chunks.
## 관리자 종목 마스터 정리 테이블

### admin_symbol_reconciliation_runs

관리자가 종목 마스터 정리 스캔을 실행한 단위 이력을 저장합니다. `SKHYV`처럼 정식 상장 전 사용되던 임시 해외주식 심볼이 검색 후보나 랭킹 캐시에 남아 있는지 점검할 때 사용합니다.

- `id` (UUID, PK)
- `started_at` (TIMESTAMPTZ)
- `finished_at` (TIMESTAMPTZ)
- `status` (TEXT): `RUNNING`, `COMPLETED`, `FAILED`
- `checked_count` (INTEGER)
- `normal_count` (INTEGER)
- `suspicious_count` (INTEGER)
- `deactivation_candidate_count` (INTEGER)
- `deletable_count` (INTEGER)
- `raw_summary` (JSONB)
- `created_by` (UUID)
- `created_at` (TIMESTAMPTZ)

### admin_symbol_reconciliation_items

종목 마스터 정리 스캔 결과의 개별 심볼 판정 결과를 저장합니다.

- `id` (UUID, PK)
- `run_id` (UUID, FK)
- `symbol` (TEXT)
- `name` (TEXT)
- `source_table` (TEXT): `kis_stock_master`, `kis_stock_turnover_latest`
- `market_country` (TEXT)
- `market_segment` (TEXT)
- `status` (TEXT): `NORMAL`, `SUSPICIOUS`, `DEACTIVATION_CANDIDATE`, `INACTIVE`, `DELETABLE`
- `reason` (TEXT)
- `suggested_action` (TEXT): `NONE`, `REVIEW`, `DEACTIVATE`, `DELETE_CACHE`, `DELETE_MASTER`, `RESTORE`
- `broker_check_result` (JSONB)
- `reference_count` (INTEGER)
- `last_seen_at` (TIMESTAMPTZ)
- `created_at` (TIMESTAMPTZ)

### symbol_aliases

임시코드, 폐기코드, 종목명 변경 등으로 인해 사용자 검색 결과에서 정식 심볼로 연결하거나 배지를 표시해야 하는 심볼 매핑을 저장합니다.

- `id` (UUID, PK)
- `alias_symbol` (TEXT, UNIQUE): 임시 또는 별칭 심볼
- `canonical_symbol` (TEXT): 정식 심볼
- `alias_type` (TEXT): `TEMPORARY`, `RENAMED`, `DELISTED`, `MANUAL`
- `label` (TEXT): 화면 표시 배지. 예: `임시코드`
- `reason` (TEXT)
- `market_country` (TEXT)
- `source` (TEXT)
- `is_active` (BOOLEAN)
- `created_at` (TIMESTAMPTZ)
- `updated_at` (TIMESTAMPTZ)
