import ast
import re
from typing import Any


DEFAULT_ACTION = "입력값, API 키 권한, 거래소 계정 상태를 확인한 뒤 다시 시도하세요."


ERROR_GUIDES = {
    "COINONE": {
        "154": {
            "title": "코인원 API 출금주소록 등록이 필요합니다.",
            "message": "입력한 주소가 코인원 API 출금주소로 등록되어 있지 않거나 추가 정보/추가 채널 인증이 완료되지 않았습니다.",
            "action": "코인원 Open API > API 출금주소록에서 주소와 Destination Tag/Memo를 등록하고 추가 정보 등록 및 추가 채널 인증을 완료한 뒤 다시 시도하세요.",
            "severity": "warning",
        },
        "3006": {
            "title": "첫 원화 입금 후 72시간 출금 제한 중입니다.",
            "message": "코인원 보안 정책상 첫 원화 입금 후 72시간 동안 가상자산 출금이 제한됩니다.",
            "action": "코인원 앱/웹에서 출금 가능 시각을 확인하고 제한이 해제된 뒤 다시 시도하세요.",
            "severity": "warning",
        },
        "101": {
            "title": "코인원 API 키 인증에 실패했습니다.",
            "message": "코인원 Access Token이 올바르지 않거나 만료/삭제된 키일 수 있습니다.",
            "action": "설정 화면에서 코인원 Access Token과 Secret Key를 다시 저장하고 연결 테스트를 실행하세요.",
            "severity": "error",
        },
        "104": {
            "title": "코인원 API 서명 검증에 실패했습니다.",
            "message": "코인원 Secret Key가 잘못되었거나 요청 서명이 거래소 규격과 맞지 않습니다.",
            "action": "코인원 Secret Key를 다시 확인해 저장하고, 계속 실패하면 새 API 키를 발급하세요.",
            "severity": "error",
        },
        "306": {
            "title": "코인원 최소 주문금액보다 작은 주문입니다.",
            "message": "코인원이 허용하는 최소 주문금액보다 낮아 주문이 거절되었습니다.",
            "action": "주문 금액을 최소 5,000원 이상으로 조정한 뒤 다시 시도하세요. 수수료와 호가 단위 때문에 여유 있게 입력하는 것이 안전합니다.",
            "severity": "warning",
        },
    },
    "BINANCE": {
        "-4061": {
            "title": "바이낸스 선물 포지션 모드와 주문 방향이 맞지 않습니다.",
            "message": "현재 계정의 포지션 모드가 주문의 LONG/SHORT/BOTH 설정과 맞지 않아 Binance가 주문을 거절했습니다.",
            "action": "바이낸스 선물 계정이 One-way 모드라면 BOTH를 선택하세요. LONG/SHORT를 쓰려면 Binance Futures에서 Hedge Mode를 먼저 켜야 합니다.",
            "severity": "warning",
        },
        "-4059": {
            "title": "바이낸스 선물 포지션 모드 변경이 필요 없습니다.",
            "message": "요청한 포지션 모드가 이미 계정에 적용되어 있습니다.",
            "action": "현재 설정 그대로 다시 주문하세요.",
            "severity": "warning",
        },
        "-4046": {
            "title": "바이낸스 선물 마진 모드가 이미 적용되어 있습니다.",
            "message": "요청한 교차/격리 마진 모드가 이미 해당 심볼에 적용되어 있습니다.",
            "action": "마진 모드를 그대로 두고 다시 주문하세요.",
            "severity": "warning",
        },
        "-4028": {
            "title": "바이낸스 선물 레버리지 배수가 허용 범위를 벗어났습니다.",
            "message": "선택한 심볼 또는 계정에서 해당 레버리지 배수를 사용할 수 없어 Binance가 주문을 거절했습니다.",
            "action": "레버리지 배수를 낮춰 다시 시도하세요. 코인별 최대 배율은 다르며 DOGE 같은 알트코인은 75x가 제한될 수 있습니다.",
            "severity": "warning",
        },
        "-2019": {
            "title": "바이낸스 선물 증거금이 부족합니다.",
            "message": "주문에 필요한 선물 증거금이 현재 사용 가능 잔고보다 큽니다.",
            "action": "수량 또는 레버리지를 조정하거나 선물 지갑의 사용 가능 USDT를 확인하세요.",
            "severity": "warning",
        },
        "-2015": {
            "title": "바이낸스 API 키 권한을 확인해야 합니다.",
            "message": "API Key, IP 제한, 권한 설정 중 하나가 바이낸스 요청을 차단했습니다.",
            "action": "바이낸스 API 관리 화면에서 선물 거래 권한, IP 제한, Testnet/실거래 키 구분을 확인한 뒤 키를 다시 저장하세요.",
            "severity": "error",
        },
        "-2022": {
            "title": "바이낸스 Reduce Only 주문이 거절되었습니다.",
            "message": "현재 포지션과 주문 방향/수량이 Reduce Only 조건에 맞지 않습니다.",
            "action": "보유 포지션 방향과 수량을 확인하고, 신규 진입이면 Reduce Only를 끄세요.",
            "severity": "warning",
        },
        "-1111": {
            "title": "바이낸스 주문 가격 또는 수량 단위가 맞지 않습니다.",
            "message": "입력한 가격/수량의 소수점 정밀도가 해당 선물 심볼의 허용 단위와 맞지 않습니다.",
            "action": "수량과 가격 소수점 자릿수를 줄여 다시 시도하세요. DOGEUSDT는 수량을 정수 단위로 입력하는 편이 안전합니다.",
            "severity": "warning",
        },
        "-4164": {
            "title": "바이낸스 선물 최소 주문금액보다 작습니다.",
            "message": "주문 명목 금액이 Binance Futures 최소 주문 기준보다 작습니다.",
            "action": "주문 수량을 늘리거나 가격을 확인한 뒤 다시 시도하세요.",
            "severity": "warning",
        },
        "-1022": {
            "title": "바이낸스 API 서명 검증에 실패했습니다.",
            "message": "Secret Key가 다르거나 요청 서명 값이 바이낸스 규격과 맞지 않습니다.",
            "action": "바이낸스 Secret Key를 다시 확인해 저장하세요. 새 키 발급이 가장 빠를 수 있습니다.",
            "severity": "error",
        },
        "-1003": {
            "title": "바이낸스 요청 한도를 초과했습니다.",
            "message": "짧은 시간에 너무 많은 요청을 보내 바이낸스가 일시적으로 제한했습니다.",
            "action": "잠시 후 다시 시도하세요. 반복되면 자동 새로고침 주기를 늘려야 합니다.",
            "severity": "warning",
        },
    },
    "KIS": {
        "EGW00201": {
            "title": "KIS API 호출 한도를 초과했습니다.",
            "message": "한국투자증권 API가 너무 잦은 요청을 제한했습니다.",
            "action": "잠시 후 다시 시도하세요. 반복되면 시세/호가 자동 새로고침 주기를 줄여야 합니다.",
            "severity": "warning",
        },
    },
    "TOSS": {
        "401": {
            "title": "Toss 인증 토큰을 갱신해야 합니다.",
            "message": "Toss API 인증이 만료되었거나 키가 올바르지 않습니다.",
            "action": "설정 화면에서 Toss 키를 다시 연결 테스트하거나 잠시 후 재시도하세요.",
            "severity": "warning",
        },
        "ZSTD_DECODE": {
            "title": "Toss 응답 압축 해제에 실패했습니다.",
            "message": "Toss 응답의 zstd 압축을 로컬 HTTP 클라이언트가 처리하지 못했습니다.",
            "action": "서버를 재시작한 뒤 다시 시도하세요. 반복되면 Toss 요청 헤더에서 zstd 압축을 제외하도록 점검해야 합니다.",
            "severity": "warning",
        },
    },
    "SUPABASE": {
        "404": {
            "title": "DB 테이블 또는 API 경로를 찾을 수 없습니다.",
            "message": "필요한 Supabase 테이블이 아직 원격 DB에 적용되지 않았거나 REST API에 노출되지 않았습니다.",
            "action": "마이그레이션 적용 상태와 RLS/권한 설정을 확인하세요.",
            "severity": "error",
        },
    },
}


KEYWORD_GUIDES = [
    (
        "NO_MODULE",
        ["No module named", "ModuleNotFoundError"],
        {
            "title": "서버 의존성이 설치되지 않았습니다.",
            "message": "필요한 Python 패키지가 현재 실행 환경에 없습니다.",
            "action": "backend 또는 ml 환경에서 requirements 설치 상태를 확인하세요.",
            "severity": "error",
        },
    ),
    (
        "NETWORK",
        ["timeout", "timed out", "connection refused", "connection error", "max retries exceeded", "no host", "dns"],
        {
            "title": "외부 API 통신이 일시적으로 실패했습니다.",
            "message": "거래소 또는 네트워크 연결이 지연되거나 차단되었습니다.",
            "action": "잠시 후 다시 시도하세요. 반복되면 API 키/IP 제한과 서버 네트워크 상태를 확인하세요.",
            "severity": "warning",
        },
    ),
    (
        "AUTH",
        ["unauthorized", "invalid_client", "invalid access token", "invalid api-key", "401", "403"],
        {
            "title": "API 인증 정보를 확인해야 합니다.",
            "message": "API 키가 잘못되었거나 권한이 부족해 요청이 거부되었습니다.",
            "action": "설정 화면에서 해당 거래소 API 키를 다시 저장하고 연결 테스트를 실행하세요.",
            "severity": "error",
        },
    ),
    (
        "SUPABASE_REST",
        ["Supabase REST API 에러"],
        {
            "title": "DB 요청 처리에 실패했습니다.",
            "message": "Supabase 테이블 권한, RLS 정책, 마이그레이션 상태 중 하나를 확인해야 합니다.",
            "action": "테이블 생성/권한/RLS 적용 여부를 확인하세요.",
            "severity": "error",
        },
    ),
    (
        "INSUFFICIENT",
        ["insufficient", "잔고", "예수금", "available"],
        {
            "title": "주문 또는 출금 가능 잔고가 부족합니다.",
            "message": "요청 수량/금액이 현재 사용 가능한 잔고보다 큽니다.",
            "action": "수량을 줄이거나 거래소 앱에서 사용 가능 잔고를 확인하세요.",
            "severity": "warning",
        },
    ),
]


def extract_exchange_error(error: Exception | str) -> dict[str, Any]:
    """
    원문 예외 문자열에서 거래소 에러 코드와 payload를 최대한 복원합니다.
    """
    raw_message = str(error)
    code = None
    payload = None

    code_match = re.search(r"코드\s+([^)\s:]+)", raw_message)
    if code_match:
        code = code_match.group(1)

    binance_match = re.search(r"code[\"']?\s*[:=]\s*(-?\d+)", raw_message, re.IGNORECASE)
    if binance_match:
        code = binance_match.group(1)

    egw_match = re.search(r"(EGW\d+)", raw_message, re.IGNORECASE)
    if egw_match:
        code = egw_match.group(1).upper()

    dict_match = re.search(r"(\{.*\})", raw_message)
    if dict_match:
        try:
            payload = ast.literal_eval(dict_match.group(1))
            if isinstance(payload, dict):
                code = str(
                    payload.get("error_code")
                    or payload.get("errorCode")
                    or payload.get("code")
                    or payload.get("msg_cd")
                    or code
                    or ""
                )
        except Exception:
            payload = None

    return {
        "code": str(code or "").strip() or None,
        "raw_message": raw_message,
        "payload": payload if isinstance(payload, dict) else None,
    }


def infer_exchange(raw_message: str, explicit_exchange: str | None = None) -> str | None:
    if explicit_exchange:
        return explicit_exchange.upper()
    lowered = raw_message.lower()
    if "coinone" in lowered or "코인원" in raw_message:
        return "COINONE"
    if "binance" in lowered or "바이낸스" in raw_message:
        return "BINANCE"
    if "kis" in lowered or "한국투자" in raw_message or "egw" in lowered:
        return "KIS"
    if "toss" in lowered or "토스" in raw_message or "zstd" in lowered:
        return "TOSS"
    if "supabase" in lowered:
        return "SUPABASE"
    return None


def format_error_payload(
    error: Exception | str,
    context: str = "요청 처리 실패",
    exchange: str | None = None,
    default_action: str = DEFAULT_ACTION,
) -> dict[str, Any]:
    """
    프론트가 일관되게 표시할 수 있는 사용자 친화 에러 payload를 생성합니다.
    """
    extracted = extract_exchange_error(error)
    raw_message = extracted["raw_message"]
    inferred_exchange = infer_exchange(raw_message, exchange)
    code = extracted.get("code")

    if inferred_exchange == "TOSS" and "zstd" in raw_message.lower():
        code = "ZSTD_DECODE"

    guide = None
    if inferred_exchange and code:
        guide = ERROR_GUIDES.get(inferred_exchange, {}).get(str(code))

    if not guide:
        lowered = raw_message.lower()
        for keyword_code, keywords, keyword_guide in KEYWORD_GUIDES:
            if any(keyword.lower() in lowered for keyword in keywords):
                code = code or keyword_code
                guide = keyword_guide
                break

    if not guide:
        guide = {
            "title": context,
            "message": "요청을 처리하는 중 문제가 발생했습니다.",
            "action": default_action,
            "severity": "error",
        }

    return {
        "success": False,
        "message": guide["message"],
        "error": {
            "code": code,
            "exchange": inferred_exchange,
            "title": guide["title"],
            "message": guide["message"],
            "action": guide["action"],
            "severity": guide.get("severity", "error"),
            "raw_message": raw_message,
            "raw_payload": extracted.get("payload"),
        },
    }
