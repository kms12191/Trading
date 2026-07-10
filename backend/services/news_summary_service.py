import os
import re
from typing import Any

import requests

OPENAI_CHAT_COMPLETIONS_URL = "https://api.openai.com/v1/chat/completions"
GEMINI_INTERACTIONS_URL = "https://generativelanguage.googleapis.com/v1beta/interactions"


class NewsSummaryService:
    def __init__(self) -> None:
        self.api_key = os.getenv("OPENAI_API_KEY", "")
        self.model = os.getenv("NEWS_SUMMARY_MODEL", "gpt-4o-mini")
        self.gemini_api_key = os.getenv("GEMINI_API_KEY", "")
        self.gemini_primary_model = os.getenv(
            "NEWS_SUMMARY_GEMINI_PRIMARY_MODEL",
            os.getenv("DART_GEMINI_PRIMARY_MODEL", "gemini-3.5-flash"),
        )
        self.gemini_fallback_model = os.getenv(
            "NEWS_SUMMARY_GEMINI_FALLBACK_MODEL",
            os.getenv("DART_GEMINI_FALLBACK_MODEL", "gemini-3.1-flash-lite"),
        )
        self.prompt_version = os.getenv("NEWS_SUMMARY_PROMPT_VERSION", "v1")
        self.timeout_seconds = int(os.getenv("NEWS_SUMMARY_TIMEOUT_SECONDS", "30"))

    @property
    def enabled(self) -> bool:
        return bool(self.api_key or self.gemini_api_key)

    def summarize(self, article: dict[str, Any]) -> dict[str, str]:
        prompt = self._build_prompt(article)

        openai_summary = self._request_openai_summary(prompt)
        if openai_summary:
            return {
                "ai_summary": openai_summary,
                "ai_summary_model": self.model,
                "ai_summary_prompt_version": self.prompt_version,
            }

        gemini_summary = self._request_gemini_summary(prompt)
        if gemini_summary:
            summary, model = gemini_summary
            return {
                "ai_summary": summary,
                "ai_summary_model": model,
                "ai_summary_prompt_version": self.prompt_version,
            }

        return {
            "ai_summary": self._fallback_summary(article),
            "ai_summary_model": "fallback",
            "ai_summary_prompt_version": self.prompt_version,
        }

    def _request_openai_summary(self, prompt: str) -> str:
        if not self.api_key:
            return ""

        try:
            response = requests.post(
                OPENAI_CHAT_COMPLETIONS_URL,
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
                                "너는 주식/코인 뉴스 게시판용 요약기다. "
                                "항상 한국어로만 답하고, 반드시 3줄로만 출력한다. "
                                "투자 권유나 가격 예측 없이 확인된 사실 중심으로 요약한다."
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
        except (requests.RequestException, ValueError):
            return ""

        if not isinstance(payload, dict):
            return ""
        return self._normalize_summary(self._extract_openai_content(payload))

    def _request_gemini_summary(self, prompt: str) -> tuple[str, str] | None:
        if not self.gemini_api_key:
            return None

        for model in self._gemini_models():
            try:
                response = requests.post(
                    GEMINI_INTERACTIONS_URL,
                    headers={
                        "x-goog-api-key": self.gemini_api_key,
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": model,
                        "system_instruction": (
                            "너는 주식/코인 뉴스 게시판용 요약기다. "
                            "한국어 3줄로만 출력하고 투자 권유나 가격 예측은 하지 않는다."
                        ),
                        "input": prompt,
                        "generation_config": {
                            "temperature": 0.2,
                            "max_output_tokens": 220,
                        },
                    },
                    timeout=self.timeout_seconds,
                )
                response.raise_for_status()
                payload = response.json()
            except (requests.RequestException, ValueError):
                continue

            if not isinstance(payload, dict):
                continue
            summary = self._normalize_summary(self._extract_gemini_content(payload))
            if summary:
                return summary, model
        return None

    def _build_prompt(self, article: dict[str, Any]) -> str:
        title = self._clean(article.get("title", ""))
        summary = self._clean(article.get("summary", ""))
        company_name = self._clean(article.get("company_name", ""))
        symbol = self._clean(article.get("symbol", ""))
        market = self._clean(article.get("market", ""))
        source = self._clean(article.get("source", ""))
        raw_payload = article.get("raw_payload") or {}
        category = self._clean(raw_payload.get("query_category", "")) if isinstance(raw_payload, dict) else ""
        url = self._clean(article.get("url", ""))

        return (
            "아래 뉴스 기사를 3줄로 요약해줘.\n"
            "출력 조건:\n"
            "1. 반드시 한국어\n"
            "2. 정확히 3줄\n"
            "3. 각 줄은 1문장\n"
            "4. 각 줄은 '1. ', '2. ', '3. '로 시작\n"
            "5. 투자 권유, 매수/매도 권유, 주가 예측 금지\n"
            "6. 제목과 내용이 부족하면 부족하다고 짧게 언급\n\n"
            f"제목: {title}\n"
            f"본문 요약: {summary}\n"
            f"종목명: {company_name}\n"
            f"심볼: {symbol}\n"
            f"시장: {market}\n"
            f"소스: {source}\n"
            f"카테고리: {category}\n"
            f"링크: {url}\n"
        )

    def _extract_openai_content(self, payload: dict[str, Any]) -> str:
        choices = payload.get("choices") or []
        if not choices:
            return ""
        first_choice = choices[0]
        if not isinstance(first_choice, dict):
            return ""
        message = first_choice.get("message") or {}
        if not isinstance(message, dict):
            return ""
        content = message.get("content")
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            chunks: list[str] = []
            for item in content:
                if isinstance(item, dict) and item.get("type") == "text":
                    text = item.get("text") or ""
                    if text:
                        chunks.append(str(text))
            return "\n".join(chunks)
        return ""

    def _extract_gemini_content(self, payload: dict[str, Any]) -> str:
        text = self._clean(payload.get("output_text"))
        if text:
            return text

        chunks: list[str] = []
        for candidate in payload.get("candidates") or []:
            if not isinstance(candidate, dict):
                continue
            content = candidate.get("content") or {}
            if not isinstance(content, dict):
                continue
            for part in content.get("parts") or []:
                if isinstance(part, dict):
                    chunks.append(str(part.get("text") or ""))

        for step in payload.get("steps") or []:
            if not isinstance(step, dict):
                continue
            for item in step.get("content") or step.get("contents") or []:
                if isinstance(item, dict):
                    chunks.append(str(item.get("text") or ""))
        return self._clean(" ".join(chunks))

    def _gemini_models(self) -> list[str]:
        models: list[str] = []
        for model in [self.gemini_primary_model, self.gemini_fallback_model]:
            normalized = str(model or "").strip()
            if normalized and normalized not in models:
                models.append(normalized)
        return models

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
                f"2. {sentence}",
                "3. 원문과 공시, 실적 발표 여부를 함께 확인하세요.",
            ]
        )

    def _clean(self, value: Any) -> str:
        return re.sub(r"\s+", " ", str(value or "")).strip()
