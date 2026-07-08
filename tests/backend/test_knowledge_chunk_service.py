from backend.services.knowledge_chunk_service import KnowledgeChunkService


def test_split_text_keeps_short_text_as_single_chunk():
    service = KnowledgeChunkService()

    chunks = service.split_text("짧은 투자 노트입니다.", max_chars=100, overlap_chars=10)

    assert chunks == ["짧은 투자 노트입니다."]


def test_split_text_uses_overlap_for_long_text():
    service = KnowledgeChunkService()
    text = "가" * 80 + "\n\n" + "나" * 80 + "\n\n" + "다" * 80

    chunks = service.split_text(text, max_chars=120, overlap_chars=20)

    assert len(chunks) == 3
    assert chunks[0].startswith("가")
    assert chunks[1].startswith("나")
    assert chunks[2].startswith("다")


def test_build_chunks_adds_source_metadata_without_embedding():
    service = KnowledgeChunkService()

    rows = service.build_chunks(
        user_id="user-1",
        source_type="OBSIDIAN",
        source_id="note-1",
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
    assert rows[0]["source_id"] == "note-1"
    assert rows[0]["symbol"] == "005930"
    assert rows[0]["market"] == "KR"
    assert rows[0]["metadata"]["title"] == "삼성전자 노트"
    assert rows[0]["embedding"] is None
    assert rows[0]["embedding_status"] == "PENDING"
    assert rows[0]["content_hash"]
