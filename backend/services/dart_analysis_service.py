import os
import re
import zipfile
import json
from datetime import datetime, timezone
from io import BytesIO
from typing import Any
from xml.etree import ElementTree as ET

import requests

from backend.services.dart_repository import DartRepository


DART_DOCUMENT_URL = "https://opendart.fss.or.kr/api/document.xml"
DART_ANALYSIS_VERSION = "v3.33"
OPENAI_CHAT_COMPLETIONS_URL = "https://api.openai.com/v1/chat/completions"
GEMINI_INTERACTIONS_URL = "https://generativelanguage.googleapis.com/v1beta/interactions"
ALLOWED_SENTIMENTS = {"positive", "negative", "caution", "info"}
ALLOWED_CONFIDENCES = {"high", "medium", "low"}

DART_ANALYSIS_SCHEMAS: dict[str, dict[str, Any]] = {
    "유상증자 발행가액 확정": {
        "required": ["확정발행가액", "발행주식수", "확정일"],
        "optional": ["할인율", "증자방식", "청약예정일", "납입일", "상장예정일"],
        "summary_limit": 6,
    },
    "무상증자": {
        "required": ["보통주 신주", "1주당 배정", "배정기준일", "상장예정일"],
        "optional": ["기타주식 신주", "전입재원"],
        "summary_limit": 6,
    },
    "권리락": {
        "required": ["기준가", "권리락 실시일", "사유"],
        "optional": ["주권종류", "단축코드"],
        "summary_limit": 5,
    },
    "수주·공급계약": {
        "required": ["계약금액", "계약상대", "계약기간"],
        "optional": ["매출액대비", "최근매출액"],
        "summary_limit": 5,
    },
    "공급계약 해지": {
        "required": ["해지금액", "계약상대", "해지사유"],
        "optional": ["매출액대비", "해지일자"],
        "summary_limit": 5,
    },
    "자금조달·증권신고서": {
        "required": ["증자방식", "발행가액", "신주의 수"],
        "optional": ["자금의 사용목적", "자금조달의 목적", "납입일", "상장예정일"],
        "summary_limit": 6,
    },
    "주식관련사채": {
        "required": ["사채의 권면총액", "전환가액"],
        "optional": ["자금의 사용목적", "전환청구기간", "표면이자율", "만기이자율"],
        "summary_limit": 6,
    },
    "자금조달·증권발행": {
        "required": ["발행가액", "신주의 수"],
        "optional": ["증자방식", "납입일", "상장예정일"],
        "summary_limit": 5,
    },
    "종속회사 유상증자": {
        "required": ["신주의 수", "발행가액", "증자방식"],
        "optional": ["자금조달의 목적", "납입일", "상장예정일"],
        "summary_limit": 6,
    },
    "DR 발행": {
        "required": ["DR 발행총액", "신주 발행가액", "납입일"],
        "optional": ["DR 발행형태", "원주 전환비율", "자금조달의 목적", "상장예정일"],
        "summary_limit": 7,
    },
    "증권 발행결과": {
        "required": ["실제발행주식수", "실제발행금액", "납입일"],
        "optional": ["발행방법", "발행예정주식수", "발행예정금액", "상장예정일"],
        "summary_limit": 6,
    },
    "채무증권 발행": {
        "required": ["발행총액", "자금조달의 목적"],
        "optional": ["표면이자율", "만기이자율", "사채만기일", "이자율", "발행수익률"],
        "summary_limit": 6,
    },
    "배당": {
        "required": ["1주당 배당금", "배당금총액"],
        "optional": ["시가배당율", "배당기준일", "배당금지급 예정일자"],
        "summary_limit": 5,
    },
    "주주환원": {
        "required": ["취득예정금액"],
        "optional": ["소각예정금액", "취득예정주식", "취득예상기간"],
        "summary_limit": 5,
    },
    "자사주 신탁 해지": {
        "required": ["해지금액"],
        "optional": ["계약상대", "해지사유", "해지일자"],
        "summary_limit": 5,
    },
    "공개매수": {
        "required": ["매수가격", "매수예정수량"],
        "optional": ["공개매수자", "공개매수기간", "매수목적"],
        "summary_limit": 5,
    },
    "주식매수선택권": {
        "required": ["행사주식수", "행사가격"],
        "optional": ["부여주식수", "부여대상", "행사기간", "부여일", "상장예정일"],
        "summary_limit": 5,
    },
    "전환가액 조정": {
        "required": ["조정후 전환가액"],
        "optional": ["조정전 전환가액", "조정사유", "적용일"],
        "summary_limit": 5,
    },
    "자사주 소각": {
        "required": ["소각예정금액", "소각예정주식"],
        "optional": ["소각예정일", "소각목적"],
        "summary_limit": 5,
    },
    "자기주식 처분": {
        "required": ["처분예정금액", "처분목적"],
        "optional": ["처분예정주식", "처분예정기간"],
        "summary_limit": 5,
    },
    "대표이사 변경": {
        "required": ["변경후 대표이사", "변경사유"],
        "optional": ["변경전 대표이사", "변경일"],
        "summary_limit": 4,
    },
    "신규 시설투자": {
        "required": ["투자금액", "투자목적"],
        "optional": ["자기자본대비", "투자기간", "투자대상"],
        "summary_limit": 5,
    },
    "영업정지": {
        "required": ["영업정지금액", "영업정지사유"],
        "optional": ["매출액대비", "영업정지기간", "향후대책"],
        "summary_limit": 5,
    },
    "감자": {
        "required": ["감자비율", "감자기준일"],
        "optional": ["감자주식수", "감자사유", "감자방법", "상장예정일"],
        "summary_limit": 6,
    },
    "액면분할": {
        "required": ["분할비율", "신주권상장예정일"],
        "optional": ["매매거래정지기간", "효력발생일"],
        "summary_limit": 4,
    },
    "액면병합": {
        "required": ["병합비율", "신주권상장예정일"],
        "optional": ["매매거래정지기간", "효력발생일"],
        "summary_limit": 4,
    },
    "거래정지": {
        "required": ["거래정지사유"],
        "optional": ["거래정지일", "해제일시", "시장구분"],
        "summary_limit": 5,
    },
    "상장폐지 위험": {
        "required": ["위험사유"],
        "optional": ["상장폐지사유", "개선기간", "심사일정"],
        "summary_limit": 5,
    },
    "관리종목 위험": {
        "required": ["지정사유"],
        "optional": ["해제사유", "시장조치", "심사일정"],
        "summary_limit": 5,
    },
    "불성실공시": {
        "required": ["지정사유"],
        "optional": ["벌점", "제재금", "지정일"],
        "summary_limit": 5,
    },
    "감사의견 위험": {
        "required": ["감사의견"],
        "optional": ["위험사유", "해소여부", "감사인"],
        "summary_limit": 5,
    },
    "중대재해": {
        "required": ["재해내용", "발생일자"],
        "optional": ["사망자 수", "부상자 수", "조치사항"],
        "summary_limit": 5,
    },
    "횡령·배임": {
        "required": ["발생금액", "자기자본대비"],
        "optional": ["발생사실", "향후대책"],
        "summary_limit": 5,
    },
    "회생절차": {
        "required": ["신청사유", "신청일자"],
        "optional": ["관할법원", "결정내용"],
        "summary_limit": 5,
    },
    "최대주주 변경": {
        "required": ["변경후 최대주주", "변경사유"],
        "optional": ["지분율", "변경일"],
        "summary_limit": 4,
    },
    "최대주주 변경 계약": {
        "required": ["변경예정 최대주주"],
        "optional": ["계약금액", "예정지분율", "변경예정일", "계약상대방"],
        "summary_limit": 5,
    },
    "합병": {
        "required": ["합병상대회사", "합병비율"],
        "optional": ["합병기일", "합병목적"],
        "summary_limit": 5,
    },
    "합병 종료": {
        "required": ["합병기일"],
        "optional": ["합병상대회사", "합병비율", "합병목적"],
        "summary_limit": 4,
    },
    "분할": {
        "required": ["분할신설회사", "분할기일"],
        "optional": ["분할목적"],
        "summary_limit": 4,
    },
    "소송": {
        "required": ["청구내용"],
        "optional": ["소송가액", "원고", "피고", "판결ㆍ결정내용"],
        "summary_limit": 5,
    },
    "채무보증": {
        "required": ["채무보증금액", "채무자", "자기자본대비"],
        "optional": ["채무보증기간", "채무보증 총 잔액", "채무(차입)금액", "채권자", "보증사유"],
        "summary_limit": 6,
    },
    "담보제공": {
        "required": ["담보제공금액", "담보제공대상"],
        "optional": ["자기자본대비", "담보제공기간", "담보제공사유"],
        "summary_limit": 6,
    },
    "단기차입금 증가": {
        "required": ["차입금액", "차입목적"],
        "optional": ["자기자본대비", "차입후 총차입금", "차입기간"],
        "summary_limit": 6,
    },
    "전환청구권 행사": {
        "required": ["행사주식수", "발행주식총수 대비", "전환가액"],
        "optional": ["청구금액", "상장예정일"],
        "summary_limit": 5,
    },
    "영업실적": {
        "required": ["매출액", "영업이익", "당기순이익"],
        "optional": ["전년동기대비", "직전분기대비"],
        "summary_limit": 5,
    },
    "손익구조 변동": {
        "required": ["매출액", "영업이익", "당기순이익"],
        "optional": ["변동사유", "전년대비"],
        "summary_limit": 5,
    },
    "기업가치 제고 계획": {
        "required": ["주주환원계획", "목표지표"],
        "optional": ["이행기간", "공시주기", "주요내용"],
        "summary_limit": 5,
    },
    "공정공시 중요정보": {
        "required": ["주요내용"],
        "optional": ["계약상대", "계약금액", "전망매출액", "전망영업이익", "추진일정"],
        "summary_limit": 5,
    },
    "타법인 주식 취득·처분": {
        "required": ["거래금액"],
        "optional": ["거래상대방", "거래목적", "취득예정일", "처분예정일", "자기자본대비"],
        "summary_limit": 6,
    },
    "투자판단 주요경영사항": {
        "required": ["주요내용"],
        "optional": ["계약상대", "계약금액", "추진일정", "투자목적"],
        "summary_limit": 5,
    },
    "조회공시 답변": {
        "required": ["답변내용"],
        "optional": ["조회공시요구일", "답변일", "진행사항"],
        "summary_limit": 4,
    },
}


class DartDisclosureAnalysisService:
    def __init__(self) -> None:
        self.api_key = os.getenv("DART_API_KEY", "")
        self.request_timeout_seconds = int(os.getenv("DART_REQUEST_TIMEOUT_SECONDS", "15"))
        self.openai_api_key = os.getenv("OPENAI_API_KEY", "")
        self.gemini_api_key = os.getenv("GEMINI_API_KEY", "")
        self.ai_enabled = os.getenv("DART_ANALYSIS_AI_ENABLED", "true").lower() == "true"
        self.ai_provider = os.getenv("DART_ANALYSIS_AI_PROVIDER", "openai").strip().lower()
        self.ai_model = os.getenv("DART_ANALYSIS_MODEL", "gpt-4o-mini")
        self.gemini_primary_model = os.getenv("DART_GEMINI_PRIMARY_MODEL", "gemini-3.5-flash")
        self.gemini_fallback_model = os.getenv("DART_GEMINI_FALLBACK_MODEL", "gemini-3.1-flash-lite")
        self.gemini_models = self._parse_gemini_models()
        self._gemini_model_cursor = 0
        self.ai_prompt_version = os.getenv("DART_ANALYSIS_PROMPT_VERSION", "v3")
        self.ai_timeout_seconds = int(os.getenv("DART_ANALYSIS_TIMEOUT_SECONDS", "30"))
        self.ai_excerpt_chars = int(os.getenv("DART_ANALYSIS_EXCERPT_CHARS", "4000"))
        self.repository = DartRepository()

    def ensure_analysis(self, rcept_no: str, force_refresh: bool = False) -> dict[str, Any]:
        clean_rcept_no = str(rcept_no or "").strip()
        if not clean_rcept_no:
            raise ValueError("공시 접수번호가 필요합니다.")

        cached = self.repository.get_disclosure_analysis(clean_rcept_no)
        cached_version = ((cached or {}).get("raw_payload") or {}).get("analysis_version")
        if not force_refresh and cached and cached_version == DART_ANALYSIS_VERSION and cached.get("plain_summary"):
            return {"analysis": cached, "fromCache": True}

        disclosure = self.repository.get_disclosure_by_rcept_no(clean_rcept_no)
        if not disclosure:
            raise LookupError("공시 목록에서 해당 접수번호를 찾을 수 없습니다.")

        detail_text = ""
        detail_source = "TITLE_ONLY"
        detail_error = ""
        if self.api_key:
            try:
                detail_text = self._fetch_document_text(clean_rcept_no)
                detail_source = "OPENDART_DOCUMENT" if detail_text else "TITLE_ONLY"
            except Exception as error:
                detail_error = str(error)

        analysis = self._analyze(disclosure, detail_text, detail_source, detail_error)
        analysis = self._apply_ai_refinement(analysis, disclosure, detail_text)
        saved = self.repository.upsert_disclosure_analysis(analysis)
        if saved:
            return {"analysis": {**analysis, **saved, "plain_summary": saved.get("plain_summary") or analysis.get("plain_summary")}, "fromCache": False}
        return {"analysis": analysis, "fromCache": False}

    def _fetch_document_text(self, rcept_no: str) -> str:
        response = requests.get(
            DART_DOCUMENT_URL,
            params={
                "crtfc_key": self.api_key,
                "rcept_no": rcept_no,
            },
            timeout=self.request_timeout_seconds,
        )
        response.raise_for_status()

        content_type = response.headers.get("Content-Type", "")
        content = response.content or b""
        if "xml" in content_type.lower() and content.strip().startswith(b"<"):
            self._raise_if_dart_error_xml(content)
            return self._xml_bytes_to_text(content)

        with zipfile.ZipFile(BytesIO(content)) as archive:
            chunks: list[str] = []
            for name in archive.namelist():
                if not name.lower().endswith((".xml", ".html", ".htm", ".txt")):
                    continue
                raw = archive.read(name)
                chunks.append(self._xml_bytes_to_text(raw))
            return self._clean_text("\n".join(chunks))

    def _raise_if_dart_error_xml(self, content: bytes) -> None:
        try:
            root = ET.fromstring(content)
        except ET.ParseError:
            return
        status = root.findtext("status")
        message = root.findtext("message")
        if status and status != "000":
            raise RuntimeError(f"OpenDART document failed status={status}, message={message}")

    def _xml_bytes_to_text(self, content: bytes) -> str:
        decoded = content.decode("utf-8", errors="ignore")
        try:
            root = ET.fromstring(decoded)
            text = " ".join(item.strip() for item in root.itertext() if item and item.strip())
        except ET.ParseError:
            text = re.sub(r"<[^>]+>", " ", decoded)
        return self._clean_text(text)

    def _analyze(self, disclosure: dict[str, Any], detail_text: str, source: str, detail_error: str) -> dict[str, Any]:
        report_name = str(disclosure.get("report_nm") or "").strip()
        text = self._clean_text(f"{report_name} {disclosure.get('summary') or ''} {detail_text}")
        category, sentiment, confidence = self._classify(report_name, text, bool(detail_text))
        metrics = self._extract_metrics(text, category)
        metrics = self._finalize_metrics(category, metrics)
        check_items = self._build_check_items(category, metrics, text, source)
        sentiment, confidence = self._refine_sentiment(category, sentiment, confidence, check_items)
        required_status = self._required_metric_status(category, metrics)
        confidence = self._adjust_confidence_by_required_fields(confidence, required_status, source)
        key_points = self._build_key_points(disclosure, category, sentiment, metrics, source)
        risk_points = self._build_risk_points(category, sentiment, metrics, source)
        plain_summary = self._plain_summary(category, sentiment, metrics, source, check_items)

        return {
            "rcept_no": disclosure["rcept_no"],
            "category": category,
            "sentiment": sentiment,
            "sentiment_label": self._sentiment_label(sentiment),
            "sentiment_message": self._sentiment_message(sentiment),
            "confidence": confidence,
            "headline": self._headline(category, sentiment),
            "plain_summary": plain_summary,
            "key_points": key_points,
            "risk_points": risk_points,
            "check_items": check_items,
            "metrics": metrics,
            "analysis_source": source,
            "raw_payload": {
                "report_nm": report_name,
                "corp_name": disclosure.get("corp_name"),
                "stock_code": disclosure.get("stock_code"),
                "detail_error": detail_error,
                "analysis_version": DART_ANALYSIS_VERSION,
                "analysis_mode": "v2_rules",
                "required_fields": required_status,
                "text_excerpt": detail_text[:1200],
            },
            "analyzed_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }

    def _apply_ai_refinement(
        self,
        analysis: dict[str, Any],
        disclosure: dict[str, Any],
        detail_text: str,
    ) -> dict[str, Any]:
        if not self.ai_enabled or not self._has_ai_credentials() or not detail_text:
            return analysis

        try:
            prompt = self._build_ai_refinement_prompt(analysis, disclosure, detail_text)
            if self.ai_provider == "gemini":
                payload, used_model = self._request_gemini_refinement(prompt)
                refined = self._parse_ai_refinement(payload)
                if not refined:
                    return analysis
                return self._merge_ai_refinement(analysis, refined, used_model)

            response = requests.post(
                OPENAI_CHAT_COMPLETIONS_URL,
                headers={
                    "Authorization": f"Bearer {self.openai_api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": self.ai_model,
                    "messages": [
                        {
                            "role": "system",
                            "content": (
                                "너는 공시 투자판단 보조 요약기다. 분석가처럼 예측하지 말고, "
                                "이미 제공된 v2 룰 분석 결과를 사람이 읽기 쉽게 정리한다. "
                                "반드시 한국어 JSON만 출력한다. 매수·매도 권유, 주가 예측, 원문에 없는 수치 생성은 금지한다."
                            ),
                        },
                        {"role": "user", "content": prompt},
                    ],
                    "temperature": 0.1,
                    "max_tokens": 650,
                    "response_format": {"type": "json_object"},
                },
                timeout=self.ai_timeout_seconds,
            )
            response.raise_for_status()
            refined = self._parse_ai_refinement(response.json())
            if not refined:
                return analysis
            return self._merge_ai_refinement(analysis, refined)
        except Exception as error:
            raw_payload = dict(analysis.get("raw_payload") or {})
            raw_payload.update({
                "ai_refinement_error": str(error)[:300],
                "ai_refinement_model": self.gemini_primary_model if self.ai_provider == "gemini" else self.ai_model,
                "ai_refinement_provider": self.ai_provider,
                "ai_refinement_prompt_version": self.ai_prompt_version,
            })
            analysis["raw_payload"] = raw_payload
            return analysis

    def _has_ai_credentials(self) -> bool:
        if self.ai_provider == "gemini":
            return bool(self.gemini_api_key)
        return bool(self.openai_api_key)

    def _parse_gemini_models(self) -> list[str]:
        configured_models = os.getenv("DART_GEMINI_MODELS", "")
        if configured_models:
            raw_models = configured_models.split(",")
        else:
            raw_models = [
                self.gemini_primary_model,
                self.gemini_fallback_model,
                "gemini-2.5-flash",
                "gemini-2.5-flash-lite",
            ]
        models: list[str] = []
        for model in raw_models:
            normalized = str(model or "").strip()
            if normalized and normalized not in models:
                models.append(normalized)
        return models

    def _rotated_gemini_models(self) -> list[str]:
        models = self.gemini_models or [self.gemini_primary_model, self.gemini_fallback_model]
        if not models:
            return []
        cursor = self._gemini_model_cursor % len(models)
        self._gemini_model_cursor = (self._gemini_model_cursor + 1) % len(models)
        return models[cursor:] + models[:cursor]

    def _request_gemini_refinement(self, prompt: str) -> tuple[dict[str, Any], str]:
        models = self._rotated_gemini_models()
        last_error: Exception | None = None
        for model in models:
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
                            "너는 DART 공시 요약 보조기다. 분석가처럼 예측하지 말고, "
                            "이미 제공된 v2 룰 분석 결과와 원문 일부를 사람이 읽기 쉽게 정리한다. "
                            "반드시 한국어 JSON만 출력한다. 매수/매도 권유, 주가 예측, 원문에 없는 수치 생성은 금지한다."
                        ),
                        "input": prompt,
                        "generation_config": {
                            "temperature": 0.1,
                            "max_output_tokens": 650,
                        },
                    },
                    timeout=self.ai_timeout_seconds,
                )
                response.raise_for_status()
                return self._gemini_payload_as_openai_payload(response.json()), model
            except Exception as error:
                last_error = error
                print(f"[DART Gemini] model fallback. model={model}, reason={str(error)[:160]}")
        if last_error:
            raise last_error
        raise RuntimeError("Gemini model is not configured.")

    def _gemini_payload_as_openai_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        text = self._clean_text(payload.get("output_text"))
        if not text:
            chunks: list[str] = []
            for step in payload.get("steps") or []:
                for item in step.get("content") or step.get("contents") or []:
                    if isinstance(item, dict):
                        chunks.append(str(item.get("text") or ""))
            text = self._clean_text(" ".join(chunks))
        return {"choices": [{"message": {"content": text}}]}

    def _build_ai_refinement_prompt(
        self,
        analysis: dict[str, Any],
        disclosure: dict[str, Any],
        detail_text: str,
    ) -> str:
        v2_payload = {
            "category": analysis.get("category"),
            "sentiment": analysis.get("sentiment"),
            "sentiment_label": analysis.get("sentiment_label"),
            "confidence": analysis.get("confidence"),
            "headline": analysis.get("headline"),
            "plain_summary": analysis.get("plain_summary"),
            "metrics": analysis.get("metrics") or [],
            "check_items": analysis.get("check_items") or [],
            "risk_points": analysis.get("risk_points") or [],
            "required_fields": (analysis.get("raw_payload") or {}).get("required_fields") or {},
        }
        disclosure_payload = {
            "corp_name": disclosure.get("corp_name"),
            "stock_code": disclosure.get("stock_code"),
            "report_nm": disclosure.get("report_nm"),
            "rcept_dt": disclosure.get("rcept_dt"),
        }
        excerpt = self._clean_text(detail_text)[:self.ai_excerpt_chars]

        return (
            "아래 DART 공시 v2 룰 분석 결과를 사람이 읽기 쉬운 문장으로만 보정해줘.\n"
            "중요 제한:\n"
            "1. category는 변경하지 않는다.\n"
            "2. sentiment는 positive, negative, caution, info 중 하나만 허용한다.\n"
            "3. 점수, 매수/매도 추천, 목표가, 주가 예측은 절대 쓰지 않는다.\n"
            "4. 원문 일부와 v2 결과에 없는 숫자·계약상대·발행조건을 만들지 않는다.\n"
            "5. metrics에 있는 값만 요약문에 숫자로 쓴다.\n"
            "6. required_fields.missing에 있는 값은 숫자를 만들지 말고 확인 포인트로만 짧게 언급한다.\n"
            "7. plain_summary는 1~2문장, headline은 한 문장으로 짧게 작성한다.\n"
            "8. risk_points는 확인 포인트 1개만 담는다.\n"
            "9. metrics는 새로 만들지 말고 v2 metrics를 그대로 유지한다고 생각한다.\n\n"
            "반드시 아래 JSON 형태만 출력:\n"
            "{\n"
            '  "sentiment": "positive|negative|caution|info",\n'
            '  "confidence": "high|medium|low",\n'
            '  "headline": "짧은 한 줄",\n'
            '  "plain_summary": "쉬운 설명 1~2문장",\n'
            '  "risk_points": ["확인 포인트 1개"]\n'
            "}\n\n"
            f"공시 기본정보:\n{json.dumps(disclosure_payload, ensure_ascii=False)}\n\n"
            f"v2 룰 분석 결과:\n{json.dumps(v2_payload, ensure_ascii=False)}\n\n"
            f"DART 원문 일부:\n{excerpt}\n"
        )

    def _parse_ai_refinement(self, payload: dict[str, Any]) -> dict[str, Any]:
        choices = payload.get("choices") or []
        if not choices:
            return {}
        message = choices[0].get("message") or {}
        content = message.get("content") or ""
        if isinstance(content, list):
            content = "\n".join(item.get("text", "") for item in content if isinstance(item, dict))
        text = self._clean_text(content)
        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text).strip()
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}

    def _merge_ai_refinement(
        self,
        analysis: dict[str, Any],
        refined: dict[str, Any],
        used_model: str | None = None,
    ) -> dict[str, Any]:
        next_analysis = dict(analysis)

        sentiment = self._clean_text(refined.get("sentiment"))
        if sentiment in ALLOWED_SENTIMENTS:
            next_analysis["sentiment"] = sentiment
            next_analysis["sentiment_label"] = self._sentiment_label(sentiment)
            next_analysis["sentiment_message"] = self._sentiment_message(sentiment)

        confidence = self._clean_text(refined.get("confidence"))
        if confidence in ALLOWED_CONFIDENCES:
            next_analysis["confidence"] = confidence

        headline = self._trim_ai_text(refined.get("headline"), 90)
        if headline:
            next_analysis["headline"] = headline

        plain_summary = self._trim_ai_text(refined.get("plain_summary"), 260)
        if plain_summary:
            next_analysis["plain_summary"] = plain_summary

        risk_points = refined.get("risk_points")
        if isinstance(risk_points, list):
            cleaned_risks = [self._trim_ai_text(item, 140) for item in risk_points]
            cleaned_risks = [item for item in cleaned_risks if item]
            if cleaned_risks:
                next_analysis["risk_points"] = cleaned_risks[:1]

        raw_payload = dict(next_analysis.get("raw_payload") or {})
        raw_payload.update({
            "analysis_mode": "v3_ai_refined",
            "ai_refinement_model": used_model or self.ai_model,
            "ai_refinement_provider": self.ai_provider,
            "ai_refinement_prompt_version": self.ai_prompt_version,
        })
        next_analysis["raw_payload"] = raw_payload
        next_analysis["updated_at"] = datetime.now(timezone.utc).isoformat()
        return next_analysis

    def _trim_ai_text(self, value: Any, limit: int) -> str:
        text = self._clean_text(value)
        if not text:
            return ""
        blocked = ["매수", "매도", "목표가", "상한가", "급등 예상", "상승 가능성 높"]
        for keyword in blocked:
            text = text.replace(keyword, "")
        return text if len(text) <= limit else text[:limit].rstrip() + "..."

    def _classify(self, report_name: str, text: str, has_detail: bool) -> tuple[str, str, str]:
        report_compact = re.sub(r"\s+", "", report_name)
        compact = re.sub(r"\s+", "", f"{report_name} {text}")
        head_compact = re.sub(r"\s+", "", f"{report_name} {text[:2500]}")

        if self._contains(report_compact, ["유상증자최종발행가액확정", "최종발행가액확정"]):
            return "유상증자 발행가액 확정", "caution", "high" if has_detail else "medium"
        if self._contains(report_compact, ["기재정정"]) and self._contains(report_compact, ["증권신고서", "투자설명서"]):
            return "정정 공시", "caution", "medium" if has_detail else "low"
        if self._contains(report_compact, ["공개매수"]):
            return "공개매수", "caution", "high" if has_detail else "medium"
        if self._contains(report_compact, ["주식매수선택권"]):
            return "주식매수선택권", "caution", "high" if has_detail else "medium"
        if self._contains(report_compact, ["전환가액의조정", "전환가액조정"]):
            return "전환가액 조정", "caution", "high" if has_detail else "medium"
        if self._contains(report_compact, ["유상증자결정"]) and self._contains(report_compact, ["종속회사", "자회사"]):
            return "종속회사 유상증자", "caution", "high" if has_detail else "medium"
        if self._contains(report_compact, ["증권예탁증권", "DR발행"]):
            return "DR 발행", "caution", "high" if has_detail else "medium"
        if self._contains(report_compact, ["전환청구권행사"]):
            return "전환청구권 행사", "caution", "high" if has_detail else "medium"
        if self._contains(report_compact, ["전환사채", "신주인수권부사채", "교환사채", "CB", "BW", "EB"]):
            return "주식관련사채", "caution", "high" if has_detail else "medium"
        if self._contains(report_compact, ["증권발행결과"]):
            return "증권 발행결과", "caution", "high" if has_detail else "medium"
        if self._contains(report_compact, ["채무증권", "자본으로인정되는채무증권", "회사채"]):
            return "채무증권 발행", "caution", "high" if has_detail else "medium"
        if (
            self._contains(report_compact, ["증권발행실적보고서", "투자설명서"])
            and self._contains(head_compact, ["채무증권", "무보증사채", "회사채", "일반사채"])
            and not self._contains(report_compact, ["지분증권"])
        ):
            return "채무증권 발행", "caution", "high" if has_detail else "medium"
        if self._contains(report_compact, ["증권신고서", "유상증자"]):
            return "자금조달·증권신고서", "caution", "high" if has_detail else "medium"
        if self._contains(report_compact, ["증권예탁증권", "DR발행", "증권발행실적보고서", "투자설명서"]):
            return "자금조달·증권발행", "caution", "high" if has_detail else "medium"
        if self._contains(report_compact, ["정정"]):
            return "정정 공시", "caution", "medium" if has_detail else "low"
        if self._contains(report_compact, ["횡령", "배임"]):
            return "횡령·배임", "negative", "high" if has_detail else "medium"
        if self._contains(report_compact, ["회생절차"]):
            return "회생절차", "negative", "high" if has_detail else "medium"
        if self._contains(report_compact, ["중대재해"]):
            return "중대재해", "negative", "high" if has_detail else "medium"
        if self._contains(report_compact, ["불성실공시"]):
            return "불성실공시", "negative", "high" if has_detail else "medium"
        if self._contains(report_compact, ["감사의견거절", "의견거절", "감사의견"]):
            return "감사의견 위험", "negative", "high" if has_detail else "medium"
        if self._contains(report_compact, ["관리종목", "투자주의환기", "환기종목"]):
            return "관리종목 위험", "negative", "high" if has_detail else "medium"
        if self._contains(report_compact, ["상장폐지", "관리종목", "감사의견거절", "의견거절", "부도"]):
            return "상장폐지 위험", "negative", "high" if has_detail else "medium"
        if self._contains(report_compact, ["거래정지", "매매거래정지"]):
            return "거래정지", "negative", "high" if has_detail else "medium"
        if self._contains(report_compact, ["감자결정", "무상감자", "유상감자", "자본감소"]):
            return "감자", "caution", "high" if has_detail else "medium"
        if self._contains(report_compact, ["자기주식소각", "자사주소각", "주식소각"]):
            return "자사주 소각", "positive", "high" if has_detail else "medium"
        if self._contains(report_compact, ["감사의견"]):
            return "시장 신뢰도 위험", "negative", "high" if has_detail else "medium"
        if self._contains(report_compact, ["영업정지"]):
            return "영업정지", "negative", "high" if has_detail else "medium"
        if self._contains(report_compact, ["단기차입금", "차입금증가"]):
            return "단기차입금 증가", "caution", "high" if has_detail else "medium"
        if self._contains(report_compact, ["담보제공", "주식담보", "질권"]):
            return "담보제공", "caution", "high" if has_detail else "medium"
        if self._contains(report_compact, ["자기주식취득신탁계약해지", "자사주신탁해지"]):
            return "자사주 신탁 해지", "caution", "high" if has_detail else "medium"
        if self._contains(report_compact, ["공급계약해지", "계약해지", "단일판매공급계약해지"]):
            return "공급계약 해지", "negative", "high" if has_detail else "medium"
        if self._contains(report_compact, ["단일판매", "공급계약", "수주"]):
            return "수주·공급계약", "positive", "high" if has_detail else "medium"
        if self._contains(report_compact, ["권리락"]):
            return "권리락", "info", "high" if has_detail else "medium"
        if self._contains(report_compact, ["무상증자"]):
            return "무상증자", "positive", "high" if has_detail else "medium"
        if self._contains(report_compact, ["액면분할", "주식분할"]):
            return "액면분할", "info", "high" if has_detail else "medium"
        if self._contains(report_compact, ["액면병합", "주식병합"]):
            return "액면병합", "caution", "high" if has_detail else "medium"
        if self._contains(report_compact, ["자기주식취득", "자사주취득"]):
            return "주주환원", "positive", "high" if has_detail else "medium"
        if self._contains(report_compact, ["현금배당", "현물배당", "배당결정"]):
            return "배당", "positive", "high" if has_detail else "medium"
        if self._contains(report_compact, ["대표이사변경", "대표집행임원변경"]):
            return "대표이사 변경", "caution", "high" if has_detail else "medium"
        if self._contains(report_compact, ["신규시설투자", "시설투자"]):
            return "신규 시설투자", "positive", "high" if has_detail else "medium"
        if self._contains(report_compact, ["영업잠정실적", "영업(잠정)실적", "잠정실적", "잠정)실적"]):
            return "영업실적", "info", "high" if has_detail else "medium"
        if self._contains(report_compact, ["매출액또는손익구조", "손익구조", "30%변동"]):
            return "손익구조 변동", "caution", "high" if has_detail else "medium"
        if self._contains(report_compact, ["기업가치제고계획", "밸류업"]):
            return "기업가치 제고 계획", "positive", "high" if has_detail else "medium"
        if self._contains(report_compact, ["조회공시", "조회공시답변", "풍문", "보도", "급등락", "현저한시황변동"]):
            return "조회공시 답변", "caution", "high" if has_detail else "medium"
        if self._contains(report_compact, ["실적전망", "신제품개발", "기술이전", "신규사업", "신규사업진출", "경영계획"]):
            return "공정공시 중요정보", "caution", "high" if has_detail else "medium"
        if self._contains(report_compact, ["특수관계인", "내부거래", "동일인등", "계열회사"]):
            return "특수관계인·내부거래", "caution", "medium" if has_detail else "low"
        if self._contains(report_compact, ["타법인주식", "출자증권취득", "출자증권처분", "출자증권양수"]):
            return "타법인 주식 취득·처분", "caution", "high" if has_detail else "medium"
        if self._contains(report_compact, ["투자판단관련주요경영사항"]):
            return "투자판단 주요경영사항", "caution", "high" if has_detail else "medium"
        if self._contains(report_compact, ["장래사업", "경영계획", "공정공시"]):
            return "사업계획·전망", "info", "medium" if has_detail else "low"
        if self._contains(report_compact, ["지속가능경영", "ESG", "자율공시"]):
            return "ESG·자율공시", "info", "medium" if has_detail else "low"
        if self._contains(report_compact, ["자기주식처분"]):
            return "자기주식 처분", "caution", "high" if has_detail else "medium"
        if self._contains(report_compact, ["최대주주변경을수반하는주식양수도계약"]):
            return "최대주주 변경 계약", "caution", "high" if has_detail else "medium"
        if self._contains(report_compact, ["최대주주변경"]):
            return "최대주주 변경", "caution", "high" if has_detail else "medium"
        if self._contains(report_compact, ["합병등종료보고서"]):
            return "합병 종료", "caution", "medium" if has_detail else "low"
        if self._contains(report_compact, ["합병"]):
            return "합병", "caution", "high" if has_detail else "medium"
        if self._contains(report_compact, ["분할"]):
            return "분할", "caution", "high" if has_detail else "medium"
        if self._contains(report_compact, ["소송"]):
            return "소송", "negative", "high" if has_detail else "medium"
        if self._contains(report_compact, ["타인에대한채무보증", "채무보증결정", "채무보증"]):
            return "채무보증", "caution", "high" if has_detail else "medium"
        return "정보성 공시", "info", "medium" if has_detail else "low"

    def _extract_metrics(self, text: str, category: str) -> list[dict[str, str]]:
        labels = self._metric_labels_for_category(category)
        metrics: list[dict[str, str]] = []
        seen: set[str] = set()

        if category == "유상증자 발행가액 확정":
            self._append_rights_offering_price_fallback_metrics(text, metrics)
            return metrics
        if category == "무상증자":
            self._append_bonus_issue_fallback_metrics(text, metrics)
            return metrics
        if category == "권리락":
            self._append_rights_detachment_metrics(text, metrics)
            return metrics
        if category == "액면병합":
            self._append_reverse_split_fallback_metrics(text, metrics)
        if category == "증권 발행결과":
            self._append_security_issuance_result_metrics(text, metrics)
            return metrics
        if category == "채무증권 발행":
            self._append_debt_security_metrics(text, metrics)
            return metrics
        if category == "전환청구권 행사":
            self._append_conversion_request_metrics(text, metrics)
            return metrics
        if category == "종속회사 유상증자":
            self._append_subsidiary_rights_offering_metrics(text, metrics)
            return metrics
        if category == "DR 발행":
            self._append_dr_issuance_metrics(text, metrics)
            return metrics
        if category == "중대재해":
            self._append_serious_accident_metrics(text, metrics)
            return metrics
        if category == "조회공시 답변":
            self._append_query_response_metrics(text, metrics)
            return metrics
        if category == "특수관계인·내부거래":
            self._append_related_party_transaction_metrics(text, metrics)
            return metrics
        if category == "자사주 신탁 해지":
            self._append_treasury_trust_cancel_metrics(text, metrics)
            return metrics
        if category == "상장폐지 위험":
            self._append_delisting_risk_metrics(text, metrics)
        if category == "거래정지":
            self._append_trading_halt_metrics(text, metrics)
        if category == "타법인 주식 취득·처분":
            self._append_other_corp_share_metrics(text, metrics)
            return metrics
        if category == "투자판단 주요경영사항":
            self._append_major_management_metrics(text, metrics)
            return metrics
        if category == "합병 종료":
            self._append_merger_completion_metrics(text, metrics)
            return metrics
        if category == "최대주주 변경 계약":
            self._append_largest_holder_contract_metrics(text, metrics)
            return metrics
        if category == "공개매수":
            self._append_tender_offer_metrics(text, metrics)
            return metrics
        if category == "주식매수선택권":
            self._append_stock_option_metrics(text, metrics)
            return metrics
        if category == "전환가액 조정":
            self._append_conversion_price_adjustment_metrics(text, metrics)
            return metrics
        if category == "불성실공시":
            self._append_unfaithful_disclosure_metrics(text, metrics)
            return metrics
        if category == "관리종목 위험":
            self._append_admin_issue_metrics(text, metrics)
            return metrics
        if category == "감사의견 위험":
            self._append_audit_opinion_metrics(text, metrics)
            return metrics
        if category == "단기차입금 증가":
            self._append_short_term_borrowing_metrics(text, metrics)
            return metrics
        if category == "담보제공":
            self._append_collateral_metrics(text, metrics)
            return metrics

        if not labels:
            return metrics

        for label in labels:
            value = self._find_label_value(text, label, labels)
            if not value:
                continue
            key = f"{label}:{value}"
            if key in seen:
                continue
            seen.add(key)
            short_value = self._shorten_metric_value(label, value)
            if not short_value:
                continue
            metrics.append({"label": label, "value": short_value})
            if len(metrics) >= 8:
                return metrics

        if category == "수주·공급계약":
            self._append_supply_contract_fallback_metrics(text, metrics)
        return metrics

    def _clean_rights_offering_metrics(self, metrics: list[dict[str, str]]) -> list[dict[str, str]]:
        cleaned: list[dict[str, str]] = []
        seen_values: set[str] = set()
        preferred_labels = {"확정발행가액", "발행주식수", "확정일", "증자방식"}

        for metric in metrics:
            label = str(metric.get("label") or "")
            value = str(metric.get("value") or "")
            if label in {"발행가액", "확정발행가액"} and not self._looks_like_money(value):
                continue
            if label in {"신주의 수", "발행주식수"} and not self._looks_like_stock_count(value):
                continue
            if label in {"확정일", "청약예정일", "납입일", "상장예정일"} and not self._looks_like_date(value):
                continue

            normalized_value = self._clean_text(value)
            if label not in preferred_labels and normalized_value in seen_values:
                continue
            seen_values.add(normalized_value)
            cleaned.append(metric)

        return cleaned

    def _append_metric_if_missing(self, metrics: list[dict[str, str]], label: str, value: str) -> None:
        if not value or any(metric.get("label") == label for metric in metrics):
            return
        metrics.append({"label": label, "value": value})

    def _finalize_metrics(self, category: str, metrics: list[dict[str, str]]) -> list[dict[str, str]]:
        schema = DART_ANALYSIS_SCHEMAS.get(category) or {}
        ordered_labels = list(schema.get("required") or []) + list(schema.get("optional") or [])
        summary_limit = int(schema.get("summary_limit") or 6)

        deduped: dict[str, str] = {}
        for metric in metrics:
            label = self._clean_text(metric.get("label"))
            value = self._clean_text(metric.get("value"))
            if not label or not value:
                continue
            if label not in deduped:
                deduped[label] = value

        ordered: list[dict[str, str]] = []
        for label in ordered_labels:
            value = deduped.pop(label, "")
            if value:
                ordered.append({"label": label, "value": value})

        for label, value in deduped.items():
            ordered.append({"label": label, "value": value})

        return ordered[:summary_limit]

    def _required_metric_status(self, category: str, metrics: list[dict[str, str]]) -> dict[str, Any]:
        schema = DART_ANALYSIS_SCHEMAS.get(category) or {}
        required = list(schema.get("required") or [])
        metric_labels = {self._clean_text(metric.get("label")) for metric in metrics}
        missing = [label for label in required if label not in metric_labels]
        return {
            "required": required,
            "missing": missing,
            "coverage": 1.0 if not required else round((len(required) - len(missing)) / len(required), 2),
        }

    def _adjust_confidence_by_required_fields(
        self,
        confidence: str,
        required_status: dict[str, Any],
        source: str,
    ) -> str:
        missing = required_status.get("missing") or []
        required = required_status.get("required") or []
        if source == "TITLE_ONLY":
            return "low"
        if not required:
            return confidence
        if not missing:
            return confidence
        if len(missing) >= len(required):
            return "low"
        return "medium" if confidence == "high" else confidence

    def _append_rights_offering_price_fallback_metrics(self, text: str, metrics: list[dict[str, str]]) -> None:
        issue_price = self._find_pattern_value(text, [
            r"확정가액\s*\(\s*원\s*\)\s*([0-9][0-9,]*(?:\.\d+)?)",
            r"확정\s*가액\s*\(\s*원\s*\)\s*([0-9][0-9,]*(?:\.\d+)?)",
            r"확정발행가액\s*\(\s*1주당\s*\).*?확정가액\s*\(\s*원\s*\)\s*([0-9][0-9,]*(?:\.\d+)?)",
            r"1주당\s*발행가액\s*[:：]?\s*([0-9][0-9,]*(?:\.\d+)?\s*(?:원|KRW)?)",
        ])
        issue_price = self._normalize_won_value(issue_price)
        self._append_metric_if_missing(metrics, "확정발행가액", issue_price)

        shares = self._find_pattern_value(text, [
            r"주식수\s*\(\s*주\s*\)\s*([0-9][0-9,]*)",
            r"신주의\s*수\s*[:：]?\s*([0-9][0-9,]*\s*주)",
            r"발행할\s*주식.*?수\s*[:：]?\s*([0-9][0-9,]*\s*주)",
        ])
        shares = self._normalize_stock_count_value(shares)
        self._append_metric_if_missing(metrics, "발행주식수", shares)

        fixed_date = self._find_pattern_value(text, [
            r"확정일\s*[:：]?\s*(\d{4}[.\-/년]\s*\d{1,2}[.\-/월]\s*\d{1,2})",
            r"확정일\s*[:：]?\s*(\d{8})",
        ])
        fixed_date = self._shorten_metric_value("확정일", fixed_date)
        self._append_metric_if_missing(metrics, "확정일", fixed_date)

        discount = self._find_pattern_value(text, [
            r"할인율(?:은|을)?\s*([0-9]+(?:\.\d+)?\s*%)",
            r"할인율\s*[:：]?\s*([0-9]+(?:\.\d+)?\s*%)",
        ])
        self._append_metric_if_missing(metrics, "할인율", discount)

        method = "주주배정 후 실권주 일반공모" if "주주배정후실권주일반공모" in re.sub(r"\s+", "", text) else ""
        self._append_metric_if_missing(metrics, "증자방식", method)

    def _append_bonus_issue_fallback_metrics(self, text: str, metrics: list[dict[str, str]]) -> None:
        common_shares = self._find_pattern_value(text, [
            r"신주의\s*종류와\s*수\s*보통주식\s*\(\s*주\s*\)\s*([0-9][0-9,]*)",
            r"보통주식\s*\(\s*주\s*\)\s*([0-9][0-9,]*)",
        ])
        self._append_metric_if_missing(metrics, "보통주 신주", self._normalize_stock_count_value(common_shares))

        preferred_shares = self._find_pattern_value(text, [
            r"신주의\s*종류와\s*수.*?기타주식\s*\(\s*주\s*\)\s*([0-9][0-9,]*)",
            r"기타주식\s*\(\s*주\s*\)\s*([0-9][0-9,]*)",
        ])
        self._append_metric_if_missing(metrics, "기타주식 신주", self._normalize_stock_count_value(preferred_shares))

        ratio = self._find_pattern_value(text, [
            r"1주당\s*신주배정\s*주식수\s*보통주식\s*\(\s*주\s*\)\s*([0-9]+(?:\.\d+)?)",
            r"1주당\s*신주배정\s*주식수\s*[:：]?\s*([0-9]+(?:\.\d+)?)",
        ])
        self._append_metric_if_missing(metrics, "1주당 배정", f"{ratio}주" if ratio else "")

        base_date = self._find_pattern_value(text, [
            r"신주배정기준일\s*[:：]?\s*(\d{4}[년.\-/]\s*\d{1,2}[월.\-/]\s*\d{1,2}\s*일?)",
            r"배정기준일\s*[:：]?\s*(\d{4}[년.\-/]\s*\d{1,2}[월.\-/]\s*\d{1,2}\s*일?)",
        ])
        self._append_metric_if_missing(metrics, "배정기준일", self._shorten_metric_value("배정기준일", base_date))

        listing_date = self._find_pattern_value(text, [
            r"신주의\s*상장\s*예정일\s*[:：]?\s*(\d{4}[년.\-/]\s*\d{1,2}[월.\-/]\s*\d{1,2}\s*일?)",
            r"상장\s*예정일\s*[:：]?\s*(\d{4}[년.\-/]\s*\d{1,2}[월.\-/]\s*\d{1,2}\s*일?)",
        ])
        self._append_metric_if_missing(metrics, "상장예정일", self._shorten_metric_value("상장예정일", listing_date))

        source_amount = self._find_pattern_value(text, [
            r"주식발행초과금\s*[:：]?\s*([0-9][0-9,]*(?:\.\d+)?\s*원)",
            r"자본에\s*전입할\s*재원과\s*금액.*?([0-9][0-9,]*(?:\.\d+)?\s*원)",
        ])
        self._append_metric_if_missing(metrics, "전입재원", source_amount)

    def _append_rights_detachment_metrics(self, text: str, metrics: list[dict[str, str]]) -> None:
        if self._append_rights_detachment_table_row_metrics(text, metrics):
            return

        stock_type = self._find_pattern_value(text, [
            r"주권종류\s*[:：]?\s*([가-힣A-Za-z\s]{1,20})(?=\s*\d+\.|$)",
            r"2\.\s*주권종류\s*([가-힣A-Za-z\s]{1,20})(?=\s*\d+\.|$)",
        ])
        self._append_metric_if_missing(metrics, "주권종류", self._truncate_metric_value(stock_type, 16))

        short_code = self._find_pattern_value(text, [
            r"단축코드\s*[:：]?\s*([A-Z0-9]{4,12})",
            r"3\.\s*단축코드\s*([A-Z0-9]{4,12})",
        ])
        self._append_metric_if_missing(metrics, "단축코드", short_code)

        base_price = self._find_pattern_value(text, [
            r"기준가\s*\(\s*원\s*\)\s*([0-9][0-9,]*(?:\.\d+)?)(?!\.)",
            r"기준가\s*[:：]?\s*([0-9][0-9,]*(?:\.\d+)?\s*원?)(?!\.)",
            r"4\.\s*기준가\s*\(\s*원\s*\)\s*([0-9][0-9,]*(?:\.\d+)?)(?!\.)",
        ])
        self._append_metric_if_missing(metrics, "기준가", self._normalize_won_value(base_price))

        event_date = self._find_pattern_value(text, [
            r"권리락\s*실시일\s*[:：]?\s*(\d{4}[.\-/년]\s*\d{1,2}[.\-/월]\s*\d{1,2}\s*일?)",
            r"5\.\s*권리락\s*실시일\s*(\d{4}[.\-/년]\s*\d{1,2}[.\-/월]\s*\d{1,2}\s*일?)",
        ])
        self._append_metric_if_missing(metrics, "권리락 실시일", self._shorten_metric_value("권리락 실시일", event_date))

        reason = self._find_pattern_value(text, [
            r"사유\s*[:：]?\s*([가-힣A-Za-z0-9ㆍ·\s]{1,40})",
            r"6\.\s*사유\s*([가-힣A-Za-z0-9ㆍ·\s]{1,40})",
        ])
        self._append_metric_if_missing(metrics, "사유", self._truncate_metric_value(reason, 24))

    def _append_rights_detachment_table_row_metrics(self, text: str, metrics: list[dict[str, str]]) -> bool:
        compact_text = self._clean_text(text)
        pattern = re.compile(
            r"(?:1\.\s*)?회사명\s+"
            r"(?:2\.\s*)?주권종류\s+"
            r"(?:3\.\s*)?단축코드\s+"
            r"(?:4\.\s*)?기준가\s*\(\s*원\s*\)\s+"
            r"(?:5\.\s*)?권리락\s*실시일\s+"
            r"(?:6\.\s*)?사유\s+"
            r"(?P<corp>.+?)\s+"
            r"(?P<stock_type>보통주식|우선주식|종류주식)\s+"
            r"(?P<short_code>[A-Z0-9]{4,12})\s+"
            r"(?P<base_price>\d[\d,]*(?:\.\d+)?)\s+"
            r"(?P<event_date>\d{4}[.\-/]\d{1,2}[.\-/]\d{1,2})\s+"
            r"(?P<reason>[가-힣A-Za-z0-9ㆍ·\s]{1,30})"
        )
        match = pattern.search(compact_text)
        if not match:
            return False

        self._append_metric_if_missing(metrics, "주권종류", match.group("stock_type"))
        self._append_metric_if_missing(metrics, "단축코드", match.group("short_code"))
        self._append_metric_if_missing(metrics, "기준가", self._normalize_won_value(match.group("base_price")))
        self._append_metric_if_missing(metrics, "권리락 실시일", self._shorten_metric_value("권리락 실시일", match.group("event_date")))
        self._append_metric_if_missing(metrics, "사유", self._truncate_metric_value(match.group("reason"), 24))
        return True

    def _append_reverse_split_fallback_metrics(self, text: str, metrics: list[dict[str, str]]) -> None:
        if any(metric.get("label") == "병합비율" for metric in metrics):
            return
        match = re.search(r"1주당\s*가액\s*\(?\s*원\s*\)?\s*([0-9][0-9,]*)\s+([0-9][0-9,]*)", text)
        if not match:
            return
        before = int(match.group(1).replace(",", ""))
        after = int(match.group(2).replace(",", ""))
        if before <= 0 or after <= 0:
            return
        if after >= before and after % before == 0:
            self._append_metric_if_missing(metrics, "병합비율", f"{after // before}:1")
        elif before % after == 0:
            self._append_metric_if_missing(metrics, "병합비율", f"1:{before // after}")

    def _append_security_issuance_result_metrics(self, text: str, metrics: list[dict[str, str]]) -> None:
        labels = ["발행방법", "발행예정주식수", "발행예정금액", "실제발행주식수", "실제발행금액", "납입일", "상장예정일"]
        method = self._find_label_value(text, "발행방법", labels)
        self._append_metric_if_missing(metrics, "발행방법", self._truncate_metric_value(method, 24))
        for label in ["발행예정주식수", "실제발행주식수"]:
            value = self._find_label_value(text, label, labels)
            self._append_metric_if_missing(metrics, label, self._normalize_stock_count_value(value))
        for label in ["발행예정금액", "실제발행금액"]:
            value = self._find_label_value(text, label, labels)
            self._append_metric_if_missing(metrics, label, self._normalize_won_value(value))
        paid_date = self._find_label_value(text, "납입일", labels)
        self._append_metric_if_missing(metrics, "납입일", self._shorten_metric_value("납입일", paid_date))
        listing_date = self._find_pattern_value(text, [
            r"신주\s*상장\s*예정일\s*[:：]?\s*(\d{4}[년.\-/]\s*\d{1,2}[월.\-/]\s*\d{1,2}\s*일?)",
            r"상장예정일\s*[:：]?\s*(\d{4}[년.\-/]\s*\d{1,2}[월.\-/]\s*\d{1,2}\s*일?)",
        ])
        self._append_metric_if_missing(metrics, "상장예정일", self._shorten_metric_value("상장예정일", listing_date))

    def _append_debt_security_metrics(self, text: str, metrics: list[dict[str, str]]) -> None:
        amount = self._extract_debt_security_amount(text)
        if not amount:
            amount = self._find_pattern_value(text, [
                r"사채의\s*권면\s*\(전자등록\)\s*총액\s*\(\s*원\s*\)\s*([0-9][0-9,]*)",
                r"모집\s*또는\s*매출금액\s*[:：]?\s*.*?([0-9][0-9,]{6,})",
            ])
        self._append_metric_if_missing(metrics, "발행총액", self._normalize_won_value(amount))
        purpose = self._find_label_value(text, "자금조달의 목적", ["자금조달의 목적", "사채의 이율", "사채만기일", "이자율"])
        purpose_value = self._shorten_metric_value("자금조달의 목적", purpose)
        if not purpose_value:
            purpose_value = ", ".join(keyword for keyword in ["시설자금", "운영자금", "채무상환자금"] if keyword in text)
        self._append_metric_if_missing(metrics, "자금조달의 목적", purpose_value)
        rate_values = self._extract_debt_security_rates(text)
        for label in ["표면이자율", "만기이자율", "이자율", "발행수익률"]:
            value = rate_values.get(label) or ""
            self._append_metric_if_missing(metrics, label, self._shorten_metric_value(label, value))
        maturity = self._find_label_value(text, "사채만기일", ["사채만기일", "이자지급방법", "이자율"])
        self._append_metric_if_missing(metrics, "사채만기일", self._shorten_metric_value("사채만기일", maturity))

    def _append_conversion_request_metrics(self, text: str, metrics: list[dict[str, str]]) -> None:
        shares = self._find_pattern_value(text, [
            r"행사주식수\s*누계\s*\(\s*주\s*\).*?([0-9][0-9,]*)",
            r"발행한\s*주식수\s*([0-9][0-9,]*)",
        ])
        self._append_metric_if_missing(metrics, "행사주식수", self._normalize_stock_count_value(shares))
        ratio = self._find_pattern_value(text, [
            r"발행주식총수\s*대비\s*\(\s*%\s*\)\s*([0-9]+(?:\.\d+)?)",
        ])
        self._append_metric_if_missing(metrics, "발행주식총수 대비", f"{ratio}%" if ratio else "")
        row_values = self._extract_conversion_request_row(text)
        price = row_values.get("전환가액") or self._find_pattern_value(text, [
            r"전환가액\s*([0-9][0-9,]*(?:\.\d+)?)",
        ])
        self._append_metric_if_missing(metrics, "전환가액", self._normalize_won_value(price))
        amount = row_values.get("청구금액") or self._find_pattern_value(text, [
            r"청구금액\s*([0-9][0-9,]*(?:\.\d+)?\s*원?)",
        ])
        self._append_metric_if_missing(metrics, "청구금액", self._normalize_won_value(amount))
        listing = row_values.get("상장예정일") or self._find_pattern_value(text, [
            r"상장일\s*또는\s*예정일\s*([0-9]{4}[.\-/년]\s*[0-9]{1,2}[.\-/월]\s*[0-9]{1,2}\s*일?)",
        ])
        self._append_metric_if_missing(metrics, "상장예정일", self._shorten_metric_value("상장예정일", listing))

    def _extract_debt_security_amount(self, text: str) -> str:
        direct_match = re.search(r"총\s*발행금액\s*[:：]?\s*([0-9][0-9,]{6,})", text)
        if direct_match:
            return f"{direct_match.group(1)}원"
        section_match = re.search(
            r"모집\s*또는\s*매출\s*(?:금액|총액|총\s*액)\s*[:：]?\s*(.{0,500}?)(?:\s+\d+\.\s*정정사유|\s+정정사유|\s+5\.\s*정정사항|$)",
            text,
            flags=re.S,
        )
        if not section_match:
            section_match = re.search(
                r"모집\s*\(매출\)\s*총액.{0,160}?([0-9][0-9,]{6,})",
                text,
                flags=re.S,
            )
            if section_match:
                return f"{section_match.group(1)}원"
        if section_match:
            amounts = [int(value.replace(",", "")) for value in re.findall(r"\\\s*([0-9][0-9,]{6,})", section_match.group(1))]
            if amounts:
                return f"{sum(amounts):,}원"
            amount = re.search(r"([0-9][0-9,]{6,})\s*원", section_match.group(1))
            if amount:
                return f"{amount.group(1)}원"
        return ""

    def _extract_debt_security_rates(self, text: str) -> dict[str, str]:
        values: dict[str, str] = {}
        surface_match = re.search(r"표면이자율\s*\(?%\)?\s*[:：]?\s*([0-9]+(?:\.[0-9]+)?)", text)
        if surface_match:
            values["표면이자율"] = f"{surface_match.group(1)}%"
        maturity_match = re.search(r"만기이자율\s*\(?%\)?\s*[:：]?\s*([0-9]+(?:\.[0-9]+)?)", text)
        if maturity_match:
            values["만기이자율"] = f"{maturity_match.group(1)}%"
        interest_match = re.search(r"이자율\s*[:：]\s*([0-9]+(?:\.[0-9]+)?)\s*%", text)
        if interest_match:
            values["이자율"] = f"{interest_match.group(1)}%"
        yield_match = re.search(r"발행수익률\s*[:：]\s*([0-9]+(?:\.[0-9]+)?)\s*%", text)
        if yield_match:
            values["발행수익률"] = f"{yield_match.group(1)}%"
        annual_match = re.search(r"연리이자율\(%\)\s*[:：]\s*([0-9]+(?:\.[0-9]+)?)", text)
        if annual_match and "이자율" not in values:
            values["이자율"] = f"{annual_match.group(1)}%"
        return values

    def _extract_conversion_request_row(self, text: str) -> dict[str, str]:
        row_match = re.search(
            r"청구금액\s+전환가액\s+발행한\s+주식수\s+상장일\s+또는\s+예정일.*?"
            r"([0-9][0-9,]*원)\s+([0-9][0-9,]*)\s+([0-9][0-9,]*)\s+(\d{4}[.\-/]\d{1,2}[.\-/]\d{1,2})",
            text,
            flags=re.S,
        )
        if not row_match:
            return {}
        return {
            "청구금액": row_match.group(1),
            "전환가액": row_match.group(2),
            "상장예정일": row_match.group(4),
        }

    def _append_subsidiary_rights_offering_metrics(self, text: str, metrics: list[dict[str, str]]) -> None:
        shares = self._find_pattern_value(text, [
            r"신주의\s*종류와\s*수\s*보통주식\s*\(\s*주\s*\)\s*([0-9][0-9,]*)",
            r"보통주식\s*\(\s*주\s*\)\s*([0-9][0-9,]*)\s*기타주식",
            r"보통주식\s*\(\s*주\s*\)\s*([0-9][0-9,]*)\s*종류주식",
        ])
        self._append_metric_if_missing(metrics, "신주의 수", self._normalize_stock_count_value(shares))
        price = self._find_pattern_value(text, [
            r"예정발행가\s*보통주식\s*\(\s*원\s*\)\s*([0-9][0-9,]*)",
            r"확정발행가\s*보통주식\s*\(\s*원\s*\)\s*([0-9][0-9,]*)",
            r"신주\s*발행가액.*?보통주식\s*\(\s*원\s*\)\s*([0-9][0-9,]*)",
            r"발행가액.*?보통주식\s*\(\s*원\s*\)\s*([0-9][0-9,]*)",
            r"신주\s*발행가액.*?보통주식\s*([0-9][0-9,]*)",
        ])
        self._append_metric_if_missing(metrics, "발행가액", self._normalize_won_value(price))
        method = self._find_pattern_value(text, [
            r"증자방식\s*([^\n\r]{1,80})",
        ])
        self._append_metric_if_missing(metrics, "증자방식", self._shorten_metric_value("증자방식", method))
        purpose = self._extract_funding_purpose(text)
        self._append_metric_if_missing(metrics, "자금조달의 목적", purpose)
        paid_date = self._find_pattern_value(text, [
            r"납입일\s*(\d{4}[.\-/년]\s*\d{1,2}[.\-/월]\s*\d{1,2}\s*일?)",
        ])
        self._append_metric_if_missing(metrics, "납입일", self._shorten_metric_value("납입일", paid_date))
        listing_date = self._find_pattern_value(text, [
            r"상장예정일\s*(\d{4}[.\-/년]\s*\d{1,2}[.\-/월]\s*\d{1,2}\s*일?)",
        ])
        self._append_metric_if_missing(metrics, "상장예정일", self._shorten_metric_value("상장예정일", listing_date))

    def _append_dr_issuance_metrics(self, text: str, metrics: list[dict[str, str]]) -> None:
        dr_type = self._find_pattern_value(text, [r"DR\s*발행형태\s*([^\s]+)"])
        self._append_metric_if_missing(metrics, "DR 발행형태", self._truncate_metric_value(dr_type, 24))
        total = self._find_pattern_value(text, [
            r"DR\s*발행총액.*?원화금액\(\s*원\s*\)\s*([0-9][0-9,]*)",
        ])
        self._append_metric_if_missing(metrics, "DR 발행총액", self._normalize_won_value(total))
        price = self._find_pattern_value(text, [
            r"신주\s*발행가액\(\s*원\s*\)\s*보통주식\s*([0-9][0-9,]*)",
            r"신주\s*발행가액.*?보통주식\s*([0-9][0-9,]*)",
        ])
        self._append_metric_if_missing(metrics, "신주 발행가액", self._normalize_won_value(price))
        ratio = self._find_pattern_value(text, [
            r"원주\s*전환비율\(\s*주\s*\)\s*([0-9]+(?:\.[0-9]+)?)",
        ])
        self._append_metric_if_missing(metrics, "원주 전환비율", f"{ratio}주" if ratio else "")
        self._append_metric_if_missing(metrics, "자금조달의 목적", self._extract_funding_purpose(text))
        paid_date = self._find_pattern_value(text, [
            r"납입일\s*(\d{4}[.\-/년]\s*\d{1,2}[.\-/월]\s*\d{1,2}\s*일?)",
        ])
        self._append_metric_if_missing(metrics, "납입일", self._shorten_metric_value("납입일", paid_date))
        listing_date = self._find_pattern_value(text, [
            r"상장예정일\s*(\d{4}[.\-/년]\s*\d{1,2}[.\-/월]\s*\d{1,2}\s*일?)",
        ])
        self._append_metric_if_missing(metrics, "상장예정일", self._shorten_metric_value("상장예정일", listing_date))

    def _append_serious_accident_metrics(self, text: str, metrics: list[dict[str, str]]) -> None:
        content = self._find_pattern_value(text, [
            r"발생\s*재해\s*내용\s*([^\n\r]{1,160}?)(?:\s+사망자\s*수|\s+부상자\s*수|\s+2\.)",
        ])
        self._append_metric_if_missing(metrics, "재해내용", self._truncate_metric_value(content, 48))
        accident_date = self._find_pattern_value(text, [
            r"중대재해\s*발생일자\s*(\d{4}[.\-/년]\s*\d{1,2}[.\-/월]\s*\d{1,2}\s*일?)",
        ])
        self._append_metric_if_missing(metrics, "발생일자", self._shorten_metric_value("발생일자", accident_date))
        death_count = self._find_pattern_value(text, [r"사망자\s*수\s*([0-9]+)"])
        self._append_metric_if_missing(metrics, "사망자 수", f"{death_count}명" if death_count else "")
        injury_count = self._find_pattern_value(text, [r"부상자\s*수\s*([0-9]+)"])
        self._append_metric_if_missing(metrics, "부상자 수", f"{injury_count}명" if injury_count else "")
        action = self._find_pattern_value(text, [
            r"조치사항\s*및\s*향후대책\s*([^\n\r]{1,180}?)(?:\s+5\.|\s+기타|\s*$)",
        ])
        self._append_metric_if_missing(metrics, "조치사항", self._truncate_metric_value(action, 48))

    def _append_query_response_metrics(self, text: str, metrics: list[dict[str, str]]) -> None:
        answer = self._find_pattern_value(text, [
            r"해명내용\s*(.*?)(?:\s+5\.\s*재공시|\s+재공시예정일|\s+공시책임자|\s*$)",
            r"답변내용\s*(.*?)(?:\s+재공시|\s+공시책임자|\s*$)",
        ])
        self._append_metric_if_missing(metrics, "답변내용", self._truncate_metric_value(answer, 64))
        request_date = self._find_pattern_value(text, [
            r"조회공시요구일\s*(\d{4}[.\-/년]\s*\d{1,2}[.\-/월]\s*\d{1,2}\s*일?)",
            r"풍문\s*또는\s*보도의\s*발생일자\s*(\d{4}[.\-/년]\s*\d{1,2}[.\-/월]\s*\d{1,2}\s*일?)",
        ])
        self._append_metric_if_missing(metrics, "조회공시요구일", self._shorten_metric_value("조회공시요구일", request_date))
        answer_date = self._find_pattern_value(text, [
            r"공시일자\s*(\d{4}[.\-/년]\s*\d{1,2}[.\-/월]\s*\d{1,2}\s*일?)",
        ])
        self._append_metric_if_missing(metrics, "답변일", self._shorten_metric_value("답변일", answer_date))
        progress = self._find_pattern_value(text, [
            r"재공시예정일\s*([^\n\r]{1,80})",
        ])
        self._append_metric_if_missing(metrics, "진행사항", self._truncate_metric_value(progress, 36))

    def _append_related_party_transaction_metrics(self, text: str, metrics: list[dict[str, str]]) -> None:
        unit = "백만원" if "단위 : 백만 원" in text or "단위:백만원" in re.sub(r"\s+", "", text) else "원"
        counterparty = self._find_pattern_value(text, [
            r"거래상대방\s*([^\n\r]{1,80}?)(?:\s+회사와의\s*관계|\s+매출액|\s+매입액|\s+합계액)",
            r"매출액대비\(D/A,\s*%\)\s+(.+?)\s+[-0-9,]+\s+[-0-9,]+\s+[0-9][0-9,]*\s+[0-9]+(?:\.[0-9]+)?",
            r"\)\s*([가-힣A-Za-z0-9().ㆍ\s]+?)\s+[-0-9,]+\s+[-0-9,]+\s+[-0-9,]+\s+[0-9.]+",
        ])
        if "동일인" in counterparty or "출자계열회사" in counterparty:
            counterparty = self._find_pattern_value(text, [
                r"매출액대비\(D/A,\s*%\)\s+(.+?)\s+[-0-9,]+\s+[-0-9,]+\s+[0-9][0-9,]*\s+[0-9]+(?:\.[0-9]+)?",
            ])
        self._append_metric_if_missing(metrics, "거래상대방", self._clean_counterparty(counterparty))
        amount = self._find_pattern_value(text, [
            r"총거래금액\s*([0-9][0-9,]*)",
            r"라\.\s*거래금액\s*([0-9][0-9,]*)",
            r"거래상대방\(동일인\s*등\s*출자계열회사\).*?\s([0-9][0-9,]*)\s+[0-9]+(?:\.[0-9]+)?\s+5\.",
        ])
        self._append_metric_if_missing(metrics, "거래금액", f"{amount}{unit}" if amount else "")
        purpose = self._find_pattern_value(text, [
            r"거래목적\s*([^\n\r]{1,80}?)(?:\s+거래금액|\s+계약체결|\s+6\.|\s+7\.|\s*$)",
            r"거래조건\s+거래목적\s+거래금액\s+계약체결방식.*?\s([가-힣A-Za-z0-9ㆍ\s]{2,50})\s+[0-9][0-9,]*\s+(?:수의계약|경쟁입찰|제한경쟁입찰|지명경쟁입찰)",
            r"거래대상\s+거래조건\s+거래목적\s+거래금액.*?\s([가-힣A-Za-z0-9ㆍ\s]{2,40})\s+[0-9][0-9,]*\s+(?:수의계약|경쟁입찰|제한경쟁입찰|지명경쟁입찰)",
        ])
        if purpose in {"거래금액", "계약체결방식", "거래대상 거래조건 거래목적 거래금액"}:
            purpose = self._find_pattern_value(text, [
                r"거래조건\s+거래목적\s+거래금액\s+계약체결방식.*?\s([가-힣A-Za-z0-9ㆍ\s]{2,50})\s+[0-9][0-9,]*\s+(?:수의계약|경쟁입찰|제한경쟁입찰|지명경쟁입찰)",
            ])
        self._append_metric_if_missing(metrics, "거래목적", self._truncate_metric_value(purpose, 32))
        transaction_date = self._find_pattern_value(text, [
            r"거래일자\s*(\d{4}[.\-/년]\s*\d{1,2}[.\-/월]\s*\d{1,2}\s*일?)",
        ])
        self._append_metric_if_missing(metrics, "거래일자", self._shorten_metric_value("거래일자", transaction_date))
        board_date = self._find_pattern_value(text, [
            r"이사회\s*의결일\s*(\d{4}[.\-/년]\s*\d{1,2}[.\-/월]\s*\d{1,2}\s*일?)",
            r"이사회의결일\s*(\d{4}[.\-/년]\s*\d{1,2}[.\-/월]\s*\d{1,2}\s*일?)",
        ])
        self._append_metric_if_missing(metrics, "이사회 의결일", self._shorten_metric_value("이사회 의결일", board_date))

    def _extract_funding_purpose(self, text: str) -> str:
        purposes = [keyword for keyword in ["시설자금", "운영자금", "채무상환자금", "타법인 증권 취득자금", "타법인증권취득자금", "기타자금"] if keyword in text]
        return ", ".join(dict.fromkeys(purposes))

    def _append_treasury_trust_cancel_metrics(self, text: str, metrics: list[dict[str, str]]) -> None:
        amount = self._find_pattern_value(text, [
            r"해지금액\s*\(\s*원\s*\)\s*([0-9][0-9,]*)",
            r"계약금액\s*\(\s*원\s*\)\s*([0-9][0-9,]*)",
            r"신탁계약금액\s*\(\s*원\s*\)\s*([0-9][0-9,]*)",
        ])
        self._append_metric_if_missing(metrics, "해지금액", self._normalize_won_value(amount))
        counterparty = self._find_pattern_value(text, [
            r"계약상대방\s*([^\n\r]{1,80}?)(?:\s+\d+\.|\s+해지|\s+계약|\s+기타)",
        ])
        self._append_metric_if_missing(metrics, "계약상대", self._clean_counterparty(counterparty))
        reason = self._find_pattern_value(text, [
            r"해지사유\s*([^\n\r]{1,120}?)(?:\s+\d+\.|\s+해지일|\s+기타|\s*$)",
        ])
        self._append_metric_if_missing(metrics, "해지사유", self._truncate_metric_value(reason, 40))
        cancel_date = self._find_pattern_value(text, [
            r"해지일자\s*(\d{4}[.\-/년]\s*\d{1,2}[.\-/월]\s*\d{1,2}\s*일?)",
            r"해지예정일자\s*(\d{4}[.\-/년]\s*\d{1,2}[.\-/월]\s*\d{1,2}\s*일?)",
        ])
        self._append_metric_if_missing(metrics, "해지일자", self._shorten_metric_value("해지일자", cancel_date))

    def _append_delisting_risk_metrics(self, text: str, metrics: list[dict[str, str]]) -> None:
        reason = self._find_pattern_value(text, [
            r"상장폐지\s*사유\s*([^\n\r]{1,120}?)(?:\s+\d+\.|\s+개선기간|\s+심사|\s+기타|\s*$)",
            r"\((상장폐지[^\)]{1,60})\)",
            r"(상장폐지\s*[^\n\r]{1,80}?)(?:\s+\d+\.|\s+기타|\s*$)",
        ])
        self._append_metric_if_missing(metrics, "위험사유", self._truncate_metric_value(reason, 40))
        if reason:
            self._append_metric_if_missing(metrics, "상장폐지사유", self._truncate_metric_value(reason, 40))
        schedule = self._find_pattern_value(text, [
            r"(코스닥시장위원회\s*개최\s*결과[^\n\r]{0,80})",
            r"(정리매매\s*개시[^\n\r]{0,80})",
            r"(이의신청서\s*접수[^\n\r]{0,80})",
        ])
        self._append_metric_if_missing(metrics, "심사일정", self._truncate_metric_value(schedule, 40))

    def _append_trading_halt_metrics(self, text: str, metrics: list[dict[str, str]]) -> None:
        reason = self._find_pattern_value(text, [
            r"\(([^)]*(?:거래정지|감자|상장폐지|변경상장)[^)]*)\)",
            r"매매거래정지\s*사유\s*([^\n\r]{1,100})",
            r"거래정지\s*사유\s*([^\n\r]{1,100})",
        ])
        self._append_metric_if_missing(metrics, "거래정지사유", self._truncate_metric_value(reason, 40))
        halt_date = self._find_pattern_value(text, [
            r"정지일시\s*(\d{4}[.\-/년]\s*\d{1,2}[.\-/월]\s*\d{1,2}\s*일?)",
            r"정지기간\s*(\d{4}[.\-/년]\s*\d{1,2}[.\-/월]\s*\d{1,2}\s*일?)",
        ])
        self._append_metric_if_missing(metrics, "거래정지일", self._shorten_metric_value("거래정지일", halt_date))
        release = self._find_pattern_value(text, [
            r"해제일시\s*(\d{4}[.\-/년]\s*\d{1,2}[.\-/월]\s*\d{1,2}\s*일?)",
            r"매매거래정지해제\s*일시\s*(\d{4}[.\-/년]\s*\d{1,2}[.\-/월]\s*\d{1,2}\s*일?)",
        ])
        self._append_metric_if_missing(metrics, "해제일시", self._shorten_metric_value("해제일시", release))

    def _append_other_corp_share_metrics(self, text: str, metrics: list[dict[str, str]]) -> None:
        amount = self._find_pattern_value(text, [
            r"(?:취득|처분|양수|양도)\s*금액\s*\(\s*원\s*\)\s*([0-9][0-9,]*)",
            r"(?:취득|처분|양수|양도)가액\s*\(\s*원\s*\)\s*([0-9][0-9,]*)",
            r"거래금액\s*\(\s*원\s*\)\s*([0-9][0-9,]*)",
        ])
        self._append_metric_if_missing(metrics, "거래금액", self._normalize_won_value(amount))
        counterparty = self._find_pattern_value(text, [
            r"발행회사\s*([^\n\r]{1,80}?)(?:\s+회사와의|\s+국적|\s+대표자|\s+자본금)",
            r"거래상대방\s*([^\n\r]{1,80}?)(?:\s+회사와의|\s+생년월일|\s+국적|\s+\d+\.)",
        ])
        self._append_metric_if_missing(metrics, "거래상대방", self._clean_counterparty(counterparty))
        purpose = self._find_pattern_value(text, [
            r"(?:취득|처분|양수|양도)\s*목적\s*([^\n\r]{1,120}?)(?:\s+\d+\.|\s+(?:취득|처분|양수|양도)예정|\s+기타|\s*$)",
        ])
        self._append_metric_if_missing(metrics, "거래목적", self._truncate_metric_value(purpose, 40))
        date = self._find_pattern_value(text, [
            r"취득예정일자\s*(\d{4}[.\-/년]\s*\d{1,2}[.\-/월]\s*\d{1,2}\s*일?)",
            r"처분예정일자\s*(\d{4}[.\-/년]\s*\d{1,2}[.\-/월]\s*\d{1,2}\s*일?)",
        ])
        self._append_metric_if_missing(metrics, "취득예정일", self._shorten_metric_value("취득예정일", date))
        ratio = self._find_pattern_value(text, [
            r"자기자본대비\s*\(\s*%\s*\)\s*([0-9]+(?:\.[0-9]+)?)",
        ])
        self._append_metric_if_missing(metrics, "자기자본대비", f"{ratio}%" if ratio else "")

    def _append_major_management_metrics(self, text: str, metrics: list[dict[str, str]]) -> None:
        content = self._find_pattern_value(text, [
            r"주요내용\s*([^\n\r]{1,180}?)(?:\s+\d+\.|\s+기타|\s+관련공시|\s*$)",
            r"투자판단\s*관련\s*주요경영사항\s*([^\n\r]{1,180}?)(?:\s+\d+\.|\s+기타|\s*$)",
        ])
        self._append_metric_if_missing(metrics, "주요내용", self._truncate_metric_value(content, 60))
        counterparty = self._find_pattern_value(text, [
            r"계약상대방\s*([^\n\r]{1,80}?)(?:\s+회사와의|\s+\d+\.|\s+계약)",
        ])
        self._append_metric_if_missing(metrics, "계약상대", self._clean_counterparty(counterparty))
        amount = self._find_pattern_value(text, [
            r"계약금액\s*\(\s*원\s*\)\s*([0-9][0-9,]*)",
            r"투자금액\s*\(\s*원\s*\)\s*([0-9][0-9,]*)",
        ])
        self._append_metric_if_missing(metrics, "계약금액", self._normalize_won_value(amount))
        schedule = self._find_pattern_value(text, [
            r"(?:추진|진행|승인|허가|계약)\s*일정\s*([^\n\r]{1,80})",
            r"(?:승인|허가)일자\s*(\d{4}[.\-/년]\s*\d{1,2}[.\-/월]\s*\d{1,2}\s*일?)",
        ])
        self._append_metric_if_missing(metrics, "추진일정", self._truncate_metric_value(schedule, 36))

    def _append_merger_completion_metrics(self, text: str, metrics: list[dict[str, str]]) -> None:
        date = self._find_pattern_value(text, [
            r"합병기일\s*(\d{4}[.\-/년]\s*\d{1,2}[.\-/월]\s*\d{1,2}\s*일?)",
            r"종료일\s*(\d{4}[.\-/년]\s*\d{1,2}[.\-/월]\s*\d{1,2}\s*일?)",
        ])
        self._append_metric_if_missing(metrics, "합병기일", self._shorten_metric_value("합병기일", date))
        ratio = self._find_pattern_value(text, [
            r"합병비율\s*([0-9]+(?:\.[0-9]+)?\s*[:：]\s*[0-9]+(?:\.[0-9]+)?)",
        ])
        self._append_metric_if_missing(metrics, "합병비율", ratio)
        target = self._find_pattern_value(text, [
            r"피합병회사\s*([^\n\r]{1,80}?)(?:\s+합병|\s+회사|\s+\d+\.)",
            r"상대회사\s*([^\n\r]{1,80}?)(?:\s+합병|\s+회사|\s+\d+\.)",
        ])
        self._append_metric_if_missing(metrics, "합병상대회사", self._clean_counterparty(target))

    def _append_largest_holder_contract_metrics(self, text: str, metrics: list[dict[str, str]]) -> None:
        holder = self._find_pattern_value(text, [
            r"변경예정\s*최대주주\s*([^\n\r]{1,80}?)(?:\s+예정|\s+소유|\s+계약|\s+\d+\.)",
            r"양수인\s*([^\n\r]{1,80}?)(?:\s+회사와의|\s+계약|\s+\d+\.)",
        ])
        self._append_metric_if_missing(metrics, "변경예정 최대주주", self._clean_counterparty(holder))
        amount = self._find_pattern_value(text, [
            r"양수도대금\s*\(\s*원\s*\)\s*([0-9][0-9,]*)",
            r"계약금액\s*\(\s*원\s*\)\s*([0-9][0-9,]*)",
            r"총\s*양수도금액\s*\(\s*원\s*\)\s*([0-9][0-9,]*)",
        ])
        self._append_metric_if_missing(metrics, "계약금액", self._normalize_won_value(amount))
        ratio = self._find_pattern_value(text, [
            r"예정\s*소유비율\s*\(\s*%\s*\)\s*([0-9]+(?:\.[0-9]+)?)",
            r"지분율\s*\(\s*%\s*\)\s*([0-9]+(?:\.[0-9]+)?)",
        ])
        self._append_metric_if_missing(metrics, "예정지분율", f"{ratio}%" if ratio else "")
        date = self._find_pattern_value(text, [
            r"변경예정일자\s*(\d{4}[.\-/년]\s*\d{1,2}[.\-/월]\s*\d{1,2}\s*일?)",
            r"계약체결일\s*(\d{4}[.\-/년]\s*\d{1,2}[.\-/월]\s*\d{1,2}\s*일?)",
        ])
        self._append_metric_if_missing(metrics, "변경예정일", self._shorten_metric_value("변경예정일", date))

    def _append_tender_offer_metrics(self, text: str, metrics: list[dict[str, str]]) -> None:
        buyer = self._find_pattern_value(text, [
            r"공개매수자\s*ㆍ?\s*성명\s*[:：]\s*([^\n\r]{1,80}?)(?:\s+■|\s+□|\s+주\s*소|\s+전화번호)",
            r"공개매수자\s*([^\n\r]{1,80}?)(?:\s+회사와의|\s+특별관계|\s+\d+\.)",
        ])
        self._append_metric_if_missing(metrics, "공개매수자", self._clean_counterparty(buyer))
        price = self._find_pattern_value(text, [
            r"매수가격\s*\(\s*원\s*\)\s*([0-9][0-9,]*)",
            r"공개매수\s*가격\s*([0-9][0-9,]*)",
            r"1주당\s*매수\s*가격\s*([0-9][0-9,]*)",
            r"매수\s*가격\s*주당\s*([0-9][0-9,]*)\s*원",
        ])
        self._append_metric_if_missing(metrics, "매수가격", self._normalize_won_value(price))
        quantity = self._find_pattern_value(text, [
            r"매수예정수량\s*\(\s*주\s*\)\s*([0-9][0-9,]*)",
            r"매수예정\s*주식수\s*([0-9][0-9,]*)",
            r"매수\s*예정\s*수량\s*\([^)]*\)\s*([0-9][0-9,]*)\s*주",
        ])
        self._append_metric_if_missing(metrics, "매수예정수량", self._normalize_stock_count_value(quantity))
        period = self._find_pattern_value(text, [
            r"공개매수기간\s*([^\n\r]{1,80}?)(?:\s+\d+\.|\s+결제일|\s+매수|\s*$)",
        ])
        self._append_metric_if_missing(metrics, "공개매수기간", self._truncate_metric_value(period, 36))
        purpose = self._find_pattern_value(text, [
            r"공개매수\s*목적\s*([^\n\r]{1,120}?)(?:\s+\d+\.|\s+공개매수|\s+기타|\s*$)",
        ])
        self._append_metric_if_missing(metrics, "매수목적", self._truncate_metric_value(purpose, 40))

    def _append_stock_option_metrics(self, text: str, metrics: list[dict[str, str]]) -> None:
        exercised = self._find_pattern_value(text, [
            r"행사주식수\s*현황.*?주식수\s*합계\s+[0-9][0-9,]*\s+([0-9][0-9,]*)",
            r"행사주식수\s*\(\s*주\s*\)\s*([0-9][0-9,]*)",
            r"금번\s*행사\s*수량\s*[:：]?\s*([0-9][0-9,]*)\s*주",
        ])
        self._append_metric_if_missing(metrics, "행사주식수", self._normalize_stock_count_value(exercised))
        shares = self._find_pattern_value(text, [
            r"(?:부여|행사)\s*주식수\s*\(\s*주\s*\)\s*([0-9][0-9,]*)",
            r"부여주식수\s*([0-9][0-9,]*)",
            r"총\s*부여\s*수량\s*[:：]?\s*([0-9][0-9,]*)\s*주",
        ])
        self._append_metric_if_missing(metrics, "부여주식수", self._normalize_stock_count_value(shares))
        price = self._find_pattern_value(text, [
            r"행사가격\s*\(\s*원\s*\)\s*([0-9][0-9,]*)",
            r"행사가액\s*\(\s*원\s*\)\s*([0-9][0-9,.]*)",
            r"행사가액\s*[:：]\s*([0-9][0-9,.]*)\s*원",
        ])
        self._append_metric_if_missing(metrics, "행사가격", self._normalize_won_value(price))
        target = self._find_pattern_value(text, [
            r"부여대상자\s*([^\n\r]{1,80}?)(?:\s+부여|\s+주식|\s+\d+\.)",
        ])
        self._append_metric_if_missing(metrics, "부여대상", self._truncate_metric_value(target, 32))
        period = self._find_pattern_value(text, [
            r"행사기간\s*[:：]?\s*([0-9]{4}[.\-/년][^\n\r]{1,40}?)(?:\s+\d+\)|\s+\d+\.|\s+기타|\s*$)",
        ])
        self._append_metric_if_missing(metrics, "행사기간", self._truncate_metric_value(period, 36))
        date = self._find_pattern_value(text, [
            r"부여일\s*(\d{4}[.\-/년]\s*\d{1,2}[.\-/월]\s*\d{1,2}\s*일?)",
            r"행사일\s*(\d{4}[.\-/년]\s*\d{1,2}[.\-/월]\s*\d{1,2}\s*일?)",
        ])
        self._append_metric_if_missing(metrics, "부여일", self._shorten_metric_value("부여일", date))
        listing = self._find_pattern_value(text, [
            r"신주상장예정일\s*([0-9]{4}[.\-/년]\s*[0-9]{1,2}[.\-/월]\s*[0-9]{1,2}\s*일?)",
        ])
        self._append_metric_if_missing(metrics, "상장예정일", self._shorten_metric_value("상장예정일", listing))

    def _append_conversion_price_adjustment_metrics(self, text: str, metrics: list[dict[str, str]]) -> None:
        before_from_table = ""
        after_from_table = ""
        table_match = re.search(
            r"조정전\s*전환가액\s*\(\s*원\s*\)\s*조정후\s*전환가액\s*\(\s*원\s*\)\s*\d+\s+\S+\s+([0-9][0-9,]*)\s+([0-9][0-9,]*)",
            text,
        )
        if table_match:
            before_from_table, after_from_table = table_match.group(1), table_match.group(2)
        before = before_from_table or self._find_pattern_value(text, [
            r"조정전\s*전환가액\s*\(\s*원\s*\)\s*([0-9][0-9,]*)",
            r"조정\s*전\s*전환가액\s*([0-9][0-9,]*)",
        ])
        self._append_metric_if_missing(metrics, "조정전 전환가액", self._normalize_won_value(before))
        after = after_from_table or self._find_pattern_value(text, [
            r"조정후\s*전환가액\s*\(\s*원\s*\)\s*([0-9][0-9,]*)",
            r"조정\s*후\s*전환가액\s*([0-9][0-9,]*)",
            r"⑧조정후\s*전환가액\s*[:：]\s*([0-9][0-9,]*)\s*원",
        ])
        self._append_metric_if_missing(metrics, "조정후 전환가액", self._normalize_won_value(after))
        reason = self._find_pattern_value(text, [
            r"조정사유\s*([^\n\r]{1,120}?)(?:\s+\d+\.|\s+조정|\s+기타|\s*$)",
        ])
        self._append_metric_if_missing(metrics, "조정사유", self._truncate_metric_value(reason, 40))
        date = self._find_pattern_value(text, [
            r"조정가액\s*적용일\s*(\d{4}[.\-/년]\s*\d{1,2}[.\-/월]\s*\d{1,2}\s*일?)",
            r"적용일\s*(\d{4}[.\-/년]\s*\d{1,2}[.\-/월]\s*\d{1,2}\s*일?)",
        ])
        self._append_metric_if_missing(metrics, "적용일", self._shorten_metric_value("적용일", date))

    def _append_unfaithful_disclosure_metrics(self, text: str, metrics: list[dict[str, str]]) -> None:
        reason = self._find_pattern_value(text, [
            r"지정사유\s*([^\n\r]{1,120}?)(?:\s+\d+\.|\s+부과벌점|\s+벌점|\s+공시위반|\s*$)",
            r"불성실공시\s*유형\s*([^\n\r]{1,40}?)\s*3\.\s*불성실공시\s*내용\s*([^\n\r]{1,120}?)(?:\s+4\.|\s+예고일자)",
            r"불성실공시\s*내용\s*([^\n\r]{1,120}?)(?:\s+4\.|\s+예고일자)",
            r"\((공시[^\)]{1,60})\)",
        ])
        self._append_metric_if_missing(metrics, "지정사유", self._truncate_metric_value(reason, 40))
        penalty = self._find_pattern_value(text, [
            r"부과벌점\s*([0-9]+(?:\.[0-9]+)?)",
            r"벌점\s*([0-9]+(?:\.[0-9]+)?)",
        ])
        self._append_metric_if_missing(metrics, "벌점", f"{penalty}점" if penalty else "")
        fine = self._find_pattern_value(text, [
            r"공시위반제재금\s*\(\s*원\s*\)\s*([0-9][0-9,]*)",
            r"제재금\s*\(\s*원\s*\)\s*([0-9][0-9,]*)",
        ])
        self._append_metric_if_missing(metrics, "제재금", self._normalize_won_value(fine))
        date = self._find_pattern_value(text, [
            r"지정일\s*(\d{4}[.\-/년]\s*\d{1,2}[.\-/월]\s*\d{1,2}\s*일?)",
            r"지정예고일\s*(\d{4}[.\-/년]\s*\d{1,2}[.\-/월]\s*\d{1,2}\s*일?)",
        ])
        self._append_metric_if_missing(metrics, "지정일", self._shorten_metric_value("지정일", date))

    def _append_admin_issue_metrics(self, text: str, metrics: list[dict[str, str]]) -> None:
        reason = self._find_pattern_value(text, [
            r"\(([^)]*(?:관리종목|투자주의|환기|시가총액|거래량)[^)]*)\)",
            r"지정사유\s*([^\n\r]{1,120}?)(?:\s+\d+\.|\s+기타|\s*$)",
        ])
        self._append_metric_if_missing(metrics, "지정사유", self._truncate_metric_value(reason, 40))
        release = self._find_pattern_value(text, [
            r"해제사유\s*([^\n\r]{1,120}?)(?:\s+\d+\.|\s+기타|\s*$)",
        ])
        self._append_metric_if_missing(metrics, "해제사유", self._truncate_metric_value(release, 40))
        action = self._find_pattern_value(text, [
            r"(시장조치[^\n\r]{1,80})",
            r"(매매거래정지[^\n\r]{1,80})",
        ])
        self._append_metric_if_missing(metrics, "시장조치", self._truncate_metric_value(action, 40))

    def _append_audit_opinion_metrics(self, text: str, metrics: list[dict[str, str]]) -> None:
        opinion = self._find_pattern_value(text, [
            r"'(의견거절|한정|부적정|적정)'",
            r"(의견거절|한정|부적정|적정)",
            r"감사의견\s*([^\n\r]{1,80}?)(?:\s+계속기업|\s+강조사항|\s+감사인|\s+\d+\.)",
        ])
        self._append_metric_if_missing(metrics, "감사의견", self._truncate_metric_value(opinion, 24))
        reason = self._find_pattern_value(text, [
            r"(계속기업\s*존속능력에\s*대한\s*불확실성)",
            r"(계속기업불확실성\s*사유\s*해소가\s*불가능)",
            r"(감사의견거절\s*사유\s*해소에\s*대한\s*감사인의\s*확인서\s*미제출)",
            r"감사의견(?:거절)?\s*사유\s*([^\n\r]{1,140}?)(?:\s+\d+\.|\s+해소|\s+기타|\s*$)",
            r"(계속기업\s*불확실성[^\n\r]{0,80})",
        ])
        self._append_metric_if_missing(metrics, "위험사유", self._truncate_metric_value(reason, 48))
        auditor = self._find_pattern_value(text, [
            r"감사인\s*([^\n\r]{1,80}?)(?:\s+감사의견|\s+\d+\.|\s+기타)",
        ])
        auditor_value = self._clean_counterparty(auditor)
        if "미제출" in auditor_value or "확인서" in auditor_value:
            auditor_value = ""
        self._append_metric_if_missing(metrics, "감사인", auditor_value)

    def _append_short_term_borrowing_metrics(self, text: str, metrics: list[dict[str, str]]) -> None:
        amount = self._find_pattern_value(text, [
            r"단기차입금\s*증가금액\s*\(\s*원\s*\)\s*([0-9][0-9,]*)",
            r"차입금액\s*\(\s*원\s*\)\s*([0-9][0-9,]*)",
            r"증가금액\s*\(\s*원\s*\)\s*([0-9][0-9,]*)",
        ])
        self._append_metric_if_missing(metrics, "차입금액", self._normalize_won_value(amount))
        purpose = self._find_pattern_value(text, [
            r"차입목적\s*([^\n\r]{1,120}?)(?:\s+\d+\.|\s+차입|\s+기타|\s*$)",
        ])
        self._append_metric_if_missing(metrics, "차입목적", self._truncate_metric_value(purpose, 40))
        ratio = self._find_pattern_value(text, [
            r"자기자본대비\s*\(\s*%\s*\)\s*([0-9]+(?:\.[0-9]+)?)",
        ])
        self._append_metric_if_missing(metrics, "자기자본대비", f"{ratio}%" if ratio else "")
        total = self._find_pattern_value(text, [
            r"차입후\s*총차입금\s*\(\s*원\s*\)\s*([0-9][0-9,]*)",
            r"차입\s*후\s*총\s*차입금\s*([0-9][0-9,]*)",
        ])
        self._append_metric_if_missing(metrics, "차입후 총차입금", self._normalize_won_value(total))

    def _append_collateral_metrics(self, text: str, metrics: list[dict[str, str]]) -> None:
        amount = self._find_pattern_value(text, [
            r"담보제공금액\s*\(\s*원\s*\)\s*([0-9][0-9,]*)",
            r"담보설정금액\s*\(\s*원\s*\)\s*([0-9][0-9,]*)",
        ])
        self._append_metric_if_missing(metrics, "담보제공금액", self._normalize_won_value(amount))
        target = self._find_pattern_value(text, [
            r"담보제공\s*대상\s*([^\n\r]{1,80}?)(?:\s+회사와의|\s+담보|\s+\d+\.)",
            r"채무자\s*([^\n\r]{1,80}?)(?:\s+회사와의|\s+담보|\s+\d+\.)",
        ])
        self._append_metric_if_missing(metrics, "담보제공대상", self._clean_counterparty(target))
        ratio = self._find_pattern_value(text, [
            r"자기자본대비\s*\(\s*%\s*\)\s*([0-9]+(?:\.[0-9]+)?)",
        ])
        self._append_metric_if_missing(metrics, "자기자본대비", f"{ratio}%" if ratio else "")
        period = self._find_pattern_value(text, [
            r"담보제공기간\s*([^\n\r]{1,100}?)(?:\s+\d+\.|\s+기타|\s*$)",
        ])
        self._append_metric_if_missing(metrics, "담보제공기간", self._truncate_metric_value(period, 36))
        reason = self._find_pattern_value(text, [
            r"담보제공사유\s*([^\n\r]{1,120}?)(?:\s+\d+\.|\s+기타|\s*$)",
        ])
        self._append_metric_if_missing(metrics, "담보제공사유", self._truncate_metric_value(reason, 40))

    def _append_supply_contract_fallback_metrics(self, text: str, metrics: list[dict[str, str]]) -> None:
        existing_labels = {metric.get("label") for metric in metrics}

        if "계약금액" not in existing_labels:
            amount = self._find_pattern_value(text, [
                r"계약\s*금액\s*[:：]?\s*([^\n\r]{1,100})",
                r"계약금액\s*[:：]?\s*([^\n\r]{1,100})",
            ])
            amount = self._shorten_metric_value("계약금액", amount)
            if amount:
                metrics.append({"label": "계약금액", "value": amount})
                existing_labels.add("계약금액")

        if "매출액대비" not in existing_labels:
            ratio = self._find_pattern_value(text, [
                r"매출액\s*대비\s*[:：]?\s*([^\n\r]{0,80}?\d+(?:\.\d+)?\s*%)",
                r"최근\s*매출액\s*대비\s*[:：]?\s*([^\n\r]{0,80}?\d+(?:\.\d+)?\s*%)",
                r"매출\s*대비\s*[:：]?\s*([^\n\r]{0,80}?\d+(?:\.\d+)?\s*%)",
                r"매출액대비\s*[:：]?\s*([^\n\r]{0,80}?\d+(?:\.\d+)?\s*%)",
            ])
            ratio = self._shorten_metric_value("매출액대비", ratio)
            if ratio:
                metrics.append({"label": "매출액대비", "value": ratio})

    def _find_pattern_value(self, text: str, patterns: list[str]) -> str:
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                return self._clean_text(match.group(1))
        return ""

    def _build_check_items(
        self,
        category: str,
        metrics: list[dict[str, str]],
        text: str,
        source: str,
    ) -> list[dict[str, str]]:
        metric_map = {metric.get("label"): metric.get("value") for metric in metrics if metric.get("label") and metric.get("value")}
        checks: list[dict[str, str]] = []

        if category in {"자금조달·증권신고서", "자금조달·증권발행"}:
            purpose = metric_map.get("자금의 사용목적") or metric_map.get("자금조달의 목적")
            checks.append(self._check_item(
                "자금 목적",
                purpose or "확인 필요",
                "시설투자·인수면 긍정, 운영자금·채무상환이면 주의가 필요합니다.",
                "positive" if purpose and any(item in purpose for item in ["시설자금", "타법인증권취득자금"]) else "caution",
            ))
            checks.append(self._check_item(
                "희석 가능성",
                metric_map.get("신주의 수") or "확인 필요",
                "새 주식이나 전환 가능 물량이 많으면 기존 주주 지분이 희석될 수 있습니다.",
                "caution",
            ))
            checks.append(self._check_item(
                "발행 조건",
                metric_map.get("발행가액") or metric_map.get("납입일") or "확인 필요",
                "발행가액, 납입일, 배정 대상에 따라 해석이 달라집니다.",
                "caution",
            ))
            return checks

        if category == "유상증자 발행가액 확정":
            checks.append(self._check_item(
                "최종 발행가",
                metric_map.get("확정발행가액") or metric_map.get("발행가액") or "확인 필요",
                "최종 발행가가 확정되면 실제 조달 규모와 기존 주주 청약 판단 기준이 더 명확해집니다.",
                "caution",
            ))
            checks.append(self._check_item(
                "발행 주식 수",
                metric_map.get("발행주식수") or metric_map.get("신주의 수") or "확인 필요",
                "발행 주식 수는 희석 규모와 총 조달금액을 가늠하는 핵심 수치입니다.",
                "caution",
            ))
            checks.append(self._check_item(
                "확정일",
                metric_map.get("확정일") or metric_map.get("청약예정일") or metric_map.get("납입일") or "확인 필요",
                "확정일과 청약 일정은 단기 수급 변동 시점을 볼 때 중요합니다.",
                "caution",
            ))
            return checks

        if category == "수주·공급계약":
            ratio = metric_map.get("매출액대비")
            ratio_value = self._percent_to_float(ratio)
            checks.append(self._check_item(
                "계약 규모",
                ratio or metric_map.get("계약금액") or "확인 필요",
                "최근 매출 대비 비중이 클수록 실적 영향 가능성이 커집니다.",
                "positive" if ratio_value is not None and ratio_value >= 10 else "info",
            ))
            checks.append(self._check_item(
                "계약 상대",
                metric_map.get("계약상대") or "확인 필요",
                "공공기관·대기업 등 신뢰도 높은 상대면 계약 안정성이 높아집니다.",
                "positive" if self._contains(metric_map.get("계약상대") or "", ["공사", "공단", "정부", "삼성", "현대", "LG", "SK", "한국"]) else "info",
            ))
            checks.append(self._check_item(
                "계약 기간",
                metric_map.get("계약기간") or "확인 필요",
                "장기 계약인지, 단기 일회성 계약인지 확인해야 합니다.",
                "info",
            ))
            return checks

        if category == "공급계약 해지":
            checks.append(self._check_item(
                "해지 규모",
                metric_map.get("해지금액") or metric_map.get("매출액대비") or "확인 필요",
                "기존 매출 기대가 사라지는 공시라 해지 금액과 매출 대비 비중이 중요합니다.",
                "negative",
            ))
            checks.append(self._check_item(
                "해지 사유",
                metric_map.get("해지사유") or "확인 필요",
                "상대방 귀책인지, 회사 귀책인지에 따라 악재 강도가 달라집니다.",
                "negative",
            ))
            return checks

        if category == "증권 발행결과":
            checks.append(self._check_item(
                "발행 결과",
                metric_map.get("실제발행금액") or metric_map.get("실제발행주식수") or "확인 필요",
                "증권 발행결과는 실제 납입과 발행 규모가 확정됐는지 보는 공시입니다.",
                "caution",
            ))
            checks.append(self._check_item(
                "납입 일정",
                metric_map.get("납입일") or metric_map.get("상장예정일") or "확인 필요",
                "납입 완료 여부와 신주 상장일 전후 수급 변동을 확인해야 합니다.",
                "caution",
            ))
            return checks

        if category == "채무증권 발행":
            checks.append(self._check_item(
                "발행 규모",
                metric_map.get("발행총액") or "확인 필요",
                "채무증권 발행은 차입성 자금조달이므로 발행 규모와 상환 부담을 확인해야 합니다.",
                "caution",
            ))
            checks.append(self._check_item(
                "조달 목적",
                metric_map.get("자금조달의 목적") or "확인 필요",
                "운영자금·채무상환 목적이면 재무 부담 성격이 강할 수 있습니다.",
                "caution",
            ))
            return checks

        if category == "주식관련사채":
            checks.append(self._check_item(
                "사채 규모",
                metric_map.get("사채의 권면총액") or "확인 필요",
                "전환사채·신주인수권부사채는 조달 규모가 크면 희석 부담이 커질 수 있습니다.",
                "caution",
            ))
            checks.append(self._check_item(
                "전환 조건",
                metric_map.get("전환가액") or metric_map.get("행사가액") or metric_map.get("교환가액") or "확인 필요",
                "전환·행사 가격이 현재 주가와 가까울수록 주식 전환 가능성을 더 봐야 합니다.",
                "caution",
            ))
            checks.append(self._check_item(
                "청구 기간",
                metric_map.get("전환청구기간") or metric_map.get("행사청구기간") or "확인 필요",
                "전환청구 가능 시점부터 오버행 부담이 생길 수 있습니다.",
                "caution",
            ))
            return checks

        if category == "정정 공시":
            checks.append(self._check_item(
                "정정 내용",
                "원문 확인 필요",
                "금액·기간·상대방 등 핵심 조건이 바뀌었는지 확인해야 합니다.",
                "caution",
            ))
            checks.append(self._check_item(
                "정정 방향",
                "원공시 비교 필요",
                "호재가 축소됐는지, 악재가 커졌는지 비교해야 합니다.",
                "caution",
            ))
            return checks

        if category == "특수관계인·내부거래":
            checks.append(self._check_item(
                "거래 상대",
                metric_map.get("거래상대방") or "확인 필요",
                "계열사·특수관계인과의 거래는 가격과 조건이 공정한지 확인해야 합니다.",
                "caution",
            ))
            checks.append(self._check_item(
                "거래 목적",
                metric_map.get("거래목적") or "확인 필요",
                "회사에 유리한 거래인지, 계열사 지원 성격인지 확인해야 합니다.",
                "caution",
            ))
            return checks

        if category == "사업계획·전망":
            checks.append(self._check_item(
                "구체성",
                "원문 확인 필요",
                "숫자 목표와 기한이 있으면 신뢰도가 높고, 추상적이면 참고 수준입니다.",
                "info",
            ))
            checks.append(self._check_item(
                "실행 여부",
                "후속 확인 필요",
                "계획 발표보다 실제 투자·실적 반영 여부가 중요합니다.",
                "info",
            ))
            return checks

        if category == "액면분할":
            checks.append(self._check_item(
                "분할 비율",
                metric_map.get("분할비율") or "확인 필요",
                "액면분할은 주식 수와 1주당 가격 단위가 바뀌는 이벤트라 비율을 확인해야 합니다.",
                "info",
            ))
            checks.append(self._check_item(
                "상장 일정",
                metric_map.get("신주권상장예정일") or metric_map.get("매매거래정지기간") or "확인 필요",
                "거래정지 기간과 신주권 상장일 전후로 단기 변동이 생길 수 있습니다.",
                "info",
            ))
            return checks

        if category == "액면병합":
            checks.append(self._check_item(
                "병합 비율",
                metric_map.get("병합비율") or "확인 필요",
                "액면병합은 주식 수가 줄고 1주당 가격 단위가 커지는 이벤트라 비율 확인이 필요합니다.",
                "caution",
            ))
            checks.append(self._check_item(
                "거래정지 일정",
                metric_map.get("매매거래정지기간") or metric_map.get("신주권상장예정일") or "확인 필요",
                "병합 과정에서 거래정지가 동반될 수 있어 매매 가능 일정을 확인해야 합니다.",
                "caution",
            ))
            return checks

        if category == "시장 신뢰도 위험":
            checks.append(self._check_item(
                "위험 사유",
                "원문 확인 필요",
                "거래정지·중대재해·감사의견 등은 회사 신뢰도에 부담이 될 수 있습니다.",
                "negative",
            ))
            return checks

        if category == "배당":
            checks.append(self._check_item(
                "배당 규모",
                metric_map.get("1주당 배당금") or metric_map.get("시가배당율") or "확인 필요",
                "배당금과 시가배당률이 높을수록 주주환원 매력이 커집니다.",
                "positive",
            ))
            return checks

        if category == "무상증자":
            checks.append(self._check_item(
                "주식 배정",
                metric_map.get("1주당 배정") or "확인 필요",
                "무상증자는 1주당 배정 비율과 권리락 기준에 따라 단기 가격 조정이 발생할 수 있습니다.",
                "positive",
            ))
            checks.append(self._check_item(
                "신주 규모",
                metric_map.get("보통주 신주") or metric_map.get("기타주식 신주") or "확인 필요",
                "신주 수는 유통 주식 수 증가 폭과 권리락 후 기준 가격을 볼 때 중요합니다.",
                "info",
            ))
            checks.append(self._check_item(
                "상장 일정",
                metric_map.get("상장예정일") or metric_map.get("배정기준일") or "확인 필요",
                "배정기준일과 상장예정일 전후로 수급 변동이 커질 수 있습니다.",
                "info",
            ))
            return checks

        if category == "횡령·배임":
            checks.append(self._check_item(
                "발생 규모",
                metric_map.get("발생금액") or metric_map.get("자기자본대비") or "확인 필요",
                "횡령·배임 금액과 자기자본 대비 비중은 상장 적격성 심사와 신뢰도 판단의 핵심입니다.",
                "negative",
            ))
            checks.append(self._check_item(
                "회사 대응",
                metric_map.get("향후대책") or metric_map.get("발생사실") or "확인 필요",
                "고소·회수 가능성·내부통제 개선 여부를 확인해야 합니다.",
                "negative",
            ))
            return checks

        if category == "회생절차":
            checks.append(self._check_item(
                "신청 사유",
                metric_map.get("신청사유") or "확인 필요",
                "회생절차는 계속기업 가능성과 채무 조정 이슈가 있어 신청 사유가 중요합니다.",
                "negative",
            ))
            checks.append(self._check_item(
                "법원 일정",
                metric_map.get("관할법원") or metric_map.get("신청일자") or metric_map.get("결정내용") or "확인 필요",
                "개시 결정 여부와 법원 일정에 따라 거래 지속 가능성이 달라집니다.",
                "negative",
            ))
            return checks

        if category == "권리락":
            checks.append(self._check_item(
                "조정 기준가",
                metric_map.get("기준가") or "확인 필요",
                "권리락 기준가는 권리락 이후 가격 비교의 기준이 되는 조정 가격입니다.",
                "info",
            ))
            checks.append(self._check_item(
                "실시일",
                metric_map.get("권리락 실시일") or "확인 필요",
                "권리락 실시일 이후에는 전일 종가와 단순 비교하면 등락을 잘못 볼 수 있습니다.",
                "info",
            ))
            checks.append(self._check_item(
                "권리락 사유",
                metric_map.get("사유") or "확인 필요",
                "무상증자 등 권리락 사유를 함께 봐야 가격 조정 이유를 이해할 수 있습니다.",
                "info",
            ))
            return checks

        if category == "주주환원":
            checks.append(self._check_item(
                "환원 규모",
                metric_map.get("취득예정금액") or metric_map.get("소각예정금액") or "확인 필요",
                "자사주 취득·소각 규모와 실제 실행 여부를 확인해야 합니다.",
                "positive",
            ))
            return checks

        if category == "자사주 소각":
            checks.append(self._check_item(
                "소각 규모",
                metric_map.get("소각예정금액") or metric_map.get("소각예정주식") or "확인 필요",
                "소각은 유통 주식 수 감소로 주주환원 성격이 강하지만 규모가 중요합니다.",
                "positive",
            ))
            checks.append(self._check_item(
                "소각 일정",
                metric_map.get("소각예정일") or "확인 필요",
                "소각 예정일과 실제 이행 여부를 확인해야 합니다.",
                "positive",
            ))
            return checks

        if category == "자기주식 처분":
            checks.append(self._check_item(
                "처분 목적",
                metric_map.get("처분목적") or "확인 필요",
                "임직원 보상·전략 제휴 목적이면 중립에 가깝고, 자금 확보 목적이면 주의가 필요합니다.",
                "caution",
            ))
            checks.append(self._check_item(
                "처분 규모",
                metric_map.get("처분예정금액") or metric_map.get("처분예정주식") or "확인 필요",
                "규모가 크면 단기 수급 부담으로 해석될 수 있습니다.",
                "caution",
            ))
            return checks

        if category == "대표이사 변경":
            checks.append(self._check_item(
                "변경 후 대표",
                metric_map.get("변경후 대표이사") or "확인 필요",
                "대표이사 변경은 경영 방향과 책임 주체가 바뀌는 이벤트라 변경 후 인물이 중요합니다.",
                "caution",
            ))
            checks.append(self._check_item(
                "변경 사유",
                metric_map.get("변경사유") or "확인 필요",
                "임기만료인지, 사임·해임인지에 따라 해석이 달라집니다.",
                "caution",
            ))
            return checks

        if category == "신규 시설투자":
            checks.append(self._check_item(
                "투자 규모",
                metric_map.get("투자금액") or metric_map.get("자기자본대비") or "확인 필요",
                "시설투자는 성장 재료가 될 수 있지만 규모가 크면 재무 부담도 함께 봐야 합니다.",
                "positive" if metric_map.get("투자금액") else "caution",
            ))
            checks.append(self._check_item(
                "투자 목적",
                metric_map.get("투자목적") or metric_map.get("투자대상") or "확인 필요",
                "증설·신제품·수요 대응 목적이면 긍정 여지가 커지고, 유지보수 성격이면 효과가 제한적일 수 있습니다.",
                "info",
            ))
            return checks

        if category == "영업정지":
            checks.append(self._check_item(
                "정지 규모",
                metric_map.get("영업정지금액") or metric_map.get("매출액대비") or "확인 필요",
                "영업정지 금액과 매출 대비 비중이 클수록 실적 충격 가능성이 큽니다.",
                "negative",
            ))
            checks.append(self._check_item(
                "정지 사유",
                metric_map.get("영업정지사유") or "확인 필요",
                "인허가, 제재, 생산 차질 등 사유에 따라 회복 가능성이 달라집니다.",
                "negative",
            ))
            return checks

        if category == "감자":
            checks.append(self._check_item(
                "감자 비율",
                metric_map.get("감자비율") or "확인 필요",
                "감자는 주식 수와 자본금이 줄어드는 이벤트라 감자비율이 핵심입니다.",
                "caution",
            ))
            checks.append(self._check_item(
                "감자 사유",
                metric_map.get("감자사유") or "확인 필요",
                "결손 보전 목적이면 재무구조 악화 신호일 수 있어 주의가 필요합니다.",
                "caution",
            ))
            checks.append(self._check_item(
                "감자 일정",
                metric_map.get("감자기준일") or metric_map.get("상장예정일") or "확인 필요",
                "매매정지, 기준일, 변경상장 일정을 함께 확인해야 합니다.",
                "caution",
            ))
            return checks

        if category == "거래정지":
            checks.append(self._check_item(
                "정지 사유",
                metric_map.get("거래정지사유") or "확인 필요",
                "거래정지는 투자자 보호나 중요 사유 발생 때 내려질 수 있어 사유가 가장 중요합니다.",
                "negative",
            ))
            checks.append(self._check_item(
                "정지 기간",
                metric_map.get("거래정지일") or metric_map.get("해제일시") or "확인 필요",
                "정지 시작일과 해제 조건을 확인해야 매매 가능 시점을 알 수 있습니다.",
                "negative",
            ))
            return checks

        if category == "상장폐지 위험":
            checks.append(self._check_item(
                "위험 사유",
                metric_map.get("위험사유") or metric_map.get("상장폐지사유") or "확인 필요",
                "상장폐지, 관리종목, 감사의견 문제는 시장 신뢰도에 큰 부담입니다.",
                "negative",
            ))
            checks.append(self._check_item(
                "심사 일정",
                metric_map.get("심사일정") or metric_map.get("개선기간") or "확인 필요",
                "거래소 심사 일정과 개선기간 부여 여부를 확인해야 합니다.",
                "negative",
            ))
            return checks

        if category == "최대주주 변경":
            checks.append(self._check_item(
                "변경 사유",
                metric_map.get("변경사유") or "확인 필요",
                "경영권 매각, 지분 승계, 담보권 실행 등 사유에 따라 해석이 크게 달라집니다.",
                "caution",
            ))
            checks.append(self._check_item(
                "새 최대주주",
                metric_map.get("변경후 최대주주") or metric_map.get("지분율") or "확인 필요",
                "새 최대주주의 신뢰도와 지분율이 경영 안정성 판단의 핵심입니다.",
                "caution",
            ))
            return checks

        if category == "합병":
            checks.append(self._check_item(
                "합병 상대",
                metric_map.get("합병상대회사") or "확인 필요",
                "합병 상대의 사업성, 재무상태, 기존 회사와의 시너지를 확인해야 합니다.",
                "caution",
            ))
            checks.append(self._check_item(
                "합병 조건",
                metric_map.get("합병비율") or metric_map.get("합병기일") or "확인 필요",
                "합병비율과 일정은 기존 주주의 이해관계에 직접 영향을 줍니다.",
                "caution",
            ))
            return checks

        if category == "분할":
            checks.append(self._check_item(
                "분할 목적",
                metric_map.get("분할목적") or "확인 필요",
                "사업 전문화 목적이면 긍정 여지가 있고, 부실 분리 목적이면 주의가 필요합니다.",
                "caution",
            ))
            checks.append(self._check_item(
                "분할 구조",
                metric_map.get("분할신설회사") or metric_map.get("분할기일") or "확인 필요",
                "인적분할인지 물적분할인지, 기존 주주에게 어떤 지분이 배정되는지 확인해야 합니다.",
                "caution",
            ))
            return checks

        if category == "소송":
            checks.append(self._check_item(
                "소송 규모",
                metric_map.get("소송가액") or "확인 필요",
                "소송가액이 크면 재무 부담이나 충당부채 가능성을 확인해야 합니다.",
                "negative" if metric_map.get("소송가액") else "caution",
            ))
            checks.append(self._check_item(
                "청구 내용",
                metric_map.get("청구내용") or metric_map.get("판결ㆍ결정내용") or "확인 필요",
                "소송의 성격과 회사 책임 가능성에 따라 악재 강도가 달라집니다.",
                "caution",
            ))
            return checks

        if category == "채무보증":
            checks.append(self._check_item(
                "보증 규모",
                metric_map.get("채무보증금액") or metric_map.get("자기자본대비") or "확인 필요",
                "채무보증은 보증 대상이 갚지 못할 때 회사가 부담할 수 있어 보증 규모가 핵심입니다.",
                "caution",
            ))
            checks.append(self._check_item(
                "보증 대상",
                metric_map.get("채무자") or metric_map.get("채권자") or "확인 필요",
                "채무자와 회사의 관계, 보증 대상의 재무 상태를 확인해야 합니다.",
                "caution",
            ))
            checks.append(self._check_item(
                "보증 기간",
                metric_map.get("채무보증기간") or "확인 필요",
                "보증 기간이 길수록 우발채무 리스크가 오래 유지될 수 있습니다.",
                "caution",
            ))
            return checks

        if category == "전환청구권 행사":
            checks.append(self._check_item(
                "행사 물량",
                metric_map.get("행사주식수") or metric_map.get("발행주식총수 대비") or "확인 필요",
                "전환청구권 행사는 전환사채가 주식으로 바뀌는 이벤트라 실제 유통 물량 증가를 봐야 합니다.",
                "caution",
            ))
            checks.append(self._check_item(
                "전환 조건",
                metric_map.get("전환가액") or metric_map.get("청구금액") or "확인 필요",
                "전환가액과 청구금액은 기존 주주 희석 부담 판단에 중요합니다.",
                "caution",
            ))
            return checks

        if category == "영업실적":
            checks.append(self._check_item(
                "실적 규모",
                metric_map.get("매출액") or metric_map.get("영업이익") or metric_map.get("당기순이익") or "확인 필요",
                "매출과 이익이 함께 개선되는지 봐야 실적의 질을 판단할 수 있습니다.",
                "info",
            ))
            checks.append(self._check_item(
                "증감 방향",
                metric_map.get("전년동기대비") or metric_map.get("직전분기대비") or "확인 필요",
                "전년동기·직전분기 대비 개선인지 악화인지 확인해야 합니다.",
                "info",
            ))
            return checks

        if category == "손익구조 변동":
            checks.append(self._check_item(
                "변동 규모",
                metric_map.get("영업이익") or metric_map.get("당기순이익") or metric_map.get("전년대비") or "확인 필요",
                "손익구조 30% 변동 공시는 이익의 방향과 일회성 요인 여부가 중요합니다.",
                "caution",
            ))
            checks.append(self._check_item(
                "변동 사유",
                metric_map.get("변동사유") or "확인 필요",
                "본업 개선인지 일회성 비용·수익인지에 따라 해석이 달라집니다.",
                "caution",
            ))
            return checks

        if category == "기업가치 제고 계획":
            checks.append(self._check_item(
                "계획 구체성",
                metric_map.get("목표지표") or metric_map.get("주주환원계획") or "확인 필요",
                "밸류업 공시는 구체적인 목표 지표와 주주환원 계획이 있어야 신뢰도가 높습니다.",
                "positive" if metric_map.get("목표지표") or metric_map.get("주주환원계획") else "info",
            ))
            checks.append(self._check_item(
                "실행 일정",
                metric_map.get("이행기간") or metric_map.get("공시주기") or "확인 필요",
                "목표만 있고 실행 시점이 없으면 참고 수준으로 보는 편이 좋습니다.",
                "info",
            ))
            return checks

        if category == "공정공시 중요정보":
            checks.append(self._check_item(
                "핵심 내용",
                metric_map.get("주요내용") or metric_map.get("계약금액") or metric_map.get("전망매출액") or "확인 필요",
                "공정공시는 특정 투자자에게 먼저 줄 수 없는 중요 정보를 동시에 공개하는 성격이라 핵심 내용이 중요합니다.",
                "caution",
            ))
            checks.append(self._check_item(
                "실현 가능성",
                metric_map.get("추진일정") or metric_map.get("계약상대") or "확인 필요",
                "전망·신제품·기술이전·신규사업은 실제 계약, 일정, 매출 반영 여부를 확인해야 합니다.",
                "caution",
            ))
            return checks

        if category == "조회공시 답변":
            checks.append(self._check_item(
                "답변 내용",
                metric_map.get("답변내용") or metric_map.get("진행사항") or "확인 필요",
                "거래소 조회 요구에 대한 답변은 풍문이 사실인지, 진행 중인지, 부인인지가 핵심입니다.",
                "caution",
            ))
            checks.append(self._check_item(
                "후속 일정",
                metric_map.get("답변일") or metric_map.get("조회공시요구일") or "확인 필요",
                "미확정 또는 검토 중 답변이면 추후 재공시 일정이 중요합니다.",
                "caution",
            ))
            return checks

        if source == "TITLE_ONLY":
            checks.append(self._check_item("상세 확인", "제목 기반", "상세 원문을 확인하지 못해 예비 분류만 가능합니다.", "info"))
        return checks

    def _check_item(self, question: str, answer: str, reason: str, signal: str) -> dict[str, str]:
        return {
            "question": question,
            "answer": answer,
            "reason": reason,
            "signal": signal,
        }

    def _refine_sentiment(
        self,
        category: str,
        sentiment: str,
        confidence: str,
        check_items: list[dict[str, str]],
    ) -> tuple[str, str]:
        signals = [item.get("signal") for item in check_items]
        if "negative" in signals:
            return "negative", "high" if confidence == "high" else "medium"
        if category == "수주·공급계약" and "positive" in signals:
            return "positive", "high" if confidence == "high" else "medium"
        if category in {
            "자금조달·증권신고서", "자금조달·증권발행", "유상증자 발행가액 확정", "특수관계인·내부거래",
            "정정 공시", "자기주식 처분", "감자", "액면병합", "주식관련사채", "증권 발행결과",
            "채무증권 발행", "전환청구권 행사", "공개매수", "주식매수선택권", "전환가액 조정",
            "단기차입금 증가", "담보제공",
            "최대주주 변경", "대표이사 변경", "합병", "분할", "채무보증", "손익구조 변동",
            "공정공시 중요정보", "조회공시 답변",
        }:
            return "caution", confidence
        return sentiment, confidence

    def _percent_to_float(self, value: str | None) -> float | None:
        if not value:
            return None
        match = re.search(r"\d+(?:\.\d+)?", value)
        return float(match.group(0)) if match else None

    def _metric_labels_for_category(self, category: str) -> list[str]:
        if category == "수주·공급계약":
            return ["계약금액", "계약상대", "계약기간", "최근매출액", "매출액대비"]
        if category == "권리락":
            return ["기준가", "권리락 실시일", "사유", "주권종류", "단축코드"]
        if category == "공급계약 해지":
            return ["해지금액", "계약상대", "해지사유", "매출액대비", "해지일자"]
        if category == "주식관련사채":
            return ["사채의 권면총액", "전환가액", "행사가액", "교환가액", "자금의 사용목적", "전환청구기간", "행사청구기간", "표면이자율", "만기이자율"]
        if category == "증권 발행결과":
            return ["실제발행주식수", "실제발행금액", "납입일", "발행방법", "발행예정주식수", "발행예정금액", "상장예정일"]
        if category == "채무증권 발행":
            return ["발행총액", "자금조달의 목적", "표면이자율", "만기이자율", "사채만기일", "이자율", "발행수익률"]
        if category == "자사주 신탁 해지":
            return ["해지금액", "계약상대", "해지사유", "해지일자"]
        if category == "종속회사 유상증자":
            return ["신주의 수", "발행가액", "증자방식", "자금조달의 목적", "납입일", "상장예정일"]
        if category == "DR 발행":
            return ["DR 발행총액", "신주 발행가액", "납입일", "DR 발행형태", "원주 전환비율", "자금조달의 목적", "상장예정일"]
        if category == "공개매수":
            return ["매수가격", "매수예정수량", "공개매수자", "공개매수기간", "매수목적"]
        if category == "주식매수선택권":
            return ["행사주식수", "행사가격", "부여주식수", "부여대상", "행사기간", "부여일", "상장예정일"]
        if category == "전환가액 조정":
            return ["조정후 전환가액", "조정전 전환가액", "조정사유", "적용일"]
        if category == "불성실공시":
            return ["지정사유", "벌점", "제재금", "지정일"]
        if category == "관리종목 위험":
            return ["지정사유", "해제사유", "시장조치", "심사일정"]
        if category == "감사의견 위험":
            return ["감사의견", "위험사유", "해소여부", "감사인"]
        if category == "단기차입금 증가":
            return ["차입금액", "차입목적", "자기자본대비", "차입후 총차입금", "차입기간"]
        if category == "담보제공":
            return ["담보제공금액", "담보제공대상", "자기자본대비", "담보제공기간", "담보제공사유"]
        if category in {"자금조달·증권신고서", "자금조달·증권발행", "정정 공시"}:
            return [
                "증자방식", "자금조달의 목적", "자금의 사용목적",
                "발행가액", "신주의 수", "납입일", "상장예정일",
                "전환가액", "사채의 권면총액", "전환청구기간",
            ]
        if category == "유상증자 발행가액 확정":
            return ["확정발행가액", "발행가액", "발행주식수", "신주의 수", "확정일", "증자방식", "모집총액", "청약예정일", "납입일", "상장예정일"]
        if category == "배당":
            return ["배당금총액", "1주당 배당금", "시가배당율", "배당기준일", "배당금지급 예정일자"]
        if category == "무상증자":
            return ["보통주 신주", "기타주식 신주", "1주당 배정", "배정기준일", "상장예정일", "전입재원"]
        if category == "주주환원":
            return ["취득예정금액", "처분예정금액", "소각예정금액", "취득예정주식", "취득예상기간"]
        if category == "자사주 소각":
            return ["소각예정금액", "소각예정주식", "소각예정일", "소각목적"]
        if category == "특수관계인·내부거래":
            return ["거래금액", "거래상대방", "거래목적", "거래일자", "이사회 의결일"]
        if category == "자기주식 처분":
            return ["처분예정금액", "처분예정주식", "처분목적", "처분예정기간"]
        if category == "대표이사 변경":
            return ["변경후 대표이사", "변경전 대표이사", "변경사유", "변경일"]
        if category == "신규 시설투자":
            return ["투자금액", "투자목적", "자기자본대비", "투자기간", "투자대상"]
        if category == "영업정지":
            return ["영업정지금액", "영업정지사유", "매출액대비", "영업정지기간", "향후대책"]
        if category == "감자":
            return ["감자비율", "감자주식수", "감자기준일", "감자사유", "감자방법", "상장예정일"]
        if category == "액면분할":
            return ["분할비율", "신주권상장예정일", "매매거래정지기간", "효력발생일"]
        if category == "액면병합":
            return ["병합비율", "신주권상장예정일", "매매거래정지기간", "효력발생일"]
        if category == "거래정지":
            return ["거래정지사유", "거래정지일", "해제일시", "시장구분"]
        if category == "상장폐지 위험":
            return ["위험사유", "상장폐지사유", "개선기간", "심사일정"]
        if category == "중대재해":
            return ["재해내용", "발생일자", "사망자 수", "부상자 수", "조치사항"]
        if category == "횡령·배임":
            return ["발생금액", "자기자본대비", "발생사실", "향후대책"]
        if category == "회생절차":
            return ["신청사유", "신청일자", "관할법원", "결정내용"]
        if category == "최대주주 변경":
            return ["변경후 최대주주", "변경사유", "지분율", "변경일"]
        if category == "최대주주 변경 계약":
            return ["변경예정 최대주주", "계약금액", "예정지분율", "변경예정일", "계약상대방"]
        if category == "합병":
            return ["합병상대회사", "합병비율", "합병기일", "합병목적"]
        if category == "합병 종료":
            return ["합병기일", "합병상대회사", "합병비율", "합병목적"]
        if category == "분할":
            return ["분할신설회사", "분할기일", "분할목적"]
        if category == "소송":
            return ["소송가액", "원고", "피고", "청구내용", "판결ㆍ결정내용"]
        if category == "채무보증":
            return ["채무보증금액", "채무자", "자기자본대비", "채무보증기간", "채무보증 총 잔액", "채무(차입)금액", "채권자", "보증사유"]
        if category == "타법인 주식 취득·처분":
            return ["거래금액", "거래상대방", "거래목적", "취득예정일", "처분예정일", "자기자본대비"]
        if category == "투자판단 주요경영사항":
            return ["주요내용", "계약상대", "계약금액", "추진일정", "투자목적"]
        if category == "전환청구권 행사":
            return ["행사주식수", "발행주식총수 대비", "전환가액", "청구금액", "상장예정일"]
        if category == "영업실적":
            return ["매출액", "영업이익", "당기순이익", "전년동기대비", "직전분기대비"]
        if category == "손익구조 변동":
            return ["매출액", "영업이익", "당기순이익", "변동사유", "전년대비"]
        if category == "기업가치 제고 계획":
            return ["주주환원계획", "목표지표", "이행기간", "공시주기", "주요내용"]
        if category == "공정공시 중요정보":
            return ["주요내용", "계약상대", "계약금액", "전망매출액", "전망영업이익", "추진일정"]
        if category == "조회공시 답변":
            return ["답변내용", "조회공시요구일", "답변일", "진행사항"]
        return []

    def _find_label_value(self, text: str, label: str, labels: list[str]) -> str:
        pattern = re.compile(rf"{re.escape(label)}\s*(?:\([^)]*\))?\s*[:：]?\s*([^\n\r]{{1,120}})")
        match = pattern.search(text)
        if not match:
            return ""
        value = match.group(1).strip()
        next_indexes = []
        for next_label in labels:
            if next_label == label:
                continue
            index = value.find(next_label)
            if index > 0:
                next_indexes.append(index)
        if next_indexes:
            value = value[:min(next_indexes)]
        value = re.split(r"\s{2,}|[|]", value.strip())[0]
        return self._clean_text(value)[:80]

    def _shorten_metric_value(self, label: str, value: str) -> str:
        text = self._clean_text(value)
        if not text:
            return ""

        amount_match = re.search(r"[-+]?\d[\d,]*(?:\.\d+)?\s*(?:원|천원|백만원|억원|조원|달러|유로|USD|EUR)", text)
        plain_amount_match = re.search(r"[-+]?\d[\d,]{3,}(?:\.\d+)?", text)
        percent_match = re.search(r"[-+]?\d+(?:\.\d+)?\s*%", text)
        ratio_match = re.search(r"\d+(?:\.\d+)?\s*[:：]\s*\d+(?:\.\d+)?", text)
        stock_match = re.search(r"\d[\d,]*\s*주", text)
        date_match = re.search(r"\d{4}[.\-/년]\s*\d{1,2}[.\-/월]\s*\d{1,2}\s*일?|\d{8}", text)

        if label in {
            "계약금액", "해지금액", "최근매출액", "발행가액", "확정발행가액", "모집총액",
            "전환가액", "행사가액", "교환가액", "사채의 권면총액", "배당금총액", "1주당 배당금",
            "취득예정금액", "처분예정금액", "소각예정금액", "소송가액", "전입재원",
            "발생금액", "매출액", "영업이익", "당기순이익", "투자금액", "영업정지금액",
            "전망매출액", "전망영업이익", "채무보증금액", "채무보증 총 잔액", "채무(차입)금액",
            "발행예정금액", "실제발행금액", "발행총액", "청구금액", "DR 발행총액", "신주 발행가액", "거래금액", "계약금액",
            "매수가격", "행사가격", "조정전 전환가액", "조정후 전환가액", "제재금", "차입금액", "차입후 총차입금", "담보제공금액",
        }:
            if amount_match:
                return amount_match.group(0)
            if label in {"발행가액", "확정발행가액"} and plain_amount_match:
                return f"{plain_amount_match.group(0)}원"
            if label == "계약금액" and plain_amount_match:
                return f"{plain_amount_match.group(0)}원"
            if plain_amount_match:
                return f"{plain_amount_match.group(0)}원"
            return ""
        if label in {"매출액대비", "시가배당율", "합병비율", "지분율", "감자비율", "자기자본대비", "전년동기대비", "직전분기대비", "전년대비", "분할비율", "병합비율", "표면이자율", "만기이자율", "이자율", "발행수익률", "발행주식총수 대비"}:
            if label in {"합병비율", "분할비율", "병합비율"} and ratio_match:
                return ratio_match.group(0)
            if percent_match:
                return percent_match.group(0)
            number_match = re.search(r"[-+]?\d+(?:\.\d+)?", text)
            return f"{number_match.group(0)}%" if number_match else ""
        if label in {"신주의 수", "발행주식수", "보통주 신주", "기타주식 신주", "취득예정주식", "처분예정주식", "소각예정주식", "감자주식수", "발행예정주식수", "실제발행주식수", "행사주식수", "매수예정수량", "부여주식수"}:
            return stock_match.group(0) if stock_match else ""
        if label in {"납입일", "상장예정일", "계약기간", "전환청구기간", "행사청구기간", "배당기준일", "배당금지급 예정일자", "취득예상기간", "거래일자", "이사회 의결일", "배정기준일", "처분예정기간", "변경일", "변경예정일", "합병기일", "분할기일", "청약예정일", "확정일", "소각예정일", "감자기준일", "거래정지일", "해제일시", "신주권상장예정일", "매매거래정지기간", "효력발생일", "신청일자", "해지일자", "취득예정일", "처분예정일", "투자기간", "영업정지기간", "추진일정", "조회공시요구일", "답변일", "권리락 실시일", "채무보증기간", "사채만기일", "발생일자", "부여일", "적용일", "지정일"}:
            return date_match.group(0) if date_match else ""
        if label in {"자금조달의 목적", "자금의 사용목적"}:
            purposes = [keyword for keyword in ["시설자금", "운영자금", "채무상환자금", "타법인증권취득자금", "기타자금"] if keyword in text]
            return ", ".join(purposes[:3]) if purposes else ""
        if label in {"계약상대", "거래상대방", "변경후 대표이사", "변경전 대표이사", "채무자", "채권자"}:
            return self._clean_counterparty(text)
        if label in {"처분목적", "소각목적", "감자사유", "감자방법", "거래정지사유", "위험사유", "상장폐지사유", "개선기간", "심사일정", "시장구분", "변경사유", "합병목적", "분할목적", "청구내용", "판결ㆍ결정내용", "발생사실", "향후대책", "신청사유", "관할법원", "결정내용", "해지사유", "변동사유", "주주환원계획", "목표지표", "이행기간", "공시주기", "주요내용", "투자목적", "투자대상", "영업정지사유", "답변내용", "진행사항", "보증사유", "발행방법", "DR 발행형태", "재해내용", "조치사항", "거래목적", "매수목적", "조정사유", "지정사유", "해제사유", "시장조치", "해소여부", "감사의견", "차입목적", "담보제공사유"}:
            return self._truncate_metric_value(text, 36)
        if label in {"변경후 최대주주", "합병상대회사", "분할신설회사", "원고", "피고"}:
            return self._clean_counterparty(text)
        if label == "증자방식":
            if "주주배정후실권주일반공모" in re.sub(r"\s+", "", text):
                return "주주배정 후 실권주 일반공모"
            methods = [keyword for keyword in ["주주배정", "제3자배정", "일반공모", "공모", "사모"] if keyword in text]
            return ", ".join(methods[:3]) if methods else ""
        if label == "거래목적":
            return self._truncate_metric_value(text, 32)
        return self._truncate_metric_value(text)

    def _normalize_won_value(self, value: str) -> str:
        text = self._clean_text(value)
        if not text:
            return ""
        match = re.search(r"\d[\d,]*(?:\.\d+)?\s*(?:원|KRW)?", text)
        if not match:
            return ""
        amount = match.group(0).strip()
        return amount if amount.endswith(("원", "KRW")) else f"{amount}원"

    def _normalize_stock_count_value(self, value: str) -> str:
        text = self._clean_text(value)
        if not text:
            return ""
        match = re.search(r"\d[\d,]*", text)
        return f"{match.group(0)}주" if match else ""

    def _looks_like_money(self, value: str) -> bool:
        return bool(re.search(r"\d[\d,]*(?:\.\d+)?\s*(?:원|KRW)$", self._clean_text(value)))

    def _looks_like_stock_count(self, value: str) -> bool:
        text = self._clean_text(value)
        match = re.search(r"(\d[\d,]*)\s*주$", text)
        if not match:
            return False
        return int(match.group(1).replace(",", "")) > 1

    def _looks_like_date(self, value: str) -> bool:
        return bool(re.search(r"\d{4}[.\-/년]\s*\d{1,2}[.\-/월]\s*\d{1,2}\s*일?|\d{8}", self._clean_text(value)))

    def _clean_counterparty(self, value: str) -> str:
        text = self._clean_text(value)
        text = re.split(r"\s*-\s*(?:회사와의 관계|4\.|판매|계약기간|계약금액|최근매출액|자산양수|이사회)", text)[0]
        text = re.split(r"\s+(?:회사와의\s*관계|판매ㆍ공급|계약기간|계약금액|최근매출액|자산양수|이사회)", text)[0]
        text = re.split(r"\s+\d+\.", text)[0]
        return self._truncate_metric_value(text, 28)

    def _truncate_metric_value(self, value: str, limit: int = 24) -> str:
        text = self._clean_text(value)
        return text if len(text) <= limit else text[:limit].rstrip() + "..."

    def _build_key_points(
        self,
        disclosure: dict[str, Any],
        category: str,
        sentiment: str,
        metrics: list[dict[str, str]],
        source: str,
    ) -> list[str]:
        subject = "정보성 공시입니다." if category == "정보성 공시" else f"{category} 관련 공시입니다."
        points = [subject, self._sentiment_message(sentiment)]
        if metrics:
            labels = ", ".join(metric["label"] for metric in metrics[:3])
            points.append(f"핵심 확인 항목은 {labels}입니다.")
        elif source == "TITLE_ONLY":
            points.append("상세 수치를 확인하지 못해 제목 기반으로 예비 분류했습니다.")
        else:
            points.append("원문에서 바로 구조화 가능한 핵심 수치가 제한적입니다.")
        return points

    def _plain_summary(
        self,
        category: str,
        sentiment: str,
        metrics: list[dict[str, str]],
        source: str,
        check_items: list[dict[str, str]] | None = None,
    ) -> str:
        metric_map = {metric.get("label"): metric.get("value") for metric in metrics if metric.get("label") and metric.get("value")}
        check_map = {
            item.get("question"): item.get("answer")
            for item in check_items or []
            if item.get("question") and self._is_summary_value(item.get("answer"))
        }

        if category == "자금조달·증권신고서":
            method = metric_map.get("증자방식")
            purpose = check_map.get("자금 목적") or metric_map.get("자금의 사용목적") or metric_map.get("자금조달의 목적")
            shares = check_map.get("희석 가능성") or metric_map.get("신주의 수")
            due_date = metric_map.get("납입일")
            details = []
            if method:
                details.append(f"증자방식은 {method}")
            if purpose:
                details.append(f"자금 목적은 {purpose}")
            if shares:
                details.append(f"발행 주식 수는 {shares}")
            if due_date:
                details.append(f"납입일은 {due_date}")
            suffix = ", ".join(details)
            if method == "제3자배정":
                base = "제3자배정 방식의 자금조달 공시입니다. 배정 대상, 발행가액, 할인율, 자금 사용 목적을 우선 확인해야 합니다"
            else:
                base = "자금조달 관련 공시입니다. 기존 주주 희석 가능성과 발행 조건을 확인해야 합니다"
            return f"{base}{f' ({suffix}).' if suffix else '.'}"

        if category == "자금조달·증권발행":
            shares = metric_map.get("신주의 수")
            due_date = metric_map.get("납입일")
            details = []
            if shares:
                details.append(f"발행 주식 수는 {shares}")
            if due_date:
                details.append(f"납입일은 {due_date}")
            suffix = ", ".join(details)
            return f"증권 발행 관련 공시로, 발행 조건과 기존 주주 희석 가능성을 확인해야 합니다{f' ({suffix}).' if suffix else '.'}"

        if category == "유상증자 발행가액 확정":
            method = metric_map.get("증자방식")
            issue_price = metric_map.get("확정발행가액") or metric_map.get("발행가액")
            shares = metric_map.get("발행주식수") or metric_map.get("신주의 수")
            fixed_date = metric_map.get("확정일")
            total_amount = metric_map.get("모집총액")
            details = []
            if issue_price:
                details.append(f"최종 발행가는 {issue_price}")
            if shares:
                details.append(f"발행 주식 수는 {shares}")
            if fixed_date:
                details.append(f"확정일은 {fixed_date}")
            if method:
                details.append(f"방식은 {method}")
            if total_amount:
                details.append(f"모집총액은 {total_amount}")
            suffix = ", ".join(details)
            return f"유상증자의 최종 발행가액을 확정한 공시입니다. 새 증자 결정이라기보다 진행 중인 증자의 가격 조건이 확정된 단계라, 할인율과 청약 일정, 실권주 발생 가능성을 함께 확인해야 합니다{f' ({suffix}).' if suffix else '.'}"

        if category == "정정 공시":
            return "기존 공시 내용을 고친 정정 공시입니다. 무엇이 바뀌었는지 원문에서 정정 전후 내용을 확인해야 합니다."

        if category == "수주·공급계약":
            amount = metric_map.get("계약금액")
            ratio = metric_map.get("매출액대비")
            counterparty = metric_map.get("계약상대")
            details = []
            if amount:
                details.append(f"계약금액은 {amount}")
            if ratio:
                details.append(f"매출 대비 {ratio}")
            if counterparty:
                details.append(f"계약상대는 {counterparty}")
            suffix = ", ".join(details)
            return f"공급계약 또는 수주 관련 공시입니다{f' ({suffix}).' if suffix else '. 계약 규모와 실제 매출 반영 시점을 확인해야 합니다.'}"

        if category == "공급계약 해지":
            amount = metric_map.get("해지금액") or metric_map.get("매출액대비")
            reason = metric_map.get("해지사유")
            details = []
            if amount:
                details.append(f"해지 규모는 {amount}")
            if reason:
                details.append(f"해지 사유는 {reason}")
            suffix = ", ".join(details)
            return f"기존 공급계약이 해지된 공시입니다. 기대했던 매출이 줄거나 지연될 수 있어 해지 규모와 귀책 사유를 먼저 확인해야 합니다{f' ({suffix}).' if suffix else '.'}"

        if category == "증권 발행결과":
            amount = metric_map.get("실제발행금액") or metric_map.get("실제발행주식수")
            paid_date = metric_map.get("납입일")
            details = []
            if amount:
                details.append(f"실제 발행 규모는 {amount}")
            if paid_date:
                details.append(f"납입일은 {paid_date}")
            suffix = ", ".join(details)
            return f"증권 발행결과 공시입니다. 계획했던 발행이 실제로 얼마나 납입·발행됐는지 확인하는 단계라 희석 규모와 상장 일정을 봐야 합니다{f' ({suffix}).' if suffix else '.'}"

        if category == "채무증권 발행":
            amount = metric_map.get("발행총액")
            purpose = metric_map.get("자금조달의 목적")
            rate = metric_map.get("표면이자율") or metric_map.get("이자율")
            details = []
            if amount:
                details.append(f"발행총액은 {amount}")
            if purpose:
                details.append(f"자금 목적은 {purpose}")
            if rate:
                details.append(f"이자율은 {rate}")
            suffix = ", ".join(details)
            return f"채무증권 발행 관련 공시입니다. 차입성 자금조달이므로 발행 규모, 이자율, 자금 사용 목적을 확인해야 합니다{f' ({suffix}).' if suffix else '.'}"

        if category == "종속회사 유상증자":
            shares = metric_map.get("신주의 수")
            price = metric_map.get("발행가액")
            method = metric_map.get("증자방식")
            details = []
            if shares:
                details.append(f"신주 수는 {shares}")
            if price:
                details.append(f"발행가액은 {price}")
            if method:
                details.append(f"방식은 {method}")
            suffix = ", ".join(details)
            return f"종속회사 유상증자 공시입니다. 모회사 직접 증자는 아니지만 지분가치와 자금 투입 부담에 영향을 줄 수 있어 발행 규모와 자금 목적을 확인해야 합니다{f' ({suffix}).' if suffix else '.'}"

        if category == "DR 발행":
            amount = metric_map.get("DR 발행총액")
            price = metric_map.get("신주 발행가액")
            listing = metric_map.get("상장예정일")
            details = []
            if amount:
                details.append(f"DR 발행총액은 {amount}")
            if price:
                details.append(f"신주 발행가액은 {price}")
            if listing:
                details.append(f"상장예정일은 {listing}")
            suffix = ", ".join(details)
            return f"해외 증권예탁증권(DR) 발행 공시입니다. 해외 상장과 대규모 자금조달 성격이 있어 발행 규모, 가격, 상장 일정을 함께 확인해야 합니다{f' ({suffix}).' if suffix else '.'}"

        if category == "공개매수":
            price = metric_map.get("매수가격")
            quantity = metric_map.get("매수예정수량")
            buyer = metric_map.get("공개매수자")
            details = []
            if buyer:
                details.append(f"공개매수자는 {buyer}")
            if price:
                details.append(f"매수가격은 {price}")
            if quantity:
                details.append(f"매수예정수량은 {quantity}")
            suffix = ", ".join(details)
            return f"공개매수 공시입니다. 경영권, 상장폐지, 지분 확대 목적에 따라 해석이 크게 달라지므로 공개매수자와 매수가격, 예정 수량을 우선 봐야 합니다{f' ({suffix}).' if suffix else '.'}"

        if category == "주식매수선택권":
            exercised = metric_map.get("행사주식수")
            shares = metric_map.get("부여주식수")
            price = metric_map.get("행사가격")
            period = metric_map.get("행사기간")
            details = []
            if exercised:
                details.append(f"행사 주식 수는 {exercised}")
            if shares:
                details.append(f"부여 주식 수는 {shares}")
            if price:
                details.append(f"행사가격은 {price}")
            if period:
                details.append(f"행사기간은 {period}")
            suffix = ", ".join(details)
            return f"주식매수선택권 공시입니다. 임직원 보상 성격이지만 행사 물량과 행사가격에 따라 향후 희석 가능성을 확인해야 합니다{f' ({suffix}).' if suffix else '.'}"

        if category == "전환가액 조정":
            before = metric_map.get("조정전 전환가액")
            after = metric_map.get("조정후 전환가액")
            reason = metric_map.get("조정사유")
            details = []
            if before:
                details.append(f"조정전은 {before}")
            if after:
                details.append(f"조정후는 {after}")
            if reason:
                details.append(f"사유는 {reason}")
            suffix = ", ".join(details)
            return f"전환가액 조정 공시입니다. 전환가가 낮아지면 같은 사채 금액으로 더 많은 주식이 나올 수 있어 희석 부담을 확인해야 합니다{f' ({suffix}).' if suffix else '.'}"

        if category == "불성실공시":
            reason = metric_map.get("지정사유")
            penalty = metric_map.get("벌점")
            fine = metric_map.get("제재금")
            details = []
            if reason:
                details.append(f"지정사유는 {reason}")
            if penalty:
                details.append(f"벌점은 {penalty}")
            if fine:
                details.append(f"제재금은 {fine}")
            suffix = ", ".join(details)
            return f"불성실공시 관련 공시입니다. 반복되면 투자주의 환기, 관리종목 등 시장 신뢰도 리스크로 이어질 수 있어 사유와 벌점을 확인해야 합니다{f' ({suffix}).' if suffix else '.'}"

        if category == "관리종목 위험":
            reason = metric_map.get("지정사유") or metric_map.get("위험사유")
            action = metric_map.get("시장조치")
            details = []
            if reason:
                details.append(f"사유는 {reason}")
            if action:
                details.append(f"시장조치는 {action}")
            suffix = ", ".join(details)
            return f"관리종목·투자주의 환기 관련 공시입니다. 거래정지나 상장폐지 심사로 번질 수 있는지 사유와 후속 일정을 봐야 합니다{f' ({suffix}).' if suffix else '.'}"

        if category == "감사의견 위험":
            opinion = metric_map.get("감사의견")
            reason = metric_map.get("위험사유")
            details = []
            if opinion:
                details.append(f"감사의견은 {opinion}")
            if reason:
                details.append(f"사유는 {reason}")
            suffix = ", ".join(details)
            return f"감사의견 관련 위험 공시입니다. 의견거절·한정·계속기업 불확실성은 거래정지나 상장폐지 심사와 연결될 수 있어 가장 먼저 확인해야 합니다{f' ({suffix}).' if suffix else '.'}"

        if category == "단기차입금 증가":
            amount = metric_map.get("차입금액")
            purpose = metric_map.get("차입목적")
            ratio = metric_map.get("자기자본대비")
            details = []
            if amount:
                details.append(f"차입금액은 {amount}")
            if ratio:
                details.append(f"자기자본 대비 {ratio}")
            if purpose:
                details.append(f"목적은 {purpose}")
            suffix = ", ".join(details)
            return f"단기차입금 증가 공시입니다. 운영자금 부족인지 일시적 자금 조달인지에 따라 해석이 달라져 차입 규모와 목적을 확인해야 합니다{f' ({suffix}).' if suffix else '.'}"

        if category == "담보제공":
            amount = metric_map.get("담보제공금액")
            target = metric_map.get("담보제공대상")
            ratio = metric_map.get("자기자본대비")
            details = []
            if amount:
                details.append(f"담보제공금액은 {amount}")
            if ratio:
                details.append(f"자기자본 대비 {ratio}")
            if target:
                details.append(f"대상은 {target}")
            suffix = ", ".join(details)
            return f"타인에 대한 담보제공 공시입니다. 계열사나 타인을 위해 회사 자산을 담보로 잡히는 구조라 대상과 금액, 자기자본 대비 비중을 확인해야 합니다{f' ({suffix}).' if suffix else '.'}"

        if category == "주식관련사채":
            amount = metric_map.get("사채의 권면총액")
            price = metric_map.get("전환가액") or metric_map.get("행사가액") or metric_map.get("교환가액")
            period = metric_map.get("전환청구기간") or metric_map.get("행사청구기간")
            details = []
            if amount:
                details.append(f"사채 규모는 {amount}")
            if price:
                details.append(f"전환·행사 조건은 {price}")
            if period:
                details.append(f"청구 기간은 {period}")
            suffix = ", ".join(details)
            return f"전환사채·신주인수권부사채 등 주식으로 바뀔 수 있는 자금조달 공시입니다. 향후 전환 물량이 기존 주주 희석이나 오버행 부담이 될 수 있습니다{f' ({suffix}).' if suffix else '.'}"

        if category == "주주환원":
            return "자사주 취득·소각 등 주주환원 성격의 공시입니다. 규모와 실행 기간을 확인해야 합니다."

        if category == "자사주 소각":
            amount = metric_map.get("소각예정금액") or metric_map.get("소각예정주식")
            date = metric_map.get("소각예정일")
            details = []
            if amount:
                details.append(f"소각 규모는 {amount}")
            if date:
                details.append(f"소각예정일은 {date}")
            suffix = ", ".join(details)
            return f"자사주 소각 결정 공시입니다. 유통 주식 수 감소와 주주환원 성격이 있어 긍정적으로 해석될 수 있으나 실제 소각 규모와 일정을 확인해야 합니다{f' ({suffix}).' if suffix else '.'}"

        if category == "배당":
            dividend = metric_map.get("1주당 배당금") or metric_map.get("배당금총액")
            return f"배당 관련 공시입니다{f' ({dividend}).' if dividend else '. 배당 규모와 기준일을 확인해야 합니다.'}"

        if category == "무상증자":
            shares = metric_map.get("보통주 신주") or metric_map.get("신주의 수")
            ratio = metric_map.get("1주당 배정")
            base_date = metric_map.get("배정기준일")
            listing_date = metric_map.get("상장예정일")
            details = []
            if shares:
                details.append(f"보통주 신주 수는 {shares}")
            if ratio:
                details.append(f"1주당 배정은 {ratio}")
            if base_date:
                details.append(f"배정기준일은 {base_date}")
            if listing_date:
                details.append(f"상장예정일은 {listing_date}")
            suffix = ", ".join(details)
            return f"무상증자 결정 공시입니다. 시장에서는 긍정 재료로 해석되는 경우가 많지만, 기업가치가 바로 늘어나는 이벤트는 아니므로 권리락과 신주 상장 일정을 함께 봐야 합니다{f' ({suffix}).' if suffix else '.'}"

        if category == "권리락":
            base_price = metric_map.get("기준가")
            event_date = metric_map.get("권리락 실시일")
            reason = metric_map.get("사유")
            details = []
            if base_price:
                details.append(f"권리락 기준가는 {base_price}")
            if event_date:
                details.append(f"실시일은 {event_date}")
            if reason:
                details.append(f"사유는 {reason}")
            suffix = ", ".join(details)
            return f"권리락 발생 안내 공시입니다. 새 호재 공시라기보다 무상증자 등으로 기준가가 조정되는 이벤트라, 권리락 이후 가격은 조정 기준가와 비교해야 합니다{f' ({suffix}).' if suffix else '.'}"

        if category == "시장 신뢰도 위험":
            return "거래정지, 상장폐지, 감사의견 등 시장 신뢰도에 부담이 될 수 있는 공시입니다."

        if category == "중대재해":
            content = metric_map.get("재해내용")
            date = metric_map.get("발생일자")
            details = []
            if date:
                details.append(f"발생일자는 {date}")
            if content:
                details.append(f"내용은 {content}")
            suffix = ", ".join(details)
            return f"중대재해 발생 공시입니다. 상장폐지 이슈와는 별도로 안전사고와 조사·제재 가능성을 확인해야 하는 악재성 공시입니다{f' ({suffix}).' if suffix else '.'}"

        if category == "감자":
            ratio = metric_map.get("감자비율")
            shares = metric_map.get("감자주식수")
            reason = metric_map.get("감자사유")
            details = []
            if ratio:
                details.append(f"감자비율은 {ratio}")
            if shares:
                details.append(f"감자 주식 수는 {shares}")
            if reason:
                details.append(f"감자 사유는 {reason}")
            suffix = ", ".join(details)
            return f"감자 결정 공시입니다. 주식 수와 자본금이 줄어드는 이벤트라 감자 사유, 비율, 거래정지·변경상장 일정을 확인해야 합니다{f' ({suffix}).' if suffix else '.'}"

        if category == "액면분할":
            ratio = metric_map.get("분할비율")
            listing_date = metric_map.get("신주권상장예정일")
            details = []
            if ratio:
                details.append(f"분할비율은 {ratio}")
            if listing_date:
                details.append(f"신주권 상장일은 {listing_date}")
            suffix = ", ".join(details)
            return f"액면분할 공시입니다. 기업가치 자체가 늘어나는 이벤트는 아니지만 1주 가격 단위가 낮아져 거래 접근성이 좋아질 수 있습니다{f' ({suffix}).' if suffix else '.'}"

        if category == "액면병합":
            ratio = metric_map.get("병합비율")
            listing_date = metric_map.get("신주권상장예정일")
            details = []
            if ratio:
                details.append(f"병합비율은 {ratio}")
            if listing_date:
                details.append(f"신주권 상장일은 {listing_date}")
            suffix = ", ".join(details)
            return f"액면병합 공시입니다. 주식 수가 줄고 1주 가격 단위가 커지는 구조라 거래정지 일정과 병합 목적을 확인해야 합니다{f' ({suffix}).' if suffix else '.'}"

        if category == "거래정지":
            reason = metric_map.get("거래정지사유")
            date = metric_map.get("거래정지일")
            details = []
            if reason:
                details.append(f"정지 사유는 {reason}")
            if date:
                details.append(f"거래정지일은 {date}")
            suffix = ", ".join(details)
            return f"거래정지 관련 공시입니다. 매매가 제한되는 악재성 이벤트이므로 정지 사유와 해제 조건을 우선 확인해야 합니다{f' ({suffix}).' if suffix else '.'}"

        if category == "상장폐지 위험":
            reason = metric_map.get("위험사유") or metric_map.get("상장폐지사유")
            schedule = metric_map.get("심사일정") or metric_map.get("개선기간")
            details = []
            if reason:
                details.append(f"위험 사유는 {reason}")
            if schedule:
                details.append(f"일정은 {schedule}")
            suffix = ", ".join(details)
            return f"상장폐지 또는 시장 신뢰도 훼손 위험이 큰 공시입니다. 거래 지속 가능성, 개선기간, 거래소 심사 일정을 최우선으로 확인해야 합니다{f' ({suffix}).' if suffix else '.'}"

        if category == "횡령·배임":
            amount = metric_map.get("발생금액") or metric_map.get("자기자본대비")
            action = metric_map.get("향후대책")
            details = []
            if amount:
                details.append(f"발생 규모는 {amount}")
            if action:
                details.append(f"회사 대응은 {action}")
            suffix = ", ".join(details)
            return f"횡령·배임 관련 공시입니다. 회사 신뢰도와 상장 적격성에 직접 부담이 될 수 있어 발생 규모와 회사 대응을 최우선으로 봐야 합니다{f' ({suffix}).' if suffix else '.'}"

        if category == "회생절차":
            reason = metric_map.get("신청사유")
            date = metric_map.get("신청일자")
            details = []
            if reason:
                details.append(f"신청 사유는 {reason}")
            if date:
                details.append(f"신청일은 {date}")
            suffix = ", ".join(details)
            return f"회생절차 관련 공시입니다. 채무 조정과 계속기업 가능성 이슈가 있어 법원 결정, 거래정지 여부, 후속 일정을 확인해야 합니다{f' ({suffix}).' if suffix else '.'}"

        if category == "자기주식 처분":
            purpose = metric_map.get("처분목적")
            amount = metric_map.get("처분예정금액") or metric_map.get("처분예정주식")
            details = []
            if purpose:
                details.append(f"처분 목적은 {purpose}")
            if amount:
                details.append(f"처분 규모는 {amount}")
            suffix = ", ".join(details)
            return f"자기주식 처분 공시입니다. 자사주 취득·소각과 달리 단기 수급 부담이 될 수 있어 처분 목적과 규모를 확인해야 합니다{f' ({suffix}).' if suffix else '.'}"

        if category == "대표이사 변경":
            new_ceo = metric_map.get("변경후 대표이사")
            reason = metric_map.get("변경사유")
            details = []
            if new_ceo:
                details.append(f"변경 후 대표는 {new_ceo}")
            if reason:
                details.append(f"변경 사유는 {reason}")
            suffix = ", ".join(details)
            return f"대표이사 변경 공시입니다. 경영 방향과 책임 주체가 바뀔 수 있어 변경 사유와 새 대표의 이력을 확인해야 합니다{f' ({suffix}).' if suffix else '.'}"

        if category == "신규 시설투자":
            amount = metric_map.get("투자금액") or metric_map.get("자기자본대비")
            purpose = metric_map.get("투자목적") or metric_map.get("투자대상")
            details = []
            if amount:
                details.append(f"투자 규모는 {amount}")
            if purpose:
                details.append(f"투자 목적은 {purpose}")
            suffix = ", ".join(details)
            return f"신규 시설투자 공시입니다. 성장 재료가 될 수 있지만 투자 규모, 자금 부담, 실제 매출 반영 시점을 함께 확인해야 합니다{f' ({suffix}).' if suffix else '.'}"

        if category == "영업정지":
            amount = metric_map.get("영업정지금액") or metric_map.get("매출액대비")
            reason = metric_map.get("영업정지사유")
            details = []
            if amount:
                details.append(f"정지 규모는 {amount}")
            if reason:
                details.append(f"정지 사유는 {reason}")
            suffix = ", ".join(details)
            return f"영업정지 공시입니다. 매출과 이익에 직접 충격이 생길 수 있어 정지 규모, 사유, 재개 가능 시점을 우선 확인해야 합니다{f' ({suffix}).' if suffix else '.'}"

        if category == "최대주주 변경":
            holder = metric_map.get("변경후 최대주주")
            reason = metric_map.get("변경사유")
            details = []
            if holder:
                details.append(f"새 최대주주는 {holder}")
            if reason:
                details.append(f"변경 사유는 {reason}")
            suffix = ", ".join(details)
            return f"최대주주 변경 공시입니다. 경영권과 지배구조가 바뀔 수 있어 새 최대주주의 신뢰도, 지분율, 변경 사유를 확인해야 합니다{f' ({suffix}).' if suffix else '.'}"

        if category == "최대주주 변경 계약":
            holder = metric_map.get("변경예정 최대주주")
            amount = metric_map.get("계약금액")
            details = []
            if holder:
                details.append(f"변경 예정 최대주주는 {holder}")
            if amount:
                details.append(f"계약금액은 {amount}")
            suffix = ", ".join(details)
            return f"최대주주 변경을 수반하는 주식양수도 계약 공시입니다. 실제 변경 완료 전까지 납입 여부와 계약 조건 변동 가능성을 확인해야 합니다{f' ({suffix}).' if suffix else '.'}"

        if category == "합병":
            target = metric_map.get("합병상대회사")
            ratio = metric_map.get("합병비율")
            details = []
            if target:
                details.append(f"합병 상대는 {target}")
            if ratio:
                details.append(f"합병비율은 {ratio}")
            suffix = ", ".join(details)
            return f"합병 관련 공시입니다. 사업 시너지 기대와 기존 주주 이해관계 변화가 함께 있어 합병 상대, 합병비율, 일정 확인이 필요합니다{f' ({suffix}).' if suffix else '.'}"

        if category == "합병 종료":
            date = metric_map.get("합병기일")
            ratio = metric_map.get("합병비율")
            details = []
            if date:
                details.append(f"합병기일은 {date}")
            if ratio:
                details.append(f"합병비율은 {ratio}")
            suffix = ", ".join(details)
            return f"합병 절차 종료 보고입니다. 새 합병 결정이라기보다 이미 진행된 합병 절차가 완료됐는지 확인하는 공시입니다{f' ({suffix}).' if suffix else '.'}"

        if category == "분할":
            purpose = metric_map.get("분할목적")
            date = metric_map.get("분할기일")
            details = []
            if purpose:
                details.append(f"분할 목적은 {purpose}")
            if date:
                details.append(f"분할기일은 {date}")
            suffix = ", ".join(details)
            return f"분할 관련 공시입니다. 사업 전문화 기대와 지배구조 변화 가능성이 함께 있어 인적분할인지 물적분할인지, 기존 주주 배정 구조를 확인해야 합니다{f' ({suffix}).' if suffix else '.'}"

        if category == "소송":
            amount = metric_map.get("소송가액")
            claim = metric_map.get("청구내용") or metric_map.get("판결ㆍ결정내용")
            details = []
            if amount:
                details.append(f"소송가액은 {amount}")
            if claim:
                details.append(f"핵심 내용은 {claim}")
            suffix = ", ".join(details)
            return f"소송 관련 공시입니다. 재무 부담, 평판 리스크, 영업 차질 가능성을 확인해야 하는 악재성 이벤트입니다{f' ({suffix}).' if suffix else '.'}"

        if category == "자사주 신탁 해지":
            amount = metric_map.get("해지금액")
            reason = metric_map.get("해지사유")
            details = []
            if amount:
                details.append(f"해지금액은 {amount}")
            if reason:
                details.append(f"해지 사유는 {reason}")
            suffix = ", ".join(details)
            return f"자기주식 취득 신탁계약 해지 공시입니다. 신규 매입보다 기존 신탁의 종료 성격이 강하므로 해지금액과 실제 취득 결과를 확인해야 합니다{f' ({suffix}).' if suffix else '.'}"

        if category == "타법인 주식 취득·처분":
            amount = metric_map.get("거래금액")
            target = metric_map.get("거래상대방")
            details = []
            if amount:
                details.append(f"거래금액은 {amount}")
            if target:
                details.append(f"대상은 {target}")
            suffix = ", ".join(details)
            return f"타법인 주식 또는 출자증권 취득·처분 공시입니다. 투자 목적, 거래금액, 자기자본 대비 부담을 확인해야 합니다{f' ({suffix}).' if suffix else '.'}"

        if category == "투자판단 주요경영사항":
            content = metric_map.get("주요내용")
            amount = metric_map.get("계약금액")
            details = []
            if content:
                details.append(f"주요내용은 {content}")
            if amount:
                details.append(f"금액은 {amount}")
            suffix = ", ".join(details)
            return f"투자판단 관련 주요경영사항 공시입니다. 계약, 수주, 임상, 인허가 등 회사별 핵심 이벤트가 담길 수 있어 주요내용과 후속 일정을 확인해야 합니다{f' ({suffix}).' if suffix else '.'}"

        if category == "채무보증":
            amount = metric_map.get("채무보증금액") or metric_map.get("자기자본대비")
            debtor = metric_map.get("채무자")
            period = metric_map.get("채무보증기간")
            details = []
            if amount:
                details.append(f"보증 규모는 {amount}")
            if debtor:
                details.append(f"채무자는 {debtor}")
            if period:
                details.append(f"보증 기간은 {period}")
            suffix = ", ".join(details)
            return f"타인에 대한 채무보증 결정 공시입니다. 당장 현금 유출은 아니지만 채무자가 갚지 못하면 회사의 우발채무가 될 수 있어 보증금액과 자기자본 대비 비중을 확인해야 합니다{f' ({suffix}).' if suffix else '.'}"

        if category == "전환청구권 행사":
            shares = metric_map.get("행사주식수") or metric_map.get("발행주식총수 대비")
            price = metric_map.get("전환가액")
            details = []
            if shares:
                details.append(f"행사 물량은 {shares}")
            if price:
                details.append(f"전환가액은 {price}")
            suffix = ", ".join(details)
            return f"전환청구권 행사 공시입니다. 전환사채가 주식으로 바뀌며 유통 주식 수가 늘 수 있어 행사 물량과 전환가액을 확인해야 합니다{f' ({suffix}).' if suffix else '.'}"

        if category == "영업실적":
            sales = metric_map.get("매출액")
            profit = metric_map.get("영업이익")
            net_income = metric_map.get("당기순이익")
            details = []
            if sales:
                details.append(f"매출액은 {sales}")
            if profit:
                details.append(f"영업이익은 {profit}")
            if net_income:
                details.append(f"당기순이익은 {net_income}")
            suffix = ", ".join(details)
            return f"잠정 영업실적 공시입니다. 매출과 이익이 같이 좋아졌는지, 일회성 요인이 아닌지 확인해야 합니다{f' ({suffix}).' if suffix else '.'}"

        if category == "손익구조 변동":
            profit = metric_map.get("영업이익")
            net_income = metric_map.get("당기순이익")
            reason = metric_map.get("변동사유")
            details = []
            if profit:
                details.append(f"영업이익은 {profit}")
            if net_income:
                details.append(f"당기순이익은 {net_income}")
            if reason:
                details.append(f"변동 사유는 {reason}")
            suffix = ", ".join(details)
            return f"매출액 또는 손익구조가 크게 바뀐 공시입니다. 이익 개선인지 악화인지, 본업 때문인지 일회성 요인인지 확인해야 합니다{f' ({suffix}).' if suffix else '.'}"

        if category == "기업가치 제고 계획":
            target = metric_map.get("목표지표")
            plan = metric_map.get("주주환원계획")
            details = []
            if target:
                details.append(f"목표지표는 {target}")
            if plan:
                details.append(f"주주환원 계획은 {plan}")
            suffix = ", ".join(details)
            return f"기업가치 제고 계획 공시입니다. 긍정 재료가 될 수 있지만 목표 지표, 주주환원 규모, 실행 일정이 구체적인지 확인해야 합니다{f' ({suffix}).' if suffix else '.'}"

        if category == "공정공시 중요정보":
            content = metric_map.get("주요내용")
            amount = metric_map.get("계약금액") or metric_map.get("전망매출액") or metric_map.get("전망영업이익")
            details = []
            if content:
                details.append(f"핵심 내용은 {content}")
            if amount:
                details.append(f"관련 수치는 {amount}")
            suffix = ", ".join(details)
            return f"공정공시로 공개된 중요 정보입니다. 전망, 신제품, 기술이전, 신규사업은 실제 계약 여부와 실적 반영 가능성을 확인해야 합니다{f' ({suffix}).' if suffix else '.'}"

        if category == "조회공시 답변":
            answer = metric_map.get("답변내용") or metric_map.get("진행사항")
            details = []
            if answer:
                details.append(f"답변 내용은 {answer}")
            suffix = ", ".join(details)
            return f"거래소 조회 요구에 대한 답변 공시입니다. 풍문·보도·급등락 사유가 사실인지, 미확정인지, 부인인지 확인해야 합니다{f' ({suffix}).' if suffix else '.'}"

        if category == "특수관계인·내부거래":
            return "특수관계인 또는 계열회사와의 거래 공시입니다. 거래 금액, 목적, 조건이 회사에 유리한지 확인해야 합니다."

        if category == "사업계획·전망":
            return "회사의 향후 사업계획이나 경영 방향을 알리는 공시입니다. 실제 실적 반영 여부는 후속 자료로 확인해야 합니다."

        if category == "ESG·자율공시":
            return "지속가능경영이나 자율공시 성격의 자료입니다. 주가 방향보다 회사의 비재무 정보 확인에 가깝습니다."

        if source == "TITLE_ONLY":
            return "상세 내용을 아직 확인하지 못해 제목 기준으로만 분류한 공시입니다."

        return "주가 방향성과 직접 연결하기 어려운 정보성 공시입니다."

    def _is_summary_value(self, value: Any) -> bool:
        text = self._clean_text(value)
        return bool(text and text not in {"확인 필요", "원문 확인 필요", "후속 확인 필요", "원공시 비교 필요", "제목 기반"})

    def _build_risk_points(self, category: str, sentiment: str, metrics: list[dict[str, str]], source: str) -> list[str]:
        if category == "사업계획·전망":
            return ["계획 발표와 실제 실적 반영은 다를 수 있으므로 후속 실적과 투자 집행 여부를 확인해야 합니다."]
        if category == "ESG·자율공시":
            return ["비재무 정보 성격이 강하므로 단기 주가 재료로 보기는 어렵습니다."]
        if category == "무상증자":
            return ["무상증자는 호재로 해석될 수 있지만 권리락, 신주 상장일, 단기 변동성을 함께 확인해야 합니다."]
        if category == "권리락":
            return ["권리락 이후 가격은 전일 종가가 아니라 조정 기준가와 비교해야 착시를 줄일 수 있습니다."]
        if category == "유상증자 발행가액 확정":
            return ["최종 발행가, 할인율, 구주주 청약 일정과 실권주 일반공모 여부를 함께 확인해야 합니다."]
        if category == "주식관련사채":
            return ["전환·행사 가격, 전환청구 가능 시점, 주식 전환 물량에 따른 오버행 부담을 확인해야 합니다."]
        if category == "공급계약 해지":
            return ["해지 금액, 매출 대비 비중, 해지 귀책 사유와 대체 계약 가능성을 확인해야 합니다."]
        if category == "증권 발행결과":
            return ["실제 발행금액, 발행주식 수, 납입 완료 여부와 신주 상장 일정을 확인해야 합니다."]
        if category == "채무증권 발행":
            return ["발행총액, 이자율, 만기와 자금 사용 목적에 따른 재무 부담을 확인해야 합니다."]
        if category == "자사주 신탁 해지":
            return ["신탁 해지는 신규 매입 공시와 다르므로 해지금액, 실제 취득 결과, 잔여 매입 여력을 확인해야 합니다."]
        if category == "종속회사 유상증자":
            return ["종속회사 신주 발행 규모, 모회사 지분율 변화, 자금 투입 부담과 상장 일정 전후 수급을 확인해야 합니다."]
        if category == "DR 발행":
            return ["DR 발행 규모, 신주 발행가액, 원주 전환비율과 해외 상장 일정을 확인해야 합니다."]
        if category == "공개매수":
            return ["공개매수자, 매수가격의 현재가 대비 프리미엄, 매수 목적과 상장폐지 가능성을 함께 확인해야 합니다."]
        if category == "주식매수선택권":
            return ["부여·행사 물량, 행사가격, 행사 가능 기간과 발행주식 수 대비 희석 가능성을 확인해야 합니다."]
        if category == "전환가액 조정":
            return ["조정 후 전환가액, 조정 사유, 추가 전환 가능 물량에 따른 오버행 부담을 확인해야 합니다."]
        if category == "불성실공시":
            return ["지정 사유, 벌점, 제재금과 반복 발생 여부를 확인해야 합니다."]
        if category == "관리종목 위험":
            return ["관리종목·투자주의 환기 사유, 해소 조건, 거래정지와 상장폐지 심사 연결 가능성을 확인해야 합니다."]
        if category == "감사의견 위험":
            return ["감사의견 종류, 계속기업 불확실성, 의견거절·한정 사유와 해소 가능성을 최우선으로 확인해야 합니다."]
        if category == "단기차입금 증가":
            return ["차입금액, 자기자본 대비 비중, 차입 목적과 만기 구조에 따른 유동성 부담을 확인해야 합니다."]
        if category == "담보제공":
            return ["담보제공금액, 담보 대상, 자기자본 대비 비중과 담보 실행 시 재무 부담을 확인해야 합니다."]
        if category == "자기주식 처분":
            return ["처분 목적, 처분 규모, 시장 매도 여부에 따라 단기 수급 부담이 달라질 수 있습니다."]
        if category == "대표이사 변경":
            return ["변경 사유, 새 대표의 이력, 경영 전략 변화 가능성을 확인해야 합니다."]
        if category == "신규 시설투자":
            return ["투자금액, 자기자본 대비 부담, 투자 완료 후 매출 반영 시점을 확인해야 합니다."]
        if category == "영업정지":
            return ["영업정지 규모, 정지 기간, 재개 조건과 실적 충격 가능성을 확인해야 합니다."]
        if category == "자사주 소각":
            return ["실제 소각 규모, 소각 예정일, 발행주식 수 대비 비중을 함께 확인해야 합니다."]
        if category == "감자":
            return ["감자 사유, 감자비율, 거래정지와 변경상장 일정을 함께 확인해야 합니다."]
        if category == "액면분할":
            return ["액면분할은 기업가치 변화가 아니므로 권리락·거래정지·신주권 상장 일정을 확인해야 합니다."]
        if category == "액면병합":
            return ["액면병합 목적, 거래정지 기간, 병합 후 유동성 변화를 확인해야 합니다."]
        if category == "거래정지":
            return ["거래정지 사유, 해제 조건, 거래 재개 가능 시점을 우선 확인해야 합니다."]
        if category == "상장폐지 위험":
            return ["상장폐지 사유, 개선기간 부여 여부, 거래소 심사 일정을 최우선으로 확인해야 합니다."]
        if category == "중대재해":
            return ["사망·부상 규모, 고용노동부 조사, 행정처분 또는 평판 리스크 가능성을 확인해야 합니다."]
        if category == "횡령·배임":
            return ["발생 금액, 자기자본 대비 비중, 상장 적격성 심사 가능성과 회사의 회수·고소 조치를 확인해야 합니다."]
        if category == "회생절차":
            return ["회생절차 개시 여부, 법원 일정, 거래정지와 채무 조정 가능성을 확인해야 합니다."]
        if category == "최대주주 변경":
            return ["새 최대주주의 재무 여력, 지분율, 경영권 안정성을 확인해야 합니다."]
        if category == "최대주주 변경 계약":
            return ["계약금 납입 여부, 잔금 일정, 계약 해제 가능성과 실제 최대주주 변경 완료 여부를 확인해야 합니다."]
        if category == "합병":
            return ["합병비율, 주식매수청구권, 합병 상대의 재무상태와 시너지 실현 가능성을 확인해야 합니다."]
        if category == "합병 종료":
            return ["합병 절차가 실제 완료됐는지, 신주 상장과 주주 권리 변동 일정이 남아 있는지 확인해야 합니다."]
        if category == "분할":
            return ["인적분할과 물적분할의 주주 영향이 다르므로 분할 구조와 신설회사 배정 방식을 확인해야 합니다."]
        if category == "소송":
            return ["소송가액, 패소 가능성, 충당부채 반영 여부와 영업 차질 가능성을 확인해야 합니다."]
        if category == "채무보증":
            return ["채무보증금액, 자기자본 대비 비중, 채무자와 회사의 관계, 기존 보증 잔액을 확인해야 합니다."]
        if category == "타법인 주식 취득·처분":
            return ["거래금액, 자기자본 대비 비중, 취득 목적과 대상 회사의 재무상태를 확인해야 합니다."]
        if category == "투자판단 주요경영사항":
            return ["주요내용이 실제 계약·승인·매출로 이어지는지와 후속 공시 일정을 확인해야 합니다."]
        if category == "전환청구권 행사":
            return ["전환으로 늘어나는 주식 수, 발행주식총수 대비 비중, 상장예정일 전후 수급 부담을 확인해야 합니다."]
        if category == "영업실적":
            return ["매출과 이익이 함께 개선됐는지, 일회성 요인이 아닌지 확인해야 합니다."]
        if category == "손익구조 변동":
            return ["손익 변동 사유가 본업 개선인지 일회성 비용·수익인지 확인해야 합니다."]
        if category == "기업가치 제고 계획":
            return ["목표 지표, 주주환원 규모, 실행 일정이 구체적인지 확인해야 합니다."]
        if category == "공정공시 중요정보":
            return ["전망과 계획은 실제 계약, 양산, 매출 반영 여부가 확인되기 전까지는 과대 해석을 피해야 합니다."]
        if category == "조회공시 답변":
            return ["답변이 부인인지, 미확정인지, 진행 중인지와 후속 재공시 일정을 확인해야 합니다."]
        if sentiment == "positive":
            return ["계약 규모, 지속 기간, 실제 매출 반영 시점을 함께 확인해야 합니다."]
        if sentiment == "negative":
            return ["거래 제한, 신뢰도 훼손, 재무 부담 가능성을 우선 확인해야 합니다."]
        if sentiment == "caution":
            return ["자금 목적, 희석 가능성, 조건 변경 여부에 따라 해석이 달라질 수 있습니다."]
        if source == "TITLE_ONLY" or not metrics:
            return ["정량 수치가 부족하므로 원문과 후속 공시를 함께 확인하는 편이 좋습니다."]
        return ["주가 방향성과 직접 연결하기 어려운 정보성 공시입니다."]

    def _headline(self, category: str, sentiment: str) -> str:
        if sentiment == "positive":
            return f"{category} 성격으로 긍정적으로 해석될 수 있는 공시입니다."
        if sentiment == "negative":
            return f"{category} 관련 부담이 큰 악재성 공시입니다."
        if sentiment == "caution":
            return f"{category} 공시로 세부 조건 확인이 필요합니다."
        if category == "정보성 공시":
            return "주가 방향성과 직접 연결하기 어려운 정보성 공시입니다."
        return f"{category} 관련 참고 공시입니다."

    def _sentiment_label(self, sentiment: str) -> str:
        return {
            "positive": "호재",
            "negative": "악재",
            "caution": "주의",
            "info": "정보",
        }.get(sentiment, "정보")

    def _sentiment_message(self, sentiment: str) -> str:
        return {
            "positive": "긍정적으로 해석될 수 있는 공시입니다.",
            "negative": "부정적으로 해석될 수 있는 공시입니다.",
            "caution": "방향성이 애매해 세부 조건 확인이 필요한 공시입니다.",
            "info": "주가 방향성과 직접 연결하기 어려운 정보성 공시입니다.",
        }.get(sentiment, "주가 방향성과 직접 연결하기 어려운 정보성 공시입니다.")

    def _contains(self, text: str, keywords: list[str]) -> bool:
        return any(keyword in text for keyword in keywords)

    def _clean_text(self, value: Any) -> str:
        return re.sub(r"\s+", " ", str(value or "")).strip()
