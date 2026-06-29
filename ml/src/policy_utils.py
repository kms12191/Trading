from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from ml.src.model_utils import apply_probability_calibration


def predict_with_payload(payload: dict[str, Any], df: pd.DataFrame) -> np.ndarray:
    model = payload["model"]
    calibrator = payload.get("calibrator")
    feature_columns = payload["config"]["model"]["feature_columns"]
    training_options = payload.get("config", {}).get("training", {})

    probabilities = model.predict_proba(df[feature_columns])[:, 1]

    ridge_model = payload.get("ridge_model")
    if training_options.get("use_ensemble") and ridge_model is not None:
        try:
            scaler = ridge_model._feature_scaler
            scaled = scaler.transform(df[feature_columns].fillna(0.0))
            ridge_probabilities = np.clip(ridge_model.predict(scaled), 0.0, 1.0)
            lgbm_weight = float(training_options.get("ensemble_lgbm_weight", 0.7))
            ridge_weight = float(training_options.get("ensemble_ridge_weight", 0.3))
            probabilities = (lgbm_weight * probabilities) + (ridge_weight * ridge_probabilities)
        except Exception:
            pass

    return apply_probability_calibration(probabilities, calibrator)


def classify_market_regime(row: pd.Series, policy: dict[str, Any]) -> str:
    market_regime_score = float(row.get("market_regime_score", 0.0) or 0.0)
    market_breadth_5 = float(row.get("market_breadth_5", 0.0) or 0.0)
    primary_market_ma_20_gap = float(row.get("primary_market_ma_20_gap", 0.0) or 0.0)
    primary_market_drawdown_60 = float(row.get("primary_market_drawdown_60", 0.0) or 0.0)

    if (
        market_regime_score <= float(policy.get("risk_off_max_score", 0.0))
        or market_breadth_5 < float(policy.get("risk_off_market_breadth_5", 0.45))
        or primary_market_drawdown_60 < float(policy.get("risk_off_primary_market_drawdown_60", -0.10))
    ):
        return "risk_off"
    if (
        market_regime_score >= float(policy.get("risk_on_min_score", 3.0))
        and market_breadth_5 >= float(policy.get("risk_on_market_breadth_5", 0.55))
        and primary_market_ma_20_gap > 0
    ):
        return "risk_on"
    return "neutral"


def _normalize_market_group(value: Any) -> str:
    text = str(value or "").upper()
    if text in {"KR", "KOREA"}:
        return "KR"
    if text in {"US", "USA", "NASDAQ", "NYSE"}:
        return "US"
    return "UNKNOWN"


def apply_selection_caps(
    ranked_df: pd.DataFrame,
    top_n: int,
    policy: dict[str, Any],
) -> pd.DataFrame:
    if ranked_df.empty or top_n <= 0:
        return ranked_df.head(0).copy()

    max_per_market = int(policy.get("max_per_market", top_n))
    max_per_sector = int(policy.get("max_per_sector", top_n))
    max_unknown_sector = int(policy.get("max_unknown_sector", top_n))
    min_kr_count = int(policy.get("min_kr_count", 0))
    min_us_count = int(policy.get("min_us_count", 0))
    unknown_sector_penalty = float(policy.get("unknown_sector_penalty", 0.0))

    working = ranked_df.copy()
    if unknown_sector_penalty > 0:
        working["score_after_penalty"] = working["signal_score"] - np.where(
            working["sector_group"].fillna("UNKNOWN").eq("UNKNOWN"),
            unknown_sector_penalty,
            0.0,
        )
    else:
        working["score_after_penalty"] = working["signal_score"]
    working = working.sort_values("score_after_penalty", ascending=False).copy()

    selected_indices: list[int] = []
    market_counts: dict[str, int] = {}
    sector_counts: dict[str, int] = {}
    unknown_sector_count = 0

    def can_take(row: pd.Series) -> bool:
        nonlocal unknown_sector_count
        market_group = _normalize_market_group(row.get("market_group"))
        sector_group = str(row.get("sector_group") or "UNKNOWN")
        if market_counts.get(market_group, 0) >= max_per_market:
            return False
        if sector_counts.get(sector_group, 0) >= max_per_sector:
            return False
        if sector_group == "UNKNOWN" and unknown_sector_count >= max_unknown_sector:
            return False
        return True

    def register(row: pd.Series) -> None:
        nonlocal unknown_sector_count
        market_group = _normalize_market_group(row.get("market_group"))
        sector_group = str(row.get("sector_group") or "UNKNOWN")
        market_counts[market_group] = market_counts.get(market_group, 0) + 1
        sector_counts[sector_group] = sector_counts.get(sector_group, 0) + 1
        if sector_group == "UNKNOWN":
            unknown_sector_count += 1

    if min_kr_count > 0:
        for _, row in working[working["market_group"].map(_normalize_market_group) == "KR"].iterrows():
            if len(selected_indices) >= top_n or market_counts.get("KR", 0) >= min_kr_count:
                break
            if can_take(row):
                selected_indices.append(row.name)
                register(row)

    if min_us_count > 0:
        for _, row in working[working["market_group"].map(_normalize_market_group) == "US"].iterrows():
            if len(selected_indices) >= top_n or market_counts.get("US", 0) >= min_us_count:
                break
            if row.name in selected_indices:
                continue
            if can_take(row):
                selected_indices.append(row.name)
                register(row)

    for _, row in working.iterrows():
        if len(selected_indices) >= top_n:
            break
        if row.name in selected_indices:
            continue
        if can_take(row):
            selected_indices.append(row.name)
            register(row)

    selected_df = working.loc[selected_indices].copy()
    return selected_df.sort_values("score_after_penalty", ascending=False).drop(columns=["score_after_penalty"], errors="ignore")


def apply_stock_policy_frame(df: pd.DataFrame, prediction_config: dict[str, Any]) -> pd.DataFrame:
    policy = dict(prediction_config.get("stock_policy", {}) or {})
    override_policy = dict(prediction_config.get("override_policy", {}) or {})
    if not policy.get("enabled", False):
        result = df.copy()
        result["composite_spread"] = result["up_probability"] - result["risk_probability"]
        result["adjusted_composite_spread"] = result["composite_spread"]
        result["effective_long_threshold"] = float(prediction_config.get("long_threshold", 0.30))
        result["effective_min_spread"] = float(prediction_config.get("stock_min_composite_spread", 0.0))
        result["market_regime_state"] = "static"
        result["policy_blocked"] = 0.0
        result["policy_block_reason"] = ""
        result["policy_penalty"] = 0.0
        result["override_applied"] = 0.0
        result["position"] = np.where(
            (result["risk_probability"] < result["effective_long_threshold"])
            & (result["adjusted_composite_spread"] >= result["effective_min_spread"]),
            "LONG",
            "HOLD",
        )
        result["signal_score"] = np.where(result["position"] == "LONG", result["composite_spread"] * 100.0, 0.0)
        return result

    result = df.copy()
    result["composite_spread"] = result["up_probability"] - result["risk_probability"]

    positions: list[str] = []
    scores: list[float] = []
    thresholds: list[float] = []
    spreads: list[float] = []
    regimes: list[str] = []
    blocked_flags: list[float] = []
    blocked_reasons: list[str] = []
    penalties: list[float] = []
    adjusted_spreads: list[float] = []
    override_applied_flags: list[float] = []

    base_long_threshold = float(prediction_config.get("long_threshold", 0.30))
    base_min_spread = float(prediction_config.get("stock_min_composite_spread", 0.0))

    for _, row in result.iterrows():
        regime = classify_market_regime(row, policy)
        effective_long_threshold = base_long_threshold
        effective_min_spread = base_min_spread

        if regime == "risk_on":
            effective_long_threshold += float(policy.get("risk_on_long_threshold_bonus", 0.0))
            effective_min_spread += float(policy.get("risk_on_min_spread_bonus", 0.0))
        elif regime == "risk_off":
            effective_long_threshold += float(policy.get("risk_off_long_threshold_bonus", -0.03))
            effective_min_spread += float(policy.get("risk_off_min_spread_bonus", 0.10))

        reason_tokens: list[str] = []
        policy_penalty = 0.0

        market_breadth_5 = float(row.get("market_breadth_5", 0.0) or 0.0)
        sector_breadth_5 = float(row.get("sector_breadth_5", 0.0) or 0.0)
        sector_strength_score = float(row.get("sector_strength_score", 0.0) or 0.0)
        market_regime_score = float(row.get("market_regime_score", 0.0) or 0.0)
        market_news_stress_score = float(row.get("market_news_stress_score", 0.0) or 0.0)
        primary_market_drawdown_60 = float(row.get("primary_market_drawdown_60", 0.0) or 0.0)

        min_market_breadth_5 = float(policy.get("min_market_breadth_5", 0.0))
        min_sector_breadth_5 = float(policy.get("min_sector_breadth_5", 0.0))
        min_sector_strength_score = float(policy.get("min_sector_strength_score", 0.0))
        min_market_regime_score = float(policy.get("min_market_regime_score", -999.0))
        max_market_news_stress_score = float(policy.get("max_market_news_stress_score", 999.0))
        max_primary_market_drawdown_60 = float(policy.get("max_primary_market_drawdown_60", -999.0))

        market_breadth_gap = max(0.0, min_market_breadth_5 - market_breadth_5)
        sector_breadth_gap = max(0.0, min_sector_breadth_5 - sector_breadth_5)
        sector_strength_gap = max(0.0, min_sector_strength_score - sector_strength_score)
        market_regime_gap = max(0.0, min_market_regime_score - market_regime_score)
        drawdown_gap = max(0.0, max_primary_market_drawdown_60 - primary_market_drawdown_60)

        if market_breadth_gap > 0:
            reason_tokens.append("market_breadth")
            policy_penalty += market_breadth_gap * float(policy.get("market_breadth_penalty_weight", 0.45))
        if sector_breadth_gap > 0:
            reason_tokens.append("sector_breadth")
            policy_penalty += sector_breadth_gap * float(policy.get("sector_breadth_penalty_weight", 0.25))
        if sector_strength_gap > 0:
            reason_tokens.append("sector_strength")
            policy_penalty += sector_strength_gap * float(policy.get("sector_strength_penalty_weight", 0.20))
        if market_regime_gap > 0:
            reason_tokens.append("market_regime")
            policy_penalty += market_regime_gap * float(policy.get("market_regime_penalty_weight", 0.08))
        if drawdown_gap > 0:
            reason_tokens.append("market_drawdown")
            policy_penalty += drawdown_gap * float(policy.get("drawdown_penalty_weight", 0.35))

        hard_block_reasons: list[str] = []
        if market_news_stress_score > float(policy.get("hard_block_market_news_stress_score", max_market_news_stress_score + 999.0)):
            hard_block_reasons.append("news_stress")
        if primary_market_drawdown_60 < float(policy.get("hard_block_primary_market_drawdown_60", -999.0)):
            hard_block_reasons.append("hard_market_drawdown")

        adjusted_spread = float(row["composite_spread"]) - policy_penalty
        policy_blocked = len(hard_block_reasons) > 0
        override_applied = False
        if policy_blocked and override_policy.get("enabled", False):
            allowed_regimes = {str(item).strip().lower() for item in override_policy.get("allowed_regimes", ["risk_on", "neutral", "risk_off"])}
            override_hard_block_reasons = {str(item).strip() for item in override_policy.get("hard_block_reasons", ["news_stress"])}
            hard_blocked = any(reason in override_hard_block_reasons for reason in reason_tokens)
            if (
                regime.lower() in allowed_regimes
                and not hard_blocked
                and float(row.get("up_probability", 0.0) or 0.0) >= float(override_policy.get("min_up_probability", 1.0))
                and float(row.get("risk_probability", 1.0) or 1.0) <= float(override_policy.get("max_risk_probability", 0.0))
                and adjusted_spread >= float(override_policy.get("min_composite_spread", 1.0))
            ):
                policy_blocked = False
                override_applied = True
                reason_tokens.append("override")

        if (not policy_blocked) and row["risk_probability"] < effective_long_threshold and adjusted_spread >= effective_min_spread:
            positions.append("LONG")
            scores.append(float(adjusted_spread * 100.0))
        else:
            positions.append("HOLD")
            scores.append(0.0)

        thresholds.append(effective_long_threshold)
        spreads.append(effective_min_spread)
        regimes.append(regime)
        blocked_flags.append(float(policy_blocked))
        penalties.append(policy_penalty)
        adjusted_spreads.append(adjusted_spread)
        blocked_reasons.append("|".join(reason_tokens + hard_block_reasons))
        override_applied_flags.append(float(override_applied))

    result["effective_long_threshold"] = thresholds
    result["effective_min_spread"] = spreads
    result["market_regime_state"] = regimes
    result["policy_blocked"] = blocked_flags
    result["policy_block_reason"] = blocked_reasons
    result["policy_penalty"] = penalties
    result["adjusted_composite_spread"] = adjusted_spreads
    result["override_applied"] = override_applied_flags
    result["position"] = positions
    result["signal_score"] = scores
    return result
