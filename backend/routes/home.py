import os
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from datetime import datetime, timedelta
from pathlib import Path
from flask import Blueprint, request, jsonify, current_app
from backend.services.home_service import build_home_overview, fetch_coinone_overview, split_kis_holdings, to_float
from backend.services.kis_client import KISClient
from backend.services.toss_client import TossClient
from backend.services.coinone_client import CoinoneClient
from backend.services.binance_client import BinanceClient
from backend.services.market_index_service import (
    collect_market_index_rows,
    get_market_index_cache,
    market_index_rows_need_refresh,
    set_market_index_cache,
    serialize_market_index_rows,
)
from backend.services.auth_service import get_user_id_from_header
from backend.services.supabase_client import query_supabase

home_bp = Blueprint("home", __name__)

KIS_MARKET_MASTER_FILE_PATH = os.getenv("KIS_MARKET_MASTER_FILE_PATH", "")
MARKET_SYNC_ADMIN_TOKEN = os.getenv("MARKET_SYNC_ADMIN_TOKEN", "")


def _log_market_index_snapshot(payload: dict) -> None:
    items = payload.get("items") or []
    for symbol in ("USDKRW", "NASDAQ100_F"):
        item = next((row for row in items if str(row.get("key") or row.get("symbol") or "").upper() == symbol), None)
        if not item:
            continue
        current_price = item.get("current_price", item.get("currentPrice"))
        previous_close = item.get("previous_close", item.get("previousClose"))
        change_price = item.get("change_price", item.get("changePrice"))
        change_rate = item.get("change_rate", item.get("changeRate"))
        current_app.logger.info(
            "[MarketIndex][response] symbol=%s current_price=%s previous_close=%s change_price=%s change_rate=%s source=%s",
            symbol,
            current_price,
            previous_close,
            change_price,
            change_rate,
            item.get("source") or payload.get("source"),
        )


def _call_with_timeout(func, timeout_seconds: float, default):
    executor = ThreadPoolExecutor(max_workers=1)
    future = executor.submit(func)
    try:
        return future.result(timeout=timeout_seconds)
    except FuturesTimeoutError:
        future.cancel()
        return default
    except Exception:
        return default
    finally:
        executor.shutdown(wait=False, cancel_futures=True)


def _market_index_payload_has_items(payload: dict) -> bool:
    return bool(payload and payload.get("items"))


def _build_market_index_payload(rows: list[dict], source: str, cache_status: str) -> dict:
    payload = serialize_market_index_rows(rows)
    payload["source"] = source
    payload["cacheStatus"] = cache_status
    payload["refreshNeeded"] = market_index_rows_need_refresh(rows)
    return payload


def parse_date_param(value: str | None, fallback: datetime) -> str:
    if not value:
        return fallback.date().isoformat()
    try:
        return datetime.fromisoformat(value[:10]).date().isoformat()
    except ValueError:
        return fallback.date().isoformat()


def calculate_portfolio_profit_rate(balance: dict) -> float:
    holdings = balance.get("holdings") or []
    total_profit = 0.0
    invested_amount = 0.0

    for item in holdings:
        qty = to_float(item.get("qty"))
        avg_price = to_float(item.get("avg_price"))
        current_price = to_float(item.get("current_price"))
        profit = to_float(item.get("profit"))
        total_profit += profit
        invested_amount += avg_price * qty if avg_price > 0 else max(0.0, current_price * qty - profit)

    if invested_amount <= 0:
        return 0.0
    return (total_profit / invested_amount) * 100


def save_portfolio_snapshot(auth_header: str, user_id: str, balance: dict, exchange_rate: float = 1500.0):
    snapshot_date = datetime.utcnow().date().isoformat()
    total_eval = to_float(balance.get("total_evaluation"))
    avail_cash = to_float(balance.get("available_cash"))

    if balance.get("currency") == "USD":
        total_eval = total_eval * exchange_rate
        avail_cash = avail_cash * exchange_rate

    payload = {
        "user_id": user_id,
        "snapshot_date": snapshot_date,
        "total_evaluation": total_eval,
        "available_cash": avail_cash,
        "portfolio_profit_rate": calculate_portfolio_profit_rate(balance),
        "updated_at": datetime.utcnow().isoformat(),
    }

    existing = query_supabase(
        auth_header,
        "portfolio_snapshots",
        "GET",
        params={
            "user_id": f"eq.{user_id}",
            "snapshot_date": f"eq.{snapshot_date}",
            "select": "id",
        },
    )

    if existing:
        query_supabase(
            auth_header,
            f"portfolio_snapshots?id=eq.{existing[0]['id']}",
            "PATCH",
            json_data=payload,
        )
    else:
        query_supabase(
            auth_header,
            "portfolio_snapshots",
            "POST",
            json_data=payload,
        )


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
        return jsonify({
            "success": False,
            "message": f"홈 화면 시장 조회 실패: {str(error)}",
        }), 500

@home_bp.route("/api/dashboard/asset-trend", methods=["GET"] )
def get_dashboard_asset_trend():
    """로그인 사용자의 자산 추이 데이터를 조회합니다."""
    auth_header = request.headers.get("Authorization")
    if not auth_header:
        return jsonify({"success": False, "message": "인증 헤더가 필요합니다."}), 401

    now = datetime.utcnow()
    start_date = parse_date_param(request.args.get("start"), now - timedelta(days=30))
    end_date = parse_date_param(request.args.get("end"), now)

    try:
        user_id, _ = get_user_id_from_header(auth_header)
    except Exception as error:
        return jsonify({"success": False, "message": f"사용자 인증 확인 실패: {str(error)}"}), 401

    try:
        rows = query_supabase(
            auth_header,
            "portfolio_snapshots",
            "GET",
            params={
                "user_id": f"eq.{user_id}",
                "snapshot_date": f"gte.{start_date}",
                "select": "snapshot_date,total_evaluation,available_cash,portfolio_profit_rate",
                "order": "snapshot_date.asc",
            },
        )
        rows = [
            row
            for row in (rows or [])
            if str(row.get("snapshot_date", ""))[:10] <= end_date
        ]
        return jsonify({
            "success": True,
            "data": {
                "items": rows,
                "start": start_date,
                "end": end_date,
                "source": "portfolio_snapshots",
            },
        })
    except Exception as error:
        return jsonify({
            "success": True,
            "data": {
                "items": [],
                "start": start_date,
                "end": end_date,
                "source": "empty",
                "message": f"자산 추이 데이터를 아직 준비하지 못했습니다: {str(error)}",
            },
        })

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
        result["message"] = f"Coinone 조회 실패: {str(coin_error)}"

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
        return jsonify({
            "success": False,
            "message": f"KIS 조회 실패: {str(kis_error)}",
            "data": result,
        }), 500

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
        return jsonify({
            "success": False,
            "message": f"KIS 종목 마스터 동기화 실패: {str(error)}",
        }), 500

@home_bp.route("/api/market/rankings", methods=["GET"] )
def get_market_rankings():
    """유니버스 종목의 거래대금 순위를 조회합니다."""
    market_segment = request.args.get("market_segment", "ALL")
    limit = int(request.args.get("limit", 50))

    kis_market_universe_service = current_app.kis_market_universe_service
    try:
        rankings = kis_market_universe_service.repository.list_turnover_rankings(
            market_segment=market_segment,
            limit=limit,
        )
        universe_count = kis_market_universe_service.repository.count_universe(market_segment=market_segment)
        return jsonify({
            "success": True,
            "data": {
                "items": rankings,
                "totalCount": len(rankings),
                "universeCount": universe_count,
                "marketSegment": market_segment.upper(),
                "limit": limit,
            }
        })
    except Exception as error:
        return jsonify({
            "success": False,
            "message": f"거래대금 순위 조회 실패: {str(error)}",
        }), 500

def get_market_indices():
    """하단 지수 바에 사용할 최신 지수 스냅샷을 반환합니다."""
    repository = getattr(current_app, "market_index_repository", None)
    try:
        rows = get_market_index_cache()
        if rows:
            payload = serialize_market_index_rows(rows)
            payload["cacheStatus"] = "HIT"
            payload["refreshNeeded"] = market_index_rows_need_refresh(rows)
            _log_market_index_snapshot(payload)
            current_app.logger.info(
                "[MarketIndex] indices loaded count=%s source=%s fetchedAt=%s",
                len(payload.get("items") or []),
                payload.get("source"),
                payload.get("fetchedAt"),
            )
            return jsonify({
                "success": True,
                "data": payload,
            })

        if repository is not None and repository.is_configured:
            rows = _call_with_timeout(repository.list_latest, 2.0, [])
            if rows:
                payload = serialize_market_index_rows(rows)
                payload["cacheStatus"] = "HIT"
                payload["refreshNeeded"] = market_index_rows_need_refresh(rows)
                set_market_index_cache(rows)
                _log_market_index_snapshot(payload)
                current_app.logger.info(
                    "[MarketIndex] indices loaded count=%s source=%s fetchedAt=%s",
                    len(payload.get("items") or []),
                    payload.get("source"),
                    payload.get("fetchedAt"),
                )
                return jsonify({
                    "success": True,
                    "data": payload,
                })
        else:
            current_app.logger.info("[MarketIndex] repository is not configured, skipping DB cache lookup.")

        live_rows, live_errors = _call_with_timeout(collect_market_index_rows, 8.0, ([], []))
        if live_rows:
            if repository is not None and repository.is_configured:
                try:
                    repository.upsert_latest(live_rows)
                except Exception:
                    pass
            set_market_index_cache(live_rows)
            payload = serialize_market_index_rows(live_rows)
            payload["source"] = "live.collector"
            payload["cacheStatus"] = "MISS"
            payload["bootstrap"] = True
            payload["errors"] = live_errors
            _log_market_index_snapshot(payload)
            current_app.logger.info(
                "[MarketIndex] indices loaded count=%s source=%s fetchedAt=%s",
                len(payload.get("items") or []),
                payload.get("source"),
                payload.get("fetchedAt"),
            )
            return jsonify({
                "success": True,
                "data": payload,
            })

        return jsonify({
            "success": False,
            "message": "지수 캐시를 아직 준비 중입니다. 잠시 후 다시 시도해주세요.",
            "errors": live_errors,
        }), 503
    except Exception as error:
        live_rows, live_errors = _call_with_timeout(collect_market_index_rows, 8.0, ([], []))
        if live_rows:
            if repository is not None and repository.is_configured:
                try:
                    repository.upsert_latest(live_rows)
                except Exception:
                    pass
            set_market_index_cache(live_rows)
            payload = serialize_market_index_rows(live_rows)
            payload["source"] = "live.collector"
            payload["cacheStatus"] = "MISS"
            payload["bootstrap"] = True
            payload["errors"] = [str(error), *[item["message"] for item in live_errors]]
            _log_market_index_snapshot(payload)
            current_app.logger.info(
                "[MarketIndex] indices loaded count=%s source=%s fetchedAt=%s",
                len(payload.get("items") or []),
                payload.get("source"),
                payload.get("fetchedAt"),
            )
            return jsonify({
                "success": True,
                "data": payload,
            })
        return jsonify({
            "success": False,
            "message": f"지수 데이터 조회 실패: {str(error)}",
        }), 500
@home_bp.route("/api/market/indices", methods=["GET"])
def get_market_indices_v2():
    repository = getattr(current_app, "market_index_repository", None)
    fallback_payload = None

    try:
        current_app.logger.info("[MarketIndex][route] cache lookup start")
        rows = get_market_index_cache()
        if rows:
            payload = _build_market_index_payload(rows, "memory.cache", "HIT")
            if _market_index_payload_has_items(payload) and not payload.get("refreshNeeded"):
                _log_market_index_snapshot(payload)
                current_app.logger.info(
                    "[MarketIndex][route] cache load success source=%s count=%s fetchedAt=%s",
                    payload.get("source"),
                    len(payload.get("items") or []),
                    payload.get("fetchedAt"),
                )
                return jsonify({"success": True, "data": payload})
            if _market_index_payload_has_items(payload):
                fallback_payload = payload
                current_app.logger.info("[MarketIndex][route] memory cache is stale, refreshing from live collector.")
            else:
                current_app.logger.warning("[MarketIndex][route] memory cache query failed reason=empty serialized items")

        if repository is not None and repository.is_configured:
            current_app.logger.info("[MarketIndex][route] DB cache lookup start")
            rows = _call_with_timeout(repository.list_latest, 2.0, [])
            if rows:
                payload = _build_market_index_payload(rows, "supabase.market_indices_latest", "HIT")
                if _market_index_payload_has_items(payload):
                    set_market_index_cache(rows)
                    if not payload.get("refreshNeeded"):
                        _log_market_index_snapshot(payload)
                        current_app.logger.info(
                            "[MarketIndex][route] DB cache load success count=%s fetchedAt=%s",
                            len(payload.get("items") or []),
                            payload.get("fetchedAt"),
                        )
                        return jsonify({"success": True, "data": payload})
                    fallback_payload = fallback_payload or payload
                    current_app.logger.info("[MarketIndex][route] DB cache is stale, refreshing from live collector.")
                else:
                    current_app.logger.warning("[MarketIndex][route] DB cache query failed reason=empty serialized items")
            else:
                current_app.logger.warning("[MarketIndex][route] DB cache query failed reason=no rows")
        else:
            current_app.logger.info("[MarketIndex][route] repository is not configured, skipping DB cache lookup.")

        current_app.logger.info("[MarketIndex][route] live cache generation start")
        live_rows, live_errors = collect_market_index_rows()
        current_app.logger.info(
            "[MarketIndex][route] live data collection complete rowCount=%s errorCount=%s",
            len(live_rows),
            len(live_errors),
        )

        if live_rows:
            if repository is not None and repository.is_configured:
                try:
                    repository.upsert_latest(live_rows)
                    current_app.logger.info("[MarketIndex][route] DB cache save success count=%s", len(live_rows))
                except Exception as error:
                    current_app.logger.exception("[MarketIndex][route] DB cache save failed: %s", error)

            # live 수집이 끝난 즉시 메모리 캐시에 넣어 역전바가 바로 사용할 수 있게 한다.
            set_market_index_cache(live_rows)
            current_app.logger.info("[MarketIndex][route] memory cache save success count=%s", len(live_rows))

            payload = _build_market_index_payload(live_rows, "live.collector", "MISS")
            payload["bootstrap"] = True
            payload["errors"] = live_errors
            _log_market_index_snapshot(payload)
            current_app.logger.info(
                "[MarketIndex][route] indices loaded count=%s source=%s fetchedAt=%s",
                len(payload.get("items") or []),
                payload.get("source"),
                payload.get("fetchedAt"),
            )
            return jsonify({"success": True, "data": payload})

        if fallback_payload is not None:
            fallback_payload["source"] = f"{fallback_payload.get('source')}.stale"
            fallback_payload["refreshNeeded"] = True
            fallback_payload["errors"] = live_errors
            current_app.logger.warning(
                "[MarketIndex][route] live refresh failed, serving stale cache count=%s errors=%s",
                len(fallback_payload.get("items") or []),
                live_errors,
            )
            return jsonify({"success": True, "data": fallback_payload})

        current_app.logger.warning("[MarketIndex][route] cache query failed reason=empty live collection errors=%s", live_errors)
        return jsonify({
            "success": False,
            "message": "지수 캐시를 아직 준비 중입니다. 잠시 후 다시 시도해주세요.",
            "errors": live_errors,
        }), 503
    except Exception as error:
        current_app.logger.exception("[MarketIndex][route] cache query failed: %s", error)
        if fallback_payload is not None:
            fallback_payload["refreshNeeded"] = True
            fallback_payload["errors"] = [str(error)]
            return jsonify({"success": True, "data": fallback_payload})
        return jsonify({
            "success": False,
            "message": f"지수 데이터 조회 실패: {str(error)}",
        }), 500


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
        
        params = {
            "user_id": f"eq.{user_id}",
            "exchange": f"eq.{exchange}",
            "broker_env": f"eq.{broker_env}"
        }
        records = query_supabase(auth_header, "user_api_keys", "GET", params=params)
        if not records or len(records) == 0:
            return jsonify({"success": False, "message": f"등록된 {exchange} ({broker_env}) API 키가 없습니다."}), 404

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
                secret_key=secret_key
            )
            balance = client.get_balance()
        else:
            return jsonify({"success": False, "message": f"지원하지 않는 거래소입니다: {exchange}"}), 400

        exchange_rate = 1500.0
        if exchange == "TOSS" and hasattr(client, "get_exchange_rate"):
            exchange_rate = client.get_exchange_rate()

        try:
            save_portfolio_snapshot(auth_header, user_id, balance, exchange_rate)
        except Exception:
            pass

        balance["exchange_rate"] = exchange_rate

        return jsonify({
            "success": True,
            "data": balance
        })
    except Exception as e:
        return jsonify({
            "success": False,
            "message": f"잔고 조회 실패: {str(e)}"
        }), 500
