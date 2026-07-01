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

    @staticmethod
    def _normalize_symbol(symbol: str) -> str:
        """
        BTC, BTC/KRW, KRW-BTC 등 화면/DB에서 들어올 수 있는 표기를 코인원 target_currency로 정규화합니다.
        """
        normalized = str(symbol or "").strip().upper()
        if not normalized:
            return ""
        normalized = normalized.replace("_", "-").replace("/", "-")
        parts = [part for part in normalized.split("-") if part]
        if len(parts) == 2 and parts[0] == "KRW":
            return parts[1]
        if len(parts) == 2 and parts[1] == "KRW":
            return parts[0]
        if normalized.endswith("KRW") and len(normalized) > 3:
            return normalized[:-3]
        return normalized

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

    def _private_post(self, path: str, payload: dict) -> dict:
        """
        코인원 Private API v2.1 POST 요청을 공통 서명 규격으로 전송합니다.
        """
        request_payload = {
            "access_token": self.access_token,
            "nonce": str(uuid.uuid4()),
            **(payload or {}),
        }
        headers, encoded_payload = self._get_headers(request_payload)
        res = requests.post(f"{self.base_url}{path}", headers=headers, data=encoded_payload, timeout=5)
        if res.status_code != 200:
            raise Exception(f"코인원 API 호출 실패 (상태 코드 {res.status_code}): {res.text}")

        data = res.json()
        if data.get("result") != "success":
            err_code = data.get("errorCode", "알 수 없음")
            raise Exception(f"코인원 API 에러 응답 (코드 {err_code}): {data}")
        return data

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

    def get_price(self, symbol: str) -> dict:
        """
        코인원 단일 종목 현재가와 전일 대비율을 조회합니다.
        """
        target_currency = self._normalize_symbol(symbol)
        if not target_currency:
            raise ValueError("코인원 현재가 조회를 위한 심볼이 비어 있습니다.")

        url = f"{self.base_url}/public/v2/ticker/KRW/{target_currency}"
        res = requests.get(url, timeout=5)
        if res.status_code != 200:
            raise Exception(f"코인원 현재가 조회 실패 (상태 코드 {res.status_code}): {res.text}")

        data = res.json()
        if data.get("result") != "success" or not data.get("tickers"):
            raise Exception(f"코인원 현재가 에러 응답: {data}")

        ticker = data["tickers"][0]
        current_price = float(ticker.get("last") or 0.0)
        yesterday_last = float(ticker.get("yesterday_last") or current_price or 0.0)
        change_rate = 0.0
        if yesterday_last > 0:
            change_rate = ((current_price - yesterday_last) / yesterday_last) * 100.0

        return {
            "symbol": target_currency,
            "current_price": current_price,
            "change_rate": change_rate,
            "currency": "KRW",
            "raw": data,
        }

    def get_balance(self) -> dict:
        """
        코인원 계좌 잔고를 조회하여 연결 상태를 검증하고 자산 현황을 반환합니다.
        """
        data = self._private_post("/v2.1/account/balance/all", {})

        # 자산 평가를 위한 Tickers(현재가) 정보 조회
        tickers = self._get_tickers()

        balances = data.get("balances", [])
        holdings = []
        total_eval = 0.0
        available_cash = 0.0

        for item in balances:
            currency = item.get("currency", "").upper()
            try:
                avail_val = float(item.get("available", 0.0))
                limit_val = float(item.get("limit", 0.0))
                balance_val = avail_val + limit_val
                avg_price_val = float(item.get("average_price", 0.0))
            except (ValueError, TypeError):
                balance_val = 0.0
                avail_val = 0.0
                avg_price_val = 0.0

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
                    "avg_price": avg_price_val,
                    "current_price": curr_price,
                    "profit": (curr_price - avg_price_val) * balance_val if avg_price_val > 0 else 0.0,
                    "profit_rate": ((curr_price - avg_price_val) / avg_price_val) * 100.0 if avg_price_val > 0 else 0.0,
                    "currency": "KRW"
                })

        return {
            "total_evaluation": total_eval,
            "available_cash": available_cash,
            "available_cash_currency": "KRW",
            "available_cash_supported": True,
            "available_cash_source": "COINONE_ACCOUNT_BALANCE_ALL",
            "available_cash_details": [
                {
                    "currency": "KRW",
                    "amount": available_cash,
                    "source": "COINONE",
                }
            ],
            "currency": "KRW",
            "holdings": holdings,
            "raw": data
        }

    def place_order(self, symbol: str, qty: float, side: str, ord_type: str, price: float = None) -> dict:
        """
        코인원 지정가 주문을 전송합니다. 시장가 주문은 코인원 API 세부 정책 검증 전까지 차단합니다.
        """
        target_currency = self._normalize_symbol(symbol)
        side_upper = str(side or "").upper()
        order_type = str(ord_type or "").upper()

        if side_upper not in ("BUY", "SELL"):
            raise ValueError("코인원 주문 방향은 BUY 또는 SELL이어야 합니다.")
        if order_type != "LIMIT":
            raise ValueError("코인원 주문은 현재 지정가(LIMIT)만 지원합니다.")
        if not target_currency:
            raise ValueError("코인원 주문 심볼이 비어 있습니다.")
        if qty is None or float(qty) <= 0:
            raise ValueError("코인원 주문 수량은 0보다 커야 합니다.")
        if price is None or float(price) <= 0:
            raise ValueError("코인원 지정가 주문에는 0보다 큰 단가가 필요합니다.")

        payload = {
            "quote_currency": "KRW",
            "target_currency": target_currency,
            "type": "LIMIT",
            "side": side_upper,
            "price": str(price),
            "qty": str(qty),
            "post_only": False,
        }
        data = self._private_post("/v2.1/order", payload)
        order_payload = data.get("order") if isinstance(data.get("order"), dict) else {}
        order_id = (
            data.get("order_id")
            or data.get("orderId")
            or data.get("orderid")
            or order_payload.get("order_id")
            or order_payload.get("orderId")
            or order_payload.get("orderid")
        )

        return {
            "order_id": order_id,
            "status": "ORDERED",
            "client_order_id": None,
            "raw": data,
        }

    def get_order_status(self, order_id: str, symbol: str | None = None) -> dict:
        """
        코인원 주문 상태를 단건 조회합니다.
        """
        if not order_id:
            raise ValueError("코인원 주문 상태 조회에는 order_id가 필요합니다.")

        target_currency = self._normalize_symbol(symbol or "")
        payload = {
            "order_id": order_id,
            "quote_currency": "KRW",
        }
        if target_currency:
            payload["target_currency"] = target_currency

        data = self._private_post("/v2.1/order/detail", payload)
        status = str(data.get("status") or data.get("order_status") or "UNKNOWN").upper()
        return {
            "order_id": order_id,
            "status": status,
            "raw": data,
        }

    def cancel_order(self, order_id: str, symbol: str | None = None) -> dict:
        """
        코인원 미체결 주문을 취소합니다.
        """
        if not order_id:
            raise ValueError("코인원 주문 취소에는 order_id가 필요합니다.")

        target_currency = self._normalize_symbol(symbol or "")
        payload = {
            "order_id": order_id,
            "quote_currency": "KRW",
        }
        if target_currency:
            payload["target_currency"] = target_currency

        data = self._private_post("/v2.1/order/cancel", payload)
        return {
            "order_id": order_id,
            "status": "CANCELED",
            "raw": data,
        }
