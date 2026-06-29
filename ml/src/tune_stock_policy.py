import argparse
import json
import sys
from pathlib import Path

import optuna
import pandas as pd
import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))

from ml.src.backtest_signals import build_daily_backtest, load_model_payload, read_features_csv, resolve_ml_path
from ml.src.model_utils import split_by_time
from ml.src.policy_utils import apply_stock_policy_frame, predict_with_payload


optuna.logging.set_verbosity(optuna.logging.WARNING)


def load_config(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as file:
        return yaml.safe_load(file)


def save_config(path: str, config: dict) -> None:
    with open(path, "w", encoding="utf-8") as file:
        yaml.safe_dump(config, file, allow_unicode=True, sort_keys=False)


def build_policy_config(base_config: dict, params: dict) -> dict:
    config = json.loads(json.dumps(base_config))
    prediction = config.setdefault("prediction", {})
    backtest = config.setdefault("backtest", {})

    prediction["long_threshold"] = round(float(params["long_threshold"]), 4)
    prediction["stock_min_composite_spread"] = round(float(params["stock_min_composite_spread"]), 4)
    backtest["top_n"] = int(params["top_n"])
    prediction["stock_policy"] = {
        "enabled": True,
        "min_market_breadth_5": round(float(params["min_market_breadth_5"]), 4),
        "min_sector_breadth_5": round(float(params["min_sector_breadth_5"]), 4),
        "min_sector_strength_score": round(float(params["min_sector_strength_score"]), 4),
        "min_market_regime_score": int(params["min_market_regime_score"]),
        "max_market_news_stress_score": round(float(params["max_market_news_stress_score"]), 4),
        "max_primary_market_drawdown_60": round(float(params["max_primary_market_drawdown_60"]), 4),
        "risk_on_long_threshold_bonus": round(float(params["risk_on_long_threshold_bonus"]), 4),
        "risk_on_min_spread_bonus": round(float(params["risk_on_min_spread_bonus"]), 4),
        "risk_off_long_threshold_bonus": round(float(params["risk_off_long_threshold_bonus"]), 4),
        "risk_off_min_spread_bonus": round(float(params["risk_off_min_spread_bonus"]), 4),
        "risk_on_min_score": int(params["risk_on_min_score"]),
        "risk_off_max_score": int(params["risk_off_max_score"]),
        "risk_on_market_breadth_5": round(float(params["risk_on_market_breadth_5"]), 4),
        "risk_off_market_breadth_5": round(float(params["risk_off_market_breadth_5"]), 4),
        "risk_off_primary_market_drawdown_60": round(float(params["risk_off_primary_market_drawdown_60"]), 4),
    }
    prediction["selection_policy"] = {
        "enabled": True,
        "max_per_market": int(params["max_per_market"]),
        "max_per_sector": int(params["max_per_sector"]),
        "max_unknown_sector": int(params["max_unknown_sector"]),
        "min_kr_count": int(params["min_kr_count"]),
        "min_us_count": int(params["min_us_count"]),
        "unknown_sector_penalty": round(float(params["unknown_sector_penalty"]), 4),
    }
    return config


def score_summary(summary: dict, total_rows: int) -> float:
    selected_rows = float(summary.get("selected_rows", 0))
    active_ratio = selected_rows / max(total_rows, 1)
    excess_return_net = float(summary.get("excess_return_net", 0.0))
    max_drawdown_net = abs(float(summary.get("max_drawdown_net", 0.0)))
    win_rate = float(summary.get("selection_win_rate_net", 0.0))
    test_periods = float(summary.get("test_periods", 0.0))

    objective = 0.0
    objective += excess_return_net * 220.0
    objective -= max_drawdown_net * 8.0
    objective += (win_rate - 0.5) * 2.5
    objective += min(active_ratio, 0.12) * 0.8
    if selected_rows <= 0:
        objective -= 5.0
    if test_periods < 10:
        objective -= 1.0
    return objective


def main() -> None:
    parser = argparse.ArgumentParser(description="주식 복합 선택 정책 임계값을 Optuna로 탐색합니다.")
    parser.add_argument("--config", required=True, help="상승 모델 설정 파일 경로")
    parser.add_argument("--risk-model", default=None, help="위험 모델 경로 override")
    parser.add_argument("--trials", type=int, default=80, help="탐색 trial 수")
    parser.add_argument("--output", default=None, help="탐색 결과 JSON 저장 경로")
    parser.add_argument("--update-config", action="store_true", help="최적 정책을 설정 파일에 반영")
    args = parser.parse_args()

    config_path = args.config
    config = load_config(config_path)
    features_path = resolve_ml_path(config_path, config["data"]["features_path"])
    model_path = resolve_ml_path(config_path, config["model"]["output_path"])
    risk_model_path = args.risk_model or config.get("prediction", {}).get("risk_model_path")
    if not risk_model_path:
        raise ValueError("정책 튜닝에는 risk 모델 경로가 필요합니다.")

    features_df = read_features_csv(features_path)
    _, valid_df = split_by_time(features_df, float(config["model"]["validation_ratio"]))
    valid_df = valid_df.copy()

    up_payload = load_model_payload(model_path)
    risk_payload = load_model_payload(resolve_ml_path(config_path, str(risk_model_path)))
    valid_df["up_probability"] = predict_with_payload(up_payload, valid_df)
    valid_df["risk_probability"] = predict_with_payload(risk_payload, valid_df)
    valid_df["up_model_version"] = up_payload["config"]["model"]["version"]
    valid_df["risk_model_version"] = risk_payload["config"]["model"]["version"]

    backtest_config = config.get("backtest", {})
    fee_bps = float(backtest_config.get("fee_bps", 0.0))
    slippage_bps = float(backtest_config.get("slippage_bps", 0.0))

    def objective(trial: optuna.Trial) -> float:
        params = {
            "long_threshold": trial.suggest_float("long_threshold", 0.16, 0.34),
            "stock_min_composite_spread": trial.suggest_float("stock_min_composite_spread", 0.15, 0.75),
            "top_n": trial.suggest_int("top_n", 1, 4),
            "min_market_breadth_5": trial.suggest_float("min_market_breadth_5", 0.35, 0.60),
            "min_sector_breadth_5": trial.suggest_float("min_sector_breadth_5", 0.30, 0.65),
            "min_sector_strength_score": trial.suggest_float("min_sector_strength_score", 0.35, 0.80),
            "min_market_regime_score": trial.suggest_int("min_market_regime_score", -1, 3),
            "max_market_news_stress_score": trial.suggest_float("max_market_news_stress_score", 0.5, 5.0),
            "max_primary_market_drawdown_60": trial.suggest_float("max_primary_market_drawdown_60", -0.25, -0.05),
            "risk_on_long_threshold_bonus": trial.suggest_float("risk_on_long_threshold_bonus", 0.0, 0.08),
            "risk_on_min_spread_bonus": trial.suggest_float("risk_on_min_spread_bonus", -0.10, 0.05),
            "risk_off_long_threshold_bonus": trial.suggest_float("risk_off_long_threshold_bonus", -0.10, 0.0),
            "risk_off_min_spread_bonus": trial.suggest_float("risk_off_min_spread_bonus", 0.0, 0.20),
            "risk_on_min_score": trial.suggest_int("risk_on_min_score", 1, 4),
            "risk_off_max_score": trial.suggest_int("risk_off_max_score", -2, 1),
            "risk_on_market_breadth_5": trial.suggest_float("risk_on_market_breadth_5", 0.45, 0.70),
            "risk_off_market_breadth_5": trial.suggest_float("risk_off_market_breadth_5", 0.30, 0.55),
            "risk_off_primary_market_drawdown_60": trial.suggest_float("risk_off_primary_market_drawdown_60", -0.20, -0.05),
            "max_per_market": trial.suggest_int("max_per_market", 1, 3),
            "max_per_sector": trial.suggest_int("max_per_sector", 1, 2),
            "max_unknown_sector": trial.suggest_int("max_unknown_sector", 0, 2),
            "min_kr_count": trial.suggest_int("min_kr_count", 0, 1),
            "min_us_count": trial.suggest_int("min_us_count", 0, 1),
            "unknown_sector_penalty": trial.suggest_float("unknown_sector_penalty", 0.0, 20.0),
        }
        tuned_config = build_policy_config(config, params)
        tuned_df = apply_stock_policy_frame(valid_df, tuned_config.get("prediction", {}))
        _, summary = build_daily_backtest(tuned_df, int(params["top_n"]), fee_bps, slippage_bps)
        objective_value = score_summary(summary, len(valid_df))
        trial.set_user_attr("summary", summary)
        return objective_value

    study = optuna.create_study(direction="maximize")
    study.optimize(objective, n_trials=args.trials)

    best_config = build_policy_config(config, study.best_params)
    result = {
        "best_value": study.best_value,
        "best_params": study.best_params,
        "best_policy": best_config.get("prediction", {}),
        "best_backtest": study.best_trial.user_attrs.get("summary", {}),
        "trials": args.trials,
    }

    if args.output:
        output_path = Path(args.output)
        if not output_path.is_absolute():
            output_path = Path.cwd() / output_path
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    if args.update_config:
        config["prediction"] = best_config["prediction"]
        config["backtest"] = best_config["backtest"]
        save_config(config_path, config)

    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
