from backend.services.chatbot.chat_service import ChatbotService


class FakeLLMClient:
    def __init__(self):
        self.system_prompt = None
        self.history = None
        self.reply = "테스트 응답"

    def generate_reply(self, system_prompt, user_message, user_id=None, auth_header=None, function_schemas=None, history=None):
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


def test_reply_loads_and_persists_authenticated_chat_history(monkeypatch):
    queries = []

    def fake_query(auth_header, endpoint, method="GET", json_data=None, params=None):
        queries.append({
            "auth_header": auth_header,
            "endpoint": endpoint,
            "method": method,
            "json_data": json_data,
            "params": params,
        })
        if method == "GET":
            return [{"role": "user", "message": "이전 질문", "created_at": "2026-07-10T00:00:00Z"}]
        return [{"id": 1}, {"id": 2}]

    monkeypatch.setattr(
        "backend.services.chatbot.chat_service.safe_query_supabase",
        fake_query,
    )
    monkeypatch.setattr(
        "backend.services.chatbot.chat_service.run_chatbot_tool",
        lambda auth_header, text: None,
    )

    service = ChatbotService()
    fake_llm = FakeLLMClient()
    service.llm_client = fake_llm
    service.rag_service = FakeRAGService()

    result = service.reply("새 질문", user_id="user-1", auth_header="Bearer test")

    assert result["reply"] == "테스트 응답"
    assert fake_llm.history[0] == {"role": "user", "content": "이전 질문"}
    post_calls = [query for query in queries if query["method"] == "POST"]
    assert len(post_calls) == 1
    assert post_calls[0]["endpoint"] == "chat_history"
    assert [row["role"] for row in post_calls[0]["json_data"]] == ["user", "assistant"]
    assert all(row["user_id"] == "user-1" for row in post_calls[0]["json_data"])


def test_anonymous_reply_does_not_read_or_write_shared_history(monkeypatch):
    query_count = 0

    def fake_query(*args, **kwargs):
        nonlocal query_count
        query_count += 1
        return []

    monkeypatch.setattr(
        "backend.services.chatbot.chat_service.safe_query_supabase",
        fake_query,
    )
    monkeypatch.setattr(
        "backend.services.chatbot.chat_service.run_chatbot_tool",
        lambda auth_header, text: None,
    )

    service = ChatbotService()
    service.llm_client = FakeLLMClient()
    service.rag_service = FakeRAGService()

    service.reply("첫 번째 질문", user_id=None, auth_header=None)
    service.reply("두 번째 질문", user_id=None, auth_header=None)

    assert query_count == 0
    assert service._get_recent_history(None) == []
    assert service._peek_pending_action(None) is None


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


def test_reply_includes_trace_steps_for_recommendation_rag_tool(monkeypatch):
    monkeypatch.setattr(
        "backend.services.chatbot.chat_service.run_chatbot_tool",
        lambda auth_header, text: {
            "reply": "추천 후보입니다.",
            "data": {
                "source": "ML_ACTIVE_SIGNAL",
                "citations": [
                    {
                        "source_type": "DISCLOSURE",
                        "source_id": "20260701000001",
                        "summary": "공시 근거",
                    }
                ],
            },
        },
    )

    service = ChatbotService()
    service.llm_client = FakeLLMClient()
    service.rag_service = FakeRAGService()

    result = service.reply("국내 주식 추천해줘", user_id="user-1", auth_header="Bearer test")

    assert result["meta"]["trace_steps"] == [
        {"kind": "ml", "label": "ML 신호"},
        {"kind": "rag", "label": "RAG 벡터검색"},
        {"kind": "disclosure", "label": "DART 공시"},
    ]


def test_reply_emits_live_trace_callback_while_running_project_tool(monkeypatch):
    monkeypatch.setattr(
        "backend.services.chatbot.chat_service.run_chatbot_tool",
        lambda auth_header, text: {
            "reply": "추천 후보입니다.",
            "data": {
                "source": "ML_ACTIVE_SIGNAL",
                "citations": [{"source_type": "DISCLOSURE", "source_id": "1"}],
            },
        },
    )

    service = ChatbotService()
    service.llm_client = FakeLLMClient()
    service.rag_service = FakeRAGService()
    traces = []

    result = service.reply(
        "국내 주식 추천해줘",
        user_id="user-1",
        auth_header="Bearer test",
        trace_callback=traces.append,
    )

    assert result["reply"] == "추천 후보입니다."
    assert traces[:2] == [
        {"kind": "tool_routing", "label": "도구 확인"},
        {"kind": "ml", "label": "ML 신호"},
    ]
    assert {"kind": "rag", "label": "RAG 벡터검색"} in traces


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


def test_reply_captures_auto_memory_after_exchange(monkeypatch):
    monkeypatch.setattr(
        "backend.services.chatbot.chat_service.run_chatbot_tool",
        lambda auth_header, text: None,
    )

    captured = []

    class FakeMemoryService:
        def capture_from_exchange(self, auth_header, user_id, user_message, assistant_message):
            captured.append({
                "auth_header": auth_header,
                "user_id": user_id,
                "user_message": user_message,
                "assistant_message": assistant_message,
            })
            return {"captured_count": 1}

    service = ChatbotService()
    service.llm_client = FakeLLMClient()
    service.rag_service = FakeRAGService()
    service.memory_service = FakeMemoryService()

    service.reply("나는 국내주식 위주로 보고 싶어", user_id="user-1", auth_header="Bearer test")

    assert captured == [
        {
            "auth_header": "Bearer test",
            "user_id": "user-1",
            "user_message": "나는 국내주식 위주로 보고 싶어",
            "assistant_message": "테스트 응답",
        }
    ]


def test_prompt_includes_auto_memory_context(monkeypatch):
    monkeypatch.setattr(
        "backend.services.chatbot.chat_service.load_user_investment_profile_context",
        lambda auth_header, user_id=None: "",
    )

    class FakeKnowledgeRepository:
        def list_chatbot_memory_context(self, auth_header, user_id):
            return "자동메모리:\n- risk_preference: 사용자는 코인 리스크를 회피합니다."

    service = ChatbotService()
    service.rag_service = FakeRAGService()
    service.knowledge_repository = FakeKnowledgeRepository()

    prompt = service._build_prompt_for_user("Bearer test", "user-1", "추천해줘")

    assert "자동메모리:" in prompt
    assert "코인 리스크를 회피" in prompt
