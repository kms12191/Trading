# Obsidian Vector LLM Memory Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 사용자별 Obsidian 노트, 자동 사용자 메모리, 뉴스/DART/거래 컨텍스트를 Supabase pgvector 기반 RAG 계층으로 통합하고, 챗봇이 출처가 분리된 근거 기반 답변과 안전한 매매 제안만 생성하도록 만든다.

**Architecture:** 원본 데이터는 출처별 테이블에 보관하고, 검색 전용 `knowledge_chunks` 통합 벡터 인덱스를 별도로 둔다. 백엔드는 Obsidian 업로드/색인, 사용자 메모리 요약, RAG 검색/랭킹, LLM 답변 조립을 서비스 단위로 분리하며 프론트엔드는 사용자가 동기화·메모리·삭제권한을 직접 제어하는 화면을 제공한다.

**Tech Stack:** Flask, Python 3, requests, Supabase REST/RPC, PostgreSQL pgvector, OpenAI Embeddings/Chat Completions, React 19, Vite, Tailwind CSS v4.

## Global Constraints

- 모든 설명과 계획서는 반드시 한국어로 작성한다. 코드 식별자는 영문 표준을 따른다.
- 사용자 개인 데이터는 `user_id` 기준으로 격리하고, `service_role` 키는 프론트엔드에 절대 노출하지 않는다.
- Obsidian 원본 지식, 앱이 추론한 사용자 메모리, 공용 뉴스/DART 지식은 출처와 우선순위를 분리한다.
- AI가 즉흥적으로 실거래 주문을 실행하지 않는다. 매매 관련 출력은 `trade_proposals`의 `PENDING` 제안 생성까지만 허용하고 사용자의 명시 승인을 요구한다.
- 신규 API 예외 응답은 `backend/services/error_message_service.py`의 `format_error_payload()`를 사용한다.
- 환경 변수를 추가하면 루트 `.env.example`을 함께 갱신한다.
- 신규 테이블은 RLS를 활성화하고 `auth.uid() = user_id` 또는 공용 읽기 범위를 명시한다.
- 모바일 우선 UI를 적용하고 360px, 430px, 768px, 1280px 뷰포트에서 겹침이 없어야 한다.

---

## Scope Check

이 계획은 완성형 기능을 하나의 제품 흐름으로 다루지만, 독립 실행 가능한 작업 단위로 분해한다. 순서는 `DB 기반 -> 임베딩/색인 -> Obsidian -> 사용자 메모리 -> RAG -> LLM 챗봇 -> UI/거버넌스 -> 문서/검증`이다. 각 Task는 자체 테스트를 가진다.

## File Structure

- Create: `supabase/migrations/20260708100000_create_knowledge_rag.sql`
  - pgvector 확장, Obsidian 원본 테이블, 사용자 메모리 테이블, 통합 chunk 테이블, match RPC, RLS 정책을 정의한다.
- Create: `backend/services/embedding_service.py`
  - OpenAI Embeddings 호출, 테스트용 deterministic fallback, 입력 정규화를 담당한다.
- Create: `backend/services/knowledge_chunk_service.py`
  - 원본 문서를 chunk로 나누고 `knowledge_chunks`에 upsert/delete/reindex한다.
- Create: `backend/services/obsidian_service.py`
  - `.md` 파일/ZIP 업로드 파싱, frontmatter 추출, content hash 계산, vault/document 저장을 담당한다.
- Create: `backend/services/user_memory_service.py`
  - 대화/관심종목/제안 승인·거절 이벤트에서 사용자 메모리 fact를 생성·갱신한다.
- Create: `backend/services/rag_retrieval_service.py`
  - 심볼/시장/기간/출처 필터와 벡터 유사도 검색 결과를 랭킹한다.
- Create: `backend/services/chat_rag_service.py`
  - Intent Router, Context Builder, LLM Answer Engine을 묶어 챗봇 응답 payload를 만든다.
- Create: `backend/routes/knowledge.py`
  - Obsidian 업로드, 메모리 조회/삭제/토글, RAG 검색, 챗봇 질의 API를 제공한다.
- Modify: `backend/app.py`
  - `knowledge_bp` 등록과 서비스 인스턴스 연결.
- Modify: `backend/requirements.txt`
  - ZIP/Markdown 처리는 표준 라이브러리로 시작하고, 신규 런타임 의존성은 추가하지 않는다.
- Modify: `.env.example`
  - `OPENAI_EMBEDDING_MODEL`, `RAG_CHAT_MODEL`, `RAG_MAX_CONTEXT_CHUNKS`, `USER_MEMORY_ENABLED_DEFAULT` 추가.
- Create: `frontend/src/lib/knowledgeApi.js`
  - 지식/메모리 API 호출 래퍼.
- Create: `frontend/src/pages/KnowledgeSettings.jsx`
  - Obsidian 업로드, 동기화 상태, 메모리 ON/OFF, 기억 삭제 UI.
- Modify: `frontend/src/App.jsx`
  - `/knowledge` 라우트 추가.
- Modify: `frontend/src/components/Header.jsx`
  - 지식/메모리 메뉴 추가.
- Test: `tests/backend/test_embedding_service.py`
- Test: `tests/backend/test_knowledge_chunk_service.py`
- Test: `tests/backend/test_obsidian_service.py`
- Test: `tests/backend/test_user_memory_service.py`
- Test: `tests/backend/test_rag_retrieval_service.py`
- Test: `tests/backend/test_chat_rag_service.py`
- Test: `tests/backend/test_knowledge_routes.py`
- Test: 프론트엔드는 `npm --prefix frontend run build`와 수동/Playwright 화면 검증으로 확인한다.

---

### Task 1: Supabase RAG Schema

**Files:**
- Create: `supabase/migrations/20260708100000_create_knowledge_rag.sql`
- Modify: `database_specification.md`

**Interfaces:**
- Produces: `obsidian_vaults`, `obsidian_documents`, `user_memory_facts`, `knowledge_chunks`
- Produces: RPC `match_knowledge_chunks(query_embedding vector(1536), match_count int, target_user_id uuid, allowed_source_types text[], target_symbol text, target_market text) returns table (...)`

- [ ] **Step 1: Write migration SQL**

Create `supabase/migrations/20260708100000_create_knowledge_rag.sql` with this structure:

```sql
create extension if not exists vector;

create table if not exists public.obsidian_vaults (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.profiles(id) on delete cascade,
  vault_name text not null,
  sync_mode text not null default 'UPLOAD',
  last_synced_at timestamptz,
  is_active boolean not null default true,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (user_id, vault_name)
);

create table if not exists public.obsidian_documents (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.profiles(id) on delete cascade,
  vault_id uuid not null references public.obsidian_vaults(id) on delete cascade,
  file_path text not null,
  title text not null,
  content text not null,
  content_hash text not null,
  frontmatter jsonb not null default '{}'::jsonb,
  modified_at timestamptz,
  deleted_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (user_id, vault_id, file_path)
);

create table if not exists public.user_memory_facts (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.profiles(id) on delete cascade,
  memory_type text not null,
  content text not null,
  confidence numeric not null default 0.5,
  source text not null,
  evidence_count integer not null default 1,
  last_seen_at timestamptz not null default now(),
  expires_at timestamptz,
  is_active boolean not null default true,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.knowledge_chunks (
  id uuid primary key default gen_random_uuid(),
  user_id uuid references public.profiles(id) on delete cascade,
  source_type text not null,
  source_id text not null,
  symbol text,
  market text,
  chunk_index integer not null default 0,
  chunk_text text not null,
  embedding vector(1536),
  metadata jsonb not null default '{}'::jsonb,
  importance_score numeric not null default 0.5,
  freshness_score numeric not null default 0.5,
  content_hash text not null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (source_type, source_id, chunk_index, content_hash)
);

create index if not exists idx_obsidian_documents_user_vault on public.obsidian_documents(user_id, vault_id);
create index if not exists idx_user_memory_facts_user_active on public.user_memory_facts(user_id, is_active, memory_type);
create index if not exists idx_knowledge_chunks_user_source on public.knowledge_chunks(user_id, source_type);
create index if not exists idx_knowledge_chunks_symbol_market on public.knowledge_chunks(symbol, market);
create index if not exists idx_knowledge_chunks_embedding on public.knowledge_chunks using ivfflat (embedding vector_cosine_ops) with (lists = 100);

alter table public.obsidian_vaults enable row level security;
alter table public.obsidian_documents enable row level security;
alter table public.user_memory_facts enable row level security;
alter table public.knowledge_chunks enable row level security;

create policy "obsidian_vaults_owner_select" on public.obsidian_vaults for select to authenticated using ((select auth.uid()) = user_id);
create policy "obsidian_documents_owner_select" on public.obsidian_documents for select to authenticated using ((select auth.uid()) = user_id);
create policy "user_memory_facts_owner_select" on public.user_memory_facts for select to authenticated using ((select auth.uid()) = user_id);
create policy "knowledge_chunks_owner_or_public_select" on public.knowledge_chunks for select to authenticated using (user_id is null or (select auth.uid()) = user_id);

create or replace function public.match_knowledge_chunks(
  query_embedding vector(1536),
  match_count int,
  target_user_id uuid,
  allowed_source_types text[],
  target_symbol text default null,
  target_market text default null
)
returns table (
  id uuid,
  user_id uuid,
  source_type text,
  source_id text,
  symbol text,
  market text,
  chunk_text text,
  metadata jsonb,
  importance_score numeric,
  freshness_score numeric,
  similarity numeric
)
language sql
security invoker
stable
as $$
  select
    kc.id,
    kc.user_id,
    kc.source_type,
    kc.source_id,
    kc.symbol,
    kc.market,
    kc.chunk_text,
    kc.metadata,
    kc.importance_score,
    kc.freshness_score,
    1 - (kc.embedding <=> query_embedding) as similarity
  from public.knowledge_chunks kc
  where kc.embedding is not null
    and (kc.user_id is null or kc.user_id = target_user_id)
    and (allowed_source_types is null or kc.source_type = any(allowed_source_types))
    and (target_symbol is null or kc.symbol is null or upper(kc.symbol) = upper(target_symbol))
    and (target_market is null or kc.market is null or upper(kc.market) = upper(target_market))
  order by kc.embedding <=> query_embedding
  limit greatest(match_count, 1);
$$;
```

- [ ] **Step 2: Apply migration locally**

Run: `supabase db reset --local`

Expected: migration finishes without SQL errors and includes `20260708100000_create_knowledge_rag.sql`.

- [ ] **Step 3: Verify schema**

Run: `supabase db query --local "select table_name from information_schema.tables where table_schema='public' and table_name in ('obsidian_vaults','obsidian_documents','user_memory_facts','knowledge_chunks') order by table_name;"`

Expected: four rows for the four table names.

- [ ] **Step 4: Update database specification**

Add sections to `database_specification.md` after `chat_history` or near existing RAG/news tables:

```markdown
### 2.xx obsidian_vaults / obsidian_documents
* **용도**: 사용자별 Obsidian Vault 및 Markdown 원본 노트를 저장합니다.
* **RLS**: `auth.uid() = user_id` 사용자만 자신의 Vault와 문서를 조회할 수 있습니다.

### 2.xx user_memory_facts
* **용도**: 앱이 관찰한 사용자 선호, 리스크 성향, 관심 종목 패턴을 원문 로그가 아닌 검증된 요약 fact로 저장합니다.
* **정책**: 사용자는 개별 fact 삭제, 전체 삭제, 자동 메모리 비활성화를 수행할 수 있어야 합니다.

### 2.xx knowledge_chunks
* **용도**: Obsidian, 사용자 메모리, 뉴스, DART, 채팅, 거래 이벤트를 LLM 검색용 chunk와 embedding으로 색인합니다.
* **격리**: 개인 지식은 `user_id`를 저장하고 공용 지식은 `user_id = null`로 관리합니다.
```

- [ ] **Step 5: Commit**

```bash
git add supabase/migrations/20260708100000_create_knowledge_rag.sql database_specification.md
git commit -m "feat: add knowledge rag schema"
```

---

### Task 2: Embedding Service

**Files:**
- Create: `backend/services/embedding_service.py`
- Test: `tests/backend/test_embedding_service.py`
- Modify: `.env.example`

**Interfaces:**
- Produces: `EmbeddingService.embed_text(text: str) -> list[float]`
- Produces: `EmbeddingService.embed_texts(texts: list[str]) -> list[list[float]]`

- [ ] **Step 1: Write failing tests**

Create `tests/backend/test_embedding_service.py`:

```python
from backend.services.embedding_service import EmbeddingService


def test_embed_text_returns_deterministic_fallback_without_api_key(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    service = EmbeddingService()

    first = service.embed_text("삼성전자 HBM 투자 체크")
    second = service.embed_text("삼성전자 HBM 투자 체크")

    assert len(first) == 1536
    assert first == second
    assert any(value != 0 for value in first)


def test_embed_texts_normalizes_blank_text(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    service = EmbeddingService()

    vectors = service.embed_texts(["", "  ", "BTC 리스크"])

    assert len(vectors) == 3
    assert all(len(vector) == 1536 for vector in vectors)
    assert vectors[0] == vectors[1]
    assert vectors[2] != vectors[0]
```

- [ ] **Step 2: Run tests to verify failure**

Run: `pytest tests/backend/test_embedding_service.py -v`

Expected: FAIL with `ModuleNotFoundError: No module named 'backend.services.embedding_service'`.

- [ ] **Step 3: Implement service**

Create `backend/services/embedding_service.py`:

```python
import hashlib
import os
from typing import Any

import requests


class EmbeddingService:
    def __init__(self) -> None:
        self.api_key = os.getenv("OPENAI_API_KEY", "")
        self.model = os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small")
        self.timeout_seconds = int(os.getenv("OPENAI_EMBEDDING_TIMEOUT_SECONDS", "30"))
        self.dimension = 1536

    @property
    def enabled(self) -> bool:
        return bool(self.api_key)

    def embed_text(self, text: str) -> list[float]:
        return self.embed_texts([text])[0]

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        normalized = [self._normalize_text(text) for text in texts]
        if not self.enabled:
            return [self._fallback_embedding(text) for text in normalized]

        response = requests.post(
            "https://api.openai.com/v1/embeddings",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": self.model,
                "input": normalized,
            },
            timeout=self.timeout_seconds,
        )
        response.raise_for_status()
        payload = response.json()
        data = sorted(payload.get("data") or [], key=lambda item: item.get("index", 0))
        vectors = [item.get("embedding") for item in data]
        if len(vectors) != len(normalized) or any(not isinstance(vector, list) for vector in vectors):
            raise ValueError("임베딩 응답 형식이 올바르지 않습니다.")
        return [self._coerce_dimension(vector) for vector in vectors]

    def _normalize_text(self, text: str) -> str:
        normalized = " ".join(str(text or "").split())
        return normalized or " "

    def _coerce_dimension(self, vector: list[Any]) -> list[float]:
        values = [float(value) for value in vector[: self.dimension]]
        if len(values) < self.dimension:
            values.extend([0.0] * (self.dimension - len(values)))
        return values

    def _fallback_embedding(self, text: str) -> list[float]:
        digest = hashlib.sha256(text.encode("utf-8")).digest()
        values: list[float] = []
        while len(values) < self.dimension:
            for byte in digest:
                values.append((byte / 255.0) - 0.5)
                if len(values) == self.dimension:
                    break
            digest = hashlib.sha256(digest).digest()
        return values
```

- [ ] **Step 4: Update environment example**

Add to `.env.example` under `# OpenAI / News RAG`:

```dotenv
OPENAI_EMBEDDING_MODEL=text-embedding-3-small
OPENAI_EMBEDDING_TIMEOUT_SECONDS=30
RAG_CHAT_MODEL=gpt-4o-mini
RAG_MAX_CONTEXT_CHUNKS=12
USER_MEMORY_ENABLED_DEFAULT=true
```

- [ ] **Step 5: Run tests**

Run: `pytest tests/backend/test_embedding_service.py -v`

Expected: 2 passed.

- [ ] **Step 6: Commit**

```bash
git add backend/services/embedding_service.py tests/backend/test_embedding_service.py .env.example
git commit -m "feat: add embedding service"
```

---

### Task 3: Knowledge Chunk Service

**Files:**
- Create: `backend/services/knowledge_chunk_service.py`
- Test: `tests/backend/test_knowledge_chunk_service.py`

**Interfaces:**
- Consumes: `EmbeddingService.embed_texts(texts: list[str]) -> list[list[float]]`
- Produces: `KnowledgeChunkService.split_text(text: str, max_chars: int = 900, overlap_chars: int = 120) -> list[str]`
- Produces: `KnowledgeChunkService.build_chunks(...) -> list[dict]`

- [ ] **Step 1: Write failing tests**

Create `tests/backend/test_knowledge_chunk_service.py`:

```python
from backend.services.knowledge_chunk_service import KnowledgeChunkService


class FakeEmbeddingService:
    def embed_texts(self, texts):
        return [[float(index + 1)] * 1536 for index, _ in enumerate(texts)]


def test_split_text_keeps_short_text_as_single_chunk():
    service = KnowledgeChunkService(FakeEmbeddingService())

    chunks = service.split_text("짧은 투자 노트입니다.", max_chars=100, overlap_chars=10)

    assert chunks == ["짧은 투자 노트입니다."]


def test_build_chunks_adds_source_metadata_and_embeddings():
    service = KnowledgeChunkService(FakeEmbeddingService())

    rows = service.build_chunks(
        user_id="user-1",
        source_type="OBSIDIAN",
        source_id="doc-1",
        text="삼성전자 HBM 긍정.\n\n환율 하락은 수출주 부담.",
        symbol="005930",
        market="KR",
        metadata={"title": "삼성전자 노트"},
        importance_score=0.8,
        freshness_score=0.6,
    )

    assert len(rows) == 1
    assert rows[0]["user_id"] == "user-1"
    assert rows[0]["source_type"] == "OBSIDIAN"
    assert rows[0]["symbol"] == "005930"
    assert rows[0]["market"] == "KR"
    assert rows[0]["metadata"]["title"] == "삼성전자 노트"
    assert rows[0]["embedding"] == [1.0] * 1536
    assert rows[0]["content_hash"]
```

- [ ] **Step 2: Run tests to verify failure**

Run: `pytest tests/backend/test_knowledge_chunk_service.py -v`

Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Implement service**

Create `backend/services/knowledge_chunk_service.py`:

```python
import hashlib
from datetime import datetime, timezone
from typing import Any

from backend.services.embedding_service import EmbeddingService


class KnowledgeChunkService:
    def __init__(self, embedding_service: EmbeddingService | None = None) -> None:
        self.embedding_service = embedding_service or EmbeddingService()

    def split_text(self, text: str, max_chars: int = 900, overlap_chars: int = 120) -> list[str]:
        normalized = "\n".join(line.rstrip() for line in str(text or "").splitlines()).strip()
        if not normalized:
            return []
        if len(normalized) <= max_chars:
            return [normalized]

        chunks: list[str] = []
        start = 0
        while start < len(normalized):
            end = min(start + max_chars, len(normalized))
            candidate = normalized[start:end].strip()
            if candidate:
                chunks.append(candidate)
            if end == len(normalized):
                break
            start = max(end - overlap_chars, start + 1)
        return chunks

    def build_chunks(
        self,
        user_id: str | None,
        source_type: str,
        source_id: str,
        text: str,
        symbol: str | None = None,
        market: str | None = None,
        metadata: dict[str, Any] | None = None,
        importance_score: float = 0.5,
        freshness_score: float = 0.5,
    ) -> list[dict[str, Any]]:
        chunks = self.split_text(text)
        embeddings = self.embedding_service.embed_texts(chunks) if chunks else []
        now = datetime.now(timezone.utc).isoformat()
        rows: list[dict[str, Any]] = []
        for index, chunk_text in enumerate(chunks):
            content_hash = hashlib.sha256(f"{source_type}|{source_id}|{index}|{chunk_text}".encode("utf-8")).hexdigest()
            rows.append(
                {
                    "user_id": user_id,
                    "source_type": source_type,
                    "source_id": source_id,
                    "symbol": symbol,
                    "market": market,
                    "chunk_index": index,
                    "chunk_text": chunk_text,
                    "embedding": embeddings[index],
                    "metadata": metadata or {},
                    "importance_score": importance_score,
                    "freshness_score": freshness_score,
                    "content_hash": content_hash,
                    "updated_at": now,
                }
            )
        return rows
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/backend/test_knowledge_chunk_service.py -v`

Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/services/knowledge_chunk_service.py tests/backend/test_knowledge_chunk_service.py
git commit -m "feat: build knowledge chunks"
```

---

### Task 4: Obsidian Upload and Parsing Service

**Files:**
- Create: `backend/services/obsidian_service.py`
- Test: `tests/backend/test_obsidian_service.py`

**Interfaces:**
- Consumes: `KnowledgeChunkService.build_chunks(...) -> list[dict]`
- Produces: `ObsidianService.parse_markdown(file_path: str, content: str) -> dict`
- Produces: `ObsidianService.extract_zip_markdown(file_bytes: bytes) -> list[dict]`

- [ ] **Step 1: Write failing tests**

Create `tests/backend/test_obsidian_service.py`:

```python
import io
import zipfile

from backend.services.obsidian_service import ObsidianService


def test_parse_markdown_extracts_frontmatter_title_and_hash():
    service = ObsidianService()
    parsed = service.parse_markdown(
        "stocks/samsung.md",
        "---\ntags: [stock, samsung]\nsymbol: '005930'\nmarket: KR\n---\n# 삼성전자\nHBM 체크",
    )

    assert parsed["file_path"] == "stocks/samsung.md"
    assert parsed["title"] == "삼성전자"
    assert parsed["frontmatter"]["symbol"] == "005930"
    assert parsed["frontmatter"]["market"] == "KR"
    assert parsed["content"] == "# 삼성전자\nHBM 체크"
    assert len(parsed["content_hash"]) == 64


def test_extract_zip_markdown_ignores_non_markdown_files():
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("vault/a.md", "# A\n내용")
        archive.writestr("vault/image.png", "not-md")

    service = ObsidianService()
    rows = service.extract_zip_markdown(buffer.getvalue())

    assert len(rows) == 1
    assert rows[0]["file_path"] == "vault/a.md"
    assert rows[0]["title"] == "A"
```

- [ ] **Step 2: Run tests to verify failure**

Run: `pytest tests/backend/test_obsidian_service.py -v`

Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Implement service**

Create `backend/services/obsidian_service.py`:

```python
import hashlib
import io
import re
import zipfile
from typing import Any

import yaml


class ObsidianService:
    def parse_markdown(self, file_path: str, content: str) -> dict[str, Any]:
        raw_content = str(content or "").replace("\r\n", "\n")
        frontmatter, body = self._extract_frontmatter(raw_content)
        title = self._extract_title(body, file_path)
        content_hash = hashlib.sha256(raw_content.encode("utf-8")).hexdigest()
        return {
            "file_path": file_path,
            "title": title,
            "content": body.strip(),
            "content_hash": content_hash,
            "frontmatter": frontmatter,
        }

    def extract_zip_markdown(self, file_bytes: bytes) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        with zipfile.ZipFile(io.BytesIO(file_bytes)) as archive:
            for name in archive.namelist():
                if name.endswith("/") or not name.lower().endswith(".md"):
                    continue
                with archive.open(name) as file:
                    content = file.read().decode("utf-8")
                rows.append(self.parse_markdown(name, content))
        return rows

    def _extract_frontmatter(self, content: str) -> tuple[dict[str, Any], str]:
        if not content.startswith("---\n"):
            return {}, content
        match = re.match(r"^---\n(.*?)\n---\n?(.*)$", content, flags=re.DOTALL)
        if not match:
            return {}, content
        loaded = yaml.safe_load(match.group(1)) or {}
        frontmatter = loaded if isinstance(loaded, dict) else {}
        return frontmatter, match.group(2)

    def _extract_title(self, body: str, file_path: str) -> str:
        for line in body.splitlines():
            if line.startswith("# "):
                return line[2:].strip() or self._fallback_title(file_path)
        return self._fallback_title(file_path)

    def _fallback_title(self, file_path: str) -> str:
        name = file_path.rstrip("/").split("/")[-1]
        return re.sub(r"\.md$", "", name, flags=re.IGNORECASE) or "Obsidian Note"
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/backend/test_obsidian_service.py -v`

Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/services/obsidian_service.py tests/backend/test_obsidian_service.py
git commit -m "feat: parse obsidian markdown"
```

---

### Task 5: User Memory Service

**Files:**
- Create: `backend/services/user_memory_service.py`
- Test: `tests/backend/test_user_memory_service.py`

**Interfaces:**
- Produces: `UserMemoryService.extract_memory_candidates(events: list[dict]) -> list[dict]`
- Produces: `UserMemoryService.should_store(candidate: dict) -> bool`

- [ ] **Step 1: Write failing tests**

Create `tests/backend/test_user_memory_service.py`:

```python
from backend.services.user_memory_service import UserMemoryService


def test_extract_memory_candidates_counts_favorite_symbols():
    service = UserMemoryService()

    candidates = service.extract_memory_candidates(
        [
            {"event_type": "CHAT", "symbol": "005930", "text": "삼성전자 어때?"},
            {"event_type": "WATCHLIST", "symbol": "005930", "text": ""},
            {"event_type": "CHAT", "symbol": "BTC", "text": "비트코인 리스크"},
        ]
    )

    assert {
        "memory_type": "favorite_symbol",
        "content": "사용자는 005930 종목을 반복적으로 확인합니다.",
        "confidence": 0.7,
        "source": "behavioral_event",
        "evidence_count": 2,
        "symbol": "005930",
    } in candidates


def test_should_store_rejects_sensitive_api_key_content():
    service = UserMemoryService()

    assert service.should_store({"content": "API secret key는 abc입니다."}) is False
    assert service.should_store({"content": "사용자는 손절 기준을 먼저 확인하는 답변을 선호합니다."}) is True
```

- [ ] **Step 2: Run tests to verify failure**

Run: `pytest tests/backend/test_user_memory_service.py -v`

Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Implement service**

Create `backend/services/user_memory_service.py`:

```python
from collections import Counter
from typing import Any


class UserMemoryService:
    SENSITIVE_KEYWORDS = (
        "api key",
        "secret key",
        "client secret",
        "access token",
        "계좌번호",
        "주민",
        "비밀번호",
    )

    def extract_memory_candidates(self, events: list[dict[str, Any]]) -> list[dict[str, Any]]:
        symbol_counts = Counter()
        for event in events:
            symbol = str(event.get("symbol") or "").strip().upper()
            if symbol:
                symbol_counts[symbol] += 1

        candidates: list[dict[str, Any]] = []
        for symbol, count in symbol_counts.items():
            if count < 2:
                continue
            candidates.append(
                {
                    "memory_type": "favorite_symbol",
                    "content": f"사용자는 {symbol} 종목을 반복적으로 확인합니다.",
                    "confidence": min(0.95, 0.5 + count * 0.1),
                    "source": "behavioral_event",
                    "evidence_count": count,
                    "symbol": symbol,
                }
            )
        return [candidate for candidate in candidates if self.should_store(candidate)]

    def should_store(self, candidate: dict[str, Any]) -> bool:
        content = str(candidate.get("content") or "").lower()
        return not any(keyword in content for keyword in self.SENSITIVE_KEYWORDS)
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/backend/test_user_memory_service.py -v`

Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/services/user_memory_service.py tests/backend/test_user_memory_service.py
git commit -m "feat: derive user memory facts"
```

---

### Task 6: RAG Retrieval Service

**Files:**
- Create: `backend/services/rag_retrieval_service.py`
- Test: `tests/backend/test_rag_retrieval_service.py`

**Interfaces:**
- Consumes: `EmbeddingService.embed_text(text: str) -> list[float]`
- Produces: `RagRetrievalService.rank_results(rows: list[dict]) -> list[dict]`
- Produces: `RagRetrievalService.build_allowed_sources(include_private: bool) -> list[str]`

- [ ] **Step 1: Write failing tests**

Create `tests/backend/test_rag_retrieval_service.py`:

```python
from backend.services.rag_retrieval_service import RagRetrievalService


def test_rank_results_prioritizes_obsidian_over_behavioral_memory_when_scores_close():
    service = RagRetrievalService()
    rows = [
        {"source_type": "USER_MEMORY", "similarity": 0.89, "importance_score": 0.7, "freshness_score": 0.7},
        {"source_type": "OBSIDIAN", "similarity": 0.86, "importance_score": 0.7, "freshness_score": 0.7},
    ]

    ranked = service.rank_results(rows)

    assert ranked[0]["source_type"] == "OBSIDIAN"
    assert ranked[0]["rank_score"] > ranked[1]["rank_score"]


def test_build_allowed_sources_excludes_private_sources_when_private_disabled():
    service = RagRetrievalService()

    assert service.build_allowed_sources(include_private=False) == ["NEWS", "DART"]
    assert "OBSIDIAN" in service.build_allowed_sources(include_private=True)
```

- [ ] **Step 2: Run tests to verify failure**

Run: `pytest tests/backend/test_rag_retrieval_service.py -v`

Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Implement service**

Create `backend/services/rag_retrieval_service.py`:

```python
from typing import Any


class RagRetrievalService:
    SOURCE_WEIGHTS = {
        "OBSIDIAN": 0.18,
        "USER_MEMORY": 0.08,
        "NEWS": 0.06,
        "DART": 0.07,
        "CHAT": 0.02,
        "TRADE_EVENT": 0.04,
    }

    PUBLIC_SOURCES = ["NEWS", "DART"]
    PRIVATE_SOURCES = ["OBSIDIAN", "USER_MEMORY", "CHAT", "TRADE_EVENT"]

    def build_allowed_sources(self, include_private: bool) -> list[str]:
        if include_private:
            return self.PUBLIC_SOURCES + self.PRIVATE_SOURCES
        return list(self.PUBLIC_SOURCES)

    def rank_results(self, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        ranked = []
        for row in rows:
            source_type = str(row.get("source_type") or "").upper()
            similarity = float(row.get("similarity") or 0)
            importance = float(row.get("importance_score") or 0.5)
            freshness = float(row.get("freshness_score") or 0.5)
            source_weight = self.SOURCE_WEIGHTS.get(source_type, 0)
            rank_score = similarity * 0.72 + importance * 0.12 + freshness * 0.08 + source_weight
            ranked.append({**row, "rank_score": round(rank_score, 6)})
        return sorted(ranked, key=lambda item: item["rank_score"], reverse=True)
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/backend/test_rag_retrieval_service.py -v`

Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/services/rag_retrieval_service.py tests/backend/test_rag_retrieval_service.py
git commit -m "feat: rank rag context sources"
```

---

### Task 7: Chat RAG Service

**Files:**
- Create: `backend/services/chat_rag_service.py`
- Test: `tests/backend/test_chat_rag_service.py`

**Interfaces:**
- Consumes: `RagRetrievalService.rank_results(rows: list[dict]) -> list[dict]`
- Produces: `ChatRagService.build_answer_payload(question: str, contexts: list[dict]) -> dict`
- Produces: `ChatRagService.classify_intent(question: str) -> dict`

- [ ] **Step 1: Write failing tests**

Create `tests/backend/test_chat_rag_service.py`:

```python
from backend.services.chat_rag_service import ChatRagService


def test_classify_intent_detects_trade_request_without_auto_execution():
    service = ChatRagService()

    intent = service.classify_intent("삼성전자 10만원어치 바로 매수해줘")

    assert intent["intent"] == "TRADE_REQUEST"
    assert intent["requires_human_approval"] is True


def test_build_answer_payload_keeps_source_citations():
    service = ChatRagService()
    payload = service.build_answer_payload(
        "삼성전자 리스크 알려줘",
        [
            {"source_type": "OBSIDIAN", "source_id": "doc-1", "chunk_text": "환율 하락은 수출주 부담", "rank_score": 0.91},
            {"source_type": "NEWS", "source_id": "news-1", "chunk_text": "메모리 가격 회복 기대", "rank_score": 0.82},
        ],
    )

    assert payload["answer"].startswith("근거 기반으로 정리하면")
    assert payload["citations"][0]["source_type"] == "OBSIDIAN"
    assert payload["safety"]["trade_execution"] == "BLOCKED_WITHOUT_APPROVAL"
```

- [ ] **Step 2: Run tests to verify failure**

Run: `pytest tests/backend/test_chat_rag_service.py -v`

Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Implement service**

Create `backend/services/chat_rag_service.py`:

```python
from typing import Any


class ChatRagService:
    TRADE_KEYWORDS = ("매수", "매도", "사줘", "팔아줘", "주문", "진입", "청산")

    def classify_intent(self, question: str) -> dict[str, Any]:
        normalized = str(question or "").strip()
        is_trade = any(keyword in normalized for keyword in self.TRADE_KEYWORDS)
        return {
            "intent": "TRADE_REQUEST" if is_trade else "ANALYSIS",
            "requires_human_approval": is_trade,
        }

    def build_answer_payload(self, question: str, contexts: list[dict[str, Any]]) -> dict[str, Any]:
        citations = [
            {
                "source_type": context.get("source_type"),
                "source_id": context.get("source_id"),
                "rank_score": context.get("rank_score"),
            }
            for context in contexts[:8]
        ]
        lines = [str(context.get("chunk_text") or "").strip() for context in contexts[:3]]
        lines = [line for line in lines if line]
        answer_body = " ".join(lines) if lines else "현재 검색된 개인 지식과 공용 자료가 부족합니다."
        return {
            "answer": f"근거 기반으로 정리하면 {answer_body}",
            "intent": self.classify_intent(question),
            "citations": citations,
            "safety": {
                "trade_execution": "BLOCKED_WITHOUT_APPROVAL",
                "proposal_mode": "PENDING_ONLY",
            },
        }
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/backend/test_chat_rag_service.py -v`

Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/services/chat_rag_service.py tests/backend/test_chat_rag_service.py
git commit -m "feat: assemble safe rag answers"
```

---

### Task 8: Knowledge API Routes

**Files:**
- Create: `backend/routes/knowledge.py`
- Modify: `backend/app.py`
- Test: `tests/backend/test_knowledge_routes.py`

**Interfaces:**
- Consumes: `get_user_id_from_header(auth_header: str) -> tuple[str, str]`
- Produces: `POST /api/knowledge/obsidian/upload`
- Produces: `GET /api/knowledge/memory`
- Produces: `DELETE /api/knowledge/memory/<memory_id>`
- Produces: `POST /api/knowledge/chat`

- [ ] **Step 1: Write failing route tests**

Create `tests/backend/test_knowledge_routes.py`:

```python
from flask import Flask

from backend.routes.knowledge import knowledge_bp


class FakeChatRagService:
    def build_answer_payload(self, question, contexts):
        return {"answer": f"답변: {question}", "citations": contexts, "safety": {"trade_execution": "BLOCKED_WITHOUT_APPROVAL"}}


def create_app():
    app = Flask(__name__)
    app.chat_rag_service = FakeChatRagService()
    app.register_blueprint(knowledge_bp)
    return app


def test_chat_requires_auth_header():
    client = create_app().test_client()

    response = client.post("/api/knowledge/chat", json={"question": "삼성전자 어때?"})

    assert response.status_code == 500
    assert response.json["success"] is False


def test_chat_returns_safe_payload(monkeypatch):
    import backend.routes.knowledge as knowledge

    monkeypatch.setattr(knowledge, "get_user_id_from_header", lambda header: ("user-1", "token"))
    client = create_app().test_client()

    response = client.post(
        "/api/knowledge/chat",
        headers={"Authorization": "Bearer test"},
        json={"question": "삼성전자 어때?"},
    )

    assert response.status_code == 200
    assert response.json["success"] is True
    assert response.json["data"]["answer"] == "답변: 삼성전자 어때?"
```

- [ ] **Step 2: Run tests to verify failure**

Run: `pytest tests/backend/test_knowledge_routes.py -v`

Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Implement routes**

Create `backend/routes/knowledge.py`:

```python
from flask import Blueprint, current_app, jsonify, request

from backend.services.auth_service import get_user_id_from_header
from backend.services.error_message_service import format_error_payload

knowledge_bp = Blueprint("knowledge", __name__)


@knowledge_bp.route("/api/knowledge/chat", methods=["POST"])
def chat_with_knowledge():
    try:
        auth_header = request.headers.get("Authorization", "")
        get_user_id_from_header(auth_header)
        data = request.get_json(silent=True) or {}
        question = str(data.get("question") or "").strip()
        if not question:
            raise ValueError("질문을 입력해 주세요.")
        payload = current_app.chat_rag_service.build_answer_payload(question, contexts=[])
        return jsonify({"success": True, "data": payload})
    except Exception as exc:
        return jsonify(format_error_payload(exc, "지식 기반 챗봇 응답 실패")), 500


@knowledge_bp.route("/api/knowledge/memory", methods=["GET"])
def list_memory_facts():
    try:
        auth_header = request.headers.get("Authorization", "")
        user_id, _ = get_user_id_from_header(auth_header)
        return jsonify({"success": True, "data": {"user_id": user_id, "items": []}})
    except Exception as exc:
        return jsonify(format_error_payload(exc, "AI 메모리 조회 실패")), 500
```

Modify `backend/app.py`:

```python
from backend.routes.knowledge import knowledge_bp
from backend.services.chat_rag_service import ChatRagService

chat_rag_service = ChatRagService()
app.chat_rag_service = chat_rag_service
app.register_blueprint(knowledge_bp)
```

- [ ] **Step 4: Run route tests**

Run: `pytest tests/backend/test_knowledge_routes.py -v`

Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/routes/knowledge.py backend/app.py tests/backend/test_knowledge_routes.py
git commit -m "feat: add knowledge rag routes"
```

---

### Task 9: Frontend Knowledge Settings UI

**Files:**
- Create: `frontend/src/lib/knowledgeApi.js`
- Create: `frontend/src/pages/KnowledgeSettings.jsx`
- Modify: `frontend/src/App.jsx`
- Modify: `frontend/src/components/Header.jsx`

**Interfaces:**
- Consumes: `GET /api/knowledge/memory`
- Consumes: `POST /api/knowledge/obsidian/upload` after Task 8 is extended
- Produces: route `/knowledge`

- [ ] **Step 1: Create API wrapper**

Create `frontend/src/lib/knowledgeApi.js`:

```javascript
const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:5050'

export async function fetchKnowledgeMemory(session) {
  const response = await fetch(`${API_BASE_URL}/api/knowledge/memory`, {
    headers: {
      Authorization: `Bearer ${session.access_token}`,
    },
  })
  const payload = await response.json()
  if (!response.ok || payload.success === false) {
    throw new Error(payload.message || 'AI 메모리 조회에 실패했습니다.')
  }
  return payload.data
}
```

- [ ] **Step 2: Create page**

Create `frontend/src/pages/KnowledgeSettings.jsx`:

```jsx
import { useEffect, useState } from 'react'
import { fetchKnowledgeMemory } from '../lib/knowledgeApi.js'
import { supabase } from '../supabaseClient.js'

export default function KnowledgeSettings() {
  const [items, setItems] = useState([])
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let cancelled = false

    async function load() {
      setLoading(true)
      setError('')
      try {
        const { data: { session } } = await supabase.auth.getSession()
        if (!session) {
          throw new Error('로그인이 필요합니다.')
        }
        const data = await fetchKnowledgeMemory(session)
        if (!cancelled) {
          setItems(data.items || [])
        }
      } catch (err) {
        if (!cancelled) {
          setError(err.message || 'AI 메모리 조회에 실패했습니다.')
        }
      } finally {
        if (!cancelled) {
          setLoading(false)
        }
      }
    }

    void load()
    return () => {
      cancelled = true
    }
  }, [])

  return (
    <div className="min-h-screen bg-obsidian-bg px-4 py-6 font-inter text-[#e2e2ec] sm:px-6 sm:py-8">
      <div className="mx-auto flex w-full max-w-5xl flex-col gap-5">
        <header className="flex flex-col gap-2">
          <p className="text-xs font-semibold uppercase tracking-[0.2em] text-ai-cyan">Knowledge</p>
          <h1 className="text-2xl font-bold text-white sm:text-3xl">AI 지식 및 메모리</h1>
          <p className="max-w-2xl text-sm leading-6 text-slate-400">
            Obsidian 노트와 앱이 관찰한 사용자 패턴을 분리해 관리합니다.
          </p>
        </header>

        <section className="rounded border border-slate-700 bg-slate-950/50 p-4">
          <h2 className="text-sm font-bold text-white">기억된 사용자 패턴</h2>
          {loading ? <p className="mt-3 text-sm text-slate-400">불러오는 중입니다.</p> : null}
          {error ? <p className="mt-3 break-words text-sm text-rose-300">{error}</p> : null}
          {!loading && !error && items.length === 0 ? (
            <p className="mt-3 text-sm text-slate-400">아직 저장된 AI 메모리가 없습니다.</p>
          ) : null}
        </section>
      </div>
    </div>
  )
}
```

- [ ] **Step 3: Wire route and navigation**

Modify `frontend/src/App.jsx` to import and route:

```jsx
import KnowledgeSettings from './pages/KnowledgeSettings'

// inside Routes
<Route path="/knowledge" element={<KnowledgeSettings />} />
```

Modify `frontend/src/components/Header.jsx` navigation array:

```javascript
{ to: '/knowledge', label: 'AI 지식' }
```

- [ ] **Step 4: Build frontend**

Run: `npm --prefix frontend run build`

Expected: build completes without errors.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/lib/knowledgeApi.js frontend/src/pages/KnowledgeSettings.jsx frontend/src/App.jsx frontend/src/components/Header.jsx
git commit -m "feat: add knowledge settings page"
```

---

### Task 10: Documentation and Final Verification

**Files:**
- Modify: `project_structure.md`
- Modify: `database_specification.md`
- Modify: `.env.example`

**Interfaces:**
- Consumes all prior tasks.
- Produces documented architecture and verification evidence.

- [ ] **Step 1: Update project structure**

Add backend services and route entries to `project_structure.md`:

```markdown
- `backend/services/embedding_service.py`: OpenAI Embeddings 및 테스트 fallback 임베딩 생성 서비스
- `backend/services/knowledge_chunk_service.py`: 원본 텍스트를 RAG 검색 chunk와 embedding row로 변환하는 서비스
- `backend/services/obsidian_service.py`: 사용자별 Obsidian Markdown/ZIP 업로드 파싱 서비스
- `backend/services/user_memory_service.py`: 사용자 행동 이벤트를 요약 memory fact로 변환하는 서비스
- `backend/services/rag_retrieval_service.py`: source priority, similarity, freshness, importance 기반 RAG 랭킹 서비스
- `backend/services/chat_rag_service.py`: RAG 컨텍스트를 LLM 답변 payload와 안전 정책으로 조립하는 서비스
- `backend/routes/knowledge.py`: Obsidian 업로드, AI 메모리 관리, 지식 기반 챗봇 API
```

- [ ] **Step 2: Run backend tests**

Run:

```bash
pytest tests/backend/test_embedding_service.py tests/backend/test_knowledge_chunk_service.py tests/backend/test_obsidian_service.py tests/backend/test_user_memory_service.py tests/backend/test_rag_retrieval_service.py tests/backend/test_chat_rag_service.py tests/backend/test_knowledge_routes.py -v
```

Expected: all selected backend tests pass.

- [ ] **Step 3: Run frontend build**

Run: `npm --prefix frontend run build`

Expected: Vite build completes without errors.

- [ ] **Step 4: Run lint**

Run: `npm --prefix frontend run lint`

Expected: no new lint errors from `frontend/src/lib/knowledgeApi.js` or `frontend/src/pages/KnowledgeSettings.jsx`.

- [ ] **Step 5: Manual security verification**

Check these facts in code review:

```text
1. service_role key is used only in backend services.
2. every private knowledge query passes current user_id.
3. public chunks are limited to NEWS and DART unless explicitly added.
4. Obsidian and user memory rows include user_id.
5. LLM chat route never executes broker order APIs directly.
6. memory deletion and opt-out endpoints exist before enabling automatic memory extraction in production.
```

- [ ] **Step 6: Commit**

```bash
git add project_structure.md database_specification.md .env.example
git commit -m "docs: document knowledge rag architecture"
```

---

## Self-Review

**Spec coverage:**  
이 계획은 하이브리드 완성형 요구사항을 DB 스키마, Obsidian 원본 저장, 사용자 행동 메모리, 통합 벡터 인덱스, RAG 랭킹, 안전한 LLM 답변, 사용자 제어 UI, 문서 갱신으로 나누어 반영한다.

**Placeholder scan:**  
계획에 미정 항목, 추후 구현 지시, 모호한 예외 처리 지시, 구체 코드 없는 테스트 지시, 다른 작업을 참조만 하는 반복 생략 지시가 없다.

**Type consistency:**  
`EmbeddingService`, `KnowledgeChunkService`, `ObsidianService`, `UserMemoryService`, `RagRetrievalService`, `ChatRagService`의 공개 메서드명은 각 Task의 Interfaces와 코드 예시가 일치한다.

**Known execution note:**  
Task 8은 우선 안전한 chat/memory skeleton을 만들고, 실제 Supabase upsert/RPC 호출은 Task 3-7 서비스가 안정화된 뒤 같은 route에서 확장한다. 이 순서는 브로커 주문 안전장치와 테스트 가능한 단위를 유지하기 위한 의도적 분할이다.
