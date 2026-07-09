import pytest

from backend.services.disclosure_knowledge_sync_service import DisclosureKnowledgeSyncService
from backend.services.knowledge_chunk_service import KnowledgeChunkService


class FakeEmbeddingService:
    def __init__(self):
        self.calls = []

    def embed_texts(self, texts):
        self.calls.append(texts)
        return [[0.1, 0.2, 0.3] for _ in texts]


def test_sync_analysis_skips_when_disclosure_chunk_is_already_embedded(monkeypatch):
    calls = []

    def fake_query(endpoint, method="GET", json_data=None, params=None):
        calls.append((endpoint, method, json_data, params))
        return [{"id": "chunk-1", "embedding_status": "EMBEDDED"}]

    monkeypatch.setattr(
        "backend.services.disclosure_knowledge_sync_service.query_supabase_as_service_role",
        fake_query,
    )
    embedding_service = FakeEmbeddingService()
    service = DisclosureKnowledgeSyncService(KnowledgeChunkService(), embedding_service)

    result = service.sync_analysis(
        analysis={"rcept_no": "20260709000001", "plain_summary": "요약"},
        disclosure={"rcept_no": "20260709000001", "stock_code": "000660", "corp_name": "SK하이닉스"},
    )

    assert result["status"] == "SKIPPED"
    assert result["chunk_count"] == 1
    assert embedding_service.calls == []
    assert calls == [
        (
            "knowledge_chunks",
            "GET",
            None,
            {
                "source_type": "eq.DISCLOSURE",
                "source_id": "eq.20260709000001",
                "select": "id,embedding_status",
                "limit": "20",
            },
        )
    ]


def test_sync_analysis_replaces_chunks_and_embeds_summary(monkeypatch):
    calls = []

    def fake_query(endpoint, method="GET", json_data=None, params=None):
        calls.append((endpoint, method, json_data, params))
        if method == "GET":
            return []
        return [{"id": "chunk-1"}]

    monkeypatch.setattr(
        "backend.services.disclosure_knowledge_sync_service.query_supabase_as_service_role",
        fake_query,
    )
    embedding_service = FakeEmbeddingService()
    service = DisclosureKnowledgeSyncService(KnowledgeChunkService(), embedding_service)

    result = service.sync_analysis(
        analysis={
            "rcept_no": "20260709000002",
            "category": "수주",
            "sentiment_label": "호재",
            "headline": "대규모 공급계약",
            "plain_summary": "계약 규모와 기간을 확인해야 합니다.",
        },
        disclosure={
            "rcept_no": "20260709000002",
            "stock_code": "000660",
            "corp_name": "SK하이닉스",
            "report_nm": "단일판매ㆍ공급계약체결",
            "rcept_dt": "20260709",
        },
    )

    assert result == {"status": "EMBEDDED", "chunk_count": 1}
    assert len(embedding_service.calls) == 1
    assert embedding_service.calls[0][0].endswith("대규모 공급계약\n계약 규모와 기간을 확인해야 합니다.")
    assert calls[1][0] == "knowledge_chunks"
    assert calls[1][1] == "DELETE"
    assert calls[2][0] == "knowledge_chunks"
    assert calls[2][1] == "POST"
    assert calls[2][2][0]["source_type"] == "DISCLOSURE"
    assert calls[2][2][0]["source_id"] == "20260709000002"
    assert calls[2][2][0]["embedding_status"] == "PENDING"
    assert calls[3] == (
        "knowledge_chunks?source_type=eq.DISCLOSURE&source_id=eq.20260709000002&chunk_index=eq.0",
        "PATCH",
        {"embedding": [0.1, 0.2, 0.3], "embedding_status": "EMBEDDED"},
        None,
    )


def test_sync_analysis_marks_failed_when_embedding_raises(monkeypatch):
    calls = []

    def fake_query(endpoint, method="GET", json_data=None, params=None):
        calls.append((endpoint, method, json_data, params))
        if method == "GET":
            return []
        return None

    class FailingEmbeddingService:
        def embed_texts(self, texts):
            raise RuntimeError("OPENAI_API_KEY is missing")

    monkeypatch.setattr(
        "backend.services.disclosure_knowledge_sync_service.query_supabase_as_service_role",
        fake_query,
    )
    service = DisclosureKnowledgeSyncService(KnowledgeChunkService(), FailingEmbeddingService())

    result = service.sync_analysis(
        analysis={"rcept_no": "20260709000003", "plain_summary": "요약"},
        disclosure={"rcept_no": "20260709000003", "stock_code": "000660"},
    )

    assert result == {"status": "FAILED", "chunk_count": 1}
    assert calls[-1] == (
        "knowledge_chunks?source_type=eq.DISCLOSURE&source_id=eq.20260709000003",
        "PATCH",
        {"embedding_status": "FAILED"},
        None,
    )


def test_sync_analysis_requires_rcept_no():
    service = DisclosureKnowledgeSyncService(KnowledgeChunkService(), FakeEmbeddingService())

    with pytest.raises(ValueError, match="rcept_no"):
        service.sync_analysis(analysis={"plain_summary": "요약"}, disclosure={})
