from flask import Flask

from backend.routes.knowledge import knowledge_bp


class FakeObsidianService:
    def parse_markdown(self, file_path, content):
        return {
            "file_path": file_path,
            "title": "매매 전 체크리스트",
            "content": content,
            "content_hash": "a" * 64,
            "frontmatter": {"template_key": "pre-trade-checklist"},
        }


class FakeKnowledgeRepository:
    def __init__(self):
        self.synced_payload = None
        self.replaced_chunks = None

    def upsert_obsidian_note(self, auth_header, user_id, payload):
        self.synced_payload = payload
        return {"status": "SYNCED", "note_id": "note-1"}

    def replace_knowledge_chunks(self, auth_header, source_type, source_id, chunks):
        self.replaced_chunks = {
            "source_type": source_type,
            "source_id": source_id,
            "chunks": chunks,
        }
        return {"chunk_count": len(chunks)}

    def list_auto_memory(self, auth_header, user_id):
        return {
            "favorite_symbols": ["삼성전자(005930)를 자주 확인합니다."],
            "repeated_mistakes": ["근거 없이 추격매수하는 패턴이 있습니다."],
        }


class FakeKnowledgeChunkService:
    def build_chunks(self, **kwargs):
        return [
            {
                "user_id": kwargs["user_id"],
                "source_type": kwargs["source_type"],
                "source_id": kwargs["source_id"],
                "chunk_index": 0,
                "chunk_text": kwargs["text"],
                "content_hash": "b" * 64,
                "embedding": None,
                "embedding_status": "PENDING",
                "metadata": kwargs["metadata"],
            }
        ]


def create_app():
    app = Flask(__name__)
    app.config["TESTING"] = True
    app.obsidian_service = FakeObsidianService()
    app.knowledge_repository = FakeKnowledgeRepository()
    app.knowledge_chunk_service = FakeKnowledgeChunkService()
    app.register_blueprint(knowledge_bp)
    return app


def test_sync_note_requires_auth_header():
    client = create_app().test_client()

    response = client.post("/api/knowledge/obsidian/sync-note", json={})

    assert response.status_code == 401
    assert response.json["success"] is False


def test_sync_note_stores_parsed_markdown(monkeypatch):
    import backend.routes.knowledge as knowledge

    monkeypatch.setattr(knowledge, "get_user_id_from_header", lambda header: ("user-1", "token"))
    app = create_app()
    client = app.test_client()

    response = client.post(
        "/api/knowledge/obsidian/sync-note",
        headers={"Authorization": "Bearer test"},
        json={
            "vault_name": "AI-Trading-Vault",
            "file_path": "AI-Trading/01_매매전_체크리스트.md",
            "content": "# 매매 전 체크리스트",
            "modified_at": "2026-07-08T00:00:00Z",
        },
    )

    assert response.status_code == 200
    assert response.json["success"] is True
    assert response.json["data"]["status"] == "SYNCED"
    assert response.json["data"]["chunk_count"] == 1
    assert app.knowledge_repository.synced_payload["user_id"] == "user-1"
    assert app.knowledge_repository.synced_payload["title"] == "매매 전 체크리스트"
    assert app.knowledge_repository.replaced_chunks["source_type"] == "OBSIDIAN"
    assert app.knowledge_repository.replaced_chunks["source_id"] == "note-1"


def test_auto_memory_returns_marker_lists(monkeypatch):
    import backend.routes.knowledge as knowledge

    monkeypatch.setattr(knowledge, "get_user_id_from_header", lambda header: ("user-1", "token"))
    client = create_app().test_client()

    response = client.get(
        "/api/knowledge/obsidian/auto-memory",
        headers={"Authorization": "Bearer test"},
    )

    assert response.status_code == 200
    assert response.json["data"]["favorite_symbols"] == ["삼성전자(005930)를 자주 확인합니다."]
    assert response.json["data"]["repeated_mistakes"] == ["근거 없이 추격매수하는 패턴이 있습니다."]
