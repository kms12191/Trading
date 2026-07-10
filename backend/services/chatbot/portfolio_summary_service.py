import math


DEFAULT_KRW_EXCHANGE_RATE = 1500.0
SUPPORTED_CURRENCIES = {"KRW", "USD", "USDT"}


def _to_float(value) -> float:
    try:
        parsed = float(value or 0)
    except (TypeError, ValueError):
        return 0.0
    return parsed if math.isfinite(parsed) else 0.0


def _first_present(source: dict, *keys: str):
    for key in keys:
        if key in source and source[key] is not None:
            return source[key]
    return None


def _currency_factor(currency: str, exchange_rate: float) -> float:
    if currency == "KRW":
        return 1.0
    if currency in {"USD", "USDT"}:
        return exchange_rate
    return 0.0


def normalize_account_summary(exchange: str, env: str, balance: dict) -> dict:
    """거래소별 잔고를 평가액·현금의 원화 환산 구조로 정규화합니다."""
    source = balance if isinstance(balance, dict) else {}
    currency = str(
        source.get("currency")
        or source.get("available_cash_currency")
        or "KRW"
    ).upper()
    available_cash_currency = str(
        source.get("available_cash_currency") or currency
    ).upper()
    cash_details = source.get("available_cash_details") or {}
    exchange_rate = (
        _to_float(source.get("exchange_rate"))
        or _to_float(cash_details.get("exchange_rate"))
    )
    if exchange_rate <= 0:
        exchange_rate = DEFAULT_KRW_EXCHANGE_RATE
    total_evaluation = _to_float(
        _first_present(
            source,
            "total_evaluation",
            "total_asset",
            "total_balance",
        )
    )
    available_cash = _to_float(
        _first_present(source, "available_cash", "cash", "krw_balance")
    )
    holdings = source.get("holdings")
    warning_parts = []
    if source.get("warning"):
        warning_parts.append(str(source["warning"]))
    unsupported_currencies = {
        value
        for value in (currency, available_cash_currency)
        if value not in SUPPORTED_CURRENCIES
    }
    if unsupported_currencies:
        warning_parts.append(
            "지원하지 않는 통화: " + ", ".join(sorted(unsupported_currencies))
        )

    return {
        "exchange": str(exchange or "").upper(),
        "env": str(env or "").upper(),
        "currency": currency,
        "available_cash_currency": available_cash_currency,
        "exchange_rate": exchange_rate,
        "total_evaluation": total_evaluation,
        "available_cash": available_cash,
        "total_evaluation_krw": total_evaluation
        * _currency_factor(currency, exchange_rate),
        "available_cash_krw": available_cash
        * _currency_factor(available_cash_currency, exchange_rate),
        "holdings": holdings if isinstance(holdings, list) else [],
        "warning": " ".join(warning_parts) or None,
    }


def build_portfolio_totals(accounts: list[dict]) -> dict[str, dict]:
    """REAL과 MOCK 계좌를 섞지 않고 환경별 원화 합계를 계산합니다."""
    totals = {
        "REAL": {
            "total_evaluation_krw": 0.0,
            "available_cash_krw": 0.0,
            "account_count": 0,
        },
        "MOCK": {
            "total_evaluation_krw": 0.0,
            "available_cash_krw": 0.0,
            "account_count": 0,
        },
    }
    for account in accounts or []:
        if not isinstance(account, dict):
            continue
        env = str(account.get("env") or "").upper()
        if env not in totals:
            continue
        totals[env]["total_evaluation_krw"] += _to_float(
            account.get("total_evaluation_krw")
        )
        totals[env]["available_cash_krw"] += _to_float(
            account.get("available_cash_krw")
        )
        totals[env]["account_count"] += 1
    return totals


def format_portfolio_reply(
    totals_by_env: dict,
    accounts: list[dict],
    errors: list[str],
) -> str:
    """보유종목 전체 목록 없이 환경별 평가자산·현금 합계를 표시합니다."""
    labels = {"REAL": "실거래", "MOCK": "모의계좌"}
    lines = []
    for env in ("REAL", "MOCK"):
        total = (totals_by_env or {}).get(env) or {}
        account_count = int(_to_float(total.get("account_count")))
        if account_count <= 0:
            continue
        evaluation = _to_float(total.get("total_evaluation_krw"))
        cash = _to_float(total.get("available_cash_krw"))
        lines.append(
            f"{labels[env]} 평가자산 합계: {evaluation:,.0f}원 "
            f"({account_count}개 계좌)"
        )
        lines.append(f"{labels[env]} 주문가능 현금 합계: {cash:,.0f}원")

    if not accounts:
        lines.append(
            "조회 가능한 계좌가 없습니다. 설정의 API 키와 계좌 환경을 확인해 주세요."
        )
    if errors:
        lines.append("조회 실패: " + ", ".join(str(error) for error in errors[:3]))
    return "\n".join(lines)
