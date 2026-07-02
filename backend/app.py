import os
import sys
from pathlib import Path
from flask import Flask
from flask_cors import CORS
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
from backend.services.news_summary_service import NewsSummaryService
from backend.services.dart_repository import DartRepository
from backend.services.dart_ingest import DartIngestService
from backend.services.kis_market_universe import KISMarketUniverseService
from backend.services.market_snapshot_scheduler import start_market_snapshot_scheduler
from backend.services.ml_scheduler import start_dart_ingest_scheduler, start_news_ingest_scheduler, start_ml_automation_scheduler
from backend.services.auto_trading_rule_engine import start_auto_trading_rule_scheduler

from backend.routes.home import home_bp
from backend.routes.keys import keys_bp
from backend.routes.ml import ml_bp
from backend.routes.news import news_bp
from backend.routes.disclosures import disclosures_bp
from backend.routes.trade import trade_bp
from backend.routes.transfer import transfer_bp

app = Flask(__name__)
# 프론트엔드 연동을 위해 CORS 활성화 및 Authorization 헤더 허용
CORS(app, resources={r"/api/*": {"origins": "*"}}, supports_credentials=True)

# 환경 변수에서 주요 설정값 로드
ENCRYPTION_KEY = os.getenv("ENCRYPTION_KEY", "default-dev-encryption-key-32bytes!")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY")
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")

# Support both legacy and current env key names for KIS credentials.
KIS_APPKEY = os.getenv("KIS_APPKEY", "") or os.getenv("KIS_APP_KEY", "")
KIS_APPSECRET = os.getenv("KIS_APPSECRET", "") or os.getenv("KIS_APP_SECRET", "")
KIS_CANO = os.getenv("KIS_CANO", "")
KIS_ACNT_PRDT_CD = os.getenv("KIS_ACNT_PRDT_CD", "01")
KIS_ENV = os.getenv("KIS_ENV", "MOCK")
COINONE_ACCESS_TOKEN = os.getenv("COINONE_ACCESS_TOKEN", "")
COINONE_SECRET_KEY = os.getenv("COINONE_SECRET_KEY", "")
BINANCE_API_KEY = os.getenv("BINANCE_API_KEY", "")
BINANCE_SECRET_KEY = os.getenv("BINANCE_SECRET_KEY", "")

NEWS_INGEST_ENABLED = os.getenv("NEWS_INGEST_ENABLED", "false").lower() == "true"
NEWS_INGEST_INTERVAL_SECONDS = int(os.getenv("NEWS_INGEST_INTERVAL_SECONDS", "600"))
DART_INGEST_ENABLED = os.getenv("DART_INGEST_ENABLED", "false").lower() == "true"
DART_INGEST_INTERVAL_SECONDS = int(os.getenv("DART_INGEST_INTERVAL_SECONDS", "900"))
ML_AUTOMATION_ENABLED = os.getenv("ML_AUTOMATION_ENABLED", "true").lower() == "true"
HOME_MARKET_SNAPSHOT_ENABLED = os.getenv("HOME_MARKET_SNAPSHOT_ENABLED", "true").lower() == "true"
HOME_MARKET_OPEN_INTERVAL_SECONDS = int(os.getenv("HOME_MARKET_OPEN_INTERVAL_SECONDS", "60"))
HOME_MARKET_CLOSED_INTERVAL_SECONDS = int(os.getenv("HOME_MARKET_CLOSED_INTERVAL_SECONDS", "600"))
HOME_MARKET_SNAPSHOT_LIMIT = int(os.getenv("HOME_MARKET_SNAPSHOT_LIMIT", "300"))
HOME_MARKET_SNAPSHOT_WORKERS = int(os.getenv("HOME_MARKET_SNAPSHOT_WORKERS", "2"))
AUTO_TRADING_RULES_ENABLED = os.getenv("AUTO_TRADING_RULES_ENABLED", "false").lower() == "true"
AUTO_TRADING_RULES_INTERVAL_SECONDS = int(os.getenv("AUTO_TRADING_RULES_INTERVAL_SECONDS", "30"))

# Flask Config에 값 바인딩
app.config["KIS_APPKEY"] = KIS_APPKEY
app.config["KIS_APPSECRET"] = KIS_APPSECRET
app.config["KIS_CANO"] = KIS_CANO
app.config["KIS_ACNT_PRDT_CD"] = KIS_ACNT_PRDT_CD
app.config["KIS_ENV"] = KIS_ENV
app.config["COINONE_ACCESS_TOKEN"] = COINONE_ACCESS_TOKEN
app.config["COINONE_SECRET_KEY"] = COINONE_SECRET_KEY
app.config["BINANCE_API_KEY"] = BINANCE_API_KEY
app.config["BINANCE_SECRET_KEY"] = BINANCE_SECRET_KEY
app.config["PROJECT_ROOT_PATH"] = PROJECT_ROOT

# 전역 공유 서비스 인스턴스 초기화 및 App 바인딩 (의존성 주입)
crypto = CryptoHelper(ENCRYPTION_KEY)
news_repository = NewsRepository()
news_ingest_service = NewsIngestService()
news_summary_service = NewsSummaryService()
dart_repository = DartRepository()
dart_ingest_service = DartIngestService()
kis_market_universe_service = KISMarketUniverseService()

app.crypto = crypto
app.news_repository = news_repository
app.news_ingest_service = news_ingest_service
app.news_summary_service = news_summary_service
app.dart_repository = dart_repository
app.dart_ingest_service = dart_ingest_service
app.kis_market_universe_service = kis_market_universe_service

# Blueprint 등록
app.register_blueprint(home_bp)
app.register_blueprint(keys_bp)
app.register_blueprint(ml_bp)
app.register_blueprint(news_bp)
app.register_blueprint(disclosures_bp)
app.register_blueprint(trade_bp)
app.register_blueprint(transfer_bp)

# Flask 디버그 모드 리로더에 의한 스케줄러 이중 기동 방지 및 flask run 환경 지원
is_scheduler_host = (not app.debug) or (os.environ.get("WERKZEUG_RUN_MAIN") == "true")
SCHEDULER_RUN_IN_GATEWAY = os.getenv("SCHEDULER_RUN_IN_GATEWAY", "false").lower() == "true"

if is_scheduler_host and SCHEDULER_RUN_IN_GATEWAY:
    start_news_ingest_scheduler(
        news_ingest_service=news_ingest_service,
        news_ingest_enabled=NEWS_INGEST_ENABLED,
        news_ingest_interval_seconds=NEWS_INGEST_INTERVAL_SECONDS
    )
    start_dart_ingest_scheduler(
        dart_ingest_service=dart_ingest_service,
        dart_ingest_enabled=DART_INGEST_ENABLED,
        dart_ingest_interval_seconds=DART_INGEST_INTERVAL_SECONDS,
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
    start_auto_trading_rule_scheduler(
        enabled=AUTO_TRADING_RULES_ENABLED,
        interval_seconds=AUTO_TRADING_RULES_INTERVAL_SECONDS,
    )
if __name__ == "__main__":
    # Flask 서버 구동 (python backend/app.py 로 기동할 때만 타며, flask run 시에는 타지 않음)
    app.run(host="0.0.0.0", port=5050, debug=True)
