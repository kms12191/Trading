import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests
from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[2]
BACKEND_DIR = PROJECT_ROOT / "backend"
DEFAULT_UNIVERSE_PATH = PROJECT_ROOT / "ml" / "data" / "reference" / "training_universes.json"
BATCH_NAME = "ml_top10_domestic_dart_ai"

load_dotenv(BACKEND_DIR / ".env")
sys.path.append(str(PROJECT_ROOT))

from backend.services.dart_analysis_service import DART_ANALYSIS_VERSION, DartDisclosureAnalysisService


ETF_KEYWORDS = ("ETF", "ETN", "KODEX", "TIGER", "ACE", "SOL", "KBSTAR", "HANARO", "ARIRANG", "레버리지", "인버스")
AI_SENTIMENTS = {"positive", "negative", "caution"}


def load_top_domestic_symbols(path: Path, limit: int, offset: int = 0) -> list[str]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    etf_symbols = set(payload.get("stock_etf_20") or [])
    symbols: list[str] = []
    for symbol in payload.get("stock_core_90") or []:
        normalized = str(symbol or "").strip()
        if len(normalized) != 6 or not normalized.isdigit():
            continue
        if normalized in etf_symbols:
            continue
        if normalized not in symbols:
            symbols.append(normalized)
        if len(symbols) >= offset + limit:
            break
    return symbols[offset:offset + limit]


def maybe_contains_etf_keyword(disclosure: dict[str, Any]) -> bool:
    text = f"{disclosure.get('corp_name') or ''} {disclosure.get('report_nm') or ''}".upper()
    return any(keyword.upper() in text for keyword in ETF_KEYWORDS)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="ML 국내주식 유니버스의 DART 공시를 AI 요약 캐시에 적재합니다.")
    parser.add_argument("--universe-path", default=str(DEFAULT_UNIVERSE_PATH), help="training_universes.json 경로")
    parser.add_argument("--symbol-limit", type=int, default=10, help="처리할 국내주식 종목 수")
    parser.add_argument("--symbol-offset", type=int, default=0, help="국내주식 유니버스에서 건너뛸 종목 수")
    parser.add_argument("--disclosure-limit", type=int, default=10, help="종목별 최근 공시 수")
    parser.add_argument("--provider", default="gemini", choices=["gemini", "openai"], help="AI 보정 제공자")
    parser.add_argument("--dry-run", action="store_true", help="DB 저장 없이 대상과 분류만 확인")
    parser.add_argument("--count-only", action="store_true", help="저장하지 않고 sentiment 개수만 집계")
    parser.add_argument("--candidate-offset", type=int, default=0, help="AI 후보 목록에서 건너뛸 개수")
    parser.add_argument("--candidate-limit", type=int, default=0, help="AI 후보 목록에서 처리할 최대 개수")
    parser.add_argument("--skip-existing-ai", action="store_true", help="이미 AI 보정된 분석 캐시는 스킵")
    parser.add_argument("--retry-count", type=int, default=3, help="429 등 일시 실패 시 재시도 횟수")
    parser.add_argument("--retry-sleep-seconds", type=int, default=60, help="재시도 전 대기 초")
    parser.add_argument("--save-info-rules", action="store_true", help="정보성 공시도 룰 분석 결과만 DB에 저장")
    parser.add_argument("--cleanup-batch-info", action="store_true", help="이번 배치명으로 저장된 정보성 분석 캐시를 삭제")
    return parser


def cleanup_batch_info_rows(service: DartDisclosureAnalysisService) -> int:
    repository = service.repository
    response = requests.delete(
        f"{repository.supabase_url}/rest/v1/dart_disclosure_analyses",
        headers=repository._write_headers(),
        params={
            "sentiment": "eq.info",
            "raw_payload->>batch_name": f"eq.{BATCH_NAME}",
        },
        timeout=30,
    )
    response.raise_for_status()
    content_range = response.headers.get("Content-Range", "")
    if "/" in content_range:
        total = content_range.rsplit("/", 1)[-1]
        return int(total) if total.isdigit() else 0
    return 0


def fetch_analysis_map(service: DartDisclosureAnalysisService, rcept_nos: list[str]) -> dict[str, dict[str, Any]]:
    repository = service.repository
    rows_by_rcept_no: dict[str, dict[str, Any]] = {}
    for index in range(0, len(rcept_nos), 200):
        chunk = [value for value in rcept_nos[index:index + 200] if value]
        if not chunk:
            continue
        response = requests.get(
            f"{repository.supabase_url}/rest/v1/dart_disclosure_analyses",
            headers=repository._read_headers(),
            params={
                "select": "rcept_no,sentiment,plain_summary,raw_payload",
                "rcept_no": f"in.({','.join(chunk)})",
            },
            timeout=30,
        )
        response.raise_for_status()
        for row in response.json():
            rows_by_rcept_no[str(row.get("rcept_no") or "")] = row
    return rows_by_rcept_no


def collect_disclosures(service: DartDisclosureAnalysisService, symbols: list[str], disclosure_limit: int) -> list[dict[str, Any]]:
    disclosures: list[dict[str, Any]] = []
    for symbol in symbols:
        disclosures.extend(service.repository.list_disclosures(symbol=symbol, limit=disclosure_limit))
    return disclosures


def is_existing_ai_analysis(cached: dict[str, Any] | None) -> bool:
    if not cached:
        return False
    raw_payload = cached.get("raw_payload") or {}
    return bool(
        cached.get("plain_summary")
        and raw_payload.get("analysis_version") == DART_ANALYSIS_VERSION
        and (
            raw_payload.get("analysis_mode") == "v3_ai_refined"
            or raw_payload.get("batch_name") == BATCH_NAME
        )
    )


def classify_disclosure_fast(
    service: DartDisclosureAnalysisService,
    disclosure: dict[str, Any],
    cached: dict[str, Any] | None,
) -> str:
    cached_version = ((cached or {}).get("raw_payload") or {}).get("analysis_version")
    if cached and cached_version == DART_ANALYSIS_VERSION and cached.get("sentiment"):
        return str(cached.get("sentiment") or "unknown")
    analysis = service._analyze(disclosure, "", "TITLE_ONLY", "")
    return str(analysis.get("sentiment") or "unknown")


def build_candidate_rows(
    service: DartDisclosureAnalysisService,
    disclosures: list[dict[str, Any]],
    analysis_map: dict[str, dict[str, Any]],
    skip_existing_ai: bool,
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    counts = {"positive": 0, "negative": 0, "caution": 0, "info": 0, "unknown": 0}
    candidates: list[dict[str, Any]] = []
    skipped_existing = 0
    skipped_etf = 0

    for disclosure in disclosures:
        rcept_no = str(disclosure.get("rcept_no") or "").strip()
        cached = analysis_map.get(rcept_no)
        if skip_existing_ai and is_existing_ai_analysis(cached):
            skipped_existing += 1
            continue
        if maybe_contains_etf_keyword(disclosure):
            skipped_etf += 1
            continue
        sentiment = classify_disclosure_fast(service, disclosure, cached)
        if sentiment not in counts:
            sentiment = "unknown"
        counts[sentiment] += 1
        if sentiment in AI_SENTIMENTS:
            candidates.append(disclosure)

    return candidates, {**counts, "skipped_existing_ai": skipped_existing, "skipped_etf": skipped_etf}


def count_sentiments_only(
    service: DartDisclosureAnalysisService,
    symbols: list[str],
    disclosure_limit: int,
    skip_existing_ai: bool,
) -> dict[str, Any]:
    disclosures = collect_disclosures(service, symbols, disclosure_limit)
    rcept_nos = [str(row.get("rcept_no") or "").strip() for row in disclosures]
    analysis_map = fetch_analysis_map(service, rcept_nos)
    candidates, counts = build_candidate_rows(service, disclosures, analysis_map, skip_existing_ai)
    return {
        "symbols": symbols,
        "checked": len(disclosures),
        "cached_count": len(analysis_map),
        "sentiment_counts": {
            "positive": counts["positive"],
            "negative": counts["negative"],
            "caution": counts["caution"],
            "info": counts["info"],
            "unknown": counts["unknown"],
        },
        "skipped_existing_ai": counts["skipped_existing_ai"],
        "skipped_etf": counts["skipped_etf"],
        "ai_candidate_count": len(candidates),
    }


def analyze_without_ai(service: DartDisclosureAnalysisService, disclosure: dict[str, Any]) -> dict[str, Any]:
    rcept_no = str(disclosure.get("rcept_no") or "").strip()
    detail_text = ""
    detail_source = "TITLE_ONLY"
    detail_error = ""
    if service.api_key:
        try:
            detail_text = service._fetch_document_text(rcept_no)
            detail_source = "OPENDART_DOCUMENT" if detail_text else "TITLE_ONLY"
        except Exception as error:
            detail_error = str(error)
    analysis = service._analyze(disclosure, detail_text, detail_source, detail_error)
    return {
        "analysis": analysis,
        "detail_text": detail_text,
    }


def refine_with_retry(
    service: DartDisclosureAnalysisService,
    analysis: dict[str, Any],
    disclosure: dict[str, Any],
    detail_text: str,
    retry_count: int,
    retry_sleep_seconds: int,
) -> dict[str, Any]:
    next_analysis = analysis
    for attempt in range(retry_count + 1):
        next_analysis = service._apply_ai_refinement(analysis, disclosure, detail_text)
        error_text = str((next_analysis.get("raw_payload") or {}).get("ai_refinement_error") or "")
        if not error_text:
            return next_analysis
        if "429" not in error_text and "RESOURCE_EXHAUSTED" not in error_text:
            return next_analysis
        if attempt >= retry_count:
            return next_analysis
        wait_seconds = retry_sleep_seconds * (attempt + 1)
        print(f"[retry] 429 감지. {wait_seconds}초 대기 후 재시도합니다. rcept_no={disclosure.get('rcept_no')}")
        time.sleep(wait_seconds)
    return next_analysis


def main() -> int:
    args = build_parser().parse_args()
    os.environ["DART_ANALYSIS_AI_PROVIDER"] = args.provider

    service = DartDisclosureAnalysisService()
    repository = service.repository
    if not repository.is_configured:
        raise SystemExit("Supabase service role 설정이 필요합니다.")
    if args.provider == "gemini" and not service.gemini_api_key:
        raise SystemExit("GEMINI_API_KEY 설정이 필요합니다.")
    if args.cleanup_batch_info:
        deleted = cleanup_batch_info_rows(service)
        print(json.dumps({"cleanup_batch_info": deleted}, ensure_ascii=False, indent=2))
        return 0

    symbols = load_top_domestic_symbols(Path(args.universe_path), args.symbol_limit, args.symbol_offset)
    if args.count_only:
        result = count_sentiments_only(service, symbols, args.disclosure_limit, args.skip_existing_ai)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0

    disclosures = collect_disclosures(service, symbols, args.disclosure_limit)
    rcept_nos = [str(row.get("rcept_no") or "").strip() for row in disclosures]
    analysis_map = fetch_analysis_map(service, rcept_nos)
    candidates, candidate_counts = build_candidate_rows(service, disclosures, analysis_map, args.skip_existing_ai)
    total_candidates = len(candidates)
    start = max(args.candidate_offset, 0)
    end = None if args.candidate_limit <= 0 else start + args.candidate_limit
    selected_candidates = candidates[start:end]

    result = {
        "symbols": symbols,
        "checked": len(disclosures),
        "candidate_total": total_candidates,
        "candidate_offset": start,
        "candidate_limit": args.candidate_limit,
        "selected": len(selected_candidates),
        "ai_saved": 0,
        "info_skipped": 0,
        "rule_info_saved": 0,
        "etf_skipped": candidate_counts["skipped_etf"],
        "skipped_existing_ai": candidate_counts["skipped_existing_ai"],
        "sentiment_counts": {
            "positive": candidate_counts["positive"],
            "negative": candidate_counts["negative"],
            "caution": candidate_counts["caution"],
            "info": candidate_counts["info"],
            "unknown": candidate_counts["unknown"],
        },
        "failures": [],
    }

    for disclosure in selected_candidates:
        rcept_no = str(disclosure.get("rcept_no") or "").strip()
        symbol = str(disclosure.get("stock_code") or "").strip()
        try:
            analyzed = analyze_without_ai(service, disclosure)
            analysis = analyzed["analysis"]
            detail_text = analyzed["detail_text"]
            sentiment = analysis.get("sentiment")

            if sentiment == "info":
                if args.save_info_rules and not args.dry_run:
                    repository.upsert_disclosure_analysis(analysis)
                    result["rule_info_saved"] += 1
                else:
                    result["info_skipped"] += 1
                continue

            if detail_text:
                analysis = refine_with_retry(
                    service,
                    analysis,
                    disclosure,
                    detail_text,
                    args.retry_count,
                    args.retry_sleep_seconds,
                )
            if analysis.get("sentiment") == "info":
                result["info_skipped"] += 1
                continue

            raw_payload = dict(analysis.get("raw_payload") or {})
            raw_payload.update(
                {
                    "analysis_version": DART_ANALYSIS_VERSION,
                    "batch_name": BATCH_NAME,
                    "batch_provider": args.provider,
                    "batch_processed_at": datetime.now(timezone.utc).isoformat(),
                }
            )
            analysis["raw_payload"] = raw_payload
            analysis["updated_at"] = datetime.now(timezone.utc).isoformat()

            if not args.dry_run:
                repository.upsert_disclosure_analysis(analysis)
            result["ai_saved"] += 1
            print(
                f"[saved] {symbol} {rcept_no} {disclosure.get('report_nm')} "
                f"=> {analysis.get('sentiment_label')} / {analysis.get('headline')}"
            )
        except Exception as error:
            result["failures"].append(
                {
                    "symbol": symbol,
                    "rcept_no": rcept_no,
                    "report_nm": disclosure.get("report_nm"),
                    "error": str(error)[:300],
                }
            )
            print(f"[failed] {symbol} {rcept_no}: {error}")

    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 1 if result["failures"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
