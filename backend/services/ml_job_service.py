import json
import subprocess
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
OPS_DIR = PROJECT_ROOT / "ml" / "data" / "ops"
JOB_HISTORY_PATH = OPS_DIR / "job_history.json"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def ensure_ops_dir() -> None:
    OPS_DIR.mkdir(parents=True, exist_ok=True)


def read_job_history() -> list[dict[str, Any]]:
    ensure_ops_dir()
    if not JOB_HISTORY_PATH.exists():
        return []
    return json.loads(JOB_HISTORY_PATH.read_text(encoding="utf-8"))


def write_job_history(jobs: list[dict[str, Any]]) -> None:
    ensure_ops_dir()
    JOB_HISTORY_PATH.write_text(json.dumps(jobs, ensure_ascii=False, indent=2), encoding="utf-8")


def parse_job_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        normalized = str(value).replace("Z", "+00:00")
        parsed = datetime.fromisoformat(normalized)
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except ValueError:
        return None


def create_job(job_type: str, payload: dict[str, Any]) -> dict[str, Any]:
    job = {
        "id": str(uuid.uuid4()),
        "type": job_type,
        "status": "running",
        "started_at": utc_now_iso(),
        "finished_at": None,
        **payload,
    }
    jobs = read_job_history()
    jobs.insert(0, job)
    write_job_history(jobs)
    return job


def update_job(job_id: str, patch: dict[str, Any]) -> dict[str, Any] | None:
    jobs = read_job_history()
    target = None
    for job in jobs:
        if job.get("id") == job_id:
            job.update(patch)
            target = job
            break
    if target is None:
        return None
    write_job_history(jobs)
    return target


def mark_stale_running_jobs(max_age_minutes: int = 180) -> list[dict[str, Any]]:
    """비정상 종료로 running에 고착된 작업을 실패 상태로 정리합니다."""
    jobs = read_job_history()
    if not jobs:
        return []

    cutoff = datetime.now(timezone.utc) - timedelta(minutes=max_age_minutes)
    stale_jobs: list[dict[str, Any]] = []
    for job in jobs:
        if job.get("status") != "running":
            continue
        started_at = parse_job_datetime(job.get("started_at"))
        if started_at is None or started_at > cutoff:
            continue
        job.update(
            {
                "status": "failed",
                "finished_at": utc_now_iso(),
                "error": f"{max_age_minutes}분 이상 완료되지 않아 stale running 작업으로 자동 정리되었습니다.",
                "stale": True,
            }
        )
        stale_jobs.append(job)

    if stale_jobs:
        write_job_history(jobs)
    return stale_jobs


def list_jobs(limit: int = 30) -> list[dict[str, Any]]:
    mark_stale_running_jobs()
    return read_job_history()[:limit]


def resolve_ml_python() -> str:
    candidate = PROJECT_ROOT / "ml" / ".venv" / "bin" / "python"
    if candidate.exists():
        return str(candidate)
    return sys.executable


def run_ml_pipeline(
    config_path: str,
    risk_config_path: str | None = None,
    short_config_path: str | None = None,
    skip_build_features: bool = False,
    summary_output: str | None = None,
) -> dict[str, Any]:
    python_bin = resolve_ml_python()
    
    # 1. 학습 기동 전 유니버스 스크리너 선행 구동 (active_universe.json 자동 최신화)
    screener_command = [python_bin, "ml/src/universe_screener.py"]
    subprocess.run(
        screener_command,
        cwd=PROJECT_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    command = [
        python_bin,
        "ml/src/run_pipeline_bundle.py",
        "--config",
        config_path,
    ]
    if risk_config_path:
        command.extend(["--risk-config", risk_config_path])
    if short_config_path:
        command.extend(["--short-config", short_config_path])
    if skip_build_features:
        command.append("--skip-build-features")
    if summary_output:
        command.extend(["--summary-output", summary_output])

    completed = subprocess.run(
        command,
        cwd=PROJECT_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    return {
        "command": command,
        "returncode": completed.returncode,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
        "success": completed.returncode == 0,
    }


def run_ml_tuning(
    config_path: str,
    trials: int = 20,
    update_config: bool = False,
) -> dict[str, Any]:
    python_bin = resolve_ml_python()
    build_command = [
        python_bin,
        "ml/src/build_features.py",
        "--config",
        config_path,
    ]
    build_completed = subprocess.run(
        build_command,
        cwd=PROJECT_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    if build_completed.returncode != 0:
        return {
            "command": build_command,
            "returncode": build_completed.returncode,
            "stdout": build_completed.stdout,
            "stderr": build_completed.stderr,
            "success": False,
        }

    command = [
        python_bin,
        "ml/src/tune_hyperparameters.py",
        "--config",
        config_path,
        "--trials",
        str(trials),
    ]
    if update_config:
        command.append("--update-config")

    completed = subprocess.run(
        command,
        cwd=PROJECT_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    return {
        "command": command,
        "returncode": completed.returncode,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
        "success": completed.returncode == 0,
    }
