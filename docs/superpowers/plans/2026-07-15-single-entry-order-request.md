# 상단 단일 진입 매매 요청 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 상단 `매매 요청` 버튼에서만 시작하는 주식·코인 현물·바이낸스 USD-M 선물 공통 3단계 주문 흐름을 구현하고, 서명된 사전검증 결과가 있는 경우에만 승인 대기 제안을 생성한다.

**Architecture:** 기존 `trade.py`의 거래소 클라이언트 생성, 수량 필터, 잔고 검증, 실거래 하드캡, 승인 재검증을 재사용한다. 순수 주문 계약과 서명 토큰은 별도 서비스로 분리하고, 프론트엔드는 조회·사전검증 API를 직접 호출하되 제안 생성은 구조화 챗봇 요청을 통해 기존 Realtime 승인 카드 흐름에 연결한다.

**Tech Stack:** Flask, Python 3, React 19, Vite, Tailwind CSS v4, Supabase Auth/PostgREST/Realtime, Node test runner, pytest

## Global Constraints

- 주문 진입점은 챗봇 상단 `매매 요청` 버튼 하나로 제한한다.
- 자연어 주문 요청은 주문 파라미터를 추출하거나 폼을 열지 않는다.
- 구조화 요청 누락값을 `TOSS`, `REAL`, `BUY`, `LIMIT`로 보정하지 않는다.
- 실거래 1회 한도는 레버리지 적용 전 명목 주문금액의 원화 환산액 100,000원이다.
- 바이낸스 USD-M 선물 서비스 레버리지 상한은 10배이며 환경값은 이를 낮추는 데만 사용한다.
- 외부 API 오류는 `format_error_payload()`로 표준화하고 비밀 키를 응답하지 않는다.
- 본 작업은 데스크톱 화면이 범위이며 조건감시·자연어 프리필·모바일 최적화는 제외한다.

---

### Task 1: 주문 계약, 선물 변환, 사전검증 토큰

**Files:**
- Create: `backend/services/order_entry_service.py`
- Create: `backend/tests/test_order_entry_service.py`
- Modify: `backend/routes/trade.py`

**Interfaces:**
- Produces: `normalize_order_request(values: dict) -> dict`
- Produces: `resolve_futures_execution(intent: str, position_mode: str, position_side: str | None) -> dict`
- Produces: `resolve_service_leverage_limit(exchange_limit: int | None, configured_limit: str | None) -> int`
- Produces: `order_request_hash(values: dict) -> str`
- Produces: `issue_precheck_token(user_id: str, order: dict, precheck: dict, secret: str, now: int | None = None) -> str`
- Produces: `verify_precheck_token(token: str, user_id: str, order: dict, secret: str, now: int | None = None) -> dict`

- [ ] **Step 1: 필수값 누락, 선물 One-way/Hedge 변환, 레버리지 상한, 토큰 변조·만료 테스트를 작성한다.**

```python
def test_normalize_order_request_does_not_apply_defaults():
    with pytest.raises(ValueError, match="누락"):
        normalize_order_request({"symbol": "005930"})

def test_one_way_short_close_forces_reduce_only_buy():
    assert resolve_futures_execution("CLOSE_POSITION", "ONE_WAY", "SHORT") == {
        "side": "BUY", "position_side": "BOTH", "reduce_only": True,
    }

def test_precheck_token_rejects_changed_quantity():
    token = issue_precheck_token("user-1", ORDER, PRECHECK, "secret", now=100)
    with pytest.raises(ValueError, match="일치"):
        verify_precheck_token(token, "user-1", {**ORDER, "quantity": 2}, "secret", now=101)
```

- [ ] **Step 2: 테스트를 실행해 새 서비스 부재로 실패하는지 확인한다.**

Run: `python3 -m pytest -q backend/tests/test_order_entry_service.py`
Expected: FAIL with `ModuleNotFoundError: backend.services.order_entry_service`

- [ ] **Step 3: HMAC-SHA256 서명, 5분 만료, 정규화된 주문 SHA-256 해시와 선물 변환을 최소 구현한다.**

```python
SERVICE_LEVERAGE_LIMIT = 10
PRECHECK_TOKEN_TTL_SECONDS = 300

def resolve_service_leverage_limit(exchange_limit, configured_limit):
    configured = int(configured_limit or SERVICE_LEVERAGE_LIMIT)
    service_limit = min(max(configured, 1), SERVICE_LEVERAGE_LIMIT)
    return min(service_limit, int(exchange_limit)) if exchange_limit else service_limit
```

- [ ] **Step 4: 단위 테스트 통과를 확인한다.**

Run: `python3 -m pytest -q backend/tests/test_order_entry_service.py`
Expected: PASS

### Task 2: 주문 입력 조회 API와 검증 토큰 발급

**Files:**
- Create: `backend/tests/test_trade_order_entry_routes.py`
- Modify: `backend/routes/trade.py`

**Interfaces:**
- Produces: `GET /api/trade/order-entry/accounts`
- Produces: `GET /api/trade/order-entry/symbols`
- Produces: `GET /api/trade/order-entry/holdings`
- Produces: `GET /api/trade/order-entry/context`
- Extends: `POST /api/trade/precheck` with `order_hash`, `precheck_token`, `can_create_proposal`

- [ ] **Step 1: 인증, 비밀정보 제외, 선택 종목 필수, 보유 목록, 컨텍스트와 토큰 발급 라우트 테스트를 작성한다.**

```python
def test_order_entry_accounts_never_returns_encrypted_keys(client, monkeypatch):
    response = client.get("/api/trade/order-entry/accounts", headers=AUTH)
    assert response.status_code == 200
    assert "encrypted_access_key" not in response.get_data(as_text=True)

def test_precheck_returns_signed_token_without_creating_proposal(client, monkeypatch):
    response = client.post("/api/trade/precheck", json=VALID_ORDER, headers=AUTH)
    data = response.get_json()["data"]
    assert data["precheck_token"]
    assert data["order_hash"]
    assert inserts == []
```

- [ ] **Step 2: 신규 라우트가 없어 404 또는 필드 누락으로 실패하는지 확인한다.**

Run: `python3 -m pytest -q backend/tests/test_trade_order_entry_routes.py`
Expected: FAIL

- [ ] **Step 3: 기존 사용자 키·클라이언트·심볼 메타데이터·잔고 조회기를 재사용해 안전한 DTO를 반환한다.**

```python
return jsonify({"success": True, "data": {"accounts": safe_accounts}})
```

- [ ] **Step 4: `precheck_manual_order()`를 strict 정규화하고 차단 사유가 없을 때만 서명 토큰을 포함한다.**

```python
order = normalize_order_request(request.json or {})
payload = _build_precheck_payload(...)
payload["order_hash"] = order_request_hash(order)
payload["precheck_token"] = issue_precheck_token(user_id, order, payload, _precheck_secret())
payload["can_create_proposal"] = not _collect_precheck_blockers(payload, order["broker_env"])
```

- [ ] **Step 5: 라우트와 기존 주문 안전 테스트를 통과시킨다.**

Run: `python3 -m pytest -q backend/tests/test_trade_order_entry_routes.py backend/tests/test_trade_proposal_approval_safety.py`
Expected: PASS

### Task 3: 검증된 구조화 요청만 제안 생성

**Files:**
- Modify: `backend/services/chatbot/chat_service.py`
- Modify: `backend/services/chatbot/tool_registry.py`
- Modify: `tests/backend/test_chatbot_order_form_policy.py`

**Interfaces:**
- Consumes: `verify_precheck_token(...) -> dict`
- Produces: 토큰에 서명된 사전검증 스냅샷을 `raw_order_payload.precheck`로 저장하는 `PENDING` 제안

- [ ] **Step 1: 누락 기본값, 토큰 누락·변조·만료, 중복 제안 테스트를 먼저 작성한다.**

```python
def test_structured_order_without_precheck_token_is_rejected(monkeypatch):
    result = service._create_proposal_from_structured(AUTH, USER_ID, VALID_ORDER)
    assert result["data"]["reason"] == "precheck_required"
    assert inserts == []
```

- [ ] **Step 2: 기존 구현이 기본값을 넣거나 토큰 없이 진행해 실패하는지 확인한다.**

Run: `python3 -m pytest -q tests/backend/test_chatbot_order_form_policy.py`
Expected: FAIL

- [ ] **Step 3: 구조화 요청을 strict 정규화하고 토큰 검증 결과로만 `create_trade_proposal()`을 호출한다.**

```python
verified = verify_precheck_token(token, user_id, order, secret)
return create_trade_proposal(auth_header, {
    **order,
    "raw_order_payload": {
        "source": "ORDER_ENTRY",
        "precheck_status": "OK",
        "precheck": verified["precheck"],
        "order_hash": verified["order_hash"],
        "proposal_idempotency_key": order["idempotency_key"],
    },
})
```

- [ ] **Step 4: 챗봇 정책 테스트 통과를 확인한다.**

Run: `python3 -m pytest -q tests/backend/test_chatbot_order_form_policy.py`
Expected: PASS

### Task 4: 데스크톱 3단계 주문 UI와 문서 정합성

**Files:**
- Create: `frontend/src/features/chatbot/orderEntryModel.js`
- Create: `frontend/src/features/chatbot/orderEntryModel.test.mjs`
- Create: `frontend/src/features/chatbot/OrderEntryFlow.jsx`
- Modify: `frontend/src/features/chatbot/chatbotApi.js`
- Modify: `frontend/src/features/chatbot/ChatbotWidget.jsx`
- Modify: `frontend/src/features/chatbot/chatbotOrderForm.test.mjs`
- Modify: `frontend/src/features/chatbot/ChatbotWidget.quickActions.test.mjs`
- Modify: `project_structure.md`
- Modify: `system_workflow.md`
- Modify: `.env.example`

**Interfaces:**
- Produces: `createEmptyOrderDraft()`, `invalidatePrecheck(draft)`, `canAdvanceOrderStep(draft, step)`
- Produces: `fetchOrderEntryAccounts()`, `searchOrderEntrySymbols()`, `fetchOrderEntryHoldings()`, `fetchOrderEntryContext()`, `precheckOrderEntry()`
- Produces: `OrderEntryFlow({ onClose, onProposalCreated })`

- [ ] **Step 1: 빈 시작, 종목 선택 강제, 입력 변경 시 토큰 무효화, 자산별 용어·단위 테스트를 작성한다.**

```javascript
test('검색 문자열만 있고 선택 종목이 없으면 2단계를 통과하지 못한다', () => {
  const draft = { ...createEmptyOrderDraft(), account_id: 'a', intent: 'BUY', symbol_query: '삼성전자' }
  assert.equal(canAdvanceOrderStep(draft, 2), false)
})
```

- [ ] **Step 2: 모델·컴포넌트 부재로 테스트 실패를 확인한다.**

Run: `node --test frontend/src/features/chatbot/orderEntryModel.test.mjs frontend/src/features/chatbot/chatbotOrderForm.test.mjs frontend/src/features/chatbot/ChatbotWidget.quickActions.test.mjs`
Expected: FAIL

- [ ] **Step 3: API 클라이언트와 3단계 폼을 구현하고 기존 자유입력·조건감시·자연어 행동 진입을 제거한다.**

```jsx
{showOrderForm ? (
  <OrderEntryFlow key={orderFormRevision} onClose={() => setShowOrderForm(false)} onProposalCreated={handleProposalCreated} />
) : null}
```

- [ ] **Step 4: 상단 버튼은 항상 빈 draft를 열고 제안 생성 성공 후 폼을 닫도록 연결한다.**

```javascript
const toggleEmptyOrderForm = () => {
  setOrderFormRevision((revision) => revision + 1)
  setShowOrderForm((visible) => !visible)
}
```

- [ ] **Step 5: 구조·환경설정·흐름 문서를 실제 파일 기준으로 갱신한다.**

```text
ORDER_PRECHECK_SIGNING_SECRET=replace-with-a-long-random-secret
ORDER_PRECHECK_TOKEN_TTL_SECONDS=300
BINANCE_FUTURES_SERVICE_MAX_LEVERAGE=10
```

- [ ] **Step 6: 프론트 단위 테스트, ESLint, 프로덕션 빌드를 실행한다.**

Run: `node --test frontend/src/features/chatbot/*.test.mjs && npm --prefix frontend run lint && npm --prefix frontend run build`
Expected: PASS

### Task 5: 전체 회귀와 완료 검증

**Files:**
- Verify only

- [ ] **Step 1: 변경 파일에서 `console.log`, 자연어 폼 행동, 조건감시 UI, 구조화 기본값 보정이 없는지 검사한다.**

Run: `rg -n "console\\.log|open_order_form|조건감시|structured_order.get\\(.* or \"(TOSS|REAL|BUY|LIMIT)\"" backend/services/chatbot frontend/src/features/chatbot`
Expected: 제거 대상 참조 0건

- [ ] **Step 2: 백엔드 관련 전체 테스트를 실행한다.**

Run: `python3 -m pytest -q tests/backend backend/tests`
Expected: PASS

- [ ] **Step 3: 프론트 전체 테스트·린트·빌드를 새로 실행한다.**

Run: `node --test frontend/src/**/*.test.mjs && npm --prefix frontend run lint && npm --prefix frontend run build`
Expected: PASS

- [ ] **Step 4: `git diff --check`와 변경 통계를 확인한다.**

Run: `git diff --check && git status --short`
Expected: 공백 오류 0건, 사용자 기존 미추적 파일은 그대로 유지
