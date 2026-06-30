import os
import json
import time
import uuid
import random
import logging
import requests
from pathlib import Path
from datetime import datetime, timedelta, timezone
from backend.services.exchange_client import ExchangeClient

logger = logging.getLogger(__name__)

# 전역 레이트 리밋 상태 공유
TOSS_LIMITS = {}

KST = timezone(timedelta(hours=9))

def _floor_kst_bucket_timestamp(timestamp: int, interval_minutes: int) -> int:
    """
    유닉스 타임스탬프를 한국시간 기준 캔들 시작 시각으로 내림 정렬합니다.
    """
    dt_kst = datetime.fromtimestamp(timestamp, tz=KST)
    bucket_minute = (dt_kst.minute // interval_minutes) * interval_minutes
    bucket_dt = dt_kst.replace(minute=bucket_minute, second=0, microsecond=0)
    return int(bucket_dt.timestamp())

class TossClient(ExchangeClient):
    """
    토스증권 Open API 연동 및 연결 검증을 담당하는 클라이언트 클래스입니다.
    """
    def __init__(self, client_id: str, client_secret: str, account_seq: str = None, env: str = "MOCK", user_id: str | None = None):
        self.client_id = client_id
        self.client_secret = client_secret
        self.account_seq = account_seq
        self.env = env.upper()
        self.base_url = "https://openapi.tossinvest.com"
        self.user_id = user_id
        # 토큰 캐시 상태를 마지막 호출 결과와 함께 보관한다.
        self._last_token_cache_info = {
            "source": "token_cache_service",
            "cacheStatus": "MISS",
            "tokenStatus": "REFRESHED",
            "errorMessage": None,
        }
        self._access_token_cache = {
            "token": None,
            "expired_at": None,
        }

    def _send_request(self, method: str, url: str, **kwargs) -> requests.Response:
        """
        토스 OpenAPI 요청 공통 메소드.
        Rate Limit 트래킹, 서킷 브레이커, 429 지수 백오프/재시도, 401 토큰 갱신을 통합 처리합니다.
        """
        # 그룹 이름 매핑
        path = url.replace(self.base_url, "")
        if "?" in path:
            path = path.split("?")[0]
            
        group = "MARKET_DATA"
        if "oauth2/token" in path:
            group = "AUTH"
        elif "api/v1/accounts" in path:
            group = "ACCOUNT"
        elif "api/v1/holdings" in path:
            group = "ASSET"
        elif "api/v1/stocks" in path:
            group = "STOCK"
        elif "api/v1/exchange-rate" in path or "api/v1/market-calendar" in path:
            group = "MARKET_INFO"
        elif "api/v1/candles" in path:
            group = "MARKET_DATA_CHART"
        elif "api/v1/orderbook" in path or "api/v1/prices" in path or "api/v1/trades" in path or "api/v1/price-limits" in path:
            group = "MARKET_DATA"
        elif "api/v1/orders" in path:
            if method.upper() == "POST":
                group = "ORDER"
            else:
                group = "ORDER_HISTORY"
        elif "api/v1/buying-power" in path or "api/v1/sellable-quantity" in path or "api/v1/commissions" in path:
            group = "ORDER_INFO"

        now = time.time()
        group_status = TOSS_LIMITS.setdefault(group, {
            "remaining": 100,
            "reset": 0.0,
            "blocked_until": 0.0,
            "limit": 5
        })

        # 1. 서킷 브레이커 (429 차단 체크)
        if group_status["blocked_until"] > now:
            wait_time = group_status["blocked_until"] - now
            logger.warning(f"[Toss Client] Rate Limit 서킷 브레이커 작동. 그룹: {group}, {wait_time:.2f}초간 차단됨.")
            raise Exception(f"Toss Rate Limit Exceeded (Circuit Breaker active for group {group}). Blocked for {wait_time:.2f}s")

        # 2. Self-Throttling (남은 할당량이 0 혹은 1로 낮고 리셋 주기가 남아있는 경우 짧은 대기 유도)
        if group_status["remaining"] <= 1 and group_status["reset"] > now:
            throttle_wait = min(group_status["reset"] - now, 0.5)
            if throttle_wait > 0.01:
                logger.info(f"[Toss Client] Self-Throttling 활성화. {throttle_wait:.2f}초간 지연합니다.")
                time.sleep(throttle_wait)

        max_attempts = 2
        refreshed_once = False
        last_exception = None
        for attempt in range(max_attempts):
            try:
                headers = dict(kwargs.get("headers") or {})
                auth_header = headers.get("Authorization")
                if isinstance(auth_header, str) and auth_header.startswith("Bearer "):
                    headers["Authorization"] = f"Bearer {self._get_cached_token()}"
                elif group != "AUTH":
                    headers["Authorization"] = f"Bearer {self._get_cached_token()}"
                kwargs["headers"] = headers

                masked_auth = "NONE"
                if isinstance(headers.get("Authorization"), str) and headers["Authorization"].startswith("Bearer "):
                    token_value = headers["Authorization"].split(" ", 1)[1].strip()
                    masked_auth = f"Bearer ***{token_value[-6:]}" if len(token_value) > 6 else "Bearer ***"
                logger.debug(
                    "[Toss Client][request] method=%s path=%s auth_present=%s auth_value=%s attempt=%s",
                    method.upper(),
                    path,
                    bool(headers.get("Authorization")),
                    masked_auth,
                    attempt + 1,
                )

                res = requests.request(method, url, **kwargs)

                # Rate Limit 헤더 업데이트
                limit_hdr = res.headers.get("X-RateLimit-Limit")
                rem_hdr = res.headers.get("X-RateLimit-Remaining")
                reset_hdr = res.headers.get("X-RateLimit-Reset")

                if limit_hdr is not None:
                    group_status["limit"] = int(limit_hdr)
                if rem_hdr is not None:
                    group_status["remaining"] = int(rem_hdr)
                if reset_hdr is not None:
                    group_status["reset"] = time.time() + float(reset_hdr)

                # 429 Too Many Requests 응답 처리
                if res.status_code == 429:
                    retry_after = float(res.headers.get("Retry-After", 1.0))
                    logger.warning(f"[Toss Client] 429 Too Many Requests 수신. 그룹: {group}, Retry-After: {retry_after}초")
                    group_status["blocked_until"] = time.time() + retry_after

                    if attempt < max_attempts - 1:
                        sleep_dur = retry_after + random.uniform(0.1, 0.5)
                        logger.info(f"[Toss Client] {sleep_dur:.2f}초 후 재시도합니다... (시도 {attempt + 1}/{max_attempts})")
                        time.sleep(sleep_dur)
                        continue
                    else:
                        raise Exception(f"Toss Rate Limit Exceeded (429) after {max_attempts} attempts. Group: {group}")

                # 401 Unauthorized 및 토큰 유효성 체크
                is_unauthorized = False
                if res.status_code == 401:
                    is_unauthorized = True
                else:
                    try:
                        data = res.json()
                        if isinstance(data, dict) and "error" in data:
                            err_code = data["error"].get("code", "")
                            if err_code in ("invalid-token", "expired-token", "login-user-not-found"):
                                is_unauthorized = True
                    except Exception:
                        pass

                if is_unauthorized:
                    logger.warning(
                        "[Toss Client] 401 Unauthorized 감지. 토큰 1회 재발급 후 재시도합니다. (시도 %s/%s)",
                        attempt + 1,
                        max_attempts,
                    )
                    if not refreshed_once:
                        refreshed_once = True
                        self._clear_token_cache()
                        continue

                return res

            except requests.exceptions.RequestException as e:
                last_exception = e
                if attempt < max_attempts - 1:
                    sleep_dur = 0.5 * (2 ** attempt) + random.uniform(0.1, 0.3)
                    logger.warning(f"[Toss Client] 통신 에러 발생 ({str(e)}), {sleep_dur:.2f}초 후 재시도... (시도 {attempt + 1}/{max_attempts})")
                    time.sleep(sleep_dur)
                else:
                    raise e

        if last_exception:
            raise last_exception
        raise Exception("알 수 없는 에러로 토스 OpenAPI 요청에 실패했습니다.")


    def _clear_token_cache(self):
        """
        DB 캐시 테이블에서 현재 exchange/env에 해당하는 토큰 정보를 강제 만료시킵니다.
        """
        from backend.services.token_cache_service import clear_db_token
        try:
            clear_db_token("TOSS", self.env, self.user_id)
        except Exception:
            pass
        self._access_token_cache = {
            "token": None,
            "expired_at": None,
        }

    def get_token_cache_info(self) -> dict:
        return dict(self._last_token_cache_info)

    def get_access_token(self) -> str:
        # 외부 호출부는 이 메서드만 사용하면 토큰 갱신 세부사항을 몰라도 된다.
        return self._get_cached_token()

    def _get_cached_token(self) -> str:
        """
        Supabase DB의 token_caches 테이블에서 토스 Access Token을 가져옵니다.
        토큰이 만료되었거나 캐시가 없으면 새로 발급을 요청합니다.
        """
        from backend.services.token_cache_service import get_db_token_with_status, set_db_token

        cached_token = self._access_token_cache.get("token")
        cached_expired_at = self._access_token_cache.get("expired_at")
        if cached_token and isinstance(cached_expired_at, datetime):
            if (cached_expired_at - datetime.utcnow()).total_seconds() > 300:
                self._last_token_cache_info = {
                    "source": "memory",
                    "cacheStatus": "HIT",
                    "tokenStatus": "REUSED",
                    "errorMessage": None,
                    "expiredAt": cached_expired_at.isoformat() + "Z",
                }
                return cached_token
        
        # DB에서 유효한 공용 토큰 획득 시도
        cache_state = get_db_token_with_status("TOSS", self.env, self.user_id)
        self._last_token_cache_info = {
            "source": "token_cache_service",
            "cacheStatus": cache_state.get("cache_status", "MISS"),
            "tokenStatus": cache_state.get("token_status", "REFRESHED"),
            "errorMessage": cache_state.get("error_message"),
            "expiredAt": cache_state.get("expired_at"),
        }
        token = cache_state.get("token")
        if token:
            expired_at_raw = cache_state.get("expired_at")
            try:
                cached_expired_at = datetime.fromisoformat(str(expired_at_raw).replace("Z", "+00:00")).replace(tzinfo=None) if expired_at_raw else None
            except Exception:
                cached_expired_at = None
            self._access_token_cache = {
                "token": token,
                "expired_at": cached_expired_at,
            }
            return token

        # 토큰 새로 발급
        token_data = self._request_new_token()
        new_token = token_data["access_token"]
        expires_in = int(token_data.get("expires_in", 86400))

        # DB 캐시 테이블에 신규 토큰 저장 (Upsert)
        try:
            set_db_token("TOSS", self.env, new_token, expires_in, self.user_id)
        except Exception:
            pass
        self._access_token_cache = {
            "token": new_token,
            "expired_at": datetime.utcnow() + timedelta(seconds=expires_in),
        }
        self._last_token_cache_info = {
            "source": "token_cache_service",
            "cacheStatus": "MISS",
            "tokenStatus": "REFRESHED",
            "errorMessage": cache_state.get("error_message"),
            "expiredAt": (datetime.utcnow() + timedelta(seconds=expires_in)).isoformat() + "Z",
        }

        return new_token


    def _request_new_token(self) -> dict:
        """
        토스 API 서버로부터 새로운 OAuth2 액세스 토큰을 발급받습니다.
        """
        url = f"{self.base_url}/oauth2/token"
        payload = {
            "grant_type": "client_credentials",
            "client_id": self.client_id,
            "client_secret": self.client_secret
        }
        headers = {
            "Content-Type": "application/x-www-form-urlencoded"
        }
        res = self._send_request("POST", url, data=payload, headers=headers)
        if res.status_code != 200:
            err_data = {}
            try:
                err_data = res.json()
            except Exception:
                pass
            err_msg = err_data.get("error_description") or err_data.get("error") or res.text
            raise Exception(f"토스 토큰 발급 실패: {err_msg}")
        return res.json()

    def _market_index_symbol(self, definition: dict) -> str:
        # Toss API가 요구하는 심볼 표기와 내부 심볼 표기를 맞춘다.
        return {
            "USDKRW": "USDKRW",
            "KOSPI": "KOSPI",
            "KOSDAQ": "KOSDAQ",
            "NASDAQ100_F": "NDX",
            "SP500": "SPX",
        }.get(definition["symbol"], definition.get("code") or definition["symbol"])

    def _market_index_symbol_candidates(self, definition: dict) -> list[str]:
        symbol = str(definition.get("symbol") or "").upper()
        code = str(definition.get("code") or "").upper()
        candidates_by_symbol = {
            "USDKRW": ["USDKRW"],
            "KOSPI": ["KS11", "^KS11", "KOSPI"],
            "KOSDAQ": ["KQ11", "^KQ11", "KOSDAQ"],
            "NASDAQ100_F": ["NDX", "^NDX"],
            "SP500": ["SPX", "^GSPC"],
        }
        candidates = candidates_by_symbol.get(symbol, [])
        if code and code not in candidates:
            candidates.append(code)
        if symbol and symbol not in candidates:
            candidates.append(symbol)
        return [candidate for candidate in dict.fromkeys(candidates) if candidate]

    def _fetch_price_payload(self, symbol: str) -> dict:
        # price 엔드포인트와 복수형 파라미터를 모두 시도해 응답 차이를 흡수한다.
        url = f"{self.base_url}/api/v1/prices"
        headers = {
            "Authorization": f"Bearer {self._get_cached_token()}",
            "Content-Type": "application/json",
        }
        response = self._send_request("GET", url, headers=headers, params={"symbol": symbol}, timeout=15)
        if response.status_code != 200:
            response = self._send_request("GET", url, headers=headers, params={"symbols": symbol}, timeout=15)
        if response.status_code != 200:
            raise RuntimeError(f"Toss price lookup failed for {symbol}: {response.text}")

        payload = response.json()
        if isinstance(payload, dict) and payload.get("error"):
            err = payload["error"]
            raise RuntimeError(f"Toss price lookup failed for {symbol}: {err.get('message') or err}")

        result = payload.get("result", {})
        if not result or not isinstance(result, dict):
            for key in ("output", "data"):
                if isinstance(payload, dict) and payload.get(key):
                    result = payload.get(key)
                    break
        if isinstance(result, list):
            result = result[0] if result else {}
        if not isinstance(result, dict):
            result = {}

        current_price = float(
            result.get("currentPrice")
            or result.get("current_price")
            or result.get("closePrice")
            or result.get("close_price")
            or result.get("price")
            or result.get("lastPrice")
            or result.get("last_price")
            or 0.0
        )
        return {
            "current_price": current_price,
            "result": result,
            "raw": payload,
        }

    def _get_daily_previous_close(self, symbol: str, count: int = 5) -> dict:
        # 일봉 데이터에서 오늘 봉이 있으면 바로 직전 봉을 전일 종가로 계산한다.
        candles = self.get_candles(symbol, interval="1d", count=count)
        if not candles:
            return {
                "previous_close": 0.0,
                "candles": [],
                "selected_index": None,
                "today_candle_included": False,
            }

        today_kst = datetime.now(KST).date().isoformat()
        normalized = []
        for candle in candles:
            candle_time = candle.get("time")
            candle_date = str(candle_time).split(" ")[0] if candle_time is not None else ""
            normalized.append({**candle, "date": candle_date})

        today_index = None
        for index in range(len(normalized) - 1, -1, -1):
            if normalized[index].get("date") == today_kst:
                today_index = index
                break

        # 오늘 봉이 있으면 직전 봉을 전일 종가로 쓰고, 없으면 마지막 봉을 전일 종가로 사용한다.
        if today_index is not None and today_index > 0:
            selected_index = today_index - 1
            today_candle_included = True
        else:
            selected_index = len(normalized) - 1
            today_candle_included = False

        selected = normalized[selected_index] if 0 <= selected_index < len(normalized) else normalized[-1]
        return {
            "previous_close": float(selected.get("close") or 0.0),
            "candles": normalized,
            "selected_index": selected_index,
            "today_candle_included": today_candle_included,
        }

    def _build_standard_market_index_row(self, definition: dict, symbol: str, current_price: float, previous_close: float, payload: dict, source: str, token_info: dict | None = None) -> dict:
        # 백엔드/프론트/DB가 같은 필드 세트를 보도록 공통 응답 형태로 정규화한다.
        change_price = current_price - previous_close if previous_close else 0.0
        change_rate = ((change_price / previous_close) * 100) if previous_close else 0.0
        synced_at = datetime.now(timezone.utc).isoformat()
        raw_payload = payload if isinstance(payload, dict) else {"payload": payload}
        if token_info:
            raw_payload = {**raw_payload, "tokenInfo": token_info}
        return {
            "symbol": definition["symbol"],
            "label": definition["label"],
            "source": source,
            "market_country": definition["market_country"],
            "ticker": symbol,
            "current_price": current_price,
            "previous_close": previous_close,
            "change_price": change_price,
            "change_rate": change_rate,
            "current_value": current_price,
            "change_value": change_price,
            "change_percent": change_rate,
            "currency": definition["currency"],
            "display_order": definition["display_order"],
            "as_of": synced_at,
            "synced_at": synced_at,
            "raw_payload": raw_payload,
        }

    def get_market_index_snapshot(self, definition: dict) -> dict:
        if definition["kind"] == "fx":
            return self._get_exchange_rate_snapshot(definition)

        candidates = self._market_index_symbol_candidates(definition)
        logger.info(
            "[Toss Client][market-index] definition=%s candidates=%s",
            definition.get("symbol"),
            ",".join(candidates) if candidates else "NONE",
        )

        last_error: Exception | None = None
        # 지수는 후보 심볼을 순서대로 시도해서 stock-not-found를 줄인다.
        for candidate in candidates:
            logger.info(
                "[Toss Client][market-index] definition=%s symbol=%s",
                definition.get("symbol"),
                candidate,
            )
            try:
                quote = self._fetch_price_payload(candidate)
                try:
                    candle_info = self._get_daily_previous_close(candidate)
                except Exception as candle_error:
                    logger.debug(
                        "[Toss Client][market-index] candle lookup failed for symbol=%s error=%s",
                        candidate,
                        candle_error,
                    )
                    candle_info = {
                        "previous_close": 0.0,
                        "candles": [],
                        "selected_index": None,
                        "today_candle_included": False,
                    }

                current_price = float(quote.get("current_price") or 0.0)
                previous_close = float(candle_info.get("previous_close") or 0.0)
                if not current_price:
                    raise RuntimeError(f"Toss index lookup returned empty value for {candidate}")

                return self._build_standard_market_index_row(
                    definition,
                    candidate,
                    current_price,
                    previous_close,
                    {
                        "quote": quote.get("raw") or {},
                        "candles": candle_info.get("candles") or [],
                        "candleSelection": candle_info,
                        "symbolUsed": candidate,
                    },
                    source="TOSS_OPEN_API",
                    token_info=self.get_token_cache_info(),
                )
            except Exception as error:
                last_error = error

        raise RuntimeError(
            f"Toss index lookup failed for {definition.get('symbol')} with candidates={candidates}: {last_error}"
        )

    def _get_exchange_rate_snapshot(self, definition: dict) -> dict:
        # 환율은 별도 API로 가져오되, 응답이 비면 전일 종가 기준값으로도 구성한다.
        token = self._get_cached_token()
        response = self._send_request(
            "GET",
            f"{self.base_url}/api/v1/exchange-rate",
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            params={
                "baseCurrency": "USD",
                "quoteCurrency": "KRW",
            },
            timeout=15,
        )
        if response.status_code != 200:
            raise RuntimeError(f"Toss exchange rate failed: {response.text}")

        payload = response.json()
        result = payload.get("result", {})
        rate = result.get("rate") or result.get("basePrice") or result.get("exchangeRate") or result.get("price")
        if not rate:
            raise RuntimeError("Toss exchange rate returned empty payload")

        candle_info = self._get_daily_previous_close("USDKRW")
        current_price = float(rate)
        previous_close = float(candle_info.get("previous_close") or 0.0)
        return self._build_standard_market_index_row(
            definition,
            "USDKRW",
            current_price,
            previous_close,
            {
                "quote": payload,
                "rate": result.get("rate"),
                "midRate": result.get("midRate"),
                "basisPoint": result.get("basisPoint"),
                "rateChangeType": result.get("rateChangeType"),
                "validFrom": result.get("validFrom"),
                "validUntil": result.get("validUntil"),
                "candles": candle_info.get("candles") or [],
                "candleSelection": candle_info,
            },
            source="TOSS_EXCHANGE_RATE",
            token_info=self.get_token_cache_info(),
        )

    def _build_market_index_row(
        self,
        definition: dict,
        ticker: str,
        current_value: float,
        change_value: float,
        change_percent: float,
        payload: dict,
        source: str = "TOSS_OPEN_API",
    ) -> dict:
        synced_at = datetime.now(timezone.utc).isoformat()
        return {
            "symbol": definition["symbol"],
            "label": definition["label"],
            "source": source,
            "market_country": definition["market_country"],
            "ticker": ticker,
            "current_value": current_value,
            "current_price": current_value,
            "previous_close": current_value - change_value if change_value else 0.0,
            "change_value": change_value,
            "change_price": change_value,
            "change_percent": change_percent,
            "change_rate": change_percent,
            "currency": definition["currency"],
            "display_order": definition["display_order"],
            "as_of": synced_at,
            "synced_at": synced_at,
            "raw_payload": payload,
        }

    def _get_accounts_impl(self) -> list:
        token = self._get_cached_token()
        url = f"{self.base_url}/api/v1/accounts"
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }
        res = self._send_request("GET", url, headers=headers)
        
        if res.status_code != 200:
            fallback_url = f"{self.base_url}/v1/accounts"
            res = self._send_request("GET", fallback_url, headers=headers)

        if res.status_code != 200:
            raise Exception(f"토스 계좌 목록 조회 실패 (상태 코드 {res.status_code}): {res.text}")

        data = res.json()
        if "error" in data:
            err = data["error"]
            raise Exception(f"토스 계좌 조회 에러 [{err.get('code')}]: {err.get('message')} (Request ID: {err.get('requestId')})")

        result = data.get("result", [])
        if isinstance(result, dict):
            accounts = result.get("accounts", [])
        else:
            accounts = result

        return accounts

    def get_accounts(self) -> list:
        """
        사용자의 계좌 목록 정보를 가져옵니다.
        """
        return self._get_accounts_impl()

    def _get_balance_impl(self) -> dict:
        if not self.account_seq:
            accounts = self.get_accounts()
            if not accounts:
                raise Exception("조회 가능한 토스 계좌가 존재하지 않습니다.")
            self.account_seq = accounts[0].get("accountSeq")

        token = self._get_cached_token()
        url = f"{self.base_url}/api/v1/holdings"
        headers = {
            "Authorization": f"Bearer {token}",
            "X-Tossinvest-Account": self.account_seq,
            "Content-Type": "application/json"
        }
        res = self._send_request("GET", url, headers=headers)

        if res.status_code != 200:
            fallback_url = f"{self.base_url}/v1/accounts/holdings"
            res = self._send_request("GET", fallback_url, headers=headers)

        if res.status_code != 200:
            raise Exception(f"토스 보유 종목 조회 실패 (상태 코드 {res.status_code}): {res.text}")

        data = res.json()
        if "error" in data:
            err = data["error"]
            raise Exception(f"토스 보유자산 조회 에러 [{err.get('code')}]: {err.get('message')}")

        # 실제 Toss API 응답 구조:
        # result.marketValue.amount.usd  → 총 평가금액 (USD)
        # result.items[]                 → 보유 종목 목록
        #   .symbol, .name, .quantity, .lastPrice, .averagePurchasePrice
        #   .profitLoss.amount, .profitLoss.rate
        result = data.get("result", {})
        holdings_list = []

        # 총 평가금액: USD 기준 (해외주식은 krw=0이므로 usd 우선)
        total_eval = 0.0
        usd_val = 0.0
        try:
            mv = result.get("marketValue", {}).get("amount", {})
            usd_val = float(mv.get("usd", 0) or 0)
            krw_val = float(mv.get("krw", 0) or 0)
            total_eval = usd_val if usd_val > 0 else krw_val
        except (ValueError, TypeError):
            pass

        # 보유 종목: 실제 필드명은 `items` (기존 `holdings` 아님)
        raw_items = result.get("items", []) if isinstance(result, dict) else []
        if not raw_items and isinstance(result, list):
            raw_items = result

        for item in raw_items:
            symbol = item.get("symbol", "")
            name = item.get("name", "")
            currency = item.get("currency", "USD")
            try:
                qty = float(item.get("quantity", 0) or 0)
                avg_price = float(item.get("averagePurchasePrice", 0) or 0)
                current_price = float(item.get("lastPrice", 0) or 0)
                pl = item.get("profitLoss", {})
                profit = float(pl.get("amount", 0) or 0)
                profit_rate = float(pl.get("rate", 0) or 0) * 100.0
                mv_item = item.get("marketValue", {})
                eval_amount = float(mv_item.get("amount", 0) or 0)
            except (ValueError, TypeError):
                qty = avg_price = current_price = profit = profit_rate = eval_amount = 0.0

            if qty <= 0:
                continue

            holdings_list.append({
                "symbol": symbol,
                "name": name,
                "qty": qty,
                "avg_price": avg_price,
                "current_price": current_price,
                "profit": profit,
                "profit_rate": profit_rate,
                "eval_amount": eval_amount,
                "currency": currency,
            })

        # 총 평가금액이 0이면 items 합산으로 보정
        if total_eval == 0.0:
            total_eval = sum(h["eval_amount"] for h in holdings_list)

        return {
            "total_evaluation": total_eval,
            "available_cash": 0.0,  # holdings API에 예수금 미포함
            "currency": "USD" if usd_val > 0.0 else "KRW",
            "holdings": holdings_list
        }

    def get_balance(self) -> dict:
        """
        보유 자산 정보를 조회합니다.
        """
        return self._get_balance_impl()

    def _get_price_impl(self, symbol: str) -> dict:
        token = self._get_cached_token()
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }

        # 종목코드 보정 및 variants 생성 (예: 005930 -> [005930, A005930])
        symbol_variants = [symbol]
        if symbol.isdigit() and len(symbol) == 6:
            symbol_variants.append(f"A{symbol}")

        last_error = None
        last_raw = None

        for candidate in symbol_variants:
            url = f"{self.base_url}/api/v1/prices"
            # Toss API는 'symbol' 파라미터 또는 'symbols' 파라미터를 사용합니다.
            # 양방향 대응을 위해 둘 다 지원하도록 순차 조회
            res = self._send_request("GET", url, headers=headers, params={"symbol": candidate}, timeout=15)
            if res.status_code != 200:
                res = self._send_request("GET", url, headers=headers, params={"symbols": candidate}, timeout=15)

            if res.status_code != 200:
                last_error = f"{candidate}: {res.text}"
                continue

            data = res.json()
            last_raw = data
            if isinstance(data, dict) and data.get("error"):
                err = data["error"]
                last_error = f"{candidate}: {err.get('message') or err}"
                continue

            result = data.get("result", {})
            # result가 없거나 비어있는 경우 data 또는 output을 후보군으로 확인
            if not result or not isinstance(result, dict):
                for k in ("output", "data"):
                    if isinstance(data, dict) and data.get(k):
                        result = data.get(k)
                        break

            # 리스트 형태 등으로 들어오는 경우 첫번째 레코드 취함
            if isinstance(result, list) and len(result) > 0:
                result = result[0]
            if not isinstance(result, dict):
                result = {}

            try:
                current_price = float(
                    result.get("currentPrice")
                    or result.get("current_price")
                    or result.get("closePrice")
                    or result.get("close_price")
                    or result.get("price")
                    or result.get("lastPrice")
                    or result.get("last_price")
                    or 0.0
                )
                change_rate = float(
                    result.get("changeRate")
                    or result.get("change_rate")
                    or result.get("changePercent")
                    or result.get("change_percent")
                    or result.get("prdy_ctrt")
                    or 0.0
                )
                prev_close = float(
                    result.get("previousClosePrice")
                    or result.get("prev_close_price")
                    or result.get("basePrice")
                    or result.get("base_price")
                    or 0.0
                )
            except (ValueError, TypeError):
                current_price = 0.0
                change_rate = 0.0
                prev_close = 0.0

            # 이전 종가 획득 보조 (캔들 보조 조회)
            if not prev_close:
                try:
                    candle_res = self._send_request(
                        "GET",
                        f"{self.base_url}/api/v1/candles",
                        headers=headers,
                        params={"symbol": candidate, "interval": "1d", "count": 2},
                        timeout=15
                    )
                    if candle_res.status_code == 200:
                        candle_data = candle_res.json()
                        candles = candle_data.get("result", {}).get("candles", []) or candle_data.get("result", [])
                        if isinstance(candles, list) and len(candles) >= 2:
                            prev_close = float(candles[-2].get("closePrice") or candles[-2].get("close") or 0.0)
                        elif isinstance(candles, list) and len(candles) >= 1:
                            prev_close = float(candles[-1].get("closePrice") or candles[-1].get("close") or 0.0)
                except Exception:
                    pass

            if current_price and prev_close and not change_rate:
                change_rate = ((current_price - prev_close) / prev_close) * 100 if prev_close else 0.0

            if current_price or change_rate or prev_close:
                return {
                    "current_price": current_price,
                    "change_rate": change_rate,
                    "previous_close": prev_close,
                    "symbol_used": candidate,
                    "raw": data
                }

            last_error = f"{candidate}: empty price payload"

        return {
            "current_price": 0.0,
            "change_rate": 0.0,
            "previous_close": 0.0,
            "symbol_used": symbol_variants[-1],
            "raw": last_raw or {"error": last_error or "empty price payload"}
        }

    def get_price(self, symbol: str) -> dict:
        """
        현재가를 조회합니다.
        """
        return self._get_price_impl(symbol)

    def _place_order_impl(self, symbol: str, qty: float, side: str, ord_type: str, price: float = None) -> dict:
        if self.env == "MOCK":
            client_order_id = f"mock-toss-{uuid.uuid4().hex[:16]}"
            return {
                "order_id": f"MOCK-TOSS-{int(time.time())}",
                "status": "ORDERED",
                "client_order_id": client_order_id,
                "raw": {"symbol": symbol, "qty": qty, "side": side, "ord_type": ord_type, "client_order_id": client_order_id}
            }
            
        token = self._get_cached_token()
        url = f"{self.base_url}/api/v1/orders"
        headers = {
            "Authorization": f"Bearer {token}",
            "X-Tossinvest-Account": self.account_seq,
            "Content-Type": "application/json"
        }
        client_order_id = f"toss-{uuid.uuid4().hex[:16]}"
        payload = {
            "clientOrderId": client_order_id,
            "symbol": symbol,
            "quantity": qty,
            "side": side.upper(),
            "orderType": ord_type.upper(),
        }
        if price:
            payload["price"] = price

        res = self._send_request("POST", url, json=payload, headers=headers)
        if res.status_code != 200:
            raise Exception(f"토스 주문 접수 실패: {res.text}")

        data = res.json()
        result = data.get("result", {})
        return {
            "order_id": result.get("orderId"),
            "status": result.get("status"),
            "client_order_id": client_order_id,
            "raw": data
        }

    def place_order(self, symbol: str, qty: float, side: str, ord_type: str, price: float = None) -> dict:
        """
        주문을 접수합니다.
        """
        return self._place_order_impl(symbol, qty, side, ord_type, price)

    def cancel_order(self, order_id: str) -> dict:
        """
        접수된 토스 대기 주문을 취소합니다.
        """
        if self.env == "MOCK":
            return {
                "order_id": order_id,
                "status": "CANCELED",
                "raw": {"order_id": order_id, "env": self.env}
            }

        token = self._get_cached_token()
        url = f"{self.base_url}/api/v1/orders/{order_id}/cancel"
        headers = {
            "Authorization": f"Bearer {token}",
            "X-Tossinvest-Account": self.account_seq,
            "Content-Type": "application/json"
        }
        res = self._send_request("POST", url, headers=headers)
        if res.status_code != 200:
            raise Exception(f"토스 주문 취소 실패: {res.text}")

        data = res.json()
        result = data.get("result", {})
        return {
            "order_id": result.get("orderId", order_id),
            "status": result.get("status", "CANCELED"),
            "raw": data
        }

    def modify_order(self, order_id: str, price: float | None = None, quantity: float | None = None) -> dict:
        """
        접수된 토스 대기 주문의 가격 또는 수량을 정정합니다.
        """
        if price is None and quantity is None:
            raise ValueError("정정할 가격 또는 수량이 필요합니다.")

        if self.env == "MOCK":
            return {
                "order_id": order_id,
                "status": "MODIFIED",
                "raw": {"order_id": order_id, "price": price, "quantity": quantity, "env": self.env}
            }

        token = self._get_cached_token()
        url = f"{self.base_url}/api/v1/orders/{order_id}/modify"
        headers = {
            "Authorization": f"Bearer {token}",
            "X-Tossinvest-Account": self.account_seq,
            "Content-Type": "application/json"
        }
        payload = {}
        if price is not None:
            payload["price"] = price
        if quantity is not None:
            payload["quantity"] = quantity

        res = self._send_request("POST", url, json=payload, headers=headers)
        if res.status_code != 200:
            raise Exception(f"토스 주문 정정 실패: {res.text}")

        data = res.json()
        result = data.get("result", {})
        return {
            "order_id": result.get("orderId", order_id),
            "status": result.get("status", "MODIFIED"),
            "raw": data
        }

    def _get_order_status_impl(self, order_id: str) -> dict:
        if self.env == "MOCK":
            return {
                "order_id": order_id,
                "status": "ORDERED",
                "qty": 0.0,
                "executed_qty": 0.0,
                "raw": {"order_id": order_id, "env": self.env}
            }

        token = self._get_cached_token()
        url = f"{self.base_url}/api/v1/orders/{order_id}"
        headers = {
            "Authorization": f"Bearer {token}",
            "X-Tossinvest-Account": self.account_seq,
            "Content-Type": "application/json"
        }
        res = self._send_request("GET", url, headers=headers)
        if res.status_code != 200:
            raise Exception(f"토스 주문 조회 실패: {res.text}")

        data = res.json()
        result = data.get("result", {})
        return {
            "order_id": result.get("orderId"),
            "status": result.get("status"),
            "qty": float(result.get("quantity", 0)),
            "executed_qty": float(result.get("executedQuantity", 0)),
            "raw": data
        }

    def get_order_status(self, order_id: str) -> dict:
        """
        주문 상태를 조회합니다.
        """
        return self._get_order_status_impl(order_id)

    def _get_candles_impl(self, symbol: str, interval: str = "1d", count: int = 120) -> list:
        token = self._get_cached_token()
        url = f"{self.base_url}/api/v1/candles"
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }
        params = {
            "symbol": symbol,
            "interval": interval,
            "count": min(count, 200),
            "adjusted": "true"
        }
        res = self._send_request("GET", url, headers=headers, params=params)
        if res.status_code != 200:
            raise Exception(f"Toss get_candles failed: {res.text}")
            
        data = res.json()
        if "error" in data:
            err = data["error"]
            raise Exception(f"Toss get_candles error [{err.get('code')}]: {err.get('message')}")
            
        result = data.get("result", {})
        candles = []
        is_intraday = interval not in ("1d", "1w", "1M", "day", "week", "month", "D", "W", "M")
        
        for candle in result.get("candles", []):
            try:
                timestamp = candle.get("timestamp", "")
                if is_intraday:
                    try:
                        dt = datetime.strptime(timestamp, "%Y-%m-%d %H:%M:%S")
                        dt = dt.replace(tzinfo=KST)
                        time_val = int(dt.timestamp())
                    except ValueError:
                        try:
                            dt = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
                            dt = dt.astimezone(KST)
                            time_val = int(dt.timestamp())
                        except ValueError:
                            time_val = timestamp
                else:
                    time_val = timestamp.split(" ")[0] if " " in timestamp else timestamp
                    
                candles.append({
                    "time": time_val,
                    "open": float(candle.get("openPrice", 0)),
                    "high": float(candle.get("highPrice", 0)),
                    "low": float(candle.get("lowPrice", 0)),
                    "close": float(candle.get("closePrice", 0)),
                    "volume": float(candle.get("volume", 0))
                })
            except (ValueError, TypeError):
                pass
                
        seen = set()
        unique_candles = []
        for c in candles:
            if c["time"] not in seen:
                seen.add(c["time"])
                unique_candles.append(c)
                
        unique_candles.sort(key=lambda x: x["time"])
        return unique_candles

    def get_candles(self, symbol: str, interval: str = "1d", count: int = 120) -> list:
        """
        주식 캔들 데이터를 조회합니다. 미지원 주기(5m, 15m, 30m, 1h, 1w, 1M 등)일 경우 자체 리샘플링하여 반환합니다.
        """
        normalized_interval = interval
        if interval in ("1d", "D", "day"):
            normalized_interval = "1d"
        elif interval in ("1m", "minute"):
            normalized_interval = "1m"

        # 1. 토스 네이티브 지원 주기인 경우 바로 호출
        if normalized_interval in ("1d", "1m"):
            return self._get_candles_impl(symbol, interval=normalized_interval, count=count)

        # 2. 토스 미지원 주기인 경우 자체 리샘플링
        # 2-A. 분봉/시간봉 리샘플링 (5m, 15m, 30m, 60m, 1h 등)
        if normalized_interval in ("5m", "15m", "30m", "60m", "1h"):
            interval_minutes = 5
            if normalized_interval == "15m":
                interval_minutes = 15
            elif normalized_interval == "30m":
                interval_minutes = 30
            elif normalized_interval in ("60m", "1h"):
                interval_minutes = 60

            # 1분봉 데이터를 최대한 많이 가져옴 (리샘플링하기 위해 count보다 넉넉히 가져옴, 최대 200개 한계)
            raw_candles = self.get_candles(symbol, interval="1m", count=200)
            if not raw_candles:
                return []

            buckets = {}
            for c in raw_candles:
                try:
                    ts = int(c["time"])
                except (ValueError, TypeError):
                    continue
                bucket_ts = _floor_kst_bucket_timestamp(ts, interval_minutes)
                if bucket_ts not in buckets:
                    buckets[bucket_ts] = []
                buckets[bucket_ts].append(c)

            resampled = []
            for b_ts, c_list in sorted(buckets.items()):
                resampled.append({
                    "time": b_ts,
                    "open": c_list[0]["open"],
                    "high": max(x["high"] for x in c_list),
                    "low": min(x["low"] for x in c_list),
                    "close": c_list[-1]["close"],
                    "volume": sum(x["volume"] for x in c_list)
                })
            return resampled[-count:]

        # 2-B. 주봉/월봉 리샘플링 (1w, W, 1M, M 등)
        elif normalized_interval in ("1w", "W", "week", "1M", "M", "month"):
            raw_candles = self.get_candles(symbol, interval="1d", count=200)
            if not raw_candles:
                return []

            buckets = {}
            is_week = normalized_interval in ("1w", "W", "week")

            for c in raw_candles:
                date_str = c["time"]
                try:
                    dt = datetime.strptime(date_str, "%Y-%m-%d")
                except ValueError:
                    continue

                if is_week:
                    monday = dt - timedelta(days=dt.weekday())
                    bucket_key = monday.strftime("%Y-%m-%d")
                else:
                    bucket_key = dt.strftime("%Y-%m-01")

                if bucket_key not in buckets:
                    buckets[bucket_key] = []
                buckets[bucket_key].append(c)

            resampled = []
            for b_key, c_list in sorted(buckets.items()):
                resampled.append({
                    "time": b_key,
                    "open": c_list[0]["open"],
                    "high": max(x["high"] for x in c_list),
                    "low": min(x["low"] for x in c_list),
                    "close": c_list[-1]["close"],
                    "volume": sum(x["volume"] for x in c_list)
                })
            return resampled[-count:]

        # 3. 그 외의 경우 일봉으로 폴백
        return self.get_candles(symbol, interval="1d", count=count)

    def _get_exchange_rate_impl(self) -> float:
        try:
            token = self._get_cached_token()
            res = self._send_request(
                "GET",
                f"{self.base_url}/api/v1/exchange-rate",
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                },
                params={
                    "baseCurrency": "USD",
                    "quoteCurrency": "KRW",
                },
                timeout=15,
            )
            if res.status_code == 200:
                data = res.json()
                result = data.get("result", {})
                rate = result.get("rate")
                if rate:
                    return float(rate)
        except Exception as error:
            logger.warning(f"[Toss Client] exchange-rate request failed: {error}")

        try:
            # 실시간 환율이 실패하면 저장된 지수 캐시에서 USD/KRW를 마지막 대안으로 읽는다.
            from backend.services.market_index_repository import MarketIndexRepository

            repository = MarketIndexRepository()
            rows = repository.list_latest()
            for row in rows or []:
                if str(row.get("symbol") or "").upper() == "USDKRW":
                    cached_rate = float(row.get("current_price") or row.get("current_value") or 0)
                    if cached_rate > 0:
                        logger.info("[Toss Client] exchange-rate fallback from DB cache")
                        return cached_rate
        except Exception as error:
            logger.warning(f"[Toss Client] exchange-rate DB fallback failed: {error}")

        return 1500.0

    def get_exchange_rate(self) -> float:
        """
        실시간 환율 정보를 조회합니다.
        """
        try:
            return self._get_exchange_rate_impl()
        except Exception:
            return 1500.0

    def _get_orderbook_impl(self, symbol: str) -> dict:
        token = self._get_cached_token()
        url = f"{self.base_url}/api/v1/orderbook"
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }
        res = self._send_request("GET", url, headers=headers, params={"symbol": symbol})
        if res.status_code != 200:
            raise Exception(f"토스 호가 조회 실패: {res.text}")
        return res.json()

    def get_orderbook(self, symbol: str) -> dict:
        """
        종목코드에 해당하는 호가 정보(Orderbook)를 가져옵니다.
        """
        return self._get_orderbook_impl(symbol)

    def _get_trades_impl(self, symbol: str) -> dict:
        token = self._get_cached_token()
        url = f"{self.base_url}/api/v1/trades"
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }
        res = self._send_request("GET", url, headers=headers, params={"symbol": symbol})
        if res.status_code != 200:
            raise Exception(f"토스 체결 조회 실패: {res.text}")
        return res.json()

    def get_trades(self, symbol: str) -> dict:
        """
        종목코드에 해당하는 실시간 체결 정보(Trades)를 가져옵니다.
        """
        return self._get_trades_impl(symbol)
