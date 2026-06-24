import os
from typing import Any

import requests


class MarketRepository:
    def __init__(self) -> None:
        self.supabase_url = os.getenv("SUPABASE_URL", "").rstrip("/")
        self.supabase_service_role_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")

    @property
    def is_configured(self) -> bool:
        return bool(self.supabase_url and self.supabase_service_role_key)

    def upsert_stock_master(self, rows: list[dict[str, Any]]) -> None:
        if not self.is_configured or not rows:
            return

        response = requests.post(
            f"{self.supabase_url}/rest/v1/kis_stock_master?on_conflict=symbol",
            headers=self._service_write_headers(),
            json=rows,
            timeout=60,
        )
        response.raise_for_status()

    def upsert_turnover_latest(self, rows: list[dict[str, Any]]) -> None:
        if not self.is_configured or not rows:
            return

        response = requests.post(
            f"{self.supabase_url}/rest/v1/kis_stock_turnover_latest?on_conflict=symbol",
            headers=self._service_write_headers(),
            json=rows,
            timeout=60,
        )
        response.raise_for_status()

    def list_turnover_rankings(self, market_segment: str = "ALL", limit: int = 50) -> list[dict[str, Any]]:
        if not self.is_configured:
            return []

        params = {
            "select": "symbol,name,market_segment,current_price,change_rate,trading_volume,trading_value,as_of",
            "order": "trading_value.desc,updated_at.desc",
            "limit": str(limit),
        }
        if market_segment and market_segment.upper() != "ALL":
            params["market_segment"] = f"eq.{market_segment.upper()}"

        response = requests.get(
            f"{self.supabase_url}/rest/v1/kis_stock_turnover_latest",
            headers=self._service_read_headers(),
            params=params,
            timeout=30,
        )
        response.raise_for_status()
        return response.json()

    def count_universe(self, market_segment: str = "ALL") -> int:
        if not self.is_configured:
            return 0

        params = {
            "is_active": "eq.true",
            "symbol": "match.\\d{6}",
        }
        if market_segment and market_segment.upper() != "ALL":
            params["market_segment"] = f"eq.{market_segment.upper()}"

        response = requests.get(
            f"{self.supabase_url}/rest/v1/kis_stock_master",
            headers={**self._service_read_headers(), "Prefer": "count=exact"},
            params=params,
            timeout=30,
        )
        response.raise_for_status()
        content_range = response.headers.get("Content-Range", "0")
        return int(content_range.split("/")[-1])

    def list_universe(self, market_segment: str = "ALL", limit: int = 5000) -> list[dict[str, Any]]:
        if not self.is_configured:
            return []

        params = {
            "select": "symbol,name,market_segment,market_country,asset_type,source,is_active,listed_at,source_file_row",
            "is_active": "eq.true",
            "symbol": "match.\\d{6}",
            "order": "market_segment.asc,symbol.asc",
            "limit": str(limit),
        }
        if market_segment and market_segment.upper() != "ALL":
            params["market_segment"] = f"eq.{market_segment.upper()}"

        response = requests.get(
            f"{self.supabase_url}/rest/v1/kis_stock_master",
            headers=self._service_read_headers(),
            params=params,
            timeout=30,
        )
        response.raise_for_status()
        return response.json()

    def _service_read_headers(self) -> dict[str, str]:
        return {
            "apikey": self.supabase_service_role_key,
            "Authorization": f"Bearer {self.supabase_service_role_key}",
            "Content-Type": "application/json",
        }

    def _service_write_headers(self) -> dict[str, str]:
        return {
            "apikey": self.supabase_service_role_key,
            "Authorization": f"Bearer {self.supabase_service_role_key}",
            "Content-Type": "application/json",
            "Prefer": "resolution=merge-duplicates,return=minimal",
        }
