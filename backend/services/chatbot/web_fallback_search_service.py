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
from backend.services.news_repository import NewsRepository
from backend.services.news_summary_service import NewsSummaryService
from backend.services.tavily_client import TavilyClient, TavilySearchError


class ChatbotWebFallbackSearchService:
    def __init__(self) -> None:
        self.rag_service = ChatbotRAGService()
        self.news_repository = NewsRepository()
        self.dart_repository = DartRepository()
        self.dart_analysis_service = DartDisclosureAnalysisService()
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
        is_disclosure_query = self._is_disclosure_query(text)
        if is_disclosure_query:
            max_results = min(max_results, 3)

        if self._is_freshness_query(text):
            if self._is_crypto_query(text) and not is_disclosure_query:
                tavily_result = self._search_tavily(text, max_results)
                if tavily_result:
                    return tavily_result

            api_result = self._search_existing_open_apis(text, max_results)
            if api_result:
                return api_result

            db_result = self._search_internal_db(text, max_results)
            if db_result:
                return db_result

            rag_result = self._search_rag(auth_header, user_id, text, max_results)
            if rag_result:
                return rag_result

            if is_disclosure_query:
                return {
                    "reply": "조건에 맞는 DART 공시 결과를 찾지 못했습니다.",
                    "data": {"source": "NO_RESULT", "query": text},
                }

            tavily_result = self._search_tavily(text, max_results)
            if tavily_result:
                return tavily_result

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
        search_query = self._normalize_disclosure_query(query)
        rows: list[dict[str, Any]] | None = None
        for attempt in range(2):
            try:
                rows = self.dart_repository.list_disclosures(query=search_query, limit=limit)
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

        visible_rows = rows[:limit]
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
            result_items.append({
                **row,
                "corp_name": corp_name,
                "report_nm": title,
                "analysis": self._normalize_disclosure_analysis(analysis),
            })
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
        lines.append("출처: Tavily + AI 요약")
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
        lines.append(f"출처: {source} API + AI 요약")
        return {"reply": "\n".join(lines), "data": {"source": f"{source}_API", "query": query, "items": articles}}

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
        if cached and self._normalize_disclosure_text(cached.get("plain_summary")):
            return cached

        analysis_service = getattr(self, "dart_analysis_service", None)
        if not analysis_service:
            analysis_service = DartDisclosureAnalysisService()
        try:
            result = analysis_service.ensure_analysis(rcept_no)
        except Exception:
            return None
        analysis = result.get("analysis") if isinstance(result, dict) else None
        return analysis if isinstance(analysis, dict) else None

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
    def _normalize_disclosure_query(query: str) -> str:
        text = re.sub(r"\s+", " ", str(query or "")).strip()
        keywords = [
            "\uacf5\uc2dc",
            "\ubcf4\uc5ec\uc918",
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
        text = re.sub(r"\s+", " ", text).strip()
        return text or str(query or "").strip()

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
