from backend.services.chatbot.recommendation_service import (
    ChatbotRecommendationService,
    RecommendationConfig,
    build_default_rag_evidence_provider,
)


def test_recommendation_service_prioritizes_ml_candidates_and_filters_risky_rows():
    def fake_signal_payload(asset_key, auth_header, symbols=None, position=None, min_signal_score=None, limit=20):
        assert asset_key == "kr_stock"
        assert position == "LONG"
        return {
            "asset_type": "STOCK",
            "model_version": "lgbm_kr_stock_signal_v1",
            "predictions": [
                {
                    "symbol": "005930",
                    "display_name": "삼성전자",
                    "signal_grade": "WATCH",
                    "signal_score": 24.0,
                    "up_probability": 0.57,
                    "risk_probability": 0.42,
                    "reason_summary": "관찰 후보입니다.",
                },
                {
                    "symbol": "000660",
                    "display_name": "SK하이닉스",
                    "signal_grade": "STRONG_BUY_CANDIDATE",
                    "signal_score": 38.0,
                    "up_probability": 0.64,
                    "risk_probability": 0.36,
                    "reason_summary": "상승 후보입니다.",
                },
                {
                    "symbol": "123456",
                    "display_name": "위험종목",
                    "signal_grade": "RISKY",
                    "signal_score": 80.0,
                    "up_probability": 0.66,
                    "risk_probability": 0.82,
                    "reason_summary": "리스크 우선 확인 대상입니다.",
                },
            ],
            "performance": {"cv_roc_auc": 0.55},
        }

    service = ChatbotRecommendationService(
        signal_payload_builder=fake_signal_payload,
        config=RecommendationConfig(default_limit=3),
    )

    result = service.recommend(auth_header="Bearer test", message="국내 주식 추천해줘")

    assert result["data"]["source"] == "ML_ACTIVE_SIGNAL"
    assert [item["symbol"] for item in result["data"]["items"]] == ["000660", "005930"]
    assert "SK하이닉스(000660)" in result["reply"]
    assert "위험종목" not in result["reply"]


def test_recommendation_service_returns_safe_empty_message_without_predictions():
    service = ChatbotRecommendationService(signal_payload_builder=lambda **kwargs: None)

    result = service.recommend(auth_header="Bearer test", message="추천해줘")

    assert result["data"]["items"] == []
    assert "활성 예측 결과를 찾지 못했습니다" in result["reply"]


def test_recommendation_service_attaches_rag_evidence_to_candidates():
    def fake_signal_payload(**kwargs):
        return {
            "asset_type": "STOCK",
            "model_version": "lgbm_kr_stock_signal_v1",
            "predictions": [
                {
                    "symbol": "005930",
                    "display_name": "삼성전자",
                    "signal_grade": "STRONG_BUY_CANDIDATE",
                    "signal_score": 44.0,
                    "up_probability": 0.66,
                    "risk_probability": 0.34,
                    "reason_summary": "상승 후보입니다.",
                },
            ],
            "performance": {},
        }

    def fake_evidence_provider(auth_header, symbol, question, limit):
        assert auth_header == "Bearer test"
        assert symbol == "005930"
        assert "삼성전자" in question
        assert limit == 2
        return [
            {
                "source_type": "DISCLOSURE",
                "source_id": "20260701000001",
                "chunk_text": "삼성전자는 신규 공급계약과 실적 개선 가능성이 함께 언급됐습니다.",
                "similarity": 0.91,
                "metadata": {"report_name": "주요사항보고서"},
            }
        ]

    service = ChatbotRecommendationService(
        signal_payload_builder=fake_signal_payload,
        evidence_provider=fake_evidence_provider,
    )

    result = service.recommend(auth_header="Bearer test", message="삼성전자 포함해서 국내 주식 추천해줘")

    item = result["data"]["items"][0]
    assert item["evidence"][0]["source_type"] == "DISCLOSURE"
    assert item["evidence"][0]["source_id"] == "20260701000001"
    assert result["data"]["citations"] == [
        {
            "source_type": "DISCLOSURE",
            "source_id": "20260701000001",
            "title": "삼성전자",
            "summary": "삼성전자는 신규 공급계약과 실적 개선 가능성이 함께 언급됐습니다.",
            "similarity": 0.91,
            "symbol": "005930",
            "metadata": {"report_name": "주요사항보고서"},
        }
    ]
    assert "근거: DISCLOSURE" in result["reply"]


def test_default_rag_evidence_provider_filters_to_symbol_and_disclosure_sources(monkeypatch):
    calls = []

    class FakeEmbeddingService:
        pass

    class FakeKnowledgeRepository:
        pass

    class FakeRagRetrievalService:
        def __init__(self, embedding_service, knowledge_repository):
            assert isinstance(embedding_service, FakeEmbeddingService)
            assert isinstance(knowledge_repository, FakeKnowledgeRepository)

        def retrieve_context(self, **kwargs):
            calls.append(kwargs)
            return [{"source_type": "DISCLOSURE", "source_id": "1", "chunk_text": "근거"}]

    monkeypatch.setattr(
        "backend.services.chatbot.recommendation_service.EmbeddingService",
        FakeEmbeddingService,
    )
    monkeypatch.setattr(
        "backend.services.chatbot.recommendation_service.KnowledgeRepository",
        FakeKnowledgeRepository,
    )
    monkeypatch.setattr(
        "backend.services.chatbot.recommendation_service.RagRetrievalService",
        FakeRagRetrievalService,
    )

    provider = build_default_rag_evidence_provider()
    rows = provider("Bearer test", "005930", "삼성전자 추천 근거", 2)

    assert rows[0]["source_id"] == "1"
    assert calls == [
        {
            "user_id": None,
            "question": "삼성전자 추천 근거",
            "symbol": "005930",
            "market": "KR",
            "source_types": ["DISCLOSURE", "OBSIDIAN", "APP_NOTE"],
            "limit": 2,
        }
    ]
