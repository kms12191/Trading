import hashlib
from datetime import datetime, timezone
from typing import Any


class KnowledgeChunkService:
    """지식 노트를 검색/임베딩하기 좋은 작은 단위로 분할합니다."""

    def split_text(self, text: str, max_chars: int = 900, overlap_chars: int = 120) -> list[str]:
        normalized = "\n".join(line.rstrip() for line in str(text or "").splitlines()).strip()
        if not normalized:
            return []
        if len(normalized) <= max_chars:
            return [normalized]

        paragraphs = [paragraph.strip() for paragraph in normalized.split("\n\n") if paragraph.strip()]
        chunks: list[str] = []
        current = ""

        for paragraph in paragraphs:
            if len(paragraph) > max_chars:
                if current:
                    chunks.append(current.strip())
                    current = ""
                chunks.extend(self._split_long_block(paragraph, max_chars, overlap_chars))
                continue

            candidate = f"{current}\n\n{paragraph}".strip() if current else paragraph
            if len(candidate) <= max_chars:
                current = candidate
                continue

            if current:
                chunks.append(current.strip())
            current = paragraph

        if current:
            chunks.append(current.strip())

        return chunks

    def build_chunks(
        self,
        user_id: str | None,
        source_type: str,
        source_id: str,
        text: str,
        symbol: str | None = None,
        market: str | None = None,
        metadata: dict[str, Any] | None = None,
        importance_score: float = 0.5,
        freshness_score: float = 0.5,
    ) -> list[dict[str, Any]]:
        chunks = self.split_text(text)
        now = datetime.now(timezone.utc).isoformat()
        rows: list[dict[str, Any]] = []

        for index, chunk_text in enumerate(chunks):
            content_hash = hashlib.sha256(
                f"{source_type}|{source_id}|{index}|{chunk_text}".encode("utf-8")
            ).hexdigest()
            rows.append(
                {
                    "user_id": user_id,
                    "source_type": source_type,
                    "source_id": source_id,
                    "symbol": symbol,
                    "market": market,
                    "chunk_index": index,
                    "chunk_text": chunk_text,
                    "embedding": None,
                    "embedding_status": "PENDING",
                    "metadata": metadata or {},
                    "importance_score": importance_score,
                    "freshness_score": freshness_score,
                    "content_hash": content_hash,
                    "updated_at": now,
                }
            )

        return rows

    def _split_long_block(self, text: str, max_chars: int, overlap_chars: int) -> list[str]:
        safe_overlap = max(0, min(overlap_chars, max_chars - 1))
        chunks: list[str] = []
        start = 0
        while start < len(text):
            end = min(start + max_chars, len(text))
            candidate = text[start:end].strip()
            if candidate:
                chunks.append(candidate)
            if end == len(text):
                break
            start = max(end - safe_overlap, start + 1)
        return chunks
