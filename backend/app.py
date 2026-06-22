import os
import sys
from flask import Flask, request, jsonify
from flask_cors import CORS
from dotenv import load_dotenv

# Ensure backend directory is in python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.utils.crypto_helper import CryptoHelper
from backend.services.kis_client import KISClient

load_dotenv()

app = Flask(__name__)
# Enable CORS for frontend integration
CORS(app, resources={r"/api/*": {"origins": "*"}})

# Encryption key from environment variables
ENCRYPTION_KEY = os.getenv("ENCRYPTION_KEY", "default-dev-encryption-key-32bytes!")

crypto = CryptoHelper(ENCRYPTION_KEY)

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

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5050, debug=True)
