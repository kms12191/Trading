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


def resolve_symbol_groups(symbol: object, asset_type: object) -> tuple[str, str]:
    if str(asset_type).upper() == "CRYPTO":
        return "CRYPTO", "CRYPTO"
    from backend.services.symbol_metadata import SYMBOL_METADATA

    metadata = SYMBOL_METADATA.get(str(symbol).upper(), {})
    return metadata.get("market", "UNKNOWN"), metadata.get("sector", "UNKNOWN")


def resolve_output_paths(config: dict, strategy: str) -> tuple[Path, Path]:
    if strategy == "composite":
        return (
            Path(config["data"]["backtest_composite_summary_path"]),
            Path(config["data"]["backtest_composite_daily_path"]),
        )
    if strategy == "short_only":
        return (
            Path(config["data"]["backtest_short_summary_path"]),
            Path(config["data"]["backtest_short_daily_path"]),
        )
    return (
        Path(config["data"]["backtest_up_only_summary_path"]),
        Path(config["data"]["backtest_up_only_daily_path"]),
    )


def load_median_dollar_volumes(config_path: str) -> dict[str, float]:
    """
    각 종목별 최근 20일 기준 중간값 거래대금을 원천 캔들 데이터 파일로부터 계산하여 반환합니다.
    """
    raw_path = resolve_ml_path(config_path, load_config(config_path)["data"]["raw_candles_path"])
    if not raw_path.exists():
        return {}
    try:
        df = pd.read_csv(raw_path)
        if df.empty or "close" not in df.columns or "volume" not in df.columns:
            return {}
        df["dollar_volume"] = df["close"].astype(float) * df["volume"].astype(float)
        return {
            str(symbol).upper(): float(group.sort_values("date").tail(20)["dollar_volume"].median())
            for symbol, group in df.groupby("symbol")
        }
    except Exception:
        return {}


def build_daily_backtest(
    valid_df: pd.DataFrame,
    top_n: int,
    fee_bps: float,
    slippage_bps: float,
    funding_bps_per_horizon: float = 0.0,
    selection_policy: dict | None = None,
    volumes_cache: dict[str, float] | None = None,
    stop_loss_pct: float | None = None,
    btc_trend_filter_enabled: bool = False,
) -> tuple[pd.DataFrame, dict]:
    daily_rows = []
    selection_rows = []
    
    # volumes_cache가 제공되지 않은 경우 빈 딕셔너리로 초기화
    volumes = volumes_cache or {}
    universe_cost_rate = (fee_bps + slippage_bps) / 10000.0

    for date, group in valid_df.groupby("date", sort=True):
        universe_group = group.copy()
        ranked = group.copy()
        if "position" in ranked.columns:
            ranked = ranked[ranked["position"] != "HOLD"].copy()
        group_values = ranked.apply(
            lambda row: resolve_symbol_groups(row["symbol"], row.get("asset_type", "STOCK")), axis=1
        )
        ranked["market_group"] = group_values.map(lambda value: value[0])
        ranked["sector_group"] = group_values.map(lambda value: value[1])
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
            universe_avg_return = float(universe_group["future_return"].mean()) if not universe_group.empty else 0.0
            net_universe_avg_return = universe_avg_return - universe_cost_rate
            daily_rows.append(
                {
                    "date": date,
                    "selected_symbols": "",
                    "selected_count": 0,
                    "top_avg_future_return": 0.0,
                    "top_avg_future_return_net": 0.0,
                    "universe_avg_future_return": universe_avg_return,
                    "universe_avg_future_return_net": net_universe_avg_return,
                    "excess_return": -universe_avg_return,
                    "excess_return_net": -net_universe_avg_return,
                    "avg_signal_score": 0.0,
                    "avg_up_probability": 0.0,
                    "avg_risk_probability": 0.0,
                    "precision_at_top_n": 0.0,
                }
            )
            continue

        actual_returns = []
        is_positives = []
        net_returns = []
        for idx, row in selected.iterrows():
            pos = row.get("position", "LONG")

            # BTC 하드 필터: BTC 하락 중이면 LONG 강제 HOLD (v11+)
            if btc_trend_filter_enabled and pos == "LONG":
                btc_filter = row.get("btc_trend_filter", 0.0)
                if pd.notna(btc_filter) and float(btc_filter) >= 1.0:
                    pos = "HOLD"

            if pos == "HOLD":
                actual_returns.append(0.0)
                net_returns.append(0.0)
                is_positives.append(0)
                continue

            ret = row["future_return"]

            # stop-loss 시뮬: horizon 기간 내 최저 수익률이 stop_loss_pct 이하이면 강제 청산 (v11+)
            # LONG 기준: 중간에 -N% 터치하면 future_return 대신 stop_loss_pct 사용
            # SHORT 기준: 중간에 +N% 터치하면 short profit = stop_loss_pct (절댓값 반전)
            if stop_loss_pct is not None and "min_future_return" in row.index:
                min_ret = row.get("min_future_return")
                if pd.notna(min_ret):
                    if pos == "LONG" and float(min_ret) <= stop_loss_pct:
                        ret = stop_loss_pct
                    elif pos == "SHORT" and float(min_ret) >= -stop_loss_pct:
                        # 숏 포지션: 가격이 +|stop_loss_pct| 이상 오르면 손절
                        ret = stop_loss_pct

            # 개별 종목 가변 슬리피지 연산
            symbol_upper = str(row["symbol"]).upper()
            median_vol = volumes.get(symbol_upper, 0.0)
            asset_type = row.get("asset_type", "STOCK")
            
            # 거래대금 반비례 공식 적용 (기본 슬리피지 5 bps = 0.0005)
            # alpha: 주식 5,000,000 / 코인 1,000,000
            alpha = 5000000.0 if asset_type == "STOCK" else 1000000.0
            if median_vol > 0:
                slippage_penalty = 0.0005 + (alpha / median_vol)
            else:
                slippage_penalty = 0.0100  # 유동성 정보 유실 시 최대 1% 패널티 부과
                
            # 슬리피지 1.0% 상한선 제어
            slippage_penalty = min(slippage_penalty, 0.0100)
            funding_cost_rate = (funding_bps_per_horizon / 10000.0) if pos == "SHORT" else 0.0
            configured_slippage_rate = slippage_bps / 10000.0
            cost_rate = (fee_bps / 10000.0) + max(configured_slippage_rate, slippage_penalty) + funding_cost_rate
            
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
        net_universe_avg_return = universe_avg_return - universe_cost_rate
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
            "asset_type",
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
        group_values = selections_df.apply(
            lambda row: resolve_symbol_groups(row["symbol"], row.get("asset_type", "STOCK")), axis=1
        )
        selections_df["market_group"] = group_values.map(lambda value: value[0])
        selections_df["sector_group"] = group_values.map(lambda value: value[1])
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
        "selection_win_rate": float(selections_df["is_positive"].mean()) if not selections_df.empty else 0.0,
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
        "funding_bps_per_horizon": float(funding_bps_per_horizon),
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
    parser.add_argument("--strategy", choices=["up_only", "composite", "short_only"], default="up_only")
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
    if "asset_type" not in valid_df.columns:
        valid_df["asset_type"] = asset_type
    else:
        valid_df["asset_type"] = valid_df["asset_type"].fillna(asset_type).astype(str).str.upper()
        valid_df.loc[valid_df["asset_type"].isin({"", "NAN", "NONE"}), "asset_type"] = asset_type
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
            min_composite_spread = float(prediction_config.get("min_composite_spread", 0.0))
            positions = []
            scores = []
            valid_df["composite_spread"] = valid_df["up_probability"] - valid_df["risk_probability"]
            for _, row in valid_df.iterrows():
                up_p = row["up_probability"]
                risk_p = row["risk_probability"]
                spread = row["composite_spread"]
                if risk_p < long_threshold and spread >= min_composite_spread:
                    positions.append("LONG")
                    scores.append(spread * 100)
                elif risk_p > short_threshold:
                    positions.append("SHORT")
                    scores.append(risk_p * 100)
                else:
                    positions.append("HOLD")
                    scores.append(0.0)
            valid_df["position"] = positions
            valid_df["signal_score"] = scores
            valid_df["scoring_strategy"] = "composite"
        else:
            valid_df = apply_stock_policy_frame(valid_df, prediction_config)
            valid_df["scoring_strategy"] = "composite"
    elif args.strategy == "short_only":
        valid_df["short_probability"] = valid_df["up_probability"]
        valid_df["risk_probability"] = valid_df["short_probability"]
        valid_df["up_probability"] = 1 - valid_df["short_probability"]
        valid_df["position"] = valid_df["short_probability"].map(
            lambda probability: "SHORT" if probability >= float(prediction_config.get("short_entry_threshold", short_threshold)) else "HOLD"
        )
        valid_df["signal_score"] = valid_df["short_probability"] * 100
        valid_df.loc[valid_df["position"] == "HOLD", "signal_score"] = 0.0
        valid_df["scoring_strategy"] = "short_only"
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
    funding_bps_per_horizon = float(backtest_config.get("funding_bps_per_horizon", 0.0))
    top_n = int(args.top_n if args.top_n is not None else backtest_config.get("top_n", 3))
    if args.top_percent is not None:
        top_n = max(1, int(math.ceil(valid_df["symbol"].nunique() * float(args.top_percent))))

    # v11+: stop-loss / BTC trend filter config 읽기
    stop_loss_pct_raw = backtest_config.get("stop_loss_pct")
    stop_loss_pct = float(stop_loss_pct_raw) if stop_loss_pct_raw is not None else None
    btc_trend_filter_enabled = bool(backtest_config.get("btc_trend_filter_enabled", False))

    selection_policy = config.get("prediction", {}).get("selection_policy", {})
    volumes_cache = load_median_dollar_volumes(args.config)
    daily_df, summary = build_daily_backtest(
        valid_df,
        top_n,
        fee_bps,
        slippage_bps,
        funding_bps_per_horizon,
        selection_policy,
        volumes_cache=volumes_cache,
        stop_loss_pct=stop_loss_pct,
        btc_trend_filter_enabled=btc_trend_filter_enabled,
    )
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
