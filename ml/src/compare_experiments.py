import argparse
import json
from pathlib import Path


def load_json(path_text: str) -> dict:
    path = Path(path_text)
    return json.loads(path.read_text(encoding="utf-8"))


def extract_row(summary: dict) -> dict:
    metrics = summary.get("metrics", {})
    risk_metrics = summary.get("risk_metrics", {})
    up_only = summary.get("backtest_up_only_summary", {})
    composite = summary.get("backtest_composite_summary", {})
    return {
        "model_version": summary.get("model_version"),
        "risk_model_version": summary.get("risk_model_version"),
        "roc_auc": metrics.get("roc_auc"),
        "average_precision": metrics.get("average_precision"),
        "accuracy": metrics.get("accuracy"),
        "cv_roc_auc": (metrics.get("time_series_cv_average") or {}).get("roc_auc"),
        "cv_top10_precision": (metrics.get("time_series_cv_average") or {}).get("precision_at_top_10pct"),
        "risk_roc_auc": risk_metrics.get("roc_auc"),
        "composite_excess_return_net": composite.get("excess_return_net"),
        "composite_selection_win_rate_net": composite.get("selection_win_rate_net"),
        "composite_max_drawdown_net": composite.get("max_drawdown_net"),
        "up_only_excess_return_net": up_only.get("excess_return_net"),
        "up_only_selection_win_rate_net": up_only.get("selection_win_rate_net"),
        "valid_rows": metrics.get("valid_rows"),
        "test_periods": composite.get("test_periods"),
        "top_n": composite.get("top_n"),
    }


def format_value(value):
    if value is None:
        return "-"
    if isinstance(value, float):
        return f"{value:.6f}"
    return str(value)


def main() -> None:
    parser = argparse.ArgumentParser(description="실험 요약 JSON들을 한 번에 비교합니다.")
    parser.add_argument("--summary", action="append", required=True, help="비교할 summary JSON 경로")
    args = parser.parse_args()

    rows = [extract_row(load_json(path_text)) for path_text in args.summary]
    headers = [
        "model_version",
        "roc_auc",
        "average_precision",
        "accuracy",
        "cv_roc_auc",
        "cv_top10_precision",
        "risk_roc_auc",
        "composite_excess_return_net",
        "composite_selection_win_rate_net",
        "composite_max_drawdown_net",
        "up_only_excess_return_net",
        "valid_rows",
        "test_periods",
        "top_n",
    ]

    widths = {
        header: max(len(header), *(len(format_value(row.get(header))) for row in rows))
        for header in headers
    }
    line = " | ".join(header.ljust(widths[header]) for header in headers)
    divider = "-+-".join("-" * widths[header] for header in headers)
    print(line)
    print(divider)
    for row in rows:
        print(" | ".join(format_value(row.get(header)).ljust(widths[header]) for header in headers))


if __name__ == "__main__":
    main()
