from backend.services.ml_model_service import build_active_signal_payload


Scalar = str | int | float | None


PREDICTIVE_OUTLOOK_KEYWORDS = (
    "오를까",
    "내릴까",
    "상승",
    "하락",
    "살까",
    "사도",
    "매수",
    "매도",
    "진입",
)


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
    reply = "\n".join(
        [
            f"{display_name}({symbol})은 ML 활성 예측 기준으로 이렇게 봅니다.",
            f"- 방향: {_format_position(prediction.get('position'))} / 등급: {prediction.get('signal_grade') or '-'}",
            f"- 상승 확률: {_format_probability(prediction.get('up_probability'))}",
            f"- 위험 확률: {_format_probability(prediction.get('risk_probability'))}",
            f"- 신호 점수: {_format_number(prediction.get('signal_score'))}",
            "",
            _decision_line(prediction),
            "단, 이 결과는 매매 실행 지시가 아니라 모델 기반 참고 신호입니다. 실제 매수는 가격, 거래량, 뉴스/공시, 손절 기준을 같이 확인한 뒤 판단하세요.",
        ]
    )
    return {
        "reply": reply,
        "data": {
            "source": "ML_ACTIVE_SIGNAL",
            "mode": "single_asset_outlook",
            "asset_key": asset_key,
            "symbol": symbol,
            "display_name": display_name,
            "model_version": payload.get("model_version"),
            "items": [prediction],
            "performance": payload.get("performance") or {},
        },
    }


def _asset_key_for_symbol(symbol_data: dict) -> str:
    asset_type = str(symbol_data.get("asset_type") or "").upper()
    market = str(symbol_data.get("market") or "").upper()
    symbol = str(symbol_data.get("symbol") or "").upper()
    if asset_type == "CRYPTO":
        return "crypto"
    if market == "US" or any(char.isalpha() for char in symbol):
        return "us_stock"
    return "kr_stock"


def _missing_prediction_result(
    asset_key: str,
    symbol: str,
    display_name: str,
    payload: dict | None = None,
) -> dict:
    return {
        "reply": (
            f"{display_name}({symbol})의 활성 ML 예측 결과를 아직 찾지 못했습니다.\n"
            "로컬에는 예측 파일이 없어도, 배포 환경에 serving 모델과 predictions CSV가 있으면 이 질문은 ML 신호로 답변됩니다.\n"
            "지금은 매수/매도 판단을 단정하지 말고 뉴스·공시·가격 흐름을 같이 확인해 주세요."
        ),
        "data": {
            "source": "ML_ACTIVE_SIGNAL",
            "mode": "single_asset_outlook",
            "asset_key": asset_key,
            "symbol": symbol,
            "display_name": display_name,
            "items": [],
            "reason": "missing_active_predictions",
            "model_version": (payload or {}).get("model_version"),
            "performance": (payload or {}).get("performance") or {},
        },
    }


def _decision_line(prediction: dict) -> str:
    grade = str(prediction.get("signal_grade") or "").upper()
    risk = _to_float(prediction.get("risk_probability"))
    score = _to_float(prediction.get("signal_score"))
    if grade == "RISKY" or (risk is not None and risk >= 0.65):
        return "결론: 위험 신호가 강해서 바로 진입보다는 관망 또는 비중 축소 관점이 더 안전합니다."
    if score is not None and score >= 10:
        return "결론: 모델상 관심 후보로 볼 수 있지만, 바로 추격 매수보다는 분할 접근 여부를 확인하는 쪽이 안전합니다."
    return "결론: 모델 신호가 강하지 않아 바로 매수 판단은 어렵고, 추가 확인이 필요합니다."


def _format_position(value: Scalar) -> str:
    position = str(value or "").upper()
    labels = {"LONG": "상승 우위", "HOLD": "중립", "SHORT": "하락/위험 우위"}
    return labels.get(position, position or "-")


def _format_probability(value: Scalar) -> str:
    number = _to_float(value)
    if number is None:
        return "-"
    return f"{number * 100:.1f}%"


def _format_number(value: Scalar) -> str:
    number = _to_float(value)
    if number is None:
        return "-"
    return f"{number:.2f}"


def _to_float(value: Scalar) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
