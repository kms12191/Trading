from flask import Blueprint, jsonify, request

from backend.services.auth_service import get_user_id_from_header
from backend.services.chatbot.chat_service import ChatbotService
from backend.services.error_message_service import format_error_payload


chatbot_bp = Blueprint("chatbot", __name__)
chatbot_service = ChatbotService()


@chatbot_bp.route("/api/chatbot/message", methods=["POST"])
def send_chatbot_message():
    auth_header = request.headers.get("Authorization")
    user_id = None
    if auth_header:
        try:
            user_id, _ = get_user_id_from_header(auth_header)
        except Exception:
            user_id = None

    try:
        data = request.json or {}
        result = chatbot_service.reply(
            data.get("message"),
            user_id=user_id,
            auth_header=auth_header,
            user_timezone=data.get("timezone"),
        )
        return jsonify({"success": True, "data": result})
    except Exception as error:
        return jsonify(format_error_payload(error, "챗봇 응답 생성 실패")), 500
