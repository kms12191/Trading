import os
import sys
import re
import threading
import time
from datetime import datetime, timedelta
from flask import Flask, request, jsonify
from flask_cors import CORS
from dotenv import load_dotenv
import requests

# backend 디렉토리가 파이썬 경로에 포함되도록 설정
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.utils.crypto_helper import CryptoHelper
from backend.services.kis_client import KISClient
from backend.services.news_repository import NewsRepository
from backend.services.news_ingest import NewsIngestService

load_dotenv()

app = Flask(__name__)
# 프론트엔드 연동을 위해 CORS 활성화
CORS(app, resources={r"/api/*": {"origins": "*"}})

# 환경 변수에서 암호화 키 로드
ENCRYPTION_KEY = os.getenv("ENCRYPTION_KEY", "default-dev-encryption-key-32bytes!")

crypto = CryptoHelper(ENCRYPTION_KEY)
news_repository = NewsRepository()
news_ingest_service = NewsIngestService()

NEWS_INGEST_ENABLED = os.getenv("NEWS_INGEST_ENABLED", "false").lower() == "true"
NEWS_INGEST_INTERVAL_SECONDS = int(os.getenv("NEWS_INGEST_INTERVAL_SECONDS", "600"))
_news_ingest_started = False
COINONE_WATCHLIST = ["BTC", "ETH", "XRP", "SOL"]


def _to_float(value, default=0.0):
    try:
        if value is None or value == "":
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _normalize_coinone_ticker(symbol: str, payload: dict) -> dict:
    tickers = payload.get("tickers") or []
    ticker = tickers[0] if tickers else payload.get("ticker") or payload

    last = _to_float(
        ticker.get("last")
        or ticker.get("close")
        or ticker.get("price")
        or ticker.get("last_price")
    )
    first = _to_float(
        ticker.get("first")
        or ticker.get("open")
        or ticker.get("yesterday_price")
        or ticker.get("prev_close")
    )
    high = _to_float(ticker.get("high"))
    low = _to_float(ticker.get("low"))
    change_rate = _to_float(
        ticker.get("change_rate")
        or ticker.get("rate")
        or ticker.get("change")
        or ticker.get("price_change_percent")
    )

    if not change_rate and first:
        change_rate = ((last - first) / first) * 100 if first else 0.0

    if not first:
        first = last

    return {
        "symbol": symbol,
        "name": symbol,
        "price": last,
        "open": first,
        "high": high,
        "low": low,
        "change_rate": change_rate,
    }


def _fetch_coinone_overview(symbols=None) -> list[dict]:
    symbols = symbols or COINONE_WATCHLIST
    rows = []

    for symbol in symbols:
        url = f"https://api.coinone.co.kr/public/v2/ticker_new/KRW/{symbol}"
        response = requests.get(url, params={"additional_data": "true"}, timeout=10)
        response.raise_for_status()
        payload = response.json()
        if payload.get("result") not in (None, "success"):
            raise Exception(payload.get("error_message") or payload.get("message") or "Coinone API error")
        rows.append(_normalize_coinone_ticker(symbol, payload))

    return rows


def _split_kis_holdings(holdings: list[dict]) -> tuple[list[dict], list[dict]]:
    domestic = []
    foreign = []

    for stock in holdings or []:
        symbol = str(stock.get("symbol", "")).strip()
        row = {
            "symbol": symbol,
            "name": stock.get("name", symbol),
            "qty": _to_float(stock.get("qty")),
            "avg_price": _to_float(stock.get("avg_price")),
            "current_price": _to_float(stock.get("current_price")),
            "profit": _to_float(stock.get("profit")),
            "profit_rate": _to_float(stock.get("profit_rate")),
        }

        if re.search(r"[A-Za-z]", symbol):
            foreign.append(row)
        else:
            domestic.append(row)

    domestic.sort(key=lambda item: abs(item["profit_rate"]), reverse=True)
    foreign.sort(key=lambda item: abs(item["profit_rate"]), reverse=True)
    return domestic, foreign


@app.route("/api/home/overview", methods=["POST"])
def get_home_overview():
    """
    홈 화면용 시장 요약 데이터.
    KIS 키가 있으면 계좌 보유 종목을, 키가 없어도 Coinone 공개 시세는 반환합니다.
    """
    data = request.json or {}
    appkey = data.get("appkey")
    appsecret = data.get("appsecret")
    cano = data.get("cano")
    acnt_prdt_cd = data.get("acnt_prdt_cd", "01")
    env = data.get("env", "MOCK")

    result = {
        "kis": None,
        "coins": [],
        "updated_at": datetime.utcnow().isoformat() + "Z",
        "message": "",
    }

    try:
        result["coins"] = _fetch_coinone_overview()
    except Exception as coin_error:
        result["message"] = f"Coinone 조회 실패: {str(coin_error)}"

    has_kis_credentials = bool(appkey and appsecret and cano)
    if not has_kis_credentials:
        if not result["message"]:
            result["message"] = "KIS 키를 입력하면 국내/해외 보유 종목을 함께 불러올 수 있습니다."
        return jsonify({
            "success": True,
            "data": result
        })

    try:
        client = KISClient(
            appkey=appkey,
            appsecret=appsecret,
            cano=cano,
            acnt_prdt_cd=acnt_prdt_cd,
            env=env,
        )

        balance = client.get_balance()
        domestic_holdings, foreign_holdings = _split_kis_holdings(balance.get("holdings", []))

        result["kis"] = {
            "total_evaluation": _to_float(balance.get("total_evaluation")),
            "available_cash": _to_float(balance.get("available_cash")),
            "domestic": domestic_holdings,
            "foreign": foreign_holdings,
        }

        return jsonify({
            "success": True,
            "data": result
        })
    except Exception as kis_error:
        return jsonify({
            "success": False,
            "message": f"KIS 조회 실패: {str(kis_error)}",
            "data": result,
        }), 500

@app.route("/api/keys/test", methods=["POST"])
def test_keys():
    """
    한국투자증권(KIS) API Key 유효성을 검증합니다.
    평문 키를 수신하여 암호화하고, 다시 복호화하여 일치 여부를 검증한 후,
    토큰 발급 및 잔고 조회를 요청하여 KIS 연결을 최종 확인합니다.
    """
    data = request.json or {}
    appkey = data.get("appkey")
    appsecret = data.get("appsecret")
    cano = data.get("cano")
    acnt_prdt_cd = data.get("acnt_prdt_cd", "01")
    env = data.get("env", "MOCK")
    
    if not appkey or not appsecret or not cano:
        return jsonify({
            "success": False,
            "message": "Missing required fields: appkey, appsecret, or cano."
        }), 400
        
    try:
        # 1. 암호화/복호화 주기 테스트
        enc_appkey = crypto.encrypt(appkey)
        enc_appsecret = crypto.encrypt(appsecret)
        enc_cano = crypto.encrypt(cano)
        
        dec_appkey = crypto.decrypt(enc_appkey)
        dec_appsecret = crypto.decrypt(enc_appsecret)
        dec_cano = crypto.decrypt(enc_cano)
        
        # 2. 복호화된 크리덴셜을 사용하여 KIS API 연결 테스트
        client = KISClient(
            appkey=dec_appkey,
            appsecret=dec_appsecret,
            cano=dec_cano,
            acnt_prdt_cd=acnt_prdt_cd,
            env=env
        )
        
        balance = client.get_balance()
        
        return jsonify({
            "success": True,
            "message": "API key validated and connection established successfully.",
            "data": {
                "balance": balance,
                "encrypted": {
                    "appkey": enc_appkey,
                    "appsecret": enc_appsecret,
                    "cano": enc_cano
                }
            }
        })
    except Exception as e:
        return jsonify({
            "success": False,
            "message": f"Validation failed: {str(e)}"
        }), 500

@app.route("/api/dashboard/balance", methods=["POST"])
def get_dashboard_balance():
    """
    암호화된 크리덴셜을 복호화하여 실시간 잔고를 조회합니다.
    ENCRYPTION_KEY를 사용하여 키를 복호화한 후, KIS에 요청을 수행합니다.
    """
    data = request.json or {}
    enc_appkey = data.get("appkey")
    enc_appsecret = data.get("appsecret")
    enc_cano = data.get("cano")
    acnt_prdt_cd = data.get("acnt_prdt_cd", "01")
    env = data.get("env", "MOCK")
    
    if not enc_appkey or not enc_appsecret or not enc_cano:
        return jsonify({
            "success": False,
            "message": "Missing encrypted credentials."
        }), 400
        
    try:
        dec_appkey = crypto.decrypt(enc_appkey)
        dec_appsecret = crypto.decrypt(enc_appsecret)
        dec_cano = crypto.decrypt(enc_cano)
        
        client = KISClient(
            appkey=dec_appkey,
            appsecret=dec_appsecret,
            cano=dec_cano,
            acnt_prdt_cd=acnt_prdt_cd,
            env=env
        )
        
        balance = client.get_balance()
        return jsonify({
            "success": True,
            "data": balance
        })
    except Exception as e:
        return jsonify({
            "success": False,
            "message": f"Failed to retrieve balance: {str(e)}"
        }), 500


@app.route("/api/news", methods=["GET"])
def get_news_feed():
    """
    Retrieve a unified board-style news feed.
    Query params:
      - market: ALL | DOMESTIC | GLOBAL
      - query: optional search keyword or stock name/ticker
      - limit: max items, default 20
    """
    market = request.args.get("market", "ALL")
    query = request.args.get("query", "")
    limit = request.args.get("limit", 20)
    offset = request.args.get("offset", 0)
    try:
        items = news_repository.list_articles(
            market=market,
            query=query,
            limit=int(limit),
            offset=int(offset),
        )
        return jsonify({
            "success": True,
            "data": {
                "items": items,
                "count": len(items),
                "market": market.upper(),
                "query": query,
                "offset": int(offset),
            }
        })
    except requests.exceptions.HTTPError as e:
        return jsonify({
            "success": False,
            "message": f"News provider error: {str(e)}"
        }), 502
    except Exception as e:
        return jsonify({
            "success": False,
            "message": f"Failed to retrieve news feed: {str(e)}"
        }), 500


@app.route("/api/news/sync", methods=["POST"])
def sync_news_feed():
    try:
        result = news_ingest_service.run_once()
        return jsonify({
            "success": True,
            "data": result,
        })
    except Exception as e:
        return jsonify({
            "success": False,
            "message": f"Failed to sync news feed: {str(e)}"
        }), 500


def _start_news_ingest_scheduler() -> None:
    global _news_ingest_started
    if _news_ingest_started or not NEWS_INGEST_ENABLED:
        return
    _news_ingest_started = True

    def _loop() -> None:
        while True:
            try:
                news_ingest_service.run_once()
            except Exception:
                pass
            now_kr = datetime.utcnow() + timedelta(hours=9)
            is_weekday = now_kr.weekday() < 5
            is_market_hours = is_weekday and (
                (now_kr.hour > 9 or (now_kr.hour == 9 and now_kr.minute >= 0))
                and (now_kr.hour < 15 or (now_kr.hour == 15 and now_kr.minute <= 30))
            )
            sleep_seconds = NEWS_INGEST_INTERVAL_SECONDS if is_market_hours else max(NEWS_INGEST_INTERVAL_SECONDS * 3, 1800)
            time.sleep(sleep_seconds)

    thread = threading.Thread(target=_loop, daemon=True)
    thread.start()

if __name__ == "__main__":
    _start_news_ingest_scheduler()
    app.run(host="0.0.0.0", port=5050, debug=True)
