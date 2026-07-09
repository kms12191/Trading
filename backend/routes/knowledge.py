from flask import Blueprint, current_app, jsonify, request

from backend.services.auth_service import get_user_id_from_header
from backend.services.error_message_service import format_error_payload


knowledge_bp = Blueprint("knowledge", __name__)
DEFAULT_RAG_SOURCE_TYPES = ["DISCLOSURE", "OBSIDIAN", "AUTO_MEMORY", "APP_NOTE"]


@knowledge_bp.route("/api/knowledge/obsidian/sync-note", methods=["POST"])
def sync_obsidian_note():
    auth_header = request.headers.get("Authorization", "")
    try:
        user_id, _ = get_user_id_from_header(auth_header)
    except Exception as error:
        return jsonify(format_error_payload(error, "Obsidian 노트 동기화 인증 실패")), 401

    try:
        data = request.get_json(silent=True) or {}
        vault_name = str(data.get("vault_name") or "").strip()
        file_path = str(data.get("file_path") or "").strip()
        content = str(data.get("content") or "")
        if not vault_name:
            raise ValueError("vault_name이 필요합니다.")
        if not file_path:
            raise ValueError("file_path가 필요합니다.")
        if not file_path.lower().endswith(".md"):
            raise ValueError("Markdown(.md) 파일만 동기화할 수 있습니다.")

        parsed = current_app.obsidian_service.parse_markdown(file_path, content)
        payload = {
            **parsed,
            "user_id": user_id,
            "vault_name": vault_name,
            "modified_at": data.get("modified_at"),
        }
        result = current_app.knowledge_repository.upsert_obsidian_note(auth_header, user_id, payload)
        source_id = str(result.get("note_id") or parsed["content_hash"])
        frontmatter = parsed.get("frontmatter") or {}
        chunks = current_app.knowledge_chunk_service.build_chunks(
            user_id=user_id,
            source_type="OBSIDIAN",
            source_id=source_id,
            text=parsed["content"],
            symbol=frontmatter.get("symbol"),
            market=frontmatter.get("market"),
            metadata={
                "title": parsed["title"],
                "vault_name": vault_name,
                "file_path": file_path,
                "template_key": frontmatter.get("template_key"),
            },
        )
        chunk_result = current_app.knowledge_repository.replace_knowledge_chunks(
            auth_header,
            "OBSIDIAN",
            source_id,
            chunks,
        )
        return jsonify({"success": True, "data": {**result, **chunk_result}})
    except Exception as error:
        return jsonify(format_error_payload(error, "Obsidian 노트 동기화 실패")), 500


@knowledge_bp.route("/api/knowledge/obsidian/auto-memory", methods=["GET"])
def get_obsidian_auto_memory():
    auth_header = request.headers.get("Authorization", "")
    try:
        user_id, _ = get_user_id_from_header(auth_header)
    except Exception as error:
        return jsonify(format_error_payload(error, "Obsidian 자동메모리 인증 실패")), 401

    try:
        data = current_app.knowledge_repository.list_auto_memory(auth_header, user_id)
        return jsonify({"success": True, "data": data})
    except Exception as error:
        return jsonify(format_error_payload(error, "Obsidian 자동메모리 조회 실패")), 500
@knowledge_bp.route("/api/knowledge/retrieve-context", methods=["POST"])
def retrieve_context():
    auth_header = request.headers.get("Authorization", "")
    try:
        user_id, _ = get_user_id_from_header(auth_header)
    except Exception as error:
        return jsonify(format_error_payload(error, "RAG 검색 인증 실패")), 401

    try:
        data = request.get_json(silent=True) or {}
        question = str(data.get("question") or "").strip()
        if not question:
            raise ValueError("question이 필요합니다.")
        result = current_app.rag_retrieval_service.retrieve_context(
            user_id=user_id,
            question=question,
            symbol=str(data.get("symbol") or "").strip() or None,
            market=str(data.get("market") or "").strip() or None,
            source_types=data.get("source_types") or DEFAULT_RAG_SOURCE_TYPES,
            limit=int(data.get("limit") or 12),
        )
        return jsonify({"success": True, "data": result})
    except Exception as error:
        return jsonify(format_error_payload(error, "RAG 검색 실패")), 500
