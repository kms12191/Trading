import uuid
from datetime import datetime, timedelta, timezone
from flask import Blueprint, request, jsonify, current_app

from backend.services.auth_service import get_user_id_from_header
from backend.services.supabase_client import query_supabase
from backend.services.coinone_client import CoinoneClient
from backend.services.binance_client import BinanceClient
from backend.services.error_message_service import format_error_payload

transfer_bp = Blueprint("transfer", __name__)

TAG_REQUIRED_CURRENCIES = {"XRP", "XLM", "EOS"}


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_exchange_client(auth_header: str, user_id: str, exchange: str):
    """
    사용자별 암호화 API 키를 복호화해 거래소 클라이언트를 생성합니다.
    """
    records = query_supabase(
        auth_header,
        "user_api_keys",
        "GET",
        params={
            "user_id": f"eq.{user_id}",
            "exchange": f"eq.{exchange}",
            "broker_env": "eq.REAL",
            "limit": "1",
        },
    )
    if not records:
        raise ValueError(f"{exchange} 실거래 API 키가 등록되어 있지 않습니다.")

    record = records[0]
    access_key = current_app.crypto.decrypt(record.get("encrypted_access_key"))
    secret_key = current_app.crypto.decrypt(record.get("encrypted_secret_key"))

    if exchange == "COINONE":
        return CoinoneClient(access_token=access_key, secret_key=secret_key)
    if exchange == "BINANCE":
        return BinanceClient(api_key=access_key, secret_key=secret_key)
    raise ValueError(f"지원하지 않는 거래소입니다: {exchange}")


def _get_coinone_available_qty(client: CoinoneClient, currency: str) -> float:
    """
    코인원 잔고 응답에서 출금 가능한 수량을 추출합니다.
    """
    balance = client.get_balance() or {}
    normalized_currency = CoinoneClient._normalize_symbol(currency)
    for item in (balance.get("raw") or {}).get("balances", []) or []:
        if str(item.get("currency") or "").upper() != normalized_currency:
            continue
        for key in ("available", "avail", "balance"):
            try:
                return float(item.get(key) or 0)
            except (TypeError, ValueError):
                continue
    return 0.0


def _validate_withdraw_payload(data: dict) -> dict:
    currency = CoinoneClient._normalize_symbol(data.get("currency") or data.get("symbol"))
    network = str(data.get("network") or currency or "").strip().upper()
    address = str(data.get("address") or "").strip()
    secondary_address = str(data.get("secondary_address") or data.get("tag") or "").strip()

    try:
        amount = float(data.get("amount"))
    except (TypeError, ValueError):
        raise ValueError("출금 수량 포맷이 올바르지 않습니다.")

    if not currency:
        raise ValueError("출금 코인을 선택해 주세요.")
    if amount <= 0:
        raise ValueError("출금 수량은 0보다 커야 합니다.")
    if not address:
        raise ValueError("바이낸스 입금 주소가 필요합니다.")
    if currency in TAG_REQUIRED_CURRENCIES and not secondary_address:
        raise ValueError(f"{currency} 출금에는 Destination Tag/Memo가 필수입니다.")
    if currency in {"XRP", "XLM"} and secondary_address and not secondary_address.isdigit():
        raise ValueError(f"{currency} Destination Tag/Memo는 숫자여야 합니다.")

    return {
        "currency": currency,
        "network": network,
        "amount": amount,
        "address": address,
        "secondary_address": secondary_address,
    }


def _build_precheck(auth_header: str, user_id: str, data: dict) -> dict:
    payload = _validate_withdraw_payload(data)
    coinone_client = _load_exchange_client(auth_header, user_id, "COINONE")
    binance_client = _load_exchange_client(auth_header, user_id, "BINANCE")

    available_qty = _get_coinone_available_qty(coinone_client, payload["currency"])
    if payload["amount"] > available_qty:
        raise ValueError(f"출금 가능 수량을 초과했습니다. 가능 수량: {available_qty:g} {payload['currency']}")

    deposit_address = binance_client.get_deposit_address(
        payload["currency"],
        network=payload["network"],
        amount=payload["amount"],
    )
    expected_address = str(deposit_address.get("address") or "").strip()
    expected_tag = str(deposit_address.get("tag") or "").strip()
    address_matches = bool(expected_address) and expected_address == payload["address"]
    tag_matches = (not expected_tag and not payload["secondary_address"]) or expected_tag == payload["secondary_address"]

    warnings = []
    if expected_address and not address_matches:
        warnings.append("입력 주소가 바이낸스 API에서 조회한 입금 주소와 다릅니다.")
    if expected_tag and not tag_matches:
        warnings.append("입력 Destination Tag/Memo가 바이낸스 API 조회값과 다릅니다.")
    if payload["currency"] in TAG_REQUIRED_CURRENCIES:
        warnings.append("Destination Tag/Memo 오입력 시 자산을 잃을 수 있습니다.")

    return {
        **payload,
        "available_qty": available_qty,
        "binance_deposit_address": expected_address,
        "binance_deposit_tag": expected_tag,
        "address_matches_binance": address_matches,
        "tag_matches_binance": tag_matches,
        "warnings": warnings,
        "checked_at": _utc_now_iso(),
    }


def _insert_transfer_proposal(auth_header: str, user_id: str, precheck: dict, status: str, raw_request: dict):
    proposal_id = str(uuid.uuid4())
    payload = {
        "id": proposal_id,
        "user_id": user_id,
        "from_exchange": "COINONE",
        "to_exchange": "BINANCE",
        "currency": precheck["currency"],
        "network": precheck["network"],
        "amount": precheck["amount"],
        "address": precheck["address"],
        "secondary_address": precheck.get("secondary_address") or None,
        "status": status,
        "raw_request": raw_request,
        "precheck_payload": precheck,
    }
    query_supabase(auth_header, "asset_transfer_proposals", "POST", json_data=payload)
    return proposal_id


def _patch_transfer_proposal(auth_header: str, proposal_id: str, payload: dict):
    query_supabase(
        auth_header,
        f"asset_transfer_proposals?id=eq.{proposal_id}",
        "PATCH",
        json_data={**payload, "updated_at": _utc_now_iso()},
    )


def _match_binance_deposit(row: dict, history: list[dict]) -> dict | None:
    currency = str(row.get("currency") or "").upper()
    address = str(row.get("address") or "").strip()
    secondary_address = str(row.get("secondary_address") or "").strip()
    amount = float(row.get("amount") or 0)

    for item in history:
        item_coin = str(item.get("coin") or "").upper()
        item_address = str(item.get("address") or "").strip()
        item_tag = str(item.get("addressTag") or "").strip()
        try:
            item_amount = float(item.get("amount") or 0)
        except (TypeError, ValueError):
            item_amount = 0

        if item_coin != currency:
            continue
        if item_address != address:
            continue
        if secondary_address and item_tag != secondary_address:
            continue
        if amount > 0 and abs(item_amount - amount) > max(0.000001, amount * 0.0001):
            continue
        return item
    return None


@transfer_bp.route("/api/transfer/withdraw/precheck", methods=["POST"])
def precheck_withdrawal():
    auth_header = request.headers.get("Authorization")
    if not auth_header:
        return jsonify({"success": False, "message": "인증 헤더가 누락되었습니다."}), 401

    try:
        user_id, _ = get_user_id_from_header(auth_header)
        precheck = _build_precheck(auth_header, user_id, request.json or {})
        return jsonify({"success": True, "data": precheck})
    except ValueError as e:
        return jsonify({"success": False, "message": str(e)}), 400
    except Exception as e:
        formatted = format_error_payload(e, "출금 사전검증 실패")
        return jsonify(formatted), 500


@transfer_bp.route("/api/transfer/binance/deposit-address", methods=["GET"])
def get_binance_deposit_address():
    auth_header = request.headers.get("Authorization")
    if not auth_header:
        return jsonify({"success": False, "message": "인증 헤더가 누락되었습니다."}), 401

    try:
        user_id, _ = get_user_id_from_header(auth_header)
        currency = CoinoneClient._normalize_symbol(request.args.get("currency"))
        network = str(request.args.get("network") or currency or "").strip().upper()
        if not currency:
            return jsonify({"success": False, "message": "currency가 필요합니다."}), 400
        binance_client = _load_exchange_client(auth_header, user_id, "BINANCE")
        address = binance_client.get_deposit_address(currency, network=network)
        return jsonify({"success": True, "data": address})
    except ValueError as e:
        return jsonify({"success": False, "message": str(e)}), 400
    except Exception as e:
        formatted = format_error_payload(e, "바이낸스 입금 주소 조회 실패", exchange="BINANCE")
        return jsonify(formatted), 500


@transfer_bp.route("/api/transfer/withdraw/approve", methods=["POST"])
def approve_withdrawal():
    auth_header = request.headers.get("Authorization")
    if not auth_header:
        return jsonify({"success": False, "message": "인증 헤더가 누락되었습니다."}), 401

    data = request.json or {}
    if not data.get("confirm"):
        return jsonify({"success": False, "message": "사용자 최종 승인 확인값이 필요합니다."}), 400

    try:
        user_id, _ = get_user_id_from_header(auth_header)
        precheck = _build_precheck(auth_header, user_id, data)
        if not precheck.get("address_matches_binance"):
            raise ValueError("바이낸스 API 조회 주소와 입력 주소가 달라 출금을 차단했습니다.")
        if not precheck.get("tag_matches_binance"):
            raise ValueError("바이낸스 API 조회 Destination Tag/Memo와 입력값이 달라 출금을 차단했습니다.")
        proposal_id = _insert_transfer_proposal(auth_header, user_id, precheck, "APPROVED", data)
        coinone_client = _load_exchange_client(auth_header, user_id, "COINONE")

        result = coinone_client.withdraw_coin(
            currency=precheck["currency"],
            amount=precheck["amount"],
            address=precheck["address"],
            secondary_address=precheck.get("secondary_address"),
        )
        _patch_transfer_proposal(
            auth_header,
            proposal_id,
            {
                "status": "SUBMITTED",
                "external_transaction_id": result.get("transaction_id"),
                "raw_response": result.get("raw"),
                "submitted_at": _utc_now_iso(),
            },
        )
        return jsonify({
            "success": True,
            "message": "코인원 출금 요청이 접수되었습니다.",
            "proposal_id": proposal_id,
            "data": result,
        })
    except ValueError as e:
        return jsonify({"success": False, "message": str(e)}), 400
    except Exception as e:
        formatted = format_error_payload(e, "출금 승인 처리 실패")
        if "proposal_id" in locals():
            _patch_transfer_proposal(
                auth_header,
                proposal_id,
                {
                    "status": "FAILED",
                    "failure_reason": formatted.get("message", str(e))[:500],
                    "raw_response": {
                        "error": formatted.get("error"),
                    },
                },
            )
        return jsonify(formatted), 500


@transfer_bp.route("/api/transfer/withdraw/status", methods=["GET"])
def list_withdrawal_statuses():
    auth_header = request.headers.get("Authorization")
    if not auth_header:
        return jsonify({"success": False, "message": "인증 헤더가 누락되었습니다."}), 401

    try:
        user_id, _ = get_user_id_from_header(auth_header)
        limit = min(max(int(request.args.get("limit", 20)), 1), 100)
        rows = query_supabase(
            auth_header,
            "asset_transfer_proposals",
            "GET",
            params={
                "user_id": f"eq.{user_id}",
                "order": "created_at.desc",
                "limit": str(limit),
            },
        ) or []

        open_rows = [
            row for row in rows
            if str(row.get("status") or "").upper() in {"APPROVED", "SUBMITTED", "WITHDRAWAL_REGISTER", "WITHDRAWAL_WAIT"}
        ]
        if open_rows:
            binance_client = _load_exchange_client(auth_header, user_id, "BINANCE")
            start_time = int((datetime.now(timezone.utc) - timedelta(days=7)).timestamp() * 1000)
            for row in open_rows:
                history = binance_client.get_deposit_history(
                    coin=row.get("currency"),
                    start_time=start_time,
                    limit=100,
                )
                matched = _match_binance_deposit(row, history)
                if not matched:
                    continue
                if int(matched.get("status") or 0) == 1:
                    _patch_transfer_proposal(
                        auth_header,
                        row["id"],
                        {
                            "status": "COMPLETED",
                            "binance_deposit_payload": matched,
                            "completed_at": _utc_now_iso(),
                        },
                    )
                    row["status"] = "COMPLETED"
                    row["binance_deposit_payload"] = matched

        return jsonify({"success": True, "data": rows})
    except Exception as e:
        formatted = format_error_payload(e, "출금 상태 조회 실패")
        return jsonify(formatted), 500
