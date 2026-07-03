import os
import re
import zipfile
from datetime import datetime, timezone
from io import BytesIO
from typing import Any
from xml.etree import ElementTree as ET

import requests

from backend.services.dart_repository import DartRepository


DART_DOCUMENT_URL = "https://opendart.fss.or.kr/api/document.xml"
DART_ANALYSIS_VERSION = "v2.9"


class DartDisclosureAnalysisService:
    def __init__(self) -> None:
        self.api_key = os.getenv("DART_API_KEY", "")
        self.request_timeout_seconds = int(os.getenv("DART_REQUEST_TIMEOUT_SECONDS", "15"))
        self.repository = DartRepository()

    def ensure_analysis(self, rcept_no: str) -> dict[str, Any]:
        clean_rcept_no = str(rcept_no or "").strip()
        if not clean_rcept_no:
            raise ValueError("공시 접수번호가 필요합니다.")

        cached = self.repository.get_disclosure_analysis(clean_rcept_no)
        cached_version = ((cached or {}).get("raw_payload") or {}).get("analysis_version")
        if cached and cached_version == DART_ANALYSIS_VERSION:
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
        saved = self.repository.upsert_disclosure_analysis(analysis)
        return {"analysis": saved or analysis, "fromCache": False}

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
        check_items = self._build_check_items(category, metrics, text, source)
        sentiment, confidence = self._refine_sentiment(category, sentiment, confidence, check_items)
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
                "text_excerpt": detail_text[:1200],
            },
            "analyzed_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }

    def _classify(self, report_name: str, text: str, has_detail: bool) -> tuple[str, str, str]:
        report_compact = re.sub(r"\s+", "", report_name)
        compact = re.sub(r"\s+", "", f"{report_name} {text}")

        if self._contains(report_compact, ["증권신고서", "유상증자", "전환사채", "신주인수권부사채", "교환사채"]):
            return "자금조달·증권신고서", "caution", "high" if has_detail else "medium"
        if self._contains(report_compact, ["증권예탁증권", "DR발행", "증권발행실적보고서", "투자설명서"]):
            return "자금조달·증권발행", "caution", "high" if has_detail else "medium"
        if self._contains(report_compact, ["정정"]):
            return "정정 공시", "caution", "medium" if has_detail else "low"
        if self._contains(report_compact, ["거래정지", "상장폐지", "관리종목", "감사의견", "횡령", "배임", "회생절차", "부도", "중대재해"]):
            return "시장 신뢰도 위험", "negative", "high" if has_detail else "medium"
        if self._contains(report_compact, ["단일판매", "공급계약", "수주"]):
            return "수주·공급계약", "positive", "high" if has_detail else "medium"
        if self._contains(report_compact, ["무상증자"]):
            return "무상증자", "positive", "high" if has_detail else "medium"
        if self._contains(report_compact, ["자기주식취득", "자사주취득", "자기주식소각", "주식소각"]):
            return "주주환원", "positive", "high" if has_detail else "medium"
        if self._contains(report_compact, ["현금배당", "현물배당", "배당결정"]):
            return "배당", "positive", "high" if has_detail else "medium"
        if self._contains(report_compact, ["특수관계인", "내부거래", "동일인등", "계열회사"]):
            return "특수관계인·내부거래", "caution", "medium" if has_detail else "low"
        if self._contains(report_compact, ["장래사업", "경영계획", "공정공시"]):
            return "사업계획·전망", "info", "medium" if has_detail else "low"
        if self._contains(report_compact, ["지속가능경영", "ESG", "자율공시"]):
            return "ESG·자율공시", "info", "medium" if has_detail else "low"
        if self._contains(report_compact, ["자기주식처분"]):
            return "자기주식 처분", "caution", "high" if has_detail else "medium"
        if self._contains(report_compact, ["최대주주변경"]):
            return "최대주주 변경", "caution", "high" if has_detail else "medium"
        if self._contains(report_compact, ["합병"]):
            return "합병", "caution", "high" if has_detail else "medium"
        if self._contains(report_compact, ["분할"]):
            return "분할", "caution", "high" if has_detail else "medium"
        if self._contains(report_compact, ["소송"]):
            return "소송", "negative", "high" if has_detail else "medium"
        return "정보성 공시", "info", "medium" if has_detail else "low"

    def _extract_metrics(self, text: str, category: str) -> list[dict[str, str]]:
        labels = self._metric_labels_for_category(category)
        metrics: list[dict[str, str]] = []
        seen: set[str] = set()

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
                metric_map.get("신주의 수") or metric_map.get("상장예정일") or "확인 필요",
                "무상증자는 유통 주식 수와 권리락 기준에 영향을 주기 때문에 배정 규모와 일정을 확인해야 합니다.",
                "positive",
            ))
            checks.append(self._check_item(
                "실질 가치",
                "기업가치 자체 증가 아님",
                "무상증자는 회계상 자본 항목 이동에 가깝기 때문에 실적 개선과는 구분해서 봐야 합니다.",
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
            "자금조달·증권신고서", "자금조달·증권발행", "특수관계인·내부거래",
            "정정 공시", "자기주식 처분", "최대주주 변경", "합병", "분할",
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
        if category in {"자금조달·증권신고서", "자금조달·증권발행", "정정 공시"}:
            return [
                "증자방식", "자금조달의 목적", "자금의 사용목적",
                "발행가액", "신주의 수", "납입일", "상장예정일",
                "전환가액", "사채의 권면총액", "전환청구기간",
            ]
        if category == "배당":
            return ["배당금총액", "1주당 배당금", "시가배당율", "배당기준일", "배당금지급 예정일자"]
        if category == "무상증자":
            return ["신주의 수", "배정기준일", "상장예정일"]
        if category == "주주환원":
            return ["취득예정금액", "처분예정금액", "소각예정금액", "취득예정주식", "취득예상기간"]
        if category == "특수관계인·내부거래":
            return ["거래금액", "거래상대방", "거래목적", "거래일자", "이사회 의결일"]
        if category == "자기주식 처분":
            return ["처분예정금액", "처분예정주식", "처분목적", "처분예정기간"]
        if category == "최대주주 변경":
            return ["변경후 최대주주", "변경사유", "지분율", "변경일"]
        if category == "합병":
            return ["합병상대회사", "합병비율", "합병기일", "합병목적"]
        if category == "분할":
            return ["분할신설회사", "분할기일", "분할목적"]
        if category == "소송":
            return ["소송가액", "원고", "피고", "청구내용", "판결ㆍ결정내용"]
        return []

    def _find_label_value(self, text: str, label: str, labels: list[str]) -> str:
        pattern = re.compile(rf"{re.escape(label)}\s*[:：]?\s*([^\n\r]{{1,120}})")
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

        amount_match = re.search(r"\d[\d,]*(?:\.\d+)?\s*(?:원|천원|백만원|억원|조원|달러|유로|USD|EUR)", text)
        plain_amount_match = re.search(r"\d[\d,]{3,}(?:\.\d+)?", text)
        percent_match = re.search(r"\d+(?:\.\d+)?\s*%", text)
        ratio_match = re.search(r"\d+(?:\.\d+)?\s*[:：]\s*\d+(?:\.\d+)?", text)
        stock_match = re.search(r"\d[\d,]*\s*주", text)
        date_match = re.search(r"\d{4}[.\-/년]\s*\d{1,2}[.\-/월]\s*\d{1,2}|\d{8}", text)

        if label in {"계약금액", "최근매출액", "발행가액", "전환가액", "사채의 권면총액", "배당금총액", "1주당 배당금", "취득예정금액", "처분예정금액", "소각예정금액", "소송가액"}:
            if amount_match:
                return amount_match.group(0)
            if label == "계약금액" and plain_amount_match:
                return f"{plain_amount_match.group(0)}원"
            return ""
        if label in {"매출액대비", "시가배당율", "합병비율", "지분율"}:
            if label == "합병비율" and ratio_match:
                return ratio_match.group(0)
            return percent_match.group(0) if percent_match else ""
        if label in {"신주의 수", "취득예정주식", "처분예정주식"}:
            return stock_match.group(0) if stock_match else ""
        if label in {"납입일", "상장예정일", "계약기간", "전환청구기간", "배당기준일", "배당금지급 예정일자", "취득예상기간", "거래일자", "이사회 의결일", "배정기준일", "처분예정기간", "변경일", "합병기일", "분할기일"}:
            return date_match.group(0) if date_match else ""
        if label in {"자금조달의 목적", "자금의 사용목적"}:
            purposes = [keyword for keyword in ["시설자금", "운영자금", "채무상환자금", "타법인증권취득자금", "기타자금"] if keyword in text]
            return ", ".join(purposes[:3]) if purposes else ""
        if label in {"계약상대", "거래상대방"}:
            return self._clean_counterparty(text)
        if label in {"처분목적", "변경사유", "합병목적", "분할목적", "청구내용", "판결ㆍ결정내용"}:
            return self._truncate_metric_value(text, 36)
        if label in {"변경후 최대주주", "합병상대회사", "분할신설회사", "원고", "피고"}:
            return self._clean_counterparty(text)
        if label == "증자방식":
            methods = [keyword for keyword in ["주주배정", "제3자배정", "일반공모", "공모", "사모"] if keyword in text]
            return ", ".join(methods[:2]) if methods else ""
        if label == "거래목적":
            return self._truncate_metric_value(text, 32)
        return self._truncate_metric_value(text)

    def _clean_counterparty(self, value: str) -> str:
        text = self._clean_text(value)
        text = re.split(r"\s*-\s*(?:회사와의 관계|4\.|판매|계약기간|계약금액|최근매출액|자산양수|이사회)", text)[0]
        text = re.split(r"\s+(?:회사와의\s*관계|판매ㆍ공급|계약기간|계약금액|최근매출액|자산양수|이사회)", text)[0]
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
        check_map = {item.get("question"): item.get("answer") for item in check_items or [] if item.get("question") and item.get("answer")}

        if category == "자금조달·증권신고서":
            purpose = check_map.get("자금 목적") or metric_map.get("자금의 사용목적") or metric_map.get("자금조달의 목적")
            shares = check_map.get("희석 가능성") or metric_map.get("신주의 수")
            due_date = metric_map.get("납입일")
            details = []
            if purpose:
                details.append(f"자금 목적은 {purpose}")
            if shares:
                details.append(f"발행 주식 수는 {shares}")
            if due_date:
                details.append(f"납입일은 {due_date}")
            suffix = ", ".join(details)
            return f"자금조달 관련 공시로, 기존 주주 희석 가능성과 발행 조건을 확인해야 합니다{f' ({suffix}).' if suffix else '.'}"

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

        if category == "주주환원":
            return "자사주 취득·소각 등 주주환원 성격의 공시입니다. 규모와 실행 기간을 확인해야 합니다."

        if category == "배당":
            dividend = metric_map.get("1주당 배당금") or metric_map.get("배당금총액")
            return f"배당 관련 공시입니다{f' ({dividend}).' if dividend else '. 배당 규모와 기준일을 확인해야 합니다.'}"

        if category == "무상증자":
            shares = metric_map.get("신주의 수")
            base_date = metric_map.get("배정기준일")
            listing_date = metric_map.get("상장예정일")
            details = []
            if shares:
                details.append(f"신주 수는 {shares}")
            if base_date:
                details.append(f"배정기준일은 {base_date}")
            if listing_date:
                details.append(f"상장예정일은 {listing_date}")
            suffix = ", ".join(details)
            return f"무상증자 결정 공시입니다. 시장에서는 긍정 재료로 해석되는 경우가 많지만, 기업가치가 바로 늘어나는 이벤트는 아니므로 권리락과 신주 상장 일정을 함께 봐야 합니다{f' ({suffix}).' if suffix else '.'}"

        if category == "시장 신뢰도 위험":
            return "거래정지, 상장폐지, 감사의견 등 시장 신뢰도에 부담이 될 수 있는 공시입니다."

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

        if category == "특수관계인·내부거래":
            return "특수관계인 또는 계열회사와의 거래 공시입니다. 거래 금액, 목적, 조건이 회사에 유리한지 확인해야 합니다."

        if category == "사업계획·전망":
            return "회사의 향후 사업계획이나 경영 방향을 알리는 공시입니다. 실제 실적 반영 여부는 후속 자료로 확인해야 합니다."

        if category == "ESG·자율공시":
            return "지속가능경영이나 자율공시 성격의 자료입니다. 주가 방향보다 회사의 비재무 정보 확인에 가깝습니다."

        if source == "TITLE_ONLY":
            return "상세 내용을 아직 확인하지 못해 제목 기준으로만 분류한 공시입니다."

        return "주가 방향성과 직접 연결하기 어려운 정보성 공시입니다."

    def _build_risk_points(self, category: str, sentiment: str, metrics: list[dict[str, str]], source: str) -> list[str]:
        if category == "사업계획·전망":
            return ["계획 발표와 실제 실적 반영은 다를 수 있으므로 후속 실적과 투자 집행 여부를 확인해야 합니다."]
        if category == "ESG·자율공시":
            return ["비재무 정보 성격이 강하므로 단기 주가 재료로 보기는 어렵습니다."]
        if category == "무상증자":
            return ["무상증자는 호재로 해석될 수 있지만 권리락, 신주 상장일, 단기 변동성을 함께 확인해야 합니다."]
        if category == "자기주식 처분":
            return ["처분 목적, 처분 규모, 시장 매도 여부에 따라 단기 수급 부담이 달라질 수 있습니다."]
        if category == "최대주주 변경":
            return ["새 최대주주의 재무 여력, 지분율, 경영권 안정성을 확인해야 합니다."]
        if category == "합병":
            return ["합병비율, 주식매수청구권, 합병 상대의 재무상태와 시너지 실현 가능성을 확인해야 합니다."]
        if category == "분할":
            return ["인적분할과 물적분할의 주주 영향이 다르므로 분할 구조와 신설회사 배정 방식을 확인해야 합니다."]
        if category == "소송":
            return ["소송가액, 패소 가능성, 충당부채 반영 여부와 영업 차질 가능성을 확인해야 합니다."]
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
