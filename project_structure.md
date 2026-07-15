# 프로젝트 구조 문서

본 문서는 현재 저장소에 실제로 존재하는 디렉토리와 파일을 기준으로 정리한 구조 안내서입니다.
과거 문서에 섞여 있던 "추가 예정" 구조는 최소화했고, 아직 없는 모듈은 존재하는 것처럼 적지 않습니다.

## 루트 구조

```text
teamproject/
├── .env.example
├── README.md
├── agents.md
├── design.md
├── database_specification.md
├── project_structure.md
├── system_workflow.md
├── toss_api_guide.md
├── kis_api_guide.md
├── backend/
├── frontend/
├── ml/
├── scratch/
└── supabase/
```

## backend

```text
backend/
├── app.py
├── worker.py
├── requirements.txt
├── routes/
│   ├── home.py
│   ├── keys.py
│   ├── ml.py
│   ├── admin_users.py
│   ├── news.py
│   ├── disclosures.py
│   ├── trade.py
│   └── transfer.py
├── scripts/
│   ├── backfill_dart_disclosures.py
│   ├── export_dart_features.py
│   ├── export_news_features.py
│   ├── export_training_candles.py
│   ├── sync_dart_corp_codes.py
│   └── sync_kis_market_universe.py
├── services/
│   ├── auth_service.py
│   ├── auto_trading_rule_engine.py
│   ├── binance_client.py
│   ├── broker_order_history_service.py
│   ├── chatbot/
│   │   ├── __init__.py
│   │   ├── chat_service.py
│   │   ├── conversation_repository.py
│   │   ├── function_calling.py
│   │   ├── llm_client.py
│   │   ├── memory_service.py
│   │   ├── order_form_policy.py
│   │   ├── order_parser.py
│   │   ├── portfolio_summary_service.py
│   │   ├── prompt_registry.py
│   │   ├── qa_event_repository.py
│   │   ├── rag_service.py
│   │   ├── recommendation_service.py
│   │   ├── safety_guard.py
│   │   ├── tool_registry.py
│   │   └── web_fallback_search_service.py
│   ├── coinone_client.py
│   ├── dart_ingest.py
│   ├── dart_repository.py
│   ├── error_message_service.py
│   ├── exchange_client.py
│   ├── home_service.py
│   ├── keys_service.py
│   ├── kis_client.py
│   ├── kis_market_universe.py
│   ├── lock_service.py
│   ├── market_repository.py
│   ├── market_snapshot_scheduler.py
│   ├── ml_automation_service.py
│   ├── ml_job_service.py
│   ├── ml_model_service.py
│   ├── ml_registry_service.py
│   ├── ml_scheduler.py
│   ├── ml_split_model_promotion_service.py
│   ├── news_ingest.py
│   ├── news_query_planner.py
│   ├── news_repository.py
│   ├── news_summary_service.py
│   ├── order_entry_service.py
│   ├── supabase_client.py
│   ├── symbol_metadata.py
│   ├── token_cache_service.py
│   ├── toss_client.py
│   └── upbit_client.py
└── utils/
    ├── crypto_helper.py
    └── file_helpers.py
```

### backend 역할 구분

- `app.py`
  - Flask 앱 생성
  - Blueprint 등록
  - CORS 설정
  - 환경 변수 로드
  - 일부 스케줄러를 gateway 내부에서 돌릴지 결정
- `worker.py`
  - 뉴스 수집
  - DART 공시 수집
  - ML 자동화
  - 홈 마켓 스냅샷
  - 조건감시 자동/반자동 매도 스케줄러
  - 전체 사용자 미완료 주문 상태 동기화 스케줄러
- `routes/`
  - HTTP API 입구
  - `admin_users.py`는 관리자 전용 사용자 목록, 실제 챗봇 토큰 사용량, 유저별 거래내역 조회, role 변경 API를 제공합니다. 사용량 집계·정렬·페이지 제한은 service-role 전용 Supabase RPC에 위임하고, 관리용 거래내역은 `trade_proposals`, `broker_order_history`, `asset_transfer_proposals`의 제한 필드만 반환하며 보유자산/잔고는 노출하지 않습니다.
  - `disclosures.py`는 OpenDART 공시 목록 조회 및 수동 동기화 API를 담당
  - `transfer.py`는 코인원 ↔ 바이낸스 가상자산 출금 사전검증, 수수료 조회, 승인, 상태 추적 API를 담당
  - `knowledge.py`는 Obsidian Markdown 노트 동기화와 앱 자동메모리 조회 API를 담당
- `services/`
  - 거래소 연동, Supabase, 스케줄러, ML 운영 로직
  - `chatbot/conversation_repository.py`는 Supabase `chat_history`와 `chatbot_conversation_states`를 사용해 다중 워커 간 대화 이력, 만료 가능한 대기 작업, 최근 추천 상태를 공유
  - `chatbot/portfolio_summary_service.py`는 거래소별 KRW·USD·USDT 잔고를 원화로 환산하고 REAL/MOCK 계좌 합계를 분리
  - `chatbot/llm_client.py`는 OpenAI Chat Completions 스트림의 텍스트 delta를 전달하고 분할된 tool-call과 usage를 누적
  - `chatbot/qa_event_repository.py`는 챗봇 QA 분석용 자동 이벤트를 `chatbot_qa_events`에 service role로 저장하며, 민감한 거래소 raw payload 대신 trace·도구·지연시간 요약만 남깁니다.
  - `order_entry_service.py`는 구조화 주문 필수값, 주식·현물·선물 거래 목적, One-way/Hedge 주문 변환, 서비스 레버리지 상한, 주문 해시와 HMAC 사전검증 토큰을 담당합니다.
  - `chatbot/order_form_policy.py`는 일반 채팅의 자연어 주문 의도를 주문 제안 생성 전에 차단하고 상단 `매매 요청` 버튼을 이용하라는 안내만 반환합니다. 종목·수량·가격·거래소를 추출하거나 저장하지 않습니다.
  - `chatbot/tool_registry.py`는 `get_crypto_market_context`를 통해 코인 현재가, 호가, 캔들, ML 활성 신호, 보유 스냅샷, 스프레드·슬리피지, Coinone/Binance 김치프리미엄과 주의사항을 통합한 읽기 전용 분석 도구를 제공합니다.
  - `obsidian_service.py`는 Markdown frontmatter/title/hash 정규화를 담당
  - `knowledge_chunk_service.py`는 저장된 노트 본문을 RAG/embedding 대상 chunk로 분할
  - `knowledge_repository.py`는 `user_knowledge_notes`, `user_memory_facts` Supabase 저장/조회 래퍼를 담당
- `scripts/`
  - 수집/변환/유니버스 동기화 보조 스크립트

### backend에서 문서상 주의할 점

- `agent.py`, `trading_engine.py`는 현재 저장소에 없습니다.
- 토큰 캐시는 현재 `token_cache_service.py`와 Supabase `token_caches`를 기준으로 보는 것이 맞습니다.
- `coinone_client.py`는 코인원 잔고/현재가/지정가 주문/미체결 주문 취소, 입금 주소 조회, Public 가상자산 입출금 수수료 조회, 출금을 담당하며, 시장가 주문은 아직 운영 경로가 아닙니다.
- `binance_client.py`는 `BinanceSpotClient`와 `BinanceFuturesClient`를 포함합니다. 현물 클라이언트는 입금 주소/입금 내역, 네트워크별 출금 수수료, 출금 요청을 지원합니다. API Key 저장은 `BINANCE` 레코드 하나를 사용하고, `BINANCE_UM_FUTURES`는 USD-M 선물 잔고/주문/이력 요청 식별자로만 사용합니다. 선물 주문은 레버리지와 교차/격리 마진 타입을 주문 직전에 반영하며, 선물 REAL 주문은 `BINANCE_FUTURES_REAL_ENABLED=true` 환경변수 없이는 차단됩니다.
- `auto_trading_rule_engine.py`는 Supabase `auto_trading_rules`의 `RUNNING` 규칙을 감시하고, 조건 도달 시 `trade_proposals`에 매도 제안을 생성하거나 사용자가 `AUTO`로 선택한 규칙에 한해 자동 매도 주문을 전송합니다.
- `open_order_status_sync_service.py`는 worker가 전체 사용자의 미완료 주문만 주기적으로 조회해 KIS/코인원/바이낸스/바이낸스 선물 실제 주문 상태를 `trade_proposals`에 반영하는 서비스입니다.
- `error_message_service.py`는 거래소 원문 에러를 사용자 친화적인 `message`, `error.title`, `error.action`, `error.code`, `error.raw_message` 구조로 변환하는 표준 에러 메시지 레이어입니다.
- `broker_order_history_service.py`는 Toss/KIS/Coinone/Binance 주문 원장 동기화 및 미체결/체결 상태 보정 흐름을 담당합니다.
- `upbit_client.py`는 남아 있지만 현재 핵심 운영 경로는 아닙니다.

## frontend

## 2026-07-01 OpenDART 공시 연동 추가 모듈

- `backend/routes/disclosures.py`: 종목 상세 공시 목록 조회 및 수동 공시 동기화 API
- `backend/services/dart_repository.py`: Supabase `dart_*` 테이블 조회/upsert 저장소
- `backend/services/dart_ingest.py`: OpenDART 전체 공시 목록 수집, 최근 1년 백필, `CORPCODE.xml` 매핑 동기화 서비스
- `backend/scripts/sync_dart_corp_codes.py`: 루트 `CORPCODE.xml`을 `dart_corp_codes`에 업서트하는 스크립트
- `backend/scripts/backfill_dart_disclosures.py`: 최근 1년 공시를 날짜 구간별로 수집해 `dart_disclosures`에 업서트하는 스크립트
- `supabase/migrations/20260701093000_create_dart_disclosures.sql`: DART 공시 캐시 테이블, 로그 테이블, RLS 정책 생성

```text
frontend/
├── package.json
├── package-lock.json
├── vite.config.js
└── src/
    ├── App.jsx
    ├── App.css
    ├── index.css
    ├── main.jsx
    ├── supabaseClient.js
    ├── dashboardConstants.js
    ├── dashboardUtils.js
    ├── assets/
    ├── components/
    │   ├── DashboardComponents.jsx
    │   ├── Header.jsx
    │   ├── InvestmentSurveyModal.jsx
    │   └── SymbolSearch.jsx
    ├── lib/
    │   ├── apiError.js
    │   └── supabaseClient.js
    ├── features/
    │   └── chatbot/
    │       ├── ChatbotWidget.jsx
    │       ├── OrderEntryFlow.jsx
    │       ├── chatbotApi.js
    │       └── orderEntryModel.js
    └── pages/
        ├── AdminInquiryPanel.jsx
        ├── AdminMlData.jsx
        ├── AdminUsers.jsx
        ├── AssetDetail.jsx
        ├── AssetsTab.jsx
        ├── Dashboard.jsx
        ├── Home.jsx
        ├── Login.jsx
        ├── MarketRankings.jsx
        ├── News.jsx
        ├── SearchNotFound.jsx
        ├── Settings.jsx
        ├── Signup.jsx
        ├── TradeHistoryTab.jsx
        └── WatchlistTab.jsx
```

### frontend 역할 구분

- `features/chatbot/OrderEntryFlow.jsx`
  - 챗봇 상단 버튼에서 빈 상태로 시작하는 데스크톱 3단계 매매 요청 UI
  - 연결 계좌와 거래 목적, 검색 결과 또는 서버 보유 목록, 주문 조건, 사전검증 결과를 순서대로 확인
  - 검증 토큰이 유효한 경우에만 구조화 챗봇 요청으로 `PENDING` 제안을 생성
- `features/chatbot/orderEntryModel.js`
  - 입력 변경 시 사전검증 무효화, 단계 이동 가능 여부, 자산별 수량·통화·거래 목적 용어, API 요청 DTO를 관리

- `Dashboard.jsx`
  - 메인 대시보드
  - 자산/시장/실거래 vs 모의 토글 흐름
- `AssetDetail.jsx`
  - 종목 상세
  - 차트, 호가, 체결, 주문 사전검증, ML 신호 카드
  - TOSS 주식 상세 헤더의 종목 유의사항 배지 연동
- `AdminInquiryPanel.jsx`
  - 3분리 모델 자동화 상태 모니터링 및 수동 검증 패널
- `AdminMlData.jsx`
  - ML 운영 콘솔
  - readiness, serving audit, 활성 신호, 자동화 실행, 작업 이력, 고급 도구
  - 관리자 유저 관리 탭에서 `AdminUsers.jsx`를 렌더링
- `AdminUsers.jsx`
  - 관리자 유저 관리 탭의 데스크톱/반응형 UI
  - UTC 기준 실제 챗봇 토큰 사용량 집계와 사용자별 사용 내역을 조회
  - 현재 기본 모델 `gpt-4.1-mini` 가격 기준으로 통산/30일/유저별/요청별 예상 비용을 추정 표시
- `supabaseClient.js`, `lib/supabaseClient.js`
  - Supabase 초기화 경로가 2개 존재
  - 향후 통합 시 import 호출부 전수 확인이 필요

### frontend에서 문서상 주의할 점

- 현재 프로젝트는 Next.js 구조가 아니라 `Vite + React` 구조입니다.
- `frontend/README.md`는 기본 템플릿이었으나 실제 구조 기준으로 별도 정리해야 합니다.

## ml

```text
ml/
├── README.md
├── automation_plan.md
├── dataset_ops_runbook.md
├── experiments.md
├── live_run_checklist.md
├── requirements.txt
├── serving_package_runbook.md
├── test_yf.py
├── configs/
├── data/
│   ├── ops/
│   ├── processed/
│   ├── raw/
│   └── reference/
├── models/
├── notebooks/
├── reports/
├── serving_packages/
└── src/
    ├── backtest_signals.py
    ├── build_features.py
    ├── compare_experiments.py
    ├── compare_model_versions.py
    ├── evaluate.py
    ├── export_serving_package.py
    ├── model_utils.py
    ├── policy_utils.py
    ├── predict.py
    ├── run_pipeline_bundle.py
    ├── train_model.py
    ├── tune_hyperparameters.py
    ├── tune_stock_policy.py
    └── write_experiment_report.py
```

### ml 역할 구분

- `configs/`
  - 현재 기준 주식 신호 `v1~v11`
  - 주식 위험 `v1~v11`
  - 코인 신호/위험 `v1~v9`
  - 3분리 shadow 모델 설정: `lgbm_kr_stock_v1.yaml`, `lgbm_kr_stock_risk_v1.yaml`, `lgbm_us_stock_v1.yaml`, `lgbm_us_stock_risk_v1.yaml`
- `data/raw/`
  - 원천 캔들 및 외부 피처 CSV
- `data/ops/`
  - `job_history.json`
  - `model_registry.json`
- `models/`
  - 학습된 joblib 및 metrics JSON
- `reports/`
  - 비교 리포트와 최신 실험 리포트
- `serving_packages/`
  - EC2 업로드용 서빙 패키지 출력 디렉토리
  - `manifest.json`, 모델 joblib, risk 모델 joblib, config, metrics, summary만 포함하며 raw 학습 데이터는 포함하지 않습니다.

## supabase

```text
supabase/
├── config.toml
└── migrations/
```

이 디렉토리는 존재합니다. 다만 현재 애플리케이션 동작의 일부는 파일 기반 이력과 Supabase best-effort 동기화가 섞여 있으므로, "모든 운영 상태가 Supabase 마이그레이션만으로 완전히 재현된다"고 적으면 사실과 다릅니다.

## scratch

`scratch/`는 운영 코드가 아니라 로컬 확인용 스크립트와 임시 테스트 파일 보관 영역입니다. 문서나 리뷰에서 제품 기능처럼 설명하지 않는 것이 맞습니다.

## 문서 업데이트 원칙

- 실제 파일이 없으면 존재한다고 적지 않습니다.
- 계획 문서는 `automation_plan.md`처럼 계획 문서로 남기고, 현재 구조 문서와 섞지 않습니다.
- API, DB, ML 버전은 코드 기준으로 맞추고, 실험 리포트 숫자는 별도 리포트 문서에서만 관리합니다.

---

1. **역할의 명확성**: 파일명만 봐도 해당 코드가 프론트엔드 화면, 백엔드 API Gateway, Toss 통신 로직, DB 마이그레이션 중 영역인지 즉시 식별할 수 있습니다.
2. **Toss 전환 안정성**: KIS 레거시 구현을 보존하면서 신규 Toss 클라이언트를 별도 모듈로 추가하므로, 기존 기능을 훼손하지 않고 점진적으로 전환할 수 있습니다.
3. **ML 실험 격리**: `ml/` 디렉토리에서 주식/코인 모델의 학습 데이터, 피처 생성, 모델 학습을 격리하므로 Flask 서비스 코드와 실험 코드가 섞이지 않습니다.
4. **협업 병목 제거**: 프론트엔드 개발자는 `frontend/` 내부 UI와 Supabase Realtime 구독에 집중하고, 백엔드 개발자는 `backend/` 내부에서 Toss API 스펙과 보안 정책에 맞춰 작업할 수 있습니다.
5. **배포 편리성**: `Docker` 빌드 시 프론트엔드 도커파일과 백엔드 도커파일을 루트의 서브디렉토리 기준으로 각각 빌드하기 최적화된 구조입니다.

---

## 5. KIS order execution and estimated holdings additions

* `backend/services/kis_client.py`
  * `get_daily_order_executions()`: KIS domestic stock daily order/execution inquiry.
  * `get_order_execution_status()`: Normalizes KIS order state into `EXECUTED`, `PARTIALLY_FILLED`, `CANCELED`, `ORDERED`, or `UNKNOWN`.
* `backend/routes/trade.py`
  * `POST /api/trade/orders/sync-status`: Syncs KIS DB order records with real KIS execution status, then falls back to balance checks.
  * `POST /api/trade/estimated-holdings`: Builds DB-estimated holdings from executed `trade_proposals`, enriches stock positions with broker prices, and calculates valuation profit and profit rate.

## 6. Disclosure summary RAG additions

* `backend/services/disclosure_knowledge_index_service.py`: Builds summary-only DART disclosure documents/chunks for `knowledge_chunks`.
* `backend/services/embedding_service.py`: Embeds pending knowledge chunks with OpenAI embeddings.
* `backend/services/rag_retrieval_service.py`: Embeds a question and retrieves ranked context through Supabase vector search.
* `backend/scripts/backfill_disclosure_summary_chunks.py`: Rebuilds `DISCLOSURE` chunks from cached DART AI/rule summaries.
* `backend/scripts/embed_pending_knowledge_chunks.py`: Embeds pending chunks, defaulting to `DISCLOSURE`.
* `supabase/migrations/20260709103000_add_knowledge_chunk_vector_search.sql`: Adds the vector index and `match_knowledge_chunks` RPC.
* This flow excludes news and DART original text; only saved disclosure summaries and metadata are indexed.
