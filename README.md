# Stock & Coin Trading Bot MVP

한국투자증권(주식) 및 업비트(가상자산) API를 단일 챗봇 및 대시보드로 통합 관리하는 AI 기반 트레이딩 보조 시스템의 기본 프레임워크 MVP입니다.

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
│   └── requirements.txt       # 백엔드 의존 라이브러리 정의
│
├── frontend/                 # Vite + React 프론트엔드
│   ├── src/
│   │   ├── App.jsx            # API 테스트 및 대시보드 메인 화면
│   │   └── index.css          # design.md 기반의 Obsidian Navy 테마 CSS (Tailwind v4)
│   ├── package.json           # 프론트엔드 의존성 및 스크립트 정의
│   └── vite.config.js         # Vite 및 Tailwind v4 컴파일 설정
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
