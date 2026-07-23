# -*- coding: utf-8 -*-
import threading
import time
import requests
import logging
from pathlib import Path

# 로거 초기화
logger = logging.getLogger(__name__)

# 동적 캐시로 사용될 종목 메타데이터 사전
# DB의 kis_stock_master 테이블에서 display_name, sector가 입력된 국내/해외 주식을 읽어와 동적으로 구성합니다.
SYMBOL_METADATA = {}

# 주요 코인 한글명 매핑 사전 (바이낸스 매핑 보완용 및 폴백용)
COIN_DISPLAY_NAMES = {
    "BTC": "비트코인",
    "ETH": "이더리움",
    "XRP": "리플",
    "SOL": "솔라나",
    "USDT": "테더",
    "USDC": "USD코인",
    "DOGE": "도지코인",
    "ADA": "에이다",
    "TRX": "트론",
    "AVAX": "아발란체",
    "DOT": "폴카닷",
    "LINK": "체인링크",
    "BCH": "비트코인캐시",
    "NEAR": "니어프로토콜",
    "APT": "앱토스",
    "TON": "톤",
    "ETC": "이더리움클래식",
    "HBAR": "헤더라",
    "ATOM": "코스모스",
    "ARB": "아비트럼",
    "OP": "옵티미즘",
    "INJ": "인젝티브",
    "SEI": "세이",
    "PEPE": "페페",
    "SHIB": "시바이누",
    "FIL": "파일코인",
    "MKR": "메이커",
    "AAVE": "에이브",
    "UNI": "유니스왑",
    "CRV": "커브",
    "TIA": "셀레스티아",
    "WIF": "도그위햇",
    "BONK": "봉크",
    "JUP": "주피터",
    "PYTH": "피스네트워크",
    "ENA": "에나",
    "RENDER": "렌더토큰",
    "FET": "인공지능수퍼얼라이언스",
    "RUNE": "토르체인",
    "GRT": "더그래프",
    "ALGO": "알고랜드",
    "SAND": "샌드박스",
    "MANA": "디센트럴랜드",
    "EOS": "이오스",
    "KAS": "카스파",
    "ICP": "인터넷컴퓨터",
    "IMX": "이뮤터블엑스",
    "SUI": "수이",
    "WLD": "월드코인",
    "STRK": "스타크넷",
    "ONDO": "온도파이낸스",
    "FLOKI": "플로키",
    "TAO": "비텐서",
    "BLUR": "블러",
    "POL": "폴리곤",
    "PENDLE": "펜들",
    "SGR": "슈가",
}


# 가상자산 목록 전역 캐시
_crypto_cache = {"coinone": [], "binance": [], "last_updated": 0.0}
_crypto_cache_lock = threading.Lock()
CRYPTO_CACHE_TTL = 3600 * 24  # 24시간 캐시 유지


def load_symbol_metadata_from_db():
    """
    Supabase DB의 kis_stock_master 테이블에서 display_name 또는 sector가 존재하거나
    해외주식(market_country = 'US')인 종목들을 조회해 SYMBOL_METADATA 전역 딕셔너리를 캐싱합니다.
    """
    global SYMBOL_METADATA
    try:
        # 독립 실행 스크립트에서도 환경 변수를 안전하게 로드할 수 있도록 보정
        from dotenv import load_dotenv
        env_path = Path(__file__).resolve().parent.parent / ".env"
        load_dotenv(env_path)

        from backend.services.supabase_client import safe_query_supabase_as_service_role
        
        offset = 0
        limit = 1000
        new_metadata = {}
        
        while True:
            records = safe_query_supabase_as_service_role(
                "kis_stock_master",
                "GET",
                params={
                    "or": "(display_name.not.is.null,sector.not.is.null,market_country.eq.US)",
                    "limit": limit,
                    "offset": offset
                }
            )
            if not records:
                break
                
            for row in records:
                symbol = str(row.get("symbol", "")).upper()
                if not symbol:
                    continue
                new_metadata[symbol] = {
                    "display_name": row.get("display_name") or row.get("name") or symbol,
                    "asset_type": row.get("asset_type", "STOCK"),
                    "market": row.get("market_country") or "KR",
                    "sector": row.get("sector") or "",
                }
                
            if len(records) < limit:
                break
            offset += limit
            
        if new_metadata:
            SYMBOL_METADATA.clear()
            SYMBOL_METADATA.update(new_metadata)
            logger.info(f"[SymbolMetadata] Successfully loaded {len(SYMBOL_METADATA)} curated stock symbols from DB.")
    except Exception as e:
        logger.error(f"[SymbolMetadata] Warning: Failed to load symbol metadata from DB: {e}")


# 모듈 임포트 시점에 DB 데이터를 캐싱
load_symbol_metadata_from_db()


def refresh_crypto_symbols_cache():
    """
    코인원 및 바이낸스의 실시간 상장 코인 목록을 긁어와 전역 캐시를 동기화합니다.
    """
    global _crypto_cache
    
    # 1. 코인원 상장 코인 목록 획득
    coinone_symbols = []
    try:
        res = requests.get("https://api.coinone.co.kr/public/v2/currencies", timeout=8)
        if res.status_code == 200:
            data = res.json()
            currencies = data.get("currencies", [])
            for c in currencies:
                sym = str(c.get("symbol", "")).upper()
                if sym:
                    coinone_symbols.append(sym)
    except Exception:
        pass

    # 2. 바이낸스 USDT 상장 코인 목록 획득
    binance_symbols = []
    try:
        res = requests.get("https://api.binance.com/api/v3/ticker/price", timeout=8)
        if res.status_code == 200:
            data = res.json()
            # USDT 마켓만 필터링
            for item in data:
                sym = str(item.get("symbol", "")).upper()
                if sym.endswith("USDT"):
                    binance_symbols.append(sym)
    except Exception:
        pass

    # 캐시 갱신
    with _crypto_cache_lock:
        _crypto_cache["coinone"] = coinone_symbols or _crypto_cache["coinone"]
        _crypto_cache["binance"] = binance_symbols or _crypto_cache["binance"]
        _crypto_cache["last_updated"] = time.time()


def get_cached_crypto_symbols() -> dict:
    """
    메모리에 캐시된 가상자산 심볼 리스트를 반환합니다. TTL(24시간) 만료 시 자동 백그라운드 갱신을 실행합니다.
    """
    now = time.time()
    if now - _crypto_cache["last_updated"] > CRYPTO_CACHE_TTL or (not _crypto_cache["coinone"] and not _crypto_cache["binance"]):
        # 최초 기동 시점 또는 캐시 만료 시 동기 갱신
        refresh_crypto_symbols_cache()
    return _crypto_cache


def normalize_crypto_base_symbol(symbol: str | None) -> str:
    """
    거래소별 마켓 심볼(BTCUSDT, KRW-BTC 등)을 사용자 기준 기본 심볼(BTC)로 정규화합니다.
    """
    normalized = str(symbol or "").strip().upper().replace("_", "-").replace("/", "-")
    if not normalized:
        return ""
    parts = [part for part in normalized.split("-") if part]
    if len(parts) == 2:
        if parts[0] in {"KRW", "USDT", "BUSD", "USDC"}:
            return parts[1]
        if parts[1] in {"KRW", "USDT", "BUSD", "USDC"}:
            return parts[0]
    for suffix in ("USDT", "BUSD", "USDC", "KRW"):
        if normalized.endswith(suffix) and len(normalized) > len(suffix):
            return normalized[:-len(suffix)]
    return normalized


def search_crypto_symbols(query: str, limit: int = 10) -> list[dict]:
    """
    검색어(query)를 기반으로 코인원/바이낸스 상장 코인을 기본 심볼 단위로 병합 검색합니다.
    """
    query = str(query or "").strip().upper()
    try:
        from backend.services.crypto_asset_service import search_crypto_assets

        db_results = search_crypto_assets(query, limit=limit)
        if db_results:
            return db_results
    except Exception:
        logger.warning("[SymbolMetadata] crypto_assets 검색 실패, 실시간 캐시로 폴백합니다.", exc_info=True)

    cache = get_cached_crypto_symbols()
    merged = {}

    def ensure_entry(base_symbol: str) -> dict:
        if base_symbol not in merged:
            merged[base_symbol] = {
                "symbol": base_symbol,
                "display_name": COIN_DISPLAY_NAMES.get(base_symbol, base_symbol),
                "asset_type": "CRYPTO",
                "market": "",
                "markets": [],
                "exchanges": [],
                "aliases": [base_symbol],
            }
        return merged[base_symbol]

    def append_unique(values: list, value: str):
        if value and value not in values:
            values.append(value)

    def matches(base_symbol: str, market_symbol: str, korean_name: str) -> bool:
        return query in base_symbol or query in market_symbol or bool(korean_name and query in korean_name.upper())

    # 1. 코인원 검색
    for sym in cache["coinone"]:
        base_sym = normalize_crypto_base_symbol(sym)
        korean_name = COIN_DISPLAY_NAMES.get(base_sym, "")
        if base_sym and matches(base_sym, sym, korean_name):
            entry = ensure_entry(base_sym)
            append_unique(entry["markets"], "KRW")
            append_unique(entry["exchanges"], "COINONE")
            append_unique(entry["aliases"], sym)
            append_unique(entry["aliases"], f"KRW-{base_sym}")
            append_unique(entry["aliases"], f"{base_sym}KRW")

    # 2. 바이낸스 검색
    for sym in cache["binance"]:
        base_sym = normalize_crypto_base_symbol(sym)
        korean_name = COIN_DISPLAY_NAMES.get(base_sym, "")
        if base_sym and matches(base_sym, sym, korean_name):
            entry = ensure_entry(base_sym)
            append_unique(entry["markets"], "USDT")
            append_unique(entry["exchanges"], "BINANCE")
            append_unique(entry["aliases"], sym)

    results = list(merged.values())
    for entry in results:
        entry["market"] = " · ".join(entry["markets"]) if entry["markets"] else ""

    results.sort(key=lambda item: (0 if item["symbol"] == query else 1, len(item["symbol"]), item["symbol"]))

    return results[:limit]


def enrich_symbol(row: dict) -> dict:
    """
    조회된 단일 종목 행(dict)에 display_name 및 sector를 결합(enrich)합니다.
    """
    symbol = str(row.get("symbol", "")).upper()
    
    # 만약 메모리 캐시가 준비되지 않았을 경우 1회 동적 복구 시도
    if not SYMBOL_METADATA:
        load_symbol_metadata_from_db()
        
    metadata = SYMBOL_METADATA.get(symbol)
    
    if metadata:
        return {
            **row,
            "display_name": metadata.get("display_name", symbol),
            "market": metadata.get("market") or row.get("market_country") or row.get("currency") or "",
            "sector": metadata.get("sector", ""),
        }
        
    # 하드코딩 사전에 없을 경우 동적 코인 한글명 매핑 보완 (바이낸스/코인원 대비)
    base_symbol = symbol[:-4] if symbol.endswith("USDT") else symbol
    korean_name = COIN_DISPLAY_NAMES.get(base_symbol)
    
    if korean_name:
        return {
            **row,
            "display_name": korean_name,
            "market": row.get("market_country") or row.get("currency") or ("USDT" if symbol.endswith("USDT") else ""),
            "sector": "가상자산",
        }

    return {
        **row,
        "display_name": symbol,
        "market": row.get("market_country") or row.get("currency") or "",
        "sector": "",
    }
