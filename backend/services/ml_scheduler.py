import os
import time
import threading
import requests
import yaml
from datetime import datetime, timedelta
from pathlib import Path

from backend.services.lock_service import distributed_lock
from backend.services.ml_automation_service import resolve_automation_preset
from backend.services.ml_job_service import create_job, list_jobs, update_job, run_ml_pipeline, run_ml_tuning
from backend.services.ml_model_service import (
    build_promotion_guard_report,
    build_serving_audit_report,
    build_training_audit_bundle,
)
from backend.services.supabase_client import (
    sync_dataset_job_to_supabase,
    sync_training_job_to_supabase,
    sync_model_registry_to_supabase,
    safe_query_supabase
)
from backend.utils.crypto_helper import CryptoHelper
from backend.scripts.export_training_candles import (
    DEFAULT_UNIVERSE_PATH,
    fetch_binance_klines,
    fetch_macro_indices,
    fetch_toss_candles,
    load_preset_symbols,
    write_rows
)

PROJECT_ROOT = Path(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
ENCRYPTION_KEY = os.getenv("ENCRYPTION_KEY", "default-dev-encryption-key-32bytes!")
crypto = CryptoHelper(ENCRYPTION_KEY)

# 모듈 수준의 전역 상태 변수
_news_ingest_started = False
_ml_automation_started = False

def resolve_model_version_from_config(config_path: str) -> str | None:
    """학습 설정 파일에서 모델 버전을 읽어 자동 감사 대상에 사용합니다."""
    try:
        config_file = PROJECT_ROOT / config_path if not str(config_path).startswith("/") else Path(config_path)
        config = yaml.safe_load(config_file.read_text(encoding="utf-8"))
        return str(((config or {}).get("model") or {}).get("version") or "").strip() or None
    except Exception:
        return None

def record_model_audit_jobs(auth_header: str, asset_key: str, model_version: str | None) -> None:
    """학습 직후 후보 모델 승격 검증과 전체 serving 감사를 작업 이력에 남깁니다."""
    if not model_version:
        return

    promotion_job = create_job(
        "promotion_audit",
        {
            "asset_type": "STOCK" if asset_key == "stock" else "CRYPTO",
            "model_version": model_version,
        },
    )
    try:
        guard_report = build_promotion_guard_report(asset_key, auth_header, model_version)
        update_job(
            promotion_job["id"],
            {
                "status": "success" if guard_report else "failed",
                "finished_at": datetime.utcnow().isoformat() + "Z",
                "audit_kind": "promotion_guard",
                "guard_report": guard_report,
            },
        )
    except Exception as error:
        update_job(
            promotion_job["id"],
            {
                "status": "failed",
                "finished_at": datetime.utcnow().isoformat() + "Z",
                "error": str(error),
                "audit_kind": "promotion_guard",
            },
        )

    serving_job = create_job(
        "serving_audit",
        {
            "asset_type": "ALL",
            "model_version": model_version,
        },
    )
    try:
        audit_report = build_serving_audit_report(auth_header)
        update_job(
            serving_job["id"],
            {
                "status": "success",
                "finished_at": datetime.utcnow().isoformat() + "Z",
                "audit_kind": "serving_audit",
                "serving_audit_report": audit_report,
            },
        )
    except Exception as error:
        update_job(
            serving_job["id"],
            {
                "status": "failed",
                "finished_at": datetime.utcnow().isoformat() + "Z",
                "error": str(error),
                "audit_kind": "serving_audit",
            },
        )

def attach_training_audit_to_job(job_id: str, auth_header: str, asset_type: str, config_path: str) -> None:
    """학습 작업 이력에도 감사 결과를 함께 기록합니다."""
    try:
        training_audit = build_training_audit_bundle(
            auth_header=auth_header,
            asset_type=asset_type,
            config_path=config_path,
        )
        if training_audit:
            update_job(
                job_id,
                {
                    "training_audit": training_audit,
                },
            )
    except Exception:
        pass

def start_news_ingest_scheduler(news_ingest_service, news_ingest_enabled: bool, news_ingest_interval_seconds: int) -> None:
    """뉴스 수집 스케줄러를 백그라운드 스레드로 구동합니다."""
    global _news_ingest_started
    if _news_ingest_started or not news_ingest_enabled:
        return
    _news_ingest_started = True

    def _loop() -> None:
        while True:
            try:
                # 10분(600초) 동안 유효한 뉴스 수집 분산 락 획득 시도
                with distributed_lock("news_ingest", 600) as locked:
                    if locked:
                        news_ingest_service.run_once()
            except Exception:
                pass
            now_kr = datetime.utcnow() + timedelta(hours=9)
            is_weekday = now_kr.weekday() < 5
            is_market_hours = is_weekday and (
                (now_kr.hour > 9 or (now_kr.hour == 9 and now_kr.minute >= 0))
                and (now_kr.hour < 15 or (now_kr.hour == 15 and now_kr.minute <= 30))
            )
            sleep_seconds = news_ingest_interval_seconds if is_market_hours else max(news_ingest_interval_seconds * 3, 1800)
            time.sleep(sleep_seconds)

    thread = threading.Thread(target=_loop, daemon=True)
    thread.start()

def start_ml_automation_scheduler(ml_automation_enabled: bool, supabase_service_role_key: str) -> None:
    """ML 자동 수집 및 재학습 스케줄러를 백그라운드 스레드로 구동합니다."""
    global _ml_automation_started
    
    # ML 전담 개발자(khs) 식별자 검증 안전장치 추가
    developer_name = os.getenv("DEVELOPER_NAME")
    if developer_name != "khs":
        return

    if _ml_automation_started or not ml_automation_enabled:
        return
    _ml_automation_started = True

    def _loop() -> None:
        last_stock_date = None
        last_crypto_hour = None
        crypto_run_count = 0

        time.sleep(30)

        while True:
            try:
                now_kr = datetime.utcnow() + timedelta(hours=9)
                today_str = now_kr.strftime("%Y-%m-%d")
                current_slot_hour = (now_kr.hour // 4) * 4
                crypto_slot_str = f"{today_str} {current_slot_hour:02d}:00:00"

                # 1. 코인 자동화 (4시간 주기)
                if last_crypto_hour != crypto_slot_str:
                    with distributed_lock("crypto_automation", 7200) as locked:
                        if locked:
                            last_crypto_hour = crypto_slot_str
                            try:
                                # v8: 30분 캔들 + 잔차 수익률 라벨 + Ridge 앙상블 자동화
                                preset = resolve_automation_preset("crypto-v8-full")
                                dataset_config = preset["dataset"]
                                training_config = preset["training"]
                                
                                # 48회 구동될 때마다(약 8일에 한 번) Auto-HPO 튜닝 수행
                                if crypto_run_count > 0 and crypto_run_count % 48 == 0:
                                    try:
                                        run_ml_tuning(
                                            config_path=training_config["config"],
                                            trials=15,
                                            update_config=True
                                        )
                                    except Exception:
                                        pass
                                
                                crypto_run_count += 1
                                
                                preset_symbols = load_preset_symbols(dataset_config["preset"], DEFAULT_UNIVERSE_PATH)
                                symbols = list(dict.fromkeys([*(dataset_config.get("symbols") or []), *preset_symbols]))
                                
                                dataset_job = create_job(
                                    "dataset_export",
                                    {
                                        "label": preset["label"] + " (Auto)",
                                        "asset_type": dataset_config["asset_type"],
                                        "exchange": dataset_config["exchange"],
                                        "symbols": symbols,
                                        "preset_name": dataset_config.get("preset"),
                                        "interval": dataset_config["interval"],
                                        "count": dataset_config["count"],
                                    },
                                )
                                
                                rows, failures = fetch_binance_klines(
                                    symbols,
                                    dataset_config["interval"],
                                    int(dataset_config["count"]),
                                    sleep_seconds=float(dataset_config.get("sleep_seconds", 0.2)),
                                    retry=int(dataset_config.get("retry", 2)),
                                    retry_wait_seconds=float(dataset_config.get("retry_wait_seconds", 10.0)),
                                )
                                # 수집 간격에 따라 별도 파일로 분리 저장 (1h/30m 혼재 방지)
                                raw_output_name = dataset_config.get("raw_output", "crypto_candles.csv")
                                output = PROJECT_ROOT / "ml" / "data" / "raw" / raw_output_name
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
                                        "symbols": symbols,
                                    },
                                )
                                
                                train_job = create_job(
                                    "training_run",
                                    {
                                        "label": preset["label"] + " (Auto)",
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
                                        "stdout": result["stdout"][-8000:],
                                        "stderr": result["stderr"][-8000:],
                                    },
                                )
                                
                                if supabase_service_role_key:
                                    auth_header = f"Bearer {supabase_service_role_key}"
                                    attach_training_audit_to_job(
                                        train_job["id"],
                                        auth_header,
                                        dataset_config["asset_type"],
                                        training_config["config"],
                                    )
                                    latest_ds_job = next((j for j in list_jobs(limit=100) if j.get("id") == dataset_job["id"]), None)
                                    if latest_ds_job:
                                        sync_dataset_job_to_supabase(auth_header, latest_ds_job)
                                    latest_tr_job = next((j for j in list_jobs(limit=100) if j.get("id") == train_job["id"]), None)
                                    if latest_tr_job:
                                        sync_training_job_to_supabase(auth_header, latest_tr_job)
                                    sync_model_registry_to_supabase(auth_header, training_config.get("summary_output"))
                                    record_model_audit_jobs(
                                        auth_header,
                                        "crypto",
                                        resolve_model_version_from_config(training_config["config"]),
                                    )
                                
                            except Exception:
                                pass
                        else:
                            last_crypto_hour = crypto_slot_str

                # 2. 주식 자동화 (평일 16:30 ~ 17:00 사이, 하루 1회)
                is_weekday = now_kr.weekday() < 5
                if is_weekday and now_kr.hour == 16 and 30 <= now_kr.minute <= 59:
                    if last_stock_date != today_str:
                        with distributed_lock("stock_automation", 7200) as locked:
                            if locked:
                                last_stock_date = today_str
                                if supabase_service_role_key:
                                    try:
                                        auth_header = f"Bearer {supabase_service_role_key}"
                                        toss_keys = safe_query_supabase(auth_header, "user_api_keys", "GET", params={"broker_name": "eq.TOSS"})
                                        if toss_keys:
                                            record = toss_keys[0]
                                            client_id = crypto.decrypt(record.get("encrypted_access_key"))
                                            client_secret = crypto.decrypt(record.get("encrypted_secret_key"))
                                            
                                            token_res = requests.post(
                                                "https://open-api.tossinvest.com/oauth2/token",
                                                headers={"Content-Type": "application/x-www-form-urlencoded"},
                                                data={
                                                    "grant_type": "client_credentials",
                                                    "client_id": client_id,
                                                    "client_secret": client_secret,
                                                },
                                                timeout=10,
                                            )
                                            token_json = token_res.json()
                                            access_token = token_json.get("access_token")
                                            
                                            if access_token:
                                                # v8: 잔차 수익률 라벨 + Ridge 앙상블 주식 자동화
                                                preset = resolve_automation_preset("stock-v8-full")
                                                dataset_config = preset["dataset"]
                                                training_config = preset["training"]
                                                
                                                # 금요일 16:30 학습 기동 시 Auto-HPO 튜닝 선행 적용
                                                if now_kr.weekday() == 4:
                                                    try:
                                                        run_ml_tuning(
                                                            config_path=training_config["config"],
                                                            trials=15,
                                                            update_config=True
                                                        )
                                                    except Exception:
                                                        pass
                                                
                                                preset_symbols = load_preset_symbols(dataset_config["preset"], DEFAULT_UNIVERSE_PATH)
                                                symbols = list(dict.fromkeys([*(dataset_config.get("symbols") or []), *preset_symbols]))
                                                
                                                dataset_job = create_job(
                                                    "dataset_export",
                                                    {
                                                        "label": preset["label"] + " (Auto)",
                                                        "asset_type": dataset_config["asset_type"],
                                                        "exchange": dataset_config["exchange"],
                                                        "symbols": symbols,
                                                        "preset_name": dataset_config.get("preset"),
                                                        "interval": dataset_config["interval"],
                                                        "count": dataset_config["count"],
                                                    },
                                                )
                                                
                                                macro_rows = fetch_macro_indices(int(dataset_config["count"]))
                                                macro_output = PROJECT_ROOT / "ml" / "data" / "raw" / "macro_indices.csv"
                                                write_rows(macro_output, macro_rows, append=bool(dataset_config.get("append", True)))
                                                
                                                rows, failures = fetch_toss_candles(
                                                    symbols,
                                                    access_token,
                                                    dataset_config["interval"],
                                                    int(dataset_config["count"]),
                                                    sleep_seconds=float(dataset_config.get("sleep_seconds", 2.0)),
                                                    retry=int(dataset_config.get("retry", 3)),
                                                    retry_wait_seconds=float(dataset_config.get("retry_wait_seconds", 60.0)),
                                                )
                                                output = PROJECT_ROOT / "ml" / "data" / "raw" / "stock_candles.csv"
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
                                                        "symbols": symbols,
                                                    },
                                                )
                                                
                                                train_job = create_job(
                                                    "training_run",
                                                    {
                                                        "label": preset["label"] + " (Auto)",
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
                                                        "stdout": result["stdout"][-8000:],
                                                        "stderr": result["stderr"][-8000:],
                                                    },
                                                )
                                                
                                                latest_ds_job = next((j for j in list_jobs(limit=100) if j.get("id") == dataset_job["id"]), None)
                                                if latest_ds_job:
                                                    sync_dataset_job_to_supabase(auth_header, latest_ds_job)
                                                attach_training_audit_to_job(
                                                    train_job["id"],
                                                    auth_header,
                                                    dataset_config["asset_type"],
                                                    training_config["config"],
                                                )
                                                latest_tr_job = next((j for j in list_jobs(limit=100) if j.get("id") == train_job["id"]), None)
                                                if latest_tr_job:
                                                    sync_training_job_to_supabase(auth_header, latest_tr_job)
                                                sync_model_registry_to_supabase(auth_header, training_config.get("summary_output"))
                                                record_model_audit_jobs(
                                                    auth_header,
                                                    "stock",
                                                    resolve_model_version_from_config(training_config["config"]),
                                                )
                                                
                                    except Exception:
                                        pass
                            else:
                                last_stock_date = today_str

            except Exception:
                pass
            
            time.sleep(60)

    thread = threading.Thread(target=_loop, daemon=True)
    thread.start()
