from __future__ import annotations

from dataclasses import dataclass
from typing import TypeAlias

from backend.services.knowledge_chunk_service import KnowledgeChunkService

JsonValue: TypeAlias = str | int | float | bool | None | list["JsonValue"] | dict[str, "JsonValue"]
JsonObject: TypeAlias = dict[str, JsonValue]


@dataclass(frozen=True, slots=True)
class DisclosureSummaryDocument:
    rcept_no: str
    stock_code: str
    corp_name: str
    report_name: str
    rcept_dt: str
    url: str
    category: str
    sentiment_label: str
    sentiment_message: str
    headline: str
    plain_summary: str
    key_points: list[str]
    risk_points: list[str]
    check_items: list[str]
    metrics: list[str]


def disclosure_summary_document_from_rows(
    analysis: JsonObject,
    disclosure: JsonObject | None = None,
) -> DisclosureSummaryDocument:
    metadata = disclosure or {}
    rcept_no = _read_text(analysis, "rcept_no")
    return DisclosureSummaryDocument(
        rcept_no=rcept_no,
        stock_code=_read_text(metadata, "stock_code"),
        corp_name=_read_text(metadata, "corp_name"),
        report_name=_read_text(metadata, "report_nm"),
        rcept_dt=_read_text(metadata, "rcept_dt"),
        url=_read_text(metadata, "url"),
        category=_read_text(analysis, "category"),
        sentiment_label=_read_text(analysis, "sentiment_label"),
        sentiment_message=_read_text(analysis, "sentiment_message"),
        headline=_read_text(analysis, "headline"),
        plain_summary=_read_text(analysis, "plain_summary"),
        key_points=_read_text_list(analysis.get("key_points")),
        risk_points=_read_text_list(analysis.get("risk_points")),
        check_items=_read_text_list(analysis.get("check_items")),
        metrics=_read_text_list(analysis.get("metrics")),
    )


def build_disclosure_summary_text(document: DisclosureSummaryDocument) -> str:
    sections = [
        f"회사: {document.corp_name} ({document.stock_code})",
        f"공시: {document.report_name}",
        f"분류: {document.category}",
        f"판정: {document.sentiment_label}",
        document.sentiment_message,
        document.headline,
        document.plain_summary,
        _format_list("핵심 포인트", document.key_points),
        _format_list("주의 포인트", document.risk_points),
        _format_list("확인 항목", document.check_items),
        _format_list("핵심 수치", document.metrics),
    ]
    return "\n".join(section for section in sections if section.strip())


def build_disclosure_chunk_metadata(document: DisclosureSummaryDocument) -> JsonObject:
    return {
        "source_type": "DISCLOSURE",
        "rcept_no": document.rcept_no,
        "symbol": document.stock_code,
        "market": "KR",
        "corp_name": document.corp_name,
        "report_name": document.report_name,
        "rcept_dt": document.rcept_dt,
        "url": document.url,
        "category": document.category,
        "sentiment": document.sentiment_label,
    }


def build_disclosure_summary_chunks(
    chunk_service: KnowledgeChunkService,
    document: DisclosureSummaryDocument,
) -> list[JsonObject]:
    return chunk_service.build_chunks(
        user_id=None,
        source_type="DISCLOSURE",
        source_id=document.rcept_no,
        text=build_disclosure_summary_text(document),
        symbol=document.stock_code,
        market="KR",
        metadata=build_disclosure_chunk_metadata(document),
        importance_score=_importance_score(document.sentiment_label),
        freshness_score=0.7,
    )


def _format_list(label: str, values: list[str]) -> str:
    clean_values = [value.strip() for value in values if value.strip()]
    if not clean_values:
        return ""
    return f"{label}: " + " / ".join(clean_values)


def _importance_score(sentiment_label: str) -> float:
    if sentiment_label in {"호재", "악재", "주의"}:
        return 0.8
    return 0.5


def _read_text(row: JsonObject, key: str) -> str:
    value = row.get(key)
    return value if isinstance(value, str) else ""


def _read_text_list(value: JsonValue) -> list[str]:
    if not isinstance(value, list):
        return []
    texts: list[str] = []
    for item in value:
        if isinstance(item, str):
            texts.append(item)
        elif isinstance(item, dict):
            texts.extend(f"{key}: {item_value}" for key, item_value in item.items() if isinstance(item_value, str))
    return texts
