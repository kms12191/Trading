import os
from datetime import datetime, timezone

import requests
from flask import Blueprint, jsonify, request


admin_inquiries_bp = Blueprint("admin_inquiries", __name__)

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY")
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

ALLOWED_REPLY_STATUSES = {"WAITING", "COMPLETED", "NEED_MORE", "CANCELED"}


def _json_error(message, status_code):
    return jsonify({"success": False, "message": message}), status_code


def _extract_bearer_token(auth_header):
    if not auth_header or not auth_header.startswith("Bearer "):
        raise ValueError("Authorization header is required.")
    token = auth_header.split(" ", 1)[1].strip()
    if not token:
        raise ValueError("Authorization token is empty.")
    return token


def _require_supabase_config():
    if not SUPABASE_URL or not SUPABASE_ANON_KEY or not SUPABASE_SERVICE_ROLE_KEY:
        raise RuntimeError("Supabase environment variables are missing.")


def _service_headers(extra_headers=None):
    headers = {
        "apikey": SUPABASE_SERVICE_ROLE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
        "Content-Type": "application/json",
    }
    if extra_headers:
        headers.update(extra_headers)
    return headers


def _supabase_request(endpoint, method="GET", params=None, json_data=None, extra_headers=None):
    _require_supabase_config()
    url = f"{SUPABASE_URL}/rest/v1/{endpoint}"
    response = requests.request(
        method,
        url,
        headers=_service_headers(extra_headers),
        params=params,
        json=json_data,
        timeout=15,
    )
    if response.status_code not in (200, 201, 204):
        raise RuntimeError(f"Supabase request failed ({response.status_code}): {response.text}")
    if not response.text:
        return None
    return response.json()


def _verify_user(auth_header):
    _require_supabase_config()
    token = _extract_bearer_token(auth_header)

    user_response = requests.get(
        f"{SUPABASE_URL}/auth/v1/user",
        headers={
            "apikey": SUPABASE_ANON_KEY,
            "Authorization": f"Bearer {token}",
        },
        timeout=15,
    )
    if user_response.status_code != 200:
        raise PermissionError("Valid login is required.")

    user = user_response.json() or {}
    user_id = user.get("id")
    if not user_id:
        raise PermissionError("Valid login is required.")

    profiles = _supabase_request(
        "profiles",
        params={
            "select": "id,email,nickname,role",
            "id": f"eq.{user_id}",
            "limit": "1",
        },
    ) or []
    profile = profiles[0] if profiles else {}
    return {"id": user_id, "email": user.get("email") or profile.get("email"), "profile": profile}


def _load_profiles_by_id(user_ids):
    ids = sorted({str(user_id) for user_id in user_ids if user_id})
    if not ids:
        return {}

    rows = _supabase_request(
        "profiles",
        params={
            "select": "id,email,nickname",
            "id": f"in.({','.join(ids)})",
        },
    ) or []
    return {row.get("id"): row for row in rows}


def _map_inquiry(row, profiles_by_id):
    profile = profiles_by_id.get(row.get("user_id")) or {}
    return {
        "id": row.get("id"),
        "title": row.get("title"),
        "inquiryType": row.get("inquiry_type"),
        "status": row.get("status"),
        "userEmail": profile.get("email") or profile.get("nickname") or "-",
        "content": row.get("content"),
        "answer": row.get("answer") or "",
        "fileName": row.get("file_name") or "",
        "attachmentPath": row.get("attachment_path") or "",
        "mimeType": row.get("mime_type") or "",
        "fileSize": row.get("file_size"),
        "createdAt": row.get("created_at"),
        "answeredAt": row.get("answered_at"),
    }


@admin_inquiries_bp.route("/api/admin/inquiries", methods=["GET"])
def list_admin_inquiries():
    try:
        actor = _verify_user(request.headers.get("Authorization"))
        profile = actor.get("profile") or {}
        is_admin = profile.get("role") == "ADMIN"
        params = {
            "select": "id,user_id,inquiry_type,title,content,file_name,attachment_path,mime_type,file_size,status,answer,answered_at,created_at",
            "order": "created_at.desc",
        }
        if not is_admin:
            params["user_id"] = f"eq.{actor['id']}"

        rows = _supabase_request(
            "inquiries",
            params=params,
        ) or []
        profiles_by_id = _load_profiles_by_id(row.get("user_id") for row in rows)
        return jsonify({
            "success": True,
            "data": [_map_inquiry(row, profiles_by_id) for row in rows],
            "role": profile.get("role") or "USER",
            "canReply": True,
        })
    except ValueError as exc:
        return _json_error(str(exc), 401)
    except PermissionError as exc:
        return _json_error(str(exc), 403)
    except Exception as exc:
        return _json_error(str(exc), 500)


@admin_inquiries_bp.route("/api/admin/inquiries/<inquiry_id>/reply", methods=["PATCH"])
def reply_admin_inquiry(inquiry_id):
    try:
        actor = _verify_user(request.headers.get("Authorization"))
        is_admin = (actor.get("profile") or {}).get("role") == "ADMIN"
        payload = request.get_json(silent=True) or {}
        answer = str(payload.get("answer") or "").strip()
        status = str(payload.get("status") or "COMPLETED").upper()

        if status not in ALLOWED_REPLY_STATUSES:
            return _json_error("Unsupported inquiry status.", 400)
        if status == "COMPLETED" and not answer:
            return _json_error("Answer is required when status is COMPLETED.", 400)

        update_payload = {
            "answer": answer,
            "status": status,
            "answered_at": datetime.now(timezone.utc).isoformat() if answer and status == "COMPLETED" else None,
        }
        rows = _supabase_request(
            "inquiries",
            method="PATCH",
            params={
                "id": f"eq.{inquiry_id}",
                **({} if is_admin else {"user_id": f"eq.{actor['id']}"}),
            },
            json_data=update_payload,
            extra_headers={"Prefer": "return=representation"},
        ) or []
        if not rows:
            return _json_error("Inquiry was not found.", 404)

        profiles_by_id = _load_profiles_by_id([rows[0].get("user_id")])
        return jsonify({"success": True, "data": _map_inquiry(rows[0], profiles_by_id)})
    except ValueError as exc:
        return _json_error(str(exc), 401)
    except PermissionError as exc:
        return _json_error(str(exc), 403)
    except Exception as exc:
        return _json_error(str(exc), 500)
