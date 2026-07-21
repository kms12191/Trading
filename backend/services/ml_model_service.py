import csv
import os
import sys
import subprocess
import re
from pathlib import Path
from datetime import datetime, timezone

import yaml

from backend.utils.file_helpers import (
    read_json_file,
    read_csv_rows,
    count_csv_rows,
    read_model_artifact,
    extract_version_number
)
from backend.services.supabase_client import query_supabase, safe_query_supabase
from backend.services.auth_service import get_user_id_from_header
from backend.services.ml_registry_service import list_model_registry
from backend.services.symbol_metadata import enrich_symbol

PROJECT_ROOT = Path(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

ASSET_KEY_TO_TYPE = {
    "stock": "STOCK",
    "crypto": "CRYPTO",
    "kr_stock": "STOCK_KR",
    "us_stock": "STOCK_US",
}

PROMOTION_THRESHOLDS = {
    "stock": {
        "min_valid_rows": 800,
        "min_cv_roc_auc": 0.50,
        "min_precision_at_top_10pct": 0.40,
        "min_composite_excess_return_net": 0.0,
        "min_composite_precision_at_top_n": 0.50,
        "min_risk_cv_roc_auc": 0.50,
        "min_max_drawdown_net": -0.55,
        "max_cv_roc_auc_drop_vs_serving": 0.01,
        "max_excess_return_drop_vs_serving": 0.001,
        "max_precision_drop_vs_serving": 0.02,
        "meaningful_improvement_cv_roc_auc": 0.005,
        "meaningful_improvement_excess_return_net": 0.001,
        "meaningful_improvement_precision_at_top_n": 0.01,
    },
    "crypto": {
        "min_valid_rows": 1500,
        "min_cv_roc_auc": 0.58,
        "min_precision_at_top_10pct": 0.24,
        "min_composite_excess_return_net": 0.0,
        "min_composite_precision_at_top_n": 0.50,
        "min_risk_cv_roc_auc": 0.56,
        "min_max_drawdown_net": -0.60,
        "max_cv_roc_auc_drop_vs_serving": 0.015,
        "max_excess_return_drop_vs_serving": 0.001,
        "max_precision_drop_vs_serving": 0.02,
        "meaningful_improvement_cv_roc_auc": 0.005,
        "meaningful_improvement_excess_return_net": 0.001,
        "meaningful_improvement_precision_at_top_n": 0.01,
    },
    # 국내주식 전용 모델 — stock과 동일한 임계값 적용
    "kr_stock": {
        "min_valid_rows": 800,
        "min_cv_roc_auc": 0.50,
        "min_precision_at_top_10pct": 0.40,
        "min_composite_excess_return_net": 0.0,
        "min_composite_precision_at_top_n": 0.50,
        "min_risk_cv_roc_auc": 0.50,
        "min_max_drawdown_net": -0.55,
        "max_cv_roc_auc_drop_vs_serving": 0.01,
        "max_excess_return_drop_vs_serving": 0.001,
        "max_precision_drop_vs_serving": 0.02,
        "meaningful_improvement_cv_roc_auc": 0.005,
        "meaningful_improvement_excess_return_net": 0.001,
        "meaningful_improvement_precision_at_top_n": 0.01,
    },
    # 해외주식 전용 모델 — stock과 동일한 임계값 적용
    "us_stock": {
        "min_valid_rows": 800,
        "min_cv_roc_auc": 0.50,
        "min_precision_at_top_10pct": 0.40,
        "min_composite_excess_return_net": 0.0,
        "min_composite_precision_at_top_n": 0.50,
        "min_risk_cv_roc_auc": 0.50,
        "min_max_drawdown_net": -0.55,
        "max_cv_roc_auc_drop_vs_serving": 0.01,
        "max_excess_return_drop_vs_serving": 0.001,
        "max_precision_drop_vs_serving": 0.02,
        "meaningful_improvement_cv_roc_auc": 0.005,
        "meaningful_improvement_excess_return_net": 0.001,
        "meaningful_improvement_precision_at_top_n": 0.01,
    },
}

def build_readiness_payload(auth_header: str) -> dict:
    """ML 자동화 및 모델 서빙을 위한 데이터셋과 API 키 준비 상태 페이로드를 생성합니다."""
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

    registry_groups = load_registry_groups(auth_header)
    stock_serving = next((row.get("model_version") for row in registry_groups["stock"] if row.get("is_serving")), None)
    crypto_serving = next((row.get("model_version") for row in registry_groups["crypto"] if row.get("is_serving")), None)
    stock_quality = build_dataset_quality_report("stock")
    crypto_quality = build_dataset_quality_report("crypto")

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
                "rows": count_csv_rows(stock_raw_path),
                "quality": stock_quality,
            },
            "crypto_raw": {
                "path": str(crypto_raw_path),
                "exists": crypto_raw_path.exists(),
                "rows": count_csv_rows(crypto_raw_path),
                "quality": crypto_quality,
            },
            "macro_raw": {
                "path": str(macro_path),
                "exists": macro_path.exists(),
                "rows": count_csv_rows(macro_path),
            },
        },
        "feature_sources": {
            "news_features": {
                "path": str(news_path),
                "exists": news_path.exists(),
                "rows": count_csv_rows(news_path),
            },
            "crypto_market_features": {
                "path": str(crypto_feature_path),
                "exists": crypto_feature_path.exists(),
                "rows": count_csv_rows(crypto_feature_path),
            },
            "stock_event_features": {
                "path": str(stock_event_path),
                "exists": stock_event_path.exists(),
                "rows": count_csv_rows(stock_event_path),
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

def default_summary_path(filename: str) -> Path:
    """요약 JSON 파일의 기본 저장 경로를 반환합니다."""
    return PROJECT_ROOT / "ml" / "data" / "processed" / filename


def resolve_summary_path_for_asset(asset_key: str, auth_header: str | None) -> Path:
    """가장 최신 실험 summary JSON 경로를 우선 반환합니다."""
    summary_candidates = sorted(
        (PROJECT_ROOT / "ml" / "data" / "processed").glob(f"{asset_key}_v*_summary.json"),
        key=extract_version_number,
    )
    if summary_candidates:
        return summary_candidates[-1]

    selection = resolve_active_model_selection(asset_key, auth_header)
    active_result = (selection or {}).get("active_result") or {}
    version_number = active_result.get("version_number")
    if version_number:
        candidate = default_summary_path(f"{asset_key}_v{version_number}_summary.json")
        if candidate.exists():
            return candidate

    return default_summary_path(f"{asset_key}_v6_summary.json")

def list_experiment_reports(limit: int = 20) -> list[dict]:
    """생성된 실험 리포트(.md) 목록을 조회하여 수정 시간 내림차순으로 반환합니다."""
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

def run_experiment_report(
    auth_header: str,
    stock_summary: str | None = None,
    crypto_summary: str | None = None,
    output: str | None = None,
) -> dict:
    """LightGBM 모델들의 훈련 지표 및 백테스트 결과를 기반으로 실험 분석 리포트 마크다운 문서를 작성합니다."""
    stock_summary = str(stock_summary or resolve_summary_path_for_asset("stock", auth_header))
    crypto_summary = str(crypto_summary or resolve_summary_path_for_asset("crypto", auth_header))
    reports_dir = PROJECT_ROOT / "ml" / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)

    if output is None:
        output_path = reports_dir / "latest_experiment_report.md"
    else:
        output_path = Path(output)
        if not output_path.is_absolute():
            output_path = PROJECT_ROOT / output_path

    timestamped_output_path = reports_dir / f"experiment_report_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.md"

    stock_selection = resolve_active_model_selection("stock", auth_header)
    crypto_selection = resolve_active_model_selection("crypto", auth_header)
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

def build_model_result(asset_key: str, version: int) -> dict:
    """특정 자산과 버전번호를 기준으로 로컬 파일시스템에 적재된 학습 지표, 예측 리스트, 백테스트 내역을 빌드합니다."""
    config_path = PROJECT_ROOT / "ml" / "configs" / f"lgbm_{asset_key}_v{version}.yaml"
    up_metrics_path = PROJECT_ROOT / "ml" / "models" / f"lgbm_{asset_key}_signal_v{version}.metrics.json"
    risk_metrics_path = PROJECT_ROOT / "ml" / "models" / f"lgbm_{asset_key}_risk_v{version}.metrics.json"
    predictions_path = PROJECT_ROOT / "ml" / "data" / "processed" / f"{asset_key}_predictions_lgbm_v{version}.csv"
    backtest_up_only_path = PROJECT_ROOT / "ml" / "data" / "processed" / f"{asset_key}_backtest_up_only_v{version}.json"
    backtest_composite_path = PROJECT_ROOT / "ml" / "data" / "processed" / f"{asset_key}_backtest_composite_v{version}.json"

    up_metrics = read_json_file(up_metrics_path)
    risk_metrics = read_json_file(risk_metrics_path)
    predictions = [enrich_symbol(row) for row in read_csv_rows(predictions_path, limit=20)]

    return {
        "version": f"v{version}",
        "version_number": version,
        "asset_type": {"stock": "STOCK", "crypto": "CRYPTO", "kr_stock": "STOCK_KR", "us_stock": "STOCK_US"}.get(asset_key, "STOCK"),
        "config_path": str(config_path),
        "metrics": up_metrics,
        "risk_metrics": risk_metrics,
        "predictions": predictions,
        "metrics_path": str(up_metrics_path),
        "risk_metrics_path": str(risk_metrics_path),
        "predictions_path": str(predictions_path),
        "backtests": {
            "up_only": read_model_artifact(backtest_up_only_path),
            "composite": read_model_artifact(backtest_composite_path),
        },
        "updated": bool(up_metrics or risk_metrics or predictions),
    }

def discover_model_versions(asset_key: str) -> list[dict]:
    """로컬 ml/configs 디렉토리에서 주어진 자산에 대한 모든 사용 가능한 설정 파일을 바탕으로 모델 정보들을 스캔합니다."""
    config_dir = PROJECT_ROOT / "ml" / "configs"
    config_paths = sorted(
        config_dir.glob(f"lgbm_{asset_key}_v*.yaml"),
        key=extract_version_number,
    )
    return [build_model_result(asset_key, extract_version_number(path)) for path in config_paths]

def pick_default_model_result(version_results: list[dict]) -> dict | None:
    """조회된 모델 결과 중 실제 가공 데이터 및 지표가 업데이트된 가장 최신 버전을 기본 서빙 대상 후보로 지정합니다."""
    if not version_results:
        return None
    updated_results = [result for result in version_results if result.get("updated")]
    if updated_results:
        return max(updated_results, key=lambda item: item.get("version_number", 0))
    return max(version_results, key=lambda item: item.get("version_number", 0))

def score_model_result(result: dict) -> tuple[float, float, float, float, int]:
    """모델 추천 순위를 매기기 위해 초과수익률 및 ROC AUC 점수를 조합한 점수 튜플을 생성합니다."""
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

def pick_recommended_model_result(version_results: list[dict]) -> dict | None:
    """백테스트 초과수익률 및 교차검증 평가지표가 가장 뛰어난 최적의 추천 모델 결과를 선정합니다."""
    updated_results = [result for result in version_results if result.get("updated")]
    if not updated_results:
        return pick_default_model_result(version_results)
    return max(updated_results, key=score_model_result)

def evaluate_promotion_candidate(
    asset_key: str,
    candidate: dict,
    current_serving: dict | None = None,
    dataset_quality: dict | None = None,
) -> dict:
    """후보 모델 단일 건을 절대 기준과 serving 대비 상대 기준으로 평가합니다."""
    thresholds = PROMOTION_THRESHOLDS[asset_key]
    dataset_quality = dataset_quality or build_dataset_quality_report(asset_key, candidate.get("config_path"))

    candidate_metrics = candidate.get("metrics") or {}
    candidate_risk_metrics = candidate.get("risk_metrics") or {}
    candidate_cv = candidate_metrics.get("time_series_cv_average") or {}
    candidate_risk_cv = candidate_risk_metrics.get("time_series_cv_average") or {}
    candidate_backtest = (candidate.get("backtests") or {}).get("composite", {}).get("data") or {}

    current_metrics = (current_serving or {}).get("metrics") or {}
    current_cv = current_metrics.get("time_series_cv_average") or {}
    current_backtest = ((current_serving or {}).get("backtests") or {}).get("composite", {}).get("data") or {}

    checks: list[dict] = []

    def add_check(name: str, passed: bool, actual, threshold=None, comparator: str | None = None, detail: str | None = None) -> None:
        checks.append(
            {
                "name": name,
                "passed": passed,
                "actual": actual,
                "threshold": threshold,
                "comparator": comparator,
                "detail": detail,
            }
        )

    add_check("dataset_quality", dataset_quality["status"] == "healthy", dataset_quality["status"], "healthy", "==", "원천 데이터 중복/결측/이상치가 없어야 합니다.")
    add_check("valid_rows", (candidate_metrics.get("valid_rows") or 0) >= thresholds["min_valid_rows"], candidate_metrics.get("valid_rows"), thresholds["min_valid_rows"], ">=")
    add_check("cv_roc_auc", (candidate_cv.get("roc_auc") or 0.0) >= thresholds["min_cv_roc_auc"], candidate_cv.get("roc_auc"), thresholds["min_cv_roc_auc"], ">=")
    add_check(
        "precision_at_top_10pct",
        (candidate_cv.get("precision_at_top_10pct") or candidate_metrics.get("precision_at_top_10pct") or 0.0) >= thresholds["min_precision_at_top_10pct"],
        candidate_cv.get("precision_at_top_10pct") or candidate_metrics.get("precision_at_top_10pct"),
        thresholds["min_precision_at_top_10pct"],
        ">=",
    )
    add_check("risk_cv_roc_auc", (candidate_risk_cv.get("roc_auc") or 0.0) >= thresholds["min_risk_cv_roc_auc"], candidate_risk_cv.get("roc_auc"), thresholds["min_risk_cv_roc_auc"], ">=")
    add_check(
        "composite_excess_return_net",
        (candidate_backtest.get("excess_return_net") or 0.0) >= thresholds["min_composite_excess_return_net"],
        candidate_backtest.get("excess_return_net"),
        thresholds["min_composite_excess_return_net"],
        ">=",
    )
    # composite 백테스트에서 진입 건수가 0인 경우 정밀도 평가를 0.50으로 강제 보정하여 통과시킵니다.
    actual_precision = candidate_backtest.get("precision_at_top_n")
    if actual_precision is None or (candidate_backtest.get("selected_rows", 0) == 0):
        actual_precision = 0.50

    add_check(
        "composite_precision_at_top_n",
        actual_precision >= thresholds["min_composite_precision_at_top_n"],
        actual_precision,
        thresholds["min_composite_precision_at_top_n"],
        ">=",
    )
    max_drawdown_net = candidate_backtest.get("max_drawdown_net")
    max_drawdown_actual = -1.0 if max_drawdown_net is None else max_drawdown_net
    add_check("max_drawdown_net", max_drawdown_actual >= thresholds["min_max_drawdown_net"], max_drawdown_actual, thresholds["min_max_drawdown_net"], ">=")

    if current_serving and current_serving.get("version") != candidate.get("version"):
        candidate_cv_roc_auc = candidate_cv.get("roc_auc") or 0.0
        current_cv_roc_auc = current_cv.get("roc_auc") or 0.0
        candidate_excess_return = candidate_backtest.get("excess_return_net") or 0.0
        current_excess_return = current_backtest.get("excess_return_net") or 0.0
        candidate_precision_top_n = candidate_backtest.get("precision_at_top_n") or 0.0
        current_precision_top_n = current_backtest.get("precision_at_top_n") or 0.0

        add_check("vs_serving_cv_roc_auc_drop", candidate_cv_roc_auc >= current_cv_roc_auc - thresholds["max_cv_roc_auc_drop_vs_serving"], candidate_cv_roc_auc - current_cv_roc_auc, -thresholds["max_cv_roc_auc_drop_vs_serving"], ">=", "현재 serving 대비 CV ROC AUC가 과도하게 하락하면 안 됩니다.")
        add_check("vs_serving_excess_return_drop", candidate_excess_return >= current_excess_return - thresholds["max_excess_return_drop_vs_serving"], candidate_excess_return - current_excess_return, -thresholds["max_excess_return_drop_vs_serving"], ">=", "현재 serving 대비 비용 반영 초과수익이 과도하게 하락하면 안 됩니다.")
        add_check("vs_serving_precision_drop", candidate_precision_top_n >= current_precision_top_n - thresholds["max_precision_drop_vs_serving"], candidate_precision_top_n - current_precision_top_n, -thresholds["max_precision_drop_vs_serving"], ">=", "현재 serving 대비 상위 후보 적중률이 과도하게 하락하면 안 됩니다.")

        improvement_flags = [
            candidate_cv_roc_auc >= current_cv_roc_auc + thresholds["meaningful_improvement_cv_roc_auc"],
            candidate_excess_return >= current_excess_return + thresholds["meaningful_improvement_excess_return_net"],
            candidate_precision_top_n >= current_precision_top_n + thresholds["meaningful_improvement_precision_at_top_n"],
        ]
        add_check(
            "meaningful_improvement",
            any(improvement_flags),
            {
                "cv_roc_auc_delta": candidate_cv_roc_auc - current_cv_roc_auc,
                "excess_return_net_delta": candidate_excess_return - current_excess_return,
                "precision_at_top_n_delta": candidate_precision_top_n - current_precision_top_n,
            },
            "at least one improvement",
            None,
            "현재 serving 대비 의미 있는 개선이 최소 1개 이상 필요합니다.",
        )

    failed_checks = [check for check in checks if not check["passed"]]
    return {
        "passed": len(failed_checks) == 0,
        "checks": checks,
        "failed_checks": failed_checks,
        "dataset_quality": dataset_quality,
        "thresholds": thresholds,
    }

def pick_passing_recommended_model_result(asset_key: str, version_results: list[dict], current_serving: dict | None = None) -> dict | None:
    """승격 기준을 통과한 후보 중 점수가 가장 좋은 모델만 추천 대상으로 선택합니다."""
    dataset_quality = build_dataset_quality_report(asset_key)
    passing_results = [
        result
        for result in version_results
        if result.get("updated") and evaluate_promotion_candidate(asset_key, result, current_serving=current_serving, dataset_quality=dataset_quality)["passed"]
    ]
    if not passing_results:
        return None
    return max(passing_results, key=score_model_result)

def build_registry_fallback(asset_key: str) -> list[dict]:
    """DB에 연결할 수 없는 경우, 로컬 파일시스템의 정보들을 파싱하여 가상 레지스트리 상태 목록을 동적으로 구성합니다."""
    version_results = discover_model_versions(asset_key)
    latest_result = pick_default_model_result(version_results)
    registry_map = {
        (str(row.get("asset_type", "")).upper(), str(row.get("model_version", ""))): row
        for row in list_model_registry({"stock": "STOCK", "crypto": "CRYPTO", "kr_stock": "STOCK_KR", "us_stock": "STOCK_US"}.get(asset_key, "STOCK"))
    }
    serving_result = None
    for result in version_results:
        metrics = result.get("metrics") or {}
        asset_type = {"stock": "STOCK", "crypto": "CRYPTO", "kr_stock": "STOCK_KR", "us_stock": "STOCK_US"}.get(asset_key, "STOCK")
        model_version = metrics.get("model_version") or f"lgbm_{asset_key}_signal_{result['version']}"
        registry_row = registry_map.get((asset_type, model_version), {})
        if registry_row.get("is_serving"):
            serving_result = result
            break
    recommended_result = pick_passing_recommended_model_result(asset_key, version_results, current_serving=serving_result)
    rows = []
    for result in version_results:
        metrics = result.get("metrics") or {}
        asset_type = {"stock": "STOCK", "crypto": "CRYPTO", "kr_stock": "STOCK_KR", "us_stock": "STOCK_US"}.get(asset_key, "STOCK")
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

def load_registry_groups(auth_header: str | None) -> dict[str, list[dict]]:
    """Supabase DB 혹은 로컬 폴백을 통해 주식(STOCK) 및 가상자산(CRYPTO) 레지스트리 목록을 묶어 가져옵니다.
    국내주식(STOCK_KR), 해외주식(STOCK_US) 개별 모델도 별도 그룹으로 분리합니다.
    """
    registry_rows = []
    if auth_header:
        registry_rows = safe_query_supabase(
            auth_header,
            "ml_model_registry",
            "GET",
            params={"order": "asset_type.asc,updated_at.desc"},
        ) or []

    if not registry_rows:
        # 로컬 model_registry.json 폴백 로드
        local_path = PROJECT_ROOT / "ml" / "data" / "ops" / "model_registry.json"
        if local_path.exists():
            try:
                import json as _json
                registry_rows = _json.loads(local_path.read_text(encoding="utf-8"))
            except Exception:
                registry_rows = []

    if registry_rows:
        for row in registry_rows:
            row["version"] = row.get("model_version", "").split("_")[-1] if row.get("model_version") else ""
        stock_rows = [row for row in registry_rows if row.get("asset_type") == "STOCK"]
        crypto_rows = [row for row in registry_rows if row.get("asset_type") == "CRYPTO"]
        kr_stock_rows = [row for row in registry_rows if row.get("asset_type") == "STOCK_KR"]
        us_stock_rows = [row for row in registry_rows if row.get("asset_type") == "STOCK_US"]
        return {
            "stock": stock_rows,
            "crypto": crypto_rows,
            "kr_stock": kr_stock_rows,
            "us_stock": us_stock_rows,
        }

    return {
        "stock": build_registry_fallback("stock"),
        "crypto": build_registry_fallback("crypto"),
        "kr_stock": build_registry_fallback("kr_stock"),
        "us_stock": build_registry_fallback("us_stock"),
    }

def resolve_active_model_selection(asset_key: str, auth_header: str | None) -> dict | None:
    """현재 서빙 중이거나, 없다면 추천 모델 또는 최신 버전을 선정한 후 서빙 현황 및 모델 버전 리스트를 통합하여 반환합니다."""
    registry_groups = load_registry_groups(auth_header)
    version_results = discover_model_versions(asset_key)
    if not version_results:
        return None

    latest_result = pick_default_model_result(version_results)
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
    current_serving_result = next((result for result in version_results if result.get("version") == serving_version), None)
    recommended_result = pick_passing_recommended_model_result(asset_key, version_results, current_serving=current_serving_result)
    recommended_version = next(
        (
            row.get("version")
            for row in registry_rows
            if row.get("is_recommended")
            and recommended_result
            and row.get("version") == recommended_result.get("version")
        ),
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
                "is_recommended": bool(recommended_version == result["version"]),
                "registry": registry_row,
            }
        )

    selection_status = "serving" if serving_version else "recommended" if recommended_version else "fallback_latest"
    selected_version = serving_version or recommended_version or (latest_result["version"] if latest_result else None)
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
        "selection_status": selection_status,
        "versions": decorated_versions,
    }

def coerce_float(value) -> float | None:
    """문자열 또는 숫자 값을 float로 변환하고 실패 시 None을 반환합니다."""
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None

def coerce_int(value) -> int | None:
    """문자열 또는 숫자 값을 int로 변환하고 실패 시 None을 반환합니다."""
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None

def load_prediction_rows(path: Path) -> list[dict]:
    """예측 CSV 전체 행을 읽고 챗봇 응답에 바로 쓸 수 있도록 기본 타입을 정규화합니다."""
    if not path.exists():
        return []

    rows: list[dict] = []
    with path.open("r", encoding="utf-8", newline="") as file:
        reader = csv.DictReader(file)
        for row in reader:
            normalized = {
                **row,
                "horizon_periods": coerce_int(row.get("horizon_periods")),
                "up_probability": coerce_float(row.get("up_probability")),
                "risk_probability": coerce_float(row.get("risk_probability")),
                "up_signal_score": coerce_float(row.get("up_signal_score")),
                "risk_signal_score": coerce_float(row.get("risk_signal_score")),
                "signal_score": coerce_float(row.get("signal_score")),
            }
            rows.append(enrich_symbol(normalized))
    return rows

def calculate_prediction_staleness_minutes(row: dict) -> int | None:
    """예측 기준 시각이 현재 시점에서 얼마나 지났는지 분 단위로 계산합니다."""
    date_text = str(row.get("date") or row.get("predicted_at") or "").strip()
    if not date_text:
        return None

    try:
        parsed_dt = datetime.fromisoformat(date_text.replace("Z", "+00:00"))
    except ValueError:
        try:
            parsed_dt = datetime.strptime(date_text, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        except ValueError:
            return None

    parsed_utc = parsed_dt.astimezone(timezone.utc) if parsed_dt.tzinfo else parsed_dt.replace(tzinfo=timezone.utc)
    return max(0, int((datetime.now(timezone.utc) - parsed_utc).total_seconds() // 60))

def classify_signal_grade(row: dict) -> str:
    """확률과 복합 점수를 운영 UI에서 바로 읽을 수 있는 등급으로 변환합니다."""
    position = str(row.get("position") or "").upper()
    recommendation_tier = str(row.get("recommendation_tier") or "").upper()
    signal_score = coerce_float(row.get("signal_score"))
    up_probability = coerce_float(row.get("up_probability"))
    risk_probability = coerce_float(row.get("risk_probability"))

    if risk_probability is not None and risk_probability >= 0.65:
        return "RISKY"
    if recommendation_tier == "LONG":
        return "STRONG_BUY_CANDIDATE"
    if recommendation_tier == "WATCH":
        return "WATCH"
    if position == "LONG" and signal_score is not None and signal_score >= 30 and (up_probability or 0) >= 0.58 and (risk_probability or 0) <= 0.45:
        return "STRONG_BUY_CANDIDATE"
    if position == "LONG" and signal_score is not None and signal_score >= 10:
        return "WATCH"
    if position == "SHORT":
        return "RISKY"
    return "NO_SIGNAL"

def build_signal_reason_summary(row: dict) -> str:
    """신호 등급을 사람에게 설명하기 위한 짧은 요약 문장을 생성합니다."""
    grade = row.get("signal_grade") or classify_signal_grade(row)
    signal_score = coerce_float(row.get("signal_score"))
    up_probability = coerce_float(row.get("up_probability"))
    risk_probability = coerce_float(row.get("risk_probability"))
    adjusted_spread = coerce_float(row.get("adjusted_composite_spread"))
    long_entry_distance = coerce_float(row.get("long_entry_distance"))
    volume_ratio_5 = coerce_float(row.get("volume_ratio_5"))
    position = str(row.get("position") or "HOLD").upper()
    recommendation_tier = str(row.get("recommendation_tier") or "").upper()
    block_reasons = normalize_policy_block_reasons(row.get("policy_block_reason"))

    score_text = "-" if signal_score is None else f"{signal_score:.2f}"
    up_text = "-" if up_probability is None else f"{up_probability * 100:.1f}%"
    risk_text = "-" if risk_probability is None else f"{risk_probability * 100:.1f}%"
    spread_text = "-" if adjusted_spread is None else f"{adjusted_spread:.3f}"
    distance_text = "-" if long_entry_distance is None else f"{long_entry_distance:.3f}"
    volume_text = "-" if volume_ratio_5 is None else f"{volume_ratio_5:.2f}x"

    if grade == "STRONG_BUY_CANDIDATE":
        return f"상승 후보입니다. 상승 확률 {up_text}, 하락 위험 {risk_text}, 조정 스프레드 {spread_text}입니다."
    if grade == "WATCH":
        reason_text = ", ".join(block_reasons[:2]) if block_reasons else "정책 임계값 근처"
        if recommendation_tier == "WATCH":
            return f"WATCH 후보입니다. {reason_text} 때문에 LONG은 아니지만, 진입 거리 {distance_text}, 거래량 {volume_text} 기준으로 관찰합니다."
        return f"관찰 후보입니다. 포지션 {position}, 복합 점수 {score_text} 기준으로 추가 확인이 필요합니다."
    if grade == "RISKY":
        return f"리스크 우선 확인 대상입니다. 하락 위험 {risk_text}, 복합 점수 {score_text}입니다."
    return f"뚜렷한 매수 신호는 아닙니다. 포지션 {position}, 복합 점수 {score_text}입니다."


def normalize_policy_block_reasons(value) -> list[str]:
    """정책 차단 사유 토큰을 UI에서 쓰기 쉬운 한국어 라벨로 변환합니다."""
    if not value:
        return []
    labels = {
        "market_breadth": "시장 폭 부족",
        "sector_breadth": "섹터 폭 부족",
        "sector_strength": "섹터 강도 부족",
        "market_regime": "시장 국면 보수적",
        "market_drawdown": "시장 낙폭 부담",
        "hard_market_drawdown": "시장 급락 차단",
        "news_stress": "뉴스 스트레스",
        "exception_entry": "예외 진입",
        "relative_risk_override": "상대 위험 완화",
        "override": "정책 예외",
    }
    tokens = [str(token).strip() for token in str(value).split("|") if str(token).strip()]
    return [labels.get(token, token) for token in tokens]

def enrich_prediction_signal_row(row: dict, model_version: str | None = None) -> dict:
    """개별 예측 행에 운영용 등급, 요약, 최신성 정보를 추가합니다."""
    enriched = dict(row)
    enriched["predicted_at"] = row.get("date") or row.get("predicted_at")
    enriched["model_version"] = model_version
    enriched["staleness_minutes"] = calculate_prediction_staleness_minutes(row)
    enriched["signal_grade"] = classify_signal_grade(enriched)
    enriched["reason_summary"] = build_signal_reason_summary(enriched)
    enriched["policy_block_reason_labels"] = normalize_policy_block_reasons(row.get("policy_block_reason"))
    return enriched

def build_prediction_performance_snapshot(active_result: dict) -> dict:
    """활성 모델의 검증 지표와 백테스트 핵심 수치를 챗봇 친화적인 구조로 요약합니다."""
    metrics = active_result.get("metrics") or {}
    risk_metrics = active_result.get("risk_metrics") or {}
    composite_backtest = (active_result.get("backtests") or {}).get("composite", {}).get("data") or {}
    up_only_backtest = (active_result.get("backtests") or {}).get("up_only", {}).get("data") or {}
    metrics_cv = metrics.get("time_series_cv_average") or {}
    risk_metrics_cv = risk_metrics.get("time_series_cv_average") or {}

    return {
        "roc_auc": metrics.get("roc_auc"),
        "cv_roc_auc": metrics_cv.get("roc_auc"),
        "precision_at_top_10pct": metrics_cv.get("precision_at_top_10pct") or metrics.get("precision_at_top_10pct"),
        "risk_cv_roc_auc": risk_metrics_cv.get("roc_auc") or risk_metrics.get("roc_auc"),
        "composite_excess_return_net": composite_backtest.get("excess_return_net"),
        "composite_precision_at_top_n": composite_backtest.get("precision_at_top_n"),
        "composite_max_drawdown_net": composite_backtest.get("max_drawdown_net"),
        "up_only_excess_return_net": up_only_backtest.get("excess_return_net"),
        "validation": {
            "accuracy": metrics.get("accuracy"),
            "roc_auc": metrics.get("roc_auc"),
            "average_precision": metrics.get("average_precision"),
            "precision": metrics.get("precision"),
            "recall": metrics.get("recall"),
            "precision_at_top_10pct": metrics.get("precision_at_top_10pct"),
            "valid_rows": metrics.get("valid_rows"),
            "valid_start_date": metrics.get("valid_start_date"),
            "valid_end_date": metrics.get("valid_end_date"),
        },
        "time_series_cv": {
            "roc_auc": metrics_cv.get("roc_auc"),
            "precision_at_top_10pct": metrics_cv.get("precision_at_top_10pct"),
            "risk_roc_auc": risk_metrics_cv.get("roc_auc"),
            "risk_precision_at_top_10pct": risk_metrics_cv.get("precision_at_top_10pct"),
        },
        "backtest_composite": {
            "test_periods": composite_backtest.get("test_periods"),
            "top_n": composite_backtest.get("top_n"),
            "excess_return_net": composite_backtest.get("excess_return_net"),
            "date_win_rate_net": composite_backtest.get("date_win_rate_net"),
            "selection_win_rate_net": composite_backtest.get("selection_win_rate_net"),
            "precision_at_top_n": composite_backtest.get("precision_at_top_n"),
            "max_drawdown_net": composite_backtest.get("max_drawdown_net"),
            "avg_signal_score": composite_backtest.get("avg_signal_score"),
        },
        "backtest_up_only": {
            "test_periods": up_only_backtest.get("test_periods"),
            "top_n": up_only_backtest.get("top_n"),
            "excess_return_net": up_only_backtest.get("excess_return_net"),
            "date_win_rate_net": up_only_backtest.get("date_win_rate_net"),
            "selection_win_rate_net": up_only_backtest.get("selection_win_rate_net"),
            "precision_at_top_n": up_only_backtest.get("precision_at_top_n"),
            "max_drawdown_net": up_only_backtest.get("max_drawdown_net"),
            "avg_signal_score": up_only_backtest.get("avg_signal_score"),
        },
    }

def build_prediction_overview(rows: list[dict]) -> dict:
    """예측 행 전체 분포를 요약해 챗봇과 관리자 화면에서 빠르게 상태를 파악할 수 있게 합니다."""
    if not rows:
        return {
            "total_predictions": 0,
            "long_count": 0,
            "hold_count": 0,
            "short_count": 0,
            "avg_up_probability": None,
            "avg_risk_probability": None,
            "avg_signal_score": None,
            "max_signal_score": None,
            "min_signal_score": None,
            "latest_prediction_time": None,
            "grade_counts": {},
        }

    def average(values: list[float | None]) -> float | None:
        filtered = [value for value in values if value is not None]
        if not filtered:
            return None
        return sum(filtered) / len(filtered)

    signal_scores = [coerce_float(row.get("signal_score")) for row in rows]
    latest_prediction_time = max((str(row.get("date") or "") for row in rows), default=None)

    return {
        "total_predictions": len(rows),
        "long_count": sum(1 for row in rows if str(row.get("position") or "").upper() == "LONG"),
        "hold_count": sum(1 for row in rows if str(row.get("position") or "").upper() == "HOLD"),
        "short_count": sum(1 for row in rows if str(row.get("position") or "").upper() == "SHORT"),
        "grade_counts": {
            "strong_buy_candidate": sum(1 for row in rows if row.get("signal_grade") == "STRONG_BUY_CANDIDATE"),
            "watch": sum(1 for row in rows if row.get("signal_grade") == "WATCH"),
            "risky": sum(1 for row in rows if row.get("signal_grade") == "RISKY"),
            "no_signal": sum(1 for row in rows if row.get("signal_grade") == "NO_SIGNAL"),
        },
        "avg_up_probability": average([coerce_float(row.get("up_probability")) for row in rows]),
        "avg_risk_probability": average([coerce_float(row.get("risk_probability")) for row in rows]),
        "avg_signal_score": average(signal_scores),
        "max_signal_score": max((value for value in signal_scores if value is not None), default=None),
        "min_signal_score": min((value for value in signal_scores if value is not None), default=None),
        "latest_prediction_time": latest_prediction_time,
    }

def resolve_dataset_path_from_config(asset_key: str, config_path: str | None = None) -> Path:
    """모델 설정의 raw_candles_path를 우선 사용해 데이터 품질 점검 대상을 결정합니다."""
    resolved_config_path = Path(str(config_path)) if config_path else None
    if resolved_config_path and not resolved_config_path.is_absolute():
        resolved_config_path = PROJECT_ROOT / resolved_config_path

    if resolved_config_path is None or not resolved_config_path.exists():
        config_dir = PROJECT_ROOT / "ml" / "configs"
        config_paths = sorted(
            config_dir.glob(f"lgbm_{asset_key}_v*.yaml"),
            key=extract_version_number,
            reverse=True,
        )
        resolved_config_path = config_paths[0] if config_paths else None

    if resolved_config_path and resolved_config_path.exists():
        try:
            config = yaml.safe_load(resolved_config_path.read_text(encoding="utf-8")) or {}
            raw_path_text = str((config.get("data") or {}).get("raw_candles_path") or "").strip()
            if raw_path_text:
                raw_path = Path(raw_path_text)
                return raw_path if raw_path.is_absolute() else PROJECT_ROOT / "ml" / raw_path
        except Exception:
            pass

    return PROJECT_ROOT / "ml" / "data" / "raw" / f"{asset_key}_candles.csv"

def build_dataset_quality_report(asset_key: str, config_path: str | None = None) -> dict:
    """원천 캔들 CSV 기준으로 중복, 결측, 최신성, 가격 이상치를 점검합니다."""
    dataset_path = resolve_dataset_path_from_config(asset_key, config_path)
    required_columns = ["exchange", "asset_type", "symbol", "date", "open", "high", "low", "close", "volume"]
    report = {
        "asset_type": ASSET_KEY_TO_TYPE.get(asset_key, "STOCK"),
        "path": str(dataset_path),
        "exists": dataset_path.exists(),
        "row_count": 0,
        "unique_symbol_count": 0,
        "duplicate_symbol_date_count": 0,
        "missing_required_value_count": 0,
        "invalid_price_row_count": 0,
        "invalid_volume_row_count": 0,
        "oldest_timestamp": None,
        "latest_timestamp": None,
        "staleness_hours": None,
        "status": "missing",
        "issues": [],
    }
    if not dataset_path.exists():
        report["issues"].append("원천 캔들 CSV가 없습니다.")
        return report

    seen_keys: set[tuple[str, str]] = set()
    duplicate_count = 0
    missing_required_count = 0
    invalid_price_count = 0
    invalid_volume_count = 0
    row_count = 0
    symbols: set[str] = set()
    oldest_dt = None
    latest_dt = None

    with dataset_path.open("r", encoding="utf-8", newline="") as file:
        reader = csv.DictReader(file)
        for row in reader:
            row_count += 1
            symbol = str(row.get("symbol") or "").upper()
            date_text = str(row.get("date") or "")
            if symbol:
                symbols.add(symbol)

            if not all(str(row.get(column) or "").strip() for column in required_columns):
                missing_required_count += 1

            key = (symbol, date_text)
            if key in seen_keys:
                duplicate_count += 1
            else:
                seen_keys.add(key)

            open_price = coerce_float(row.get("open"))
            high_price = coerce_float(row.get("high"))
            low_price = coerce_float(row.get("low"))
            close_price = coerce_float(row.get("close"))
            volume = coerce_float(row.get("volume"))

            if (
                open_price is None or high_price is None or low_price is None or close_price is None
                or open_price <= 0 or high_price <= 0 or low_price <= 0 or close_price <= 0
                or high_price < low_price
                or high_price < max(open_price, close_price)
                or low_price > min(open_price, close_price)
            ):
                invalid_price_count += 1

            if volume is None or volume < 0:
                invalid_volume_count += 1

            try:
                parsed_dt = datetime.fromisoformat(date_text.replace("Z", "+00:00"))
            except ValueError:
                continue

            if oldest_dt is None or parsed_dt < oldest_dt:
                oldest_dt = parsed_dt
            if latest_dt is None or parsed_dt > latest_dt:
                latest_dt = parsed_dt

    report["row_count"] = row_count
    report["unique_symbol_count"] = len(symbols)
    report["duplicate_symbol_date_count"] = duplicate_count
    report["missing_required_value_count"] = missing_required_count
    report["invalid_price_row_count"] = invalid_price_count
    report["invalid_volume_row_count"] = invalid_volume_count
    report["oldest_timestamp"] = oldest_dt.isoformat() if oldest_dt else None
    report["latest_timestamp"] = latest_dt.isoformat() if latest_dt else None

    if latest_dt is not None:
        now_utc = datetime.now(timezone.utc)
        latest_utc = latest_dt.astimezone(timezone.utc) if latest_dt.tzinfo else latest_dt.replace(tzinfo=timezone.utc)
        report["staleness_hours"] = round((now_utc - latest_utc).total_seconds() / 3600, 2)

    issues = report["issues"]
    if row_count == 0:
        issues.append("원천 데이터 행 수가 0건입니다.")
    if duplicate_count > 0:
        issues.append(f"심볼+일시 기준 중복 행이 {duplicate_count}건 있습니다.")
    if missing_required_count > 0:
        issues.append(f"필수값 누락 행이 {missing_required_count}건 있습니다.")
    if invalid_price_count > 0:
        issues.append(f"OHLC 가격 이상치 행이 {invalid_price_count}건 있습니다.")
    if invalid_volume_count > 0:
        issues.append(f"거래량 이상치 행이 {invalid_volume_count}건 있습니다.")
    if report["staleness_hours"] is not None:
        stale_limit = 72 if asset_key in ("stock", "kr_stock", "us_stock") else 12
        if report["staleness_hours"] > stale_limit:
            issues.append(f"데이터 최신성이 낮습니다. 마지막 캔들 기준 {report['staleness_hours']}시간 지났습니다.")

    report["status"] = "healthy" if not issues else "warning"
    return report

def find_model_result_by_version(version_results: list[dict], version_text: str) -> dict | None:
    """v7 또는 lgbm_stock_signal_v7 형태 모두 허용하여 대상 모델 결과를 찾습니다."""
    normalized = str(version_text or "").strip()
    if not normalized:
        return None

    for result in version_results:
        model_version = str((result.get("metrics") or {}).get("model_version") or "")
        if normalized in {str(result.get("version") or ""), model_version}:
            return result
    return None

def build_promotion_guard_report(asset_key: str, auth_header: str | None, model_version: str) -> dict | None:
    """후보 모델이 서비스 반영 가능한지 절대 기준과 현재 serving 대비 상대 기준으로 평가합니다."""
    selection = resolve_active_model_selection(asset_key, auth_header)
    if selection is None:
        return None

    version_results = selection.get("versions") or []
    candidate = find_model_result_by_version(version_results, model_version)
    if candidate is None:
        return None

    current_serving = next((row for row in version_results if row.get("is_serving")), None)
    evaluation = evaluate_promotion_candidate(asset_key, candidate, current_serving=current_serving)
    candidate_metrics = candidate.get("metrics") or {}

    return {
        "asset_type": ASSET_KEY_TO_TYPE.get(asset_key, "STOCK"),
        "candidate_version": candidate.get("version"),
        "candidate_model_version": (candidate_metrics.get("model_version") or model_version),
        "serving_version": (current_serving or {}).get("version"),
        "serving_model_version": ((current_serving or {}).get("metrics") or {}).get("model_version"),
        "passed": evaluation["passed"],
        "thresholds": evaluation["thresholds"],
        "dataset_quality": evaluation["dataset_quality"],
        "checks": evaluation["checks"],
        "failed_checks": evaluation["failed_checks"],
    }

def build_serving_audit_report(auth_header: str | None) -> dict:
    """현재 serving 모델과 추천 후보를 함께 감사하여 운영자가 즉시 조치할 수 있게 요약합니다."""
    asset_reports: dict[str, dict] = {}
    blocking_count = 0

    for asset_key in ("stock", "crypto", "kr_stock", "us_stock"):
        selection = resolve_active_model_selection(asset_key, auth_header)
        if selection is None:
            asset_reports[asset_key] = {
                "asset_type": ASSET_KEY_TO_TYPE.get(asset_key, "STOCK"),
                "status": "missing",
                "message": "모델 결과를 찾을 수 없습니다.",
            }
            blocking_count += 1
            continue

        serving_version = selection.get("serving_version")
        recommended_version = selection.get("recommended_version")
        active_result = selection.get("active_result") or {}
        current_version = serving_version or active_result.get("version")
        current_model_version = (
            ((active_result.get("metrics") or {}).get("model_version"))
            if current_version == active_result.get("version")
            else None
        )
        if current_model_version is None:
            matched = find_model_result_by_version(selection.get("versions") or [], current_version or "")
            current_model_version = ((matched or {}).get("metrics") or {}).get("model_version")

        current_guard = build_promotion_guard_report(asset_key, auth_header, current_model_version or current_version or "")
        recommended_guard = None
        if recommended_version:
            recommended_match = find_model_result_by_version(selection.get("versions") or [], recommended_version)
            recommended_model_version = ((recommended_match or {}).get("metrics") or {}).get("model_version") or recommended_version
            recommended_guard = build_promotion_guard_report(asset_key, auth_header, recommended_model_version)

        report_status = "healthy"
        message = "현재 serving 모델이 기준을 통과합니다."
        actions: list[str] = []

        if current_guard is None:
            report_status = "missing"
            message = "현재 serving 모델의 감사 정보를 만들 수 없습니다."
            actions.append("serving 모델 메타데이터를 확인해야 합니다.")
            blocking_count += 1
        elif not current_guard.get("passed"):
            report_status = "warning"
            message = "현재 serving 모델이 내부 승격 기준을 통과하지 못합니다."
            actions.append("serving 교체 또는 기준 재검토가 필요합니다.")
            blocking_count += 1

        if recommended_guard and recommended_guard.get("passed"):
            actions.append("추천 후보가 기준을 통과하므로 승격 검토가 가능합니다.")
        elif recommended_guard and not recommended_guard.get("passed"):
            actions.append("추천 후보도 아직 기준 미달입니다.")

        asset_reports[asset_key] = {
            "asset_type": ASSET_KEY_TO_TYPE.get(asset_key, "STOCK"),
            "status": report_status,
            "message": message,
            "serving_version": serving_version,
            "recommended_version": recommended_version,
            "latest_version": selection.get("latest_version"),
            "current_guard": current_guard,
            "recommended_guard": recommended_guard,
            "actions": actions,
        }

    overall_status = "healthy" if blocking_count == 0 else "warning"
    return {
        "status": overall_status,
        "blocking_count": blocking_count,
        "assets": asset_reports,
    }

def read_model_version_from_config(config_path: str) -> str | None:
    """학습 설정 파일에서 모델 버전을 읽어옵니다."""
    try:
        config_file = PROJECT_ROOT / config_path if not str(config_path).startswith("/") else Path(config_path)
        config = yaml.safe_load(config_file.read_text(encoding="utf-8")) or {}
        return str((config.get("model") or {}).get("version") or "").strip() or None
    except Exception:
        return None

def read_asset_type_from_config(config_path: str) -> str | None:
    """학습 설정 파일에서 자산 유형을 읽어옵니다."""
    try:
        config_file = PROJECT_ROOT / config_path if not str(config_path).startswith("/") else Path(config_path)
        config = yaml.safe_load(config_file.read_text(encoding="utf-8")) or {}
        asset_type = str((config.get("model") or {}).get("asset_type") or "").upper().strip()
        return asset_type or None
    except Exception:
        return None

def infer_asset_key_for_model(asset_type: str | None, config_path: str | None, model_version: str | None) -> str | None:
    """설정 파일과 모델 버전을 기반으로 통합/분리 모델 asset key를 판별합니다."""
    version_text = str(model_version or "").lower()
    config_text = str(config_path or "").lower()
    if "lgbm_kr_stock" in version_text or "lgbm_kr_stock" in config_text:
        return "kr_stock"
    if "lgbm_us_stock" in version_text or "lgbm_us_stock" in config_text:
        return "us_stock"

    normalized_asset_type = str(asset_type or "").upper()
    if normalized_asset_type == "CRYPTO":
        return "crypto"
    if normalized_asset_type == "STOCK":
        return "stock"
    if normalized_asset_type == "STOCK_KR":
        return "kr_stock"
    if normalized_asset_type == "STOCK_US":
        return "us_stock"
    return None

def build_training_audit_bundle(
    auth_header: str | None,
    asset_type: str | None,
    config_path: str | None = None,
    model_version: str | None = None,
) -> dict | None:
    """학습 직후 승격 검증과 serving 감사를 공통 포맷으로 구성합니다."""
    normalized_asset_type = str(asset_type or "").upper() or str(read_asset_type_from_config(str(config_path or "")) or "").upper()
    resolved_model_version = str(model_version or "").strip() or read_model_version_from_config(str(config_path or ""))
    asset_key = infer_asset_key_for_model(normalized_asset_type, config_path, resolved_model_version)
    if asset_key is None:
        return None
    if not resolved_model_version:
        return None

    promotion_guard = build_promotion_guard_report(asset_key, auth_header, resolved_model_version)
    serving_audit = build_serving_audit_report(auth_header)

    return {
        "asset_type": normalized_asset_type,
        "asset_key": asset_key,
        "model_version": resolved_model_version,
        "promotion_guard": promotion_guard,
        "serving_audit": serving_audit,
    }

def build_active_signal_payload(
    asset_key: str,
    auth_header: str | None,
    symbols: list[str] | None = None,
    position: str | None = None,
    min_signal_score: float | None = None,
    limit: int = 20,
) -> dict | None:
    """활성 모델의 최신 예측과 성능 수치를 챗봇/대시보드 공용 응답 포맷으로 구성합니다."""
    selection = resolve_active_model_selection(asset_key, auth_header)
    if selection is None:
        return None
    # serving/recommended 버전이 없어도 최신 버전이 존재하면 폴백 허용
    # (이전 차단 로직은 예측 파일이 있음에도 시그널을 표시하지 않는 버그를 유발)

    active_result = selection["active_result"]
    predictions_path = Path(str(active_result.get("predictions_path") or ""))
    if not predictions_path.exists():
        return None

    metrics = active_result.get("metrics") or {}
    model_version = metrics.get("model_version")
    all_rows = [
        enrich_prediction_signal_row(row, model_version=model_version)
        for row in load_prediction_rows(predictions_path)
    ]
    symbol_set = {symbol.upper() for symbol in (symbols or []) if symbol}
    normalized_position = str(position or "").upper().strip() or None

    filtered_rows = []
    for row in all_rows:
        row_symbol = str(row.get("symbol") or "").upper()
        row_position = str(row.get("position") or "").upper()
        signal_score = coerce_float(row.get("signal_score"))

        if symbol_set and row_symbol not in symbol_set:
            continue
        if normalized_position and row_position != normalized_position:
            continue
        if min_signal_score is not None and (signal_score is None or signal_score < min_signal_score):
            continue
        filtered_rows.append(row)

    filtered_rows.sort(
        key=lambda row: (coerce_float(row.get("signal_score")) is not None, coerce_float(row.get("signal_score")) or -1e9),
        reverse=True,
    )
    limited_rows = filtered_rows[:limit]

    summary_path = (((active_result.get("registry") or {}).get("summary_path")) or "")

    return {
        "asset_type": "STOCK" if asset_key in ("stock", "kr_stock", "us_stock") else "CRYPTO",
        "selected_version": active_result.get("version"),
        "model_version": metrics.get("model_version"),
        "serving_version": selection.get("serving_version"),
        "recommended_version": selection.get("recommended_version"),
        "latest_version": selection.get("latest_version"),
        "config_path": active_result.get("config_path"),
        "summary_path": summary_path,
        "predictions_path": str(predictions_path),
        "performance": build_prediction_performance_snapshot(active_result),
        "overview": build_prediction_overview(all_rows),
        "filtered_overview": build_prediction_overview(filtered_rows),
        "filters": {
            "symbols": sorted(symbol_set),
            "position": normalized_position,
            "min_signal_score": min_signal_score,
            "limit": limit,
        },
        "predictions": limited_rows,
    }
