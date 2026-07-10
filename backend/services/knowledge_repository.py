from __future__ import annotations

from datetime import UTC, datetime
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

    def upsert_memory_fact(self, auth_header: str, user_id: str, fact: dict[str, Any]) -> dict[str, Any]:
        memory_type = str(fact.get("memory_type") or "").strip()
        content = str(fact.get("content") or "").strip()
        symbol = str(fact.get("symbol") or "").strip().upper() or None
        if not memory_type or not content:
            raise ValueError("memory_type과 content가 필요합니다.")

        params = {
            "user_id": f"eq.{user_id}",
            "memory_type": f"eq.{memory_type}",
            "content": f"eq.{content}",
            "is_active": "eq.true",
            "select": "id,evidence_count,confidence,metadata",
            "limit": "1",
        }
        if symbol:
            params["symbol"] = f"eq.{symbol}"
        else:
            params["symbol"] = "is.null"

        existing = safe_query_supabase(auth_header, "user_memory_facts", "GET", params=params) or []
        confidence = _bounded_confidence(fact.get("confidence"), default=0.7)
        metadata = fact.get("metadata") if isinstance(fact.get("metadata"), dict) else {}

        if existing:
            row = existing[0] or {}
            row_id = row.get("id")
            payload = {
                "confidence": max(_bounded_confidence(row.get("confidence"), default=0.5), confidence),
                "evidence_count": int(row.get("evidence_count") or 1) + 1,
                "metadata": {**(row.get("metadata") or {}), **metadata},
                "updated_at": datetime.now(UTC).isoformat(),
            }
            result = safe_query_supabase(
                auth_header,
                f"user_memory_facts?id=eq.{row_id}",
                "PATCH",
                json_data=payload,
                params={"select": "id,memory_type,content,symbol,confidence,evidence_count"},
            )
        else:
            payload = {
                "user_id": user_id,
                "memory_type": memory_type,
                "content": content,
                "symbol": symbol,
                "confidence": confidence,
                "evidence_count": 1,
                "source": fact.get("source") or "behavioral_event",
                "is_active": True,
                "metadata": metadata,
            }
            result = safe_query_supabase(
                auth_header,
                "user_memory_facts",
                "POST",
                json_data=payload,
                params={"select": "id,memory_type,content,symbol,confidence,evidence_count"},
            )

        return (result[0] if isinstance(result, list) and result else {}) or {}

    def list_chatbot_memory_context(self, auth_header: str, user_id: str, limit: int = 12) -> str:
        rows = safe_query_supabase(
            auth_header,
            "user_memory_facts",
            "GET",
            params={
                "user_id": f"eq.{user_id}",
                "is_active": "eq.true",
                "select": "memory_type,content,symbol,confidence,evidence_count",
                "order": "confidence.desc,evidence_count.desc,updated_at.desc",
                "limit": str(limit),
            },
        )
        lines = []
        for row in rows if isinstance(rows, list) else []:
            memory_type = str(row.get("memory_type") or "").strip()
            content = str(row.get("content") or "").strip()
            if memory_type and content:
                lines.append(f"- {memory_type}: {content}")

        if not lines:
            return ""
        return "\n".join([
            "자동메모리:",
            "아래 내용은 사용자가 대화와 행동으로 명시한 선호/주의점입니다. 추천과 설명 톤을 조절할 때만 사용하고 단정하지 마세요.",
            *lines,
        ])


def _bounded_confidence(value, default: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        number = default
    return min(max(number, 0.0), 1.0)
