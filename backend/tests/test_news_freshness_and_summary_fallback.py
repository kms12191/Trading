import requests

from backend.services.chatbot.web_fallback_search_service import ChatbotWebFallbackSearchService
from backend.services.news_summary_service import NewsSummaryService


def test_fresh_news_query_prefers_external_api_before_vector_db(monkeypatch):
    service = object.__new__(ChatbotWebFallbackSearchService)
    service.max_results = 5
    calls: list[str] = []

    def fake_api(query, limit):
        calls.append("api")
        return {"reply": "external", "data": {"source": "NAVER_API"}}

    def fake_rag(auth_header, user_id, query, limit):
        calls.append("rag")
        return {"reply": "old-vector", "data": {"source": "VECTOR_DB"}}

    monkeypatch.setattr(service, "_search_existing_open_apis", fake_api)
    monkeypatch.setattr(service, "_search_rag", fake_rag)
    monkeypatch.setattr(service, "_search_internal_db", lambda query, limit: None)
    monkeypatch.setattr(service, "_search_tavily", lambda query, limit: None)

    result = service.search("Bearer token", "user-1", "삼성전자 최신 뉴스 요약", limit=3)

    assert result["data"]["source"] == "NAVER_API"
    assert calls == ["api"]


def test_fresh_disclosure_query_does_not_fallback_to_general_news(monkeypatch):
    service = object.__new__(ChatbotWebFallbackSearchService)
    service.max_results = 5
    calls: list[str] = []

    monkeypatch.setattr(service, "_sync_and_search_dart", lambda query, limit: None)
    monkeypatch.setattr(service, "_search_internal_db", lambda query, limit: {"reply": "disclosure-db", "data": {"source": "DISCLOSURE_DB"}})
    monkeypatch.setattr(service, "_search_rag", lambda auth_header, user_id, query, limit: None)
    monkeypatch.setattr(service, "_search_tavily", lambda query, limit: None)

    def fake_naver(query, limit):
        calls.append("naver")
        return {"reply": "general-news", "data": {"source": "NAVER_API"}}

    monkeypatch.setattr(service, "_search_naver_news", fake_naver)
    monkeypatch.setattr(service, "_search_finnhub_news", lambda query, limit: None)

    result = service.search("Bearer token", "user-1", "삼성전자 최근 공시 보여줘", limit=3)

    assert result["data"]["source"] == "DISCLOSURE_DB"
    assert calls == []


def test_disclosure_query_limits_results_to_three(monkeypatch):
    service = object.__new__(ChatbotWebFallbackSearchService)
    service.max_results = 5
    captured_limits: list[int] = []

    def fake_dart(query, limit):
        captured_limits.append(limit)
        return {"reply": "disclosures", "data": {"source": "DISCLOSURE_DB"}}

    monkeypatch.setattr(service, "_sync_and_search_dart", fake_dart)
    monkeypatch.setattr(service, "_search_internal_db", lambda query, limit: None)
    monkeypatch.setattr(service, "_search_rag", lambda auth_header, user_id, query, limit: None)
    monkeypatch.setattr(service, "_search_tavily", lambda query, limit: None)

    result = service.search("Bearer token", "user-1", "\uc0bc\uc131\uc804\uc790 \uacf5\uc2dc \ubcf4\uc5ec\uc918")

    assert result["data"]["source"] == "DISCLOSURE_DB"
    assert captured_limits == [3]


def test_disclosure_query_uses_subject_term_for_dart_db_search(monkeypatch):
    service = object.__new__(ChatbotWebFallbackSearchService)
    captured_queries: list[str] = []

    def fake_list_disclosures(query, limit):
        captured_queries.append(query)
        return [
            {
                "corp_name": "\uc0bc\uc131\uc804\uc790",
                "report_nm": "\ud604\uae08\u318d\ud604\ubb3c\ubc30\ub2f9 \uacb0\uc815",
                "summary": "\ubc30\ub2f9 \uacb0\uc815 \uacf5\uc2dc",
                "url": "https://dart.fss.or.kr/example",
            }
        ]

    class FakeRepository:
        def list_disclosures(self, query, limit):
            return fake_list_disclosures(query, limit)

    service.dart_repository = FakeRepository()

    result = service._search_disclosure_db("\uc0bc\uc131\uc804\uc790 \uacf5\uc2dc \ubcf4\uc5ec\uc918", 3)

    assert result is not None
    assert result["data"]["source"] == "DISCLOSURE_DB"
    assert captured_queries == ["\uc0bc\uc131\uc804\uc790"]


def test_disclosure_db_retries_one_transient_server_error():
    service = object.__new__(ChatbotWebFallbackSearchService)

    class FakeRepository:
        def __init__(self):
            self.calls = 0

        def list_disclosures(self, query, limit):
            self.calls += 1
            if self.calls == 1:
                response = requests.Response()
                response.status_code = 500
                raise requests.HTTPError("temporary supabase failure", response=response)
            return [
                {
                    "corp_name": "\uc774\ub178\uc2a4\ud398\uc774\uc2a4",
                    "report_nm": "\uad8c\ub9ac\ub77d (\ubb34\uc0c1\uc99d\uc790)",
                    "summary": "\ubb34\uc0c1\uc99d\uc790\uc5d0 \ub530\ub978 \uad8c\ub9ac\ub77d \uc548\ub0b4\uc785\ub2c8\ub2e4.",
                    "url": "https://dart.fss.or.kr/example",
                }
            ]

    repository = FakeRepository()
    service.dart_repository = repository

    result = service._search_disclosure_db("\uc774\ub178\uc2a4\ud398\uc774\uc2a4 \uacf5\uc2dc", 3)

    assert result is not None
    assert repository.calls == 2
    assert result["data"]["source"] == "DISCLOSURE_DB"


def test_disclosure_query_does_not_use_tavily_when_dart_and_db_are_empty(monkeypatch):
    service = object.__new__(ChatbotWebFallbackSearchService)
    service.max_results = 5
    calls: list[str] = []

    monkeypatch.setattr(service, "_sync_and_search_dart", lambda query, limit: None)
    monkeypatch.setattr(service, "_search_internal_db", lambda query, limit: None)
    monkeypatch.setattr(service, "_search_rag", lambda auth_header, user_id, query, limit: None)

    def fake_tavily(query, limit):
        calls.append("tavily")
        return {"reply": "web", "data": {"source": "TAVILY_FALLBACK"}}

    monkeypatch.setattr(service, "_search_tavily", fake_tavily)

    result = service.search("Bearer token", "user-1", "\uc0bc\uc131\uc804\uc790 \uacf5\uc2dc \ubcf4\uc5ec\uc918")

    assert result["data"]["source"] == "NO_RESULT"
    assert calls == []


def test_disclosure_db_reply_separates_items_with_blank_lines():
    service = object.__new__(ChatbotWebFallbackSearchService)

    class FakeRepository:
        def list_disclosures(self, query, limit):
            return [
                {
                    "corp_name": "\uc0bc\uc131\uc804\uc790",
                    "report_nm": "1\ubc88 \uacf5\uc2dc",
                    "summary": "\uccab \ubc88\uc9f8 \uc694\uc57d",
                    "url": "https://dart.fss.or.kr/1",
                },
                {
                    "corp_name": "\uc0bc\uc131\uc804\uc790",
                    "report_nm": "2\ubc88 \uacf5\uc2dc",
                    "summary": "\ub450 \ubc88\uc9f8 \uc694\uc57d",
                    "url": "https://dart.fss.or.kr/2",
                },
            ]

    service.dart_repository = FakeRepository()

    result = service._search_disclosure_db("\uc0bc\uc131\uc804\uc790 \uacf5\uc2dc", 3)

    assert result is not None
    assert "https://dart.fss.or.kr/1\n\n2." in result["reply"]


def test_disclosure_db_reply_uses_analysis_summary_and_source_link():
    service = object.__new__(ChatbotWebFallbackSearchService)

    class FakeRepository:
        def list_disclosures(self, query, limit):
            return [
                {
                    "rcept_no": "20260701000123",
                    "corp_name": "\uc0bc\uc131\uc804\uc790",
                    "report_nm": "\ud604\uae08\u318d\ud604\ubb3c\ubc30\ub2f9 \uacb0\uc815",
                    "summary": "\uc0bc\uc131\uc804\uc790 - \ud604\uae08\u318d\ud604\ubb3c\ubc30\ub2f9 \uacb0\uc815 - 2026-07-01",
                    "url": "https://dart.fss.or.kr/example",
                }
            ]

        def get_disclosure_analysis(self, rcept_no):
            return {
                "plain_summary": "\ubc30\ub2f9 \uacb0\uc815\uc744 \uacf5\uc2dc\ud588\uc73c\uba70 \ubc30\ub2f9\uae30\uc900\uc77c\uacfc \uc9c0\uae09\uc608\uc815\uc77c \ud655\uc778\uc774 \ud544\uc694\ud569\ub2c8\ub2e4.",
                "headline": "\ubc30\ub2f9 \uacb0\uc815 \uacf5\uc2dc",
            }

    service.dart_repository = FakeRepository()

    result = service._search_disclosure_db("\uc0bc\uc131\uc804\uc790 \uacf5\uc2dc", 3)

    assert result is not None
    assert "\uc694\uc57d: \ubc30\ub2f9 \uacb0\uc815\uc744 \uacf5\uc2dc" in result["reply"]
    assert "https://dart.fss.or.kr/example\n\n\ucd9c\ucc98:" in result["reply"]
    assert "https://dart.fss.or.kr/dsab007/main.do" in result["reply"]
    assert "textCrpNm=%EC%82%BC%EC%84%B1%EC%A0%84%EC%9E%90" in result["reply"]


def test_disclosure_db_reply_matches_disclosure_tab_summary_view():
    service = object.__new__(ChatbotWebFallbackSearchService)

    class FakeRepository:
        def list_disclosures(self, query, limit):
            return [
                {
                    "rcept_no": "20260701000123",
                    "corp_name": "\uc0bc\uc131\uc804\uc790",
                    "report_nm": "\ud604\uae08\u318d\ud604\ubb3c\ubc30\ub2f9 \uacb0\uc815",
                    "summary": "",
                    "url": "https://dart.fss.or.kr/example",
                }
            ]

        def get_disclosure_analysis(self, rcept_no):
            return None

    class FakeAnalysisService:
        def ensure_analysis(self, rcept_no):
            return {
                "analysis": {
                    "headline": "\ubc30\ub2f9 \uacb0\uc815 \uacf5\uc2dc",
                    "plain_summary": "\ud604\uae08\ubc30\ub2f9 \uacb0\uc815\uc744 \uacf5\uc2dc\ud588\uc73c\uba70 \ubc30\ub2f9\uae30\uc900\uc77c\uacfc \uc9c0\uae09\uc77c \ud655\uc778\uc774 \ud544\uc694\ud569\ub2c8\ub2e4.",
                    "metrics": [{"label": "\ubc30\ub2f9 \uc720\ud615", "value": "\ud604\uae08\ubc30\ub2f9"}],
                    "check_items": [{"question": "\ud655\uc778 \ud3ec\uc778\ud2b8", "answer": "\ubc30\ub2f9\uae30\uc900\uc77c"}],
                    "risk_points": ["\ubc30\ub2f9 \uae30\ub300\uac10\uc774 \uc120\ubc18\uc601\ub410\ub294\uc9c0 \ud655\uc778"],
                }
            }

    service.dart_repository = FakeRepository()
    service.dart_analysis_service = FakeAnalysisService()

    result = service._search_disclosure_db("\uc0bc\uc131\uc804\uc790 \uacf5\uc2dc", 3)

    assert result is not None
    assert "\ud575\uc2ec: \ubc30\ub2f9 \uacb0\uc815 \uacf5\uc2dc" not in result["reply"]
    assert "\uc694\uc57d: \ud604\uae08\ubc30\ub2f9 \uacb0\uc815" in result["reply"]
    assert "\uc9c0\ud45c: \ubc30\ub2f9 \uc720\ud615 \u00b7 \ud604\uae08\ubc30\ub2f9" in result["reply"]
    assert "\ud655\uc778: \ud655\uc778 \ud3ec\uc778\ud2b8 \u00b7 \ubc30\ub2f9\uae30\uc900\uc77c" in result["reply"]
    assert "\ub9ac\uc2a4\ud06c: \ubc30\ub2f9 \uae30\ub300\uac10" in result["reply"]


def test_disclosure_db_reply_normalizes_title_and_repeated_headline_text():
    service = object.__new__(ChatbotWebFallbackSearchService)

    class FakeRepository:
        def list_disclosures(self, query, limit):
            return [
                {
                    "rcept_no": "20260701000456",
                    "corp_name": "\uc774\ub178\uc2a4\ud398\uc774\uc2a4",
                    "report_nm": "\uad8c\ub9ac\ub77d              (\ubb34\uc0c1\uc99d\uc790)",
                    "url": "https://dart.fss.or.kr/example",
                }
            ]

        def get_disclosure_analysis(self, rcept_no):
            return {
                "headline": "\uc815\uc815 \uacf5\uc2dc \uacf5\uc2dc\ub85c \uc138\ubd80 \uc870\uac74 \ud655\uc778\uc774 \ud544\uc694\ud569\ub2c8\ub2e4.",
                "plain_summary": "\uae30\uc874 \uacc4\uc57d \ub0b4\uc6a9\uc774 \uc815\uc815\ub410\uc2b5\ub2c8\ub2e4.",
            }

    service.dart_repository = FakeRepository()

    result = service._search_disclosure_db("\uc774\ub178\uc2a4\ud398\uc774\uc2a4 \uacf5\uc2dc", 3)

    assert result is not None
    assert "\uad8c\ub9ac\ub77d (\ubb34\uc0c1\uc99d\uc790)" in result["reply"]
    assert "\uad8c\ub9ac\ub77d              (\ubb34\uc0c1\uc99d\uc790)" not in result["reply"]
    assert "\uacf5\uc2dc \uacf5\uc2dc" not in result["reply"]
    assert "\ud575\uc2ec:" not in result["reply"]


def test_disclosure_db_refreshes_incomplete_cached_analysis_for_real_summary():
    service = object.__new__(ChatbotWebFallbackSearchService)

    class FakeRepository:
        def list_disclosures(self, query, limit):
            return [
                {
                    "rcept_no": "20260701000789",
                    "corp_name": "\uc774\ub178\uc2a4\ud398\uc774\uc2a4",
                    "report_nm": "[\uae30\uc7ac\uc815\uc815]\ub2e8\uc77c\ud310\ub9e4\u318d\uacf5\uae09\uacc4\uc57d\uccb4\uacb0",
                    "url": "https://dart.fss.or.kr/example",
                }
            ]

        def get_disclosure_analysis(self, rcept_no):
            return {
                "headline": "\uc815\uc815 \uacf5\uc2dc\ub85c \uc138\ubd80 \uc870\uac74 \ud655\uc778\uc774 \ud544\uc694\ud569\ub2c8\ub2e4.",
                "plain_summary": "",
                "risk_points": ["\uc6d0\uacf5\uc2dc \ube44\uad50 \ud544\uc694"],
            }

    class FakeAnalysisService:
        def ensure_analysis(self, rcept_no):
            return {
                "analysis": {
                    "headline": "\uacf5\uae09\uacc4\uc57d \uc815\uc815 \ub0b4\uc6a9 \ud655\uc778\uc774 \ud544\uc694\ud569\ub2c8\ub2e4.",
                    "plain_summary": "\uae30\uc874 \uacf5\uae09\uacc4\uc57d\uc758 \uae08\uc561\uacfc \uae30\uac04 \ub4f1 \uc870\uac74\uc774 \ubc14\ub00c\uc5c8\uc2b5\ub2c8\ub2e4. \uc815\uc815 \uc804\ud6c4 \ucc28\uc774\ub97c \ud655\uc778\ud574\uc57c \ud569\ub2c8\ub2e4.",
                    "metrics": [],
                    "check_items": [],
                    "risk_points": ["\uacc4\uc57d \uaddc\ubaa8\uc640 \uc77c\uc815 \ubcc0\uacbd \uc5ec\ubd80\ub97c \ud655\uc778\ud574\uc57c \ud569\ub2c8\ub2e4."],
                }
            }

    service.dart_repository = FakeRepository()
    service.dart_analysis_service = FakeAnalysisService()

    result = service._search_disclosure_db("\uc774\ub178\uc2a4\ud398\uc774\uc2a4 \uacf5\uc2dc", 3)

    assert result is not None
    assert "\uc694\uc57d: \uae30\uc874 \uacf5\uae09\uacc4\uc57d\uc758 \uae08\uc561\uacfc \uae30\uac04" in result["reply"]
    assert result["data"]["items"][0]["analysis"]["plain_summary"].startswith("\uae30\uc874 \uacf5\uae09\uacc4\uc57d")


def test_openai_summary_failure_uses_gemini_primary(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "openai-key")
    monkeypatch.setenv("GEMINI_API_KEY", "gemini-key")
    monkeypatch.setenv("NEWS_SUMMARY_GEMINI_PRIMARY_MODEL", "gemini-primary")
    monkeypatch.setenv("NEWS_SUMMARY_GEMINI_FALLBACK_MODEL", "gemini-fallback")
    calls: list[str] = []

    def fake_post(url, **kwargs):
        json_payload = kwargs.get("json") or {}
        if "openai.com" in url:
            calls.append("openai")
            raise requests.Timeout("openai timeout")
        calls.append(json_payload["model"])

        class Response:
            def raise_for_status(self):
                return None

            def json(self):
                return {"output_text": "1. 첫 줄\n2. 둘째 줄\n3. 셋째 줄"}

        return Response()

    monkeypatch.setattr(requests, "post", fake_post)

    result = NewsSummaryService().summarize({
        "title": "삼성전자 뉴스",
        "summary": "실적 관련 기사입니다.",
        "company_name": "삼성전자",
        "source": "NAVER",
    })

    assert calls == ["openai", "gemini-primary"]
    assert result["ai_summary_model"] == "gemini-primary"
    assert result["ai_summary"].startswith("1. 첫 줄")


def test_summary_failure_uses_deterministic_fallback_after_all_ai_failures(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "openai-key")
    monkeypatch.setenv("GEMINI_API_KEY", "gemini-key")
    monkeypatch.setenv("NEWS_SUMMARY_GEMINI_PRIMARY_MODEL", "gemini-primary")
    monkeypatch.setenv("NEWS_SUMMARY_GEMINI_FALLBACK_MODEL", "gemini-fallback")
    calls: list[str] = []

    def fake_post(url, **kwargs):
        json_payload = kwargs.get("json") or {}
        calls.append("openai" if "openai.com" in url else json_payload["model"])
        raise requests.ConnectionError("temporary failure")

    monkeypatch.setattr(requests, "post", fake_post)

    result = NewsSummaryService().summarize({
        "title": "코인 뉴스",
        "summary": "비트코인 변동성 관련 기사입니다.",
        "company_name": "BTC",
        "source": "TAVILY",
    })

    assert calls == ["openai", "gemini-primary", "gemini-fallback"]
    assert result["ai_summary_model"] == "fallback"
    assert "비트코인 변동성" in result["ai_summary"]
