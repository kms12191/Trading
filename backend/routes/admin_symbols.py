from flask import Blueprint, jsonify, request

from backend.routes.admin_users import _verify_admin
from backend.services.error_message_service import format_error_payload
from backend.services.symbol_reconciliation_service import (
    deactivate_symbols,
    delete_symbols,
    get_latest_symbol_reconciliation,
    restore_symbols,
    run_symbol_reconciliation,
    update_stock_master_symbol,
)
from backend.services.crypto_asset_service import (
    CryptoAssetPatch,
    list_crypto_assets,
    patch_crypto_asset,
)
from backend.services.crypto_asset_sync_service import sync_crypto_assets


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


def _parse_aliases(value):
    if isinstance(value, str):
        return tuple(alias.strip() for alias in value.split(",") if alias.strip())
    if isinstance(value, list):
        return tuple(str(alias).strip() for alias in value if str(alias or "").strip())
    return None


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


@admin_symbols_bp.route("/api/admin/crypto-symbols", methods=["GET"])
def list_admin_crypto_symbols():
    try:
        _require_admin()
        rows = list_crypto_assets(
            query=request.args.get("query", ""),
            exchange=request.args.get("exchange", "ALL"),
            tradable=request.args.get("tradable", "ALL"),
            blocked=request.args.get("blocked", "ALL"),
            limit=int(request.args.get("limit") or 300),
        )
        return jsonify({"success": True, "data": {"items": rows}})
    except Exception as error:
        return _json_error(error, "코인 종목 마스터 조회 실패", 403 if isinstance(error, PermissionError) else 400)


@admin_symbols_bp.route("/api/admin/crypto-symbols/sync", methods=["POST"])
def sync_admin_crypto_symbols():
    try:
        _require_admin()
        return jsonify({"success": True, "data": sync_crypto_assets()})
    except Exception as error:
        return _json_error(error, "코인 종목 마스터 동기화 실패", 403 if isinstance(error, PermissionError) else 400)


@admin_symbols_bp.route("/api/admin/crypto-symbols/<base_symbol>", methods=["PATCH"])
def update_admin_crypto_symbol(base_symbol):
    try:
        _require_admin()
        body = request.get_json(silent=True) or {}
        updated = patch_crypto_asset(
            base_symbol,
            CryptoAssetPatch(
                display_name_ko=body.get("display_name_ko"),
                display_name_en=body.get("display_name_en"),
                aliases=_parse_aliases(body.get("aliases")),
                default_exchange=body.get("default_exchange"),
                is_visible=body.get("is_visible") if "is_visible" in body else None,
                admin_trading_blocked=body.get("admin_trading_blocked") if "admin_trading_blocked" in body else None,
                admin_block_reason=body.get("admin_block_reason"),
                admin_note=body.get("admin_note"),
                coinone_symbol=body.get("coinone_symbol"),
                binance_symbol=body.get("binance_symbol"),
            ),
        )
        return jsonify({"success": True, "data": updated})
    except Exception as error:
        return _json_error(error, "코인 종목 마스터 수정 실패", 403 if isinstance(error, PermissionError) else 400)


@admin_symbols_bp.route("/api/admin/market-symbols/<symbol>", methods=["PATCH"])
def update_admin_market_symbol(symbol):
    try:
        _require_admin()
        body = request.get_json(silent=True) or {}
        updated = update_stock_master_symbol(symbol, body)
        return jsonify({"success": True, "data": updated})
    except Exception as error:
        return _json_error(error, "주식 종목 마스터 수정 실패", 403 if isinstance(error, PermissionError) else 400)
