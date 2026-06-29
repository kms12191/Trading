import os
import argparse
import json
import math
import sys
from pathlib import Path

import joblib
import pandas as pd
import yaml

os.environ.setdefault("LOKY_MAX_CPU_COUNT", str(os.cpu_count() or 1))

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))

from backend.services.symbol_metadata import SYMBOL_METADATA
from ml.src.model_utils import apply_probability_calibration, calculate_max_drawdown, split_by_time
from ml.src.policy_utils import apply_selection_caps, apply_stock_policy_frame, predict_with_payload


def load_config(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as file:
        return yaml.safe_load(file)


def resolve_ml_path(config_path: str, target_path: str) -> Path:
    base_dir = Path(config_path).resolve().parent.parent
    path = Path(target_path)
    return path if path.is_absolute() else base_dir / path


def read_features_csv(path: Path) -> pd.DataFrame:
    """종목코드 문자열 보존을 위해 symbol dtype을 고정합니다."""
    return pd.read_csv(path, dtype={"symbol": "string"}, low_memory=False)


def load_model_payload(path: Path) -> dict:
    return joblib.load(path)


def resolve_output_paths(config: dict, strategy: str) -> tuple[Path, Path]:
    if strategy == "composite":
        return (
            Path(config["data"]["backtest_composite_summary_path"]),
            Path(config["data"]["backtest_composite_daily_path"]),
        )
    return (
        Path(config["data"]["backtest_up_only_summary_path"]),
        Path(config["data"]["backtest_up_only_daily_path"]),
    )


def build_daily_backtest(
    valid_df: pd.DataFrame,
    top_n: int,
    fee_bps: float,
    slippage_bps: float,
    selection_policy: dict | None = None,
) -> tuple[pd.DataFrame, dict]:
    daily_rows = []
    selection_rows = []
    cost_rate = (fee_bps + slippage_bps) / 10000.0

    for date, group in valid_df.groupby("date", sort=True):
        universe_group = group.copy()
        ranked = group.copy()
        if "position" in ranked.columns:
            ranked = ranked[ranked["position"] != "HOLD"].copy()
        ranked["market_group"] = ranked["symbol"].map(
            lambda symbol: SYMBOL_METADATA.get(str(symbol).upper(), {}).get("market", "UNKNOWN")
        )
        ranked["sector_group"] = ranked["symbol"].map(
            lambda symbol: SYMBOL_METADATA.get(str(symbol).upper(), {}).get("sector", "UNKNOWN")
        )
        if "market_country_group" in ranked.columns:
            ranked["market_group"] = ranked["market_country_group"].fillna(ranked["market_group"])
        elif "market_country" in ranked.columns:
            ranked["market_group"] = ranked["market_country"].fillna(ranked["market_group"])
        if "sector" in ranked.columns:
            ranked["sector_group"] = ranked["sector"].fillna(ranked["sector_group"])
        ranked = ranked.sort_values("signal_score", ascending=False).copy()
        if selection_policy and selection_policy.get("enabled"):
            selected = apply_selection_caps(ranked, min(top_n, len(ranked)), selection_policy)
        else:
            selected = ranked.head(min(top_n, len(ranked))).copy()
        if selected.empty:
            continue

        actual_returns = []
        is_positives = []
        net_returns = []
        for idx, row in selected.iterrows():
            pos = row.get("position", "LONG")
            ret = row["future_return"]
            actual_ret = -ret if pos == "SHORT" else ret
            net_ret = actual_ret - cost_rate
            actual_returns.append(actual_ret)
            net_returns.append(net_ret)
            is_pos = 1 if actual_ret > 0 else 0
            is_positives.append(is_pos)

        selected["actual_future_return"] = actual_returns
        selected["future_return_net"] = net_returns
        selected["is_positive"] = is_positives

        top_avg_return = float(selected["actual_future_return"].mean())
        net_top_avg_return = float(selected["future_return_net"].mean())
        universe_avg_return = float(universe_group["future_return"].mean())
        net_universe_avg_return = universe_avg_return - cost_rate
        excess_return = top_avg_return - universe_avg_return
        net_excess_return = net_top_avg_return - net_universe_avg_return

        daily_rows.append(
            {
                "date": date,
                "selected_symbols": ",".join(selected["symbol"].astype(str).tolist()),
                "selected_count": int(len(selected)),
                "top_avg_future_return": top_avg_return,
                "top_avg_future_return_net": net_top_avg_return,
                "universe_avg_future_return": universe_avg_return,
                "universe_avg_future_return_net": net_universe_avg_return,
                "excess_return": excess_return,
                "excess_return_net": net_excess_return,
                "avg_signal_score": float(selected["signal_score"].mean()),
                "avg_up_probability": float(selected["up_probability"].mean()),
                "avg_risk_probability": float(selected["risk_probability"].mean()),
                "precision_at_top_n": float(selected["is_positive"].mean()),
            }
        )

        selection_cols = [
            "symbol",
            "future_return",
            "up_probability",
            "risk_probability",
            "signal_score",
        ]
        for optional_col in ("market_country_group", "market_country", "sector"):
            if optional_col in selected.columns:
                selection_cols.append(optional_col)
        if "position" in selected.columns:
            selection_cols.append("position")

        selection_rows.append(
            selected[selection_cols].assign(
                date=date,
                future_return_net=selected["future_return_net"],
                is_positive=selected["is_positive"],
            )
        )

    daily_df = pd.DataFrame(daily_rows)
    selections_df = pd.concat(selection_rows, ignore_index=True) if selection_rows else pd.DataFrame()
    if not selections_df.empty:
        selections_df["market_group"] = selections_df["symbol"].map(
            lambda symbol: SYMBOL_METADATA.get(str(symbol).upper(), {}).get("market", "UNKNOWN")
        )
        selections_df["sector_group"] = selections_df["symbol"].map(
            lambda symbol: SYMBOL_METADATA.get(str(symbol).upper(), {}).get("sector", "UNKNOWN")
        )
        if "market_country_group" in selections_df.columns:
            selections_df["market_group"] = selections_df["market_country_group"].fillna(selections_df["market_group"])
        elif "market_country" in selections_df.columns:
            selections_df["market_group"] = selections_df["market_country"].fillna(selections_df["market_group"])
        if "sector" in selections_df.columns:
            selections_df["sector_group"] = selections_df["sector"].fillna(selections_df["sector_group"])
    symbol_summary = (
        selections_df.groupby("symbol")
        .agg(
            selections=("symbol", "count"),
            avg_future_return=("future_return", "mean"),
            avg_future_return_net=("future_return_net", "mean"),
            win_rate=("is_positive", "mean"),
            avg_signal_score=("signal_score", "mean"),
        )
        .reset_index()
        .sort_values(["avg_future_return_net", "win_rate"], ascending=False)
        if not selections_df.empty
        else pd.DataFrame()
    )
    market_summary = (
        selections_df.groupby("market_group")
        .agg(
            selections=("symbol", "count"),
            avg_future_return=("future_return", "mean"),
            avg_future_return_net=("future_return_net", "mean"),
            win_rate=("is_positive", "mean"),
            avg_signal_score=("signal_score", "mean"),
        )
        .reset_index()
        .sort_values(["avg_future_return_net", "win_rate"], ascending=False)
        if not selections_df.empty
        else pd.DataFrame()
    )
    sector_summary = (
        selections_df.groupby("sector_group")
        .agg(
            selections=("symbol", "count"),
            avg_future_return=("future_return", "mean"),
            avg_future_return_net=("future_return_net", "mean"),
            win_rate=("is_positive", "mean"),
            avg_signal_score=("signal_score", "mean"),
        )
        .reset_index()
        .sort_values(["avg_future_return_net", "win_rate"], ascending=False)
        if not selections_df.empty
        else pd.DataFrame()
    )

    summary = {
        "test_periods": int(len(daily_df)),
        "top_n": int(top_n),
        "avg_selected_count": float(daily_df["selected_count"].mean()) if not daily_df.empty else 0.0,
        "top_avg_future_return": float(daily_df["top_avg_future_return"].mean()) if not daily_df.empty else 0.0,
        "top_avg_future_return_net": float(daily_df["top_avg_future_return_net"].mean()) if not daily_df.empty else 0.0,
        "universe_avg_future_return": float(daily_df["universe_avg_future_return"].mean()) if not daily_df.empty else 0.0,
        "universe_avg_future_return_net": float(daily_df["universe_avg_future_return_net"].mean()) if not daily_df.empty else 0.0,
        "excess_return": float(daily_df["excess_return"].mean()) if not daily_df.empty else 0.0,
        "excess_return_net": float(daily_df["excess_return_net"].mean()) if not daily_df.empty else 0.0,
        "date_win_rate": float((daily_df["top_avg_future_return"] > 0).mean()) if not daily_df.empty else 0.0,
        "date_win_rate_net": float((daily_df["top_avg_future_return_net"] > 0).mean()) if not daily_df.empty else 0.0,
        "selection_win_rate": float((selections_df["future_return"] > 0).mean()) if not selections_df.empty else 0.0,
        "selection_win_rate_net": float((selections_df["future_return_net"] > 0).mean()) if not selections_df.empty else 0.0,
        "avg_signal_score": float(selections_df["signal_score"].mean()) if not selections_df.empty else 0.0,
        "avg_up_probability": float(selections_df["up_probability"].mean()) if not selections_df.empty else 0.0,
        "avg_risk_probability": float(selections_df["risk_probability"].mean()) if not selections_df.empty else 0.0,
        "precision_at_top_n": float(selections_df["is_positive"].mean()) if not selections_df.empty else 0.0,
        "selection_return_std": float(selections_df["future_return_net"].std()) if not selections_df.empty else 0.0,
        "max_drawdown_net": calculate_max_drawdown(daily_df["top_avg_future_return_net"]) if not daily_df.empty else 0.0,
        "selected_rows": int(len(selections_df)),
        "fee_bps": float(fee_bps),
        "slippage_bps": float(slippage_bps),
        "symbol_breakdown": symbol_summary.to_dict(orient="records"),
        "market_breakdown": market_summary.to_dict(orient="records"),
        "sector_breakdown": sector_summary.head(15).to_dict(orient="records"),
    }
    return daily_df, summary


def main() -> None:
    parser = argparse.ArgumentParser(description="signal_score 기준 단순 백테스트를 수행합니다.")
    parser.add_argument("--config", default="configs/lgbm_stock_v1.yaml", help="상승 모델 설정 파일 경로")
    parser.add_argument("--model", default=None, help="상승 모델 파일 경로")
    parser.add_argument("--risk-model", default=None, help="하락 위험 모델 파일 경로")
    parser.add_argument("--strategy", choices=["up_only", "composite"], default="up_only")
    parser.add_argument("--top-n", type=int, default=None, help="날짜별 상위 후보 개수")
    parser.add_argument("--top-percent", type=float, default=None, help="날짜별 상위 퍼센트(예: 0.1 = 상위 10%)")
    parser.add_argument("--fee-bps", type=float, default=None, help="거래 수수료 basis points")
    parser.add_argument("--slippage-bps", type=float, default=None, help="슬리피지 basis points")
    parser.add_argument("--summary-output", default=None, help="백테스트 요약 JSON 경로")
    parser.add_argument("--daily-output", default=None, help="백테스트 일별 CSV 경로")
    args = parser.parse_args()

    config = load_config(args.config)
    features_path = resolve_ml_path(args.config, config["data"]["features_path"])
    model_path = resolve_ml_path(args.config, args.model or config["model"]["output_path"])
    risk_model_path = args.risk_model or config.get("prediction", {}).get("risk_model_path")

    features_df = read_features_csv(features_path)
    _, valid_df = split_by_time(features_df, float(config["model"]["validation_ratio"]))

    up_payload = load_model_payload(model_path)
    valid_df = valid_df.copy()
    valid_df["up_probability"] = predict_with_payload(up_payload, valid_df)
    valid_df["risk_probability"] = 1 - valid_df["up_probability"]
    valid_df["scoring_strategy"] = "up_only"
    valid_df["up_model_version"] = up_payload["config"]["model"]["version"]
    valid_df["risk_model_version"] = ""
    valid_df["signal_score"] = valid_df["up_probability"] * 100

    asset_type = config["model"].get("asset_type", "STOCK").upper()
    long_threshold = float(config.get("prediction", {}).get("long_threshold", 0.30))
    short_threshold = float(config.get("prediction", {}).get("short_threshold", 0.70))
    prediction_config = config.get("prediction", {})
    stock_min_composite_spread = float(prediction_config.get("stock_min_composite_spread", 0.0))

    if args.strategy == "composite":
        if not risk_model_path:
            raise ValueError("복합 백테스트에는 risk 모델 경로가 필요합니다.")
        risk_payload = load_model_payload(resolve_ml_path(args.config, str(risk_model_path)))
        valid_df["risk_probability"] = predict_with_payload(risk_payload, valid_df)
        valid_df["risk_model_version"] = risk_payload["config"]["model"]["version"]
        
        if asset_type == "CRYPTO":
            positions = []
            scores = []
            for _, row in valid_df.iterrows():
                up_p = row["up_probability"]
                risk_p = row["risk_probability"]
                if risk_p < long_threshold:
                    positions.append("LONG")
                    scores.append(up_p * 100)
                elif risk_p > short_threshold:
                    positions.append("SHORT")
                    scores.append(risk_p * 100)
                else:
                    positions.append("HOLD")
                    scores.append(0.0)
            valid_df["position"] = positions
            valid_df["signal_score"] = scores
            valid_df["composite_spread"] = valid_df["up_probability"] - valid_df["risk_probability"]
            valid_df["scoring_strategy"] = "composite"
        else:
            valid_df = apply_stock_policy_frame(valid_df, prediction_config)
            valid_df["scoring_strategy"] = "composite"
    else:
        valid_df["position"] = "LONG"
        valid_df["signal_score"] = valid_df["up_probability"] * 100
        valid_df["scoring_strategy"] = "up_only"

    summary_output, daily_output = resolve_output_paths(config, args.strategy)
    if not summary_output.is_absolute():
        summary_output = resolve_ml_path(args.config, str(summary_output))
    if not daily_output.is_absolute():
        daily_output = resolve_ml_path(args.config, str(daily_output))
    if args.summary_output:
        summary_output = Path(args.summary_output)
    if args.daily_output:
        daily_output = Path(args.daily_output)

    backtest_config = config.get("backtest", {})
    fee_bps = float(args.fee_bps if args.fee_bps is not None else backtest_config.get("fee_bps", 0.0))
    slippage_bps = float(args.slippage_bps if args.slippage_bps is not None else backtest_config.get("slippage_bps", 0.0))
    top_n = int(args.top_n if args.top_n is not None else backtest_config.get("top_n", 3))
    if args.top_percent is not None:
        top_n = max(1, int(math.ceil(valid_df["symbol"].nunique() * float(args.top_percent))))

    selection_policy = config.get("prediction", {}).get("selection_policy", {})
    daily_df, summary = build_daily_backtest(valid_df, top_n, fee_bps, slippage_bps, selection_policy)
    summary.update(
        {
            "strategy": args.strategy,
            "asset_type": config["model"]["asset_type"],
            "model_version": up_payload["config"]["model"]["version"],
            "risk_model_version": valid_df["risk_model_version"].iloc[0] if not valid_df.empty else "",
            "top_n": top_n,
            "top_percent": args.top_percent,
            "valid_rows": int(len(valid_df)),
            "valid_start_date": str(valid_df["date"].min()) if not valid_df.empty else "",
            "valid_end_date": str(valid_df["date"].max()) if not valid_df.empty else "",
            "selection_policy": selection_policy,
        }
    )

    summary_output.parent.mkdir(parents=True, exist_ok=True)
    daily_output.parent.mkdir(parents=True, exist_ok=True)
    summary_output.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    daily_df.to_csv(daily_output, index=False)

    print(f"백테스트 요약 저장 완료: {summary_output}")
    print(f"백테스트 일별 결과 저장 완료: {daily_output}")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
