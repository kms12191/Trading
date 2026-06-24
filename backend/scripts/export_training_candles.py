import argparse
import base64
import csv
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))


def load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


load_env_file(PROJECT_ROOT / "backend" / ".env")
load_env_file(PROJECT_ROOT / ".env")


ENCRYPTION_KEY = os.getenv("ENCRYPTION_KEY", "default-dev-encryption-key-32bytes!")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY")


def http_json(
    url: str,
    method: str = "GET",
    headers: dict[str, str] | None = None,
    params: dict[str, Any] | None = None,
    data: dict[str, Any] | None = None,
    timeout: int = 15,
) -> Any:
    request_url = url
    if params:
        request_url = f"{url}?{urlencode(params)}"

    body = None
    request_headers = headers.copy() if headers else {}
    if data is not None:
        body = urlencode(data).encode("utf-8")
        request_headers.setdefault("Content-Type", "application/x-www-form-urlencoded")

    request = Request(request_url, data=body, headers=request_headers, method=method)
    try:
        with urlopen(request, timeout=timeout) as response:
            raw = response.read().decode("utf-8")
            return json.loads(raw)
    except HTTPError as error:
        raw = error.read().decode("utf-8")
        raise RuntimeError(f"HTTP {error.code}: {raw}") from error


def parse_symbols(symbols: str) -> list[str]:
    return [symbol.strip().upper() for symbol in symbols.split(",") if symbol.strip()]


def ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def write_rows(path: Path, rows: list[dict[str, Any]]) -> None:
    ensure_parent(path)
    fieldnames = [
        "exchange",
        "asset_type",
        "market_country",
        "currency",
        "symbol",
        "date",
        "open",
        "high",
        "low",
        "close",
        "volume",
    ]
    with path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def get_user_id_from_token(auth_token: str) -> str:
    parts = auth_token.split(".")
    if len(parts) < 2:
        raise ValueError("Supabase JWT 형식이 올바르지 않습니다.")
    payload_segment = parts[1]
    padding = "=" * (-len(payload_segment) % 4)
    payload = json.loads(base64.urlsafe_b64decode(payload_segment + padding))
    user_id = payload.get("sub")
    if not user_id:
        raise ValueError("Supabase JWT에서 user_id(sub)를 찾을 수 없습니다.")
    return user_id


def fetch_saved_key(auth_token: str, exchange: str, broker_env: str = "REAL") -> dict[str, Any]:
    from backend.utils.crypto_helper import CryptoHelper

    crypto = CryptoHelper(ENCRYPTION_KEY)
    if not SUPABASE_URL or not SUPABASE_ANON_KEY:
        raise ValueError("SUPABASE_URL과 SUPABASE_ANON_KEY 환경 변수가 필요합니다.")

    user_id = get_user_id_from_token(auth_token)
    url = f"{SUPABASE_URL}/rest/v1/user_api_keys"
    headers = {
        "apikey": SUPABASE_ANON_KEY,
        "Authorization": f"Bearer {auth_token}",
        "Content-Type": "application/json",
    }
    params = {
        "user_id": f"eq.{user_id}",
        "exchange": f"eq.{exchange}",
        "broker_env": f"eq.{broker_env}",
        "limit": "1",
    }
    records = http_json(url, headers=headers, params=params, timeout=15)
    if not records:
        raise RuntimeError(f"저장된 {exchange} ({broker_env}) API 키가 없습니다.")

    record = records[0]
    return {
        "access_key": crypto.decrypt(record.get("encrypted_access_key")),
        "secret_key": crypto.decrypt(record.get("encrypted_secret_key")),
        "record": record,
    }


def fetch_toss_token(api_key: str, secret_key: str) -> str:
    payload = http_json(
        "https://openapi.tossinvest.com/oauth2/token",
        method="POST",
        data={
            "grant_type": "client_credentials",
            "client_id": api_key,
            "client_secret": secret_key,
        },
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        timeout=15,
    )
    return payload["access_token"]


def fetch_toss_candles(symbols: list[str], auth_token: str, interval: str, count: int) -> list[dict[str, Any]]:
    saved_key = fetch_saved_key(auth_token, "TOSS", "REAL")
    access_token = fetch_toss_token(saved_key["access_key"], saved_key["secret_key"])

    rows: list[dict[str, Any]] = []
    for symbol in symbols:
        payload = http_json(
            "https://openapi.tossinvest.com/api/v1/candles",
            headers={"Authorization": f"Bearer {access_token}"},
            params={
                "symbol": symbol,
                "interval": interval,
                "count": min(count, 200),
                "adjusted": "true",
            },
            timeout=15,
        )

        result = payload.get("result", {})
        for candle in result.get("candles", []):
            currency = candle.get("currency") or ("USD" if symbol.isalpha() else "KRW")
            rows.append({
                "exchange": "TOSS",
                "asset_type": "STOCK",
                "market_country": "US" if symbol.isalpha() else "KR",
                "currency": currency,
                "symbol": symbol,
                "date": candle.get("timestamp"),
                "open": candle.get("openPrice"),
                "high": candle.get("highPrice"),
                "low": candle.get("lowPrice"),
                "close": candle.get("closePrice"),
                "volume": candle.get("volume"),
            })

    return sorted(rows, key=lambda row: (row["symbol"], row["date"]))


def fetch_binance_klines(symbols: list[str], interval: str, limit: int) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for symbol in symbols:
        payload = http_json(
            "https://api.binance.com/api/v3/klines",
            params={"symbol": symbol, "interval": interval, "limit": min(limit, 1000)},
            timeout=15,
        )

        for item in payload:
            candle_time = datetime.fromtimestamp(item[0] / 1000, tz=timezone.utc).isoformat()
            rows.append({
                "exchange": "BINANCE",
                "asset_type": "CRYPTO",
                "market_country": "",
                "currency": "USDT",
                "symbol": symbol,
                "date": candle_time,
                "open": item[1],
                "high": item[2],
                "low": item[3],
                "close": item[4],
                "volume": item[5],
            })

    return sorted(rows, key=lambda row: (row["symbol"], row["date"]))


def main() -> None:
    parser = argparse.ArgumentParser(description="학습용 캔들 CSV를 생성합니다.")
    parser.add_argument("--asset-type", choices=["STOCK", "CRYPTO"], required=True)
    parser.add_argument("--exchange", choices=["TOSS", "BINANCE"], required=True)
    parser.add_argument("--symbols", required=True, help="쉼표로 구분한 심볼 목록")
    parser.add_argument("--interval", default=None, help="Toss: 1d/1m, Binance: 1h/4h/1d 등")
    parser.add_argument("--count", type=int, default=200)
    parser.add_argument("--auth-token", default=None, help="저장된 Toss API 키 조회용 Supabase JWT")
    parser.add_argument("--output", default=None)
    args = parser.parse_args()

    symbols = parse_symbols(args.symbols)
    if not symbols:
        raise ValueError("수집할 심볼이 없습니다.")

    if args.exchange == "TOSS":
        if args.asset_type != "STOCK":
            raise ValueError("TOSS 수집은 STOCK asset-type만 지원합니다.")
        if not args.auth_token:
            raise ValueError("TOSS 수집에는 --auth-token Supabase JWT가 필요합니다.")
        interval = args.interval or "1d"
        output = Path(args.output or PROJECT_ROOT / "ml" / "data" / "raw" / "stock_candles.csv")
        rows = fetch_toss_candles(symbols, args.auth_token, interval, args.count)
    elif args.exchange == "BINANCE":
        if args.asset_type != "CRYPTO":
            raise ValueError("BINANCE 수집은 CRYPTO asset-type만 지원합니다.")
        interval = args.interval or "1h"
        output = Path(args.output or PROJECT_ROOT / "ml" / "data" / "raw" / "crypto_candles.csv")
        rows = fetch_binance_klines(symbols, interval, args.count)
    else:
        raise ValueError(f"지원하지 않는 거래소입니다: {args.exchange}")

    write_rows(output, rows)
    print(f"CSV 생성 완료: {output}")
    print(f"행 수: {len(rows):,}")


if __name__ == "__main__":
    main()
