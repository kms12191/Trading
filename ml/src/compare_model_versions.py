import argparse
import csv
import json
from pathlib import Path
from typing import Any


def resolve_repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def normalize_version(version: str) -> str:
    version = version.strip()
    if version.startswith("v"):
        return version
    return f"v{version}"


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def safe_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    return float(value)


def format_decimal(value: Any, digits: int = 4) -> str:
    number = safe_float(value)
    if number is None:
        return "-"
    return f"{number:.{digits}f}"


def format_percent(value: Any, digits: int = 2) -> str:
    number = safe_float(value)
    if number is None:
        return "-"
    return f"{number * 100:.{digits}f}%"


def read_prediction_summary(path: Path) -> dict[str, Any]:
    summary: dict[str, Any] = {
        "position_counts": {},
        "recommendation_tier_counts": {},
        "top_watch_symbols": [],
        "policy_block_reason_counts": {},
    }
    if not path.exists():
        return summary

    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        watch_rows: list[tuple[int, str]] = []
        for row in reader:
            position = (row.get("position") or "").strip() or "UNKNOWN"
            summary["position_counts"][position] = summary["position_counts"].get(position, 0) + 1

            recommendation_tier = (row.get("recommendation_tier") or "").strip()
            if recommendation_tier:
                summary["recommendation_tier_counts"][recommendation_tier] = summary["recommendation_tier_counts"].get(recommendation_tier, 0) + 1

            watch_candidate = (row.get("watch_candidate") or "").strip()
            watch_rank = (row.get("watch_rank") or "").strip()
            symbol = (row.get("symbol") or "").strip()
            if watch_candidate == "1" and watch_rank.isdigit() and symbol:
                watch_rows.append((int(watch_rank), symbol))

            block_reason = (row.get("policy_block_reason") or "").strip()
            if block_reason:
                for token in block_reason.split("|"):
                    normalized = token.strip()
                    if not normalized:
                        continue
                    summary["policy_block_reason_counts"][normalized] = (
                        summary["policy_block_reason_counts"].get(normalized, 0) + 1
                    )

    summary["top_watch_symbols"] = [symbol for _, symbol in sorted(watch_rows, key=lambda item: item[0])]
    return summary


def format_position_counts(counts: dict[str, int]) -> str:
    if not counts:
        return "-"
    ordered = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    return ", ".join(f"{key}:{value}" for key, value in ordered)


def format_top_counts(counts: dict[str, int], limit: int = 5) -> str:
    if not counts:
        return "-"
    ordered = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    return ", ".join(f"{key}:{value}" for key, value in ordered[:limit])


def load_version_row(repo_root: Path, asset_key: str, version: str) -> dict[str, Any]:
    metrics_path = repo_root / "ml" / "models" / f"lgbm_{asset_key}_signal_{version}.metrics.json"
    composite_path = repo_root / "ml" / "data" / "processed" / f"{asset_key}_backtest_composite_{version}.json"
    up_only_path = repo_root / "ml" / "data" / "processed" / f"{asset_key}_backtest_up_only_{version}.json"
    predictions_path = repo_root / "ml" / "data" / "processed" / f"{asset_key}_predictions_lgbm_{version}.csv"

    metrics = load_json(metrics_path)
    composite = load_json(composite_path)
    up_only = load_json(up_only_path)
    time_series_cv = metrics.get("time_series_cv_average") or {}

    return {
        "version": version,
        "model_version": metrics.get("model_version", f"lgbm_{asset_key}_signal_{version}"),
        "risk_model_version": composite.get("risk_model_version", "-"),
        "roc_auc": metrics.get("roc_auc"),
        "average_precision": metrics.get("average_precision"),
        "cv_roc_auc": time_series_cv.get("roc_auc"),
        "cv_top10_precision": time_series_cv.get("precision_at_top_10pct"),
        "up_only_excess_return_net": up_only.get("excess_return_net"),
        "up_only_max_drawdown_net": up_only.get("max_drawdown_net"),
        "up_only_selection_win_rate_net": up_only.get("selection_win_rate_net"),
        "composite_excess_return_net": composite.get("excess_return_net"),
        "composite_max_drawdown_net": composite.get("max_drawdown_net"),
        "composite_selection_win_rate_net": composite.get("selection_win_rate_net"),
        "composite_test_periods": composite.get("test_periods"),
        "composite_top_n": composite.get("top_n"),
        "avg_selected_count": composite.get("avg_selected_count"),
        **read_prediction_summary(predictions_path),
        "metrics_path": str(metrics_path),
        "composite_path": str(composite_path),
        "up_only_path": str(up_only_path),
        "predictions_path": str(predictions_path),
    }


def pick_operational_candidate(rows: list[dict[str, Any]]) -> dict[str, Any]:
    return max(
        rows,
        key=lambda row: (
            safe_float(row.get("composite_excess_return_net")) or float("-inf"),
            -(abs(safe_float(row.get("composite_max_drawdown_net")) or float("inf"))),
            safe_float(row.get("composite_selection_win_rate_net")) or float("-inf"),
        ),
    )


def build_markdown(asset_key: str, rows: list[dict[str, Any]]) -> str:
    candidate = pick_operational_candidate(rows)
    lines = [
        f"# {asset_key.upper()} 모델 버전 비교",
        "",
        "## 비교표",
        "",
        "| 버전 | 신호 모델 | 위험 모델 | ROC AUC | AP | CV ROC AUC | CV 상위10% | 상승전용 초과수익(순) | 상승전용 MDD | 복합 초과수익(순) | 복합 MDD | 복합 승률(순) | test_periods | top_n | 예측 포지션 |",
        "| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
    ]

    for row in rows:
        lines.append(
            "| "
            + " | ".join(
                [
                    row["version"],
                    row["model_version"],
                    row["risk_model_version"],
                    format_decimal(row["roc_auc"]),
                    format_decimal(row["average_precision"]),
                    format_decimal(row["cv_roc_auc"]),
                    format_decimal(row["cv_top10_precision"]),
                    format_percent(row["up_only_excess_return_net"]),
                    format_percent(row["up_only_max_drawdown_net"]),
                    format_percent(row["composite_excess_return_net"]),
                    format_percent(row["composite_max_drawdown_net"]),
                    format_percent(row["composite_selection_win_rate_net"]),
                    str(row["composite_test_periods"] or "-"),
                    str(row["composite_top_n"] or "-"),
                    format_position_counts(row["position_counts"]),
                ]
            )
            + " |"
        )

    lines.extend(
        [
            "",
            "## 운영 판단",
            "",
            f"- 현재 비교 기준상 운영 후보는 `{candidate['version']}` 입니다.",
            f"- 복합 초과수익(순): {format_percent(candidate['composite_excess_return_net'])}",
            f"- 복합 최대낙폭: {format_percent(candidate['composite_max_drawdown_net'])}",
            f"- 복합 승률(순): {format_percent(candidate['composite_selection_win_rate_net'])}",
            f"- 최신 추천 티어 분포: {format_position_counts(candidate.get('recommendation_tier_counts', {}))}",
            f"- 최신 WATCH 후보: {', '.join(candidate.get('top_watch_symbols', [])) or '-'}",
            f"- 최신 차단 사유 상위: {format_top_counts(candidate.get('policy_block_reason_counts', {}))}",
            "",
            "## 근거 파일",
            "",
        ]
    )

    for row in rows:
        lines.extend(
            [
                f"### {row['version']}",
                f"- metrics: `{row['metrics_path']}`",
                f"- composite backtest: `{row['composite_path']}`",
                f"- up_only backtest: `{row['up_only_path']}`",
                f"- predictions: `{row['predictions_path']}`",
                "",
            ]
        )
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="모델 버전별 주요 성능 지표를 Markdown으로 비교합니다.")
    parser.add_argument("--asset-key", required=True, help="예: stock, crypto")
    parser.add_argument("--version", action="append", required=True, help="예: v8 또는 8")
    parser.add_argument("--output", required=True, help="출력 Markdown 경로")
    args = parser.parse_args()

    repo_root = resolve_repo_root()
    versions = [normalize_version(version) for version in args.version]
    rows = [load_version_row(repo_root, args.asset_key, version) for version in versions]
    markdown = build_markdown(args.asset_key, rows)

    output_path = Path(args.output)
    if not output_path.is_absolute():
        output_path = repo_root / output_path
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(markdown, encoding="utf-8")
    print(str(output_path))


if __name__ == "__main__":
    main()
