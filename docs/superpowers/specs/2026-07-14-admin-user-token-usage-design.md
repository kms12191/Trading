# 관리자 유저별 실제 챗봇 토큰 사용량 설계

## 목표

관리자 페이지에 `유저 관리` 탭을 추가해 사용자별 챗봇 실제 토큰 사용량을 확인할 수 있게 한다. 기존 `chatbot_usage_counters`는 요청 전 한도 차감용 추정 카운터로 유지하고, OpenAI 응답에서 반환되는 실제 usage를 별도 로그 테이블에 기록한다.

이번 범위는 조회와 관찰 중심이다. 사용자 계정 정지, 권한 변경, API 키 열람/삭제 같은 위험한 운영 기능은 구현하지 않는다.

## 현재 구조

- 프론트엔드 관리자 화면은 `frontend/src/pages/AdminMlData.jsx`의 내부 탭으로 `ML 데이터 관리`, `사용자 문의 관리`를 제공한다.
- 모바일 관리자 화면은 `frontend/src/pages/mobile/MobileAdminMlData.jsx`에 같은 탭 구조를 가진다.
- 문의 관리 백엔드는 `backend/routes/admin_inquiries.py`에서 Supabase 사용자 검증과 `profiles.role === ADMIN` 확인 패턴을 사용한다.
- 챗봇 LLM 호출은 `backend/services/chatbot/llm_client.py`에서 OpenAI Chat Completions 응답의 `usage`를 이미 읽어 반환한다.
- `chatbot_usage_counters`는 실제 usage가 아니라 호출 전 추정 토큰을 저장한다.

## 데이터 모델

새 migration으로 `public.chatbot_token_usage_logs`를 만든다.

주요 컬럼:

- `id UUID PRIMARY KEY DEFAULT gen_random_uuid()`
- `user_id UUID NOT NULL REFERENCES public.profiles(id) ON DELETE CASCADE`
- `request_id TEXT`
- `request_type TEXT NOT NULL`
- `model TEXT NOT NULL`
- `prompt_tokens INTEGER NOT NULL DEFAULT 0`
- `completion_tokens INTEGER NOT NULL DEFAULT 0`
- `total_tokens INTEGER NOT NULL DEFAULT 0`
- `created_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc', now())`

제약:

- 토큰 컬럼은 0 이상이어야 한다.
- `request_type`은 1차에서 `chat_reply`, `tool_synthesis`, `title_or_summary` 같은 문자열을 허용한다. DB enum은 사용하지 않아 후속 요청 유형 추가 비용을 낮춘다.
- 대화 원문, tool payload, 계좌 정보, API 키, 거래소 raw 응답은 저장하지 않는다.

RLS:

- 일반 사용자는 자신의 로그만 조회할 수 있다.
- 삽입은 백엔드가 사용자 JWT 또는 로컬 debug/service role 경로로 수행하되 `user_id`를 명시한다.
- 관리자 전체 조회는 백엔드 service role 기반 관리자 API를 통해서만 제공한다. 프론트에서 직접 전체 로그 테이블을 조회하지 않는다.

인덱스:

- `(user_id, created_at DESC)`
- `(created_at DESC)`
- 관리자 집계가 느려지면 후속으로 일별 materialized view 또는 집계 테이블을 추가한다.

## 백엔드

### 실제 사용량 기록

`ChatbotLLMClient`에 usage 기록 helper를 추가한다.

- OpenAI 응답의 `usage.prompt_tokens`, `usage.completion_tokens`, `usage.total_tokens`를 정수로 정규화한다.
- usage가 없거나 `total_tokens <= 0`이면 로그를 남기지 않는다.
- 로그 저장 실패는 챗봇 응답 자체를 실패시키지 않는다. 대신 서버 로그에만 남긴다.
- `generate_reply()`는 `request_type="chat_reply"`로 기록한다.
- `synthesize_tool_result_reply()`는 `request_type="tool_synthesis"`로 기록한다. 현재 이 메서드는 auth/user 인자가 없으므로 호출부에서 전달하거나, 메서드 시그니처를 확장해 사용자 컨텍스트를 받게 한다.

### 관리자 API

새 라우트 모듈 `backend/routes/admin_users.py`를 추가하고 `backend/app.py`에 등록한다.

`GET /api/admin/users`

- ADMIN만 전체 조회 가능하다.
- 응답은 사용자 목록과 토큰 집계를 함께 반환한다.
- 지원 쿼리:
  - `q`: 이메일 또는 닉네임 검색
  - `sort`: `today_tokens`, `tokens_7d`, `tokens_30d`, `total_tokens`, `recent_used_at`, `created_at`
  - `order`: `asc` 또는 `desc`
  - `limit`: 기본 50, 최대 200
- 각 사용자 row:
  - `id`, `email`, `nickname`, `role`, `updatedAt`
  - `usage.todayTokens`, `usage.tokens7d`, `usage.tokens30d`, `usage.totalTokens`
  - `usage.todayRequests`, `usage.requests30d`, `usage.recentUsedAt`

`GET /api/admin/users/<user_id>/chatbot-usage`

- ADMIN만 조회 가능하다.
- 지원 쿼리:
  - `days`: 기본 30, 최대 180
  - `limit`: 최근 로그 기본 50, 최대 200
- 응답:
  - 사용자 기본 정보
  - 일별 `date`, `promptTokens`, `completionTokens`, `totalTokens`, `requestCount`
  - request type별 합계
  - 최근 요청 로그 `createdAt`, `requestType`, `model`, `promptTokens`, `completionTokens`, `totalTokens`

에러 응답:

- 사용자 화면으로 전달되는 실패는 `format_error_payload()`를 사용한다.
- 권한 없음, 설정 누락, Supabase 조회 실패를 구분해 한국어 안내를 반환한다.

## 프론트엔드

### 데스크톱

`frontend/src/pages/AdminMlData.jsx` 내부 탭에 `유저 관리`를 추가한다.

구성:

- 상단 요약 카드:
  - 전체 유저 수
  - 오늘 실제 토큰
  - 30일 실제 토큰
  - 최근 24시간 활성 유저
- 검색/정렬 컨트롤:
  - 이메일/닉네임 검색
  - 정렬 기준 선택
  - 오름차순/내림차순
- 사용자 테이블:
  - 유저
  - 권한
  - 오늘 토큰
  - 7일 토큰
  - 30일 토큰
  - 전체 토큰
  - 최근 사용 시각
- 사용자 상세 패널:
  - 일별 사용량 막대형 리스트
  - 요청 유형별 합계
  - 최근 요청 로그

### 모바일

`frontend/src/pages/mobile/MobileAdminMlData.jsx`에도 같은 탭을 추가한다. 모바일에서는 테이블 대신 사용자별 카드 목록을 사용하고, 상세 정보는 확장 패널로 보여준다.

스타일:

- `design.md`의 Obsidian Navy 배경, Slate border, AI Cyan 강조 색상을 따른다.
- 숫자는 `font-mono`를 사용한다.
- 긴 이메일은 `truncate` 또는 `break-all`로 처리한다.
- 360px, 430px, 768px, 1280px 폭에서 버튼/텍스트 겹침이 없어야 한다.

## 부가 기능 후보

이번 1차에 포함:

- 사용자 검색
- 토큰 사용량 정렬
- 기간별 집계
- 최근 사용 시각 표시
- 과다 사용 사용자 시각적 강조

후속 후보:

- 사용자별 일일 한도 override
- 관리자 메모
- 사용자 상세에서 문의 이력 연결
- 사용자별 거래 제안 수와 실패율
- 사용자별 API 키 등록 상태 요약
- 계정 상태 변경 또는 역할 변경

후속 후보 중 API 키 원문 열람, 암호화 비밀 복호화 노출, 관리자 임의 주문 실행은 보안상 제외한다.

## 테스트

백엔드:

- usage 정규화와 저장 helper 단위 테스트
- usage 저장 실패가 챗봇 응답을 실패시키지 않는 테스트
- 관리자 API가 ADMIN이 아니면 403을 반환하는 테스트
- 사용자 목록 집계가 오늘/7일/30일/전체 토큰을 올바르게 계산하는 테스트
- 상세 API가 일별 합계와 최근 로그를 반환하는 테스트

프론트엔드:

- 사용자 목록 API 응답을 표/카드로 렌더링하는 테스트
- 검색/정렬 상태가 요청 쿼리로 반영되는 테스트
- 빈 상태와 실패 상태 표시 테스트
- 모바일 폭에서 텍스트 overflow와 버튼 겹침이 없는지 브라우저 또는 Playwright로 확인한다.

## 비범위

- OpenAI 비용 금액 계산은 이번 범위에서 제외한다. 모델별 가격은 변동 가능성이 높아 별도 최신 가격 소스 검증이 필요하다.
- 토큰 사용량 기반 자동 과금, 자동 차단, 사용자 통지는 구현하지 않는다.
- 기존 `chatbot_usage_counters`의 한도 차감 로직을 대체하지 않는다.
