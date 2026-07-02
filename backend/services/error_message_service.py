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
        "-1003": {
            "title": "바이낸스 요청 한도를 초과했습니다.",
            "message": "짧은 시간에 너무 많은 요청을 보내 바이낸스가 일시적으로 제한했습니다.",
            "action": "잠시 후 다시 시도하세요. 반복되면 차트/잔고/주문 상태 자동 새로고침 주기를 줄여야 합니다.",
            "severity": "warning",
        },
        "-1007": {
            "title": "바이낸스 주문 응답이 지연되었습니다.",
            "message": "바이낸스 서버 응답 시간이 초과되어 주문 처리 결과가 즉시 확인되지 않았습니다.",
            "action": "같은 주문을 바로 다시 보내지 말고 거래내역 또는 바이낸스 앱에서 체결 여부를 먼저 확인하세요.",
            "severity": "warning",
        },
        "-1013": {
            "title": "바이낸스 주문 필터 조건을 통과하지 못했습니다.",
            "message": "최소 주문금액, 가격 단위, 수량 단위, 허용 가격 범위 중 하나가 바이낸스 심볼 규칙과 맞지 않습니다.",
            "action": "주문 수량과 가격을 현재 호가 기준으로 다시 입력하세요. 반복되면 해당 심볼의 최소 주문금액과 수량 단위를 확인해야 합니다.",
            "severity": "warning",
        },
        "-1015": {
            "title": "바이낸스 신규 주문 한도를 초과했습니다.",
            "message": "짧은 시간에 신규 주문을 너무 많이 제출해 바이낸스가 주문을 제한했습니다.",
            "action": "열린 주문을 정리하고 잠시 후 다시 시도하세요. 자동 주문/상태 동기화 주기도 함께 점검해야 합니다.",
            "severity": "warning",
        },
        "-1021": {
            "title": "바이낸스 요청 시간이 서버 시간과 맞지 않습니다.",
            "message": "로컬 서버 시간과 바이낸스 서버 시간 차이가 커서 서명 요청이 거절되었습니다.",
            "action": "서버 시간을 자동 동기화한 뒤 다시 시도하세요. 로컬 개발 환경이면 시스템 시간 설정을 확인하세요.",
            "severity": "warning",
        },
        "-1022": {
            "title": "바이낸스 API 서명 검증에 실패했습니다.",
            "message": "Secret Key가 다르거나 요청 서명 값이 바이낸스 규격과 맞지 않습니다.",
            "action": "바이낸스 Secret Key를 다시 확인해 저장하세요. 새 키 발급이 가장 빠를 수 있습니다.",
            "severity": "error",
        },
        "-1102": {
            "title": "바이낸스 주문 필수값이 누락되었거나 형식이 맞지 않습니다.",
            "message": "주문에 필요한 심볼, 방향, 수량, 가격, 포지션 옵션 중 일부가 비어 있거나 잘못된 형식입니다.",
            "action": "주문 폼을 새로고침한 뒤 심볼, 주문 유형, 수량, 가격, 선물 옵션을 다시 확인하세요.",
            "severity": "warning",
        },
        "-1111": {
            "title": "바이낸스 주문 가격 또는 수량 단위가 맞지 않습니다.",
            "message": "입력한 가격/수량의 소수점 정밀도가 해당 심볼의 허용 단위와 맞지 않습니다.",
            "action": "수량과 가격 소수점 자릿수를 줄여 다시 시도하세요. 알트코인은 수량 단위가 심볼마다 다를 수 있습니다.",
            "severity": "warning",
        },
        "-1116": {
            "title": "바이낸스 주문 유형이 올바르지 않습니다.",
            "message": "선택한 주문 유형이 해당 거래소 또는 심볼에서 지원되지 않습니다.",
            "action": "지정가 또는 시장가처럼 지원되는 주문 유형으로 다시 선택하세요.",
            "severity": "warning",
        },
        "-1117": {
            "title": "바이낸스 주문 방향이 올바르지 않습니다.",
            "message": "BUY/SELL 주문 방향 값이 바이낸스 규격과 맞지 않습니다.",
            "action": "매수 또는 매도 탭을 다시 선택한 뒤 주문을 재시도하세요.",
            "severity": "warning",
        },
        "-1121": {
            "title": "바이낸스에서 지원하지 않는 심볼입니다.",
            "message": "입력한 종목 코드가 바이낸스 현물/선물 시장에 없거나 현재 거래 가능한 상태가 아닙니다.",
            "action": "DOGEUSDT처럼 바이낸스에서 실제 거래되는 심볼인지 확인하고, 현물/선물 시장 구분도 다시 선택하세요.",
            "severity": "warning",
        },
        "-2010": {
            "title": "바이낸스 주문이 거래소에서 거절되었습니다.",
            "message": "거래소 매칭 엔진이 주문을 거절했습니다. 보통 잔고, 최소 주문금액, 가격 범위, 계정 상태 중 하나가 원인입니다.",
            "action": "주문 수량/가격/잔고를 확인하고, 바이낸스 앱에서 해당 계정의 거래 제한 여부를 확인하세요.",
            "severity": "warning",
        },
        "-2011": {
            "title": "바이낸스 주문 취소에 실패했습니다.",
            "message": "취소하려는 주문이 이미 체결/취소되었거나 거래소에서 찾을 수 없습니다.",
            "action": "거래내역을 새로고침해 현재 주문 상태를 다시 확인하세요.",
            "severity": "warning",
        },
        "-2013": {
            "title": "바이낸스 주문을 찾을 수 없습니다.",
            "message": "조회하려는 주문 번호가 존재하지 않거나 이미 정리된 주문입니다.",
            "action": "거래내역을 다시 동기화한 뒤 주문 ID가 올바른지 확인하세요.",
            "severity": "warning",
        },
        "-2014": {
            "title": "바이낸스 API 키 형식이 올바르지 않습니다.",
            "message": "저장된 API Key 형식이 바이낸스가 요구하는 형식과 맞지 않습니다.",
            "action": "설정 화면에서 바이낸스 API Key와 Secret Key를 다시 저장하세요.",
            "severity": "error",
        },
        "-2015": {
            "title": "바이낸스 API 키 권한을 확인해야 합니다.",
            "message": "API Key, IP 제한, 권한 설정 중 하나가 바이낸스 요청을 차단했습니다.",
            "action": "바이낸스 API 관리 화면에서 현물/선물 거래 권한, IP 제한, Testnet/실거래 키 구분을 확인한 뒤 키를 다시 저장하세요.",
            "severity": "error",
        },
        "-2018": {
            "title": "바이낸스 잔고가 부족합니다.",
            "message": "주문 또는 포지션 변경에 필요한 사용 가능 잔고가 부족합니다.",
            "action": "주문 수량을 줄이거나 바이낸스 지갑의 사용 가능 잔고를 확인하세요.",
            "severity": "warning",
        },
        "-2019": {
            "title": "바이낸스 선물 증거금이 부족합니다.",
            "message": "주문에 필요한 선물 증거금이 현재 사용 가능 잔고보다 큽니다.",
            "action": "수량을 줄이거나 레버리지/마진 모드를 조정하고, 선물 지갑의 사용 가능 USDT를 확인하세요.",
            "severity": "warning",
        },
        "-2021": {
            "title": "바이낸스 조건 주문이 즉시 발동될 가격입니다.",
            "message": "입력한 스탑/트리거 가격이 현재가와 맞지 않아 주문이 즉시 실행될 수 있는 상태입니다.",
            "action": "현재가를 기준으로 트리거 가격을 다시 설정하세요.",
            "severity": "warning",
        },
        "-2022": {
            "title": "바이낸스 Reduce Only 주문이 거절되었습니다.",
            "message": "현재 포지션과 주문 방향/수량이 Reduce Only 조건에 맞지 않거나 기존 열린 주문과 충돌합니다.",
            "action": "보유 포지션 방향과 수량을 확인하고, 신규 진입이면 Reduce Only를 끄세요. 기존 청산 주문이 있으면 먼저 취소해야 할 수 있습니다.",
            "severity": "warning",
        },
        "-2024": {
            "title": "바이낸스 선물 포지션 수량이 부족합니다.",
            "message": "줄이거나 청산하려는 수량이 현재 보유 포지션보다 큽니다.",
            "action": "현재 포지션 수량을 새로고침한 뒤 청산 수량을 보유 수량 이하로 조정하세요.",
            "severity": "warning",
        },
        "-2025": {
            "title": "바이낸스 열린 주문 한도를 초과했습니다.",
            "message": "해당 계정 또는 심볼의 미체결 주문 개수가 허용 한도에 도달했습니다.",
            "action": "미체결 주문을 일부 취소한 뒤 다시 주문하세요.",
            "severity": "warning",
        },
        "-2027": {
            "title": "현재 레버리지에서 허용되는 최대 포지션 한도를 초과했습니다.",
            "message": "주문 후 예상 포지션 명목금액이 현재 레버리지 단계에서 바이낸스가 허용하는 최대 한도보다 큽니다.",
            "action": "주문 수량을 줄이거나 기존 포지션을 일부 줄이세요. 높은 레버리지일수록 허용 포지션 한도가 작아질 수 있으므로 레버리지를 낮춘 뒤 다시 사전검증하는 것도 방법입니다.",
            "severity": "warning",
        },
        "-2028": {
            "title": "바이낸스 선물 레버리지 설정에 필요한 증거금이 부족합니다.",
            "message": "요청한 레버리지/포지션 조합을 유지하기에 사용 가능 증거금이 부족합니다.",
            "action": "주문 수량을 줄이거나 선물 지갑 잔고를 늘린 뒤 다시 시도하세요.",
            "severity": "warning",
        },
        "-4003": {
            "title": "바이낸스 주문 수량은 0보다 커야 합니다.",
            "message": "주문 수량이 0 이하로 전달되어 거래소가 거절했습니다.",
            "action": "수량을 다시 입력한 뒤 주문하세요.",
            "severity": "warning",
        },
        "-4004": {
            "title": "바이낸스 최소 주문 수량보다 작습니다.",
            "message": "입력한 수량이 해당 선물 심볼의 최소 수량보다 작습니다.",
            "action": "수량을 늘리거나 심볼의 최소 주문 수량을 확인하세요.",
            "severity": "warning",
        },
        "-4005": {
            "title": "바이낸스 최대 주문 수량을 초과했습니다.",
            "message": "입력한 수량이 해당 선물 심볼의 단일 주문 최대 수량보다 큽니다.",
            "action": "주문 수량을 줄이거나 여러 주문으로 나누세요. 단, 포지션 한도와 레버리지 한도도 함께 확인해야 합니다.",
            "severity": "warning",
        },
        "-4013": {
            "title": "바이낸스 최소 주문 가격보다 낮습니다.",
            "message": "입력한 지정가가 해당 심볼의 허용 최소 가격보다 낮습니다.",
            "action": "현재 호가와 가격 단위를 확인해 주문 가격을 다시 입력하세요.",
            "severity": "warning",
        },
        "-4014": {
            "title": "바이낸스 주문 가격 단위가 맞지 않습니다.",
            "message": "입력한 가격이 해당 심볼의 틱 사이즈 단위와 맞지 않습니다.",
            "action": "가격 소수점 자릿수를 호가 단위에 맞게 조정하세요.",
            "severity": "warning",
        },
        "-4016": {
            "title": "바이낸스 허용 가격 상단을 초과했습니다.",
            "message": "입력한 주문 가격이 현재 기준가 대비 허용 상단보다 높습니다.",
            "action": "현재가에 더 가까운 가격으로 다시 주문하세요.",
            "severity": "warning",
        },
        "-4023": {
            "title": "바이낸스 주문 수량 단위가 맞지 않습니다.",
            "message": "입력한 수량이 해당 심볼의 step size 단위와 맞지 않습니다.",
            "action": "수량 소수점 자릿수 또는 정수 단위를 심볼 규칙에 맞춰 조정하세요.",
            "severity": "warning",
        },
        "-4024": {
            "title": "바이낸스 허용 가격 하단보다 낮습니다.",
            "message": "입력한 주문 가격이 현재 기준가 대비 허용 하단보다 낮습니다.",
            "action": "현재가에 더 가까운 가격으로 다시 주문하세요.",
            "severity": "warning",
        },
        "-4028": {
            "title": "바이낸스 선물 레버리지 배수가 허용 범위를 벗어났습니다.",
            "message": "선택한 심볼 또는 계정에서 해당 레버리지 배수를 사용할 수 없어 Binance가 주문을 거절했습니다.",
            "action": "레버리지 배수를 낮춰 다시 시도하세요. 코인별 최대 배율은 다르며 알트코인은 높은 배율이 제한될 수 있습니다.",
            "severity": "warning",
        },
        "-4046": {
            "title": "바이낸스 선물 마진 모드가 이미 적용되어 있습니다.",
            "message": "요청한 교차/격리 마진 모드가 이미 해당 심볼에 적용되어 있습니다.",
            "action": "마진 모드를 그대로 두고 다시 주문하세요.",
            "severity": "warning",
        },
        "-4047": {
            "title": "미체결 주문이 있어 마진 모드를 바꿀 수 없습니다.",
            "message": "해당 심볼에 열린 주문이 남아 있어 바이낸스가 교차/격리 마진 모드 변경을 거절했습니다.",
            "action": "해당 심볼의 미체결 주문을 취소한 뒤 마진 모드를 변경하거나, 현재 마진 모드 그대로 주문하세요.",
            "severity": "warning",
        },
        "-4048": {
            "title": "보유 포지션이 있어 마진 모드를 바꿀 수 없습니다.",
            "message": "해당 심볼에 보유 포지션이 남아 있어 바이낸스가 교차/격리 마진 모드 변경을 거절했습니다.",
            "action": "포지션을 먼저 정리한 뒤 마진 모드를 변경하거나, 현재 적용된 마진 모드 그대로 주문하세요.",
            "severity": "warning",
        },
        "-4050": {
            "title": "바이낸스 교차 마진 잔고가 부족합니다.",
            "message": "교차 마진 주문 또는 설정 변경에 필요한 잔고가 부족합니다.",
            "action": "수량을 줄이거나 선물 지갑 잔고를 확인하세요.",
            "severity": "warning",
        },
        "-4051": {
            "title": "바이낸스 격리 마진 잔고가 부족합니다.",
            "message": "격리 마진 주문 또는 설정 변경에 필요한 잔고가 부족합니다.",
            "action": "수량을 줄이거나 해당 심볼의 격리 마진 잔고를 확인하세요.",
            "severity": "warning",
        },
        "-4059": {
            "title": "바이낸스 선물 포지션 모드 변경이 필요 없습니다.",
            "message": "요청한 포지션 모드가 이미 계정에 적용되어 있습니다.",
            "action": "현재 설정 그대로 다시 주문하세요.",
            "severity": "warning",
        },
        "-4060": {
            "title": "바이낸스 선물 포지션 방향 값이 올바르지 않습니다.",
            "message": "positionSide 값이 바이낸스가 허용하는 BOTH, LONG, SHORT 중 하나로 전달되지 않았습니다.",
            "action": "포지션 방향을 다시 선택한 뒤 주문하세요.",
            "severity": "warning",
        },
        "-4061": {
            "title": "바이낸스 선물 포지션 모드와 주문 방향이 맞지 않습니다.",
            "message": "현재 계정의 포지션 모드가 주문의 LONG/SHORT/BOTH 설정과 맞지 않아 Binance가 주문을 거절했습니다.",
            "action": "바이낸스 선물 계정이 One-way 모드라면 BOTH를 선택하세요. LONG/SHORT를 쓰려면 Binance Futures에서 Hedge Mode를 먼저 켜야 합니다.",
            "severity": "warning",
        },
        "-4164": {
            "title": "바이낸스 선물 최소 주문금액보다 작습니다.",
            "message": "주문 명목 금액이 Binance Futures 최소 주문 기준보다 작습니다.",
            "action": "주문 수량을 늘리거나 가격을 확인한 뒤 다시 시도하세요.",
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


def normalize_exchange_key(exchange: str | None) -> str | None:
    """
    내부 거래소 식별자를 사용자 친화 에러 가이드의 상위 브로커 키로 정규화합니다.
    """
    if not exchange:
        return None
    normalized = exchange.upper()
    if "BINANCE" in normalized:
        return "BINANCE"
    if "COINONE" in normalized:
        return "COINONE"
    if "TOSS" in normalized:
        return "TOSS"
    if "KIS" in normalized or "한국투자" in normalized:
        return "KIS"
    if "SUPABASE" in normalized:
        return "SUPABASE"
    return normalized


def infer_exchange(raw_message: str, explicit_exchange: str | None = None) -> str | None:
    if explicit_exchange:
        return normalize_exchange_key(explicit_exchange)
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
