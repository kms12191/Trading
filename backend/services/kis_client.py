import os
import json
import time
import threading
import logging
import requests
from pathlib import Path
from datetime import datetime, timedelta, timezone
from backend.services.exchange_client import ExchangeClient, MarketClosedError, is_market_closed_order_error

KST = timezone(timedelta(hours=9))
logger = logging.getLogger(__name__)

# KIS 모의투자 API Rate Limiter
_kis_mock_rate_limiter_lock = threading.Lock()
_last_kis_mock_request_time = 0.0
KIS_MOCK_MIN_INTERVAL = 0.5  # 초당 3회 한도 방어를 위해 최소 0.5초 간격 유지

DEFAULT_US_RANK_EXCHANGES = ["NAS", "NYS", "AMS"]


def _enforce_kis_mock_rate_limit(env: str):
    global _last_kis_mock_request_time
    if env.upper() != "MOCK":
        return
    with _kis_mock_rate_limiter_lock:
        now = time.time()
        elapsed = now - _last_kis_mock_request_time
        if elapsed < KIS_MOCK_MIN_INTERVAL:
            sleep_time = KIS_MOCK_MIN_INTERVAL - elapsed
            time.sleep(sleep_time)
        _last_kis_mock_request_time = time.time()


def _floor_kst_bucket_timestamp(timestamp: int, interval_minutes: int) -> int:
    """
    유닉스 타임스탬프를 한국시간 기준 캔들 시작 시각으로 내림 정렬합니다.
    """
    dt_kst = datetime.fromtimestamp(timestamp, tz=KST)
    bucket_minute = (dt_kst.minute // interval_minutes) * interval_minutes
    bucket_dt = dt_kst.replace(minute=bucket_minute, second=0, microsecond=0)
    return int(bucket_dt.timestamp())

class KISClient(ExchangeClient):
    def __init__(self, appkey: str, appsecret: str, cano: str, acnt_prdt_cd: str = "01", env: str = "MOCK", user_id: str | None = None):
        self.appkey = appkey
        self.appsecret = appsecret
        self.cano = cano
        self.acnt_prdt_cd = acnt_prdt_cd
        self.env = env.upper()
        self.user_id = user_id
        # 마지막 토큰 조회 결과를 기록해 상위 로직에서 캐시 상태를 함께 볼 수 있게 한다.
        # 이 정보는 "왜 지금은 재사용인지 / 재발급인지"를 로그와 응답에서 구분할 때 쓰인다.
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
        
        if self.env == "REAL":
            self.base_url = "https://openapi.koreainvestment.com:9443"
            self.balance_tr_id = "TTTC8434R"
            self.buy_tr_id = "TTTC0802U"
            self.sell_tr_id = "TTTC0801U"
            self.modify_cancel_tr_id = "TTTC0803U"
        else:
            self.base_url = "https://openapivts.koreainvestment.com:29443"
            self.balance_tr_id = "VTTC8434R"
            self.buy_tr_id = "VTTC0802U"
            self.sell_tr_id = "VTTC0801U"
            self.modify_cancel_tr_id = "VTTC0803U"

    def _clear_token_cache(self):
        """
        DB 캐시 테이블에서 현재 KIS 토큰 정보를 강제 만료시킵니다.
        """
        from backend.services.token_cache_service import clear_db_token
        try:
            clear_db_token("KIS", self.env, self.user_id)
        except Exception:
            pass

    def get_token_cache_info(self) -> dict:
        return dict(self._last_token_cache_info)

    def get_access_token(self) -> str:
        # 외부 호출부는 이 메서드만 쓰면 토큰 획득/갱신 세부사항을 몰라도 된다.
        # 즉, 토큰 캐시가 있으면 재사용하고 없으면 내부에서 새로 발급한다는 의미다.
        return self._get_cached_token()

    def _get_cached_token(self) -> str:
        """
        Supabase DB의 token_caches 테이블에서 KIS Access Token을 가져옵니다.
        토큰이 만료되었거나 캐시가 없으면 새로 발급을 요청합니다.
        """
        from backend.services.token_cache_service import get_db_token_with_status, set_db_token
        
        # DB에서 유효한 공용 토큰 획득 시도
        # 토큰이 아직 남아 있으면 외부 호출을 아끼고, 만료 임박이면 바로 재발급한다.
        cache_state = get_db_token_with_status("KIS", self.env, self.user_id)
        self._last_token_cache_info = {
            "source": "token_cache_service",
            "cacheStatus": cache_state.get("cache_status", "MISS"),
            "tokenStatus": cache_state.get("token_status", "REFRESHED"),
            "errorMessage": cache_state.get("error_message"),
            "expiredAt": cache_state.get("expired_at"),
        }
        token = cache_state.get("token")
        if token:
            return token

        # 토큰 새로 발급
        token_data = self._request_new_token()
        new_token = token_data["access_token"]
        
        # 만료 시각 계산
        expires_in = 86400
        expired_at_raw = token_data.get("access_token_token_expired")
        if expired_at_raw:
            try:
                exp_dt = datetime.strptime(expired_at_raw, "%Y-%m-%d %H:%M:%S")
                expires_in = int((exp_dt - datetime.now()).total_seconds())
            except Exception:
                pass

        # DB 캐시 테이블에 신규 토큰 저장 (Upsert)
        try:
            set_db_token("KIS", self.env, new_token, expires_in, self.user_id)
        except Exception:
            pass
        self._last_token_cache_info = {
            "source": "token_cache_service",
            "cacheStatus": "MISS",
            "tokenStatus": "REFRESHED",
            "errorMessage": cache_state.get("error_message"),
            "expiredAt": (datetime.utcnow() + timedelta(seconds=expires_in)).isoformat() + "Z",
        }
            
        return new_token

    def _clear_token_cache(self):
        from backend.services.token_cache_service import clear_db_token
        try:
            clear_db_token("KIS", self.env, self.user_id)
        except Exception:
            pass
        self._access_token_cache = {
            "token": None,
            "expired_at": None,
        }

    def _is_expired_token_response(self, response: requests.Response) -> bool:
        try:
            payload = response.json()
        except ValueError:
            payload = {}
        message = str(payload.get("msg1") or response.text or "")
        return payload.get("msg_cd") == "EGW00123" or "기간이 만료된 token" in message

    def _request_with_token_retry(
        self,
        method: str,
        url: str,
        headers: dict,
        *,
        params: dict | None = None,
        json_data: dict | None = None,
        timeout: int = 10,
    ) -> requests.Response:
        for attempt in range(2):
            token = self._get_cached_token()
            request_headers = {
                **headers,
                "authorization": f"Bearer {token}",
                "appkey": self.appkey,
                "appsecret": self.appsecret,
            }
            response = requests.request(
                method,
                url,
                headers=request_headers,
                params=params,
                json=json_data,
                timeout=timeout,
            )
            if not self._is_expired_token_response(response) or attempt == 1:
                return response

            logger.warning("[KIS Client] expired token detected. token cache will be refreshed once. path=%s", url)
            self._clear_token_cache()

        return response

    def _get_cached_token(self) -> str:
        from backend.services.lock_service import distributed_lock
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

        cache_state = get_db_token_with_status("KIS", self.env, self.user_id)
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

        # 같은 토큰을 동시에 다시 발급하지 않도록 잠근다.
        lock_key = f"kis-token:{self.env}:{self.user_id or 'anonymous'}"
        with distributed_lock(lock_key, duration_seconds=120) as acquired:
            if not acquired:
                time.sleep(0.5)
                cache_state = get_db_token_with_status("KIS", self.env, self.user_id)
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
                    self._last_token_cache_info = {
                        "source": "token_cache_service",
                        "cacheStatus": "HIT",
                        "tokenStatus": "REUSED",
                        "errorMessage": cache_state.get("error_message"),
                        "expiredAt": cache_state.get("expired_at"),
                    }
                    return token

            token_data = self._request_new_token()
            new_token = token_data["access_token"]
            expires_in = 86400
            expired_at_raw = token_data.get("expires_in") or token_data.get("access_token_token_expired") or token_data.get("access_token_expired_at")
            if expired_at_raw:
                try:
                    if isinstance(expired_at_raw, (int, float)):
                        expires_in = int(expired_at_raw)
                    else:
                        exp_dt = datetime.strptime(str(expired_at_raw), "%Y-%m-%d %H:%M:%S")
                        expires_in = int((exp_dt - datetime.now()).total_seconds())
                except Exception:
                    pass
            if expires_in <= 0:
                expires_in = 86400

            try:
                set_db_token("KIS", self.env, new_token, expires_in, self.user_id)
            except Exception as error:
                logger.warning("[KIS Client] token cache save failed: %s", error)
            expired_at = datetime.utcnow() + timedelta(seconds=expires_in)
            self._access_token_cache = {
                "token": new_token,
                "expired_at": expired_at,
            }
            self._last_token_cache_info = {
                "source": "token_cache_service",
                "cacheStatus": "MISS",
                "tokenStatus": "REFRESHED",
                "errorMessage": cache_state.get("error_message"),
                "expiredAt": expired_at.isoformat() + "Z",
            }
            return new_token

    def _request_new_token(self) -> dict:
        _enforce_kis_mock_rate_limit(self.env)
        url = f"{self.base_url}/oauth2/tokenP"
        payload = {
            "grant_type": "client_credentials",
            "appkey": self.appkey,
            "appsecret": self.appsecret
        }
        headers = {
            "content-type": "application/json"
        }
        res = requests.post(url, json=payload, headers=headers, timeout=10)
        if res.status_code != 200:
            raise Exception(f"KIS Token issuance failed: {res.text}")
        return res.json()

    def get_price(self, symbol: str) -> dict:
        _enforce_kis_mock_rate_limit(self.env)
        url = f"{self.base_url}/uapi/domestic-stock/v1/quotations/inquire-price"
        headers = {
            "content-type": "application/json; charset=utf-8",
            "tr_id": "FHKST01010100"
        }
        params = {
            "FID_COND_MRKT_DIV_CODE": "J",
            "FID_INPUT_ISCD": symbol
        }
        res = self._request_with_token_retry("GET", url, headers, params=params, timeout=10)
        if res.status_code != 200:
            raise Exception(f"KIS get_price failed: {res.text}")
            
        data = res.json()
        if data.get("rt_cd") != "0":
            raise Exception(f"KIS get_price error: {data.get('msg1')}")
            
        output = data.get("output", {})
        try:
            current_price = float(output.get("stck_prpr", 0))
            change_rate = float(output.get("prdy_ctrt", 0))
            trading_volume = float(output.get("acml_vol", 0))
            trading_value = float(output.get("acml_tr_pbmn", 0))
        except (ValueError, TypeError):
            current_price = 0.0
            change_rate = 0.0
            trading_volume = 0.0
            trading_value = 0.0

        if not trading_value and current_price and trading_volume:
            trading_value = current_price * trading_volume
            
        return {
            "current_price": current_price,
            "change_rate": change_rate,
            "trading_volume": trading_volume,
            "trading_value": trading_value,
            "raw": data
        }

    def get_turnover_rankings(self, limit: int = 10) -> list[dict]:
        """
        국내주식 순위 API를 조회한 뒤 누적 거래대금을 기준으로 정렬해 반환합니다.
        홈페이지 랭킹 표 전용 보조 데이터이며, 주문/거래 실행에는 사용하지 않습니다.
        """
        url = f"{self.base_url}/uapi/domestic-stock/v1/quotations/volume-rank"
        headers = {
            "content-type": "application/json; charset=utf-8",
            "tr_id": "FHPST01710000",
        }
        params = {
            "FID_COND_MRKT_DIV_CODE": "J",
            "FID_COND_SCR_DIV_CODE": "20171",
            "FID_INPUT_ISCD": "0000",
            "FID_DIV_CLS_CODE": "0",
            "FID_BLNG_CLS_CODE": "0",
            "FID_TRGT_CLS_CODE": "111111111",
            "FID_TRGT_EXLS_CLS_CODE": "000000",
            "FID_INPUT_PRICE_1": "",
            "FID_INPUT_PRICE_2": "",
            "FID_VOL_CNT": "",
            "FID_INPUT_DATE_1": "",
        }
        res = self._request_with_token_retry("GET", url, headers, params=params, timeout=10)
        if res.status_code != 200:
            raise Exception(f"KIS turnover ranking failed: {res.text}")

        data = res.json()
        if data.get("rt_cd") != "0":
            raise Exception(f"KIS turnover ranking error: {data.get('msg1')}")

        rankings = []
        for item in data.get("output", []) or []:
            try:
                current_price = float(item.get("stck_prpr") or 0)
                change_rate = float(item.get("prdy_ctrt") or 0)
                trading_volume = float(item.get("acml_vol") or 0)
                trading_value = float(
                    item.get("acml_tr_pbmn")
                    or item.get("acc_trdval")
                    or 0
                )
            except (TypeError, ValueError):
                current_price = 0.0
                change_rate = 0.0
                trading_volume = 0.0
                trading_value = 0.0

            if not trading_value and current_price and trading_volume:
                trading_value = current_price * trading_volume

            symbol = str(item.get("stck_shrn_iscd") or item.get("mksc_shrn_iscd") or "").strip()
            name = str(item.get("hts_kor_isnm") or item.get("data_rank_name") or symbol).strip()
            if not symbol:
                continue

            rankings.append({
                "symbol": symbol,
                "name": name,
                "market_segment": "OTHER" if not symbol.isdigit() else "KOSPI",
                "market_country": "KR",
                "current_price": current_price,
                "change_rate": change_rate,
                "trading_volume": trading_volume,
                "trading_value": trading_value,
                "as_of": datetime.utcnow().isoformat() + "Z",
                "raw": item,
            })

        rankings.sort(key=lambda row: row["trading_value"], reverse=True)
        return rankings[:limit]

    def _to_float(self, value, default: float = 0.0) -> float:
        try:
            if value is None or value == "":
                return default
            return float(str(value).replace(",", "").strip())
        except (TypeError, ValueError):
            return default

    def _normalize_domestic_rank_item(self, item: dict, source: str) -> dict | None:
        symbol = str(item.get("stck_shrn_iscd") or item.get("mksc_shrn_iscd") or "").strip().upper()
        if not symbol:
            return None

        current_price = self._to_float(item.get("stck_prpr"))
        change_rate = self._to_float(item.get("prdy_ctrt"))
        trading_volume = self._to_float(
            item.get("acml_vol")
            or item.get("acc_trdvol")
            or item.get("cntg_vol")
        )
        trading_value = self._to_float(
            item.get("acml_tr_pbmn")
            or item.get("acc_trdval")
            or item.get("acc_trdprc")
        )
        if not trading_value and current_price and trading_volume:
            trading_value = current_price * trading_volume

        return {
            "symbol": symbol,
            "name": str(item.get("hts_kor_isnm") or item.get("data_rank_name") or symbol).strip(),
            "market_segment": "OTHER" if not symbol.isdigit() else "KOSPI",
            "market_country": "KR",
            "current_price": current_price,
            "change_rate": change_rate,
            "trading_volume": trading_volume,
            "trading_value": trading_value,
            "as_of": datetime.utcnow().isoformat() + "Z",
            "raw": {**item, "_rank_source": source},
        }

    def _get_domestic_rankings(
        self,
        endpoint: str,
        tr_id: str,
        params: dict,
        source: str,
        limit: int,
    ) -> list[dict]:
        _enforce_kis_mock_rate_limit(self.env)
        headers = {
            "content-type": "application/json; charset=utf-8",
            "tr_id": tr_id,
        }
        res = self._request_with_token_retry(
            "GET",
            f"{self.base_url}{endpoint}",
            headers,
            params=params,
            timeout=15,
        )
        if res.status_code != 200:
            raise Exception(f"KIS ranking request failed: {res.text}")

        data = res.json()
        if data.get("rt_cd") != "0":
            raise Exception(f"KIS ranking error: {data.get('msg1')}")

        rankings = []
        for item in data.get("output", []) or []:
            row = self._normalize_domestic_rank_item(item, source)
            if row:
                rankings.append(row)
        return rankings[:limit]

    def get_fluctuation_rankings(self, direction: str = "up", limit: int = 50) -> list[dict]:
        """
        KIS 국내주식 등락률 순위 API를 호출합니다.
        direction='up'은 상승률 상위, direction='down'은 하락률 하위를 반환합니다.
        """
        sort_code = "0" if direction == "up" else "1"
        params = {
            "FID_COND_MRKT_DIV_CODE": "J",
            "FID_COND_SCR_DIV_CODE": "20170",
            "FID_INPUT_ISCD": "0000",
            "FID_RANK_SORT_CLS_CODE": sort_code,
            "FID_INPUT_CNT_1": "0",
            "FID_PRC_CLS_CODE": "1",
            "FID_INPUT_PRICE_1": "",
            "FID_INPUT_PRICE_2": "",
            "FID_VOL_CNT": "",
            "FID_TRGT_CLS_CODE": "0",
            "FID_TRGT_EXLS_CLS_CODE": "0",
            "FID_DIV_CLS_CODE": "0",
            "FID_RSFL_RATE1": "",
            "FID_RSFL_RATE2": "",
        }
        rankings = self._get_domestic_rankings(
            endpoint="/uapi/domestic-stock/v1/ranking/fluctuation",
            tr_id="FHPST01700000",
            params=params,
            source=f"KIS_FLUCTUATION_{direction.upper()}",
            limit=limit,
        )
        rankings.sort(key=lambda row: row["change_rate"], reverse=direction == "up")
        return rankings[:limit]

    def _normalize_overseas_rank_item(self, item: dict, source: str) -> dict | None:
        symbol = str(item.get("symb") or item.get("ovrs_pdno") or "").strip().upper()
        if not symbol:
            return None

        current_price = self._to_float(item.get("last") or item.get("ovrs_now_pric"))
        change_rate = self._to_float(item.get("rate") or item.get("n_rate"))
        trading_volume = self._to_float(item.get("tvol") or item.get("a_tvol"))
        trading_value = self._to_float(item.get("tamt"))

        return {
            "symbol": symbol,
            "name": str(item.get("name") or item.get("ename") or symbol).strip(),
            "market_segment": "US",
            "market_country": "US",
            "current_price": current_price,
            "change_rate": change_rate,
            "trading_volume": trading_volume,
            "trading_value": trading_value,
            "as_of": datetime.utcnow().isoformat() + "Z",
            "raw": {**item, "_rank_source": source, "_exchange_code": item.get("excd")},
        }

    def _get_overseas_rankings(
        self,
        endpoint: str,
        tr_id: str,
        params: dict,
        source: str,
        limit: int,
    ) -> list[dict]:
        _enforce_kis_mock_rate_limit(self.env)
        token = self._get_cached_token()
        headers = {
            "content-type": "application/json; charset=utf-8",
            "authorization": f"Bearer {token}",
            "appkey": self.appkey,
            "appsecret": self.appsecret,
            "tr_id": tr_id,
        }
        res = requests.get(f"{self.base_url}{endpoint}", headers=headers, params=params, timeout=20)
        if res.status_code != 200:
            raise Exception(f"KIS overseas ranking failed: {res.text}")

        data = res.json()
        if data.get("rt_cd") != "0":
            raise Exception(f"KIS overseas ranking error: {data.get('msg1')}")

        rows = []
        for item in data.get("output2", []) or []:
            row = self._normalize_overseas_rank_item(item, source)
            if row:
                rows.append(row)
        return rows[:limit]

    def get_overseas_trade_volume_rankings(self, exchange: str = "NAS", limit: int = 50) -> list[dict]:
        """
        KIS 해외주식 거래량 순위 API를 호출합니다.
        """
        return self._get_overseas_rankings(
            endpoint="/uapi/overseas-stock/v1/ranking/trade-vol",
            tr_id="HHDFS76310010",
            params={
                "EXCD": exchange,
                "NDAY": "0",
                "VOL_RANG": "0",
                "KEYB": "",
                "AUTH": "",
                "PRC1": "",
                "PRC2": "",
            },
            source=f"KIS_OVERSEAS_TRADE_VOLUME_{exchange}",
            limit=limit,
        )

    def get_overseas_updown_rankings(self, direction: str = "up", exchange: str = "NAS", limit: int = 50) -> list[dict]:
        """
        KIS 해외주식 상승률/하락률 순위 API를 호출합니다.
        direction='up'은 상승률 상위, direction='down'은 하락률 하위를 반환합니다.
        """
        return self._get_overseas_rankings(
            endpoint="/uapi/overseas-stock/v1/ranking/updown-rate",
            tr_id="HHDFS76290000",
            params={
                "EXCD": exchange,
                "NDAY": "0",
                "GUBN": "1" if direction == "up" else "0",
                "VOL_RANG": "0",
                "AUTH": "",
                "KEYB": "",
            },
            source=f"KIS_OVERSEAS_UPDOWN_{direction.upper()}_{exchange}",
            limit=limit,
        )

    def get_overseas_rank_candidates(self, limit: int = 50) -> list[dict]:
        """
        미국 시장 거래량/상승률/하락률 순위 API를 합쳐 홈 캐시 후보군을 만듭니다.
        NASDAQ, NYSE, AMEX를 기본 대상으로 조회합니다.
        """
        exchanges = [
            value.strip().upper()
            for value in os.getenv("KIS_US_RANK_EXCHANGES", ",".join(DEFAULT_US_RANK_EXCHANGES)).split(",")
            if value.strip()
        ]
        collected: list[dict] = []
        errors: list[str] = []
        for exchange in exchanges:
            for fetcher in (
                lambda exchange=exchange: self.get_overseas_trade_volume_rankings(exchange=exchange, limit=limit),
                lambda exchange=exchange: self.get_overseas_updown_rankings(direction="up", exchange=exchange, limit=limit),
                lambda exchange=exchange: self.get_overseas_updown_rankings(direction="down", exchange=exchange, limit=limit),
            ):
                try:
                    collected.extend(fetcher())
                except Exception as exc:
                    errors.append(str(exc))

        by_symbol: dict[str, dict] = {}
        for row in collected:
            symbol = str(row.get("symbol") or "").strip().upper()
            if not symbol:
                continue
            previous = by_symbol.get(symbol)
            if not previous:
                by_symbol[symbol] = row
                continue
            merged = {**previous, **row}
            merged["trading_volume"] = max(
                self._to_float(previous.get("trading_volume")),
                self._to_float(row.get("trading_volume")),
            )
            merged["trading_value"] = max(
                self._to_float(previous.get("trading_value")),
                self._to_float(row.get("trading_value")),
            )
            by_symbol[symbol] = merged

        rows = list(by_symbol.values())
        rows.sort(key=lambda row: row.get("trading_volume", 0), reverse=True)
        if not rows and errors:
            raise Exception("KIS overseas rank candidates failed: " + "; ".join(errors[:5]))
        return rows

    def get_market_rank_candidates(self, limit: int = 50) -> list[dict]:
        """
        거래대금/거래량 후보와 상승률/하락률 후보를 합쳐 DB 캐시 업서트용 후보군을 만듭니다.
        같은 종목은 가장 정보가 많은 최신 행 하나로 합칩니다.
        """
        collected: list[dict] = []
        errors: list[str] = []
        for fetcher in (
            lambda: self.get_turnover_rankings(limit=limit),
            lambda: self.get_fluctuation_rankings(direction="up", limit=limit),
            lambda: self.get_fluctuation_rankings(direction="down", limit=limit),
        ):
            try:
                collected.extend(fetcher())
            except Exception as exc:
                errors.append(str(exc))

        by_symbol: dict[str, dict] = {}
        for row in collected:
            symbol = str(row.get("symbol") or "").strip().upper()
            if not symbol:
                continue
            previous = by_symbol.get(symbol)
            if not previous:
                by_symbol[symbol] = row
                continue
            merged = {**previous, **row}
            merged["trading_value"] = max(
                self._to_float(previous.get("trading_value")),
                self._to_float(row.get("trading_value")),
            )
            merged["trading_volume"] = max(
                self._to_float(previous.get("trading_volume")),
                self._to_float(row.get("trading_volume")),
            )
            by_symbol[symbol] = merged

        rows = list(by_symbol.values())
        rows.sort(key=lambda row: row.get("trading_value", 0), reverse=True)
        if not rows and errors:
            raise Exception("; ".join(errors))
        return rows

    def get_balance(self) -> dict:
        _enforce_kis_mock_rate_limit(self.env)
        url = f"{self.base_url}/uapi/domestic-stock/v1/trading/inquire-balance"
        token = self._get_cached_token()
        headers = {
            "authorization": f"Bearer {token}",
            "appkey": self.appkey,
            "appsecret": self.appsecret,
            "tr_id": self.balance_tr_id
        }
        params = {
            "CANO": self.cano,
            "ACNT_PRDT_CD": self.acnt_prdt_cd,
            "AFHR_FLPR_YN": "N",
            "OFL_YN": "",
            "FNCG_AMT_AUTO_RDPT_YN": "N",
            "PRCS_DVSN": "01",
            "INQR_DVSN": "02",
            "UNPR_DVSN": "01",
            "FUND_STTL_ICLD_YN": "N",
            "FCTS_DVSN": "00",
            "CTX_AREA_FK100": "",
            "CTX_AREA_NK100": ""
        }
        output1 = []
        output2 = []

        # KIS 잔고 응답은 보유 종목이 많으면 CTX_AREA 토큰으로 나뉘어 내려올 수 있습니다.
        for _ in range(10):
            res = requests.get(url, headers=headers, params=params, timeout=10)
            if res.status_code != 200:
                raise Exception(f"KIS get_balance failed: {res.text}")

            data = res.json()
            if data.get("rt_cd") != "0":
                raise Exception(f"KIS get_balance error: {data.get('msg1')}")

            page_output1 = data.get("output1", []) or []
            page_output2 = data.get("output2", []) or []
            output1.extend(page_output1)
            if page_output2:
                output2 = page_output2

            next_fk100 = str(data.get("ctx_area_fk100") or data.get("CTX_AREA_FK100") or "").strip()
            next_nk100 = str(data.get("ctx_area_nk100") or data.get("CTX_AREA_NK100") or "").strip()
            tr_cont = str(res.headers.get("tr_cont") or res.headers.get("Tr_Cont") or "").upper()

            if not next_fk100 and not next_nk100:
                break
            if tr_cont and tr_cont not in {"M", "F"}:
                break

            params["CTX_AREA_FK100"] = next_fk100
            params["CTX_AREA_NK100"] = next_nk100
        
        holdings = []
        for stock in output1:
            try:
                qty = float(stock.get("hldg_qty", 0))
            except (ValueError, TypeError):
                qty = 0.0
                
            if qty <= 0:
                continue
            
            symbol = stock.get("pdno", "")
            name = stock.get("prdt_name", "")
            try:
                avg_price = float(stock.get("pchs_avg_pric", 0))
                current_price = float(stock.get("prpr", 0))
                profit = float(stock.get("evlu_pfls_amt", 0))
                profit_rate = float(stock.get("evlu_pfls_rt", 0))
            except (ValueError, TypeError):
                avg_price = 0.0
                current_price = 0.0
                profit = 0.0
                profit_rate = 0.0
            
            holdings.append({
                "symbol": symbol,
                "name": name,
                "qty": qty,
                "avg_price": avg_price,
                "current_price": current_price,
                "profit": profit,
                "profit_rate": profit_rate
            })
            
        total_eval = 0.0
        available_cash = 0.0
        if len(output2) > 0:
            summary = output2[0]
            try:
                total_eval = float(summary.get("tot_evlu_amt", 0))
                available_cash = float(summary.get("dnca_tot_amt", 0))
            except (ValueError, TypeError):
                pass
                
        return {
            "total_evaluation": total_eval,
            "available_cash": available_cash,
            "available_cash_currency": "KRW",
            "available_cash_supported": True,
            "currency": "KRW",
            "holdings": holdings
        }

    def place_order(self, symbol: str, qty: float, side: str, ord_type: str, price: float = None) -> dict:
        """
        주식 현금 주문을 전송합니다.
        :param symbol: 종목코드 (예: "005930")
        :param qty: 주문 수량
        :param side: 주문 방향 ("BUY" 또는 "SELL")
        :param ord_type: 호가 구분 ("LIMIT" 또는 "MARKET")
        :param price: 주문 단가 (LIMIT일 때 필수, MARKET일 때는 0 또는 생략 가능)
        """
        _enforce_kis_mock_rate_limit(self.env)
        url = f"{self.base_url}/uapi/domestic-stock/v1/trading/order-cash"
        token = self._get_cached_token()
        
        # side ("BUY"/"SELL") 에 따른 tr_id 셋업
        tr_id = self.buy_tr_id if side.upper() == "BUY" else self.sell_tr_id
        
        headers = {
            "content-type": "application/json",
            "authorization": f"Bearer {token}",
            "appkey": self.appkey,
            "appsecret": self.appsecret,
            "tr_id": tr_id
        }
        
        # 호가 구분 매핑 (LIMIT: "00", MARKET: "01")
        ord_dvsn = "00" if ord_type.upper() == "LIMIT" else "01"
        
        # 단가 보정 (MARKET이면 단가는 무조건 "0")
        order_price = int(price) if (ord_type.upper() == "LIMIT" and price is not None) else 0
        
        payload = {
            "CANO": self.cano,
            "ACNT_PRDT_CD": self.acnt_prdt_cd,
            "PDNO": symbol,
            "ORD_DVSN": ord_dvsn,
            "ORD_QTY": str(int(qty)),
            "ORD_UNPR": str(order_price)
        }
        
        res = requests.post(url, json=payload, headers=headers, timeout=10)
        if res.status_code != 200:
            if is_market_closed_order_error(res.text):
                raise MarketClosedError()
            raise Exception(f"KIS place_order failed: {res.text}")
            
        data = res.json()
        if data.get("rt_cd") != "0":
            message = data.get("msg1")
            if is_market_closed_order_error(message):
                raise MarketClosedError()
            raise Exception(f"KIS place_order error: {message}")
            
        output = data.get("output", {})
        return {
            "order_id": output.get("ODNO", ""),
            "order_org_no": output.get("KRX_FWDG_ORD_ORGNO", ""),
            "status": "ORDERED",
            "raw": data
        }

    def get_modifiable_orders(self) -> list[dict]:
        """
        KIS 국내주식 정정/취소 가능 주문 목록을 조회합니다.
        """
        _enforce_kis_mock_rate_limit(self.env)
        url = f"{self.base_url}/uapi/domestic-stock/v1/trading/inquire-psbl-rvsecncl"
        token = self._get_cached_token()
        headers = {
            "content-type": "application/json",
            "authorization": f"Bearer {token}",
            "appkey": self.appkey,
            "appsecret": self.appsecret,
            "tr_id": "TTTC8036R" if self.env == "REAL" else "VTTC8036R",
        }
        params = {
            "CANO": self.cano,
            "ACNT_PRDT_CD": self.acnt_prdt_cd,
            "INQR_DVSN_1": "0",
            "INQR_DVSN_2": "0",
            "CTX_AREA_FK100": "",
            "CTX_AREA_NK100": "",
        }
        orders = []

        for _ in range(10):
            res = requests.get(url, headers=headers, params=params, timeout=10)
            if res.status_code != 200:
                raise Exception(f"KIS modifiable orders failed: {res.text}")

            data = res.json()
            if data.get("rt_cd") != "0":
                raise Exception(f"KIS modifiable orders error: {data.get('msg1')}")

            page_orders = data.get("output", []) or data.get("output1", []) or []
            if isinstance(page_orders, dict):
                page_orders = [page_orders]

            for row in page_orders:
                order_id = str(row.get("odno") or row.get("ODNO") or row.get("orgn_odno") or "").strip()
                order_org_no = str(
                    row.get("ord_gno_brno")
                    or row.get("KRX_FWDG_ORD_ORGNO")
                    or row.get("krx_fwdg_ord_orgno")
                    or ""
                ).strip()
                order_qty = self._to_float(row.get("ord_qty") or row.get("ORD_QTY"))
                executed_qty = self._to_float(row.get("tot_ccld_qty") or row.get("TOT_CCLD_QTY"))
                remaining_qty = self._to_float(
                    row.get("psbl_qty")
                    or row.get("rvse_cncl_psbl_qty")
                    or row.get("nccs_qty")
                    or row.get("rmn_qty")
                )
                if remaining_qty <= 0 and order_qty > 0:
                    remaining_qty = max(order_qty - executed_qty, 0)

                orders.append({
                    "order_id": order_id,
                    "order_org_no": order_org_no,
                    "symbol": str(row.get("pdno") or row.get("PDNO") or "").strip(),
                    "name": row.get("prdt_name") or row.get("PRDT_NAME") or "",
                    "order_qty": order_qty,
                    "executed_qty": executed_qty,
                    "remaining_qty": remaining_qty,
                    "raw": row,
                })

            next_fk100 = str(data.get("ctx_area_fk100") or data.get("CTX_AREA_FK100") or "").strip()
            next_nk100 = str(data.get("ctx_area_nk100") or data.get("CTX_AREA_NK100") or "").strip()
            tr_cont = str(res.headers.get("tr_cont") or res.headers.get("Tr_Cont") or "").upper()
            if not next_fk100 and not next_nk100:
                break
            if tr_cont and tr_cont not in {"M", "F"}:
                break
            params["CTX_AREA_FK100"] = next_fk100
            params["CTX_AREA_NK100"] = next_nk100

        return orders

    def get_modifiable_order(self, order_id: str, order_org_no: str = "") -> dict:
        """
        특정 원주문의 정정/취소 가능 여부와 미체결 잔량을 반환합니다.
        """
        target_order_id = str(order_id or "").strip()
        target_org_no = str(order_org_no or "").strip()
        for order in self.get_modifiable_orders():
            same_order = order.get("order_id") == target_order_id
            same_org = not target_org_no or not order.get("order_org_no") or order.get("order_org_no") == target_org_no
            if same_order and same_org:
                return {**order, "is_modifiable": order.get("remaining_qty", 0) > 0}

        return {
            "order_id": target_order_id,
            "order_org_no": target_org_no,
            "remaining_qty": 0.0,
            "is_modifiable": False,
            "raw": {},
        }

    def _modify_or_cancel_order(
        self,
        order_id: str,
        order_org_no: str = "",
        action: str = "CANCEL",
        price: float | None = None,
        quantity: float | None = None,
        ord_type: str = "LIMIT",
    ) -> dict:
        """
        KIS 국내주식 주문 정정/취소 요청을 전송합니다.
        action은 CANCEL 또는 MODIFY를 사용합니다.
        """
        _enforce_kis_mock_rate_limit(self.env)
        if not order_id:
            raise ValueError("KIS 원주문번호가 필요합니다.")

        action_upper = action.upper()
        if action_upper not in ("CANCEL", "MODIFY"):
            raise ValueError("지원하지 않는 KIS 주문 액션입니다.")
        if action_upper == "MODIFY" and price is None and quantity is None:
            raise ValueError("정정할 가격 또는 수량이 필요합니다.")

        url = f"{self.base_url}/uapi/domestic-stock/v1/trading/order-rvsecncl"
        token = self._get_cached_token()
        headers = {
            "content-type": "application/json",
            "authorization": f"Bearer {token}",
            "appkey": self.appkey,
            "appsecret": self.appsecret,
            "tr_id": self.modify_cancel_tr_id,
        }

        ord_dvsn = "00" if ord_type.upper() == "LIMIT" else "01"
        order_price = int(price) if price is not None else 0
        order_qty = int(quantity) if quantity is not None else 0

        payload = {
            "CANO": self.cano,
            "ACNT_PRDT_CD": self.acnt_prdt_cd,
            "KRX_FWDG_ORD_ORGNO": order_org_no or "",
            "ORGN_ODNO": order_id,
            "ORD_DVSN": ord_dvsn,
            "RVSE_CNCL_DVSN_CD": "01" if action_upper == "MODIFY" else "02",
            "ORD_QTY": str(order_qty),
            "ORD_UNPR": str(order_price),
            "QTY_ALL_ORD_YN": "Y" if action_upper == "CANCEL" and quantity is None else "N",
        }

        res = requests.post(url, json=payload, headers=headers, timeout=10)
        if res.status_code != 200:
            raise Exception(f"KIS order {action_upper.lower()} failed: {res.text}")

        data = res.json()
        if data.get("rt_cd") != "0":
            raise Exception(f"KIS order {action_upper.lower()} error: {data.get('msg1')}")

        output = data.get("output", {})
        return {
            "order_id": output.get("ODNO", order_id),
            "order_org_no": output.get("KRX_FWDG_ORD_ORGNO", order_org_no or ""),
            "status": "MODIFIED" if action_upper == "MODIFY" else "CANCELED",
            "raw": data,
        }

    def cancel_order(self, order_id: str, order_org_no: str = "", quantity: float | None = None) -> dict:
        """
        KIS 국내주식 미체결 주문을 취소합니다.
        """
        return self._modify_or_cancel_order(
            order_id=order_id,
            order_org_no=order_org_no,
            action="CANCEL",
            quantity=quantity,
        )

    def modify_order(
        self,
        order_id: str,
        order_org_no: str = "",
        price: float | None = None,
        quantity: float | None = None,
        ord_type: str = "LIMIT",
    ) -> dict:
        """
        KIS 국내주식 미체결 주문을 정정합니다.
        """
        return self._modify_or_cancel_order(
            order_id=order_id,
            order_org_no=order_org_no,
            action="MODIFY",
            price=price,
            quantity=quantity,
            ord_type=ord_type,
        )

    def get_daily_order_executions(
        self,
        start_date: str | None = None,
        end_date: str | None = None,
        symbol: str = "",
        order_id: str = "",
    ) -> list[dict]:
        """
        KIS 국내주식 계좌 일별 주문체결 내역을 조회합니다.
        """
        _enforce_kis_mock_rate_limit(self.env)
        today = datetime.now(KST).strftime("%Y%m%d")
        start = start_date or today
        end = end_date or today
        url = f"{self.base_url}/uapi/domestic-stock/v1/trading/inquire-daily-ccld"
        token = self._get_cached_token()
        headers = {
            "content-type": "application/json",
            "authorization": f"Bearer {token}",
            "appkey": self.appkey,
            "appsecret": self.appsecret,
            "tr_id": "TTTC0081R" if self.env == "REAL" else "VTTC0081R",
        }
        params = {
            "CANO": self.cano,
            "ACNT_PRDT_CD": self.acnt_prdt_cd,
            "INQR_STRT_DT": start,
            "INQR_END_DT": end,
            "SLL_BUY_DVSN_CD": "00",
            "INQR_DVSN": "00",
            "PDNO": symbol or "",
            "CCLD_DVSN": "00",
            "ORD_GNO_BRNO": "",
            "ODNO": order_id or "",
            "INQR_DVSN_3": "00",
            "INQR_DVSN_1": "",
            "CTX_AREA_FK100": "",
            "CTX_AREA_NK100": "",
        }
        executions = []

        for _ in range(10):
            res = requests.get(url, headers=headers, params=params, timeout=10)
            if res.status_code != 200:
                raise Exception(f"KIS daily executions failed: {res.text}")

            data = res.json()
            if data.get("rt_cd") != "0":
                raise Exception(f"KIS daily executions error: {data.get('msg1')}")

            page_rows = data.get("output1", []) or data.get("output", []) or []
            if isinstance(page_rows, dict):
                page_rows = [page_rows]

            for row in page_rows:
                row_order_id = str(row.get("odno") or row.get("ODNO") or "").strip()
                row_symbol = str(row.get("pdno") or row.get("PDNO") or "").strip()
                order_qty = self._to_float(row.get("ord_qty") or row.get("ORD_QTY"))
                executed_qty = self._to_float(
                    row.get("tot_ccld_qty")
                    or row.get("TOT_CCLD_QTY")
                    or row.get("ccld_qty")
                    or row.get("CCLD_QTY")
                )
                remaining_qty = self._to_float(row.get("nccs_qty") or row.get("NCCS_QTY"))
                avg_price = self._to_float(
                    row.get("avg_prvs")
                    or row.get("AVG_PRVS")
                    or row.get("ord_unpr")
                    or row.get("ORD_UNPR")
                )
                cancel_yn = str(row.get("cncl_yn") or row.get("CNCL_YN") or "").upper()

                executions.append({
                    "order_id": row_order_id,
                    "symbol": row_symbol,
                    "name": row.get("prdt_name") or row.get("PRDT_NAME") or "",
                    "side_code": row.get("sll_buy_dvsn_cd") or row.get("SLL_BUY_DVSN_CD") or "",
                    "order_qty": order_qty,
                    "executed_qty": executed_qty,
                    "remaining_qty": remaining_qty,
                    "avg_price": avg_price,
                    "canceled": cancel_yn == "Y",
                    "raw": row,
                })

            next_fk100 = str(data.get("ctx_area_fk100") or data.get("CTX_AREA_FK100") or "").strip()
            next_nk100 = str(data.get("ctx_area_nk100") or data.get("CTX_AREA_NK100") or "").strip()
            tr_cont = str(res.headers.get("tr_cont") or res.headers.get("Tr_Cont") or "").upper()
            if not next_fk100 and not next_nk100:
                break
            if tr_cont and tr_cont not in {"M", "F"}:
                break
            params["CTX_AREA_FK100"] = next_fk100
            params["CTX_AREA_NK100"] = next_nk100

        return executions

    def get_order_execution_status(self, order_id: str, symbol: str = "", lookback_days: int = 7) -> dict:
        """
        주문번호 기준으로 계좌 주문체결 상태를 조회합니다.
        """
        end_dt = datetime.now(KST)
        start_dt = end_dt - timedelta(days=lookback_days)
        executions = self.get_daily_order_executions(
            start_date=start_dt.strftime("%Y%m%d"),
            end_date=end_dt.strftime("%Y%m%d"),
            symbol=symbol,
            order_id=order_id,
        )
        target_order_id = str(order_id or "").strip()
        target_symbol = str(symbol or "").strip().upper()
        matched = [
            item for item in executions
            if (not target_order_id or item.get("order_id") == target_order_id)
            and (not target_symbol or str(item.get("symbol") or "").upper() == target_symbol)
        ]
        if not matched:
            return {
                "order_id": target_order_id,
                "symbol": target_symbol,
                "status": "UNKNOWN",
                "order_qty": 0.0,
                "executed_qty": 0.0,
                "remaining_qty": 0.0,
                "canceled": False,
                "raw": [],
            }

        order_qty = max((item.get("order_qty") or 0) for item in matched)
        executed_qty = sum(item.get("executed_qty") or 0 for item in matched)
        remaining_qty = max(order_qty - executed_qty, 0)
        canceled = any(item.get("canceled") for item in matched)
        if canceled:
            status = "CANCELED"
        elif order_qty > 0 and executed_qty >= order_qty:
            status = "EXECUTED"
        elif executed_qty > 0:
            status = "PARTIALLY_FILLED"
        else:
            status = "ORDERED"

        return {
            "order_id": target_order_id,
            "symbol": target_symbol,
            "status": status,
            "order_qty": order_qty,
            "executed_qty": executed_qty,
            "remaining_qty": remaining_qty,
            "canceled": canceled,
            "raw": matched,
        }

    def get_order_status(self, order_id: str) -> dict:
        return {
            "order_id": order_id,
            "status": "ORDERED",
            "qty": 0.0,
            "executed_qty": 0.0,
            "raw": {}
        }

    def get_candles(self, symbol: str, interval: str = "D", count: int = 120) -> list:
        """
        국내주식 기간별 시세(캔들)를 조회합니다.
        :param symbol: 종목코드 (예: "005930")
        :param interval: 기간 구분 ("D": 일, "W": 주, "M": 월)
        :param count: 가져올 캔들 개수
        """
        _enforce_kis_mock_rate_limit(self.env)
        url = f"{self.base_url}/uapi/domestic-stock/v1/quotations/inquire-daily-itemchartprice"
        token = self._get_cached_token()
        # 모의투자 및 실전투자 모두 FHKST03010100을 사용합니다.
        tr_id = "FHKST03010100"
        headers = {
            "content-type": "application/json",
            "authorization": f"Bearer {token}",
            "appkey": self.appkey,
            "appsecret": self.appsecret,
            "tr_id": tr_id
        }
        
        # 날짜 범위 설정 (오늘부터 count * 1.5 일 전까지 조회)
        end_date = datetime.now().strftime("%Y%m%d")
        start_date = (datetime.now() - timedelta(days=int(count * 1.5))).strftime("%Y%m%d")
        
        params = {
            "FID_COND_MRKT_DIV_CODE": "J",
            "FID_INPUT_ISCD": symbol,
            "FID_INPUT_DATE_1": start_date,
            "FID_INPUT_DATE_2": end_date,
            "FID_PERIOD_DIV_CODE": interval.upper(),
            "FID_ORG_ADJ_PRC": "0"
        }
        
        res = requests.get(url, headers=headers, params=params, timeout=10)
        if res.status_code != 200:
            raise Exception(f"KIS get_candles failed: {res.text}")
            
        data = res.json()
        if data.get("rt_cd") != "0":
            raise Exception(f"KIS get_candles error: {data.get('msg1')}")
            
        output2 = data.get("output2", [])
        candles = []
        for item in output2:
            date_str = item.get("stck_bsop_date", "")
            if not date_str:
                continue
            # YYYYMMDD -> YYYY-MM-DD 로 변환
            formatted_date = f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]}"
            try:
                candles.append({
                    "time": formatted_date,
                    "open": float(item.get("stck_oprc", 0)),
                    "high": float(item.get("stck_hgpr", 0)),
                    "low": float(item.get("stck_lwpr", 0)),
                    "close": float(item.get("stck_clpr", 0)),
                    "volume": float(item.get("acml_vol", 0))
                })
            except (ValueError, TypeError):
                pass
                
        # API 응답은 최신순(역순)이므로 과거순으로 정렬
        candles.reverse()
        return candles[-count:]

    def get_minute_candles(self, symbol: str, interval_minutes: int, count: int = 120) -> list:
        """
        국내주식 당일 분봉 데이터를 조회하여 리샘플링 후 반환합니다.
        :param symbol: 종목코드 (예: "005930")
        :param interval_minutes: 분봉 간격 (1, 5, 15, 30, 60 등)
        :param count: 가져올 최종 캔들 개수
        """
        _enforce_kis_mock_rate_limit(self.env)
        url = f"{self.base_url}/uapi/domestic-stock/v1/quotations/inquire-time-itemchartprice"
        token = self._get_cached_token()
        headers = {
            "content-type": "application/json; charset=utf-8",
            "authorization": f"Bearer {token}",
            "appkey": self.appkey,
            "appsecret": self.appsecret,
            "tr_id": "FHKST03010200"
        }
        
        raw_candles = []
        today_str = datetime.now(KST).strftime("%Y%m%d")
        
        # 장 중이 아니면 15시 30분을 조회 기준으로 설정하여 안전하게 오늘 정규장 분봉을 가져옴
        now_kst = datetime.now(KST)
        current_hour = now_kst.hour
        current_minute = now_kst.minute
        if current_hour > 15 or (current_hour == 15 and current_minute > 30):
            input_time = "153000"
        else:
            input_time = now_kst.strftime("%H%M%S")
            
        # 필요한 1분봉 개수 계산 (정규장 최대 390분으로 한계 설정)
        needed_1m_count = interval_minutes * count
        max_candles_to_fetch = min(needed_1m_count, 390)
        fetched_count = 0
        
        # 필요한 호출 횟수 동적 계산 (최대 13회)
        max_calls = min(int(max_candles_to_fetch / 30) + 1, 13)
        sleep_time = 0.35 if self.env == "MOCK" else 0.05
        
        for _ in range(max_calls):
            if fetched_count >= max_candles_to_fetch:
                break
                
            params = {
                "FID_COND_MRKT_DIV_CODE": "J",
                "FID_INPUT_ISCD": symbol,
                "FID_INPUT_HOUR_1": input_time,
                "FID_PW_DATA_INCU_YN": "Y",
                "FID_ETC_CLS_CODE": ""
            }
            
            res = requests.get(url, headers=headers, params=params, timeout=10)
            if res.status_code != 200:
                break
                
            data = res.json()
            if data.get("rt_cd") != "0":
                break
                
            output2 = data.get("output2", [])
            if not output2:
                break
                
            for item in output2:
                time_str = item.get("stck_cntg_hour")  # "HHMMSS"
                date_str = item.get("stck_bsop_date", today_str)  # "YYYYMMDD"
                if not time_str or not date_str:
                    continue
                    
                try:
                    dt_obj = datetime.strptime(f"{date_str}{time_str}", "%Y%m%d%H%M%S")
                    dt_obj = dt_obj.replace(tzinfo=KST)
                    ts = int(dt_obj.timestamp())
                except ValueError:
                    continue
                    
                raw_candles.append({
                    "timestamp": ts,
                    "open": float(item.get("stck_oprc", 0)),
                    "high": float(item.get("stck_hgpr", 0)),
                    "low": float(item.get("stck_lwpr", 0)),
                    "close": float(item.get("stck_prpr", 0)),
                    "volume": float(item.get("cntg_vol", 0))
                })
                
            fetched_count = len(raw_candles)
            
            # 다음 페이지 조회를 위해 1분 차감된 시간 설정
            last_time = output2[-1].get("stck_cntg_hour")
            if not last_time:
                break
                
            try:
                dt_last = datetime.strptime(last_time, "%H%M%S")
                dt_next = dt_last - timedelta(minutes=1)
                input_time = dt_next.strftime("%H%M%S")
            except ValueError:
                break
                
            time.sleep(sleep_time)
            
        if not raw_candles:
            return []
            
        # 중복 제거 및 시간 순 정렬 (1분 차트가 일그러지는 현상 방지 핵심)
        seen = set()
        unique_candles = []
        for c in raw_candles:
            if c["timestamp"] not in seen:
                seen.add(c["timestamp"])
                unique_candles.append(c)
        unique_candles.sort(key=lambda x: x["timestamp"])
        
        # 1분봉은 그대로 포맷 맞춰서 반환
        if interval_minutes == 1:
            formatted = []
            for c in unique_candles:
                formatted.append({
                    "time": c["timestamp"],
                    "open": c["open"],
                    "high": c["high"],
                    "low": c["low"],
                    "close": c["close"],
                    "volume": c["volume"]
                })
            return formatted[-count:]
            
        # 리샘플링 진행
        buckets = {}
        for c in unique_candles:
            bucket_ts = _floor_kst_bucket_timestamp(c["timestamp"], interval_minutes)
            if bucket_ts not in buckets:
                buckets[bucket_ts] = []
            buckets[bucket_ts].append(c)
            
        resampled_candles = []
        for b_ts, c_list in sorted(buckets.items()):
            resampled_candles.append({
                "time": b_ts,
                "open": c_list[0]["open"],
                "high": max(x["high"] for x in c_list),
                "low": min(x["low"] for x in c_list),
                "close": c_list[-1]["close"],
                "volume": sum(x["volume"] for x in c_list)
            })
            
        return resampled_candles[-count:]

    def get_orderbook(self, symbol: str) -> dict:
        """
        국내주식 호가 조회를 수행합니다. 매도/매수 10단계 호가 및 잔량을 리턴합니다.
        """
        _enforce_kis_mock_rate_limit(self.env)
        url = f"{self.base_url}/uapi/domestic-stock/v1/quotations/inquire-asking-price-exp-ccn"
        token = self._get_cached_token()
        headers = {
            "content-type": "application/json; charset=utf-8",
            "authorization": f"Bearer {token}",
            "appkey": self.appkey,
            "appsecret": self.appsecret,
            "tr_id": "FHKST01010200"
        }
        params = {
            "FID_COND_MRKT_DIV_CODE": "J",
            "FID_INPUT_ISCD": symbol
        }
        res = requests.get(url, headers=headers, params=params, timeout=10)
        if res.status_code != 200:
            raise Exception(f"KIS 호가 조회 실패: {res.text}")
            
        data = res.json()
        if data.get("rt_cd") != "0":
            raise Exception(f"KIS 호가 조회 에러: {data.get('msg1')}")
            
        return data

    def get_trades(self, symbol: str) -> dict:
        """
        국내주식 실시간 체결 조회를 수행합니다. (최근 체결 30건 등)
        """
        _enforce_kis_mock_rate_limit(self.env)
        url = f"{self.base_url}/uapi/domestic-stock/v1/quotations/inquire-time-itemconclusion"
        token = self._get_cached_token()
        headers = {
            "content-type": "application/json; charset=utf-8",
            "authorization": f"Bearer {token}",
            "appkey": self.appkey,
            "appsecret": self.appsecret,
            "tr_id": "FHKST01010300"
        }
        params = {
            "FID_COND_MRKT_DIV_CODE": "J",
            "FID_INPUT_ISCD": symbol
        }
        res = requests.get(url, headers=headers, params=params, timeout=10)
        if res.status_code != 200:
            raise Exception(f"KIS 체결 조회 실패: {res.text}")
            
        data = res.json()
        if data.get("rt_cd") != "0":
            raise Exception(f"KIS 체결 조회 에러: {data.get('msg1')}")
            
        return data
