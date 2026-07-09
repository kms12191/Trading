from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, TypeAlias

JsonValue: TypeAlias = str | int | float | bool | None | list["JsonValue"] | dict[str, "JsonValue"]
JsonObject: TypeAlias = dict[str, JsonValue]


class EmbeddingProvider(Protocol):
    def embed_query(self, text: str) -> list[float]:
        ...


class KnowledgeMatcher(Protocol):
    def match_knowledge_chunks(self, payload: JsonObject) -> list[JsonObject]:
        ...


@dataclass(frozen=True, slots=True)
class RetrievalQuery:
    user_id: str | None
    question: str
    symbol: str | None = None
    market: str | None = None
    source_types: list[str] | None = None
    limit: int = 12


class RagRetrievalService:
    def __init__(self, embedding_service: EmbeddingProvider, knowledge_repository: KnowledgeMatcher) -> None:
        self.embedding_service = embedding_service
        self.knowledge_repository = knowledge_repository

    def retrieve(self, query: RetrievalQuery) -> list[JsonObject]:
        embedding = self.embedding_service.embed_query(query.question)
        payload: JsonObject = {
            "query_embedding": embedding,
            "match_user_id": query.user_id,
            "match_symbol": query.symbol,
            "match_market": query.market,
            "match_source_types": query.source_types,
            "match_count": query.limit,
        }
        return self.knowledge_repository.match_knowledge_chunks(payload)

    def retrieve_context(
        self,
        user_id: str | None,
        question: str,
        symbol: str | None = None,
        market: str | None = None,
        source_types: list[str] | None = None,
        limit: int = 12,
    ) -> list[JsonObject]:
        return self.retrieve(
            RetrievalQuery(
                user_id=user_id,
                question=question,
                symbol=symbol,
                market=market,
                source_types=source_types,
                limit=limit,
            )
        )
