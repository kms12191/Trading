# AI 위탁운용 통합 자동선별 Implementation Plan

상태: 2026-07-22 완료. 구현·원격 마이그레이션·회귀 검증까지 반영했다.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 기존 가상자산 자동선별을 유지하면서 토스증권의 국내·미국 주식 활성 ML 신호도 종목 입력 없이 위험 한도 내 자동 운용한다.

**Architecture:** 기존 코인 CSV 자동선별 경로는 그대로 유지한다. 독립적인 주식 후보 선별 서비스가 토스용 활성 모델 예측 행을 정규화하고 시장 범위·신호 품질·기보유 종목·시장별 배분을 적용한다. 스케줄러는 토스 설정에 한해 이 서비스를 추가 호출하며 기존 주문·대사·청산·회로 차단기 경로를 그대로 사용한다. 화면은 기존 `AdminAiFundDashboard`를 확장한다.

**Tech Stack:** Python, Flask, Supabase Postgres, React, Tailwind CSS, pytest, Node test runner.

## Global Constraints

- 사용자는 가상자산 거래소, 국내·미국 시장 범위, 운용금, 위험도, 최대 보유 종목 수, 모의·실거래 모드만 설정한다.
- 종목 심볼 입력은 토스 주식 자동선별 화면에 두지 않는다.
- 실거래 주문은 기존 토스 자격증명, 주문 대사, 리스크 가드, 운용 모드 검사를 우회하지 않는다.
- 관리자 권한 검증 강화는 이번 범위에서 제외한다.

---

### Task 1: 주식 후보 선별 서비스

**Files:**
- Create: `backend/services/ai_fund_stock_selection.py`
- Create: `backend/tests/test_ai_fund_stock_selection.py`

**Interfaces:**
- Consumes: `backend.services.ml_model_service.build_active_signal_payload(asset_key, auth_header, position, min_signal_score, limit)`
- Produces: `AiFundStockSelectionService.select_candidates(config, held_symbols, auth_header=None) -> list[dict]`

- [ ] **Step 1: 실패하는 단위 테스트를 작성한다.**

```python
def test_select_candidates_uses_market_scope_and_excludes_held_symbols(monkeypatch):
    service = AiFundStockSelectionService()
    monkeypatch.setattr(service, "_load_active_predictions", lambda market, *_: [
        {"symbol": "005930", "position": "LONG", "signal_score": 91.0, "policy_blocked": False},
    ] if market == "KR" else [{"symbol": "AAPL", "position": "LONG", "signal_score": 94.0, "policy_blocked": False}])

    result = service.select_candidates(
        {"asset_scope": "ALL", "max_open_positions": 3, "min_signal_confidence": 0.75},
        held_symbols={"005930"},
    )

    assert [item["symbol"] for item in result] == ["AAPL"]
    assert result[0]["market"] == "US"
```

- [ ] **Step 2: 테스트가 실패하는지 확인한다.**

Run: `pytest backend/tests/test_ai_fund_stock_selection.py -v`
Expected: FAIL with `ModuleNotFoundError` or missing `AiFundStockSelectionService`.

- [ ] **Step 3: 최소 구현을 작성한다.**

```python
class AiFundStockSelectionService:
    def select_candidates(self, config, held_symbols, auth_header=None):
        markets = {"KR": ("kr_stock", "KR"), "US": ("us_stock", "US")}
        scope = str(config.get("asset_scope") or "ALL").upper()
        selected = []
        for market in ("KR", "US"):
            if scope not in ("ALL", market):
                continue
            for row in self._load_active_predictions(market, auth_header):
                if self._eligible(row, held_symbols, config):
                    selected.append(self._to_candidate(row, market))
        return sorted(selected, key=lambda item: item["confidence_score"], reverse=True)[: self._slot_count(config, held_symbols)]
```

`_eligible`은 LONG, 정책 미차단, 양수 점수, 최소 신뢰도, 미보유 종목을 검사하고 `_to_candidate`는 감사용 모델 버전과 신호 식별자를 채운다.

- [ ] **Step 4: 테스트가 통과하는지 확인한다.**

Run: `pytest backend/tests/test_ai_fund_stock_selection.py -v`
Expected: PASS.

## 실행 결과

- [x] 주식 후보 선별 서비스와 단위 테스트를 추가했다.
- [x] 토스만 주식 후보를 사용하도록 스케줄러를 분기하고 코인 경로 회귀를 검증했다.
- [x] 토스 자동선별 설정 검증, 후보 조회 API, 원격 스키마 마이그레이션을 적용했다.
- [x] 새 콘솔을 제거하고 기존 `AdminAiFundDashboard`에 주식 자동선별 UI를 통합했다.
- [x] 백엔드 31개 및 프론트엔드 2개 테스트와 production build를 통과했다.

### Task 2: 토스 스케줄러 연결과 설정 스키마

**Files:**
- Modify: `backend/services/admin_ai_fund_trading_scheduler.py`
- Modify: `backend/tests/test_admin_ai_fund_trading_scheduler.py`
- Create: `supabase/migrations/20260722223000_add_ai_fund_stock_selection_config.sql`

**Interfaces:**
- Consumes: `AiFundStockSelectionService.select_candidates(config, held_symbols) -> list[dict]`
- Produces: 코인원·바이낸스는 기존 코인 신호를 유지하고, 토스 설정의 신규 매수만 주식 후보를 사용한다.

- [ ] **Step 1: 실패하는 스케줄러 테스트를 작성한다.**

```python
def test_toss_cycle_uses_stock_candidates_not_crypto_signals(monkeypatch):
    monkeypatch.setattr(scheduler, "_load_active_configs", lambda: [
        {"user_id": "user-1", "exchange_type": "toss", "max_position_size": 100, "min_signal_confidence": 0.75,
         "asset_scope": "ALL", "max_open_positions": 2}
    ])
    monkeypatch.setattr(scheduler, "_read_crypto_signals", lambda *_: pytest.fail("crypto signals must not be read"))
    monkeypatch.setattr("backend.services.ai_fund_stock_selection.AiFundStockSelectionService.select_candidates", lambda *_args, **_kwargs: [
        {"symbol": "AAPL", "confidence_score": 0.91, "signal_id": "us:1"}
    ])
```

- [ ] **Step 2: 테스트가 실패하는지 확인한다.**

Run: `pytest backend/tests/test_admin_ai_fund_trading_scheduler.py::test_toss_cycle_uses_stock_candidates_not_crypto_signals -v`
Expected: FAIL because the scheduler reads crypto signals for Toss.

- [ ] **Step 3: 최소 구현과 마이그레이션을 작성한다.**

```sql
ALTER TABLE public.admin_ai_fund_configs
  ADD COLUMN IF NOT EXISTS asset_scope VARCHAR(8) NOT NULL DEFAULT 'ALL',
  ADD COLUMN IF NOT EXISTS max_open_positions INTEGER NOT NULL DEFAULT 3,
  ADD COLUMN IF NOT EXISTS kr_allocation_pct NUMERIC(5,2) NOT NULL DEFAULT 50.00,
  ADD COLUMN IF NOT EXISTS us_allocation_pct NUMERIC(5,2) NOT NULL DEFAULT 50.00,
  ADD COLUMN IF NOT EXISTS selection_refresh_minutes INTEGER NOT NULL DEFAULT 60;
```

스케줄러는 `exchange_type == "toss"`일 때 보유 종목을 수집해 후보 서비스에 전달하고, 반환 후보를 차례로 현재가·기존 리스크 검증에 넘긴다. 다른 거래소는 기존 코인 신호 경로를 유지한다.

- [ ] **Step 4: 테스트가 통과하는지 확인한다.**

Run: `pytest backend/tests/test_admin_ai_fund_trading_scheduler.py backend/tests/test_ai_fund_stock_selection.py -v`
Expected: PASS.

### Task 3: 자동선별 API와 설정 검증

**Files:**
- Modify: `backend/routes/admin_ai_fund.py`
- Modify: `backend/tests/test_admin_ai_fund_routes.py`

**Interfaces:**
- Produces: `GET /api/admin/ai-fund/stock-candidates?user_id=<uuid>` 및 토스 설정 검증.

- [ ] **Step 1: 실패하는 라우트 테스트를 작성한다.**

```python
def test_stock_candidates_returns_auto_selected_rows(client, monkeypatch):
    monkeypatch.setattr("backend.routes.admin_ai_fund.AiFundStockSelectionService.select_candidates", lambda *_args, **_kwargs: [
        {"symbol": "005930", "market": "KR", "confidence_score": 0.92}
    ])
    response = client.get("/api/admin/ai-fund/stock-candidates?user_id=user-1")
    assert response.status_code == 200
    assert response.get_json()["candidates"][0]["symbol"] == "005930"
```

- [ ] **Step 2: 테스트가 실패하는지 확인한다.**

Run: `pytest backend/tests/test_admin_ai_fund_routes.py::test_stock_candidates_returns_auto_selected_rows -v`
Expected: FAIL with 404.

- [ ] **Step 3: 최소 라우트를 구현한다.**

라우트는 토스 설정을 조회하고 `AiFundStockSelectionService`를 호출한다. 설정 저장 시 `asset_scope`, `max_open_positions`, 배분 합계, 갱신 주기를 검증하며 잘못된 입력은 400으로 응답한다.

- [ ] **Step 4: 테스트가 통과하는지 확인한다.**

Run: `pytest backend/tests/test_admin_ai_fund_routes.py -v`
Expected: PASS.

### Task 4: 종목 입력 없는 토스 자동선별 UI

**Files:**
- Modify: `frontend/src/pages/AdminAiFundDashboard.jsx`
- Modify: `frontend/src/tests/AdminAiFundDashboard.test.jsx`

**Interfaces:**
- Produces: `buildStockSelectionPayload({ userId, capital, riskPreset, scope, maxOpenPositions, krAllocation, usAllocation }) -> object | null`

- [ ] **Step 1: 실패하는 프론트엔드 모델 테스트를 작성한다.**

```javascript
assert.deepEqual(
  buildStockSelectionPayload({ userId: 'user-1', capital: 5000000, riskPreset: 'neutral', scope: 'ALL', maxOpenPositions: 3, krAllocation: 50, usAllocation: 50 }),
  { user_id: 'user-1', exchange_type: 'toss', allocated_capital: 5000000, risk_preset: 'neutral', asset_scope: 'ALL', max_open_positions: 3, kr_allocation_pct: 50, us_allocation_pct: 50 }
)
```

- [ ] **Step 2: 테스트가 실패하는지 확인한다.**

Run: `node --test frontend/src/pages/adminAiFundConsoleModel.test.mjs`
Expected: FAIL because `buildStockSelectionPayload` does not exist.

- [ ] **Step 3: 최소 UI를 구현한다.**

기존 대시보드의 토스 선택 영역에 시장 범위 세그먼트, 시장별 배분 입력, 최대 보유 종목 수 입력, AI 후보 표를 추가한다. 코인원·바이낸스 선택은 기존 가상자산 자동선별을 그대로 보여 준다. 새 `AiFundOperationsConsole`은 주 화면에서 제거하고, 저장은 `/api/admin/ai-fund/configs`를 사용하며 후보 표는 새 API를 호출한다.

- [ ] **Step 4: 프론트엔드 모델 테스트와 빌드를 확인한다.**

Run: `node --test frontend/src/pages/adminAiFundConsoleModel.test.mjs && npm --prefix frontend run build`
Expected: PASS and production build completes.

### Task 5: 문서와 최종 회귀 검증

**Files:**
- Modify: `docs/superpowers/specs/2026-07-22-ai-fund-stock-selection-design.md`
- Modify: `docs/superpowers/plans/2026-07-22-ai-fund-stock-selection-plan.md`

- [ ] **Step 1: 완료 항목과 실제 제한을 문서에 반영한다.**

토스 외부 DNS·토큰 장애가 남아 있으면 "실거래 준비 전제"로 명시하고, 구현 완료로 잘못 표현하지 않는다.

- [ ] **Step 2: 전체 관련 테스트를 실행한다.**

Run: `pytest backend/tests/test_ai_fund_stock_selection.py backend/tests/test_admin_ai_fund_trading_scheduler.py backend/tests/test_admin_ai_fund_routes.py -v && node --test frontend/src/pages/adminAiFundConsoleModel.test.mjs && npm --prefix frontend run build && git diff --check`
Expected: PASS.
