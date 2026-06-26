import os
import json
import time
import requests
from datetime import datetime, timedelta, timezone
from backend.services.exchange_client import ExchangeClient

KST = timezone(timedelta(hours=9))

TOKEN_CACHE_FILE = ".kis_token_cache.json"

class KISClient(ExchangeClient):
    def __init__(self, appkey: str, appsecret: str, cano: str, acnt_prdt_cd: str = "01", env: str = "MOCK"):
        self.appkey = appkey
        self.appsecret = appsecret
        self.cano = cano
        self.acnt_prdt_cd = acnt_prdt_cd
        self.env = env.upper()
        
        if self.env == "REAL":
            self.base_url = "https://openapi.koreainvestment.com:17207"
            self.balance_tr_id = "TTTC8434R"
            self.buy_tr_id = "TTTC0802U"
            self.sell_tr_id = "TTTC0801U"
        else:
            self.base_url = "https://openapivts.koreainvestment.com:29443"
            self.balance_tr_id = "VTTC8434R"
            self.buy_tr_id = "VTTC0802U"
            self.sell_tr_id = "VTTC0801U"

    def _get_cached_token(self) -> str:
        """
        로컬 JSON 캐시에서 Access Token을 가져옵니다.
        만료되었거나 캐시가 존재하지 않으면 새로 발급을 요청하고 캐시를 갱신합니다.
        """
        cache = {}
        if os.path.exists(TOKEN_CACHE_FILE):
            try:
                with open(TOKEN_CACHE_FILE, "r") as f:
                    cache = json.load(f)
            except Exception:
                pass
                
        key_cache = cache.get(self.appkey, {})
        token = key_cache.get("access_token")
        expired_at_str = key_cache.get("expired_at")
        
        if token and expired_at_str:
            try:
                expired_at = datetime.strptime(expired_at_str, "%Y-%m-%d %H:%M:%S")
                if (expired_at - datetime.now()).total_seconds() > 300:
                    return token
            except Exception:
                pass
                
        token_data = self._request_new_token()
        new_token = token_data["access_token"]
        
        expired_at_raw = token_data.get("access_token_token_expired")
        if not expired_at_raw:
            expired_at_raw = datetime.fromtimestamp(time.time() + 86400).strftime("%Y-%m-%d %H:%M:%S")
            
        cache[self.appkey] = {
            "access_token": new_token,
            "expired_at": expired_at_raw
        }
        try:
            with open(TOKEN_CACHE_FILE, "w") as f:
                json.dump(cache, f, indent=2)
        except Exception:
            pass
            
        return new_token

    def _request_new_token(self) -> dict:
        url = f"{self.base_url}/oauth2/tokenP"
        payload = {
            "grant_type": "client_credentials",
            "appkey": self.appkey,
            "appsecret": self.appsecret
        }
        headers = {
            "content-type": "application/json"
        }
        res = requests.post(url, json=payload, headers=headers)
        if res.status_code != 200:
            raise Exception(f"KIS Token issuance failed: {res.text}")
        return res.json()

    def get_price(self, symbol: str) -> dict:
        url = f"{self.base_url}/uapi/domestic-stock/v1/quotations/inquire-price"
        token = self._get_cached_token()
        headers = {
            "authorization": f"Bearer {token}",
            "appkey": self.appkey,
            "appsecret": self.appsecret,
            "tr_id": "FHKST01010100"
        }
        params = {
            "FID_COND_MRKT_DIV_CODE": "J",
            "FID_INPUT_ISCD": symbol
        }
        res = requests.get(url, headers=headers, params=params)
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
        token = self._get_cached_token()
        headers = {
            "content-type": "application/json; charset=utf-8",
            "authorization": f"Bearer {token}",
            "appkey": self.appkey,
            "appsecret": self.appsecret,
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
        res = requests.get(url, headers=headers, params=params)
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

    def get_balance(self) -> dict:
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
        res = requests.get(url, headers=headers, params=params)
        if res.status_code != 200:
            raise Exception(f"KIS get_balance failed: {res.text}")
            
        data = res.json()
        if data.get("rt_cd") != "0":
            raise Exception(f"KIS get_balance error: {data.get('msg1')}")
            
        output1 = data.get("output1", [])
        output2 = data.get("output2", [])
        
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
        
        res = requests.post(url, json=payload, headers=headers)
        if res.status_code != 200:
            raise Exception(f"KIS place_order failed: {res.text}")
            
        data = res.json()
        if data.get("rt_cd") != "0":
            raise Exception(f"KIS place_order error: {data.get('msg1')}")
            
        output = data.get("output", {})
        return {
            "order_id": output.get("ODNO", ""),
            "status": "ORDERED",
            "raw": data
        }

    def get_order_status(self, order_id: str) -> dict:
        return {
            "order_id": order_id,
            "status": "EXECUTED",
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
        
        res = requests.get(url, headers=headers, params=params)
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
            
            res = requests.get(url, headers=headers, params=params)
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
        interval_seconds = interval_minutes * 60
        buckets = {}
        for c in unique_candles:
            bucket_ts = (c["timestamp"] // interval_seconds) * interval_seconds
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
        url = f"{self.base_url}/uapi/domestic-stock/v1/quotations/inquire-askprice"
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
        res = requests.get(url, headers=headers, params=params)
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
        url = f"{self.base_url}/uapi/domestic-stock/v1/quotations/inquire-ccld"
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
        res = requests.get(url, headers=headers, params=params)
        if res.status_code != 200:
            raise Exception(f"KIS 체결 조회 실패: {res.text}")
            
        data = res.json()
        if data.get("rt_cd") != "0":
            raise Exception(f"KIS 체결 조회 에러: {data.get('msg1')}")
            
        return data
