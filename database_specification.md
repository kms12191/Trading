# Supabase Database 스키마 & ERD 명세서

본 문서는 **Toss증권 Open API를 메인 주식 브로커로 사용하는 AI 트레이딩 챗봇 시스템**의 Supabase 데이터베이스 물리 스키마 명세와 ERD 구조를 정리한 산출물입니다.

현재 저장소의 기존 스키마는 KIS와 Upbit 기준이었으나, 코인원(COINONE) 및 바이낸스(BINANCE)를 도입하고 업비트(UPBIT)는 배제합니다. 본 문서는 코인원과 바이낸스를 반영한 최종 목표 구조를 설명하며, 실제 DB 반영은 별도 Supabase 마이그레이션으로 수행해야 합니다.

## 1. 데이터베이스 ERD (Mermaid)

```mermaid
erDiagram
    profiles ||--o{ user_api_keys : "possesses"
    profiles ||--o{ chat_history : "writes"
    profiles ||--o{ trade_proposals : "requests"
    profiles ||--o{ auto_trading_rules : "defines"
    profiles ||--o{ paper_portfolios : "tracks virtual assets"

    profiles {
        uuid id PK "auth.users(id) 참조"
        string email "사용자 이메일"
        string nickname "사용자 닉네임"
        string phone "사용자 연락처 (알림용)"
        integer invest_score "투자 성향 설문 총점"
        string invest_type "투자 성향 유형"
        jsonb survey_answers "설문 응답 상세 데이터"
        timestamp updated_at "수정 일시"
    }

    user_api_keys {
        uuid id PK "기본키"
        uuid user_id FK "profiles(id) 참조"
        string exchange "브로커/거래소 (TOSS | COINONE | BINANCE | KIS)"
        string encrypted_access_key "암호화된 Access Key 또는 Toss client_id"
        string encrypted_secret_key "암호화된 Secret Key 또는 Toss client_secret"
        string toss_account_seq "Toss accountSeq"
        string toss_account_no "Toss 계좌번호"
        string kis_account_no "KIS 계좌번호 (레거시)"
        string kis_account_code "KIS 계좌코드 (레거시)"
        string broker_env "브로커 환경 (MOCK | REAL)"
        timestamp created_at "등록 일시"
    }

    paper_portfolios {
        uuid id PK "기본키"
        uuid user_id FK "profiles(id) 참조"
        string asset_type "자산 종류 (CRYPTO | STOCK)"
        string ticker "내부 종목코드"
        numeric average_buy_price "평균 매입 단가"
        numeric volume "보유 수량"
        numeric virtual_cash "가상 원화 예수금"
        timestamp updated_at "갱신 일시"
    }

    chat_history {
        bigint id PK "자동 증가 기본키"
        uuid user_id FK "profiles(id) 참조"
        string role "화자 (user | assistant)"
        text message "메시지 내용"
        timestamp created_at "생성 일시"
    }

    trade_proposals {
        uuid id PK "기본키"
        uuid user_id FK "profiles(id) 참조"
        string exchange "브로커/거래소 (TOSS | COINONE | BINANCE | KIS)"
        string asset_type "자산 종류 (CRYPTO | STOCK)"
        string ticker "내부 종목코드"
        string symbol "Toss API symbol"
        string side "매수/매도 구분 (BUY | SELL)"
        numeric price "주문 가격"
        numeric volume "주문 수량"
        numeric order_amount "Toss 금액 주문 금액"
        string ord_type "내부 주문 유형"
        string time_in_force "Toss 주문 유효 조건"
        string market_country "시장 국가 (KR | US)"
        string currency "통화 (KRW | USD)"
        string client_order_id "Toss clientOrderId"
        string external_order_id "Toss orderId"
        string status "상태"
        string failure_reason "실패 사유 로그"
        timestamp created_at "제안 일시"
    }

    auto_trading_rules {
        uuid id PK "기본키"
        uuid user_id FK "profiles(id) 참조"
        string exchange "브로커/거래소 (TOSS | COINONE | BINANCE | KIS)"
        string asset_type "자산 종류 (CRYPTO | STOCK)"
        string ticker "내부 감시 종목코드"
        string symbol "Toss API symbol"
        string market_country "시장 국가 (KR | US)"
        numeric entry_price "진입 시점 기준가"
        numeric investment_amount "설정 투자금액"
        numeric target_profit_rate "목표 익절률 (%)"
        numeric stop_loss_rate "손실 제한 손절률 (%)"
        string status "감시 상태"
        timestamp created_at "생성 일시"
        timestamp updated_at "수정 일시"
    }
```

---

## 2. 공통 설계 원칙

### 2.1 브로커/거래소 값

`exchange` 컬럼은 목표 스키마 기준으로 다음 값을 허용합니다.

| 값 | 용도 | 상태 |
| :--- | :--- | :--- |
| `TOSS` | Toss증권 Open API. 국내·미국 주식 메인 브로커 | 메인 |
| `KIS` | 한국투자증권 API | 레거시/보류 |
| `COINONE` | 코인원 API. 메인 가상자산 브로커 | 메인 가상자산 |
| `BINANCE` | 바이낸스 API. 글로벌 가상자산 확장 브로커 | 확장 가상자산 |

### 2.2 Toss 용어 매핑

기존 DB와 Toss API의 필드명이 다르므로 다음 매핑을 기준으로 합니다.

| 내부 필드 | Toss API 필드 | 설명 |
| :--- | :--- | :--- |
| `ticker` | `symbol` | 기존 내부 종목코드. Toss 주식 API 호출 시 `symbol`과 매핑합니다. |
| `volume` | `quantity` | 수량 기반 주문 수량입니다. |
| `ord_type` | `orderType` | `LIMIT`, `MARKET` 값을 매핑합니다. |
| `order_amount` | `orderAmount` | Toss US MARKET 금액 기반 주문에 사용합니다. |
| `client_order_id` | `clientOrderId` | Toss 주문 생성 멱등성 키입니다. |
| `external_order_id` | `orderId` | Toss 서버가 발급한 주문 식별자입니다. |
| `time_in_force` | `timeInForce` | `DAY`, `CLS` 값을 매핑합니다. |

---

## 3. 테이블 상세 설명

### 3.1 `profiles` (사용자 프로필)

* **설명**: Supabase Auth의 `auth.users` 테이블과 연동되어 서비스 내 사용자의 기본 프로필 정보를 저장하고, 사용자의 투자 성향 설문 결과를 보관합니다.
* **제약 조건 및 트리거**:
  * `id` 필드가 `auth.users.id`를 외래키로 참조하며 삭제 시 연쇄 삭제(Cascade)됩니다.
  * 사용자가 가입할 때 트리거 함수(`handle_new_user`)에 의해 `auth.users` 테이블에서 `email`, `nickname`, `phone` 정보가 자동으로 복사됩니다.

| 컬럼명 | 데이터 타입 | 제약 조건 | 설명 |
| :--- | :--- | :--- | :--- |
| `id` | `UUID` | PK, References `auth.users(id)` | 사용자 고유 ID |
| `email` | `TEXT` | - | 사용자 이메일 주소 |
| `nickname` | `TEXT` | - | 사용자 별명 |
| `phone` | `TEXT` | - | 휴대폰 번호 (자동매매 알림 발송용) |
| `invest_score` | `INT` | - | 투자 성향 설문 조사 총점 |
| `invest_type` | `TEXT` | - | 판정된 투자 성향명 |
| `survey_answers` | `JSONB` | - | 설문 응답 상세 데이터 |
| `updated_at` | `TIMESTAMPTZ` | DEFAULT now(), NOT NULL | 마지막 수정 시간 |

---

### 3.2 `user_api_keys` (브로커/거래소 인증 정보)

* **설명**: 사용자가 등록한 Toss, KIS, 코인원, 바이낸스 인증 크리덴셜을 양방향 암호화(AES-256)하여 저장합니다.
* **Toss 기준**:
  * `encrypted_access_key`에는 Toss `client_id`를 암호화하여 저장합니다.
  * `encrypted_secret_key`에는 Toss `client_secret`을 암호화하여 저장합니다.
  * `toss_account_seq`는 `GET /api/v1/accounts` 응답의 `accountSeq`를 저장합니다.
  * `toss_account_no`는 계좌 식별 표시용으로만 사용하며, 프론트엔드에는 마스킹된 값만 노출합니다.
* **제약 조건 목표**:
  * `exchange`는 `TOSS`, `COINONE`, `BINANCE`, `KIS` 중 하나여야 합니다.
  * 동일 사용자(`user_id`)가 같은 브로커(`exchange`)와 환경(`broker_env`)에 대해 중복 인증 정보를 만들지 않도록 유니크 제약을 둡니다.

| 컬럼명 | 데이터 타입 | 제약 조건 | 설명 |
| :--- | :--- | :--- | :--- |
| `id` | `UUID` | PK, DEFAULT gen_random_uuid() | API 키 레코드 고유 ID |
| `user_id` | `UUID` | FK, References `profiles(id)` | 소유자 고유 ID |
| `exchange` | `TEXT` | CHECK (exchange IN ('TOSS', 'COINONE', 'BINANCE', 'KIS')), NOT NULL | 브로커/거래소 구분 |
| `encrypted_access_key` | `TEXT` | NOT NULL | AES-256 암호화된 Access Key 또는 Toss client_id |
| `encrypted_secret_key` | `TEXT` | NOT NULL | AES-256 암호화된 Secret Key 또는 Toss client_secret |
| `toss_account_seq` | `TEXT` | - | Toss 계좌 기반 API의 `X-Tossinvest-Account` 헤더 값 |
| `toss_account_no` | `TEXT` | - | Toss 계좌번호. 표시 시 마스킹 필요 |
| `kis_account_no` | `TEXT` | - | 한국투자증권 종합계좌번호. 레거시 필드 |
| `kis_account_code` | `TEXT` | - | 한국투자증권 종합계좌 상품코드. 레거시 필드 |
| `broker_env` | `TEXT` | CHECK (broker_env IN ('MOCK', 'REAL')), DEFAULT 'REAL' | 브로커 환경 구분 |
| `created_at` | `TIMESTAMPTZ` | DEFAULT now(), NOT NULL | 등록 일시 |

---

### 3.3 `paper_portfolios` (가상 투자 포트폴리오)

* **설명**: Toss 주문 시뮬레이션, Upbit 가상 투자, 전체 자산 현황 조회를 위한 가상 잔고와 종목 보유 수량을 관리합니다.
* **특이 사항**:
  * 가입 시 기본 10,000,000원(`virtual_cash`)의 모의 투자 자금을 지원하며, 매수/매도 실행 시 이 예수금과 보유 물량(`volume`)이 증감합니다.
  * Toss 주식 시뮬레이션에서는 `ticker`를 Toss `symbol`과 동일하게 저장할 수 있습니다.

| 컬럼명 | 데이터 타입 | 제약 조건 | 설명 |
| :--- | :--- | :--- | :--- |
| `id` | `UUID` | PK, DEFAULT gen_random_uuid() | 포트폴리오 레코드 고유 ID |
| `user_id` | `UUID` | FK, References `profiles(id)` | 소유자 고유 ID |
| `asset_type` | `TEXT` | CHECK (asset_type IN ('CRYPTO', 'STOCK')), NOT NULL | 자산 타입 구분 |
| `ticker` | `TEXT` | NOT NULL | 내부 종목 코드. Toss 연동 시 `symbol`과 매핑 |
| `average_buy_price` | `NUMERIC` | DEFAULT 0, NOT NULL | 평균 매수 단가 |
| `volume` | `NUMERIC` | DEFAULT 0, NOT NULL | 보유 수량 |
| `virtual_cash` | `NUMERIC` | DEFAULT 10000000, NOT NULL | 가상 예수금 잔고 |
| `updated_at` | `TIMESTAMPTZ` | DEFAULT now(), NOT NULL | 갱신 일시 |

---

### 3.4 `chat_history` (챗봇 대화 이력)

* **설명**: 사용자와 AI 트레이딩 챗봇 간의 자연어 대화 기록을 타임스탬프 순으로 기록합니다.

| 컬럼명 | 데이터 타입 | 제약 조건 | 설명 |
| :--- | :--- | :--- | :--- |
| `id` | `BIGINT` | PK, GENERATED BY DEFAULT AS IDENTITY | 자동 증가 대화 ID |
| `user_id` | `UUID` | FK, References `profiles(id)` | 소유자 고유 ID |
| `role` | `TEXT` | CHECK (role IN ('user', 'assistant')), NOT NULL | 발화자 역할 |
| `message` | `TEXT` | NOT NULL | 대화 메시지 본문 |
| `created_at` | `TIMESTAMPTZ` | DEFAULT now(), NOT NULL | 대화 일시 |

---

### 3.5 `trade_proposals` (매매 제안 카드)

* **설명**: AI 챗봇이 시장을 분석한 후 사용자에게 추천하는 매매 제안 기록입니다.
* **동작 원리**:
  * 이 테이블의 상태(`status`)가 `PENDING`으로 추가되면, Supabase Realtime 기능이 이를 트리거하여 프론트엔드 대시보드 챗봇 영역에 매매 승인/반대 카드를 실시간으로 렌더링합니다.
  * 사용자가 승인하면 백엔드는 주문 전 검증을 다시 수행하고, Toss 주문 생성 API 호출 시 `client_order_id`를 `clientOrderId`로 전달합니다.

| 컬럼명 | 데이터 타입 | 제약 조건 | 설명 |
| :--- | :--- | :--- | :--- |
| `id` | `UUID` | PK, DEFAULT gen_random_uuid() | 제안 고유 ID |
| `user_id` | `UUID` | FK, References `profiles(id)` | 대상 사용자 ID |
| `exchange` | `TEXT` | CHECK (exchange IN ('TOSS', 'COINONE', 'BINANCE', 'KIS')), NOT NULL | 브로커/거래소 구분 |
| `asset_type` | `TEXT` | CHECK (asset_type IN ('CRYPTO', 'STOCK')), NOT NULL | 자산 유형 |
| `ticker` | `TEXT` | NOT NULL | 내부 종목 코드 |
| `symbol` | `TEXT` | - | Toss API 호출용 종목 심볼 |
| `side` | `TEXT` | CHECK (side IN ('BUY', 'SELL')), NOT NULL | 거래 구분 |
| `price` | `NUMERIC` | - | 제안 단가. 시장가 또는 금액 주문은 NULL 가능 |
| `volume` | `NUMERIC` | - | 주문 수량. Toss `quantity`와 매핑 |
| `order_amount` | `NUMERIC` | - | Toss US MARKET 금액 기반 주문 금액 |
| `ord_type` | `TEXT` | CHECK (ord_type IN ('LIMIT', 'MARKET')), NOT NULL | 내부 주문 유형. Toss `orderType`과 매핑 |
| `time_in_force` | `TEXT` | CHECK (time_in_force IN ('DAY', 'CLS')), DEFAULT 'DAY' | Toss 주문 유효 조건 |
| `market_country` | `TEXT` | CHECK (market_country IN ('KR', 'US')) | Toss 시장 국가 |
| `currency` | `TEXT` | CHECK (currency IN ('KRW', 'USD')) | 거래 통화 |
| `client_order_id` | `TEXT` | UNIQUE | Toss 주문 생성 멱등성 키 |
| `external_order_id` | `TEXT` | - | Toss `orderId` |
| `status` | `TEXT` | CHECK (status IN ('PENDING', 'APPROVED', 'REJECTED', 'EXECUTED', 'FAILED')), DEFAULT 'PENDING' | 승인 상태 흐름 |
| `failure_reason` | `TEXT` | - | 주문 실행 실패 시 에러 사유 |
| `created_at` | `TIMESTAMPTZ` | DEFAULT now(), NOT NULL | 제안 생성 시각 |

---

### 3.6 `auto_trading_rules` (조건 감시 규칙)

* **설명**: 사용자가 정의한 실시간 조건식 자동 매매 감시 규칙을 관리합니다.
* **동작 원리**:
  * 백그라운드 워커가 `RUNNING` 상태의 행을 주기적으로 감시하여, 현재 시세가 손절률(`stop_loss_rate`) 또는 익절률(`target_profit_rate`)에 도달하면 자동 주문 제안을 생성하거나 사전 승인된 조건식에 한해 주문을 실행합니다.
  * Toss 주식 감시는 장 캘린더 API를 기준으로 폴링 주기를 조정합니다.

| 컬럼명 | 데이터 타입 | 제약 조건 | 설명 |
| :--- | :--- | :--- | :--- |
| `id` | `UUID` | PK, DEFAULT gen_random_uuid() | 규칙 고유 ID |
| `user_id` | `UUID` | FK, References `profiles(id)` | 소유자 고유 ID |
| `exchange` | `TEXT` | CHECK (exchange IN ('TOSS', 'COINONE', 'BINANCE', 'KIS')), NOT NULL | 브로커/거래소 구분 |
| `asset_type` | `TEXT` | CHECK (asset_type IN ('CRYPTO', 'STOCK')), NOT NULL | 자산 유형 |
| `ticker` | `TEXT` | NOT NULL | 내부 감시 종목코드 |
| `symbol` | `TEXT` | - | Toss API 호출용 종목 심볼 |
| `market_country` | `TEXT` | CHECK (market_country IN ('KR', 'US')) | 시장 국가 |
| `entry_price` | `NUMERIC` | NOT NULL | 규칙 진입 시점의 기준가 |
| `investment_amount` | `NUMERIC` | NOT NULL | 투자 원금 |
| `target_profit_rate` | `NUMERIC` | NOT NULL | 익절 목표 수익률 (%) |
| `stop_loss_rate` | `NUMERIC` | NOT NULL | 손절 제한 손실률 (%) |
| `status` | `TEXT` | CHECK (status IN ('RUNNING', 'COMPLETED', 'STOPPED')), DEFAULT 'RUNNING' | 감시 활성화 상태 |
| `created_at` | `TIMESTAMPTZ` | DEFAULT now(), NOT NULL | 규칙 등록 일시 |
| `updated_at` | `TIMESTAMPTZ` | DEFAULT now(), NOT NULL | 규칙 변경 일시 |

---

## 4. Toss 및 가상자산 마이그레이션 적용 완료 내역

목표 스키마를 실제 DB에 적용하기 위해 다음 마이그레이션이 반영되었습니다.

1. **멀티 브로커 지원 마이그레이션 (`20260623090000_update_user_api_keys_for_multi_broker.sql`)**
   - `user_api_keys` 테이블에 `toss_account_seq`, `toss_account_no`, `broker_env` 컬럼을 추가하여 Toss 연동을 지원하도록 구성했습니다.
   - `trade_proposals` 테이블에 `symbol`, `order_amount`, `time_in_force`, `market_country`, `currency`, `client_order_id`, `external_order_id` 컬럼을 추가하고, `client_order_id`에 대한 UNIQUE 제약을 부여해 주문 멱등성을 보장하도록 구성했습니다.
   - `auto_trading_rules` 테이블에 `symbol`, `market_country` 컬럼을 추가했습니다.
2. **코인원 및 바이낸스 대체 마이그레이션 (`20260623100000_replace_upbit_with_coinone_binance.sql`)**
   - 가상자산 거래소를 업비트(`UPBIT`)에서 코인원(`COINONE`) 및 바이낸스(`BINANCE`)로 변경함에 따라 `user_api_keys`, `trade_proposals`, `auto_trading_rules` 테이블의 `exchange` CHECK 제약을 `('COINONE', 'BINANCE', 'KIS', 'TOSS')`만 허용하도록 전면 교체 적용 완료했습니다.

---

## 5. 보안 정책 (Row Level Security, RLS)

모든 테이블은 데이터 보안을 강화하기 위해 **Row Level Security(RLS)**를 사용합니다.

* 사용자는 **오직 자신의 `user_id` 또는 `id`가 자신의 `auth.uid()`와 일치하는 행**에 대한 데이터에만 접근할 수 있습니다.
* Toss `client_id`, `client_secret`, access token, 계좌번호 원문은 프론트엔드에 노출하지 않습니다.
* 백엔드만 암호화된 인증 정보를 복호화할 수 있으며, 복호화된 값은 로그에 기록하지 않습니다.
* `trade_proposals.failure_reason`에는 민감정보를 저장하지 않고 Toss `requestId`, 에러 코드, 사용자 노출 가능한 메시지만 기록합니다.
* 데이터베이스 단에서 사용자별 행을 완전히 격리하여 멀티 테넌시 안정성을 보장합니다.

---

## 6. 향후 토큰 캐시 DB화 및 Upsert 설계 로드맵

현재 로컬 파일 시스템 캐시(`.toss_token_cache.json` 및 `.kis_token_cache.json`)로 관리 중인 OAuth 2.0 Access Token은 향후 클라우드 및 다중 서버(Scale-out) 배포 시 동기화와 영속성 확보를 위해 다음과 같은 DB 기반의 **Upsert(업서트) 패턴**으로 전환하여 고도화합니다.

### 6.1 목표 스키마 설계 (`token_caches` 신설)

```mermaid
erDiagram
    token_caches {
        uuid id PK "기본키"
        string exchange "거래소 (TOSS | KIS)"
        string broker_env "브로커 환경 (MOCK | REAL)"
        string encrypted_access_token "암호화된 Access Token"
        timestamp expired_at "토큰 만료 일시"
        timestamp updated_at "갱신 일시"
    }
```

#### 테이블 명세 (`token_caches`)

| 컬럼명 | 데이터 타입 | 제약 조건 | 설명 |
| :--- | :--- | :--- | :--- |
| `id` | `UUID` | PK, DEFAULT gen_random_uuid() | 고유 식별자 |
| `exchange` | `TEXT` | CHECK (exchange IN ('TOSS', 'KIS')), NOT NULL | 거래소 구분 (현재 토큰 기반 거래소만 대상) |
| `broker_env` | `TEXT` | CHECK (broker_env IN ('MOCK', 'REAL')), DEFAULT 'REAL' | 거래 환경 구분 |
| `encrypted_access_token` | `TEXT` | NOT NULL | AES-256 GCM으로 양방향 암호화된 토큰 원문 |
| `expired_at` | `TIMESTAMPTZ` | NOT NULL | 토큰의 실제 유효기간 만료 시각 |
| `updated_at` | `TIMESTAMPTZ` | DEFAULT now(), NOT NULL | 마지막 업데이트 시각 |

* **유니크 제약 (Unique Constraint)**:
  * `UNIQUE (exchange, broker_env)` 제약을 생성하여, 동일 거래소의 동일 실행 환경에 대해서는 **항상 테이블 내에 오직 1개의 행만 유지**되도록 제약합니다.

### 6.2 데이터 수명 주기 및 Upsert 동작 흐름

1. **토큰 조회**:
   * 백엔드 API 요청 시 `token_caches`에서 `exchange`와 `broker_env`에 매칭되는 데이터를 SELECT합니다.
   * `expired_at`이 현재 시간보다 전이면 만료된 것으로 판정하여 재발급 프로세스를 시작합니다.
2. **토큰 갱신 및 Upsert 실행**:
   * 토큰이 만료되었거나 없을 경우, 해당 거래소 API를 통해 새로운 토큰을 발급받고 `CryptoHelper`로 암호화합니다.
   * 저장 시 Postgres의 `ON CONFLICT (exchange, broker_env) DO UPDATE` 구문(Upsert)을 사용하여 기존 토큰 레코드를 덮어씁니다:
     ```sql
     INSERT INTO public.token_caches (exchange, broker_env, encrypted_access_token, expired_at, updated_at)
     VALUES ('TOSS', 'REAL', 'encrypted_value_here', '2026-06-24 14:24:31+09', now())
     ON CONFLICT (exchange, broker_env)
     DO UPDATE SET 
       encrypted_access_token = EXCLUDED.encrypted_access_token,
       expired_at = EXCLUDED.expired_at,
       updated_at = EXCLUDED.updated_at;
     ```
   * 이 방식을 통해 DB 내 데이터가 무한히 누적되는 문제를 방지하고, 별도의 클린업 쿼리 없이 **테이블 전체 크기를 최소화(최대 4개 행 이내)**하여 극단적인 쿼리 성능 향상을 꾀합니다.
3. **로컬 파일 클린업**:
   * DB 캐시 테이블 원격 배포 및 코드 적용 완료 시점 즉시, 로컬 디렉토리의 `.toss_token_cache.json` 및 `.kis_token_cache.json` 파일을 **영구 삭제(rm)**하고 `.gitignore` 항목을 정리합니다.

