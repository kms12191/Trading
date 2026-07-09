# AI 개발 에이전트를 위한 Toss 메인 트레이딩 MVP 프로젝트 지침서 (agents.md)

본 문서는 다른 AI 코딩 어시스턴트나 에이전트가 본 프로젝트의 맥락을 즉각적으로 이해하고, 일관된 설계 사상과 제약 조건을 준수하며 개발할 수 있도록 안내하는 시스템 가이드입니다.

이 프로젝트를 수정하거나 새로운 코드를 작성할 때, 아래의 지침과 보안 규칙을 **반드시 최우선적으로 준수**하십시오.

---

## 1. 프로젝트 핵심 맥락 (Project Context)

* **정의**: Toss증권 Open API 및 코인원 API를 주요 거래소로 사용하여 국내·미국 주식과 가상자산의 시세, 계좌, 보유자산, 주문 제안, 주문 실행 승인 흐름을 단일 챗봇 및 대시보드로 통합 관리하는 AI 기반 트레이딩 보조 시스템입니다.
* **브로커 우선순위**:
  * **주식 메인**: Toss증권 Open API (`TOSS`)
  * **주식 보류/레거시**: 한국투자증권 API (`KIS`)
  * **가상자산 메인**: 코인원 API (`COINONE`)
  * **가상자산 확장/선물**: 바이낸스 API (`BINANCE`, `BINANCE_UM_FUTURES`)
* **사용자 통제 원칙 (Human-in-the-Loop)**: AI가 시장을 독자적으로 판단하여 즉흥적으로 실거래 주문을 실행하는 것은 원천적으로 차단합니다.
  * 일반 매매 주문: **챗봇의 제안 -> 사전 검증 및 시뮬레이션 보고 -> 사용자의 명시적 승인 -> 실행**
  * 조건감시 자동/반자동 매도: 사용자가 명시적으로 설정한 **수치적 조건식(예: 익절 +5%, 손절 -3%)만** 백그라운드 워커가 기계적으로 감시합니다. `PROPOSAL` 모드는 매도 제안만 만들고, `AUTO` 모드는 사용자가 자동 실행을 선택한 규칙에 한해 주문을 전송합니다.
* **독립 격리 환경**: 실거래 자금이 움직이는 백엔드(Flask) 및 DB(Supabase)는 기존 웹 서비스 인프라와 완전히 분리하여 운영합니다.
* **현재 구현 기준**: 현재 저장소는 Vite React 프론트엔드, Flask 백엔드, Supabase DB 구조입니다. 문서와 코드 변경 시 실제 구현 상태를 기준으로 업데이트하며, 아직 구현되지 않은 모듈은 목표 구조로만 명시합니다.


---

## 2. 아키텍처 및 데이터 흐름 지침

```text
  [React Frontend] (Vite + Tailwind CSS)
         |
         +-- (1) Supabase SDK: 사용자 인증(Auth) & 승인 상태 실시간 구독(Realtime)
         +-- (2) REST API: Toss/KIS/코인원/바이낸스 시세·계좌 조회, 수동 매매, 조건감시 규칙 등록
         |
         v
  [Flask Backend] (API Gateway & Worker)
         |
         +-- [routes/home.py, keys.py, ml.py, news.py, disclosures.py, trade.py, transfer.py, admin_inquiries.py, chatbot.py, knowledge.py] : Blueprint 기반 API 라우트 레이어
         +-- [utils/crypto_helper.py, file_helpers.py] : 암호화 및 파일 처리 공통 유틸리티
         +-- [services/auth_service.py]                       : Authorization 헤더 디코딩
         +-- [services/supabase_client.py]                   : Supabase DB 및 작업 동기화
         +-- [services/home_service.py]                       : 대시보드 및 잔고 융합 헬퍼
         +-- [services/keys_service.py]                       : API 키 AES-256 GCM 암복호화 서비스
         +-- [services/token_cache_service.py]               : OAuth 토큰 Supabase DB 캐싱 서비스
         +-- [services/lock_service.py]                       : 분산 락(Distributed Lock) 컨텍스트 매니저
         +-- [services/exchange_client.py]                   : 거래소 추상화 베이스 클래스(ExchangeClient)
         +-- [services/toss_client.py]                        : Toss Open API 메인 주식 클라이언트
         +-- [services/kis_client.py]                         : KIS 레거시/보류 주식 클라이언트
         +-- [services/coinone_client.py]                     : 코인원 메인 가상자산 클라이언트
         +-- [services/binance_client.py]                     : 바이낸스 확장 가상자산 클라이언트
         +-- [services/upbit_client.py]                       : 업비트 보조 클라이언트(참고용)
         +-- [services/auto_trading_rule_engine.py]          : 조건감시 자동/반자동 매도 워커
         +-- [services/open_order_status_sync_service.py]   : 전체 사용자 미완료 주문 상태 동기화 워커
         +-- [services/broker_order_history_service.py]      : 브로커 주문 이력 동기화 서비스
         +-- [services/market_repository.py]                 : 시세 데이터 레포지토리
         +-- [services/market_snapshot_scheduler.py]         : 시세 스냅샷 백그라운드 스케줄러
         +-- [services/symbol_metadata.py]                   : 한글 종목명 ↔ 종목코드 매핑 유틸
         +-- [services/error_message_service.py]             : 사용자 친화 에러 메시지 표준화
         +-- [services/dart_analysis_service.py]             : DART 공시 AI 분석 서비스 (Gemini 다중 모델 Failover)
         +-- [services/dart_ingest.py]                        : 공시 수집 파이프라인
         +-- [services/dart_repository.py]                   : 공시 DB 레포지토리
         +-- [services/news_ingest.py]                        : 뉴스 수집 파이프라인
         +-- [services/news_query_planner.py]                : 뉴스 검색 쿼리 플래너
         +-- [services/news_repository.py]                   : 뉴스 DB 레포지토리
         +-- [services/news_summary_service.py]              : 뉴스 AI 요약 서비스
         +-- [services/obsidian_service.py]                  : Obsidian Markdown frontmatter/title/hash 정규화 서비스
         +-- [services/knowledge_repository.py]              : 사용자 지식 노트, 자동메모리, 지식 chunk Supabase 저장/조회 서비스
         +-- [services/knowledge_chunk_service.py]           : 저장된 노트 본문을 RAG/embedding 대상 chunk로 분할하는 서비스
         +-- [services/ml_model_service.py]                  : ML 모델 정보 조회 및 실험 리포트 기동
         +-- [services/ml_scheduler.py]                       : 백그라운드 스레드 기반 스케줄러 워커
         +-- [services/ml_automation_service.py]             : ML 자동화 프리셋 정의 및 실행 서비스
         +-- [services/ml_job_service.py]                     : ML 작업(수집/학습/백테스트) 실행기
         +-- [services/ml_registry_service.py]               : ML 모델 레지스트리 통합 관리 서비스
         +-- [services/ml_split_model_promotion_service.py] : KR/US 분리 모델 승격 검증 서비스
         |
         v
  [Supabase DB] & [External APIs] (Toss / Coinone / Binance / Tavily News / KIS API)
```

### 2.1 에이전트 코딩 시 준수할 통신 규칙

1. **상태 동기화**: 매매 제안의 생성은 Flask 백엔드가 수행하여 Supabase `trade_proposals` 테이블에 `PENDING`으로 인서트하고, React 프론트엔드는 Supabase Realtime 구독 기능을 통해 이 이벤트를 캐치하여 챗봇 창에 승인 카드를 즉시 렌더링해야 합니다.
2. **Toss 인증 및 계좌 흐름**:
   * Toss증권 Open API는 OAuth 2.0 Client Credentials Grant 방식을 사용합니다.
   * `/oauth2/token` 엔드포인트는 `Authorization` 헤더 없이 호출하며, 요청 본문은 `application/x-www-form-urlencoded` 형식입니다.
   * 계좌 기반 API 호출 전 `GET /api/v1/accounts`를 먼저 호출해 `accountSeq`를 확보한 후, 이후 모든 보유자산 및 주문 관련 API에 `X-Tossinvest-Account: {accountSeq}` 헤더를 필수 전송합니다.
3. **코인원(Coinone) 인증 및 통신 규칙**:
   * 코인원 Private API v2.1은 `Access Token`과 `Secret Key`를 사용한 HMAC-SHA512 서명 방식을 사용합니다.
   * 요청 본문 JSON 데이터를 Base64 인코딩하여 `X-COINONE-PAYLOAD` 헤더에 담고, 이를 Secret Key로 HMAC-SHA512 서명(Hex 소문자 변환)을 수행해 `X-COINONE-SIGNATURE` 헤더에 담아 전송합니다.
   * nonce값은 매 요청마다 중복되지 않는 고유한 UUID string 형식을 포함시킵니다.
4. **바이낸스(Binance) 인증 및 통신 규칙**:
   * 바이낸스는 `API Key`와 `Secret Key`를 사용하며, 서명된 요청에는 HMAC-SHA256 알고리즘을 적용한 `signature` 쿼리 파라미터가 요구됩니다.
   * 모든 요청 헤더에는 `X-MBX-APIKEY: {api_key}`를 필수로 전송합니다.
5. **API Key 보안**:
   * Toss, KIS, 코인원, 바이낸스의 모든 API 비밀 정보(Secret Key, AppSecret 등)는 프론트엔드로 절대 전달하지 않습니다.
   * 사용자의 API 인증 정보는 DB에 평문으로 저장하지 않고, 반드시 백엔드 내부의 대칭키(AES-256 GCM) 암호화 기능을 거쳐 저장합니다.
6. **에러 응답 처리**:
   * 거래소 API 에러 시 `trade_proposals.status`를 `FAILED`로 변경하고 `failure_reason`에 에러 정보와 에러 코드를 기록하여 추적 가능하게 관리합니다.
   * 사용자가 직접 보는 API 응답에는 원문 예외(`str(e)`, 거래소 raw payload, stack trace)를 그대로 노출하지 말고, 반드시 `backend/services/error_message_service.py`의 `format_error_payload()`를 사용해 `message`, `error.title`, `error.action`, `error.code`, `error.raw_message` 구조로 반환하십시오.
   * 거래소/외부 API 신규 에러 코드를 발견하면 해당 코드의 의미, 사용자에게 보여줄 원인, 사용자가 다음에 해야 할 행동을 `ERROR_GUIDES` 또는 `KEYWORD_GUIDES`에 추가한 뒤 라우트에서 재사용하십시오.
   * 프론트엔드는 실패 응답 표시 시 `frontend/src/lib/apiError.js`의 `getApiErrorMessage()` 또는 `buildApiErrorText()`를 우선 사용하고, 화면에는 `error.title`과 `error.action`을 중심으로 표시해야 합니다. 원문 로그는 디버깅용으로만 보존하고 주요 사용자 문구로 사용하지 않습니다.
   * 에러 메시지는 "실패했습니다"에서 끝내지 말고, 사용자가 이해할 수 있는 원인과 다음 행동을 포함해야 합니다. 예: "코인원 API 출금주소록 등록이 필요합니다. 코인원 Open API > API 출금주소록에서 주소와 Destination Tag/Memo를 등록하고 추가 채널 인증을 완료한 뒤 다시 시도하세요."

---

## 3. 핵심 데이터 스키마 및 디자인 참조

AI 에이전트는 데이터 변경이나 조회 쿼리를 작성할 때 다음 핵심 테이블 구조를 준수해야 합니다. 자세한 명세는 [database_specification.md](database_specification.md)를 참고하십시오. UI/UX 구현 시 [design.md](design.md)에 기술된 스타일 규격을 준수해야 합니다.

* `profiles`: 사용자 기본 정보 (Supabase Auth와 auth.uid() 연동)
* `user_api_keys`: Toss/KIS/Coinone/Binance 인증 정보를 암호화 저장합니다. Toss는 `client_id`, `client_secret`, `accountSeq` 중심으로 관리합니다.
* `paper_portfolios`: 페이퍼 트레이딩 및 시뮬레이션용 가상 잔고와 보유 종목을 저장합니다.

* `trade_proposals`: 챗봇이 제안하고 사용자의 승인을 기다리는 주문 내역입니다.
* `auto_trading_rules`: 사용자가 정의한 익절/손절 조건감시 규칙, 실행 모드(`PROPOSAL`/`AUTO`), 트리거 결과, 자동매도 결과를 저장합니다.
* `chat_history`: 사용자와 AI 트레이딩 챗봇 간의 대화 이력을 저장합니다.
* `user_knowledge_notes`: 앱 내부 투자노트 및 Obsidian 플러그인에서 동기화한 Markdown 원문과 frontmatter, content hash를 사용자별로 저장합니다.
* `user_memory_facts`: 챗봇/앱 행동 로그에서 추출한 관심종목, 반복실수, 리스크 성향, 답변 선호도 등의 자동메모리 fact를 저장합니다.
* `knowledge_chunks`: Obsidian/앱 노트, 자동메모리, 뉴스, 공시 등을 RAG 검색에 사용할 수 있도록 chunk 단위로 저장합니다. 1차 구현은 `embedding_status=PENDING` 상태까지 생성하며, 실제 vector embedding 및 검색은 후속 담당 영역입니다.
* `design.md`: 프론트엔드 UI 컴포넌트, 색상, 타이포그래피, 마진 등 공통 스타일 가이드라인 정보입니다.

---

## 4. 단계별 구현 로드맵 및 개발 범위 (Roadmap)

작성 중인 코드의 기능 수준이 현재 프로젝트의 어느 Phase에 속하는지 명확히 인식하고 기능을 구현해야 합니다.

### Phase 1: Toss 정보 조회 및 뉴스 RAG 챗봇

* **구현 범위**: 실거래 주문/자동화 제외. Toss 시세, 호가, 체결, 캔들, 종목 정보, 종목 유의사항, 환율, 장 캘린더, 계좌 목록, 보유자산 조회 API와 Tavily 검색 API를 결합한 최신 뉴스 RAG 프롬프트 체인을 구축합니다.
* **Obsidian/자동메모리 현재 구현 범위**:
  * 내부 시연용 Obsidian 플러그인은 `obsidian-plugin/ai-trading-memory`에 위치합니다.
  * 플러그인은 `POST /api/knowledge/obsidian/sync-note`로 현재 Markdown 노트를 Flask에 동기화합니다.
  * Flask는 `user_knowledge_notes`에 원문을 저장하고, 같은 요청에서 `knowledge_chunks`에 검색용 chunk를 `embedding_status=PENDING`으로 생성합니다.
  * `GET /api/knowledge/obsidian/auto-memory`는 `user_memory_facts`를 읽어 Obsidian 자동메모리 marker 영역에 반영할 배열을 반환합니다.
  * Obsidian은 필수 사용자 경로가 아니라 고급 사용자용 외부 Markdown 편집/소유 옵션입니다. 일반 사용자의 기본 메모리 저장소는 앱 DB와 자동메모리 테이블입니다.
* **마이그레이션 적용 순서**:
  * `supabase/migrations/20260708110000_create_user_knowledge_memory.sql`
  * `supabase/migrations/20260708113000_create_knowledge_chunks.sql`
  * 두 번째 migration 적용 전에는 Obsidian 노트 동기화가 `knowledge_chunks` 테이블 부재로 실패할 수 있습니다.
* **Toss API 범위**:
  * Market Data: `/api/v1/prices`, `/api/v1/orderbook`, `/api/v1/trades`, `/api/v1/candles`, `/api/v1/price-limits`
  * Stock Info: `/api/v1/stocks`, `/api/v1/stocks/{symbol}/warnings`
  * Market Info: `/api/v1/exchange-rate`, `/api/v1/market-calendar/KR`, `/api/v1/market-calendar/US`
  * Account/Asset: `/api/v1/accounts`, `/api/v1/holdings`
* **코드 예외**: 실거래 주문 API 호출은 이 단계에서 절대 활성화하지 않습니다.

### Phase 2: Toss 주문 시뮬레이션 & 페이퍼 트레이딩

* **구현 범위**: Toss 주문 요청 스키마를 기반으로 주문 전 검증, 예상 비용, 가능 수량, 가능 금액, 페이퍼 체결 엔진을 구현합니다.
* **검증 모듈**:
  * `GET /api/v1/buying-power`
  * `GET /api/v1/sellable-quantity`
  * `GET /api/v1/commissions`
  * `GET /api/v1/stocks/{symbol}/warnings`
* **체결 모듈**: `paper_portfolios` 테이블을 업데이트하는 가상 매수/매도 로직을 설계하여 실거래 리스크를 회피합니다.

### Phase 1.5: LightGBM 사전학습 신호 엔진

* **구현 범위**: LLM이 직접 상승/하락을 단정하지 않도록, 가격·거래량·기술지표 기반 LightGBM 모델을 오프라인에서 사전학습합니다.
* **모델 분리 원칙**:
  * 주식 모델과 코인 모델은 시장 구조가 다르므로 반드시 별도 모델로 관리합니다.
  * 통합 주식 모델 (현재 서빙): `lgbm_stock_signal_v11`
  * 국내주식 전용 모델 (현재 서빙): `lgbm_kr_stock_signal_v1` — KIS 데이터 기반, STOCK_KR asset_type 라우팅
  * 해외주식 전용 모델 (현재 서빙): `lgbm_us_stock_signal_v1` — Toss 데이터 기반, STOCK_US asset_type 라우팅
  * 코인 모델 (현재 서빙): `lgbm_crypto_signal_v9`
  * 심볼 분류 규칙: 숫자 심볼(예: 005930)은 STOCK_KR, 영문 심볼(예: AAPL)은 STOCK_US로 자동 분기.
* **코인 예측 기준**:
  * 코인은 24시간 거래되므로 `3거래일 뒤` 기준보다 `1시간`, `4시간`, `24시간` 기준 예측을 우선합니다.
  * 초기 MVP 코인 라벨은 `4시간 뒤 수익률이 +1.0% 이상이면 상승`, `4시간 뒤 수익률이 -1.5% 이하이면 하락 위험`으로 시작합니다.
  * 코인 피처에는 5분·15분·1시간·4시간·24시간 수익률, 거래량 평균 대비 비율, 변동성, RSI, BTC/ETH 동조 피처, 코인원-바이낸스 가격 차이, 김치프리미엄 후보 값을 포함할 수 있습니다.
* **Optuna HPO (하이퍼파라미터 최적화) 도구**:
  * `ml/src/tune_hyperparameters.py`를 활용하여 Optuna 기반 HPO 튜닝을 기동하고, 목적 함수(Objective)를 정의하여 ROC AUC 또는 Excess Return을 최적화하는 파라미터 조합을 탐색합니다.
* **자동 스케줄러 및 ML 자동화 서비스**:
  * `ml_automation_service.py`와 `ml_scheduler.py`를 통해 백그라운드에서 캔들 데이터 자동 수집 및 학습 파이프라인을 기동합니다.
  * 주식은 평일 장 마감 후(16:30 ~ 18:30), 코인은 4시간 단위로 데이터셋 추출 및 모델 학습 스케줄링이 백그라운드 스레드에서 주기적으로 가동됩니다.
  * 수집 실행 일자(`last_stock_date`)는 `stock_automation_state.json` 파일에 영속화하여 서버 재시작 시에도 중복 수집을 방지합니다.
  * 자동화 프리셋: 코인(`crypto-v9-full`), 주식(`stock-v11-full`), 국내주식(`kr-stock-v1-full`), 해외주식(`us-stock-v1-full`).
* **Stochastic/OBV 피처 도입 (v11/v9 모델)**:
  * 현재 서빙 중인 v11(주식), v9(코인) 학습 설정은 전통적 이동평균 외에 Stochastic Oscillator, OBV(On-Balance Volume) 등 기술적 보조지표 피처를 강화하여 모델 예측력을 고도화합니다.
* **모델 레지스트리 및 승격 검증 (Promotion Check)**:
  * `ml_registry_service.py`를 통해 디스크 파일과 DB(`ml_model_registry`)에 모델 상태를 통합 관리합니다.
  * 절대 기준(검증 CV ROC AUC, MDD, excess return)과 상대 기준(serving 모델 대비 성능 하락 한계)을 검증하여 통과한 모델만 서비스(`Serving`) 버전으로 승격시키며, 기준 미달 시 강제 승격(`force=true`)을 제외하고는 차단합니다.
  * 국내/해외 분리 모델은 `ml_split_model_promotion_service.py`를 통해 STOCK_KR / STOCK_US 그룹별로 독립적으로 승격 검증합니다.
  * `model_registry.json`에 asset_type별 그룹(stock, crypto, kr_stock, us_stock)으로 구분하여 모델 메타데이터를 저장하며, `ml_model_service.py`의 `resolve_active_model_selection`이 이를 로드하여 서빙 모델을 결정합니다.
* **실행 환경 원칙**:
  * 초기 개발과 Flask 연동 검증은 맥북 M2 로컬 Python 환경에서 수행합니다.
  * Colab은 대량 분봉 데이터 학습, 반복 튜닝, 팀 공유가 필요할 때 학습 전용 보조 환경으로 사용합니다.
  * GPU는 LightGBM 초기 MVP에 필수로 요구하지 않습니다.
* **안전 원칙**:
  * 모델 결과는 매매 실행 명령이 아니라 참고 신호와 리스크 점수입니다.
  * 챗봇은 모델 점수의 근거를 설명하고, 모든 주문은 기존 Human-in-the-Loop 승인 절차를 반드시 거칩니다.
  * 사용자 개인 계좌 데이터, 주문 이력, API Key는 모델 학습 데이터로 사용하지 않습니다.

### Phase 3: Toss 실거래 반자동 매매 (소액 제한)

* **구현 범위**: 사용자가 승인 버튼을 누르면 Toss 주문 API를 호출하되, 보안과 리스크 하드캡을 적용합니다.
* **코드 필수 안전 조항**:
  * 1회 주문 한도 하드캡 검증 코드를 삽입합니다. 기본 한도는 서비스 정책으로 별도 상수화하며, 초기값은 10만 원 이하를 권장합니다.
  * Toss 주문 생성 시 서버가 `clientOrderId`를 생성하여 멱등성 키로 사용합니다.
  * `clientOrderId`는 Toss 문서 기준 최대 36자이며 영숫자, `-`, `_`만 허용합니다.
  * Toss 문서 기준 `clientOrderId` 멱등성 키는 10분간 유효하므로, 동일 승인 요청의 중복 실행을 DB와 API 양쪽에서 방어합니다.
  * 주문 생성 전 `buying-power`, `sellable-quantity`, `commissions`, `stocks/{symbol}/warnings`를 조회해 사용자에게 사전 검증 결과를 제시합니다.
  * Toss 문서상 1억 원 이상 주문에는 `confirmHighValueOrder`가 필요하지만, 본 서비스의 내부 하드캡이 우선 적용되어야 합니다.

### Phase 4: 조건식 자동/반자동 트레이딩

* **구현 범위**: 사용자가 기지정한 가격 또는 수익률 조건 도달 시 자동 주문 제안을 생성하거나, 사용자가 `AUTO` 실행을 명시 선택한 조건식에 한해 주문을 실행하는 백그라운드 워커를 구축합니다.
* **현재 구현 기준**: `backend/services/auto_trading_rule_engine.py`가 Supabase `auto_trading_rules`의 `RUNNING` 규칙을 조회하고, 조건 도달 시 `trade_proposals`에 매도 제안 또는 자동 주문 결과를 기록합니다.
* **구조적 제약**: Flask의 웹 서비스 웹훅/API 스레드와 별도 스레드 또는 별도 프로세스로 완전히 격리하여 감시 엔진을 구동합니다. 기본 운영은 `backend/worker.py` 단독 프로세스이며, `SCHEDULER_RUN_IN_GATEWAY=true`일 때만 gateway 내부 기동을 허용합니다.
* **안전 정책**:
  * `execution_mode=PROPOSAL`은 조건 도달 시 매도 제안만 생성합니다.
  * `execution_mode=AUTO`는 조건 도달 시 워커가 매도 주문을 직접 전송합니다.
  * 실거래(`REAL`) 자동매도 추정 원화 금액이 내부 1회 한도 10만 원을 초과하면 자동 주문 대신 제안 생성으로 우회합니다.
  * Binance USD-M 선물 자동매도는 롱 포지션 청산(`BOTH + reduceOnly SELL`) 중심으로 취급합니다. 숏 포지션 청산은 매수 청산이므로 별도 자동청산 정책이 필요합니다.
* **최적화**:
  * 국내 주식은 `GET /api/v1/market-calendar/KR`의 장 운영 정보를 사용합니다.
  * 미국 주식은 `GET /api/v1/market-calendar/US`의 데이마켓, 프리마켓, 정규장, 애프터마켓 정보를 사용합니다.
  * 장 운영 시간이 아닌 경우 잦은 API 폴링을 중단하고 긴 주기로 조회합니다.

---

## 5. AI 에이전트를 위한 코드 구현 가이드라인

1. **거래소 추상화 클래스 준수**: 새로운 브로커나 자산이 추가될 경우 `ExchangeClient` 추상 클래스를 상속받아 `get_price`, `get_balance`, `place_order`, `get_order_status`를 오버라이딩하여 구현하십시오. Toss 금액 주문(`orderAmount`)처럼 기존 인터페이스로 표현이 부족한 경우, 호출부와 선언부를 함께 수정하고 전수 검사하십시오.
2. **Toss 및 코인원/바이낸스 클라이언트 우선 구현**:
   * 신규 주식 기능은 `toss_client.py`를 우선 구현 대상으로 삼습니다.
   * `kis_client.py`는 기존 구현이 있으나 레거시/보류 클라이언트로 취급합니다.
   * `coinone_client.py`를 가상자산 메인 클라이언트로 신설하고, `binance_client.py`를 가상자산 확장 클라이언트로 구현합니다.
3. **LangChain 에이전트의 툴(Tool) 정의**:
   * 챗봇이 시세를 묻거나 뉴스 흐름 분석을 요청받을 때, `get_price`, `get_holdings`, `search_news`, `get_stock_warnings`, `get_market_calendar` 도구를 호출할 수 있도록 명확한 Type Hint와 docstring을 명시하여 LangChain 에이전트에 바인딩하십시오.
4. **LightGBM 모델 연동 규칙**:
   * 신규 예측 모델은 `ml/` 디렉토리에서 먼저 사전학습 및 백테스트를 완료한 뒤 백엔드에 탑재합니다.
   * Flask 백엔드는 저장된 모델 파일을 읽어 예측만 수행하며, 서비스 요청 중 임의 재학습을 수행하지 않습니다.
   * 주식과 코인은 `asset_type`과 `model_version`을 기준으로 별도 모델 파일을 로드합니다.
   * 모델 출력은 `up_probability`, `risk_probability`, `signal_score`, `model_version` 형태로 표준화합니다.
   * 모델 점수는 주문 실행 근거가 아니라 챗봇 설명과 매매 제안 후보 선별에만 사용합니다.
5. **오류 대응 및 로깅**:
   * Toss API의 응답 지연이나 에러 발생 시, `trade_proposals` 테이블의 `status`를 `FAILED`로 변경하고 `failure_reason` 컬럼에 반드시 원인을 상세히 기록하도록 코딩하십시오.
   * 신규 라우트 또는 기존 라우트의 `except Exception` 응답을 추가/수정할 때는 `jsonify({"success": False, "message": f"...{str(e)}"})` 형태를 금지합니다. 사용자 화면에 노출될 수 있는 API는 `format_error_payload(e, "작업명 실패", exchange=exchange)`를 사용해 표준 에러 payload로 반환하십시오.
   * 사용자 친화 에러 문구는 다음 3요소를 포함해야 합니다: `무슨 일이 발생했는지`, `왜 발생했을 가능성이 높은지`, `사용자가 다음에 무엇을 해야 하는지`.
   * 거래소/브로커별 에러 코드는 원문 코드를 숨기지 말고 `error.code`와 `error.raw_message`에 보존하되, 화면 기본 문구는 한국어 안내형 문장으로 작성하십시오.
   * 프론트엔드에서 API 실패를 처리할 때는 `payload.message`만 직접 출력하지 말고 `getApiErrorMessage()`를 거쳐 `title`과 `detail/action`을 함께 보여주십시오.
   * 관리자/ML 작업처럼 원문 로그가 필요한 화면도 사용자 기본 문구는 친화적으로 유지하고, 상세 원문은 접힘 영역, 작업 로그, `raw_message` 등 디버깅 맥락에만 표시하십시오.
6. **디자인 시스템 엄격 준수**: UI를 개발할 때 [design.md](design.md)에 명시된 Obsidian Navy 배경, JetBrains Mono 폰트 사용처, Glassmorphism, 2px Cyan 매매 승인 카드 왼쪽 강조 테두리 등 모든 스타일 토큰을 정교하게 적용하십시오.
7. **모바일 우선 반응형 UI 필수 적용**:
   * 모든 신규 페이지, 컴포넌트, 모달, 카드, 표, 차트, 폼, 버튼 그룹은 **모바일 화면을 기본 기준으로 먼저 설계**하고 `sm`, `md`, `lg`, `xl` 브레이크포인트로 확장하십시오.
   * 최소 검증 뷰포트는 모바일 `360px`, 모바일 대형 `430px`, 태블릿 `768px`, 데스크톱 `1280px`입니다.
   * 가로 스크롤은 데이터 테이블, 차트, 코드 블록처럼 구조적으로 필요한 경우에만 허용하고, 일반 레이아웃에서는 발생하지 않도록 `min-w`, `max-w`, `overflow`, `grid`, `flex-wrap`을 반드시 점검하십시오.
   * 사이드바, 탭, 네비게이션, 관리자 도구 화면은 모바일에서 접힘/슬라이드/가로 스크롤 탭 등으로 전환되어야 하며, 주요 버튼은 엄지 조작이 가능한 충분한 터치 영역을 가져야 합니다.
   * 차트와 대시보드 카드 영역은 고정 폭에 의존하지 말고 `w-full`, 반응형 grid, `aspect-ratio`, `min-h`를 사용해 작은 화면에서도 깨지지 않게 구성하십시오.
   * 긴 종목명, 이메일, 파일 경로, 에러 메시지, API 응답 텍스트는 `break-words`, `break-all`, `truncate`, `line-clamp` 등을 상황에 맞게 적용해 컨테이너 밖으로 넘치지 않게 처리하십시오.
   * UI 작업 완료 전에는 최소한 브라우저 개발자 도구 또는 Playwright/스크린샷 검증으로 모바일 폭에서 버튼, 입력창, 카드, 헤더, 하단 콘텐츠가 겹치지 않는지 확인하십시오.
8. **Dead Code 지양**: `console.log`, 사용되지 않는 라이브러리 임포트, 임시 주석 처리된 코드는 발견 즉시 삭제하고 정돈된 프로덕션 품질의 코드를 생산하십시오.
9. **주석 한글화 원칙**: 코드 내부의 설명 주석 및 함수/클래스 개발 관련 설명글은 반드시 한국어로 작성하여 직관적인 코드 가독성을 보장하십시오. 영문 주석은 외부 API 필드명이나 표준 용어 인용이 필요한 경우에만 사용합니다.
10. **관련 문서 최신화**: 테이블 구조 신설/변경, 라우트 신설, 신규 컴포넌체 추가, 디렉토리 구조 변경 등 작업이 성공적으로 완료되면, 실제 코드를 바탕으로 연관된 프로젝트 사양 문서(예: `database_specification.md`, `project_structure.md` 등)를 누락 없이 최신 정보로 갱신하여 문서 일치성을 유지하십시오.
11. **통합 금융 차트 및 시세 API 어댑터 규칙**:
   * 시세 캔들 차트는 **TradingView Lightweight Charts** 라이브러리를 단일 리액트 컴포넌트로 재사용하여 표현하십시오.
   * 프론트엔드가 개별 거래소 API에 직접 의존하지 않고, 백엔드 단일 API 엔드포인트(`GET /api/chart/candles?exchange={EXCHANGE}&symbol={SYMBOL}&interval={INTERVAL}`)를 통해 시세를 호출하도록 하십시오.
   * 백엔드(Flask)에서는 어댑터(Adapter) 패턴을 구현하여, 호출된 거래소 클라이언트(Toss, KIS, Coinone, Binance)의 상이한 날짜/가격 포맷 데이터를 Lightweight Charts가 규정하는 `{ time, open, high, low, close }` 공통 포맷으로 매핑하여 반환해야 합니다.
   * 불필요한 외부 호출을 방지하고 차트 리로딩 속도를 극대화하기 위해, 백엔드 레벨에서 단기 시세 데이터 캐싱(Caching)을 필수로 탑재하십시오.
12. **모의투자 한도 및 실거래 하드캡 분기**:
   * 실거래 주문 한도(예: 1회 주문 한도 10만 원 이하) 가드 캡은 실제 주문 거래가 이루어지는 실거래(`REAL`) 환경에서만 엄격히 활성화해야 합니다.
   * 모의투자 테스트 및 시뮬레이션(`MOCK` 환경) 모드일 때는 개발/테스트의 유연성과 빠른 검증을 위해 주문 한도 제한 코드를 우회(분기 처리)하도록 설계해야 합니다.
13. **실시간 호가 및 체결 API의 동적 폴백(Fallback) 보정**:
   * 상세 페이지 진입 시 차트와 호가/체결 조회가 비동기로 동시 가동되는 레이스 컨디션으로 인해, 극초기에는 시세 캐시(`CANDLE_CACHE`)가 없거나 불완전하여 15만원 등 엉뚱한 Mock 가격이 노출될 위험이 있습니다.
   * 캐시가 만료되었거나 누락된 상태에서 호가/체결 요청이 들어오면, 즉각 거래소 API(`client.get_price`)를 동기적으로 1회 백업 호출하여 기준 가격(`base_price`)을 동적 보정하는 이중 안전장치를 필수 탑재해야 합니다.
14. **한글명 종목 매핑 및 실시간 자동완성 검색**:
   * 사용자가 대시보드에서 종목 코드뿐만 아니라 한글 종목명(예: "삼성전자", "하이닉스")으로 빠르게 검색할 수 있도록, 백엔드의 `/api/symbol/lookup` 및 `/api/symbol/search`와 `symbol_metadata.py`를 활용해 한글명을 종목코드로 자동 치환하는 구조를 확립해야 합니다.
   * 프론트엔드의 대시보드 퀵 검색창에 실시간 키 입력 추천 목록(자동완성 드롭다운 팝업)을 탑재하여 UX를 최적화하십시오.
15. **모의계좌 ON/OFF 토글 필터 연산 규칙**:
   * 사용자가 대시보드에서 "실거래 전용" vs "모의계좌 포함" 토글을 변경할 때 추가적인 API 호출을 발생시켜서는 안 되며, 이미 받아온 보유자산 목록(`rawBalances`)에서 `broker_env === 'MOCK'`인 자산을 제외하거나 병합하는 방식으로 O(1) 수준으로 즉시 재계산하여 렌더링해야 합니다.
   * `Dashboard.jsx`의 `mergeAccountBalances` 함수와 `AssetsTab.jsx` 컴포넌트 등 자산 집계 연산이 일어나는 모든 지점에서 이 토글 상태(`showMockAssets`)가 일관성 있게 적용되도록 프레임워크 코드를 유지하십시오.
16. **Toss 실시간 환율 Live API 연동 및 폴백 규칙**:
   * Toss 환율 API `/api/v1/exchange-rate` 호출 시 필수 파라미터인 `params={"baseCurrency": "USD", "quoteCurrency": "KRW"}`가 누락되면 `400 Bad Request` 에러를 반환하므로, 반드시 이 파라미터 조합을 전송하도록 코딩해야 합니다.
   * API 호출 실패 및 장애 상황을 대비해 `1500.0`원의 현실적인 폴백(Fallback) 값을 지정하고, 실시간 API 연동 상태를 사용자가 신뢰할 수 있게 UI 상에 Live 상태 배지와 함께 마크업해야 합니다.
17. **해외주식 수익률 백분율 스케일링 규칙**:
   * Toss 해외주식의 `profit_rate` 계산 식에 `* 100.0`을 곱하여 KIS(백분율 기준)와 일치시킴으로써 전체 해외주식 자산의 수익률 스케일링 통일성을 보장하십시오.
18. **스케줄러의 게이트웨이 독립 및 worker.py 분리**:
   * Flask 백엔드(`app.py`)는 다중 워커 프로세스 환경에서 스케줄러가 중복 기동되는 것을 피해야 합니다. `SCHEDULER_RUN_IN_GATEWAY=true` 설정이 없을 경우 `app.py` 내부에서의 스레드 기동을 엄격히 차단하며, 배포 및 무중단 스케줄링 운영 시에는 `backend/worker.py`를 별도의 단독 프로세스로 띄워 모든 백그라운드 스케줄러 스레드를 중앙 제어해야 합니다.
19. **분산 락(Distributed Lock)과 토큰 캐시 DB화 규칙**:
   * Gunicorn 다중 워커 및 개발자 로컬 분산 환경에서 뉴스 수집 및 ML 학습 자동화 루프가 중복 작동하지 않도록 `distributed_lock` 컨텍스트 매니저를 통해 실행 독점권을 획득해야 합니다.
   * 로컬 파일 시스템에 임시 저장되던 Toss/KIS OAuth 토큰은 파일 동기화 문제를 막기 위해 완전히 제거되었으므로, 모든 비즈니스 레이어에서는 `token_cache_service`를 거쳐 Supabase `token_caches` 테이블에 암호화 보관된 토큰을 읽고 써야(Upsert) 합니다.
20. **환경 변수 추가 시 .env.example 갱신 필수화**:
   * 새로운 기능 개발이나 스케줄러 도입 등으로 인해 백엔드(`backend/.env`) 혹은 프론트엔드(`frontend/.env`)에 환경 변수가 신규 추가되거나 변경될 경우, 반드시 루트 디렉토리의 `.env.example` 파일의 매칭되는 섹션에 변수명과 설명 및 교체 예시값(`replace-me`)을 작성하여 최신화해 두어야 합니다. 이는 신규 팀원 참여 및 다중 분산 협업 시의 실행 정합성을 담보하기 위함입니다.
21. **무조건적 보안 하드캡 및 Fail-Fast 설계 규칙 (보안 필수)**:
    * **암호화 키 Fail-Fast**: `ENCRYPTION_KEY`와 같은 대칭 키 복호화용 환경 변수가 빈 값이거나 누락되었을 경우, 코드에 절대 하드코딩된 기본값(Default)을 대안으로 제공하지 마십시오. 환경 변수가 확보되지 않으면 구동 즉시 강제 예외(Raise Exception)를 던져 서버 프로세스를 즉각 종료시키십시오.
    * **비용 청구 라우트 방어**: 실시간 뉴스 수집(`/api/news/sync`), LLM 요약(`/api/news/summaries/ensure`) 등 외부 유료 API(Tavily, OpenAI, Gemini) 비용을 유발하는 백엔드 Route는 비인증 노출을 금지합니다. 무조건 어드민 토큰(`X-Admin-Token`) 헤더 검증 또는 JWT 세션 인증 데코레이터를 적용하십시오.
    * **에러 응답 마스킹 확대**: `admin_inquiries.py`, `ml.py` 등 백엔드 API 라우트 내에서 에러 발생 시 `str(e)` 예외 원문을 직접 반환하지 마십시오. 시스템 내부 정보 유출을 막기 위해 무조건 `format_error_payload`를 통하게 하여 민감한 DB 스택이나 파일 경로를 숨기고 마스킹 처리하십시오.
22. **Supabase RLS 공용-개인 데이터 분리 격리 규칙 (DB 필수)**:
    * **공용 데이터 변조 방지**: `knowledge_chunks` 등 공용 지식 데이터(공시, 뉴스 등 `user_id IS NULL`인 상태)가 담기는 테이블의 RLS 정책에서 일반 인증 사용자(`authenticated`)에게 Insert, Update, Delete를 허용하는 `user_id IS NULL` 조건을 절대 부여하지 마십시오.
    * 일반 사용자 권한의 쓰기(Insert/Update/Delete) 정책에서는 무조건 `user_id = auth.uid()` 조건만 강제하고, 공용 데이터 영역은 오직 `service_role` 세션을 통해서만 쓰기 작업을 하도록 철저히 격리하십시오.
23. **개발 종료 전 정적 코드 검증 의무화 (품질 필수)**:
    * **Vite React 컴파일 전 정밀 진단**: 프론트엔드 작업 완료 전 반드시 ESLint를 활용하여 컴파일 및 린트 경고를 확인하고, 미사용 변수(`no-unused-vars`) 및 호이스팅 TDZ(선언 전 접근 오류) 가능성을 완전히 해결하십시오.
    * **디버그 잔재 제거**: 코드를 커밋하기 전 `grep` 등의 도구를 통해 소스 코드 전반에 `print`, `console.log` 및 `traceback.print_exc()` 잔재가 남아 있는지 전수 확인하고, 정상적인 표준 로그(`logger.info`, `logger.error`) 구문으로 모두 대체 또는 소거하십시오.


---

## 6. 거래소 간 자산 송금 및 재정거래 안전 규칙 (Arbitrage & Transfer)

코인원(COINONE)에서 리플(XRP) 등의 가상자산을 매수하여 바이낸스(BINANCE)로 전송하고 즉각 매도하여 차익을 거두는 재정거래(Arbitrage) 파이프라인을 API로 구현할 때, 다음의 보안 및 안전 규정을 **반드시 최우선적으로 준수**해야 합니다.

### 6.1 규제 및 인증 보안 제약 조건

1. **출금 지갑 주소 화이트리스트 사전 등록 강제**:
   * 대한민국 가상자산 트래블룰(Travel Rule) 규제에 따라, 임의의 주소로의 송금은 차단됩니다.
   * 사용자는 코인원 공식 웹/앱에서 바이낸스의 본인 명의 리플 지갑 주소 및 데스티네이션 태그(Destination Tag)를 **사전에 출금 화이트리스트 주소로 반드시 등록**해 두어야 합니다.
   * API 구현 시, 사전에 등록 완료된 화이트리스트 주소로만 출금 요청(`POST /v2.1/account/withdraw/coin`)을 날리도록 인터페이스를 설계해야 합니다.
2. **API Key 권한 및 2차 인증 대응**:
   * 코인원 API를 통한 출금 기능을 활성화하려면, 발급된 API Key에 **'출금(Withdraw)'** 권한이 허용되어 있어야 합니다.
   * 2차 인증(OTP, PIN 번호 등) 프로세스가 API 흐름 내에 결합될 경우, 이를 자동화하거나 우회하려 하지 말고 사용자에게 명시적으로 PIN 입력을 요구하는 등의 검증 단계를 프론트엔드와 조율하여 구현하십시오.
3. **24시간 원화 입금 후 출금 제한 예외 처리**:
   * 국내 가상자산 거래소의 금융사고 방지 규칙에 따라, 원화(KRW) 입금 후 24시간 동안은 해당 자산 규모만큼 가상자산의 출금이 제한됩니다.
   * 백엔드는 출금 API 호출 전 코인원 자산 현황(`GET /v2.1/account/balance/all`)을 조회하여 **'출금 가능 잔고(Available Balance)'**가 주문액보다 큰지 검증을 선행해야 합니다.

### 6.2 전송 모니터링 및 주문 안정성 (Human-in-the-Loop)

1. **송금 승인 프로세스 수동 확인 필터 적용**:
   * 시스템이 코인원에서 리플 매수를 실행한 후, 바이낸스로의 실제 자산 이동(출금) 단계로 넘어갈 때는 **절대 백그라운드에서 독자적으로 자동 송금을 수행해서는 안 됩니다.**
   * 반드시 Supabase `trade_proposals`에 송금 제안 카드를 생성하고, 사용자가 프론트엔드 화면에서 **최종 승인 버튼을 명시적으로 눌렀을 때만** 코인원 출금 API를 기동해야 합니다.
2. **XRP Destination Tag 필수 유효성 검사**:
   * 리플 전송 시 Destination Tag 누락 혹은 오기입으로 인한 자산 분실(미아) 사고를 막기 위해, 출금 페이로드 생성 시 `destination_tag`가 양의 정수로 정확히 포함되어 있는지 정규식 및 타입 검증을 강제하십시오.
3. **바이낸스 입금 모니터링 및 실시간 폴링**:
   * 송금이 개시되면 바이낸스의 입금 내역 확인 API(`GET /sapi/v1/capital/deposit/hisrec`)를 주기적으로 폴링(30초~1분 간격)하여, 입금 상태가 `Success`로 확인되는 순간 즉시 다음 단계인 매도 주문 트리거로 넘어가도록 비동기 이벤트를 작성하십시오.
4. **전송 지연 시 세일 슬리피지(Slippage) 방어**:
   * 블록체인 전송 도중(일반적으로 3~5분 소요) 해외 마켓의 가격 급락 리스크를 방어하기 위해, 바이낸스 입금이 완료된 순간 실시간 시세를 확인하여 코인원 매수 단가 대비 손실이 서비스 설정 한도(예: -1.5%)를 초과할 경우 매도를 보류하고 사용자에게 알리는 슬리피지 안전 장치를 마련하십시오.
