# 조건감시 진입가(평균단가) 보정 및 수동 등록 고도화 구현 계획서

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 조건감시 수동 등록 시 보유 평단가를 기본 진입가로 세팅하고, 주문 시 등록된 자동감시 규칙은 백그라운드 동기화 워커가 주문 체결(EXECUTED)을 확인하는 순간 실제 평균체결단가로 보정합니다.

**Architecture:** DB 마이그레이션을 통해 `auto_trading_rules`에 `entry_order_proposal_id` 컬럼을 생성하고, 수동 주문 성공 후 감시 규칙 등록 시 이 ID를 채워 넣습니다. 백그라운드 워커인 `OpenOrderStatusSyncService`는 주문 상태가 체결 완료(`EXECUTED`)로 전환될 때, 거래소별 API 응답 raw 데이터에서 평균체결가(average filled price)를 안전하게 추출하여 감시 규칙의 `entry_price`를 자동 보정합니다.

**Tech Stack:** Python, Flask, Supabase (PostgreSQL), React (Vite, Javascript)

## Global Constraints
- 모든 설명과 코멘트는 영문 표준으로 하되, 설명은 한국어로만 소통합니다.
- 라이브러리 및 언어 문법은 Next 16, React 19, Tailwind v4, Python 3.10+ 표준에 맞춥니다.
- 미사용 임포트나 데드 코드는 엄격히 삭제합니다.

---

### Task 1: Supabase DB 스키마 수정

**Files:**
- Create: `supabase/migrations/20260709113000_add_entry_order_proposal_id_to_rules.sql`

**Interfaces:**
- Consumes: None
- Produces: `auto_trading_rules` 테이블 내 `entry_order_proposal_id` 컬럼

- [ ] **Step 1: 마이그레이션 파일 작성**
  아래 쿼리를 포함하는 `supabase/migrations/20260709113000_add_entry_order_proposal_id_to_rules.sql` 파일을 신설합니다.
  ```sql
  ALTER TABLE public.auto_trading_rules 
  ADD COLUMN IF NOT EXISTS entry_order_proposal_id UUID REFERENCES public.trade_proposals(id) ON DELETE SET NULL;

  CREATE INDEX IF NOT EXISTS idx_auto_trading_rules_entry_proposal
  ON public.auto_trading_rules (entry_order_proposal_id)
  WHERE entry_order_proposal_id IS NOT NULL;
  ```
- [ ] **Step 2: 마이그레이션 파일 적용 검증**
  (Supabase 콘솔 또는 local cli가 있을 경우 쿼리 실행을 통해 성공 확인)
- [ ] **Step 3: Commit**
  ```bash
  git add supabase/migrations/20260709113000_add_entry_order_proposal_id_to_rules.sql
  git commit -m "db: add entry_order_proposal_id to auto_trading_rules"
  ```

---

### Task 2: Backend 공통 잔고 헬퍼 및 단독 조건감시 API 개선

**Files:**
- Modify: `backend/routes/trade.py`

**Interfaces:**
- Consumes: `ExchangeClient.get_balance()`
- Produces: `_get_holding_info_from_balance(client, symbol: str) -> dict | None`, 보정된 `create_auto_trading_rule()` API

- [ ] **Step 1: `_get_holding_info_from_balance` 구현**
  `backend/routes/trade.py`에 수량과 평단가를 모두 반환하는 헬퍼 함수를 작성합니다.
  ```python
  def _get_holding_info_from_balance(client, symbol: str) -> dict | None:
      """
      잔고 API에서 특정 종목의 현재 보유 수량과 평균단가를 조회합니다.
      """
      try:
          balance = client.get_balance() or {}
      except Exception:
          return None

      target_symbol = str(symbol or "").strip().upper()
      for item in balance.get("holdings", []) or []:
          holding_symbol = str(item.get("symbol") or "").strip().upper()
          if holding_symbol == target_symbol:
              return {
                  "qty": float(item.get("qty") or 0.0),
                  "avg_price": float(item.get("avg_price") or 0.0)
              }
      return {"qty": 0.0, "avg_price": 0.0}
  ```
- [ ] **Step 2: `create_auto_trading_rule` API 내부 교체 및 진입가 가드 추가**
  `create_auto_trading_rule()` 함수 내에서 `_get_holding_qty_from_balance`를 `_get_holding_info_from_balance` 호출로 교체하고, `entry_price` 보정 가드를 작성합니다.
  ```python
      # 기존: qty = _get_holding_qty_from_balance(client, symbol)
      # 변경:
      holding = _get_holding_info_from_balance(client, symbol)
      if not holding or holding["qty"] <= 0:
          return jsonify({
              "success": False,
              "message": f"현재 {exchange} ({broker_env}) 계좌에 {symbol} 자산의 보유 수량이 없거나 조회할 수 없습니다."
          }), 400
      
      # 사용자가 진입가를 입력하지 않았거나(0) 보유 평단가가 유효하다면 평단가를 우선 적용
      final_entry_price = entry_price
      if entry_price <= 0 or holding["avg_price"] > 0:
          final_entry_price = holding["avg_price"]
          
      # rule_data의 entry_price 대입 시 final_entry_price 사용
      # investment_amount 역시 final_entry_price * quantity 로 변경
  ```
- [ ] **Step 3: 테스트 및 Commit**
  ```bash
  git add backend/routes/trade.py
  git commit -m "feat: add balance holding info helper and fallback to avg_price in manual rule creation"
  ```

---

### Task 3: Backend 주문 API 개선 (진입 주문 proposal ID 기록)

**Files:**
- Modify: `backend/routes/trade.py`

**Interfaces:**
- Consumes: `trade_proposals` 테이블의 INSERT 결과 `id`
- Produces: `auto_exit` 감시 조건 등록 시 `entry_order_proposal_id` 필드 바인딩

- [ ] **Step 1: `place_manual_order()` 수정**
  - `place_manual_order()` 내부에서 `order_res` 체결 처리 완료 후 `auto_exit = True`인 감시 등록 구문 실행 전에 `trade_proposals` 테이블에 기록을 완료하여 proposal ID를 확보합니다. (현재는 감시 규칙 등록 후에 주문 이력을 `trade_proposals`에 적재하므로, 순서를 바꾸거나 proposal ID를 선발행해야 합니다.)
  - 순서 변경: `trade_proposals`에 먼저 데이터를 적재(status = `order_status_for_db`)하여 proposal 레코드를 생성하고 생성된 `id`를 획득한 후, 감시 조건 등록 시 `entry_order_proposal_id`를 입력하여 저장합니다.
- [ ] **Step 2: `rule_data` 구성에 `entry_order_proposal_id` 추가**
  ```python
  rule_data = {
      # ... 기존 속성들 ...
      "entry_order_proposal_id": proposal_id, # 새로 확보한 proposal.id
      "status": "RUNNING"
  }
  ```
- [ ] **Step 3: 테스트 및 Commit**
  ```bash
  git add backend/routes/trade.py
  git commit -m "feat: link auto-exit rules to their entry trade proposal"
  ```

---

### Task 4: 백그라운드 주문 상태 동기화 및 평단가 자동 보정 워커 구현

**Files:**
- Modify: `backend/services/open_order_status_sync_service.py`

**Interfaces:**
- Consumes: `trade_proposals` (status = `EXECUTED`), `ExchangeClient.get_order_status()`
- Produces: `auto_trading_rules` (entry_price 및 investment_amount 자동 업데이트)

- [ ] **Step 1: `SUPPORTED_SYNC_EXCHANGES` 및 `_build_client`에 TOSS 추가**
  `open_order_status_sync_service.py`의 상단 `SUPPORTED_SYNC_EXCHANGES` 튜플에 `"TOSS"`를 추가하고, `_build_client()`에 TossClient 인스턴스를 빌드하는 로직을 삽입합니다.
  ```python
  if exchange == "TOSS":
      return TossClient(
          client_id=self.crypto.decrypt(record.get("encrypted_access_key")),
          client_secret=self.crypto.decrypt(record.get("encrypted_secret_key")),
          account_seq=record.get("toss_account_seq"),
          env=broker_env,
          user_id=user_id,
      )
  ```
- [ ] **Step 2: 체결 완료 시 감시 진입가 업데이트 로직 구현**
  `_patch_proposal` 함수에서 `next_status == "EXECUTED"`가 감지되었을 때, `auto_trading_rules`를 자동 보정해 주는 함수 `_update_associated_auto_trading_rule`을 호출합니다.
  ```python
      def _update_associated_auto_trading_rule(self, proposal: dict, current_order: dict):
          proposal_id = proposal.get("id")
          exchange = str(proposal.get("exchange") or "").upper()
          
          # 1. entry_order_proposal_id가 proposal_id인 활성 감시 규칙 조회
          rules = query_supabase_as_service_role(
              "auto_trading_rules",
              "GET",
              params={
                  "entry_order_proposal_id": f"eq.{proposal_id}",
                  "status": "eq.RUNNING"
              }
          ) or []
          if not rules:
              return

          # 2. 거래소별 평균체결단가 추출
          avg_price = 0.0
          if exchange == "TOSS":
              raw_result = current_order.get("raw", {}).get("result", {})
              execution = raw_result.get("execution") or {}
              avg_price = _as_float(
                  raw_result.get("averageFilledPrice")
                  or execution.get("averageFilledPrice")
              )
          elif exchange == "KIS":
              # KIS matched 이력의 avg_price 취함
              raw_matched = current_order.get("raw", [])
              if isinstance(raw_matched, list) and len(raw_matched) > 0:
                  avg_price = _as_float(raw_matched[0].get("avg_price"))
          elif exchange == "COINONE":
              raw_data = current_order.get("raw", {})
              avg_price = _as_float(raw_data.get("average_price"))
          elif exchange in ("BINANCE", "BINANCE_UM_FUTURES"):
              raw_data = current_order.get("raw", {})
              avg_price = _as_float(raw_data.get("price") or raw_data.get("avgPrice"))
              
          if avg_price <= 0.0:
              avg_price = _as_float(proposal.get("price")) # Fallback to order price

          if avg_price <= 0.0:
              return

          # 3. DB 업데이트
          for rule in rules:
              rule_id = rule["id"]
              qty = _as_float(rule.get("quantity")) or _as_float(proposal.get("volume"))
              patch_data = {
                  "entry_price": avg_price,
                  "investment_amount": avg_price * qty,
                  "updated_at": _utc_now_iso()
              }
              query_supabase_as_service_role(
                  f"auto_trading_rules?id=eq.{rule_id}",
                  "PATCH",
                  json_data=patch_data
              )
  ```
- [ ] **Step 3: 테스트 및 Commit**
  ```bash
  git add backend/services/open_order_status_sync_service.py
  git commit -m "feat: automatic correction of entry price upon order execution"
  ```

---

### Task 5: Frontend 수동 감시 등록 폼의 기본값 보정

**Files:**
- Modify: `frontend/src/pages/AssetDetail.jsx`

**Interfaces:**
- Consumes: `myHolding.avg_price`
- Produces: 보정된 등록 폼 기본 인풋값

- [ ] **Step 1: `AssetDetail.jsx` 내 가격 세팅 부분 수정**
  사용자가 새로운 감시를 등록하고자 폼을 열었을 때, `myHolding` 정보에 평균 매수가(`avg_price`)가 존재할 경우 이를 기본 인풋값으로 적용합니다.
  ```javascript
  // 기존: setAddRulePrice(String(currentPrice || ''))
  // 변경:
  setAddRulePrice(myHolding && myHolding.avg_price ? String(myHolding.avg_price) : String(currentPrice || ''))
  ```
- [ ] **Step 2: 브라우저 렌더링 검증 및 Commit**
  ```bash
  git add frontend/src/pages/AssetDetail.jsx
  git commit -m "frontend: set manual auto-trading rule entry price default value to asset average purchase price"
  ```
