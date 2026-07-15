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
    if "\uad00\uc2ec\uc885\ubaa9" not in value:
        return False
    return any(
        keyword in value
        for keyword in [
            "\ubb50\uc600",
            "\uc804\uc5d0",
            "\uae30\uc5b5",
            "\uc54c\ub824\uc918",
            "\ubcf4\uc5ec\uc918",
            "\uc870\ud68c",
            "\uc815\ub9ac",
            "\ubaa9\ub85d",
        ]
    )


def is_watchlist_focus_request(text: str) -> bool:
    value = str(text or "").replace(" ", "")
    if "\uad00\uc2ec\uc885\ubaa9" not in value:
        return False
    return any(
        keyword in value
        for keyword in ["\uc624\ub298", "\ubcfc\uac83", "\uc911\uc2ec", "\uae30\uc900", "\uccb4\ud06c", "\ucc59\uaca8"]
    )


def is_user_note_query(text: str) -> bool:
    value = str(text or "")
    has_note_keyword = any(
        keyword in value
        for keyword in [
            "Obsidian",
            "\uc635\uc2dc\ub514\uc5b8",
            "\ud22c\uc790\ub178\ud2b8",
            "\ud22c\uc790 \ub178\ud2b8",
            "\uba54\ubaa8",
            "\ub178\ud2b8",
        ]
    )
    has_lookup_keyword = any(
        keyword in value
        for keyword in ["\ucc3e\uc544", "\ubcf4\uc5ec", "\uc694\uc57d", "\uae30\uc900", "\uc815\ub9ac", "\ubb50"]
    )
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
        reply = (
            "\uc544\uc9c1 \ud558\ud2b8 \uad00\uc2ec\uc885\ubaa9\uc774\ub098 \uc790\ub3d9\uba54\ubaa8\ub9ac\uc5d0 "
            "\uc800\uc7a5\ub41c \uad00\uc2ec\uc885\ubaa9\uc774 \uc5c6\uc2b5\ub2c8\ub2e4. "
            "\uad00\uc2ec\uc885\ubaa9\uc744 \uba3c\uc800 \ucd94\uac00\ud558\uba74 \uc774\ud6c4 \ub300\ud654\uc5d0\uc11c "
            "\uae30\uc900\uc73c\ub85c \uc0bc\uc744\uac8c\uc694."
        )
        return {"reply": reply, "actions": [], "data": data}

    if is_watchlist_focus_request(context.text):
        reply = _build_watchlist_focus_reply(items)
    elif source == "USER_WATCHLIST":
        reply = "\uad00\uc2ec\uc885\ubaa9\uc744 \ud45c\ub85c \uc815\ub9ac\ud588\uc2b5\ub2c8\ub2e4."
    else:
        lines = [f"{index}. {_format_favorite_item(item)}" for index, item in enumerate(items, start=1)]
        reply = "\n".join(
            [
                "\uc804\uc5d0 \ub9d0\ud55c \uad00\uc2ec\uc885\ubaa9\uc740 \uc544\ub798\ucc98\ub7fc \uae30\uc5b5\ud558\uace0 \uc788\uc2b5\ub2c8\ub2e4.",
                *lines,
            ]
        )
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
            "title": str(row.get("title") or "\uc81c\ubaa9 \uc5c6\ub294 \ub178\ud2b8").strip(),
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
        reply = (
            f"\uc800\uc7a5\ub41c \ud22c\uc790\ub178\ud2b8/Obsidian \uba54\ubaa8\uc5d0\uc11c{target} "
            "\uad00\ub828 \ub0b4\uc6a9\uc744 \ucc3e\uc9c0 \ubabb\ud588\uc2b5\ub2c8\ub2e4."
        )
        return {"reply": reply, "actions": [], "data": data}

    lines = ["\uc800\uc7a5\ub41c \ud22c\uc790\ub178\ud2b8/Obsidian \uba54\ubaa8\uc5d0\uc11c \ucc3e\uc740 \ub0b4\uc6a9\uc785\ub2c8\ub2e4."]
    for index, item in enumerate(items, start=1):
        path = f" ({item['file_path']})" if item["file_path"] else ""
        lines.append(f"{index}. {item['title']}{path}")
        if item["content"]:
            lines.append(f"   - {item['content']}")
    return {"reply": "\n".join(lines), "actions": [], "data": data}


def _extract_note_query(text: str) -> str:
    value = str(text or "").strip()
    removals = [
        "Obsidian\uc5d0 \uc801\uc740",
        "Obsidian",
        "\uc635\uc2dc\ub514\uc5b8\uc5d0 \uc801\uc740",
        "\uc635\uc2dc\ub514\uc5b8",
        "\ud22c\uc790 \ub178\ud2b8",
        "\ud22c\uc790\ub178\ud2b8",
        "\uba54\ubaa8",
        "\ub178\ud2b8",
        "\ucc3e\uc544\uc918",
        "\ucc3e\uc544",
        "\ubcf4\uc5ec\uc918",
        "\ubcf4\uc5ec",
        "\uc694\uc57d\ud574\uc918",
        "\uc694\uc57d",
        "\uc815\ub9ac\ud574\uc918",
        "\uc815\ub9ac",
        "\uae30\uc900\uc73c\ub85c",
        "\uae30\uc900",
        "\uc5d0 \uc801\uc740",
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
        "content": f"\ud558\ud2b8 \uad00\uc2ec\uc885\ubaa9 {label}",
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
        return f"{label} - \ud558\ud2b8 \uad00\uc2ec\uc885\ubaa9{f' ({suffix})' if suffix else ''}"
    return str(item.get("content") or "").strip()


def _build_watchlist_focus_reply(items: list[dict[str, str]]) -> str:
    groups: dict[str, list[str]] = {}
    for item in items:
        group = _infer_watchlist_group(item)
        groups.setdefault(group, []).append(_format_focus_label(item))

    blocks = ["\uad00\uc2ec\uc885\ubaa9 \uae30\uc900\uc73c\ub85c \uc624\ub298 \ubcfc \uac83\uc744 \ubd84\uc57c\ubcc4\ub85c \ubb36\uc73c\uba74 \uc774\ub807\uac8c \uc815\ub9ac\ub429\ub2c8\ub2e4."]
    for index, (group, labels) in enumerate(groups.items(), start=1):
        blocks.append(
            "\n".join(
                [
                    f"{index}. {group}: {', '.join(labels)}",
                    f"   - \uc624\ub298 \ubcfc \uac83: {_focus_check_for_group(group)}",
                    f"   - \uac19\uc774 \ubcfc \ud6c4\ubcf4: {_sector_candidates_for_group(group)}",
                ]
            )
        )
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
        return "\uac00\uc0c1\uc790\uc0b0"
    if any(keyword in name for keyword in ["\uc0bc\uc131\uc804\uc790", "\ud558\uc774\ub2c9\uc2a4", "\ubc18\ub3c4\uccb4", "SK\ud558\uc774\ub2c9\uc2a4"]) or symbol in {"005930", "000660"}:
        return "\ubc18\ub3c4\uccb4\u00b7AI \uc778\ud504\ub77c"
    if any(keyword in name for keyword in ["\uc2a4\ud398\uc774\uc2a4", "\uc6b0\uc8fc", "\ud56d\uacf5"]) or symbol in {"462350"}:
        return "\uc6b0\uc8fc\ud56d\uacf5"
    if asset_type.startswith("STOCK"):
        return "\uc8fc\uc2dd \uae30\ud0c0"
    return "\uae30\ud0c0"


def _focus_check_for_group(group: str) -> str:
    checks = {
        "\ubc18\ub3c4\uccb4\u00b7AI \uc778\ud504\ub77c": "\uba54\ubaa8\ub9ac \uac00\uaca9, AI \uc11c\ubc84 \uc218\uc694, \ubbf8\uad6d \uae30\uc220\uc8fc \ud750\ub984, \uad00\ub828 \uacf5\uc2dc\ub97c \uc6b0\uc120 \ud655\uc778",
        "\uc6b0\uc8fc\ud56d\uacf5": "\uc218\uc8fc\u00b7\ubc1c\uc0ac \uc77c\uc815, \uc815\ubd80 \uc815\ucc45, \uae30\uc220 \uc778\uc99d\u00b7\uacf5\uc2dc \uc5ec\ubd80\ub97c \uc6b0\uc120 \ud655\uc778",
        "\uac00\uc0c1\uc790\uc0b0": "BTC \ubc29\ud5a5\uc131, \uac70\ub798\ub7c9 \uae09\uc99d, \uaddc\uc81c \ub274\uc2a4, \uae09\ub4f1\ub77d \ub9ac\uc2a4\ud06c\ub97c \uc6b0\uc120 \ud655\uc778",
        "\uc8fc\uc2dd \uae30\ud0c0": "\ud574\ub2f9 \uc885\ubaa9\uc758 \ucd5c\uc2e0 \ub274\uc2a4, \uacf5\uc2dc, \uac70\ub798\ub7c9 \ubcc0\ud654\ub97c \uc6b0\uc120 \ud655\uc778",
    }
    return checks.get(group, "\ucd5c\uc2e0 \ub274\uc2a4, \uacf5\uc2dc, \uac00\uaca9\u00b7\uac70\ub798\ub7c9 \ubcc0\ud654\ub97c \uc6b0\uc120 \ud655\uc778")


def _sector_candidates_for_group(group: str) -> str:
    candidates = {
        "\ubc18\ub3c4\uccb4\u00b7AI \uc778\ud504\ub77c": "\ud55c\ubbf8\ubc18\ub3c4\uccb4, HPSP, \ub9ac\ub178\uacf5\uc5c5 - HBM\u00b7AI \uc11c\ubc84\u00b7\ubc18\ub3c4\uccb4 \uc7a5\ube44/\ubd80\ud488 \uc5f0\uad00",
        "\uc6b0\uc8fc\ud56d\uacf5": "\ud55c\ud654\uc5d0\uc5b4\ub85c\uc2a4\ud398\uc774\uc2a4, \ucee8\ud14d, AP\uc704\uc131 - \ubc1c\uc0ac\uccb4\u00b7\uc704\uc131\u00b7\ubc29\uc0b0/\uc6b0\uc8fc \uc815\ucc45 \uc5f0\uad00",
        "\uac00\uc0c1\uc790\uc0b0": "BTC, ETH, SOL - \uc2dc\uc7a5 \ubc29\ud5a5\uc131\uacfc \uc704\ud5d8\uc2e0\ud638\ub97c \ud655\uc778\ud558\uae30 \uc88b\uc740 \ub300\ud45c \uc8fc\uc694 \ucf54\uc778",
        "\uc8fc\uc2dd \uae30\ud0c0": "\uac19\uc740 \uc5c5\uc885 \ub0b4 \uac70\ub798\ub300\uae08 \uc0c1\uc704 \uc885\ubaa9 - \ub274\uc2a4\u00b7\uacf5\uc2dc\uac00 \ub3d9\ubc18\ub418\ub294\uc9c0 \ud655\uc778",
    }
    return candidates.get(group, "\uac19\uc740 \uc5c5\uc885\uc758 \uac70\ub798\ub300\uae08 \uc0c1\uc704 \uc885\ubaa9 - \ub274\uc2a4\u00b7\uacf5\uc2dc \uadfc\uac70\uac00 \uc788\uc744 \ub54c\ub9cc \ud655\uc778")
