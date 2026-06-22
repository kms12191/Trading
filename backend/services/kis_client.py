import os
import json
import time
import requests
from datetime import datetime
from backend.services.exchange_client import ExchangeClient

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
        else:
            self.base_url = "https://openapivts.koreainvestment.com:29443"
            self.balance_tr_id = "VTTC8434R"

    def _get_cached_token(self) -> str:
        """
        Get access token from local JSON cache.
        If expired or doesn't exist, request a new one and update cache.
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
            "tr_id": "FNSW1111"
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
        except (ValueError, TypeError):
            current_price = 0.0
            change_rate = 0.0
            
        return {
            "current_price": current_price,
            "change_rate": change_rate,
            "raw": data
        }

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
        return {
            "order_id": "MOCK-ORDER-12345",
            "status": "ORDERED",
            "raw": { "symbol": symbol, "qty": qty, "side": side, "ord_type": ord_type }
        }

    def get_order_status(self, order_id: str) -> dict:
        return {
            "order_id": order_id,
            "status": "EXECUTED",
            "qty": 0.0,
            "executed_qty": 0.0,
            "raw": {}
        }
