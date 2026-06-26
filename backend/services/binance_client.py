import hmac
import hashlib
import time
import requests
from urllib.parse import urlencode

class BinanceClient:
    """
    바이낸스 API 연동 및 연결 검증을 담당하는 클라이언트 클래스입니다.
    """
    def __init__(self, api_key: str, secret_key: str):
        self.api_key = api_key
        self.secret_key = secret_key.encode('utf-8')
        self.base_url = "https://api.binance.com"

    def _sign(self, query_params: dict) -> str:
        """
        쿼리 파라미터를 기반으로 HMAC-SHA256 signature를 생성합니다.
        """
        query_string = urlencode(query_params)
        signature = hmac.new(
            self.secret_key,
            query_string.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
        return signature

    def _get_tickers(self) -> dict:
        """
        바이낸스 마켓의 모든 코인 현재가(Ticker) 정보를 조회합니다.
        """
        url = f"{self.base_url}/api/v3/ticker/price"
        try:
            res = requests.get(url, timeout=5)
            if res.status_code == 200:
                data = res.json()
                tickers = {}
                for t in data:
                    symbol = t.get("symbol", "").upper()
                    tickers[symbol] = float(t.get("price", 0.0))
                return tickers
        except Exception:
            pass
        return {}

    def get_balance(self) -> dict:
        """
        바이낸스 현물 계좌 정보를 조회하여 연결 상태를 검증하고 자산 현황을 반환합니다.
        """
        url = f"{self.base_url}/api/v3/account"
        
        # 바이낸스 API 호출에 필요한 타임스탬프와 signature 생성
        params = {
            "timestamp": int(time.time() * 1000),
            "recvWindow": 60000
        }
        params["signature"] = self._sign(params)

        headers = {
            "X-MBX-APIKEY": self.api_key
        }

        res = requests.get(url, headers=headers, params=params, timeout=5)

        if res.status_code != 200:
            raise Exception(f"바이낸스 API 호출 실패 (상태 코드 {res.status_code}): {res.text}")

        data = res.json()

        # 자산 평가를 위한 Tickers(현재가) 정보 조회
        tickers = self._get_tickers()

        balances = data.get("balances", [])
        holdings = []
        total_eval = 0.0
        available_cash = 0.0

        for item in balances:
            asset = item.get("asset", "").upper()
            try:
                free_val = float(item.get("free", 0.0))
                locked_val = float(item.get("locked", 0.0))
            except (ValueError, TypeError):
                free_val = 0.0
                locked_val = 0.0

            total_qty = free_val + locked_val
            if total_qty <= 0.000001:  # 소액 자산 제외
                continue

            if asset == "USDT" or asset == "BUSD" or asset == "USDC":
                # 스테이블코인은 현금성 자산으로 판단
                if asset == "USDT":
                    available_cash = free_val
                total_eval += total_qty
            else:
                # USDT 페어로 가치 환산
                pair = f"{asset}USDT"
                curr_price = tickers.get(pair, 0.0)
                eval_price = curr_price * total_qty
                total_eval += eval_price

                holdings.append({
                    "symbol": asset,
                    "name": asset,
                    "qty": total_qty,
                    "avg_price": 0.0,  # 바이낸스 잔고 API는 평균 매수가를 제공하지 않음
                    "current_price": curr_price,
                    "profit": 0.0,
                    "profit_rate": 0.0
                })

        return {
            "total_evaluation": total_eval,
            "available_cash": available_cash,
            "currency": "USD",
            "holdings": holdings,
            "raw": data
        }
