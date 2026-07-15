from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from functools import lru_cache
from typing import Any
from uuid import uuid4

from backend.services.supabase_client import (
    query_supabase_as_service_role,
    safe_query_supabase_as_service_role,
)


DEFAULT_TEMPORARY_SYMBOL_ALIASES = {
    "SKHYV": "SKHY",
}

REFERENCE_TABLES = (
    ("user_watchlist", "symbol"),
    ("trade_proposals", "symbol"),
    ("trade_proposals", "ticker"),
    ("broker_order_history", "symbol"),
    ("auto_trading_rules", "symbol"),
)


def normalize_symbol(symbol: str | None) -> str:
    return str(symbol or "").strip().upper()


@lru_cache(maxsize=1)
def load_temporary_symbol_aliases() -> dict[str, str]:
    rows = safe_query_supabase_as_service_role(
        "symbol_aliases",
        "GET",
        params={
            "select": "alias_symbol,canonical_symbol",
            "alias_type": "eq.TEMPORARY",
            "is_active": "eq.true",
        },
    )
    if not rows:
        return dict(DEFAULT_TEMPORARY_SYMBOL_ALIASES)

    aliases = {}
    for row in rows:
        alias_symbol = normalize_symbol(row.get("alias_symbol"))
        canonical_symbol = normalize_symbol(row.get("canonical_symbol"))
        if alias_symbol and canonical_symbol:
            aliases[alias_symbol] = canonical_symbol
    return aliases or dict(DEFAULT_TEMPORARY_SYMBOL_ALIASES)


def canonical_symbol_for(symbol: str | None) -> str:
    normalized = normalize_symbol(symbol)
    return load_temporary_symbol_aliases().get(normalized, normalized)


def is_temporary_symbol(symbol: str | None) -> bool:
    return normalize_symbol(symbol) in load_temporary_symbol_aliases()


def should_hide_temporary_symbol(symbol: str | None, available_symbols: set[str]) -> bool:
    normalized = normalize_symbol(symbol)
    if not is_temporary_symbol(normalized):
        return False
    canonical = canonical_symbol_for(normalized)
    return canonical in available_symbols


def decorate_symbol_result(row: dict[str, Any]) -> dict[str, Any]:
    symbol = normalize_symbol(row.get("symbol"))
    is_temporary = is_temporary_symbol(symbol)
    result = dict(row)
    result["symbol"] = symbol
    result["is_temporary_symbol"] = is_temporary
    if is_temporary:
        result["canonical_symbol"] = canonical_symbol_for(symbol)
        result["symbol_badge"] = "임시코드"
    return result


def filter_symbol_results(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    available_symbols = {normalize_symbol(row.get("symbol")) for row in rows if row.get("symbol")}
    filtered: list[dict[str, Any]] = []
    seen = set()

    for row in rows:
        symbol = normalize_symbol(row.get("symbol"))
        if not symbol or symbol in seen:
            continue
        if should_hide_temporary_symbol(symbol, available_symbols):
            continue
        decorated = decorate_symbol_result(row)
        seen.add(symbol)
        filtered.append(decorated)

    return filtered


def _safe_count(table: str, column: str, symbol: str) -> int:
    try:
        rows = query_supabase_as_service_role(
            table,
            "GET",
            params={"select": column, column: f"eq.{symbol}", "limit": "1"},
        )
        return 1 if rows else 0
    except Exception:
        return 0


def count_symbol_references(symbol: str) -> int:
    normalized = normalize_symbol(symbol)
    if not normalized:
        return 0
    return sum(_safe_count(table, column, normalized) for table, column in REFERENCE_TABLES)


def _load_source_rows(table: str, limit: int, market_country: str) -> list[dict[str, Any]]:
    select = "symbol,name,market_country,market_segment,is_active,updated_at"
    if table == "kis_stock_master":
        select = "symbol,name,display_name,market_country,market_segment,is_active,updated_at"
    elif table == "kis_stock_turnover_latest":
        select = "symbol,name,market_country,market_segment,updated_at,as_of"
    params = {
        "select": select,
        "limit": str(limit),
    }
    if market_country in {"KR", "US"}:
        params["market_country"] = f"eq.{market_country}"
    rows = safe_query_supabase_as_service_role(table, "GET", params=params) or []
    return rows if isinstance(rows, list) else []


def _merge_source_rows(limit: int, market_country: str) -> list[dict[str, Any]]:
    merged: list[dict[str, Any]] = []
    for table in ("kis_stock_master", "kis_stock_turnover_latest"):
        for row in _load_source_rows(table, limit, market_country):
            item = dict(row)
            item["source_table"] = table
            merged.append(item)
    return merged[: max(limit * 2, limit)]


def _build_canonical_lookup(rows: list[dict[str, Any]]) -> set[str]:
    return {normalize_symbol(row.get("symbol")) for row in rows if row.get("symbol")}


def _classify_row(row: dict[str, Any], all_symbols: set[str]) -> dict[str, Any]:
    symbol = normalize_symbol(row.get("symbol"))
    source_table = row.get("source_table") or "kis_stock_master"
    reference_count = count_symbol_references(symbol)
    is_temporary = is_temporary_symbol(symbol)
    canonical = canonical_symbol_for(symbol)
    canonical_exists = canonical != symbol and canonical in all_symbols
    is_active = row.get("is_active", True)

    status = "NORMAL"
    suggested_action = "NONE"
    reason = "정상 후보입니다."

    if is_temporary and canonical_exists:
        reason = f"정식 심볼 {canonical}이 존재하는 상장 전 임시코드입니다."
        if source_table == "kis_stock_turnover_latest" and reference_count == 0:
            status = "DELETABLE"
            suggested_action = "DELETE_CACHE"
        else:
            status = "DEACTIVATION_CANDIDATE" if is_active else "INACTIVE"
            suggested_action = "DEACTIVATE" if is_active else "NONE"
    elif is_temporary:
        status = "SUSPICIOUS"
        suggested_action = "REVIEW"
        reason = f"임시코드로 추정됩니다. 정식 심볼 후보는 {canonical}입니다."
    elif is_active is False:
        status = "INACTIVE"
        suggested_action = "RESTORE"
        reason = "비활성화된 종목입니다."

    return {
        "symbol": symbol,
        "name": row.get("display_name") or row.get("name") or symbol,
        "source_table": source_table,
        "market_country": row.get("market_country") or "KR",
        "market_segment": row.get("market_segment") or "OTHER",
        "status": status,
        "reason": reason,
        "suggested_action": suggested_action,
        "broker_check_result": {
            "is_temporary_symbol": is_temporary,
            "canonical_symbol": canonical if canonical != symbol else None,
            "canonical_exists": canonical_exists,
        },
        "reference_count": reference_count,
        "last_seen_at": row.get("updated_at") or row.get("as_of"),
    }


def _summarize_items(items: list[dict[str, Any]]) -> dict[str, int]:
    counts = defaultdict(int)
    for item in items:
        counts[item["status"]] += 1
    return {
        "checked_count": len(items),
        "normal_count": counts["NORMAL"],
        "suspicious_count": counts["SUSPICIOUS"],
        "deactivation_candidate_count": counts["DEACTIVATION_CANDIDATE"],
        "deletable_count": counts["DELETABLE"],
    }


def run_symbol_reconciliation(actor_id: str, market_country: str = "ALL", limit: int = 1000) -> dict[str, Any]:
    normalized_country = str(market_country or "ALL").upper()
    rows = _merge_source_rows(max(1, min(int(limit or 1000), 5000)), normalized_country)
    all_symbols = _build_canonical_lookup(rows)
    items = [_classify_row(row, all_symbols) for row in rows]
    summary = _summarize_items(items)
    run_id = str(uuid4())
    now = datetime.now(timezone.utc).isoformat()

    run_payload = {
        "id": run_id,
        "started_at": now,
        "finished_at": now,
        "status": "COMPLETED",
        **summary,
        "raw_summary": {
            "market_country": normalized_country,
            "limit": limit,
            "temporary_aliases": load_temporary_symbol_aliases(),
        },
        "created_by": actor_id,
    }
    query_supabase_as_service_role("admin_symbol_reconciliation_runs", "POST", json_data=run_payload)

    item_payloads = [{**item, "run_id": run_id} for item in items]
    for start in range(0, len(item_payloads), 200):
        query_supabase_as_service_role(
            "admin_symbol_reconciliation_items",
            "POST",
            json_data=item_payloads[start:start + 200],
        )

    return {"run": run_payload, "items": item_payloads}


def get_latest_symbol_reconciliation() -> dict[str, Any]:
    runs = safe_query_supabase_as_service_role(
        "admin_symbol_reconciliation_runs",
        "GET",
        params={"select": "*", "order": "started_at.desc", "limit": "1"},
    ) or []
    if not runs:
        return {"run": None, "items": []}
    run = runs[0]
    items = safe_query_supabase_as_service_role(
        "admin_symbol_reconciliation_items",
        "GET",
        params={"select": "*", "run_id": f"eq.{run['id']}", "order": "status.asc,symbol.asc"},
    ) or []
    return {"run": run, "items": items}


def deactivate_symbols(symbols: list[str], reason: str) -> dict[str, Any]:
    changed = []
    for symbol in [normalize_symbol(value) for value in symbols]:
        if not symbol:
            continue
        query_supabase_as_service_role(
            f"kis_stock_master?symbol=eq.{symbol}",
            "PATCH",
            json_data={"is_active": False},
        )
        changed.append(symbol)
    return {"symbols": changed, "reason": reason}


def restore_symbols(symbols: list[str]) -> dict[str, Any]:
    changed = []
    for symbol in [normalize_symbol(value) for value in symbols]:
        if not symbol:
            continue
        query_supabase_as_service_role(
            f"kis_stock_master?symbol=eq.{symbol}",
            "PATCH",
            json_data={"is_active": True},
        )
        changed.append(symbol)
    return {"symbols": changed}


def delete_symbols(symbols: list[str], source_table: str) -> dict[str, Any]:
    if source_table not in {"kis_stock_turnover_latest", "kis_stock_master"}:
        raise ValueError("삭제 가능한 원천 테이블이 아닙니다.")

    deleted = []
    blocked = []
    for symbol in [normalize_symbol(value) for value in symbols]:
        if not symbol:
            continue
        reference_count = count_symbol_references(symbol)
        if reference_count > 0:
            blocked.append({"symbol": symbol, "reference_count": reference_count})
            continue
        if source_table == "kis_stock_master":
            rows = safe_query_supabase_as_service_role(
                "kis_stock_master",
                "GET",
                params={"symbol": f"eq.{symbol}", "is_active": "eq.false", "limit": "1"},
            ) or []
            if not rows:
                blocked.append({"symbol": symbol, "reference_count": reference_count, "reason": "마스터 종목은 먼저 비활성화해야 합니다."})
                continue
        query_supabase_as_service_role(f"{source_table}?symbol=eq.{symbol}", "DELETE")
        deleted.append(symbol)
    return {"deleted": deleted, "blocked": blocked}
