import os
import threading
import time
from datetime import datetime, timedelta, timezone

from backend.services.supabase_client import safe_query_supabase_as_service_role
from backend.services.toss_client import TossClient

KST = timezone(timedelta(hours=9))


def _calendar_session(raw: dict, key: str) -> dict:
    today = raw.get("today") if isinstance(raw, dict) else {}
    integrated = today.get("integrated") if isinstance(today, dict) else {}
    session = integrated.get(key) if isinstance(integrated, dict) else {}
    return session if isinstance(session, dict) else {}


def _normalize_calendar_row(market_country: str, trade_date: str, raw: dict, source: str) -> dict:
    today = raw.get("today") if isinstance(raw, dict) else {}
    regular = _calendar_session(raw, "regularMarket")
    regular_open_at = regular.get("startTime")
    regular_close_at = regular.get("endTime")
    is_open = bool(today and regular_open_at and regular_close_at)
    holiday_name = ""
    if isinstance(today, dict):
        holiday_name = str(today.get("holidayName") or today.get("name") or "").strip()
    if not is_open and not holiday_name:
        holiday_name = "휴장일"
    return {
        "market_country": market_country,
        "trade_date": trade_date,
        "is_open": is_open,
        "holiday_name": holiday_name or None,
        "regular_open_at": regular_open_at,
        "regular_close_at": regular_close_at,
        "source": source,
        "raw_payload": raw,
    }


def _fetch_calendar_row(market_country: str, trade_date: str) -> dict | None:
    rows = safe_query_supabase_as_service_role(
        "market_calendar_days",
        "GET",
        params={
            "market_country": f"eq.{market_country}",
            "trade_date": f"eq.{trade_date}",
            "select": "id",
            "limit": "1",
        },
    ) or []
    return rows[0] if rows else None


def _upsert_calendar_row(row: dict) -> None:
    existing = _fetch_calendar_row(row["market_country"], row["trade_date"])
    if existing and existing.get("id"):
        safe_query_supabase_as_service_role(
            f"market_calendar_days?id=eq.{existing['id']}",
            "PATCH",
            json_data=row,
        )
        return
    safe_query_supabase_as_service_role("market_calendar_days", "POST", json_data=row)


def _build_toss_client(env: str = "REAL") -> TossClient | None:
    client_id = os.getenv("SHARED_TOSS_CLIENT_ID") or os.getenv("TOSS_CLIENT_ID") or os.getenv("TOSS_API_KEY")
    client_secret = os.getenv("SHARED_TOSS_CLIENT_SECRET") or os.getenv("TOSS_CLIENT_SECRET") or os.getenv("TOSS_SECRET_KEY")
    account_seq = os.getenv("SHARED_TOSS_ACCOUNT_SEQ") or os.getenv("TOSS_ACCOUNT_SEQ")
    if not (client_id and client_secret):
        return None
    return TossClient(
        client_id=client_id,
        client_secret=client_secret,
        account_seq=account_seq,
        env=env,
        user_id="market_calendar_scheduler",
    )


def sync_today_market_calendars(env: str = "REAL") -> dict:
    client = _build_toss_client(env)
    if not client:
        return {"synced": 0, "errors": ["Toss 공용 API 키가 없어 캘린더 적재를 건너뜁니다."]}

    trade_date = datetime.now(KST).date().isoformat()
    synced = 0
    errors = []
    for market_country in ("KR", "US"):
        try:
            raw = client.get_market_calendar(market_country)
            row = _normalize_calendar_row(market_country, trade_date, raw, "TOSS")
            _upsert_calendar_row(row)
            synced += 1
        except Exception as error:
            errors.append(f"{market_country}: {error}")
    return {"synced": synced, "errors": errors}


def start_market_calendar_scheduler(
    enabled: bool,
    interval_seconds: int = 86400,
    env: str = "REAL",
) -> None:
    if not enabled:
        return

    def _loop() -> None:
        while True:
            result = sync_today_market_calendars(env)
            print(
                "[MarketCalendarScheduler] "
                f"캘린더 적재 완료: {result.get('synced', 0)}건, "
                f"오류 {len(result.get('errors') or [])}건"
            )
            time.sleep(interval_seconds)

    thread = threading.Thread(target=_loop, daemon=True)
    thread.start()
