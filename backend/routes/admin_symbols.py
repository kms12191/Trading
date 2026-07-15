from flask import Blueprint, jsonify, request

from backend.routes.admin_users import _verify_admin
from backend.services.error_message_service import format_error_payload
from backend.services.symbol_reconciliation_service import (
    deactivate_symbols,
    delete_symbols,
    get_latest_symbol_reconciliation,
    restore_symbols,
    run_symbol_reconciliation,
)


admin_symbols_bp = Blueprint("admin_symbols", __name__)


def _require_admin():
    return _verify_admin(request.headers.get("Authorization"))


def _json_error(error, title, status_code=400):
    return jsonify(format_error_payload(error, title)), status_code


def _request_symbols():
    body = request.get_json(silent=True) or {}
    symbols = body.get("symbols") or []
    if isinstance(symbols, str):
        symbols = [symbols]
    return [str(symbol).strip().upper() for symbol in symbols if str(symbol or "").strip()]


@admin_symbols_bp.route("/api/admin/market-symbols/reconciliation/latest", methods=["GET"])
def get_latest_reconciliation():
    try:
        _require_admin()
        return jsonify({"success": True, "data": get_latest_symbol_reconciliation()})
    except Exception as error:
        return _json_error(error, "종목 마스터 정리 결과 조회 실패", 403 if isinstance(error, PermissionError) else 400)


@admin_symbols_bp.route("/api/admin/market-symbols/reconcile", methods=["POST"])
def reconcile_market_symbols():
    try:
        actor = _require_admin()
        body = request.get_json(silent=True) or {}
        result = run_symbol_reconciliation(
            actor_id=actor["id"],
            market_country=body.get("market_country", "ALL"),
            limit=int(body.get("limit") or 1000),
        )
        return jsonify({"success": True, "data": result})
    except Exception as error:
        return _json_error(error, "종목 마스터 스캔 실패", 403 if isinstance(error, PermissionError) else 400)


@admin_symbols_bp.route("/api/admin/market-symbols/deactivate", methods=["POST"])
def deactivate_market_symbols():
    try:
        _require_admin()
        body = request.get_json(silent=True) or {}
        symbols = _request_symbols()
        if not symbols:
            raise ValueError("비활성화할 종목을 선택해 주세요.")
        result = deactivate_symbols(symbols, body.get("reason") or "관리자 종목 마스터 정리")
        return jsonify({"success": True, "data": result})
    except Exception as error:
        return _json_error(error, "종목 비활성화 실패", 403 if isinstance(error, PermissionError) else 400)


@admin_symbols_bp.route("/api/admin/market-symbols/delete", methods=["POST"])
def delete_market_symbols():
    try:
        _require_admin()
        body = request.get_json(silent=True) or {}
        symbols = _request_symbols()
        if not symbols:
            raise ValueError("삭제할 종목을 선택해 주세요.")
        result = delete_symbols(symbols, body.get("source_table") or "kis_stock_turnover_latest")
        return jsonify({"success": True, "data": result})
    except Exception as error:
        return _json_error(error, "종목 삭제 실패", 403 if isinstance(error, PermissionError) else 400)


@admin_symbols_bp.route("/api/admin/market-symbols/restore", methods=["POST"])
def restore_market_symbols():
    try:
        _require_admin()
        symbols = _request_symbols()
        if not symbols:
            raise ValueError("복구할 종목을 선택해 주세요.")
        result = restore_symbols(symbols)
        return jsonify({"success": True, "data": result})
    except Exception as error:
        return _json_error(error, "종목 복구 실패", 403 if isinstance(error, PermissionError) else 400)
