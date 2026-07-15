# Chatbot Crypto Market Context Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 챗봇이 코인 질문에 대해 시세, 호가, 캔들 흐름, ML 활성 신호, 거래소별 주의사항을 한 번에 묶은 코인 전용 컨텍스트를 반환하도록 만든다.

**Architecture:** 기존 `backend/services/chatbot/tool_registry.py`에 `get_crypto_market_context` 도구를 추가하고, 기존 내부 API(`/api/chart/quote`, `/api/chart/orderbook`, `/api/chart/candles`)와 `build_single_asset_ml_outlook`를 조합한다. 신규 외부 API나 DB 테이블은 만들지 않고, `run_chatbot_tool`의 라우팅과 `FUNCTION_SCHEMAS`에만 연결한다.

**Tech Stack:** Flask, Python, pytest, Supabase-backed internal API, existing Chatbot tool registry.

## Global Constraints

- 모든 사용자 설명과 문서는 한국어로 작성한다.
- 실제 금융 데이터는 프로젝트 도구 조회 결과만 사용하고 추측하지 않는다.
- 코인 매매 실행은 사용자 승인 없이 수행하지 않는다.
- Coinone 시장가 주문 제한, Binance 선물 실거래 잠금, REAL/MOCK 분기를 챗봇 문구에서 명확히 유지한다.
- 신규 에러 응답은 원문 예외를 사용자에게 그대로 노출하지 않는다.

---

### Task 1: 코인 통합 컨텍스트 도구

**Files:**
- Modify: `backend/services/chatbot/tool_registry.py`
- Test: `tests/backend/test_chatbot_tool_registry_price.py`

**Interfaces:**
- Produces: `get_crypto_market_context(auth_header: str, message: str) -> dict`
- Produces data source: `CRYPTO_MARKET_CONTEXT`

- [ ] **Step 1: Write the failing test**

`tests/backend/test_chatbot_tool_registry_price.py`에 `리플 코인 분석해줘`가 `CRYPTO_MARKET_CONTEXT`로 라우팅되고 quote/orderbook/candles/ML 데이터를 합치는 테스트를 추가한다.

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/backend/test_chatbot_tool_registry_price.py::test_crypto_analysis_routes_to_market_context -q`
Expected: FAIL because `get_crypto_market_context` routing is not implemented.

- [ ] **Step 3: Write minimal implementation**

`tool_registry.py`에 코인 심볼 해석, quote/orderbook/candles 조회, ML outlook 호출, 거래소 주의사항 생성 로직을 추가한다.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/backend/test_chatbot_tool_registry_price.py::test_crypto_analysis_routes_to_market_context -q`
Expected: PASS.

### Task 2: Function Calling 스키마 연결

**Files:**
- Modify: `backend/services/chatbot/function_calling.py`
- Test: `tests/backend/test_chatbot_tool_registry_price.py`

**Interfaces:**
- Produces schema name: `get_crypto_market_context`

- [ ] **Step 1: Write the failing test**

`FUNCTION_SCHEMAS`에 `get_crypto_market_context`가 있고 `query` 파라미터가 필수인지 검증한다.

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/backend/test_chatbot_tool_registry_price.py::test_function_schemas_include_crypto_market_context -q`
Expected: FAIL because schema is missing.

- [ ] **Step 3: Write minimal implementation**

`function_calling.py`에 도구 스키마를 추가하고, `chat_service.py`의 import/LLM tool 실행 연결이 기존 패턴을 따르도록 확인한다.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/backend/test_chatbot_tool_registry_price.py::test_function_schemas_include_crypto_market_context -q`
Expected: PASS.

### Task 3: 문서 갱신 및 회귀 검증

**Files:**
- Modify: `TradingBot.md`
- Modify: `project_structure.md`

**Interfaces:**
- Documents: 코인 통합 컨텍스트 도구의 목적, 데이터 소스, 안전 제약

- [ ] **Step 1: Update docs**

챗봇 도구 설명에 `get_crypto_market_context`를 추가하고 Coinone/Binance 구분 및 ML v9 참고 신호 원칙을 적는다.

- [ ] **Step 2: Run focused tests**

Run: `pytest tests/backend/test_chatbot_tool_registry_price.py -q`
Expected: PASS.

- [ ] **Step 3: Inspect diff**

Run: `git diff -- backend/services/chatbot/tool_registry.py backend/services/chatbot/function_calling.py tests/backend/test_chatbot_tool_registry_price.py TradingBot.md project_structure.md docs/superpowers/plans/2026-07-15-chatbot-crypto-market-context.md`
Expected: Only intended files changed.
