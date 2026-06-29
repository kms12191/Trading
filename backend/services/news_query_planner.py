import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from backend.services.symbol_metadata import SYMBOL_METADATA


@dataclass(frozen=True)
class NewsQuery:
    provider: str
    query_key: str
    query_text: str
    category: str
    market: str
    priority: int
    symbol: str = ""
    company_name: str = ""
    reason: str = ""


class NewsQueryPlanner:
    def __init__(self, repository: Any) -> None:
        self.repository = repository
        self.daily_naver_budget = self._env_int("NEWS_NAVER_DAILY_QUERY_BUDGET", 2000)
        self.max_queries_per_run = self._env_int("NEWS_MAX_QUERIES_PER_RUN", 30)
        self.dynamic_symbols_per_run = self._env_int("NEWS_DYNAMIC_SYMBOLS_PER_RUN", 5)
        self.static_symbol_queries_per_run = self._env_int("NEWS_STATIC_SYMBOLS_PER_RUN", 8)
        self.query_cooldown_minutes = self._env_int("NEWS_QUERY_COOLDOWN_MINUTES", 30)

    def build_plan(self, include_naver: bool, include_finnhub: bool) -> tuple[list[NewsQuery], list[dict[str, Any]]]:
        candidates: list[NewsQuery] = []
        skipped: list[dict[str, Any]] = []

        if include_naver:
            candidates.extend(self._static_naver_queries())
            candidates.extend(self._static_symbol_naver_queries())
            candidates.extend(self._dynamic_naver_queries())

        if include_finnhub:
            candidates.extend(self._finnhub_queries())

        ordered = sorted(candidates, key=lambda item: (item.priority, item.query_key))
        selected: list[NewsQuery] = []
        naver_used_today = self.repository.count_fetch_requests(
            source="NAVER",
            since=self._start_of_today_utc(),
        )
        recent_keys = set(
            self.repository.list_recent_query_keys(
                since=datetime.now(timezone.utc) - timedelta(minutes=self.query_cooldown_minutes),
            )
        )

        naver_calls_this_run = 0
        for query in ordered:
            if query.query_key in recent_keys:
                skipped.append(self._skip(query, "COOLDOWN"))
                continue

            if query.provider == "NAVER":
                if naver_used_today + naver_calls_this_run >= self.daily_naver_budget:
                    skipped.append(self._skip(query, "DAILY_BUDGET_EXCEEDED"))
                    continue
                if naver_calls_this_run >= self.max_queries_per_run:
                    skipped.append(self._skip(query, "RUN_LIMIT_EXCEEDED"))
                    continue
                naver_calls_this_run += 1

            selected.append(query)

        return selected, skipped

    def _static_naver_queries(self) -> list[NewsQuery]:
        groups = [
            ("market", 10, ["코스피", "코스닥", "증시", "환율", "금리"]),
            ("macro", 20, ["인플레이션", "FOMC", "연준", "미국 국채"]),
            ("sentiment", 30, ["외국인 순매수", "기관 순매수", "공매도", "신용융자"]),
            ("sector", 40, ["반도체", "이차전지", "배터리", "바이오"]),
        ]
        queries: list[NewsQuery] = []
        for category, priority, keywords in groups:
            for keyword in keywords:
                queries.append(
                    NewsQuery(
                        provider="NAVER",
                        query_key=f"naver:{category}:{keyword}",
                        query_text=keyword,
                        category=category,
                        market="DOMESTIC",
                        priority=priority,
                        company_name=keyword,
                        reason="static_keyword",
                    )
                )
        return queries

    def _static_symbol_naver_queries(self) -> list[NewsQuery]:
        configured_symbols = [
            symbol.strip().upper()
            for symbol in os.getenv(
                "NEWS_STATIC_SYMBOLS",
                "005930,000660,035420,068270,AAPL,MSFT,NVDA,AMD,AVGO,TSLA",
            ).split(",")
            if symbol.strip()
        ]
        variants = [
            ("headline", ""),
            ("earnings", "실적"),
            ("guidance", "전망"),
            ("contract", "수주"),
            ("disclosure", "공시"),
        ]
        queries: list[NewsQuery] = []
        added = 0
        for symbol in configured_symbols:
            meta = SYMBOL_METADATA.get(symbol, {})
            if meta.get("asset_type") != "STOCK":
                continue
            company_name = str(meta.get("display_name") or symbol).strip()
            market = "GLOBAL" if str(meta.get("market") or "").upper() == "US" else "DOMESTIC"
            for variant_index, (variant_key, suffix) in enumerate(variants):
                query_text = company_name if not suffix else f"{company_name} {suffix}"
                queries.append(
                    NewsQuery(
                        provider="NAVER",
                        query_key=f"naver:static-symbol:{symbol}:{variant_key}",
                        query_text=query_text,
                        category="symbol",
                        market=market,
                        priority=45 + added,
                        symbol=symbol,
                        company_name=company_name,
                        reason="static_symbol",
                    )
                )
            added += 1
            if added >= self.static_symbol_queries_per_run:
                break
        return queries

    def _dynamic_naver_queries(self) -> list[NewsQuery]:
        symbols = self.repository.list_watchlist_symbols(limit=self.dynamic_symbols_per_run)
        variants = [
            ("headline", ""),
            ("earnings", "실적"),
            ("disclosure", "공시"),
            ("guidance", "전망"),
            ("contract", "수주"),
        ]
        queries: list[NewsQuery] = []
        for index, item in enumerate(symbols):
            company_name = (item.get("name") or item.get("company_name") or item.get("symbol") or "").strip()
            symbol = (item.get("symbol") or "").strip().upper()
            if not company_name:
                continue

            market = str(item.get("market_country") or item.get("exchange") or "").upper()
            query_market = "GLOBAL" if market == "US" else "DOMESTIC"
            for variant_offset, (variant_key, suffix) in enumerate(variants):
                query_text = company_name if not suffix else f"{company_name} {suffix}"
                queries.append(
                    NewsQuery(
                        provider="NAVER",
                        query_key=f"naver:symbol:{symbol or company_name}:{variant_key}",
                        query_text=query_text,
                        category="symbol",
                        market=query_market,
                        priority=60 + (index * 5) + variant_offset,
                        symbol=symbol,
                        company_name=company_name,
                        reason="watchlist_symbol",
                    )
                )
        return queries

    def _finnhub_queries(self) -> list[NewsQuery]:
        symbols = [
            symbol.strip().upper()
            for symbol in os.getenv("NEWS_FINNHUB_SYMBOLS", "AAPL,MSFT,NVDA").split(",")
            if symbol.strip()
        ]
        return [
            NewsQuery(
                provider="FINNHUB",
                query_key=f"finnhub:symbol:{symbol}",
                query_text=symbol,
                category="symbol",
                market="GLOBAL",
                priority=70 + index,
                symbol=symbol,
                company_name=symbol,
                reason="default_global_symbol",
            )
            for index, symbol in enumerate(symbols)
        ]

    def _skip(self, query: NewsQuery, reason: str) -> dict[str, Any]:
        return {
            "provider": query.provider,
            "query_key": query.query_key,
            "query_text": query.query_text,
            "query_category": query.category,
            "skipped_reason": reason,
        }

    def _start_of_today_utc(self) -> datetime:
        now = datetime.now(timezone.utc)
        return datetime(now.year, now.month, now.day, tzinfo=timezone.utc)

    def _env_int(self, key: str, default: int) -> int:
        try:
            return int(os.getenv(key, str(default)))
        except (TypeError, ValueError):
            return default
