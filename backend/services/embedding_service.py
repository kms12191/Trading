from __future__ import annotations

import os
from dataclasses import dataclass
from typing import TypeAlias

import requests

from backend.services.supabase_client import query_supabase_as_service_role

JsonValue: TypeAlias = str | int | float | bool | None | list["JsonValue"] | dict[str, "JsonValue"]
JsonObject: TypeAlias = dict[str, JsonValue]

OPENAI_EMBEDDINGS_URL = "https://api.openai.com/v1/embeddings"


@dataclass(frozen=True, slots=True)
class EmbeddingConfig:
    api_key: str
    model: str
    timeout_seconds: int


class EmbeddingService:
    def __init__(self, config: EmbeddingConfig | None = None) -> None:
        self.config = config or EmbeddingConfig(
            api_key=os.getenv("OPENAI_API_KEY", "").strip(),
            model=os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small").strip(),
            timeout_seconds=int(os.getenv("OPENAI_EMBEDDING_TIMEOUT_SECONDS", "30")),
        )

    def embed_query(self, text: str) -> list[float]:
        embeddings = self.embed_texts([text])
        return embeddings[0] if embeddings else []

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        clean_texts = [text.strip() for text in texts if text.strip()]
        if not clean_texts:
            return []
        if not self.config.api_key:
            raise RuntimeError("OPENAI_API_KEY가 설정되어 있지 않습니다.")

        response = requests.post(
            OPENAI_EMBEDDINGS_URL,
            headers={
                "Authorization": f"Bearer {self.config.api_key}",
                "Content-Type": "application/json",
            },
            json={"model": self.config.model, "input": clean_texts},
            timeout=self.config.timeout_seconds,
        )
        response.raise_for_status()
        data = response.json().get("data") or []
        return [item.get("embedding") for item in data if isinstance(item.get("embedding"), list)]

    def embed_pending_chunks(self, limit: int = 100, source_type: str | None = None) -> int:
        params: dict[str, str] = {
            "select": "id,chunk_text",
            "embedding_status": "eq.PENDING",
            "order": "updated_at.asc",
            "limit": str(limit),
        }
        if source_type:
            params["source_type"] = f"eq.{source_type}"

        rows = query_supabase_as_service_role("knowledge_chunks", "GET", params=params) or []
        if not isinstance(rows, list) or not rows:
            return 0

        texts = [str(row.get("chunk_text") or "") for row in rows if isinstance(row, dict)]
        embeddings = self.embed_texts(texts)
        saved = 0
        for row, embedding in zip(rows, embeddings, strict=False):
            if not isinstance(row, dict):
                continue
            row_id = str(row.get("id") or "")
            if not row_id:
                continue
            query_supabase_as_service_role(
                f"knowledge_chunks?id=eq.{row_id}",
                "PATCH",
                json_data={"embedding": embedding, "embedding_status": "EMBEDDED"},
            )
            saved += 1
        return saved
