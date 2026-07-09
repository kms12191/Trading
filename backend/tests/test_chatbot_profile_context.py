from backend.services.chatbot.chat_service import ChatbotService


class FakeLLMClient:
    def __init__(self):
        self.system_prompt = None
        self.history = None
        self.reply = "테스트 응답"

    def generate_reply(self, system_prompt, user_message, user_id=None, function_schemas=None, history=None):
        self.system_prompt = system_prompt
        self.history = history
        return {
            "reply": self.reply,
            "model": "fake",
            "usage": {},
            "tool_calls": [],
        }


class FakeRAGService:
    def build_context(self, auth_header, user_id, query):
        return "", []


def test_reply_adds_investment_profile_context_to_system_prompt(monkeypatch):
    monkeypatch.setattr(
        "backend.services.chatbot.chat_service.load_user_investment_profile_context",
        lambda auth_header, user_id=None: "사용자 투자성향: 위험중립형",
    )
    monkeypatch.setattr(
        "backend.services.chatbot.chat_service.run_chatbot_tool",
        lambda auth_header, text: None,
    )

    service = ChatbotService()
    fake_llm = FakeLLMClient()
    service.llm_client = fake_llm
    service.rag_service = FakeRAGService()

    result = service.reply("삼성전자 투자 의견 알려줘", user_id="user-1", auth_header="Bearer test")

    assert result["reply"] == "테스트 응답"
    assert "사용자 투자성향: 위험중립형" in fake_llm.system_prompt


def test_reply_adds_current_datetime_context_to_system_prompt(monkeypatch):
    monkeypatch.setattr(
        "backend.services.chatbot.chat_service.load_user_investment_profile_context",
        lambda auth_header, user_id=None: "",
    )
    monkeypatch.setattr(
        "backend.services.chatbot.chat_service.run_chatbot_tool",
        lambda auth_header, text: None,
    )

    service = ChatbotService()
    fake_llm = FakeLLMClient()
    service.llm_client = fake_llm
    service.rag_service = FakeRAGService()

    service.reply("오늘 날짜가 언제야?", user_id="user-1", auth_header="Bearer test", user_timezone="Asia/Seoul")

    assert "현재 날짜/시간 기준:" in fake_llm.system_prompt
    assert "기준 시간대: Asia/Seoul" in fake_llm.system_prompt
    assert "오늘 날짜:" in fake_llm.system_prompt
    assert "상대 날짜" in fake_llm.system_prompt


def test_reply_executes_pending_portfolio_summary_on_confirmation(monkeypatch):
    monkeypatch.setattr(
        "backend.services.chatbot.chat_service.run_chatbot_tool",
        lambda auth_header, text: None,
    )
    monkeypatch.setattr(
        "backend.services.chatbot.chat_service.get_portfolio_summary",
        lambda auth_header, text: {
            "reply": "평가 자산 합계: 1,000,000원",
            "data": {"summaries": []},
        },
    )

    service = ChatbotService()
    service.llm_client = FakeLLMClient()
    service.rag_service = FakeRAGService()
    service._set_pending_action("user-1", "portfolio_summary")

    result = service.reply("조회해도 돼", user_id="user-1", auth_header="Bearer test")

    assert result["reply"] == "평가 자산 합계: 1,000,000원"
    assert result["meta"]["source"] == "PROJECT_TOOL_PENDING"


def test_reply_passes_recent_history_to_llm(monkeypatch):
    monkeypatch.setattr(
        "backend.services.chatbot.chat_service.run_chatbot_tool",
        lambda auth_header, text: None,
    )
    monkeypatch.setattr(
        "backend.services.chatbot.chat_service.load_user_investment_profile_context",
        lambda auth_header, user_id=None: "",
    )

    service = ChatbotService()
    fake_llm = FakeLLMClient()
    service.llm_client = fake_llm
    service.rag_service = FakeRAGService()
    service.reply("국내주식 매매 제안해줘", user_id="user-1", auth_header="Bearer test")
    service.reply("조회해도 돼", user_id="user-1", auth_header="Bearer test")

    assert fake_llm.history
    assert fake_llm.history[-1]["content"] == "테스트 응답"
