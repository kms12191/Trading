from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from backend.services.ml_model_service import build_active_signal_payload
from backend.services.embedding_service import EmbeddingService
from backend.services.knowledge_repository import KnowledgeRepository
from backend.services.rag_retrieval_service import RagRetrievalService


SignalPayloadBuilder = Callable[..., dict | None]
EvidenceProvider = Callable[[str, str, str, int], list[dict]]


@dataclass(frozen=True, slots=True)
class RecommendationConfig:
    default_limit: int = 5
    min_signal_score: float = 10.0
    max_risk_probability: float = 0.65


class ChatbotRecommendationService:
    """챗봇 추천 요청을 활성 ML 신호 기반 후보 목록으로 변환합니다."""

    def __init__(
        self,
        signal_payload_builder: SignalPayloadBuilder = build_active_signal_payload,
        evidence_provider: EvidenceProvider | None = None,
        config: RecommendationConfig | None = None,
    ) -> None:
        self.signal_payload_builder = signal_payload_builder
        self.evidence_provider = evidence_provider or build_default_rag_evidence_provider()
        self.config = config or RecommendationConfig()

    def recommend(self, auth_header: str, message: str) -> dict:
        asset_key = self._detect_asset_key(message)
        payload = self.signal_payload_builder(
            asset_key=asset_key,
            auth_header=auth_header,
            position="LONG",
            min_signal_score=self.config.min_signal_score,
            limit=max(self.config.default_limit * 4, 20),
        )
        if not payload:
            return {
                "reply": "활성 예측 결과를 찾지 못했습니다. ML 예측 파일과 서빙 모델 상태를 먼저 확인해 주세요.",
                "data": {"source": "ML_ACTIVE_SIGNAL", "items": [], "reason": "missing_active_predictions"},
            }

        candidates = self._select_candidates(payload.get("predictions") or [])
        limited = [
            self._attach_evidence(auth_header, message, item)
            for item in candidates[: self.config.default_limit]
        ]
        if not limited:
            return {
                "reply": "현재 기준으로 매수 후보로 제시할 만한 신호가 없습니다. 무리한 진입보다 관망이 적절합니다.",
                "data": {
                    "source": "ML_ACTIVE_SIGNAL",
                    "asset_key": asset_key,
                    "model_version": payload.get("model_version"),
                    "items": [],
                    "performance": payload.get("performance") or {},
                },
            }

        lines = []
        for index, item in enumerate(limited, start=1):
            name = item.get("display_name") or item.get("name") or item.get("symbol")
            symbol = item.get("symbol")
            score = _format_number(item.get("signal_score"))
            up = _format_probability(item.get("up_probability"))
            risk = _format_probability(item.get("risk_probability"))
            reason = item.get("reason_summary") or "활성 ML 신호 기준으로 관찰할 만한 후보입니다."
            lines.append(f"{index}. {name}({symbol}) - 점수 {score}, 상승 {up}, 위험 {risk}\n   {reason}")
            evidence_text = self._format_evidence_line(item.get("evidence") or [])
            if evidence_text:
                lines.append(f"   {evidence_text}")

        return {
            "reply": (
                "활성 ML 신호 기준 추천 후보입니다. 주문 실행 근거가 아니라 검토 출발점으로 보세요.\n"
                + "\n".join(lines)
            ),
            "data": {
                "source": "ML_ACTIVE_SIGNAL",
                "asset_key": asset_key,
                "model_version": payload.get("model_version"),
                "items": limited,
                "citations": self._build_citations(limited),
                "performance": payload.get("performance") or {},
            },
        }

    def _select_candidates(self, rows: list[dict]) -> list[dict]:
        candidates = []
        for row in rows:
            grade = str(row.get("signal_grade") or "").upper()
            risk_probability = _to_float(row.get("risk_probability"))
            signal_score = _to_float(row.get("signal_score"))
            if grade == "RISKY":
                continue
            if risk_probability is not None and risk_probability >= self.config.max_risk_probability:
                continue
            if signal_score is None or signal_score < self.config.min_signal_score:
                continue
            candidates.append(row)

        candidates.sort(
            key=lambda row: (
                1 if str(row.get("signal_grade") or "").upper() == "STRONG_BUY_CANDIDATE" else 0,
                _to_float(row.get("signal_score")) or -1e9,
                -(_to_float(row.get("risk_probability")) or 0),
            ),
            reverse=True,
        )
        return candidates

    def _attach_evidence(self, auth_header: str, message: str, item: dict) -> dict:
        symbol = str(item.get("symbol") or "").upper()
        display_name = str(item.get("display_name") or item.get("name") or symbol)
        if not symbol:
            return {**item, "evidence": []}
        question = f"{display_name} {symbol} 추천 근거 최근 공시 리스크 투자노트 {message}"
        try:
            evidence = self.evidence_provider(auth_header, symbol, question, 2)
        except Exception:
            evidence = []
        return {**item, "evidence": [self._compact_evidence(row) for row in evidence[:2]]}

    @staticmethod
    def _compact_evidence(row: dict) -> dict:
        chunk_text = str(row.get("chunk_text") or "").strip()
        if len(chunk_text) > 140:
            chunk_text = chunk_text[:137].rstrip() + "..."
        return {
            "source_type": row.get("source_type"),
            "source_id": row.get("source_id"),
            "summary": chunk_text,
            "similarity": row.get("similarity"),
            "metadata": row.get("metadata") or {},
        }

    @staticmethod
    def _format_evidence_line(evidence_rows: list[dict]) -> str:
        if not evidence_rows:
            return ""
        first = evidence_rows[0]
        source_type = first.get("source_type") or "RAG"
        source_id = first.get("source_id") or "-"
        summary = first.get("summary") or ""
        return f"근거: {source_type} {source_id} - {summary}"

    @staticmethod
    def _build_citations(items: list[dict]) -> list[dict]:
        citations = []
        seen = set()
        for item in items:
            symbol = str(item.get("symbol") or "").upper()
            title = str(item.get("display_name") or item.get("name") or symbol).strip()
            for evidence in item.get("evidence") or []:
                source_type = evidence.get("source_type")
                source_id = evidence.get("source_id")
                key = (source_type, source_id, symbol)
                if key in seen:
                    continue
                seen.add(key)
                citations.append({
                    "source_type": source_type,
                    "source_id": source_id,
                    "title": title,
                    "summary": evidence.get("summary"),
                    "similarity": evidence.get("similarity"),
                    "symbol": symbol,
                    "metadata": evidence.get("metadata") or {},
                })
        return citations[:10]

    @staticmethod
    def _detect_asset_key(message: str) -> str:
        text = str(message or "").upper()
        if "코인" in message or "CRYPTO" in text:
            return "crypto"
        if "미국" in message or "해외" in message or "US" in text:
            return "us_stock"
        if "국내" in message or "한국" in message or "KR" in text:
            return "kr_stock"
        return "kr_stock"


def _to_float(value) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _format_number(value) -> str:
    number = _to_float(value)
    return "-" if number is None else f"{number:.2f}"


def _format_probability(value) -> str:
    number = _to_float(value)
    return "-" if number is None else f"{number * 100:.1f}%"


def build_default_rag_evidence_provider() -> EvidenceProvider:
    retrieval_service = RagRetrievalService(EmbeddingService(), KnowledgeRepository())

    def provider(auth_header: str, symbol: str, question: str, limit: int) -> list[dict]:
        return retrieval_service.retrieve_context(
            user_id=None,
            question=question,
            symbol=symbol,
            market="KR",
            source_types=["DISCLOSURE", "OBSIDIAN", "APP_NOTE"],
            limit=limit,
        )

    return provider
