# AI 개발 에이전트를 위한 주식·코인 자동매매 MVP 프로젝트 지침서 (agents.md)

본 문서는 다른 AI 코딩 어시스턴트나 에이전트가 본 프로젝트의 맥락을 즉각적으로 이해하고, 일관된 설계 사상과 제약 조건을 준수하며 개발할 수 있도록 안내하는 시스템 가이드입니다. 

이 프로젝트를 수정하거나 새로운 코드를 작성할 때, 아래의 지침과 보안 규칙을 **반드시 최우선적으로 준수**하십시오.

---

## 1. 프로젝트 핵심 맥락 (Project Context)

* **정의**: 한국투자증권 API(국내 주식)와 업비트 API(가상자산)를 단일 챗봇 및 대시보드로 통합 관리하는 AI 기반 트레이딩 보조 시스템.
* **사용자 통제 원칙 (Human-in-the-Loop)**: AI가 시장을 독자적으로 판단하여 즉흥적으로 실거래 주문을 실행하는 것은 원천적으로 차단합니다. 
  - 일반 매매 주문: **챗봇의 제안 -> 시뮬레이션 보고 -> 사용자의 명시적 승인 -> 실행**
  - 자동 트레이딩(Phase 4): 사용자가 자연어로 설정한 **수치적 조건식(예: 익절 +5%, 손절 -3%)만** 백그라운드 워커가 기계적으로 감시 및 실행.
* **독립 격리 환경**: 실거래 자금이 움직이는 백엔드(Flask) 및 DB(Supabase)는 기존 웹 서비스 인프라와 완전히 분리하여 운영합니다.

---

## 2. 아키텍처 및 데이터 흐름 지침

```
  [React Frontend] (Vite + Tailwind CSS)
         |
         +-- (1) Supabase SDK: 사용자 인증(Auth) & 승인 상태 실시간 구독(Realtime)
         +-- (2) REST API: LLM 챗봇 질의, 수동 매매 승인, 자동 매매 규칙 등록
         |
         v
  [Flask Backend] (API Gateway & Worker)
         |
         +-- [utils/crypto_helper.py]  : API Key를 AES-256 양방향 암호화하여 DB 송수신
         +-- [services/agent.py]        : LangChain 활용 LLM Tool-calling 오케스트레이터
         +-- [services/trading_engine.py] : Background Thread Pool 기반 실시간 시세 감시
         |
         v
  [Supabase DB] & [External APIs] (KIS API / Upbit API / Tavily News API)
```

### 2.1 에이전트 코딩 시 준수할 3대 통신 규칙
1. **상태 동기화**: 매매 제안의 생성은 Flask 백엔드가 수행하여 Supabase `trade_proposals` 테이블에 `PENDING`으로 인서트하고, React 프론트엔드는 Supabase Realtime 구독 기능을 통해 이 이벤트를 캐치하여 챗봇 창에 승인 카드를 즉시 렌더링해야 합니다.
2. **인증 분기**: 
   - 한국투자증권(KIS): OAuth 2.0 기반 Access Token 발급 및 24시간 캐싱 처리 필요.
   - 업비트(Upbit): 요청 발생 시마다 HMAC 서명이 가미된 일회성 JWT를 즉석 발행하여 API 호출.
3. **API Key 보안**: 사용자 거래소 API Key는 어떠한 경우에도 평문 상태로 DB에 저장하거나 프론트엔드로 전달해서는 안 됩니다. 반드시 백엔드의 대칭키(AES-256) 암호화 기능을 거쳐야 합니다.

---

## 3. 핵심 데이터 스키마 및 디자인 참조
AI 에이전트는 데이터 변경이나 조회 쿼리를 짤 때 다음 5개 핵심 테이블 구조를 준수해야 합니다. 자세한 명세는 [supabase_schema.md](supabase_schema.md)를 참고하십시오. 또한, UI/UX 구현 시 [design.md](design.md)에 기술된 스타일 규격을 완벽히 준수해야 합니다.

* `profiles`: 사용자 기본 정보 (Supabase Auth와 auth.uid() 연동)
* `user_api_keys`: 암호화된 API Key, KIS 계좌 정보 및 실전/모의(`kis_env` IN ('MOCK', 'REAL')) 구분 정보 보관.
* `paper_portfolios`: 업비트 가상 투자(시뮬레이터)를 위한 가상 잔고 및 보유 종목 저장.
* `trade_proposals`: 챗봇이 제안하고 승인을 기다리는 주문 내역 (`status` CHECK ('PENDING', 'APPROVED', 'REJECTED', 'EXECUTED', 'FAILED'))
* `auto_trading_rules`: 사용자가 정의한 실시간 조건 감시 규칙 및 활성화 여부 보관.
* `design.md`: 프론트엔드 UI 컴포넌트, 색상, 타이포그래피, 마진 등 공통 스타일 가이드라인 정보 보관.

---

## 4. 단계별 구현 로드맵 및 개발 범위 (Roadmap)

작성 중인 코드의 기능 수준이 현재 프로젝트의 어느 Phase에 속하는지 명확히 인식하고 기능을 구현해야 합니다.

### Phase 1: 정보 조회 및 뉴스 RAG 챗봇
* **구현 범위**: 주문/자동화 제외. 시세 및 자산 현황 조회 API, Tavily 검색 API를 결합한 최신 뉴스 RAG 프롬프트 체인 구축.
* **코드 예외**: 실거래 주문 API 호출은 이 단계에서 절대 활성화하지 않습니다.

### Phase 2: 모의투자 & 페이퍼 트레이딩 시뮬레이터
* **구현 범위**: KIS 모의투자 환경 연동 및 업비트용 가상 체결 엔진 개발.
* **체결 모듈**: `paper_portfolios` 테이블을 업데이트하는 가상 매수/매도 로직을 설계하여 업비트의 실거래 리스크를 회피합니다.

### Phase 3: 실거래 반자동 매매 (소액 제한)
* **구현 범위**: 사용자가 승인 버튼을 누르면 실거래 주문을 날리되, 보안과 리스크 하드캡을 적용합니다.
* **코드 필수 안전 조항**: 
  - 1회 주문 한도 하드캡 (예: 최대 10만 원) 검증 코드 삽입.
  - 동일 주문의 중복 실행 방지를 위한 **Idempotency Key (멱등성 키)** 검증 로직 구현.

### Phase 4: 조건식 자동 트레이딩 (자동 트레이닝)
* **구현 범위**: 사용자가 기지정한 가격 도달 시 자동 주문을 실행하는 백그라운드 워커 구축.
* **구조적 제약**: Flask의 웹 서비스 웹훅/API 스레드와 **별도 스레드(또는 APScheduler/Celery 프로세스)로 완전히 격리**하여 감시 엔진을 구동합니다.
* **최적화**: 주식 자산의 경우 평일 정규 거래 시간(09:00 ~ 15:30) 외에는 주기적 API 폴링을 중단(Sleep)하고 긴 주기로 조회하도록 설계해야 합니다.

---

## 5. AI 에이전트를 위한 코드 구현 가이드라인

1. **거래소 추상화 클래스 준수**: 새로운 거래소나 자산이 추가될 경우 `ExchangeClient` 추상 클래스를 상속받아 `get_price`, `get_balance`, `place_order`, `get_order_status`를 오버라이딩하여 구현하십시오.
2. **LangChain 에이전트의 툴(Tool) 정의**: 
   - 챗봇이 시세를 묻거나 뉴스 흐름 분석을 요청받을 때, `get_price` 및 `search_news` 도구를 호출할 수 있도록 명확한 Type Hint와 docstring을 명시하여 LangChain 에이전트에 바인딩하십시오.
3. **오류 대응 및 로깅**: 거래소 API의 응답 지연이나 에러 발생 시, `trade_proposals` 테이블의 `status`를 `FAILED`로 변경하고 `failure_reason` 컬럼에 반드시 원인을 상세히 기록하도록 코딩하십시오.
4. **디자인 시스템 엄격 준수**: UI를 개발할 때 [design.md](design.md)에 명시된 Obsidian Navy 배경, JetBrains Mono 폰트 사용처, Glassmorphism, 2px Cyan 매매 승인 카드 왼쪽 강조 테두리 등 모든 스타일 토큰을 정교하게 적용하십시오.
5. **Dead Code 지양**: `console.log`, 사용되지 않는 라이브러리 임포트, 임시 주석 처리된 코드는 발견 즉시 삭제하고 정돈된 프로덕션 품질의 코드를 생산하십시오.
6. **주석 한글화 원칙**: 코드 내부의 설명 주석 및 함수/클래스 개발 관련 설명글은 반드시 한국어로 작성하여 직관적인 코드 가독성을 보장하십시오. (영문 주석 배제)
7. **관련 문서 최신화**: 테이블 구조 신설/변경, 라우트 신설, 신규 컴포넌트 추가, 디렉토리 구조 변경 등 작업이 성공적으로 완료되면, 실제 코드를 바탕으로 연관된 프로젝트 사양 문서(예: `database_specification.md`, `project_structure.md` 등)를 누락 없이 최신 정보로 갱신하여 문서 일치성을 유지하십시오.
