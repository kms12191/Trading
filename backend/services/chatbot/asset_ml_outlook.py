from backend.services.ml_model_service import build_active_signal_payload


Scalar = str | int | float | None


PREDICTIVE_OUTLOOK_KEYWORDS = (
    "오를까",
    "올라",
    "내릴까",
    "전망",
    "상승",
    "하락",
    "살까",
    "팔까",
    "매수",
    "매도",
    "진입",
)

# 내부 정책 사유 코드 → 일반 언어 변환
_POLICY_REASON_KOR = {
    "market_breadth": "시장 전체 상승 종목이 부족합니다",
    "sector_breadth": "이 업종의 흐름이 약합니다",
    "sector_strength": "업종 전반이 힘을 잃고 있습니다",
    "market_regime": "현재 시장은 보수적 대응이 필요합니다",
    "market_drawdown": "시장 전반에 낙폭 부담이 있습니다",
    "hard_market_drawdown": "시장 급락 구간으로 진입을 차단합니다",
    "news_stress": "부정적 뉴스 신호가 감지됩니다",
    # 한글 레이블이 그대로 올 경우
    "시장 폭 부족": "시장 전체 상승 종목이 부족합니다",
    "섹터 폭 부족": "이 업종의 흐름이 약합니다",
    "섹터 강도 부족": "업종 전반이 힘을 잃고 있습니다",
    "시장 국면 보수적": "현재 시장은 보수적 대응이 필요합니다",
    "시장 낙폭 부담": "시장 전반에 낙폭 부담이 있습니다",
    "시장 급락 차단": "시장 급락 구간으로 진입을 차단합니다",
    "뉴스 스트레스": "부정적 뉴스 신호가 감지됩니다",
}

# 내부 등급 코드 → 한글
_GRADE_KOR = {
    "STRONG_BUY_CANDIDATE": "강력 매수 후보",
    "BUY_CANDIDATE": "매수 후보",
    "HOLD": "관망",
    "WATCH": "관망",
    "RISKY": "위험 주의",
    "NEUTRAL": "중립",
}


def is_predictive_outlook_question(text: str) -> bool:
    value = str(text or "")
    return any(keyword in value for keyword in PREDICTIVE_OUTLOOK_KEYWORDS)


def build_single_asset_ml_outlook(
    auth_header: str,
    message: str,
    symbol_data: dict,
) -> dict | None:
    if not is_predictive_outlook_question(message):
        return None

    symbol = str(symbol_data.get("symbol") or "").upper().strip()
    if not symbol:
        return None

    asset_key = _asset_key_for_symbol(symbol_data)
    payload = build_active_signal_payload(
        asset_key=asset_key,
        auth_header=auth_header,
        symbols=[symbol],
        limit=1,
    )
    display_name = str(symbol_data.get("display_name") or symbol).strip()
    if not payload:
        return _missing_prediction_result(asset_key, symbol, display_name)

    rows = payload.get("predictions") if isinstance(payload.get("predictions"), list) else []
    if not rows:
        return _missing_prediction_result(asset_key, symbol, display_name, payload)

    prediction = rows[0]

    # ── 응답 구성 ───────────────────────────────────────────
    position_label = _format_position(prediction.get("position"))
    grade_label = _format_grade(prediction.get("signal_grade"))
    up_pct = _format_probability(prediction.get("up_probability"))
    risk_pct = _format_probability(prediction.get("risk_probability"))

    reply_lines = [
        f"{display_name}({symbol}) 종목의 ML 참고 신호입니다.",
        "",
        f"▶ 판단: {position_label} ({grade_label})",
        f"  상승 가능성 {up_pct}  ·  하락 위험 {risk_pct}",
    ]

    # 모델이 생성한 요약 문장
    reason_summary = str(prediction.get("reason_summary") or "").strip()
    if reason_summary:
        reply_lines += ["", reason_summary]

    # 관망·주의 이유 (일반 언어)
    block_labels = prediction.get("policy_block_reason_labels")
    if not isinstance(block_labels, list) or not block_labels:
        raw = str(prediction.get("policy_block_reason") or "").strip()
        if raw:
            block_labels = [r.strip() for r in raw.split("|") if r.strip()]
    if block_labels:
        reply_lines += ["", "현재 관망을 권고하는 이유:"]
        for label in block_labels[:4]:
            plain = _POLICY_REASON_KOR.get(label, label)
            reply_lines.append(f"  • {plain}")

    # 시장 국면
    regime = str(prediction.get("market_regime_state") or "").strip()
    if regime:
        regime_kor = "보수적 관망" if regime == "risk_off" else regime
        reply_lines += ["", f"시장 국면: {regime_kor}"]

    reply_lines += [
        "",
        "이 신호는 참고용 예측이며 매매 실행 근거가 아닙니다.",
        "뉴스·공시·보유 비중 등을 함께 확인 후 최종 판단하세요.",
    ]

    return {
        "reply": "\n".join(reply_lines),
        "actions": [],
        "data": {
            "source": "ML_ACTIVE_SIGNAL",
            "mode": "single_asset_outlook",
            "asset_key": asset_key,
            "symbol": symbol,
            "display_name": display_name,
            "model_version": prediction.get("model_version") or payload.get("model_version"),
            "prediction": prediction,
        },
    }


def _missing_prediction_result(
    asset_key: str,
    symbol: str,
    display_name: str,
    payload: dict | None = None,
) -> dict:
    reply = "\n".join(
        [
            f"{display_name}({symbol}) 종목은 현재 ML 예측 데이터가 없어 오를지 내릴지 판단하기 어렵습니다.",
            "현재 기준으로는 매수/매도 판단을 단정할 수 없습니다.",
            "모델 예측 데이터가 준비된 뒤 다시 확인해 주세요.",
        ]
    )
    return {
        "reply": reply,
        "actions": [],
        "data": {
            "source": "ML_ACTIVE_SIGNAL",
            "mode": "single_asset_outlook",
            "asset_key": asset_key,
            "symbol": symbol,
            "display_name": display_name,
            "reason": "missing_active_predictions",
            "raw_payload": payload or {},
        },
    }


def _asset_key_for_symbol(symbol_data: dict) -> str:
    asset_type = str(symbol_data.get("asset_type") or "").upper()
    exchange = str(symbol_data.get("exchange") or "").upper()
    symbol = str(symbol_data.get("symbol") or "").upper()
    if asset_type == "CRYPTO" or exchange in {"COINONE", "BINANCE", "UPBIT"}:
        return "crypto"
    if asset_type in {"STOCK_US", "US_STOCK"} or symbol.isalpha():
        return "us_stock"
    if asset_type in {"STOCK_KR", "KR_STOCK"} or symbol.isdigit():
        return "kr_stock"
    return "stock"


def _format_position(value: Scalar) -> str:
    normalized = str(value or "").strip().upper()
    mapping = {
        "BUY": "매수 후보",
        "LONG": "매수 후보",
        "SELL": "매도 주의",
        "SHORT": "매도 주의",
        "HOLD": "관망",
        "NEUTRAL": "중립",
        "WATCH": "관망",
    }
    return mapping.get(normalized, str(value or "알 수 없음"))


def _format_grade(value: Scalar) -> str:
    return _GRADE_KOR.get(str(value or "").strip().upper(), str(value or "-"))


def _format_probability(value: Scalar) -> str:
    number = _to_float(value)
    if number is None:
        return "-"
    if number <= 1:
        number *= 100
    return f"{number:.1f}%"


def _format_number(value: Scalar) -> str:
    number = _to_float(value)
    if number is None:
        return "-"
    return f"{number:.3f}"


def _to_float(value: Scalar) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
