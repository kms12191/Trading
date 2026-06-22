import os
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
        limit: int = 20,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        if not self.supabase_url or not self.supabase_anon_key:
            return []

        params: dict[str, str] = {
            "select": "id,market,source,source_article_id,title,summary,url,published_at,fetched_at,company_name,symbol,language,sentiment,content_hash,is_active",
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
                f"title.ilike.%{q}%",
                f"summary.ilike.%{q}%",
                f"company_name.ilike.%{q}%",
                f"symbol.ilike.%{q}%",
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
        }

    def _write_headers(self) -> dict[str, str]:
        return {
            "apikey": self.supabase_service_role_key,
            "Authorization": f"Bearer {self.supabase_service_role_key}",
            "Content-Type": "application/json",
            "Prefer": "resolution=merge-duplicates,return=minimal",
        }
