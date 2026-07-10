# 챗봇 버그 수정과 주문 안전성 강화 구현 계획

> **에이전트 작업자 필수:** 이 계획을 구현할 때 `superpowers:subagent-driven-development`(권장) 또는 `superpowers:executing-plans`를 사용한다. 모든 진행 단계는 체크박스(`- [ ]`)로 추적한다.

**목표:** 공시·Obsidian RAG 기능을 유지하면서 챗봇의 스트림 실패, 불완전 주문 제안, API 미등록 제안, 실거래 하드캡 누락, 중복 승인, 자산 요약, 대화 연속성, 승인 카드 위치, 한글 IME 입력 결함을 재현 테스트와 함께 수정한다.

**아키텍처:** 공시·Obsidian RAG 검색과 citation 조립은 그대로 두고, 매매 제안 생성은 LLM function call에서 분리해 결정론적 주문 파서와 서버 사전검증을 통과한 경우에만 `trade_proposals.status=PENDING`을 생성한다. 여러 Flask 워커가 공유해야 하는 대기 작업과 최근 추천은 Supabase 상태 테이블에 저장하고, 승인 시점에는 PostgreSQL RPC가 `PENDING -> APPROVED`를 원자적으로 선점한다. SSE는 Flask 애플리케이션 컨텍스트와 요청 추적 ID를 보존하고, LLM 텍스트 응답은 OpenAI Chat Completions 스트림을 그대로 전달한다.

**기술 스택:** Flask, Python 3, requests, OpenAI Chat Completions API, Supabase REST/RPC, PostgreSQL RLS, React 19, Vite, Tailwind CSS v4, Node.js test runner.

## 전역 제약사항

- 모든 설명, 계획, 코드 주석, 커밋 메시지는 한국어로 작성한다. 코드 식별자와 외부 API 필드명은 영문 표준을 따른다.
- 챗봇은 거래소 주문 API를 직접 호출하지 않는다. 검증된 `PENDING` 제안 생성 후 사용자의 승인 카드 클릭을 반드시 거친다.
- 매수 제안은 `수량` 또는 `금액` 중 하나가 필수이고, 매도 제안은 `수량`, `비율`, `전량` 중 하나가 필수다.
- 거래 환경을 말하지 않으면 반드시 `MOCK`으로 해석한다. `REAL`은 사용자가 `실거래`, `실전`, `REAL`을 명시한 요청에서만 허용한다.
- 현재가, 예상 주문금액, API 연결, 거래소 주문유형, 장 운영, 잔고/보유수량, 권한, 실거래 하드캡 검증 중 하나라도 실패하면 `PENDING` 제안을 생성하지 않는다.
- 실거래 1회 주문 한도는 `REAL_ORDER_LIMIT_KRW = 100000.0`이며 `REAL`에서만 적용한다. `MOCK`은 이 한도를 우회한다.
- `MOCK`도 잔고·보유수량 검증은 유지하며, `REAL` 시장가는 슬리피지로 하드캡을 보장할 수 없어 차단한다.
- 코인원 챗봇 제안은 현재 구현 범위인 `LIMIT`만 허용한다. 가격 없는 `MARKET` 제안을 만들어 승인 단계에서 실패시키지 않는다.
- 동일 `proposal_id`는 외부 주문 API로 최대 한 번만 전달되어야 한다.
- 승인과 거절은 모두 `PENDING` 조건부 갱신으로 경쟁 상태를 원자적으로 해결해야 한다.
- 외부 주문 접수 후 상태와 외부 주문 ID 저장이 실패하면 최소 식별자를 복구하고, 복구도 실패한 요청은 성공으로 응답하지 않는다.
- SSE 로그에는 `request_id`, `user_id`, 예외 스택만 남기고 사용자 메시지 원문, JWT, API 키, 거래소 비밀값은 기록하지 않는다.
- 사용자에게 보이는 오류는 `format_error_payload()`와 프론트 `buildApiErrorText()`를 사용한다. 원문 예외는 기본 문구로 노출하지 않는다.
- 공시·Obsidian `knowledge_chunks` 검색, `ChatbotRAGService`, citation payload와 기존 자동메모리 동작은 회귀시키지 않는다.
- 신규 Supabase 테이블은 RLS와 역할별 GRANT를 명시한다. `UPDATE` 정책은 `USING`과 `WITH CHECK`를 모두 사용한다.
- OpenAI API는 이번 수정에서 Responses API로 마이그레이션하지 않는다. 현재 Chat Completions 계약을 유지하고 `stream=true`, `stream_options.include_usage=true`만 추가한다.
- 프론트 UI는 360px, 430px, 768px, 1280px에서 승인 카드, 입력창, 버튼이 겹치지 않아야 한다.
- 관련 없는 dirty change를 되돌리지 않는다. 각 작업은 실패 테스트, 최소 구현, 관련 회귀 테스트, 한글 커밋 순서로 끝낸다.

---

## 범위 점검

이 계획은 DB 상태, 주문 안전성, 스트림, 프론트 UI라는 서로 다른 계층을 건드리지만 하나의 챗봇 요청 흐름을 복구하는 작업이다. 각 Task는 독립적으로 검토 가능한 결과를 만들며, 순서는 `DB 상태 기반 -> 대화 상태 -> 제안 생성 게이트 -> 승인 안전성 -> 자산 요약 -> 스트림 -> 프론트 -> 통합 검증/문서`로 고정한다.

## 파일 구조

- CLI로 생성: `supabase/migrations/*_add_chatbot_conversation_state_and_trade_claim.sql`
  - `supabase migration new add_chatbot_conversation_state_and_trade_claim`이 출력한 실제 경로만 사용한다. 타임스탬프 파일명은 수동으로 만들지 않는다.
  - `chatbot_conversation_states`, `trade_proposals.approved_at`, 원자 승인 RPC, RLS/GRANT를 정의한다.
- Create: `backend/services/chatbot/conversation_repository.py`
  - 최신 대화 이력, 대기 작업, 최근 추천 후보를 Supabase에서 읽고 저장한다.
- Modify: `backend/services/chatbot/chat_service.py`
  - 서버 메모리 대화/대기 상태를 제거하고 저장소 및 스트림 callback을 사용한다.
- Modify: `backend/services/chatbot/order_parser.py`
  - 불완전한 주문 생성 표현도 안전 경로로 보내고, 필수 입력과 명시적 실거래를 판별한다.
- Modify: `backend/services/chatbot/function_calling.py`
  - LLM이 `create_trade_proposal`을 직접 호출하지 못하도록 해당 schema를 제거한다.
- Modify: `backend/services/chatbot/tool_registry.py`
  - 최근 추천 상태를 DB화하고, 사전검증 통과 전 제안 insert를 차단하며, 자산 요약 서비스를 연결한다.
- Create: `backend/services/chatbot/portfolio_summary_service.py`
  - 계좌별 통화를 KRW로 정규화하고 REAL/MOCK 합계를 분리한 요약을 만든다.
- Modify: `backend/services/chatbot/llm_client.py`
  - Chat Completions SSE 응답의 text delta, tool call delta, usage를 누적한다.
- Modify: `backend/routes/chatbot.py`
  - 작업 스레드에 Flask app context를 전달하고 request ID 기반 로그와 실제 delta 전달을 구현한다.
- Modify: `backend/routes/trade.py`
  - 실거래 하드캡을 계산하고 승인 직전 원자 선점 RPC를 호출한다.
- Create: `backend/tests/test_chatbot_conversation_repository.py`
- Create: `backend/tests/test_chatbot_llm_streaming.py`
- Create: `backend/tests/test_chatbot_rag_service.py`
- Create: `backend/tests/test_trade_proposal_approval_safety.py`
- Modify: `backend/tests/test_chatbot_profile_context.py`
- Modify: `backend/tests/test_chatbot_route_auth.py`
- Modify: `backend/tests/test_chatbot_safety_and_proposals.py`
- Modify: `tests/backend/test_chatbot_order_parser.py`
- Create: `frontend/src/features/chatbot/chatbotInput.js`
- Create: `frontend/src/features/chatbot/chatbotInput.test.mjs`
- Create: `frontend/src/features/chatbot/chatbotTimeline.js`
- Create: `frontend/src/features/chatbot/chatbotTimeline.test.mjs`
- Modify: `frontend/src/features/chatbot/chatbotApi.js`
- Modify: `frontend/src/features/chatbot/chatbotStream.test.mjs`
- Modify: `frontend/src/features/chatbot/chatbotProposalPrecheck.js`
- Modify: `frontend/src/features/chatbot/chatbotProposalPrecheck.test.mjs`
- Modify: `frontend/src/features/chatbot/ChatbotWidget.jsx`
- Modify: `database_specification.md`
- Modify: `project_structure.md`
- Modify: `README.md`

---

### Task 1: Supabase 대화 상태와 원자 승인 스키마

**Files:**
- Create via CLI: `supabase/migrations/*_add_chatbot_conversation_state_and_trade_claim.sql`
- Modify: `database_specification.md:76`
- Modify: `database_specification.md:412`

**Interfaces:**
- Produces: `public.chatbot_conversation_states`
- Produces: `public.claim_trade_proposal_for_execution(p_proposal_id uuid) returns setof public.trade_proposals`
- Produces: `trade_proposals.approved_at timestamptz`

- [ ] **Step 1: Supabase CLI 명령 형태와 버전을 확인한다**

Run:

```bash
supabase --version
supabase migration new --help
supabase db query --help
```

Expected: 버전이 출력되고 `migration new`가 사용 가능하다. `db query`가 없으면 SQL 검증은 연결된 Supabase MCP `execute_sql` 또는 Dashboard SQL Editor에서 같은 SELECT를 실행한다.

- [ ] **Step 2: CLI로 migration 파일을 생성한다**

Run:

```bash
supabase migration new add_chatbot_conversation_state_and_trade_claim
```

Expected: `supabase/migrations/` 아래에 타임스탬프가 붙은 SQL 파일 하나가 생성된다. 이후 단계는 CLI가 출력한 그 파일만 수정한다.

- [ ] **Step 3: 대화 상태, RLS, 승인 선점 RPC SQL을 작성한다**

CLI가 생성한 SQL 파일에 다음 내용을 넣는다.

```sql
create table if not exists public.chatbot_conversation_states (
  user_id uuid primary key references public.profiles(id) on delete cascade,
  pending_action text,
  pending_payload jsonb not null default '{}'::jsonb,
  pending_expires_at timestamptz,
  recommendation_items jsonb not null default '[]'::jsonb,
  recommendation_source text,
  recommendation_expires_at timestamptz,
  updated_at timestamptz not null default timezone('utc'::text, now()),
  constraint chatbot_conversation_states_pending_payload_object
    check (jsonb_typeof(pending_payload) = 'object'),
  constraint chatbot_conversation_states_recommendation_items_array
    check (jsonb_typeof(recommendation_items) = 'array')
);

alter table public.chatbot_conversation_states enable row level security;

grant select, insert, update, delete
on table public.chatbot_conversation_states
to authenticated;

revoke all
on table public.chatbot_conversation_states
from anon;

drop policy if exists "chatbot_conversation_states_owner_select"
on public.chatbot_conversation_states;
create policy "chatbot_conversation_states_owner_select"
on public.chatbot_conversation_states
for select
to authenticated
using ((select auth.uid()) = user_id);

drop policy if exists "chatbot_conversation_states_owner_insert"
on public.chatbot_conversation_states;
create policy "chatbot_conversation_states_owner_insert"
on public.chatbot_conversation_states
for insert
to authenticated
with check ((select auth.uid()) = user_id);

drop policy if exists "chatbot_conversation_states_owner_update"
on public.chatbot_conversation_states;
create policy "chatbot_conversation_states_owner_update"
on public.chatbot_conversation_states
for update
to authenticated
using ((select auth.uid()) = user_id)
with check ((select auth.uid()) = user_id);

drop policy if exists "chatbot_conversation_states_owner_delete"
on public.chatbot_conversation_states;
create policy "chatbot_conversation_states_owner_delete"
on public.chatbot_conversation_states
for delete
to authenticated
using ((select auth.uid()) = user_id);

alter table public.trade_proposals
add column if not exists approved_at timestamptz;

grant select, insert, update, delete
on table public.trade_proposals
to authenticated;

create or replace function public.claim_trade_proposal_for_execution(
  p_proposal_id uuid
)
returns setof public.trade_proposals
language sql
security invoker
set search_path = ''
as $$
  update public.trade_proposals
  set
    status = 'APPROVED',
    approved_at = timezone('utc'::text, now()),
    failure_reason = null
  where id = p_proposal_id
    and user_id = (select auth.uid())
    and status = 'PENDING'
  returning *;
$$;

revoke execute
on function public.claim_trade_proposal_for_execution(uuid)
from public, anon;

grant execute
on function public.claim_trade_proposal_for_execution(uuid)
to authenticated, service_role;
```

- [ ] **Step 4: migration 파일을 비파괴 방식으로 검증한다**

Run:

```bash
supabase migration list --local
```

Expected: migration 파일이 목록에 표시된다. 기존 로컬 데이터 보존을 위해 `supabase db reset --local`은 실행하지 않는다. 연결된 테스트용 Supabase 프로젝트가 별도로 준비된 경우에만 SQL Editor 또는 MCP `execute_sql`로 migration SQL을 트랜잭션 안에서 실행한 뒤 rollback하여 문법을 검증한다.

- [ ] **Step 5: 테이블과 함수 권한을 SQL로 검증한다**

`supabase db query --help`가 확인된 환경에서는 다음 두 쿼리를 실행한다.

```sql
select table_name
from information_schema.tables
where table_schema = 'public'
  and table_name = 'chatbot_conversation_states';

select routine_name, security_type
from information_schema.routines
where routine_schema = 'public'
  and routine_name = 'claim_trade_proposal_for_execution';
```

Expected: 테이블 1건, 함수 1건이 반환되고 함수 `security_type`은 `INVOKER`다.

- [ ] **Step 6: DB 명세를 갱신한다**

`database_specification.md`의 `trade_proposals`에 `approved_at`과 원자 승인 RPC를 추가하고, `chat_history` 다음에 아래 내용을 추가한다.

```markdown
### chatbot_conversation_states
* **용도**: 여러 Flask 워커가 공유해야 하는 챗봇 대기 작업과 최근 추천 후보를 사용자별로 저장합니다.
* **TTL**: `pending_expires_at`, `recommendation_expires_at`이 지난 상태는 대화 해석에 사용하지 않습니다.
* **RLS**: `authenticated` 사용자는 `auth.uid() = user_id`인 자신의 행만 조회·삽입·수정·삭제할 수 있습니다.
```

- [ ] **Step 7: 한글 커밋을 만든다**

```bash
git add supabase/migrations database_specification.md
git commit -m "feat: 챗봇 대화 상태와 원자 승인 스키마 추가"
```

---

### Task 2: 서버 메모리 대화 상태를 Supabase 저장소로 교체

**Files:**
- Create: `backend/services/chatbot/conversation_repository.py`
- Create: `backend/tests/test_chatbot_conversation_repository.py`
- Modify: `backend/services/chatbot/chat_service.py:1-27`
- Modify: `backend/services/chatbot/chat_service.py:154-278`
- Modify: `backend/services/chatbot/tool_registry.py:1-24`
- Modify: `backend/services/chatbot/tool_registry.py:815-912`
- Modify: `backend/tests/test_chatbot_profile_context.py:139`
- Modify: `backend/tests/test_chatbot_safety_and_proposals.py:298`

**Interfaces:**
- Produces: `ChatbotConversationRepository.load_recent_history(auth_header: str, user_id: str, limit: int = 12) -> list[dict]`
- Produces: `ChatbotConversationRepository.record_exchange(auth_header: str, user_id: str, user_message: str, assistant_message: str) -> None`
- Produces: `ChatbotConversationRepository.set_pending_action(auth_header: str, user_id: str, action: str, payload: dict | None = None, ttl_seconds: int = 300) -> None`
- Produces: `ChatbotConversationRepository.consume_pending_action(auth_header: str, user_id: str, now: datetime | None = None) -> tuple[str | None, dict]`
- Produces: `ChatbotConversationRepository.peek_pending_action(auth_header: str, user_id: str, now: datetime | None = None) -> str | None`
- Produces: `ChatbotConversationRepository.store_recommendations(auth_header: str, user_id: str, items: list[dict], source: str | None, ttl_seconds: int = 600) -> None`
- Produces: `ChatbotConversationRepository.load_recommendations(auth_header: str, user_id: str, now: datetime | None = None) -> list[dict]`
- Consumes: Task 1의 `chatbot_conversation_states`

- [ ] **Step 1: 여러 워커를 흉내 내는 실패 테스트를 작성한다**

Create `backend/tests/test_chatbot_conversation_repository.py`:

```python
from datetime import UTC, datetime, timedelta

from backend.services.chatbot.conversation_repository import ChatbotConversationRepository


def test_load_recent_history_reads_supabase_on_every_request(monkeypatch):
    calls = []

    def fake_query(auth_header, endpoint, method="GET", json_data=None, params=None):
        calls.append((endpoint, method, params))
        return [
            {"id": 2, "role": "assistant", "message": "두 번째", "created_at": "2026-07-10T01:00:02Z"},
            {"id": 1, "role": "user", "message": "첫 번째", "created_at": "2026-07-10T01:00:01Z"},
        ]

    monkeypatch.setattr(
        "backend.services.chatbot.conversation_repository.query_supabase",
        fake_query,
    )
    repository = ChatbotConversationRepository()

    first = repository.load_recent_history("Bearer test", "user-1")
    second = repository.load_recent_history("Bearer test", "user-1")

    assert first == [
        {"role": "user", "content": "첫 번째"},
        {"role": "assistant", "content": "두 번째"},
    ]
    assert second == first
    assert len(calls) == 2


def test_expired_recommendations_are_not_reused(monkeypatch):
    expired_at = (datetime.now(UTC) - timedelta(seconds=1)).isoformat()
    monkeypatch.setattr(
        "backend.services.chatbot.conversation_repository.query_supabase",
        lambda *args, **kwargs: [{
            "user_id": "user-1",
            "recommendation_items": [{"symbol": "DOGE"}],
            "recommendation_expires_at": expired_at,
        }],
    )

    result = ChatbotConversationRepository().load_recommendations(
        "Bearer test",
        "user-1",
        now=datetime.now(UTC),
    )

    assert result == []
```

- [ ] **Step 2: 테스트가 실패하는지 확인한다**

Run:

```bash
python3 -m pytest backend/tests/test_chatbot_conversation_repository.py -q
```

Expected: `conversation_repository` 모듈이 없어 FAIL한다.

- [ ] **Step 3: 대화 상태 저장소를 구현한다**

Create `backend/services/chatbot/conversation_repository.py` with these public methods and normalization rules:

```python
from datetime import UTC, datetime, timedelta

from backend.services.supabase_client import query_supabase


class ChatbotConversationRepository:
    def load_recent_history(
        self,
        auth_header: str,
        user_id: str,
        limit: int = 12,
    ) -> list[dict]:
        rows = query_supabase(
            auth_header,
            "chat_history",
            "GET",
            params={
                "user_id": f"eq.{user_id}",
                "select": "role,message,created_at,id",
                "order": "created_at.desc,id.desc",
                "limit": str(max(1, min(limit, 50))),
            },
        ) or []
        history = []
        for row in reversed(rows):
            role = str((row or {}).get("role") or "").strip()
            message = str((row or {}).get("message") or "").strip()
            if role in {"user", "assistant"} and message:
                history.append({"role": role, "content": message})
        return history

    def record_exchange(
        self,
        auth_header: str,
        user_id: str,
        user_message: str,
        assistant_message: str,
    ) -> None:
        query_supabase(
            auth_header,
            "chat_history",
            "POST",
            json_data=[
                {"user_id": user_id, "role": "user", "message": user_message.strip()},
                {"user_id": user_id, "role": "assistant", "message": assistant_message.strip()},
            ],
        )

    def set_pending_action(
        self,
        auth_header: str,
        user_id: str,
        action: str,
        payload: dict | None = None,
        ttl_seconds: int = 300,
    ) -> None:
        self._patch_or_insert_state(
            auth_header,
            user_id,
            {
                "pending_action": action,
                "pending_payload": payload or {},
                "pending_expires_at": (
                    datetime.now(UTC) + timedelta(seconds=ttl_seconds)
                ).isoformat(),
            },
        )

    def store_recommendations(
        self,
        auth_header: str,
        user_id: str,
        items: list[dict],
        source: str | None,
        ttl_seconds: int = 600,
    ) -> None:
        self._patch_or_insert_state(
            auth_header,
            user_id,
            {
                "recommendation_items": items,
                "recommendation_source": source,
                "recommendation_expires_at": (
                    datetime.now(UTC) + timedelta(seconds=ttl_seconds)
                ).isoformat(),
            },
        )
```

`consume_pending_action()`은 유효한 상태를 읽은 뒤 `pending_action`, `pending_payload`, `pending_expires_at`을 `null/{}/null`로 PATCH하고 `(action, payload)`를 반환한다. `peek_pending_action()`과 `load_recommendations()`은 timezone-aware `datetime`으로 TTL을 검사하고 만료 상태를 빈 값으로 반환한다. `_patch_or_insert_state()`는 먼저 `user_id=eq.<id>`를 조회하고, 존재하면 PATCH, 없으면 POST한다. POST가 unique 충돌로 실패하면 동일 사용자 행을 PATCH해 동시 최초 생성 경쟁을 복구한다.

- [ ] **Step 4: `ChatbotService`의 프로세스 메모리를 제거한다**

`chat_service.py`에서 다음을 제거한다.

```python
from collections import defaultdict, deque
self._history_by_user
self._history_loaded_users
self._pending_actions
```

생성자와 호출부를 다음 계약으로 교체한다.

```python
self.conversation_repository = ChatbotConversationRepository()

history = self.conversation_repository.load_recent_history(
    auth_header,
    user_id,
    CHAT_HISTORY_MAXLEN,
)

pending_action, pending_payload = self.conversation_repository.consume_pending_action(
    auth_header,
    user_id,
)
```

`_record_exchange()`는 `conversation_repository.record_exchange()`를 호출하고 자동메모리 수집은 기존처럼 best-effort로 유지한다. 대화 저장 실패는 Flask logger에 남기되 인메모리 복사본으로 숨기지 않는다.

- [ ] **Step 5: 최근 추천을 DB 상태로 교체한다**

`tool_registry.py`의 `_last_recommendations_by_user`를 삭제한다. `_store_last_recommendations()`와 `_with_referenced_recommendation_symbol()`은 `get_user_id_from_header()`로 사용자 ID를 확인한 뒤 `ChatbotConversationRepository.store_recommendations()`와 `load_recommendations()`를 사용한다. 추천 후보는 symbol이 있는 dict만 최대 10개 저장하고 TTL은 600초로 고정한다.

- [ ] **Step 6: 관련 테스트를 통과시킨다**

Run:

```bash
python3 -m pytest backend/tests/test_chatbot_conversation_repository.py backend/tests/test_chatbot_profile_context.py backend/tests/test_chatbot_safety_and_proposals.py -q
```

Expected: 모든 테스트 PASS, `_history_by_user`, `_history_loaded_users`, `_pending_actions`, `_last_recommendations_by_user` 참조 0건.

Run:

```bash
rg -n "_history_by_user|_history_loaded_users|_pending_actions|_last_recommendations_by_user" backend tests
```

Expected: 검색 결과 없음.

- [ ] **Step 7: 한글 커밋을 만든다**

```bash
git add backend/services/chatbot/conversation_repository.py backend/services/chatbot/chat_service.py backend/services/chatbot/tool_registry.py backend/tests/test_chatbot_conversation_repository.py backend/tests/test_chatbot_profile_context.py backend/tests/test_chatbot_safety_and_proposals.py
git commit -m "fix: 챗봇 대화와 추천 상태를 DB로 일원화"
```

---

### Task 3: 불완전 주문과 사전검증 실패의 PENDING 생성 차단

**Files:**
- Modify: `backend/services/chatbot/order_parser.py:7-74`
- Modify: `backend/services/chatbot/order_parser.py:112-164`
- Modify: `backend/services/chatbot/function_calling.py:98-117`
- Modify: `backend/services/chatbot/chat_service.py:380-411`
- Modify: `backend/services/chatbot/tool_registry.py:629-812`
- Modify: `backend/services/chatbot/tool_registry.py:914-967`
- Modify: `backend/services/chatbot/tool_registry.py:1339-1383`
- Modify: `tests/backend/test_chatbot_order_parser.py`
- Modify: `backend/tests/test_chatbot_safety_and_proposals.py`

**Interfaces:**
- Produces: `ParsedOrderIntent.is_order_request`가 완성/불완전 주문 생성 요청을 모두 표시한다.
- Produces: `_run_chatbot_precheck(auth_header: str, exchange: str, symbol: str, side: str, order_type: str, quantity: float, price: float | None, broker_env: str) -> dict`, 실패 시 예외 발생.
- Produces: `_collect_precheck_blockers(precheck: dict, broker_env: str) -> list[str]`
- Consumes: Task 2의 DB 추천 후보.

- [ ] **Step 1: 사용자 제보 흐름의 실패 테스트를 추가한다**

`tests/backend/test_chatbot_order_parser.py`에 추가:

```python
def test_incomplete_trade_proposal_phrase_routes_to_safe_clarification():
    intent = parse_order_intent("매매 제안 만들어줘")

    assert intent.is_order_request is True
    assert intent.side is None
    assert intent.symbol_query == ""


def test_order_history_query_is_not_order_creation():
    assert parse_order_intent("최근 주문내역 보여줘").is_order_request is False


def test_price_token_is_not_parsed_as_order_budget():
    intent = parse_order_intent("XRP 10개 800원에 모의로 사줘")

    assert intent.quantity == 10
    assert intent.price == 800
    assert intent.amount_krw is None
```

`backend/tests/test_chatbot_safety_and_proposals.py`에 추가:

```python
def test_incomplete_proposal_request_never_calls_llm_or_inserts(monkeypatch):
    inserted = []
    monkeypatch.setattr(tool_registry, "query_supabase", lambda *args, **kwargs: inserted.append(kwargs))

    result = run_chatbot_tool("Bearer test", "매매 제안 만들어줘")

    assert result["data"]["reason"] == "missing_order_intent"
    assert "종목" in result["reply"]
    assert inserted == []


def test_precheck_failure_does_not_insert_pending_proposal(monkeypatch):
    monkeypatch.setattr(tool_registry, "_resolve_symbol", lambda *args: {
        "symbol": "DOGE", "asset_type": "CRYPTO", "market": "KR",
    })
    monkeypatch.setattr(tool_registry, "_run_chatbot_precheck", lambda **kwargs: (_ for _ in ()).throw(
        ValueError("등록된 COINONE (REAL) API 키가 없습니다.")
    ))
    monkeypatch.setattr(tool_registry, "query_supabase", lambda *args, **kwargs: (_ for _ in ()).throw(
        AssertionError("검증 실패 후 insert 금지")
    ))

    result = run_chatbot_tool("Bearer test", "도지 10개 실거래로 팔아줘")

    assert result["data"]["reason"] == "precheck_failed"
    assert "API 키" in result["reply"]
```

- [ ] **Step 2: 새 테스트가 현재 결함을 잡는지 확인한다**

Run:

```bash
python3 -m pytest tests/backend/test_chatbot_order_parser.py backend/tests/test_chatbot_safety_and_proposals.py -q
```

Expected: 불완전 제안이 LLM 경로로 빠지는 테스트와 사전검증 실패 후 insert 차단 테스트가 FAIL한다.

- [ ] **Step 3: 주문 파서가 불완전한 생성 요청도 안전 경로로 보낸다**

`order_parser.py`에 주문 생성 표현과 조회 제외 표현을 분리한다.

```python
ORDER_CREATION_PATTERNS = (
    "매매 제안",
    "매수 제안",
    "매도 제안",
    "주문 만들어",
    "주문해",
    *ORDER_KEYWORDS,
)

ORDER_READ_PATTERNS = (
    "주문내역",
    "주문 내역",
    "미체결 주문",
    "열린 주문",
)
```

`parse_order_intent()`는 조회 표현이면 `False`, 생성 표현이면 필수값이 없어도 `is_order_request=True`를 반환한다. `_extract_amount_krw()`는 `원에` 가격 표현을 예산으로 해석하지 않도록 금액 정규식에 `(?!\s*에)` 조건을 적용한다.

- [ ] **Step 4: LLM의 직접 제안 생성 권한을 제거한다**

`function_calling.py`에서 `create_trade_proposal` schema 전체를 삭제한다. `chat_service.py`의 `_run_llm_tool_call()`에서도 다음 분기를 삭제한다.

```python
if tool_name == "create_trade_proposal":
    return create_trade_proposal(auth_header, arguments)
```

Expected: 모든 매매 제안은 `run_chatbot_tool() -> create_trade_proposal_from_message()` 경로만 사용한다.

- [ ] **Step 5: 사전검증을 예외 기반 필수 게이트로 바꾼다**

`_build_chatbot_precheck_payload()`을 `_run_chatbot_precheck()`으로 바꾸고 실패를 dict로 숨기지 않는다.

```python
def _run_chatbot_precheck(
    auth_header: str,
    exchange: str,
    symbol: str,
    side: str,
    order_type: str,
    quantity: float,
    price: float | None,
    broker_env: str,
) -> dict:
    response = _post_internal(
        "/api/trade/precheck",
        auth_header,
        {
            "exchange": exchange,
            "symbol": symbol,
            "action": side,
            "order_type": order_type,
            "quantity": quantity,
            "price": price,
            "broker_env": broker_env,
        },
    )
    precheck = response.get("data") or {}
    if not precheck.get("reference_price") or not precheck.get("estimated_amount_krw"):
        raise ValueError("현재가와 예상 주문금액을 확인하지 못했습니다.")
    return precheck
```

다음 blocker helper를 추가한다.

```python
def _collect_precheck_blockers(precheck: dict, broker_env: str) -> list[str]:
    blockers = []
    if precheck.get("is_market_closed"):
        blockers.append(precheck.get("market_status_message") or "현재 거래 가능 시간이 아닙니다.")
    if precheck.get("insufficient_cash"):
        blockers.append("주문 가능 현금이 부족합니다.")
    if precheck.get("insufficient_holding"):
        blockers.append("보유 수량보다 많은 매도 주문입니다.")
    if precheck.get("insufficient_permission"):
        blockers.append(precheck.get("permission_message") or "거래 권한이 없습니다.")
    if precheck.get("futures_real_blocked"):
        blockers.append("바이낸스 선물 실거래가 잠겨 있습니다.")
    if broker_env == "REAL" and precheck.get("exceeds_real_order_limit"):
        blockers.append("실거래 1회 주문 한도 100,000원을 초과했습니다.")
    return blockers
```

- [ ] **Step 6: PENDING insert 직전에 검증 결과를 재확인한다**

`create_trade_proposal()`은 `raw_order_payload.precheck_status == "OK"`, 비어 있지 않은 `precheck`, blocker 0건을 요구한다. 이 방어는 호출자가 바뀌어도 검증 없는 insert를 막는 마지막 계층이다.

```python
raw_order_payload = values.get("raw_order_payload") or {}
precheck = raw_order_payload.get("precheck") or {}
if raw_order_payload.get("precheck_status") != "OK" or not precheck:
    raise ValueError("주문 사전검증을 통과한 제안만 생성할 수 있습니다.")
blockers = _collect_precheck_blockers(precheck, broker_env)
if blockers:
    raise ValueError(" ".join(blockers))
```

`create_trade_proposal_from_message()`은 `_run_chatbot_precheck()` 예외를 잡아 `reason=precheck_failed`와 사용자 행동 문구를 반환하고 insert를 호출하지 않는다. 성공한 경우에만 아래 payload를 전달한다.

```python
"raw_order_payload": {
    "precheck_status": "OK",
    "precheck": precheck,
    "source": "CHATBOT_ORDER_PARSER",
}
```

- [ ] **Step 7: 주문유형과 환경 규칙을 고정한다**

`create_trade_proposal_from_message()`에서 `broker_env = parsed.broker_env or "MOCK"`을 사용한다. 코인원 `MARKET`은 현재가로 임의 변환하지 말고 `reason=unsupported_order_type`으로 중단하며 `LIMIT` 가격 입력 방법을 안내한다. `REAL`은 parser가 명시적으로 반환한 경우에만 유지한다.

- [ ] **Step 8: 주문 관련 테스트를 통과시킨다**

Run:

```bash
python3 -m pytest tests/backend/test_chatbot_order_parser.py backend/tests/test_chatbot_safety_and_proposals.py backend/tests/test_chatbot_profile_context.py -q
```

Expected: PASS. `precheck_status=FAILED`인 `trade_proposals` insert를 기대하는 테스트는 존재하지 않는다.

- [ ] **Step 9: 한글 커밋을 만든다**

```bash
git add backend/services/chatbot/order_parser.py backend/services/chatbot/function_calling.py backend/services/chatbot/chat_service.py backend/services/chatbot/tool_registry.py tests/backend/test_chatbot_order_parser.py backend/tests/test_chatbot_safety_and_proposals.py backend/tests/test_chatbot_profile_context.py
git commit -m "fix: 검증되지 않은 챗봇 매매 제안 생성 차단"
```

---

### Task 4: 실거래 하드캡과 중복 승인 원자성

**Files:**
- Create: `backend/tests/test_trade_proposal_approval_safety.py`
- Modify: `backend/routes/trade.py:574-620`
- Modify: `backend/routes/trade.py:1363-1554`
- Modify: `backend/routes/trade.py:1617-1783`
- Modify: `backend/tests/test_chatbot_safety_and_proposals.py:69-128`

**Interfaces:**
- Produces: `_exceeds_real_order_limit(broker_env: str, estimated_amount_krw: float) -> bool`
- Produces: `_claim_trade_proposal_for_execution(auth_header: str, proposal_id: str) -> dict | None`
- Consumes: Task 1의 `claim_trade_proposal_for_execution` RPC.

- [ ] **Step 1: 하드캡과 동시 승인 실패 테스트를 작성한다**

Create `backend/tests/test_trade_proposal_approval_safety.py`:

```python
from backend.routes.trade import _exceeds_real_order_limit


def test_real_order_limit_applies_only_to_real_orders():
    assert _exceeds_real_order_limit("REAL", 100001) is True
    assert _exceeds_real_order_limit("REAL", 100000) is False
    assert _exceeds_real_order_limit("MOCK", 5000000) is False


def test_claim_trade_proposal_returns_none_after_first_claim(monkeypatch):
    calls = []

    def fake_query(auth_header, endpoint, method="GET", json_data=None, params=None):
        assert endpoint == "rpc/claim_trade_proposal_for_execution"
        calls.append(json_data["p_proposal_id"])
        if len(calls) == 1:
            return [{"id": "proposal-1", "status": "APPROVED"}]
        return []

    monkeypatch.setattr("backend.routes.trade.query_supabase", fake_query)

    assert _claim_trade_proposal_for_execution("Bearer test", "proposal-1")["status"] == "APPROVED"
    assert _claim_trade_proposal_for_execution("Bearer test", "proposal-1") is None
```

승인 route 테스트에는 같은 proposal로 두 번 요청했을 때 `client.place_order()` 호출 횟수가 1이고 두 번째 응답이 HTTP 409인지 확인하는 케이스를 추가한다.

- [ ] **Step 2: 테스트가 현재 결함을 잡는지 확인한다**

Run:

```bash
python3 -m pytest backend/tests/test_trade_proposal_approval_safety.py -q
```

Expected: helper가 없어 FAIL한다.

- [ ] **Step 3: 실거래 하드캡 계산을 구현한다**

`trade.py`에 pure helper를 추가하고 `_build_precheck_payload()`에서 사용한다.

```python
def _exceeds_real_order_limit(broker_env: str, estimated_amount_krw: float) -> bool:
    return (
        str(broker_env or "").upper() == "REAL"
        and float(estimated_amount_krw or 0) > REAL_ORDER_LIMIT_KRW
    )
```

기존 `exceeds_hard_cap = False`를 다음으로 교체한다.

```python
exceeds_hard_cap = _exceeds_real_order_limit(broker_env, estimated_amount_krw)
if exceeds_hard_cap:
    warnings.append("실거래 1회 주문 한도 100,000원을 초과했습니다.")
```

`place_manual_order()`은 외부 주문 전에 다음을 검사한다.

```python
if precheck.get("exceeds_real_order_limit"):
    return jsonify({
        "success": False,
        "message": "실거래 1회 주문 한도 100,000원을 초과했습니다. 수량 또는 가격을 낮춰 주세요.",
    }), 400
```

- [ ] **Step 4: 승인 선점 RPC wrapper를 구현한다**

```python
def _claim_trade_proposal_for_execution(
    auth_header: str,
    proposal_id: str,
) -> dict | None:
    rows = query_supabase(
        auth_header,
        "rpc/claim_trade_proposal_for_execution",
        "POST",
        json_data={"p_proposal_id": proposal_id},
    ) or []
    return rows[0] if isinstance(rows, list) and rows else None
```

- [ ] **Step 5: 외부 주문 직전에만 원자 선점한다**

`_resolve_proposal_order_data()`는 PENDING row의 서버 필드 고정 용도로 유지한다. 모든 정적 검증, API credential 로드, `_build_precheck_payload()`가 끝난 후이면서 `client.place_order()`보다 앞인 위치에서 RPC를 호출한다.

```python
if approval_proposal:
    claimed = _claim_trade_proposal_for_execution(auth_header, approval_proposal["id"])
    if not claimed:
        return jsonify({
            "success": False,
            "message": "이미 승인·거절·실행 중인 매매 제안입니다. 거래내역을 새로고침해 상태를 확인하세요.",
        }), 409
    approval_proposal = claimed
```

기존 `_patch_trade_proposal(auth_header, approval_proposal["id"], {"status": "APPROVED"})`는 삭제한다. 선점 후 거래소 주문 실패는 기존처럼 `FAILED`, 성공은 `EXECUTED` 또는 `APPROVED` 실제 주문 상태로 갱신한다.

- [ ] **Step 6: 승인 회귀 테스트를 실행한다**

Run:

```bash
python3 -m pytest backend/tests/test_trade_proposal_approval_safety.py backend/tests/test_chatbot_safety_and_proposals.py -q
```

Expected: PASS, 중복 승인 테스트에서 외부 주문 호출 1회.

- [ ] **Step 7: 한글 커밋을 만든다**

```bash
git add backend/routes/trade.py backend/tests/test_trade_proposal_approval_safety.py backend/tests/test_chatbot_safety_and_proposals.py
git commit -m "fix: 실거래 하드캡과 중복 승인 방어 적용"
```

---

### Task 5: 보유자산 요약을 금액 중심 REAL/MOCK 요약으로 교체

**Files:**
- Create: `backend/services/chatbot/portfolio_summary_service.py`
- Create: `backend/tests/test_chatbot_portfolio_summary_service.py`
- Modify: `backend/services/chatbot/tool_registry.py:385-425`
- Modify: `backend/services/chatbot/tool_registry.py:599-626`
- Modify: `backend/tests/test_chatbot_profile_context.py:139-165`

**Interfaces:**
- Produces: `normalize_account_summary(exchange: str, env: str, balance: dict) -> dict`
- Produces: `build_portfolio_totals(accounts: list[dict]) -> dict[str, dict]`
- Produces: `format_portfolio_reply(totals_by_env: dict, accounts: list[dict], errors: list[str]) -> str`

- [ ] **Step 1: 통화 혼합과 요약 형식 실패 테스트를 작성한다**

Create `backend/tests/test_chatbot_portfolio_summary_service.py`:

```python
from backend.services.chatbot.portfolio_summary_service import (
    build_portfolio_totals,
    format_portfolio_reply,
    normalize_account_summary,
)


def test_portfolio_totals_convert_currency_and_separate_real_mock():
    accounts = [
        normalize_account_summary("KIS", "REAL", {
            "total_evaluation": 1000000,
            "available_cash": 200000,
            "currency": "KRW",
        }),
        normalize_account_summary("BINANCE", "REAL", {
            "total_evaluation": 100,
            "available_cash": 20,
            "currency": "USDT",
            "exchange_rate": 1500,
        }),
        normalize_account_summary("KIS", "MOCK", {
            "total_evaluation": 5000000,
            "available_cash": 1000000,
            "currency": "KRW",
        }),
    ]

    totals = build_portfolio_totals(accounts)

    assert totals["REAL"]["total_evaluation_krw"] == 1150000
    assert totals["REAL"]["available_cash_krw"] == 230000
    assert totals["MOCK"]["total_evaluation_krw"] == 5000000


def test_portfolio_reply_is_summary_not_holding_dump():
    reply = format_portfolio_reply(
        {
            "REAL": {"total_evaluation_krw": 1150000, "available_cash_krw": 230000, "account_count": 2},
            "MOCK": {"total_evaluation_krw": 5000000, "available_cash_krw": 1000000, "account_count": 1},
        },
        [],
        [],
    )

    assert "실거래 평가자산 합계: 1,150,000원" in reply
    assert "모의계좌 평가자산 합계: 5,000,000원" in reply
    assert "보유 현황입니다" not in reply
```

- [ ] **Step 2: 테스트가 실패하는지 확인한다**

Run:

```bash
python3 -m pytest backend/tests/test_chatbot_portfolio_summary_service.py -q
```

Expected: 모듈이 없어 FAIL한다.

- [ ] **Step 3: 통화 정규화와 환경별 합계를 구현한다**

Create `backend/services/chatbot/portfolio_summary_service.py`:

```python
def _to_float(value) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def normalize_account_summary(exchange: str, env: str, balance: dict) -> dict:
    currency = str(balance.get("currency") or balance.get("available_cash_currency") or "KRW").upper()
    rate = _to_float(balance.get("exchange_rate")) or 1500.0
    factor = 1.0 if currency == "KRW" else rate
    total = _to_float(balance.get("total_evaluation") or balance.get("total_asset") or balance.get("total_balance"))
    cash = _to_float(balance.get("available_cash") or balance.get("cash") or balance.get("krw_balance"))
    return {
        "exchange": exchange,
        "env": env,
        "currency": currency,
        "exchange_rate": rate,
        "total_evaluation": total,
        "available_cash": cash,
        "total_evaluation_krw": total * factor,
        "available_cash_krw": cash * factor,
        "holdings": balance.get("holdings") or [],
        "warning": balance.get("warning"),
    }
```

`build_portfolio_totals()`은 `REAL`, `MOCK`을 절대 합치지 않고 각 환경의 원화 환산 평가자산, 현금, 계좌 수를 반환한다. `format_portfolio_reply()`은 환경별 두 줄 요약과 조회 실패 거래소 최대 3건만 표시하고 holdings 전체 목록은 출력하지 않는다.

- [ ] **Step 4: `get_portfolio_summary()`와 `get_holdings()` 역할을 분리한다**

`get_portfolio_summary()`은 `/api/dashboard/balance` 응답을 `normalize_account_summary()`에 전달하고 `format_portfolio_reply()`를 사용한다. 반환 data는 다음 구조를 유지한다.

```python
{
    "summaries": accounts,
    "totals_by_env": totals_by_env,
    "errors": errors[:5],
    "source": "PORTFOLIO_SUMMARY",
}
```

`get_holdings()`은 기존 상세 수량 목록 역할을 유지하되 사용자가 `요약`을 요청한 경우 routing에서 `get_portfolio_summary()`가 먼저 선택되도록 `run_chatbot_tool()` 조건 순서를 조정한다.

- [ ] **Step 5: 자산 요약 회귀 테스트를 실행한다**

Run:

```bash
python3 -m pytest backend/tests/test_chatbot_portfolio_summary_service.py backend/tests/test_chatbot_profile_context.py backend/tests/test_chatbot_safety_and_proposals.py -q
```

Expected: PASS. `내 보유자산 요약해줘`는 `source=PORTFOLIO_SUMMARY`, 금액 중심 답변을 반환한다.

- [ ] **Step 6: 한글 커밋을 만든다**

```bash
git add backend/services/chatbot/portfolio_summary_service.py backend/services/chatbot/tool_registry.py backend/tests/test_chatbot_portfolio_summary_service.py backend/tests/test_chatbot_profile_context.py backend/tests/test_chatbot_safety_and_proposals.py
git commit -m "fix: 보유자산 요약을 금액과 계좌 환경 기준으로 개선"
```

---

### Task 6: Flask 앱 컨텍스트, 스트림 로그, 실제 LLM delta

**Files:**
- Create: `backend/tests/test_chatbot_llm_streaming.py`
- Modify: `backend/services/chatbot/llm_client.py:1-155`
- Modify: `backend/services/chatbot/chat_service.py:413-517`
- Modify: `backend/routes/chatbot.py:1-145`
- Modify: `backend/tests/test_chatbot_route_auth.py:47-120`

**Interfaces:**
- Produces: `ChatbotLLMClient.stream_reply(*, system_prompt: str, user_message: str, user_id: str | None, auth_header: str | None, function_schemas: list[dict] | None, history: list[dict] | None, on_delta: Callable[[str], None]) -> dict`
- Extends: `ChatbotService.reply(message: str, user_id: str | None = None, auth_header: str | None = None, user_timezone: str | None = None, trace_callback: TraceCallback | None = None, delta_callback: Callable[[str], None] | None = None) -> dict`
- SSE events: `trace`, `delta`, `done`, `error`
- `done.meta.request_id`와 `error.meta.request_id`를 반환한다.

- [ ] **Step 1: OpenAI 스트림 parser 실패 테스트를 작성한다**

Create `backend/tests/test_chatbot_llm_streaming.py`:

```python
import json

from backend.services.chatbot.llm_client import ChatbotLLMClient


class FakeStreamResponse:
    status_code = 200

    def iter_lines(self, decode_unicode=True):
        chunks = [
            {"choices": [{"delta": {"content": "첫 "}, "finish_reason": None}], "usage": None},
            {"choices": [{"delta": {"content": "답변"}, "finish_reason": "stop"}], "usage": None},
            {"choices": [], "usage": {"prompt_tokens": 10, "completion_tokens": 2, "total_tokens": 12}},
        ]
        for chunk in chunks:
            yield f"data: {json.dumps(chunk, ensure_ascii=False)}"
        yield "data: [DONE]"


def test_stream_reply_emits_openai_text_deltas(monkeypatch):
    client = ChatbotLLMClient()
    client.api_key = "test"
    monkeypatch.setattr(client, "_consume_shared_usage", lambda *args: None)
    monkeypatch.setattr("backend.services.chatbot.llm_client.requests.post", lambda *args, **kwargs: FakeStreamResponse())
    deltas = []

    result = client.stream_reply(
        system_prompt="system",
        user_message="질문",
        user_id="user-1",
        auth_header="Bearer test",
        function_schemas=[],
        history=[],
        on_delta=deltas.append,
    )

    assert deltas == ["첫 ", "답변"]
    assert result["reply"] == "첫 답변"
    assert result["usage"]["total_tokens"] == 12
```

같은 파일에 tool call delta 누적 테스트도 추가한다.

```python
def test_stream_reply_accumulates_tool_call_argument_deltas(monkeypatch):
    class FakeToolStreamResponse:
        status_code = 200

        def iter_lines(self, decode_unicode=True):
            chunks = [
                {"choices": [{"delta": {"tool_calls": [{
                    "index": 0,
                    "id": "call-1",
                    "type": "function",
                    "function": {"name": "get_portfolio_summary", "arguments": "{\"broker_"},
                }]}, "finish_reason": None}]},
                {"choices": [{"delta": {"tool_calls": [{
                    "index": 0,
                    "function": {"arguments": "env\":\"REAL\"}"},
                }]}, "finish_reason": "tool_calls"}]},
            ]
            for chunk in chunks:
                yield f"data: {json.dumps(chunk, ensure_ascii=False)}"
            yield "data: [DONE]"

    client = ChatbotLLMClient()
    client.api_key = "test"
    monkeypatch.setattr(client, "_consume_shared_usage", lambda *args: None)
    monkeypatch.setattr(
        "backend.services.chatbot.llm_client.requests.post",
        lambda *args, **kwargs: FakeToolStreamResponse(),
    )

    result = client.stream_reply(
        system_prompt="system",
        user_message="자산 알려줘",
        user_id="user-1",
        auth_header="Bearer test",
        function_schemas=[],
        history=[],
        on_delta=lambda text: None,
    )

    assert result["tool_calls"] == [{
        "id": "call-1",
        "type": "function",
        "function": {
            "name": "get_portfolio_summary",
            "arguments": "{\"broker_env\":\"REAL\"}",
        },
    }]
```

- [ ] **Step 2: route의 Flask app context와 오류 로그 실패 테스트를 작성한다**

`backend/tests/test_chatbot_route_auth.py`에 `from flask import current_app`을 추가하고 다음 테스트를 작성한다.

```python
def test_chatbot_stream_worker_has_app_context_and_logs_request_id(monkeypatch):
    monkeypatch.setattr(
        "backend.routes.chatbot.validate_access_token",
        lambda auth_header: ("user-1", "token"),
    )
    logged = []

    def fake_reply(
        message,
        user_id=None,
        auth_header=None,
        user_timezone=None,
        trace_callback=None,
        delta_callback=None,
    ):
        assert current_app.name == app.name
        raise RuntimeError("stream failed")

    monkeypatch.setattr("backend.routes.chatbot.chatbot_service.reply", fake_reply)
    monkeypatch.setattr(
        app.logger,
        "exception",
        lambda message, *args: logged.append((message, args)),
    )

    response = app.test_client().post(
        "/api/chatbot/stream",
        headers={"Authorization": "Bearer valid"},
        json={"message": "질문"},
    )
    body = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "event: error" in body
    assert '"request_id"' in body
    assert len(logged) == 1
    assert logged[0][0] == "챗봇 스트림 생성 실패: request_id=%s user_id=%s"
    assert logged[0][1][1] == "user-1"
```

- [ ] **Step 3: 스트림 테스트가 실패하는지 확인한다**

Run:

```bash
python3 -m pytest backend/tests/test_chatbot_llm_streaming.py backend/tests/test_chatbot_route_auth.py -q
```

Expected: `stream_reply`와 worker app context/logging 테스트가 FAIL한다.

- [ ] **Step 4: Chat Completions 스트림을 구현한다**

`llm_client.py`에서 요청 payload 생성과 입력/usage 제한 예약을 `_build_request_payload()`로 공통화한다. `stream_reply()`는 다음 옵션으로 요청한다.

```python
payload = {
    **base_payload,
    "stream": True,
    "stream_options": {"include_usage": True},
}
response = requests.post(
    OPENAI_CHAT_COMPLETIONS_URL,
    headers={
        "Authorization": f"Bearer {self.api_key}",
        "Content-Type": "application/json",
    },
    json=payload,
    timeout=self.timeout_seconds,
    stream=True,
)
```

각 `data:` JSON에서 `choices[0].delta.content`를 즉시 `on_delta()`에 전달하고 reply에 누적한다. `delta.tool_calls`는 index별로 합쳐 `generate_reply()`와 동일한 `tool_calls` list를 반환한다. 마지막 usage chunk를 저장한다. `[DONE]`에서 종료하며 HTTP 오류에는 status만 포함한 `RuntimeError`를 발생시킨다.

- [ ] **Step 5: ChatbotService가 delta callback을 전달한다**

`reply()` signature를 다음과 같이 확장한다.

```python
def reply(
    self,
    message: str,
    user_id: str | None = None,
    auth_header: str | None = None,
    user_timezone: str | None = None,
    trace_callback: TraceCallback | None = None,
    delta_callback: Callable[[str], None] | None = None,
) -> dict:
```

LLM 분기에서 `delta_callback`이 있으면 `stream_reply()`, 없으면 기존 `generate_reply()`를 사용한다. deterministic project tool 응답은 route가 기존 `_chunk_reply_text()`로 전달하고, LLM text 응답만 실제 OpenAI delta를 사용한다.

- [ ] **Step 6: worker app context와 request ID 로그를 구현한다**

`chatbot.py` route 진입 시 아래 값을 캡처한다.

```python
from uuid import uuid4
from flask import current_app

app = current_app._get_current_object()
request_id = uuid4().hex[:16]
```

`run_reply()`은 `with app.app_context():` 안에서 다음과 같이 모든 인자를 전달한다. 예외 시 아래 로그와 payload를 만든다.

```python
result = chatbot_service.reply(
    data.get("message"),
    user_id=user_id,
    auth_header=auth_header,
    user_timezone=data.get("timezone"),
    trace_callback=publish_trace,
    delta_callback=publish_delta,
)
```

```python
app.logger.exception(
    "챗봇 스트림 생성 실패: request_id=%s user_id=%s",
    request_id,
    user_id,
)
payload = format_error_payload(error, "챗봇 스트림 생성 실패")
payload["meta"] = {"request_id": request_id}
event_queue.put(("error", payload))
```

event queue는 `delta` 이벤트도 처리한다. 실제 delta가 하나 이상 전달된 LLM 답변은 결과 도착 후 `_chunk_reply_text()`로 다시 보내지 않는다. `done.meta.request_id`를 항상 포함한다.

- [ ] **Step 7: 스트림 관련 테스트를 통과시킨다**

Run:

```bash
python3 -m pytest backend/tests/test_chatbot_llm_streaming.py backend/tests/test_chatbot_route_auth.py backend/tests/test_chatbot_llm_limits.py -q
```

Expected: PASS. route 테스트에서 `trace -> delta -> done` 순서와 `request_id`가 확인된다.

- [ ] **Step 8: 한글 커밋을 만든다**

```bash
git add backend/services/chatbot/llm_client.py backend/services/chatbot/chat_service.py backend/routes/chatbot.py backend/tests/test_chatbot_llm_streaming.py backend/tests/test_chatbot_route_auth.py
git commit -m "fix: 챗봇 스트림 컨텍스트와 실시간 응답 로그 개선"
```

---

### Task 7: 승인 카드 타임라인, IME, null 가격, 구조화 오류 UI

**Files:**
- Create: `frontend/src/features/chatbot/chatbotInput.js`
- Create: `frontend/src/features/chatbot/chatbotInput.test.mjs`
- Create: `frontend/src/features/chatbot/chatbotTimeline.js`
- Create: `frontend/src/features/chatbot/chatbotTimeline.test.mjs`
- Modify: `frontend/src/features/chatbot/chatbotApi.js:1-97`
- Modify: `frontend/src/features/chatbot/chatbotStream.test.mjs`
- Modify: `frontend/src/features/chatbot/chatbotProposalPrecheck.js`
- Modify: `frontend/src/features/chatbot/chatbotProposalPrecheck.test.mjs`
- Modify: `frontend/src/features/chatbot/ChatbotWidget.jsx:1-135`
- Modify: `frontend/src/features/chatbot/ChatbotWidget.jsx:257-545`
- Modify: `frontend/src/features/chatbot/ChatbotWidget.jsx:600-695`

**Interfaces:**
- Produces: `shouldSubmitChatbotInput(event) -> boolean`
- Produces: `formatChatbotProposalNumber(value) -> string`
- Produces: `buildChatbotTimeline(messages, pendingProposals) -> list`
- Consumes: `buildApiErrorText(payloadOrError, fallback)`

- [ ] **Step 1: IME, null 가격, 카드 순서 실패 테스트를 작성한다**

Create `frontend/src/features/chatbot/chatbotInput.test.mjs`:

```javascript
import assert from 'node:assert/strict'
import test from 'node:test'

import { shouldSubmitChatbotInput } from './chatbotInput.js'

test('does not submit while Korean IME composition is active', () => {
  assert.equal(shouldSubmitChatbotInput({
    key: 'Enter',
    shiftKey: false,
    keyCode: 229,
    nativeEvent: { isComposing: true },
  }), false)
})

test('submits plain Enter after composition ends', () => {
  assert.equal(shouldSubmitChatbotInput({
    key: 'Enter',
    shiftKey: false,
    keyCode: 13,
    nativeEvent: { isComposing: false },
  }), true)
})
```

Create `frontend/src/features/chatbot/chatbotTimeline.test.mjs`:

```javascript
import assert from 'node:assert/strict'
import test from 'node:test'

import { buildChatbotTimeline, formatChatbotProposalNumber } from './chatbotTimeline.js'

test('places a newly created proposal after the request that created it', () => {
  const timeline = buildChatbotTimeline(
    [{ id: 'm1', createdAt: '2026-07-10T01:00:00Z' }],
    [{ id: 'p1', created_at: '2026-07-10T01:00:01Z', status: 'PENDING' }],
  )

  assert.deepEqual(timeline.map((item) => item.type), ['message', 'proposal'])
})

test('does not format a missing market price as zero', () => {
  assert.equal(formatChatbotProposalNumber(null), '-')
  assert.equal(formatChatbotProposalNumber(undefined), '-')
})
```

- [ ] **Step 2: 프론트 테스트가 실패하는지 확인한다**

Run:

```bash
node --test frontend/src/features/chatbot/chatbotInput.test.mjs frontend/src/features/chatbot/chatbotTimeline.test.mjs
```

Expected: 두 모듈이 없어 FAIL한다.

- [ ] **Step 3: 입력과 타임라인 pure helper를 구현한다**

Create `chatbotInput.js`:

```javascript
export function shouldSubmitChatbotInput(event) {
  const isComposing = Boolean(event?.nativeEvent?.isComposing || event?.isComposing || event?.keyCode === 229)
  return event?.key === 'Enter' && !event?.shiftKey && !isComposing
}
```

Create `chatbotTimeline.js`:

```javascript
function toTimestamp(value) {
  const timestamp = Date.parse(value || '')
  return Number.isFinite(timestamp) ? timestamp : Number.MAX_SAFE_INTEGER
}

export function formatChatbotProposalNumber(value) {
  if (value === null || value === undefined || value === '') return '-'
  const numeric = Number(value)
  if (!Number.isFinite(numeric)) return '-'
  return numeric.toLocaleString('ko-KR', { maximumFractionDigits: 8 })
}

export function buildChatbotTimeline(messages = [], pendingProposals = []) {
  return [
    ...messages.map((message) => ({ type: 'message', id: `message-${message.id}`, createdAt: message.createdAt, data: message })),
    ...pendingProposals.map((proposal) => ({ type: 'proposal', id: `proposal-${proposal.id}`, createdAt: proposal.created_at, data: proposal })),
  ].sort((left, right) => toTimestamp(left.createdAt) - toTimestamp(right.createdAt))
}
```

- [ ] **Step 4: 구조화 오류 문구를 챗봇 API에 적용한다**

`chatbotApi.js`에 다음 import를 추가한다.

```javascript
import { buildApiErrorText } from '../../lib/apiError'
```

HTTP 실패와 SSE `error` 이벤트 모두 아래 형식으로 예외를 만든다.

```javascript
throw new Error(buildApiErrorText(payload, '챗봇 스트림을 불러오지 못했습니다.'))
```

`chatbotStream.test.mjs`에는 `error.title`, `error.message`, `error.action`, `meta.request_id`가 포함된 SSE error frame을 parser가 보존하는 테스트를 추가한다.

- [ ] **Step 5: ChatbotWidget 렌더링과 입력을 교체한다**

다음 변경을 적용한다.

1. 로컬 `formatProposalNumber()`를 삭제하고 `formatChatbotProposalNumber()`를 사용한다.
2. 고정 상단 `pendingProposals` section을 삭제한다.
3. `buildChatbotTimeline(messages, pendingProposals)` 결과를 map하며 message와 proposal card를 생성 시각 순으로 렌더링한다.
4. proposal card는 `precheck_status !== 'OK'`이거나 `insufficient_cash`, `insufficient_holding`, `is_market_closed`, `insufficient_permission`, `futures_real_blocked`, `exceeds_real_order_limit` 중 하나가 true일 때만 승인 버튼을 disabled 처리한다. 단순 안내 `warnings`만 있는 유효 제안은 승인할 수 있다.
5. `onKeyDown`은 `shouldSubmitChatbotInput(event)`이 true일 때만 `preventDefault()`와 `submitMessage()`를 호출한다.
6. 승인/거절 fetch 오류도 `buildApiErrorText(payload, fallback)`을 사용한다.
7. `proposalActionId`로 동일 브라우저의 중복 클릭을 막되 서버 RPC가 최종 방어임을 유지한다.

타임라인 render의 핵심 형태:

```jsx
{buildChatbotTimeline(messages, pendingProposals).map((item) => (
  item.type === 'message'
    ? <ChatMessage key={item.id} message={item.data} onAction={handleAction} />
    : <TradeProposalCard key={item.id} proposal={item.data} />
))}
```

- [ ] **Step 6: 프론트 단위 테스트와 정적 검증을 실행한다**

Run:

```bash
node --test frontend/src/features/chatbot/*.test.mjs
npm --prefix frontend run lint
npm --prefix frontend run build
```

Expected: 모든 Node test PASS, ESLint 오류 0건, Vite production build 성공.

- [ ] **Step 7: 모바일 브라우저 검증을 수행한다**

실행 시 `browser:control-in-app-browser` 스킬을 사용해 로그인된 로컬 앱에서 다음을 확인한다.

- 360px: 한글 조합 중 Enter로 전송되지 않고, 조합 종료 후 Enter 1회로 메시지 1건만 전송된다.
- 430px: 새 승인 카드가 대화를 만든 사용자 메시지 뒤에 나타나며 화면 맨 위로 이동하지 않는다.
- 768px: API 미등록/사전검증 실패는 승인 카드 없이 원인과 다음 행동을 표시한다.
- 1280px: 승인/거절 버튼과 사전검증 요약이 겹치지 않는다.
- 모든 폭: `price=null`은 `0`이 아니라 `-` 또는 `시장가`로 표시된다.

- [ ] **Step 8: 한글 커밋을 만든다**

```bash
git add frontend/src/features/chatbot frontend/src/lib/apiError.js
git commit -m "fix: 챗봇 입력과 승인 카드 표시 흐름 개선"
```

---

### Task 8: 사용자 제보 시나리오 통합 회귀와 문서 동기화

**Files:**
- Modify: `database_specification.md`
- Modify: `project_structure.md`
- Modify: `README.md`

**Interfaces:**
- Verifies: Task 1~7의 사용자 흐름 전체.
- Preserves: Obsidian/DART RAG retrieval, citation, 자동메모리.

- [ ] **Step 1: Task 1~7에서 추가한 사용자 제보 회귀를 한 번에 실행한다**

Run:

```bash
python3 -m pytest backend/tests/test_chatbot_route_auth.py backend/tests/test_chatbot_profile_context.py backend/tests/test_chatbot_safety_and_proposals.py backend/tests/test_chatbot_trade_history.py backend/tests/test_chatbot_llm_limits.py backend/tests/test_chatbot_conversation_repository.py backend/tests/test_chatbot_llm_streaming.py backend/tests/test_chatbot_portfolio_summary_service.py backend/tests/test_chatbot_rag_service.py backend/tests/test_trade_proposal_approval_safety.py tests/backend/test_chatbot_order_parser.py tests/backend/test_chatbot_memory_service.py tests/backend/test_chatbot_recommendation_service.py tests/backend/test_knowledge_repository.py tests/backend/test_knowledge_routes.py -q
```

Expected: 모든 테스트 PASS.

- [ ] **Step 2: 프론트 전체 회귀와 build를 실행한다**

Run:

```bash
node --test frontend/src/features/chatbot/*.test.mjs
npm --prefix frontend run lint
npm --prefix frontend run build
```

Expected: Node test 전체 PASS, lint 오류 0건, build 성공.

- [ ] **Step 3: 문서를 실제 코드 기준으로 갱신한다**

`database_specification.md`에는 다음을 반영한다.

- `chatbot_conversation_states` 필드, TTL, RLS.
- `trade_proposals.approved_at`과 원자 승인 RPC.
- `PENDING`은 사전검증 성공 제안만 허용한다는 규칙.

`project_structure.md`에는 다음 서비스 책임을 반영한다.

- `conversation_repository.py`: 다중 워커 대화/대기/추천 상태.
- `portfolio_summary_service.py`: 통화 환산과 REAL/MOCK 분리 요약.
- `llm_client.py`: Chat Completions streaming delta/tool-call 누적.

`README.md` 챗봇 항목에는 아래 운영 규칙을 추가한다.

```markdown
- 환경 미지정 챗봇 주문 제안은 MOCK이 기본이며 REAL은 사용자가 명시한 경우에만 허용됩니다.
- 사전검증 실패, API 키 미등록, 지원하지 않는 주문유형, 실거래 10만 원 초과 요청은 PENDING 제안을 생성하지 않습니다.
- 승인 요청은 Supabase RPC로 원자 선점되어 같은 proposal_id가 중복 주문으로 전송되지 않습니다.
- 챗봇 SSE 오류는 사용자에게 request_id를 제공하고 서버 로그는 같은 request_id로 조회합니다.
```

- [ ] **Step 4: dead code와 호출부-선언부를 전수 검사한다**

Run:

```bash
rg -n "console\.log|_history_by_user|_history_loaded_users|_pending_actions|_last_recommendations_by_user|precheck_status.*FAILED" backend/services/chatbot backend/routes/chatbot.py frontend/src/features/chatbot
```

Expected: `console.log`와 제거 대상 메모리 상태 참조 0건. `precheck_status=FAILED`는 오류 응답 테스트 fixture 외에 proposal insert payload로 존재하지 않는다.

Run:

```bash
rg -n "reply\(|stream_reply\(|create_trade_proposal\(|_claim_trade_proposal_for_execution\(|buildChatbotTimeline\(|shouldSubmitChatbotInput\(" backend frontend tests
```

Expected: 모든 호출부 인자와 선언부 signature가 일치하며 사용되지 않는 import가 없다.

- [ ] **Step 5: 최종 한글 커밋을 만든다**

```bash
git add database_specification.md project_structure.md README.md
git commit -m "docs: 챗봇 안전 흐름과 검증 절차 최신화"
```

---

## 완료 기준

- `매매 제안 만들어줘`만으로는 제안이 생성되지 않고 종목·방향·금액/수량을 묻는다.
- API 키가 없거나 사전검증이 실패하면 `trade_proposals`에 새 `PENDING` row가 없다.
- 코인원 가격 없는 시장가 제안이 생성되지 않는다.
- 환경 미지정은 MOCK, 명시적 REAL만 실거래 제안이다.
- REAL 100,000원 초과는 차단되고 MOCK은 같은 금액을 허용한다.
- 같은 proposal을 동시에 승인해도 거래소 주문 호출은 1회다.
- `내 보유자산 요약해줘`는 REAL/MOCK을 분리한 원화 금액 요약을 반환한다.
- Flask worker app context 오류가 없고 스트림 실패 로그와 UI 오류에 동일 request ID가 있다.
- LLM 텍스트는 OpenAI delta 단위로 표시되고 deterministic tool 답변은 중복 출력되지 않는다.
- 승인 카드는 대화 생성 시각에 맞춰 표시되고 `price=null`을 0으로 표시하지 않는다.
- 한글 IME 조합 중 Enter는 전송하지 않는다.
- 공시·Obsidian RAG citation과 자동메모리 회귀 테스트가 통과한다.
- 관련 backend test, frontend Node test, lint, build, 4개 뷰포트 QA가 모두 통과한다.
