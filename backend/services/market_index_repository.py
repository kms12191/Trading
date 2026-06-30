import json
import logging
import os
from typing import Any

import requests
from requests import HTTPError

logger = logging.getLogger(__name__)


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

        payload = [self._compat_row(row) for row in rows]
        symbols = [str(row.get("symbol") or "") for row in payload]
        logger.info("[MarketIndex][upsert] count=%s symbols=%s", len(payload), ",".join(symbols))
        logger.debug(
            "[MarketIndex][upsert] payload=%s",
            json.dumps(payload, ensure_ascii=False, default=str),
        )
        response = requests.post(
            f"{self.supabase_url}/rest/v1/market_indices_latest?on_conflict=symbol",
            headers=self._service_write_headers(),
            json=payload,
            timeout=60,
        )
        if response.ok:
            logger.info("[MarketIndex][upsert] saved count=%s symbols=%s", len(payload), ",".join(symbols))
            return

        logger.warning(
            "[MarketIndex][upsert] failed status=%s body=%s",
            response.status_code,
            response.text,
        )
        fallback_response = requests.post(
            f"{self.supabase_url}/rest/v1/market_indices_latest?on_conflict=symbol",
            headers=self._service_write_headers(),
            json=payload,
            timeout=60,
        )
        if not fallback_response.ok:
            logger.error(
                "[MarketIndex][upsert] retry failed status=%s body=%s",
                fallback_response.status_code,
                fallback_response.text,
            )
        fallback_response.raise_for_status()
        logger.info("[MarketIndex][upsert] retry saved count=%s symbols=%s", len(payload), ",".join(symbols))

    def list_latest(self) -> list[dict[str, Any]]:
        if not self.is_configured:
            return []

        try:
            response = requests.get(
                f"{self.supabase_url}/rest/v1/market_indices_latest",
                headers=self._service_read_headers(),
                params={
                    "select": "symbol,label,source,market_country,ticker,current_price,previous_close,change_price,change_rate,current_value,change_value,change_percent,currency,display_order,as_of,updated_at,raw_payload",
                    "order": "display_order.asc,updated_at.desc",
                },
                timeout=30,
            )
            response.raise_for_status()
            rows = response.json()
            logger.info(
                "[MarketIndex][db-load] count=%s symbols=%s",
                len(rows or []),
                ",".join(str(row.get("symbol") or "") for row in (rows or [])),
            )
            return rows
        except HTTPError as error:
            if error.response is not None and error.response.status_code == 404:
                raise RuntimeError("market_indices_latest table is not available in Supabase yet.") from error
            logger.warning("[MarketIndex][db-load] failed: %s", error, exc_info=True)
            return self._list_latest_fallback()
        except Exception as error:
            logger.warning("[MarketIndex][db-load] failed: %s", error, exc_info=True)
            return self._list_latest_fallback()

    def _list_latest_fallback(self) -> list[dict[str, Any]]:
        try:
            response = requests.get(
                f"{self.supabase_url}/rest/v1/market_indices_latest",
                headers=self._service_read_headers(),
                params={
                    "select": "symbol,label,source,market_country,ticker,current_price,previous_close,change_price,change_rate,current_value,change_value,change_percent,currency,display_order,as_of,updated_at,raw_payload",
                    "order": "display_order.asc,updated_at.desc",
                },
                timeout=30,
            )
            response.raise_for_status()
            rows = response.json()
            logger.info(
                "[MarketIndex][db-fallback] load success count=%s symbols=%s",
                len(rows or []),
                ",".join(str(row.get("symbol") or "") for row in (rows or [])),
            )
            return rows
        except Exception as error:
            logger.warning("[MarketIndex][db-fallback] list_latest failed: %s", error, exc_info=True)
            return []

    def _compat_row(self, row: dict[str, Any]) -> dict[str, Any]:
        current_price = row.get("current_price") or row.get("current_value") or 0
        change_price = row.get("change_price") or row.get("change_value") or 0
        change_rate = row.get("change_rate") or row.get("change_percent") or 0
        previous_close = row.get("previous_close")
        if previous_close in (None, ""):
            previous_close = current_price - change_price if current_price and change_price is not None else 0
        updated_at = row.get("updated_at") or row.get("synced_at") or row.get("as_of")
        return {
            "symbol": row.get("symbol"),
            "label": row.get("label"),
            "source": row.get("source"),
            "market_country": row.get("market_country"),
            "ticker": row.get("ticker"),
            "current_price": current_price,
            "previous_close": previous_close,
            "change_price": change_price,
            "change_rate": change_rate,
            "current_value": current_price,
            "change_value": change_price,
            "change_percent": change_rate,
            "currency": row.get("currency"),
            "display_order": row.get("display_order"),
            "as_of": row.get("as_of") or row.get("synced_at") or updated_at,
            "updated_at": updated_at,
            "raw_payload": row.get("raw_payload") or {},
        }

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
