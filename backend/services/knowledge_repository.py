from __future__ import annotations

from typing import Any

from backend.services.supabase_client import query_supabase_as_service_role, safe_query_supabase


class KnowledgeRepository:
    """Obsidian 노트와 자동메모리 데이터를 Supabase에 저장/조회합니다."""

    def upsert_obsidian_note(self, auth_header: str, user_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        note_payload = {
            "user_id": user_id,
            "vault_name": payload["vault_name"],
            "file_path": payload["file_path"],
            "title": payload["title"],
            "content": payload["content"],
            "content_hash": payload["content_hash"],
            "frontmatter": payload.get("frontmatter") or {},
            "modified_at": payload.get("modified_at"),
            "source": "obsidian",
            "sync_status": "SYNCED",
        }
        existing = safe_query_supabase(
            auth_header,
            "user_knowledge_notes",
            "GET",
            params={
                "user_id": f"eq.{user_id}",
                "vault_name": f"eq.{payload['vault_name']}",
                "file_path": f"eq.{payload['file_path']}",
                "select": "id",
                "limit": "1",
            },
        )
        existing_id = existing[0].get("id") if isinstance(existing, list) and existing else None

        if existing_id:
            result = safe_query_supabase(
                auth_header,
                f"user_knowledge_notes?id=eq.{existing_id}",
                "PATCH",
                json_data=note_payload,
                params={"select": "id,content_hash,sync_status"},
            )
        else:
            result = safe_query_supabase(
                auth_header,
                "user_knowledge_notes",
                "POST",
                json_data=note_payload,
                params={"select": "id,content_hash,sync_status"},
            )

        first_row = result[0] if isinstance(result, list) and result else {}
        return {
            "status": first_row.get("sync_status") or "SYNCED",
            "note_id": first_row.get("id"),
            "content_hash": first_row.get("content_hash") or note_payload["content_hash"],
        }

    def replace_knowledge_chunks(
        self,
        auth_header: str,
        source_type: str,
        source_id: str,
        chunks: list[dict[str, Any]],
    ) -> dict[str, int]:
        safe_query_supabase(
            auth_header,
            "knowledge_chunks",
            "DELETE",
            params={
                "source_type": f"eq.{source_type}",
                "source_id": f"eq.{source_id}",
            },
        )
        if chunks:
            safe_query_supabase(auth_header, "knowledge_chunks", "POST", json_data=chunks)
        return {"chunk_count": len(chunks)}

    def match_knowledge_chunks(self, payload: dict[str, Any]) -> list[dict[str, Any]]:
        rows = query_supabase_as_service_role("rpc/match_knowledge_chunks", "POST", json_data=payload) or []
        if not isinstance(rows, list):
            return []
        return [row for row in rows if isinstance(row, dict)]

    def list_auto_memory(self, auth_header: str, user_id: str) -> dict[str, list[str]]:
        rows = safe_query_supabase(
            auth_header,
            "user_memory_facts",
            "GET",
            params={
                "user_id": f"eq.{user_id}",
                "is_active": "eq.true",
                "select": "memory_type,content,symbol,confidence,evidence_count",
                "order": "confidence.desc,evidence_count.desc,updated_at.desc",
                "limit": "30",
            },
        )
        favorite_symbols: list[str] = []
        repeated_mistakes: list[str] = []

        for row in rows if isinstance(rows, list) else []:
            content = str(row.get("content") or "").strip()
            if not content:
                continue
            memory_type = str(row.get("memory_type") or "")
            if memory_type == "favorite_symbol":
                favorite_symbols.append(content)
            elif memory_type in {"repeated_mistake", "risk_preference"}:
                repeated_mistakes.append(content)

        return {
            "favorite_symbols": favorite_symbols,
            "repeated_mistakes": repeated_mistakes,
        }
