import argparse
import base64
import csv
import json
import math
import os
import sys
import time
from datetime import datetime, timedelta, timezone
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
DEFAULT_UNIVERSE_PATH = PROJECT_ROOT / "ml" / "data" / "reference" / "training_universes.json"


def http_json(
    url: str,
    method: str = "GET",
    headers: dict[str, str] | None = None,
    params: dict[str, Any] | None = None,
    data: dict[str, Any] | None = None,
    timeout: int = 15,
    retry: int = 0,
    retry_wait_seconds: float = 60.0,
) -> Any:
    request_url = url
    if params:
        request_url = f"{url}?{urlencode(params)}"

    body = None
    request_headers = headers.copy() if headers else {}
    if data is not None:
        body = urlencode(data).encode("utf-8")
        request_headers.setdefault("Content-Type", "application/x-www-form-urlencoded")

    last_error: Exception | None = None
    for attempt in range(retry + 1):
        request = Request(request_url, data=body, headers=request_headers, method=method)
        try:
            with urlopen(request, timeout=timeout) as response:
                raw = response.read().decode("utf-8")
                return json.loads(raw)
        except HTTPError as error:
            raw = error.read().decode("utf-8")
            last_error = RuntimeError(f"HTTP {error.code}: {raw}")
            if error.code == 429 and attempt < retry:
                wait_seconds = retry_wait_seconds * (attempt + 1)
                print(
                    f"요청 한도 초과로 {wait_seconds:.1f}초 대기 후 재시도합니다. ({attempt + 1}/{retry})",
                    file=sys.stderr,
                )
                time.sleep(wait_seconds)
                continue
            raise last_error from error
    if last_error:
        raise last_error
    raise RuntimeError("알 수 없는 HTTP 요청 실패입니다.")


def parse_symbols(symbols: str) -> list[str]:
    return [symbol.strip().upper() for symbol in symbols.split(",") if symbol.strip()]


def load_symbols_from_file(path: Path) -> list[str]:
    if not path.exists():
        raise FileNotFoundError(f"심볼 파일이 없습니다: {path}")
    raw_text = path.read_text(encoding="utf-8")
    if path.suffix.lower() == ".json":
        payload = json.loads(raw_text)
        if isinstance(payload, list):
            return [str(item).upper() for item in payload]
        raise ValueError("JSON 심볼 파일은 배열 형태여야 합니다.")
    return [line.strip().upper() for line in raw_text.splitlines() if line.strip()]


def load_preset_symbols(preset_name: str, universe_path: Path) -> list[str]:
    if not universe_path.exists():
        raise FileNotFoundError(f"유니버스 파일이 없습니다: {universe_path}")
    payload = json.loads(universe_path.read_text(encoding="utf-8"))
    preset = payload.get(preset_name)
    if not preset or not isinstance(preset, list):
        raise ValueError(f"유니버스 프리셋을 찾을 수 없습니다: {preset_name}")
    return [str(symbol).upper() for symbol in preset]


def ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def deduplicate_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    unique_rows: dict[tuple[str, str, str], dict[str, Any]] = {}
    for row in rows:
        key = (str(row.get("exchange", "")), str(row.get("symbol", "")), str(row.get("date", "")))
        unique_rows[key] = row
    return sorted(unique_rows.values(), key=lambda row: (row.get("symbol", ""), row.get("date", "")))


def write_rows(path: Path, rows: list[dict[str, Any]], append: bool = False) -> None:
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
    if append and path.exists():
        with path.open("r", newline="", encoding="utf-8") as file:
            existing_rows = list(csv.DictReader(file))
        rows = deduplicate_rows([*existing_rows, *rows])

    with path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def write_failures(path: Path | None, failures: list[dict[str, Any]]) -> None:
    if path is None:
        return
    ensure_parent(path)
    path.write_text(json.dumps(failures, ensure_ascii=False, indent=2), encoding="utf-8")


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
        retry=2,
        retry_wait_seconds=30,
    )
    return payload["access_token"]


def fetch_toss_candles(
    symbols: list[str],
    auth_token: str,
    interval: str,
    count: int,
    sleep_seconds: float = 2.0,
    retry: int = 3,
    retry_wait_seconds: float = 60.0,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    saved_key = fetch_saved_key(auth_token, "TOSS", "REAL")
    access_token = fetch_toss_token(saved_key["access_key"], saved_key["secret_key"])

    rows: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    for index, symbol in enumerate(symbols):
        if index > 0 and sleep_seconds > 0:
            time.sleep(sleep_seconds)

        try:
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
                retry=retry,
                retry_wait_seconds=retry_wait_seconds,
            )
            result = payload.get("result", {})
            symbol_rows = 0
            for candle in result.get("candles", []):
                currency = candle.get("currency") or ("USD" if symbol.isalpha() else "KRW")
                rows.append(
                    {
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
                    }
                )
                symbol_rows += 1
            if symbol_rows == 0:
                failures.append({"symbol": symbol, "reason": "empty-candles"})
        except Exception as error:
            failures.append({"symbol": symbol, "reason": str(error)})

    return sorted(rows, key=lambda row: (row["symbol"], row["date"])), failures


def fetch_binance_klines(
    symbols: list[str],
    interval: str,
    limit: int,
    sleep_seconds: float = 0.2,
    retry: int = 2,
    retry_wait_seconds: float = 10.0,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    rows: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    for index, symbol in enumerate(symbols):
        if index > 0 and sleep_seconds > 0:
            time.sleep(sleep_seconds)

        try:
            payload = http_json(
                "https://api.binance.com/api/v3/klines",
                params={"symbol": symbol, "interval": interval, "limit": min(limit, 1000)},
                timeout=15,
                retry=retry,
                retry_wait_seconds=retry_wait_seconds,
            )
            if not payload:
                failures.append({"symbol": symbol, "reason": "empty-candles"})
                continue

            for item in payload:
                candle_time = datetime.fromtimestamp(item[0] / 1000, tz=timezone.utc).isoformat()
                rows.append(
                    {
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
                    }
                )
        except Exception as error:
            failures.append({"symbol": symbol, "reason": str(error)})

    return sorted(rows, key=lambda row: (row["symbol"], row["date"])), failures


def fetch_macro_indices(count: int) -> list[dict[str, Any]]:
    import pandas as pd
    import yfinance as yf

    days_to_fetch = count * 2
    start_date = (datetime.now(timezone.utc) - timedelta(days=days_to_fetch)).strftime("%Y-%m-%d")
    tickers = {
        "KOSPI": "^KS11",
        "KOSDAQ": "^KQ11",
        "NASDAQ": "^IXIC",
        "USDKRW": "USDKRW=X",
    }

    rows: list[dict[str, Any]] = []
    for name, ticker in tickers.items():
        try:
            print(f"yfinance에서 {name} ({ticker}) 데이터를 수집 중...", file=sys.stderr)
            df = yf.download(ticker, start=start_date, progress=False)
            if df.empty:
                continue
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)
            df = df.reset_index()
            df["Date"] = pd.to_datetime(df["Date"])
            for _, row in df.iterrows():
                candle_date = row["Date"].strftime("%Y-%m-%d %H:%M:%S")
                volume = float(row["Volume"]) if "Volume" in row and not pd.isna(row["Volume"]) else 0.0
                rows.append(
                    {
                        "exchange": "YAHOO",
                        "asset_type": "MACRO",
                        "market_country": "KR" if name in ("KOSPI", "KOSDAQ") else "US",
                        "currency": "KRW" if name != "NASDAQ" else "USD",
                        "symbol": name,
                        "date": candle_date,
                        "open": float(row["Open"]),
                        "high": float(row["High"]),
                        "low": float(row["Low"]),
                        "close": float(row["Close"]),
                        "volume": volume,
                    }
                )
        except Exception as error:
            print(f"yfinance 수집 에러 ({name}): {str(error)}", file=sys.stderr)

    return sorted(rows, key=lambda row: (row["symbol"], row["date"]))


def main() -> None:
    parser = argparse.ArgumentParser(description="학습용 캔들 CSV를 생성합니다.")
    parser.add_argument("--asset-type", choices=["STOCK", "CRYPTO"], required=True)
    parser.add_argument("--exchange", choices=["TOSS", "BINANCE"], required=True)
    parser.add_argument("--symbols", default=None, help="쉼표로 구분한 심볼 목록")
    parser.add_argument("--symbols-file", default=None, help="줄바꿈 또는 JSON 배열 형식의 심볼 파일")
    parser.add_argument("--preset", default=None, help="미리 정의된 유니버스 프리셋 이름")
    parser.add_argument("--universe-file", default=str(DEFAULT_UNIVERSE_PATH), help="유니버스 프리셋 JSON 파일")
    parser.add_argument("--interval", default=None, help="Toss: 1d/1m, Binance: 1h/4h/1d 등")
    parser.add_argument("--count", type=int, default=200)
    parser.add_argument("--auth-token", default=None, help="저장된 Toss API 키 조회용 Supabase JWT")
    parser.add_argument("--output", default=None)
    parser.add_argument("--sleep-seconds", type=float, default=None, help="종목별 요청 사이 대기 초")
    parser.add_argument("--retry", type=int, default=None, help="HTTP 429 재시도 횟수")
    parser.add_argument("--retry-wait-seconds", type=float, default=None, help="HTTP 429 재시도 기본 대기 초")
    parser.add_argument("--append", action="store_true", help="기존 CSV에 병합 저장하고 중복 행을 제거합니다.")
    parser.add_argument("--include-macro", action="store_true", help="KOSPI, NASDAQ, 환율 등 거시 지표 캔들을 함께 다운로드합니다.")
    parser.add_argument("--chunk-size", type=int, default=None, help="심볼 목록을 나눠서 수집할 때 청크 크기")
    parser.add_argument("--chunk-index", type=int, default=1, help="1부터 시작하는 청크 번호")
    parser.add_argument("--failure-output", default=None, help="실패 심볼 요약 JSON 경로")
    args = parser.parse_args()

    symbols: list[str] = []
    if args.symbols:
        symbols.extend(parse_symbols(args.symbols))
    if args.symbols_file:
        symbols.extend(load_symbols_from_file(Path(args.symbols_file)))
    if args.preset:
        symbols.extend(load_preset_symbols(args.preset, Path(args.universe_file)))
    symbols = list(dict.fromkeys(symbols))

    if not symbols:
        raise ValueError("수집할 심볼이 없습니다. --symbols, --symbols-file, --preset 중 하나를 지정하세요.")

    if args.chunk_size and args.chunk_size > 0:
        total_chunks = int(math.ceil(len(symbols) / args.chunk_size))
        chunk_index = min(max(1, args.chunk_index), total_chunks)
        start = (chunk_index - 1) * args.chunk_size
        end = start + args.chunk_size
        symbols = symbols[start:end]
        print(f"청크 수집: {chunk_index}/{total_chunks} ({len(symbols)} symbols)")

    if args.include_macro:
        macro_output = PROJECT_ROOT / "ml" / "data" / "raw" / "macro_indices.csv"
        print("매크로 지수(KOSPI, NASDAQ, 환율 등) 수집을 시작합니다...")
        macro_rows = fetch_macro_indices(args.count)
        write_rows(macro_output, macro_rows, append=args.append)
        print(f"매크로 지수 CSV 생성 완료: {macro_output} ({len(macro_rows)} 행)")

    if args.exchange == "TOSS":
        if args.asset_type != "STOCK":
            raise ValueError("TOSS 수집은 STOCK asset-type만 지원합니다.")
        if not args.auth_token:
            raise ValueError("TOSS 수집에는 --auth-token Supabase JWT가 필요합니다.")
        interval = args.interval or "1d"
        output = Path(args.output or PROJECT_ROOT / "ml" / "data" / "raw" / "stock_candles.csv")
        rows, failures = fetch_toss_candles(
            symbols,
            args.auth_token,
            interval,
            args.count,
            sleep_seconds=args.sleep_seconds if args.sleep_seconds is not None else 2.0,
            retry=args.retry if args.retry is not None else 3,
            retry_wait_seconds=args.retry_wait_seconds if args.retry_wait_seconds is not None else 60.0,
        )
    elif args.exchange == "BINANCE":
        if args.asset_type != "CRYPTO":
            raise ValueError("BINANCE 수집은 CRYPTO asset-type만 지원합니다.")
        interval = args.interval or "1h"
        output = Path(args.output or PROJECT_ROOT / "ml" / "data" / "raw" / "crypto_candles.csv")
        rows, failures = fetch_binance_klines(
            symbols,
            interval,
            args.count,
            sleep_seconds=args.sleep_seconds if args.sleep_seconds is not None else 0.2,
            retry=args.retry if args.retry is not None else 2,
            retry_wait_seconds=args.retry_wait_seconds if args.retry_wait_seconds is not None else 10.0,
        )
    else:
        raise ValueError(f"지원하지 않는 거래소입니다: {args.exchange}")

    write_rows(output, rows, append=args.append)
    failure_output = Path(args.failure_output) if args.failure_output else None
    write_failures(failure_output, failures)
    print(f"CSV 생성 완료: {output}")
    print(f"행 수: {len(rows):,}")
    print(f"실패 심볼 수: {len(failures):,}")
    if failure_output:
        print(f"실패 요약 저장 완료: {failure_output}")


if __name__ == "__main__":
    main()
