import os
import re
from typing import Any

import requests


class NewsSummaryService:
    def __init__(self) -> None:
        self.api_key = os.getenv("OPENAI_API_KEY", "")
        self.model = os.getenv("NEWS_SUMMARY_MODEL", "gpt-4o-mini")
        self.prompt_version = os.getenv("NEWS_SUMMARY_PROMPT_VERSION", "v1")
        self.timeout_seconds = int(os.getenv("NEWS_SUMMARY_TIMEOUT_SECONDS", "30"))

    @property
    def enabled(self) -> bool:
        return bool(self.api_key)

    def summarize(self, article: dict[str, Any]) -> dict[str, str]:
        if not self.enabled:
            return {
                "ai_summary": self._fallback_summary(article),
                "ai_summary_model": "fallback",
                "ai_summary_prompt_version": self.prompt_version,
            }

        prompt = self._build_prompt(article)
        response = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": self.model,
                "messages": [
                    {
                        "role": "system",
                        "content": (
                            "너는 주식 뉴스 게시판용 요약기다. "
                            "항상 한국어로만 답하고, 반드시 3줄로만 출력한다. "
                            "각 줄은 짧고 핵심적이어야 하며, 줄마다 한 문장만 쓴다. "
                            "형식은 '1. ...', '2. ...', '3. ...'로 맞춘다. "
                            "투자 조언처럼 들리지 않게 사실 중심으로 요약한다."
                        ),
                    },
                    {"role": "user", "content": prompt},
                ],
                "temperature": 0.2,
                "max_tokens": 220,
            },
            timeout=self.timeout_seconds,
        )
        response.raise_for_status()
        payload = response.json()
        text = self._extract_content(payload)
        summary = self._normalize_summary(text) or self._fallback_summary(article)
        return {
            "ai_summary": summary,
            "ai_summary_model": self.model,
            "ai_summary_prompt_version": self.prompt_version,
        }

    def _build_prompt(self, article: dict[str, Any]) -> str:
        title = self._clean(article.get("title", ""))
        summary = self._clean(article.get("summary", ""))
        company_name = self._clean(article.get("company_name", ""))
        symbol = self._clean(article.get("symbol", ""))
        market = self._clean(article.get("market", ""))
        source = self._clean(article.get("source", ""))
        category = self._clean((article.get("raw_payload") or {}).get("query_category", ""))
        url = self._clean(article.get("url", ""))

        return (
            "아래 주식 뉴스 기사를 3줄로 요약해줘.\n"
            "출력 조건:\n"
            "1. 반드시 한국어\n"
            "2. 정확히 3줄\n"
            "3. 각 줄은 1문장만\n"
            "4. 각 줄은 '1. ', '2. ', '3. '로 시작\n"
            "5. 첫 줄은 핵심 사실, 두 번째 줄은 주가/섹터 영향, 세 번째 줄은 확인 포인트\n"
            "6. 과장이나 투자 권유 금지\n"
            "7. 제목과 내용이 부족하면 부족하다고 짧게 언급\n\n"
            f"제목: {title}\n"
            f"본문 요약: {summary}\n"
            f"종목명: {company_name}\n"
            f"심볼: {symbol}\n"
            f"시장: {market}\n"
            f"소스: {source}\n"
            f"카테고리: {category}\n"
            f"링크: {url}\n"
        )

    def _extract_content(self, payload: dict[str, Any]) -> str:
        choices = payload.get("choices") or []
        if not choices:
            return ""
        message = choices[0].get("message") or {}
        content = message.get("content")
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            chunks = []
            for item in content:
                if isinstance(item, dict) and item.get("type") == "text":
                    text = item.get("text") or ""
                    if text:
                        chunks.append(text)
            return "\n".join(chunks)
        return ""

    def _normalize_summary(self, text: str) -> str:
        if not text:
            return ""
        lines = [re.sub(r"\s+", " ", line).strip() for line in text.splitlines()]
        lines = [line for line in lines if line]
        if not lines:
            return ""

        normalized: list[str] = []
        for line in lines:
            normalized.append(line if re.match(r"^\d+\.", line) else f"{len(normalized) + 1}. {line}")
            if len(normalized) == 3:
                break

        while len(normalized) < 3:
            normalized.append(f"{len(normalized) + 1}. -")

        return "\n".join(normalized[:3])

    def _fallback_summary(self, article: dict[str, Any]) -> str:
        title = self._clean(article.get("title", ""))
        summary = self._clean(article.get("summary", ""))
        company_name = self._clean(article.get("company_name", ""))

        sentence = summary or title or "기사 정보가 부족합니다."
        sentence = re.sub(r"\s+", " ", sentence).strip()
        if len(sentence) > 80:
            sentence = sentence[:79].rstrip() + "..."

        subject = company_name or "해당 종목"
        return "\n".join(
            [
                f"1. {title or sentence}",
                f"2. {subject} 관련 흐름을 함께 봐야 합니다.",
                f"3. 원문과 수급, 실적 발표 여부를 확인하세요.",
            ]
        )

    def _clean(self, value: Any) -> str:
        return re.sub(r"\s+", " ", str(value or "")).strip()
