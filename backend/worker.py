import os
import sys
import time
from pathlib import Path
from dotenv import load_dotenv

# backend/.env를 백엔드 표준 환경 파일로 사용합니다.
BACKEND_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BACKEND_DIR.parent
load_dotenv(BACKEND_DIR / ".env")

# backend 디렉토리가 파이썬 경로에 포함되도록 설정
sys.path.append(str(PROJECT_ROOT))

from backend.utils.crypto_helper import CryptoHelper
from backend.services.news_repository import NewsRepository
from backend.services.news_ingest import NewsIngestService
from backend.services.kis_market_universe import KISMarketUniverseService
from backend.services.market_index_repository import MarketIndexRepository
from backend.services.market_index_scheduler import start_market_index_scheduler
from backend.services.market_snapshot_scheduler import start_market_snapshot_scheduler
from backend.services.ml_scheduler import start_news_ingest_scheduler, start_ml_automation_scheduler
from backend.services.portfolio_snapshot_scheduler import start_portfolio_snapshot_scheduler

def main():
    print("[Worker] 백그라운드 스케줄러 배치 프로세스를 시작합니다...")
    
    ENCRYPTION_KEY = os.getenv("ENCRYPTION_KEY", "default-dev-encryption-key-32bytes!")
    SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
    
    KIS_APPKEY = os.getenv("KIS_APPKEY", "") or os.getenv("KIS_APP_KEY", "")
    KIS_APPSECRET = os.getenv("KIS_APPSECRET", "") or os.getenv("KIS_APP_SECRET", "")
    KIS_CANO = os.getenv("KIS_CANO", "")
    KIS_ACNT_PRDT_CD = os.getenv("KIS_ACNT_PRDT_CD", "01")
    KIS_ENV = os.getenv("KIS_ENV", "MOCK")
    
    NEWS_INGEST_ENABLED = os.getenv("NEWS_INGEST_ENABLED", "false").lower() == "true"
    NEWS_INGEST_INTERVAL_SECONDS = int(os.getenv("NEWS_INGEST_INTERVAL_SECONDS", "600"))
    ML_AUTOMATION_ENABLED = os.getenv("ML_AUTOMATION_ENABLED", "true").lower() == "true"
    HOME_MARKET_SNAPSHOT_ENABLED = os.getenv("HOME_MARKET_SNAPSHOT_ENABLED", "true").lower() == "true"
    HOME_MARKET_OPEN_INTERVAL_SECONDS = int(os.getenv("HOME_MARKET_OPEN_INTERVAL_SECONDS", "60"))
    HOME_MARKET_CLOSED_INTERVAL_SECONDS = int(os.getenv("HOME_MARKET_CLOSED_INTERVAL_SECONDS", "600"))
    HOME_MARKET_SNAPSHOT_LIMIT = int(os.getenv("HOME_MARKET_SNAPSHOT_LIMIT", "300"))
    HOME_MARKET_SNAPSHOT_WORKERS = int(os.getenv("HOME_MARKET_SNAPSHOT_WORKERS", "2"))
    MARKET_INDEX_SNAPSHOT_ENABLED = os.getenv("MARKET_INDEX_SNAPSHOT_ENABLED", "true").lower() == "true"
    MARKET_INDEX_OPEN_INTERVAL_SECONDS = int(os.getenv("MARKET_INDEX_OPEN_INTERVAL_SECONDS", "60"))
    MARKET_INDEX_CLOSED_INTERVAL_SECONDS = int(os.getenv("MARKET_INDEX_CLOSED_INTERVAL_SECONDS", "600"))
    PORTFOLIO_SNAPSHOT_ENABLED = os.getenv("PORTFOLIO_SNAPSHOT_ENABLED", "true").lower() == "true"
    PORTFOLIO_SNAPSHOT_INTERVAL_SECONDS = int(os.getenv("PORTFOLIO_SNAPSHOT_INTERVAL_SECONDS", "60"))
    PORTFOLIO_SNAPSHOT_RUN_ON_START = os.getenv("PORTFOLIO_SNAPSHOT_RUN_ON_START", "false").lower() == "true"
    
    crypto = CryptoHelper(ENCRYPTION_KEY)
    news_ingest_service = NewsIngestService()
    kis_market_universe_service = KISMarketUniverseService()
    market_index_repository = MarketIndexRepository()
    
    # 1. 뉴스 수집 스케줄러 기동
    print(f"[Worker] News Ingest Scheduler (Enabled: {NEWS_INGEST_ENABLED}) 기동 시도")
    start_news_ingest_scheduler(
        news_ingest_service=news_ingest_service,
        news_ingest_enabled=NEWS_INGEST_ENABLED,
        news_ingest_interval_seconds=NEWS_INGEST_INTERVAL_SECONDS
    )
    
    # 2. ML 자동화 스케줄러 기동
    print(f"[Worker] ML Automation Scheduler (Enabled: {ML_AUTOMATION_ENABLED}) 기동 시도")
    start_ml_automation_scheduler(
        ml_automation_enabled=ML_AUTOMATION_ENABLED,
        supabase_service_role_key=SUPABASE_SERVICE_ROLE_KEY
    )
    
    # 3. 홈 마켓 스냅샷 스케줄러 기동
    print(f"[Worker] Home Market Snapshot Scheduler (Enabled: {HOME_MARKET_SNAPSHOT_ENABLED}) 기동 시도")
    start_market_snapshot_scheduler(
        kis_market_universe_service=kis_market_universe_service,
        enabled=HOME_MARKET_SNAPSHOT_ENABLED,
        kis_config={
            "appkey": KIS_APPKEY,
            "appsecret": KIS_APPSECRET,
            "cano": KIS_CANO,
            "acnt_prdt_cd": KIS_ACNT_PRDT_CD,
            "env": KIS_ENV,
        },
        open_interval_seconds=HOME_MARKET_OPEN_INTERVAL_SECONDS,
        closed_interval_seconds=HOME_MARKET_CLOSED_INTERVAL_SECONDS,
        quote_limit=HOME_MARKET_SNAPSHOT_LIMIT,
        max_workers=HOME_MARKET_SNAPSHOT_WORKERS,
    )
    
    # 4. 마켓 인덱스 스케줄러 기동
    print(f"[Worker] Market Index Scheduler (Enabled: {MARKET_INDEX_SNAPSHOT_ENABLED}) 기동 시도")
    start_market_index_scheduler(
        market_index_repository=market_index_repository,
        enabled=MARKET_INDEX_SNAPSHOT_ENABLED,
        open_interval_seconds=MARKET_INDEX_OPEN_INTERVAL_SECONDS,
        closed_interval_seconds=MARKET_INDEX_CLOSED_INTERVAL_SECONDS,
    )
    
    # 5. 포트폴리오 스냅샷 스케줄러 기동
    print(f"[Worker] Portfolio Snapshot Scheduler (Enabled: {PORTFOLIO_SNAPSHOT_ENABLED}) 기동 시도")
    start_portfolio_snapshot_scheduler(
        crypto_helper=crypto,
        enabled=PORTFOLIO_SNAPSHOT_ENABLED,
        interval_seconds=PORTFOLIO_SNAPSHOT_INTERVAL_SECONDS,
        run_on_start=PORTFOLIO_SNAPSHOT_RUN_ON_START,
    )
    
    print("[Worker] 모든 스케줄러가 성공적으로 등록되었습니다. 무한 대기 상태로 진입합니다.")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("[Worker] 키보드 인터럽트로 인해 스케줄러 워커 프로세스를 종료합니다.")

if __name__ == "__main__":
    main()
