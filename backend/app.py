import csv
import json
import os
import sys
import re
import subprocess
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from flask import Flask, request, jsonify
from flask_cors import CORS
from dotenv import load_dotenv
import requests
import jwt

# backend 디렉토리가 파이썬 경로에 포함되도록 설정
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.utils.crypto_helper import CryptoHelper
from backend.services.kis_client import KISClient
from backend.services.kis_market_universe import KISMarketUniverseService
from backend.services.toss_client import TossClient
from backend.services.coinone_client import CoinoneClient
from backend.services.binance_client import BinanceClient
from backend.services.news_repository import NewsRepository
from backend.services.news_ingest import NewsIngestService
from backend.services.news_summary_service import NewsSummaryService
from backend.services.ml_job_service import create_job, list_jobs, run_ml_pipeline, update_job
from backend.services.ml_automation_service import list_automation_presets, resolve_automation_preset
from backend.services.ml_registry_service import list_model_registry, set_serving_model, upsert_model_registry
from backend.services.symbol_metadata import enrich_symbol
from backend.scripts.export_training_candles import (
    DEFAULT_UNIVERSE_PATH,
    fetch_binance_klines,
    fetch_macro_indices,
    fetch_toss_candles,
    load_preset_symbols,
    write_rows,
)

load_dotenv()

app = Flask(__name__)
# 프론트엔드 연동을 위해 CORS 활성화 및 Authorization 헤더 허용
CORS(app, resources={r"/api/*": {"origins": "*"}}, supports_credentials=True)

# 환경 변수에서 암호화 키 및 Supabase 정보 로드
ENCRYPTION_KEY = os.getenv("ENCRYPTION_KEY", "default-dev-encryption-key-32bytes!")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY")
KIS_APPKEY = os.getenv("KIS_APPKEY", "")
KIS_APPSECRET = os.getenv("KIS_APPSECRET", "")
KIS_CANO = os.getenv("KIS_CANO", "")
KIS_ACNT_PRDT_CD = os.getenv("KIS_ACNT_PRDT_CD", "01")
KIS_ENV = os.getenv("KIS_ENV", "MOCK")

crypto = CryptoHelper(ENCRYPTION_KEY)
news_repository = NewsRepository()
news_ingest_service = NewsIngestService()
news_summary_service = NewsSummaryService()
kis_market_universe_service = KISMarketUniverseService()
PROJECT_ROOT = Path(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

NEWS_INGEST_ENABLED = os.getenv("NEWS_INGEST_ENABLED", "false").lower() == "true"
NEWS_INGEST_INTERVAL_SECONDS = int(os.getenv("NEWS_INGEST_INTERVAL_SECONDS", "600"))
_news_ingest_started = False
COINONE_WATCHLIST = ["BTC", "ETH", "XRP", "SOL"]
COINONE_HOME_LIMIT = int(os.getenv("COINONE_HOME_LIMIT", "50"))
KIS_MARKET_MASTER_FILE_PATH = os.getenv("KIS_MARKET_MASTER_FILE_PATH", "")


def _to_float(value, default=0.0):
    try:
        if value is None or value == "":
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _normalize_coinone_ticker(symbol: str, ticker: dict) -> dict:
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
    trading_volume = _to_float(
        ticker.get("volume")
        or ticker.get("trading_volume")
        or ticker.get("quote_volume")
        or ticker.get("acc_volume")
    )
    trading_value = _to_float(
        ticker.get("quote_volume")
        or ticker.get("trading_value")
        or ticker.get("acc_trading_value")
    )

    if not change_rate and first:
        change_rate = ((last - first) / first) * 100 if first else 0.0

    if not first:
        first = last

    if not trading_value and last and trading_volume:
        trading_value = last * trading_volume

    return {
        "symbol": symbol,
        "name": symbol,
        "price": last,
        "open": first,
        "high": high,
        "low": low,
        "change_rate": change_rate,
        "trading_volume": trading_volume,
        "trading_value": trading_value,
    }


def _fetch_coinone_overview(limit=COINONE_HOME_LIMIT) -> list[dict]:
    url = "https://api.coinone.co.kr/public/v2/ticker_new/KRW"
    response = requests.get(url, params={"additional_data": "true"}, timeout=10)
    response.raise_for_status()
    payload = response.json()
    if payload.get("result") not in (None, "success"):
        raise Exception(payload.get("error_message") or payload.get("message") or "Coinone API error")

    rows = []
    for ticker in payload.get("tickers", []):
        symbol = str(
            ticker.get("target_currency")
            or ticker.get("currency")
            or ticker.get("symbol")
            or ""
        ).upper().strip()
        if not symbol:
            continue
        rows.append(_normalize_coinone_ticker(symbol, ticker))

    rows.sort(key=lambda item: (item.get("trading_value", 0.0), abs(item.get("change_rate", 0.0))), reverse=True)
    return rows[:limit]


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


def _resolve_kis_credentials(data: dict) -> dict:
    return {
        "appkey": data.get("appkey") or KIS_APPKEY,
        "appsecret": data.get("appsecret") or KIS_APPSECRET,
        "cano": data.get("cano") or KIS_CANO,
        "acnt_prdt_cd": data.get("acnt_prdt_cd") or KIS_ACNT_PRDT_CD,
        "env": (data.get("env") or KIS_ENV or "MOCK").upper(),
    }


def _build_home_overview(data: dict) -> dict:
    kis = _resolve_kis_credentials(data)
    appkey = kis["appkey"]
    appsecret = kis["appsecret"]
    cano = kis["cano"]
    acnt_prdt_cd = kis["acnt_prdt_cd"]
    env = kis["env"]

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

    if not (appkey and appsecret and cano):
        if not result["message"]:
            result["message"] = "KIS 환경변수가 없어서 국내/해외 보유 종목은 비어 있습니다."
        return result

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
    return result


@app.route("/api/home/market", methods=["POST"])
def get_home_market():
    try:
        data = request.json or {}
        overview = _build_home_overview(data)
        return jsonify({
            "success": True,
            "data": overview
        })
    except Exception as error:
        return jsonify({
            "success": False,
            "message": f"홈 시장 데이터 조회 실패: {str(error)}",
        }), 500


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

@app.route("/api/market/kis/sync", methods=["POST"])
def sync_kis_market_universe():
    data = request.json or {}
    file_paths = data.get("file_paths")
    file_path = data.get("file_path") or KIS_MARKET_MASTER_FILE_PATH
    refresh_quotes = bool(data.get("refresh_quotes", True))
    max_workers = int(data.get("max_workers") or 4)
    quote_limit_raw = data.get("quote_limit", 300)
    quote_limit = None if quote_limit_raw in (None, "", "all", "ALL") else int(quote_limit_raw)

    if isinstance(file_paths, str):
        file_paths = [part.strip() for part in file_paths.split(",") if part.strip()]
    elif isinstance(file_paths, list):
        file_paths = [str(part).strip() for part in file_paths if str(part).strip()]
    else:
        file_paths = []

    if file_path and not file_paths:
        file_paths = [part.strip() for part in str(file_path).split(",") if part.strip()]

    if not file_paths:
        return jsonify({
            "success": False,
            "message": "KIS 종목 정보 파일 경로가 필요합니다. body.file_path, body.file_paths 또는 KIS_MARKET_MASTER_FILE_PATH를 설정해주세요.",
        }), 400

    if not kis_market_universe_service.repository.is_configured:
        return jsonify({
            "success": False,
            "message": "SUPABASE_SERVICE_ROLE_KEY가 필요합니다. Supabase 관리 키를 .env에 넣어주세요.",
        }), 500

    try:
        kis_client = KISClient(
            appkey=KIS_APPKEY,
            appsecret=KIS_APPSECRET,
            cano=KIS_CANO,
            acnt_prdt_cd=KIS_ACNT_PRDT_CD,
            env=KIS_ENV,
        )
        result = kis_market_universe_service.sync_from_files(
            file_paths=file_paths,
            kis_client=kis_client,
            refresh_quotes=refresh_quotes,
            max_workers=max_workers,
            quote_limit=quote_limit,
        )
        return jsonify({
            "success": True,
            "message": "KIS 종목 마스터와 거래대금 스냅샷 동기화가 완료되었습니다.",
            "data": result,
        })
    except Exception as error:
        return jsonify({
            "success": False,
            "message": f"KIS 종목 동기화 실패: {str(error)}",
        }), 500


@app.route("/api/market/rankings", methods=["GET"])
def get_market_rankings():
    market_segment = request.args.get("market_segment", "ALL")
    limit = int(request.args.get("limit", 50))

    try:
        rankings = kis_market_universe_service.repository.list_turnover_rankings(
            market_segment=market_segment,
            limit=limit,
        )
        universe_count = kis_market_universe_service.repository.count_universe(market_segment=market_segment)
        return jsonify({
            "success": True,
            "data": {
                "items": rankings,
                "totalCount": len(rankings),
                "universeCount": universe_count,
                "marketSegment": market_segment.upper(),
                "limit": limit,
            }
        })
    except Exception as error:
        return jsonify({
            "success": False,
            "message": f"거래대금 순위 조회 실패: {str(error)}",
        }), 500


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


def safe_query_supabase(auth_header, endpoint, method="GET", json_data=None, params=None):
    """
    Supabase 작업 로깅용 베스트 에포트 호출.
    테이블이 아직 없거나 권한이 없어도 서비스 흐름은 계속 진행합니다.
    """
    try:
        return query_supabase(auth_header, endpoint, method=method, json_data=json_data, params=params)
    except Exception:
        return None


def sync_dataset_job_to_supabase(auth_header, job: dict):
    user_id, _ = get_user_id_from_header(auth_header)
    payload = {
        "id": job["id"],
        "user_id": user_id,
        "asset_type": job.get("asset_type"),
        "exchange": job.get("exchange"),
        "preset_name": job.get("preset_name"),
        "interval": job.get("interval"),
        "count": job.get("count"),
        "chunk_size": job.get("chunk_size"),
        "chunk_index": job.get("chunk_index"),
        "symbols": job.get("symbols", []),
        "status": job.get("status"),
        "row_count": job.get("row_count"),
        "failure_count": job.get("failure_count", 0),
        "output_path": job.get("output"),
        "failure_output_path": job.get("failure_output_path"),
        "failures": job.get("failures", []),
        "error_message": job.get("error"),
        "started_at": job.get("started_at"),
        "finished_at": job.get("finished_at"),
    }
    existing = safe_query_supabase(auth_header, "ml_dataset_jobs", "GET", params={"id": f"eq.{job['id']}"})
    if existing:
        safe_query_supabase(auth_header, f"ml_dataset_jobs?id=eq.{job['id']}", "PATCH", json_data=payload)
    else:
        safe_query_supabase(auth_header, "ml_dataset_jobs", "POST", json_data=payload)


def sync_training_job_to_supabase(auth_header, job: dict):
    user_id, _ = get_user_id_from_header(auth_header)
    summary_json = None
    summary_output = job.get("summary_output")
    if summary_output:
        summary_path = PROJECT_ROOT / summary_output if not str(summary_output).startswith("/") else Path(summary_output)
        if summary_path.exists():
            try:
                summary_json = json.loads(summary_path.read_text(encoding="utf-8"))
            except Exception:
                summary_json = None

    payload = {
        "id": job["id"],
        "user_id": user_id,
        "label": job.get("label"),
        "asset_type": (summary_json or {}).get("metrics", {}).get("asset_type"),
        "config_path": job.get("config"),
        "risk_config_path": job.get("risk_config"),
        "summary_output_path": summary_output,
        "skip_build_features": job.get("skip_build_features", False),
        "model_version": (summary_json or {}).get("model_version"),
        "status": job.get("status"),
        "command": job.get("command", []),
        "returncode": job.get("returncode"),
        "stdout_tail": job.get("stdout"),
        "stderr_tail": job.get("stderr"),
        "metrics_json": (summary_json or {}).get("metrics"),
        "risk_metrics_json": (summary_json or {}).get("risk_metrics"),
        "backtest_up_only_json": (summary_json or {}).get("backtest_up_only_summary"),
        "backtest_composite_json": (summary_json or {}).get("backtest_composite_summary"),
        "started_at": job.get("started_at"),
        "finished_at": job.get("finished_at"),
    }
    existing = safe_query_supabase(auth_header, "ml_training_runs", "GET", params={"id": f"eq.{job['id']}"})
    if existing:
        safe_query_supabase(auth_header, f"ml_training_runs?id=eq.{job['id']}", "PATCH", json_data=payload)
    else:
        safe_query_supabase(auth_header, "ml_training_runs", "POST", json_data=payload)


def sync_model_registry_to_supabase(auth_header, summary_output: str | None):
    if not summary_output:
        return

    summary_path = PROJECT_ROOT / summary_output if not str(summary_output).startswith("/") else Path(summary_output)
    if not summary_path.exists():
        return

    try:
        summary_json = json.loads(summary_path.read_text(encoding="utf-8"))
    except Exception:
        return

    asset_type = str((summary_json.get("metrics") or {}).get("asset_type") or "").upper()
    model_version = str(summary_json.get("model_version") or "")
    metrics_path = str(summary_json.get("metrics_path") or "")
    model_path = metrics_path.replace(".metrics.json", ".joblib") if metrics_path.endswith(".metrics.json") else ""

    if asset_type not in ("STOCK", "CRYPTO") or not model_version:
        return

    asset_key = "stock" if asset_type == "STOCK" else "crypto"
    version_results = _discover_model_versions(asset_key)
    latest_result = _pick_default_model_result(version_results)
    recommended_result = _pick_recommended_model_result(version_results)
    is_latest = bool(latest_result and latest_result.get("metrics", {}).get("model_version") == model_version)
    is_recommended = bool(recommended_result and recommended_result.get("metrics", {}).get("model_version") == model_version)

    safe_query_supabase(
        auth_header,
        f"ml_model_registry?asset_type=eq.{asset_type}",
        "PATCH",
        json_data={
            "is_latest": False,
            "is_recommended": False,
        },
    )

    payload = {
        "asset_type": asset_type,
        "model_version": model_version,
        "model_path": model_path,
        "metrics_path": metrics_path,
        "summary_path": str(summary_path),
        "recommendation_reason": "file-based score comparison",
        "is_latest": is_latest,
        "is_recommended": is_recommended,
        "is_serving": False,
    }
    existing = safe_query_supabase(
        auth_header,
        "ml_model_registry",
        "GET",
        params={
            "asset_type": f"eq.{asset_type}",
            "model_version": f"eq.{model_version}",
        },
    )
    if existing:
        record_id = existing[0]["id"]
        safe_query_supabase(auth_header, f"ml_model_registry?id=eq.{record_id}", "PATCH", json_data=payload)
    else:
        safe_query_supabase(auth_header, "ml_model_registry", "POST", json_data=payload)

    upsert_model_registry(
        {
            "asset_type": asset_type,
            "model_version": model_version,
            "model_path": model_path,
            "metrics_path": metrics_path,
            "summary_path": str(summary_path),
            "recommendation_reason": "file-based score comparison",
            "is_latest": is_latest,
            "is_recommended": is_recommended,
            "is_serving": False,
        }
    )

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


@app.route("/api/ml/export-candles", methods=["POST"])
def export_ml_candles():
    """
    관리자 페이지에서 학습용 캔들 CSV를 생성합니다.
    사용자의 API Key는 프론트엔드로 전달하지 않고 서버 내부에서만 사용합니다.
    """
    auth_header = request.headers.get("Authorization")
    if not auth_header:
        return jsonify({"success": False, "message": "인증 헤더가 누락되었습니다."}), 401

    data = request.json or {}
    asset_type = str(data.get("asset_type", "")).upper()
    exchange = str(data.get("exchange", "")).upper()
    symbols = data.get("symbols") or []
    preset_name = str(data.get("preset") or "").strip() or None
    interval = data.get("interval")
    count = int(data.get("count") or 200)
    sleep_seconds = float(data.get("sleep_seconds") if data.get("sleep_seconds") is not None else 2.0)
    retry = int(data.get("retry") if data.get("retry") is not None else 3)
    retry_wait_seconds = float(data.get("retry_wait_seconds") if data.get("retry_wait_seconds") is not None else 60.0)
    append = bool(data.get("append", True))
    include_macro = bool(data.get("include_macro", False))
    chunk_size = int(data.get("chunk_size") or 0)
    chunk_index = int(data.get("chunk_index") or 1)

    if isinstance(symbols, str):
        symbols = [symbol.strip().upper() for symbol in symbols.split(",") if symbol.strip()]
    else:
        symbols = [str(symbol).strip().upper() for symbol in symbols if str(symbol).strip()]

    if preset_name:
        preset_symbols = load_preset_symbols(preset_name, DEFAULT_UNIVERSE_PATH)
        symbols = list(dict.fromkeys([*symbols, *preset_symbols]))

    if chunk_size > 0:
        start = max(0, (max(1, chunk_index) - 1) * chunk_size)
        end = start + chunk_size
        symbols = symbols[start:end]

    if not symbols:
        return jsonify({"success": False, "message": "수집할 심볼 또는 preset을 입력해 주세요."}), 400

    if count < 1 or count > 1000:
        return jsonify({"success": False, "message": "count는 1 이상 1000 이하로 입력해 주세요."}), 400

    try:
        token = auth_header.split(" ", 1)[1] if auth_header.startswith("Bearer ") else auth_header
        dataset_job = create_job(
            "dataset_export",
            {
                "asset_type": asset_type,
                "exchange": exchange,
                "symbols": symbols,
                "preset_name": preset_name,
                "interval": interval or ("1d" if exchange == "TOSS" else "1h"),
                "count": count,
                "chunk_size": chunk_size or None,
                "chunk_index": chunk_index if chunk_size > 0 else None,
            },
        )

        if include_macro:
            macro_rows = fetch_macro_indices(count)
            macro_output = PROJECT_ROOT / "ml" / "data" / "raw" / "macro_indices.csv"
            write_rows(macro_output, macro_rows, append=append)

        if exchange == "TOSS" and asset_type == "STOCK":
            rows, failures = fetch_toss_candles(
                symbols,
                token,
                interval or "1d",
                count,
                sleep_seconds=sleep_seconds,
                retry=retry,
                retry_wait_seconds=retry_wait_seconds,
            )
            output = PROJECT_ROOT / "ml" / "data" / "raw" / "stock_candles.csv"
        elif exchange == "BINANCE" and asset_type == "CRYPTO":
            rows, failures = fetch_binance_klines(
                symbols,
                interval or "1h",
                count,
                sleep_seconds=sleep_seconds,
                retry=retry,
                retry_wait_seconds=retry_wait_seconds,
            )
            output = PROJECT_ROOT / "ml" / "data" / "raw" / "crypto_candles.csv"
        else:
            return jsonify({"success": False, "message": "지원하지 않는 asset_type/exchange 조합입니다."}), 400

        write_rows(output, rows, append=append)
        update_job(
            dataset_job["id"],
            {
                "status": "success",
                "finished_at": datetime.utcnow().isoformat() + "Z",
                "output": str(output),
                "row_count": len(rows),
                "failure_count": len(failures),
                "failures": failures[:50],
                "append": append,
                "preset_name": preset_name,
                "include_macro": include_macro,
                "chunk_size": chunk_size or None,
                "chunk_index": chunk_index if chunk_size > 0 else None,
            },
        )
        latest_dataset_job = next((job for job in list_jobs(limit=100) if job.get("id") == dataset_job["id"]), None)
        if latest_dataset_job:
            sync_dataset_job_to_supabase(auth_header, latest_dataset_job)

        return jsonify({
            "success": True,
            "message": "학습용 캔들 CSV 생성이 완료되었습니다.",
            "data": {
                "job_id": dataset_job["id"],
                "output": str(output),
                "row_count": len(rows),
                "failure_count": len(failures),
                "failures": failures[:20],
                "symbols": symbols,
                "preset_name": preset_name,
                "asset_type": asset_type,
                "exchange": exchange,
                "interval": interval or ("1d" if exchange == "TOSS" else "1h"),
                "count": count,
                "sleep_seconds": sleep_seconds,
                "retry": retry,
                "retry_wait_seconds": retry_wait_seconds,
                "append": append,
                "include_macro": include_macro,
                "chunk_size": chunk_size or None,
                "chunk_index": chunk_index if chunk_size > 0 else None,
            }
        })
    except Exception as e:
        if "dataset_job" in locals():
            failed_job = update_job(
                dataset_job["id"],
                {
                    "status": "failed",
                    "finished_at": datetime.utcnow().isoformat() + "Z",
                    "error": str(e),
                },
            )
            if failed_job:
                sync_dataset_job_to_supabase(auth_header, failed_job)
        return jsonify({
            "success": False,
            "message": f"학습용 캔들 CSV 생성 실패: {str(e)}"
        }), 500


@app.route("/api/ml/jobs", methods=["GET"])
def get_ml_jobs():
    auth_header = request.headers.get("Authorization")
    if not auth_header:
        return jsonify({"success": False, "message": "인증 헤더가 누락되었습니다."}), 401

    try:
        get_user_id_from_header(auth_header)
        limit = int(request.args.get("limit", 20))
        return jsonify({
            "success": True,
            "data": {
                "jobs": list_jobs(limit=limit),
            }
        })
    except Exception as e:
        return jsonify({
            "success": False,
            "message": f"작업 이력 조회 실패: {str(e)}"
        }), 500


@app.route("/api/ml/jobs/train", methods=["POST"])
def run_ml_training_job():
    auth_header = request.headers.get("Authorization")
    if not auth_header:
        return jsonify({"success": False, "message": "인증 헤더가 누락되었습니다."}), 401

    try:
        get_user_id_from_header(auth_header)
        data = request.json or {}
        config = str(data.get("config") or "").strip()
        risk_config = str(data.get("risk_config") or "").strip() or None
        summary_output = str(data.get("summary_output") or "").strip() or None
        skip_build_features = bool(data.get("skip_build_features", False))
        label = str(data.get("label") or config or "ml-train").strip()

        if not config:
            return jsonify({"success": False, "message": "config 경로가 필요합니다."}), 400

        train_job = create_job(
            "training_run",
            {
                "label": label,
                "config": config,
                "risk_config": risk_config,
                "summary_output": summary_output,
                "skip_build_features": skip_build_features,
            },
        )

        result = run_ml_pipeline(
            config_path=config,
            risk_config_path=risk_config,
            skip_build_features=skip_build_features,
            summary_output=summary_output,
        )

        update_job(
            train_job["id"],
            {
                "status": "success" if result["success"] else "failed",
                "finished_at": datetime.utcnow().isoformat() + "Z",
                "command": result["command"],
                "returncode": result["returncode"],
                "stdout": result["stdout"][-12000:],
                "stderr": result["stderr"][-12000:],
            },
        )
        latest_training_job = next((job for job in list_jobs(limit=100) if job.get("id") == train_job["id"]), None)
        if latest_training_job:
            sync_training_job_to_supabase(auth_header, latest_training_job)
        sync_model_registry_to_supabase(auth_header, summary_output)
        auto_report = None
        if result["success"]:
            try:
                auto_report = _run_experiment_report(auth_header=auth_header, output=None)
            except Exception:
                auto_report = None

        status_code = 200 if result["success"] else 500
        return jsonify({
            "success": result["success"],
            "message": "ML 학습 작업이 완료되었습니다." if result["success"] else "ML 학습 작업이 실패했습니다.",
            "data": {
                "job_id": train_job["id"],
                "report": auto_report,
                **result,
            }
        }), status_code
    except Exception as e:
        return jsonify({
            "success": False,
            "message": f"ML 학습 작업 실행 실패: {str(e)}"
        }), 500


@app.route("/api/ml/automation/presets", methods=["GET"])
def get_ml_automation_presets():
    auth_header = request.headers.get("Authorization")
    if not auth_header:
        return jsonify({"success": False, "message": "인증 헤더가 누락되었습니다."}), 401

    try:
        get_user_id_from_header(auth_header)
        return jsonify({
            "success": True,
            "data": {
                "presets": list_automation_presets(),
            }
        })
    except Exception as e:
        return jsonify({
            "success": False,
            "message": f"자동화 프리셋 조회 실패: {str(e)}"
        }), 500


@app.route("/api/ml/jobs/full-run", methods=["POST"])
def run_ml_full_pipeline_job():
    auth_header = request.headers.get("Authorization")
    if not auth_header:
        return jsonify({"success": False, "message": "인증 헤더가 누락되었습니다."}), 401

    try:
        get_user_id_from_header(auth_header)
        data = request.json or {}
        preset_key = str(data.get("preset_key") or "").strip()
        if not preset_key:
            return jsonify({"success": False, "message": "preset_key가 필요합니다."}), 400

        preset = resolve_automation_preset(preset_key)
        dataset_config = preset["dataset"]
        training_config = preset["training"]
        token = auth_header.split(" ", 1)[1] if auth_header.startswith("Bearer ") else auth_header

        dataset_job = create_job(
            "dataset_export",
            {
                "label": preset["label"],
                "asset_type": dataset_config["asset_type"],
                "exchange": dataset_config["exchange"],
                "symbols": dataset_config.get("symbols") or [],
                "preset_name": dataset_config.get("preset"),
                "interval": dataset_config["interval"],
                "count": dataset_config["count"],
                "chunk_size": dataset_config.get("chunk_size"),
                "chunk_index": dataset_config.get("chunk_index"),
            },
        )

        preset_symbols = []
        if dataset_config.get("preset"):
            preset_symbols = load_preset_symbols(dataset_config["preset"], DEFAULT_UNIVERSE_PATH)
        symbols = list(dict.fromkeys([*(dataset_config.get("symbols") or []), *preset_symbols]))
        chunk_size = int(dataset_config.get("chunk_size") or 0)
        chunk_index = int(dataset_config.get("chunk_index") or 1)
        if chunk_size > 0:
            start = max(0, (max(1, chunk_index) - 1) * chunk_size)
            end = start + chunk_size
            symbols = symbols[start:end]
        if not symbols:
            raise ValueError("자동화 프리셋에서 실제 수집 심볼이 비어 있습니다.")

        if dataset_config.get("include_macro"):
            macro_rows = fetch_macro_indices(int(dataset_config["count"]))
            macro_output = PROJECT_ROOT / "ml" / "data" / "raw" / "macro_indices.csv"
            write_rows(macro_output, macro_rows, append=bool(dataset_config.get("append", True)))

        if dataset_config["exchange"] == "TOSS" and dataset_config["asset_type"] == "STOCK":
            rows, failures = fetch_toss_candles(
                symbols,
                token,
                dataset_config["interval"],
                int(dataset_config["count"]),
                sleep_seconds=float(dataset_config.get("sleep_seconds", 2.0)),
                retry=int(dataset_config.get("retry", 3)),
                retry_wait_seconds=float(dataset_config.get("retry_wait_seconds", 60.0)),
            )
            output = PROJECT_ROOT / "ml" / "data" / "raw" / "stock_candles.csv"
        elif dataset_config["exchange"] == "BINANCE" and dataset_config["asset_type"] == "CRYPTO":
            rows, failures = fetch_binance_klines(
                symbols,
                dataset_config["interval"],
                int(dataset_config["count"]),
                sleep_seconds=float(dataset_config.get("sleep_seconds", 0.2)),
                retry=int(dataset_config.get("retry", 2)),
                retry_wait_seconds=float(dataset_config.get("retry_wait_seconds", 10.0)),
            )
            output = PROJECT_ROOT / "ml" / "data" / "raw" / "crypto_candles.csv"
        else:
            raise ValueError("지원하지 않는 자동화 dataset 조합입니다.")

        write_rows(output, rows, append=bool(dataset_config.get("append", True)))
        update_job(
            dataset_job["id"],
            {
                "status": "success",
                "finished_at": datetime.utcnow().isoformat() + "Z",
                "output": str(output),
                "row_count": len(rows),
                "failure_count": len(failures),
                "failures": failures[:50],
                "append": bool(dataset_config.get("append", True)),
                "symbols": symbols,
                "preset_name": dataset_config.get("preset"),
            },
        )
        latest_dataset_job = next((job for job in list_jobs(limit=100) if job.get("id") == dataset_job["id"]), None)
        if latest_dataset_job:
            sync_dataset_job_to_supabase(auth_header, latest_dataset_job)

        train_job = create_job(
            "training_run",
            {
                "label": preset["label"],
                "config": training_config["config"],
                "risk_config": training_config.get("risk_config"),
                "summary_output": training_config.get("summary_output"),
                "skip_build_features": bool(training_config.get("skip_build_features", False)),
                "dataset_job_id": dataset_job["id"],
            },
        )
        result = run_ml_pipeline(
            config_path=training_config["config"],
            risk_config_path=training_config.get("risk_config"),
            skip_build_features=bool(training_config.get("skip_build_features", False)),
            summary_output=training_config.get("summary_output"),
        )
        update_job(
            train_job["id"],
            {
                "status": "success" if result["success"] else "failed",
                "finished_at": datetime.utcnow().isoformat() + "Z",
                "command": result["command"],
                "returncode": result["returncode"],
                "stdout": result["stdout"][-12000:],
                "stderr": result["stderr"][-12000:],
            },
        )
        latest_training_job = next((job for job in list_jobs(limit=100) if job.get("id") == train_job["id"]), None)
        if latest_training_job:
            sync_training_job_to_supabase(auth_header, latest_training_job)
        sync_model_registry_to_supabase(auth_header, training_config.get("summary_output"))
        auto_report = None
        if result["success"]:
            try:
                auto_report = _run_experiment_report(auth_header=auth_header, output=None)
            except Exception:
                auto_report = None

        status_code = 200 if result["success"] else 500
        return jsonify({
            "success": result["success"],
            "message": "자동 수집+학습 작업이 완료되었습니다." if result["success"] else "자동 수집+학습 작업이 실패했습니다.",
            "data": {
                "preset_key": preset_key,
                "label": preset["label"],
                "dataset_job_id": dataset_job["id"],
                "training_job_id": train_job["id"],
                "dataset_output": str(output),
                "dataset_rows": len(rows),
                "dataset_failures": failures[:20],
                "report": auto_report,
                **result,
            }
        }), status_code
    except Exception as e:
        if "dataset_job" in locals():
            failed_dataset_job = update_job(
                dataset_job["id"],
                {
                    "status": "failed",
                    "finished_at": datetime.utcnow().isoformat() + "Z",
                    "error": str(e),
                },
            )
            if failed_dataset_job:
                sync_dataset_job_to_supabase(auth_header, failed_dataset_job)
        if "train_job" in locals():
            failed_train_job = update_job(
                train_job["id"],
                {
                    "status": "failed",
                    "finished_at": datetime.utcnow().isoformat() + "Z",
                    "error": str(e),
                },
            )
            if failed_train_job:
                sync_training_job_to_supabase(auth_header, failed_train_job)
        return jsonify({
            "success": False,
            "message": f"자동 수집+학습 실행 실패: {str(e)}"
        }), 500


def _read_json_file(path: Path) -> dict | None:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _read_csv_rows(path: Path, limit: int = 20) -> list[dict]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8", newline="") as file:
        return list(csv.DictReader(file))[:limit]


def _count_csv_rows(path: Path) -> int:
    if not path.exists():
        return 0
    with path.open("r", encoding="utf-8", newline="") as file:
        reader = csv.reader(file)
        next(reader, None)
        return sum(1 for _ in reader)


def _read_model_artifact(path: Path) -> dict:
    return {
        "path": str(path),
        "data": _read_json_file(path),
        "updated": path.exists(),
    }


def _pick_existing_path(paths: list[Path]) -> Path:
    for path in paths:
        if path.exists():
            return path
    return paths[0]


def _extract_version_number(path: Path) -> int:
    match = re.search(r"_v(\d+)\.ya?ml$", path.name)
    return int(match.group(1)) if match else 0


def _build_readiness_payload(auth_header: str) -> dict:
    records = query_supabase(auth_header, "user_api_keys", "GET")
    key_status = {
        "TOSS": False,
        "BINANCE": False,
        "COINONE": False,
        "KIS": False,
    }
    toss_record_count = 0
    toss_account_seq_ready = False
    toss_broker_env = None

    for record in records:
        exchange = str(record.get("exchange") or "").upper()
        if exchange in key_status and record.get("encrypted_access_key") and record.get("encrypted_secret_key"):
            key_status[exchange] = True

        if exchange == "TOSS":
            toss_record_count += 1
            if record.get("toss_account_seq"):
                toss_account_seq_ready = True
            if not toss_broker_env and record.get("broker_env"):
                toss_broker_env = record.get("broker_env")

    stock_raw_path = PROJECT_ROOT / "ml" / "data" / "raw" / "stock_candles.csv"
    crypto_raw_path = PROJECT_ROOT / "ml" / "data" / "raw" / "crypto_candles.csv"
    macro_path = PROJECT_ROOT / "ml" / "data" / "raw" / "macro_indices.csv"
    news_path = PROJECT_ROOT / "ml" / "data" / "raw" / "news_features.csv"
    crypto_feature_path = PROJECT_ROOT / "ml" / "data" / "raw" / "crypto_market_features.csv"
    stock_event_path = PROJECT_ROOT / "ml" / "data" / "raw" / "stock_event_features.csv"

    registry_groups = _load_registry_groups(auth_header)
    stock_serving = next((row.get("model_version") for row in registry_groups["stock"] if row.get("is_serving")), None)
    crypto_serving = next((row.get("model_version") for row in registry_groups["crypto"] if row.get("is_serving")), None)

    return {
        "keys": {
            "toss_ready": key_status["TOSS"],
            "toss_source": "supabase.user_api_keys -> encrypted_access_key/encrypted_secret_key -> crypto.decrypt",
            "toss_record_count": toss_record_count,
            "toss_account_seq_ready": toss_account_seq_ready,
            "toss_broker_env": toss_broker_env,
            "binance_ready": True,
            "binance_source": "public market candles (no personal key required)",
            "coinone_ready": key_status["COINONE"],
            "kis_ready": key_status["KIS"],
        },
        "datasets": {
            "stock_raw": {
                "path": str(stock_raw_path),
                "exists": stock_raw_path.exists(),
                "rows": _count_csv_rows(stock_raw_path),
            },
            "crypto_raw": {
                "path": str(crypto_raw_path),
                "exists": crypto_raw_path.exists(),
                "rows": _count_csv_rows(crypto_raw_path),
            },
            "macro_raw": {
                "path": str(macro_path),
                "exists": macro_path.exists(),
                "rows": _count_csv_rows(macro_path),
            },
        },
        "feature_sources": {
            "news_features": {
                "path": str(news_path),
                "exists": news_path.exists(),
                "rows": _count_csv_rows(news_path),
            },
            "crypto_market_features": {
                "path": str(crypto_feature_path),
                "exists": crypto_feature_path.exists(),
                "rows": _count_csv_rows(crypto_feature_path),
            },
            "stock_event_features": {
                "path": str(stock_event_path),
                "exists": stock_event_path.exists(),
                "rows": _count_csv_rows(stock_event_path),
            },
        },
        "artifacts": {
            "stock_v6_summary": (PROJECT_ROOT / "ml" / "data" / "processed" / "stock_v6_summary.json").exists(),
            "stock_v7_summary": (PROJECT_ROOT / "ml" / "data" / "processed" / "stock_v7_summary.json").exists(),
            "crypto_v6_summary": (PROJECT_ROOT / "ml" / "data" / "processed" / "crypto_v6_summary.json").exists(),
            "crypto_v7_summary": (PROJECT_ROOT / "ml" / "data" / "processed" / "crypto_v7_summary.json").exists(),
        },
        "registry": {
            "stock_serving": stock_serving,
            "crypto_serving": crypto_serving,
        },
    }


def _default_summary_path(filename: str) -> Path:
    return PROJECT_ROOT / "ml" / "data" / "processed" / filename


def _list_experiment_reports(limit: int = 20) -> list[dict]:
    reports_dir = PROJECT_ROOT / "ml" / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    report_paths = sorted(
        reports_dir.glob("*.md"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )[:limit]
    rows = []
    for path in report_paths:
        stat = path.stat()
        rows.append(
            {
                "name": path.name,
                "path": str(path),
                "updated_at": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
                "size_bytes": stat.st_size,
            }
        )
    return rows


def _run_experiment_report(
    auth_header: str,
    stock_summary: str | None = None,
    crypto_summary: str | None = None,
    output: str | None = None,
) -> dict:
    stock_summary = str(stock_summary or _default_summary_path("stock_v6_summary.json"))
    crypto_summary = str(crypto_summary or _default_summary_path("crypto_v6_summary.json"))
    reports_dir = PROJECT_ROOT / "ml" / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)

    if output is None:
        output_path = reports_dir / "latest_experiment_report.md"
    else:
        output_path = Path(output)
        if not output_path.is_absolute():
            output_path = PROJECT_ROOT / output_path

    timestamped_output_path = reports_dir / f"experiment_report_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.md"

    stock_selection = _resolve_active_model_selection("stock", auth_header)
    crypto_selection = _resolve_active_model_selection("crypto", auth_header)
    stock_serving = (stock_selection or {}).get("serving_version") or "-"
    crypto_serving = (crypto_selection or {}).get("serving_version") or "-"

    python_bin = str(PROJECT_ROOT / "ml" / ".venv" / "bin" / "python")
    if not Path(python_bin).exists():
        python_bin = sys.executable

    command = [
        python_bin,
        "ml/src/write_experiment_report.py",
        "--stock-summary",
        stock_summary,
        "--crypto-summary",
        crypto_summary,
        "--output",
        str(output_path),
        "--stock-serving",
        str(stock_serving),
        "--crypto-serving",
        str(crypto_serving),
    ]
    completed = subprocess.run(
        command,
        cwd=PROJECT_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        raise RuntimeError(completed.stderr or "실험 리포트 생성에 실패했습니다.")

    if output_path != timestamped_output_path:
        timestamped_command = command.copy()
        timestamped_command[timestamped_command.index(str(output_path))] = str(timestamped_output_path)
        timestamped_completed = subprocess.run(
            timestamped_command,
            cwd=PROJECT_ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
        if timestamped_completed.returncode != 0:
            raise RuntimeError(timestamped_completed.stderr or "타임스탬프 리포트 생성에 실패했습니다.")

    return {
        "output": str(output_path),
        "timestamped_output": str(timestamped_output_path),
        "stock_serving": stock_serving,
        "crypto_serving": crypto_serving,
    }


def _build_model_result(asset_key: str, version: int) -> dict:
    up_metrics_path = PROJECT_ROOT / "ml" / "models" / f"lgbm_{asset_key}_signal_v{version}.metrics.json"
    risk_metrics_path = PROJECT_ROOT / "ml" / "models" / f"lgbm_{asset_key}_risk_v{version}.metrics.json"
    predictions_path = PROJECT_ROOT / "ml" / "data" / "processed" / f"{asset_key}_predictions_lgbm_v{version}.csv"
    backtest_up_only_path = PROJECT_ROOT / "ml" / "data" / "processed" / f"{asset_key}_backtest_up_only_v{version}.json"
    backtest_composite_path = PROJECT_ROOT / "ml" / "data" / "processed" / f"{asset_key}_backtest_composite_v{version}.json"

    up_metrics = _read_json_file(up_metrics_path)
    risk_metrics = _read_json_file(risk_metrics_path)
    predictions = [enrich_symbol(row) for row in _read_csv_rows(predictions_path, limit=20)]

    return {
        "version": f"v{version}",
        "version_number": version,
        "asset_type": "STOCK" if asset_key == "stock" else "CRYPTO",
        "metrics": up_metrics,
        "risk_metrics": risk_metrics,
        "predictions": predictions,
        "metrics_path": str(up_metrics_path),
        "risk_metrics_path": str(risk_metrics_path),
        "predictions_path": str(predictions_path),
        "backtests": {
            "up_only": _read_model_artifact(backtest_up_only_path),
            "composite": _read_model_artifact(backtest_composite_path),
        },
        "updated": bool(up_metrics or risk_metrics or predictions),
    }


def _discover_model_versions(asset_key: str) -> list[dict]:
    config_dir = PROJECT_ROOT / "ml" / "configs"
    config_paths = sorted(
        config_dir.glob(f"lgbm_{asset_key}_v*.yaml"),
        key=_extract_version_number,
    )
    return [_build_model_result(asset_key, _extract_version_number(path)) for path in config_paths]


def _pick_default_model_result(version_results: list[dict]) -> dict | None:
    if not version_results:
        return None
    updated_results = [result for result in version_results if result.get("updated")]
    if updated_results:
        return max(updated_results, key=lambda item: item.get("version_number", 0))
    return max(version_results, key=lambda item: item.get("version_number", 0))


def _score_model_result(result: dict) -> tuple[float, float, float, int]:
    composite_data = result.get("backtests", {}).get("composite", {}).get("data", {}) or {}
    up_only_data = result.get("backtests", {}).get("up_only", {}).get("data", {}) or {}
    composite_excess = float(composite_data.get("excess_return_net") or composite_data.get("excess_return") or 0.0)
    up_only_excess = float(up_only_data.get("excess_return_net") or up_only_data.get("excess_return") or 0.0)
    up_roc_auc = float(
        result.get("metrics", {}).get("time_series_cv_average", {}).get("roc_auc")
        or result.get("metrics", {}).get("roc_auc")
        or 0.0
    )
    risk_roc_auc = float(
        result.get("risk_metrics", {}).get("time_series_cv_average", {}).get("roc_auc")
        or result.get("risk_metrics", {}).get("roc_auc")
        or 0.0
    )
    version_number = int(result.get("version_number") or 0)
    return (composite_excess, up_only_excess, up_roc_auc, risk_roc_auc, version_number)


def _pick_recommended_model_result(version_results: list[dict]) -> dict | None:
    updated_results = [result for result in version_results if result.get("updated")]
    if not updated_results:
        return _pick_default_model_result(version_results)
    return max(updated_results, key=_score_model_result)


def _build_registry_fallback(asset_key: str) -> list[dict]:
    version_results = _discover_model_versions(asset_key)
    latest_result = _pick_default_model_result(version_results)
    recommended_result = _pick_recommended_model_result(version_results)
    registry_map = {
        (str(row.get("asset_type", "")).upper(), str(row.get("model_version", ""))): row
        for row in list_model_registry("STOCK" if asset_key == "stock" else "CRYPTO")
    }
    rows = []
    for result in version_results:
        metrics = result.get("metrics") or {}
        asset_type = "STOCK" if asset_key == "stock" else "CRYPTO"
        model_version = metrics.get("model_version") or f"lgbm_{asset_key}_signal_{result['version']}"
        registry_row = registry_map.get((asset_type, model_version), {})
        rows.append(
            {
                "asset_type": asset_type,
                "model_version": model_version,
                "summary_path": "",
                "metrics_path": result.get("metrics_path"),
                "model_path": result.get("metrics_path", "").replace(".metrics.json", ".joblib"),
                "recommendation_reason": "file-based score comparison",
                "is_latest": bool(latest_result and latest_result.get("version") == result.get("version")),
                "is_recommended": bool(recommended_result and recommended_result.get("version") == result.get("version")),
                "is_serving": bool(registry_row.get("is_serving", False)),
                "approved_by": registry_row.get("approved_by"),
                "approved_at": registry_row.get("approved_at"),
                "updated": result.get("updated", False),
                "version": result.get("version"),
                "version_number": result.get("version_number"),
                "roc_auc": metrics.get("roc_auc"),
                "cv_roc_auc": (metrics.get("time_series_cv_average") or {}).get("roc_auc"),
                "cv_top10_precision": (metrics.get("time_series_cv_average") or {}).get("precision_at_top_10pct"),
            }
        )
    return rows


def _load_registry_groups(auth_header: str | None) -> dict[str, list[dict]]:
    registry_rows = []
    if auth_header:
        registry_rows = safe_query_supabase(
            auth_header,
            "ml_model_registry",
            "GET",
            params={"order": "asset_type.asc,updated_at.desc"},
        ) or []

    if registry_rows:
        for row in registry_rows:
            row["version"] = row.get("model_version", "").split("_")[-1] if row.get("model_version") else ""
        stock_rows = [row for row in registry_rows if row.get("asset_type") == "STOCK"]
        crypto_rows = [row for row in registry_rows if row.get("asset_type") == "CRYPTO"]
        return {"stock": stock_rows, "crypto": crypto_rows}

    return {
        "stock": _build_registry_fallback("stock"),
        "crypto": _build_registry_fallback("crypto"),
    }


def _resolve_active_model_selection(asset_key: str, auth_header: str | None) -> dict | None:
    registry_groups = _load_registry_groups(auth_header)
    version_results = _discover_model_versions(asset_key)
    if not version_results:
        return None

    latest_result = _pick_default_model_result(version_results)
    recommended_result = _pick_recommended_model_result(version_results)
    registry_rows = registry_groups.get(asset_key, [])
    registry_map = {
        str(row.get("model_version") or ""): row
        for row in registry_rows
    }
    serving_version = next((row.get("version") for row in registry_rows if row.get("is_serving")), None)
    latest_version = next(
        (row.get("version") for row in registry_rows if row.get("is_latest")),
        latest_result["version"] if latest_result else None,
    )
    recommended_version = next(
        (row.get("version") for row in registry_rows if row.get("is_recommended")),
        recommended_result["version"] if recommended_result else None,
    )

    decorated_versions = []
    for result in version_results:
        model_version = str((result.get("metrics") or {}).get("model_version") or "")
        registry_row = registry_map.get(model_version, {})
        decorated_versions.append(
            {
                **result,
                "is_serving": bool(registry_row.get("is_serving", False)),
                "is_latest": bool(registry_row.get("is_latest", latest_version == result["version"])),
                "is_recommended": bool(registry_row.get("is_recommended", recommended_version == result["version"])),
                "registry": registry_row,
            }
        )

    selected_version = serving_version or recommended_version or (recommended_result["version"] if recommended_result else None)
    active_result = next(
        (item for item in decorated_versions if item.get("version") == selected_version),
        decorated_versions[0] if decorated_versions else None,
    )
    if not active_result:
        return None

    return {
        "asset_key": asset_key,
        "active_result": active_result,
        "serving_version": serving_version,
        "latest_version": latest_version,
        "recommended_version": recommended_version,
        "versions": decorated_versions,
    }


@app.route("/api/ml/model-results", methods=["GET"])
def get_ml_model_results():
    """
    관리자 페이지에서 최신 모델 성능 지표와 예측 순위를 조회합니다.
    """
    auth_header = request.headers.get("Authorization")
    if not auth_header:
        return jsonify({"success": False, "message": "인증 헤더가 누락되었습니다."}), 401

    try:
        get_user_id_from_header(auth_header)
        results = {}
        for asset_key in ["stock", "crypto"]:
            selection = _resolve_active_model_selection(asset_key, auth_header)
            if selection is None:
                continue

            results[asset_key] = {
                **selection["active_result"],
                "selected_version": selection["active_result"]["version"],
                "latest_version": selection["latest_version"],
                "recommended_version": selection["recommended_version"],
                "serving_version": selection["serving_version"],
                "versions": selection["versions"],
            }

        return jsonify({"success": True, "data": results})
    except Exception as e:
        return jsonify({
            "success": False,
            "message": f"모델 결과 조회 실패: {str(e)}"
        }), 500


@app.route("/api/ml/registry", methods=["GET"])
def get_ml_registry():
    auth_header = request.headers.get("Authorization")
    if not auth_header:
        return jsonify({"success": False, "message": "인증 헤더가 누락되었습니다."}), 401

    try:
        get_user_id_from_header(auth_header)
        registry_groups = _load_registry_groups(auth_header)
        stock_rows = registry_groups["stock"]
        crypto_rows = registry_groups["crypto"]

        return jsonify(
            {
                "success": True,
                "data": {
                    "stock": stock_rows,
                    "crypto": crypto_rows,
                },
            }
        )
    except Exception as e:
        return jsonify({
            "success": False,
            "message": f"모델 레지스트리 조회 실패: {str(e)}"
        }), 500


@app.route("/api/ml/registry/activate", methods=["POST"])
def activate_ml_registry_version():
    auth_header = request.headers.get("Authorization")
    if not auth_header:
        return jsonify({"success": False, "message": "인증 헤더가 누락되었습니다."}), 401

    try:
        user_id, _ = get_user_id_from_header(auth_header)
        data = request.json or {}
        asset_type = str(data.get("asset_type") or "").upper()
        model_version = str(data.get("model_version") or "").strip()

        if asset_type not in ("STOCK", "CRYPTO"):
            return jsonify({"success": False, "message": "asset_type은 STOCK 또는 CRYPTO여야 합니다."}), 400
        if not model_version:
            return jsonify({"success": False, "message": "model_version이 필요합니다."}), 400

        registry_rows = safe_query_supabase(
            auth_header,
            "ml_model_registry",
            "GET",
            params={
                "asset_type": f"eq.{asset_type}",
                "model_version": f"eq.{model_version}",
            },
        )
        file_target = set_serving_model(asset_type, model_version, approved_by=user_id)
        if not registry_rows:
            return jsonify({
                "success": True,
                "message": f"{asset_type} 서비스 반영 버전이 {model_version}으로 변경되었습니다. (file registry)",
                "data": {
                    "asset_type": asset_type,
                    "model_version": model_version,
                    "registry": file_target,
                }
            })

        safe_query_supabase(
            auth_header,
            f"ml_model_registry?asset_type=eq.{asset_type}",
            "PATCH",
            json_data={"is_serving": False},
        )
        safe_query_supabase(
            auth_header,
            f"ml_model_registry?asset_type=eq.{asset_type}&model_version=eq.{model_version}",
            "PATCH",
            json_data={
                "is_serving": True,
                "approved_by": user_id,
                "approved_at": datetime.utcnow().isoformat() + "Z",
            },
        )

        return jsonify({
            "success": True,
            "message": f"{asset_type} 서비스 반영 버전이 {model_version}으로 변경되었습니다.",
            "data": {
                "asset_type": asset_type,
                "model_version": model_version,
            }
        })
    except Exception as e:
        return jsonify({
            "success": False,
            "message": f"모델 서비스 반영 실패: {str(e)}"
        }), 500


@app.route("/api/ml/readiness", methods=["GET"])
def get_ml_readiness():
    auth_header = request.headers.get("Authorization")
    if not auth_header:
        return jsonify({"success": False, "message": "인증 헤더가 누락되었습니다."}), 401

    try:
        get_user_id_from_header(auth_header)
        return jsonify({
            "success": True,
            "data": _build_readiness_payload(auth_header),
        })
    except Exception as e:
        return jsonify({
            "success": False,
            "message": f"ML 운영 준비 상태 조회 실패: {str(e)}"
        }), 500


@app.route("/api/ml/active-model", methods=["GET"])
def get_ml_active_model():
    auth_header = request.headers.get("Authorization")
    if not auth_header:
        return jsonify({"success": False, "message": "인증 헤더가 누락되었습니다."}), 401

    try:
        get_user_id_from_header(auth_header)
        asset_type = str(request.args.get("asset_type") or "").upper()
        if asset_type not in ("STOCK", "CRYPTO"):
            return jsonify({"success": False, "message": "asset_type은 STOCK 또는 CRYPTO여야 합니다."}), 400

        asset_key = "stock" if asset_type == "STOCK" else "crypto"
        selection = _resolve_active_model_selection(asset_key, auth_header)
        if selection is None:
            return jsonify({"success": False, "message": "활성 모델 정보를 찾을 수 없습니다."}), 404

        active_result = selection["active_result"]
        return jsonify({
            "success": True,
            "data": {
                "asset_type": asset_type,
                "selected_version": active_result.get("version"),
                "model_version": (active_result.get("metrics") or {}).get("model_version"),
                "serving_version": selection["serving_version"],
                "recommended_version": selection["recommended_version"],
                "latest_version": selection["latest_version"],
                "metrics_path": active_result.get("metrics_path"),
                "predictions_path": active_result.get("predictions_path"),
                "backtest_composite": active_result.get("backtests", {}).get("composite", {}).get("data"),
            }
        })
    except Exception as e:
        return jsonify({
            "success": False,
            "message": f"활성 모델 조회 실패: {str(e)}"
        }), 500


@app.route("/api/ml/report", methods=["POST"])
def write_ml_report():
    auth_header = request.headers.get("Authorization")
    if not auth_header:
        return jsonify({"success": False, "message": "인증 헤더가 누락되었습니다."}), 401

    try:
        get_user_id_from_header(auth_header)
        data = request.json or {}
        report_result = _run_experiment_report(
            auth_header=auth_header,
            stock_summary=data.get("stock_summary"),
            crypto_summary=data.get("crypto_summary"),
            output=data.get("output"),
        )

        return jsonify({
            "success": True,
            "message": "실험 리포트가 생성되었습니다.",
            "data": report_result,
        })
    except Exception as e:
        return jsonify({
            "success": False,
            "message": f"실험 리포트 생성 실패: {str(e)}"
        }), 500


@app.route("/api/ml/reports", methods=["GET"])
def list_ml_reports():
    auth_header = request.headers.get("Authorization")
    if not auth_header:
        return jsonify({"success": False, "message": "인증 헤더가 누락되었습니다."}), 401

    try:
        get_user_id_from_header(auth_header)
        limit = int(request.args.get("limit", 20))
        return jsonify({
            "success": True,
            "data": {
                "reports": _list_experiment_reports(limit=max(1, min(limit, 100))),
            },
        })
    except Exception as e:
        return jsonify({
            "success": False,
            "message": f"실험 리포트 목록 조회 실패: {str(e)}"
        }), 500


@app.route("/api/news", methods=["GET"])
def get_news_feed():
    market = request.args.get("market", "ALL")
    query = request.args.get("query", "")
    limit = request.args.get("limit", 10)
    offset = request.args.get("offset", 0)
    try:
        items = news_repository.list_articles(
            market=market,
            query=query,
            limit=int(limit),
            offset=int(offset),
        )

        total_count = news_repository.count_articles(
            market=market,
            query=query,
        )

        return jsonify({
            "success": True,
            "data": {
                "items": items,
                "totalCount": total_count,
                "limit": int(limit),
                "offset": int(offset),
                "market": market.upper(),
                "query": query,
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


@app.route("/api/news/summaries/ensure", methods=["POST"])
def ensure_news_summaries():
    try:
        data = request.json or {}
        article_ids = data.get("article_ids") or []
        article_ids = [str(article_id).strip() for article_id in article_ids if str(article_id).strip()]

        if not article_ids:
            return jsonify({
                "success": True,
                "data": {
                    "items": [],
                    "generatedCount": 0,
                }
            })

        articles = news_repository.list_articles_by_ids(article_ids)
        article_by_id = {article["id"]: article for article in articles if article.get("id")}
        updates = []
        items = []

        for article_id in article_ids:
            article = article_by_id.get(article_id)
            if not article:
                continue

            existing_summary = (article.get("ai_summary") or "").strip()
            if existing_summary:
                items.append({
                    "id": article_id,
                    "ai_summary": existing_summary,
                    "ai_summary_model": article.get("ai_summary_model"),
                    "ai_summary_generated_at": article.get("ai_summary_generated_at"),
                    "ai_summary_prompt_version": article.get("ai_summary_prompt_version"),
                })
                continue

            summary_payload = news_summary_service.summarize(article)
            update_row = {
                "id": article_id,
                "ai_summary": summary_payload["ai_summary"],
                "ai_summary_model": summary_payload["ai_summary_model"],
                "ai_summary_generated_at": datetime.utcnow().isoformat() + "Z",
                "ai_summary_prompt_version": summary_payload["ai_summary_prompt_version"],
            }
            updates.append(update_row)
            items.append(update_row)

        if updates:
            news_repository.upsert_article_summaries(updates)

        return jsonify({
            "success": True,
            "data": {
                "items": items,
                "generatedCount": len(updates),
            }
        })
    except Exception as e:
        return jsonify({
            "success": False,
            "message": f"Failed to ensure news summaries: {str(e)}"
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
