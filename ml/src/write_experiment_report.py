import argparse
import json
from datetime import datetime, timezone
from pathlib import Path


def load_json(path_text: str) -> dict:
    path = Path(path_text)
    return json.loads(path.read_text(encoding="utf-8"))


def format_metric(value, percent: bool = False) -> str:
    if value is None:
        return "-"
    number = float(value)
    if percent:
        return f"{number * 100:.2f}%"
    return f"{number:.4f}"


def build_section(title: str, summary: dict) -> str:
    metrics = summary.get("metrics", {})
    risk_metrics = summary.get("risk_metrics", {})
    composite = summary.get("backtest_composite_summary", {})
    up_only = summary.get("backtest_up_only_summary", {})

    lines = [
        f"## {title}",
        "",
        f"- 모델 버전: `{summary.get('model_version', '-')}`",
        f"- 위험 모델 버전: `{summary.get('risk_model_version', '-')}`",
        f"- ROC AUC: {format_metric(metrics.get('roc_auc'))}",
        f"- Average Precision: {format_metric(metrics.get('average_precision'))}",
        f"- Accuracy: {format_metric(metrics.get('accuracy'))}",
        f"- 시계열 CV ROC AUC: {format_metric((metrics.get('time_series_cv_average') or {}).get('roc_auc'))}",
        f"- 시계열 상위 10% 적중: {format_metric((metrics.get('time_series_cv_average') or {}).get('precision_at_top_10pct'))}",
        f"- 위험 ROC AUC: {format_metric(risk_metrics.get('roc_auc'))}",
        f"- 복합 초과수익(순): {format_metric(composite.get('excess_return_net'), percent=True)}",
        f"- 복합 승률(순): {format_metric(composite.get('selection_win_rate_net'), percent=True)}",
        f"- 복합 최대낙폭: {format_metric(composite.get('max_drawdown_net'), percent=True)}",
        f"- 상승 전용 초과수익(순): {format_metric(up_only.get('excess_return_net'), percent=True)}",
        "",
    ]
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="summary JSON 기준 실험 리포트 Markdown을 생성합니다.")
    parser.add_argument("--stock-summary", required=True)
    parser.add_argument("--crypto-summary", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--stock-serving", default="-")
    parser.add_argument("--crypto-serving", default="-")
    args = parser.parse_args()

    stock_summary = load_json(args.stock_summary)
    crypto_summary = load_json(args.crypto_summary)

    lines = [
        "# ML 실험 리포트",
        "",
        f"- 생성 시각: {datetime.now(timezone.utc).isoformat()}",
        f"- 주식 SERVING: `{args.stock_serving}`",
        f"- 코인 SERVING: `{args.crypto_serving}`",
        "",
        build_section("주식", stock_summary),
        build_section("코인", crypto_summary),
    ]

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(lines), encoding="utf-8")
    print(str(output_path))


if __name__ == "__main__":
    main()
