from backend.services.rag_retrieval_service import RagRetrievalService, RetrievalQuery


class FakeEmbeddingService:
    def embed_query(self, text: str) -> list[float]:
        assert text == "하이닉스 공시 요약 보여줘"
        return [0.1, 0.2, 0.3]


class FakeKnowledgeRepository:
    def __init__(self):
        self.payload = None

    def match_knowledge_chunks(self, payload):
        self.payload = payload
        return [
            {
                "source_type": "DISCLOSURE",
                "source_id": "20260709000001",
                "chunk_text": "공급계약 체결 요약",
                "similarity": 0.91,
                "rank_score": 0.88,
                "metadata": {"symbol": "000660"},
            }
        ]


def test_retrieve_context_calls_match_rpc_with_filters():
    repository = FakeKnowledgeRepository()
    service = RagRetrievalService(
        embedding_service=FakeEmbeddingService(),
        knowledge_repository=repository,
    )

    results = service.retrieve(
        RetrievalQuery(
            user_id="user-1",
            question="하이닉스 공시 요약 보여줘",
            symbol="000660",
            market="KR",
            source_types=["DISCLOSURE"],
            limit=12,
        )
    )

    assert results[0]["source_type"] == "DISCLOSURE"
    assert repository.payload == {
        "query_embedding": [0.1, 0.2, 0.3],
        "match_user_id": "user-1",
        "match_symbol": "000660",
        "match_market": "KR",
        "match_source_types": ["DISCLOSURE"],
        "match_count": 12,
    }
