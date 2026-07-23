import hashlib
import hmac
import os
from pathlib import Path

from flask import Blueprint, jsonify, request
from backend.services.error_message_service import format_error_payload
from backend.services.ai_fund_portfolio import apply_risk_preset, normalize_target_allocations
from backend.services.ai_fund_performance_service import AiFundPerformanceService
from backend.services.ai_fund_operations import AiFundOperationsService
from backend.services.ai_fund_strategy_backtest import run_strategy_backtest
from backend.services.ai_fund_trade_intent import TradeIntent, TradeIntentValidationError
from backend.services.ai_fund_stock_selection import AiFundStockSelectionService
from backend.services.ai_fund_crypto_selection import AiFundCryptoSelectionService
from backend.services.ai_fund_crypto_short_performance import AiFundCryptoShortPerformanceService
from backend.services.supabase_client import safe_query_supabase_as_service_role
from backend.services.admin_ai_managed_trader import AdminAiManagedTrader

admin_ai_fund_bp = Blueprint("admin_ai_fund", __name__)
PROJECT_ROOT = Path(__file__).resolve().parents[2]
CRYPTO_PREDICTIONS_PATH = PROJECT_ROOT / "ml" / "data" / "processed" / "crypto_predictions_lgbm_v10.csv"


def _is_valid_webhook_signature(raw_body: bytes, signature: str | None) -> bool:
    secret = os.getenv("AI_FUND_WEBHOOK_SECRET", "")
    if not secret or not signature:
        return False
    expected = hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature.strip())


def _extract_bearer_token(auth_header: str | None) -> str:
    if not auth_header or not auth_header.startswith("Bearer "):
        raise ValueError("로그인이 필요합니다.")
    token = auth_header.split(" ", 1)[1].strip()
    if not token:
        raise ValueError("로그인이 필요합니다.")
    return token


def _valid_strategy_config(strategy_type: str, config: object) -> bool:
    if not isinstance(config, dict):
        return False
    required_by_type = {
        "DCA": ("reference_price", "trigger_drawdown_pct", "entry_amount", "max_entries"),
        "GRID": ("lower_price", "upper_price", "grid_count", "order_amount"),
    }
    required = required_by_type.get(strategy_type)
    if not required:
        return False
    try:
        return all(float(config.get(key) or 0) > 0 for key in required)
    except (TypeError, ValueError):
        return False


def _normalize_toss_stock_selection_config(data: dict) -> None:
    """토스 주식 자동선별 설정을 검증하고 저장 가능한 값으로 정규화한다."""
    scope = str(data.get("asset_scope") or "ALL").upper()
    if scope not in {"KR", "US", "ALL"}:
        raise ValueError("asset_scope는 KR, US, ALL 중 하나여야 합니다.")
    try:
        max_open_positions = int(data.get("max_open_positions") or 3)
        refresh_minutes = int(data.get("selection_refresh_minutes") or 60)
    except (TypeError, ValueError) as error:
        raise ValueError("최대 보유 종목 수와 갱신 주기는 정수여야 합니다.") from error
    if not 1 <= max_open_positions <= 20:
        raise ValueError("max_open_positions는 1에서 20 사이여야 합니다.")
    if not 5 <= refresh_minutes <= 1440:
        raise ValueError("selection_refresh_minutes는 5에서 1440 사이여야 합니다.")

    if scope == "KR":
        kr_allocation_pct, us_allocation_pct = 100.0, 0.0
    elif scope == "US":
        kr_allocation_pct, us_allocation_pct = 0.0, 100.0
    else:
        try:
            kr_allocation_pct = float(data.get("kr_allocation_pct", 50.0))
            us_allocation_pct = float(data.get("us_allocation_pct", 50.0))
        except (TypeError, ValueError) as error:
            raise ValueError("시장별 배분 비율은 숫자여야 합니다.") from error
        if kr_allocation_pct < 0 or us_allocation_pct < 0 or abs(kr_allocation_pct + us_allocation_pct - 100.0) > 0.001:
            raise ValueError("국내·미국 시장 배분 비율의 합계는 100이어야 합니다.")

    data.update(
        asset_scope=scope,
        max_open_positions=max_open_positions,
        selection_refresh_minutes=refresh_minutes,
        kr_allocation_pct=kr_allocation_pct,
        us_allocation_pct=us_allocation_pct,
    )


@admin_ai_fund_bp.route("/api/admin/ai-fund/configs", methods=["GET"])
def get_ai_fund_configs():
    try:
        auth_header = request.headers.get("Authorization")
        _extract_bearer_token(auth_header)
        
        configs = safe_query_supabase_as_service_role("admin_ai_fund_configs") or []
        return jsonify({"success": True, "configs": configs}), 200
    except ValueError as val_err:
        return jsonify(format_error_payload(val_err, "인증 에러")), 401
    except Exception as err:
        return jsonify(format_error_payload(err, "설정 조회 에러")), 500


@admin_ai_fund_bp.route("/api/admin/ai-fund/strategies", methods=["GET"])
def get_ai_fund_strategies():
    try:
        _extract_bearer_token(request.headers.get("Authorization"))
        user_id = str(request.args.get("user_id") or "").strip()
        exchange_type = str(request.args.get("exchange_type") or "").lower().strip()
        if not user_id or not exchange_type:
            return jsonify(format_error_payload(ValueError("user_id와 exchange_type은 필수입니다."), "입력값 에러")), 400
        strategies = safe_query_supabase_as_service_role(
            "ai_fund_strategies",
            params={
                "user_id": f"eq.{user_id}",
                "exchange_type": f"eq.{exchange_type}",
                "order": "created_at.desc",
            },
        ) or []
        return jsonify({"success": True, "strategies": strategies}), 200
    except ValueError as error:
        return jsonify(format_error_payload(error, "인증 에러")), 401
    except Exception as error:
        return jsonify(format_error_payload(error, "전략 조회 에러")), 500


@admin_ai_fund_bp.route("/api/admin/ai-fund/strategies", methods=["POST"])
def create_ai_fund_strategy():
    try:
        _extract_bearer_token(request.headers.get("Authorization"))
        payload = request.get_json(silent=True)
        if not isinstance(payload, dict):
            return jsonify(format_error_payload(ValueError("전략 입력값이 필요합니다."), "입력값 에러")), 400
        user_id = str(payload.get("user_id") or "").strip()
        exchange_type = str(payload.get("exchange_type") or "").lower().strip()
        strategy_type = str(payload.get("strategy_type") or "").upper()
        symbol = str(payload.get("symbol") or "").upper().strip()
        config = payload.get("config")
        if not user_id or not exchange_type or not symbol or not _valid_strategy_config(strategy_type, config):
            return jsonify(format_error_payload(
                ValueError("전략 종류와 필수 설정값을 확인해 주세요."),
                "입력값 에러",
            )), 400
        result = safe_query_supabase_as_service_role(
            "ai_fund_strategies",
            method="POST",
            json_data={
                "user_id": user_id,
                "exchange_type": exchange_type,
                "strategy_type": strategy_type,
                "symbol": symbol,
                "status": "PAUSED",
                "config": config,
                "state": {},
            },
            extra_headers={"Prefer": "return=representation"},
        )
        return jsonify({"success": True, "strategy": result}), 201
    except ValueError as error:
        return jsonify(format_error_payload(error, "인증 에러")), 401
    except Exception as error:
        return jsonify(format_error_payload(error, "전략 생성 에러")), 500


@admin_ai_fund_bp.route("/api/admin/ai-fund/strategies/<strategy_id>/status", methods=["POST"])
def update_ai_fund_strategy_status(strategy_id: str):
    try:
        _extract_bearer_token(request.headers.get("Authorization"))
        payload = request.get_json(silent=True) or {}
        status = str(payload.get("status") or "").upper()
        if status not in {"RUNNING", "PAUSED", "HALTED"}:
            return jsonify(format_error_payload(ValueError("지원하지 않는 전략 상태입니다."), "입력값 에러")), 400
        result = safe_query_supabase_as_service_role(
            f"ai_fund_strategies?id=eq.{strategy_id}",
            method="PATCH",
            json_data={"status": status},
        )
        return jsonify({"success": True, "strategy": result}), 200
    except ValueError as error:
        return jsonify(format_error_payload(error, "인증 에러")), 401
    except Exception as error:
        return jsonify(format_error_payload(error, "전략 상태 변경 에러")), 500


@admin_ai_fund_bp.route("/api/admin/ai-fund/intents", methods=["GET"])
def get_ai_fund_trade_intents():
    try:
        _extract_bearer_token(request.headers.get("Authorization"))
        user_id = str(request.args.get("user_id") or "").strip()
        exchange_type = str(request.args.get("exchange_type") or "").lower().strip()
        status = str(request.args.get("status") or "PENDING").upper()
        if not user_id or not exchange_type:
            return jsonify(format_error_payload(ValueError("user_id와 exchange_type은 필수입니다."), "입력값 에러")), 400
        intents = safe_query_supabase_as_service_role(
            "ai_fund_trade_intents",
            params={
                "user_id": f"eq.{user_id}",
                "exchange_type": f"eq.{exchange_type}",
                "status": f"eq.{status}",
                "order": "created_at.desc",
                "limit": "100",
            },
        ) or []
        return jsonify({"success": True, "intents": intents}), 200
    except ValueError as error:
        return jsonify(format_error_payload(error, "인증 에러")), 401
    except Exception as error:
        return jsonify(format_error_payload(error, "주문 의도 조회 에러")), 500


@admin_ai_fund_bp.route("/api/admin/ai-fund/configs", methods=["POST"])
def upsert_ai_fund_config():
    try:
        auth_header = request.headers.get("Authorization")
        _extract_bearer_token(auth_header)
        
        data = dict(request.json or {})
        user_id = data.get("user_id")
        exchange_type = str(data.get("exchange_type", "coinone")).lower()
        
        if not user_id:
            return jsonify(format_error_payload(ValueError("user_id는 필수입니다."), "입력값 에러")), 400

        if exchange_type == "toss":
            try:
                _normalize_toss_stock_selection_config(data)
            except ValueError as error:
                return jsonify(format_error_payload(error, "입력값 에러")), 400

        try:
            data = apply_risk_preset(data)
        except ValueError as error:
            return jsonify(format_error_payload(error, "입력값 에러")), 400
        operation_mode = str(data.get("operation_mode") or "PAPER").upper()
        if operation_mode not in {"PAPER", "CANARY", "LIVE"}:
            return jsonify(format_error_payload(
                ValueError("operation_mode는 PAPER, CANARY, LIVE 중 하나여야 합니다."),
                "입력값 에러",
            )), 400
        data["exchange_type"] = exchange_type
        data["operation_mode"] = operation_mode
        if "target_allocations" in data:
            normalized_targets = normalize_target_allocations(data["target_allocations"])
            if not normalized_targets:
                return jsonify(format_error_payload(
                    ValueError("target_allocations는 양수 비중의 합계가 100%여야 합니다."),
                    "입력값 에러",
                )), 400
            data["target_allocations"] = normalized_targets
        if "rebalance_threshold_pct" in data:
            try:
                rebalance_threshold_pct = float(data["rebalance_threshold_pct"])
            except (TypeError, ValueError):
                rebalance_threshold_pct = -1.0
            if not 0 <= rebalance_threshold_pct <= 100:
                return jsonify(format_error_payload(
                    ValueError("rebalance_threshold_pct는 0에서 100 사이여야 합니다."),
                    "입력값 에러",
                )), 400
            data["rebalance_threshold_pct"] = rebalance_threshold_pct
        if operation_mode == "CANARY":
            try:
                canary_max_order_amount = float(data.get("canary_max_order_amount") or 0.0)
            except (TypeError, ValueError):
                canary_max_order_amount = 0.0
            if canary_max_order_amount <= 0:
                return jsonify(format_error_payload(
                    ValueError("CANARY 모드에는 0보다 큰 canary_max_order_amount가 필요합니다."),
                    "입력값 에러",
                )), 400
            data["canary_max_order_amount"] = canary_max_order_amount
        elif "canary_max_order_amount" in data:
            data["canary_max_order_amount"] = None

        res = safe_query_supabase_as_service_role(
            "admin_ai_fund_configs",
            method="POST",
            json_data=data,
            params={"on_conflict": "user_id,exchange_type"},
            extra_headers={"Prefer": "resolution=merge-duplicates"}
        )

        return jsonify({"success": True, "config": res}), 200
    except ValueError as val_err:
        return jsonify(format_error_payload(val_err, "인증 에러")), 401
    except Exception as err:
        return jsonify(format_error_payload(err, "설정 저장 에러")), 500


@admin_ai_fund_bp.route("/api/admin/ai-fund/stock-candidates", methods=["GET"])
def get_ai_fund_stock_candidates():
    try:
        _extract_bearer_token(request.headers.get("Authorization"))
        user_id = str(request.args.get("user_id") or "").strip()
        if not user_id:
            return jsonify(format_error_payload(ValueError("user_id는 필수입니다."), "입력값 에러")), 400
        configs = safe_query_supabase_as_service_role(
            "admin_ai_fund_configs",
            params={"user_id": f"eq.{user_id}", "exchange_type": "eq.toss", "limit": "1"},
        ) or []
        if not configs:
            return jsonify(format_error_payload(ValueError("토스 주식 자동선별 설정이 없습니다."), "설정 조회 에러")), 404
        config = configs[0]
        trader = AdminAiManagedTrader(user_id=user_id, exchange_type="toss")
        held_symbols = {
            str(position.get("symbol") or "").upper()
            for position in trader.list_open_positions()
            if position.get("symbol")
        }
        selection_service = AiFundStockSelectionService()
        candidates = selection_service.select_candidates(config, held_symbols)
        availability = selection_service.get_availability(config)
        return jsonify({"success": True, "candidates": candidates, "availability": availability}), 200
    except ValueError as error:
        return jsonify(format_error_payload(error, "인증 에러")), 401
    except Exception as error:
        return jsonify(format_error_payload(error, "주식 후보 조회 에러")), 500


@admin_ai_fund_bp.route("/api/admin/ai-fund/crypto-candidates", methods=["GET"])
def get_ai_fund_crypto_candidates():
    try:
        _extract_bearer_token(request.headers.get("Authorization"))
        user_id = str(request.args.get("user_id") or "").strip()
        exchange_type = str(request.args.get("exchange_type") or "").lower().strip()
        if not user_id or exchange_type not in {"coinone", "binance"}:
            return jsonify(format_error_payload(ValueError("user_id와 코인 거래소가 필요합니다."), "입력값 에러")), 400
        configs = safe_query_supabase_as_service_role(
            "admin_ai_fund_configs",
            params={"user_id": f"eq.{user_id}", "exchange_type": f"eq.{exchange_type}", "limit": "1"},
        ) or []
        min_confidence = float((configs[0] if configs else {}).get("min_signal_confidence") or 0.75)
        snapshot = AiFundCryptoSelectionService(CRYPTO_PREDICTIONS_PATH).get_snapshot(min_confidence)
        return jsonify({"success": True, "exchange_type": exchange_type, **snapshot}), 200
    except ValueError as error:
        return jsonify(format_error_payload(error, "입력값 에러")), 400
    except Exception as error:
        return jsonify(format_error_payload(error, "코인 후보 조회 에러")), 500


@admin_ai_fund_bp.route("/api/admin/ai-fund/crypto-short-performance", methods=["GET"])
def get_ai_fund_crypto_short_performance():
    try:
        _extract_bearer_token(request.headers.get("Authorization"))
        snapshot = AiFundCryptoShortPerformanceService().get_snapshot()
        return jsonify({"success": True, **snapshot}), 200
    except ValueError as error:
        return jsonify(format_error_payload(error, "인증 에러")), 401
    except Exception as error:
        return jsonify(format_error_payload(error, "숏 모델 성능 조회 에러")), 500


@admin_ai_fund_bp.route("/api/admin/ai-fund/logs", methods=["GET"])
def get_ai_fund_trade_logs():
    try:
        auth_header = request.headers.get("Authorization")
        _extract_bearer_token(auth_header)
        
        logs = safe_query_supabase_as_service_role(
            "admin_ai_trade_logs",
            params={"order": "created_at.desc", "limit": "50"}
        ) or []
        return jsonify({"success": True, "logs": logs}), 200
    except ValueError as val_err:
        return jsonify(format_error_payload(val_err, "인증 에러")), 401
    except Exception as err:
        return jsonify(format_error_payload(err, "트레이딩 로그 조회 에러")), 500


@admin_ai_fund_bp.route("/api/admin/ai-fund/performance", methods=["GET"])
def get_ai_fund_performance():
    try:
        _extract_bearer_token(request.headers.get("Authorization"))
        user_id = str(request.args.get("user_id") or "").strip()
        exchange_type = str(request.args.get("exchange_type") or "coinone").lower()
        if not user_id:
            return jsonify(format_error_payload(ValueError("user_id는 필수입니다."), "입력값 에러")), 400
        if exchange_type != "coinone":
            return jsonify(format_error_payload(
                ValueError("현재 성과 현재가 조회는 coinone만 지원합니다."),
                "입력값 에러",
            )), 400
        from backend.services.admin_ai_fund_trading_scheduler import _get_current_price_coinone

        performance = AiFundPerformanceService().get_report(
            user_id,
            exchange_type,
            _get_current_price_coinone,
        )
        return jsonify({"success": True, "performance": performance}), 200
    except ValueError as error:
        return jsonify(format_error_payload(error, "인증 에러")), 401
    except Exception as error:
        return jsonify(format_error_payload(error, "성과 조회 에러")), 500


@admin_ai_fund_bp.route("/api/admin/ai-fund/operations/<config_id>/resume", methods=["POST"])
def resume_ai_fund_operations(config_id: str):
    try:
        _extract_bearer_token(request.headers.get("Authorization"))
        AiFundOperationsService().resume(config_id)
        return jsonify({"success": True, "message": "AI 위탁운용을 재개했습니다."}), 200
    except ValueError as error:
        return jsonify(format_error_payload(error, "인증 에러")), 401
    except Exception as error:
        return jsonify(format_error_payload(error, "운영 재개 에러")), 500


@admin_ai_fund_bp.route("/api/admin/ai-fund/operations/<config_id>/events", methods=["GET"])
def get_ai_fund_operation_events(config_id: str):
    try:
        _extract_bearer_token(request.headers.get("Authorization"))
        events = safe_query_supabase_as_service_role(
            "ai_fund_operation_events",
            params={
                "config_id": f"eq.{config_id}",
                "order": "created_at.desc",
                "limit": "100",
            },
        ) or []
        return jsonify({"success": True, "events": events}), 200
    except ValueError as error:
        return jsonify(format_error_payload(error, "인증 에러")), 401
    except Exception as error:
        return jsonify(format_error_payload(error, "운영 이벤트 조회 에러")), 500


@admin_ai_fund_bp.route("/api/admin/ai-fund/kill-switch", methods=["POST"])
def execute_kill_switch():
    try:
        auth_header = request.headers.get("Authorization")
        _extract_bearer_token(auth_header)
        
        data = request.json or {}
        user_id = data.get("user_id", "00000000-0000-0000-0000-000000000000")
        exchange_type = data.get("exchange_type", "coinone")
        
        trader = AdminAiManagedTrader(user_id=user_id, exchange_type=exchange_type)
        killed = trader.emergency_kill_switch()
        
        return jsonify({"success": killed, "message": "긴급 셧다운 실행 완료" if killed else "셧다운 실패"}), 200
    except ValueError as val_err:
        return jsonify(format_error_payload(val_err, "인증 에러")), 401
    except Exception as err:
        return jsonify(format_error_payload(err, "긴급 셧다운 에러")), 500


@admin_ai_fund_bp.route("/api/admin/ai-fund/webhooks/intents", methods=["POST"])
def receive_ai_fund_webhook_intent():
    raw_body = request.get_data(cache=True)
    if not _is_valid_webhook_signature(raw_body, request.headers.get("X-AI-Fund-Signature")):
        return jsonify(format_error_payload(ValueError("웹훅 서명이 올바르지 않습니다."), "인증 에러")), 401
    try:
        payload = request.get_json(silent=True)
        if not isinstance(payload, dict):
            raise TradeIntentValidationError("웹훅 본문은 JSON 객체여야 합니다.")
        user_id = str(payload.get("user_id") or "").strip()
        exchange_type = str(payload.get("exchange_type") or "").lower().strip()
        if not user_id or not exchange_type:
            raise TradeIntentValidationError("user_id와 exchange_type은 필수입니다.")
        intent = TradeIntent.from_payload(payload)
        result = safe_query_supabase_as_service_role(
            "ai_fund_trade_intents",
            method="POST",
            json_data={
                "user_id": user_id,
                "exchange_type": exchange_type,
                "strategy_id": intent.strategy_id,
                "source": intent.source,
                "source_id": intent.source_id,
                "idempotency_key": intent.idempotency_key,
                "symbol": intent.symbol,
                "side": intent.side,
                "confidence": intent.confidence,
                "expires_at": intent.expires_at.isoformat() if intent.expires_at else None,
                "status": "PENDING",
                "payload": payload,
            },
            extra_headers={"Prefer": "resolution=ignore-duplicates,return=representation"},
        )
        return jsonify({"success": True, "intent": result}), 202
    except TradeIntentValidationError as error:
        return jsonify(format_error_payload(error, "입력값 에러")), 400
    except Exception as error:
        return jsonify(format_error_payload(error, "웹훅 의도 저장 에러")), 500


@admin_ai_fund_bp.route("/api/admin/ai-fund/intents/<intent_id>/<action>", methods=["POST"])
def update_ai_fund_trade_intent_status(intent_id: str, action: str):
    try:
        _extract_bearer_token(request.headers.get("Authorization"))
        status_by_action = {"approve": "APPROVED", "reject": "REJECTED"}
        status = status_by_action.get(action.lower())
        if not status:
            return jsonify(format_error_payload(ValueError("지원하지 않는 주문 의도 처리입니다."), "입력값 에러")), 400
        result = safe_query_supabase_as_service_role(
            f"ai_fund_trade_intents?id=eq.{intent_id}&status=eq.PENDING",
            method="PATCH",
            json_data={"status": status},
        )
        return jsonify({"success": True, "intent": result}), 200
    except ValueError as error:
        return jsonify(format_error_payload(error, "인증 에러")), 401
    except Exception as error:
        return jsonify(format_error_payload(error, "주문 의도 상태 변경 에러")), 500


@admin_ai_fund_bp.route("/api/admin/ai-fund/strategies/<strategy_id>/backtests", methods=["POST"])
def run_ai_fund_strategy_backtest(strategy_id: str):
    try:
        _extract_bearer_token(request.headers.get("Authorization"))
        payload = request.get_json(silent=True)
        if not isinstance(payload, dict) or not isinstance(payload.get("candles"), list):
            return jsonify(format_error_payload(ValueError("candles 배열은 필수입니다."), "입력값 에러")), 400
        candles = payload["candles"]
        if not candles or len(candles) > 10000:
            return jsonify(format_error_payload(ValueError("캔들은 1건 이상 10,000건 이하여야 합니다."), "입력값 에러")), 400
        try:
            fee_bps = float(payload.get("fee_bps") or 0.0)
        except (TypeError, ValueError):
            return jsonify(format_error_payload(ValueError("fee_bps 값이 올바르지 않습니다."), "입력값 에러")), 400
        if fee_bps < 0:
            return jsonify(format_error_payload(ValueError("fee_bps는 0 이상이어야 합니다."), "입력값 에러")), 400

        strategies = safe_query_supabase_as_service_role(
            "ai_fund_strategies",
            params={"id": f"eq.{strategy_id}", "limit": "1"},
        ) or []
        if not strategies:
            return jsonify(format_error_payload(ValueError("전략을 찾을 수 없습니다."), "조회 에러")), 404
        strategy = strategies[0]
        result = run_strategy_backtest(strategy, candles, fee_bps=fee_bps)
        stored = safe_query_supabase_as_service_role(
            "ai_fund_strategy_backtests",
            method="POST",
            json_data={
                "strategy_id": strategy_id,
                "user_id": strategy["user_id"],
                "exchange_type": strategy["exchange_type"],
                "strategy_type": strategy["strategy_type"],
                "symbol": strategy["symbol"],
                "candle_count": len(candles),
                "fee_bps": fee_bps,
                "result": result,
            },
        )
        return jsonify({"success": True, "backtest": stored, "result": result}), 201
    except ValueError as error:
        return jsonify(format_error_payload(error, "인증 에러")), 401
    except Exception as error:
        return jsonify(format_error_payload(error, "전략 백테스트 실행 에러")), 500
