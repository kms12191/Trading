from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, TypeAlias

from backend.services.disclosure_knowledge_index_service import (
    JsonObject,
    build_disclosure_summary_chunks,
    disclosure_summary_document_from_rows,
)
from backend.services.knowledge_chunk_service import KnowledgeChunkService
from backend.services.supabase_client import query_supabase_as_service_role

JsonValue: TypeAlias = str | int | float | bool | None | list["JsonValue"] | dict[str, "JsonValue"]


class EmbeddingClient(Protocol):
    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        ...


@dataclass(frozen=True, slots=True)
class DisclosureKnowledgeIndexResult:
    status: str
    chunk_count: int

    def to_payload(self) -> dict[str, JsonValue]:
        return {"status": self.status, "chunk_count": self.chunk_count}


class DisclosureKnowledgeSyncService:
    def __init__(self, chunk_service: KnowledgeChunkService, embedding_service: EmbeddingClient) -> None:
        self.chunk_service = chunk_service
        self.embedding_service = embedding_service

    def sync_analysis(self, analysis: JsonObject, disclosure: JsonObject | None = None) -> dict[str, JsonValue]:
        document = disclosure_summary_document_from_rows(analysis, disclosure)
        if not document.rcept_no:
            raise ValueError("rcept_no is required")  # noqa: GENERIC_ERR_OK

        existing_rows = self._list_existing_chunks(document.rcept_no)
        embedded_count = sum(
            1
            for row in existing_rows
            if str(row.get("embedding_status") or "").upper() == "EMBEDDED"
        )
        if embedded_count > 0:
            return DisclosureKnowledgeIndexResult(status="SKIPPED", chunk_count=embedded_count).to_payload()

        chunks = build_disclosure_summary_chunks(self.chunk_service, document)
        if not chunks:
            return DisclosureKnowledgeIndexResult(status="EMPTY", chunk_count=0).to_payload()

        self._replace_chunks(document.rcept_no, chunks)
        try:
            embeddings = self.embedding_service.embed_texts([str(chunk.get("chunk_text") or "") for chunk in chunks])
        except (RuntimeError, OSError):
            self._mark_chunks(document.rcept_no, "FAILED")
            return DisclosureKnowledgeIndexResult(status="FAILED", chunk_count=len(chunks)).to_payload()

        saved_count = 0
        for chunk, embedding in zip(chunks, embeddings, strict=False):
            chunk_index = int(chunk.get("chunk_index") or 0)
            self._mark_chunk_embedded(document.rcept_no, chunk_index, embedding)
            saved_count += 1

        status = "EMBEDDED" if saved_count == len(chunks) else "PARTIAL"
        return DisclosureKnowledgeIndexResult(status=status, chunk_count=len(chunks)).to_payload()

    def _list_existing_chunks(self, rcept_no: str) -> list[JsonObject]:
        rows = query_supabase_as_service_role(
            "knowledge_chunks",
            "GET",
            params={
                "source_type": "eq.DISCLOSURE",
                "source_id": f"eq.{rcept_no}",
                "select": "id,embedding_status",
                "limit": "20",
            },
        )
        if not isinstance(rows, list):
            return []
        return [row for row in rows if isinstance(row, dict)]

    def _replace_chunks(self, rcept_no: str, chunks: list[JsonObject]) -> None:
        query_supabase_as_service_role(
            "knowledge_chunks",
            "DELETE",
            params={"source_type": "eq.DISCLOSURE", "source_id": f"eq.{rcept_no}"},
        )
        query_supabase_as_service_role("knowledge_chunks", "POST", json_data=chunks)

    def _mark_chunks(self, rcept_no: str, status: str) -> None:
        query_supabase_as_service_role(
            f"knowledge_chunks?source_type=eq.DISCLOSURE&source_id=eq.{rcept_no}",
            "PATCH",
            json_data={"embedding_status": status},
        )

    def _mark_chunk_embedded(self, rcept_no: str, chunk_index: int, embedding: list[float]) -> None:
        query_supabase_as_service_role(
            f"knowledge_chunks?source_type=eq.DISCLOSURE&source_id=eq.{rcept_no}&chunk_index=eq.{chunk_index}",
            "PATCH",
            json_data={"embedding": embedding, "embedding_status": "EMBEDDED"},
        )
