# AI 위탁운용 1차 안정화 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 거래소 공통 계약, AI 위탁 전용 주문·체결·포지션 원장, 대사·운용 모드를 구현해 장애와 재실행에도 안전한 실제 운용 기반을 만든다.

**Architecture:** 기존 `ExchangeClient`를 호환성 있게 확장하고, AI 위탁운용은 정규화된 주문 모델을 통해서만 거래소에 제출한다. 거래소 응답은 주문·체결 원장에 기록한 뒤 포지션 집계에 반영하며, 대사 작업은 거래소 주문 상태를 기준으로 미확정 주문을 복구한다.

**Tech Stack:** Python 3.13, Flask, Pytest, Supabase PostgreSQL, 기존 Coinone/Binance/Toss 클라이언트.

## Global Constraints

- 기존 `place_order`, `get_order_status`, `cancel_order` 호출부는 깨지지 않아야 한다.
- 새 공개 테이블은 RLS를 활성화하고 `TO authenticated`와 관리자 역할 조건을 함께 사용한다.
- 주문 제출은 항상 `client_order_id` 멱등 키를 먼저 기록한 뒤 진행한다.
- `FILLED`, `CANCELED`, `REJECTED`는 종료 상태이며 다시 제출하지 않는다.
- 모호한 네트워크 실패는 재주문하지 않고 `NEEDS_REVIEW`로 보낸다.
- 실제 주문은 LIVE 모드와 유효한 사용자별 API 키가 모두 있을 때만 허용한다.

---

### Task 1: 공통 거래소 주문 모델과 Capability (완료)

**Files:**
- Create: `backend/services/ai_fund_exchange.py`
- Modify: `backend/services/exchange_client.py`
- Test: `backend/tests/test_ai_fund_exchange.py`

**Interfaces:**
- Produces: `ExchangeCapability`, `OrderRequest`, `ExchangeOrder`, `normalize_exchange_order()`.
- Consumes: 기존 거래소 클라이언트의 주문 응답 딕셔너리.

- [ ] **Step 1: 실패 테스트 작성**

```python
def test_normalize_exchange_order_preserves_client_order_id_and_partial_fill():
    order = normalize_exchange_order(
        exchange_type="coinone",
        payload={"order_id": "co-1", "status": "PARTIALLY_FILLED", "executed_qty": 0.2, "price": 100.0},
        request=OrderRequest(symbol="BTC", side="BUY", quantity=1.0, client_order_id="fund-1"),
    )
    assert order.client_order_id == "fund-1"
    assert order.status == "PARTIALLY_FILLED"
    assert order.filled_qty == 0.2
```

- [ ] **Step 2: 실패 확인**

Run: `python3 -m pytest backend/tests/test_ai_fund_exchange.py -q`
Expected: import error because the normalized model does not exist.

- [ ] **Step 3: 최소 구현**

```python
@dataclass(frozen=True)
class OrderRequest:
    symbol: str
    side: str
    quantity: float
    client_order_id: str
    order_type: str = "LIMIT"
    price: float | None = None

@dataclass(frozen=True)
class ExchangeOrder:
    exchange_order_id: str | None
    client_order_id: str
    symbol: str
    side: str
    requested_qty: float
    filled_qty: float
    average_fill_price: float | None
    status: str
    fee: float
    raw: dict
```

`ExchangeCapability`은 현물·주문조회·취소·시장가 주문 지원 여부와 최소 주문 금액을 갖고, `ExchangeClient`에 `get_capabilities()` 기본 메서드를 추가한다.

- [ ] **Step 4: 통과 확인**

Run: `python3 -m pytest backend/tests/test_ai_fund_exchange.py -q`
Expected: PASS.

### Task 2: 주문·체결·포지션 원장 스키마와 서비스 (코드 완료, DB 적용 대기)

**Files:**
- Create: `supabase/migrations/<generated>_add_ai_fund_execution_ledger.sql`
- Create: `backend/services/ai_fund_ledger.py`
- Test: `backend/tests/test_ai_fund_ledger.py`

**Interfaces:**
- Produces: `AiFundLedger.create_pending_order()`, `record_exchange_order()`, `apply_fill()`, `get_sellable_quantity()`.
- Consumes: `ExchangeOrder`.

- [ ] **Step 1: 실패 테스트 작성**

```python
def test_apply_fill_updates_position_and_sellable_quantity():
    ledger = AiFundLedger("user-1", "coinone")
    ledger.apply_fill(order_id="order-1", symbol="BTC", side="BUY", quantity=0.4, price=100.0, fee=1.0)
    assert ledger.get_sellable_quantity("BTC") == 0.4
```

- [ ] **Step 2: 실패 확인**

Run: `python3 -m pytest backend/tests/test_ai_fund_ledger.py -q`
Expected: import error because `AiFundLedger` does not exist.

- [ ] **Step 3: 스키마·서비스 구현**

`ai_fund_orders`, `ai_fund_fills`, `ai_fund_positions`, `ai_fund_reconciliation_runs`를 생성한다. `ai_fund_orders.client_order_id`와 `(exchange_type, exchange_fill_id)`에 유일 제약을 둔다. `ai_fund_ledger.py`는 Supabase REST 경로를 통해 주문 상태와 체결을 멱등적으로 기록하고 포지션 수량·평균단가·실현손익을 갱신한다.

- [ ] **Step 4: 통과 확인**

Run: `python3 -m pytest backend/tests/test_ai_fund_ledger.py -q`
Expected: PASS.

### Task 3: AI 위탁 주문 상태 머신과 운용 모드 (코드 및 원격 설정 컬럼 배포 완료)

**Files:**
- Modify: `backend/services/admin_ai_managed_trader.py`
- Modify: `backend/services/admin_ai_fund_trading_scheduler.py`
- Test: `backend/tests/test_admin_ai_managed_trader.py`
- Test: `backend/tests/test_admin_ai_fund_trading_scheduler.py`

**Interfaces:**
- Consumes: `AiFundLedger`, `OrderRequest`, `ExchangeOrder`, config `operation_mode`.
- Produces: `PENDING_SUBMIT`부터 `NEEDS_REVIEW`까지의 상태 전이와 PAPER/CANARY/LIVE 실행 규칙.

- [ ] **Step 1: 실패 테스트 작성**

```python
def test_live_timeout_marks_order_needs_review_without_second_submit():
    trader = AdminAiManagedTrader("user-1", "coinone")
    client = MagicMock(place_order=MagicMock(side_effect=TimeoutError("timeout")))
    result = trader.evaluate_and_execute_signal("BTC", "BUY", 0.9, 100.0, client)
    assert result["status"] == "NEEDS_REVIEW"
    assert client.place_order.call_count == 1
```

- [ ] **Step 2: 실패 확인**

Run: `python3 -m pytest backend/tests/test_admin_ai_managed_trader.py -q`
Expected: FAIL because the existing implementation writes a success log after any order call.

- [ ] **Step 3: 상태 전이 구현**

주문 실행 전 `PENDING_SUBMIT`을 저장하고, PAPER는 모의 체결만 기록한다. CANARY는 `canary_max_order_amount` 이하로 주문 금액을 제한한다. LIVE에서 제출 예외가 발생하면 재시도 없이 `NEEDS_REVIEW`로 기록한다. 거래소가 체결 수량을 응답하면 그 수량만 원장에 반영한다.

- [ ] **Step 4: 통과 확인**

Run: `python3 -m pytest backend/tests/test_admin_ai_managed_trader.py backend/tests/test_admin_ai_fund_trading_scheduler.py -q`
Expected: PASS.

### Task 4: 대사·재시작 복구와 스펙 반영 (코드 완료, DB 적용 대기)

**Files:**
- Create: `backend/services/ai_fund_reconciliation.py`
- Modify: `backend/services/admin_ai_fund_trading_scheduler.py`
- Modify: `docs/superpowers/specs/2026-07-22-ai-fund-stability-v1-design.md`
- Test: `backend/tests/test_ai_fund_reconciliation.py`

**Interfaces:**
- Produces: `AiFundReconciliationService.reconcile_config(config, client)`.
- Consumes: 열린 내부 주문, `ExchangeClient.get_order_status()`, `AiFundLedger`.

- [ ] **Step 1: 실패 테스트 작성**

```python
def test_reconcile_marks_missing_exchange_order_as_needs_review():
    service = AiFundReconciliationService(ledger)
    client = MagicMock(get_order_status=MagicMock(return_value=None))
    result = service.reconcile_config(config, client)
    assert result.needs_review_count == 1
```

- [ ] **Step 2: 실패 확인**

Run: `python3 -m pytest backend/tests/test_ai_fund_reconciliation.py -q`
Expected: import error because the reconciliation service does not exist.

- [ ] **Step 3: 구현과 문서 갱신**

스케줄러는 신규 신호 전 모든 활성 설정의 미종료 주문을 대사한다. 조회 불가·응답 유실 주문은 `NEEDS_REVIEW`, 부분 체결은 체결분 반영 후 `PARTIALLY_FILLED`, 종료 주문은 종료 상태로 기록한다. 1차 스펙에는 각 항목의 구현 상태와 검증 결과를 갱신한다.

- [ ] **Step 4: 전체 검증**

Run: `python3 -m pytest backend/tests/test_ai_fund_exchange.py backend/tests/test_ai_fund_ledger.py backend/tests/test_admin_ai_managed_trader.py backend/tests/test_admin_ai_fund_trading_scheduler.py backend/tests/test_ai_fund_reconciliation.py -q`
Expected: PASS.

Run: `git diff --check`
Expected: no output.
