# 프로젝트 디렉토리 아키텍처 설계서 (Directory Structure Guide)

본 문서는 **Vite React(프론트엔드) + Flask(백엔드 API 및 워커) + Supabase(데이터베이스 및 인증)** 기반의 AI 자동매매 MVP 프로젝트의 확장성과 독립성을 보장하기 위한 표준 디렉토리 구조 가이드라인입니다.

---

## 1. 전체 디렉토리 트리 (Root)

```text
teamproject/
├── .gitignore               # 전체 Git 무시 파일 설정
├── README.md                # 프로젝트 소개 및 실행 방법
├── agents.md                # AI 개발 가이드 및 제약 수칙
├── database_specification.md# Supabase 테이블 및 ERD 명세
├── project_structure.md     # [본 문서] 디렉토리 아키텍처 설계 가이드
├── supabase/                # Supabase CLI 설정 및 DB 마이그레이션
│   ├── config.toml          # 로컬/원격 Supabase 설정 파일
│   └── migrations/          # DB 버전 관리 SQL 마이그레이션 파일들
├── backend/                 # Flask 백엔드 (API Gateway & 자동매매 엔진)
│   ├── app.py               # Flask 서버 진입점 (라우트 등록)
│   ├── requirements.txt     # 파이썬 의존성 패키지 목록
│   ├── config.py            # 환경 변수 및 공통 설정 로더
│   ├── services/            # 비즈니스 로직 서비스 레이어 (거래소 클라이언트 등)
│   │   ├── __init__.py
│   │   ├── exchange_client.py# 거래소 추상화 부모 클래스
│   │   ├── kis_client.py    # 한국투자증권 API 통신 및 토큰 캐싱
│   │   ├── upbit_client.py  # 업비트 JWT 서명 및 API 통신
│   │   ├── agent.py         # LLM & LangChain 챗봇 오케스트레이터
│   │   └── trading_engine.py# 백그라운드 자동매매 감시 엔진
│   ├── utils/               # 공통 유틸리티 함수
│   │   ├── __init__.py
│   │   ├── crypto_helper.py # API Key AES-256 양방향 암호화
│   │   └── logger.py        # 자동매매 이력 로깅 헬퍼
│   └── tests/               # API 및 엔진 단위 테스트 코드
└── frontend/                # React 프론트엔드 (Vite + Tailwind CSS v4)
    ├── package.json         # 노드 의존성 및 스크립트 정의
    ├── vite.config.js       # Vite 빌드 설정
    ├── index.html           # SPA 진입 HTML 파일
    ├── public/              # 이미지, 로고, 정적 자산 보관 (logo.png)
    └── src/                 # React 소스 코드 디렉토리
        ├── main.jsx         # React 렌더링 진입점
        ├── App.jsx          # 라우팅 및 전역 세션 감지
        ├── App.css          # 공통 컴포넌트 세부 스타일시트
        ├── index.css        # Tailwind v4 및 전역 CSS 변수 설정
        ├── supabaseClient.js# Supabase Client 인스턴스 초기화
        ├── pages/           # 라우트 단위 페이지 컴포넌트
        │   ├── Dashboard.jsx# 메인 대시보드 화면
        │   ├── Login.jsx    # Stitch 스타일 로그인 페이지
        │   └── Signup.jsx   # 이메일 회원가입 페이지
        ├── components/      # 재사용 가능한 UI 아토믹 컴포넌트 (버튼, 모달, 차트 등)
        │   ├── Header.jsx   # 상단 공통 헤더
        │   ├── TradeCard.jsx# 챗봇 매매 승인/거절 컴포넌트
        │   └── SurveyOverlay.jsx # 투자 성향 설문 오버레이 (App.jsx에서 분리 시 활용)
        ├── hooks/           # 커스텀 훅 (실시간 챗 구독, 시세 갱신 등)
        └── context/         # AuthContext 등 전역 컨텍스트 (필요 시)
```

---

## 2. 레이어별 설계 사상 및 상세 설명

### 2.1 프론트엔드 (`frontend/src/`)
* **`pages/` vs `components/` 분리**: 
  * 라우터와 1:1로 매핑되는 단일 유닛 화면은 `pages/`에 두고, 그 화면 안에서 재사용되는 디자인 요소(예: 매매 승인용 특수 카드, 차트, 커스텀 인풋)는 `components/`로 격리하여 코드 중복을 최소화합니다.
* **`supabaseClient.js`**:
  * 애플리케이션 전체에서 하나의 Supabase 클라이언트 인스턴스만 재사용(Singleton Pattern)하도록 격리합니다.
* **`hooks/`**:
  * Supabase Realtime 채널을 리스닝하여 대시보드의 잔고나 매매 제안 상태를 실시간 업데이트하는 비동기 이벤트를 Custom Hook으로 분리하면, UI 렌더링 로직이 대폭 정돈됩니다.

### 2.2 백엔드 (`backend/`)
* **`app.py` (API Gateway)**:
  * 프론트엔드와 챗봇의 모든 요청을 받아들이는 통로 역할을 수행하며, 세부 비즈니스 로직은 `services/`로 전부 위임합니다.
* **`services/` (독립 격리 레이어)**:
  * **거래소 연동 (`kis_client.py`, `upbit_client.py`)**: `ExchangeClient` 추상 클래스를 상속받아 구현함으로써 각 거래소별 API 구현 스펙이 변경되더라도 프론트엔드나 챗봇 엔진에 영향이 가지 않도록 방어합니다.
  * **감시 엔진 (`trading_engine.py`)**: 사용자 조건식이 등록되면 독립적인 백그라운드 스레드 풀 또는 Celery 프로세스로 감시 모듈을 기동하여 Flask 웹 요청 응답 속도에 영향을 주지 않도록 설계합니다.

### 2.3 Supabase (`supabase/`)
* **`migrations/`**:
  * 테이블 생성, RLS(Row Level Security) 설정, Postgres 트리거 및 펑션 정의는 수동으로 원격 DB에 쿼리를 치는 것이 아니라, 버전 번호가 매겨진 `.sql` 마이그레이션 파일로 여기에 누적하여 형상 관리합니다.

---

## 3. 디렉토리 표준화에 따른 개발 이점
1. **역할(Role)의 명확성**: 파일명만 봐도 해당 코드가 프론트엔드의 화면 단인지, 백엔드의 증권사 통신 로직인지 즉시 식별이 가능합니다.
2. **협업 병목 제거**: 프론트엔드 개발자는 `frontend/` 경로 내부만 만지고, 백엔드 개발자는 `backend/` 내부에서 API 스펙에만 맞춰 집중 작업하여 컨플릭트(Conflict)를 예방합니다.
3. **배포 편리성**: `Docker` 빌드 시 프론트엔드 도커파일과 백엔드 도커파일을 루트의 서브디렉토리 기준으로 각각 빌드하기 최적화된 구조입니다.
