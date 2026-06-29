import argparse
import json
import math
import re
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))

from backend.services.news_repository import NewsRepository
from backend.services.symbol_metadata import SYMBOL_METADATA


NEGATIVE_KEYWORDS = [
    "급락", "하락", "쇼크", "악화", "부진", "감소", "중단", "리콜", "규제", "소송",
    "환불", "적자", "우려", "경고", "위반", "처벌", "조사", "downgrade", "miss",
    "lawsuit", "risk", "probe", "recall", "decline",
]
POSITIVE_KEYWORDS = [
    "급등", "상승", "호조", "서프라이즈", "확대", "성장", "개선", "수주", "계약",
    "흑자", "돌파", "신고가", "buyback", "beat", "upgrade", "partnership",
]
WARNING_KEYWORDS = [
    "경고", "관리종목", "상장폐지", "거래정지", "불성실", "횡령", "배임", "주의",
    "warning", "delisting", "halt", "fraud",
]


EXACT_ALIAS_TO_SYMBOLS: defaultdict[str, set[str]] = defaultdict(set)
TEXT_PATTERNS: list[tuple[re.Pattern[str], str]] = []


def _register_symbol_aliases() -> None:
    for symbol, meta in SYMBOL_METADATA.items():
        normalized_symbol = normalize_symbol(symbol)
        display_name = str(meta.get("display_name") or "").strip()
        aliases = {normalized_symbol}
        if display_name:
            aliases.add(display_name)

        for alias in aliases:
            cleaned_alias = alias.strip()
            if not cleaned_alias:
                continue
            EXACT_ALIAS_TO_SYMBOLS[cleaned_alias.upper()].add(normalized_symbol)
            if re.fullmatch(r"[A-Z][A-Z0-9.\-]{1,9}", cleaned_alias.upper()):
                pattern = re.compile(rf"\b{re.escape(cleaned_alias.upper())}\b", re.IGNORECASE)
            elif len(cleaned_alias) >= 2:
                pattern = re.compile(re.escape(cleaned_alias), re.IGNORECASE)
            else:
                continue
            TEXT_PATTERNS.append((pattern, normalized_symbol))

def normalize_symbol(symbol: object) -> str:
    if symbol is None or (isinstance(symbol, float) and math.isnan(symbol)):
        return ""
    text = str(symbol).strip().upper()
    if text.endswith(".0") and text[:-2].isdigit():
        text = text[:-2]
    if text.isdigit() and len(text) <= 6:
        return text.zfill(6)
    return text


_register_symbol_aliases()


def build_sentiment_score(text: str) -> float:
    lower = (text or "").lower()
    positive_hits = sum(1 for keyword in POSITIVE_KEYWORDS if keyword.lower() in lower)
    negative_hits = sum(1 for keyword in NEGATIVE_KEYWORDS if keyword.lower() in lower)
    total_hits = positive_hits + negative_hits
    if total_hits == 0:
        return 0.0
    return (positive_hits - negative_hits) / total_hits


def keyword_ratio(text: str, keywords: list[str]) -> float:
    lower = (text or "").lower()
    if not lower.strip():
        return 0.0
    hits = sum(1 for keyword in keywords if keyword.lower() in lower)
    return hits / max(len(keywords), 1)


def parse_article_text(article: dict) -> str:
    parts = [
        article.get("title") or "",
        article.get("summary") or "",
        article.get("ai_summary") or "",
    ]
    payload = article.get("raw_payload")
    if isinstance(payload, dict):
        parts.extend(
            [
                str(payload.get("query_text") or ""),
                str(payload.get("query_category") or ""),
                str(payload.get("collection_reason") or ""),
            ]
        )
    return " ".join(part for part in parts if part).strip()


def resolve_alias_to_symbols(value: object) -> list[str]:
    text = str(value or "").strip()
    if not text:
        return []
    normalized = normalize_symbol(text)
    if normalized in SYMBOL_METADATA:
        return [normalized]
    return sorted(EXACT_ALIAS_TO_SYMBOLS.get(text.upper(), set()))


def extract_candidate_symbols(article: dict) -> list[str]:
    candidates: set[str] = set()
    for field_name in ("symbol", "company_name"):
        for symbol in resolve_alias_to_symbols(article.get(field_name)):
            candidates.add(symbol)

    payload = article.get("raw_payload")
    if isinstance(payload, dict):
        for key in ("query_text", "query_key"):
            for symbol in resolve_alias_to_symbols(payload.get(key)):
                candidates.add(symbol)

    article_text = parse_article_text(article).upper()
    for pattern, symbol in TEXT_PATTERNS:
        if pattern.search(article_text):
            candidates.add(symbol)

    return sorted(candidates)


def aggregate_news_features(articles: list[dict], output_path: Path) -> pd.DataFrame:
    rows: list[dict] = []
    per_symbol_days: defaultdict[str, list[tuple[str, int]]] = defaultdict(list)

    grouped: defaultdict[tuple[str, str], list[dict]] = defaultdict(list)
    for article in articles:
        published_at = pd.to_datetime(article.get("published_at"), utc=True, errors="coerce")
        if pd.isna(published_at):
            continue
        date_str = published_at.tz_convert("Asia/Seoul").strftime("%Y-%m-%d 00:00:00")
        symbols = extract_candidate_symbols(article) or ["__ALL__"]
        for symbol in symbols:
            grouped[(symbol, date_str)].append(article)

    for (symbol, date_str), items in grouped.items():
        sentiments = []
        negative_ratios = []
        for item in items:
            text = parse_article_text(item)
            base_sentiment = item.get("sentiment")
            sentiment_score = float(base_sentiment) if isinstance(base_sentiment, (int, float)) else build_sentiment_score(text)
            sentiments.append(sentiment_score)
            negative_ratios.append(keyword_ratio(text, NEGATIVE_KEYWORDS))

        article_count = len(items)
        avg_sentiment = sum(sentiments) / article_count if article_count else 0.0
        avg_negative_ratio = sum(negative_ratios) / article_count if article_count else 0.0
        rows.append(
            {
                "symbol": symbol,
                "date": date_str,
                "news_sentiment": round(avg_sentiment, 6),
                "news_article_count_24h": article_count,
                "negative_keyword_ratio": round(avg_negative_ratio, 6),
            }
        )
        per_symbol_days[symbol].append((date_str, article_count))

    df = pd.DataFrame(rows)
    if df.empty:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(output_path, index=False)
        return df

    burst_values: dict[tuple[str, str], float] = {}
    for symbol, entries in per_symbol_days.items():
        entries = sorted(entries, key=lambda item: item[0])
        counts = pd.Series([count for _, count in entries], dtype=float)
        rolling_mean = counts.rolling(20, min_periods=1).mean()
        rolling_std = counts.rolling(20, min_periods=1).std().replace(0, pd.NA)
        zscores = ((counts - rolling_mean) / rolling_std).astype("Float64").fillna(0.0)
        for (date_str, _), zscore in zip(entries, zscores.tolist()):
            burst_values[(symbol, date_str)] = float(zscore)

    df["news_burst_zscore"] = df.apply(
        lambda row: round(burst_values.get((row["symbol"], row["date"]), 0.0), 6),
        axis=1,
    )
    df = df.sort_values(["symbol", "date"]).reset_index(drop=True)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(output_path, index=False)
    return df


def aggregate_stock_event_features(candles_path: Path, news_features: pd.DataFrame, articles: list[dict], output_path: Path) -> pd.DataFrame:
    candles = pd.read_csv(candles_path)
    candles["symbol"] = candles["symbol"].map(normalize_symbol)
    candles["date"] = pd.to_datetime(candles["date"], errors="coerce")
    candles = candles.dropna(subset=["date"]).copy()
    candles["date"] = candles["date"].dt.strftime("%Y-%m-%d 00:00:00")
    candles["close"] = candles["close"].astype(float)
    candles["volume"] = candles["volume"].astype(float)

    warning_by_day: defaultdict[tuple[str, str], float] = defaultdict(float)
    for article in articles:
        published_at = pd.to_datetime(article.get("published_at"), utc=True, errors="coerce")
        if pd.isna(published_at):
            continue
        date_str = published_at.tz_convert("Asia/Seoul").strftime("%Y-%m-%d 00:00:00")
        text = parse_article_text(article)
        warning_value = 1.0 if keyword_ratio(text, WARNING_KEYWORDS) > 0 else 0.0
        if warning_value <= 0:
            continue
        for symbol in extract_candidate_symbols(article):
            warning_by_day[(symbol, date_str)] = max(
                warning_by_day[(symbol, date_str)],
                warning_value,
            )

    rows: list[pd.DataFrame] = []
    for symbol, group in candles.groupby("symbol", sort=False):
        group = group.sort_values("date").copy()
        turnover_ratio = group["volume"] / group["volume"].rolling(20, min_periods=1).mean().replace(0, pd.NA)
        close_min_20 = group["close"].rolling(20, min_periods=1).min()
        close_max_20 = group["close"].rolling(20, min_periods=1).max()
        band_width = (close_max_20 - close_min_20).replace(0, pd.NA)
        price_limit_proximity = ((group["close"] - close_min_20) / band_width).astype("Float64").fillna(0.5)
        frame = pd.DataFrame(
            {
                "symbol": symbol,
                "date": group["date"],
                "warning_flag": [warning_by_day.get((symbol, date), 0.0) for date in group["date"].tolist()],
                "price_limit_proximity": price_limit_proximity.clip(0.0, 1.0).round(6),
                "turnover_ratio": turnover_ratio.astype("Float64").fillna(1.0).round(6),
                "market_open_flag": 1.0,
            }
        )
        rows.append(frame)

    df = pd.concat(rows, ignore_index=True) if rows else pd.DataFrame(
        columns=["symbol", "date", "warning_flag", "price_limit_proximity", "turnover_ratio", "market_open_flag"]
    )
    df = df.sort_values(["symbol", "date"]).reset_index(drop=True)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(output_path, index=False)
    return df


def fetch_articles(repository: NewsRepository, days: int) -> list[dict]:
    since = datetime.now(timezone.utc) - timedelta(days=days)
    offset = 0
    batch_size = 5000
    articles: list[dict] = []
    while True:
        batch = repository.list_recent_articles_for_ml(since=since, limit=batch_size, offset=offset)
        if not batch:
            break
        for item in batch:
            payload = item.get("raw_payload")
            if isinstance(payload, str):
                try:
                    item["raw_payload"] = json.loads(payload)
                except Exception:
                    item["raw_payload"] = {}
        articles.extend(batch)
        if len(batch) < batch_size:
            break
        offset += batch_size
    return articles


def main() -> None:
    parser = argparse.ArgumentParser(description="Supabase news_articles를 ML raw feature CSV로 변환합니다.")
    parser.add_argument("--days", type=int, default=120, help="최근 며칠치 기사를 집계할지")
    parser.add_argument("--news-output", default="ml/data/raw/news_features.csv")
    parser.add_argument("--stock-event-output", default="ml/data/raw/stock_event_features.csv")
    parser.add_argument("--candles-path", default="ml/data/raw/stock_candles.csv")
    args = parser.parse_args()

    repository = NewsRepository()
    if not repository.is_configured:
        raise RuntimeError("SUPABASE 설정이 없어 news feature export를 실행할 수 없습니다.")

    articles = fetch_articles(repository, args.days)
    news_output_path = (PROJECT_ROOT / args.news_output).resolve()
    stock_event_output_path = (PROJECT_ROOT / args.stock_event_output).resolve()
    candles_path = (PROJECT_ROOT / args.candles_path).resolve()

    news_df = aggregate_news_features(articles, news_output_path)
    stock_event_df = aggregate_stock_event_features(candles_path, news_df, articles, stock_event_output_path)

    print(
        json.dumps(
            {
                "articles": len(articles),
                "news_rows": len(news_df),
                "stock_event_rows": len(stock_event_df),
                "news_output": str(news_output_path),
                "stock_event_output": str(stock_event_output_path),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
