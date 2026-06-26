import os
import json
import time
import uuid
import requests
from pathlib import Path
from datetime import datetime, timedelta, timezone
from backend.services.exchange_client import ExchangeClient

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
    def __init__(self, client_id: str, client_secret: str, account_seq: str = None, env: str = "MOCK"):
        self.client_id = client_id
        self.client_secret = client_secret
        self.account_seq = account_seq
        self.env = env.upper()
        self.base_url = "https://openapi.tossinvest.com"

    def _clear_token_cache(self):
        """
        DB 캐시 테이블에서 현재 exchange/env에 해당하는 토큰 정보를 강제 만료시킵니다.
        """
        from backend.services.token_cache_service import clear_db_token
        try:
            clear_db_token("TOSS", self.env)
        except Exception:
            pass

    def _get_cached_token(self) -> str:
        """
        Supabase DB의 token_caches 테이블에서 토스 Access Token을 가져옵니다.
        토큰이 만료되었거나 캐시가 없으면 새로 발급을 요청합니다.
        """
        from backend.services.token_cache_service import get_db_token, set_db_token
        
        # DB에서 유효한 공용 토큰 획득 시도
        try:
            token = get_db_token("TOSS", self.env)
            if token:
                return token
        except Exception:
            pass

        # 토큰 새로 발급
        token_data = self._request_new_token()
        new_token = token_data["access_token"]
        expires_in = int(token_data.get("expires_in", 86400))

        # DB 캐시 테이블에 신규 토큰 저장 (Upsert)
        try:
            set_db_token("TOSS", self.env, new_token, expires_in)
        except Exception:
            pass

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
        res = requests.post(url, data=payload, headers=headers)
        if res.status_code != 200:
            err_data = {}
            try:
                err_data = res.json()
            except Exception:
                pass
            err_msg = err_data.get("error_description") or err_data.get("error") or res.text
            raise Exception(f"토스 토큰 발급 실패: {err_msg}")
        return res.json()

    def _get_accounts_impl(self) -> list:
        token = self._get_cached_token()
        url = f"{self.base_url}/api/v1/accounts"
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }
        res = requests.get(url, headers=headers)
        
        if res.status_code != 200:
            fallback_url = f"{self.base_url}/v1/accounts"
            res = requests.get(fallback_url, headers=headers)

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
        사용자의 계좌 목록 정보를 가져옵니다. (토큰 만료 시 재시도 포함)
        """
        try:
            return self._get_accounts_impl()
        except Exception as e:
            err_str = str(e).lower()
            if "invalid-token" in err_str or "invalid_token" in err_str or "unauthorized" in err_str or "401" in err_str:
                self._clear_token_cache()
                return self._get_accounts_impl()
            raise e

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
        res = requests.get(url, headers=headers)

        if res.status_code != 200:
            fallback_url = f"{self.base_url}/v1/accounts/holdings"
            res = requests.get(fallback_url, headers=headers)

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
        보유 자산 정보를 조회합니다. (토큰 만료 시 재시도 포함)
        """
        try:
            return self._get_balance_impl()
        except Exception as e:
            err_str = str(e).lower()
            if "invalid-token" in err_str or "invalid_token" in err_str or "unauthorized" in err_str or "401" in err_str:
                self._clear_token_cache()
                return self._get_balance_impl()
            raise e

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
            res = requests.get(url, headers=headers, params={"symbol": candidate}, timeout=15)
            if res.status_code != 200:
                res = requests.get(url, headers=headers, params={"symbols": candidate}, timeout=15)

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
                    candle_res = requests.get(
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
        현재가를 조회합니다. (토큰 만료 시 재시도 포함)
        """
        try:
            return self._get_price_impl(symbol)
        except Exception as e:
            err_str = str(e).lower()
            if "invalid-token" in err_str or "invalid_token" in err_str or "unauthorized" in err_str or "401" in err_str:
                self._clear_token_cache()
                return self._get_price_impl(symbol)
            raise e

    def _place_order_impl(self, symbol: str, qty: float, side: str, ord_type: str, price: float = None) -> dict:
        if self.env == "MOCK":
            return {
                "order_id": f"MOCK-TOSS-{int(time.time())}",
                "status": "ORDERED",
                "raw": {"symbol": symbol, "qty": qty, "side": side, "ord_type": ord_type}
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

        res = requests.post(url, json=payload, headers=headers)
        if res.status_code != 200:
            raise Exception(f"토스 주문 접수 실패: {res.text}")

        data = res.json()
        result = data.get("result", {})
        return {
            "order_id": result.get("orderId"),
            "status": result.get("status"),
            "raw": data
        }

    def place_order(self, symbol: str, qty: float, side: str, ord_type: str, price: float = None) -> dict:
        """
        주문을 접수합니다. (토큰 만료 시 재시도 포함)
        """
        try:
            return self._place_order_impl(symbol, qty, side, ord_type, price)
        except Exception as e:
            err_str = str(e).lower()
            if "invalid-token" in err_str or "invalid_token" in err_str or "unauthorized" in err_str or "401" in err_str:
                self._clear_token_cache()
                return self._place_order_impl(symbol, qty, side, ord_type, price)
            raise e

    def _get_order_status_impl(self, order_id: str) -> dict:
        token = self._get_cached_token()
        url = f"{self.base_url}/api/v1/orders/{order_id}"
        headers = {
            "Authorization": f"Bearer {token}",
            "X-Tossinvest-Account": self.account_seq,
            "Content-Type": "application/json"
        }
        res = requests.get(url, headers=headers)
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
        주문 상태를 조회합니다. (토큰 만료 시 재시도 포함)
        """
        try:
            return self._get_order_status_impl(order_id)
        except Exception as e:
            err_str = str(e).lower()
            if "invalid-token" in err_str or "invalid_token" in err_str or "unauthorized" in err_str or "401" in err_str:
                self._clear_token_cache()
                return self._get_order_status_impl(order_id)
            raise e

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
        res = requests.get(url, headers=headers, params=params)
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
        (토큰 만료 시 자동 재시도 포함)
        """
        normalized_interval = interval
        if interval in ("1d", "D", "day"):
            normalized_interval = "1d"
        elif interval in ("1m", "minute"):
            normalized_interval = "1m"

        # 1. 토스 네이티브 지원 주기인 경우 바로 호출
        if normalized_interval in ("1d", "1m"):
            try:
                return self._get_candles_impl(symbol, interval=normalized_interval, count=count)
            except Exception as e:
                err_str = str(e).lower()
                if "invalid-token" in err_str or "invalid_token" in err_str or "unauthorized" in err_str or "401" in err_str:
                    self._clear_token_cache()
                    return self._get_candles_impl(symbol, interval=normalized_interval, count=count)
                raise e

    def _get_exchange_rate_impl(self) -> float:
        token = self._get_cached_token()
        url = f"{self.base_url}/api/v1/exchange-rate"
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }
        params = {
            "baseCurrency": "USD",
            "quoteCurrency": "KRW"
        }
        res = requests.get(url, headers=headers, params=params)
        if res.status_code == 200:
            data = res.json()
            result = data.get("result", {})
            rate = result.get("rate") or result.get("basePrice") or result.get("exchangeRate") or result.get("price")
            if rate:
                return float(rate)
        return 1500.0

    def get_exchange_rate(self) -> float:
        """
        실시간 환율 정보를 조회합니다. (토큰 만료 시 재시도 포함)
        """
        try:
            return self._get_exchange_rate_impl()
        except Exception as e:
            err_str = str(e).lower()
            if "invalid-token" in err_str or "invalid_token" in err_str or "unauthorized" in err_str or "401" in err_str:
                self._clear_token_cache()
                try:
                    return self._get_exchange_rate_impl()
                except Exception:
                    pass
            return 1500.0

        # 2. 토스 미지원 주기인 경우 자체 리샘플링
        # 2-A. 분봉/시간봉 리샘플링 (5m, 15m, 30m, 1h, 60m 등)
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

    def _get_orderbook_impl(self, symbol: str) -> dict:
        token = self._get_cached_token()
        url = f"{self.base_url}/api/v1/orderbook"
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }
        res = requests.get(url, headers=headers, params={"symbol": symbol})
        if res.status_code != 200:
            raise Exception(f"토스 호가 조회 실패: {res.text}")
        return res.json()

    def get_orderbook(self, symbol: str) -> dict:
        """
        종목코드에 해당하는 호가 정보(Orderbook)를 가져옵니다. (토큰 만료 시 재시도 포함)
        """
        try:
            return self._get_orderbook_impl(symbol)
        except Exception as e:
            err_str = str(e).lower()
            if "invalid-token" in err_str or "invalid_token" in err_str or "unauthorized" in err_str or "401" in err_str:
                self._clear_token_cache()
                return self._get_orderbook_impl(symbol)
            raise e

    def _get_trades_impl(self, symbol: str) -> dict:
        token = self._get_cached_token()
        url = f"{self.base_url}/api/v1/trades"
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }
        res = requests.get(url, headers=headers, params={"symbol": symbol})
        if res.status_code != 200:
            raise Exception(f"토스 체결 조회 실패: {res.text}")
        return res.json()

    def get_trades(self, symbol: str) -> dict:
        """
        종목코드에 해당하는 실시간 체결 정보(Trades)를 가져옵니다. (토큰 만료 시 재시도 포함)
        """
        try:
            return self._get_trades_impl(symbol)
        except Exception as e:
            err_str = str(e).lower()
            if "invalid-token" in err_str or "invalid_token" in err_str or "unauthorized" in err_str or "401" in err_str:
                self._clear_token_cache()
                return self._get_trades_impl(symbol)
            raise e
