# 프로젝트 디렉토리 아키텍처 설계서 (Directory Structure Guide)

본 문서는 **Vite React(프론트엔드) + Flask(백엔드 API 및 워커) + Supabase(데이터베이스 및 인증)** 기반의 Toss 메인 AI 트레이딩 MVP 프로젝트의 확장성과 독립성을 보장하기 위한 표준 디렉토리 구조 가이드라인입니다.

현재 저장소는 Vite React와 Flask 구조로 구현되어 있습니다. Toss Open API 전환 과정에서는 실제 존재하는 파일과 목표 구조를 구분하여 문서를 갱신합니다.

---

## 1. 전체 디렉토리 트리 (Root)

```text
teamproject/
├── .gitignore                    # 전체 Git 무시 파일 설정
├── README.md                     # 프로젝트 소개 및 실행 방법
├── agents.md                     # AI 개발 가이드 및 제약 수칙
├── database_specification.md     # Supabase 테이블 및 ERD 명세
├── project_structure.md          # [본 문서] 디렉토리 아키텍처 설계 가이드
├── supabase/                     # Supabase CLI 설정 및 DB 마이그레이션
│   ├── config.toml               # 로컬/원격 Supabase 설정 파일
│   └── migrations/               # DB 버전 관리 SQL 마이그레이션 파일들
├── ml/                           # LightGBM 사전학습 및 예측 파이프라인
│   ├── README.md                 # 로컬/Colab 학습 실행 가이드
│   ├── experiments.md            # LightGBM 실험 결과 누적 기록
│   ├── dataset_ops_runbook.md    # 데이터셋 수집/학습/검증 운영 절차 문서
│   ├── live_run_checklist.md     # 관리자 페이지 기준 실전 실행 체크리스트
│   ├── automation_plan.md        # 자동 수집/자동 학습/모델 레지스트리 설계 계획
│   ├── requirements.txt          # ML 전용 Python 의존성
│   ├── configs/
│   │   ├── lgbm_stock_v1.yaml         # 주식 상승 신호 모델 설정
│   │   ├── lgbm_stock_risk_v1.yaml    # 주식 하락 위험 모델 설정
│   │   ├── ...
│   │   ├── lgbm_stock_v6.yaml         # 주식 고도화 실험 설정
│   │   ├── lgbm_stock_risk_v6.yaml    # 주식 하락 위험 고도화 설정
│   │   ├── lgbm_crypto_v6.yaml        # 코인 고도화 실험 설정
│   │   └── lgbm_crypto_risk_v6.yaml   # 코인 하락 위험 고도화 설정
│   ├── data/
│   │   ├── raw/                  # 원천 캔들 CSV 보관
│   │   │   ├── *.template.csv    # 뉴스/코인 외부/주식 이벤트 피처 템플릿 예시
│   │   ├── ops/                  # 데이터셋/학습 작업 이력(JSON), 모델 레지스트리 상태 및 운영 보조 산출물
│   │   ├── processed/            # 피처/라벨/예측 CSV 출력
│   │   └── reference/            # 유니버스 프리셋, 고정 메타 데이터 파일
│   │       └── training_universes.json # 주식/코인 확장 수집용 프리셋 목록
│   ├── models/                   # 학습된 모델 파일 출력
│   ├── reports/                  # 생성된 실험 보고서 Markdown 산출물
│   ├── notebooks/                # Colab 또는 로컬 Jupyter 실험 노트북
│   └── src/
│       ├── build_features.py     # 캔들 데이터 기반 피처/라벨 생성
│       ├── train_model.py        # LightGBM 학습 및 모델 저장
│       ├── evaluate.py           # 검증 지표 출력
│       ├── predict.py            # 저장 모델 기반 최신 데이터 예측
│       ├── backtest_signals.py   # 상위 signal_score 후보 기준 백테스트
│       ├── run_pipeline_bundle.py# 동일 조건 재현용 일괄 실행기
│       ├── compare_experiments.py# summary JSON 기준 버전별 성능 비교 스크립트
│       ├── write_experiment_report.py # summary JSON 기반 Markdown 리포트 생성기
│       └── model_utils.py        # 시계열 분할/가중치/평가 공용 유틸
├── backend/                      # Flask 백엔드 (API Gateway & 자동매매 엔진)
│   ├── app.py                    # Flask 서버 진입점 (현재 구현됨, model-results/registry/active-model/jobs/full-run/readiness API 포함)
│   ├── requirements.txt          # 파이썬 의존성 패키지 목록 (현재 구현됨)
│   ├── config.py                 # 환경 변수 및 공통 설정 로더 (추가 예정)
│   ├── scripts/
│   │   └── export_training_candles.py # 학습용 주식/코인 캔들 CSV 수집 스크립트 (preset/chunk/failure-output 지원)
│   ├── services/                 # 비즈니스 로직 서비스 레이어
│   │   ├── __init__.py           # 패키지 초기화 파일 (추가 예정)
│   │   ├── exchange_client.py    # 거래소/브로커 추상화 부모 클래스 (현재 구현됨)
│   │   ├── toss_client.py        # Toss Open API 메인 주식 클라이언트 (현재 구현됨)
│   │   ├── kis_client.py         # 한국투자증권 레거시/보류 주식 클라이언트 (현재 구현됨)
│   │   ├── coinone_client.py     # 코인원 가상자산 메인 클라이언트 (현재 구현됨)
│   │   ├── binance_client.py     # 바이낸스 가상자산 확장 클라이언트 (현재 구현됨)
│   │   ├── upbit_client.py       # 업비트 가상자산 클라이언트 (레거시/비활성화됨)
│   │   ├── news_repository.py    # 뉴스 데이터 조회/저장 서비스 (현재 구현됨)
│   │   ├── news_summary_service.py # 뉴스 GPT 요약 생성 서비스
│   │   ├── news_query_planner.py # 뉴스 수집 쿼리 예산/쿨다운/우선순위 플래너
│   │   ├── news_ingest.py        # 뉴스 수집 서비스 (현재 구현됨)
│   │   ├── ml_job_service.py     # ML 작업 이력 저장 및 파이프라인 실행 서비스 (현재 구현됨)
│   │   ├── ml_automation_service.py # 자동 수집+학습 preset 정의 서비스 (현재 구현됨)
│   │   ├── ml_registry_service.py # 파일 기반 모델 레지스트리 상태 저장 서비스 (현재 구현됨)
│   │   ├── symbol_metadata.py    # 모델 결과 표시용 심볼명/시장/섹터 메타데이터 매핑 (현재 구현됨)
│   │   ├── agent.py              # LLM & LangChain 챗봇 오케스트레이터 (추가 예정)
│   │   └── trading_engine.py     # 백그라운드 조건 감시 엔진 (추가 예정)
│   ├── utils/                    # 공통 유틸리티 함수
│   │   ├── __init__.py           # 패키지 초기화 파일 (추가 예정)
│   │   ├── crypto_helper.py      # API Key AES-256 양방향 암호화 (현재 구현됨)
│   │   └── logger.py             # 자동매매 이력 로깅 헬퍼 (추가 예정)
│   └── tests/                    # API 및 엔진 단위 테스트 코드 (추가 예정)
└── frontend/                     # React 프론트엔드 (Vite + Tailwind CSS v4)
    ├── package.json              # 노드 의존성 및 스크립트 정의
    ├── package-lock.json         # 노드 의존성 잠금 파일
    ├── vite.config.js            # Vite 빌드 설정
    ├── index.html                # SPA 진입 HTML 파일
    ├── public/                   # 이미지, 로고, 정적 자산 보관
    └── src/                      # React 소스 코드 디렉토리
        ├── main.jsx              # React 렌더링 진입점
        ├── App.jsx               # 라우팅 및 전역 세션 감지
        ├── App.css               # 공통 컴포넌트 세부 스타일시트
        ├── index.css             # Tailwind v4 및 전역 CSS 변수 설정
        ├── supabaseClient.js     # Supabase Client 인스턴스 초기화
        ├── lib/
        │   └── supabaseClient.js # Supabase Client 보조 초기화 파일
        ├── pages/                # 라우트 단위 페이지 컴포넌트
        │   ├── Dashboard.jsx     # 메인 대시보드 화면
        │   ├── News.jsx          # 뉴스 화면
        │   ├── AdminMlData.jsx   # 학습 데이터 수집 + 학습 실행 + 작업 이력 + 모델 버전별 성능 비교 + 레지스트리/서비스 반영 관리자 화면
        │   ├── Login.jsx         # 로그인 페이지
        │   └── Signup.jsx        # 이메일 회원가입 페이지
        ├── components/           # 재사용 가능한 UI 컴포넌트
        │   └── Header.jsx        # 상단 공통 헤더
        ├── hooks/                # 커스텀 훅 (추가 예정)
        └── context/              # AuthContext 등 전역 컨텍스트 (추가 예정)
```

---

## 2. 레이어별 설계 사상 및 상세 설명

### 2.1 프론트엔드 (`frontend/src/`)

* **`pages/` vs `components/` 분리**:
  * 라우터와 1:1로 매핑되는 단일 유닛 화면은 `pages/`에 두고, 그 화면 안에서 재사용되는 디자인 요소는 `components/`로 격리하여 코드 중복을 최소화합니다.
* **Supabase Client**:
  * 애플리케이션 전체에서 하나의 Supabase 클라이언트 인스턴스만 재사용하도록 격리합니다.
  * 현재 `src/supabaseClient.js`와 `src/lib/supabaseClient.js`가 함께 존재하므로, 향후 한 경로로 통합할 때 호출부 import 경로를 전수 검사해야 합니다.
* **Toss 민감정보 접근 금지**:
  * 프론트엔드는 Toss `client_id`, `client_secret`, access token을 직접 다루지 않습니다.
  * Toss 관련 요청은 Flask 백엔드 REST API를 통해서만 수행합니다.
* **`hooks/` 목표 구조**:
  * Supabase Realtime 채널을 리스닝하여 대시보드의 잔고나 매매 제안 상태를 실시간 업데이트하는 비동기 이벤트를 Custom Hook으로 분리합니다.
* **통합 금융 차트 라이브러리 채택**:
  * 주식(Toss, KIS) 및 코인(Coinone, Binance)의 실시간 캔들 차트를 그리기 위해 **TradingView Lightweight Charts**를 전면 채택합니다.
  * 단일 리액트 차트 컴포넌트를 설계하여, 사용자의 거래소/종목/주기 변경 이벤트에 따라 동적으로 시세 데이터를 교체(setData)하는 고성능 비동기 방식으로 구현합니다.

### 2.2 백엔드 (`backend/`)

* **`app.py` (API Gateway)**:
  * 프론트엔드와 챗봇의 모든 요청을 받아들이는 통로 역할을 수행하며, 세부 비즈니스 로직은 `services/`로 위임합니다.
  * **학습 데이터 수집 API (`POST /api/ml/export-candles`)**:
    * 관리자 페이지(`/admin/ml-data`)에서 호출하는 학습용 CSV 생성 엔드포인트입니다.
    * 주식은 Toss Open API, 코인은 Binance 공개 캔들 API를 사용합니다.
    * Toss 수집 시 프론트엔드는 Supabase access token만 전달하고, 서버가 `user_api_keys`에서 로그인 사용자 API Key를 읽어 내부에서만 복호화합니다.
    * 생성 파일은 `ml/data/raw/stock_candles.csv` 또는 `ml/data/raw/crypto_candles.csv`에 저장합니다.
    * 스크립트 레벨에서는 preset 유니버스, chunk 수집, 실패 심볼 요약 JSON 저장을 지원하며, 관리자 API 응답에도 실패 건수를 포함합니다.
    * 호출 이력은 `ml/data/ops/job_history.json`에 `dataset_export` 타입으로 기록합니다.
  * **ML 운영 준비 상태 API (`GET /api/ml/readiness`)**:
    * 관리자 페이지에서 Toss 키 준비 여부, 원천 CSV, 외부 피처, 현재 serving 상태를 한 번에 조회합니다.
    * Toss 키 항목은 `supabase.user_api_keys -> encrypted_access_key/encrypted_secret_key -> crypto.decrypt` 경로를 설명용 메타데이터로 함께 반환해, 실제 데이터셋 수집이 어떤 보안 흐름으로 동작하는지 운영자가 확인할 수 있게 합니다.
  * **ML 작업 이력 API (`GET /api/ml/jobs`)**:
    * 최근 데이터셋 수집 및 학습 실행 이력을 조회합니다.
    * 현재는 Supabase 테이블이 아니라 파일 기반 작업 이력(JSON)을 읽습니다.
  * **ML 학습 실행 API (`POST /api/ml/jobs/train`)**:
    * 관리자 페이지에서 특정 config/risk-config 조합의 학습을 직접 실행합니다.
    * 내부적으로 `ml/src/run_pipeline_bundle.py`를 호출하고, stdout/stderr 일부와 상태를 작업 이력에 남깁니다.
  * **모델 결과 조회 API (`GET /api/ml/model-results`)**:
    * 관리자 페이지(`/admin/ml-data`)에서 최신 모델 성능 지표와 예측 순위를 조회합니다.
    * `ml/models/*.metrics.json`, `ml/data/processed/*_predictions_lgbm_v*.csv`, `ml/data/processed/*_backtest_*.json`을 읽어 주식/코인 결과를 분리 반환합니다.
    * 상승 모델 지표, 하락 위험 모델 지표, 시계열 CV 평균 지표, 복합 점수 예측 결과, `up_only/composite` 백테스트 요약을 함께 제공합니다.
    * 예측 결과의 티커는 `symbol_metadata.py`의 임시 메타데이터로 표시명, 시장, 섹터를 보강합니다. 추후 `watchlist_symbols` 테이블이 운영되면 DB 기반 메타데이터로 이전합니다.
    * 인증 헤더가 없는 요청은 차단하며, API Key나 계좌 정보는 응답에 포함하지 않습니다.
    * 추천 버전은 단순 최신 버전이 아니라 비용 반영 백테스트와 시계열 안정성을 함께 고려해 선택합니다.
    * 프론트엔드 관리자 페이지는 선택 버전과 `SERVING / PICK / LATEST` 기준 버전 사이의 핵심 지표 차이를 별도 요약 패널로 보여 주어, 운영자가 어떤 버전을 올릴지 빠르게 판단할 수 있게 합니다.
  * **통합 시세 조회 API (`GET /api/chart/candles`)**:
    * 프론트엔드에 일관된 데이터 인터페이스를 제공하기 위한 게이트웨이 라우트입니다.
    * 요청 파라미터(`exchange`, `symbol`, `interval`)에 맞추어 각각의 거래소 클라이언트를 동적으로 스위칭 호출합니다.
    * 각 거래소마다 상이한 시간 및 가격 포맷을 융합하여 TradingView Lightweight Charts 규격(`time`, `open`, `high`, `low`, `close`)으로 변환(어댑터 패턴)하여 공통 규격의 JSON 배열로 반환합니다.
    * 빈번한 중복 호출로 인한 거래소 API 차단(Rate Limit)을 예방하기 위해 백엔드 레벨에서 정적 캐싱(Caching)을 수행합니다.
* **`services/toss_client.py` (현재 구현됨, 메인 주식 클라이언트)**:
  * Toss Open API의 인증, 시세, 종목 정보, 시장 정보, 계좌, 보유자산, 주문 전 검증, 주문, 주문 조회를 담당합니다.
  * `/oauth2/token` 토큰 발급은 form-urlencoded 방식으로 처리합니다.
  * 계좌 기반 API 호출 전 `GET /api/v1/accounts`로 `accountSeq`를 조회하고, 이후 요청에 `X-Tossinvest-Account` 헤더를 포함합니다.
  * 일반 API 응답은 `result` envelope 기준으로 파싱하고, 에러 응답은 `error.requestId`, `error.code`, `error.message`, `error.data` 기준으로 처리합니다.
  * 토큰 발급 실패는 OAuth2 표준 에러 형식인 `error`, `error_description` 기준으로 별도 처리합니다.
* **`services/exchange_client.py` (추상화 레이어)**:
  * Toss, KIS, Coinone, Binance 구현체가 동일한 상위 인터페이스를 따르도록 설계합니다.
  * Toss 금액 주문(`orderAmount`)과 수량 주문(`quantity`)처럼 기존 메서드 시그니처로 표현이 부족한 경우, 추상 클래스와 모든 구현체/호출부를 함께 수정합니다.
* **`services/kis_client.py` (레거시/보류)**:
  * 현재 구현된 KIS 클라이언트는 보존하되, 신규 주식 기능의 기본 구현 대상은 Toss로 둡니다.
* **`services/coinone_client.py` (현재 구현됨, 메인 가상자산 클라이언트)**:
  * 코인원 Private API v2.1 HMAC-SHA512 서명 및 전체 잔고 조회와 연결 테스트 검증 기능을 제공합니다.
* **`services/binance_client.py` (현재 구현됨, 확장 가상자산 클라이언트)**:
  * 바이낸스 API Key 조회 권한을 활용한 계정 잔고 조회 및 HMAC-SHA256 기반 연결 테스트 기능을 제공합니다.
* **`services/trading_engine.py` (추가 예정)**:
  * 사용자 조건식이 등록되면 독립적인 백그라운드 스레드 풀 또는 별도 프로세스로 감시 모듈을 기동하여 Flask 웹 요청 응답 속도에 영향을 주지 않도록 설계합니다.
  * 국내/미국 주식 장 운영 여부는 Toss 장 캘린더 API를 기준으로 판단합니다.

### 2.3 Supabase (`supabase/`)

* **`migrations/`**:
  * 테이블 생성, RLS(Row Level Security) 설정, Postgres 트리거 및 펑션 정의는 수동으로 원격 DB에 쿼리를 치는 것이 아니라, 버전 번호가 매겨진 `.sql` 마이그레이션 파일로 누적하여 형상 관리합니다.
* **Toss/가상자산 전환 시 DB 변경 대상**:
  * `exchange` CHECK 제약에 `TOSS`, `COINONE`, `BINANCE`를 추가해야 합니다.

  * `user_api_keys`에는 Toss `accountSeq` 저장 필드가 필요합니다.
  * `trade_proposals`에는 Toss `clientOrderId`, `orderId`, `marketCountry`, `currency`, `timeInForce`, `orderAmount` 매핑 필드가 필요합니다.
  * 실제 DB 변경은 문서 갱신 이후 별도 마이그레이션으로 수행합니다.

### 2.4 ML 파이프라인 (`ml/`)

* **로컬 우선 원칙**:
  * LightGBM 초기 MVP는 맥북 M2 로컬 Python 환경에서 개발하고 검증합니다.
  * 데이터가 커지거나 반복 튜닝 시간이 길어지는 경우 Colab을 학습 전용 보조 환경으로 사용합니다.
* **주식/코인 모델 분리**:
  * 주식은 `lgbm_stock_v1.yaml`와 `lgbm_stock_risk_v1.yaml` 기준으로 상승 확률과 하락 위험을 분리 학습합니다.
  * 코인은 `lgbm_crypto_v1.yaml`와 `lgbm_crypto_risk_v1.yaml` 기준으로 상승 확률과 하락 위험을 분리 학습합니다.
  * 코인 모델은 24시간 시장 특성을 반영해 5분·15분·1시간·4시간·24시간 수익률과 거래량·변동성 피처를 우선 사용합니다.
* **역할 분리**:
  * `ml/src/build_features.py`는 캔들 CSV를 읽어 과거 기반 피처와 미래 라벨을 생성합니다.
  * `ml/src/train_model.py`는 생성된 피처 파일로 LightGBM 모델을 학습하고 `ml/models/`에 저장합니다.
  * `ml/src/predict.py`는 저장된 모델로 최신 피처의 상승 확률, 하락 위험 점수, 종합 신호 점수를 산출합니다.
  * `ml/src/backtest_signals.py`는 검증 구간에서 날짜별 상위 `signal_score` 후보의 비용 반영 미래 수익률, 후보 승률, 최대 낙폭을 계산합니다.
  * `ml/src/model_utils.py`는 시계열 분할, class weight, 심볼 균형 가중치, 확률 보정, 공통 평가 지표 계산을 담당합니다.
  * Flask 백엔드는 학습을 직접 수행하지 않고, 검증된 모델 파일을 로드해 예측 API만 제공합니다.
  * 자동화 단계에서는 `ml/automation_plan.md`에 정의한 별도 워커/모델 레지스트리 구조를 기준으로 확장합니다.
* **데이터 보안**:
  * `ml/data/`와 `ml/models/`에는 대용량 데이터와 모델 산출물이 생성되므로 Git 커밋 대상에서 제외합니다.
  * 사용자 개인 계좌 데이터, 주문 이력, API Key는 ML 학습 데이터로 사용하지 않습니다.

---

## 3. Toss Open API 기준 백엔드 모듈 책임

### 3.1 인증 및 계좌

* `issue_oauth2_token`: `/oauth2/token` 호출 및 토큰 캐시 관리
* `get_accounts`: `/api/v1/accounts` 호출 및 `accountSeq` 선택
* `resolve_account_header`: 계좌 기반 요청에 사용할 `X-Tossinvest-Account` 헤더 구성

### 3.2 조회 기능

* `get_price`, `get_prices`: 현재가 조회
* `get_orderbook`: 호가 조회
* `get_trades`: 최근 체결 조회
* `get_candles`: 1분봉/일봉 캔들 조회
* `get_stock_info`: 종목 기본 정보 조회
* `get_stock_warnings`: 매수 유의사항 조회
* `get_exchange_rate`: KRW/USD 환율 조회
* `get_market_calendar`: 국내/미국 장 운영 정보 조회
* `get_holdings`: 계좌 보유 주식 조회

### 3.3 주문 및 주문 전 검증

* `get_buying_power`: 매수 가능 금액 조회
* `get_sellable_quantity`: 판매 가능 수량 조회
* `get_commissions`: 수수료 조회
* `create_order`: 주문 생성. `clientOrderId`를 반드시 사용합니다.
* `get_orders`, `get_order`: 주문 목록 및 상세 조회
* `modify_order`, `cancel_order`: 정정 및 취소

---

## 4. 디렉토리 표준화에 따른 개발 이점

1. **역할의 명확성**: 파일명만 봐도 해당 코드가 프론트엔드 화면, 백엔드 API Gateway, Toss 통신 로직, DB 마이그레이션 중 어느 영역인지 즉시 식별할 수 있습니다.
2. **Toss 전환 안정성**: KIS 레거시 구현을 보존하면서 신규 Toss 클라이언트를 별도 모듈로 추가하므로, 기존 기능을 훼손하지 않고 점진적으로 전환할 수 있습니다.
3. **ML 실험 격리**: `ml/` 디렉토리에서 주식/코인 모델의 학습 데이터, 피처 생성, 모델 학습을 격리하므로 Flask 서비스 코드와 실험 코드가 섞이지 않습니다.
4. **협업 병목 제거**: 프론트엔드 개발자는 `frontend/` 내부 UI와 Supabase Realtime 구독에 집중하고, 백엔드 개발자는 `backend/` 내부에서 Toss API 스펙과 보안 정책에 맞춰 작업할 수 있습니다.
5. **배포 편리성**: `Docker` 빌드 시 프론트엔드 도커파일과 백엔드 도커파일을 루트의 서브디렉토리 기준으로 각각 빌드하기 최적화된 구조입니다.
