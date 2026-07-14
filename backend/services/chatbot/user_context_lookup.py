from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from backend.services.knowledge_repository import KnowledgeRepository


@dataclass(frozen=True, slots=True)
class UserLookupContext:
    auth_header: str | None
    user_id: str | None
    text: str
    knowledge_repository: KnowledgeRepository


def is_favorite_memory_query(text: str) -> bool:
    value = str(text or "").replace(" ", "")
    if "관심종목" not in value:
        return False
    return any(keyword in value for keyword in ["뭐였", "전에", "기억", "알려줘", "보여줘", "조회", "정리", "목록"])


def is_watchlist_focus_request(text: str) -> bool:
    value = str(text or "").replace(" ", "")
    if "관심종목" not in value:
        return False
    return any(keyword in value for keyword in ["오늘", "볼것", "중심", "기준", "체크", "챙겨"])


def is_user_note_query(text: str) -> bool:
    value = str(text or "")
    has_note_keyword = any(keyword in value for keyword in ["Obsidian", "옵시디언", "투자노트", "투자 노트", "메모", "노트"])
    has_lookup_keyword = any(keyword in value for keyword in ["찾아", "보여", "요약", "기준", "정리", "뭐"])
    return has_note_keyword and has_lookup_keyword


def build_favorite_memory_result(context: UserLookupContext) -> dict[str, Any] | None:
    if not context.auth_header or not context.user_id:
        return None
    memory_rows = context.knowledge_repository.list_memory_facts(
        context.auth_header,
        context.user_id,
        memory_type="favorite_symbol",
        limit=12,
    )
    watchlist_rows = context.knowledge_repository.list_watchlist_items(
        context.auth_header,
        context.user_id,
        limit=20,
    )
    memory_items = [
        {
            "content": str(row.get("content") or "").strip(),
            "symbol": str(row.get("symbol") or "").strip(),
            "name": "",
            "memory_type": str(row.get("memory_type") or "").strip(),
            "source": "USER_MEMORY_FACTS",
        }
        for row in memory_rows
        if str(row.get("content") or "").strip()
    ]
    watchlist_items = [_normalize_watchlist_item(row) for row in watchlist_rows]
    items = _dedupe_favorite_items([*watchlist_items, *memory_items])
    source = "USER_WATCHLIST" if watchlist_items else "USER_MEMORY_FACTS"
    view = "focus" if is_watchlist_focus_request(context.text) else "list"
    data = {
        "source": source,
        "view": view,
        "memory_type": "favorite_symbol",
        "items": items,
    }
    if not items:
        reply = "아직 하트 관심종목이나 자동메모리에 저장된 관심종목이 없습니다. 관심종목을 먼저 추가하면 이후 대화에서 기준으로 삼을게요."
        return {"reply": reply, "actions": [], "data": data}

    if is_watchlist_focus_request(context.text):
        reply = _build_watchlist_focus_reply(items)
    else:
        lines = [f"{index}. {_format_favorite_item(item)}" for index, item in enumerate(items, start=1)]
        reply = "관심종목을 표로 정리했습니다." if source == "USER_WATCHLIST" else "\n".join(["전에 말한 관심종목은 아래처럼 기억하고 있습니다.", *lines])
    return {"reply": reply, "actions": [], "data": data}


def build_user_note_result(context: UserLookupContext) -> dict[str, Any] | None:
    if not context.auth_header or not context.user_id:
        return None
    query = _extract_note_query(context.text)
    rows = context.knowledge_repository.search_user_notes(
        context.auth_header,
        context.user_id,
        query,
        limit=3,
    )
    items = [
        {
            "title": str(row.get("title") or "제목 없는 노트").strip(),
            "file_path": str(row.get("file_path") or "").strip(),
            "content": _compact_note_content(str(row.get("content") or "")),
            "source": str(row.get("source") or "note").strip(),
        }
        for row in rows
    ]
    data = {
        "source": "USER_KNOWLEDGE_NOTES",
        "query": query,
        "items": items,
    }
    if not items:
        target = f" '{query}'" if query else ""
        reply = f"저장된 투자노트/Obsidian 메모에서{target} 관련 내용을 찾지 못했습니다."
        return {"reply": reply, "actions": [], "data": data}

    lines = ["저장된 투자노트/Obsidian 메모에서 찾은 내용입니다."]
    for index, item in enumerate(items, start=1):
        path = f" ({item['file_path']})" if item["file_path"] else ""
        lines.append(f"{index}. {item['title']}{path}")
        if item["content"]:
            lines.append(f"   - {item['content']}")
    return {"reply": "\n".join(lines), "actions": [], "data": data}


def _extract_note_query(text: str) -> str:
    value = str(text or "").strip()
    removals = [
        "Obsidian에 적은",
        "Obsidian",
        "옵시디언에 적은",
        "옵시디언",
        "투자 노트",
        "투자노트",
        "메모",
        "노트",
        "찾아줘",
        "찾아",
        "보여줘",
        "보여",
        "요약해줘",
        "요약",
        "정리해줘",
        "정리",
        "기준으로",
        "기준",
        "에 적은",
    ]
    for removal in removals:
        value = value.replace(removal, " ")
    return re.sub(r"\s+", " ", value).strip()


def _compact_note_content(content: str, limit: int = 220) -> str:
    value = re.sub(r"\s+", " ", str(content or "")).strip()
    if len(value) <= limit:
        return value
    return f"{value[:limit].rstrip()}..."


def _normalize_watchlist_item(row: dict[str, Any]) -> dict[str, str]:
    symbol = str(row.get("symbol") or "").strip().upper()
    name = str(row.get("name") or symbol).strip()
    asset_type = str(row.get("asset_type") or "").strip().upper()
    exchange = str(row.get("exchange") or "").strip().upper()
    label = f"{name}({symbol})" if symbol and symbol != name else name or symbol
    return {
        "content": f"하트 관심종목: {label}",
        "symbol": symbol,
        "name": name,
        "asset_type": asset_type,
        "exchange": exchange,
        "source": "USER_WATCHLIST",
    }


def _dedupe_favorite_items(items: list[dict[str, str]]) -> list[dict[str, str]]:
    deduped: list[dict[str, str]] = []
    seen: set[str] = set()
    for item in items:
        key = str(item.get("symbol") or item.get("content") or "").strip().upper()
        if not key or key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    return deduped


def _format_favorite_item(item: dict[str, str]) -> str:
    if item.get("source") == "USER_WATCHLIST":
        name = str(item.get("name") or "").strip()
        symbol = str(item.get("symbol") or "").strip()
        asset_type = str(item.get("asset_type") or "").strip()
        exchange = str(item.get("exchange") or "").strip()
        suffix = " / ".join(part for part in [asset_type, exchange] if part)
        label = f"{name}({symbol})" if symbol and name and symbol != name else name or symbol
        return f"{label} - 하트 관심종목{f' ({suffix})' if suffix else ''}"
    return str(item.get("content") or "").strip()


def _build_watchlist_focus_reply(items: list[dict[str, str]]) -> str:
    groups: dict[str, list[str]] = {}
    for item in items:
        group = _infer_watchlist_group(item)
        groups.setdefault(group, []).append(_format_focus_label(item))

    blocks = ["관심종목 기준으로 오늘 볼 것을 분야별로 묶으면 이렇게 정리됩니다."]
    for index, (group, labels) in enumerate(groups.items(), start=1):
        blocks.append("\n".join([
            f"{index}. {group}: {', '.join(labels)}",
            f"   - 오늘 볼 것: {_focus_check_for_group(group)}",
            f"   - 같이 볼 후보: {_sector_candidates_for_group(group)}",
        ]))
    return "\n\n".join(blocks)


def _format_focus_label(item: dict[str, str]) -> str:
    name = str(item.get("name") or "").strip()
    symbol = str(item.get("symbol") or "").strip()
    content = str(item.get("content") or "").strip()
    if item.get("source") == "USER_MEMORY_FACTS" and content:
        return content
    if name and symbol and name != symbol:
        return f"{name}({symbol})"
    if name or symbol:
        return name or symbol
    return content


def _infer_watchlist_group(item: dict[str, str]) -> str:
    name = str(item.get("name") or item.get("content") or "").upper()
    symbol = str(item.get("symbol") or "").upper()
    asset_type = str(item.get("asset_type") or "").upper()
    if asset_type == "CRYPTO" or symbol in {"BTC", "ETH", "XRP", "DOGE", "SOL"}:
        return "가상자산"
    if any(keyword in name for keyword in ["삼성전자", "하이닉스", "반도체", "SK하이닉스"]) or symbol in {"005930", "000660"}:
        return "반도체·AI 인프라"
    if any(keyword in name for keyword in ["스페이스", "우주", "항공"]) or symbol in {"462350"}:
        return "우주항공"
    if asset_type == "STOCK":
        return "주식 기타"
    return "기타"


def _focus_check_for_group(group: str) -> str:
    checks = {
        "반도체·AI 인프라": "메모리 가격, AI 서버 수요, 미국 기술주 흐름, 관련 공시를 우선 확인",
        "우주항공": "수주·발사 일정, 정부 정책, 기술 인증·공시 여부를 우선 확인",
        "가상자산": "BTC 방향성, 거래량 급증, 규제 뉴스, 급등락 리스크를 우선 확인",
        "주식 기타": "해당 종목의 최신 뉴스, 공시, 거래량 변화를 우선 확인",
    }
    return checks.get(group, "최신 뉴스, 공시, 가격·거래량 변화를 우선 확인")


def _sector_candidates_for_group(group: str) -> str:
    candidates = {
        "반도체·AI 인프라": "한미반도체, HPSP, 리노공업 - HBM·AI 서버·반도체 장비/부품 연관",
        "우주항공": "한화에어로스페이스, 쎄트렉아이 - 발사체·위성·방산 우주 정책 연관",
        "가상자산": "BTC, ETH, SOL - 시장 방향성과 위험선호를 확인하기 좋은 대장/주요 코인",
        "주식 기타": "같은 업종 내 거래대금 상위 종목 - 뉴스·공시가 동반되는지 확인",
    }
    return candidates.get(group, "같은 업종의 거래대금 상위 종목 - 뉴스·공시 근거가 있을 때만 확인")
