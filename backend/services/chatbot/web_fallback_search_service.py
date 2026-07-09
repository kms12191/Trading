import hashlib
import html
import os
import re
from datetime import date, datetime, timedelta, timezone
from typing import Any

import requests

from backend.services.chatbot.rag_service import ChatbotRAGService
from backend.services.dart_ingest import DartIngestService
from backend.services.dart_repository import DartRepository
from backend.services.news_repository import NewsRepository
from backend.services.news_summary_service import NewsSummaryService
from backend.services.tavily_client import TavilyClient, TavilySearchError


class ChatbotWebFallbackSearchService:
    def __init__(self) -> None:
        self.rag_service = ChatbotRAGService()
        self.news_repository = NewsRepository()
        self.dart_repository = DartRepository()
        self.news_summary_service = NewsSummaryService()
        self.tavily_client = TavilyClient()
        self.naver_client_id = os.getenv("NAVER_CLIENT_ID", "")
        self.naver_client_secret = os.getenv("NAVER_CLIENT_SECRET", "")
        self.finnhub_api_key = os.getenv("FINNHUB_API_KEY", "")
        self.max_results = self._read_int_env("CHATBOT_WEB_SEARCH_MAX_RESULTS", 5)
        self.tavily_enabled = os.getenv("CHATBOT_TAVILY_FALLBACK_ENABLED", "true").lower() == "true"

    @staticmethod
    def _read_int_env(name: str, default: int) -> int:
        try:
            value = int(os.getenv(name, str(default)))
            return value if value > 0 else default
        except (TypeError, ValueError):
            return default

    def search(self, auth_header: str | None, user_id: str | None, query: str, limit: int | None = None) -> dict[str, Any]:
        text = str(query or "").strip()
        max_results = max(1, min(int(limit or self.max_results), 10))
        if not text:
            return {"reply": "검색어를 입력해 주세요.", "data": {"source": "EMPTY_QUERY"}}

        rag_result = self._search_rag(auth_header, user_id, text, max_results)
        if rag_result:
            return rag_result

        db_result = self._search_internal_db(text, max_results)
        if db_result:
            return db_result

        api_result = self._search_existing_open_apis(text, max_results)
        if api_result:
            return api_result

        tavily_result = self._search_tavily(text, max_results)
        if tavily_result:
            return tavily_result

        return {
            "reply": "조건에 맞는 뉴스/공시/웹 검색 결과를 찾지 못했습니다.",
            "data": {"source": "NO_RESULT", "query": text},
        }

    def _search_rag(self, auth_header: str | None, user_id: str | None, query: str, limit: int) -> dict[str, Any] | None:
        context, rows = self.rag_service.build_context(auth_header, user_id, query)
        if not context or not rows:
            return None

        lines = ["저장된 벡터 DB 요약본에서 먼저 찾은 내용입니다."]
        for index, row in enumerate(rows[:limit], start=1):
            chunk_text = self._compact(row.get("chunk_text"), 220)
            if not chunk_text:
                continue
            source_type = row.get("source_type") or "UNKNOWN"
            source_id = row.get("source_id") or "-"
            lines.append(f"{index}. {chunk_text}")
            lines.append(f"   source_type={source_type}, source_id={source_id}")

        if len(lines) == 1:
            return None
        lines.append("출처: Vector DB")
        return {
            "reply": "\n".join(lines),
            "data": {"source": "VECTOR_DB", "items": rows[:limit]},
        }

    def _search_internal_db(self, query: str, limit: int) -> dict[str, Any] | None:
        ordered_sources = ["DISCLOSURE", "NEWS"] if self._is_disclosure_query(query) else ["NEWS", "DISCLOSURE"]
        for source in ordered_sources:
            if source == "NEWS":
                result = self._search_news_db(query, limit)
            else:
                result = self._search_disclosure_db(query, limit)
            if result:
                return result
        return None

    def _search_news_db(self, query: str, limit: int) -> dict[str, Any] | None:
        try:
            rows = self.news_repository.list_articles(query=query, limit=limit)
        except Exception:
            return None
        if not rows:
            return None

        lines = ["DB에 저장된 뉴스 원문/요약에서 찾은 내용입니다."]
        for index, row in enumerate(rows[:limit], start=1):
            title = row.get("title") or "제목 없음"
            summary = row.get("ai_summary") or row.get("summary") or ""
            url = row.get("url") or ""
            lines.append(f"{index}. {title}")
            if summary:
                lines.append(f"   {self._compact(summary, 180)}")
            if url:
                lines.append(f"   {url}")
        lines.append("출처: news_articles DB")
        return {"reply": "\n".join(lines), "data": {"source": "NEWS_DB", "items": rows[:limit]}}

    def _search_disclosure_db(self, query: str, limit: int) -> dict[str, Any] | None:
        try:
            rows = self.dart_repository.list_disclosures(query=query, limit=limit)
        except Exception:
            return None
        if not rows:
            return None

        lines = ["DB에 저장된 공시 원문/요약에서 찾은 내용입니다."]
        for index, row in enumerate(rows[:limit], start=1):
            title = row.get("report_nm") or "공시 제목 없음"
            corp_name = row.get("corp_name") or "-"
            summary = row.get("summary") or ""
            url = row.get("url") or ""
            lines.append(f"{index}. {corp_name} / {title}")
            if summary:
                lines.append(f"   {self._compact(summary, 180)}")
            if url:
                lines.append(f"   {url}")
        lines.append("출처: dart_disclosures DB")
        return {"reply": "\n".join(lines), "data": {"source": "DISCLOSURE_DB", "items": rows[:limit]}}

    def _search_existing_open_apis(self, query: str, limit: int) -> dict[str, Any] | None:
        if self._is_disclosure_query(query):
            disclosure_result = self._sync_and_search_dart(query, limit)
            if disclosure_result:
                return disclosure_result

        news_result = self._search_naver_news(query, limit)
        if news_result:
            return news_result

        finnhub_result = self._search_finnhub_news(query, limit)
        if finnhub_result:
            return finnhub_result

        if not self._is_disclosure_query(query):
            return self._sync_and_search_dart(query, limit)
        return None

    def _sync_and_search_dart(self, query: str, limit: int) -> dict[str, Any] | None:
        if not os.getenv("DART_API_KEY", ""):
            return None
        try:
            DartIngestService().run_incremental()
        except Exception:
            return None
        return self._search_disclosure_db(query, limit)

    def _search_naver_news(self, query: str, limit: int) -> dict[str, Any] | None:
        if not self.naver_client_id or not self.naver_client_secret:
            return None
        try:
            response = requests.get(
                "https://openapi.naver.com/v1/search/news.json",
                headers={
                    "X-Naver-Client-Id": self.naver_client_id,
                    "X-Naver-Client-Secret": self.naver_client_secret,
                },
                params={"query": query, "display": min(limit, 10), "sort": "date"},
                timeout=15,
            )
            response.raise_for_status()
        except Exception:
            return None

        articles = []
        for item in response.json().get("items") or []:
            title = self._clean_html(item.get("title"))
            summary = self._clean_html(item.get("description"))
            url = item.get("originallink") or item.get("link") or ""
            articles.append({
                "market": "DOMESTIC",
                "source": "NAVER",
                "source_article_id": url or f"naver:{self._hash(title + query)}",
                "title": title,
                "summary": summary,
                "url": url,
                "published_at": self._parse_naver_date(item.get("pubDate")),
                "company_name": query,
                "symbol": "",
                "language": "ko",
                "raw_payload": {"provider": "NAVER", "query_text": query, **item},
                "content_hash": self._hash(f"{title}|{summary}|{url}"),
                "is_active": True,
                "fetched_at": datetime.now(timezone.utc).isoformat(),
            })

        if not articles:
            return None
        self._try_upsert_news(articles)
        return self._format_external_news("NAVER", query, articles[:limit])

    def _search_finnhub_news(self, query: str, limit: int) -> dict[str, Any] | None:
        if not self.finnhub_api_key:
            return None
        symbol = self._extract_us_symbol(query)
        if not symbol:
            return None
        today = date.today()
        try:
            response = requests.get(
                "https://finnhub.io/api/v1/company-news",
                params={
                    "symbol": symbol,
                    "from": (today - timedelta(days=7)).isoformat(),
                    "to": today.isoformat(),
                    "token": self.finnhub_api_key,
                },
                timeout=15,
            )
            response.raise_for_status()
        except Exception:
            return None

        articles = []
        for item in (response.json() or [])[:limit]:
            title = str(item.get("headline") or "").strip()
            summary = str(item.get("summary") or "").strip()
            url = str(item.get("url") or "").strip()
            articles.append({
                "market": "GLOBAL",
                "source": "FINNHUB",
                "source_article_id": str(item.get("id") or item.get("datetime") or url),
                "title": title,
                "summary": summary,
                "url": url,
                "published_at": self._normalize_timestamp(item.get("datetime")),
                "company_name": symbol,
                "symbol": symbol,
                "language": "en",
                "raw_payload": {"provider": "FINNHUB", "query_text": query, **item},
                "content_hash": self._hash(f"{title}|{summary}|{url}"),
                "is_active": True,
                "fetched_at": datetime.now(timezone.utc).isoformat(),
            })

        if not articles:
            return None
        self._try_upsert_news(articles)
        return self._format_external_news("FINNHUB", query, articles[:limit])

    def _search_tavily(self, query: str, limit: int) -> dict[str, Any] | None:
        if not self.tavily_enabled:
            return None
        try:
            payload = self.tavily_client.search(query, max_results=limit)
        except TavilySearchError as exc:
            return {
                "reply": (
                    "최신 웹 검색을 사용할 수 없습니다.\n"
                    "현재 외부 검색 서비스 요청이 많거나 일시적으로 응답이 지연되고 있습니다.\n"
                    "잠시 후 또는 내일 다시 시도해 주세요."
                ),
                "data": {"source": "TAVILY", "enabled": False},
            }

        results = payload.get("results") or []
        if not results:
            return None

        summarized = []
        for item in results[:limit]:
            article = {
                "title": item.get("title") or "제목 없음",
                "summary": item.get("content") or payload.get("answer") or "",
                "url": item.get("url") or "",
                "source": "TAVILY",
                "company_name": query,
                "symbol": "",
                "market": "WEB",
                "raw_payload": {"query_category": "tavily_fallback"},
            }
            summary_payload = self.news_summary_service.summarize(article)
            summarized.append({**article, **summary_payload})

        lines = ["최신 웹 검색 결과를 요약했습니다."]
        for index, item in enumerate(summarized, start=1):
            lines.append(f"{index}. {item['title']}")
            lines.append(f"   {self._compact(item.get('ai_summary'), 260)}")
            if item.get("url"):
                lines.append(f"   {item['url']}")
        lines.append("출처: Tavily + OpenAI 요약")
        return {
            "reply": "\n".join(lines),
            "data": {"source": "TAVILY_FALLBACK", "query": query, "items": summarized},
        }

    def _format_external_news(self, source: str, query: str, articles: list[dict[str, Any]]) -> dict[str, Any]:
        lines = [f"{source} API로 새로 조회한 뉴스입니다."]
        for index, article in enumerate(articles, start=1):
            summary_payload = self.news_summary_service.summarize(article)
            article.update(summary_payload)
            lines.append(f"{index}. {article.get('title') or '제목 없음'}")
            lines.append(f"   {self._compact(article.get('ai_summary'), 260)}")
            if article.get("url"):
                lines.append(f"   {article['url']}")
        lines.append(f"출처: {source} API + OpenAI 요약")
        return {"reply": "\n".join(lines), "data": {"source": f"{source}_API", "query": query, "items": articles}}

    def _try_upsert_news(self, articles: list[dict[str, Any]]) -> None:
        try:
            self.news_repository.upsert_articles(articles)
        except Exception:
            return

    @staticmethod
    def _is_disclosure_query(query: str) -> bool:
        return any(keyword in query for keyword in ["공시", "사업보고서", "반기보고서", "분기보고서", "DART", "전자공시"])

    @staticmethod
    def _clean_html(value: Any) -> str:
        return html.unescape(re.sub(r"<[^>]+>", "", str(value or ""))).strip()

    @staticmethod
    def _compact(value: Any, limit: int) -> str:
        text = re.sub(r"\s+", " ", str(value or "")).strip()
        if len(text) <= limit:
            return text
        return text[: limit - 3].rstrip() + "..."

    @staticmethod
    def _hash(value: str) -> str:
        return hashlib.sha256(str(value or "").encode("utf-8")).hexdigest()

    @staticmethod
    def _extract_us_symbol(query: str) -> str:
        match = re.search(r"\b[A-Z]{1,5}\b", str(query or "").upper())
        return match.group(0) if match else ""

    @staticmethod
    def _parse_naver_date(value: Any) -> str:
        text = str(value or "").strip()
        if not text:
            return datetime.now(timezone.utc).isoformat()
        try:
            parsed = datetime.strptime(text, "%a, %d %b %Y %H:%M:%S %z")
            return parsed.astimezone(timezone.utc).isoformat()
        except ValueError:
            return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def _normalize_timestamp(value: Any) -> str:
        try:
            number = int(value)
            return datetime.fromtimestamp(number, tz=timezone.utc).isoformat()
        except (TypeError, ValueError):
            return datetime.now(timezone.utc).isoformat()
