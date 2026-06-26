# Stock & Coin Trading Bot MVP

Toss증권 Open API(국내·미국 주식), 코인원 및 바이낸스(가상자산)를 단일 챗봇 및 대시보드로 통합 관리하는 AI 기반 트레이딩 보조 시스템의 MVP입니다. LightGBM 기반 사전학습 신호 엔진은 주식과 코인을 별도 모델로 분리하여 `ml/` 디렉토리에서 관리합니다.

---

## 📂 프로젝트 구조

```
teamproject/
├── backend/                   # Flask 백엔드 서버 (API Gateway & 워커)
│   ├── app.py                 # Flask 서버 진입점 (Blueprint 등록 및 스케줄러 기동)
│   ├── requirements.txt       # 백엔드 의존 라이브러리 정의
│   ├── scripts/               # 학습 데이터 수집 등 운영 스크립트
│   │   ├── export_training_candles.py # 캔들 CSV 수집 스크립트
│   │   └── sync_kis_market_universe.py # KIS 주식 유니버스 동기화
│   ├── routes/                # Blueprint 기반 API 라우트 레이어
│   │   ├── home.py            # 대시보드, 홈/시장, 잔고 조회 라우트
│   │   ├── keys.py            # API 키 등록, 저장, 조회 라우트
│   │   ├── ml.py              # ML 데이터셋, 학습, 모델 레지스트리 라우트
│   │   ├── news.py            # 뉴스 피드 조회 및 AI 요약 라우트
│   │   └── trade.py           # 수동 주문, 사전검증, 차트/시세 라우트
│   ├── services/              # 비즈니스 로직 서비스 레이어
│   │   ├── exchange_client.py # 거래소 추상화 인터페이스
│   │   ├── toss_client.py     # Toss Open API 메인 주식 클라이언트
│   │   ├── kis_client.py      # KIS 레거시/보류 주식 클라이언트
│   │   ├── coinone_client.py  # 코인원 가상자산 메인 클라이언트 (HMAC-SHA512)
│   │   ├── binance_client.py  # 바이낸스 가상자산 확장 클라이언트
│   │   ├── auth_service.py    # Authorization 헤더 디코딩 및 user_id 파싱
│   │   ├── supabase_client.py # Supabase REST API 통신 및 데이터 동기화
│   │   ├── home_service.py    # 대시보드 종합 데이터 빌드 및 잔고 헬퍼
│   │   ├── keys_service.py    # API 호출 에러 분류 (FATAL / TEMPORARY)
│   │   ├── ml_model_service.py # ML 모델 지표 스캔, 추천, 준비 상태 빌드
│   │   └── ml_scheduler.py    # 뉴스 수집 및 ML 자동화 백그라운드 스케줄러
│   └── utils/
│       ├── crypto_helper.py   # API Key AES-256-GCM 암호화/복호화 유틸리티
│       └── file_helpers.py    # JSON/CSV 파일 입출력 및 모델 아티팩트 파싱
│
├── frontend/                  # Vite + React 프론트엔드
│   ├── src/
│   │   ├── App.jsx            # 라우팅 및 전역 세션 감지
│   │   ├── pages/             # 대시보드, 뉴스, 설정, 관리자 화면
│   │   │   ├── Dashboard.jsx  # 메인 대시보드 (모의계좌 ON/OFF 필터 포함)
│   │   │   ├── AssetsTab.jsx  # 보유 자산 현황 요약 탭
│   │   │   ├── AdminMlData.jsx # ML 모델 관리자 패널
│   │   │   └── ...
│   │   ├── components/        # 재사용 가능한 UI 컴포넌트
│   │   │   ├── Header.jsx     # 공통 상단 헤더
│   │   │   └── InvestmentSurveyModal.jsx # 투자 성향 진단 설문 모달
│   │   ├── index.css          # design.md 기반의 Obsidian Navy 테마 CSS (Tailwind v4)
│   │   ├── package.json       # 프론트엔드 의존성 및 스크립트 정의
│   │   └── vite.config.js     # Vite 및 Tailwind v4 컴파일 설정
│   └── public/                # 정적 에셋
│
├── ml/                        # LightGBM 사전학습 및 예측 파이프라인
│   ├── configs/               # 주식/코인 모델 v1~v7 설정 YAML
│   ├── data/                  # 원천/가공 데이터 보관
│   ├── models/                # 학습 모델 joblib 파일 출력
│   └── src/                   # 피처 생성, 학습, 평가, 예측 스크립트
│
├── design.md                  # Stitch 프로젝트 기반 UI/UX 디자인 가이드라인
├── agents.md                  # AI 개발 에이전트를 위한 설계 사상 지침서
├── database_specification.md  # Supabase 테이블 및 ERD 명세서
└── project_structure.md       # 디렉토리 아키텍처 설계 가이드
```

---

## 🚀 핵심 탑재 기능 (Core Features)

* **실거래 vs 모의계좌 ON/OFF 토글 필터**:
  * 사용자의 필요에 따라 실거래 자산(Toss)만 분리해서 보거나, 모의투자(KIS) 자산과 합산한 통합 포트폴리오를 대시보드 및 보유 자산 탭에서 실시간 O(1) 속도로 필터링하여 확인하는 기능을 제공합니다.
* **Toss 실시간 환율 API 연동 및 모니터링**:
  * Toss증권 Open API의 `/api/v1/exchange-rate` 엔드포인트를 통해 실시간 USD/KRW 환율을 수집합니다.
  * API 장애 발생 시 현실적인 기준인 `1500.0`원으로 안전하게 폴백되며, UI 상에 `실시간 API (Live)` 또는 `임시 고정 환율 적용됨` 배지와 함께 현재 적용 환율을 투명하게 표시합니다.
* **해외주식 수익률 백분율 스케일링 통일**:
  * Toss 해외주식 수익률 계산 로직을 타 거래소(KIS 등)의 백분율 양식과 통일하기 위해 `profit_rate * 100.0` 보정을 반영하여 일관된 수익률 비교를 보장합니다.
* **백그라운드 스냅샷 스케줄러 상시 기동**:
  * Gunicorn 및 Flask run 개발 환경 모두에서 백그라운드 포트폴리오 스냅샷 수집 스레드가 상시 기동됩니다.
  * `PORTFOLIO_SNAPSHOT_RUN_ON_START=true` 설정을 통해 서버 시작 즉시 첫 번째 스냅샷을 즉각 수집하도록 보장합니다.

---

## 🛠️ 설치 및 실행 방법

### 1. 백엔드 (Flask) 설정
백엔드 폴더로 이동하여 패키지 설치 및 환경 변수를 구성합니다.

```bash
cd backend
pip3 install -r requirements.txt
```

`backend/.env` 파일을 신설하여 API Key 암호화에 사용할 대칭키를 설정합니다. **(이 키는 Git 커밋에 포함되지 않도록 절대 주의하세요!)**

```ini
ENCRYPTION_KEY=your-secure-32character-encryption-key
```

백엔드 서버를 실행합니다:
```bash
python3 app.py
```
* 서버 구동 포트: `http://localhost:5050`

---

### 2. 프론트엔드 (React) 설정
프론트엔드 폴더로 이동하여 의존성 패키지를 설치한 후 개발 서버를 구동합니다.

```bash
cd frontend
npm install
npm run dev
```
* 프론트엔드 구동 주소: `http://localhost:5173`

---

## 🔒 보안 규칙 (Security Rule)
* **대칭키 분실 주의**: `ENCRYPTION_KEY`가 변경되면 이전에 DB에 암호화 저장된 API Key 복호화가 불가능해집니다. 로컬 개발 환경별 키 공유 관리에 주의하십시오.
* **토큰 캐시**: KIS 토큰은 불필요한 Rate Limit 소모 방지를 위해 로컬 디렉토리의 `.kis_token_cache.json` 파일에 저장 및 자동 관리되므로 Git에 커밋되지 않도록 `.gitignore`에 등록되어 있습니다.
* **ML 데이터 분리**: `ml/data/`와 `ml/models/`에는 대용량 학습 데이터와 모델 산출물이 생성되므로 원칙적으로 Git에 커밋하지 않습니다.

---

## 🧠 LightGBM 학습 준비

초기 학습은 맥북 M2 로컬 Python 환경에서 진행하고, 대량 분봉 데이터나 반복 튜닝이 필요할 때 Colab을 보조 환경으로 사용합니다.

```bash
cd ml
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

주식 모델은 일봉 중심으로 시작합니다.

```bash
python src/build_features.py --config configs/lgbm_stock_v1.yaml
python src/train_model.py --config configs/lgbm_stock_v1.yaml
```

코인 모델은 24시간 시장 특성에 맞춰 1시간봉 또는 4시간봉 데이터로 시작합니다.

```bash
python src/build_features.py --config configs/lgbm_crypto_v1.yaml
python src/train_model.py --config configs/lgbm_crypto_v1.yaml
```

학습용 캔들 CSV는 관리자 페이지 또는 스크립트로 생성합니다.

```text
관리자 페이지: http://localhost:5173/admin/ml-data
백엔드 API: POST http://localhost:5050/api/ml/export-candles
활성 예측 API: GET http://localhost:5050/api/ml/predictions/active?asset_type=STOCK&symbols=005930&limit=5
데이터 품질 API: GET http://localhost:5050/api/ml/data-quality?asset_type=STOCK
승격 검증 API: GET http://localhost:5050/api/ml/registry/promotion-check?asset_type=STOCK&model_version=lgbm_stock_signal_v7
serving 감사 API: GET http://localhost:5050/api/ml/serving-audit
```

`GET /api/ml/predictions/active`는 현재 serving 모델이 있거나 승격 기준을 통과한 추천 모델이 있을 때만 응답합니다. 기준 통과 모델이 없으면 활성 예측을 비워 두어, 최신이지만 품질이 낮은 모델을 챗봇이 실수로 사용하지 않게 합니다.

코인 CSV는 Binance 공개 캔들 API로 즉시 수집할 수 있습니다.

```bash
source ml/.venv/bin/activate
python backend/scripts/export_training_candles.py \
  --asset-type CRYPTO \
  --exchange BINANCE \
  --symbols BTCUSDT,ETHUSDT \
  --interval 1h \
  --count 500 \
  --output ml/data/raw/crypto_candles.csv
```

---

## 뉴스 게시판 수집/적재

뉴스 게시판은 프론트엔드가 외부 뉴스 API를 직접 호출하지 않고, Flask 백엔드가 Naver/Finnhub 뉴스를 수집해 Supabase `news_articles`에 적재한 뒤 프론트엔드가 DB만 조회합니다.

```ini
NAVER_CLIENT_ID=your-naver-client-id
NAVER_CLIENT_SECRET=your-naver-client-secret
FINNHUB_API_KEY=your-finnhub-api-key
OPENAI_API_KEY=your-openai-api-key
NEWS_SUMMARY_MODEL=gpt-4o-mini
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_ANON_KEY=your-anon-key
SUPABASE_SERVICE_ROLE_KEY=your-service-role-key
NEWS_INGEST_ENABLED=false
NEWS_INGEST_INTERVAL_SECONDS=600
NEWS_MAX_ITEMS_PER_QUERY=12
NEWS_NAVER_DAILY_QUERY_BUDGET=2000
NEWS_MAX_QUERIES_PER_RUN=30
NEWS_DYNAMIC_SYMBOLS_PER_RUN=5
NEWS_QUERY_COOLDOWN_MINUTES=30
NEWS_FINNHUB_SYMBOLS=AAPL,MSFT,NVDA
```

수동 적재는 백엔드 서버 실행 후 아래 엔드포인트로 호출합니다.

```bash
curl -X POST http://localhost:5050/api/news/sync
```

Naver 수집은 시장/매크로/수급/섹터 키워드를 기본으로 사용하고, `watchlist_symbols`에 활성 주식 종목이 있으면 실행당 일부만 선택해 `{종목명} 주식`, `{종목명} 실적`, `{종목명} 공시`, `{종목명} 영업이익` 쿼리를 순환 적용합니다.
뉴스 카드의 `요약 보기`를 누르면 GPT 3줄 요약을 생성하고 `news_articles.ai_summary`에 저장한 뒤, 다음부터는 저장된 요약을 재사용합니다.
