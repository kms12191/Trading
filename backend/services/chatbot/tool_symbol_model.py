import json
import re
from functools import lru_cache
from pathlib import Path


SYMBOL_QUERY_ALIASES = {
    "삼전": "삼성전자",
    "삼성": "삼성전자",
    "하닉": "SK하이닉스",
    "하이닉스": "SK하이닉스",
    "네이버": "035420",
    "NAVER": "035420",
    "카카오": "035720",
    "엔씨": "036570",
    "엔씨소프트": "036570",
    "카카오뱅크": "323410",
    "카뱅": "323410",
    "카카오페이": "377300",
    "카페이": "377300",
    "현대건설": "000720",
    "현대건설우": "000725",
    "현대그린푸드": "453340",
    "두산에너빌리티": "034020",
    "두산에너": "034020",
    "삼성전기": "009150",
    "삼바": "207940",
    "삼성바이오로직스": "207940",
    "엘지에너지솔루션": "373220",
    "LG에너지솔루션": "373220",
    "엘지엔솔": "373220",
    "LG엔솔": "373220",
    "엘지화학": "051910",
    "LG화학": "051910",
    "포스코홀딩스": "005490",
    "POSCO홀딩스": "005490",
    "셀트리온": "068270",
    "GST": "083450",
    "지에스티": "083450",
    "쥐에스티": "083450",
    "기아": "000270",
    "현대차": "005380",
    "현대자동차": "005380",
    "애플": "AAPL",
    "마이크로소프트": "MSFT",
    "마소": "MSFT",
    "엔비디아": "NVDA",
    "엔비": "NVDA",
    "엔비디아주식": "NVDA",
    "아마존": "AMZN",
    "구글": "GOOGL",
    "알파벳": "GOOGL",
    "메타": "META",
    "테슬라": "TSLA",
    "브로드컴": "AVGO",
    "넷플릭스": "NFLX",
    "코스트코": "COST",
    "오라클": "ORCL",
    "어도비": "ADBE",
    "레딧": "RDDT",
    "REDDIT": "RDDT",
    "퀄컴": "QCOM",
    "인텔": "INTC",
    "팔란티어": "PLTR",
    "우버": "UBER",
    "큐큐큐": "QQQ",
    "인베스코QQQ": "QQQ",
    "인베스코큐큐큐": "QQQ",
    "나스닥100": "QQQ",
    "에스피와이": "SPY",
    "스파이": "SPY",
    "S&P500": "SPY",
    "에스앤피500": "SPY",
    "브이오오": "VOO",
    "뱅가드S&P500": "VOO",
    "슈드": "SCHD",
    "찰스슈왑배당": "SCHD",
    "티큐큐": "TQQQ",
    "에스큐큐큐": "SQQQ",
    "비트": "BTC",
    "비트코인": "BTC",
    "이더": "ETH",
    "이더리움": "ETH",
    "리플": "XRP",
    "엑스알피": "XRP",
    "도지": "DOGE",
    "도지코인": "DOGE",
    "테더": "USDT",
    "솔라나": "SOL",
    "에이다": "ADA",
    "트론": "TRX",
    "수이": "SUI",
    "체인링크": "LINK",
    "폴리곤": "POL",
    "아발란체": "AVAX",
    "바이낸스코인": "BNB",
    "비앤비": "BNB",
}

SYMBOL_COMMAND_PATTERN = re.compile(
    r"(관심\s*종목|관심종목|설정해줘|추가해줘|등록해줘|보여줘|조회해줘|알려줘|"
    r"거래내역|거래\s*내역|주문내역|주문\s*내역|뉴스|공시|시세|환율|"
    r"설정|추가|등록|해제|삭제|조회|검색)"
)

KOREAN_MONEY_NUMBER_PATTERN = re.compile(
    r"[일한이삼사오육칠팔구십백천만]+\s*(?:만원|천원|원|만)"
)

SYMBOL_QUERY_NAME_PRESERVE_ALIASES = {"삼성전기"}


class SymbolDisambiguationError(ValueError):
    """종목명이 여러 후보로 해석될 때 챗봇 선택 버튼 생성을 위해 사용합니다."""

    def __init__(self, query: str, candidates: list[dict]):
        super().__init__("종목 후보가 여러 개입니다.")
        self.query = query
        self.candidates = candidates


@lru_cache(maxsize=1)
def load_training_universe_symbols() -> set[str]:
    universe_path = Path(__file__).resolve().parents[3] / "ml" / "data" / "reference" / "training_universes.json"
    try:
        payload = json.loads(universe_path.read_text(encoding="utf-8"))
    except Exception:
        return set()

    symbols: set[str] = set()
    for values in payload.values() if isinstance(payload, dict) else []:
        if not isinstance(values, list):
            continue
        for value in values:
            symbol = str(value or "").strip().upper()
            if symbol:
                symbols.add(symbol)
    return symbols


def normalize_symbol_candidate(candidate: str) -> str:
    symbol = str(candidate or "").strip()
    if not symbol:
        return ""

    # 1. 조사 제거 전 원본으로 별칭(Alias) 룩업
    alias = SYMBOL_QUERY_ALIASES.get(symbol) or SYMBOL_QUERY_ALIASES.get(symbol.upper())
    if alias:
        return alias

    # 2. 조사 제거 전 원본으로 학습 유니버스(Training Universe) 매칭
    upper_symbol = symbol.upper()
    training_symbols = load_training_universe_symbols()
    if upper_symbol in training_symbols:
        if upper_symbol.endswith("USDT") and len(upper_symbol) > 4:
            return upper_symbol[:-4]
        return upper_symbol

    # 3. 매칭 실패 시에만 한국어 조사(의|은|는|이|가|을|를) 제거
    stripped_symbol = re.sub(r"(의|은|는|이|가|을|를)$", "", symbol).strip()
    if not stripped_symbol:
        return symbol

    # 4. 조사 제거된 텍스트로 별칭 룩업
    alias = SYMBOL_QUERY_ALIASES.get(stripped_symbol) or SYMBOL_QUERY_ALIASES.get(stripped_symbol.upper())
    if alias:
        return alias

    # 5. 조사 제거된 텍스트로 학습 유니버스 매칭
    upper_stripped = stripped_symbol.upper()
    if upper_stripped in training_symbols:
        if upper_stripped.endswith("USDT") and len(upper_stripped) > 4:
            return upper_stripped[:-4]
        return upper_stripped

    # 6. 최종 실패 시 조사 제거된 텍스트 반환
    return stripped_symbol



def normalize_symbol_alias(candidate: str) -> str:
    """사용자 입력 종목 별칭을 lookup/search 전에 표준 검색어로 정규화합니다."""
    return normalize_symbol_candidate(candidate)


def normalize_symbol_result(row: dict) -> dict:
    symbol = str(row.get("symbol") or "").strip().upper()
    display_name = str(row.get("display_name") or row.get("name") or symbol).strip()
    asset_type = str(row.get("asset_type") or "STOCK").strip().upper()
    market = str(row.get("market") or row.get("market_country") or "").strip().upper()
    return {
        **row,
        "symbol": symbol,
        "display_name": display_name or symbol,
        "asset_type": asset_type,
        "market": market,
    }


def asset_route(candidate: dict) -> str:
    asset_type = str(candidate.get("asset_type") or "STOCK").upper()
    symbol = str(candidate.get("symbol") or "").upper()
    return f"/asset/{asset_type}/{symbol}"


def build_symbol_choice_response(query: str, candidates: list[dict]) -> dict:
    display_query = str(query or "").strip() or "입력한 종목"
    lines = ["어떤 종목을 말하나요?"]
    for index, candidate in enumerate(candidates[:5], start=1):
        symbol = candidate.get("symbol")
        display_name = candidate.get("display_name") or symbol
        market = candidate.get("market") or candidate.get("asset_type") or ""
        market_text = f" / {market}" if market else ""
        lines.append(f"{index}. {display_name}({symbol}){market_text}")

    actions = [
        {
            "type": "navigate",
            "label": f"{candidate.get('display_name') or candidate.get('symbol')}({candidate.get('symbol')}) 조회",
            "to": asset_route(candidate),
        }
        for candidate in candidates[:5]
        if candidate.get("symbol")
    ]
    return {
        "reply": "\n".join(lines),
        "actions": actions,
        "data": {
            "source": "SYMBOL_DISAMBIGUATION",
            "query": display_query,
            "candidates": candidates[:5],
        },
    }


def extract_symbol_query(text: str) -> str:
    cleaned = SYMBOL_COMMAND_PATTERN.sub(" ", text)
    cleaned = re.sub(r"\d+(?:\.\d+)?\s*(만원|천원|원|만)", " ", cleaned)
    cleaned = KOREAN_MONEY_NUMBER_PATTERN.sub(" ", cleaned)
    cleaned = re.sub(r"(?<![가-힣])만원\s*(이상|이하|초과|미만|넘는|넘어|부터)?", " ", cleaned)
    cleaned = re.sub(r"(이상|이하|초과|미만|넘는|넘어|부터|전체|최근|상태|매수|매도|취소|미체결주문|미체결내역|미체결|체결|완료|실패|조회|검색|확인|내|나의|내가|내역|목록|전망|분석|어때|오를까|괜찮아|살까|해외주식|미국주식|국내주식|해외|미국|국내|주식|주가)", " ", cleaned)
    cleaned = re.sub(r"(?<=\S)(의|은|는|이|가|을|를)$", " ", cleaned)
    cleaned = re.sub(r"[^0-9A-Za-z가-힣._-]+", " ", cleaned)
    candidates = [part.strip() for part in cleaned.split() if part.strip()]
    if not candidates:
        return ""
    candidate = candidates[0]
    if candidate in SYMBOL_QUERY_NAME_PRESERVE_ALIASES:
        return candidate
    return normalize_symbol_alias(candidate)
