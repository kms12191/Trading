# 프로젝트 보안 및 더미코드 전수 감사 종합 보고서 (Security & Code Audit Report)

본 보고서는 프로젝트의 `backend/`, `frontend/src/`, `ml/`, `supabase/migrations/` 전 영역의 소스 코드를 대상으로 수행된 보안 취약점, 환경 변수 매핑, 더미 코드 및 품질 진단 결과를 종합 정리한 문서입니다. 본 감사는 유저의 요청에 따라 **오직 읽기 전용 도구만을 사용하여 소스 코드의 무결성을 유지한 상태**에서 수행되었습니다.

---

## 1. 환경 변수 및 API 키 사용처 종합 매핑 (Environment Variables Mapping)

프로젝트 루트의 `.env.example`을 기준으로 시스템에서 조회하는 모든 환경 변수의 용도와 실제 소스코드 상의 호출 위치를 취합한 매핑 테이블입니다.

### 1.1 코어 보안 및 데이터베이스 환경 변수
| 환경 변수명 | 사용 위치 (파일 단위) | 설명 및 용도 | 보안 수립 상태 |
| :--- | :--- | :--- | :--- |
| `ENCRYPTION_KEY` | `backend/app.py`<br>`backend/services/token_cache_service.py`<br>`backend/services/auto_trading_rule_engine.py`<br>`backend/services/open_order_status_sync_service.py`<br>`backend/services/ml_scheduler.py`<br>`ml/src/export_training_candles.py` | 사용자 브로커 API 크리덴셜 암복호화용 대칭 마스터 키 (AES-256 GCM) | ⚠️ **위험**: 환경 변수가 누락되었을 때 기본 개발용 키가 하드코딩되어 동작하고 있어, Fail-Fast 구동 중단 정책으로 수정이 권장됩니다. |
| `SUPABASE_URL` | `backend/app.py`<br>`backend/services/supabase_client.py`<br>`backend/services/news_repository.py`<br>`backend/services/market_repository.py`<br>`backend/services/dart_repository.py`<br>`backend/services/broker_order_history_service.py`<br>`backend/routes/admin_inquiries.py`<br>`ml/src/export_training_candles.py`<br>`ml/src/export_dart_features.py`<br>`frontend/src/supabaseClient.js` | Supabase 프로젝트 REST API 엔드포인트 URL | 안전하게 사용 중. 프론트엔드는 `VITE_` 접두사 규칙 준수. |
| `SUPABASE_ANON_KEY` | `backend/app.py`<br>`backend/services/supabase_client.py`<br>`backend/services/news_repository.py`<br>`backend/services/dart_repository.py`<br>`backend/routes/admin_inquiries.py`<br>`ml/src/export_training_candles.py`<br>`frontend/src/supabaseClient.js` | Supabase 클라이언트 연동용 공개 익명 키 | 안전하게 사용 중. 프론트엔드는 `VITE_` 접두사 규칙 준수. |
| `SUPABASE_SERVICE_ROLE_KEY` | `backend/app.py`<br>`backend/services/supabase_client.py`<br>`backend/services/news_repository.py`<br>`backend/services/market_repository.py`<br>`backend/services/dart_repository.py`<br>`backend/services/broker_order_history_service.py`<br>`backend/routes/admin_inquiries.py`<br>`backend/worker.py`<br>`ml/src/export_dart_features.py` | Supabase DB 서비스 롤 어드민 키 (RLS 우회 작업용) | **안전**: 프론트엔드로 절대 유출되지 않고 백엔드 내부/배치 스크립트에서만 한정 사용됨. |

### 1.2 외부 거래소 및 브로커 API 환경 변수
| 환경 변수명 | 사용 위치 (파일 단위) | 설명 및 용도 | 보안 수립 상태 |
| :--- | :--- | :--- | :--- |
| `TOSS_API_KEY` | `backend/services/home_service.py`<br>`backend/services/toss_client.py` | 토스증권 Open API Client ID | 백엔드 내에서만 안전하게 주입받아 임시 인증 객체로 다뤄짐. |
| `TOSS_SECRET_KEY` | `backend/services/home_service.py`<br>`backend/services/toss_client.py` | 토스증권 Open API Client Secret | 백엔드 내에서만 안전하게 주입받아 임시 인증 객체로 다뤄짐. |
| `KIS_APPKEY` | `backend/services/home_service.py`<br>`backend/services/kis_client.py`<br>`backend/worker.py`<br>`backend/scripts/sync_kis_market_universe.py` | 한국투자증권(KIS) Open API 호출용 App Key | 백엔드 내에서만 로드되어 동작함. |
| `KIS_APPSECRET` | `backend/services/home_service.py`<br>`backend/services/kis_client.py`<br>`backend/worker.py`<br>`backend/scripts/sync_kis_market_universe.py` | 한국투자증권(KIS) Open API 호출용 App Secret | 백엔드 내에서만 로드되어 동작함. |
| `KIS_CANO` | `backend/services/home_service.py`<br>`backend/services/kis_client.py`<br>`backend/worker.py`<br>`backend/scripts/sync_kis_market_universe.py` | 한국투자증권 종합계좌번호(앞 8자리) | 백엔드 내에서만 로드되어 동작함. |
| `KIS_ACNT_PRDT_CD` | `backend/services/home_service.py`<br>`backend/services/kis_client.py`<br>`backend/worker.py`<br>`backend/scripts/sync_kis_market_universe.py` | 한국투자증권 계좌 상품 코드 (기본값: `"01"`) | 백엔드 내에서만 로드되어 동작함. |
| `KIS_ENV` | `backend/services/home_service.py`<br>`backend/services/kis_client.py`<br>`backend/worker.py`<br>`backend/scripts/sync_kis_market_universe.py` | KIS 접속 환경 구분 (`MOCK` 모의투자 / `REAL` 실거래) | 백엔드 내에서만 로드되어 동작함. |
| `COINONE_ACCESS_TOKEN` | `backend/app.py`<br>`backend/services/coinone_client.py` | 코인원 가상자산 API Access Token | 백엔드 내에서만 로드되어 동작함. |
| `COINONE_SECRET_KEY` | `backend/app.py`<br>`backend/services/coinone_client.py` | 코인원 가상자산 API Secret Key | 백엔드 내에서만 로드되어 동작함. |
| `BINANCE_API_KEY` | `backend/app.py`<br>`backend/services/binance_client.py` | 바이낸스 가상자산 API Key | 백엔드 내에서만 로드되어 동작함. |
| `BINANCE_SECRET_KEY` | `backend/app.py`<br>`backend/services/binance_client.py` | 바이낸스 가상자산 API Secret Key | 백엔드 내에서만 로드되어 동작함. |

### 1.3 LLM & 데이터 수집 환경 변수
| 환경 변수명 | 사용 위치 (파일 단위) | 설명 및 용도 | 보안 수립 상태 |
| :--- | :--- | :--- | :--- |
| `OPENAI_API_KEY` | `backend/services/chatbot/llm_client.py`<br>`backend/services/dart_analysis_service.py`<br>`backend/services/news_summary_service.py` | OpenAI API 호출 인증용 API Key | 백엔드 내에서만 로드되어 동작함. |
| `GEMINI_API_KEY` | `backend/services/dart_analysis_service.py` | Google Gemini API 호출 인증용 API Key | 백엔드 내에서만 로드되어 동작함. |
| `DART_API_KEY` | `backend/services/dart_analysis_service.py`<br>`backend/services/dart_ingest.py` | Open DART API 호출을 위한 인증 키 | 백엔드 내에서만 로드되어 동작함. |
| `NAVER_CLIENT_ID` | `backend/services/news_ingest.py` | 네이버 뉴스 Open API Client ID | 백엔드 내에서만 로드되어 동작함. |
| `NAVER_CLIENT_SECRET` | `backend/services/news_ingest.py` | 네이버 뉴스 Open API Client Secret | 백엔드 내에서만 로드되어 동작함. |
| `FINNHUB_API_KEY` | `backend/services/news_ingest.py` | 해외 주식 뉴스 수집용 Finnhub API Key | 백엔드 내에서만 로드되어 동작함. |

---

## 2. 보안 취약점 목록 (Security Vulnerabilities)

전수 조사 결과 식별된 보안 취약점 목록과 구체적 원인 및 조치 제안입니다.

### [보안 수준: High] 1. 암호화 키 기본값 하드코딩 취약점
* **취약점 위치**:
  * [token_cache_service.py:L10](file:///Users/kangheesung/10-19_개발/13_프로젝트/13.05_트레이딩/teamproject/backend/services/token_cache_service.py#L10)
  * [auto_trading_rule_engine.py:L78](file:///Users/kangheesung/10-19_개발/13_프로젝트/13.05_트레이딩/teamproject/backend/services/auto_trading_rule_engine.py#L78)
  * [open_order_status_sync_service.py:L74](file:///Users/kangheesung/10-19_개발/13_프로젝트/13.05_트레이딩/teamproject/backend/services/open_order_status_sync_service.py#L74)
  * [ml_scheduler.py:L38](file:///Users/kangheesung/10-19_개발/13_프로젝트/13.05_트레이딩/teamproject/backend/services/ml_scheduler.py#L38)
* **원인 및 취약점 설명**:
  * `ENCRYPTION_KEY` 환경 변수가 유입되지 않았을 때 고정된 평문 문자열 `"default-dev-encryption-key-32bytes!"`가 기본값으로 적용됩니다.
  * 프로덕션 배포 시 해당 환경 변수가 미설정될 경우, 모든 사용자의 거래소 키와 민감 자격 증명이 고정된 기본 암호화 키로 대칭 암호화(AES-256 GCM)되어 저장되므로 DB 정보 유출 시 손쉽게 대량 복호화 및 탈취가 가능해집니다.
* **권한 권장 조치**:
  * `ENCRYPTION_KEY`가 공백이거나 유입되지 않았을 경우, 기본값을 할당하지 말고 오류를 던지며 애플리케이션 시작을 강제 종료하는 **Fail-Fast 방식**으로 코드를 개선해야 합니다.

### [보안 수준: High/Medium] 2. `knowledge_chunks` 테이블 RLS 정책 훼손 위협
* **취약점 위치**:
  * [20260708113000_create_knowledge_chunks.sql](file:///Users/kangheesung/10-19_개발/13_프로젝트/13.05_트레이딩/teamproject/supabase/migrations/20260708113000_create_knowledge_chunks.sql)
* **원인 및 취약점 설명**:
  * RAG에서 사용하는 전체 공용 지식 데이터(공시, 뉴스 요약 등)는 특정 사용자에 묶여 있지 않으므로 `user_id`를 `NULL`로 생성하여 저장하게 됩니다.
  * 그러나 `knowledge_chunks`에 대한 Insert, Update, Delete의 RLS(Row Level Security) 정책 조건에 `user_id IS NULL`인 경우가 허용되도록 명시되어 있습니다.
  * 이로 인해, 로그인된 임의의 일반 인증 사용자(`authenticated`)라면 누구나 공용 지식 데이터 청크를 임의로 오염(Insert/Update)시키거나 통째로 삭제(Delete)할 수 있는 무단 변조 리스크가 존재합니다.
* **권한 권장 조치**:
  * `authenticated` 역할에 대한 쓰기 권한(Insert/Update/Delete) 정책 조건에서 `user_id IS NULL` 판별 로직을 삭제하고, 오직 `user_id = auth.uid()` 규칙만 남겨야 합니다. 공용 지식 데이터는 데이터베이스 관리자 계정이나 서비스 롤(Service Role)을 통해서만 쓰기 권한이 부여되도록 차단하고 일반 유저에게는 Read-Only로 분리해야 합니다.

### [보안 수준: Medium] 3. 실시간 뉴스 및 LLM 요약 API 비인증 접근 허용
* **취약점 위치**:
  * `backend/routes/news.py` 내의 `/api/news/sync` 및 `/api/news/summaries/ensure` 엔드포인트
* **원인 및 취약점 설명**:
  * 해당 엔드포인트들은 어떠한 JWT 헤더 검증이나 비인증 차단 데코레이터가 붙어 있지 않습니다.
  * 악의적인 공격자나 미인증 외부 클라이언트가 이 API를 빈번하게 직접 호출하여 백그라운드 수집을 계속 유발시키고, 대량의 Tavily 검색 및 OpenAI/Gemini API 호출을 반복 작동시켜 클라우드 요금을 폭발시키는 DDoS 자원 고갈 위협에 노출되어 있습니다.
* **권한 권장 조치**:
  * 타 어드민 동기화 API들처럼 헤더에서 관리자 인증 토큰(`X-Admin-Token`)을 검증하거나 사용자 세션 JWT를 필수 검사하도록 데코레이터 또는 권한 검증 미들웨어를 보강해야 합니다.

### [보안 수준: Medium] 4. 에러 발생 시 원천 raw message 및 payload 정보 외부 노출
* **취약점 위치**:
  * `backend/services/error_message_service.py` 내 `format_error_payload` 함수
  * `backend/routes/admin_inquiries.py` 및 `backend/routes/ml.py` 전체 엔드포인트
* **원인 및 취약점 설명**:
  * `format_error_payload`는 백엔드가 API 응답 시 원본 예외 정보를 가공해 보내는 유틸리티이나, 응답 객체의 `error.raw_message` 키에 날것의 시스템 예외 메시지를 그대로 담아 반환하고 있습니다.
  * 또한 `admin_inquiries.py` 및 `ml.py` 내의 여러 API는 `format_error_payload`를 거치지 않고 직접 `str(e)` 예외 메시지를 JSON 바디에 담아 응답합니다.
  * 이는 프론트엔드가 UI상으로 에러를 숨기더라도 브라우저 개발자 도구(Network 탭)를 통해 원천 예외, 데이터베이스 스택 추적, 라이브러리 타입 에러 등을 고스란히 공격자에게 누출시켜 시스템 정보 수집을 유발할 수 있습니다.
* **권한 권장 조치**:
  * `format_error_payload` 내부에서 프로덕션 모드(예: `ENV == 'PRODUCTION'`)일 때 `raw_message` 및 `raw_payload` 필드를 삭제하거나 빈 값으로 필터링하고 백엔드 서버 로컬 로그에만 안전하게 남겨두어야 합니다. 또한 `admin_inquiries.py`와 `ml.py` 내의 예외 유턴 구문들도 모두 `format_error_payload`를 통하도록 개편해야 합니다.

---

## 3. 더미코드 및 데드코드 검출 목록 (Dummy & Dead Codes)

시스템 최적화 및 유지보수성 향상을 위해 제거 또는 정리해야 할 코드 잔재 목록입니다.

### 3.1 디버깅용 print문 및 강제 출력 잔재
* **발견 위치**:
  * [keys.py:L310, L337](file:///Users/kangheesung/10-19_개발/13_프로젝트/13.05_트레이딩/teamproject/backend/routes/keys.py#L310) (디버깅 print 잔재)
  * [ml.py:L586-587](file:///Users/kangheesung/10-19_개발/13_프로젝트/13.05_트레이딩/teamproject/backend/routes/ml.py#L586-L587) (`traceback.print_exc()` 강제 출력 잔재)
  * `backend/services/` 스케줄러 계열 파일([auto_trading_rule_engine.py](file:///Users/kangheesung/10-19_개발/13_프로젝트/13.05_트레이딩/teamproject/backend/services/auto_trading_rule_engine.py), [open_order_status_sync_service.py](file:///Users/kangheesung/10-19_개발/13_프로젝트/13.05_트레이딩/teamproject/backend/services/open_order_status_sync_service.py) 등)의 로깅 목적 직접 `print` 호출 15여 군데.
* **현상 및 설명**:
  * 개발 중 실시간 동작 확인을 위해 print문을 삽입하였으나 프로덕션 빌드 후에도 콘솔을 어지럽히고 중앙식 로그 수집기 통제에 방해가 됩니다.
  * `frontend/src/components/InvestmentSurveyModal.jsx`의 `console.log("1. onSuccess 호출 전");` 잔재는 2026-07-15에 제거 완료했습니다.
* **조치 제안**:
  * 백엔드는 `current_app.logger` 혹은 `logging` 표준 로거로 모두 이관해야 합니다.

### 3.2 미사용 및 레거시 파일 (Dead Files)
* **발견 위치**:
  * [AdminInquiryPanel.jsx](file:///Users/kangheesung/10-19_개발/13_프로젝트/13.05_트레이딩/teamproject/frontend/src/pages/AdminInquiryPanel.jsx) (사용처 없음, Mock 문의 데이터 `initialInquiries`가 코드에 하드코딩 잔존)
  * [upbit_client.py](file:///Users/kangheesung/10-19_개발/13_프로젝트/13.05_트레이딩/teamproject/backend/services/upbit_client.py) (현재 핵심 가상자산 브로커가 코인원으로 결정됨에 따라 사용되지 않는 참고용 임시 파일. 내부에 임시 대체 매핑 코드 잔존)
  * [ml/test_yf.py](file:///Users/kangheesung/10-19_개발/13_프로젝트/13.05_트레이딩/teamproject/ml/test_yf.py) (yfinance 검증용 로컬 유틸리티 파일)
* **조치 제안**:
  * `AdminInquiryPanel.jsx`는 실제 사용하는 `AdminInquiries.jsx`와 혼동할 우려가 크므로 영구 삭제 조치합니다.
  * `upbit_client.py`는 아카이빙 폴더로 이전하거나 영구 삭제를 제안합니다.
  * `ml/test_yf.py`는 `ml/tests/` 디렉토리를 구축하여 테스트 스위트로 정규 관리하는 것이 권장됩니다.

### 3.3 미사용 선언 변수 및 호이스팅 리스크 (ESLint 분석)
* **발견 위치**:
  * `Dashboard.jsx` (L34 `formatKrw`, L894-896 `encrypted`, `loading`, `message` 등)
  * `Login.jsx` & `Signup.jsx` (L1 `React` 불필요한 import, L9 `loginInputs`, L50 `data` 등)
  * **호이스팅 리스크 (Temporal Dead Zone)**:
    * `Dashboard.jsx` L1180 `loadDashboardWatchlist` const 함수 선언부 이전에 useEffect 내에서 호출하고 있어 TDZ 오류 위험이 감지되었습니다.
    * `TradeHistoryTab.jsx` L419 `syncTradeStatuses` 역시 선언 전 호출 위험이 있습니다.
* **조치 제안**:
  * 미사용 변수와 임포트는 소거 처리를 권장합니다.
  * TDZ 위험을 막기 위해 훅보다 위에 해당 함수 선언부를 올려 정의하도록 리팩토링합니다.

### 3.4 React 19 이펙트 내 직접 상태 변경 (Cascading Render 병목)
* **발견 위치**:
  * `WatchlistTab.jsx` (L131, L632, L642)
  * `Home.jsx` (L436, L462)
  * `News.jsx` (L126)
  * `Inquiry.jsx` (L457, L475)
  * `AdminInquiries.jsx` (L100, Line 210)
  * `AssetLogo.jsx` (L38)
* **현상 및 위험 설명**:
  * 이펙트 내부에서 비동기 보정이나 조건 체크 없이 직후 상태를 변경하는 `setState`를 호출하여, 브라우저가 화면을 렌더링한 직후 추가 상태 변화에 의해 재렌더링하는 루프(Cascading Render) 병목이 식별되었습니다.
* **조치 제안**:
  * `useState` 초기화 시 직접 상태 값을 바인딩하거나, 비동기 핸들러 함수로 로직을 이동시켜 이펙트 내에서의 부작용(Side Effect) 발생을 최소화해야 합니다.
