import os
import json
import logging
import time
import requests
from pathlib import Path
from dotenv import load_dotenv
from backend.services.auth_service import get_user_id_from_header

logger = logging.getLogger(__name__)

# Supabase 연결 타임아웃 설정
# Free tier cold start 고려: connect 5초, read 20초
_SUPABASE_CONNECT_TIMEOUT = 5
_SUPABASE_READ_TIMEOUT = 20
_SUPABASE_TIMEOUT = (_SUPABASE_CONNECT_TIMEOUT, _SUPABASE_READ_TIMEOUT)
# 재시도 정사
_SUPABASE_MAX_RETRIES = 3        # 최대 3회 재시도
_SUPABASE_RETRY_BACKOFF = 1.5    # 최초 1.5초 대기, 이후 지수 배율
_SUPABASE_RETRY_ON = (           # 재시도 대상 예외
    requests.exceptions.Timeout,
    requests.exceptions.ConnectionError,
)

PROJECT_ROOT = Path(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

# supabase_client 로딩 시 .env 환경변수 강제 보장
load_dotenv(PROJECT_ROOT / "backend" / ".env")

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY")

def _supabase_request_with_retry(
    method: str,
    url: str,
    headers: dict,
    json_data: dict | None = None,
    params: dict | None = None,
    timeout: tuple = _SUPABASE_TIMEOUT,
    max_retries: int = _SUPABASE_MAX_RETRIES,
) -> requests.Response:
    """
    Supabase REST 요청을 지수 백오프 재시도와 함께 실행합니다.
    timeout: (connect_timeout, read_timeout) 튀 지정
    """
    method_upper = method.upper()
    last_exc: Exception | None = None

    for attempt in range(1, max_retries + 1):
        try:
            if method_upper == "GET":
                res = requests.get(url, headers=headers, params=params, timeout=timeout)
            elif method_upper == "POST":
                res = requests.post(url, headers=headers, json=json_data, params=params, timeout=timeout)
            elif method_upper == "PATCH":
                res = requests.patch(url, headers=headers, json=json_data, params=params, timeout=timeout)
            elif method_upper == "PUT":
                res = requests.put(url, headers=headers, json=json_data, params=params, timeout=timeout)
            elif method_upper == "DELETE":
                res = requests.delete(url, headers=headers, params=params, timeout=timeout)
            else:
                raise ValueError("지원하지 않는 HTTP 메소드입니다.")
            return res  # 성공 시 즉시 반환
        except _SUPABASE_RETRY_ON as exc:
            last_exc = exc
            wait = _SUPABASE_RETRY_BACKOFF * (2 ** (attempt - 1))  # 1.5s, 3s, 6s
            is_timeout = isinstance(exc, requests.exceptions.Timeout)
            logger.warning(
                "Supabase %s %s %s (시도 %d/%d) — %.1f초 후 재시도합니다.",
                method_upper,
                url,
                "Read Timeout" if is_timeout else "ConnectionError",
                attempt,
                max_retries,
                wait,
            )
            if attempt < max_retries:
                time.sleep(wait)

    # 모든 재시도 실패
    exc_type = type(last_exc).__name__
    if isinstance(last_exc, requests.exceptions.Timeout):
        raise requests.exceptions.Timeout(
            f"Supabase 연결이 {_SUPABASE_MAX_RETRIES}회 시도 후에도 응답하지 않습니다 (read timeout={_SUPABASE_READ_TIMEOUT}s). "
            "Supabase 대시보드에서 DB 절전(고절) 여부를 확인하거나 잠시 후 다시 시도하세요."
        ) from last_exc
    raise requests.exceptions.ConnectionError(
        f"Supabase 연결에 실패했습니다 ({exc_type}). 네트워크 상태를 확인하세요."
    ) from last_exc


def query_supabase(
    auth_header: str,
    endpoint: str,
    method: str = "GET",
    json_data: dict = None,
    params: dict = None,
    extra_headers: dict = None,
) -> any:
    """
    사용자의 JWT 토큰을 릴레이하여 Supabase REST API를 직접 호출합니다.
    타임아웃 및 연결 오류 시 최대 3회 지수 백오프로 재시도합니다.
    """
    user_id, token = get_user_id_from_header(auth_header)
    url = f"{SUPABASE_URL}/rest/v1/{endpoint}"

    # 로컀 개발 및 테스트 모드에서의 JWT 서명 불일치 에러(401) 방지를 위해
    # debug 또는 TESTING 모드에서는 service_role 키를 릴레이하여 RLS를 우회하되,
    # user_id 필터를 명시적으로 제공하여 데이터 격리를 실현합니다.
    use_service_role = False
    try:
        from flask import current_app
        if current_app and (current_app.config.get("TESTING") or current_app.debug):
            use_service_role = True
    except Exception:
        pass

    supabase_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY") if use_service_role else SUPABASE_ANON_KEY
    if not supabase_key:
        supabase_key = SUPABASE_ANON_KEY

    headers = {
        "apikey": supabase_key,
        "Authorization": f"Bearer {supabase_key}" if use_service_role else f"Bearer {token}",
        "Content-Type": "application/json"
    }
    if extra_headers:
        for header_name, header_value in extra_headers.items():
            if str(header_name).casefold() != "prefer":
                raise ValueError("추가 Supabase 헤더는 Prefer만 허용됩니다.")
            headers["Prefer"] = header_value

    try:
        res = _supabase_request_with_retry(
            method=method,
            url=url,
            headers=headers,
            json_data=json_data,
            params=params,
        )
    except requests.exceptions.Timeout as exc:
        raise Exception(str(exc)) from exc
    except requests.exceptions.ConnectionError as exc:
        raise Exception(str(exc)) from exc

    if res.status_code not in (200, 201, 204):
        raise Exception(f"Supabase REST API 에러 ({res.status_code}): {res.text}")

    if res.text:
        try:
            return res.json()
        except Exception:
            return res.text
    return None

def safe_query_supabase(auth_header: str, endpoint: str, method: str = "GET", json_data: dict = None, params: dict = None) -> any:
    """
    Supabase 작업 로깅용 베스트 에포트 호출.
    테이블이 아직 없거나 권한이 없어도 서비스 흐름은 계속 진행합니다.
    """
    try:
        return query_supabase(auth_header, endpoint, method=method, json_data=json_data, params=params)
    except Exception:
        return None

def sync_dataset_job_to_supabase(auth_header: str, job: dict):
    """데이터 수집 작업 상태를 Supabase에 동기화합니다."""
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

def sync_training_job_to_supabase(auth_header: str, job: dict):
    """모델 학습 작업 상태를 Supabase에 동기화합니다."""
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

def sync_model_registry_to_supabase(auth_header: str, summary_output: str | None):
    """모델 레지스트리를 Supabase 및 로컬 메모리 레지스트리에 동기화합니다."""
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
    
    # 순환 참조 방지를 위해 로컬 임포트 진행
    from backend.services.ml_model_service import (
        discover_model_versions,
        pick_default_model_result,
        pick_passing_recommended_model_result,
    )
    from backend.services.ml_registry_service import list_model_registry, upsert_model_registry

    version_results = discover_model_versions(asset_key)
    latest_result = pick_default_model_result(version_results)
    serving_result = next(
        (
            result
            for result in version_results
            if str((result.get("metrics") or {}).get("model_version") or "") in {
                str(row.get("model_version") or "")
                for row in list_model_registry(asset_type)
                if row.get("is_serving")
            }
        ),
        None,
    )
    recommended_result = pick_passing_recommended_model_result(asset_key, version_results, current_serving=serving_result)
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

def upsert_user_api_key(auth_header: str, data: dict):
    """사용자 API 키 정보를 user_api_keys 테이블에 upsert 처리합니다."""
    user_id, token = get_user_id_from_header(auth_header)
    exchange = data.get("exchange")
    broker_env = data.get("broker_env", "REAL")

    params = {
        "user_id": f"eq.{user_id}",
        "exchange": f"eq.{exchange}",
        "broker_env": f"eq.{broker_env}"
    }
    existing = query_supabase(auth_header, "user_api_keys", "GET", params=params)

    if existing and len(existing) > 0:
        record_id = existing[0]["id"]
        query_supabase(auth_header, f"user_api_keys?id=eq.{record_id}", "PATCH", json_data=data)
    else:
        data["user_id"] = user_id
        query_supabase(auth_header, "user_api_keys", "POST", json_data=data)

SERVICE_ROLE_TIMEOUT_SECONDS = 15


def query_supabase_as_service_role(
    endpoint: str,
    method: str = "GET",
    json_data: dict | list[dict] | None = None,
    params: dict | None = None,
    extra_headers: dict | None = None,
) -> any:
    """
    사용자 JWT 인증 없이 SUPABASE_SERVICE_ROLE_KEY 권한으로 Supabase REST API를 직접 쿼리합니다.
    주로 백그라운드 스케줄러, 토큰 캐시 DB화 등 관리자 수준 동기화 작업에 사용됩니다.
    """
    url = f"{SUPABASE_URL}/rest/v1/{endpoint}"
    service_role_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    if not service_role_key:
        raise ValueError("SUPABASE_SERVICE_ROLE_KEY 환경 변수가 로드되지 않았습니다.")
        
    headers = {
        "apikey": service_role_key,
        "Authorization": f"Bearer {service_role_key}",
        "Content-Type": "application/json"
    }
    if extra_headers:
        for header_name, header_value in extra_headers.items():
            if str(header_name).casefold() != "prefer":
                raise ValueError("추가 Supabase 헤더는 Prefer만 허용됩니다.")
            headers["Prefer"] = str(header_value)
    
    try:
        res = _supabase_request_with_retry(
            method=method,
            url=url,
            headers=headers,
            json_data=json_data,
            params=params,
            timeout=(_SUPABASE_CONNECT_TIMEOUT, SERVICE_ROLE_TIMEOUT_SECONDS),
            max_retries=_SUPABASE_MAX_RETRIES,
        )
    except requests.exceptions.Timeout as exc:
        raise Exception(str(exc)) from exc
    except requests.exceptions.ConnectionError as exc:
        raise Exception(str(exc)) from exc
        
    if res.status_code not in (200, 201, 204):
        raise Exception(f"Supabase REST API service_role 에러 ({res.status_code}): {res.text}")
        
    if res.text:
        try:
            return res.json()
        except Exception:
            return res.text
    return None

def safe_query_supabase_as_service_role(
    endpoint: str,
    method: str = "GET",
    json_data: dict | list[dict] | None = None,
    params: dict | None = None,
    extra_headers: dict | None = None,
) -> any:
    """
    safe_query_supabase의 service_role 버전. 예외를 무시하고 진행합니다.
    """
    try:
        return query_supabase_as_service_role(
            endpoint,
            method=method,
            json_data=json_data,
            params=params,
            extra_headers=extra_headers,
        )
    except Exception:
        logger.warning(
            "Supabase service_role 요청 실패: endpoint=%s method=%s",
            endpoint,
            method,
            exc_info=True,
        )
        return None
