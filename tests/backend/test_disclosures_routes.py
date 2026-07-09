from flask import Flask

from backend.routes.disclosures import disclosures_bp


class FakeAnalysisService:
    def ensure_analysis(self, rcept_no):
        return {
            "analysis": {
                "rcept_no": rcept_no,
                "plain_summary": "요약",
            },
            "fromCache": False,
        }


class FakeDartRepository:
    def get_disclosure_by_rcept_no(self, rcept_no):
        return {"rcept_no": rcept_no, "stock_code": "000660"}


class FakeKnowledgeSyncService:
    def sync_analysis(self, analysis, disclosure):
        return {"status": "EMBEDDED", "chunk_count": 1}


def test_disclosure_analysis_route_includes_knowledge_index_result():
    app = Flask(__name__)
    app.register_blueprint(disclosures_bp)
    app.dart_analysis_service = FakeAnalysisService()
    app.dart_repository = FakeDartRepository()
    app.disclosure_knowledge_sync_service = FakeKnowledgeSyncService()

    client = app.test_client()
    response = client.get("/api/disclosures/20260709000001/analysis")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["success"] is True
    assert payload["data"]["knowledge_index"] == {"status": "EMBEDDED", "chunk_count": 1}


class FailingKnowledgeSyncService:
    def sync_analysis(self, analysis, disclosure):
        raise RuntimeError("embedding failed")


def test_disclosure_analysis_route_keeps_summary_response_when_knowledge_index_fails():
    app = Flask(__name__)
    app.register_blueprint(disclosures_bp)
    app.dart_analysis_service = FakeAnalysisService()
    app.dart_repository = FakeDartRepository()
    app.disclosure_knowledge_sync_service = FailingKnowledgeSyncService()

    client = app.test_client()
    response = client.get("/api/disclosures/20260709000002/analysis")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["success"] is True
    assert payload["data"]["analysis"]["plain_summary"] == "요약"
    assert payload["data"]["knowledge_index"] == {"status": "FAILED", "chunk_count": 0}
