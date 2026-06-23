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
├── backend/                      # Flask 백엔드 (API Gateway & 자동매매 엔진)
│   ├── app.py                    # Flask 서버 진입점 (현재 구현됨)
│   ├── requirements.txt          # 파이썬 의존성 패키지 목록 (현재 구현됨)
│   ├── config.py                 # 환경 변수 및 공통 설정 로더 (추가 예정)
│   ├── services/                 # 비즈니스 로직 서비스 레이어
│   │   ├── __init__.py           # 패키지 초기화 파일 (추가 예정)
│   │   ├── exchange_client.py    # 거래소/브로커 추상화 부모 클래스 (현재 구현됨)
│   │   ├── toss_client.py        # Toss Open API 메인 주식 클라이언트 (현재 구현됨)
│   │   ├── kis_client.py         # 한국투자증권 레거시/보류 주식 클라이언트 (현재 구현됨)
│   │   ├── coinone_client.py     # 코인원 가상자산 메인 클라이언트 (현재 구현됨)
│   │   ├── binance_client.py     # 바이낸스 가상자산 확장 클라이언트 (현재 구현됨)
│   │   ├── upbit_client.py       # 업비트 가상자산 클라이언트 (레거시/비활성화됨)
│   │   ├── news_repository.py    # 뉴스 데이터 조회/저장 서비스 (현재 구현됨)
│   │   ├── news_ingest.py        # 뉴스 수집 서비스 (현재 구현됨)
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

### 2.2 백엔드 (`backend/`)

* **`app.py` (API Gateway)**:
  * 프론트엔드와 챗봇의 모든 요청을 받아들이는 통로 역할을 수행하며, 세부 비즈니스 로직은 `services/`로 위임합니다.
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
3. **협업 병목 제거**: 프론트엔드 개발자는 `frontend/` 내부 UI와 Supabase Realtime 구독에 집중하고, 백엔드 개발자는 `backend/` 내부에서 Toss API 스펙과 보안 정책에 맞춰 작업할 수 있습니다.
4. **배포 편리성**: `Docker` 빌드 시 프론트엔드 도커파일과 백엔드 도커파일을 루트의 서브디렉토리 기준으로 각각 빌드하기 최적화된 구조입니다.
