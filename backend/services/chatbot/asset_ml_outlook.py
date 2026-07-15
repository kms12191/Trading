from backend.services.ml_model_service import build_active_signal_payload


Scalar = str | int | float | None


PREDICTIVE_OUTLOOK_KEYWORDS = (
    "\uc624\ub97c\uae4c",
    "\ub0b4\ub9b4\uae4c",
    "\uc0c1\uc2b9",
    "\ud558\ub77d",
    "\uc0b4\uae4c",
    "\ud314\uae4c",
    "\ub9e4\uc218",
    "\ub9e4\ub3c4",
    "\uc9c4\uc785",
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
            f"{display_name}({symbol}) \uc9c8\ubb38\uc740 ML \ud65c\uc131 \uc2e0\ud638 \uae30\uc900\uc73c\ub85c \ubcf4\uba74 \ub2e4\uc74c\uacfc \uac19\uc2b5\ub2c8\ub2e4.",
            f"- \ubc29\ud5a5: {_format_position(prediction.get('position'))} / \ub4f1\uae09: {prediction.get('signal_grade') or '-'}",
            f"- \uc0c1\uc2b9 \ud655\ub960: {_format_probability(prediction.get('up_probability'))}",
            f"- \uc704\ud5d8 \ud655\ub960: {_format_probability(prediction.get('risk_probability'))}",
            f"- \uc2e0\ud638 \uc810\uc218: {_format_number(prediction.get('signal_score'))}",
            f"- \ubaa8\ub378: {prediction.get('model_version') or '-'}",
            "",
            "\ubaa8\ub378 \uae30\ubc18 \ucc38\uace0 \uc2e0\ud638\uc774\uba70, \ubc14\ub85c \ub9e4\uc218/\ub9e4\ub3c4\ub97c \ub2e8\uc815\ud558\ub294 \ub2f5\uc774 \uc544\ub2d9\ub2c8\ub2e4.",
            "\uc8fc\uc758: \uc774 \uac12\uc740 \ub9e4\ub9e4 \uc2e4\ud589 \uc2e0\ud638\uac00 \uc544\ub2c8\ub77c \ucc38\uace0\uc6a9 \uc608\uce21\uc785\ub2c8\ub2e4. "
            "\ub274\uc2a4, \uacf5\uc2dc, \uac00\uaca9/\uac70\ub798\ub7c9, \ubcf4\uc720 \ube44\uc911\uc744 \ud568\uaed8 \ud655\uc778\ud55c \ub4a4 \ud310\ub2e8\ud574\uc57c \ud569\ub2c8\ub2e4.",
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
            f"{display_name}({symbol}) \uc885\ubaa9\uc758 \ud65c\uc131 ML \uc608\uce21 \uacb0\uacfc\ub97c \uc544\uc9c1 \ucc3e\uc9c0 \ubabb\ud588\uc2b5\ub2c8\ub2e4.",
            "\ubc30\ud3ec \ud658\uacbd\uc5d0\ub294 \ubaa8\ub378/\uc608\uce21 \ud14c\uc774\ube14\uc774 \uc900\ube44\ub418\uc5b4 \uc788\uc744 \uc218 \uc788\uc9c0\ub9cc, "
            "\ud604\uc7ac \uc2e4\ud589 \ud658\uacbd\uc5d0\uc11c\ub294 \ud574\ub2f9 \uc885\ubaa9\uc758 \ucd5c\uc2e0 \uc608\uce21\uac12\uc774 \uc5c6\uc2b5\ub2c8\ub2e4.",
            "\ud655\uc778 \ud544\uc694: ML \uc2a4\ucf00\uc904\ub7ec \uc2e4\ud589 \uc5ec\ubd80, active prediction \uc800\uc7a5 \uc5ec\ubd80, "
            "\ubaa8\ub378 \ub808\uc9c0\uc2a4\ud2b8\ub9ac \uc0c1\ud0dc\ub97c \ud655\uc778\ud574 \uc8fc\uc138\uc694.",
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
        "BUY": "\ub9e4\uc218 \ud6c4\ubcf4",
        "LONG": "\ub9e4\uc218 \ud6c4\ubcf4",
        "SELL": "\ub9e4\ub3c4 \uc8fc\uc758",
        "SHORT": "\ub9e4\ub3c4 \uc8fc\uc758",
        "HOLD": "\ubcf4\uc720",
        "NEUTRAL": "\uc911\ub9bd",
        "WATCH": "\uad00\ub9dd",
    }
    return mapping.get(normalized, str(value or "\uc54c \uc218 \uc5c6\uc74c"))


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
