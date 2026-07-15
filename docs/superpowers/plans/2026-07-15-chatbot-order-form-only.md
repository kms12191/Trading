# 챗봇 매매 요청 폼 단일 진입점 구현 계획

> **에이전트 지침:** `superpowers:subagent-driven-development` 또는 `superpowers:executing-plans`를 사용해 작업별로 구현한다. 각 단계는 체크박스로 관리한다.

**목표:** 일반 채팅의 자연어 주문으로는 주문 제안을 생성하지 않고, `매매 요청` 폼 제출만 주문 제안 생성 경로로 허용한다.

**구조:** 백엔드가 주문 도구 라우팅 전에 자연어 주문 의도를 차단한다. 인식값은 `open_order_form` 행동의 임시 입력값으로만 전달하고, 프론트엔드는 사용자가 필수 필드를 확인해 폼을 제출할 때만 `structured_order`를 전송한다.

**기술:** Flask, Python 3, React, Vite, Node.js 내장 테스트, pytest

## 전역 제약

- 설명, 계획, 주석, 사용자 문구는 한글로 작성한다.
- 커밋 메시지는 `docs:`, `test:`, `feat:`, `fix:` 접두사를 유지하고 설명은 한글로 작성한다.
- 일반 `message`는 주문 제안·조건감시 규칙·실제 주문을 생성할 수 없다.
- `structured_order.is_structured_order=true`인 폼 제출만 기존 사전검증과 제안 생성 경로로 진입한다.
- 자연어 분석값에 없는 필드를 임의 추론하지 않는다.
- 기존 `제안 -> 사전검증 -> 사용자 승인 -> 서버 재검증 -> 실행` 순서를 유지한다.

---

### 작업 1: 백엔드 자연어 주문 차단

**파일:**
- 생성: `backend/services/chatbot/order_form_policy.py`
- 수정: `backend/services/chatbot/chat_service.py`
- 테스트: `tests/backend/test_chatbot_order_form_policy.py`

**인터페이스:**
- `build_order_form_redirect(message: str) -> dict | None`
- 반환 action: `{"type": "open_order_form", "label": "매매 요청 열기", "prefill": dict}`
- 반환 source: `ORDER_FORM_REDIRECT`

- [ ] **1단계: 자연어 주문 차단 실패 테스트 작성**

```python
def test_plain_order_returns_order_form_action_without_proposal(monkeypatch):
    service = ChatbotService.__new__(ChatbotService)
    service.conversation_repository = FakeConversationRepository()
    monkeypatch.setattr(
        chat_service,
        "create_trade_proposal_from_message",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("일반 채팅에서 주문 제안 생성 금지")),
    )

    result = service.reply("코인원 XRP 10개 800원에 사줘", user_id=None, auth_header=None)

    assert result["data"]["source"] == "ORDER_FORM_REDIRECT"
    assert result["actions"][0]["type"] == "open_order_form"
    assert result["actions"][0]["prefill"]["symbol_query"] == "XRP"
    assert result["actions"][0]["prefill"]["price"] == 800.0
```

- [ ] **2단계: 테스트 실패 확인**

실행: `PYTHONPATH=. pytest tests/backend/test_chatbot_order_form_policy.py -q`

예상: `ORDER_FORM_REDIRECT` 정책이 없어 FAIL

- [ ] **3단계: 폼 전환 정책 구현**

```python
def build_order_form_redirect(message: str) -> dict | None:
    intent = parse_order_intent(message)
    if not intent.is_order_request:
        return None
    prefill = _build_prefill(message, intent)
    return {
        "reply": "주문은 매매 요청 폼에서 내용을 확인한 뒤 진행할 수 있어요.\n인식한 내용은 임시 입력값이므로 제출 전에 다시 확인해 주세요.",
        "actions": [{"type": "open_order_form", "label": "매매 요청 열기", "prefill": prefill}],
        "data": {"source": "ORDER_FORM_REDIRECT", "prefill": prefill},
    }
```

`_build_prefill()`은 명시된 거래소만 `TOSS`, `KIS`, `COINONE`, `BINANCE`로 매핑한다. 가격이 있으면 `LIMIT`, “시장가”가 명시되면 `MARKET`, 둘 다 없으면 빈 값으로 둔다.

- [ ] **4단계: `ChatbotService.reply()` 최상단에 정책 연결**

```python
order_form_redirect = build_order_form_redirect(text)
if order_form_redirect:
    self._discard_trade_pending_action(auth_header, user_id)
    return order_form_redirect
```

`structured_order` 분기는 위 정책보다 먼저 유지한다. `_discard_trade_pending_action()`은 `trade_proposal_missing_*`만 제거하고 다른 pending action은 보존한다.

- [ ] **5단계: 자연어 차단과 구조화 폼 허용 테스트 통과**

실행: `PYTHONPATH=. pytest tests/backend/test_chatbot_order_form_policy.py -q`

예상: 자연어 주문은 `ORDER_FORM_REDIRECT`, 폼 제출은 기존 제안 생성 경로로 PASS

- [ ] **6단계: 커밋**

```bash
git add backend/services/chatbot/order_form_policy.py backend/services/chatbot/chat_service.py tests/backend/test_chatbot_order_form_policy.py
git commit -m "feat: 자연어 주문을 매매 요청 폼으로 전환"
```

### 작업 2: 프론트엔드 폼 임시 입력값

**파일:**
- 생성: `frontend/src/features/chatbot/chatbotOrderForm.js`
- 생성: `frontend/src/features/chatbot/chatbotOrderForm.test.mjs`
- 수정: `frontend/src/features/chatbot/ChatbotWidget.jsx`

**인터페이스:**
- `normalizeOrderFormPrefill(prefill: object) -> object`
- `ChatOrderForm({ initialValues, onClose, onSubmit })`

- [ ] **1단계: 알 수 없는 필드를 비우는 실패 테스트 작성**

```javascript
test('unknown fields stay empty', () => {
  assert.deepEqual(normalizeOrderFormPrefill({ symbol_query: 'XRP', quantity: 10 }), {
    exchange: '', broker_env: '', side: '', symbol_query: 'XRP',
    quantity: '10', order_type: '', price: '',
  })
})
```

- [ ] **2단계: 테스트 실패 확인**

실행: `node --test frontend/src/features/chatbot/chatbotOrderForm.test.mjs`

예상: 정규화 모듈이 없어 FAIL

- [ ] **3단계: 임시 입력값 정규화 구현**

```javascript
const EXCHANGES = new Set(['TOSS', 'KIS', 'COINONE', 'BINANCE'])
const BROKER_ENVS = new Set(['REAL', 'MOCK'])
const SIDES = new Set(['BUY', 'SELL'])
const ORDER_TYPES = new Set(['LIMIT', 'MARKET'])

export function normalizeOrderFormPrefill(prefill = {}) {
  return {
    exchange: normalizeChoice(prefill.exchange, EXCHANGES),
    broker_env: normalizeChoice(prefill.broker_env, BROKER_ENVS),
    side: normalizeChoice(prefill.side, SIDES),
    symbol_query: String(prefill.symbol_query || '').trim(),
    quantity: toPositiveText(prefill.quantity),
    order_type: normalizeChoice(prefill.order_type, ORDER_TYPES),
    price: toPositiveText(prefill.price),
  }
}
```

- [ ] **4단계: `open_order_form` action을 폼과 연결**

```javascript
if (action?.type === 'open_order_form') {
  setOrderFormInitialValues(normalizeOrderFormPrefill(action.prefill))
  setShowOrderForm(true)
  return
}
```

- [ ] **5단계: 폼의 빈 필드와 명시적 검증 구현**

`exchange`, `brokerEnv`, `side`, `orderType`은 빈 선택으로 시작한다. `alert()`를 폼 내부 `formError`로 교체하고, 임시값이 있으면 제출 전 재확인 안내를 표시한다.

```javascript
if (!exchange || !brokerEnv || !side || !orderType) {
  setFormError('거래소, 환경, 매매 구분, 주문 유형을 모두 확인해 주세요.')
  return
}
```

- [ ] **6단계: 프론트엔드 테스트 통과**

실행: `node --test frontend/src/features/chatbot/chatbotOrderForm.test.mjs frontend/src/features/chatbot/ChatbotWidget.quickActions.test.mjs`

예상: 임시값 정규화와 기존 매매 요청 버튼 테스트 PASS

- [ ] **7단계: 커밋**

```bash
git add frontend/src/features/chatbot/chatbotOrderForm.js frontend/src/features/chatbot/chatbotOrderForm.test.mjs frontend/src/features/chatbot/ChatbotWidget.jsx
git commit -m "feat: 매매 요청 폼에 자연어 임시값 반영"
```

### 작업 3: 회귀 검증과 문서 동기화

**파일:**
- 수정: `TradingBot.md`
- 수정: `project_structure.md`
- 테스트: `tests/backend/test_chatbot_order_form_policy.py`

- [ ] **1단계: 주문 문장 회귀 케이스 추가**

```python
@pytest.mark.parametrize("message", [
    "삼성전자 10주 사줘",
    "XRP 전량 팔아줘",
    "1번 추천 종목 매수 제안해줘",
    "비트코인 조건매도 등록해줘",
])
def test_all_plain_order_messages_are_redirected_to_form(message):
    result = build_order_form_redirect(message)
    assert result is not None
    assert result["data"]["source"] == "ORDER_FORM_REDIRECT"
```

- [ ] **2단계: 백엔드 회귀 테스트 실행**

실행: `PYTHONPATH=. pytest tests/backend/test_chatbot_order_form_policy.py tests/backend/test_chatbot_order_parser.py tests/backend/test_chatbot_tool_registry_price.py -q`

예상: 모든 테스트 PASS

- [ ] **3단계: 정적 검증과 프론트엔드 테스트 실행**

실행:

```bash
PYTHONPATH=. python -m py_compile backend/services/chatbot/order_form_policy.py backend/services/chatbot/chat_service.py
node --test frontend/src/features/chatbot/chatbotOrderForm.test.mjs frontend/src/features/chatbot/ChatbotWidget.quickActions.test.mjs
git diff --check
```

예상: 모든 명령 exit code 0

- [ ] **4단계: 문서 동기화**

`TradingBot.md`에 일반 채팅 주문 차단과 폼 임시값 흐름을 기록한다. `project_structure.md`에 `order_form_policy.py`의 역할을 추가한다.

- [ ] **5단계: 커밋**

```bash
git add TradingBot.md project_structure.md tests/backend/test_chatbot_order_form_policy.py
git commit -m "docs: 매매 요청 폼 단일 진입 흐름 문서화"
```
