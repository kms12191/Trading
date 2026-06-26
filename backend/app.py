import os
import sys
from pathlib import Path
from flask import Flask
from flask_cors import CORS
from dotenv import load_dotenv

# backend 디렉토리가 파이썬 경로에 포함되도록 설정
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.utils.crypto_helper import CryptoHelper
from backend.services.news_repository import NewsRepository
from backend.services.news_ingest import NewsIngestService
from backend.services.news_summary_service import NewsSummaryService
from backend.services.kis_market_universe import KISMarketUniverseService
from backend.services.market_snapshot_scheduler import start_market_snapshot_scheduler
from backend.services.ml_scheduler import start_news_ingest_scheduler, start_ml_automation_scheduler

from backend.routes.home import home_bp
from backend.routes.keys import keys_bp
from backend.routes.ml import ml_bp
from backend.routes.news import news_bp
from backend.routes.trade import trade_bp

# 환경 변수 로드
load_dotenv()

app = Flask(__name__)
# 프론트엔드 연동을 위해 CORS 활성화 및 Authorization 헤더 허용
CORS(app, resources={r"/api/*": {"origins": "*"}}, supports_credentials=True)

# 환경 변수에서 주요 설정값 로드
ENCRYPTION_KEY = os.getenv("ENCRYPTION_KEY", "default-dev-encryption-key-32bytes!")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY")
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")

KIS_APPKEY = os.getenv("KIS_APPKEY", "")
KIS_APPSECRET = os.getenv("KIS_APPSECRET", "")
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

# Flask Config에 값 바인딩
app.config["KIS_APPKEY"] = KIS_APPKEY
app.config["KIS_APPSECRET"] = KIS_APPSECRET
app.config["KIS_CANO"] = KIS_CANO
app.config["KIS_ACNT_PRDT_CD"] = KIS_ACNT_PRDT_CD
app.config["KIS_ENV"] = KIS_ENV
app.config["PROJECT_ROOT_PATH"] = Path(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 전역 공유 서비스 인스턴스 초기화 및 App 바인딩 (의존성 주입)
crypto = CryptoHelper(ENCRYPTION_KEY)
news_repository = NewsRepository()
news_ingest_service = NewsIngestService()
news_summary_service = NewsSummaryService()
kis_market_universe_service = KISMarketUniverseService()

app.crypto = crypto
app.news_repository = news_repository
app.news_ingest_service = news_ingest_service
app.news_summary_service = news_summary_service
app.kis_market_universe_service = kis_market_universe_service

# Blueprint 등록
app.register_blueprint(home_bp)
app.register_blueprint(keys_bp)
app.register_blueprint(ml_bp)
app.register_blueprint(news_bp)
app.register_blueprint(trade_bp)

if __name__ == "__main__":
    # Flask 디버그 모드 리로더에 의한 스케줄러 이중 기동 방지
    if os.environ.get("WERKZEUG_RUN_MAIN") == "true":
        start_news_ingest_scheduler(
            news_ingest_service=news_ingest_service,
            news_ingest_enabled=NEWS_INGEST_ENABLED,
            news_ingest_interval_seconds=NEWS_INGEST_INTERVAL_SECONDS
        )
        start_ml_automation_scheduler(
            ml_automation_enabled=ML_AUTOMATION_ENABLED,
            supabase_service_role_key=SUPABASE_SERVICE_ROLE_KEY
        )
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
    # Flask 서버 구동
    app.run(host="0.0.0.0", port=5050, debug=True)
