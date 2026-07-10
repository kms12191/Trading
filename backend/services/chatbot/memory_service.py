from __future__ import annotations

import re
from dataclasses import asdict, dataclass

from backend.services.knowledge_repository import KnowledgeRepository


@dataclass(frozen=True, slots=True)
class MemoryCandidate:
    memory_type: str
    content: str
    symbol: str | None = None
    confidence: float = 0.7
    metadata: dict | None = None


SYMBOL_ALIASES = {
    "삼성전자": ("005930", "삼성전자"),
    "삼전": ("005930", "삼성전자"),
    "하이닉스": ("000660", "SK하이닉스"),
    "SK하이닉스": ("000660", "SK하이닉스"),
    "비트코인": ("BTC", "비트코인"),
    "비트": ("BTC", "비트코인"),
    "이더리움": ("ETH", "이더리움"),
    "이더": ("ETH", "이더리움"),
    "리플": ("XRP", "리플"),
    "XRP": ("XRP", "리플"),
}


class ChatbotMemoryService:
    """챗봇 대화에서 명시적인 사용자 투자 메모리만 추출해 저장합니다."""

    def __init__(self, repository: KnowledgeRepository | None = None) -> None:
        self.repository = repository or KnowledgeRepository()

    def extract_memory_candidates(self, user_message: str, assistant_message: str = "") -> list[MemoryCandidate]:
        text = str(user_message or "").strip()
        if not text or self._is_plain_order_request(text):
            return []

        candidates: list[MemoryCandidate] = []
        candidates.extend(self._extract_risk_preferences(text))
        candidates.extend(self._extract_favorite_symbols(text))
        candidates.extend(self._extract_answer_preferences(text))
        candidates.extend(self._extract_repeated_mistakes(text))
        candidates.extend(self._extract_investment_principles(text))
        return self._deduplicate(candidates)

    def capture_from_exchange(
        self,
        auth_header: str,
        user_id: str,
        user_message: str,
        assistant_message: str,
    ) -> dict:
        if not auth_header or not user_id:
            return {"captured_count": 0}

        candidates = self.extract_memory_candidates(user_message, assistant_message)
        saved = []
        for candidate in candidates:
            payload = asdict(candidate)
            payload["metadata"] = {
                **(candidate.metadata or {}),
                "source_message": str(user_message or "")[:500],
            }
            try:
                saved.append(self.repository.upsert_memory_fact(auth_header, user_id, payload))
            except Exception:
                continue
        return {"captured_count": len(saved), "items": saved}

    @staticmethod
    def _is_plain_order_request(text: str) -> bool:
        return bool(
            re.search(r"\d+(?:\.\d+)?\s*(?:만원|천원|원|주|개|%)", text)
            and any(keyword in text for keyword in ["사줘", "매수", "구매", "팔아줘", "매도"])
        )

    @staticmethod
    def _extract_risk_preferences(text: str) -> list[MemoryCandidate]:
        candidates = []
        if "코인" in text and any(keyword in text for keyword in ["무서", "무섭", "위험", "피하고", "싫어", "부담"]):
            candidates.append(MemoryCandidate(
                memory_type="risk_preference",
                content="사용자는 코인 리스크를 회피하는 편입니다.",
                confidence=0.86,
            ))
        if any(keyword in text for keyword in ["국내주식 위주", "국내 주식 위주", "한국주식 위주"]):
            candidates.append(MemoryCandidate(
                memory_type="risk_preference",
                content="사용자는 국내주식 위주 검토를 선호합니다.",
                confidence=0.82,
            ))
        if re.search(r"실거래.*(?:10만원|십만원|소액|작게)", text):
            candidates.append(MemoryCandidate(
                memory_type="risk_preference",
                content="사용자는 실거래를 소액 중심으로 제한하길 선호합니다.",
                confidence=0.8,
            ))
        return candidates

    @staticmethod
    def _extract_favorite_symbols(text: str) -> list[MemoryCandidate]:
        if not any(keyword in text for keyword in ["관심", "자주", "위주로 보고", "챙겨"]):
            return []
        candidates = []
        for alias, (symbol, display_name) in SYMBOL_ALIASES.items():
            if alias in text:
                candidates.append(MemoryCandidate(
                    memory_type="favorite_symbol",
                    content=f"사용자는 {display_name}({symbol})를 관심 있게 봅니다.",
                    symbol=symbol,
                    confidence=0.84,
                ))
        return candidates

    @staticmethod
    def _extract_answer_preferences(text: str) -> list[MemoryCandidate]:
        if any(keyword in text for keyword in ["짧게", "간단히", "요약해서"]):
            return [MemoryCandidate(
                memory_type="answer_preference",
                content="사용자는 짧은 답변과 요약형 설명을 선호합니다.",
                confidence=0.78,
            )]
        return []

    @staticmethod
    def _extract_repeated_mistakes(text: str) -> list[MemoryCandidate]:
        if "손절" in text and any(keyword in text for keyword in ["못해", "늦", "어려"]):
            return [MemoryCandidate(
                memory_type="repeated_mistake",
                content="사용자는 손절 판단이 늦어지는 실수를 반복할 수 있습니다.",
                confidence=0.82,
            )]
        if "추격매수" in text and any(keyword in text for keyword in ["자주", "실수", "못 참"]):
            return [MemoryCandidate(
                memory_type="repeated_mistake",
                content="사용자는 추격매수 충동을 주의해야 합니다.",
                confidence=0.8,
            )]
        return []

    @staticmethod
    def _extract_investment_principles(text: str) -> list[MemoryCandidate]:
        if "분할매수" in text and any(keyword in text for keyword in ["원칙", "선호", "좋아"]):
            return [MemoryCandidate(
                memory_type="investment_principle",
                content="사용자는 분할매수를 투자 원칙으로 선호합니다.",
                confidence=0.78,
            )]
        if "스윙" in text and any(keyword in text for keyword in ["좋아", "선호", "위주"]):
            return [MemoryCandidate(
                memory_type="investment_principle",
                content="사용자는 단타보다 스윙 관점의 매매를 선호합니다.",
                confidence=0.78,
            )]
        return []

    @staticmethod
    def _deduplicate(candidates: list[MemoryCandidate]) -> list[MemoryCandidate]:
        seen = set()
        unique = []
        for candidate in candidates:
            key = (candidate.memory_type, candidate.content, candidate.symbol)
            if key in seen:
                continue
            seen.add(key)
            unique.append(candidate)
        return unique
