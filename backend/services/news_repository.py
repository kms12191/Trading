import os
from datetime import datetime
from typing import Any

import requests


class NewsRepository:
    def __init__(self) -> None:
        self.supabase_url = os.getenv("SUPABASE_URL", "").rstrip("/")
        self.supabase_service_role_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
        self.supabase_anon_key = os.getenv("SUPABASE_ANON_KEY", "")

    @property
    def is_configured(self) -> bool:
        return bool(self.supabase_url and self.supabase_service_role_key)

    def list_articles(
        self,
        market: str = "ALL",
        query: str = "",
        limit: int = 10,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        if not self.supabase_url or not self.supabase_anon_key:
            return []

        params: dict[str, str] = {
            "select": "id,market,source,source_article_id,title,summary,url,published_at,fetched_at,company_name,symbol,language,sentiment,content_hash,is_active,raw_payload,ai_summary,ai_summary_model,ai_summary_generated_at,ai_summary_prompt_version",
            "order": "published_at.desc",
            "limit": str(limit),
            "offset": str(offset),
            "is_active": "eq.true",
        }
        if market and market.upper() != "ALL":
            params["market"] = f"eq.{market.upper()}"

        if query:
            q = query.strip()
            or_clauses = [
                f"title.ilike.*{q}*",
                f"summary.ilike.*{q}*",
                f"company_name.ilike.*{q}*",
                f"symbol.ilike.*{q}*",
            ]
            params["or"] = f"({','.join(or_clauses)})"

        response = requests.get(
            f"{self.supabase_url}/rest/v1/news_articles",
            headers=self._read_headers(),
            params=params,
            timeout=15,
        )
        response.raise_for_status()
        return response.json()

    def count_articles(self, market: str = "ALL", query: str = "") -> int:
        if not self.supabase_url or not self.supabase_anon_key:
            return 0

        params: dict[str, str] = {
            "select": "id",
            "is_active": "eq.true",
        }

        if market and market.upper() != "ALL":
            params["market"] = f"eq.{market.upper()}"

        if query:
            q = query.strip()
            or_clauses = [
                f"title.ilike.*{q}*",
                f"summary.ilike.*{q}*",
                f"company_name.ilike.*{q}*",
                f"symbol.ilike.*{q}*",
            ]
            params["or"] = f"({','.join(or_clauses)})"

        headers = {
            **self._read_headers(),
            "Prefer": "count=exact"
        }

        response = requests.get(
            f"{self.supabase_url}/rest/v1/news_articles",
            headers=headers,
            params=params,
            timeout=15,
        )
        response.raise_for_status()

        # Supabase는 Content-Range 헤더에 전체 count를 반환합니다.
        return int(response.headers.get("Content-Range", "0").split("/")[-1])

    def list_watchlist_symbols(self, limit: int = 5) -> list[dict[str, Any]]:
        if not self.supabase_url or not self.supabase_service_role_key:
            return []

        params = {
            "select": "symbol,name,exchange,asset_type,market_country,is_active,source,created_at",
            "is_active": "eq.true",
            "asset_type": "eq.STOCK",
            "order": "created_at.desc",
            "limit": str(limit),
        }
        try:
            response = requests.get(
                f"{self.supabase_url}/rest/v1/watchlist_symbols",
                headers=self._service_read_headers(),
                params=params,
                timeout=15,
            )
            response.raise_for_status()
            return response.json()
        except requests.exceptions.HTTPError:
            # 동적 종목 테이블이 아직 없거나 RLS가 막힌 경우 정적 키워드 수집만 진행합니다.
            return []

    def list_recent_query_keys(self, since: datetime) -> list[str]:
        if not self.is_configured:
            return []

        params = {
            "select": "query_key",
            "started_at": f"gte.{since.isoformat()}",
            "request_count": "gt.0",
        }
        response = requests.get(
            f"{self.supabase_url}/rest/v1/news_fetch_logs",
            headers=self._service_read_headers(),
            params=params,
            timeout=15,
        )
        response.raise_for_status()
        return [item["query_key"] for item in response.json() if item.get("query_key")]

    def count_fetch_requests(self, source: str, since: datetime) -> int:
        if not self.is_configured:
            return 0

        params = {
            "select": "request_count",
            "source": f"eq.{source}",
            "started_at": f"gte.{since.isoformat()}",
        }
        response = requests.get(
            f"{self.supabase_url}/rest/v1/news_fetch_logs",
            headers=self._service_read_headers(),
            params=params,
            timeout=15,
        )
        response.raise_for_status()

        total = 0
        for item in response.json():
            try:
                total += int(item.get("request_count") or 0)
            except (TypeError, ValueError):
                total += 0
        return total

    def list_articles_by_ids(self, ids: list[str]) -> list[dict[str, Any]]:
        if not self.supabase_url or not self.supabase_anon_key or not ids:
            return []

        ids = [str(item).strip() for item in ids if str(item).strip()]
        if not ids:
            return []

        params = {
            "select": "id,title,summary,url,market,source,company_name,symbol,raw_payload,content_hash,ai_summary,ai_summary_model,ai_summary_generated_at,ai_summary_prompt_version",
            "id": f"in.({','.join(ids)})",
        }
        response = requests.get(
            f"{self.supabase_url}/rest/v1/news_articles",
            headers=self._read_headers(),
            params=params,
            timeout=15,
        )
        response.raise_for_status()
        return response.json()

    def upsert_article_summaries(self, rows: list[dict[str, Any]]) -> None:
        if not self.is_configured or not rows:
            return

        for row in rows:
            article_id = str(row.get("id") or "").strip()
            if not article_id:
                continue

            payload = {
                "ai_summary": row.get("ai_summary"),
                "ai_summary_model": row.get("ai_summary_model"),
                "ai_summary_generated_at": row.get("ai_summary_generated_at"),
                "ai_summary_prompt_version": row.get("ai_summary_prompt_version"),
            }
            response = requests.patch(
                f"{self.supabase_url}/rest/v1/news_articles?id=eq.{article_id}",
                headers=self._write_headers(),
                json=payload,
                timeout=30,
            )
            response.raise_for_status()

    def upsert_articles(self, articles: list[dict[str, Any]]) -> None:
        if not self.is_configured or not articles:
            return

        response = requests.post(
            f"{self.supabase_url}/rest/v1/news_articles?on_conflict=url",
            headers=self._write_headers(),
            json=articles,
            timeout=30,
        )
        response.raise_for_status()

    def insert_fetch_log(self, payload: dict[str, Any]) -> None:
        if not self.is_configured:
            return
        response = requests.post(
            f"{self.supabase_url}/rest/v1/news_fetch_logs",
            headers=self._write_headers(),
            json=payload,
            timeout=15,
        )
        response.raise_for_status()

    def _read_headers(self) -> dict[str, str]:
        return {
            "apikey": self.supabase_anon_key,
            "Authorization": f"Bearer {self.supabase_anon_key}",
            "Content-Type": "application/json",
            "Prefer": "count=exact",
        }

    def _service_read_headers(self) -> dict[str, str]:
        return {
            "apikey": self.supabase_service_role_key,
            "Authorization": f"Bearer {self.supabase_service_role_key}",
            "Content-Type": "application/json",
        }

    def _write_headers(self) -> dict[str, str]:
        return {
            "apikey": self.supabase_service_role_key,
            "Authorization": f"Bearer {self.supabase_service_role_key}",
            "Content-Type": "application/json",
            "Prefer": "resolution=merge-duplicates,return=minimal",
        }
