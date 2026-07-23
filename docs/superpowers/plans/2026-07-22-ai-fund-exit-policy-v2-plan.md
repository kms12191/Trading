# AI 위탁운용 종료 정책 2차 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 원장 기반으로 부분 익절, 본전 손절, 트레일링 손절을 재시작 이후에도 일관되게 실행한다.

**Architecture:** 포지션별 종료 정책은 `ai_fund_positions.exit_policy` JSONB에 저장한다. 순수 정책 모듈은 포지션, 현재가, 정책 상태를 입력받아 하나의 종료 결정을 반환하고, `AdminAiManagedTrader`는 결정된 수량만 원장 주문 경로로 제출한다. 부분 체결 뒤 정책 상태는 원장 포지션에 갱신되어 재시작에도 유지된다.

**Tech Stack:** Python 3.13, Flask, Supabase PostgreSQL, pytest.

## Global Constraints

- 전략은 거래소 주문을 직접 제출하지 않고 기존 `AdminAiManagedTrader.evaluate_and_execute_signal` 경로를 사용한다.
- 매도 수량은 원장 포지션 수량 및 미체결 매도 예약 수량을 초과할 수 없다.
- PAPER/CANARY/LIVE 모드와 기존 일간 손실 제한을 우회하지 않는다.
- 모든 새 행동은 pytest 실패 테스트를 먼저 추가해 검증한다.

---

### Task 1: 종료 정책 스키마와 정책 상태 저장 (완료)

**Files:**
- Create: `supabase/migrations/20260722190000_add_ai_fund_position_exit_policy.sql`
- Modify: `backend/services/ai_fund_ledger.py`
- Test: `backend/tests/test_ai_fund_ledger.py`

**Interfaces:**
- Produces: `AiFundLedger.get_position(symbol) -> dict | None`, `AiFundLedger.update_exit_policy(symbol, policy) -> None`.
- Stores: `ai_fund_positions.exit_policy JSONB NOT NULL DEFAULT '{}'::jsonb`.

- [ ] **Step 1: Write failing tests**

```python
def test_update_exit_policy_patches_only_matching_position():
    ledger = AiFundLedger("user-1", "coinone")
    ledger._query = MagicMock(return_value=[])

    ledger.update_exit_policy("BTC", {"highest_price": 110.0})

    assert ledger._query.call_args.args == ("ai_fund_positions?user_id=eq.user-1&exchange_type=eq.coinone&symbol=eq.BTC",)
    assert ledger._query.call_args.kwargs["method"] == "PATCH"
```

- [ ] **Step 2: Verify red**

Run: `python3 -m pytest backend/tests/test_ai_fund_ledger.py -q`

Expected: FAIL because `update_exit_policy` does not exist.

- [ ] **Step 3: Add migration and minimal ledger methods**

```sql
ALTER TABLE public.ai_fund_positions
    ADD COLUMN IF NOT EXISTS exit_policy JSONB NOT NULL DEFAULT '{}'::jsonb;
```

`get_position` must query the unique `(user_id, exchange_type, symbol)` row. `update_exit_policy` must PATCH only `exit_policy` and `updated_at` for that row.

- [ ] **Step 4: Verify green**

Run: `python3 -m pytest backend/tests/test_ai_fund_ledger.py -q`

Expected: PASS.

### Task 2: 순수 종료 정책 결정 엔진 (완료)

**Files:**
- Create: `backend/services/ai_fund_exit_policy.py`
- Test: `backend/tests/test_ai_fund_exit_policy.py`

**Interfaces:**
- Consumes: entry price, current quantity, current price, persisted `exit_policy` JSON object.
- Produces: `ExitDecision(reason: str, quantity: float, next_policy: dict) | None`.

- [ ] **Step 1: Write failing tests**

```python
def test_first_target_sells_configured_ratio_and_arms_break_even():
    decision = evaluate_exit_policy(
        entry_price=100.0,
        quantity=10.0,
        current_price=105.0,
        policy={"take_profit_steps": [{"target_pct": 5, "sell_ratio": 0.5}]},
    )
    assert decision.reason == "TAKE_PROFIT_1"
    assert decision.quantity == 5.0
    assert decision.next_policy["break_even_armed"] is True
```

Add separate cases for stop loss priority, armed break-even, trailing activation and trailing stop, and no repeated partial take-profit after its step is recorded.

- [ ] **Step 2: Verify red**

Run: `python3 -m pytest backend/tests/test_ai_fund_exit_policy.py -q`

Expected: FAIL because the module does not exist.

- [ ] **Step 3: Implement deterministic policy evaluation**

`evaluate_exit_policy` must normalize at most three ordered take-profit steps, cap aggregate sell ratios at one, record completed step indices, update the highest price after trailing activation, and evaluate in this order: stop loss, trailing stop, break-even stop, partial take profit.

- [ ] **Step 4: Verify green**

Run: `python3 -m pytest backend/tests/test_ai_fund_exit_policy.py -q`

Expected: PASS.

### Task 3: 거래 실행 및 스케줄러 연결 (완료)

**Files:**
- Modify: `backend/services/admin_ai_managed_trader.py`
- Modify: `backend/services/admin_ai_fund_trading_scheduler.py`
- Modify: `backend/tests/test_admin_ai_managed_trader.py`
- Modify: `backend/tests/test_admin_ai_fund_trading_scheduler.py`

**Interfaces:**
- Consumes: `ExitDecision` and `AiFundLedger.get_sellable_quantity(symbol)`.
- Produces: SELL order with decision quantity and policy state update only after an order is accepted for execution.

- [ ] **Step 1: Write failing tests**

```python
def test_exit_signal_uses_partial_take_profit_quantity_and_persists_policy(monkeypatch):
    trader = AdminAiManagedTrader("user-1", "coinone")
    # Configure a 50% first target, return a 10-unit ledger position at price 100.
    signal = trader.evaluate_exit_signal("BTC", current_price=105.0)
    assert signal["quantity"] == 5.0
    assert signal["reason"] == "TAKE_PROFIT_1"
```

Add a scheduler assertion that it passes `exit_signal["quantity"]` into the execution path rather than recomputing a full-position SELL.

- [ ] **Step 2: Verify red**

Run: `python3 -m pytest backend/tests/test_admin_ai_managed_trader.py backend/tests/test_admin_ai_fund_trading_scheduler.py -q`

Expected: FAIL because exit decisions are currently full-position only.

- [ ] **Step 3: Implement minimal integration**

Extend `evaluate_and_execute_signal` with an optional `requested_quantity` for SELL only, constrain it by `AiFundLedger.get_sellable_quantity`, and persist `ExitDecision.next_policy` after the order reaches PAPER fill or exchange submission. The scheduler must forward the decision quantity and a stable exit signal id.

- [ ] **Step 4: Verify green**

Run: `python3 -m pytest backend/tests/test_ai_fund_exit_policy.py backend/tests/test_ai_fund_ledger.py backend/tests/test_admin_ai_managed_trader.py backend/tests/test_admin_ai_fund_trading_scheduler.py -q`

Expected: PASS.

### Task 4: DB 배포와 문서 갱신 (완료)

**Files:**
- Modify: `docs/superpowers/specs/2026-07-22-ai-fund-commercial-final-design.md`
- Modify: `docs/superpowers/plans/2026-07-22-ai-fund-exit-policy-v2-plan.md`

- [ ] **Step 1: Run migration dry-run**

Run: `supabase db push --linked --dry-run --yes`

Expected: only `20260722190000_add_ai_fund_position_exit_policy.sql` is pending.

- [ ] **Step 2: Apply and inspect remote schema**

Run: `supabase db push --linked --yes`

Expected: migration applies and `ai_fund_positions.exit_policy` exists.

- [ ] **Step 3: Record verified status**

Update the final spec with tested exit-policy behaviors, DB version, and any remaining 3차 prerequisites.

### Task 5: 전략별 예산 귀속 및 차단 (완료)

`20260722193000_add_ai_fund_strategy_budgets.sql`로 `strategy_budgets`와 전략 귀속 컬럼을 적용했다. `AiFundLedger.get_strategy_exposure()`은 전략별 포지션과 미체결 매수를 합산하고, 신규 BUY는 설정된 예산을 초과하면 `AdminAiRiskViolation`으로 차단한다.
