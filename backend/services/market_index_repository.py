import os
from typing import Any

import requests
from requests import HTTPError


class MarketIndexRepository:
    def __init__(self) -> None:
        self.supabase_url = os.getenv("SUPABASE_URL", "").rstrip("/")
        self.supabase_service_role_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")

    @property
    def is_configured(self) -> bool:
        return bool(self.supabase_url and self.supabase_service_role_key)

    def upsert_latest(self, rows: list[dict[str, Any]]) -> None:
        if not self.is_configured or not rows:
            return

        response = requests.post(
            f"{self.supabase_url}/rest/v1/market_indices_latest?on_conflict=symbol",
            headers=self._service_write_headers(),
            json=rows,
            timeout=60,
        )
        response.raise_for_status()

    def list_latest(self) -> list[dict[str, Any]]:
        if not self.is_configured:
            return []

        try:
            response = requests.get(
                f"{self.supabase_url}/rest/v1/market_indices_latest",
                headers=self._service_read_headers(),
                params={
                    "select": "symbol,label,source,market_country,ticker,current_value,change_value,change_percent,currency,display_order,as_of,updated_at,raw_payload",
                    "order": "display_order.asc,updated_at.desc",
                },
                timeout=30,
            )
            response.raise_for_status()
            return response.json()
        except HTTPError as error:
            if error.response is not None and error.response.status_code == 404:
                raise RuntimeError("market_indices_latest table is not available in Supabase yet.") from error
            raise

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
