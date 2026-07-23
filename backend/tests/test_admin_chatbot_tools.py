import pytest
from backend.services.chatbot.tool_registry import execute_chatbot_tool


def test_admin_kill_switch_tool_execution():
    from unittest.mock import patch
    with patch("backend.services.admin_ai_managed_trader.AdminAiManagedTrader.emergency_kill_switch", return_value=True):
        result = execute_chatbot_tool(
            tool_name="admin_emergency_kill_switch",
            arguments={"exchange_type": "coinone"},
            user_id="admin-user-id",
            user_role="ADMIN"
        )
        assert result["success"] is True
        assert "긴급 셧다운" in result["message"]


def test_admin_tool_fails_for_non_admin():
    result = execute_chatbot_tool(
        tool_name="admin_emergency_kill_switch",
        arguments={"exchange_type": "coinone"},
        user_id="normal-user-id",
        user_role="USER"
    )
    assert result["success"] is False
    assert "권한이 없습니다" in result["message"]
