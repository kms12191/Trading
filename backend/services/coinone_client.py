import base64
import hashlib
import hmac
import json
import uuid
import requests

class CoinoneClient:
    """
    코인원 API v2.1 연동 및 연결 검증을 담당하는 클라이언트 클래스입니다.
    """
    def __init__(self, access_token: str, secret_key: str):
        self.access_token = access_token
        self.secret_key = secret_key.encode('utf-8')  # 코인원 Secret Key는 원본 바이트열 그대로 처리
        self.base_url = "https://api.coinone.co.kr"

    def _get_headers(self, payload: dict) -> tuple:
        """
        코인원 API v2.1 전용 Signature 및 Payload 헤더를 생성합니다.
        반환값: (headers_dict, encoded_payload_str)
        """
        # 1. Payload를 JSON 문자열로 변환 후 Base64 인코딩
        dumped_json = json.dumps(payload)
        encoded_payload = base64.b64encode(dumped_json.encode('utf-8')).decode('utf-8')

        # 2. Base64 페이로드를 Secret Key로 HMAC-SHA512 서명 생성
        signature = hmac.new(
            self.secret_key,
            encoded_payload.encode('utf-8'),
            hashlib.sha512
        ).hexdigest()

        headers = {
            "Content-Type": "application/json",
            "X-COINONE-PAYLOAD": encoded_payload,
            "X-COINONE-SIGNATURE": signature
        }
        return headers, encoded_payload

    def _get_tickers(self) -> dict:
        """
        코인원 마켓의 모든 코인 현재가(Ticker) 정보를 조회합니다.
        """
        url = f"{self.base_url}/public/v2/ticker_new/KRW"
        try:
            res = requests.get(url, timeout=5)
            if res.status_code == 200:
                data = res.json()
                if data.get("result") == "success":
                    tickers = {}
                    for t in data.get("tickers", []):
                        target = t.get("target_currency", "").upper()
                        tickers[target] = float(t.get("last", 0.0))
                    return tickers
        except Exception:
            pass
        return {}

    def get_balance(self) -> dict:
        """
        코인원 계좌 잔고를 조회하여 연결 상태를 검증하고 자산 현황을 반환합니다.
        """
        url = f"{self.base_url}/v2.1/account/balance/all"
        
        # 2.1 API 필수 규격에 맞춰 바디 구성
        payload = {
            "access_token": self.access_token,
            "nonce": str(uuid.uuid4())
        }
        
        headers, encoded_payload = self._get_headers(payload)
        res = requests.post(url, headers=headers, data=encoded_payload, timeout=5)

        if res.status_code != 200:
            raise Exception(f"코인원 API 호출 실패 (상태 코드 {res.status_code}): {res.text}")

        data = res.json()
        if data.get("result") != "success":
            err_code = data.get("errorCode", "알 수 없음")
            raise Exception(f"코인원 API 에러 응답 (코드 {err_code}): {data}")

        # 자산 평가를 위한 Tickers(현재가) 정보 조회
        tickers = self._get_tickers()

        balances = data.get("balances", [])
        holdings = []
        total_eval = 0.0
        available_cash = 0.0

        for item in balances:
            currency = item.get("currency", "").upper()
            try:
                balance_val = float(item.get("balance", 0.0))
                avail_val = float(item.get("avail", 0.0))
            except (ValueError, TypeError):
                balance_val = 0.0
                avail_val = 0.0

            if balance_val <= 0:
                continue

            if currency == "KRW":
                available_cash = avail_val
                total_eval += balance_val
            else:
                # 현재가 매핑 (없으면 0.0)
                curr_price = tickers.get(currency, 0.0)
                eval_price = curr_price * balance_val
                total_eval += eval_price
                
                holdings.append({
                    "symbol": currency,
                    "name": currency,
                    "qty": balance_val,
                    "avg_price": 0.0,  # 코인원 잔고 API는 평균 매수가를 제공하지 않음
                    "current_price": curr_price,
                    "profit": 0.0,
                    "profit_rate": 0.0
                })

        return {
            "total_evaluation": total_eval,
            "available_cash": available_cash,
            "holdings": holdings,
            "raw": data
        }
