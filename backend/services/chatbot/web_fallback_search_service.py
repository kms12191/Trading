import hashlib
import html
import os
import re
from datetime import date, datetime, timedelta, timezone
from typing import Any
from urllib.parse import quote

import requests

from backend.services.chatbot.rag_service import ChatbotRAGService
from backend.services.dart_analysis_service import DartDisclosureAnalysisService
from backend.services.dart_ingest import DartIngestService
from backend.services.dart_repository import DartRepository
from backend.services.disclosure_knowledge_sync_service import DisclosureKnowledgeSyncService
from backend.services.embedding_service import EmbeddingService
from backend.services.knowledge_chunk_service import KnowledgeChunkService
from backend.services.news_repository import NewsRepository
from backend.services.news_summary_service import NewsSummaryService
from backend.services.tavily_client import TavilyClient, TavilySearchError


COMPANY_QUERY_ALIASES = {
    "삼전": "삼성전자",
    "삼성": "삼성전자",
    "심상전자": "삼성전자",
    "심성전자": "삼성전자",
    "삼상전자": "삼성전자",
    "하닉": "SK하이닉스",
    "하이닉스": "SK하이닉스",
    "이노스페이스": "이노스페이스 462350",
    "도지코인": "도지코인 DOGE",
    "도지": "도지코인 DOGE",
}


class ChatbotWebFallbackSearchService:
    def __init__(self) -> None:
        self.rag_service = ChatbotRAGService()
        self.news_repository = NewsRepository()
        self.dart_repository = DartRepository()
        self.dart_analysis_service = DartDisclosureAnalysisService()
        self.disclosure_knowledge_sync_service = DisclosureKnowledgeSyncService(
            KnowledgeChunkService(),
            EmbeddingService(),
        )
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
        if self._is_combined_news_disclosure_query(text):
            requested_count = self._requested_news_count(text) or self._requested_disclosure_count(text)
            if requested_count and requested_count > 3:
                return self._news_limit_exceeded_reply(text, requested_count)
            max_results = requested_count or 1
            return self._search_combined_news_disclosure(auth_header, user_id, text, max_results)

        is_disclosure_query = self._is_disclosure_query(text)
        is_news_query = self._is_news_query(text) and not is_disclosure_query
        if is_disclosure_query:
            requested_count = self._requested_disclosure_count(text)
            if requested_count and requested_count > 3:
                return self._disclosure_limit_exceeded_reply(text, requested_count)
            max_results = requested_count or 1
            unsupported_company = self._unsupported_dart_company_name(text)
            if unsupported_company:
                return self._unsupported_disclosure_market_reply(text, unsupported_company)
            if self._is_missing_disclosure_target(text):
                return self._disclosure_target_required_reply(text)
        elif is_news_query:
            requested_count = self._requested_news_count(text)
            if requested_count and requested_count > 3:
                return self._news_limit_exceeded_reply(text, requested_count)
            max_results = requested_count or 1

        if self._is_freshness_query(text) or is_news_query:
            if self._is_crypto_query(text) and not is_disclosure_query:
                tavily_result = self._search_tavily(text, max_results)
                if tavily_result:
                    return tavily_result

            api_result = self._search_existing_open_apis(text, max_results)
            if api_result:
                return api_result

            if is_news_query:
                tavily_result = self._search_tavily(text, max_results)
                if tavily_result:
                    return tavily_result

            db_result = self._search_internal_db(text, max_results)
            if db_result:
                return db_result

            if not is_news_query:
                rag_result = self._search_rag(auth_header, user_id, text, max_results)
                if rag_result:
                    return rag_result

            if is_disclosure_query:
                return {
                    "reply": "조건에 맞는 DART 공시 결과를 찾지 못했습니다.",
                    "data": {"source": "NO_RESULT", "query": text},
                }

            if not is_news_query:
                tavily_result = self._search_tavily(text, max_results)
                if tavily_result:
                    return tavily_result

            if is_news_query:
                return {
                    "reply": "조건에 맞는 뉴스 결과를 찾지 못했습니다.",
                    "data": {"source": "NO_RESULT", "query": text},
                }

            return {
                "reply": "조건에 맞는 뉴스/공시/웹 검색 결과를 찾지 못했습니다.",
                "data": {"source": "NO_RESULT", "query": text},
            }

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

        disclosure_rows = [
            row
            for row in rows[:limit]
            if str(row.get("source_type") or "").upper() == "DISCLOSURE"
        ]
        if disclosure_rows and self._is_disclosure_query(query):
            result_items: list[dict[str, Any]] = []
            for row in disclosure_rows:
                rcept_no = str(row.get("source_id") or "").strip()
                if not rcept_no:
                    continue
                try:
                    disclosure = self.dart_repository.get_disclosure_by_rcept_no(rcept_no)
                except (requests.HTTPError, requests.ConnectionError, requests.Timeout, TypeError, ValueError):
                    disclosure = None
                if not disclosure:
                    continue

                title = self._normalize_disclosure_text(disclosure.get("report_nm")) or "공시 제목 없음"
                corp_name = self._normalize_disclosure_text(disclosure.get("corp_name")) or "-"
                analysis = self._load_disclosure_analysis(disclosure)
                normalized_analysis = self._normalize_disclosure_analysis(analysis)
                result_item = {
                    **disclosure,
                    "corp_name": corp_name,
                    "report_nm": title,
                    "analysis": normalized_analysis,
                }
                knowledge_index = self._sync_disclosure_knowledge_index(disclosure, normalized_analysis)
                if knowledge_index:
                    result_item["knowledge_index"] = knowledge_index
                result_items.append(result_item)

            if result_items:
                lines = [f"DART 공시 {len(result_items)}건을 요약했습니다."]
                for index, item in enumerate(result_items, start=1):
                    if index > 1:
                        lines.append("")
                    lines.append(f"{index}. {item['corp_name']} / {item['report_nm']}")
                    for summary_line in self._disclosure_summary_lines(item, analysis=item.get("analysis")):
                        lines.append(f"   {summary_line}")
                    url = item.get("url") or ""
                    if url:
                        lines.append(f"   {url}")
                lines.append("")
                lines.append("출처: 저장된 DART 공시 DB")
                source_url = self._dart_source_url(self._normalize_disclosure_query(query))
                return {
                    "reply": "\n".join(lines),
                    "data": {
                        "source": "DISCLOSURE_DB",
                        "items": result_items,
                        "source_url": source_url,
                        "fallback_source": "VECTOR_DB",
                    },
                }

            lines = [f"저장된 DART 공시 요약 {len(disclosure_rows)}건입니다."]
            for index, row in enumerate(disclosure_rows, start=1):
                chunk_text = self._compact(row.get("chunk_text"), 320)
                if not chunk_text:
                    continue
                source_id = str(row.get("source_id") or "").strip()
                lines.append(f"{index}. {chunk_text}")
                if source_id:
                    lines.append(f"   접수번호: {source_id}")

            if len(lines) == 1:
                return None
            lines.append("")
            lines.append("출처: Vector DB 공시 요약")
            return {
                "reply": "\n".join(lines),
                "data": {"source": "VECTOR_DB", "items": disclosure_rows},
            }

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
        if self._is_disclosure_query(query):
            result = self._search_disclosure_db(query, limit)
            return result if result else None

        ordered_sources = ["NEWS", "DISCLOSURE"]
        for source in ordered_sources:
            if source == "NEWS":
                result = self._search_news_db(query, limit)
            else:
                result = self._search_disclosure_db(query, limit)
            if result:
                return result
        return None

    def _search_combined_news_disclosure(
        self,
        auth_header: str | None,
        user_id: str | None,
        query: str,
        limit: int,
    ) -> dict[str, Any]:
        news_query = self._combined_query_for(query, "뉴스")
        disclosure_query = self._combined_query_for(query, "공시")

        news_result = self._search_existing_open_apis(news_query, limit)
        if not news_result:
            news_result = self._search_tavily(news_query, limit)
        if not news_result:
            news_result = self._search_internal_db(news_query, limit)
        if not news_result:
            news_result = self._search_rag(auth_header, user_id, news_query, limit)

        disclosure_result = self._search_existing_open_apis(disclosure_query, limit)
        if not disclosure_result:
            disclosure_result = self._search_internal_db(disclosure_query, limit)
        if not disclosure_result:
            disclosure_result = self._search_rag(auth_header, user_id, disclosure_query, limit)

        lines = ["뉴스와 공시를 나눠서 확인했습니다."]
        if news_result:
            lines.extend(["", "[뉴스]", str(news_result.get("reply") or "").strip()])
        else:
            lines.extend(["", "[뉴스]", "조건에 맞는 최신 뉴스를 찾지 못했습니다."])

        if disclosure_result:
            lines.extend(["", "[공시]", str(disclosure_result.get("reply") or "").strip()])
        else:
            lines.extend(["", "[공시]", "조건에 맞는 DART 공시 결과를 찾지 못했습니다."])

        return {
            "reply": "\n".join(line for line in lines if line is not None),
            "data": {
                "source": "NEWS_DISCLOSURE_COMBINED",
                "query": query,
                "news_query": news_query,
                "disclosure_query": disclosure_query,
                "news": news_result.get("data") if news_result else {"source": "NO_RESULT"},
                "disclosure": disclosure_result.get("data") if disclosure_result else {"source": "NO_RESULT"},
            },
        }

    @staticmethod
    def _combined_query_for(query: str, target: str) -> str:
        text = re.sub(r"\s+", " ", str(query or "")).strip()
        if target == "뉴스":
            text = re.sub(r"(?:공시와|공시랑|공시 및|공시와\s*뉴스|뉴스와\s*공시|공시)", " ", text)
        else:
            text = re.sub(r"(?:뉴스와|뉴스랑|뉴스 및|공시와\s*뉴스|뉴스와\s*공시|뉴스)", " ", text)
        text = re.sub(r"(?:보고|정리해줘|정리|요약해줘|요약|알려줘|보여줘)", " ", text)
        text = re.sub(r"\s+", " ", text).strip()
        text = ChatbotWebFallbackSearchService._normalize_company_query(text)
        if target not in text:
            text = f"{text} {target}".strip()
        return text

    def _search_news_db(self, query: str, limit: int) -> dict[str, Any] | None:
        search_query = self._normalize_news_query(query)
        try:
            rows = self.news_repository.list_articles(query=search_query, limit=max(limit * 3, limit))
        except Exception:
            return None
        if not rows:
            return None

        visible_rows = self._filter_company_news_rows(search_query, rows)[:limit]
        if not visible_rows:
            return None

        lines = [f"뉴스 {len(visible_rows)}건을 요약했습니다."]
        for index, row in enumerate(visible_rows, start=1):
            if index > 1:
                lines.append("")
            article = dict(row)
            if not article.get("ai_summary"):
                article.update(self.news_summary_service.summarize(article))
            visible_rows[index - 1] = article
            title = article.get("title") or "제목 없음"
            summary = article.get("ai_summary") or article.get("summary") or ""
            url = article.get("url") or ""
            lines.append(f"{index}. {title}")
            if summary:
                lines.append(f"   {self._compact(summary, 260)}")
            if url:
                lines.append(f"   {url}")
        lines.append("")
        lines.append("출처: news_articles DB")
        return {"reply": "\n".join(lines), "data": {"source": "NEWS_DB", "items": visible_rows}}

    def _search_disclosure_db(self, query: str, limit: int) -> dict[str, Any] | None:
        search_query = self._normalize_disclosure_query(query)
        rows: list[dict[str, Any]] | None = None
        for attempt in range(2):
            try:
                rows = self.dart_repository.list_disclosures(query=search_query, limit=max(limit * 3, limit))
                break
            except requests.HTTPError as error:
                status_code = error.response.status_code if error.response is not None else 0
                if attempt == 0 and status_code >= 500:
                    continue
                return None
            except (requests.ConnectionError, requests.Timeout):
                if attempt == 0:
                    continue
                return None
            except (TypeError, ValueError):
                return None
        if not rows:
            return None

        visible_rows = self._filter_company_disclosure_rows(search_query, rows)[:limit]
        if not visible_rows:
            return None

        lines = [f"DART 공시 {len(visible_rows)}건을 요약했습니다."]
        result_items: list[dict[str, Any]] = []
        for index, row in enumerate(visible_rows, start=1):
            if index > 1:
                lines.append("")
            title = self._normalize_disclosure_text(row.get("report_nm")) or "공시 제목 없음"
            corp_name = self._normalize_disclosure_text(row.get("corp_name")) or "-"
            url = row.get("url") or ""
            analysis = self._load_disclosure_analysis(row)
            lines.append(f"{index}. {corp_name} / {title}")
            for summary_line in self._disclosure_summary_lines(row, analysis=analysis):
                lines.append(f"   {summary_line}")
            if url:
                lines.append(f"   {url}")
            normalized_analysis = self._normalize_disclosure_analysis(analysis)
            result_item = {
                **row,
                "corp_name": corp_name,
                "report_nm": title,
                "analysis": normalized_analysis,
            }
            knowledge_index = self._sync_disclosure_knowledge_index(row, normalized_analysis)
            if knowledge_index:
                result_item["knowledge_index"] = knowledge_index
            result_items.append(result_item)
        lines.append("")
        lines.append("출처: DART 전자공시시스템")
        source_url = self._dart_source_url(search_query)
        lines.append(source_url)
        return {
            "reply": "\n".join(lines),
            "data": {
                "source": "DISCLOSURE_DB",
                "items": result_items,
                "source_url": source_url,
            },
        }

    def _search_existing_open_apis(self, query: str, limit: int) -> dict[str, Any] | None:
        if self._is_disclosure_query(query):
            disclosure_result = self._sync_and_search_dart(query, limit)
            if disclosure_result:
                return disclosure_result
            return None

        news_result = self._search_naver_news(query, limit)
        if news_result:
            return news_result

        finnhub_result = self._search_finnhub_news(query, limit)
        if finnhub_result:
            return finnhub_result

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
        search_query = self._normalize_news_query(query)
        try:
            response = requests.get(
                "https://openapi.naver.com/v1/search/news.json",
                headers={
                    "X-Naver-Client-Id": self.naver_client_id,
                    "X-Naver-Client-Secret": self.naver_client_secret,
                },
                params={"query": search_query, "display": min(limit, 10), "sort": "date"},
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
            article = {
                "market": "DOMESTIC",
                "source": "NAVER",
                "source_article_id": url or f"naver:{self._hash(title + query)}",
                "title": title,
                "summary": summary,
                "url": url,
                "published_at": self._parse_naver_date(item.get("pubDate")),
                "company_name": "",
                "symbol": "",
                "language": "ko",
                "raw_payload": {"provider": "NAVER", "query_text": search_query, **item},
                "content_hash": self._hash(f"{title}|{summary}|{url}"),
                "is_active": True,
                "fetched_at": datetime.now(timezone.utc).isoformat(),
            }
            if self._is_relevant_company_news(search_query, article):
                article["company_name"] = search_query
                articles.append(article)

        if not articles:
            return None
        self._try_upsert_news(articles)
        return self._format_external_news("NAVER", search_query, articles[:limit])

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
        search_query = self._normalize_news_query(query) if self._is_news_query(query) else query
        try:
            payload = self.tavily_client.search(search_query, max_results=limit)
        except TavilySearchError as exc:
            return {
                "reply": (
                    "최신 웹 검색을 사용할 수 없습니다.\n"
                    "현재 외부 검색 서비스 요청이 많거나 일시적으로 응답이 지연되고 있습니다.\n"
                    "잠시 후 또는 내일 다시 시도해 주세요."
                ),
                "data": {"source": "TAVILY", "enabled": False},
            }

        results = self._filter_tavily_results(query, payload.get("results") or [])
        if not results:
            return None

        summarized = []
        for item in results[:limit]:
            article = {
                "title": item.get("title") or "제목 없음",
                "summary": item.get("content") or payload.get("answer") or "",
                "url": item.get("url") or "",
                "source": "TAVILY",
                "company_name": search_query,
                "symbol": "",
                "market": "WEB",
                "raw_payload": {"query_category": "tavily_fallback"},
            }
            summary_payload = self.news_summary_service.summarize(article)
            summarized.append({**article, **summary_payload})

        lines = ["최신 웹 검색 결과를 요약했습니다."]
        for index, item in enumerate(summarized, start=1):
            if index > 1:
                lines.append("")
            lines.append(f"{index}. {item['title']}")
            lines.append(f"   {self._compact(item.get('ai_summary'), 260)}")
            if item.get("url"):
                lines.append(f"   {item['url']}")
        lines.append("")
        lines.append(f"조회 기준: Tavily 웹검색, 검색어 '{search_query}', 뉴스형 결과 우선, 위키/나무위키/지식인 제외")
        lines.append("출처: Tavily + AI 요약")
        return {
            "reply": "\n".join(lines),
            "data": {
                "source": "TAVILY_FALLBACK",
                "query": search_query,
                "items": summarized,
                "criteria": {
                    "provider": "TAVILY",
                    "query": search_query,
                    "sort": "relevance",
                    "limit": len(summarized),
                    "excluded_sources": ["wikipedia.org", "namu.wiki", "kin.naver.com", "지식인"],
                },
            },
        }

    def _format_external_news(self, source: str, query: str, articles: list[dict[str, Any]]) -> dict[str, Any]:
        lines = [f"{source} API로 새로 조회한 뉴스 {len(articles)}건을 요약했습니다."]
        for index, article in enumerate(articles, start=1):
            summary_payload = self.news_summary_service.summarize(article)
            article.update(summary_payload)
            if index > 1:
                lines.append("")
            lines.append(f"{index}. {article.get('title') or '제목 없음'}")
            lines.append(f"   {self._compact(article.get('ai_summary'), 260)}")
            if article.get("url"):
                lines.append(f"   {article['url']}")
        lines.append("")
        lines.append(f"조회 기준: {source} 뉴스 API, 검색어 '{query}', 최신순(date), 최대 {len(articles)}건")
        lines.append(f"출처: {source} API + AI 요약")
        return {
            "reply": "\n".join(lines),
            "data": {
                "source": f"{source}_API",
                "query": query,
                "items": articles,
                "criteria": {
                    "provider": source,
                    "query": query,
                    "sort": "date",
                    "limit": len(articles),
                    "fallback_order": ["NAVER_API", "FINNHUB_API", "TAVILY", "NEWS_DB", "VECTOR_DB"],
                },
            },
        }

    def _try_upsert_news(self, articles: list[dict[str, Any]]) -> None:
        try:
            self.news_repository.upsert_articles(articles)
        except Exception:
            return

    def _disclosure_summary_lines(
        self,
        row: dict[str, Any],
        analysis: dict[str, Any] | None = None,
    ) -> list[str]:
        if analysis:
            return self._format_disclosure_analysis_lines(analysis)

        summary = self._compact(row.get("summary"), 220)
        title = str(row.get("report_nm") or "").strip()
        corp_name = str(row.get("corp_name") or "").strip()
        if summary and not self._is_listing_summary(summary, title, corp_name):
            return [f"요약: {summary}"]
        return [f"요약: {self._fallback_disclosure_summary(title)}"]

    def _load_disclosure_analysis(self, row: dict[str, Any]) -> dict[str, Any] | None:
        rcept_no = str(row.get("rcept_no") or "").strip()
        if not rcept_no:
            return None

        try:
            cached = self.dart_repository.get_disclosure_analysis(rcept_no)
        except Exception:
            cached = None
        if cached and self._is_complete_disclosure_analysis(cached):
            return cached

        analysis_service = getattr(self, "dart_analysis_service", None)
        if not analysis_service:
            analysis_service = DartDisclosureAnalysisService()
        try:
            result = analysis_service.ensure_analysis(rcept_no, force_refresh=bool(cached))
        except Exception:
            return None
        analysis = result.get("analysis") if isinstance(result, dict) else None
        return analysis if isinstance(analysis, dict) else None

    def _sync_disclosure_knowledge_index(
        self,
        row: dict[str, Any],
        analysis: dict[str, Any] | None,
    ) -> dict[str, Any] | None:
        index_analysis = analysis or self._fallback_disclosure_index_analysis(row)
        rcept_no = str(row.get("rcept_no") or index_analysis.get("rcept_no") or "").strip()
        if not rcept_no:
            return None

        sync_service = getattr(self, "disclosure_knowledge_sync_service", None)
        if not sync_service:
            return None

        index_analysis = {**index_analysis, "rcept_no": str(index_analysis.get("rcept_no") or rcept_no)}
        try:
            result = sync_service.sync_analysis(analysis=index_analysis, disclosure=row)
        except (requests.HTTPError, requests.ConnectionError, requests.Timeout, RuntimeError, OSError, TypeError, ValueError):
            return {"status": "FAILED", "chunk_count": 0}
        return result if isinstance(result, dict) else None

    def _fallback_disclosure_index_analysis(self, row: dict[str, Any]) -> dict[str, Any]:
        title = self._normalize_disclosure_text(row.get("report_nm"))
        corp_name = self._normalize_disclosure_text(row.get("corp_name"))
        summary = self._compact(row.get("summary"), 360)
        if not summary or self._is_listing_summary(summary, title, corp_name):
            summary = self._fallback_disclosure_summary(title)
        return {
            "rcept_no": str(row.get("rcept_no") or "").strip(),
            "category": "공시",
            "sentiment_label": "정보",
            "sentiment_message": "저장된 공시 DB 요약을 기반으로 색인했습니다.",
            "headline": title,
            "plain_summary": summary,
            "key_points": [],
            "risk_points": [],
            "check_items": [{"question": "원문 확인", "answer": "세부 조건은 DART 원문에서 확인"}],
            "metrics": [],
            "analysis_source": "DISCLOSURE_DB",
            "confidence": "low",
        }

    def _is_complete_disclosure_analysis(self, analysis: dict[str, Any]) -> bool:
        plain_summary = self._normalize_disclosure_text(analysis.get("plain_summary"))
        if not plain_summary:
            return False

        analysis_source = self._normalize_disclosure_text(analysis.get("analysis_source")).upper()
        if analysis_source == "TITLE_ONLY":
            return False

        title_only_markers = (
            "상세 내용을 아직 확인하지 못해",
            "제목 기준",
            "제목 기반",
            "공시 제목 기준",
            "저장된 분석 요약이 없어",
        )
        return not any(marker in plain_summary for marker in title_only_markers)

    def _format_disclosure_analysis_lines(self, analysis: dict[str, Any]) -> list[str]:
        lines: list[str] = []
        headline = self._normalize_disclosure_text(analysis.get("headline"))
        plain_summary = self._normalize_disclosure_text(analysis.get("plain_summary"))
        if plain_summary:
            lines.append(f"요약: {plain_summary}")
        elif headline:
            lines.append(f"핵심: {headline}")

        metric_line = self._first_label_value_line(analysis.get("metrics"))
        if metric_line:
            lines.append(f"지표: {metric_line}")

        check_line = self._first_question_answer_line(analysis.get("check_items"))
        if check_line:
            lines.append(f"확인: {check_line}")

        risk_line = self._first_text_line(analysis.get("risk_points"))
        if risk_line:
            lines.append(f"리스크: {risk_line}")

        return lines or ["요약: 저장된 분석 요약이 없어 공시 제목 기준으로 표시합니다."]

    def _first_label_value_line(self, items: Any) -> str:
        if not isinstance(items, list):
            return ""
        for item in items:
            if not isinstance(item, dict):
                continue
            label = self._normalize_disclosure_text(item.get("label"))
            value = self._normalize_disclosure_text(item.get("value"))
            if label and value:
                return f"{label} · {value}"
        return ""

    def _first_question_answer_line(self, items: Any) -> str:
        if not isinstance(items, list):
            return ""
        for item in items:
            if not isinstance(item, dict):
                continue
            question = self._normalize_disclosure_text(item.get("question"))
            answer = self._normalize_disclosure_text(item.get("answer"))
            if question and answer:
                return f"{question} · {answer}"
        return ""

    def _first_text_line(self, items: Any) -> str:
        if not isinstance(items, list):
            return ""
        for item in items:
            text = self._normalize_disclosure_text(item)
            if text:
                return text
        return ""

    def _normalize_disclosure_analysis(self, analysis: dict[str, Any] | None) -> dict[str, Any] | None:
        if not analysis:
            return None

        normalized = dict(analysis)
        for field in ("headline", "plain_summary", "sentiment_label", "confidence", "analysis_source"):
            normalized[field] = self._normalize_disclosure_text(analysis.get(field))

        for field in ("metrics", "check_items", "risk_points"):
            value = analysis.get(field)
            normalized[field] = value if isinstance(value, list) else []
        return normalized

    @staticmethod
    def _normalize_disclosure_text(value: Any) -> str:
        text = re.sub(r"\s+", " ", str(value or "")).strip()
        return re.sub(r"공시\s+공시(?=(?:로|를|가|는|의|에|입니다|$))", "공시", text)

    @staticmethod
    def _is_listing_summary(summary: str, title: str, corp_name: str) -> bool:
        normalized_summary = re.sub(r"\s+", "", summary)
        normalized_title = re.sub(r"\s+", "", title)
        normalized_corp = re.sub(r"\s+", "", corp_name)
        return bool(
            normalized_summary
            and normalized_title
            and normalized_title in normalized_summary
            and (not normalized_corp or normalized_corp in normalized_summary)
        )

    @staticmethod
    def _fallback_disclosure_summary(title: str) -> str:
        if not title:
            return "저장된 분석 요약이 없어 공시 제목 기준으로 표시합니다."
        return f"{title} 관련 공시입니다. 세부 조건, 금액, 일정은 원문에서 확인하세요."

    @staticmethod
    def _dart_source_url(query: str) -> str:
        encoded_query = quote(str(query or "").strip())
        if not encoded_query:
            return "https://dart.fss.or.kr/dsab007/main.do"
        return f"https://dart.fss.or.kr/dsab007/main.do?option=corp&textCrpNm={encoded_query}"

    @staticmethod
    def _normalize_company_query(query: str) -> str:
        text = re.sub(r"\s+", " ", str(query or "")).strip()
        compact = re.sub(r"\s+", "", text)
        for alias, company_name in COMPANY_QUERY_ALIASES.items():
            if alias in text or alias in compact:
                return company_name
        return text

    @classmethod
    def _is_broad_news_query(cls, query: str) -> bool:
        return cls._normalize_company_query(query) in {
            "시장",
            "주요",
            "시장 주요",
            "국내 시장",
            "증시 주요",
            "국내 증시 시장 주요 뉴스",
        }

    @classmethod
    def _filter_company_news_rows(cls, query: str, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if cls._is_broad_news_query(query):
            return rows
        return [row for row in rows if cls._is_relevant_company_news(query, row)]

    @classmethod
    def _filter_company_disclosure_rows(cls, query: str, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        target = cls._normalize_company_query(query)
        target_key = re.sub(r"\s+", "", target).upper()
        if not target_key:
            return rows
        target_tokens = [
            token.upper()
            for token in re.split(r"\s+", target)
            if len(token.strip()) >= 2
        ]
        filtered_rows = []
        for row in rows:
            corp_key = re.sub(r"\s+", "", str(row.get("corp_name") or "")).upper()
            stock_code = re.sub(r"\s+", "", str(row.get("stock_code") or "")).upper()
            if target_key in corp_key or target_key == stock_code:
                filtered_rows.append(row)
                continue
            if any(token in corp_key or token == stock_code for token in target_tokens):
                filtered_rows.append(row)
        return filtered_rows

    @classmethod
    def _is_relevant_company_news(cls, query: str, article: dict[str, Any]) -> bool:
        if cls._is_broad_news_query(query):
            return True
        target = cls._normalize_company_query(query)
        target_key = re.sub(r"\s+", "", target).upper()
        if not target_key:
            return True
        haystack = " ".join(
            str(article.get(field) or "")
            for field in ("title", "summary", "company_name", "symbol")
        )
        haystack_key = re.sub(r"\s+", "", haystack).upper()
        if target_key in haystack_key:
            return True
        target_tokens = [
            token.upper()
            for token in re.split(r"\s+", target)
            if len(token.strip()) >= 2
        ]
        return any(token in haystack_key for token in target_tokens)

    @staticmethod
    def _normalize_disclosure_query(query: str) -> str:
        text = re.sub(r"\s+", " ", str(query or "")).strip()
        keywords = [
            "\uacf5\uc2dc",
            "\ubcf4\uc5ec\uc918",
            "조회",
            "검색",
            "확인",
            "\ucc3e\uc544\uc918",
            "\uc54c\ub824\uc918",
            "\uc694\uc57d",
            "\ucd5c\uc2e0",
            "\ucd5c\uadfc",
            "\uc624\ub298",
            "\uc774\ubc88 \uc8fc",
            "DART",
        ]
        for keyword in keywords:
            text = text.replace(keyword, " ")
        text = re.sub(r"\d+\s*(?:개|건)", " ", text)
        text = re.sub(r"\s+", " ", text).strip()
        return ChatbotWebFallbackSearchService._normalize_company_query(text or str(query or "").strip())

    @staticmethod
    def _requested_disclosure_count(query: str) -> int | None:
        match = re.search(r"(\d+)\s*(?:개|건)", str(query or ""))
        if not match:
            return None
        return max(1, min(int(match.group(1)), 10))

    @staticmethod
    def _requested_news_count(query: str) -> int | None:
        match = re.search(r"(\d+)\s*(?:개|건)", str(query or ""))
        if not match:
            return None
        return max(1, min(int(match.group(1)), 10))

    @classmethod
    def _is_combined_news_disclosure_query(cls, query: str) -> bool:
        return cls._is_news_query(query) and cls._is_disclosure_query(query)

    @classmethod
    def _is_missing_disclosure_target(cls, query: str) -> bool:
        subject = cls._extract_disclosure_subject(query)
        if not subject:
            return True
        generic_terms = {
            "목록",
            "리스트",
            "전체",
            "시장",
            "주식",
            "종목",
            "기업",
            "회사",
            "상장사",
            "국내",
            "한국",
        }
        tokens = {token for token in re.split(r"\s+", subject) if token}
        return bool(tokens) and tokens.issubset(generic_terms)

    @staticmethod
    def _extract_disclosure_subject(query: str) -> str:
        text = re.sub(r"\s+", " ", str(query or "")).strip()
        keywords = [
            "공시",
            "사업보고서",
            "반기보고서",
            "분기보고서",
            "전자공시",
            "보여줘",
            "조회",
            "검색",
            "확인",
            "찾아줘",
            "알려줘",
            "요약",
            "분석",
            "최신",
            "최근",
            "오늘",
            "이번 주",
            "목록",
            "리스트",
            "DART",
        ]
        for keyword in keywords:
            text = text.replace(keyword, " ")
        text = re.sub(r"\d+\s*(?:개|건)", " ", text)
        return ChatbotWebFallbackSearchService._normalize_company_query(re.sub(r"\s+", " ", text).strip())

    @staticmethod
    def _unsupported_dart_company_name(query: str) -> str:
        normalized = str(query or "").upper()
        unsupported_aliases = {
            "아마존": "아마존",
            "AMAZON": "아마존",
            "AMZN": "아마존",
            "애플": "애플",
            "APPLE": "애플",
            "AAPL": "애플",
            "테슬라": "테슬라",
            "TESLA": "테슬라",
            "TSLA": "테슬라",
            "마이크로소프트": "마이크로소프트",
            "MICROSOFT": "마이크로소프트",
            "MSFT": "마이크로소프트",
            "구글": "구글",
            "알파벳": "알파벳",
            "GOOGLE": "구글",
            "ALPHABET": "알파벳",
            "GOOGL": "알파벳",
            "GOOG": "알파벳",
            "엔비디아": "엔비디아",
            "NVIDIA": "엔비디아",
            "NVDA": "엔비디아",
            "메타": "메타",
            "META": "메타",
        }
        for alias, company_name in unsupported_aliases.items():
            if alias in normalized:
                return company_name
        return ""

    @staticmethod
    def _disclosure_target_required_reply(query: str) -> dict[str, Any]:
        return {
            "reply": (
                "어떤 종목의 공시를 볼까요? "
                "예: '삼성전자 최근 공시 보여줘' 또는 '하이닉스 최근 공시 3개 보여줘'처럼 종목명을 함께 알려주세요."
            ),
            "data": {
                "source": "DISCLOSURE_SYMBOL_REQUIRED",
                "query": query,
                "max_results": 3,
            },
        }

    @staticmethod
    def _unsupported_disclosure_market_reply(query: str, company_name: str) -> dict[str, Any]:
        return {
            "reply": (
                f"{company_name}은 DART 공시 대상이 아닙니다. "
                "DART는 국내 상장사 전자공시 조회에 사용되며, 해외 기업은 뉴스나 SEC 공시 기준으로 확인해야 합니다."
            ),
            "data": {
                "source": "DISCLOSURE_UNSUPPORTED_MARKET",
                "query": query,
                "company_name": company_name,
            },
        }

    @staticmethod
    def _disclosure_limit_exceeded_reply(query: str, requested_count: int) -> dict[str, Any]:
        return {
            "reply": "최근 공시는 최대 3개까지 조회 가능합니다. 1개, 2개, 3개 중 하나로 다시 요청해 주세요.",
            "data": {
                "source": "DISCLOSURE_LIMIT_EXCEEDED",
                "query": query,
                "requested_count": requested_count,
                "max_results": 3,
            },
        }

    @staticmethod
    def _news_limit_exceeded_reply(query: str, requested_count: int) -> dict[str, Any]:
        return {
            "reply": "최근 뉴스는 최대 3개까지 조회 가능합니다. 1개, 2개, 3개 중 하나로 다시 요청해 주세요.",
            "data": {
                "source": "NEWS_LIMIT_EXCEEDED",
                "query": query,
                "requested_count": requested_count,
                "max_results": 3,
            },
        }

    @staticmethod
    def _normalize_news_query(query: str) -> str:
        text = re.sub(r"\s+", " ", str(query or "")).strip()
        keywords = [
            "뉴스",
            "기사",
            "속보",
            "보여줘",
            "찾아줘",
            "알려줘",
            "해줘",
            "요약",
            "최신",
            "최근",
            "오늘",
            "이번 주",
            "관련된",
            "관련해서",
            "관련",
        ]
        for keyword in keywords:
            text = text.replace(keyword, " ")
        text = re.sub(r"\d+\s*(?:개|건)", " ", text)
        text = re.sub(r"\s+", " ", text).strip()
        if text in {"시장", "주요", "시장 주요", "국내 시장", "증시 주요"}:
            return "국내 증시 시장 주요 뉴스"
        return ChatbotWebFallbackSearchService._normalize_company_query(text or str(query or "").strip())

    @staticmethod
    def _is_news_query(query: str) -> bool:
        keywords = [
            "뉴스",
            "기사",
            "속보",
        ]
        return any(keyword in query for keyword in keywords)

    @staticmethod
    def _is_disclosure_query(query: str) -> bool:
        keywords = [
            "\uacf5\uc2dc",
            "\uc0ac\uc5c5\ubcf4\uace0\uc11c",
            "\ubc18\uae30\ubcf4\uace0\uc11c",
            "\ubd84\uae30\ubcf4\uace0\uc11c",
            "\uc804\uc790\uacf5\uc2dc",
            "DART",
        ]
        return any(keyword in query for keyword in keywords)

    @staticmethod
    def _is_freshness_query(query: str) -> bool:
        keywords = [
            "\ucd5c\uc2e0",
            "\ucd5c\uadfc",
            "\uc624\ub298",
            "\uc774\ubc88 \uc8fc",
            "\ubc29\uae08",
            "\uc18d\ubcf4",
            "\ub274\uc2a4",
            "\uc694\uc57d",
            "\uacf5\uc2dc",
        ]
        return any(keyword in query for keyword in keywords)

    @staticmethod
    def _is_crypto_query(query: str) -> bool:
        normalized = str(query or "").upper()
        keywords = [
            "\ucf54\uc778",
            "\uac00\uc0c1\uc790\uc0b0",
            "\ube44\ud2b8\ucf54\uc778",
            "\uc774\ub354\ub9ac\uc6c0",
            "BTC",
            "ETH",
            "USDT",
        ]
        return any(keyword in normalized for keyword in keywords)

    @classmethod
    def _filter_tavily_results(cls, query: str, results: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if not results:
            return []
        if not cls._is_news_query(query):
            return results
        return [item for item in results if not cls._is_low_quality_news_source(item)]

    @staticmethod
    def _is_low_quality_news_source(item: dict[str, Any]) -> bool:
        url = str(item.get("url") or "").lower()
        title = str(item.get("title") or "").lower()
        blocked_markers = (
            "wikipedia.org",
            "namu.wiki",
            "namu.moe",
            "wikidocs.net",
            "kin.naver.com",
            "wiki/",
            "위키백과",
            "나무위키",
            "지식in",
            "지식인",
        )
        combined = f"{url} {title}"
        return any(marker in combined for marker in blocked_markers)

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
