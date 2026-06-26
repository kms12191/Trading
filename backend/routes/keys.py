import requests
from flask import Blueprint, request, jsonify, current_app
from backend.services.supabase_client import query_supabase, upsert_user_api_key
from backend.services.auth_service import get_user_id_from_header
from backend.services.keys_service import classify_error
from backend.services.toss_client import TossClient
from backend.services.kis_client import KISClient
from backend.services.coinone_client import CoinoneClient
from backend.services.binance_client import BinanceClient

keys_bp = Blueprint("keys", __name__)

@keys_bp.route("/api/keys/status", methods=["GET"])
def get_keys_status():
    """사용자가 등록한 거래소별 API 키의 암호화 저장 상태 및 정보를 마스킹하여 반환합니다."""
    auth_header = request.headers.get("Authorization")
    if not auth_header:
        return jsonify({"success": False, "message": "인증 헤더가 누락되었습니다."}), 401
    
    try:
        user_id, token = get_user_id_from_header(auth_header)
        params = {"user_id": f"eq.{user_id}"}
        records = query_supabase(auth_header, "user_api_keys", "GET", params=params)
        
        result = {
            "TOSS": {"registered": False},
            "KIS": {"registered": False},
            "COINONE": {"registered": False},
            "BINANCE": {"registered": False}
        }
        
        crypto_helper = current_app.crypto
        for record in records:
            ex = record.get("exchange")
            if ex not in result:
                continue
                
            enc_key = record.get("encrypted_access_key")
            mask_key = ""
            if enc_key:
                try:
                    plain_key = crypto_helper.decrypt(enc_key)
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

@keys_bp.route("/api/keys/save", methods=["POST"])
def save_api_keys():
    """사용자가 입력한 거래소별 크리덴셜 및 계좌 식별정보를 암호화하여 Supabase DB에 적재합니다."""
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

        crypto_helper = current_app.crypto
        # 브로커별 키 암호화 및 컬럼 패킹
        if exchange == "TOSS":
            client_id = data.get("client_id")
            client_secret = data.get("client_secret")
            toss_account_seq = data.get("toss_account_seq")
            toss_account_no = data.get("toss_account_no")

            if not client_id or not client_secret:
                return jsonify({"success": False, "message": "client_id와 client_secret이 필수적입니다."}), 400

            db_data["encrypted_access_key"] = crypto_helper.encrypt(client_id)
            db_data["encrypted_secret_key"] = crypto_helper.encrypt(client_secret)
            db_data["toss_account_seq"] = toss_account_seq
            db_data["toss_account_no"] = toss_account_no

        elif exchange == "KIS":
            appkey = data.get("appkey")
            appsecret = data.get("appsecret")
            cano = data.get("cano")
            acnt_prdt_cd = data.get("acnt_prdt_cd", "01")

            if not appkey or not appsecret or not cano:
                return jsonify({"success": False, "message": "appkey, appsecret, cano가 필수적입니다."}), 400

            db_data["encrypted_access_key"] = crypto_helper.encrypt(appkey)
            db_data["encrypted_secret_key"] = crypto_helper.encrypt(appsecret)
            db_data["kis_account_no"] = cano
            db_data["kis_account_code"] = acnt_prdt_cd

        elif exchange == "COINONE":
            access_token = data.get("access_token")
            secret_key = data.get("secret_key")

            if not access_token or not secret_key:
                return jsonify({"success": False, "message": "access_token과 secret_key가 필수적입니다."}), 400

            db_data["encrypted_access_key"] = crypto_helper.encrypt(access_token)
            db_data["encrypted_secret_key"] = crypto_helper.encrypt(secret_key)

        elif exchange == "BINANCE":
            api_key = data.get("api_key")
            secret_key = data.get("secret_key")

            if not api_key or not secret_key:
                return jsonify({"success": False, "message": "api_key와 secret_key가 필수적입니다."}), 400

            db_data["encrypted_access_key"] = crypto_helper.encrypt(api_key)
            db_data["encrypted_secret_key"] = crypto_helper.encrypt(secret_key)

        upsert_user_api_key(auth_header, db_data)
        return jsonify({"success": True, "message": f"{exchange} API Key가 안전하게 저장되었습니다."})
    except Exception as e:
        return jsonify({"success": False, "message": f"API Key 저장 실패: {str(e)}"}), 500

@keys_bp.route("/api/keys/toss/accounts", methods=["POST"])
def get_toss_accounts():
    """Toss증권 계좌 목록을 얻어오는 전용 API를 제공합니다."""
    auth_header = request.headers.get("Authorization")
    if not auth_header:
        return jsonify({"success": False, "message": "인증 헤더가 누락되었습니다."}), 401

    data = request.json or {}
    client_id = data.get("client_id")
    client_secret = data.get("client_secret")
    broker_env = data.get("broker_env", "REAL")

    crypto_helper = current_app.crypto
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
            
            client_id = crypto_helper.decrypt(records[0].get("encrypted_access_key"))
            client_secret = crypto_helper.decrypt(records[0].get("encrypted_secret_key"))
        except Exception as e:
            return jsonify({"success": False, "message": f"DB 조회 실패: {str(e)}"}), 500

    try:
        client = TossClient(client_id=client_id, client_secret=client_secret, env=broker_env)
        accounts = client.get_accounts()
        return jsonify({"success": True, "data": accounts})
    except Exception as e:
        return jsonify({"success": False, "message": f"Toss 계좌 조회 실패: {str(e)}"}), 500

@keys_bp.route("/api/keys/test", methods=["POST"])
def test_keys():
    """임시 혹은 DB에 저장된 API Key 크리덴셜의 연결 가능 여부를 실시간 검증합니다."""
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
    
    cano = data.get("cano")
    acnt_prdt_cd = data.get("acnt_prdt_cd", "01")
    toss_account_seq = data.get("toss_account_seq")

    crypto_helper = current_app.crypto
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
            client_id = crypto_helper.decrypt(record.get("encrypted_access_key"))
            client_secret = crypto_helper.decrypt(record.get("encrypted_secret_key"))
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
