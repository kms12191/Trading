import jwt
import uuid
import hashlib
import requests
from urllib.parse import urlencode

class UpbitClient:
    """
    업비트 API 연동 및 연결 검증을 담당하는 클라이언트 클래스입니다.
    """
    def __init__(self, access_key: str, secret_key: str):
        self.access_key = access_key
        self.secret_key = secret_key
        self.base_url = "https://api.upbit.com"

    def _get_headers(self, query_params: dict = None) -> dict:
        """
        업비트 API 인증용 JWT 토큰 헤더를 생성합니다.
        """
        payload = {
            "access_key": self.access_key,
            "nonce": str(uuid.uuid4()),
        }

        if query_params:
            query_string = urlencode(query_params).encode()
            m = hashlib.sha512()
            m.update(query_string)
            query_hash = m.hexdigest()
            payload["query_hash"] = query_hash
            payload["query_hash_alg"] = "SHA512"

        # PyJWT를 사용하여 HS256 서명 수행
        jwt_token = jwt.encode(payload, self.secret_key, algorithm="HS256")
        return {
            "Authorization": f"Bearer {jwt_token}"
        }

    def get_balance(self) -> dict:
        """
        업비트 계좌 잔고를 조회하여 연결 상태를 확인하고 자산 현황을 반환합니다.
        """
        url = f"{self.base_url}/v1/accounts"
        headers = self._get_headers()
        res = requests.get(url, headers=headers)
        
        if res.status_code != 200:
            raise Exception(f"업비트 API 호출 실패 (상태 코드 {res.status_code}): {res.text}")
            
        data = res.json()
        
        holdings = []
        total_eval = 0.0
        available_cash = 0.0

        for item in data:
            currency = item.get("currency", "")
            try:
                balance_val = float(item.get("balance", 0.0))
                locked_val = float(item.get("locked", 0.0))
                avg_price = float(item.get("avg_buy_price", 0.0))
            except (ValueError, TypeError):
                balance_val = 0.0
                locked_val = 0.0
                avg_price = 0.0

            total_qty = balance_val + locked_val

            if currency == "KRW":
                available_cash = balance_val
                total_eval += total_qty
            else:
                stock_eval = avg_price * total_qty
                total_eval += stock_eval
                holdings.append({
                    "symbol": currency,
                    "name": currency,
                    "qty": total_qty,
                    "avg_price": avg_price,
                    "current_price": avg_price,  # API 심플 검증을 위해 평균 매수가로 대체 매핑
                    "profit": 0.0,
                    "profit_rate": 0.0
                })

        return {
            "total_evaluation": total_eval,
            "available_cash": available_cash,
            "holdings": holdings,
            "raw": data
        }
