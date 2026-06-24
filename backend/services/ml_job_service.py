import json
import subprocess
import sys
import uuid
from datetime import datetime, timezone
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


def list_jobs(limit: int = 30) -> list[dict[str, Any]]:
    return read_job_history()[:limit]


def resolve_ml_python() -> str:
    candidate = PROJECT_ROOT / "ml" / ".venv" / "bin" / "python"
    if candidate.exists():
        return str(candidate)
    return sys.executable


def run_ml_pipeline(
    config_path: str,
    risk_config_path: str | None = None,
    skip_build_features: bool = False,
    summary_output: str | None = None,
) -> dict[str, Any]:
    python_bin = resolve_ml_python()
    command = [
        python_bin,
        "ml/src/run_pipeline_bundle.py",
        "--config",
        config_path,
    ]
    if risk_config_path:
        command.extend(["--risk-config", risk_config_path])
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
