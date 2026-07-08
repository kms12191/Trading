# Trading Bot 챗봇 작업 정리

작성일: 2026-07-08

이 문서는 웹 대시보드 우측 하단 챗봇 기능을 추가하면서 작업한 파일, 연결 구조, 환경 변수, 토큰 제한, 현재 동작 상태를 팀원이 빠르게 이해할 수 있도록 정리한 문서입니다.

---

## 1. 작업 목표

웹 대시보드에 챗봇을 추가했습니다.

- 우측 하단에 챗봇 아이콘 표시
- 아이콘 클릭 시 카카오톡처럼 대화창 표시
- 사용자의 브라우저 시간대 기준으로 메시지 전송 시간 표시
- OpenAI API를 백엔드에서만 호출
- 시스템 롤과 트레이딩 안전 규칙을 문서 파일로 분리
- function calling 스키마와 실제 도구 연결부를 분리
- 토큰 과사용 방지를 위한 기본 제한값 적용
- Human-in-the-Loop 원칙 유지

중요: 챗봇은 사용자의 명시적 승인 없이 실거래 주문을 실행하지 않습니다.

---

## 2. 프론트엔드 작업 파일

### `frontend/src/features/chatbot/ChatbotWidget.jsx`

챗봇 UI의 핵심 컴포넌트입니다.

주요 역할:

- 우측 하단 챗봇 아이콘 렌더링
- 챗봇 대화창 열기/닫기
- 초기 환영 메시지 표시
- 사용자 메시지 입력 및 전송
- 빠른 질문 버튼 표시
- 메시지별 시간 표시
- 브라우저 시간대 기반 시간 포맷 처리

시간 표시 방식:

```js
Intl.DateTimeFormat().resolvedOptions().timeZone
```

사용자의 브라우저/PC 시간대 기준으로 `오후 1:05` 같은 형식으로 표시됩니다.

현재 초기 메시지:

```js
text: '안녕하세요. AE 트레이딩 챗봇입니다. \n시세, 보유자산, 매매 제안 흐름을 도와드릴게요.'
```

---

### `frontend/src/features/chatbot/chatbotApi.js`

챗봇 프론트에서 백엔드 API를 호출하는 파일입니다.

주요 역할:

- Supabase 세션에서 access token 확인
- Authorization 헤더에 토큰 포함
- 백엔드 `/api/chatbot/message`로 메시지 전송
- 실패 시 사용자 친화 에러 메시지 반환

호출 대상:

```text
POST {VITE_API_BASE_URL}/api/chatbot/message
```

로컬 기준:

```text
프론트엔드: http://localhost:5173
백엔드 API: http://localhost:5050
챗봇 API:  http://localhost:5050/api/chatbot/message
```

---

### `frontend/src/App.jsx`

챗봇 위젯을 전체 앱에 연결했습니다.

추가된 내용:

```jsx
import ChatbotWidget from './features/chatbot/ChatbotWidget.jsx'
```

렌더링 조건:

```jsx
<ChatbotWidget enabled={isLoggedIn && !showAdditionalInfo && !showSurvey} />
```

즉, 로그인 상태이고 추가 정보/투자성향 설문 모달이 떠 있지 않을 때 챗봇이 표시됩니다.

---

### `frontend/public/chatbot-bot.png`

챗봇 아이콘 이미지입니다.

작업 내용:

- 사용자가 제공한 로봇 이미지를 챗봇 아이콘으로 사용
- 이미지 안 말풍선 문구가 보이지 않도록 얼굴 중심으로 크롭
- 512x512 정사각형 아이콘으로 교체

---

### `frontend/public/chatbot-bot-original.png`

원본 이미지 백업 파일입니다.

필요 시 원본 이미지로 되돌리거나 다른 방식으로 다시 편집할 수 있습니다.

---

## 3. 백엔드 작업 파일

### `backend/routes/chatbot.py`

챗봇 API 라우트입니다.

추가된 엔드포인트:

```text
POST /api/chatbot/message
```

주요 역할:

- Authorization 헤더에서 사용자 정보 확인
- `ChatbotService.reply()` 호출
- 성공 시 `{ success: true, data: ... }` 반환
- 실패 시 `format_error_payload()`로 표준 에러 응답 반환

보안상 원문 stack trace나 API key는 응답에 노출하지 않습니다.

---

### `backend/app.py`

챗봇 Blueprint를 Flask 앱에 등록했습니다.

추가된 import:

```python
from backend.routes.chatbot import chatbot_bp
```

추가된 등록:

```python
app.register_blueprint(chatbot_bp)
```

---

### `backend/services/chatbot/chat_service.py`

챗봇 대화 흐름을 관리하는 서비스입니다.

현재 역할:

- 사용자 입력 공백 검증
- 시스템 프롬프트 로드
- `ChatbotLLMClient`를 통해 OpenAI 호출
- function calling 스키마 전달
- 응답과 메타 정보 반환

현재 연결 구조:

```python
result = self.llm_client.generate_reply(
    system_prompt=self.system_prompt,
    user_message=text,
    user_id=user_id,
    function_schemas=FUNCTION_SCHEMAS,
)
```

---

### `backend/services/chatbot/llm_client.py`

OpenAI API 호출과 챗봇 사용량 제한을 담당하는 파일입니다.

주요 역할:

- `OPENAI_API_KEY` 읽기
- `OPENAI_MODEL` 읽기
- OpenAI Chat Completions API 호출
- 입력 길이 제한
- 응답 토큰 제한
- 분당 요청 횟수 제한
- 일일 토큰 사용량 제한
- function calling 도구 전달 개수 제한

OpenAI 호출 URL:

```text
https://api.openai.com/v1/chat/completions
```

현재 기본 제한값:

```env
CHATBOT_MAX_INPUT_CHARS=2000
CHATBOT_MAX_OUTPUT_TOKENS=1024
CHATBOT_MAX_HISTORY_MESSAGES=16
CHATBOT_MAX_TOOL_CALLS=3
CHATBOT_MINUTE_REQUEST_LIMIT=10
CHATBOT_DAILY_TOKEN_LIMIT=50000
```

주의:

- 현재 일일 토큰 사용량 제한은 서버 메모리 기준입니다.
- 백엔드를 재시작하면 메모리 기반 사용량 카운터는 초기화됩니다.
- 운영 수준으로 가려면 Supabase 테이블에 사용자별 사용량을 저장하는 방식이 더 안전합니다.

---

### `backend/services/chatbot/function_calling.py`

OpenAI function calling에 전달할 함수 스키마 정의 파일입니다.

현재 정의된 도구:

- `get_price`
- `get_holdings`
- `create_trade_proposal`

중요:

이 파일은 "OpenAI에게 어떤 기능을 호출할 수 있는지 알려주는 스키마"입니다.
실제 기능 실행은 여기서 하지 않습니다.

---

### `backend/services/chatbot/tool_registry.py`

실제 기능 연결부로 사용할 파일입니다.

현재 상태:

- 사용 가능한 도구 이름만 반환
- 실제 시세 조회/보유자산 조회/매매 제안 생성 실행 로직은 아직 연결하지 않음

향후 연결 예정:

- `get_price` -> 기존 차트/시세 API 또는 거래소 클라이언트 연결
- `get_holdings` -> 대시보드/자산 조회 백엔드 로직 연결
- `create_trade_proposal` -> `trade_proposals` 생성 흐름 연결

실거래 주문은 반드시 사용자 승인 카드 이후 서버 검증을 거쳐야 합니다.

---

### `backend/services/chatbot/prompt_registry.py`

시스템 프롬프트 파일들을 읽어서 하나의 system prompt로 합치는 파일입니다.

현재 읽는 파일:

```python
load_prompt("system_role.md")
load_prompt("trading_rules.md")
```

---

### `backend/services/chatbot/prompts/system_role.md`

챗봇의 기본 시스템 롤입니다.

여기서 설정하는 내용:

- 챗봇의 역할
- 말투
- 답변 방식
- 민감정보 노출 금지
- 투자 판단 단정 금지

팀원이 시스템 롤을 수정할 때는 이 파일을 먼저 확인하면 됩니다.

---

### `backend/services/chatbot/prompts/trading_rules.md`

트레이딩 안전 규칙 파일입니다.

여기서 설정하는 내용:

- AI가 임의로 실거래 주문 실행 금지
- 매수/매도 요청은 먼저 매매 제안으로 생성
- 실거래 전 서버 검증 필수
- 모의투자와 실거래 구분
- 사용자가 이해하기 쉬운 상태 설명

---

### `backend/services/chatbot/safety_guard.py`

챗봇 안전 규칙을 코드 레벨에서 보조하는 파일입니다.

현재 내용:

- 사용자 승인 없이 주문 실행 불가
- 실제 주문은 사용자 승인과 서버 검증 뒤에만 실행한다는 안내 문구 제공

---

### `backend/services/chatbot/__init__.py`

챗봇 서비스 패키지 초기화 파일입니다.

---

## 4. 환경 변수 작업

### `backend/.env`

실제 OpenAI API 키가 들어가는 파일입니다.

확인 완료:

```text
OPENAI_API_KEY=FOUND
OPENAI_MODEL=FOUND
```

주의:

- 실제 API key 값은 문서나 로그에 남기면 안 됩니다.
- 프론트엔드 `.env`에는 절대 넣지 않습니다.

---

### `.env.example`

팀원들이 설정값을 알 수 있도록 예시를 추가했습니다.

추가된 값:

```env
OPENAI_MODEL=gpt-4.1-mini

CHATBOT_MAX_INPUT_CHARS=2000
CHATBOT_MAX_OUTPUT_TOKENS=1024
CHATBOT_MAX_HISTORY_MESSAGES=16
CHATBOT_MAX_TOOL_CALLS=3
CHATBOT_MINUTE_REQUEST_LIMIT=10
CHATBOT_DAILY_TOKEN_LIMIT=50000
```

이미 있던 값:

```env
OPENAI_API_KEY=replace-me
```

---

## 5. 현재 동작 확인 결과

백엔드 재시작 후 챗봇 API 연결 확인 완료.

테스트 엔드포인트:

```text
POST http://localhost:5050/api/chatbot/message
```

결과:

```text
STATUS=200
success=true
model=gpt-4.1-mini
total_tokens=429
```

OpenAI 응답도 정상 수신했습니다.

---

## 6. 포트 구조

로컬 개발 포트는 아래와 같습니다.

```text
프론트엔드 화면: http://localhost:5173
백엔드 API:     http://localhost:5050
챗봇 API:      http://localhost:5050/api/chatbot/message
```

프론트엔드가 직접 OpenAI를 호출하지 않습니다.
프론트엔드는 백엔드 챗봇 API만 호출합니다.

---

## 7. 보안 원칙

이 챗봇 작업은 `agents.md` 기준을 반영했습니다.

반영한 원칙:

- Human-in-the-Loop 유지
- 사용자 승인 전 실거래 실행 금지
- API key 프론트 노출 금지
- 거래소 key는 기존 백엔드/DB 암호화 흐름 사용
- 원문 예외와 stack trace를 사용자에게 그대로 노출하지 않음
- 시스템 롤과 트레이딩 규칙을 코드에서 분리
- function calling 스키마와 실제 도구 실행부를 분리

---

## 8. 아직 남은 작업

현재 챗봇은 OpenAI 응답까지 연결되어 있습니다.
다만 실제 기능 호출은 아직 완전히 연결하지 않았습니다.

다음 작업 후보:

1. `tool_registry.py`에 실제 도구 실행 함수 연결
2. `get_price`를 기존 시세/차트 API 또는 거래소 클라이언트와 연결
3. `get_holdings`를 대시보드/내 자산 보유 현황 로직과 연결
4. `create_trade_proposal`을 `trade_proposals` 생성 흐름과 연결
5. function calling 결과를 다시 OpenAI 응답에 반영하는 multi-step 호출 처리
6. 사용자별 챗봇 대화 기록 저장
7. 사용자별 토큰 사용량을 Supabase에 영구 저장
8. 챗봇 요청 로그 및 에러 추적 강화
9. 실제 매매 제안 카드와 챗봇 대화를 연결

---

## 9. 주의할 점

챗봇이 "매수해줘", "팔아줘" 같은 요청을 받아도 직접 주문을 실행하면 안 됩니다.

올바른 흐름:

```text
사용자 요청
-> 챗봇 분석
-> 매매 제안 생성
-> 사용자 승인
-> 서버 권한/잔고/주문 가능 상태 검증
-> 주문 실행
-> 거래내역 및 상태 동기화
```

이 흐름을 벗어나는 직접 실거래 실행은 금지입니다.

