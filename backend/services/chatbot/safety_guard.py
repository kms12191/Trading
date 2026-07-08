def is_trade_execution_allowed_without_approval() -> bool:
    """챗봇은 사용자 승인 없이 주문을 실행할 수 없습니다."""
    return False


def build_safety_notice() -> str:
    return "실제 주문은 사용자 승인과 서버 검증을 거친 뒤에만 실행됩니다."

