# Stock & Coin Trading Bot MVP

Toss증권 Open API(국내·미국 주식), 코인원 및 바이낸스(가상자산)를 단일 챗봇 및 대시보드로 통합 관리하는 AI 기반 트레이딩 보조 시스템의 MVP입니다. LightGBM 기반 사전학습 신호 엔진은 주식과 코인을 별도 모델로 분리하여 `ml/` 디렉토리에서 관리합니다.

---

## 📂 프로젝트 구조

```
teamproject/
├── backend/                  # Flask 백엔드 서버
│   ├── services/
│   │   ├── exchange_client.py # 거래소 추상화 인터페이스
│   │   └── kis_client.py      # KIS 모의투자 연동 모듈 (토큰 캐싱 포함)
│   ├── utils/
│   │   └── crypto_helper.py   # API Key AES-256-GCM 암호화/복호화 유틸리티
│   ├── app.py                 # Flask API 엔트리포인트 (Port: 5050)
│   ├── scripts/               # 학습 데이터 수집 등 운영 스크립트
│   └── requirements.txt       # 백엔드 의존 라이브러리 정의
│
├── frontend/                 # Vite + React 프론트엔드
│   ├── src/
│   │   ├── App.jsx            # 라우팅 및 전역 세션 감지
│   │   ├── pages/             # 대시보드, 뉴스, 설정, 관리자 화면
│   │   └── index.css          # design.md 기반의 Obsidian Navy 테마 CSS (Tailwind v4)
│   ├── package.json           # 프론트엔드 의존성 및 스크립트 정의
│   └── vite.config.js         # Vite 및 Tailwind v4 컴파일 설정
│
├── ml/                       # LightGBM 사전학습 및 예측 파이프라인
│   ├── configs/              # 주식/코인 모델 설정
│   ├── data/                 # 원천/가공 데이터 보관
│   ├── models/               # 학습 모델 파일 출력
│   └── src/                  # 피처 생성, 학습, 평가, 예측 스크립트
│
├── design.md                 # Stitch 프로젝트 기반 UI/UX 디자인 가이드라인
├── agents.md                 # AI 개발 에이전트를 위한 설계 사상 지침서
└── implementation_plan.md    # 통합 구현 계획서
```

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
```

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
