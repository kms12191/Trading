from enum import StrEnum


class RiskLevel(StrEnum):
    """챗봇 도구가 사용자 자산에 미치는 위험 단계입니다."""

    READ = "READ"
    WRITE = "WRITE"
    PROPOSAL = "PROPOSAL"
    ORDER = "ORDER"


class SafetyGuardError(ValueError):
    """승인 절차 없이 실행할 수 없는 도구를 차단합니다."""


_TOOL_RISK_LEVELS = {
    "get_home_market_rankings": RiskLevel.READ,
    "get_portfolio_summary": RiskLevel.READ,
    "get_holdings": RiskLevel.READ,
    "search_trade_history": RiskLevel.READ,
    "list_open_orders": RiskLevel.READ,
    "get_market_calendar": RiskLevel.READ,
    "get_exchange_rate": RiskLevel.READ,
    "get_asset_price": RiskLevel.READ,
    "get_asset_orderbook": RiskLevel.READ,
    "get_asset_candles": RiskLevel.READ,
    "search_web": RiskLevel.READ,
    "get_asset_outlook": RiskLevel.READ,
    "add_watchlist_item": RiskLevel.WRITE,
    "remove_watchlist_item": RiskLevel.WRITE,
    "create_trade_proposal": RiskLevel.PROPOSAL,
    "place_order": RiskLevel.ORDER,
    "approve_trade_proposal": RiskLevel.ORDER,
}


def assess_tool_risk(tool_name: str) -> RiskLevel:
    """도구 이름을 읽기/쓰기/제안/주문 위험 등급으로 분류합니다."""
    return _TOOL_RISK_LEVELS.get(str(tool_name or "").strip(), RiskLevel.READ)


def enforce_tool_safety(tool_name: str, arguments: dict | None = None) -> RiskLevel:
    """실제 도구 실행 전에 주문 도구가 우회 실행되지 않는지 확인합니다."""
    risk_level = assess_tool_risk(tool_name)
    if risk_level == RiskLevel.ORDER:
        raise SafetyGuardError(
            "주문 실행은 챗봇 도구에서 직접 수행할 수 없습니다. 승인 카드에서 명시적으로 승인해 주세요."
        )
    return risk_level


def is_trade_execution_allowed_without_approval() -> bool:
    """챗봇은 사용자 승인 없이 주문을 실행할 수 없습니다."""
    return False


def build_safety_notice() -> str:
    return "실제 주문은 사용자 승인과 서버 검증을 거친 뒤에만 실행됩니다."
