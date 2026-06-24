import csv
import json
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from typing import Any

from backend.services.kis_client import KISClient
from backend.services.market_repository import MarketRepository


def _to_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return default
        return float(str(value).replace(",", ""))
    except (TypeError, ValueError):
        return default


def _read_text_with_fallback(path: Path) -> str:
    raw = path.read_bytes()
    for encoding in ("utf-8-sig", "utf-8", "cp949", "euc-kr"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="ignore")


def _market_segment_from_path(path: Path) -> str:
    name = path.stem.lower()
    if "kosdaq" in name:
        return "KOSDAQ"
    if "kospi" in name:
        return "KOSPI"
    if "konex" in name:
        return "KONEX"
    return "OTHER"


def _normalize_fixed_width_mst_line(line: str, market_segment: str) -> dict[str, Any] | None:
    raw = line.rstrip("\n\r")
    if not raw.strip():
        return None

    symbol = raw.split()[0].strip() if raw.split() else ""
    if not re.fullmatch(r"\d{6}", symbol):
        return None

    if not symbol:
        return None

    name_part = raw.split(symbol, 1)[-1].strip()
    match = re.search(r"([^\s]{2,}.*?)(?:\s{2,}|$)", name_part)
    name = (match.group(1) if match else name_part).strip()
    if not name:
        return None

    return {
        "symbol": symbol.upper(),
        "name": name,
        "market_segment": market_segment,
        "market_country": "KR",
        "asset_type": "STOCK",
        "source": "KIS",
        "listed_at": None,
        "source_file_row": {"raw_line": raw},
        "is_active": True,
    }


def _load_records_from_file(file_path: str) -> list[dict[str, Any]]:
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"종목 정보 파일을 찾을 수 없습니다: {file_path}")

    suffix = path.suffix.lower()
    if suffix == ".mst":
        market_segment = _market_segment_from_path(path)
        text = _read_text_with_fallback(path)
        rows: list[dict[str, Any]] = []
        for line in text.splitlines():
            row = _normalize_fixed_width_mst_line(line, market_segment)
            if row:
                rows.append(row)
        return rows

    if suffix == ".json":
        payload = json.loads(_read_text_with_fallback(path))
        if isinstance(payload, list):
            return [dict(item) for item in payload if isinstance(item, dict)]
        if isinstance(payload, dict):
            for key in ("data", "items", "rows", "stocks", "symbols"):
                value = payload.get(key)
                if isinstance(value, list):
                    return [dict(item) for item in value if isinstance(item, dict)]
        raise ValueError("JSON 파일 형식을 해석할 수 없습니다. list 또는 data/items/rows 배열이 필요합니다.")

    if suffix in (".csv", ".txt"):
        text = _read_text_with_fallback(path)
        reader = csv.DictReader(text.splitlines())
        return [dict(row) for row in reader]

    raise ValueError("지원하지 않는 파일 형식입니다. .mst, .csv, .json 파일을 사용해주세요.")


def normalize_universe_rows(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []

    for row in records:
        symbol = str(
            row.get("symbol")
            or row.get("code")
            or row.get("iscd")
            or row.get("stk_cd")
            or row.get("stock_code")
            or row.get("종목코드")
            or row.get("단축코드")
            or row.get("종목번호")
            or ""
        ).strip()
        name = str(
            row.get("name")
            or row.get("hname")
            or row.get("stock_name")
            or row.get("issue_name")
            or row.get("종목명")
            or row.get("한글명")
            or ""
        ).strip()

        if not symbol or not name:
            continue

        market_segment = str(
            row.get("market_segment")
            or row.get("market")
            or row.get("market_division")
            or row.get("market_nm")
            or row.get("시장구분")
            or row.get("시장명")
            or "OTHER"
        ).strip().upper()
        if market_segment not in {"KOSPI", "KOSDAQ", "KONEX", "ETF", "ETN"}:
            market_segment = "OTHER"

        listed_at = str(row.get("listed_at") or row.get("listing_date") or row.get("상장일") or row.get("상장일자") or "").strip()

        normalized.append({
            "symbol": symbol.replace(" ", "").replace(".", "").upper(),
            "name": name,
            "market_segment": market_segment,
            "market_country": "KR",
            "asset_type": "STOCK",
            "source": "KIS",
            "listed_at": listed_at or None,
            "source_file_row": dict(row),
            "is_active": True,
        })

    return normalized


def build_turnover_snapshot_rows(
    master_rows: list[dict[str, Any]],
    kis_client: KISClient,
    max_workers: int = 4,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    errors: list[dict[str, Any]] = []
    snapshots: list[dict[str, Any]] = []

    def fetch_one(row: dict[str, Any]) -> dict[str, Any]:
        symbol = row["symbol"]
        price_data = kis_client.get_price(symbol)
        raw_output = price_data.get("raw", {}).get("output", {}) or {}
        current_price = _to_float(price_data.get("current_price"))
        change_rate = _to_float(price_data.get("change_rate"))
        trading_volume = _to_float(
            raw_output.get("acml_vol")
            or raw_output.get("acc_trdvol")
            or raw_output.get("stck_vol")
            or raw_output.get("volume")
        )
        trading_value = _to_float(
            raw_output.get("acml_tr_pbmn")
            or raw_output.get("acc_trdprc")
            or raw_output.get("stck_tr_pbmn")
        )
        if not trading_value and current_price and trading_volume:
            trading_value = current_price * trading_volume

        return {
            "symbol": symbol,
            "name": row["name"],
            "market_segment": row["market_segment"],
            "market_country": row["market_country"],
            "current_price": current_price,
            "change_rate": change_rate,
            "trading_volume": trading_volume,
            "trading_value": trading_value,
            "as_of": datetime.utcnow().isoformat() + "Z",
            "raw_payload": raw_output,
        }

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_map = {executor.submit(fetch_one, row): row for row in master_rows}
        for future in as_completed(future_map):
            row = future_map[future]
            try:
                snapshots.append(future.result())
            except Exception as exc:
                errors.append({
                    "symbol": row.get("symbol"),
                    "name": row.get("name"),
                    "error": str(exc),
                })

    snapshots.sort(key=lambda item: item["trading_value"], reverse=True)
    return snapshots, errors


def _dedupe_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    deduped: list[dict[str, Any]] = []
    for row in rows:
        symbol = str(row.get("symbol") or "").strip().upper()
        if not symbol or symbol in seen:
            continue
        seen.add(symbol)
        deduped.append(row)
    return deduped


class KISMarketUniverseService:
    def __init__(self) -> None:
        self.repository = MarketRepository()

    def sync_from_files(
        self,
        file_paths: list[str],
        kis_client: KISClient,
        refresh_quotes: bool = True,
        max_workers: int = 4,
        quote_limit: int | None = 300,
    ) -> dict[str, Any]:
        records: list[dict[str, Any]] = []
        for file_path in file_paths:
            records.extend(_load_records_from_file(file_path))

        master_rows = normalize_universe_rows(records)
        master_rows = _dedupe_rows(master_rows)
        if not master_rows:
            raise ValueError("종목 정보 파일에서 저장할 종목을 찾지 못했습니다.")

        self.repository.upsert_stock_master(master_rows)

        quote_rows: list[dict[str, Any]] = []
        quote_errors: list[dict[str, Any]] = []
        if refresh_quotes:
            quote_target_rows = master_rows[:quote_limit] if quote_limit else master_rows
            quote_rows, quote_errors = build_turnover_snapshot_rows(quote_target_rows, kis_client, max_workers=max_workers)
            self.repository.upsert_turnover_latest(quote_rows)

        return {
            "master_count": len(master_rows),
            "quote_count": len(quote_rows),
            "quote_limit": quote_limit,
            "quote_error_count": len(quote_errors),
            "quote_errors": quote_errors[:20],
            "sample": master_rows[:5],
        }

    def sync_from_file(
        self,
        file_path: str,
        kis_client: KISClient,
        refresh_quotes: bool = True,
        max_workers: int = 4,
        quote_limit: int | None = 300,
    ) -> dict[str, Any]:
        return self.sync_from_files(
            [file_path],
            kis_client=kis_client,
            refresh_quotes=refresh_quotes,
            max_workers=max_workers,
            quote_limit=quote_limit,
        )
