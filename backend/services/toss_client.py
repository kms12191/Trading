import os
import json
import time
import requests
from datetime import datetime, timedelta
from backend.services.exchange_client import ExchangeClient

TOSS_TOKEN_CACHE_FILE = ".toss_token_cache.json"

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

    def _get_cached_token(self) -> str:
        """
        로컬 캐시 파일에서 토스 Access Token을 가져옵니다.
        토큰이 만료되었거나 캐시가 없으면 새로 발급을 요청합니다.
        """
        cache = {}
        if os.path.exists(TOSS_TOKEN_CACHE_FILE):
            try:
                with open(TOSS_TOKEN_CACHE_FILE, "r") as f:
                    cache = json.load(f)
            except Exception:
                pass

        client_cache = cache.get(self.client_id, {})
        token = client_cache.get("access_token")
        expired_at_str = client_cache.get("expired_at")

        if token and expired_at_str:
            try:
                expired_at = datetime.strptime(expired_at_str, "%Y-%m-%d %H:%M:%S")
                # 만료 5분 전(300초) 이상 남아있는 경우에만 기존 토큰 사용
                if (expired_at - datetime.now()).total_seconds() > 300:
                    return token
            except Exception:
                pass

        # 토큰 새로 발급
        token_data = self._request_new_token()
        new_token = token_data["access_token"]
        expires_in = int(token_data.get("expires_in", 86400))

        expired_at = datetime.now() + timedelta(seconds=expires_in)
        cache[self.client_id] = {
            "access_token": new_token,
            "expired_at": expired_at.strftime("%Y-%m-%d %H:%M:%S")
        }

        try:
            with open(TOSS_TOKEN_CACHE_FILE, "w") as f:
                json.dump(cache, f, indent=2)
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
            # OAuth2 표준 에러 형식에 맞추어 예외 발생
            err_data = {}
            try:
                err_data = res.json()
            except Exception:
                pass
            err_msg = err_data.get("error_description") or err_data.get("error") or res.text
            raise Exception(f"토스 토큰 발급 실패: {err_msg}")
        return res.json()

    def get_accounts(self) -> list:
        """
        사용자의 계좌 목록 정보를 가져옵니다.
        """
        token = self._get_cached_token()
        url = f"{self.base_url}/api/v1/accounts"
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }
        res = requests.get(url, headers=headers)
        
        # /api/v1/accounts가 실패하는 경우 /v1/accounts로 폴백
        if res.status_code != 200:
            fallback_url = f"{self.base_url}/v1/accounts"
            res = requests.get(fallback_url, headers=headers)

        if res.status_code != 200:
            raise Exception(f"토스 계좌 목록 조회 실패 (상태 코드 {res.status_code}): {res.text}")

        data = res.json()
        
        # 토스증권 API의 에러 스키마 검증
        if "error" in data:
            err = data["error"]
            raise Exception(f"토스 계좌 조회 에러 [{err.get('code')}]: {err.get('message')} (Request ID: {err.get('requestId')})")

        # 토스증권 API는 주로 {"result": [...]} 또는 {"result": {"accounts": [...]}} 등의 형태를 가짐
        result = data.get("result", [])
        if isinstance(result, dict):
            accounts = result.get("accounts", [])
        else:
            accounts = result

        return accounts

    def get_balance(self) -> dict:
        """
        선택된 계좌의 보유 자산 정보를 조회하여 잔고 객체를 반환합니다.
        """
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

        # /api/v1/holdings가 실패하는 경우 /v1/accounts/holdings로 폴백
        if res.status_code != 200:
            fallback_url = f"{self.base_url}/v1/accounts/holdings"
            res = requests.get(fallback_url, headers=headers)

        if res.status_code != 200:
            raise Exception(f"토스 보유 종목 조회 실패 (상태 코드 {res.status_code}): {res.text}")

        data = res.json()
        
        if "error" in data:
            err = data["error"]
            raise Exception(f"토스 보유자산 조회 에러 [{err.get('code')}]: {err.get('message')}")

        result = data.get("result", {})
        holdings_list = []
        
        # result 구조가 리스트인 경우와 딕셔너리 내부 리스트인 경우를 유연하게 핸들링
        raw_holdings = []
        if isinstance(result, dict):
            raw_holdings = result.get("holdings", [])
        elif isinstance(result, list):
            raw_holdings = result

        total_eval = 0.0
        available_cash = 0.0

        # 평가 금액 파싱
        if isinstance(result, dict):
            try:
                total_eval = float(result.get("totalEvaluationAmount", 0.0))
                available_cash = float(result.get("availableCash", 0.0))
            except (ValueError, TypeError):
                pass

        for stock in raw_holdings:
            symbol = stock.get("symbol", "")
            name = stock.get("name", "")
            try:
                qty = float(stock.get("quantity", 0.0))
                avg_price = float(stock.get("averageBuyPrice", 0.0))
                current_price = float(stock.get("currentPrice", 0.0))
                profit = float(stock.get("evaluationProfitLoss", 0.0))
                profit_rate = float(stock.get("evaluationProfitLossRate", 0.0))
            except (ValueError, TypeError):
                qty = 0.0
                avg_price = 0.0
                current_price = 0.0
                profit = 0.0
                profit_rate = 0.0

            if qty <= 0:
                continue

            holdings_list.append({
                "symbol": symbol,
                "name": name,
                "qty": qty,
                "avg_price": avg_price,
                "current_price": current_price,
                "profit": profit,
                "profit_rate": profit_rate
            })

            # total_eval이 계산되지 않았을 경우 누적 합산하여 보강
            if total_eval == 0.0:
                total_eval += current_price * qty

        if total_eval == 0.0:
            total_eval = available_cash

        return {
            "total_evaluation": total_eval,
            "available_cash": available_cash,
            "holdings": holdings_list
        }

    def get_price(self, symbol: str) -> dict:
        """
        종목 코드에 해당하는 주식 현재가를 가져옵니다.
        """
        token = self._get_cached_token()
        url = f"{self.base_url}/api/v1/prices"
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }
        params = {"symbol": symbol}
        res = requests.get(url, headers=headers, params=params)
        
        if res.status_code != 200:
            raise Exception(f"토스 시세 조회 실패: {res.text}")
            
        data = res.json()
        result = data.get("result", {})
        
        try:
            current_price = float(result.get("currentPrice", 0.0))
            change_rate = float(result.get("changeRate", 0.0))
        except (ValueError, TypeError):
            current_price = 0.0
            change_rate = 0.0

        return {
            "current_price": current_price,
            "change_rate": change_rate,
            "raw": data
        }

    def place_order(self, symbol: str, qty: float, side: str, ord_type: str, price: float = None) -> dict:
        """
        토스증권 매수/매도 주문을 접수합니다.
        """
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
        # clientOrderId 생성
        client_order_id = f"toss-{uuid.uuid4().hex[:16]}"
        payload = {
            "clientOrderId": client_order_id,
            "symbol": symbol,
            "quantity": qty,
            "side": side.upper(), # BUY / SELL
            "orderType": ord_type.upper(), # LIMIT / MARKET
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

    def get_order_status(self, order_id: str) -> dict:
        """
        주문 식별 번호에 해당하는 주문의 상태를 확인합니다.
        """
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
