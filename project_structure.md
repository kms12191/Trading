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
│   ├── news.py
│   ├── trade.py
│   └── transfer.py
├── scripts/
│   ├── export_news_features.py
│   ├── export_training_candles.py
│   └── sync_kis_market_universe.py
├── services/
│   ├── auth_service.py
│   ├── binance_client.py
│   ├── coinone_client.py
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
│   ├── news_ingest.py
│   ├── news_query_planner.py
│   ├── news_repository.py
│   ├── news_summary_service.py
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
  - ML 자동화
  - 홈 마켓 스냅샷
- `routes/`
  - HTTP API 입구
  - `transfer.py`는 코인원에서 바이낸스로 이동하는 가상자산 출금 사전검증, 승인, 상태 추적 API를 담당
- `services/`
  - 거래소 연동, Supabase, 스케줄러, ML 운영 로직
- `scripts/`
  - 수집/변환/유니버스 동기화 보조 스크립트

### backend에서 문서상 주의할 점

- `agent.py`, `trading_engine.py`는 현재 저장소에 없습니다.
- 토큰 캐시는 현재 `token_cache_service.py`와 Supabase `token_caches`를 기준으로 보는 것이 맞습니다.
- `coinone_client.py`는 코인원 잔고/현재가/지정가 주문/미체결 주문 취소를 담당하며, 시장가 주문은 아직 운영 경로가 아닙니다.
- `binance_client.py`는 `BinanceSpotClient`와 `BinanceFuturesClient`를 포함합니다. API Key 저장은 `BINANCE` 레코드 하나를 사용하고, `BINANCE_UM_FUTURES`는 USD-M 선물 잔고/주문/이력 요청 식별자로만 사용합니다. 선물 주문은 레버리지와 교차/격리 마진 타입을 주문 직전에 반영하며, 선물 REAL 주문은 `BINANCE_FUTURES_REAL_ENABLED=true` 환경변수 없이는 차단됩니다.
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
    │   └── supabaseClient.js
    └── pages/
        ├── AdminMlData.jsx
        ├── AssetDetail.jsx
        ├── AssetsTab.jsx
        ├── Dashboard.jsx
        ├── Home.jsx
        ├── Login.jsx
        ├── News.jsx
        ├── Settings.jsx
        ├── Signup.jsx
        ├── TradeHistoryTab.jsx
        └── WatchlistTab.jsx
```

### frontend 역할 구분

- `Dashboard.jsx`
  - 메인 대시보드
  - 자산/시장/실거래 vs 모의 토글 흐름
- `AssetDetail.jsx`
  - 종목 상세
  - 차트, 호가, 체결, 주문 사전검증, ML 신호 카드
- `AdminMlData.jsx`
  - ML 운영 콘솔
  - readiness, serving audit, 활성 신호, 자동화 실행, 작업 이력, 고급 도구
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
└── src/
    ├── backtest_signals.py
    ├── build_features.py
    ├── compare_experiments.py
    ├── compare_model_versions.py
    ├── evaluate.py
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
  - 코인 신호/위험 `v1~v8`
- `data/raw/`
  - 원천 캔들 및 외부 피처 CSV
- `data/ops/`
  - `job_history.json`
  - `model_registry.json`
- `models/`
  - 학습된 joblib 및 metrics JSON
- `reports/`
  - 비교 리포트와 최신 실험 리포트

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
