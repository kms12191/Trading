# Admin AI Managed Fund & Auto-Trading Design Document

- **Date**: 2026-07-22
- **Author**: Lead AI Engineer
- **Status**: Approved
- **Scope**: Admin-only AI discretionary fund management, chatbot natural language control, real-time UI synchronization, and risk guardrails.

---

## 1. Executive Summary

This document specifies the architecture and technical design for the **Admin AI Managed Fund (관리자 전용 AI 위탁 자동투자)** feature in the AI Trading System. 

While the system enforces a strict **Human-in-the-Loop (HITL)** principle for general users (requiring manual approval for trade proposals), this feature grants **Project Administrators (ADMIN role)** the capability to allocate dedicated capital to AI models for discretionary auto-trading (**Human-on-the-Loop** model with automated execution and instant emergency kill-switches).

---

## 2. Key Requirements & Capabilities

1. **Role-Based Isolation (Strict Admin Only)**:
   - Protected by Supabase Row-Level Security (RLS) (`profiles.role = 'ADMIN'`) and Flask API gateway middleware.
   - General users cannot view, access, or configure AI fund parameters.

2. **2-Way Real-time Synchronization (Chatbot & Web Dashboard UI)**:
   - Any natural language command issued in the Chatbot (e.g., "AI 위탁 자금 500만원 코인원에 할당하고 운용 시작해줘") updates the database and triggers Supabase Realtime events.
   - The Web Dashboard UI (`/admin/ai-fund`) reflects status changes in < 1 second.
   - Toggling controls or pressing the Emergency Kill-Switch on the UI updates the Chatbot context simultaneously.

3. **Risk Guardrails & Presets**:
   - 3 Risk Presets: **Conservative (보수)**, **Neutral (중립)**, **Aggressive (공격)**, plus **Custom**.
   - Parameters: Minimum Signal Confidence Score, Daily MDD Loss Limit (%), Max Position Size (%).

4. **Emergency Stop (Kill-Switch)**:
   - Dedicated tool `admin_emergency_kill_switch` in Chatbot and prominent UI red button.
   - Deactivates all active AI fund workers, releases locks, and cancels open orders within 1 second.

---

## 3. Database Schema Design (Supabase PostgreSQL)

### 3.1 `admin_ai_fund_configs` Table

```sql
CREATE TABLE IF NOT EXISTS public.admin_ai_fund_configs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    exchange_type VARCHAR(32) NOT NULL, -- 'toss', 'coinone', 'binance'
    allocated_capital NUMERIC(18, 4) NOT NULL DEFAULT 0.0,
    max_position_size NUMERIC(18, 4) NOT NULL DEFAULT 0.0,
    risk_preset VARCHAR(16) NOT NULL DEFAULT 'neutral', -- 'conservative', 'neutral', 'aggressive', 'custom'
    daily_mdd_limit_pct NUMERIC(5, 2) NOT NULL DEFAULT -2.0,
    min_signal_confidence NUMERIC(4, 3) NOT NULL DEFAULT 0.750,
    is_active BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_admin_fund_user_exchange UNIQUE (user_id, exchange_type)
);

-- RLS Policy
ALTER TABLE public.admin_ai_fund_configs ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Admin full access to ai fund configs" ON public.admin_ai_fund_configs
    FOR ALL USING (
        EXISTS (
            SELECT 1 FROM public.profiles
            WHERE profiles.id = auth.uid() AND profiles.role = 'ADMIN'
        )
    );
```

### 3.2 `admin_ai_trade_logs` Table

```sql
CREATE TABLE IF NOT EXISTS public.admin_ai_trade_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    exchange_type VARCHAR(32) NOT NULL,
    symbol VARCHAR(32) NOT NULL,
    side VARCHAR(8) NOT NULL, -- 'BUY', 'SELL'
    confidence_score NUMERIC(5, 4) NOT NULL,
    executed_price NUMERIC(18, 4) NOT NULL,
    executed_qty NUMERIC(18, 6) NOT NULL,
    total_amount NUMERIC(18, 4) NOT NULL,
    order_id VARCHAR(128),
    status VARCHAR(16) NOT NULL DEFAULT 'SUCCESS',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- RLS Policy
ALTER TABLE public.admin_ai_trade_logs ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Admin view access to trade logs" ON public.admin_ai_trade_logs
    FOR SELECT USING (
        EXISTS (
            SELECT 1 FROM public.profiles
            WHERE profiles.id = auth.uid() AND profiles.role = 'ADMIN'
        )
    );
```

---

## 4. Backend Engine & Chatbot Tool Architecture

### 4.1 Chatbot Tool Registry Extensions (`backend/services/chatbot/tool_registry.py`)

1. `admin_set_ai_fund_config`: Sets allocation, risk preset, and custom parameters.
2. `admin_control_ai_fund`: Toggles active status (`start` / `pause`) per exchange.
3. `admin_get_ai_fund_status`: Queries current capital, PnL, open positions, and active status.
4. `admin_emergency_kill_switch`: Immediately stops all AI trading and revokes worker locks.

### 4.2 Automated Trader Engine (`backend/services/admin_ai_managed_trader.py`)

- Integrated into `backend/worker.py` background process loop.
- Monitors ML model predictions from `ml_scheduler.py`.
- Evaluates signals against `min_signal_confidence` and `daily_mdd_limit_pct`.
- Acquires distributed lock (`lock_service.py`) per trade cycle.
- Executes direct market order using normalized `ExchangeClient` adapters.

---

## 5. Frontend & UI Component Design

### 5.1 Admin AI Fund Dashboard Page (`/admin/ai-fund`)
- Integrated in React 19 + Tailwind v4 frontend.
- Consists of:
  - **Fund Control Cards**: Real-time toggle switches, capital input, preset selector.
  - **Emergency Red Banner**: Prominent Kill-Switch button linked to `admin_emergency_kill_switch`.
  - **AI Trade Feed**: Live timeline displaying AI trades, signal confidence, and RAG context summaries.

---

## 6. Risk Guardrails Matrix

| Preset | Min Signal Confidence | Daily MDD Cutoff | Max Order Size % |
| :--- | :--- | :--- | :--- |
| **Conservative (보수)** | 0.850 (85%) | -1.0% | 5% of Fund Capital |
| **Neutral (중립)** | 0.750 (75%) | -2.0% | 10% of Fund Capital |
| **Aggressive (공격)** | 0.650 (65%) | -4.0% | 20% of Fund Capital |
| **Custom** | Configurable | Configurable | Configurable |

---

## 7. Verification & Testing Plan

1. **Unit & Integration Tests**:
   - `backend/tests/test_admin_ai_managed_trader.py`: Verify risk limit violations, confidence score filtering, and distributed lock acquisition.
   - `backend/tests/test_admin_chatbot_tools.py`: Test tool execution with admin role vs rejection with non-admin role.
2. **Lint & Type Validation**:
   - Run `python3 -m pytest -q` for backend tests.
   - Run `npm run lint` for frontend React code.
