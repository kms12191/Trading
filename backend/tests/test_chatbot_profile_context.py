from backend.services.chatbot.conversation_repository import ChatbotConversationRepository
from backend.services.chatbot.chat_service import ChatbotService


class FakeLLMClient:
    def __init__(self):
        self.system_prompt = None
        self.history = None
        self.reply = "테스트 응답"
        self.generate_calls = 0
        self.stream_calls = 0

    def generate_reply(self, system_prompt, user_message, user_id=None, auth_header=None, function_schemas=None, history=None):
        self.generate_calls += 1
        self.system_prompt = system_prompt
        self.history = history
        return {
            "reply": self.reply,
            "model": "fake",
            "usage": {},
            "tool_calls": [],
        }

    def stream_reply(
        self,
        system_prompt,
        user_message,
        user_id=None,
        auth_header=None,
        function_schemas=None,
        history=None,
        on_delta=None,
    ):
        self.stream_calls += 1
        self.system_prompt = system_prompt
        self.history = history
        on_delta("테스트 ")
        on_delta("응답")
        return {
            "reply": self.reply,
            "model": "fake",
            "usage": {},
            "tool_calls": [],
        }


class FakeRAGService:
    def build_context(self, auth_header, user_id, query):
        return "", []


class FakeConversationSupabaseBoundary:
    def __init__(self):
        self.history = []
        self.state = {}

    def query(
        self,
        auth_header,
        endpoint,
        method="GET",
        json_data=None,
        params=None,
        extra_headers=None,
    ):
        params = params or {}
        user_id = str(params.get("user_id") or "").removeprefix("eq.")
        if endpoint == "chat_history":
            if method == "POST":
                for row in json_data:
                    self.history.append({
                        **row,
                        "id": len(self.history) + 1,
                        "created_at": f"2026-07-10T01:00:{len(self.history) + 1:02d}Z",
                    })
                return list(self.history)
            rows = [row for row in self.history if row.get("user_id") == user_id]
            return list(reversed(rows))
        if endpoint == "chatbot_conversation_states":
            if method == "GET":
                row = self.state.get(user_id)
                return [dict(row)] if row else []
            if method == "POST":
                payload = dict(json_data or {})
                self.state[payload["user_id"]] = payload
                return [dict(payload)]
            if method == "PATCH":
                row = self.state.get(user_id)
                if not row:
                    return []
                expected_action = params.get("pending_action")
                expected_expires_at = params.get("pending_expires_at")
                if expected_action and expected_action != f"eq.{row.get('pending_action')}":
                    return []
                if expected_expires_at and expected_expires_at != f"eq.{row.get('pending_expires_at')}":
                    return []
                row.update(json_data or {})
                if (extra_headers or {}).get("Prefer") == "return=representation":
                    return [dict(row)]
                return None
        raise AssertionError(f"지원하지 않는 Supabase 요청: {endpoint} {method}")


def test_reply_loads_and_persists_authenticated_chat_history(monkeypatch):
    boundary = FakeConversationSupabaseBoundary()
    boundary.history.append({
        "id": 1,
        "user_id": "user-1",
        "role": "user",
        "message": "이전 질문",
        "created_at": "2026-07-10T00:00:00Z",
    })

    monkeypatch.setattr(
        "backend.services.chatbot.conversation_repository.query_supabase",
        boundary.query,
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
    assert ChatbotConversationRepository().load_recent_history(
        "Bearer test",
        "user-1",
    )[-2:] == [
        {"role": "user", "content": "새 질문"},
        {"role": "assistant", "content": "테스트 응답"},
    ]


def test_reply_uses_llm_stream_when_delta_callback_is_provided(monkeypatch):
    boundary = FakeConversationSupabaseBoundary()
    monkeypatch.setattr(
        "backend.services.chatbot.conversation_repository.query_supabase",
        boundary.query,
    )
    monkeypatch.setattr(
        "backend.services.chatbot.chat_service.run_chatbot_tool",
        lambda auth_header, text: None,
    )
    service = ChatbotService()
    fake_llm = FakeLLMClient()
    service.llm_client = fake_llm
    service.rag_service = FakeRAGService()
    deltas = []

    result = service.reply(
        "새 질문",
        user_id="user-1",
        auth_header="Bearer test",
        delta_callback=deltas.append,
    )

    assert result["reply"] == "테스트 응답"
    assert deltas == ["테스트 ", "응답"]
    assert fake_llm.stream_calls == 1
    assert fake_llm.generate_calls == 0


def test_anonymous_reply_does_not_read_or_write_shared_history(monkeypatch):
    boundary = FakeConversationSupabaseBoundary()

    monkeypatch.setattr(
        "backend.services.chatbot.conversation_repository.query_supabase",
        boundary.query,
    )
    monkeypatch.setattr(
        "backend.services.chatbot.chat_service.run_chatbot_tool",
        lambda auth_header, text: None,
    )

    service = ChatbotService()
    fake_llm = FakeLLMClient()
    service.llm_client = fake_llm
    service.rag_service = FakeRAGService()

    service.reply("첫 번째 질문", user_id=None, auth_header=None)
    service.reply("두 번째 질문", user_id=None, auth_header=None)

    assert boundary.history == []
    assert boundary.state == {}
    assert fake_llm.history == []


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
    boundary = FakeConversationSupabaseBoundary()
    monkeypatch.setattr(
        "backend.services.chatbot.conversation_repository.query_supabase",
        boundary.query,
    )
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
    service.conversation_repository.set_pending_action(
        "Bearer test",
        "user-1",
        "portfolio_summary",
    )

    result = service.reply("조회해도 돼", user_id="user-1", auth_header="Bearer test")

    assert result["reply"] == "평가 자산 합계: 1,000,000원"
    assert result["meta"]["source"] == "PROJECT_TOOL_PENDING"
    assert service.conversation_repository.peek_pending_action(
        "Bearer test",
        "user-1",
    ) is None


def test_reply_retries_trade_proposal_when_user_provides_missing_quantity(monkeypatch):
    boundary = FakeConversationSupabaseBoundary()
    tool_calls = []

    def fake_run_chatbot_tool(auth_header, text):
        tool_calls.append(text)
        if text == "1번 1매 구매해줘":
            return {
                "reply": "RDDT BUY 매매 제안을 만들 수량을 알려주세요.",
                "data": {
                    "source": "CHATBOT_ORDER_PARSER",
                    "reason": "missing_quantity",
                    "symbol": "RDDT",
                },
            }
        if text == "1번 1매 구매해줘 1개":
            return {
                "reply": "RDDT BUY 매매 제안을 생성했습니다.",
                "data": {
                    "source": "TRADE_PROPOSAL_CREATED",
                    "symbol": "RDDT",
                    "status": "PENDING",
                },
            }
        return None

    monkeypatch.setattr(
        "backend.services.chatbot.conversation_repository.query_supabase",
        boundary.query,
    )
    monkeypatch.setattr(
        "backend.services.chatbot.chat_service.run_chatbot_tool",
        fake_run_chatbot_tool,
    )

    service = ChatbotService()
    service.llm_client = FakeLLMClient()
    service.rag_service = FakeRAGService()

    first = service.reply("1번 1매 구매해줘", user_id="user-1", auth_header="Bearer test")
    assert first["reply"] == "RDDT BUY 매매 제안을 만들 수량을 알려주세요."
    assert service.conversation_repository.peek_pending_action(
        "Bearer test",
        "user-1",
    ) == "trade_proposal_missing_quantity"

    second = service.reply("1개", user_id="user-1", auth_header="Bearer test")

    assert second["reply"] == "RDDT BUY 매매 제안을 생성했습니다."
    assert second["meta"]["source"] == "PROJECT_TOOL_PENDING"
    assert tool_calls == ["1번 1매 구매해줘", "1번 1매 구매해줘 1개"]
    assert service.conversation_repository.peek_pending_action(
        "Bearer test",
        "user-1",
    ) is None


def test_reply_keeps_missing_quantity_pending_when_user_confirms_without_quantity(monkeypatch):
    boundary = FakeConversationSupabaseBoundary()
    monkeypatch.setattr(
        "backend.services.chatbot.conversation_repository.query_supabase",
        boundary.query,
    )
    monkeypatch.setattr(
        "backend.services.chatbot.chat_service.run_chatbot_tool",
        lambda auth_header, text: {
            "reply": "RDDT BUY 매매 제안을 만들 수량을 알려주세요.",
            "data": {
                "source": "CHATBOT_ORDER_PARSER",
                "reason": "missing_quantity",
                "symbol": "RDDT",
            },
        },
    )

    service = ChatbotService()
    service.llm_client = FakeLLMClient()
    service.rag_service = FakeRAGService()

    service.reply("1번 1매 구매해줘", user_id="user-1", auth_header="Bearer test")
    result = service.reply("응", user_id="user-1", auth_header="Bearer test")

    assert "수량" in result["reply"]
    assert result["meta"]["source"] == "PROJECT_TOOL_PENDING"
    assert service.conversation_repository.peek_pending_action(
        "Bearer test",
        "user-1",
    ) == "trade_proposal_missing_quantity"


def test_reply_retries_trade_proposal_when_user_provides_missing_price(monkeypatch):
    boundary = FakeConversationSupabaseBoundary()
    tool_calls = []

    def fake_run_chatbot_tool(auth_header, text):
        tool_calls.append(text)
        if text == "금호건설 1주사줘":
            return {
                "reply": "002990 BUY 매매 제안은 지정가 금액이 필요합니다.",
                "data": {
                    "source": "CHATBOT_ORDER_PARSER",
                    "reason": "missing_order_price",
                    "symbol": "002990",
                    "exchange": "TOSS",
                    "broker_env": "REAL",
                },
            }
        if text == "금호건설 1주사줘 지정가 3500원에":
            return {
                "reply": "002990 BUY 매매 제안을 생성했습니다.",
                "data": {
                    "source": "TRADE_PROPOSAL_CREATED",
                    "symbol": "002990",
                    "status": "PENDING",
                },
            }
        return None

    monkeypatch.setattr(
        "backend.services.chatbot.conversation_repository.query_supabase",
        boundary.query,
    )
    monkeypatch.setattr(
        "backend.services.chatbot.chat_service.run_chatbot_tool",
        fake_run_chatbot_tool,
    )

    service = ChatbotService()
    service.llm_client = FakeLLMClient()
    service.rag_service = FakeRAGService()

    first = service.reply("금호건설 1주사줘", user_id="user-1", auth_header="Bearer test")
    assert "지정가" in first["reply"]
    assert service.conversation_repository.peek_pending_action(
        "Bearer test",
        "user-1",
    ) == "trade_proposal_missing_price"

    second = service.reply("3500원", user_id="user-1", auth_header="Bearer test")

    assert second["reply"] == "002990 BUY 매매 제안을 생성했습니다."
    assert second["meta"]["source"] == "PROJECT_TOOL_PENDING"
    assert tool_calls == ["금호건설 1주사줘", "금호건설 1주사줘 지정가 3500원에"]


def test_reply_retries_trade_proposal_when_user_provides_env_and_price(monkeypatch):
    boundary = FakeConversationSupabaseBoundary()
    tool_calls = []

    def fake_run_chatbot_tool(auth_header, text):
        tool_calls.append(text)
        if text == "KIS 삼성전자 1주사줘":
            return {
                "reply": "005930 BUY 매매 제안을 만들 계좌 환경과 지정가 금액을 알려주세요.",
                "data": {
                    "source": "CHATBOT_ORDER_PARSER",
                    "reason": "missing_order_env_and_price",
                    "symbol": "005930",
                    "exchange": "KIS",
                },
            }
        if text == "KIS 삼성전자 1주사줘 실거래 지정가 70000원에":
            return {
                "reply": "005930 BUY 매매 제안을 생성했습니다.",
                "data": {
                    "source": "TRADE_PROPOSAL_CREATED",
                    "symbol": "005930",
                    "status": "PENDING",
                },
            }
        return None

    monkeypatch.setattr(
        "backend.services.chatbot.conversation_repository.query_supabase",
        boundary.query,
    )
    monkeypatch.setattr(
        "backend.services.chatbot.chat_service.run_chatbot_tool",
        fake_run_chatbot_tool,
    )

    service = ChatbotService()
    service.llm_client = FakeLLMClient()
    service.rag_service = FakeRAGService()

    service.reply("KIS 삼성전자 1주사줘", user_id="user-1", auth_header="Bearer test")
    assert service.conversation_repository.peek_pending_action(
        "Bearer test",
        "user-1",
    ) == "trade_proposal_missing_env_and_price"

    result = service.reply("실거래 70000원", user_id="user-1", auth_header="Bearer test")

    assert result["reply"] == "005930 BUY 매매 제안을 생성했습니다."
    assert tool_calls == [
        "KIS 삼성전자 1주사줘",
        "KIS 삼성전자 1주사줘 실거래 지정가 70000원에",
    ]


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
    boundary = FakeConversationSupabaseBoundary()
    monkeypatch.setattr(
        "backend.services.chatbot.conversation_repository.query_supabase",
        boundary.query,
    )
    monkeypatch.setattr(
        "backend.services.chatbot.chat_service.run_chatbot_tool",
        lambda auth_header, text: None,
    )
    monkeypatch.setattr(
        "backend.services.chatbot.chat_service.load_user_investment_profile_context",
        lambda auth_header, user_id=None: "",
    )

    first_service = ChatbotService()
    first_service.llm_client = FakeLLMClient()
    first_service.rag_service = FakeRAGService()
    first_service.reply("첫 번째 질문", user_id="user-1", auth_header="Bearer test")

    second_service = ChatbotService()
    fake_llm = FakeLLMClient()
    second_service.llm_client = fake_llm
    second_service.rag_service = FakeRAGService()
    second_service.reply("두 번째 질문", user_id="user-1", auth_header="Bearer test")

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
