from backend.services.chatbot.memory_service import ChatbotMemoryService


def test_memory_service_extracts_explicit_user_preferences_only():
    service = ChatbotMemoryService()

    candidates = service.extract_memory_candidates(
        user_message=(
            "나는 코인은 무섭고 국내주식 위주로 보고 싶어. "
            "삼성전자랑 하이닉스 관심 있어. "
            "답변은 짧게 해줘. 손절을 자주 못해."
        ),
        assistant_message="알겠습니다.",
    )

    assert {candidate.memory_type for candidate in candidates} == {
        "risk_preference",
        "favorite_symbol",
        "answer_preference",
        "repeated_mistake",
    }
    assert any("코인 리스크" in candidate.content for candidate in candidates)
    assert any(candidate.symbol == "005930" for candidate in candidates)
    assert any(candidate.symbol == "000660" for candidate in candidates)
    assert any("짧은 답변" in candidate.content for candidate in candidates)
    assert any("손절" in candidate.content for candidate in candidates)


def test_memory_service_ignores_plain_order_requests():
    service = ChatbotMemoryService()

    candidates = service.extract_memory_candidates(
        user_message="삼성전자 10만원어치 사줘",
        assistant_message="매매 제안을 만들었습니다.",
    )

    assert candidates == []


def test_memory_service_persists_candidates_with_repository():
    saved = []

    class FakeRepository:
        def upsert_memory_fact(self, auth_header, user_id, fact):
            saved.append({"auth_header": auth_header, "user_id": user_id, "fact": fact})
            return {"id": f"memory-{len(saved)}"}

    service = ChatbotMemoryService(repository=FakeRepository())

    result = service.capture_from_exchange(
        auth_header="Bearer test",
        user_id="user-1",
        user_message="나는 국내주식 위주로 보고 싶어. 삼성전자 관심 있어.",
        assistant_message="알겠습니다.",
    )

    assert result["captured_count"] == 2
    assert saved[0]["user_id"] == "user-1"
    assert saved[0]["fact"]["memory_type"] in {"risk_preference", "favorite_symbol"}
