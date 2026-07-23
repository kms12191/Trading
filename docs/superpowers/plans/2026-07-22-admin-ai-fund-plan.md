# Admin AI Managed Fund & Auto-Trading Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement discretionary AI auto-trading capabilities for Project Administrators (ADMIN role), including Chatbot NLP tools, real-time 2-way UI synchronization via Supabase Realtime, and strict risk guardrails.

**Architecture:** 
1. Database Layer: Supabase `admin_ai_fund_configs` and `admin_ai_trade_logs` tables with Admin RLS policies.
2. Backend Layer: `AdminAiManagedTrader` execution engine with distributed locking (`active_locks`), risk limit verification, and direct broker order routing.
3. Chatbot Layer: Admin tools (`admin_set_ai_fund_config`, `admin_control_ai_fund`, `admin_get_ai_fund_status`, `admin_emergency_kill_switch`) in `tool_registry.py`.
4. Frontend Layer: Next.js/React 19 Admin UI (`/admin/ai-fund`) with Emergency Stop Kill-Switch and Supabase Realtime synchronization.

**Tech Stack:** React 19, Tailwind v4, Python 3.10+, Flask, Supabase PostgreSQL & Realtime, Pytest, Vite.

## Global Constraints
- Language: Descriptions in Korean, code and comments in standard English.
- Security: Access strictly restricted to `ADMIN` role (`profiles.role = 'ADMIN'`).
- Concurrency: Distributed lock (`active_locks`) required before evaluating and placing trades.
- Error Handling: Return standardized error payload format using `format_error_payload`.

---

### Task 1: Supabase Database Migration & Schema Setup

**Files:**
- Create: `supabase/migrations/20260722_admin_ai_fund_tables.sql`
- Test: `backend/tests/test_admin_ai_fund_schema.py`

**Interfaces:**
- Consumes: `profiles.role` ('ADMIN' | 'USER')
- Produces: `admin_ai_fund_configs` and `admin_ai_trade_logs` tables

- [ ] **Step 1: Write failing test for schema and RLS policies**

Create `backend/tests/test_admin_ai_fund_schema.py`:
```python
import pytest
from backend.services.supabase_client import get_supabase_client

def test_admin_ai_fund_configs_table_exists():
    client = get_supabase_client()
    res = client.table("admin_ai_fund_configs").select("*").limit(0).execute()
    assert res.data is not None

def test_admin_ai_trade_logs_table_exists():
    client = get_supabase_client()
    res = client.table("admin_ai_trade_logs").select("*").limit(0).execute()
    assert res.data is not None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest backend/tests/test_admin_ai_fund_schema.py -v`
Expected: FAIL (tables do not exist yet)

- [ ] **Step 3: Create SQL Migration File**

Create `supabase/migrations/20260722_admin_ai_fund_tables.sql`:
```sql
CREATE TABLE IF NOT EXISTS public.admin_ai_fund_configs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    exchange_type VARCHAR(32) NOT NULL,
    allocated_capital NUMERIC(18, 4) NOT NULL DEFAULT 0.0,
    max_position_size NUMERIC(18, 4) NOT NULL DEFAULT 0.0,
    risk_preset VARCHAR(16) NOT NULL DEFAULT 'neutral',
    daily_mdd_limit_pct NUMERIC(5, 2) NOT NULL DEFAULT -2.0,
    min_signal_confidence NUMERIC(4, 3) NOT NULL DEFAULT 0.750,
    is_active BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_admin_fund_user_exchange UNIQUE (user_id, exchange_type)
);

CREATE TABLE IF NOT EXISTS public.admin_ai_trade_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    exchange_type VARCHAR(32) NOT NULL,
    symbol VARCHAR(32) NOT NULL,
    side VARCHAR(8) NOT NULL,
    confidence_score NUMERIC(5, 4) NOT NULL,
    executed_price NUMERIC(18, 4) NOT NULL,
    executed_qty NUMERIC(18, 6) NOT NULL,
    total_amount NUMERIC(18, 4) NOT NULL,
    order_id VARCHAR(128),
    status VARCHAR(16) NOT NULL DEFAULT 'SUCCESS',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

ALTER TABLE public.admin_ai_fund_configs ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.admin_ai_trade_logs ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Admin access to admin_ai_fund_configs" ON public.admin_ai_fund_configs
    FOR ALL USING (
        EXISTS (
            SELECT 1 FROM public.profiles
            WHERE profiles.id = auth.uid() AND profiles.role = 'ADMIN'
        )
    );

CREATE POLICY "Admin access to admin_ai_trade_logs" ON public.admin_ai_trade_logs
    FOR ALL USING (
        EXISTS (
            SELECT 1 FROM public.profiles
            WHERE profiles.id = auth.uid() AND profiles.role = 'ADMIN'
        )
    );
```

- [ ] **Step 4: Execute SQL migration and verify tests pass**

Run: `python3 -m pytest backend/tests/test_admin_ai_fund_schema.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add supabase/migrations/20260722_admin_ai_fund_tables.sql backend/tests/test_admin_ai_fund_schema.py
git commit -m "feat: add Supabase tables and RLS for admin AI managed fund"
```

---

### Task 2: Backend Risk & Auto-Trading Engine (`AdminAiManagedTrader`)

**Files:**
- Create: `backend/services/admin_ai_managed_trader.py`
- Test: `backend/tests/test_admin_ai_managed_trader.py`

**Interfaces:**
- Consumes: `get_supabase_client()`, `acquire_distributed_lock()`, `ExchangeClient.place_order()`
- Produces: `AdminAiManagedTrader.evaluate_and_execute_signal()`, `AdminAiManagedTrader.emergency_kill_switch()`

- [ ] **Step 1: Write failing unit test for AdminAiManagedTrader**

Create `backend/tests/test_admin_ai_managed_trader.py`:
```python
from unittest.mock import MagicMock
import pytest
from backend.services.admin_ai_managed_trader import AdminAiManagedTrader, AdminAiRiskViolation

def test_evaluate_signal_skips_when_inactive():
    trader = AdminAiManagedTrader(user_id="admin-123", exchange_type="coinone")
    trader._get_fund_config = MagicMock(return_value={"is_active": False})
    
    result = trader.evaluate_and_execute_signal(
        symbol="BTC",
        signal_type="BUY",
        confidence_score=0.85,
        current_price=50000000.0,
        exchange_client=MagicMock()
    )
    assert result is None

def test_evaluate_signal_executes_when_valid():
    trader = AdminAiManagedTrader(user_id="admin-123", exchange_type="coinone")
    trader._get_fund_config = MagicMock(return_value={
        "is_active": True,
        "min_signal_confidence": 0.75,
        "max_position_size": 500000.0
    })
    trader._log_trade_execution = MagicMock()
    
    mock_exchange = MagicMock()
    mock_exchange.place_order.return_value = {"order_id": "ord-999", "status": "filled"}
    
    result = trader.evaluate_and_execute_signal(
        symbol="BTC",
        signal_type="BUY",
        confidence_score=0.85,
        current_price=50000000.0,
        exchange_client=mock_exchange
    )
    assert result == {"order_id": "ord-999", "status": "filled"}
    mock_exchange.place_order.assert_called_once()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest backend/tests/test_admin_ai_managed_trader.py -v`
Expected: FAIL (ModuleNotFoundError)

- [ ] **Step 3: Implement `AdminAiManagedTrader`**

Create `backend/services/admin_ai_managed_trader.py`:
```python
import logging
from decimal import Decimal
from typing import Any, Dict, Optional

from backend.services.lock_service import acquire_distributed_lock, release_distributed_lock
from backend.services.supabase_client import get_supabase_client

logger = logging.getLogger(__name__)


class AdminAiRiskViolation(Exception):
    pass


class AdminAiManagedTrader:
    def __init__(self, user_id: str, exchange_type: str):
        self.user_id = user_id
        self.exchange_type = exchange_type
        self.supabase = get_supabase_client()

    def evaluate_and_execute_signal(
        self,
        symbol: str,
        signal_type: str,
        confidence_score: float,
        current_price: float,
        exchange_client: Any,
    ) -> Optional[Dict[str, Any]]:
        lock_name = f"admin_ai_trade_{self.user_id}_{self.exchange_type}_{symbol}"
        acquired = acquire_distributed_lock(lock_name, ttl_seconds=15)
        if not acquired:
            logger.warning(f"[AdminAiTrader] Lock acquisition failed for {symbol}")
            return None

        try:
            config = self._get_fund_config()
            if not config or not config.get("is_active"):
                logger.info(f"[AdminAiTrader] Inactive config for user {self.user_id}")
                return None

            min_score = float(config.get("min_signal_confidence", 0.75))
            if confidence_score < min_score:
                logger.info(f"[AdminAiTrader] Confidence {confidence_score} < threshold {min_score}")
                return None

            max_pos_size = float(config.get("max_position_size", 0.0))
            if max_pos_size <= 0:
                raise AdminAiRiskViolation("Max position size is zero or invalid.")

            quantity = max_pos_size / current_price if current_price > 0 else 0
            if quantity <= 0:
                raise AdminAiRiskViolation("Calculated trade quantity is invalid.")

            order_result = exchange_client.place_order(
                symbol=symbol,
                side=signal_type.lower(),
                order_type="market",
                quantity=quantity,
                price=current_price
            )

            self._log_trade_execution(
                symbol=symbol,
                side=signal_type,
                confidence_score=confidence_score,
                executed_price=current_price,
                executed_qty=quantity,
                order_id=order_result.get("order_id") if order_result else None
            )

            return order_result
        finally:
            release_distributed_lock(lock_name)

    def emergency_kill_switch(self) -> bool:
        """Deactivates active AI fund configuration immediately."""
        res = self.supabase.table("admin_ai_fund_configs") \
            .update({"is_active": False}) \
            .eq("user_id", self.user_id) \
            .execute()
        return bool(res.data)

    def _get_fund_config(self) -> Optional[Dict[str, Any]]:
        res = self.supabase.table("admin_ai_fund_configs") \
            .select("*") \
            .eq("user_id", self.user_id) \
            .eq("exchange_type", self.exchange_type) \
            .maybe_single() \
            .execute()
        return res.data if res else None

    def _log_trade_execution(
        self,
        symbol: str,
        side: str,
        confidence_score: float,
        executed_price: float,
        executed_qty: float,
        order_id: Optional[str]
    ) -> None:
        self.supabase.table("admin_ai_trade_logs").insert({
            "user_id": self.user_id,
            "exchange_type": self.exchange_type,
            "symbol": symbol,
            "side": side,
            "confidence_score": confidence_score,
            "executed_price": executed_price,
            "executed_qty": executed_qty,
            "total_amount": executed_price * executed_qty,
            "order_id": order_id,
            "status": "SUCCESS"
        }).execute()
```

- [ ] **Step 4: Run unit tests to verify PASS**

Run: `python3 -m pytest backend/tests/test_admin_ai_managed_trader.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/services/admin_ai_managed_trader.py backend/tests/test_admin_ai_managed_trader.py
git commit -m "feat: implement AdminAiManagedTrader engine with risk limit checks"
```

---

### Task 3: Chatbot Admin Tools Registration (`tool_registry.py`)

**Files:**
- Modify: `backend/services/chatbot/tool_registry.py`
- Test: `backend/tests/test_admin_chatbot_tools.py`

**Interfaces:**
- Consumes: `AdminAiManagedTrader`
- Produces: `admin_set_ai_fund_config`, `admin_control_ai_fund`, `admin_get_ai_fund_status`, `admin_emergency_kill_switch` tool definitions

- [ ] **Step 1: Write failing test for Chatbot Admin Tools**

Create `backend/tests/test_admin_chatbot_tools.py`:
```python
import pytest
from backend.services.chatbot.tool_registry import execute_chatbot_tool

def test_admin_kill_switch_tool_execution(mocker):
    mocker.patch("backend.services.admin_ai_managed_trader.AdminAiManagedTrader.emergency_kill_switch", return_value=True)
    
    result = execute_chatbot_tool(
        tool_name="admin_emergency_kill_switch",
        arguments={},
        user_id="admin-user-id",
        user_role="ADMIN"
    )
    assert result["success"] is True
    assert "긴급 셧다운" in result["message"]

def test_admin_tool_fails_for_non_admin():
    result = execute_chatbot_tool(
        tool_name="admin_emergency_kill_switch",
        arguments={},
        user_id="normal-user-id",
        user_role="USER"
    )
    assert result["success"] is False
    assert "권한이 없습니다" in result["message"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest backend/tests/test_admin_chatbot_tools.py -v`
Expected: FAIL (tool not registered or handled)

- [ ] **Step 3: Update `tool_registry.py`**

Modify `backend/services/chatbot/tool_registry.py` to register admin AI fund tools and perform `user_role == 'ADMIN'` verification.

- [ ] **Step 4: Run tests to verify PASS**

Run: `python3 -m pytest backend/tests/test_admin_chatbot_tools.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/services/chatbot/tool_registry.py backend/tests/test_admin_chatbot_tools.py
git commit -m "feat: register Admin AI Fund chatbot tools with RBAC guards"
```

---

### Task 4: API Routes (`admin_ai_fund.py`) & App Registration

**Files:**
- Create: `backend/routes/admin_ai_fund.py`
- Modify: `backend/app.py`
- Test: `backend/tests/test_admin_ai_fund_routes.py`

**Interfaces:**
- Consumes: Flask Blueprint, `admin_users.py` authentication helper
- Produces: `/api/admin/ai-fund/configs`, `/api/admin/ai-fund/kill-switch` REST endpoints

- [ ] **Step 1: Write failing route tests**

Create `backend/tests/test_admin_ai_fund_routes.py`:
```python
import pytest
from backend.app import app

@pytest.fixture
def client():
    app.config['TESTING'] = True
    with app.test_client() as client:
        yield client

def test_get_ai_fund_configs_requires_auth(client):
    res = client.get("/api/admin/ai-fund/configs")
    assert res.status_code == 401
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest backend/tests/test_admin_ai_fund_routes.py -v`
Expected: FAIL (404 Not Found)

- [ ] **Step 3: Implement `backend/routes/admin_ai_fund.py` and register in `app.py`**

Create `backend/routes/admin_ai_fund.py` and import `admin_ai_fund_bp` in `backend/app.py`.

- [ ] **Step 4: Run route tests to verify PASS**

Run: `python3 -m pytest backend/tests/test_admin_ai_fund_routes.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/routes/admin_ai_fund.py backend/app.py backend/tests/test_admin_ai_fund_routes.py
git commit -m "feat: add REST API endpoints for Admin AI Fund management"
```

---

### Task 5: Frontend Admin Dashboard Page (`AdminAiFundDashboard.jsx`)

**Files:**
- Create: `frontend/src/pages/AdminAiFundDashboard.jsx`
- Modify: `frontend/src/App.jsx`
- Test: `frontend/src/tests/AdminAiFundDashboard.test.jsx`

**Interfaces:**
- Consumes: `/api/admin/ai-fund/*`, Supabase Realtime channel `admin_ai_fund_configs`
- Produces: Admin Dashboard UI at `/admin/ai-fund`

- [ ] **Step 1: Write failing component test**

Create `frontend/src/tests/AdminAiFundDashboard.test.jsx`:
```jsx
import { render, screen } from '@testing-library/react';
import AdminAiFundDashboard from '../pages/AdminAiFundDashboard';

test('renders Admin AI Fund Emergency Kill-Switch button', () => {
  render(<AdminAiFundDashboard />);
  const killSwitchBtn = screen.getByRole('button', { name: /Emergency Stop/i });
  expect(killSwitchBtn).toBeInTheDocument();
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npm run test` (or Vite/Jest test runner)
Expected: FAIL

- [ ] **Step 3: Implement `AdminAiFundDashboard.jsx`**

Create `frontend/src/pages/AdminAiFundDashboard.jsx` featuring Tailwind v4 styling, Realtime subscriptions, risk preset selectors, and the red Emergency Kill-Switch button.

- [ ] **Step 4: Verify component test PASS & run ESLint**

Run: `npm run lint`
Expected: 0 errors, 0 warnings

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/AdminAiFundDashboard.jsx frontend/src/App.jsx frontend/src/tests/AdminAiFundDashboard.test.jsx
git commit -m "feat: add React 19 Admin AI Fund Dashboard page with Realtime sync"
```
