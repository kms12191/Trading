import os
from datetime import datetime
from pathlib import Path
from flask import Blueprint, request, jsonify, current_app
from backend.services.home_service import (
    build_home_overview,
    clamp_market_limit,
    fetch_coinone_overview,
    fetch_coinone_rankings,
    format_krw_compact,
    normalize_ranking_label,
    split_kis_holdings,
    to_float,
)
from backend.services.kis_client import KISClient
from backend.services.market_repository import MarketRepository
from backend.services.toss_client import TossClient
from backend.services.coinone_client import CoinoneClient
from backend.services.binance_client import BinanceClient, BinanceFuturesClient
from backend.services.auth_service import get_user_id_from_header
from backend.services.supabase_client import query_supabase
from backend.services.error_message_service import format_error_payload

home_bp = Blueprint("home", __name__)

KIS_MARKET_MASTER_FILE_PATH = os.getenv("KIS_MARKET_MASTER_FILE_PATH", "")
MARKET_SYNC_ADMIN_TOKEN = os.getenv("MARKET_SYNC_ADMIN_TOKEN", "")


def build_direct_stock_ranking_rows(rows: list[dict], ranking: str, limit: int, is_foreign: bool = False) -> list[dict]:
    normalized_ranking = normalize_ranking_label(ranking)
    ranked_rows = []

    for index, row in enumerate((rows or [])[:limit], start=1):
        trading_value = to_float(row.get("trading_value"))
        change_rate = to_float(row.get("change_rate"))
        current_price = to_float(row.get("current_price"))
        prefix = "+" if change_rate > 0 else ""

        ranked_rows.append({
            "rank": index,
            "name": row.get("name") or row.get("symbol"),
            "code": row.get("symbol"),
            "price": f"{current_price:,.2f}" if is_foreign and current_price else f"{current_price:,.0f}" if current_price else "-",
            "change": f"{prefix}{change_rate:.2f}%",
            "value": "-" if is_foreign and normalized_ranking in {"up", "down"} else format_krw_compact(trading_value) if trading_value else "-",
            "trading_value": trading_value,
            "trading_volume": to_float(row.get("trading_volume")),
            "market_segment": row.get("market_segment"),
            "market_country": row.get("market_country"),
            "as_of": row.get("as_of"),
        })

    return ranked_rows


def sort_stock_rows_by_ranking(rows: list[dict], ranking: str) -> list[dict]:
    normalized_ranking = normalize_ranking_label(ranking)
    sortable_rows = list(rows or [])

    if normalized_ranking == "volume":
        sortable_rows.sort(key=lambda row: to_float(row.get("trading_volume")), reverse=True)
    elif normalized_ranking == "up":
        sortable_rows.sort(
            key=lambda row: (to_float(row.get("change_rate")), to_float(row.get("trading_value"))),
            reverse=True,
        )
    elif normalized_ranking == "down":
        sortable_rows.sort(
            key=lambda row: (to_float(row.get("change_rate")), -to_float(row.get("trading_value"))),
        )
    else:
        sortable_rows.sort(key=lambda row: to_float(row.get("trading_value")), reverse=True)

    return sortable_rows


def merge_rank_rows(primary_rows: list[dict], fallback_rows: list[dict], ranking: str, limit: int) -> list[dict]:
    merged_by_symbol: dict[str, dict] = {}

    for row in primary_rows or []:
        symbol = str(row.get("symbol") or "").strip().upper()
        if symbol and symbol not in merged_by_symbol:
            merged_by_symbol[symbol] = dict(row)

    for row in fallback_rows or []:
        symbol = str(row.get("symbol") or "").strip().upper()
        if symbol and symbol not in merged_by_symbol:
            merged_by_symbol[symbol] = dict(row)

    return sort_stock_rows_by_ranking(list(merged_by_symbol.values()), ranking)[:limit]


def require_market_sync_admin():
    token = request.headers.get("X-Admin-Token", "")
    if not MARKET_SYNC_ADMIN_TOKEN or token != MARKET_SYNC_ADMIN_TOKEN:
        return jsonify({
            "success": False,
            "message": "관리자 전용 작업입니다.",
        }), 403
    return None

@home_bp.route("/api/home/market", methods=["POST"] )
def get_home_market():
    """홈 화면의 시장 현황을 조회합니다."""
    try:
        auth_header = request.headers.get("Authorization")
        data = request.json or {}
        overview = build_home_overview(data, auth_header=auth_header)
        return jsonify({
            "success": True,
            "data": overview
        })
    except Exception as error:
        return jsonify(format_error_payload(error, "홈 화면 시장 조회 실패")), 500

@home_bp.route("/api/home/overview", methods=["POST"] )
def get_home_overview():
    """홈 화면의 요약 데이터를 구성합니다.
    KIS 계좌 정보가 있으면 계좌 보유 종목까지 함께 채우고, 없으면 Coinone 공개 시세만 반환합니다.
    """
    auth_header = request.headers.get("Authorization")
    user_id = None
    if auth_header:
        try:
            user_id, _ = get_user_id_from_header(auth_header)
        except Exception:
            pass

    data = request.json or {}
    appkey = data.get("appkey")
    appsecret = data.get("appsecret")
    cano = data.get("cano")
    acnt_prdt_cd = data.get("acnt_prdt_cd", "01")
    env = data.get("env", "MOCK")

    result = {
        "kis": None,
        "coins": [],
        "updated_at": datetime.utcnow().isoformat() + "Z",
        "message": "",
    }

    try:
        result["coins"] = fetch_coinone_overview()
    except Exception as coin_error:
        formatted = format_error_payload(coin_error, "Coinone 홈 코인 조회 실패", exchange="COINONE")
        result["message"] = formatted["error"]["title"]

    has_kis_credentials = bool(appkey and appsecret and cano)
    if not has_kis_credentials:
        if not result["message"]:
            result["message"] = "KIS 계좌 정보가 없어서 Coinone 공개 시세만 반환합니다. KIS 설정은 .env에서 확인해주세요."
        return jsonify({
            "success": True,
            "data": result
        })

    try:
        client = KISClient(
            appkey=appkey,
            appsecret=appsecret,
            cano=cano,
            acnt_prdt_cd=acnt_prdt_cd,
            env=env,
            user_id=user_id,
        )

        balance = client.get_balance()
        domestic_holdings, foreign_holdings = split_kis_holdings(balance.get("holdings", []))

        result["kis"] = {
            "total_evaluation": to_float(balance.get("total_evaluation")),
            "available_cash": to_float(balance.get("available_cash")),
            "domestic": domestic_holdings,
            "foreign": foreign_holdings,
        }

        return jsonify({
            "success": True,
            "data": result
        })
    except Exception as kis_error:
        formatted = format_error_payload(kis_error, "KIS 홈 계좌 조회 실패", exchange="KIS")
        formatted["data"] = result
        return jsonify(formatted), 500

@home_bp.route("/api/market/kis/sync", methods=["POST"] )
def sync_kis_market_universe():
    """KIS 시장 종목 마스터 파일을 DB의 종목 유니버스로 동기화합니다."""
    admin_error = require_market_sync_admin()
    if admin_error:
        return admin_error

    data = request.json or {}
    file_paths = data.get("file_paths")
    file_path = data.get("file_path") or KIS_MARKET_MASTER_FILE_PATH
    refresh_quotes = bool(data.get("refresh_quotes", True))
    max_workers = min(max(int(data.get("max_workers") or 4), 1), 4)
    quote_limit_raw = data.get("quote_limit", 300)
    quote_limit = None if quote_limit_raw in (None, "", "all", "ALL") else int(quote_limit_raw)
    if quote_limit is not None:
        quote_limit = min(max(quote_limit, 1), 1000)

    if isinstance(file_paths, str):
        file_paths = [part.strip() for part in file_paths.split(",") if part.strip()]
    elif isinstance(file_paths, list):
        file_paths = [str(part).strip() for part in file_paths if str(part).strip()]
    else:
        file_paths = []

    if file_path and not file_paths:
        file_paths = [part.strip() for part in str(file_path).split(",") if part.strip()]

    if not file_paths:
        return jsonify({
            "success": False,
            "message": "KIS 종목 마스터 파일 경로가 필요합니다. body.file_path, body.file_paths 또는 KIS_MARKET_MASTER_FILE_PATH를 설정해주세요.",
        }), 400

    project_root = current_app.config.get("PROJECT_ROOT_PATH")
    if project_root:
        root_path = Path(project_root).resolve()
        for item in file_paths:
            resolved_path = Path(item).resolve()
            if root_path not in resolved_path.parents and resolved_path != root_path:
                return jsonify({
                    "success": False,
                    "message": "프로젝트 외부의 파일 경로는 사용할 수 없습니다.",
                }), 400

    kis_market_universe_service = current_app.kis_market_universe_service
    if not kis_market_universe_service.repository.is_configured:
        return jsonify({
            "success": False,
            "message": "SUPABASE_SERVICE_ROLE_KEY가 필요합니다. Supabase 관리 키를 .env에 설정해주세요.",
        }), 500

    try:
        kis_client = KISClient(
            appkey=current_app.config.get("KIS_APPKEY", ""),
            appsecret=current_app.config.get("KIS_APPSECRET", ""),
            cano=current_app.config.get("KIS_CANO", ""),
            acnt_prdt_cd=current_app.config.get("KIS_ACNT_PRDT_CD", "01"),
            env=current_app.config.get("KIS_ENV", "MOCK"),
        )
        result = kis_market_universe_service.sync_from_files(
            file_paths=file_paths,
            kis_client=kis_client,
            refresh_quotes=refresh_quotes,
            max_workers=max_workers,
            quote_limit=quote_limit,
        )
        return jsonify({
            "success": True,
            "message": "KIS 종목 마스터 동기화가 완료되었습니다.",
            "data": result,
        })
    except Exception as error:
        return jsonify(format_error_payload(error, "KIS 종목 마스터 동기화 실패", exchange="KIS")), 500

@home_bp.route("/api/market/rankings", methods=["GET"] )
def get_market_rankings():
    """유니버스 종목의 거래대금 순위를 조회합니다."""
    auth_header = request.headers.get("Authorization")
    asset_type = str(request.args.get("asset_type", "STOCK")).upper()
    market_segment = request.args.get("market_segment") or request.args.get("region", "ALL")
    ranking = request.args.get("ranking", "거래대금")
    limit = clamp_market_limit(request.args.get("limit", 50), 50, 100)
    force_refresh = str(request.args.get("force_refresh", "")).lower() in {"1", "true", "yes", "y"}

    try:
        if asset_type == "CRYPTO":
            rankings = fetch_coinone_rankings(limit=limit, ranking=ranking)
            return jsonify({
                "success": True,
                "data": {
                    "items": rankings["items"],
                    "totalCount": rankings["total_count"],
                    "universeCount": rankings["total_count"],
                    "assetType": "CRYPTO",
                    "marketSegment": "KR",
                    "ranking": ranking,
                    "limit": limit,
                }
            })

        normalized_ranking = normalize_ranking_label(ranking)
        normalized_region = str(market_segment or "").strip().upper()
        is_domestic = normalized_region in {"국내", "KR", "KOREA", "DOMESTIC", "KOSPI", "KOSDAQ", "ALL", ""}
        is_overseas = normalized_region in {"해외", "US", "USA", "GLOBAL", "FOREIGN", "NASDAQ", "NYSE", "AMEX"}

        if is_domestic or is_overseas:
            client = KISClient(
                appkey=current_app.config.get("KIS_APPKEY", ""),
                appsecret=current_app.config.get("KIS_APPSECRET", ""),
                cano=current_app.config.get("KIS_CANO", ""),
                acnt_prdt_cd=current_app.config.get("KIS_ACNT_PRDT_CD", "01"),
                env=current_app.config.get("KIS_ENV", "MOCK"),
            )
            repository = MarketRepository()
            repository_rows = []

            if repository.is_configured:
                repository_market_segment = "US" if is_overseas else "KR"
                repository_order_by = "trading_value.desc,updated_at.desc"
                if normalized_ranking == "volume":
                    repository_order_by = "trading_volume.desc,updated_at.desc"
                elif normalized_ranking == "up":
                    repository_order_by = "change_rate.desc,trading_value.desc,updated_at.desc"
                elif normalized_ranking == "down":
                    repository_order_by = "change_rate.asc,trading_value.desc,updated_at.desc"

                repository_rows = repository.list_turnover_rankings(
                    market_segment=repository_market_segment,
                    limit=max(limit, 200),
                    order_by=repository_order_by,
                )

            if is_overseas:
                try:
                    if normalized_ranking == "up":
                        direct_rows = client.get_overseas_updown_rankings(direction="up", limit=limit)
                    elif normalized_ranking == "down":
                        direct_rows = client.get_overseas_updown_rankings(direction="down", limit=limit)
                    else:
                        direct_rows = client.get_overseas_trade_volume_rankings(limit=limit)
                except Exception:
                    direct_rows = []
                merged_rows = merge_rank_rows(direct_rows, repository_rows, ranking, limit)
                stock_rows = build_direct_stock_ranking_rows(merged_rows, ranking, limit, is_foreign=True)
                return jsonify({
                    "success": True,
                    "data": {
                        "items": stock_rows,
                        "totalCount": len(stock_rows),
                        "universeCount": max(len(stock_rows), len(repository_rows)),
                        "assetType": "STOCK",
                        "marketSegment": market_segment,
                        "ranking": ranking,
                        "limit": limit,
                        "message": "",
                        "marketSnapshot": {},
                    }
                })

            try:
                if normalized_ranking == "up":
                    direct_rows = client.get_fluctuation_rankings(direction="up", limit=limit)
                elif normalized_ranking == "down":
                    direct_rows = client.get_fluctuation_rankings(direction="down", limit=limit)
                elif normalized_ranking == "volume":
                    direct_rows = client.get_volume_rankings(limit=limit)
                else:
                    direct_rows = client.get_turnover_rankings(limit=limit)
            except Exception:
                direct_rows = []

            merged_rows = merge_rank_rows(direct_rows, repository_rows, ranking, limit)
            stock_rows = build_direct_stock_ranking_rows(merged_rows, ranking, limit, is_foreign=False)
            return jsonify({
                "success": True,
                "data": {
                    "items": stock_rows,
                    "totalCount": len(stock_rows),
                    "universeCount": max(len(stock_rows), len(repository_rows)),
                    "assetType": "STOCK",
                    "marketSegment": market_segment,
                    "ranking": ranking,
                    "limit": limit,
                    "message": "",
                    "marketSnapshot": {},
                }
            })

        overview = build_home_overview({
            "filters": {
                "region": market_segment,
                "ranking": ranking,
                "horizon": "실시간",
                "forceRefresh": force_refresh,
            }
        }, auth_header=auth_header)
        stock_rows = list(overview.get("stocks") or [])[:limit]
        market_snapshot = overview.get("market_snapshot") or {}
        return jsonify({
            "success": True,
            "data": {
                "items": stock_rows,
                "totalCount": len(stock_rows),
                "universeCount": len(stock_rows),
                "assetType": "STOCK",
                "marketSegment": market_segment,
                "ranking": ranking,
                "limit": limit,
                "message": overview.get("message", ""),
                "marketSnapshot": market_snapshot,
            }
        })
    except Exception as error:
        return jsonify(format_error_payload(error, "거래대금 순위 조회 실패", exchange="KIS")), 500

@home_bp.route("/api/dashboard/balance", methods=["POST"])
def get_dashboard_balance():
    """등록된 증권사 계좌의 실시간 잔고와 평가 정보를 조회합니다."""
    auth_header = request.headers.get("Authorization")
    if not auth_header:
        return jsonify({"success": False, "message": "인증 헤더가 필요합니다."}), 401

    data = request.json or {}
    exchange = data.get("exchange", "KIS")
    broker_env = data.get("env", "MOCK")

    try:
        user_id, token = get_user_id_from_header(auth_header)
        
        credential_exchange = "BINANCE" if exchange == "BINANCE_UM_FUTURES" else exchange
        params = {
            "user_id": f"eq.{user_id}",
            "exchange": f"eq.{credential_exchange}",
            "broker_env": f"eq.{broker_env}"
        }
        records = query_supabase(auth_header, "user_api_keys", "GET", params=params)
        if not records or len(records) == 0:
            return jsonify({"success": False, "message": f"등록된 {credential_exchange} ({broker_env}) API 키가 없습니다."}), 404

        record = records[0]
        crypto_helper = current_app.crypto
        access_key = crypto_helper.decrypt(record.get("encrypted_access_key"))
        secret_key = crypto_helper.decrypt(record.get("encrypted_secret_key"))

        if exchange == "TOSS":
            account_seq = record.get("toss_account_seq")
            client = TossClient(
                client_id=access_key,
                client_secret=secret_key,
                account_seq=account_seq,
                env=broker_env,
                user_id=user_id,
            )
            balance = client.get_balance()
        elif exchange == "KIS":
            cano = record.get("kis_account_no")
            acnt_prdt_cd = record.get("kis_account_code", "01")
            client = KISClient(
                appkey=access_key,
                appsecret=secret_key,
                cano=cano,
                acnt_prdt_cd=acnt_prdt_cd,
                env=broker_env,
                user_id=user_id,
            )
            balance = client.get_balance()
        elif exchange == "COINONE":
            client = CoinoneClient(
                access_token=access_key,
                secret_key=secret_key
            )
            balance = client.get_balance()
        elif exchange == "BINANCE":
            client = BinanceClient(
                api_key=access_key,
                secret_key=secret_key,
                env=broker_env,
            )
            balance = client.get_balance()
        elif exchange == "BINANCE_UM_FUTURES":
            client = BinanceFuturesClient(
                api_key=access_key,
                secret_key=secret_key,
                env=broker_env,
            )
            balance = client.get_balance()
        else:
            return jsonify({"success": False, "message": f"지원하지 않는 거래소입니다: {exchange}"}), 400

        exchange_rate = 1500.0
        if exchange == "TOSS" and hasattr(client, "get_exchange_rate"):
            exchange_rate = client.get_exchange_rate()

        balance["exchange_rate"] = exchange_rate

        return jsonify({
            "success": True,
            "data": balance
        })
    except Exception as e:
        # 모의투자(MOCK) 환경의 경우 외부 데모 서버 장애/오프라인 상태가 잦으므로,
        # 에러를 노출하여 대시보드 로드를 막기보다 빈 잔고로 안전하게 복구하여 반환합니다.
        if broker_env == "MOCK":
            current_app.logger.warning(
                f"[Dashboard][MOCK_FALLBACK] {exchange} MOCK balance query failed, fallback to empty: {str(e)}"
            )
            return jsonify({
                "success": True,
                "data": {
                    "total_evaluation": 0.0,
                    "available_cash": 0.0,
                    "currency": "USD" if "BINANCE" in exchange else "KRW",
                    "holdings": [],
                    "warning": f"{exchange} 모의투자 서버 연결이 원활하지 않아 임시로 0으로 표시합니다."
                }
            })
        return jsonify(format_error_payload(e, "잔고 조회 실패", exchange=exchange)), 500
