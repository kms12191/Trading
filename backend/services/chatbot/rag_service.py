import os

import requests

from backend.services.supabase_client import safe_query_supabase


OPENAI_EMBEDDINGS_URL = "https://api.openai.com/v1/embeddings"


class ChatbotRAGService:
    """knowledge_chunks pgvector 검색 결과를 챗봇 참고자료로 변환합니다."""

    def __init__(self):
        self.api_key = os.getenv("OPENAI_API_KEY", "").strip()
        self.embedding_model = os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small").strip()
        self.top_k = self._read_int_env("CHATBOT_RAG_TOP_K", 5)
        self.max_context_chars = self._read_int_env("CHATBOT_RAG_MAX_CONTEXT_CHARS", 6000)
        self.timeout_seconds = self._read_int_env("CHATBOT_OPENAI_TIMEOUT_SECONDS", 30)

    @staticmethod
    def _read_int_env(name: str, default: int) -> int:
        try:
            value = int(os.getenv(name, default))
            return value if value > 0 else default
        except (TypeError, ValueError):
            return default

    def _create_embedding(self, text: str) -> list[float]:
        if not self.api_key:
            return []

        response = requests.post(
            OPENAI_EMBEDDINGS_URL,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": self.embedding_model,
                "input": text,
            },
            timeout=self.timeout_seconds,
        )
        if response.status_code >= 400:
            raise RuntimeError(f"OpenAI embedding request failed: HTTP {response.status_code}")

        data = response.json()
        embedding = ((data.get("data") or [{}])[0] or {}).get("embedding") or []
        return embedding if isinstance(embedding, list) else []

    def _match_chunks(self, auth_header: str, query_embedding: list[float], user_id: str | None) -> list[dict]:
        rows = safe_query_supabase(
            auth_header,
            "rpc/match_knowledge_chunks",
            "POST",
            json_data={
                "query_embedding": query_embedding,
                "match_user_id": user_id,
                "match_count": self.top_k,
            },
        )
        return rows if isinstance(rows, list) else []

    def build_context(self, auth_header: str | None, user_id: str | None, query: str) -> tuple[str, list[dict]]:
        text = str(query or "").strip()
        if not auth_header or not text:
            return "", []

        try:
            embedding = self._create_embedding(text)
            if not embedding:
                return "", []
            rows = self._match_chunks(auth_header, embedding, user_id)
        except Exception:
            return "", []

        context_parts = []
        total_length = 0
        for index, row in enumerate(rows[: self.top_k], start=1):
            chunk_text = str(row.get("chunk_text") or "").strip()
            if not chunk_text:
                continue
            source_type = str(row.get("source_type") or "UNKNOWN").strip()
            source_id = str(row.get("source_id") or "").strip()
            similarity = row.get("similarity")
            header = f"[참고자료 {index}] source_type={source_type}"
            if source_id:
                header += f", source_id={source_id}"
            if similarity is not None:
                header += f", similarity={similarity}"
            block = f"{header}\n{chunk_text}"
            if total_length + len(block) > self.max_context_chars:
                break
            context_parts.append(block)
            total_length += len(block)

        if not context_parts:
            return "", rows

        return "\n\n".join([
            "RAG 참고자료:",
            "아래 자료는 사용자 질문에 답할 때 참고하되, 자료에 없는 내용은 추정이라고 밝히고 민감정보는 노출하지 않습니다.",
            *context_parts,
        ]), rows
