import json
import os
import time
from datetime import datetime, timedelta

import requests

from backend.services.exchange_client import ExchangeClient

TOSS_TOKEN_CACHE_FILE = ".toss_token_cache.json"


class TossClient(ExchangeClient):
    def __init__(self, client_id: str, client_secret: str, account_seq: str = None, env: str = "MOCK"):
        self.client_id = client_id
        self.client_secret = client_secret
        self.account_seq = account_seq
        self.env = env.upper()
        self.base_url = os.getenv("TOSS_BASE_URL", "https://openapi.tossinvest.com").rstrip("/")

    def _load_cache(self) -> dict:
        if not os.path.exists(TOSS_TOKEN_CACHE_FILE):
            return {}
        try:
            with open(TOSS_TOKEN_CACHE_FILE, "r", encoding="utf-8") as file:
                return json.load(file)
        except Exception:
            return {}

    def _save_cache(self, cache: dict) -> None:
        try:
            with open(TOSS_TOKEN_CACHE_FILE, "w", encoding="utf-8") as file:
                json.dump(cache, file, indent=2, ensure_ascii=False)
        except Exception:
            pass

    @staticmethod
    def _to_float(value) -> float:
        if value is None:
            return 0.0
        if isinstance(value, bool):
            return 1.0 if value else 0.0
        if isinstance(value, (int, float)):
            return float(value)
        text = str(value).strip()
        if not text or text in {"-", "N/A", "null", "None"}:
            return 0.0
        text = text.replace(",", "").replace("%", "")
        if text.startswith("+"):
            text = text[1:]
        try:
            return float(text)
        except (TypeError, ValueError):
            return 0.0

    @staticmethod
    def _symbol_variants(symbol: str) -> list[str]:
        normalized = str(symbol or "").strip().upper()
        variants = []
        if normalized:
            variants.append(normalized)
        if normalized.isdigit() and len(normalized) == 6:
            prefixed = f"A{normalized}"
            if prefixed not in variants:
                variants.append(prefixed)
        elif normalized.startswith("A") and len(normalized) == 7 and normalized[1:].isdigit():
            bare = normalized[1:]
            if bare not in variants:
                variants.append(bare)
        return variants

    @staticmethod
    def _normalize_symbol(value) -> str:
        text = str(value or "").strip().upper()
        if text.startswith("A") and len(text) == 7 and text[1:].isdigit():
            return text[1:]
        return text

    @classmethod
    def _is_price_record(cls, item: dict) -> bool:
        if not isinstance(item, dict):
            return False
        symbol_keys = ("symbol", "code", "ticker", "iscd", "stockCode")
        price_keys = (
            "currentPrice",
            "current_price",
            "lastPrice",
            "last_price",
            "closePrice",
            "close_price",
            "price",
            "changeRate",
            "change_rate",
            "changePercent",
            "change_percent",
            "rate",
            "change",
        )
        return any(item.get(key) not in (None, "") for key in symbol_keys + price_keys)

    @classmethod
    def _find_price_record(cls, payload, symbol_variants: list[str]) -> dict:
        targets = {cls._normalize_symbol(variant) for variant in symbol_variants if variant}
        queue = [payload]

        while queue:
            current = queue.pop(0)

            if isinstance(current, dict):
                symbol_value = next(
                    (
                        current.get(key)
                        for key in ("symbol", "code", "ticker", "iscd", "stockCode", "instrumentId")
                        if current.get(key) not in (None, "")
                    ),
                    None,
                )
                has_price_fields = any(
                    current.get(key) not in (None, "")
                    for key in (
                        "currentPrice",
                        "current_price",
                        "lastPrice",
                        "last_price",
                        "closePrice",
                        "close_price",
                        "price",
                        "changeRate",
                        "change_rate",
                        "changePercent",
                        "change_percent",
                        "rate",
                        "change",
                        "prdy_ctrt",
                    )
                )

                if symbol_value is not None:
                    if cls._normalize_symbol(symbol_value) in targets and has_price_fields:
                        return current
                elif has_price_fields:
                    return current

                nested_keys = ("result", "output", "data", "prices", "price", "items", "stocks", "quotes", "list")
                for key in nested_keys:
                    nested = current.get(key)
                    if isinstance(nested, (dict, list)):
                        queue.append(nested)

            elif isinstance(current, list):
                queue.extend(current)

        return {}

    def _extract_price_fields(self, data: dict, symbol_variants: list[str]) -> tuple[float, float, float]:
        payload = data
        for key in ("result", "output", "data"):
            if isinstance(payload, dict) and payload.get(key) is not None:
                payload = payload.get(key)

        record = self._find_price_record(payload, symbol_variants)
        if not record and isinstance(payload, dict):
            record = payload
        elif not record and isinstance(payload, list) and len(payload) == 1:
            record = payload[0] if payload else {}

        if not isinstance(record, dict):
            record = {}

        current_price = self._to_float(
            record.get("currentPrice")
            or record.get("current_price")
            or record.get("lastPrice")
            or record.get("last_price")
            or record.get("closePrice")
            or record.get("close_price")
            or record.get("price")
            or record.get("last")
        )
        change_rate = self._to_float(
            record.get("changeRate")
            or record.get("change_rate")
            or record.get("rate")
            or record.get("changePercent")
            or record.get("change_percent")
            or record.get("changePct")
            or record.get("change_ratio")
            or record.get("change")
            or record.get("prdy_ctrt")
        )

        prev_close = self._to_float(
            record.get("previousClosePrice")
            or record.get("prevClosePrice")
            or record.get("prev_close_price")
            or record.get("prevClose")
            or record.get("yesterdayClosePrice")
            or record.get("yesterday_close_price")
            or record.get("basePrice")
            or record.get("base_price")
            or record.get("referencePrice")
            or record.get("refPrice")
            or record.get("ref_price")
        )

        if not change_rate and current_price and prev_close:
            change_rate = ((current_price - prev_close) / prev_close) * 100 if prev_close else 0.0

        return current_price, change_rate, prev_close

    def _extract_previous_close_from_candles(self, data: dict, symbol: str) -> float:
        payload = data
        for key in ("result", "output", "data"):
            if isinstance(payload, dict) and payload.get(key) is not None:
                payload = payload.get(key)

        candles = []
        if isinstance(payload, dict):
            nested = payload.get("candles")
            if isinstance(nested, list):
                candles = nested
        elif isinstance(payload, list):
            candles = payload

        if not candles:
            return 0.0

        parsed = []
        for candle in candles:
            if not isinstance(candle, dict):
                continue
            ts = (
                candle.get("timestamp")
                or candle.get("time")
                or candle.get("candleTime")
                or candle.get("candle_time")
                or candle.get("date")
            )
            close_price = self._to_float(
                candle.get("closePrice")
                or candle.get("close_price")
                or candle.get("close")
                or candle.get("price")
            )
            parsed.append((str(ts or ""), close_price))

        if not parsed:
            return 0.0

        parsed.sort(key=lambda item: item[0])
        if len(parsed) >= 2:
            return parsed[-2][1]
        return parsed[-1][1]

    def _fetch_previous_close(self, symbol: str) -> float:
        token = self._get_cached_token()
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

        for candidate in self._symbol_variants(symbol):
            try:
                res = requests.get(
                    f"{self.base_url}/api/v1/candles",
                    headers=headers,
                    params={
                        "symbol": candidate,
                        "interval": "1d",
                        "count": 2,
                        "adjusted": "true",
                    },
                    timeout=15,
                )
            except Exception:
                continue

            if res.status_code != 200:
                continue

            data = res.json()
            if isinstance(data, dict) and data.get("error"):
                continue

            prev_close = self._extract_previous_close_from_candles(data, candidate)
            if prev_close:
                return prev_close

        return 0.0

    def _get_cached_token(self) -> str:
        cache = self._load_cache()
        client_cache = cache.get(self.client_id, {})
        token = client_cache.get("access_token")
        expired_at_str = client_cache.get("expired_at")

        if token and expired_at_str:
            try:
                expired_at = datetime.strptime(expired_at_str, "%Y-%m-%d %H:%M:%S")
                if (expired_at - datetime.now()).total_seconds() > 300:
                    return token
            except Exception:
                pass

        token_data = self._request_new_token()
        new_token = token_data["access_token"]
        expires_in = int(token_data.get("expires_in", 86400))
        expired_at = datetime.now() + timedelta(seconds=expires_in)

        cache[self.client_id] = {
            "access_token": new_token,
            "expired_at": expired_at.strftime("%Y-%m-%d %H:%M:%S"),
        }
        self._save_cache(cache)
        return new_token

    def _request_new_token(self) -> dict:
        url = f"{self.base_url}/oauth2/token"
        payload = {
            "grant_type": "client_credentials",
            "client_id": self.client_id,
            "client_secret": self.client_secret,
        }
        res = requests.post(url, data=payload, headers={"Content-Type": "application/x-www-form-urlencoded"}, timeout=15)
        if res.status_code != 200:
            try:
                err_data = res.json()
                err_msg = err_data.get("error_description") or err_data.get("error") or res.text
            except Exception:
                err_msg = res.text
            raise Exception(f"Toss token issuance failed: {err_msg}")
        return res.json()

    def get_accounts(self) -> list:
        token = self._get_cached_token()
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

        for path in ("/api/v1/accounts", "/v1/accounts"):
            res = requests.get(f"{self.base_url}{path}", headers=headers, timeout=15)
            if res.status_code == 200:
                data = res.json()
                if "error" in data:
                    err = data["error"]
                    raise Exception(f"Toss accounts error [{err.get('code')}]: {err.get('message')}")
                result = data.get("result", [])
                return result.get("accounts", []) if isinstance(result, dict) else result

        raise Exception(f"Toss account lookup failed: {res.text}")

    def get_balance(self) -> dict:
        if not self.account_seq:
            accounts = self.get_accounts()
            if not accounts:
                raise Exception("No Toss account found.")
            self.account_seq = accounts[0].get("accountSeq")

        token = self._get_cached_token()
        headers = {
            "Authorization": f"Bearer {token}",
            "X-Tossinvest-Account": self.account_seq,
            "Content-Type": "application/json",
        }

        for path in ("/api/v1/holdings", "/v1/accounts/holdings"):
            res = requests.get(f"{self.base_url}{path}", headers=headers, timeout=15)
            if res.status_code == 200:
                data = res.json()
                if "error" in data:
                    err = data["error"]
                    raise Exception(f"Toss balance error [{err.get('code')}]: {err.get('message')}")

                result = data.get("result", {})
                raw_holdings = []
                if isinstance(result, dict):
                    raw_holdings = result.get("holdings", [])
                elif isinstance(result, list):
                    raw_holdings = result

                holdings_list = []
                total_eval = 0.0
                available_cash = 0.0

                if isinstance(result, dict):
                    try:
                        total_eval = float(result.get("totalEvaluationAmount", 0.0))
                        available_cash = float(result.get("availableCash", 0.0))
                    except (ValueError, TypeError):
                        pass

                for stock in raw_holdings:
                    try:
                        qty = float(stock.get("quantity", 0.0))
                        avg_price = float(stock.get("averageBuyPrice", 0.0))
                        current_price = float(stock.get("currentPrice", 0.0))
                        profit = float(stock.get("evaluationProfitLoss", 0.0))
                        profit_rate = float(stock.get("evaluationProfitLossRate", 0.0))
                    except (ValueError, TypeError):
                        qty = avg_price = current_price = profit = profit_rate = 0.0

                    if qty <= 0:
                        continue

                    symbol = stock.get("symbol", "")
                    name = stock.get("name", "")
                    holdings_list.append(
                        {
                            "symbol": symbol,
                            "name": name,
                            "qty": qty,
                            "avg_price": avg_price,
                            "current_price": current_price,
                            "profit": profit,
                            "profit_rate": profit_rate,
                        }
                    )

                    if total_eval == 0.0:
                        total_eval += current_price * qty

                if total_eval == 0.0:
                    total_eval = available_cash

                return {
                    "total_evaluation": total_eval,
                    "available_cash": available_cash,
                    "holdings": holdings_list,
                }

        raise Exception(f"Toss balance lookup failed: {res.text}")

    def get_price(self, symbol: str) -> dict:
        token = self._get_cached_token()
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

        symbol_variants = [symbol]
        if symbol.isdigit() and len(symbol) == 6:
            symbol_variants.append(f"A{symbol}")

        last_error = None
        last_raw = None
        for candidate in symbol_variants:
            res = requests.get(
                f"{self.base_url}/api/v1/prices",
                headers=headers,
                params={"symbols": candidate},
                timeout=15,
            )

            if res.status_code != 200:
                last_error = f"{candidate}: {res.text}"
                continue

            data = res.json()
            last_raw = data
            if isinstance(data, dict) and data.get("error"):
                err = data["error"]
                last_error = f"{candidate}: {err.get('message') or err}"
                continue

            current_price, change_rate, prev_close = self._extract_price_fields(data, symbol_variants)
            candle_prev_close = self._fetch_previous_close(candidate)
            if candle_prev_close:
                prev_close = candle_prev_close
            if current_price and prev_close:
                change_rate = ((current_price - prev_close) / prev_close) * 100 if prev_close else 0.0

            if current_price or change_rate or prev_close:
                return {
                    "current_price": current_price,
                    "change_rate": change_rate,
                    "previous_close": prev_close,
                    "symbol_used": candidate,
                    "raw": data,
                }

            last_error = f"{candidate}: empty price payload"

        return {
            "current_price": 0.0,
            "change_rate": 0.0,
            "previous_close": 0.0,
            "symbol_used": symbol_variants[-1],
            "raw": last_raw or {"error": last_error or "empty price payload"},
        }

    def place_order(self, symbol: str, qty: float, side: str, ord_type: str, price: float = None) -> dict:
        if self.env == "MOCK":
            return {
                "order_id": f"MOCK-TOSS-{int(time.time())}",
                "status": "ORDERED",
                "raw": {"symbol": symbol, "qty": qty, "side": side, "ord_type": ord_type},
            }

        token = self._get_cached_token()
        headers = {
            "Authorization": f"Bearer {token}",
            "X-Tossinvest-Account": self.account_seq,
            "Content-Type": "application/json",
        }
        payload = {
            "clientOrderId": f"toss-{int(time.time() * 1000)}",
            "symbol": symbol,
            "quantity": qty,
            "side": side.upper(),
            "orderType": ord_type.upper(),
        }
        if price is not None:
            payload["price"] = price

        res = requests.post(f"{self.base_url}/api/v1/orders", json=payload, headers=headers, timeout=15)
        if res.status_code != 200:
            raise Exception(f"Toss order failed: {res.text}")

        data = res.json()
        result = data.get("result", {})
        return {
            "order_id": result.get("orderId"),
            "status": result.get("status"),
            "raw": data,
        }

    def get_order_status(self, order_id: str) -> dict:
        token = self._get_cached_token()
        headers = {
            "Authorization": f"Bearer {token}",
            "X-Tossinvest-Account": self.account_seq,
            "Content-Type": "application/json",
        }
        res = requests.get(f"{self.base_url}/api/v1/orders/{order_id}", headers=headers, timeout=15)
        if res.status_code != 200:
            raise Exception(f"Toss order status failed: {res.text}")

        data = res.json()
        result = data.get("result", {})
        return {
            "order_id": result.get("orderId"),
            "status": result.get("status"),
            "qty": float(result.get("quantity", 0)),
            "executed_qty": float(result.get("executedQuantity", 0)),
            "raw": data,
        }
