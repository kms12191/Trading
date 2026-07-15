# Trading Bot 챗봇 작업 정리

작성일: 2026-07-08

이 문서는 웹 대시보드 우측 하단 챗봇 기능을 추가하면서 작업한 파일, 연결 구조, 환경 변수, 토큰 제한, 현재 동작 상태를 팀원이 빠르게 이해할 수 있도록 정리한 문서입니다.

---

## 1. 작업 목표

웹 대시보드에 챗봇을 추가했습니다.

- 우측 하단에 챗봇 아이콘 표시
- 아이콘 클릭 시 카카오톡처럼 대화창 표시
- 사용자의 브라우저 시간대 기준으로 메시지 전송 시간 표시
- 사용자의 브라우저 시간대 기준으로 챗봇 상대 날짜 해석
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
- 챗봇 API 요청 시 브라우저 시간대 전달

시간 표시 방식:

```js
Intl.DateTimeFormat().resolvedOptions().timeZone
```

사용자의 브라우저/PC 시간대 기준으로 `오후 1:05` 같은 형식으로 표시됩니다.
같은 시간대 값을 백엔드에도 전달해 "오늘", "어제", "최근", "이번 주", "지난달" 같은 표현을 사용자의 시간대 기준으로 해석하게 합니다.

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
- 요청 시점의 현재 날짜/시간 문맥을 시스템 프롬프트에 추가
- 로그인 사용자의 `profiles.invest_type`, `profiles.invest_score`를 조회해 투자성향 문맥을 시스템 프롬프트에 추가
- 사용자별 최근 대화 히스토리를 서버 메모리에 보관해 OpenAI 요청에 함께 전달
- `조회해도 돼`, `진행해`, `응` 같은 후속 답변을 직전 pending action과 연결
- `knowledge_chunks` pgvector 검색 결과를 RAG 참고자료로 시스템 프롬프트에 추가
- `ChatbotLLMClient`를 통해 OpenAI 호출
- function calling 스키마 전달
- 응답과 메타 정보 반환

현재 연결 구조:

```python
tool_result = run_chatbot_tool(auth_header, text)
if tool_result:
    return {
        "reply": tool_result["reply"],
        ...
    }

result = self.llm_client.generate_reply(...)
```

현재는 먼저 프로젝트 내부 기능 도구를 확인하고, 해당하지 않는 일반 질문만 OpenAI 응답으로 넘깁니다.
OpenAI로 넘어가는 일반 질문에는 현재 날짜/시간, 투자성향 문맥, RAG 참고자료가 함께 붙을 수 있습니다.

현재 날짜/시간 처리:

- 프론트엔드가 `Intl.DateTimeFormat().resolvedOptions().timeZone` 값으로 사용자 브라우저 시간대를 보냅니다.
- 백엔드는 해당 시간대를 기준으로 오늘 날짜, 요일, 현재 시각을 요청마다 동적으로 계산합니다.
- 시간대가 없거나 잘못된 값이면 `Asia/Seoul` 기준으로 처리합니다.
- "오늘", "어제", "최근", "이번 주", "지난달" 같은 상대 날짜 표현은 이 문맥을 기준으로 해석하도록 시스템 프롬프트에 넣습니다.
- 날짜가 중요한 뉴스, 공시, 거래내역, 차트 요청은 가능한 경우 해석한 날짜 범위를 답변이나 도구 호출에 반영하도록 안내합니다.

대화 문맥 처리:

- 최근 대화는 사용자별 서버 메모리에 최대 12개 메시지까지 보관합니다.
- OpenAI 호출 시 `system prompt + 최근 대화 + 현재 질문` 형태로 전달합니다.
- 챗봇이 "포트폴리오 요약부터 조회해도 될까요?"처럼 읽기 기능 허락을 구하면 `pending_action=portfolio_summary`를 저장합니다.
- 사용자가 이어서 "조회해도 돼", "진행해", "응"처럼 답하면 보류된 읽기 기능을 실행합니다.
- 매수/매도 같은 실거래 주문은 pending action으로 자동 실행하지 않습니다.

투자성향 반영 흐름:

```python
profile_context = load_user_investment_profile_context(auth_header, user_id)
system_prompt = f"{base_system_prompt}\n\n{profile_context}"
```

투자성향 정보가 없거나 조회에 실패하면 기본 시스템 프롬프트만 사용합니다. 따라서 프로필 조회 오류가 챗봇 응답 전체를 막지는 않습니다.

---

### `backend/services/chatbot/rag_service.py`

Supabase `knowledge_chunks` pgvector 검색 결과를 챗봇 참고자료로 변환하는 서비스입니다.

주요 역할:

- 사용자 질문을 OpenAI Embeddings API로 벡터화
- Supabase RPC `match_knowledge_chunks` 호출
- 검색된 chunk의 `source_type`, `source_id`, `chunk_text`, `similarity`를 참고자료로 정리
- 정리된 참고자료를 `chat_service.py`의 시스템 프롬프트 뒤에 추가
- RAG 조회 실패 시 챗봇 전체가 멈추지 않도록 빈 참고자료로 처리

현재 연결된 RPC:

```text
POST /rest/v1/rpc/match_knowledge_chunks
```

현재 기대하는 RPC 인자:

```text
query_embedding
match_user_id
match_count
match_threshold
```

현재 기대하는 RPC 반환값:

```text
source_type
source_id
chunk_text
similarity
rank_score
metadata
```

주의:

- `knowledge_chunks.embedding`에 실제 embedding 값이 들어 있어야 검색 결과가 나옵니다.
- RPC 인자명이 Supabase 함수와 다르면 RAG 참고자료가 비어 있을 수 있습니다.
- RAG는 참고자료 보강용이며, 기존 프로젝트 도구 조회와 실거래 승인 흐름을 대체하지 않습니다.

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
CHATBOT_INTERNAL_API_BASE_URL=http://localhost:5050
```

주의:

- 현재 일일 토큰 사용량 제한은 서버 메모리 기준입니다.
- 백엔드를 재시작하면 메모리 기반 사용량 카운터는 초기화됩니다.
- 운영 수준으로 가려면 Supabase 테이블에 사용자별 사용량을 저장하는 방식이 더 안전합니다.

---

### `backend/services/chatbot/function_calling.py`

OpenAI function calling에 전달할 함수 스키마 정의 파일입니다.

현재 정의된 도구:

- `get_home_market_rankings`
- `get_portfolio_summary`
- `add_watchlist_item`
- `get_holdings`
- `search_trade_history`
- `get_exchange_rate`

중요:

이 파일은 "OpenAI에게 어떤 기능을 호출할 수 있는지 알려주는 스키마"입니다.
실제 기능 실행은 여기서 하지 않습니다.

---

### `backend/services/chatbot/tool_registry.py`

실제 기능 연결부로 사용할 파일입니다.

현재 상태:

- 홈 필터별 순위 조회 연결
- 평가 자산/주문가능금액 조회 연결
- 관심종목 추가 연결
- 보유 주식/코인 현황 조회 연결
- 거래내역 조건 조회 연결
- 코인 통합 분석 연결
  - `get_crypto_market_context`는 Coinone/Binance 코인 질문에 대해 현재가, 호가, 최근 캔들 흐름, crypto ML 활성 신호, 거래소별 주의사항을 한 번에 묶어 반환합니다.
  - 최우선 매수/매도 호가 기준 스프레드, 예상 매수/매도 슬리피지, 최우선 호가 잔량 금액을 계산해 단타·진입 질문의 유동성 위험을 함께 표시합니다.
  - "내", "보유", "팔까", "수익", "비중" 같은 개인 보유 문맥이 있으면 Coinone/Binance 잔고 요약에서 해당 코인의 수량, 평균단가, 평가금액, 수익률, 포트폴리오 비중을 함께 표시합니다.
  - Coinone BTC/ETH 분석에서는 Binance 현물 기준가와 USDT/KRW 환율을 사용해 김치프리미엄 또는 디스카운트를 참고 지표로 표시합니다.
  - 코인 분석은 24시간 시장 특성을 기준으로 설명하며, ML 신호는 매매 실행 명령이 아니라 참고용 단기 신호로만 표시합니다.
  - Coinone는 KRW 현물/지정가 제안 중심, Binance는 USDT 현물 또는 선물 리스크 구분을 유지합니다.
- 실제 주문 실행 기능은 연결하지 않음

홈 필터별 순위 조회 주의사항:

- 챗봇 순위 조회는 홈 화면과 같은 `/api/home/market` 데이터를 기준으로 사용합니다.
- 홈 화면의 `applyClientMarketFilters`와 같은 방식으로 지역 필터와 상승률/하락률/거래량/거래대금 정렬을 적용합니다.
- `/api/market/rankings`를 직접 호출하면 홈 화면 필터 결과와 다른 랭킹 소스를 탈 수 있으므로, 챗봇의 "홈 필터별 순위" 기능에서는 사용하지 않습니다.
- `/api/market/rankings`는 `MarketRankings.jsx`의 전체 순위/더보기 화면에서 아직 사용하므로 백엔드 라우트는 유지합니다.
- 챗봇 도구명은 혼동을 줄이기 위해 `get_home_market_rankings`로 정리했습니다.

현재 연결된 챗봇 질문 예시:

```text
국내 거래대금 순위 상위 5개 보여줘
국내 상승률 순위 상위 3개 보여줘
지금 내 돈 얼마 있어?
삼성전자 관심종목 설정해줘
토스에 내 주식 뭐뭐 있어?
30만원 이상의 거래내역 다 뽑아줘
삼성전자 거래내역만 보여줘
리플 코인 분석해줘
BTC 단기 진입 타이밍 어때?
```

향후 연결 예정:

- 뉴스/공시 요약
- 실시간 환율 단독 조회
- 조건주문 제안
- `create_trade_proposal` 기반 매매 제안 생성
- 주문 정정/취소 후 재주문 제안 생성

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

- 챗봇의 역할: AI 트레이딩 보조 챗봇이자 투자 전문가형 금융자산 운용 보조자
- 말투
- 답변 방식
- 민감정보 노출 금지
- 투자 판단 단정 금지
- 사용자 투자성향 기반 제안 강도 조절

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
OPENAI_EMBEDDING_MODEL=text-embedding-3-small

CHATBOT_MAX_INPUT_CHARS=2000
CHATBOT_MAX_OUTPUT_TOKENS=1024
CHATBOT_MAX_HISTORY_MESSAGES=16
CHATBOT_MAX_TOOL_CALLS=3
CHATBOT_MINUTE_REQUEST_LIMIT=10
CHATBOT_DAILY_TOKEN_LIMIT=50000
CHATBOT_RAG_TOP_K=5
CHATBOT_RAG_MAX_CONTEXT_CHARS=6000
CHATBOT_RAG_MATCH_THRESHOLD=0.2
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


---

## 10. 챗봇 검색 Fallback 구조 보강 - 2026-07-09

### 목표

챗봇이 뉴스, 공시, 최신 이슈를 조회할 때 Tavily를 기본 검색 엔진처럼 바로 쓰지 않고, 내부 자산을 먼저 사용한 뒤 마지막 보루로만 사용하도록 변경했습니다.

### 적용된 검색 우선순위

```text
1. Vector DB
   - knowledge_chunks
   - match_knowledge_chunks RPC
   - 이미 저장된 요약/임베딩 지식 우선 사용

2. 내부 DB 원문/요약
   - 뉴스: news_articles
   - 공시: dart_disclosures, dart_disclosure_analyses

3. 기존 Open API
   - 뉴스: Naver News API, Finnhub API
   - 공시: OpenDART API
   - 조회 결과는 가능하면 DB에 저장해 다음 검색부터 재사용

4. Tavily Fallback
   - 위 단계에서 결과가 없거나 부족할 때만 사용
   - Tavily 결과는 OpenAI 요약을 거쳐 답변
   - 원문 출처 URL을 답변에 함께 표시
```

### 수정/추가 파일

- `backend/services/tavily_client.py`
  - Tavily Search API 호출 전용 클라이언트입니다.
  - `TAVILY_API_KEY`, `TAVILY_SEARCH_DEPTH`, `TAVILY_TIMEOUT_SECONDS`를 사용합니다.

- `backend/services/chatbot/web_fallback_search_service.py`
  - 챗봇 뉴스/공시/웹 검색 fallback 흐름을 담당합니다.
  - RAG -> DB -> Naver/Finnhub/DART -> Tavily 순서로 검색합니다.
  - Tavily 결과는 `NewsSummaryService`를 통해 OpenAI로 요약합니다.

- `backend/services/chatbot/tool_registry.py`
  - `search_web` 도구를 계층형 fallback 서비스에 연결했습니다.
  - 기존 거래내역, 보유자산, 환율, 순위 도구가 먼저 처리되고, 뉴스/공시/최신 검색성 질문만 fallback 검색으로 넘어가도록 유지했습니다.

- `backend/services/chatbot/function_calling.py`
  - `search_web` function schema를 추가했습니다.

- `.env.example`
  - Tavily 및 챗봇 검색 fallback 설정 예시를 추가했습니다.

- `backend/tests/test_chatbot_trade_history.py`
  - 챗봇 웹 검색 라우팅 테스트를 추가했습니다.

### 추가된 환경변수

```env
TAVILY_API_KEY=replace-me
TAVILY_SEARCH_DEPTH=basic
TAVILY_TIMEOUT_SECONDS=20
CHATBOT_TAVILY_FALLBACK_ENABLED=true
CHATBOT_WEB_SEARCH_MAX_RESULTS=5
```

### 현재 키 연결 상태

`backend/.env`에서 아래 항목 사용을 전제로 동작합니다.

```text
OPENAI_API_KEY
NAVER_CLIENT_ID
NAVER_CLIENT_SECRET
FINNHUB_API_KEY
DART_API_KEY
TAVILY_API_KEY
```

주의: `TAVILY_API_KEY = ...`처럼 `=` 앞뒤에 공백이 있어도 대부분의 dotenv 로더는 처리하지만, 안전하게는 `TAVILY_API_KEY=...` 형태를 권장합니다.

### 동작 예시

```text
삼성전자 최신 뉴스 찾아줘
테슬라 최근 이슈 검색해줘
현대건설 최근 공시 알려줘
리플 관련 최근 뉴스 찾아봐
```

위 질문이 들어오면 챗봇은 Tavily부터 호출하지 않고, 저장된 벡터 DB와 내부 DB, 기존 뉴스/공시 API를 먼저 확인합니다.

Tavily는 내부 결과가 부족할 때만 최후 fallback으로 호출됩니다.

### 비용/쿼터 보호

- Tavily 무료 플랜 호출량을 아끼기 위해 기본 검색 경로에서 제외했습니다.
- Tavily 호출 결과는 답변에 `출처: Tavily + OpenAI 요약`으로 표시합니다.
- OpenAI 요약은 상위 검색 결과만 사용하도록 제한했습니다.

## 2026-07-10 챗봇 전망형 질문 종목 인식 보강

### 문제

`GST의 전망은?`처럼 짧은 영문 심볼과 전망 키워드가 함께 들어온 질문이 종목 조회 도구로 연결되지 않고 일반 LLM 답변으로 빠졌습니다.

기존 라우팅은 `거래내역`, `관심종목`, `환율`, `뉴스`, `공시`, `보유` 같은 명확한 조회 키워드가 있을 때만 프로젝트 도구를 호출했습니다. 그래서 `전망`, `분석`, `오를까`, `어때` 같은 투자 판단형 질문은 종목 lookup을 거치지 못했습니다.

### 수정 내용

- `backend/services/chatbot/tool_registry.py`
  - `get_asset_outlook()` 도구를 추가했습니다.
  - `전망`, `분석`, `오를까`, `어때`, `괜찮아`, `살까`, `투자해도` 키워드가 포함된 질문을 전망형 질문으로 분류합니다.
  - `GST의 전망은?` 같은 문장에서 `GST`를 먼저 영문 심볼 후보로 추출합니다.
  - `/api/symbol/lookup`으로 종목명/종목코드/코인 심볼을 확인한 뒤, 확인된 종목 기준으로 RAG/뉴스/공시/웹 검색 fallback 흐름에 연결합니다.
  - 종목을 찾지 못한 경우에도 명확한 영문 심볼이면 해당 심볼 기준으로 검색을 시도합니다.

### 기대 동작

```text
GST의 전망은?
삼성전자 전망은?
리플 오를까?
테슬라 지금 사도 괜찮아?
```

위 질문은 일반 답변으로 바로 빠지지 않고, 종목 인식 후 저장된 RAG/DB/뉴스/공시/API/Tavily fallback 검색 흐름을 사용합니다.

응답은 다음과 같은 형태로 시작합니다.

```text
GST 기준으로 확인한 전망 참고자료입니다.
...
```

또는 종목 lookup에 성공하면:

```text
GST(083450) 기준으로 확인한 전망 참고자료입니다.
...
```

### 주의

- `GST`처럼 짧은 영문 심볼은 주식, 코인, 해외 티커, 일반 약어가 충돌할 수 있습니다.
- 가장 정확한 결과를 위해 `/api/symbol/lookup`과 `kis_stock_master`, 코인 메타데이터가 최신 상태여야 합니다.
- 전망 답변은 투자 조언이 아니라 참고 분석이며, 실거래 실행은 기존 Human-in-the-Loop 승인 구조를 따라야 합니다.

## 2026-07-10 챗봇 미체결 주문 조회 도구 추가

### 목적

주문 취소, 주문 정정, 취소 후 재주문 제안 기능을 붙이기 전에 사용자가 챗봇에서 현재 미체결 주문을 먼저 확인할 수 있도록 조회 도구를 추가했습니다.

### 수정/추가 내용

- `backend/services/chatbot/tool_registry.py`
  - `list_open_orders()` 도구를 추가했습니다.
  - `PENDING`, `APPROVED`, `ORDERED`, `OPEN`, `PARTIALLY_FILLED`, `MODIFIED` 상태를 미체결 주문으로 취급합니다.
  - `trade_proposals`에서 로그인 사용자의 미체결 주문을 조회합니다.
  - 거래소, 모의/실전, 종목명/종목코드 조건이 있으면 필터에 반영합니다.
  - 응답에는 날짜, 거래소, 계좌환경, 종목명, 매수/매도, 수량, 지정가, 주문금액, 상태를 표시합니다.

- `backend/services/chatbot/function_calling.py`
  - OpenAI function calling 스키마에 `list_open_orders`를 추가했습니다.

- `backend/services/chatbot/chat_service.py`
  - OpenAI가 `list_open_orders` tool call을 선택했을 때 실제 `list_open_orders()` 도구가 실행되도록 연결했습니다.

### 사용 예시

```text
미체결 주문 보여줘
미체결 주문 조회해줘
코인원 미체결 주문 알려줘
토스 실전 미체결 주문 보여줘
리플 미체결 주문 조회해줘
```

### 현재 범위

- 현재 단계는 조회 전용입니다.
- 실제 주문 취소, 주문 정정, 취소 후 재주문은 아직 실행하지 않습니다.
- 다음 단계에서 `주문 취소 제안/승인`, `주식 주문 정정 제안`, `코인 취소 후 재주문 제안`으로 확장할 수 있습니다.

## 2026-07-13 챗봇 종목 별칭 정규화 및 후보 선택 보강

### 목적

사용자가 `현대건설우 전망은?`, `현대그린푸드 거래내역 보여줘`, `리플 시세 알려줘`처럼 종목명, 별칭, 코인 한글명을 섞어 입력해도 챗봇이 같은 종목으로 안정적으로 인식하도록 보강했습니다.

### 수정 내용

- `backend/services/chatbot/tool_registry.py`
  - `normalize_symbol_alias()` 흐름을 명시적으로 추가했습니다.
  - 사용자 입력은 `_extract_symbol_query()` → `normalize_symbol_alias()` → `/api/symbol/lookup` 순서로 처리합니다.
  - 국내 주요 종목 별칭을 추가했습니다.
    - 예: `현대건설 -> 000720`, `현대건설우 -> 000725`, `현대그린푸드 -> 453340`, `두산에너빌리티 -> 034020`
  - 코인 별칭을 추가했습니다.
    - 예: `리플 -> XRP`, `이더리움 -> ETH`, `수이 -> SUI`, `체인링크 -> LINK`
  - `/api/symbol/lookup` 실패 시 `/api/symbol/search`로 유사 후보를 조회합니다.
  - 후보가 1개면 자동 선택합니다.
  - 후보가 여러 개면 `어떤 종목을 말하나요?` 안내와 함께 종목 상세 화면으로 이동하는 버튼을 내려줍니다.

- `backend/services/chatbot/chat_service.py`
  - OpenAI function calling이 `get_asset_outlook`을 호출할 수 있도록 실제 도구 매핑을 추가했습니다.

- `backend/services/chatbot/function_calling.py`
  - `get_asset_outlook` function schema를 추가했습니다.

- `frontend/src/features/chatbot/ChatbotWidget.jsx`
  - 기존 챗봇 액션 버튼 구조를 그대로 사용합니다.
  - 백엔드가 `type: navigate`, `to: /asset/STOCK/{symbol}` 형식의 액션을 내려주면 챗봇 메시지 아래 버튼으로 표시됩니다.

### 기대 동작

```text
현대건설우 전망은?
```

별칭으로 바로 정규화되면 `000725` 기준으로 전망 조회가 진행됩니다.

```text
현대건설 전망은?
```

여러 후보가 나오는 경우:

```text
어떤 종목을 말하나요?
1. 현대건설(000720) / KR
2. 현대건설우(000725) / KR
```

그리고 챗봇 메시지 아래에 `현대건설(000720) 조회`, `현대건설우(000725) 조회` 버튼이 표시됩니다.

### 주의

- 후보 버튼은 종목 상세 페이지 이동용입니다.
- 종목 선택 후 바로 같은 질문을 이어서 실행하는 흐름은 아직 별도 pending context가 필요합니다.
- 별칭 테이블은 자주 쓰는 종목부터 보강한 상태이며, 신규 별칭은 `SYMBOL_QUERY_ALIASES`에 계속 추가할 수 있습니다.

## 2026-07-13 챗봇 현재가 등락률 재계산 보강

### 목적

챗봇에서 `하이닉스 주가 얼마야?`처럼 현재가를 조회할 때 현재가는 거래소 API 기준으로 맞게 표시되지만, 등락률이 캐시나 거래소 원본 필드와 섞여 실제 현재가 기준과 다르게 보일 수 있어 보정했습니다.

### 수정 내용

- `backend/routes/trade.py`
  - `/api/chart/quote` 응답 생성 시 `current_price`와 `previous_close`가 있으면 서버에서 등락률을 다시 계산합니다.
  - 계산식은 `((현재가 - 기준가) / 기준가) * 100`입니다.
  - KIS 전일대비 부호 필드가 넘어오는 경우 하락/상승 방향을 반영해 기준가를 계산합니다.

- `backend/services/kis_client.py`
  - `get_price()` 응답에 `previous_close`, `price_change`를 추가했습니다.
  - KIS `prdy_vrss_sign`을 반영해 하락일 때 전일대비금액 부호를 보정합니다.

- `backend/services/toss_client.py`
  - 현재가와 기준가가 있으면 Toss 원본 등락률 대신 재계산 등락률을 우선 사용합니다.

- `backend/services/coinone_client.py`
  - 24시간 기준가를 `previous_close`로 함께 반환합니다.

- `backend/services/binance_client.py`
  - 현물/선물 24시간 ticker의 `openPrice`를 `previous_close`로 반환하고 등락률을 재계산합니다.

- `backend/tests/test_quote_change_rate.py`
  - 현재가/기준가 기반 등락률 재계산 테스트를 추가했습니다.
  - KIS 하락 부호 케이스도 함께 검증합니다.

### 기대 동작

```text
하이닉스 주가 얼마야?
```

현재가와 기준가가 함께 조회되면 챗봇 응답의 등락률은 거래소 원본 `change_rate` 필드를 그대로 쓰지 않고, 현재가 기준으로 재계산된 값이 표시됩니다.
## 2026-07-13 GST 한글 별칭 정규화 보강

### 목적

`GST 얼마야?`는 영문 심볼로 인식되지만, `쥐에스티 얼마야?`, `지에스티는 주가 얼마야?`처럼 한글 발음형으로 입력하면 별칭 매핑이 없어 종목 조회에 실패했습니다.

### 수정 내용

- `backend/services/chatbot/tool_registry.py`
  - `SYMBOL_QUERY_ALIASES`에 GST 한글 발음 별칭을 추가했습니다.

```text
GST -> 083450
지에스티 -> 083450
쥐에스티 -> 083450
```

- 종목 후보 정규화 단계에서 끝에 붙은 조사(`의`, `은`, `는`, `이`, `가`, `을`, `를`)를 제거하도록 보강했습니다.

### 기대 동작

```text
GST 얼마야?
쥐에스티 얼마야?
지에스티는 주가 얼마야?
```

위 입력은 모두 `083450`으로 정규화되어 같은 GST 종목 현재가 조회로 연결됩니다.

## 2026-07-13 해외주식/ETF 한글 별칭 정규화 보강

### 목적

`QQQ 얼마야?`는 영문 티커로 조회되지만, `해외주식 큐큐큐 얼마야?`처럼 한글 발음형이나 자산 구분어가 함께 들어오면 종목 추출이 실패할 수 있었습니다.

### 수정 내용

- `backend/services/chatbot/tool_registry.py`
  - 해외주식/ETF 한글 별칭을 추가했습니다.
  - 종목 추출 시 `해외주식`, `미국주식`, `국내주식`, `주식`, `주가` 같은 설명 단어를 제거하도록 보강했습니다.

```text
큐큐큐 -> QQQ
인베스코큐큐큐 -> QQQ
나스닥100 -> QQQ
에스피와이 / 스파이 -> SPY
에스앤피500 -> SPY
브이오오 -> VOO
슈드 -> SCHD
티큐큐 -> TQQQ
에스큐큐큐 -> SQQQ
엔비 / 엔비디아주식 -> NVDA
```

### 기대 동작

```text
해외주식 큐큐큐 얼마야?
미국주식 스파이 주가 알려줘
나스닥100 얼마야?
```

위 입력은 각각 `QQQ`, `SPY`, `QQQ`로 정규화되어 현재가 조회로 연결됩니다.

## 2026-07-13 챗봇 데이터 원천 분리 원칙 보강

### 목적

챗봇이 시세, 보유자산, 거래내역, 미체결 주문, 환율 같은 실제 금융 데이터를 OpenAI 일반 지식으로 추측하지 않고, 로그인 사용자의 개인 거래소 API와 Supabase DB 조회 결과만 기준으로 답하도록 원칙을 명확히 했습니다.

### 수정 내용

- `backend/services/chatbot/prompts/system_role.md`
  - 실제 금융 데이터는 반드시 프로젝트 도구를 통해 조회한 결과만 사용하도록 명시했습니다.
  - 주식 데이터는 Toss/KIS, 코인 데이터는 Coinone/Binance, 거래내역과 관심종목은 Supabase DB 및 거래소 동기화 데이터를 우선 사용한다고 정리했습니다.
  - OpenAI는 조회된 데이터를 자연어로 정리하거나 뉴스/공시/웹 검색 결과를 요약하는 역할로 제한했습니다.
  - 도구 조회 실패 시 값을 추측하지 않고 실패 이유와 확인 항목을 안내하도록 추가했습니다.

- `backend/services/chatbot/function_calling.py`
  - function calling 도구 설명에 개인 거래소 API, Supabase DB, 내부 RAG/API 우선 원칙을 반영했습니다.
  - `get_asset_price`는 Toss/KIS/Coinone/Binance API 기준으로 조회하며 OpenAI 일반 지식으로 가격을 답하지 않는다고 명시했습니다.
  - `search_web`은 내부 RAG/DB/뉴스·공시 API 이후 부족할 때만 Tavily를 사용하고, OpenAI는 검색 결과 요약에 사용한다고 정리했습니다.

### 기준 흐름

```text
사용자 질문
-> 내부 도구 라우팅 우선 확인
-> 시세/잔고/거래내역/주문/환율이면 개인 거래소 API 또는 Supabase DB 조회
-> 뉴스/공시/전망이면 내부 RAG/DB/API 우선, 부족할 때 웹 검색
-> OpenAI는 조회 결과를 설명·요약·분석하는 역할
```

## 2026-07-14 챗봇 장 운영 캘린더 도구 추가

### 목적

챗봇이 `오늘 한국장 열려?`, `7월 17일 제헌절 국내장 열려?`, `오늘 미국장 정규거래 가능해?` 같은 질문에 OpenAI 일반 지식으로 추측하지 않고, 장 운영 캘린더 API 또는 DB 적재 데이터를 기준으로 답하도록 보강했습니다.

### 수정 내용

- `supabase/migrations/20260714100000_create_market_calendar_days.sql`
  - `market_calendar_days` 테이블을 추가했습니다.
  - 주요 컬럼:
    - `market_country`
    - `trade_date`
    - `is_open`
    - `holiday_name`
    - `regular_open_at`
    - `regular_close_at`
    - `source`
    - `raw_payload`
  - `UNIQUE (market_country, trade_date)`로 같은 시장/날짜 데이터가 중복되지 않도록 했습니다.

- `backend/services/chatbot/tool_registry.py`
  - `get_market_calendar()` 챗봇 도구를 추가했습니다.
  - 시장 구분 파서:
    - `한국장`, `국내장`, `국장`, `코스피`, `코스닥`, `제헌절` 등은 `KR`
    - `미국장`, `미장`, `나스닥`, `뉴욕증시`, `NYSE`, `NASDAQ` 등은 `US`
  - 날짜 파서:
    - `오늘`, `내일`, `어제`
    - `2026년 7월 17일`
    - `7월 17일`
  - 특정 날짜는 `market_calendar_days` DB를 먼저 조회합니다.
  - 오늘 날짜는 DB에 없으면 Toss `get_market_calendar(KR|US)`를 호출하고, 결과를 DB에 저장합니다.
  - DB에 없는 미래 날짜는 값을 추측하지 않고 캘린더 DB 적재가 필요하다고 안내합니다.

- `backend/services/chatbot/function_calling.py`
  - OpenAI function calling 스키마에 `get_market_calendar`를 추가했습니다.
  - 장 운영 여부는 OpenAI 일반 지식으로 답하지 않는다고 설명에 명시했습니다.

- `backend/services/chatbot/chat_service.py`
  - OpenAI tool call이 `get_market_calendar`를 호출할 수 있도록 연결했습니다.

- `backend/services/chatbot/prompts/system_role.md`
  - 한국장/미국장 개장, 휴장, 정규장 가능 여부는 반드시 장 운영 캘린더 도구 결과로만 답하도록 원칙을 추가했습니다.

- `backend/services/chatbot/safety_guard.py`
  - `get_market_calendar`를 읽기 전용 도구로 등록했습니다.

- `backend/services/market_calendar_scheduler.py`
  - Toss 캘린더 API로 오늘 KR/US 장 운영 정보를 조회해 `market_calendar_days`에 저장하는 스케줄러를 추가했습니다.
  - `MARKET_CALENDAR_SYNC_ENABLED=true`일 때 worker 또는 gateway scheduler에서 주기적으로 실행됩니다.

- `backend/app.py`, `backend/worker.py`
  - `MARKET_CALENDAR_SYNC_ENABLED`, `MARKET_CALENDAR_SYNC_INTERVAL_SECONDS`, `MARKET_CALENDAR_SYNC_ENV` 환경변수로 캘린더 적재 스케줄러를 켤 수 있게 연결했습니다.

- `.env.example`
  - 캘린더 적재 스케줄러 환경변수 예시를 추가했습니다.

- `backend/tests/test_chatbot_market_calendar.py`
  - 제헌절/국내장 질문이 `KR`로 분류되는지 테스트를 추가했습니다.
  - 미국장 질문이 `US`로 분류되는지 테스트를 추가했습니다.

### 현재 동작

```text
오늘 한국장 열려?
오늘 미국장 정규거래 가능해?
```

위 질문은 Toss 장 운영 캘린더 API를 조회하고, 결과를 `market_calendar_days`에 저장한 뒤 답변합니다.

```text
2026년 7월 17일 제헌절 국내장 열려?
```

해당 날짜가 `market_calendar_days`에 저장되어 있으면 DB 기준으로 답합니다.
저장되어 있지 않으면 임의 추측하지 않고 캘린더 DB 적재가 필요하다고 안내합니다.

### 남은 작업

현재 스케줄러는 Toss API가 제공하는 오늘 KR/US 장 운영 정보를 주기적으로 저장합니다.
미래 특정 날짜까지 자동으로 채우려면 KRX, NYSE/Nasdaq 공식 휴장일 캘린더 또는 별도 휴장일 데이터 소스를 추가로 연결해 `market_calendar_days`에 선적재해야 합니다.

## 2026-07-14 국내주식 등락률 현재가 기준 재계산 보강

### 목적

국내주식 현재가는 거래소 API로 최신값을 받아오는데, 등락률은 Toss/KIS 원본 필드나 캐시 기준값이 섞이면 실제 증권사 화면과 1% 이상 차이 날 수 있었습니다.

### 수정 내용

- `backend/routes/trade.py`
  - `/api/chart/quote`에서 `current_price`와 `previous_close`가 함께 있으면 거래소 원본 `change_rate`보다 서버 재계산값을 우선 사용합니다.
  - 계산식은 `((현재가 - 전일종가) / 전일종가) * 100`입니다.
  - 재계산한 경우 `change_rate_source=CALCULATED_FROM_LIVE_PRICE`를 내려줍니다.
  - 거래소 원본 등락률은 참고용으로 `raw_change_rate`에 보존합니다.
  - 일봉 캔들 캐시로 보정한 경우 `change_rate_source=CALCULATED_FROM_CANDLE_CACHE`를 내려줍니다.

- `backend/services/toss_client.py`
  - Toss 원본 등락률이 있을 때 `raw_change_rate`로 함께 반환합니다.
  - 최종 화면 표시 등락률은 `/api/chart/quote`에서 현재가와 전일종가 기준으로 다시 계산합니다.

- `backend/tests/test_quote_change_rate.py`
  - `TOSS_PRICE` 원본 등락률이 있어도 현재가와 전일종가가 있으면 재계산 등락률을 우선하는 테스트로 변경했습니다.

### 기대 동작

```text
하이닉스 주가 얼마야?
삼성전자 현재가 알려줘
```

현재가와 전일종가가 함께 조회되면 챗봇과 차트 quote 응답의 등락률은 거래소 원본 필드가 아니라 현재가 기준 재계산값으로 표시됩니다.

## 2026-07-14 국내주식 Toss 등락률 KIS 전일종가 보강

### 목적

삼성전자(005930)처럼 Toss 현재가는 맞지만 Toss 응답의 전일종가/기준가가 실제 증권 화면 기준과 달라 등락률이 1%p 이상 차이 나는 문제를 줄이기 위한 보정입니다.

### 수정 내용

- `backend/routes/trade.py`
  - `/api/chart/quote`에서 `exchange=TOSS`이고 종목코드가 국내 6자리 주식이면 KIS 전일종가를 보조 조회합니다.
  - 현재가는 기존 Toss 값을 유지하고, 등락률은 `Toss 현재가 + KIS 전일종가` 기준으로 다시 계산합니다.
  - KIS 조회가 실패하면 기존 Toss 결과를 그대로 사용합니다.
  - 응답에 `previous_close_source`, `raw_previous_close`를 포함해 어떤 기준으로 계산했는지 추적할 수 있게 했습니다.

- `backend/tests/test_quote_change_rate.py`
  - KIS 전일종가 보강 헬퍼가 국내 종목의 전일종가를 가져오는 테스트를 추가했습니다.

### 기대 동작

```text
삼성전자 현재가 알려줘
```

국내주식은 KIS 전일종가 기준으로 등락률을 계산해 Toss 기준가 차이로 인한 등락률 오차를 줄입니다.

## 2026-07-15 챗봇 종목 거래상태 답변 추가

### 목적

챗봇에서 `동양 001520 현재가 얼마야?`, `삼성전자 전망은?`처럼 종목 관련 질문을 받았을 때 현재가/전망만 답하지 않고 거래정지, 정리매매, 투자경고 같은 거래상태를 함께 안내하도록 보강했습니다.

### 수정 내용

- `backend/services/chatbot/tool_registry.py`
  - 주식 종목이면 `/api/stocks/warnings`를 호출해 Toss 종목 유의사항과 `krxTradingSuspended` 합성 결과를 조회합니다.
  - 현재가 답변 뒤에 `현재 동양(001520)은/는 거래정지 상태입니다.` 형식의 거래상태 문장을 추가합니다.
  - 전망 답변에도 같은 거래상태 문장을 덧붙입니다.
  - 조회 실패 시 전체 챗봇 답변을 실패시키지 않고 거래상태 확인 실패 문장만 보조로 붙입니다.

- `backend/tests/test_chatbot_safety_and_proposals.py`
  - 거래정지 상태 문장 생성 테스트를 추가했습니다.

### 기대 동작

```text
동양 001520 현재가 얼마야?
```

```text
동양(001520) 현재가는 550원입니다.
등락률은 +0.00%입니다.
현재 동양(001520)은/는 거래정지 상태입니다.
```

<<<<<<< HEAD
## 2026-07-15 챗봇 해외주식 원화 환산 기능 추가

### 목적

챗봇에서 해외주식 현재가를 원화 기준으로 바로 계산할 수 있게 했습니다. `애플 원화로 얼마야?`처럼 첫 질문부터 종목과 원화 환산을 요청하는 경우와, `애플 현재가 얼마야?` 다음에 `환율 계산해줘`라고 이어 묻는 경우를 모두 지원합니다.

### 수정 내용

- `backend/services/chatbot/tool_registry.py`
  - `get_asset_krw_conversion()` 도구를 추가했습니다.
  - 해외주식 USD 현재가를 조회한 뒤 USD/KRW 환율을 가져와 `달러 × 환율 × 수량 = 원화`로 계산합니다.
  - `애플 원화로 얼마야`, `AAPL 2주 한화로 계산해줘` 같은 직접 요청을 처리합니다.
  - 답변 마지막에는 항상 `실제 주문 금액은 환전 수수료, 주문 수수료, 체결가 변동에 따라 달라질 수 있습니다.` 문구를 붙입니다.

- `backend/services/chatbot/chat_service.py`
  - 직전 현재가 조회 결과의 `current_price`, `currency`, `exchange`, `broker_env`를 대화 상태에 저장합니다.
  - 직전 해외주식 조회 후 `환율 계산해줘`, `원화로 계산해줘` 같은 후속 질문이 들어오면 직전 종목 기준으로 원화 환산합니다.
  - OpenAI function calling tool map에도 `get_asset_krw_conversion`을 연결했습니다.

- `backend/services/chatbot/function_calling.py`
  - `get_asset_krw_conversion` function schema를 추가했습니다.

- `backend/services/chatbot/safety_guard.py`
  - `get_asset_krw_conversion`을 읽기 전용 도구로 등록했습니다.

- `backend/tests/test_chatbot_trade_history.py`
  - 해외주식 USD 현재가와 USD/KRW 환율을 이용해 원화 환산하는 테스트를 추가했습니다.
  - 직전 현재가 context에서 `환율 계산해줘` 후속 질문을 처리하는 테스트를 추가했습니다.

### 기대 동작

```text
애플 2주 원화로 얼마야?
```

```text
Apple(AAPL) 원화 환산 금액입니다.

2주 현재가: $315.44
적용 환율: 1 USD = 1,380.00원
계산식: 315.44 × 1,380.00 × 2 = 약 870,614원
출처: TOSS / 2026-07-15 기준

실제 주문 금액은 환전 수수료, 주문 수수료, 체결가 변동에 따라 달라질 수 있습니다.
```

---

## 2026-07-15 임시 해외주식 심볼 정리 및 관리자 점검 기능

### 목적

`SKHYV`처럼 정식 상장 전 사용되던 임시 해외주식 심볼이 `kis_stock_turnover_latest` 또는 온디맨드 backfill 과정을 통해 검색 후보에 남는 문제를 막기 위한 작업입니다.

### 수정 내용

- `backend/services/symbol_reconciliation_service.py`
  - `symbol_aliases` DB 테이블에서 임시코드/정식코드 매핑을 읽도록 구성했습니다.
  - DB migration에는 초기 데이터로 `SKHYV -> SKHY` 매핑을 추가했습니다.
  - 정식 심볼이 존재하면 임시 심볼을 검색 결과에서 제외합니다.
  - 임시 심볼만 존재하는 경우 `symbol_badge: "임시코드"`를 내려줄 수 있게 했습니다.
  - 관리자 스캔, 비활성화, 삭제, 복구에 필요한 서비스 함수를 추가했습니다.

- `backend/routes/trade.py`
  - `/api/symbol/search`, `/api/symbol/lookup`에서 임시/폐기 심볼을 필터링합니다.
  - 임시 심볼이 `kis_stock_master`에 자동 backfill되는 것을 차단합니다.

- `backend/routes/admin_symbols.py`
  - 관리자 종목 마스터 정리 API를 추가했습니다.
  - 최신 스캔 결과 조회, 스캔 실행, 선택 비활성화, 선택 삭제, 선택 복구를 지원합니다.

- `frontend/src/pages/AdminSymbolReconciliation.jsx`
  - 관리자 화면에 종목 마스터 정리 탭을 추가했습니다.
  - 요약 카드, 상태 필터, 결과 테이블, 선택 비활성화/삭제/복구 버튼을 제공합니다.

- `frontend/src/components/SymbolSearch.jsx`
  - 서버가 `symbol_badge`를 내려주는 경우 자동완성 목록에 `임시코드` 배지를 표시합니다.

- `supabase/migrations/20260715110000_create_admin_symbol_reconciliation.sql`
  - `admin_symbol_reconciliation_runs`
  - `admin_symbol_reconciliation_items`
  - `symbol_aliases`
  - 위 테이블을 추가했습니다.
  - `symbol_aliases`에 `SKHYV -> SKHY` 초기 매핑을 등록했습니다.

### 기대 동작

- `SK하이닉스 ADR` 검색 시 `SKHY`가 있으면 `SKHYV`는 표시되지 않습니다.
- 임시코드만 존재하는 해외주식은 자동완성에 `임시코드` 배지를 붙일 수 있습니다.
- 관리자는 관리자 페이지의 `종목 마스터 정리` 탭에서 의심 심볼을 스캔하고 정리할 수 있습니다.

---

## 2026-07-15 챗봇 매매 요청 폼 단일 진입점

### 목적

자연어 주문 파싱이 종목, 거래소, 환경, 수량, 가격을 잘못 인식했을 때 의도하지 않은 주문 제안이 생성되는 위험을 차단했습니다. 일반 채팅은 주문 설명과 폼 임시값 생성까지만 수행하고, 주문 제안은 `매매 요청` 폼 제출로만 시작합니다.

### 동작 흐름

```text
자연어 주문 입력
-> 주문 제안 생성 차단
-> 명시적으로 인식한 종목·매매 구분·수량·가격만 임시값으로 생성
-> 사용자가 `매매 요청 열기` 버튼 선택
-> 폼에서 거래소·환경·종목·매매 구분·수량·주문 유형·가격 재확인
-> `structured_order.is_structured_order=true`로 폼 제출
-> 서버 사전검증과 제안 생성
-> 사용자 승인 후 서버 재검증과 실행
```

### 안전 규칙

- `삼성전자 10주 사줘`, `XRP 전량 팔아줘`를 일반 메시지로 전송해도 주문 제안을 생성하지 않습니다.
- 알 수 없는 거래소, REAL/MOCK, 주문 유형은 자산 유형으로 임의 추론하지 않고 빈 값으로 유지합니다.
- 챗봇이 채운 값은 폼에 임시 입력값으로 표시하며, 폼 제출 전에는 주문 네트워크 요청이 발생하지 않습니다.
- 주식과 코인 모두 같은 폼 제출 안전 경계를 사용합니다.
