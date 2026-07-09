from __future__ import annotations

import os
import sys
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(PROJECT_ROOT))
load_dotenv(PROJECT_ROOT / "backend" / ".env")

from backend.services.disclosure_knowledge_index_service import (  # noqa: E402
    JsonObject,
    build_disclosure_summary_chunks,
    disclosure_summary_document_from_rows,
)
from backend.services.knowledge_chunk_service import KnowledgeChunkService  # noqa: E402
from backend.services.supabase_client import query_supabase_as_service_role  # noqa: E402


def main() -> int:
    limit = int(os.getenv("DISCLOSURE_RAG_BACKFILL_LIMIT", "500"))
    offset = 0
    documents = 0
    chunks: list[JsonObject] = []
    chunk_service = KnowledgeChunkService()

    while True:
        analyses = _fetch_analyses(limit, offset)
        if not analyses:
            break
        disclosures = _fetch_disclosures([str(row.get("rcept_no") or "") for row in analyses])
        for analysis in analyses:
            rcept_no = str(analysis.get("rcept_no") or "")
            if not rcept_no:
                continue
            document = disclosure_summary_document_from_rows(analysis, disclosures.get(rcept_no))
            document_chunks = build_disclosure_summary_chunks(chunk_service, document)
            chunks.extend(document_chunks)
            if document_chunks:
                documents += 1
        offset += limit
        print(f"[prepared] disclosures={documents}, chunks={len(chunks)}, offset={offset}")

    query_supabase_as_service_role("knowledge_chunks", "DELETE", params={"source_type": "eq.DISCLOSURE"})
    for chunk in _chunks(chunks, 500):
        query_supabase_as_service_role("knowledge_chunks", "POST", json_data=chunk)

    print(f"[done] disclosure summaries indexed={documents}, chunks={len(chunks)}")
    return 0


def _fetch_analyses(limit: int, offset: int) -> list[JsonObject]:
    rows = query_supabase_as_service_role(
        "dart_disclosure_analyses",
        "GET",
        params={
            "select": "rcept_no,category,sentiment_label,sentiment_message,headline,plain_summary,key_points,risk_points,check_items,metrics",
            "order": "analyzed_at.desc",
            "limit": str(limit),
            "offset": str(offset),
        },
    )
    return rows if isinstance(rows, list) else []


def _fetch_disclosures(rcept_nos: list[str]) -> dict[str, JsonObject]:
    clean_rcept_nos = [rcept_no for rcept_no in rcept_nos if rcept_no]
    if not clean_rcept_nos:
        return {}
    joined = ",".join(clean_rcept_nos)
    rows = query_supabase_as_service_role(
        "dart_disclosures",
        "GET",
        params={
            "select": "rcept_no,stock_code,corp_name,report_nm,rcept_dt,url",
            "rcept_no": f"in.({joined})",
        },
    )
    if not isinstance(rows, list):
        return {}
    return {str(row.get("rcept_no") or ""): row for row in rows if isinstance(row, dict)}


def _chunks(rows: list[JsonObject], size: int) -> list[list[JsonObject]]:
    return [rows[index:index + size] for index in range(0, len(rows), size)]


if __name__ == "__main__":
    raise SystemExit(main())
