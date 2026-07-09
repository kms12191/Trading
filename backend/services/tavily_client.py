import os
from typing import Any

import requests


TAVILY_SEARCH_URL = "https://api.tavily.com/search"


class TavilySearchError(Exception):
    pass


class TavilyClient:
    def __init__(self) -> None:
        self.api_key = os.getenv("TAVILY_API_KEY", "").strip()
        self.timeout_seconds = int(os.getenv("TAVILY_TIMEOUT_SECONDS", "20"))
        self.search_depth = os.getenv("TAVILY_SEARCH_DEPTH", "basic").strip() or "basic"

    @property
    def enabled(self) -> bool:
        return bool(self.api_key)

    def search(self, query: str, max_results: int = 5) -> dict[str, Any]:
        text = str(query or "").strip()
        if not text:
            raise TavilySearchError("검색어가 비어 있습니다.")
        if not self.enabled:
            raise TavilySearchError("TAVILY_API_KEY가 설정되어 있지 않습니다.")

        payload = {
            "api_key": self.api_key,
            "query": text,
            "search_depth": self.search_depth,
            "include_answer": True,
            "include_raw_content": False,
            "max_results": max(1, min(int(max_results or 5), 10)),
        }
        response = requests.post(
            TAVILY_SEARCH_URL,
            json=payload,
            timeout=self.timeout_seconds,
        )
        if response.status_code >= 400:
            raise TavilySearchError(f"Tavily 검색 요청 실패: HTTP {response.status_code}")

        return response.json()
