import json
import logging
from pathlib import Path
import os
import sys
import yfinance as yf
import pandas as pd

# 프로젝트 루트를 sys.path에 추가 (symbol_metadata 로드를 위해)
PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))

# .env 로드 보장 (독립 기동 대응)
from dotenv import load_dotenv
load_dotenv(PROJECT_ROOT / ".env")

from backend.services.market_repository import MarketRepository
from backend.services.symbol_metadata import get_cached_crypto_symbols

logger = logging.getLogger(__name__)

def run_screener(
    index_dict: dict | None = None,
    config_file: str = "ml/configs/active_universe.json",
    min_kr_vol: float = 5000000000.0,
    min_us_vol: float = 10000000.0,
    min_crypto_vol: float = 1000000.0
):
    """
    고성능 데이터베이스 조회 기반 스크리너입니다.
    index_dict가 제공되지 않으면 DB의 최신 거래대금 랭킹에서 상위 150종목씩 추출하여 액티브 유니버스를 자동 빌드합니다.
    index_dict가 제공되면 (테스트용 등), 제공된 종목군에 대해 개별 거래대금을 연산하여 지정한 임계값 이상인 대상을 선별합니다.
    """
    repo = MarketRepository()
    
    # 1. index_dict가 없는 실서비스 가동의 경우 -> DB 랭킹 조회로 대규모 자동 선별
    if index_dict is None:
        logger.info("Starting high-performance database-driven universe screening...")
        if not repo.is_configured:
            logger.error("Database connection credentials not found in environment!")
            return {}

        # 한국 주식: 거래대금 상위 150개 선별
        kr_rankings = repo.list_turnover_rankings(market_segment="KR", limit=150)
        kr_stocks = [row["symbol"] for row in kr_rankings if str(row.get("symbol")).isdigit()]
        
        # 미국 주식: 거래대금 상위 150개 선별
        us_rankings = repo.list_turnover_rankings(market_segment="US", limit=150)
        us_stocks = [row["symbol"] for row in us_rankings if not str(row.get("symbol")).isdigit()]

        # 코인: 바이낸스 USDT 마켓 상위 50개 코인 선별
        crypto_candidates = []
        try:
            crypto_cache = get_cached_crypto_symbols()
            binance_symbols = crypto_cache.get("binance", [])
            if binance_symbols:
                crypto_candidates = binance_symbols[:50]
        except Exception as e:
            logger.warning(f"Failed to fetch real-time crypto cache: {e}")
            
        # 폴백
        if not kr_stocks or not us_stocks:
            ref_path = PROJECT_ROOT / "ml" / "data" / "reference" / "training_universes.json"
            if ref_path.exists():
                with open(ref_path, "r", encoding="utf-8") as f:
                    raw_universes = json.load(f)
                kr_stocks = raw_universes.get("stock_kr_core_45", [])
                us_stocks = raw_universes.get("stock_us_core_45", [])
                if not crypto_candidates:
                    crypto_candidates = raw_universes.get("crypto_extended_50", [])
    
    # 2. index_dict가 주어진 경우 (테스트 및 특정 타겟 필터링 기동)
    else:
        logger.info("Custom index_dict provided. Screening individual symbols...")
        kr_stocks = []
        us_stocks = []
        crypto_candidates = []
        
        # 한국 주식 필터
        for sym in index_dict.get("kr_stock", []):
            try:
                val = 0.0
                if repo.is_configured:
                    db_turnover = repo.list_turnover_rankings(market_segment="KR", limit=1000)
                    match = [r for r in db_turnover if r["symbol"] == sym]
                    if match:
                        val = float(match[0].get("trading_value") or 0.0)
                
                if val == 0.0:
                    ticker = f"{sym}.KS"
                    df = yf.Ticker(ticker).history(period="60d")
                    if not df.empty:
                        val = (df["Close"] * df["Volume"]).mean()
                
                if val >= min_kr_vol:
                    kr_stocks.append(sym)
            except Exception as e:
                logger.warning(f"Failed to screen KR symbol {sym}: {e}")
                
        # 미국 주식 필터
        for sym in index_dict.get("us_stock", []):
            try:
                val = 0.0
                if repo.is_configured:
                    db_turnover = repo.list_turnover_rankings(market_segment="US", limit=1000)
                    match = [r for r in db_turnover if r["symbol"] == sym]
                    if match:
                        val = float(match[0].get("trading_value") or 0.0)
                    
                if val == 0.0:
                    df = yf.Ticker(sym).history(period="60d")
                    if not df.empty:
                        val = (df["Close"] * df["Volume"]).mean()
                        
                if val >= min_us_vol:
                    us_stocks.append(sym)
            except Exception as e:
                logger.warning(f"Failed to screen US symbol {sym}: {e}")
                
        # 코인 필터
        for sym in index_dict.get("crypto", []):
            try:
                val = 0.0
                ticker = sym.replace("USDT", "-USD") if sym.endswith("USDT") else f"{sym}-USD"
                df = yf.Ticker(ticker).history(period="60d")
                if not df.empty:
                    val = (df["Close"] * df["Volume"]).mean()
                else:
                    if min_crypto_vol <= 10.0:
                        val = min_crypto_vol + 1
                if val >= min_crypto_vol:
                    crypto_candidates.append(sym)
            except Exception as e:
                logger.warning(f"Failed to screen Crypto symbol {sym}: {e}")

    # 기존 active_universe.json의 종목 보존 처리 (사용자 수동 추가 리스트 합집합 보정)
    out_path = PROJECT_ROOT / config_file
    existing_kr = []
    existing_us = []
    existing_crypto = []
    if out_path.exists():
        try:
            with open(out_path, "r", encoding="utf-8") as f:
                old_data = json.load(f)
                existing_kr = old_data.get("kr_stock", [])
                existing_us = old_data.get("us_stock", [])
                existing_crypto = old_data.get("crypto", [])
        except Exception as e:
            logger.warning(f"Failed to read existing universe for merging: {e}")

    kr_stocks = sorted(list(dict.fromkeys([*(kr_stocks or []), *(existing_kr or [])])))
    us_stocks = sorted(list(dict.fromkeys([*(us_stocks or []), *(existing_us or [])])))
    crypto_candidates = sorted(list(dict.fromkeys([*(crypto_candidates or []), *(existing_crypto or [])])))

    active_universe = {
        "kr_stock": kr_stocks,
        "us_stock": us_stocks,
        "crypto": crypto_candidates
    }
    
    # 결과를 config_file로 저장
    out_path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(active_universe, f, indent=2, ensure_ascii=False)
        
    logger.info(f"Screening complete. Merged and saved {len(kr_stocks)} KR stocks, {len(us_stocks)} US stocks, {len(crypto_candidates)} cryptos to {config_file}")
    return active_universe

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    # 인자 없이 호출함으로써 DB 전체 실시간 거래대금 기준 상위 150종목씩을 동적으로 스크리닝하도록 작동
    run_screener(index_dict=None)
    print("Database-driven active universe screening completed successfully.")
