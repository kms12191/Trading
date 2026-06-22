import os
import sys
import threading
import time
from datetime import datetime, timedelta
from flask import Flask, request, jsonify
from flask_cors import CORS
from dotenv import load_dotenv
import requests

# Ensure backend directory is in python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.utils.crypto_helper import CryptoHelper
from backend.services.kis_client import KISClient
from backend.services.news_repository import NewsRepository
from backend.services.news_ingest import NewsIngestService

load_dotenv()

app = Flask(__name__)
# Enable CORS for frontend integration
CORS(app, resources={r"/api/*": {"origins": "*"}})

# Encryption key from environment variables
ENCRYPTION_KEY = os.getenv("ENCRYPTION_KEY", "default-dev-encryption-key-32bytes!")

crypto = CryptoHelper(ENCRYPTION_KEY)
news_repository = NewsRepository()
news_ingest_service = NewsIngestService()

NEWS_INGEST_ENABLED = os.getenv("NEWS_INGEST_ENABLED", "false").lower() == "true"
NEWS_INGEST_INTERVAL_SECONDS = int(os.getenv("NEWS_INGEST_INTERVAL_SECONDS", "600"))
_news_ingest_started = False

@app.route("/api/keys/test", methods=["POST"])
def test_keys():
    """
    Test KIS API Key validation.
    Receives raw keys, encrypts them, decrypts them to verify, 
    then requests token and retrieves balance to verify KIS connection.
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
        # 1. Test encryption/decryption cycle
        enc_appkey = crypto.encrypt(appkey)
        enc_appsecret = crypto.encrypt(appsecret)
        enc_cano = crypto.encrypt(cano)
        
        dec_appkey = crypto.decrypt(enc_appkey)
        dec_appsecret = crypto.decrypt(enc_appsecret)
        dec_cano = crypto.decrypt(enc_cano)
        
        # 2. Test KIS API connection using decrypted credentials
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
    Retrieve real-time balance using encrypted credentials.
    Decrypts the keys using ENCRYPTION_KEY, then queries KIS.
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
