# Admin User Token Usage Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 관리자 페이지의 유저 관리 탭에서 사용자별 실제 OpenAI 챗봇 토큰 사용량을 조회할 수 있게 한다.

**Architecture:** 기존 추정 한도 테이블 `chatbot_usage_counters`는 유지하고, 실제 OpenAI 응답 usage는 `chatbot_token_usage_logs`에 요청 단위로 저장한다. Flask 관리자 API는 service role로 프로필과 usage 로그를 집계하고, React 관리자 내부 탭은 데스크톱 테이블과 모바일 카드로 조회 UI를 제공한다.

**Tech Stack:** Supabase SQL migrations/RLS, Flask Blueprint, Python requests, React/Vite/Tailwind, pytest, frontend node test scripts where existing coverage supports it.

## Global Constraints

- 대화 원문, tool payload, 계좌 정보, API 키, 거래소 raw 응답은 토큰 로그에 저장하지 않는다.
- `chatbot_usage_counters`는 요청 전 한도 차감용 추정 카운터로 유지하고 대체하지 않는다.
- 관리자 전체 조회는 백엔드 service role 기반 관리자 API를 통해서만 제공한다.
- 사용자 화면으로 전달되는 신규/수정 API 실패는 `format_error_payload()`를 사용한다.
- UI는 `design.md`의 Obsidian Navy 배경, Slate border, AI Cyan 강조 색상을 따른다.
- 긴 이메일은 `truncate` 또는 `break-all`로 처리한다.
- 360px, 430px, 768px, 1280px 폭에서 버튼/텍스트 겹침이 없어야 한다.
- 이번 범위에서 계정 정지, 권한 변경, API 키 원문 열람, 암호화 비밀 복호화 노출, 관리자 임의 주문 실행은 제외한다.
- OpenAI 비용 금액 계산은 이번 범위에서 제외한다.

---

## File Structure

- Create: `supabase/migrations/20260714103000_create_chatbot_token_usage_logs.sql`
  - 실제 usage 로그 테이블, RLS, 인덱스, 권한을 정의한다.
- Modify: `backend/services/chatbot/llm_client.py`
  - OpenAI usage 정규화와 best-effort 로그 저장 helper를 추가하고 `generate_reply`, `synthesize_tool_result_reply`, `stream_reply`에서 호출한다.
- Modify: `backend/services/chatbot/chat_service.py`
  - tool synthesis 호출부에 `auth_header`와 `user_id`를 전달한다.
- Create: `backend/routes/admin_users.py`
  - 관리자 권한 검증, 사용자 목록 집계, 사용자별 상세 usage API를 제공한다.
- Modify: `backend/app.py`
  - `admin_users_bp`를 등록한다.
- Create: `backend/tests/test_chatbot_token_usage_logging.py`
  - 실제 usage 로그 저장 helper와 실패 허용을 검증한다.
- Create: `backend/tests/test_admin_users.py`
  - 관리자 API 권한, 목록 집계, 상세 집계를 검증한다.
- Create: `frontend/src/pages/AdminUsers.jsx`
  - 데스크톱 유저 관리 탭 UI를 구현한다.
- Create: `frontend/src/pages/mobile/MobileAdminUsers.jsx`
  - 모바일 유저 관리 탭 UI를 구현한다.
- Modify: `frontend/src/pages/AdminMlData.jsx`
  - 내부 탭에 `유저 관리`를 추가하고 `AdminUsers`를 렌더링한다.
- Modify: `frontend/src/pages/mobile/MobileAdminMlData.jsx`
  - 모바일 내부 탭에 `유저 관리`를 추가하고 `MobileAdminUsers`를 렌더링한다.
- Modify: `database_specification.md`
  - `chatbot_token_usage_logs` 테이블과 관리자 사용량 조회 흐름을 문서화한다.
- Modify: `project_structure.md`
  - 신규 라우트와 프론트 페이지를 반영한다.

---

### Task 1: 실제 챗봇 토큰 사용량 로그 테이블

**Files:**
- Create: `supabase/migrations/20260714103000_create_chatbot_token_usage_logs.sql`
- Modify: `database_specification.md`

**Interfaces:**
- Produces: `public.chatbot_token_usage_logs` table with columns `id`, `user_id`, `request_id`, `request_type`, `model`, `prompt_tokens`, `completion_tokens`, `total_tokens`, `created_at`.
- Consumes: `public.profiles(id)`.

- [ ] **Step 1: Write the migration**

Create `supabase/migrations/20260714103000_create_chatbot_token_usage_logs.sql`:

```sql
CREATE TABLE IF NOT EXISTS public.chatbot_token_usage_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES public.profiles(id) ON DELETE CASCADE,
    request_id TEXT,
    request_type TEXT NOT NULL,
    model TEXT NOT NULL,
    prompt_tokens INTEGER NOT NULL DEFAULT 0 CHECK (prompt_tokens >= 0),
    completion_tokens INTEGER NOT NULL DEFAULT 0 CHECK (completion_tokens >= 0),
    total_tokens INTEGER NOT NULL DEFAULT 0 CHECK (total_tokens >= 0),
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT timezone('utc'::text, now()),
    CONSTRAINT chatbot_token_usage_logs_request_type_not_blank CHECK (length(trim(request_type)) > 0),
    CONSTRAINT chatbot_token_usage_logs_model_not_blank CHECK (length(trim(model)) > 0)
);

CREATE INDEX IF NOT EXISTS chatbot_token_usage_logs_user_created_idx
    ON public.chatbot_token_usage_logs (user_id, created_at DESC);

CREATE INDEX IF NOT EXISTS chatbot_token_usage_logs_created_idx
    ON public.chatbot_token_usage_logs (created_at DESC);

ALTER TABLE public.chatbot_token_usage_logs ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "사용자는 자신의 챗봇 실제 토큰 로그만 조회 가능"
    ON public.chatbot_token_usage_logs;
CREATE POLICY "사용자는 자신의 챗봇 실제 토큰 로그만 조회 가능"
    ON public.chatbot_token_usage_logs
    FOR SELECT
    TO authenticated
    USING ((select auth.uid()) = user_id);

DROP POLICY IF EXISTS "사용자는 자신의 챗봇 실제 토큰 로그만 생성 가능"
    ON public.chatbot_token_usage_logs;
CREATE POLICY "사용자는 자신의 챗봇 실제 토큰 로그만 생성 가능"
    ON public.chatbot_token_usage_logs
    FOR INSERT
    TO authenticated
    WITH CHECK ((select auth.uid()) = user_id);

GRANT SELECT, INSERT ON TABLE public.chatbot_token_usage_logs TO authenticated;
```

- [ ] **Step 2: Update database specification**

Add this section after `### 2.17 chatbot_usage_counters` in `database_specification.md`:

```markdown
### 2.17.1 chatbot_token_usage_logs
*   **용도**: OpenAI Chat Completions 응답에서 반환된 실제 챗봇 토큰 사용량을 요청 단위로 저장합니다. 기존 `chatbot_usage_counters`는 한도 차감용 추정 카운터이며, 이 테이블은 관리자 관찰과 감사용 실제 사용량 로그입니다.
*   **주요 컬럼**:
    *   `id` (UUID, PK)
    *   `user_id` (UUID, FK) - `profiles.id` 참조
    *   `request_id` (TEXT) - Flask 요청 ID 또는 추적 식별자
    *   `request_type` (TEXT) - `chat_reply`, `chat_stream`, `tool_synthesis` 등 호출 유형
    *   `model` (TEXT) - OpenAI 모델명
    *   `prompt_tokens` (INTEGER) - 실제 입력 토큰 수
    *   `completion_tokens` (INTEGER) - 실제 출력 토큰 수
    *   `total_tokens` (INTEGER) - 실제 전체 토큰 수
    *   `created_at` (TIMESTAMPTZ)
*   **보안 원칙**:
    *   대화 원문, tool payload, 계좌 정보, API 키, 거래소 raw 응답은 저장하지 않습니다.
    *   일반 사용자는 자신의 로그만 조회/생성할 수 있습니다.
    *   관리자 전체 집계는 백엔드 service role 기반 `/api/admin/users` 계열 API에서만 제공합니다.
```

- [ ] **Step 3: Verify migration syntax locally**

Run:

```bash
rg -n "chatbot_token_usage_logs|CREATE TABLE|CREATE POLICY" supabase/migrations/20260714103000_create_chatbot_token_usage_logs.sql database_specification.md
```

Expected: shows the new table, policies, and database specification section.

- [ ] **Step 4: Commit**

```bash
git add supabase/migrations/20260714103000_create_chatbot_token_usage_logs.sql database_specification.md
git commit -m "feat: add chatbot token usage log table"
```

---

### Task 2: LLM 실제 Usage 기록

**Files:**
- Modify: `backend/services/chatbot/llm_client.py`
- Modify: `backend/services/chatbot/chat_service.py`
- Create: `backend/tests/test_chatbot_token_usage_logging.py`

**Interfaces:**
- Consumes: `public.chatbot_token_usage_logs` from Task 1.
- Produces: `ChatbotLLMClient._record_actual_usage(auth_header: str | None, user_id: str | None, usage: dict | None, request_type: str) -> None`.
- Produces: `ChatbotLLMClient._normalize_usage(usage: dict | None) -> dict | None`.

- [ ] **Step 1: Write failing tests**

Create `backend/tests/test_chatbot_token_usage_logging.py`:

```python
from backend.services.chatbot.llm_client import ChatbotLLMClient


class FakeResponse:
    status_code = 200

    @staticmethod
    def json():
        return {
            "choices": [{"message": {"content": "응답"}}],
            "usage": {
                "prompt_tokens": 11,
                "completion_tokens": 7,
                "total_tokens": 18,
            },
        }


def test_normalize_usage_requires_positive_total_tokens():
    client = ChatbotLLMClient()

    assert client._normalize_usage(None) is None
    assert client._normalize_usage({}) is None
    assert client._normalize_usage({"total_tokens": 0}) is None
    assert client._normalize_usage({
        "prompt_tokens": "4",
        "completion_tokens": 3,
        "total_tokens": 7,
    }) == {
        "prompt_tokens": 4,
        "completion_tokens": 3,
        "total_tokens": 7,
    }


def test_generate_reply_records_actual_usage(monkeypatch):
    calls = []
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(
        "backend.services.chatbot.llm_client.requests.post",
        lambda *args, **kwargs: FakeResponse(),
    )

    def fake_query(auth_header, endpoint, method="GET", json_data=None, params=None, extra_headers=None):
        if endpoint == "rpc/consume_chatbot_usage":
            return [{"allowed": True}]
        calls.append({
            "auth_header": auth_header,
            "endpoint": endpoint,
            "method": method,
            "json_data": json_data,
        })
        return []

    monkeypatch.setattr("backend.services.chatbot.llm_client.query_supabase", fake_query)

    client = ChatbotLLMClient()
    result = client.generate_reply(
        system_prompt="시스템",
        user_message="질문",
        user_id="user-1",
        auth_header="Bearer test",
    )

    assert result["usage"]["total_tokens"] == 18
    assert calls == [{
        "auth_header": "Bearer test",
        "endpoint": "chatbot_token_usage_logs",
        "method": "POST",
        "json_data": {
            "user_id": "user-1",
            "request_type": "chat_reply",
            "model": client.model,
            "prompt_tokens": 11,
            "completion_tokens": 7,
            "total_tokens": 18,
        },
    }]


def test_usage_logging_failure_does_not_fail_reply(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(
        "backend.services.chatbot.llm_client.requests.post",
        lambda *args, **kwargs: FakeResponse(),
    )

    def fake_query(auth_header, endpoint, method="GET", json_data=None, params=None, extra_headers=None):
        if endpoint == "rpc/consume_chatbot_usage":
            return [{"allowed": True}]
        raise RuntimeError("Supabase unavailable")

    monkeypatch.setattr("backend.services.chatbot.llm_client.query_supabase", fake_query)

    client = ChatbotLLMClient()
    result = client.generate_reply(
        system_prompt="시스템",
        user_message="질문",
        user_id="user-1",
        auth_header="Bearer test",
    )

    assert result["reply"] == "응답"
    assert result["usage"]["total_tokens"] == 18
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```bash
PYTHONPATH=. pytest backend/tests/test_chatbot_token_usage_logging.py -q
```

Expected: fails because `_normalize_usage` and `_record_actual_usage` do not exist.

- [ ] **Step 3: Implement usage normalization and logging**

In `backend/services/chatbot/llm_client.py`, add these methods inside `ChatbotLLMClient` after `_consume_shared_usage`:

```python
    @staticmethod
    def _usage_int(value) -> int:
        try:
            parsed = int(value or 0)
            return parsed if parsed >= 0 else 0
        except (TypeError, ValueError):
            return 0

    def _normalize_usage(self, usage: dict | None) -> dict | None:
        if not isinstance(usage, dict):
            return None

        normalized = {
            "prompt_tokens": self._usage_int(usage.get("prompt_tokens")),
            "completion_tokens": self._usage_int(usage.get("completion_tokens")),
            "total_tokens": self._usage_int(usage.get("total_tokens")),
        }
        if normalized["total_tokens"] <= 0:
            return None
        return normalized

    def _record_actual_usage(
        self,
        *,
        auth_header: str | None,
        user_id: str | None,
        usage: dict | None,
        request_type: str,
    ) -> None:
        normalized = self._normalize_usage(usage)
        if not auth_header or not user_id or not normalized:
            return

        payload = {
            "user_id": user_id,
            "request_type": str(request_type or "chat_reply").strip() or "chat_reply",
            "model": self.model,
            **normalized,
        }
        try:
            query_supabase(auth_header, "chatbot_token_usage_logs", "POST", json_data=payload)
        except Exception:
            return
```

- [ ] **Step 4: Call logging from non-streaming reply**

In `generate_reply()`, after `usage = data.get("usage") or {}` and before `return`, add:

```python
        self._record_actual_usage(
            auth_header=auth_header,
            user_id=user_id,
            usage=usage,
            request_type="chat_reply",
        )
```

- [ ] **Step 5: Extend tool synthesis signature and logging**

Change `synthesize_tool_result_reply` signature in `backend/services/chatbot/llm_client.py` to include:

```python
        user_id: str | None = None,
        auth_header: str | None = None,
```

Add before its return:

```python
        self._record_actual_usage(
            auth_header=auth_header,
            user_id=user_id,
            usage=usage,
            request_type="tool_synthesis",
        )
```

Update `backend/services/chatbot/chat_service.py` around the existing synthesis call:

```python
        synthesis = self.llm_client.synthesize_tool_result_reply(
            system_prompt=system_prompt,
            user_message=message,
            tool_name=tool_name,
            tool_reply=tool_reply,
            tool_data=tool_data,
            user_id=user_id,
            auth_header=auth_header,
        )
```

- [ ] **Step 6: Log streaming usage**

In `stream_reply()` just before its final `return`, add:

```python
        self._record_actual_usage(
            auth_header=auth_header,
            user_id=user_id,
            usage=usage,
            request_type="chat_stream",
        )
```

- [ ] **Step 7: Run focused tests**

Run:

```bash
PYTHONPATH=. pytest backend/tests/test_chatbot_token_usage_logging.py backend/tests/test_chatbot_llm_limits.py backend/tests/test_chatbot_llm_streaming.py -q
```

Expected: all selected tests pass.

- [ ] **Step 8: Commit**

```bash
git add backend/services/chatbot/llm_client.py backend/services/chatbot/chat_service.py backend/tests/test_chatbot_token_usage_logging.py
git commit -m "feat: log actual chatbot token usage"
```

---

### Task 3: 관리자 유저 사용량 API

**Files:**
- Create: `backend/routes/admin_users.py`
- Modify: `backend/app.py`
- Create: `backend/tests/test_admin_users.py`

**Interfaces:**
- Consumes: `chatbot_token_usage_logs`, `profiles`.
- Produces: `GET /api/admin/users`.
- Produces: `GET /api/admin/users/<user_id>/chatbot-usage`.

- [ ] **Step 1: Write failing route tests**

Create `backend/tests/test_admin_users.py`:

```python
from datetime import datetime, timedelta, timezone

import pytest
from flask import Flask

from backend.routes import admin_users


@pytest.fixture
def client():
    app = Flask(__name__)
    app.config["TESTING"] = True
    app.register_blueprint(admin_users.admin_users_bp)
    return app.test_client()


def test_list_admin_users_requires_admin(monkeypatch, client):
    monkeypatch.setattr(
        admin_users,
        "_verify_admin",
        lambda auth_header: (_ for _ in ()).throw(PermissionError("관리자 권한이 필요합니다.")),
    )

    response = client.get("/api/admin/users", headers={"Authorization": "Bearer user"})

    assert response.status_code == 403
    payload = response.get_json()
    assert payload["success"] is False
    assert "error" in payload


def test_list_admin_users_returns_usage_summary(monkeypatch, client):
    now = datetime.now(timezone.utc)

    monkeypatch.setattr(admin_users, "_verify_admin", lambda auth_header: {"id": "admin-1"})
    monkeypatch.setattr(admin_users, "_utc_now", lambda: now)

    def fake_request(endpoint, method="GET", params=None, json_data=None, extra_headers=None):
        if endpoint == "profiles":
            return [
                {"id": "user-1", "email": "a@example.com", "nickname": "alpha", "role": "USER", "updated_at": "2026-07-14T00:00:00Z"},
                {"id": "user-2", "email": "b@example.com", "nickname": "beta", "role": "ADMIN", "updated_at": "2026-07-13T00:00:00Z"},
            ]
        if endpoint == "chatbot_token_usage_logs":
            return [
                {"user_id": "user-1", "prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15, "created_at": now.isoformat()},
                {"user_id": "user-1", "prompt_tokens": 20, "completion_tokens": 10, "total_tokens": 30, "created_at": (now - timedelta(days=8)).isoformat()},
                {"user_id": "user-2", "prompt_tokens": 7, "completion_tokens": 3, "total_tokens": 10, "created_at": now.isoformat()},
            ]
        return []

    monkeypatch.setattr(admin_users, "_supabase_request", fake_request)

    response = client.get("/api/admin/users", headers={"Authorization": "Bearer admin"})

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["success"] is True
    assert payload["summary"]["totalUsers"] == 2
    assert payload["summary"]["todayTokens"] == 25
    assert payload["summary"]["tokens30d"] == 55
    assert payload["data"][0]["usage"]["totalTokens"] == 45
    assert payload["data"][0]["usage"]["tokens7d"] == 15


def test_get_admin_user_chatbot_usage_returns_daily_rows(monkeypatch, client):
    now = datetime(2026, 7, 14, 5, 0, tzinfo=timezone.utc)

    monkeypatch.setattr(admin_users, "_verify_admin", lambda auth_header: {"id": "admin-1"})
    monkeypatch.setattr(admin_users, "_utc_now", lambda: now)

    def fake_request(endpoint, method="GET", params=None, json_data=None, extra_headers=None):
        if endpoint == "profiles":
            return [{"id": "user-1", "email": "a@example.com", "nickname": "alpha", "role": "USER", "updated_at": "2026-07-14T00:00:00Z"}]
        if endpoint == "chatbot_token_usage_logs":
            return [
                {"user_id": "user-1", "request_type": "chat_reply", "model": "gpt-test", "prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15, "created_at": "2026-07-14T01:00:00+00:00"},
                {"user_id": "user-1", "request_type": "tool_synthesis", "model": "gpt-test", "prompt_tokens": 20, "completion_tokens": 10, "total_tokens": 30, "created_at": "2026-07-13T01:00:00+00:00"},
            ]
        return []

    monkeypatch.setattr(admin_users, "_supabase_request", fake_request)

    response = client.get("/api/admin/users/user-1/chatbot-usage", headers={"Authorization": "Bearer admin"})

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["success"] is True
    assert payload["user"]["email"] == "a@example.com"
    assert payload["daily"][0] == {
        "date": "2026-07-14",
        "promptTokens": 10,
        "completionTokens": 5,
        "totalTokens": 15,
        "requestCount": 1,
    }
    assert payload["byRequestType"]["tool_synthesis"]["totalTokens"] == 30
    assert payload["recentLogs"][0]["requestType"] == "chat_reply"
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```bash
PYTHONPATH=. pytest backend/tests/test_admin_users.py -q
```

Expected: fails because `backend.routes.admin_users` does not exist.

- [ ] **Step 3: Implement admin users route module**

Create `backend/routes/admin_users.py` with these functions and routes:

```python
import os
from collections import defaultdict
from datetime import datetime, timedelta, timezone

import requests
from flask import Blueprint, jsonify, request

from backend.services.error_message_service import format_error_payload


admin_users_bp = Blueprint("admin_users", __name__)

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY")
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

ALLOWED_SORTS = {
    "today_tokens",
    "tokens_7d",
    "tokens_30d",
    "total_tokens",
    "recent_used_at",
    "created_at",
}


def _utc_now():
    return datetime.now(timezone.utc)


def _json_error(error, title, status_code):
    payload = format_error_payload(error, title)
    return jsonify(payload), status_code


def _extract_bearer_token(auth_header):
    if not auth_header or not auth_header.startswith("Bearer "):
        raise ValueError("로그인이 필요합니다.")
    token = auth_header.split(" ", 1)[1].strip()
    if not token:
        raise ValueError("로그인이 필요합니다.")
    return token


def _require_supabase_config():
    if not SUPABASE_URL or not SUPABASE_ANON_KEY or not SUPABASE_SERVICE_ROLE_KEY:
        raise RuntimeError("Supabase 관리자 조회 환경변수가 설정되어 있지 않습니다.")


def _service_headers(extra_headers=None):
    headers = {
        "apikey": SUPABASE_SERVICE_ROLE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
        "Content-Type": "application/json",
    }
    if extra_headers:
        headers.update(extra_headers)
    return headers


def _supabase_request(endpoint, method="GET", params=None, json_data=None, extra_headers=None):
    _require_supabase_config()
    response = requests.request(
        method,
        f"{SUPABASE_URL}/rest/v1/{endpoint}",
        headers=_service_headers(extra_headers),
        params=params,
        json=json_data,
        timeout=15,
    )
    if response.status_code not in (200, 201, 204):
        raise RuntimeError(f"Supabase 관리자 조회에 실패했습니다. HTTP {response.status_code}")
    if not response.text:
        return None
    return response.json()


def _verify_admin(auth_header):
    _require_supabase_config()
    token = _extract_bearer_token(auth_header)
    user_response = requests.get(
        f"{SUPABASE_URL}/auth/v1/user",
        headers={"apikey": SUPABASE_ANON_KEY, "Authorization": f"Bearer {token}"},
        timeout=15,
    )
    if user_response.status_code != 200:
        raise PermissionError("유효한 로그인이 필요합니다.")
    user = user_response.json() or {}
    user_id = user.get("id")
    if not user_id:
        raise PermissionError("유효한 로그인이 필요합니다.")
    rows = _supabase_request(
        "profiles",
        params={"select": "id,email,nickname,role", "id": f"eq.{user_id}", "limit": "1"},
    ) or []
    profile = rows[0] if rows else {}
    if profile.get("role") != "ADMIN":
        raise PermissionError("관리자 권한이 필요합니다.")
    return {"id": user_id, "email": user.get("email") or profile.get("email"), "profile": profile}
```

Then add helpers:

```python
def _parse_datetime(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def _int_value(value):
    try:
        parsed = int(value or 0)
        return parsed if parsed >= 0 else 0
    except (TypeError, ValueError):
        return 0


def _load_profiles(query, limit):
    params = {
        "select": "id,email,nickname,role,updated_at",
        "order": "updated_at.desc",
        "limit": str(limit),
    }
    if query:
        safe_query = query.replace("%", "").replace(",", " ").strip()
        params["or"] = f"(email.ilike.*{safe_query}*,nickname.ilike.*{safe_query}*)"
    return _supabase_request("profiles", params=params) or []


def _load_usage_logs(user_ids, since=None):
    ids = [str(user_id) for user_id in user_ids if user_id]
    if not ids:
        return []
    params = {
        "select": "user_id,request_type,model,prompt_tokens,completion_tokens,total_tokens,created_at",
        "user_id": f"in.({','.join(ids)})",
        "order": "created_at.desc",
    }
    if since:
        params["created_at"] = f"gte.{since.isoformat()}"
    return _supabase_request("chatbot_token_usage_logs", params=params) or []


def _build_usage_by_user(logs, now):
    today = now.date()
    seven_days_ago = now - timedelta(days=7)
    thirty_days_ago = now - timedelta(days=30)
    usage = defaultdict(lambda: {
        "todayTokens": 0,
        "tokens7d": 0,
        "tokens30d": 0,
        "totalTokens": 0,
        "todayRequests": 0,
        "requests30d": 0,
        "recentUsedAt": None,
    })
    for row in logs:
        user_usage = usage[row.get("user_id")]
        created_at = _parse_datetime(row.get("created_at"))
        total_tokens = _int_value(row.get("total_tokens"))
        user_usage["totalTokens"] += total_tokens
        if created_at:
            iso_value = created_at.isoformat()
            if not user_usage["recentUsedAt"] or iso_value > user_usage["recentUsedAt"]:
                user_usage["recentUsedAt"] = iso_value
            if created_at.date() == today:
                user_usage["todayTokens"] += total_tokens
                user_usage["todayRequests"] += 1
            if created_at >= seven_days_ago:
                user_usage["tokens7d"] += total_tokens
            if created_at >= thirty_days_ago:
                user_usage["tokens30d"] += total_tokens
                user_usage["requests30d"] += 1
    return usage
```

Then add routes:

```python
@admin_users_bp.route("/api/admin/users", methods=["GET"])
def list_admin_users():
    try:
        _verify_admin(request.headers.get("Authorization"))
        query = str(request.args.get("q") or "").strip()
        sort = str(request.args.get("sort") or "tokens_30d")
        order = str(request.args.get("order") or "desc").lower()
        limit = min(max(int(request.args.get("limit") or 50), 1), 200)
        if sort not in ALLOWED_SORTS:
            sort = "tokens_30d"
        if order not in {"asc", "desc"}:
            order = "desc"

        profiles = _load_profiles(query, limit)
        now = _utc_now()
        usage_by_user = _build_usage_by_user(_load_usage_logs([row.get("id") for row in profiles]), now)
        rows = []
        for profile in profiles:
            row_usage = usage_by_user[profile.get("id")]
            rows.append({
                "id": profile.get("id"),
                "email": profile.get("email") or "",
                "nickname": profile.get("nickname") or "",
                "role": profile.get("role") or "USER",
                "updatedAt": profile.get("updated_at"),
                "usage": row_usage,
            })

        sort_key_map = {
            "today_tokens": lambda item: item["usage"]["todayTokens"],
            "tokens_7d": lambda item: item["usage"]["tokens7d"],
            "tokens_30d": lambda item: item["usage"]["tokens30d"],
            "total_tokens": lambda item: item["usage"]["totalTokens"],
            "recent_used_at": lambda item: item["usage"]["recentUsedAt"] or "",
            "created_at": lambda item: item["updatedAt"] or "",
        }
        rows.sort(key=sort_key_map[sort], reverse=(order == "desc"))

        summary = {
            "totalUsers": len(rows),
            "todayTokens": sum(item["usage"]["todayTokens"] for item in rows),
            "tokens30d": sum(item["usage"]["tokens30d"] for item in rows),
            "activeUsers24h": sum(1 for item in rows if item["usage"]["recentUsedAt"] and _parse_datetime(item["usage"]["recentUsedAt"]) and _parse_datetime(item["usage"]["recentUsedAt"]) >= now - timedelta(hours=24)),
        }
        return jsonify({"success": True, "data": rows, "summary": summary})
    except ValueError as error:
        return _json_error(error, "유저 관리 조회 실패", 401)
    except PermissionError as error:
        return _json_error(error, "유저 관리 권한 확인 실패", 403)
    except Exception as error:
        return _json_error(error, "유저 관리 조회 실패", 500)
```

Add detail route:

```python
@admin_users_bp.route("/api/admin/users/<user_id>/chatbot-usage", methods=["GET"])
def get_admin_user_chatbot_usage(user_id):
    try:
        _verify_admin(request.headers.get("Authorization"))
        days = min(max(int(request.args.get("days") or 30), 1), 180)
        limit = min(max(int(request.args.get("limit") or 50), 1), 200)
        since = _utc_now() - timedelta(days=days)
        profiles = _supabase_request(
            "profiles",
            params={"select": "id,email,nickname,role,updated_at", "id": f"eq.{user_id}", "limit": "1"},
        ) or []
        if not profiles:
            return _json_error(ValueError("사용자를 찾을 수 없습니다."), "유저 사용량 조회 실패", 404)

        logs = _load_usage_logs([user_id], since=since)
        daily = defaultdict(lambda: {"promptTokens": 0, "completionTokens": 0, "totalTokens": 0, "requestCount": 0})
        by_type = defaultdict(lambda: {"promptTokens": 0, "completionTokens": 0, "totalTokens": 0, "requestCount": 0})
        recent_logs = []
        for row in logs:
            created_at = _parse_datetime(row.get("created_at"))
            date_key = created_at.date().isoformat() if created_at else "unknown"
            request_type = row.get("request_type") or "unknown"
            prompt_tokens = _int_value(row.get("prompt_tokens"))
            completion_tokens = _int_value(row.get("completion_tokens"))
            total_tokens = _int_value(row.get("total_tokens"))
            for bucket in (daily[date_key], by_type[request_type]):
                bucket["promptTokens"] += prompt_tokens
                bucket["completionTokens"] += completion_tokens
                bucket["totalTokens"] += total_tokens
                bucket["requestCount"] += 1
            if len(recent_logs) < limit:
                recent_logs.append({
                    "createdAt": row.get("created_at"),
                    "requestType": request_type,
                    "model": row.get("model") or "",
                    "promptTokens": prompt_tokens,
                    "completionTokens": completion_tokens,
                    "totalTokens": total_tokens,
                })

        daily_rows = [
            {"date": key, **value}
            for key, value in sorted(daily.items(), key=lambda item: item[0], reverse=True)
        ]
        profile = profiles[0]
        return jsonify({
            "success": True,
            "user": {
                "id": profile.get("id"),
                "email": profile.get("email") or "",
                "nickname": profile.get("nickname") or "",
                "role": profile.get("role") or "USER",
                "updatedAt": profile.get("updated_at"),
            },
            "daily": daily_rows,
            "byRequestType": dict(by_type),
            "recentLogs": recent_logs,
        })
    except ValueError as error:
        return _json_error(error, "유저 사용량 조회 실패", 401)
    except PermissionError as error:
        return _json_error(error, "유저 사용량 권한 확인 실패", 403)
    except Exception as error:
        return _json_error(error, "유저 사용량 조회 실패", 500)
```

- [ ] **Step 4: Register blueprint**

In `backend/app.py`, add import near other route imports:

```python
from backend.routes.admin_users import admin_users_bp
```

Add registration near `admin_inquiries_bp`:

```python
app.register_blueprint(admin_users_bp)
```

- [ ] **Step 5: Run route tests**

Run:

```bash
PYTHONPATH=. pytest backend/tests/test_admin_users.py -q
```

Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
git add backend/routes/admin_users.py backend/app.py backend/tests/test_admin_users.py
git commit -m "feat: add admin user usage api"
```

---

### Task 4: 데스크톱 관리자 유저 관리 탭

**Files:**
- Create: `frontend/src/pages/AdminUsers.jsx`
- Modify: `frontend/src/pages/AdminMlData.jsx`

**Interfaces:**
- Consumes: `GET /api/admin/users`.
- Consumes: `GET /api/admin/users/<user_id>/chatbot-usage`.
- Produces: `AdminUsers({ isLoggedIn, userEmail, handleLogout, hideHeader })`.

- [ ] **Step 1: Create desktop component**

Create `frontend/src/pages/AdminUsers.jsx`:

```jsx
import { useEffect, useMemo, useState } from 'react'
import Header from '../components/Header.jsx'
import { supabase } from '../supabaseClient.js'
import { getApiErrorMessage } from '../lib/apiError.js'

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:5050'

const numberFormatter = new Intl.NumberFormat('ko-KR')

function formatNumber(value) {
  return numberFormatter.format(Number(value || 0))
}

function formatDateTime(value) {
  const date = value ? new Date(value) : null
  if (!date || Number.isNaN(date.getTime())) return '-'
  return date.toLocaleString('ko-KR', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })
}

function SummaryCard({ label, value, detail }) {
  return (
    <div className="rounded-lg border border-slate-800 bg-[#0f172a] p-4">
      <p className="text-xs font-bold text-slate-400">{label}</p>
      <p className="mt-2 font-mono text-2xl font-extrabold text-white">{value}</p>
      {detail ? <p className="mt-1 text-xs text-slate-500">{detail}</p> : null}
    </div>
  )
}

export default function AdminUsers({ isLoggedIn, userEmail, handleLogout, hideHeader = false }) {
  const [users, setUsers] = useState([])
  const [summary, setSummary] = useState({ totalUsers: 0, todayTokens: 0, tokens30d: 0, activeUsers24h: 0 })
  const [query, setQuery] = useState('')
  const [sort, setSort] = useState('tokens_30d')
  const [order, setOrder] = useState('desc')
  const [selectedUserId, setSelectedUserId] = useState('')
  const [detail, setDetail] = useState(null)
  const [loading, setLoading] = useState(false)
  const [detailLoading, setDetailLoading] = useState(false)
  const [error, setError] = useState('')
  const [detailError, setDetailError] = useState('')

  const selectedUser = useMemo(
    () => users.find((item) => item.id === selectedUserId) || users[0] || null,
    [selectedUserId, users],
  )

  const authHeaders = async () => {
    const { data: { session } } = await supabase.auth.getSession()
    if (!session?.access_token) throw new Error('로그인이 필요합니다.')
    return { Authorization: `Bearer ${session.access_token}` }
  }

  const loadUsers = async () => {
    setLoading(true)
    setError('')
    try {
      const headers = await authHeaders()
      const params = new URLSearchParams({ sort, order, limit: '100' })
      if (query.trim()) params.set('q', query.trim())
      const response = await fetch(`${API_BASE_URL}/api/admin/users?${params.toString()}`, { headers })
      const payload = await response.json().catch(() => ({}))
      if (!response.ok || payload.success === false) {
        throw new Error(getApiErrorMessage(payload, '유저 목록을 불러오지 못했습니다.'))
      }
      const rows = payload.data || []
      setUsers(rows)
      setSummary(payload.summary || {})
      setSelectedUserId((current) => current || rows[0]?.id || '')
    } catch (requestError) {
      setUsers([])
      setSummary({ totalUsers: 0, todayTokens: 0, tokens30d: 0, activeUsers24h: 0 })
      setError(requestError.message || '유저 목록을 불러오지 못했습니다.')
    } finally {
      setLoading(false)
    }
  }

  const loadDetail = async (userId) => {
    if (!userId) {
      setDetail(null)
      return
    }
    setDetailLoading(true)
    setDetailError('')
    try {
      const headers = await authHeaders()
      const response = await fetch(`${API_BASE_URL}/api/admin/users/${userId}/chatbot-usage?days=30&limit=50`, { headers })
      const payload = await response.json().catch(() => ({}))
      if (!response.ok || payload.success === false) {
        throw new Error(getApiErrorMessage(payload, '유저 사용량을 불러오지 못했습니다.'))
      }
      setDetail(payload)
    } catch (requestError) {
      setDetail(null)
      setDetailError(requestError.message || '유저 사용량을 불러오지 못했습니다.')
    } finally {
      setDetailLoading(false)
    }
  }

  useEffect(() => {
    loadUsers()
  }, [sort, order])

  useEffect(() => {
    if (selectedUser?.id) loadDetail(selectedUser.id)
  }, [selectedUser?.id])

  return (
    <div className={hideHeader ? 'font-inter text-[#e2e2ec]' : 'min-h-screen bg-obsidian-bg font-inter text-[#e2e2ec]'}>
      <div className={hideHeader ? 'grid gap-6' : 'mx-auto grid max-w-7xl gap-6 px-6 py-8'}>
        {!hideHeader ? <Header isLoggedIn={isLoggedIn} userEmail={userEmail} handleLogout={handleLogout} /> : null}

        <section className="rounded-lg border border-slate-700/80 bg-slate-surface p-4 sm:p-5">
          <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
            <div>
              <p className="text-[10px] font-bold uppercase tracking-[0.16em] text-ai-cyan">Admin Users</p>
              <h1 className="mt-1 text-2xl font-extrabold text-white">유저 관리</h1>
              <p className="mt-2 text-sm text-slate-400">사용자별 실제 챗봇 토큰 사용량과 최근 사용 흐름을 확인합니다.</p>
            </div>
            <div className="grid gap-2 sm:grid-cols-[minmax(220px,1fr)_150px_120px_auto]">
              <input
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === 'Enter') loadUsers()
                }}
                className="rounded border border-slate-700 bg-[#0f172a] px-3 py-2 text-sm text-white outline-none transition focus:border-ai-cyan"
                placeholder="이메일 또는 닉네임 검색"
              />
              <select value={sort} onChange={(event) => setSort(event.target.value)} className="rounded border border-slate-700 bg-[#0f172a] px-3 py-2 text-xs font-bold text-slate-300 outline-none focus:border-ai-cyan">
                <option value="tokens_30d">30일 토큰</option>
                <option value="today_tokens">오늘 토큰</option>
                <option value="tokens_7d">7일 토큰</option>
                <option value="total_tokens">전체 토큰</option>
                <option value="recent_used_at">최근 사용</option>
              </select>
              <select value={order} onChange={(event) => setOrder(event.target.value)} className="rounded border border-slate-700 bg-[#0f172a] px-3 py-2 text-xs font-bold text-slate-300 outline-none focus:border-ai-cyan">
                <option value="desc">내림차순</option>
                <option value="asc">오름차순</option>
              </select>
              <button type="button" onClick={loadUsers} className="rounded bg-ai-cyan px-4 py-2 text-xs font-bold text-slate-950 transition hover:bg-cyan-300">
                조회
              </button>
            </div>
          </div>

          <div className="mt-5 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <SummaryCard label="전체 유저" value={formatNumber(summary.totalUsers)} />
            <SummaryCard label="오늘 실제 토큰" value={formatNumber(summary.todayTokens)} />
            <SummaryCard label="30일 실제 토큰" value={formatNumber(summary.tokens30d)} />
            <SummaryCard label="24시간 활성 유저" value={formatNumber(summary.activeUsers24h)} />
          </div>
        </section>

        <section className="grid gap-5 xl:grid-cols-[minmax(0,1.2fr)_minmax(360px,0.8fr)]">
          <div className="overflow-hidden rounded-lg border border-slate-700/80 bg-slate-surface p-3 sm:p-4">
            <div className="hidden grid-cols-[minmax(170px,1.2fr)_90px_repeat(4,minmax(95px,1fr))_120px] rounded-t-lg bg-[#0f172a] text-xs font-bold text-slate-400 lg:grid">
              <div className="px-3 py-3">유저</div>
              <div className="px-3 py-3">권한</div>
              <div className="px-3 py-3 text-right">오늘</div>
              <div className="px-3 py-3 text-right">7일</div>
              <div className="px-3 py-3 text-right">30일</div>
              <div className="px-3 py-3 text-right">전체</div>
              <div className="px-3 py-3">최근 사용</div>
            </div>
            <div className="overflow-hidden rounded-lg border border-slate-800 lg:rounded-t-none lg:border-t-0">
              {loading ? (
                <div className="px-4 py-10 text-center text-sm font-bold text-slate-400">유저 목록을 불러오는 중입니다.</div>
              ) : error ? (
                <div className="px-4 py-10 text-center text-sm font-bold text-rose-400">{error}</div>
              ) : users.length === 0 ? (
                <div className="px-4 py-10 text-center text-sm font-bold text-slate-500">표시할 유저가 없습니다.</div>
              ) : users.map((item) => (
                <button
                  key={item.id}
                  type="button"
                  onClick={() => setSelectedUserId(item.id)}
                  className={`grid w-full grid-cols-2 gap-2 border-t border-slate-800 px-4 py-4 text-left text-sm first:border-t-0 hover:bg-white/[0.03] lg:grid-cols-[minmax(170px,1.2fr)_90px_repeat(4,minmax(95px,1fr))_120px] lg:px-0 lg:py-0 ${selectedUser?.id === item.id ? 'bg-ai-cyan/5' : ''}`}
                >
                  <span className="min-w-0 lg:px-3 lg:py-3">
                    <span className="block truncate font-bold text-white">{item.email || item.nickname || '-'}</span>
                    <span className="block truncate text-xs text-slate-500">{item.nickname || item.id}</span>
                  </span>
                  <span className="text-xs font-bold text-ai-cyan lg:px-3 lg:py-3">{item.role}</span>
                  <span className="font-mono text-xs text-slate-300 lg:px-3 lg:py-3 lg:text-right">{formatNumber(item.usage?.todayTokens)}</span>
                  <span className="font-mono text-xs text-slate-300 lg:px-3 lg:py-3 lg:text-right">{formatNumber(item.usage?.tokens7d)}</span>
                  <span className="font-mono text-xs text-white lg:px-3 lg:py-3 lg:text-right">{formatNumber(item.usage?.tokens30d)}</span>
                  <span className="font-mono text-xs text-slate-300 lg:px-3 lg:py-3 lg:text-right">{formatNumber(item.usage?.totalTokens)}</span>
                  <span className="col-span-2 text-xs text-slate-500 lg:col-span-1 lg:px-3 lg:py-3">{formatDateTime(item.usage?.recentUsedAt)}</span>
                </button>
              ))}
            </div>
          </div>

          <div className="rounded-lg border border-slate-700/80 bg-slate-surface p-4">
            <h2 className="text-sm font-bold text-white">사용량 상세</h2>
            <p className="mt-1 truncate text-xs text-slate-500">{selectedUser?.email || '유저를 선택하세요.'}</p>
            {detailLoading ? (
              <div className="mt-6 text-sm font-bold text-slate-400">상세 사용량을 불러오는 중입니다.</div>
            ) : detailError ? (
              <div className="mt-6 text-sm font-bold text-rose-400">{detailError}</div>
            ) : detail ? (
              <div className="mt-4 grid gap-5">
                <div className="grid gap-2">
                  {(detail.daily || []).slice(0, 14).map((row) => {
                    const maxTokens = Math.max(...(detail.daily || []).map((item) => Number(item.totalTokens || 0)), 1)
                    const width = `${Math.max(4, Math.round((Number(row.totalTokens || 0) / maxTokens) * 100))}%`
                    return (
                      <div key={row.date} className="grid gap-1">
                        <div className="flex items-center justify-between text-xs">
                          <span className="text-slate-400">{row.date}</span>
                          <span className="font-mono text-white">{formatNumber(row.totalTokens)}</span>
                        </div>
                        <div className="h-2 rounded bg-slate-800">
                          <div className="h-2 rounded bg-ai-cyan" style={{ width }} />
                        </div>
                      </div>
                    )
                  })}
                </div>
                <div className="rounded-lg border border-slate-800 bg-[#0f172a] p-3">
                  <p className="text-xs font-bold text-slate-400">요청 유형별 합계</p>
                  <div className="mt-2 grid gap-2">
                    {Object.entries(detail.byRequestType || {}).map(([type, value]) => (
                      <div key={type} className="flex items-center justify-between gap-3 text-xs">
                        <span className="truncate text-slate-400">{type}</span>
                        <span className="font-mono text-white">{formatNumber(value.totalTokens)}</span>
                      </div>
                    ))}
                  </div>
                </div>
                <div className="rounded-lg border border-slate-800 bg-[#0f172a] p-3">
                  <p className="text-xs font-bold text-slate-400">최근 요청 로그</p>
                  <div className="mt-2 grid gap-2">
                    {(detail.recentLogs || []).slice(0, 8).map((log) => (
                      <div key={`${log.createdAt}-${log.requestType}-${log.totalTokens}`} className="grid grid-cols-[1fr_auto] gap-3 text-xs">
                        <span className="min-w-0 truncate text-slate-400">{formatDateTime(log.createdAt)} · {log.requestType}</span>
                        <span className="font-mono text-white">{formatNumber(log.totalTokens)}</span>
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            ) : null}
          </div>
        </section>
      </div>
    </div>
  )
}
```

- [ ] **Step 2: Wire desktop tab**

In `frontend/src/pages/AdminMlData.jsx`, add import near `AdminInquiries`:

```jsx
import AdminUsers from './AdminUsers.jsx'
```

Add a third tab button after `사용자 문의 관리`:

```jsx
          <button
            type="button"
            onClick={() => setAdminTab('users')}
            className={`shrink-0 px-4 py-3 text-sm font-bold border-b-2 transition sm:px-6 ${
              adminTab === 'users'
                ? 'border-ai-cyan text-white bg-ai-cyan/5'
                : 'border-transparent text-slate-400 hover:text-white'
            }`}
          >
            유저 관리
          </button>
```

Add render block after inquiries block:

```jsx
        {adminTab === 'users' && (
          <AdminUsers
            isLoggedIn={isLoggedIn}
            userEmail={userEmail}
            handleLogout={handleLogout}
            hideHeader
          />
        )}
```

- [ ] **Step 3: Run frontend syntax check**

Run:

```bash
cd frontend && npm run build
```

Expected: Vite build completes. If existing unrelated build failures appear, capture them and run the narrow available frontend tests for changed files.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/pages/AdminUsers.jsx frontend/src/pages/AdminMlData.jsx
git commit -m "feat: add admin users desktop tab"
```

---

### Task 5: 모바일 관리자 유저 관리 탭

**Files:**
- Create: `frontend/src/pages/mobile/MobileAdminUsers.jsx`
- Modify: `frontend/src/pages/mobile/MobileAdminMlData.jsx`

**Interfaces:**
- Consumes: `GET /api/admin/users`.
- Consumes: `GET /api/admin/users/<user_id>/chatbot-usage`.
- Produces: `MobileAdminUsers({ isLoggedIn, userEmail, handleLogout, hideHeader })`.

- [ ] **Step 1: Create mobile component**

Create `frontend/src/pages/mobile/MobileAdminUsers.jsx` by adapting `AdminUsers.jsx` with card-first layout. Use this structure:

```jsx
import AdminUsers from '../AdminUsers.jsx'

export default function MobileAdminUsers(props) {
  return <AdminUsers {...props} hideHeader />
}
```

This reuses the responsive desktop component because it already renders a single-column card/table hybrid below `lg` and prevents duplicated data-fetching logic.

- [ ] **Step 2: Wire mobile tab**

In `frontend/src/pages/mobile/MobileAdminMlData.jsx`, add import near `MobileAdminInquiries`:

```jsx
import MobileAdminUsers from './MobileAdminUsers.jsx'
```

Change the tab wrapper from `grid-cols-2` to `grid-cols-3`:

```jsx
        <div className="grid grid-cols-3 gap-2 rounded-lg border border-slate-800 bg-[#0f172a] p-1">
```

Add third button after `사용자 문의 관리`:

```jsx
          <button
            type="button"
            onClick={() => setAdminTab('users')}
            className={`rounded-md px-3 py-2 text-xs font-bold transition ${
              adminTab === 'users'
                ? 'bg-ai-cyan text-slate-950'
                : 'text-slate-400 hover:bg-slate-800/70 hover:text-white'
            }`}
          >
            유저 관리
          </button>
```

Add render block after inquiries block:

```jsx
        {adminTab === 'users' && (
          <MobileAdminUsers
            isLoggedIn={isLoggedIn}
            userEmail={userEmail}
            handleLogout={handleLogout}
            hideHeader
          />
        )}
```

- [ ] **Step 3: Verify responsive build**

Run:

```bash
cd frontend && npm run build
```

Expected: Vite build completes.

- [ ] **Step 4: Optional browser verification**

If a dev server is available, run:

```bash
cd frontend && npm run dev -- --host 127.0.0.1
```

Open `/admin/ml-data` and check 360px, 430px, 768px, and 1280px widths. Expected: tab labels, search controls, user rows/cards, and detail panel do not overlap.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/mobile/MobileAdminUsers.jsx frontend/src/pages/mobile/MobileAdminMlData.jsx
git commit -m "feat: add admin users mobile tab"
```

---

### Task 6: Documentation and Full Verification

**Files:**
- Modify: `project_structure.md`
- Modify: `database_specification.md` if Task 1 did not already update it fully.

**Interfaces:**
- Consumes: all previous tasks.
- Produces: up-to-date project docs and final verification evidence.

- [ ] **Step 1: Update project structure**

In `project_structure.md`, add:

```markdown
- `backend/routes/admin_users.py`
  - 관리자 전용 사용자 목록 및 실제 챗봇 토큰 사용량 집계 API를 제공합니다.
- `frontend/src/pages/AdminUsers.jsx`
  - 관리자 유저 관리 탭의 데스크톱/반응형 UI입니다.
- `frontend/src/pages/mobile/MobileAdminUsers.jsx`
  - 모바일 관리자 유저 관리 탭 진입 컴포넌트입니다.
```

- [ ] **Step 2: Run backend tests**

Run:

```bash
PYTHONPATH=. pytest backend/tests/test_chatbot_token_usage_logging.py backend/tests/test_admin_users.py backend/tests/test_chatbot_llm_limits.py backend/tests/test_chatbot_llm_streaming.py -q
```

Expected: all selected backend tests pass.

- [ ] **Step 3: Run frontend build**

Run:

```bash
cd frontend && npm run build
```

Expected: build completes.

- [ ] **Step 4: Check changed files**

Run:

```bash
git status --short
git diff --stat
```

Expected: only files related to this feature and pre-existing unrelated dirty files remain. Do not revert unrelated user changes.

- [ ] **Step 5: Commit docs and any final fixes**

```bash
git add project_structure.md database_specification.md
git commit -m "docs: document admin token usage management"
```

If there are no doc changes left because `database_specification.md` was committed in Task 1 and `project_structure.md` already contains the new entries, skip this commit and note that no final docs commit was needed.
