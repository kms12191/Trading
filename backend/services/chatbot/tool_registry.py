"""
챗봇 도구 연결부입니다.
1차 구현에서는 실제 거래 함수 호출 대신 안전한 기본 응답만 제공합니다.
"""


def list_available_tools() -> list[str]:
    return [
        "get_price",
        "get_holdings",
        "create_trade_proposal",
    ]

