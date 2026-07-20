# 챗봇 LangGraph Agent + Gemini Failover 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 챗봇 메인 LLM을 LangGraph Agent 기반 Gemini 3.5 Pro → Gemini 3.5 Flash → GPT-4.1-mini 3단 Failover 구조로 전환한다.

**Architecture:** LangGraph StateGraph로 `call_model` ↔ `tools` 루프를 구성하고, LLM은 `with_fallbacks()`로 Gemini→GPT Failover 체인을 내장한다. 기존 `tool_registry.py` 비즈니스 로직은 100% 유지하면서 LangGraph 도구 노드에서 호출한다. 기존 SSE 스트리밍은 스레드+큐 패턴을 유지하여 Flask 호환성을 보장한다.

**Tech Stack:** `langchain-core`, `langchain-google-genai`, `langchain-openai`, `langgraph`, Python 3.11+, Flask

## Global Constraints

- Python 3.11+ (기존 프로젝트 기준)
- Flask ≥ 3.0.0 (기존 동기 프레임워크 유지, async 사용 안 함)
- 기존 `tool_registry.py`, `safety_guard.py`, `order_parser.py`, `rag_service.py`, `memory_service.py`, `conversation_repository.py` 비즈니스 로직 변경 금지
- DART 공시(`dart_analysis_service.py`), 뉴스 요약(`news_summary_service.py`) 코드 변경 금지
- 프론트엔드 SSE 이벤트 포맷(`trace`, `delta`, `done`, `error`) 변경 금지
- 환경변수 `GEMINI_API_KEY`, `OPENAI_API_KEY`는 기존에 `.env`에 존재
- 모든 코드 주석은 영문, 설명 문서는 한국어

---

### Task 1: 의존성 추가 및 환경 검증

**Files:**
- Modify: `backend/requirements.txt`
- Test: 수동 검증 (pip install 성공 여부)

**Interfaces:**
- Produces: `langchain-core`, `langchain-google-genai`, `langchain-openai`, `langgraph` 패키지 사용 가능 상태

- [ ] **Step 1: requirements.txt에 LangChain/LangGraph 패키지 추가**

```text
# backend/requirements.txt 끝에 추가
langchain-core>=0.3.0
langchain-google-genai>=2.1.0
langchain-openai>=0.3.0
langgraph>=0.3.0
```

- [ ] **Step 2: 패키지 설치 및 import 검증**

Run: `cd backend && pip install -r requirements.txt`
Expected: 모든 패키지 설치 성공

Run: `cd backend && python -c "from langchain_google_genai import ChatGoogleGenerativeAI; from langchain_openai import ChatOpenAI; from langgraph.graph import StateGraph; print('OK')"`
Expected: `OK` 출력

- [ ] **Step 3: Commit**

```bash
git add backend/requirements.txt
git commit -m "chore: LangChain, LangGraph 의존성 추가"
```

---

### Task 2: Failover LLM 프로바이더 (`llm_provider.py`)

**Files:**
- Create: `backend/services/chatbot/llm_provider.py`
- Test: `backend/tests/chatbot/test_llm_provider.py`

**Interfaces:**
- Produces: `create_chatbot_llm() -> BaseChatModel` — Task 3, 4에서 사용
- Produces: `get_chatbot_config() -> dict` — 환경변수 기반 설정 딕셔너리

- [ ] **Step 1: 테스트 파일 작성**

```python
# backend/tests/chatbot/test_llm_provider.py
import os
import pytest


def test_create_chatbot_llm_returns_model_with_fallbacks(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-gemini-key")
    monkeypatch.setenv("OPENAI_API_KEY", "test-openai-key")
    monkeypatch.setenv("CHATBOT_PRIMARY_MODEL", "gemini-3.5-pro")
    monkeypatch.setenv("CHATBOT_SECONDARY_MODEL", "gemini-3.5-flash")
    monkeypatch.setenv("CHATBOT_FALLBACK_MODEL", "gpt-4.1-mini")

    from backend.services.chatbot.llm_provider import create_chatbot_llm
    llm = create_chatbot_llm()
    assert llm is not None
    assert hasattr(llm, "invoke")


def test_create_chatbot_llm_gemini_only(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-gemini-key")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    from backend.services.chatbot.llm_provider import create_chatbot_llm
    llm = create_chatbot_llm()
    assert llm is not None


def test_create_chatbot_llm_openai_only(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "test-openai-key")

    from backend.services.chatbot.llm_provider import create_chatbot_llm
    llm = create_chatbot_llm()
    assert llm is not None


def test_create_chatbot_llm_no_keys_raises(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    from backend.services.chatbot.llm_provider import create_chatbot_llm
    with pytest.raises(RuntimeError, match="API"):
        create_chatbot_llm()


def test_get_chatbot_config_defaults(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "k")
    monkeypatch.setenv("OPENAI_API_KEY", "k")

    from backend.services.chatbot.llm_provider import get_chatbot_config
    config = get_chatbot_config()
    assert config["primary_model"] == "gemini-3.5-pro"
    assert config["secondary_model"] == "gemini-3.5-flash"
    assert config["fallback_model"] == "gpt-4.1-mini"
    assert config["temperature"] == 0.3
    assert config["max_output_tokens"] >= 2048
    assert config["max_history_messages"] >= 50
    assert config["max_tool_rounds"] >= 5
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `cd backend && python -m pytest tests/chatbot/test_llm_provider.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'backend.services.chatbot.llm_provider'`

- [ ] **Step 3: llm_provider.py 구현**

```python
# backend/services/chatbot/llm_provider.py
"""Chatbot LLM provider with Gemini -> GPT failover chain."""
import os
import logging

from langchain_core.language_models import BaseChatModel

logger = logging.getLogger(__name__)


def _read_int_env(name: str, default: int) -> int:
    try:
        value = int(os.getenv(name, default))
        return value if value > 0 else default
    except (TypeError, ValueError):
        return default


def get_chatbot_config() -> dict:
    """Return chatbot configuration from environment variables."""
    return {
        "gemini_api_key": os.getenv("GEMINI_API_KEY", "").strip(),
        "openai_api_key": os.getenv("OPENAI_API_KEY", "").strip(),
        "primary_model": os.getenv("CHATBOT_PRIMARY_MODEL", "gemini-3.5-pro").strip(),
        "secondary_model": os.getenv("CHATBOT_SECONDARY_MODEL", "gemini-3.5-flash").strip(),
        "fallback_model": os.getenv("CHATBOT_FALLBACK_MODEL", "gpt-4.1-mini").strip(),
        "primary_provider": os.getenv("CHATBOT_PRIMARY_PROVIDER", "gemini").strip().lower(),
        "secondary_provider": os.getenv("CHATBOT_SECONDARY_PROVIDER", "gemini").strip().lower(),
        "fallback_provider": os.getenv("CHATBOT_FALLBACK_PROVIDER", "openai").strip().lower(),
        "temperature": float(os.getenv("CHATBOT_TEMPERATURE", "0.3")),
        "max_output_tokens": _read_int_env("CHATBOT_MAX_OUTPUT_TOKENS", 2048),
        "max_history_messages": _read_int_env("CHATBOT_MAX_HISTORY_MESSAGES", 50),
        "max_tool_rounds": _read_int_env("CHATBOT_MAX_TOOL_ROUNDS", 5),
        "max_input_chars": _read_int_env("CHATBOT_MAX_INPUT_CHARS", 50000),
        "daily_request_limit": _read_int_env("CHATBOT_DAILY_REQUEST_LIMIT", 500),
        "daily_token_limit": _read_int_env("CHATBOT_DAILY_TOKEN_LIMIT", 500000),
    }


def _create_model(provider: str, model_name: str, api_key: str, config: dict) -> BaseChatModel | None:
    """Create a single LLM instance for the given provider."""
    if not api_key:
        return None
    if provider == "gemini":
        from langchain_google_genai import ChatGoogleGenerativeAI
        return ChatGoogleGenerativeAI(
            model=model_name,
            google_api_key=api_key,
            temperature=config["temperature"],
            max_output_tokens=config["max_output_tokens"],
        )
    if provider == "openai":
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(
            model=model_name,
            api_key=api_key,
            temperature=config["temperature"],
            max_tokens=config["max_output_tokens"],
        )
    return None


def create_chatbot_llm() -> BaseChatModel:
    """Create the chatbot LLM with Gemini -> GPT failover chain.

    Returns a BaseChatModel with .with_fallbacks() applied.
    Failover order: primary -> secondary -> fallback.
    """
    config = get_chatbot_config()
    models: list[BaseChatModel] = []

    for key_prefix in ("primary", "secondary", "fallback"):
        provider = config[f"{key_prefix}_provider"]
        model_name = config[f"{key_prefix}_model"]
        api_key = config["gemini_api_key"] if provider == "gemini" else config["openai_api_key"]
        model = _create_model(provider, model_name, api_key, config)
        if model is not None:
            models.append(model)

    if not models:
        raise RuntimeError(
            "챗봇 LLM을 생성할 수 없습니다. GEMINI_API_KEY 또는 OPENAI_API_KEY를 설정해 주세요."
        )

    primary = models[0]
    fallbacks = models[1:]
    if fallbacks:
        return primary.with_fallbacks(fallbacks)
    return primary
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `cd backend && python -m pytest tests/chatbot/test_llm_provider.py -v`
Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
git add backend/services/chatbot/llm_provider.py backend/tests/chatbot/test_llm_provider.py
git commit -m "feat: Gemini→GPT Failover LLM 프로바이더 구현"
```

---

### Task 3: LangGraph 도구 래퍼 (`langchain_tools.py`)

**Files:**
- Create: `backend/services/chatbot/langchain_tools.py`
- Test: `backend/tests/chatbot/test_langchain_tools.py`

**Interfaces:**
- Consumes: `backend.services.chatbot.tool_registry` — 기존 16개 도구 함수
- Consumes: `backend.services.chatbot.safety_guard.enforce_tool_safety`
- Produces: `build_tool_schemas() -> list[dict]` — OpenAI 호환 도구 스키마 리스트 (LLM bind_tools용)
- Produces: `execute_tool_call(tool_name: str, arguments: dict, auth_header: str) -> str` — 도구 실행 후 JSON 문자열 반환

- [ ] **Step 1: 테스트 파일 작성**

```python
# backend/tests/chatbot/test_langchain_tools.py
import json
import pytest


def test_build_tool_schemas_returns_list():
    from backend.services.chatbot.langchain_tools import build_tool_schemas
    schemas = build_tool_schemas()
    assert isinstance(schemas, list)
    assert len(schemas) >= 16
    names = [s["function"]["name"] for s in schemas]
    assert "get_asset_price" in names
    assert "search_web" in names
    assert "get_portfolio_summary" in names


def test_build_tool_schemas_openai_format():
    from backend.services.chatbot.langchain_tools import build_tool_schemas
    schemas = build_tool_schemas()
    for schema in schemas:
        assert schema["type"] == "function"
        assert "name" in schema["function"]
        assert "description" in schema["function"]
        assert "parameters" in schema["function"]


def test_execute_tool_call_unknown_tool():
    from backend.services.chatbot.langchain_tools import execute_tool_call
    result = execute_tool_call("unknown_tool", {}, "Bearer test")
    parsed = json.loads(result)
    assert "error" in parsed or "reply" in parsed


def test_execute_tool_call_blocked_order_tool():
    from backend.services.chatbot.langchain_tools import execute_tool_call
    with pytest.raises(Exception):
        execute_tool_call("place_order", {}, "Bearer test")
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `cd backend && python -m pytest tests/chatbot/test_langchain_tools.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: langchain_tools.py 구현**

```python
# backend/services/chatbot/langchain_tools.py
"""LangGraph tool wrappers around existing tool_registry functions."""
import json
import logging
from typing import Any

from backend.services.chatbot.function_calling import FUNCTION_SCHEMAS
from backend.services.chatbot.safety_guard import enforce_tool_safety
from backend.services.chatbot import tool_registry

logger = logging.getLogger(__name__)

_TOOL_FUNCTION_MAP: dict[str, Any] = {
    "get_home_market_rankings": tool_registry.get_home_market_rankings,
    "get_portfolio_summary": tool_registry.get_portfolio_summary,
    "add_watchlist_item": tool_registry.add_watchlist_item,
    "remove_watchlist_item": tool_registry.remove_watchlist_item,
    "get_holdings": tool_registry.get_holdings,
    "search_trade_history": tool_registry.search_trade_history,
    "list_open_orders": tool_registry.list_open_orders,
    "get_exchange_rate": tool_registry.get_exchange_rate,
    "get_asset_krw_conversion": tool_registry.get_asset_krw_conversion,
    "get_market_calendar": tool_registry.get_market_calendar,
    "get_asset_price": tool_registry.get_asset_price,
    "get_asset_orderbook": tool_registry.get_asset_orderbook,
    "get_asset_candles": tool_registry.get_asset_candles,
    "get_crypto_market_context": tool_registry.get_crypto_market_context,
    "get_asset_outlook": tool_registry.get_asset_outlook,
    "search_web": tool_registry.search_web,
}


def build_tool_schemas() -> list[dict]:
    """Return OpenAI-compatible tool schemas for LLM bind_tools."""
    return [
        {"type": "function", "function": schema}
        for schema in FUNCTION_SCHEMAS
    ]


def _build_tool_message(tool_name: str, arguments: dict, fallback_text: str) -> str:
    """Build the query message string for a tool call, matching chat_service patterns."""
    query = str(arguments.get("query") or fallback_text).strip()
    if tool_name in {"search_web", "add_watchlist_item", "get_asset_outlook", "remove_watchlist_item"}:
        return query
    if tool_name == "get_crypto_market_context":
        return f"{query} 코인 분석해줘"
    if tool_name == "get_asset_price":
        return f"{query} 현재가 알려줘"
    if tool_name == "get_asset_orderbook":
        return f"{query} 호가 알려줘"
    if tool_name == "get_asset_candles":
        return f"{query} 캔들 흐름 알려줘"
    if tool_name == "get_market_calendar":
        date = str(arguments.get("date") or "").strip()
        market_country = str(arguments.get("market_country") or "").strip().upper()
        market_text = "한국장" if market_country == "KR" else "미국장" if market_country == "US" else ""
        return " ".join(part for part in [date, market_text, "장 운영 여부 알려줘"] if part)
    if tool_name == "get_exchange_rate":
        base = str(arguments.get("base_currency") or "").strip()
        quote = str(arguments.get("quote_currency") or "KRW").strip()
        return f"{base}/{quote} 환율 알려줘".strip()
    if tool_name == "get_home_market_rankings":
        asset_type = str(arguments.get("asset_type") or "").upper()
        asset_text = "코인" if asset_type == "CRYPTO" else "국내주식" if asset_type == "STOCK" else ""
        ranking = arguments.get("ranking") or "상승률"
        return f"{asset_text} {ranking} 순위"
    if tool_name == "search_trade_history":
        parts = ["거래내역"]
        if arguments.get("symbol"):
            parts.append(str(arguments["symbol"]))
        return " ".join(parts)
    if tool_name == "list_open_orders":
        parts = ["미체결 주문"]
        if arguments.get("symbol"):
            parts.append(str(arguments["symbol"]))
        return " ".join(parts)
    if tool_name == "get_asset_krw_conversion":
        quantity = arguments.get("quantity")
        quantity_text = f"{quantity}주" if quantity else ""
        return " ".join(part for part in [query, quantity_text, "원화로 계산해줘"] if part)
    return query


def execute_tool_call(tool_name: str, arguments: dict, auth_header: str) -> str:
    """Execute a tool call and return the result as a JSON string.

    Raises SafetyGuardError for blocked tools (e.g., place_order).
    """
    enforce_tool_safety(tool_name, arguments)

    tool_func = _TOOL_FUNCTION_MAP.get(tool_name)
    if not tool_func:
        return json.dumps(
            {"reply": f"'{tool_name}' 도구를 찾을 수 없습니다.", "data": {"error": "unknown_tool"}},
            ensure_ascii=False,
        )

    tool_message = _build_tool_message(tool_name, arguments, "")
    try:
        result = tool_func(auth_header, tool_message, **arguments)
    except Exception as error:
        logger.exception("Tool execution failed: tool=%s", tool_name)
        return json.dumps(
            {"reply": f"도구 실행 중 오류가 발생했습니다: {str(error)[:200]}", "data": {"error": "tool_error"}},
            ensure_ascii=False,
        )

    if not isinstance(result, dict):
        return json.dumps({"reply": str(result or ""), "data": {}}, ensure_ascii=False)

    return json.dumps(result, ensure_ascii=False, default=str)
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `cd backend && python -m pytest tests/chatbot/test_langchain_tools.py -v`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add backend/services/chatbot/langchain_tools.py backend/tests/chatbot/test_langchain_tools.py
git commit -m "feat: LangGraph 도구 래퍼 (tool_registry 재사용)"
```

---

### Task 4: LangGraph Agent 정의 (`agent.py`)

**Files:**
- Create: `backend/services/chatbot/agent.py`
- Test: `backend/tests/chatbot/test_agent.py`

**Interfaces:**
- Consumes: `llm_provider.create_chatbot_llm() -> BaseChatModel` (Task 2)
- Consumes: `langchain_tools.build_tool_schemas() -> list[dict]` (Task 3)
- Consumes: `langchain_tools.execute_tool_call(tool_name, arguments, auth_header) -> str` (Task 3)
- Produces: `create_chatbot_agent(llm) -> CompiledGraph`
- Produces: `run_agent(agent, messages, config) -> dict` — `{"reply": str, "actions": list, "meta": dict}` 형식
- Produces: `stream_agent(agent, messages, config, on_delta, on_trace) -> dict` — 스트리밍 버전

- [ ] **Step 1: 테스트 파일 작성**

```python
# backend/tests/chatbot/test_agent.py
import os
import pytest


def test_create_chatbot_agent_returns_compiled_graph(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    from backend.services.chatbot.llm_provider import create_chatbot_llm
    from backend.services.chatbot.agent import create_chatbot_agent

    llm = create_chatbot_llm()
    agent = create_chatbot_agent(llm)
    assert agent is not None
    assert hasattr(agent, "invoke")


def test_agent_state_has_required_keys():
    from backend.services.chatbot.agent import AgentState
    assert "messages" in AgentState.__annotations__
    assert "trace_steps" in AgentState.__annotations__
    assert "auth_header" in AgentState.__annotations__
    assert "user_id" in AgentState.__annotations__


def test_max_tool_rounds_default():
    from backend.services.chatbot.agent import MAX_TOOL_ROUNDS
    assert MAX_TOOL_ROUNDS >= 5
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `cd backend && python -m pytest tests/chatbot/test_agent.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: agent.py 구현**

```python
# backend/services/chatbot/agent.py
"""LangGraph chatbot agent with tool-calling loop."""
import json
import logging
from typing import Annotated, Callable, TypedDict

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)
from langgraph.graph import END, StateGraph
from langgraph.graph.message import add_messages

from backend.services.chatbot.langchain_tools import (
    build_tool_schemas,
    execute_tool_call,
)

logger = logging.getLogger(__name__)
MAX_TOOL_ROUNDS = 5


class AgentState(TypedDict):
    """State for the chatbot LangGraph agent."""
    messages: Annotated[list[BaseMessage], add_messages]
    trace_steps: list[dict]
    user_id: str
    auth_header: str
    request_id: str
    tool_round: int


def _should_continue(state: AgentState) -> str:
    """Determine whether to call tools or end."""
    messages = state.get("messages") or []
    if not messages:
        return END

    last_message = messages[-1]
    if not isinstance(last_message, AIMessage):
        return END

    tool_calls = getattr(last_message, "tool_calls", None) or []
    if not tool_calls:
        return END

    tool_round = state.get("tool_round") or 0
    if tool_round >= MAX_TOOL_ROUNDS:
        logger.warning(
            "Max tool rounds reached (%d). Stopping. request_id=%s",
            MAX_TOOL_ROUNDS,
            state.get("request_id"),
        )
        return END

    return "tools"


def _call_model_node(state: AgentState, llm: BaseChatModel) -> dict:
    """Invoke the LLM with current messages."""
    messages = state.get("messages") or []
    tool_schemas = build_tool_schemas()
    llm_with_tools = llm.bind_tools(tool_schemas)
    response = llm_with_tools.invoke(messages)
    return {"messages": [response]}


def _tools_node(state: AgentState) -> dict:
    """Execute tool calls from the last AI message."""
    messages = state.get("messages") or []
    last_message = messages[-1]
    auth_header = state.get("auth_header") or ""
    trace_steps = list(state.get("trace_steps") or [])
    tool_round = (state.get("tool_round") or 0) + 1

    tool_messages: list[ToolMessage] = []
    for tool_call in getattr(last_message, "tool_calls", []) or []:
        tool_name = tool_call.get("name") or ""
        arguments = tool_call.get("args") or {}
        tool_call_id = tool_call.get("id") or ""

        trace_steps.append({"kind": "tool", "label": f"도구 실행: {tool_name}"})

        try:
            result_str = execute_tool_call(tool_name, arguments, auth_header)
        except Exception as error:
            result_str = json.dumps(
                {"reply": f"도구 실행 실패: {str(error)[:200]}", "data": {"error": "tool_error"}},
                ensure_ascii=False,
            )

        tool_messages.append(
            ToolMessage(content=result_str, tool_call_id=tool_call_id)
        )

    return {
        "messages": tool_messages,
        "trace_steps": trace_steps,
        "tool_round": tool_round,
    }


def create_chatbot_agent(llm: BaseChatModel):
    """Create a compiled LangGraph agent with the given LLM.

    The agent follows a call_model -> tools loop pattern.
    """
    graph = StateGraph(AgentState)

    graph.add_node("call_model", lambda state: _call_model_node(state, llm))
    graph.add_node("tools", _tools_node)

    graph.set_entry_point("call_model")
    graph.add_conditional_edges("call_model", _should_continue, {"tools": "tools", END: END})
    graph.add_edge("tools", "call_model")

    return graph.compile()


def run_agent(
    agent,
    *,
    system_prompt: str,
    user_message: str,
    history: list[dict] | None = None,
    user_id: str = "",
    auth_header: str = "",
    request_id: str = "",
) -> dict:
    """Run the agent synchronously and return the final result."""
    messages: list[BaseMessage] = [SystemMessage(content=system_prompt)]

    for item in history or []:
        role = item.get("role")
        content = str(item.get("content") or "").strip()
        if not content:
            continue
        if role == "user":
            messages.append(HumanMessage(content=content))
        elif role == "assistant":
            messages.append(AIMessage(content=content))

    messages.append(HumanMessage(content=user_message))

    initial_state = {
        "messages": messages,
        "trace_steps": [{"kind": "request", "label": "요청 분석"}],
        "user_id": user_id,
        "auth_header": auth_header,
        "request_id": request_id,
        "tool_round": 0,
    }

    final_state = agent.invoke(initial_state)

    final_messages = final_state.get("messages") or []
    reply = ""
    for msg in reversed(final_messages):
        if isinstance(msg, AIMessage) and msg.content:
            reply = str(msg.content).strip()
            break

    if not reply:
        reply = "응답을 만들지 못했습니다. 잠시 후 다시 시도해 주세요."

    tool_results = []
    for msg in final_messages:
        if isinstance(msg, ToolMessage):
            try:
                tool_results.append(json.loads(msg.content))
            except (TypeError, ValueError):
                tool_results.append({"reply": msg.content})

    return {
        "reply": reply,
        "actions": [],
        "meta": {
            "user_id": user_id,
            "request_id": request_id,
            "trace_steps": final_state.get("trace_steps") or [],
            "tool_results": tool_results,
            "tool_rounds": final_state.get("tool_round") or 0,
            "source": "LANGGRAPH_AGENT",
        },
    }


def stream_agent(
    agent,
    *,
    system_prompt: str,
    user_message: str,
    history: list[dict] | None = None,
    user_id: str = "",
    auth_header: str = "",
    request_id: str = "",
    on_delta: Callable[[str], None] | None = None,
    on_trace: Callable[[dict], None] | None = None,
) -> dict:
    """Run the agent with streaming, calling on_delta for each token."""
    messages: list[BaseMessage] = [SystemMessage(content=system_prompt)]

    for item in history or []:
        role = item.get("role")
        content = str(item.get("content") or "").strip()
        if not content:
            continue
        if role == "user":
            messages.append(HumanMessage(content=content))
        elif role == "assistant":
            messages.append(AIMessage(content=content))

    messages.append(HumanMessage(content=user_message))

    initial_state = {
        "messages": messages,
        "trace_steps": [{"kind": "request", "label": "요청 분석"}],
        "user_id": user_id,
        "auth_header": auth_header,
        "request_id": request_id,
        "tool_round": 0,
    }

    trace_steps: list[dict] = [{"kind": "request", "label": "요청 분석"}]
    reply_parts: list[str] = []
    tool_results: list[dict] = []
    tool_rounds = 0

    for event in agent.stream(initial_state, stream_mode="updates"):
        for node_name, node_output in event.items():
            node_messages = node_output.get("messages") or []
            for msg in node_messages:
                if isinstance(msg, AIMessage):
                    content = str(msg.content or "").strip()
                    tool_calls = getattr(msg, "tool_calls", None) or []
                    if content and not tool_calls:
                        reply_parts.append(content)
                        if on_delta:
                            on_delta(content)
                    elif tool_calls and on_trace:
                        for tc in tool_calls:
                            on_trace({"kind": "openai_tool_call", "label": f"도구 호출: {tc.get('name')}"})

                elif isinstance(msg, ToolMessage):
                    if on_trace:
                        on_trace({"kind": "tool_done", "label": "도구 결과 수신"})
                    try:
                        tool_results.append(json.loads(msg.content))
                    except (TypeError, ValueError):
                        tool_results.append({"reply": msg.content})

            if "trace_steps" in node_output:
                new_steps = node_output["trace_steps"]
                for step in new_steps:
                    if step not in trace_steps:
                        trace_steps.append(step)
                        if on_trace:
                            on_trace(step)
            if "tool_round" in node_output:
                tool_rounds = node_output["tool_round"]

    reply = "".join(reply_parts).strip()
    if not reply:
        reply = "응답을 만들지 못했습니다. 잠시 후 다시 시도해 주세요."

    return {
        "reply": reply,
        "actions": [],
        "meta": {
            "user_id": user_id,
            "request_id": request_id,
            "trace_steps": trace_steps,
            "tool_results": tool_results,
            "tool_rounds": tool_rounds,
            "source": "LANGGRAPH_AGENT",
        },
    }
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `cd backend && python -m pytest tests/chatbot/test_agent.py -v`
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add backend/services/chatbot/agent.py backend/tests/chatbot/test_agent.py
git commit -m "feat: LangGraph 챗봇 Agent 상태 그래프 구현"
```

---

### Task 5: ChatbotService에 Agent 통합

**Files:**
- Modify: `backend/services/chatbot/chat_service.py`
- Test: `backend/tests/chatbot/test_chat_service_agent.py`

**Interfaces:**
- Consumes: `llm_provider.create_chatbot_llm()` (Task 2)
- Consumes: `agent.create_chatbot_agent(llm)` (Task 4)
- Consumes: `agent.run_agent(agent, ...)` (Task 4)
- Consumes: `agent.stream_agent(agent, ...)` (Task 4)
- Produces: `ChatbotService.reply()` — 기존 시그니처 100% 호환, 내부만 Agent로 교체

- [ ] **Step 1: 테스트 파일 작성**

```python
# backend/tests/chatbot/test_chat_service_agent.py
import pytest


def test_chatbot_service_has_agent_attribute(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    from backend.services.chatbot.chat_service import ChatbotService
    service = ChatbotService()
    assert hasattr(service, "agent")
    assert service.agent is not None


def test_chatbot_service_reply_signature_unchanged(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    import inspect
    from backend.services.chatbot.chat_service import ChatbotService
    sig = inspect.signature(ChatbotService.reply)
    param_names = list(sig.parameters.keys())
    assert "message" in param_names
    assert "user_id" in param_names
    assert "auth_header" in param_names
    assert "trace_callback" in param_names
    assert "delta_callback" in param_names
    assert "request_id" in param_names
    assert "structured_order" in param_names
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `cd backend && python -m pytest tests/chatbot/test_chat_service_agent.py -v`
Expected: FAIL (agent 속성 없음)

- [ ] **Step 3: chat_service.py 수정 — Agent 초기화 추가**

`ChatbotService.__init__`에 Agent 인스턴스를 추가한다:

```python
# chat_service.py __init__ 수정 (기존 코드 아래에 추가)
from backend.services.chatbot.llm_provider import create_chatbot_llm, get_chatbot_config
from backend.services.chatbot.agent import create_chatbot_agent, run_agent, stream_agent

class ChatbotService:
    def __init__(self):
        self.system_prompt = build_system_prompt()
        self.llm_client = ChatbotLLMClient()  # 레거시 유지 (폴백용)
        self.rag_service = ChatbotRAGService()
        self.knowledge_repository = KnowledgeRepository()
        self.memory_service = ChatbotMemoryService(self.knowledge_repository)
        self.conversation_repository = ChatbotConversationRepository()
        # LangGraph Agent 초기화
        self._chatbot_config = get_chatbot_config()
        try:
            self._llm = create_chatbot_llm()
            self.agent = create_chatbot_agent(self._llm)
        except Exception:
            logger.warning("LangGraph Agent 초기화 실패. 레거시 LLM 클라이언트를 사용합니다.")
            self._llm = None
            self.agent = None
```

- [ ] **Step 4: chat_service.py 수정 — _run_agent 메서드 추가**

`reply()` 메서드의 LLM 직접 호출 부분(L972~L1050)을 `_run_agent()`로 대체한다. 기존 전처리(주문 파서, pending_action, 사용자 노트/메모리 조회 등)는 그대로 유지하고, **LLM 호출 부분만** Agent로 교체한다:

```python
def _run_agent(
    self,
    text: str,
    user_id: str | None,
    auth_header: str | None,
    user_timezone: str | None = None,
    trace_callback: TraceCallback | None = None,
    delta_callback: Callable[[str], None] | None = None,
    request_id: str | None = None,
) -> dict:
    """Run LangGraph agent for the given user message."""
    self._emit_trace(trace_callback, "history", "대화 이력 확인")
    history = self._load_recent_history(auth_header, user_id)

    self._emit_trace(trace_callback, "llm", "LLM 답변 준비")
    system_prompt = self._build_prompt_for_user(
        auth_header, user_id, text, user_timezone, trace_callback,
    )

    agent_kwargs = {
        "system_prompt": system_prompt,
        "user_message": text,
        "history": history,
        "user_id": user_id or "",
        "auth_header": auth_header or "",
        "request_id": request_id or "",
    }

    if delta_callback:
        self._emit_trace(trace_callback, "agent", "Agent 스트리밍 실행")
        result = stream_agent(
            self.agent,
            **agent_kwargs,
            on_delta=delta_callback,
            on_trace=lambda step: self._emit_trace(
                trace_callback, step.get("kind", "tool"), step.get("label", "도구 처리")
            ),
        )
    else:
        self._emit_trace(trace_callback, "agent", "Agent 실행")
        result = run_agent(self.agent, **agent_kwargs)

    reply_text = result.get("reply") or ""
    self._record_exchange(auth_header, user_id, text, reply_text)

    return result
```

- [ ] **Step 5: chat_service.py 수정 — reply() 메서드에서 Agent 분기**

기존 `reply()` 메서드의 L972 이후(LLM 직접 호출 구간)를 다음으로 교체한다:

```python
        # (기존 코드: L953~L970 tool_result 블록 이후)

        # LangGraph Agent 사용 가능하면 Agent로 실행
        if self.agent is not None:
            return self._run_agent(
                text, user_id, auth_header, user_timezone,
                trace_callback, delta_callback, request_id,
            )

        # Agent 미사용 시 레거시 LLM 클라이언트 경로 (기존 코드 유지)
        self._emit_trace(trace_callback, "history", "대화 이력 확인")
        history = self._load_recent_history(auth_header, user_id)
        # ... (기존 코드 L972~L1050 그대로)
```

- [ ] **Step 6: 테스트 통과 확인**

Run: `cd backend && python -m pytest tests/chatbot/test_chat_service_agent.py -v`
Expected: 2 passed

- [ ] **Step 7: Commit**

```bash
git add backend/services/chatbot/chat_service.py backend/tests/chatbot/test_chat_service_agent.py
git commit -m "feat: ChatbotService에 LangGraph Agent 통합 (레거시 폴백 유지)"
```

---

### Task 6: SSE 스트리밍 라우트 전환

**Files:**
- Modify: `backend/routes/chatbot.py`
- Test: 수동 검증 (프론트엔드 SSE 스트리밍 동작)

**Interfaces:**
- Consumes: `ChatbotService.reply(delta_callback=..., trace_callback=...)` — Task 5에서 Agent 스트리밍 지원 완료
- Produces: 기존 SSE 이벤트 포맷(`trace`, `delta`, `done`, `error`) 100% 호환

- [ ] **Step 1: chatbot.py 스트리밍 라우트 확인**

현재 `stream_chatbot_message()`의 스레드+큐 패턴은 이미 `delta_callback`과 `trace_callback`을 사용하고 있다. Task 5에서 `_run_agent()`가 이 콜백들을 LangGraph Agent에 전달하므로, **라우트 코드 자체는 변경 불필요**하다.

다만, Agent의 스트리밍이 정상 동작하는지 확인하기 위해 기존 `_chunk_reply_text` 폴백 로직이 Agent 스트리밍에서는 불필요할 수 있다. Agent가 `on_delta`로 토큰을 직접 전달하므로, `emitted_live_delta` 플래그가 `True`가 되어 기존 chunk 분할 로직이 자동 스킵된다.

수동 확인: SSE 스트리밍 엔드포인트를 호출하여 `event: delta`, `event: trace`, `event: done` 이벤트가 정상 발생하는지 확인한다.

- [ ] **Step 2: Commit (변경 없으면 스킵)**

라우트 코드 변경이 필요 없으면 이 단계는 스킵한다.

---

### Task 7: 통합 테스트 및 검증

**Files:**
- Test: `backend/tests/chatbot/test_integration_agent.py`

**Interfaces:**
- Consumes: 전체 Task 1~6의 결과물

- [ ] **Step 1: 통합 테스트 작성**

```python
# backend/tests/chatbot/test_integration_agent.py
import os
import pytest


@pytest.fixture(autouse=True)
def mock_env(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")


def test_full_pipeline_chatbot_service_creates_agent():
    from backend.services.chatbot.chat_service import ChatbotService
    service = ChatbotService()
    assert service.agent is not None


def test_full_pipeline_agent_has_tool_schemas():
    from backend.services.chatbot.langchain_tools import build_tool_schemas
    schemas = build_tool_schemas()
    names = [s["function"]["name"] for s in schemas]
    expected_tools = [
        "get_asset_price", "get_asset_orderbook", "get_asset_candles",
        "get_holdings", "get_portfolio_summary", "get_exchange_rate",
        "get_market_calendar", "search_web", "get_crypto_market_context",
        "get_asset_outlook", "get_home_market_rankings",
        "search_trade_history", "list_open_orders",
        "add_watchlist_item", "remove_watchlist_item",
        "get_asset_krw_conversion",
    ]
    for tool_name in expected_tools:
        assert tool_name in names, f"Missing tool: {tool_name}"


def test_full_pipeline_failover_chain_structure():
    from backend.services.chatbot.llm_provider import create_chatbot_llm
    llm = create_chatbot_llm()
    assert hasattr(llm, "invoke")
    # with_fallbacks creates a RunnableWithFallbacks
    assert hasattr(llm, "first") or hasattr(llm, "fallbacks")


def test_full_pipeline_config_values():
    from backend.services.chatbot.llm_provider import get_chatbot_config
    config = get_chatbot_config()
    assert config["max_input_chars"] >= 50000
    assert config["max_history_messages"] >= 50
    assert config["max_tool_rounds"] >= 5
    assert config["max_output_tokens"] >= 2048
```

- [ ] **Step 2: 통합 테스트 실행**

Run: `cd backend && python -m pytest tests/chatbot/test_integration_agent.py -v`
Expected: 4 passed

- [ ] **Step 3: 전체 테스트 스위트 실행**

Run: `cd backend && python -m pytest tests/ -v --tb=short`
Expected: 기존 테스트 + 새 테스트 모두 통과, 회귀 없음

- [ ] **Step 4: Commit**

```bash
git add backend/tests/chatbot/test_integration_agent.py
git commit -m "test: LangGraph Agent 통합 테스트"
```

---

### Task 8: 수동 검증 체크리스트

**Files:** 없음 (수동 검증)

- [ ] **Step 1: Flask 서버 기동 및 기본 대화 테스트**

Run: `cd backend && python app.py`
- 챗봇에 "안녕" 입력 → 정상 응답 확인
- "삼성전자 현재가" 입력 → `get_asset_price` Tool 호출 확인
- "비트코인 가격이랑 최근 뉴스 같이 알려줘" 입력 → 복합 Tool 호출(get_asset_price + search_web) 확인

- [ ] **Step 2: Failover 동작 확인**

`GEMINI_API_KEY`를 임시로 잘못된 값으로 설정:
- 챗봇 질문 시 GPT 폴백으로 자동 전환되는지 확인
- 응답 meta에서 사용된 모델 정보 확인

- [ ] **Step 3: SSE 스트리밍 확인**

브라우저 개발자도구 → Network → `/api/chatbot/stream` 요청:
- `event: trace` (도구 실행 추적) 이벤트 정상 수신 확인
- `event: delta` (토큰 단위) 이벤트 정상 수신 확인
- `event: done` (최종 결과) 이벤트 정상 수신 확인

- [ ] **Step 4: 기존 기능 회귀 확인**

- 주문 폼 리다이렉트: "삼성전자 1주 매수해줘" → `build_order_form_redirect` 동작 확인
- pending_action: 연속 대화에서 "네", "조회해줘" 같은 확인 문구 처리 정상 확인
- 투자성향 프롬프트: 투자성향이 등록된 사용자의 답변에 성향이 반영되는지 확인
