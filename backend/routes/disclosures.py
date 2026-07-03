import os

from flask import Blueprint, current_app, jsonify, request

from backend.services.error_message_service import format_error_payload


disclosures_bp = Blueprint("disclosures", __name__)


@disclosures_bp.route("/api/disclosures", methods=["GET"])
def get_disclosures():
    symbol = request.args.get("symbol", "")
    query = request.args.get("query", "")
    limit = int(request.args.get("limit", 10))
    offset = int(request.args.get("offset", 0))

    try:
        repository = current_app.dart_repository
        items = repository.list_disclosures(
            symbol=symbol,
            query=query,
            limit=limit,
            offset=offset,
        )
        total_count = repository.count_disclosures(symbol=symbol, query=query)
        return jsonify(
            {
                "success": True,
                "data": {
                    "items": items,
                    "totalCount": total_count,
                    "limit": limit,
                    "offset": offset,
                    "symbol": symbol,
                    "query": query,
                },
            }
        )
    except Exception as error:
        return jsonify(format_error_payload(error, "공시 목록 조회 실패")), 500


@disclosures_bp.route("/api/disclosures/sync", methods=["POST"])
def sync_disclosures():
    try:
        data = request.get_json(silent=True) or {}
        mode = str(data.get("mode") or "incremental").strip().lower()
        service = current_app.dart_ingest_service
        if mode in {"backfill", "corp_codes"} and not _is_admin_sync_request():
            return jsonify({"success": False, "message": "Admin token is required for this disclosure sync mode."}), 403

        if mode == "backfill":
            result = service.run_backfill_recent_year()
        elif mode == "corp_codes":
            result = service.sync_corp_codes_from_xml(data.get("xml_path"))
        else:
            result = service.run_incremental()

        return jsonify({"success": True, "data": result})
    except Exception as error:
        return jsonify(format_error_payload(error, "공시 수집 실패")), 500


@disclosures_bp.route("/api/disclosures/<rcept_no>/analysis", methods=["GET"])
def get_disclosure_analysis(rcept_no):
    try:
        service = current_app.dart_analysis_service
        result = service.ensure_analysis(rcept_no)
        return jsonify({"success": True, "data": result})
    except Exception as error:
        return jsonify(format_error_payload(error, "공시 요약 분석 실패")), 500


def _is_admin_sync_request() -> bool:
    admin_token = os.getenv("DART_SYNC_ADMIN_TOKEN") or os.getenv("MARKET_SYNC_ADMIN_TOKEN", "")
    if not admin_token:
        return False
    provided_token = request.headers.get("X-Admin-Token", "")
    return provided_token == admin_token
