import os
import xml.etree.ElementTree as ET
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import requests

from backend.services.dart_repository import DartRepository


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DART_DISCLOSURE_URL = "https://opendart.fss.or.kr/api/list.json"
EXCLUDED_DISCLOSURE_REPORT_NAMES = {
    "임원ㆍ주요주주특정증권등소유상황보고서",
    "주식등의대량보유상황보고서",
    "의결권대리행사권유참고서류",
}


class DartIngestService:
    def __init__(self) -> None:
        self.api_key = os.getenv("DART_API_KEY", "")
        self.repository = DartRepository()
        self.page_count = min(int(os.getenv("DART_PAGE_COUNT", "100")), 100)
        self.incremental_lookback_days = max(int(os.getenv("DART_INCREMENTAL_LOOKBACK_DAYS", "1")), 0)
        self.backfill_days = int(os.getenv("DART_BACKFILL_DAYS", "365"))
        self.backfill_chunk_days = max(int(os.getenv("DART_BACKFILL_CHUNK_DAYS", "1")), 1)
        self.request_timeout_seconds = int(os.getenv("DART_REQUEST_TIMEOUT_SECONDS", "15"))

    def sync_corp_codes_from_xml(self, xml_path: str | Path | None = None, dry_run: bool = False) -> dict[str, Any]:
        path = Path(xml_path) if xml_path else PROJECT_ROOT / "CORPCODE.xml"
        if not path.exists():
            raise FileNotFoundError(f"DART 고유번호 파일을 찾을 수 없습니다: {path}")

        tree = ET.parse(path)
        rows: list[dict[str, Any]] = []
        for item in tree.getroot().findall("list"):
            stock_code = self._text(item, "stock_code")
            if not stock_code:
                continue
            corp_code = self._text(item, "corp_code")
            corp_name = self._text(item, "corp_name")
            modify_date = self._format_date(self._text(item, "modify_date"))
            if not corp_code or not corp_name:
                continue
            rows.append(
                {
                    "corp_code": corp_code,
                    "corp_name": corp_name,
                    "stock_code": stock_code,
                    "modify_date": modify_date,
                    "market_country": "KR",
                    "raw_payload": {
                        "corp_code": corp_code,
                        "corp_name": corp_name,
                        "stock_code": stock_code,
                        "modify_date": self._text(item, "modify_date"),
                    },
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                }
            )

        if not dry_run:
            self.repository.upsert_corp_codes(rows)
        return {"synced": 0 if dry_run else len(rows), "parsed": len(rows), "dry_run": dry_run, "source": str(path)}

    def run_incremental(self) -> dict[str, Any]:
        end_date = date.today()
        start_date = end_date - timedelta(days=self.incremental_lookback_days)
        return self.run_range(start_date=start_date, end_date=end_date, query_key="incremental")

    def run_backfill_recent_year(self) -> dict[str, Any]:
        end_date = date.today()
        start_date = end_date - timedelta(days=self.backfill_days)
        total_fetched = 0
        total_saved = 0
        total_requests = 0
        windows = 0
        failures: list[dict[str, str]] = []

        cursor = start_date
        while cursor <= end_date:
            window_end = min(cursor + timedelta(days=self.backfill_chunk_days - 1), end_date)
            try:
                result = self.run_range(
                    start_date=cursor,
                    end_date=window_end,
                    query_key=f"backfill:{cursor.isoformat()}:{window_end.isoformat()}",
                )
                total_fetched += int(result.get("fetched", 0))
                total_saved += int(result.get("saved", 0))
                total_requests += int(result.get("request_count", 0))
                windows += 1
            except Exception as error:
                failures.append(
                    {
                        "start_date": cursor.isoformat(),
                        "end_date": window_end.isoformat(),
                        "error": str(error),
                    }
                )
            cursor = window_end + timedelta(days=1)

        return {
            "fetched": total_fetched,
            "saved": total_saved,
            "request_count": total_requests,
            "windows": windows,
            "failures": failures[:20],
        }

    def run_range(self, start_date: date, end_date: date, query_key: str = "manual") -> dict[str, Any]:
        if not self.api_key:
            raise RuntimeError("DART_API_KEY가 설정되지 않았습니다.")
        if not self.repository.is_configured:
            raise RuntimeError("Supabase service role 설정이 없습니다.")

        started_at = datetime.now(timezone.utc).isoformat()
        request_count = 0
        fetched_rows: list[dict[str, Any]] = []
        try:
            first_payload = self._request_list(start_date, end_date, page_no=1)
            request_count += 1
            fetched_rows.extend(self._extract_rows(first_payload))
            total_page = int(first_payload.get("total_page") or 1)

            for page_no in range(2, total_page + 1):
                payload = self._request_list(start_date, end_date, page_no=page_no)
                request_count += 1
                fetched_rows.extend(self._extract_rows(payload))

            deduplicated = self._deduplicate(fetched_rows)
            if deduplicated:
                self.repository.upsert_disclosures(deduplicated)

            result = {
                "fetched": len(fetched_rows),
                "saved": len(deduplicated),
                "request_count": request_count,
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
            }
            self._insert_log(
                query_key=query_key,
                status="SUCCESS",
                fetched_count=len(fetched_rows),
                inserted_count=len(deduplicated),
                request_count=request_count,
                started_at=started_at,
                query_text=f"{start_date.isoformat()}~{end_date.isoformat()}",
            )
            return result
        except Exception as error:
            self._insert_log(
                query_key=query_key,
                status="FAILED",
                fetched_count=len(fetched_rows),
                inserted_count=0,
                request_count=request_count,
                started_at=started_at,
                query_text=f"{start_date.isoformat()}~{end_date.isoformat()}",
                error_message=str(error),
            )
            raise

    def _request_list(self, start_date: date, end_date: date, page_no: int) -> dict[str, Any]:
        response = requests.get(
            DART_DISCLOSURE_URL,
            params={
                "crtfc_key": self.api_key,
                "bgn_de": start_date.strftime("%Y%m%d"),
                "end_de": end_date.strftime("%Y%m%d"),
                "page_no": page_no,
                "page_count": self.page_count,
                "sort": "date",
                "sort_mth": "desc",
            },
            timeout=self.request_timeout_seconds,
        )
        response.raise_for_status()
        payload = response.json()
        status = str(payload.get("status") or "")
        if status not in {"000", "013"}:
            raise RuntimeError(f"OpenDART list failed status={status}, message={payload.get('message')}")
        return payload

    def _extract_rows(self, payload: dict[str, Any]) -> list[dict[str, Any]]:
        rows = []
        for item in payload.get("list") or []:
            stock_code = str(item.get("stock_code") or "").strip()
            rcept_no = str(item.get("rcept_no") or "").strip()
            rcept_dt = self._format_date(str(item.get("rcept_dt") or ""))
            if not stock_code or not rcept_no or not rcept_dt:
                continue
            report_nm = str(item.get("report_nm") or "").strip()
            if self._is_excluded_report(report_nm):
                continue
            rows.append(
                {
                    "rcept_no": rcept_no,
                    "corp_code": str(item.get("corp_code") or "").strip(),
                    "stock_code": stock_code,
                    "corp_name": str(item.get("corp_name") or "").strip(),
                    "corp_cls": str(item.get("corp_cls") or "").strip(),
                    "report_nm": report_nm,
                    "flr_nm": str(item.get("flr_nm") or "").strip(),
                    "rcept_dt": rcept_dt,
                    "rm": str(item.get("rm") or "").strip(),
                    "url": f"https://dart.fss.or.kr/dsaf001/main.do?rcpNo={rcept_no}",
                    "summary": self._build_summary(item),
                    "is_active": True,
                    "fetched_at": datetime.now(timezone.utc).isoformat(),
                    "raw_payload": item,
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                }
            )
        return rows

    def _build_summary(self, item: dict[str, Any]) -> str:
        corp_name = str(item.get("corp_name") or "").strip()
        report_nm = str(item.get("report_nm") or "").strip()
        flr_nm = str(item.get("flr_nm") or "").strip()
        rcept_dt = self._format_date(str(item.get("rcept_dt") or ""))
        pieces = [piece for piece in [corp_name, report_nm, flr_nm, rcept_dt] if piece]
        return " · ".join(pieces)

    def _deduplicate(self, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        seen: set[str] = set()
        result = []
        for row in rows:
            key = row.get("rcept_no")
            if not key or key in seen:
                continue
            seen.add(key)
            result.append(row)
        return result

    def _is_excluded_report(self, report_name: str) -> bool:
        normalized = "".join(str(report_name or "").split())
        return normalized in EXCLUDED_DISCLOSURE_REPORT_NAMES

    def _insert_log(
        self,
        query_key: str,
        status: str,
        fetched_count: int,
        inserted_count: int,
        request_count: int,
        started_at: str,
        query_text: str,
        error_message: str | None = None,
    ) -> None:
        self.repository.insert_fetch_log(
            {
                "source": "OPENDART",
                "query_key": query_key,
                "query_category": "disclosure_list",
                "query_text": query_text,
                "status": status,
                "fetched_count": fetched_count,
                "inserted_count": inserted_count,
                "request_count": request_count,
                "error_message": error_message,
                "started_at": started_at,
                "finished_at": datetime.now(timezone.utc).isoformat(),
            }
        )

    def _text(self, item: ET.Element, tag: str) -> str:
        node = item.find(tag)
        return (node.text or "").strip() if node is not None else ""

    def _format_date(self, value: str) -> str | None:
        clean = "".join(ch for ch in str(value or "") if ch.isdigit())
        if len(clean) != 8:
            return None
        return f"{clean[:4]}-{clean[4:6]}-{clean[6:8]}"
