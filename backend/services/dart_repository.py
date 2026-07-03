import os
from typing import Any

import requests
from requests import HTTPError


class DartRepository:
    def __init__(self) -> None:
        self.supabase_url = os.getenv("SUPABASE_URL", "").rstrip("/")
        self.supabase_service_role_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
        self.supabase_anon_key = os.getenv("SUPABASE_ANON_KEY", "")

    @property
    def is_configured(self) -> bool:
        return bool(self.supabase_url and self.supabase_service_role_key)

    def list_disclosures(
        self,
        symbol: str = "",
        query: str = "",
        limit: int = 10,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        if not self.supabase_url or not self.supabase_anon_key:
            return []

        params: dict[str, str] = {
            "select": "id,rcept_no,corp_code,stock_code,corp_name,corp_cls,report_nm,flr_nm,rcept_dt,rm,url,summary,is_active,fetched_at,raw_payload",
            "order": "rcept_dt.desc,rcept_no.desc",
            "limit": str(limit),
            "offset": str(offset),
            "is_active": "eq.true",
        }
        normalized_symbol = str(symbol or "").strip()
        if normalized_symbol:
            params["stock_code"] = f"eq.{normalized_symbol}"

        if query:
            q = query.strip()
            params["or"] = f"(report_nm.ilike.*{q}*,corp_name.ilike.*{q}*,stock_code.ilike.*{q}*)"

        response = requests.get(
            f"{self.supabase_url}/rest/v1/dart_disclosures",
            headers=self._read_headers(),
            params=params,
            timeout=15,
        )
        response.raise_for_status()
        return response.json()

    def count_disclosures(self, symbol: str = "", query: str = "") -> int:
        if not self.supabase_url or not self.supabase_anon_key:
            return 0

        params: dict[str, str] = {
            "select": "id",
            "is_active": "eq.true",
        }
        normalized_symbol = str(symbol or "").strip()
        if normalized_symbol:
            params["stock_code"] = f"eq.{normalized_symbol}"
        if query:
            q = query.strip()
            params["or"] = f"(report_nm.ilike.*{q}*,corp_name.ilike.*{q}*,stock_code.ilike.*{q}*)"

        response = requests.get(
            f"{self.supabase_url}/rest/v1/dart_disclosures",
            headers={**self._read_headers(), "Prefer": "count=exact"},
            params=params,
            timeout=15,
        )
        response.raise_for_status()
        return int(response.headers.get("Content-Range", "0").split("/")[-1])

    def get_disclosure_by_rcept_no(self, rcept_no: str) -> dict[str, Any] | None:
        if not self.supabase_url or not self.supabase_anon_key:
            return None

        response = requests.get(
            f"{self.supabase_url}/rest/v1/dart_disclosures",
            headers=self._read_headers(),
            params={
                "select": "id,rcept_no,corp_code,stock_code,corp_name,corp_cls,report_nm,flr_nm,rcept_dt,rm,url,summary,is_active,fetched_at,raw_payload",
                "rcept_no": f"eq.{str(rcept_no or '').strip()}",
                "limit": "1",
            },
            timeout=15,
        )
        response.raise_for_status()
        rows = response.json()
        return rows[0] if rows else None

    def get_disclosure_analysis(self, rcept_no: str) -> dict[str, Any] | None:
        if not self.supabase_url or not self.supabase_anon_key:
            return None

        try:
            response = requests.get(
                f"{self.supabase_url}/rest/v1/dart_disclosure_analyses",
                headers=self._read_headers(),
                params={
                    "select": "id,rcept_no,category,sentiment,sentiment_label,sentiment_message,confidence,headline,key_points,risk_points,metrics,analysis_source,raw_payload,analyzed_at",
                    "rcept_no": f"eq.{str(rcept_no or '').strip()}",
                    "limit": "1",
                },
                timeout=15,
            )
            response.raise_for_status()
        except HTTPError:
            if response.status_code == 404:
                return None
            raise
        rows = response.json()
        return rows[0] if rows else None

    def upsert_disclosure_analysis(self, row: dict[str, Any]) -> dict[str, Any] | None:
        if not self.is_configured or not row:
            return None

        response = requests.post(
            f"{self.supabase_url}/rest/v1/dart_disclosure_analyses?on_conflict=rcept_no",
            headers={**self._write_headers(), "Prefer": "resolution=merge-duplicates,return=representation"},
            json=row,
            timeout=30,
        )
        try:
            self._raise_for_status(response, "dart_disclosure_analyses")
        except RuntimeError:
            if response.status_code == 404:
                return None
            raise
        rows = response.json()
        return rows[0] if rows else None

    def upsert_corp_codes(self, rows: list[dict[str, Any]]) -> None:
        if not self.is_configured or not rows:
            return
        for chunk in self._chunks(rows, 500):
            response = requests.post(
                f"{self.supabase_url}/rest/v1/dart_corp_codes?on_conflict=corp_code",
                headers=self._write_headers(),
                json=chunk,
                timeout=30,
            )
            self._raise_for_status(response, "dart_corp_codes")

    def upsert_disclosures(self, rows: list[dict[str, Any]]) -> None:
        if not self.is_configured or not rows:
            return
        for chunk in self._chunks(rows, 500):
            response = requests.post(
                f"{self.supabase_url}/rest/v1/dart_disclosures?on_conflict=rcept_no",
                headers=self._write_headers(),
                json=chunk,
                timeout=30,
            )
            self._raise_for_status(response, "dart_disclosures")

    def insert_fetch_log(self, payload: dict[str, Any]) -> None:
        if not self.is_configured:
            return
        response = requests.post(
            f"{self.supabase_url}/rest/v1/dart_fetch_logs",
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

    def _write_headers(self) -> dict[str, str]:
        return {
            "apikey": self.supabase_service_role_key,
            "Authorization": f"Bearer {self.supabase_service_role_key}",
            "Content-Type": "application/json",
            "Prefer": "resolution=merge-duplicates,return=minimal",
        }

    def _chunks(self, rows: list[dict[str, Any]], size: int) -> list[list[dict[str, Any]]]:
        return [rows[index:index + size] for index in range(0, len(rows), size)]

    def _raise_for_status(self, response: requests.Response, table_name: str) -> None:
        try:
            response.raise_for_status()
        except HTTPError as error:
            if response.status_code == 404:
                raise RuntimeError(
                    f"Supabase table '{table_name}'을 찾지 못했습니다. "
                    "supabase/migrations/20260701093000_create_dart_disclosures.sql 마이그레이션을 먼저 적용하세요."
                ) from error
            raise
