import requests

from backend.services.chatbot.web_fallback_search_service import ChatbotWebFallbackSearchService
from backend.services.dart_analysis_service import DartDisclosureAnalysisService
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


def test_fresh_stock_news_query_prefers_tavily_before_internal_db(monkeypatch):
    service = object.__new__(ChatbotWebFallbackSearchService)
    service.max_results = 5
    calls: list[str] = []

    def fake_tavily(query, limit):
        calls.append("tavily")
        return {"reply": "tavily", "data": {"source": "TAVILY_FALLBACK"}}

    def fake_db(query, limit):
        calls.append("db")
        return {"reply": "db", "data": {"source": "NEWS_DB"}}

    monkeypatch.setattr(service, "_search_existing_open_apis", lambda query, limit: calls.append("api") or None)
    monkeypatch.setattr(service, "_search_tavily", fake_tavily)
    monkeypatch.setattr(service, "_search_internal_db", fake_db)
    monkeypatch.setattr(service, "_search_rag", lambda auth_header, user_id, query, limit: calls.append("rag") or None)

    result = service.search("Bearer token", "user-1", "삼성전자 최신 뉴스", limit=3)

    assert result["data"]["source"] == "TAVILY_FALLBACK"
    assert calls == ["api", "tavily"]


def test_market_news_query_uses_news_pipeline_not_vector_db(monkeypatch):
    service = object.__new__(ChatbotWebFallbackSearchService)
    service.max_results = 5
    calls: list[str] = []

    def fake_api(query, limit):
        calls.append("api")
        return {"reply": "market-news", "data": {"source": "NAVER_API"}}

    def fake_rag(auth_header, user_id, query, limit):
        raise AssertionError("최신 시장 뉴스는 Vector DB보다 뉴스 API를 먼저 사용해야 합니다.")

    monkeypatch.setattr(service, "_search_existing_open_apis", fake_api)
    monkeypatch.setattr(service, "_search_tavily", lambda query, limit: None)
    monkeypatch.setattr(service, "_search_internal_db", lambda query, limit: None)
    monkeypatch.setattr(service, "_search_rag", fake_rag)

    result = service.search("Bearer token", "user-1", "오늘 시장 주요 뉴스 알려줘", limit=5)

    assert result["data"]["source"] == "NAVER_API"
    assert calls == ["api"]


def test_crypto_news_query_does_not_fallback_to_disclosure_vector_db(monkeypatch):
    service = object.__new__(ChatbotWebFallbackSearchService)
    service.max_results = 5
    calls: list[str] = []

    monkeypatch.setattr(service, "_search_existing_open_apis", lambda query, limit: calls.append("api") or None)
    monkeypatch.setattr(service, "_search_tavily", lambda query, limit: calls.append("tavily") or None)
    monkeypatch.setattr(service, "_search_internal_db", lambda query, limit: calls.append("db") or None)
    monkeypatch.setattr(
        service,
        "_search_rag",
        lambda auth_header, user_id, query, limit: calls.append("rag")
        or {
            "reply": "저장된 벡터 DB 요약본에서 먼저 찾은 내용입니다.",
            "data": {
                "source": "VECTOR_DB",
                "items": [{"source_type": "DISCLOSURE", "chunk_text": "NAVER 공시 청크"}],
            },
        },
    )

    result = service.search("Bearer token", "user-1", "비트코인 관련 뉴스 요약해줘", limit=5)

    assert result["data"]["source"] == "NO_RESULT"
    assert "뉴스 결과를 찾지 못했습니다" in result["reply"]
    assert "공시" not in result["reply"]
    assert calls == ["tavily", "api", "tavily", "db"]


def test_market_news_reply_explains_search_criteria():
    service = object.__new__(ChatbotWebFallbackSearchService)

    class FakeSummaryService:
        def summarize(self, article):
            return {"ai_summary": "1. 국내 증시 주요 흐름을 요약했습니다."}

    service.news_summary_service = FakeSummaryService()

    result = service._format_external_news(
        "NAVER",
        "국내 증시 시장 주요 뉴스",
        [
            {
                "title": "코스피 장중 상승",
                "summary": "국내 증시 주요 기사입니다.",
                "url": "https://example.com/market",
            }
        ],
    )

    assert result["data"]["criteria"]["provider"] == "NAVER"
    assert result["data"]["criteria"]["query"] == "국내 증시 시장 주요 뉴스"
    assert result["data"]["criteria"]["sort"] == "date"
    assert "조회 기준:" in result["reply"]
    assert "최신순" in result["reply"]


def test_external_news_reply_uses_generated_summary_instead_of_source_description():
    service = object.__new__(ChatbotWebFallbackSearchService)

    class GeneratedSummaryService:
        def summarize(self, article):
            assert article["summary"] == "원문 제공 요약입니다."
            return {
                "ai_summary": "1. 발사 준비가 진전됐습니다.\n2. 다음 주요 일정을 확인했습니다.\n3. 세부 내용은 원문을 확인해 주세요.",
                "ai_summary_model": "test-model",
                "ai_summary_prompt_version": "test-v1",
            }

    service.news_summary_service = GeneratedSummaryService()
    result = service._format_external_news(
        "NAVER",
        "이노스페이스 뉴스",
        [
            {
                "title": "이노스페이스 발사체 관련 소식",
                "summary": "원문 제공 요약입니다.",
                "url": "https://example.com/innospace",
            }
        ],
    )

    item = result["data"]["items"][0]
    assert item["ai_summary"].startswith("1. 발사 준비가 진전됐습니다.")
    assert item["ai_summary"] != item["summary"]
    assert item["ai_summary_model"] == "test-model"


def test_stock_news_query_does_not_fallback_to_dart_disclosures(monkeypatch):
    service = object.__new__(ChatbotWebFallbackSearchService)
    calls: list[str] = []

    monkeypatch.setattr(service, "_search_naver_news", lambda query, limit: None)
    monkeypatch.setattr(service, "_search_finnhub_news", lambda query, limit: None)

    def fail_dart(query, limit):
        calls.append("dart")
        return {"reply": "dart", "data": {"source": "DISCLOSURE_DB"}}

    monkeypatch.setattr(service, "_sync_and_search_dart", fail_dart)

    result = service._search_existing_open_apis("삼성전자 최신 뉴스", 1)

    assert result is None
    assert calls == []


def test_crypto_news_tavily_filters_wiki_like_sources():
    service = object.__new__(ChatbotWebFallbackSearchService)
    service.tavily_enabled = True

    class FakeTavilyClient:
        def search(self, query, max_results):
            return {
                "results": [
                    {
                        "title": "비트코인 - 위키백과",
                        "content": "백과사전 설명",
                        "url": "https://ko.wikipedia.org/wiki/Bitcoin",
                    },
                    {
                        "title": "비트코인 시장 급등",
                        "content": "비트코인 가격과 ETF 수급을 다룬 최신 기사입니다.",
                        "url": "https://example-news.kr/bitcoin-market",
                    },
                    {
                        "title": "비트코인 - 나무위키",
                        "content": "나무위키 문서",
                        "url": "https://namu.wiki/w/Bitcoin",
                    },
                ]
            }

    class FakeSummaryService:
        def summarize(self, article):
            return {"ai_summary": "1. 비트코인 시장 최신 흐름을 요약했습니다."}

    service.tavily_client = FakeTavilyClient()
    service.news_summary_service = FakeSummaryService()

    result = service._search_tavily("비트코인 관련 뉴스 요약해줘", 3)

    assert result is not None
    urls = [item["url"] for item in result["data"]["items"]]
    assert urls == ["https://example-news.kr/bitcoin-market"]
    assert "wikipedia" not in result["reply"]
    assert "namu.wiki" not in result["reply"]


def test_crypto_news_tavily_filters_knowledge_in_sources():
    service = object.__new__(ChatbotWebFallbackSearchService)
    service.tavily_enabled = True

    class FakeTavilyClient:
        def search(self, query, max_results):
            return {
                "results": [
                    {
                        "title": "비트코인이 뭔가요? : 네이버 지식iN",
                        "content": "지식인 답변입니다.",
                        "url": "https://kin.naver.com/qna/detail.naver?d1id=4&dirId=401",
                    },
                    {
                        "title": "비트코인 ETF 수급 점검",
                        "content": "비트코인 시장 수급을 다룬 최신 기사입니다.",
                        "url": "https://example-news.kr/bitcoin-etf",
                    },
                ]
            }

    class FakeSummaryService:
        def summarize(self, article):
            return {"ai_summary": "1. 비트코인 ETF 수급과 가격 흐름을 요약했습니다."}

    service.tavily_client = FakeTavilyClient()
    service.news_summary_service = FakeSummaryService()

    result = service._search_tavily("비트코인 관련 뉴스 요약해줘", 3)

    assert result is not None
    urls = [item["url"] for item in result["data"]["items"]]
    assert urls == ["https://example-news.kr/bitcoin-etf"]
    assert result["data"]["criteria"]["provider"] == "TAVILY"
    assert "kin.naver.com" in result["data"]["criteria"]["excluded_sources"]
    assert "조회 기준:" in result["reply"]
    assert "kin.naver.com" not in result["reply"]
    assert all("지식" not in str(item.get("title") or "") for item in result["data"]["items"])


def test_subject_news_query_removes_related_modifier_for_search():
    service = object.__new__(ChatbotWebFallbackSearchService)

    assert service._normalize_news_query("이노스페이스 관련 뉴스 요약해줘") == "이노스페이스 462350"
    assert service._normalize_news_query("도지코인 관련 뉴스 요약해줘") == "도지코인 DOGE"


def test_dogecoin_news_query_uses_crypto_news_priority(monkeypatch):
    service = object.__new__(ChatbotWebFallbackSearchService)
    service.max_results = 5
    calls: list[str] = []

    def fake_tavily(query, limit):
        calls.append(f"tavily:{query}")
        return {"reply": "dogecoin news", "data": {"source": "TAVILY_FALLBACK", "query": "도지코인"}}

    monkeypatch.setattr(service, "_search_tavily", fake_tavily)
    monkeypatch.setattr(service, "_search_existing_open_apis", lambda query, limit: calls.append("api") or None)
    monkeypatch.setattr(service, "_search_internal_db", lambda query, limit: calls.append("db") or None)
    monkeypatch.setattr(service, "_search_rag", lambda auth_header, user_id, query, limit: calls.append("rag") or None)

    result = service.search("Bearer token", "user-1", "도지코인 관련 뉴스 요약해줘", limit=5)

    assert result["data"]["source"] == "TAVILY_FALLBACK"
    assert calls == ["tavily:도지코인 관련 뉴스 요약해줘"]


def test_combined_news_and_disclosure_query_returns_both_sections(monkeypatch):
    service = object.__new__(ChatbotWebFallbackSearchService)
    service.max_results = 5
    calls: list[str] = []

    def fake_api(query, limit):
        calls.append(f"api:{query}:{limit}")
        if "공시" in query and "뉴스" not in query:
            return {"reply": "공시 요약", "data": {"source": "DISCLOSURE_DB", "items": [{"report_nm": "공시"}]}}
        return {"reply": "뉴스 요약", "data": {"source": "NAVER_API", "items": [{"title": "뉴스"}]}}

    monkeypatch.setattr(service, "_search_existing_open_apis", fake_api)
    monkeypatch.setattr(service, "_search_internal_db", lambda query, limit: None)
    monkeypatch.setattr(service, "_search_rag", lambda auth_header, user_id, query, limit: None)
    monkeypatch.setattr(service, "_search_tavily", lambda query, limit: None)

    result = service.search("Bearer token", "user-1", "삼성전자 최근 공시와 뉴스 보고 정리해줘", limit=5)

    assert result["data"]["source"] == "NEWS_DISCLOSURE_COMBINED"
    assert result["data"]["news"]["source"] == "NAVER_API"
    assert result["data"]["disclosure"]["source"] == "DISCLOSURE_DB"
    assert "뉴스 요약" in result["reply"]
    assert "공시 요약" in result["reply"]
    assert calls == [
        "api:삼성전자 뉴스:1",
        "api:삼성전자 공시:1",
    ]


def test_combined_query_normalizes_samsung_typo_before_search(monkeypatch):
    service = object.__new__(ChatbotWebFallbackSearchService)
    service.max_results = 5
    calls: list[str] = []

    def fake_api(query, limit):
        calls.append(f"api:{query}:{limit}")
        if "공시" in query and "뉴스" not in query:
            return {"reply": "삼성전자 공시", "data": {"source": "DISCLOSURE_DB", "items": [{"corp_name": "삼성전자"}]}}
        return {"reply": "삼성전자 뉴스", "data": {"source": "NAVER_API", "items": [{"title": "삼성전자 뉴스"}]}}

    monkeypatch.setattr(service, "_search_existing_open_apis", fake_api)
    monkeypatch.setattr(service, "_search_internal_db", lambda query, limit: None)
    monkeypatch.setattr(service, "_search_rag", lambda auth_header, user_id, query, limit: None)
    monkeypatch.setattr(service, "_search_tavily", lambda query, limit: None)

    result = service.search("Bearer token", "user-1", "심상전자 최근 공시와 뉴스 보여줘", limit=5)

    assert result["data"]["news_query"] == "삼성전자 뉴스"
    assert result["data"]["disclosure_query"] == "삼성전자 공시"
    assert calls == [
        "api:삼성전자 뉴스:1",
        "api:삼성전자 공시:1",
    ]


def test_combined_query_keeps_different_news_and_disclosure_targets(monkeypatch):
    service = object.__new__(ChatbotWebFallbackSearchService)
    service.max_results = 5
    calls: list[str] = []

    def fake_api(query, limit):
        calls.append(f"api:{query}:{limit}")
        if "공시" in query and "뉴스" not in query:
            return {"reply": "이노스페이스 공시", "data": {"source": "DISCLOSURE_DB", "items": [{"corp_name": "이노스페이스"}]}}
        return {"reply": "LG전자 뉴스", "data": {"source": "NAVER_API", "items": [{"title": "LG전자 뉴스"}]}}

    monkeypatch.setattr(service, "_search_existing_open_apis", fake_api)
    monkeypatch.setattr(service, "_search_internal_db", lambda query, limit: None)
    monkeypatch.setattr(service, "_search_rag", lambda auth_header, user_id, query, limit: None)
    monkeypatch.setattr(service, "_search_tavily", lambda query, limit: None)

    result = service.search("Bearer token", "user-1", "엘지전자 뉴스보여주고 이노스페이스 공시 보여줘", limit=5)

    assert result["data"]["source"] == "NEWS_DISCLOSURE_COMBINED"
    assert result["data"]["news_query"] == "LG전자 뉴스"
    assert result["data"]["disclosure_query"] == "이노스페이스 462350 공시"
    assert calls == [
        "api:LG전자 뉴스:1",
        "api:이노스페이스 462350 공시:1",
    ]


def test_combined_query_does_not_reuse_news_target_for_invalid_disclosure_target(monkeypatch):
    service = object.__new__(ChatbotWebFallbackSearchService)
    service.max_results = 5
    calls: list[str] = []

    def fake_api(query, limit):
        calls.append(f"api:{query}:{limit}")
        if query == "초콜릿맛있다 공시":
            return None
        return {"reply": "삼성전자 뉴스", "data": {"source": "NAVER_API", "items": [{"title": "삼성전자 뉴스"}]}}

    monkeypatch.setattr(service, "_search_existing_open_apis", fake_api)
    monkeypatch.setattr(service, "_search_internal_db", lambda query, limit: None)
    monkeypatch.setattr(
        service,
        "_search_rag",
        lambda auth_header, user_id, query, limit: (_ for _ in ()).throw(AssertionError("없는 공시 대상은 RAG로 대체하면 안 됩니다.")),
    )
    monkeypatch.setattr(service, "_search_tavily", lambda query, limit: None)

    result = service.search("Bearer token", "user-1", "삼성전자 뉴스와 초콜릿맛있다 공시 보여줘", limit=5)

    assert result["data"]["source"] == "NEWS_DISCLOSURE_COMBINED"
    assert result["data"]["news_query"] == "삼성전자 뉴스"
    assert result["data"]["disclosure_query"] == "초콜릿맛있다 공시"
    assert result["data"]["news"]["source"] == "NAVER_API"
    assert result["data"]["disclosure"]["source"] == "NO_RESULT"
    assert result["data"]["disclosure"]["reason"] == "disclosure_target_not_recognized"
    assert "공시 대상 종목을 인식하지 못했습니다" in result["reply"]
    assert calls == ["api:삼성전자 뉴스:1"]


def test_combined_query_reports_unknown_disclosure_target_after_valid_news(monkeypatch):
    service = object.__new__(ChatbotWebFallbackSearchService)
    service.max_results = 5
    calls: list[str] = []

    def fake_api(query, limit):
        calls.append(f"api:{query}:{limit}")
        if query == "스타후르츠 공시":
            return None
        return {"reply": "이노스페이스 뉴스", "data": {"source": "NAVER_API", "items": [{"title": "이노스페이스 뉴스"}]}}

    monkeypatch.setattr(service, "_search_existing_open_apis", fake_api)
    monkeypatch.setattr(service, "_search_internal_db", lambda query, limit: None)
    monkeypatch.setattr(
        service,
        "_search_rag",
        lambda auth_header, user_id, query, limit: (_ for _ in ()).throw(AssertionError("없는 공시 대상은 RAG로 대체하면 안 됩니다.")),
    )
    monkeypatch.setattr(service, "_search_tavily", lambda query, limit: None)

    result = service.search("Bearer token", "user-1", "이노스페이스 뉴스와 스타후르츠 공시 보여줘", limit=5)

    assert result["data"]["news_query"] == "이노스페이스 462350 뉴스"
    assert result["data"]["disclosure_query"] == "스타후르츠 공시"
    assert result["data"]["news"]["source"] == "NAVER_API"
    assert result["data"]["disclosure"]["source"] == "NO_RESULT"
    assert result["data"]["disclosure"]["reason"] == "disclosure_target_not_recognized"
    assert "이노스페이스 뉴스" in result["reply"]
    assert "공시 대상 종목을 인식하지 못했습니다" in result["reply"]
    assert calls == ["api:이노스페이스 462350 뉴스:1"]


def test_combined_query_does_not_search_unrecognized_news_phrase(monkeypatch):
    service = object.__new__(ChatbotWebFallbackSearchService)
    service.max_results = 5
    calls: list[str] = []

    def fake_api(query, limit):
        calls.append(f"api:{query}:{limit}")
        if query == "바나나 먹고 싶다 뉴스":
            raise AssertionError("종목으로 인식할 수 없는 뉴스 문장은 검색하면 안 됩니다.")
        if query == "SK하이닉스 공시":
            return {"reply": "하이닉스 공시", "data": {"source": "DISCLOSURE_DB", "items": [{"corp_name": "SK하이닉스"}]}}
        return None

    monkeypatch.setattr(service, "_search_existing_open_apis", fake_api)
    monkeypatch.setattr(service, "_search_internal_db", lambda query, limit: None)
    monkeypatch.setattr(service, "_search_rag", lambda auth_header, user_id, query, limit: None)
    monkeypatch.setattr(service, "_search_tavily", lambda query, limit: None)

    result = service.search("Bearer token", "user-1", "바나나 먹고 싶다 뉴스와 하이닉스 공시 보여줘", limit=5)

    assert result["data"]["news_query"] == "바나나 먹고 싶다 뉴스"
    assert result["data"]["disclosure_query"] == "SK하이닉스 공시"
    assert result["data"]["news"]["source"] == "NO_RESULT"
    assert result["data"]["news"]["reason"] == "news_target_not_recognized"
    assert result["data"]["disclosure"]["source"] == "DISCLOSURE_DB"
    assert "뉴스 대상 종목을 인식하지 못했습니다" in result["reply"]
    assert "하이닉스 공시" in result["reply"]
    assert calls == ["api:SK하이닉스 공시:1"]


def test_combined_query_distinguishes_missing_disclosure_result_from_unknown_target(monkeypatch):
    service = object.__new__(ChatbotWebFallbackSearchService)
    service.max_results = 5

    monkeypatch.setattr(
        service,
        "_search_existing_open_apis",
        lambda query, limit: {"reply": "삼성전자 뉴스", "data": {"source": "NAVER_API", "items": [{"title": "삼성전자 뉴스"}]}}
        if query == "삼성전자 뉴스"
        else None,
    )
    monkeypatch.setattr(service, "_search_internal_db", lambda query, limit: None)
    monkeypatch.setattr(service, "_search_rag", lambda auth_header, user_id, query, limit: None)
    monkeypatch.setattr(service, "_search_tavily", lambda query, limit: None)

    result = service.search("Bearer token", "user-1", "삼성전자 뉴스와 하이닉스 공시 보여줘", limit=5)

    assert result["data"]["disclosure_query"] == "SK하이닉스 공시"
    assert result["data"]["disclosure"]["source"] == "NO_RESULT"
    assert result["data"]["disclosure"]["reason"] == "disclosure_result_not_found"
    assert "공시 결과를 찾지 못했습니다" in result["reply"]
    assert "공시 대상 종목을 인식하지 못했습니다" not in result["reply"]


def test_combined_news_disclosure_query_requires_company_target(monkeypatch):
    service = object.__new__(ChatbotWebFallbackSearchService)
    service.max_results = 5

    monkeypatch.setattr(
        service,
        "_search_existing_open_apis",
        lambda query, limit: (_ for _ in ()).throw(AssertionError("종목 없는 통합 요청은 검색하면 안 됩니다.")),
    )
    monkeypatch.setattr(
        service,
        "_search_internal_db",
        lambda query, limit: (_ for _ in ()).throw(AssertionError("종목 없는 통합 요청은 DB 검색하면 안 됩니다.")),
    )
    monkeypatch.setattr(
        service,
        "_search_rag",
        lambda auth_header, user_id, query, limit: (_ for _ in ()).throw(AssertionError("종목 없는 통합 요청은 RAG 검색하면 안 됩니다.")),
    )

    result = service.search("Bearer token", "user-1", "뉴스 공시 보여줘", limit=5)

    assert result["data"]["source"] == "NEWS_DISCLOSURE_SYMBOL_REQUIRED"
    assert "어떤 종목" in result["reply"]
    assert "삼성전자" in result["reply"]


def test_disclosure_db_filters_out_other_company_rows_for_target():
    service = object.__new__(ChatbotWebFallbackSearchService)

    class FakeDartRepository:
        def list_disclosures(self, query, limit):
            assert query == "삼성전자"
            return [
                {
                    "corp_name": "LG전자",
                    "stock_code": "066570",
                    "report_nm": "풍문또는보도에대한해명",
                    "summary": "LG전자 공시입니다.",
                    "url": "https://dart.fss.or.kr/lg",
                },
                {
                    "corp_name": "삼성전자",
                    "stock_code": "005930",
                    "report_nm": "주요사항보고서",
                    "summary": "삼성전자 공시입니다.",
                    "url": "https://dart.fss.or.kr/samsung",
                },
            ]

    service.dart_repository = FakeDartRepository()
    service.dart_analysis_service = None
    service.disclosure_knowledge_sync_service = None

    result = service._search_disclosure_db("심상전자 최근 공시 보여줘", 1)

    assert result is not None
    assert result["data"]["items"][0]["corp_name"] == "삼성전자"
    assert "LG전자" not in result["reply"]


def test_naver_news_filters_unrelated_latest_articles(monkeypatch):
    service = object.__new__(ChatbotWebFallbackSearchService)
    service.naver_client_id = "client"
    service.naver_client_secret = "secret"

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "items": [
                    {
                        "title": "서울 집값 74주째 상승…은행권 대출 조이기",
                        "description": "서울 집값과 은행 대출 규제 관련 기사입니다.",
                        "originallink": "https://example.com/real-estate",
                        "pubDate": "Tue, 14 Jul 2026 09:00:00 +0900",
                    },
                    {
                        "title": "삼성전자, 반도체 투자 확대",
                        "description": "삼성전자가 반도체 투자 확대 계획을 밝혔습니다.",
                        "originallink": "https://example.com/samsung",
                        "pubDate": "Tue, 14 Jul 2026 09:10:00 +0900",
                    },
                ]
            }

    class FakeSummaryService:
        def summarize(self, article):
            return {"ai_summary": "1. 삼성전자 반도체 투자 뉴스를 요약했습니다."}

    monkeypatch.setattr(requests, "get", lambda *args, **kwargs: FakeResponse())
    service.news_repository = type(
        "FailingNewsRepository",
        (),
        {"upsert_articles": lambda self, articles: (_ for _ in ()).throw(AssertionError("즉시 응답 경로에서 저장하면 안 됩니다."))},
    )()
    service.news_summary_service = FakeSummaryService()

    result = service._search_naver_news("심상전자 최근 뉴스 보여줘", 2)

    assert result is not None
    assert result["data"]["query"] == "삼성전자"
    assert [item["url"] for item in result["data"]["items"]] == ["https://example.com/samsung"]
    assert "서울 집값" not in result["reply"]


def test_generic_disclosure_query_asks_for_symbol_without_db_or_rag(monkeypatch):
    service = object.__new__(ChatbotWebFallbackSearchService)
    service.max_results = 5

    def fail_lookup(*args):
        raise AssertionError("종목 없는 공시 요청은 임의 DB/RAG 조회를 실행하지 않아야 합니다.")

    monkeypatch.setattr(service, "_sync_and_search_dart", fail_lookup)
    monkeypatch.setattr(service, "_search_internal_db", fail_lookup)
    monkeypatch.setattr(service, "_search_rag", fail_lookup)
    monkeypatch.setattr(service, "_search_tavily", fail_lookup)

    result = service.search("Bearer token", "user-1", "최근 공시 목록 보여줘", limit=3)

    assert result["data"]["source"] == "DISCLOSURE_SYMBOL_REQUIRED"
    assert "어떤 종목" in result["reply"]


def test_recent_disclosure_lookup_asks_for_symbol_without_db_or_rag(monkeypatch):
    service = object.__new__(ChatbotWebFallbackSearchService)
    service.max_results = 5

    def fail_lookup(*args):
        raise AssertionError("종목 없는 최근 공시 조회는 임의 DB/RAG 조회를 실행하지 않아야 합니다.")

    monkeypatch.setattr(service, "_sync_and_search_dart", fail_lookup)
    monkeypatch.setattr(service, "_search_internal_db", fail_lookup)
    monkeypatch.setattr(service, "_search_rag", fail_lookup)
    monkeypatch.setattr(service, "_search_tavily", fail_lookup)

    result = service.search("Bearer token", "user-1", "최근 공시 조회", limit=3)

    assert result["data"]["source"] == "DISCLOSURE_SYMBOL_REQUIRED"
    assert "어떤 종목" in result["reply"]


def test_us_company_disclosure_query_returns_unsupported_market_without_db(monkeypatch):
    service = object.__new__(ChatbotWebFallbackSearchService)
    service.max_results = 5

    def fail_lookup(*args):
        raise AssertionError("해외 기업 DART 공시는 국내 DB/RAG로 임의 대체하지 않아야 합니다.")

    monkeypatch.setattr(service, "_sync_and_search_dart", fail_lookup)
    monkeypatch.setattr(service, "_search_internal_db", fail_lookup)
    monkeypatch.setattr(service, "_search_rag", fail_lookup)
    monkeypatch.setattr(service, "_search_tavily", fail_lookup)

    result = service.search("Bearer token", "user-1", "아마존 최근 공시 보여줘", limit=3)

    assert result["data"]["source"] == "DISCLOSURE_UNSUPPORTED_MARKET"
    assert "DART 공시 대상" in result["reply"]


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


def test_disclosure_query_limits_results_to_one(monkeypatch):
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
    assert captured_limits == [1]


def test_disclosure_query_uses_one_when_default_limit_passed_without_count(monkeypatch):
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

    result = service.search("Bearer token", "user-1", "\uc0bc\uc131\uc804\uc790 \uacf5\uc2dc \ubcf4\uc5ec\uc918", limit=5)

    assert result["data"]["source"] == "DISCLOSURE_DB"
    assert captured_limits == [1]


def test_disclosure_query_respects_requested_result_count(monkeypatch):
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

    result = service.search("Bearer token", "user-1", "\uc0bc\uc131\uc804\uc790 \ucd5c\uadfc \uacf5\uc2dc 3\uac1c \ubcf4\uc5ec\uc918", limit=3)

    assert result["data"]["source"] == "DISCLOSURE_DB"
    assert captured_limits == [3]


def test_disclosure_query_rejects_result_count_over_three(monkeypatch):
    service = object.__new__(ChatbotWebFallbackSearchService)
    service.max_results = 5

    def fail_dart(query, limit):
        raise AssertionError("3건 초과 요청은 DART 조회를 실행하지 않아야 합니다.")

    monkeypatch.setattr(service, "_sync_and_search_dart", fail_dart)
    monkeypatch.setattr(service, "_search_internal_db", lambda query, limit: None)
    monkeypatch.setattr(service, "_search_rag", lambda auth_header, user_id, query, limit: None)
    monkeypatch.setattr(service, "_search_tavily", lambda query, limit: None)

    result = service.search("Bearer token", "user-1", "\uc0bc\uc131\uc804\uc790 \ucd5c\uadfc \uacf5\uc2dc 4\uac1c \ubcf4\uc5ec\uc918", limit=4)

    assert result["data"]["source"] == "DISCLOSURE_LIMIT_EXCEEDED"
    assert result["data"]["max_results"] == 3
    assert "최대 3개까지 조회 가능" in result["reply"]


def test_news_query_limits_results_to_one_when_count_is_omitted(monkeypatch):
    service = object.__new__(ChatbotWebFallbackSearchService)
    service.max_results = 5
    captured_limits: list[int] = []

    def fake_api(query, limit):
        captured_limits.append(limit)
        return {"reply": "news", "data": {"source": "NAVER_API"}}

    monkeypatch.setattr(service, "_search_existing_open_apis", fake_api)
    monkeypatch.setattr(service, "_search_internal_db", lambda query, limit: None)
    monkeypatch.setattr(service, "_search_rag", lambda auth_header, user_id, query, limit: None)
    monkeypatch.setattr(service, "_search_tavily", lambda query, limit: None)

    result = service.search("Bearer token", "user-1", "삼성전자 최신 뉴스 보여줘", limit=5)

    assert result["data"]["source"] == "NAVER_API"
    assert captured_limits == [1]


def test_news_query_respects_requested_result_count(monkeypatch):
    service = object.__new__(ChatbotWebFallbackSearchService)
    service.max_results = 5
    captured_limits: list[int] = []

    def fake_api(query, limit):
        captured_limits.append(limit)
        return {"reply": "news", "data": {"source": "NAVER_API"}}

    monkeypatch.setattr(service, "_search_existing_open_apis", fake_api)
    monkeypatch.setattr(service, "_search_internal_db", lambda query, limit: None)
    monkeypatch.setattr(service, "_search_rag", lambda auth_header, user_id, query, limit: None)
    monkeypatch.setattr(service, "_search_tavily", lambda query, limit: None)

    result = service.search("Bearer token", "user-1", "삼성전자 최근 뉴스 3개 보여줘", limit=5)

    assert result["data"]["source"] == "NAVER_API"
    assert captured_limits == [3]


def test_news_query_rejects_result_count_over_three(monkeypatch):
    service = object.__new__(ChatbotWebFallbackSearchService)
    service.max_results = 5

    def fail_api(query, limit):
        raise AssertionError("3건 초과 뉴스 요청은 외부 API 조회를 실행하지 않아야 합니다.")

    monkeypatch.setattr(service, "_search_existing_open_apis", fail_api)
    monkeypatch.setattr(service, "_search_internal_db", lambda query, limit: None)
    monkeypatch.setattr(service, "_search_rag", lambda auth_header, user_id, query, limit: None)
    monkeypatch.setattr(service, "_search_tavily", lambda query, limit: None)

    result = service.search("Bearer token", "user-1", "삼성전자 최근 뉴스 4개 보여줘", limit=5)

    assert result["data"]["source"] == "NEWS_LIMIT_EXCEEDED"
    assert result["data"]["max_results"] == 3
    assert "최대 3개까지 조회 가능" in result["reply"]


def test_news_db_generates_summary_when_cached_summary_is_missing():
    service = object.__new__(ChatbotWebFallbackSearchService)

    class FakeRepository:
        def list_articles(self, query, limit):
            return [
                {
                    "title": "삼성전자 반도체 투자 확대",
                    "summary": "삼성전자가 반도체 생산라인 투자 계획을 밝혔다.",
                    "url": "https://example.com/news",
                    "source": "NAVER",
                    "market": "DOMESTIC",
                    "company_name": "삼성전자",
                }
            ]

    class FakeSummaryService:
        def summarize(self, article):
            return {
                "ai_summary": "1. 삼성전자가 반도체 투자 계획을 공개했습니다.\n2. 생산라인 확대와 공급망 대응이 핵심입니다.\n3. 세부 투자 규모와 일정은 원문 확인이 필요합니다.",
                "ai_summary_model": "fake",
                "ai_summary_prompt_version": "test",
            }

    service.news_repository = FakeRepository()
    service.news_summary_service = FakeSummaryService()

    result = service._search_news_db("삼성전자 뉴스 보여줘", 1)

    assert result is not None
    assert result["data"]["source"] == "NEWS_DB"
    assert result["data"]["items"][0]["ai_summary"].startswith("1. 삼성전자가")
    assert "삼성전자가 반도체 투자 계획을 공개했습니다" in result["reply"]


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


def test_disclosure_query_removes_requested_count_from_dart_db_search(monkeypatch):
    service = object.__new__(ChatbotWebFallbackSearchService)
    captured_queries: list[str] = []

    def fake_list_disclosures(query, limit):
        captured_queries.append(query)
        return [
            {
                "corp_name": "\uc0bc\uc131\uc804\uc790",
                "report_nm": "\uae30\uc5c5\uc124\uba85\ud68c(IR)\uac1c\ucd5c(\uc548\ub0b4\uacf5\uc2dc)",
                "summary": "IR \uc548\ub0b4 \uacf5\uc2dc",
                "url": "https://dart.fss.or.kr/example",
            }
        ]

    class FakeRepository:
        def list_disclosures(self, query, limit):
            return fake_list_disclosures(query, limit)

    service.dart_repository = FakeRepository()

    result = service._search_disclosure_db("\uc0bc\uc131\uc804\uc790 \ucd5c\uadfc \uacf5\uc2dc 3\uac1c \ubcf4\uc5ec\uc918", 3)

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


def test_disclosure_rag_fallback_reuses_db_analysis_for_table_cards():
    service = object.__new__(ChatbotWebFallbackSearchService)

    class FakeRagService:
        def build_context(self, auth_header, user_id, query):
            return (
                "RAG 참고자료",
                [
                    {
                        "source_type": "DISCLOSURE",
                        "source_id": "20260629801143",
                        "chunk_text": "삼성전자 장래사업 경영계획 공시입니다. 2040년까지 반도체 및 신사업에 대규모 투자를 추진할 계획입니다.",
                        "similarity": 0.91,
                    }
                ],
            )

    class FakeRepository:
        def get_disclosure_by_rcept_no(self, rcept_no):
            assert rcept_no == "20260629801143"
            return {
                "rcept_no": "20260629801143",
                "corp_name": "삼성전자",
                "report_nm": "장래사업ㆍ경영계획(공정공시)",
                "summary": "기존 DB 요약",
                "url": "https://dart.fss.or.kr/example",
            }

        def get_disclosure_analysis(self, rcept_no):
            assert rcept_no == "20260629801143"
            return {
                "plain_summary": "2040년까지 반도체 및 신사업에 대규모 투자를 추진합니다.",
                "headline": "장기 투자 계획 공시",
                "metrics": [{"label": "투자 규모", "value": "약 2,450조 원"}],
                "check_items": [{"question": "투자 기간", "answer": "2026~2040년"}],
                "risk_points": ["장기 계획이라 실행 변동 가능성이 있습니다."],
                "analysis_source": "OPENDART_DOCUMENT",
                "confidence": "high",
                "sentiment_label": "정보",
            }

    service.rag_service = FakeRagService()
    service.dart_repository = FakeRepository()

    result = service._search_rag("Bearer token", "user-1", "삼성전자 최근 공시 보여줘", 1)

    assert result is not None
    assert result["data"]["source"] == "DISCLOSURE_DB"
    assert "DART 공시" in result["reply"]
    assert "지표: 투자 규모 · 약 2,450조 원" in result["reply"]
    assert result["data"]["items"][0]["analysis"]["metrics"][0]["label"] == "투자 규모"
    assert result["data"]["items"][0]["analysis"]["check_items"][0]["answer"] == "2026~2040년"
    assert "source_type=" not in result["reply"]
    assert "source_id=" not in result["reply"]


def test_disclosure_db_fallback_indexes_analysis_for_vector_search():
    service = object.__new__(ChatbotWebFallbackSearchService)
    synced_payloads = []

    class FakeRepository:
        def list_disclosures(self, query, limit):
            return [
                {
                    "rcept_no": "20260714000111",
                    "corp_name": "삼성전자",
                    "stock_code": "005930",
                    "report_nm": "장래사업ㆍ경영계획(공정공시)",
                    "summary": "DB 저장 요약",
                    "url": "https://dart.fss.or.kr/example",
                }
            ]

        def get_disclosure_analysis(self, rcept_no):
            return {
                "rcept_no": rcept_no,
                "plain_summary": "반도체 및 신사업 투자 계획을 공시했습니다.",
                "headline": "장기 투자 계획",
                "metrics": [{"label": "투자 규모", "value": "약 2,450조 원"}],
                "check_items": [{"question": "투자 기간", "answer": "2026~2040년"}],
                "risk_points": ["장기 계획이라 변동 가능성이 있습니다."],
                "analysis_source": "OPENDART_DOCUMENT",
                "confidence": "high",
                "sentiment_label": "정보",
            }

    class FakeKnowledgeSyncService:
        def sync_analysis(self, analysis, disclosure=None):
            synced_payloads.append((analysis, disclosure))
            return {"status": "EMBEDDED", "chunk_count": 1}

    service.dart_repository = FakeRepository()
    service.disclosure_knowledge_sync_service = FakeKnowledgeSyncService()

    result = service._search_disclosure_db("삼성전자 최근 공시 보여줘", 1)

    assert result is not None
    assert synced_payloads[0][0]["plain_summary"] == "반도체 및 신사업 투자 계획을 공시했습니다."
    assert synced_payloads[0][1]["rcept_no"] == "20260714000111"
    assert result["data"]["items"][0]["knowledge_index"]["status"] == "EMBEDDED"


def test_disclosure_db_fallback_indexes_saved_summary_without_cached_analysis():
    service = object.__new__(ChatbotWebFallbackSearchService)
    synced_payloads = []

    class FakeRepository:
        def list_disclosures(self, query, limit):
            return [
                {
                    "rcept_no": "20260714000222",
                    "corp_name": "삼성전자",
                    "stock_code": "005930",
                    "report_nm": "기업설명회(IR)개최(안내공시)",
                    "summary": "삼성전자가 2분기 경영실적 설명회를 개최한다는 공시입니다.",
                    "url": "https://dart.fss.or.kr/example",
                }
            ]

        def get_disclosure_analysis(self, rcept_no):
            return None

    class FakeAnalysisService:
        def ensure_analysis(self, rcept_no, force_refresh=False):
            return {"analysis": None}

    class FakeKnowledgeSyncService:
        def sync_analysis(self, analysis, disclosure=None):
            synced_payloads.append((analysis, disclosure))
            return {"status": "EMBEDDED", "chunk_count": 1}

    service.dart_repository = FakeRepository()
    service.dart_analysis_service = FakeAnalysisService()
    service.disclosure_knowledge_sync_service = FakeKnowledgeSyncService()

    result = service._search_disclosure_db("삼성전자 최근 공시 보여줘", 1)

    assert result is not None
    assert synced_payloads[0][0]["analysis_source"] == "DISCLOSURE_DB"
    assert "2분기 경영실적 설명회" in synced_payloads[0][0]["plain_summary"]
    assert result["data"]["items"][0]["knowledge_index"]["status"] == "EMBEDDED"


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
        def ensure_analysis(self, rcept_no, force_refresh=False):
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
        def ensure_analysis(self, rcept_no, force_refresh=False):
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


def test_disclosure_db_refreshes_title_only_cached_analysis_before_reply():
    service = object.__new__(ChatbotWebFallbackSearchService)
    refresh_calls: list[tuple[str, bool]] = []

    class FakeRepository:
        def list_disclosures(self, query, limit):
            return [
                {
                    "rcept_no": "20260701000890",
                    "corp_name": "\uc0bc\uc131\uc804\uc790",
                    "report_nm": "\uae30\uc5c5\uc124\uba85\ud68c(IR)\uac1c\ucd5c(\uc548\ub0b4\uacf5\uc2dc)",
                    "url": "https://dart.fss.or.kr/example",
                }
            ]

        def get_disclosure_analysis(self, rcept_no):
            return {
                "analysis_source": "TITLE_ONLY",
                "confidence": "low",
                "plain_summary": "\uc0c1\uc138 \ub0b4\uc6a9\uc744 \uc544\uc9c1 \ud655\uc778\ud558\uc9c0 \ubabb\ud574 \uc81c\ubaa9 \uae30\uc900\uc73c\ub85c\ub9cc \ubd84\ub958\ud55c \uacf5\uc2dc\uc785\ub2c8\ub2e4.",
                "check_items": [{"question": "\uc0c1\uc138 \ud655\uc778", "answer": "\uc81c\ubaa9 \uae30\ubc18"}],
            }

    class FakeAnalysisService:
        def ensure_analysis(self, rcept_no, force_refresh=False):
            refresh_calls.append((rcept_no, force_refresh))
            return {
                "analysis": {
                    "analysis_source": "OPENDART_DOCUMENT",
                    "confidence": "medium",
                    "plain_summary": "\uc0bc\uc131\uc804\uc790\uac00 \uae30\uc5c5\uc124\uba85\ud68c(IR) \uac1c\ucd5c \uc77c\uc815\uacfc \ucc38\uc11d \ubc29\uc2dd\uc744 \uc548\ub0b4\ud55c \uacf5\uc2dc\uc785\ub2c8\ub2e4.",
                    "metrics": [{"label": "\ud589\uc0ac", "value": "IR"}],
                    "check_items": [{"question": "\ud655\uc778 \ud3ec\uc778\ud2b8", "answer": "\uac1c\ucd5c\uc77c\uacfc \ucc38\uc11d \ub300\uc0c1"}],
                    "risk_points": ["\uc2e4\uc801 \ubc0f \uc804\ub9dd \uc5b8\uae09 \uc5ec\ubd80\ub97c \ud655\uc778\ud574\uc57c \ud569\ub2c8\ub2e4."],
                }
            }

    service.dart_repository = FakeRepository()
    service.dart_analysis_service = FakeAnalysisService()

    result = service._search_disclosure_db("\uc0bc\uc131\uc804\uc790 \ucd5c\uadfc \uacf5\uc2dc \ubcf4\uc5ec\uc918", 1)

    assert result is not None
    assert refresh_calls == [("20260701000890", True)]
    assert "\uc694\uc57d: \uc0bc\uc131\uc804\uc790\uac00 \uae30\uc5c5\uc124\uba85\ud68c(IR) \uac1c\ucd5c" in result["reply"]
    assert "\uc0c1\uc138 \ub0b4\uc6a9\uc744 \uc544\uc9c1 \ud655\uc778\ud558\uc9c0 \ubabb\ud574" not in result["reply"]
    assert result["data"]["items"][0]["analysis"]["analysis_source"] == "OPENDART_DOCUMENT"


def test_informational_disclosure_summary_describes_content_not_price_impact():
    service = object.__new__(DartDisclosureAnalysisService)
    disclosure = {
        "rcept_no": "20260701000890",
        "corp_name": "삼성전자",
        "stock_code": "005930",
        "report_nm": "기업설명회(IR)개최(안내공시)",
        "summary": "",
    }
    detail_text = (
        "개최목적 2026년 2분기 경영실적 발표 "
        "개최일시 2026년 7월 31일 10:00 "
        "장소 컨퍼런스콜 대상 국내외 기관투자자 "
        "주요내용 경영실적 설명 및 질의응답"
    )

    analysis = service._analyze(disclosure, detail_text, "OPENDART_DOCUMENT", "")

    assert analysis["category"] == "정보성 공시"
    assert "주가 방향성" not in analysis["plain_summary"]
    assert "직접 연결" not in analysis["plain_summary"]
    assert "기업설명회" in analysis["plain_summary"]
    assert "경영실적" in analysis["plain_summary"]


def test_largest_holder_share_change_disclosure_is_summarized_as_ownership_change():
    service = object.__new__(DartDisclosureAnalysisService)
    disclosure = {
        "rcept_no": "20260706000475",
        "corp_name": "삼성전자",
        "stock_code": "005930",
        "report_nm": "최대주주등소유주식변동신고서",
        "summary": "",
    }

    analysis = service._analyze(disclosure, "", "TITLE_ONLY", "")

    assert analysis["category"] == "최대주주 지분 변동"
    assert "주가 방향성" not in analysis["plain_summary"]
    assert "직접 연결" not in analysis["plain_summary"]
    assert "주가 방향성" not in analysis["sentiment_message"]
    assert all("주가 방향성" not in point for point in analysis["key_points"])
    assert "보유주식" in analysis["plain_summary"]
    assert "변동" in analysis["plain_summary"]


def test_largest_holder_share_change_old_info_cache_is_refreshed_selectively():
    service = object.__new__(DartDisclosureAnalysisService)
    service.api_key = ""
    service.ai_enabled = False
    saved_rows: list[dict] = []

    class FakeRepository:
        def get_disclosure_analysis(self, rcept_no):
            return {
                "rcept_no": rcept_no,
                "category": "정보성 공시",
                "plain_summary": "이번 공시는 주가 방향성과 직접적인 연관이 없는 정보성 공시입니다.",
                "raw_payload": {
                    "analysis_version": "v3.33",
                    "report_nm": "최대주주등소유주식변동신고서",
                },
            }

        def get_disclosure_by_rcept_no(self, rcept_no):
            return {
                "rcept_no": rcept_no,
                "corp_name": "삼성전자",
                "stock_code": "005930",
                "report_nm": "최대주주등소유주식변동신고서",
                "summary": "",
            }

        def upsert_disclosure_analysis(self, row):
            saved_rows.append(row)
            return row

    service.repository = FakeRepository()

    result = service.ensure_analysis("20260706000475")

    assert result["fromCache"] is False
    assert saved_rows[0]["category"] == "최대주주 지분 변동"
    assert "주가 방향성" not in saved_rows[0]["plain_summary"]


def test_largest_holder_share_change_old_cache_without_report_name_is_refreshed():
    service = object.__new__(DartDisclosureAnalysisService)
    service.api_key = ""
    service.ai_enabled = False
    disclosure_reads: list[str] = []
    saved_rows: list[dict] = []

    class FakeRepository:
        def get_disclosure_analysis(self, rcept_no):
            return {
                "rcept_no": rcept_no,
                "category": "정보성 공시",
                "plain_summary": "이번 공시는 주가 방향성과 직접적인 연관이 없는 정보성 공시입니다.",
                "raw_payload": {"analysis_version": "v3.33"},
            }

        def get_disclosure_by_rcept_no(self, rcept_no):
            disclosure_reads.append(rcept_no)
            return {
                "rcept_no": rcept_no,
                "corp_name": "삼성전자",
                "stock_code": "005930",
                "report_nm": "최대주주등소유주식변동신고서",
                "summary": "",
            }

        def upsert_disclosure_analysis(self, row):
            saved_rows.append(row)
            return row

    service.repository = FakeRepository()

    result = service.ensure_analysis("20260706000475")

    assert result["fromCache"] is False
    assert disclosure_reads == ["20260706000475"]
    assert saved_rows[0]["category"] == "최대주주 지분 변동"
    assert "주가 방향성" not in saved_rows[0]["plain_summary"]


def test_largest_holder_share_change_cache_with_stale_key_points_is_refreshed():
    service = object.__new__(DartDisclosureAnalysisService)
    service.api_key = ""
    service.ai_enabled = False
    saved_rows: list[dict] = []

    class FakeRepository:
        def get_disclosure_analysis(self, rcept_no):
            return {
                "rcept_no": rcept_no,
                "category": "최대주주 지분 변동",
                "sentiment_message": "주가 방향성과 직접 연결하기 어려운 정보성 공시입니다.",
                "plain_summary": "최대주주 또는 특수관계인의 보유주식 변동을 신고한 공시입니다.",
                "key_points": ["주가 방향성과 직접 연결하기 어려운 정보성 공시입니다."],
                "raw_payload": {
                    "analysis_version": "v3.33",
                    "report_nm": "최대주주등소유주식변동신고서",
                },
            }

        def get_disclosure_by_rcept_no(self, rcept_no):
            return {
                "rcept_no": rcept_no,
                "corp_name": "삼성전자",
                "stock_code": "005930",
                "report_nm": "최대주주등소유주식변동신고서",
                "summary": "",
            }

        def upsert_disclosure_analysis(self, row):
            saved_rows.append(row)
            return row

    service.repository = FakeRepository()

    result = service.ensure_analysis("20260706800672")

    assert result["fromCache"] is False
    assert "주가 방향성" not in saved_rows[0]["sentiment_message"]
    assert all("주가 방향성" not in point for point in saved_rows[0]["key_points"])


def test_stock_option_grant_extracts_table_values_and_readable_target():
    service = object.__new__(DartDisclosureAnalysisService)
    disclosure = {
        "rcept_no": "20260706000475",
        "corp_name": "이노스페이스",
        "stock_code": "462350",
        "report_nm": "주식매수선택권부여에관한신고",
        "summary": "",
    }
    detail_text = (
        "주식매수선택권 부여 "
        "1. 부여대상자(명) 해당 상장회사의 이사ㆍ감사 또는 피용자 1 "
        "관계회사의 이사ㆍ감사 또는 피용자 - "
        "2. 당해부여 주식 (주) 보통주식 18,000 기타주식 - "
        "3. 행사 조건 행사기간 시작일 2028년 07월 06일 종료일 2033년 07월 05일 "
        "행사가격 (원) 보통주식 13,810 기타주식 - "
        "6. 부여일자 2026년 07월 06일"
    )

    analysis = service._analyze(disclosure, detail_text, "OPENDART_DOCUMENT", "")
    metric_map = {item["label"]: item["value"] for item in analysis["metrics"]}

    assert metric_map["부여대상"] == "상장회사 임직원 1명"
    assert metric_map["부여주식수"] == "18,000주"
    assert metric_map["행사가격"] == "13,810원"
    assert metric_map["행사기간"] == "2028년 07월 06일~2033년 07월 05일"
    assert "행사가격은 13,810원" in analysis["plain_summary"]
    assert "(명) 해당 상장회사" not in metric_map["부여대상"]


def test_stock_option_grant_bad_target_cache_is_refreshed_selectively():
    service = object.__new__(DartDisclosureAnalysisService)
    service.api_key = "dart-key"
    service.ai_enabled = False
    saved_rows: list[dict] = []
    detail_text = (
        "주식매수선택권 부여 "
        "1. 부여대상자(명) 해당 상장회사의 이사ㆍ감사 또는 피용자 1 "
        "관계회사의 이사ㆍ감사 또는 피용자 - "
        "2. 당해부여 주식 (주) 보통주식 18,000 기타주식 - "
        "3. 행사 조건 행사기간 시작일 2028년 07월 06일 종료일 2033년 07월 05일 "
        "행사가격 (원) 보통주식 13,810 기타주식 -"
    )

    class FakeRepository:
        def get_disclosure_analysis(self, rcept_no):
            return {
                "rcept_no": rcept_no,
                "category": "주식매수선택권",
                "plain_summary": "주식선택권 공시입니다. 임직원 보상 성격이지만 행사 물량과 행사가격에 따라 향후 희석 가능성을 확인해야 합니다.",
                "metrics": [{"label": "부여대상", "value": "(명) 해당 상장회사의 이사ㆍ감사 또는 피용자 1 관계회사..."}],
                "raw_payload": {
                    "analysis_version": "v3.33",
                    "report_nm": "주식매수선택권부여에관한신고",
                },
            }

        def get_disclosure_by_rcept_no(self, rcept_no):
            return {
                "rcept_no": rcept_no,
                "corp_name": "이노스페이스",
                "stock_code": "462350",
                "report_nm": "주식매수선택권부여에관한신고",
                "summary": "",
            }

        def upsert_disclosure_analysis(self, row):
            saved_rows.append(row)
            return row

    service.repository = FakeRepository()
    service._fetch_document_text = lambda rcept_no: detail_text

    result = service.ensure_analysis("20260706000475")

    metric_map = {item["label"]: item["value"] for item in saved_rows[0]["metrics"]}
    assert result["fromCache"] is False
    assert metric_map["부여대상"] == "상장회사 임직원 1명"
    assert metric_map["부여주식수"] == "18,000주"
    assert metric_map["행사가격"] == "13,810원"


def test_stock_option_ai_refinement_does_not_remove_core_metric_summary():
    service = object.__new__(DartDisclosureAnalysisService)
    service.ai_model = "gpt-test"
    service.ai_provider = "openai"
    service.ai_prompt_version = "v3"
    analysis = {
        "category": "주식매수선택권",
        "plain_summary": (
            "주식매수선택권 공시입니다. 임직원 보상 성격이지만 행사 물량과 행사가격에 따라 "
            "향후 희석 가능성을 확인해야 합니다 (부여 주식 수는 18,000주, 행사가격은 13,810원)."
        ),
        "metrics": [
            {"label": "부여주식수", "value": "18,000주"},
            {"label": "행사가격", "value": "13,810원"},
        ],
        "raw_payload": {},
    }
    refined = {
        "plain_summary": "주식선택권 공시입니다. 임직원 보상 성격이지만 행사 물량과 행사가격을 확인해야 합니다.",
    }

    result = service._merge_ai_refinement(analysis, refined)

    assert "18,000주" in result["plain_summary"]
    assert "13,810원" in result["plain_summary"]


def test_stock_option_cache_with_generic_summary_is_refreshed_selectively():
    service = object.__new__(DartDisclosureAnalysisService)
    service.api_key = "dart-key"
    service.ai_enabled = False
    saved_rows: list[dict] = []
    detail_text = (
        "주식매수선택권 부여 "
        "1. 부여대상자(명) 해당 상장회사의 이사ㆍ감사 또는 피용자 1 "
        "관계회사의 이사ㆍ감사 또는 피용자 - "
        "2. 당해부여 주식 (주) 보통주식 18,000 기타주식 - "
        "3. 행사 조건 행사기간 시작일 2028년 07월 06일 종료일 2033년 07월 05일 "
        "행사가격 (원) 보통주식 13,810 기타주식 -"
    )

    class FakeRepository:
        def get_disclosure_analysis(self, rcept_no):
            return {
                "rcept_no": rcept_no,
                "category": "주식매수선택권",
                "plain_summary": "주식선택권 공시입니다. 임직원 보상 성격이지만 행사 물량과 행사가격을 확인해야 합니다.",
                "metrics": [
                    {"label": "부여주식수", "value": "18,000주"},
                    {"label": "행사가격", "value": "13,810원"},
                ],
                "raw_payload": {
                    "analysis_version": "v3.33",
                    "report_nm": "주식매수선택권부여에관한신고",
                },
            }

        def get_disclosure_by_rcept_no(self, rcept_no):
            return {
                "rcept_no": rcept_no,
                "corp_name": "이노스페이스",
                "stock_code": "462350",
                "report_nm": "주식매수선택권부여에관한신고",
                "summary": "",
            }

        def upsert_disclosure_analysis(self, row):
            saved_rows.append(row)
            return row

    service.repository = FakeRepository()
    service._fetch_document_text = lambda rcept_no: detail_text

    result = service.ensure_analysis("20260706000475")

    assert result["fromCache"] is False
    assert "18,000주" in saved_rows[0]["plain_summary"]
    assert "13,810원" in saved_rows[0]["plain_summary"]


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
                return {"output_text": "1. 삼성전자 실적 관련 기사입니다.\n2. 반도체 업황 확인이 필요합니다.\n3. 세부 내용은 원문 기준으로 확인하세요."}

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
    assert result["ai_summary"].startswith("1. 삼성전자 실적")


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


def test_incomplete_ai_news_summary_uses_deterministic_fallback(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "openai-key")
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)

    def fake_post(url, **kwargs):
        class Response:
            def raise_for_status(self):
                return None

            def json(self):
                return {
                    "choices": [
                        {
                            "message": {
                                "content": "1. 단계를 구축하고 있으며,"
                            }
                        }
                    ]
                }

        return Response()

    monkeypatch.setattr(requests, "post", fake_post)

    result = NewsSummaryService().summarize({
        "title": "행정 돌 깨고 기업 사간표 맞춘다...정부 반도체 메가산단 구축 최대...",
        "summary": "정부가 반도체 메가산단 구축을 추진한다는 기사입니다.",
        "company_name": "삼성전자",
        "source": "NAVER",
    })

    assert result["ai_summary_model"] == "fallback"
    assert "단계를 구축하고 있으며" not in result["ai_summary"]
    assert "정부가 반도체 메가산단 구축" in result["ai_summary"]


def test_summary_normalization_keeps_two_valid_lines():
    summary = NewsSummaryService()._normalize_summary(
        "1. 애플이 신규 AI 기능을 공개했다.\n2. 시장 반응과 후속 일정은 아직 확인되지 않았다."
    )

    assert summary == (
        "1. 애플이 신규 AI 기능을 공개했다.\n"
        "2. 시장 반응과 후속 일정은 아직 확인되지 않았다."
    )


def test_summary_normalization_discards_meta_third_line():
    summary = NewsSummaryService()._normalize_summary(
        "1. 애플이 신규 AI 기능을 공개했다.\n"
        "2. 시장 반응과 후속 일정은 아직 확인되지 않았다.\n"
        "3. 기사 내용이 부족하여 구체적인 정보가 부족하다."
    )

    assert summary == (
        "1. 애플이 신규 AI 기능을 공개했다.\n"
        "2. 시장 반응과 후속 일정은 아직 확인되지 않았다."
    )


def test_summary_normalization_keeps_three_valid_lines():
    summary = NewsSummaryService()._normalize_summary(
        "1. 애플이 신규 AI 기능을 공개했다.\n"
        "2. 해당 기능은 다음 소프트웨어 업데이트에 포함될 예정이다.\n"
        "3. 회사는 개발자 대상 세부 내용을 공개했다."
    )

    assert summary == (
        "1. 애플이 신규 AI 기능을 공개했다.\n"
        "2. 해당 기능은 다음 소프트웨어 업데이트에 포함될 예정이다.\n"
        "3. 회사는 개발자 대상 세부 내용을 공개했다."
    )
