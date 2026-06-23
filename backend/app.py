import os
import sys
import threading
import time
from datetime import datetime, timedelta
from flask import Flask, request, jsonify
from flask_cors import CORS
from dotenv import load_dotenv
import requests
import jwt

# backend 디렉토리가 파이썬 경로에 포함되도록 설정
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.utils.crypto_helper import CryptoHelper
from backend.services.kis_client import KISClient
from backend.services.toss_client import TossClient
from backend.services.coinone_client import CoinoneClient
from backend.services.binance_client import BinanceClient
from backend.services.news_repository import NewsRepository
from backend.services.news_ingest import NewsIngestService

load_dotenv()

app = Flask(__name__)
# 프론트엔드 연동을 위해 CORS 활성화 및 Authorization 헤더 허용
CORS(app, resources={r"/api/*": {"origins": "*"}}, supports_credentials=True)

# 환경 변수에서 암호화 키 및 Supabase 정보 로드
ENCRYPTION_KEY = os.getenv("ENCRYPTION_KEY", "default-dev-encryption-key-32bytes!")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY")

crypto = CryptoHelper(ENCRYPTION_KEY)
news_repository = NewsRepository()
news_ingest_service = NewsIngestService()

NEWS_INGEST_ENABLED = os.getenv("NEWS_INGEST_ENABLED", "false").lower() == "true"
NEWS_INGEST_INTERVAL_SECONDS = int(os.getenv("NEWS_INGEST_INTERVAL_SECONDS", "600"))
_news_ingest_started = False

# Supabase 연동 헬퍼 함수 (RLS 위임)
def get_user_id_from_header(auth_header):
    """
    Authorization 헤더의 Bearer 토큰으로부터 user_id(sub)를 파싱합니다.
    """
    if not auth_header or not auth_header.startswith("Bearer "):
        raise Exception("유효하지 않은 인증 헤더입니다.")
    token = auth_header.split(" ")[1]
    # JWT 서명 검증은 Supabase API 호출 단계에서 대행하므로, 여기서는 디코딩만 처리
    payload = jwt.decode(token, options={"verify_signature": False})
    user_id = payload.get("sub")
    if not user_id:
        raise Exception("토큰 페이로드가 유효하지 않습니다.")
    return user_id, token

def query_supabase(auth_header, endpoint, method="GET", json_data=None, params=None):
    """
    사용자의 JWT 토큰을 릴레이하여 Supabase REST API를 직접 호출합니다.
    """
    user_id, token = get_user_id_from_header(auth_header)
    url = f"{SUPABASE_URL}/rest/v1/{endpoint}"
    headers = {
        "apikey": SUPABASE_ANON_KEY,
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    
    if method == "GET":
        res = requests.get(url, headers=headers, params=params)
    elif method == "POST":
        res = requests.post(url, headers=headers, json=json_data, params=params)
    elif method == "PATCH":
        res = requests.patch(url, headers=headers, json=json_data, params=params)
    elif method == "PUT":
        res = requests.put(url, headers=headers, json=json_data, params=params)
    else:
        raise ValueError("지원하지 않는 HTTP 메소드입니다.")
    
    if res.status_code not in (200, 201, 204):
        raise Exception(f"Supabase REST API 에러 ({res.status_code}): {res.text}")
    
    if res.text:
        try:
            return res.json()
        except Exception:
            return res.text
    return None

def upsert_user_api_key(auth_header, data):
    """
    사용자 인증 정보를 user_api_keys 테이블에 upsert 처리합니다.
    """
    user_id, token = get_user_id_from_header(auth_header)
    exchange = data.get("exchange")
    broker_env = data.get("broker_env", "REAL")

    # 기존 연동된 기록 검색 (동일 거래소, 동일 환경)
    params = {
        "user_id": f"eq.{user_id}",
        "exchange": f"eq.{exchange}",
        "broker_env": f"eq.{broker_env}"
    }
    existing = query_supabase(auth_header, "user_api_keys", "GET", params=params)

    if existing and len(existing) > 0:
        record_id = existing[0]["id"]
        # PATCH 방식으로 기존 레코드 갱신
        query_supabase(auth_header, f"user_api_keys?id=eq.{record_id}", "PATCH", json_data=data)
    else:
        # POST 방식으로 신규 레코드 삽입
        data["user_id"] = user_id
        query_supabase(auth_header, "user_api_keys", "POST", json_data=data)


# 1. API Key 등록 현황 조회 API
@app.route("/api/keys/status", methods=["GET"])
def get_keys_status():
    auth_header = request.headers.get("Authorization")
    if not auth_header:
        return jsonify({"success": False, "message": "인증 헤더가 누락되었습니다."}), 401
    
    try:
        records = query_supabase(auth_header, "user_api_keys", "GET")
        
        result = {
            "TOSS": {"registered": False},
            "KIS": {"registered": False},
            "COINONE": {"registered": False},
            "BINANCE": {"registered": False}
        }
        
        for record in records:
            ex = record.get("exchange")
            if ex not in result:
                continue
                
            enc_key = record.get("encrypted_access_key")
            mask_key = ""
            if enc_key:
                try:
                    plain_key = crypto.decrypt(enc_key)
                    if len(plain_key) > 8:
                        mask_key = f"{plain_key[:5]}...{plain_key[-3:]}"
                    else:
                        mask_key = plain_key
                except Exception:
                    mask_key = "복호화 실패"
            
            # 계좌 마스킹 처리
            toss_acc = record.get("toss_account_no")
            if toss_acc and len(toss_acc) > 4:
                toss_acc = f"****{toss_acc[-4:]}"
                
            kis_acc = record.get("kis_account_no")
            if kis_acc and len(kis_acc) > 4:
                kis_acc = f"****{kis_acc[-4:]}"

            result[ex] = {
                "registered": True,
                "access_key": mask_key,
                "broker_env": record.get("broker_env", "REAL"),
                "toss_account_no": toss_acc,
                "toss_account_seq": record.get("toss_account_seq"),
                "kis_account_no": kis_acc
            }
            
        return jsonify({"success": True, "data": result})
    except Exception as e:
        return jsonify({"success": False, "message": f"API Key 현황 조회 실패: {str(e)}"}), 500


# 2. API Key 암호화 저장 API
@app.route("/api/keys/save", methods=["POST"])
def save_api_keys():
    auth_header = request.headers.get("Authorization")
    if not auth_header:
        return jsonify({"success": False, "message": "인증 헤더가 누락되었습니다."}), 401

    data = request.json or {}
    exchange = data.get("exchange")
    broker_env = data.get("broker_env", "REAL")

    if not exchange or exchange not in ("TOSS", "KIS", "COINONE", "BINANCE"):
        return jsonify({"success": False, "message": "올바르지 않은 exchange 구분값입니다."}), 400

    try:
        db_data = {
            "exchange": exchange,
            "broker_env": broker_env
        }

        # 브로커별 키 암호화 및 컬럼 패킹
        if exchange == "TOSS":
            client_id = data.get("client_id")
            client_secret = data.get("client_secret")
            toss_account_seq = data.get("toss_account_seq")
            toss_account_no = data.get("toss_account_no")

            if not client_id or not client_secret:
                return jsonify({"success": False, "message": "client_id와 client_secret이 필수적입니다."}), 400

            db_data["encrypted_access_key"] = crypto.encrypt(client_id)
            db_data["encrypted_secret_key"] = crypto.encrypt(client_secret)
            db_data["toss_account_seq"] = toss_account_seq
            db_data["toss_account_no"] = toss_account_no

        elif exchange == "KIS":
            appkey = data.get("appkey")
            appsecret = data.get("appsecret")
            cano = data.get("cano")
            acnt_prdt_cd = data.get("acnt_prdt_cd", "01")

            if not appkey or not appsecret or not cano:
                return jsonify({"success": False, "message": "appkey, appsecret, cano가 필수적입니다."}), 400

            db_data["encrypted_access_key"] = crypto.encrypt(appkey)
            db_data["encrypted_secret_key"] = crypto.encrypt(appsecret)
            db_data["kis_account_no"] = cano
            db_data["kis_account_code"] = acnt_prdt_cd

        elif exchange == "COINONE":
            access_token = data.get("access_token")
            secret_key = data.get("secret_key")

            if not access_token or not secret_key:
                return jsonify({"success": False, "message": "access_token과 secret_key가 필수적입니다."}), 400

            db_data["encrypted_access_key"] = crypto.encrypt(access_token)
            db_data["encrypted_secret_key"] = crypto.encrypt(secret_key)

        elif exchange == "BINANCE":
            api_key = data.get("api_key")
            secret_key = data.get("secret_key")

            if not api_key or not secret_key:
                return jsonify({"success": False, "message": "api_key와 secret_key가 필수적입니다."}), 400

            db_data["encrypted_access_key"] = crypto.encrypt(api_key)
            db_data["encrypted_secret_key"] = crypto.encrypt(secret_key)

        upsert_user_api_key(auth_header, db_data)
        return jsonify({"success": True, "message": f"{exchange} API Key가 안전하게 저장되었습니다."})
    except Exception as e:
        return jsonify({"success": False, "message": f"API Key 저장 실패: {str(e)}"}), 500


# 3. Toss 계좌 조회 전용 API
@app.route("/api/keys/toss/accounts", methods=["POST"])
def get_toss_accounts():
    auth_header = request.headers.get("Authorization")
    if not auth_header:
        return jsonify({"success": False, "message": "인증 헤더가 누락되었습니다."}), 401

    data = request.json or {}
    client_id = data.get("client_id")
    client_secret = data.get("client_secret")
    broker_env = data.get("broker_env", "REAL")

    # 입력값이 비어있는 경우 DB에서 조회
    if not client_id or not client_secret:
        try:
            user_id, token = get_user_id_from_header(auth_header)
            params = {
                "user_id": f"eq.{user_id}",
                "exchange": "eq.TOSS",
                "broker_env": f"eq.{broker_env}"
            }
            records = query_supabase(auth_header, "user_api_keys", "GET", params=params)
            if not records or len(records) == 0:
                return jsonify({"success": False, "message": "등록된 Toss API 크리덴셜 정보가 없습니다."}), 400
            
            client_id = crypto.decrypt(records[0].get("encrypted_access_key"))
            client_secret = crypto.decrypt(records[0].get("encrypted_secret_key"))
        except Exception as e:
            return jsonify({"success": False, "message": f"DB 조회 실패: {str(e)}"}), 500

    try:
        client = TossClient(client_id=client_id, client_secret=client_secret, env=broker_env)
        accounts = client.get_accounts()
        return jsonify({"success": True, "data": accounts})
    except Exception as e:
        return jsonify({"success": False, "message": f"Toss 계좌 조회 실패: {str(e)}"}), 500


def classify_error(exchange: str, exception: Exception) -> str:
    """
    발생한 예외 정보를 기반으로 FATAL(인증 오류) 또는 TEMPORARY(일시적 오류) 에러 유형을 판별합니다.
    """
    err_msg = str(exception)
    
    # 1. 공통 네트워크/연결/타임아웃 관련 예외 체크
    import requests
    if isinstance(exception, (requests.exceptions.ConnectionError, 
                               requests.exceptions.Timeout, 
                               requests.exceptions.ConnectTimeout, 
                               requests.exceptions.ReadTimeout)):
        return "TEMPORARY"
        
    timeout_keywords = ["timeout", "timed out", "connection refused", "connection error", "max retries exceeded", "502", "503", "504"]
    if any(kw in err_msg.lower() for kw in timeout_keywords):
        return "TEMPORARY"
        
    # 2. 거래소별 에러 파싱
    if exchange == "TOSS":
        fatal_keywords = ["401", "403", "invalid_client", "unauthorized", "인증"]
        if any(kw in err_msg.lower() for kw in fatal_keywords):
            return "FATAL"
            
    elif exchange == "KIS":
        fatal_keywords = ["appkey", "appsecret", "인증", "유효하지 않은", "auth", "credential", "rt_cd"]
        if any(kw in err_msg.lower() for kw in fatal_keywords):
            return "FATAL"
            
    elif exchange == "COINONE":
        fatal_keywords = ["101", "102", "103", "104", "107", "parameter error", "invalid access token", "invalid signature"]
        if any(kw in err_msg.lower() for kw in fatal_keywords):
            return "FATAL"
        if "코드 12" in err_msg or "코드 11" in err_msg:
            return "TEMPORARY"
            
    elif exchange == "BINANCE":
        fatal_keywords = ["401", "403", "-1022", "-2015", "signature", "api key", "unauthorized"]
        if any(kw in err_msg.lower() for kw in fatal_keywords):
            return "FATAL"
            
    return "FATAL"


# 4. API Key 연결 테스트 API
@app.route("/api/keys/test", methods=["POST"])
def test_keys():
    auth_header = request.headers.get("Authorization")
    data = request.json or {}
    exchange = data.get("exchange", "KIS")
    broker_env = data.get("broker_env", "MOCK")

    client_id = (
        data.get("client_id") or 
        data.get("appkey") or 
        data.get("access_key") or 
        data.get("access_token") or 
        data.get("api_key")
    )
    client_secret = (
        data.get("client_secret") or 
        data.get("appsecret") or 
        data.get("secret_key")
    )
    
    # 1회용 연결 테스트를 위한 KIS cano 대응
    cano = data.get("cano")
    acnt_prdt_cd = data.get("acnt_prdt_cd", "01")
    toss_account_seq = data.get("toss_account_seq")

    # 입력값이 없는 경우 DB에서 읽어옴
    if not client_id or not client_secret:
        if not auth_header:
            return jsonify({"success": False, "message": "인증 정보 혹은 API 키 입력값이 누락되었습니다."}), 400
        try:
            user_id, token = get_user_id_from_header(auth_header)
            params = {
                "user_id": f"eq.{user_id}",
                "exchange": f"eq.{exchange}",
                "broker_env": f"eq.{broker_env}"
            }
            records = query_supabase(auth_header, "user_api_keys", "GET", params=params)
            if not records or len(records) == 0:
                return jsonify({"success": False, "message": f"저장된 {exchange} API 크리덴셜 정보가 없습니다."}), 400
            
            record = records[0]
            client_id = crypto.decrypt(record.get("encrypted_access_key"))
            client_secret = crypto.decrypt(record.get("encrypted_secret_key"))
            if exchange == "KIS":
                cano = record.get("kis_account_no")
                acnt_prdt_cd = record.get("kis_account_code", "01")
            elif exchange == "TOSS":
                toss_account_seq = record.get("toss_account_seq")
        except Exception as e:
            return jsonify({"success": False, "message": f"DB에서 인증정보 로드 실패: {str(e)}"}), 500

    try:
        if exchange == "TOSS":
            client = TossClient(client_id=client_id, client_secret=client_secret, account_seq=toss_account_seq, env=broker_env)
            # 계좌 목록이 성공적으로 확보되면 연결 성공으로 판단
            client.get_accounts()
            message = "Toss Open API 연결에 성공했습니다."
        elif exchange == "KIS":
            if not cano:
                return jsonify({"success": False, "message": "KIS 테스트를 위해서는 계좌번호(cano)가 필수적입니다."}), 400
            client = KISClient(appkey=client_id, appsecret=client_secret, cano=cano, acnt_prdt_cd=acnt_prdt_cd, env=broker_env)
            client.get_balance()
            message = "KIS API 연결에 성공했습니다."
        elif exchange == "COINONE":
            client = CoinoneClient(access_token=client_id, secret_key=client_secret)
            client.get_balance()
            message = "코인원 API 연결에 성공했습니다."
        elif exchange == "BINANCE":
            client = BinanceClient(api_key=client_id, secret_key=client_secret)
            client.get_balance()
            message = "바이낸스 API 연결에 성공했습니다."
        else:
            return jsonify({"success": False, "message": f"지원하지 않는 브로커: {exchange}"}), 400

        return jsonify({
            "success": True,
            "message": message
        })
    except Exception as e:
        error_type = classify_error(exchange, e)
        return jsonify({
            "success": False,
            "error_type": error_type,
            "message": f"연결 테스트 실패: {str(e)}"
        }), 500


# 5. 실시간 잔고 조회 API (대시보드 동적 연동용)
@app.route("/api/dashboard/balance", methods=["POST"])
def get_dashboard_balance():
    auth_header = request.headers.get("Authorization")
    if not auth_header:
        return jsonify({"success": False, "message": "인증 헤더가 누락되었습니다."}), 401

    data = request.json or {}
    exchange = data.get("exchange", "KIS")
    broker_env = data.get("env", "MOCK") # Dashboard.jsx 호환성

    try:
        user_id, token = get_user_id_from_header(auth_header)
        
        # DB에서 암호화된 API Key 조회
        params = {
            "user_id": f"eq.{user_id}",
            "exchange": f"eq.{exchange}",
            "broker_env": f"eq.{broker_env}"
        }
        records = query_supabase(auth_header, "user_api_keys", "GET", params=params)
        if not records or len(records) == 0:
            return jsonify({"success": False, "message": f"등록된 {exchange} ({broker_env}) API 키가 없습니다."}), 404
            
        record = records[0]
        access_key = crypto.decrypt(record.get("encrypted_access_key"))
        secret_key = crypto.decrypt(record.get("encrypted_secret_key"))
        
        if exchange == "TOSS":
            account_seq = record.get("toss_account_seq")
            client = TossClient(
                client_id=access_key,
                client_secret=secret_key,
                account_seq=account_seq,
                env=broker_env
            )
            balance = client.get_balance()
        elif exchange == "KIS":
            cano = record.get("kis_account_no")
            acnt_prdt_cd = record.get("kis_account_code", "01")
            client = KISClient(
                appkey=access_key,
                appsecret=secret_key,
                cano=cano,
                acnt_prdt_cd=acnt_prdt_cd,
                env=broker_env
            )
            balance = client.get_balance()
        elif exchange == "COINONE":
            client = CoinoneClient(
                access_token=access_key,
                secret_key=secret_key
            )
            balance = client.get_balance()
        elif exchange == "BINANCE":
            client = BinanceClient(
                api_key=access_key,
                secret_key=secret_key
            )
            balance = client.get_balance()
        else:
            return jsonify({"success": False, "message": f"지원하지 않는 거래소: {exchange}"}), 400
            
        return jsonify({
            "success": True,
            "data": balance
        })
    except Exception as e:
        return jsonify({
            "success": False,
            "message": f"잔고 조회 중 실패: {str(e)}"
        }), 500


@app.route("/api/news", methods=["GET"])
def get_news_feed():
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
