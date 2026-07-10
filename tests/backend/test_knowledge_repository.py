from backend.services.knowledge_repository import KnowledgeRepository


def test_upsert_obsidian_note_posts_when_note_does_not_exist(monkeypatch):
    calls = []

    def fake_safe_query(auth_header, endpoint, method="GET", json_data=None, params=None):
        calls.append((endpoint, method, json_data, params))
        if method == "GET":
            return []
        return [{"id": "note-1", "content_hash": "hash-1", "sync_status": "SYNCED"}]

    monkeypatch.setattr("backend.services.knowledge_repository.safe_query_supabase", fake_safe_query)
    repository = KnowledgeRepository()

    result = repository.upsert_obsidian_note(
        "Bearer token",
        "user-1",
        {
            "vault_name": "AI-Trading-Vault",
            "file_path": "AI-Trading/a.md",
            "title": "A",
            "content": "# A",
            "content_hash": "hash-1",
            "frontmatter": {},
            "modified_at": "2026-07-08T00:00:00Z",
        },
    )

    assert result["note_id"] == "note-1"
    assert calls[1][0] == "user_knowledge_notes"
    assert calls[1][1] == "POST"
    assert calls[1][2]["user_id"] == "user-1"


def test_upsert_obsidian_note_patches_when_note_exists(monkeypatch):
    calls = []

    def fake_safe_query(auth_header, endpoint, method="GET", json_data=None, params=None):
        calls.append((endpoint, method, json_data, params))
        if method == "GET":
            return [{"id": "note-1"}]
        return [{"id": "note-1", "content_hash": "hash-2", "sync_status": "SYNCED"}]

    monkeypatch.setattr("backend.services.knowledge_repository.safe_query_supabase", fake_safe_query)
    repository = KnowledgeRepository()

    result = repository.upsert_obsidian_note(
        "Bearer token",
        "user-1",
        {
            "vault_name": "AI-Trading-Vault",
            "file_path": "AI-Trading/a.md",
            "title": "A",
            "content": "# A updated",
            "content_hash": "hash-2",
            "frontmatter": {},
            "modified_at": None,
        },
    )

    assert result["content_hash"] == "hash-2"
    assert calls[1][0] == "user_knowledge_notes?id=eq.note-1"
    assert calls[1][1] == "PATCH"


def test_list_auto_memory_groups_facts_for_obsidian_markers(monkeypatch):
    def fake_safe_query(auth_header, endpoint, method="GET", json_data=None, params=None):
        return [
            {"memory_type": "favorite_symbol", "content": "삼성전자를 자주 확인합니다."},
            {"memory_type": "repeated_mistake", "content": "추격매수 후 손절이 늦습니다."},
            {"memory_type": "answer_preference", "content": "짧은 답변을 선호합니다."},
        ]

    monkeypatch.setattr("backend.services.knowledge_repository.safe_query_supabase", fake_safe_query)
    repository = KnowledgeRepository()

    result = repository.list_auto_memory("Bearer token", "user-1")

    assert result["favorite_symbols"] == ["삼성전자를 자주 확인합니다."]
    assert result["repeated_mistakes"] == ["추격매수 후 손절이 늦습니다."]


def test_upsert_memory_fact_increments_existing_fact(monkeypatch):
    calls = []

    def fake_safe_query(auth_header, endpoint, method="GET", json_data=None, params=None):
        calls.append((endpoint, method, json_data, params))
        if method == "GET":
            return [{"id": "memory-1", "evidence_count": 2, "confidence": 0.7}]
        return [{"id": "memory-1", **(json_data or {})}]

    monkeypatch.setattr("backend.services.knowledge_repository.safe_query_supabase", fake_safe_query)
    repository = KnowledgeRepository()

    result = repository.upsert_memory_fact(
        "Bearer token",
        "user-1",
        {
            "memory_type": "risk_preference",
            "content": "사용자는 국내주식 위주 검토를 선호합니다.",
            "confidence": 0.82,
            "metadata": {"source_message": "국내주식 위주로 보고 싶어"},
        },
    )

    assert result["id"] == "memory-1"
    assert calls[0][0] == "user_memory_facts"
    assert calls[0][3]["memory_type"] == "eq.risk_preference"
    assert calls[1][0] == "user_memory_facts?id=eq.memory-1"
    assert calls[1][1] == "PATCH"
    assert calls[1][2]["evidence_count"] == 3
    assert calls[1][2]["confidence"] == 0.82


def test_list_chatbot_memory_context_formats_active_memory(monkeypatch):
    def fake_safe_query(auth_header, endpoint, method="GET", json_data=None, params=None):
        return [
            {"memory_type": "risk_preference", "content": "사용자는 코인 리스크를 회피합니다.", "confidence": 0.9},
            {"memory_type": "favorite_symbol", "content": "삼성전자를 관심 있게 봅니다.", "confidence": 0.8},
        ]

    monkeypatch.setattr("backend.services.knowledge_repository.safe_query_supabase", fake_safe_query)
    repository = KnowledgeRepository()

    context = repository.list_chatbot_memory_context("Bearer token", "user-1")

    assert "자동메모리:" in context
    assert "risk_preference: 사용자는 코인 리스크를 회피합니다." in context
    assert "favorite_symbol: 삼성전자를 관심 있게 봅니다." in context


def test_replace_knowledge_chunks_deletes_old_chunks_then_inserts_new_chunks(monkeypatch):
    calls = []

    def fake_safe_query(auth_header, endpoint, method="GET", json_data=None, params=None):
        calls.append((endpoint, method, json_data, params))
        return []

    monkeypatch.setattr("backend.services.knowledge_repository.safe_query_supabase", fake_safe_query)
    repository = KnowledgeRepository()

    result = repository.replace_knowledge_chunks(
        "Bearer token",
        "OBSIDIAN",
        "note-1",
        [{"source_id": "note-1", "chunk_index": 0, "chunk_text": "내용"}],
    )

    assert result == {"chunk_count": 1}
    assert calls[0][0] == "knowledge_chunks"
    assert calls[0][1] == "DELETE"
    assert calls[0][3] == {"source_type": "eq.OBSIDIAN", "source_id": "eq.note-1"}
    assert calls[1][0] == "knowledge_chunks"
    assert calls[1][1] == "POST"
