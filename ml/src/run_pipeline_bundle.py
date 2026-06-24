import argparse
import json
import subprocess
import sys
from pathlib import Path

import yaml


PROJECT_ROOT = Path(__file__).resolve().parents[2]
ML_ROOT = PROJECT_ROOT / "ml"


def load_config(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as file:
        return yaml.safe_load(file)


def resolve_cli_path(path_text: str) -> Path:
    path = Path(path_text)
    if path.is_absolute():
        return path

    cwd_candidate = Path.cwd() / path
    if cwd_candidate.exists():
        return cwd_candidate.resolve()

    ml_candidate = ML_ROOT / path
    if ml_candidate.exists():
        return ml_candidate.resolve()

    return cwd_candidate.resolve()


def resolve_ml_path(config_path: Path, target_path: str) -> Path:
    base_dir = config_path.resolve().parent.parent
    path = Path(target_path)
    return path if path.is_absolute() else base_dir / path


def run_step(step_name: str, command: list[str]) -> None:
    print(f"\n[{step_name}] {' '.join(command)}")
    subprocess.run(command, cwd=PROJECT_ROOT, check=True)


def build_summary(config_path: Path, risk_config_path: Path | None) -> dict:
    config = load_config(config_path)
    model_path = resolve_ml_path(config_path, config["model"]["output_path"])
    metrics_path = model_path.with_suffix(".metrics.json")

    summary = {
        "config": str(config_path),
        "model_version": config["model"]["version"],
        "metrics_path": str(metrics_path),
    }

    if metrics_path.exists():
        summary["metrics"] = json.loads(metrics_path.read_text(encoding="utf-8"))

    for key in [
        "predictions_path",
        "backtest_up_only_summary_path",
        "backtest_composite_summary_path",
    ]:
        target = config.get("data", {}).get(key)
        if not target:
            continue

        resolved = resolve_ml_path(config_path, target)
        summary[key] = str(resolved)
        if resolved.exists() and resolved.suffix == ".json":
            summary[key.replace("_path", "")] = json.loads(resolved.read_text(encoding="utf-8"))

    if risk_config_path:
        risk_config = load_config(risk_config_path)
        risk_model_path = resolve_ml_path(risk_config_path, risk_config["model"]["output_path"])
        risk_metrics_path = risk_model_path.with_suffix(".metrics.json")
        summary["risk_config"] = str(risk_config_path)
        summary["risk_model_version"] = risk_config["model"]["version"]
        summary["risk_metrics_path"] = str(risk_metrics_path)
        if risk_metrics_path.exists():
            summary["risk_metrics"] = json.loads(risk_metrics_path.read_text(encoding="utf-8"))

    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="동일 조건 재현용 ML 파이프라인 번들 실행기")
    parser.add_argument("--config", required=True, help="상승 모델 설정 파일")
    parser.add_argument("--risk-config", default=None, help="하락 위험 모델 설정 파일")
    parser.add_argument("--skip-build-features", action="store_true", help="기존 피처 CSV를 그대로 사용")
    parser.add_argument("--skip-backtests", action="store_true", help="백테스트 단계를 건너뜀")
    parser.add_argument("--summary-output", default=None, help="실험 요약 JSON 저장 경로")
    args = parser.parse_args()

    config_path = resolve_cli_path(args.config)
    risk_config_path = resolve_cli_path(args.risk_config) if args.risk_config else None
    python_bin = sys.executable

    if not args.skip_build_features:
        run_step(
            "build_features",
            [python_bin, "ml/src/build_features.py", "--config", str(config_path)],
        )

    run_step(
        "train_up_model",
        [python_bin, "ml/src/train_model.py", "--config", str(config_path)],
    )
    run_step(
        "evaluate_up_model",
        [python_bin, "ml/src/evaluate.py", "--config", str(config_path)],
    )

    if risk_config_path:
        run_step(
            "train_risk_model",
            [python_bin, "ml/src/train_model.py", "--config", str(risk_config_path)],
        )
        run_step(
            "evaluate_risk_model",
            [python_bin, "ml/src/evaluate.py", "--config", str(risk_config_path)],
        )

    run_step(
        "predict",
        [python_bin, "ml/src/predict.py", "--config", str(config_path)],
    )

    if not args.skip_backtests:
        run_step(
            "backtest_up_only",
            [python_bin, "ml/src/backtest_signals.py", "--config", str(config_path), "--strategy", "up_only"],
        )
        if risk_config_path:
            run_step(
                "backtest_composite",
                [python_bin, "ml/src/backtest_signals.py", "--config", str(config_path), "--strategy", "composite"],
            )

    summary = build_summary(config_path, risk_config_path)
    if args.summary_output:
        summary_path = resolve_cli_path(args.summary_output)
        summary_path.parent.mkdir(parents=True, exist_ok=True)
        summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\n[summary] {summary_path}")

    print("\n[done]")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
