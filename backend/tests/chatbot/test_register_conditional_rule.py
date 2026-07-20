# backend/tests/chatbot/test_register_conditional_rule.py
import pytest
from unittest.mock import MagicMock, patch

@pytest.fixture(autouse=True)
def mock_env(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")


def test_register_conditional_rule_success():
    from backend.services.chatbot.tool_registry import register_conditional_rule

    # _resolve_symbol, get_asset_price, get_user_id_from_header, safe_query_supabase 모킹
    with patch("backend.services.chatbot.tool_registry._resolve_symbol") as mock_resolve, \
         patch("backend.services.chatbot.tool_registry.get_asset_price") as mock_price, \
         patch("backend.services.auth_service.get_user_id_from_header") as mock_auth, \
         patch("backend.services.chatbot.tool_registry.safe_query_supabase") as mock_supabase:

        # 1. 심볼 해석 모킹
        mock_resolve.return_value = {
            "symbol": "XRP",
            "ticker": "XRP",
            "asset_type": "CRYPTO",
            "market": "COINONE",
            "name": "리플",
        }

        # 2. 현재 시세 조회 모킹
        mock_price.return_value = {
            "reply": "XRP 현재가는 1,600원입니다.",
            "data": {
                "current_price": 1600.0,
            }
        }

        # 3. 인증 정보 모킹
        mock_auth.return_value = ("test-user-uuid", "test-token")

        # 4. Supabase DB 인서트 모킹
        mock_supabase.return_value = {"success": True}

        # 실행
        auth_header = "Bearer test-token"
        result = register_conditional_rule(
            auth_header=auth_header,
            message="리플 3% 익절로 걸어줘",
            query="리플",
            target_profit_rate=3.0,
            stop_loss_rate=0.0,
            investment_amount=100000.0,
        )

        # 검증
        assert result is not None
        assert "조건감시 자동매도 규칙이 등록되었습니다" in result["reply"]
        assert result["data"]["source"] == "REGISTER_CONDITIONAL_RULE"
        
        # DB에 전달된 파라미터 검증
        rule = result["data"]["rule"]
        assert rule["user_id"] == "test-user-uuid"
        assert rule["symbol"] == "XRP"
        assert rule["exchange"] == "COINONE"
        assert rule["broker_env"] == "REAL"  # COINONE은 모의투자가 없으므로 REAL로 강제 설정됨
        assert rule["entry_price"] == 1600.0
        assert rule["target_profit_rate"] == 3.0
        assert rule["stop_loss_rate"] is None
        assert rule["execution_mode"] == "PROPOSAL"  # "자동" 키워드가 없으므로 기본값 PROPOSAL
        assert rule["status"] == "RUNNING"


def test_register_conditional_rule_auto_mode():
    from backend.services.chatbot.tool_registry import register_conditional_rule

    with patch("backend.services.chatbot.tool_registry._resolve_symbol") as mock_resolve, \
         patch("backend.services.chatbot.tool_registry.get_asset_price") as mock_price, \
         patch("backend.services.auth_service.get_user_id_from_header") as mock_auth, \
         patch("backend.services.chatbot.tool_registry.safe_query_supabase") as mock_supabase:

        mock_resolve.return_value = {
            "symbol": "XRP",
            "ticker": "XRP",
            "asset_type": "CRYPTO",
            "market": "COINONE",
            "name": "리플",
        }
        mock_price.return_value = {
            "data": {
                "current_price": 1600.0,
            }
        }
        mock_auth.return_value = ("test-user-uuid", "test-token")
        mock_supabase.return_value = {"success": True}

        # 실행 ("자동" 키워드가 포함됨)
        result = register_conditional_rule(
            auth_header="Bearer test-token",
            message="리플 자동매매 3% 익절 등록해줘",
            query="리플",
            target_profit_rate=3.0,
        )

        rule = result["data"]["rule"]
        assert rule["execution_mode"] == "AUTO"  # "자동매매" 키워드가 있으므로 AUTO로 설정되어야 함
