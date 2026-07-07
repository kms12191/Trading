import json
import logging
import os
import time
import threading
import requests
import yaml
import sys
import subprocess
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
logger = logging.getLogger(__name__)

def get_stock_shadow_preset_keys() -> list[str]:
    """주식 자동화 시 실행할 프리셋 키 목록을 반환합니다.
    
    serving 모델과 동일한 config를 사용하는 v11이 우선이며,
    국내/해외 분리 shadow 모델(kr-v1, us-v1)은 보조 학습으로 병렬 실행됩니다.
    """
    return ["kr-stock-v1-full", "us-stock-v1-full", "stock-v11-full"]

# 모듈 수준의 전역 상태 변수
_news_ingest_started = False
_dart_ingest_started = False
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
        if not news_ingest_enabled:
            logger.info("[NewsIngestScheduler] disabled")
        return
    _news_ingest_started = True
    logger.info("[NewsIngestScheduler] started interval=%ss", news_ingest_interval_seconds)

    def _loop() -> None:
        while True:
            try:
                # 10분(600초) 동안 유효한 뉴스 수집 분산 락 획득 시도
                with distributed_lock("news_ingest", 600) as locked:
                    if locked:
                        result = news_ingest_service.run_once()
                        logger.info(
                            "[NewsIngestScheduler] run complete fetched=%s inserted=%s skipped=%s",
                            result.get("fetched"),
                            result.get("inserted"),
                            result.get("queries_skipped"),
                        )
                    else:
                        logger.info("[NewsIngestScheduler] lock not acquired")
            except Exception as error:
                logger.exception("[NewsIngestScheduler] run failed: %s", error)
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

def start_dart_ingest_scheduler(dart_ingest_service, dart_ingest_enabled: bool, dart_ingest_interval_seconds: int) -> None:
    """OpenDART 전체 공시 목록을 주기적으로 수집합니다."""
    global _dart_ingest_started
    if _dart_ingest_started or not dart_ingest_enabled:
        if not dart_ingest_enabled:
            logger.info("[DartIngestScheduler] disabled")
        return
    _dart_ingest_started = True
    logger.info("[DartIngestScheduler] started interval=%ss", dart_ingest_interval_seconds)

    def _loop() -> None:
        while True:
            try:
                with distributed_lock("dart_ingest", max(dart_ingest_interval_seconds, 900)) as locked:
                    if locked:
                        result = dart_ingest_service.run_incremental()
                        logger.info(
                            "[DartIngestScheduler] run complete fetched=%s saved=%s requests=%s",
                            result.get("fetched"),
                            result.get("saved"),
                            result.get("request_count"),
                        )
                    else:
                        logger.info("[DartIngestScheduler] lock not acquired")
            except Exception as error:
                logger.exception("[DartIngestScheduler] run failed: %s", error)
            time.sleep(dart_ingest_interval_seconds)

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

    STOCK_AUTOMATION_STATE_PATH = PROJECT_ROOT / "ml" / "data" / "ops" / "stock_automation_state.json"

    def _load_last_stock_date() -> str | None:
        """이전 서버 실행에서 저장된 주식 자동화 마지막 실행 날짜를 파일에서 복원합니다."""
        try:
            if STOCK_AUTOMATION_STATE_PATH.exists():
                state = json.loads(STOCK_AUTOMATION_STATE_PATH.read_text(encoding="utf-8"))
                return state.get("last_stock_date")
        except Exception:
            pass
        return None

    def _save_last_stock_date(date_str: str) -> None:
        """주식 자동화 실행 날짜를 파일에 영속화하여 서버 재시작 후에도 중복 실행을 방지합니다."""
        try:
            STOCK_AUTOMATION_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
            STOCK_AUTOMATION_STATE_PATH.write_text(
                json.dumps({"last_stock_date": date_str, "updated_at": datetime.utcnow().isoformat() + "Z"}, ensure_ascii=False),
                encoding="utf-8",
            )
        except Exception:
            pass

    def _loop() -> None:
        # 서버 재시작 시 파일에서 마지막 실행 날짜 복원 (메모리 변수로만 관리하면 재시작 시 당일 중복 실행 발생 가능)
        last_stock_date = _load_last_stock_date()
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
                                # v9: 30분 캔들 + 잔차 수익률 라벨 — 현재 serving 코인 모델과 동일 config
                                preset = resolve_automation_preset("crypto-v9-full")
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

                # 2. 주식 자동화 (평일 16:30 ~ 18:30 사이, 하루 1회)
                # 시간 창을 18:30까지 확장: 서버가 해당 창 내 어느 시점에 켜져도 당일 자동화가 반드시 실행됨
                is_weekday = now_kr.weekday() < 5
                in_stock_window = (
                    (now_kr.hour == 16 and now_kr.minute >= 30)
                    or (now_kr.hour == 17)
                    or (now_kr.hour == 18 and now_kr.minute <= 30)
                )
                if is_weekday and in_stock_window:
                    if last_stock_date != today_str:
                        with distributed_lock("stock_automation", 7200) as locked:
                            if locked:
                                last_stock_date = today_str
                                _save_last_stock_date(today_str)  # 파일에 영속화
                                if supabase_service_role_key:
                                    try:
                                        auth_header = f"Bearer {supabase_service_role_key}"
                                        toss_keys = safe_query_supabase(
                                            auth_header,
                                            "user_api_keys",
                                            "GET",
                                            params={
                                                "exchange": "eq.TOSS",
                                                "broker_env": "eq.REAL",
                                                "limit": "1",
                                            },
                                        )
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
                                                for preset_key in get_stock_shadow_preset_keys():
                                                    dataset_job = None
                                                    train_job = None
                                                    try:
                                                        preset = resolve_automation_preset(preset_key)
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
                                                        
                                                        if dataset_config.get("include_macro"):
                                                            macro_rows = fetch_macro_indices(int(dataset_config["count"]))
                                                            macro_output = PROJECT_ROOT / "ml" / "data" / "raw" / "macro_indices.csv"
                                                            if macro_rows:
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
                                                        raw_output_name = dataset_config.get("raw_output", "stock_candles.csv")
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
                                                        
                                                        for command in training_config.get("pre_build_commands") or []:
                                                            resolved_command = [
                                                                sys.executable if token == "python" else token
                                                                for token in command
                                                            ]
                                                            completed = subprocess.run(
                                                                resolved_command,
                                                                cwd=str(PROJECT_ROOT),
                                                                check=False,
                                                                capture_output=True,
                                                                text=True,
                                                            )
                                                            if completed.returncode != 0:
                                                                raise RuntimeError(
                                                                    "사전 피처 생성 명령이 실패했습니다: "
                                                                    + " ".join(command)
                                                                    + "\n"
                                                                    + completed.stderr[-4000:]
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
                                                    except Exception as e:
                                                        logger.exception(f"[StockAutomation] Preset={preset_key} run failed: %s", e)
                                                        if dataset_job:
                                                            try:
                                                                update_job(
                                                                    dataset_job["id"],
                                                                    {
                                                                        "status": "failed",
                                                                        "finished_at": datetime.utcnow().isoformat() + "Z",
                                                                        "error": str(e),
                                                                    }
                                                                )
                                                                latest_ds_job = next((j for j in list_jobs(limit=100) if j.get("id") == dataset_job["id"]), None)
                                                                if latest_ds_job:
                                                                    sync_dataset_job_to_supabase(auth_header, latest_ds_job)
                                                            except Exception:
                                                                pass
                                                        if train_job:
                                                            try:
                                                                update_job(
                                                                    train_job["id"],
                                                                    {
                                                                        "status": "failed",
                                                                        "finished_at": datetime.utcnow().isoformat() + "Z",
                                                                        "error": str(e),
                                                                    }
                                                                )
                                                                latest_tr_job = next((j for j in list_jobs(limit=100) if j.get("id") == train_job["id"]), None)
                                                                if latest_tr_job:
                                                                    sync_training_job_to_supabase(auth_header, latest_tr_job)
                                                            except Exception:
                                                                pass
                                                
                                    except Exception:
                                        pass
                            else:
                                # 락 획득 실패 = 다른 프로세스가 이미 실행 중이므로 오늘 날짜 저장
                                last_stock_date = today_str
                                _save_last_stock_date(today_str)

            except Exception:
                pass
            
            time.sleep(60)

    thread = threading.Thread(target=_loop, daemon=True)
    thread.start()
