# 조건감시 진입가(평균단가) 보정 및 수동 등록 고도화 설계서

본 문서는 Toss증권 Open API, 코인원, 바이낸스, KIS를 연동한 실거래/모의 트레이딩 시스템에서 자동감시 규칙 생성 시 실제 체결가(평균단가)가 아닌 주문가(지정가)로 등록되는 문제를 해결하기 위한 스펙 및 설계서입니다.

---

## 1. 개요 및 배경

현재 시스템에서는 주문 전송 시 `auto_exit = True`를 통해 조건감시 규칙을 자동 등록하거나, 사용자가 수동으로 보유 중인 자산에 대해 감시 규칙을 새로 추가할 때 아래와 같은 한계가 존재합니다.

1. **주문 전송 후 감시 등록 시**: 실제 체결된 가격(평균단가)이 아닌 사용자가 주문 시 입력한 지정가(`order_price`)로 `entry_price`가 등록됩니다. 특히 시장가 주문이나 즉시 체결되지 않는 지정가 주문의 경우, 실제 체결가와 주문가 간의 괴리가 발생하여 익절/손절 감시가 오작동할 리스크가 있습니다.
2. **조건감시 단독 수동 등록 시**: 보유 중인 자산의 평균단가가 있음에도 불구하고, UI 및 백엔드 등록 프로세스에서 현재가를 진입가의 기본값으로 사용하거나 사용자가 입력한 단가로만 등록되게 설계되어 있습니다.

본 설계를 통해 **수동 등록 시 실제 보유 평단가를 기본 제시**하고, **주문 후 자동 등록된 감시 조건은 백그라운드 주문 상태 동기화 워커가 체결 완료를 감지하는 시점에 실제 평균체결단가로 자동 보정**하도록 개선합니다.

---

## 2. 변경 내용 및 상세 설계

### 2.1 데이터베이스 스키마 변경 (Supabase Migration)

`auto_trading_rules` 테이블과 해당 규칙을 생성한 진입 주문(`trade_proposals`)을 논리적으로 연결하기 위한 컬럼 및 외래키 제약조건을 추가합니다.

```sql
-- migration 파일 생성: supabase/migrations/20260709113000_add_entry_order_proposal_id_to_rules.sql
ALTER TABLE public.auto_trading_rules 
ADD COLUMN IF NOT EXISTS entry_order_proposal_id UUID REFERENCES public.trade_proposals(id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS idx_auto_trading_rules_entry_proposal
ON public.auto_trading_rules (entry_order_proposal_id)
WHERE entry_order_proposal_id IS NOT NULL;
```

---

### 2.2 백엔드 (Flask API) 변경 사항

#### ① 수동 주문 전송 API (`backend/routes/trade.py`)
- **place_manual_order() 수정**:
  - `trade_proposals` 테이블에 주문 제안을 `POST`하여 생성된 레코드의 `id`(UUID)를 추출합니다.
  - `auto_exit = True`이고 `action == "BUY"`인 경우 등록할 `rule_data`에 `entry_order_proposal_id: proposal_id`를 추가하여 감시 규칙을 `POST`합니다.

#### ② 수동 감시 조건 단독 등록 API 및 잔고 헬퍼 (`backend/routes/trade.py`)
- **보유 정보 조회 헬퍼 신설**:
  - 기존 수량만 조회하던 `_get_holding_qty_from_balance(client, symbol)`를 확장/대체하여 수량과 평단가를 동시에 조회할 수 있는 헬퍼를 작성합니다.
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
- **create_auto_trading_rule() 수정**:
  - 기존 `_get_holding_qty_from_balance` 호출을 `_get_holding_info_from_balance`로 교체합니다.
  - 사용자가 입력한 `entry_price`가 제공되지 않았거나 0인 경우, 혹은 실제 계좌에 보유 중인 자산인 경우 보유 평단가(`avg_price`)를 `entry_price`로 강제/보완 적용합니다.
  ```python
  holding = _get_holding_info_from_balance(client, symbol)
  if not holding or holding["qty"] <= 0:
      return jsonify({"success": False, "message": "보유 수량이 없습니다."}), 400
  
  # 사용자가 지정가로 입력한 값이 없거나 보유 평단가가 유효하다면 평단가를 우선 적용
  final_entry_price = entry_price
  if entry_price <= 0 or holding["avg_price"] > 0:
      final_entry_price = holding["avg_price"]
  ```

---

### 2.3 백그라운드 워커 (Order Status Sync) 변경 사항

- **파일**: [open_order_status_sync_service.py](file:///Users/kangheesung/10-19_개발/13_프로젝트/13.05_트레이딩/teamproject/backend/services/open_order_status_sync_service.py)
- **TOSS 지원 추가**:
  - `SUPPORTED_SYNC_EXCHANGES`에 `"TOSS"`를 추가합니다.
  - `_build_client()`에 `TOSS` 분기를 신설하여 `TossClient` 인스턴스를 빌드해 상태를 동기화하도록 유도합니다.
- **체결 완료 감지 시 감시 진입가 업데이트 추가**:
  - `_patch_proposal()` 함수 내에서 주문 상태가 `EXECUTED`로 업데이트되는 경우, `entry_order_proposal_id`가 일치하는 `auto_trading_rules`를 찾습니다.
  - `current_order["raw"]` 또는 관련 데이터에서 거래소별 실제 체결 평균단가(`average_filled_price`)를 추출합니다.
    - **TOSS**: `raw.result.averageFilledPrice` 혹은 `raw.result.execution.averageFilledPrice`
    - **KIS**: matched 이력 아이템의 `avg_price`
    - **COINONE**: `average_price`
    - **BINANCE**: `price` 혹은 `avgPrice`
  - 해당 감시 규칙의 `entry_price` 및 `investment_amount = (실제 평단가 * 수량)`을 DB에 업데이트(`PATCH`)합니다.

---

### 2.4 프론트엔드 (React) 변경 사항

- **파일**: [AssetDetail.jsx](file:///Users/kangheesung/10-19_개발/13_프로젝트/13.05_트레이딩/teamproject/frontend/src/pages/AssetDetail.jsx)
- **수동 조건감시 등록 폼 기본값 보정**:
  - 새로운 감시 등록 시 `setAddRulePrice` 호출 부분을 보정하여 사용자가 보유 중인 경우 평균 단가(`myHolding.avg_price`)를 최우선 값으로 세팅합니다.
  ```javascript
  // 수정 전
  setAddRulePrice(String(currentPrice || ''))
  
  // 수정 후
  setAddRulePrice(myHolding && myHolding.avg_price ? String(myHolding.avg_price) : String(currentPrice || ''))
  ```

---

## 3. 검증 및 테스트 계획

1. **수동 감시 등록 검증**:
   - 프론트엔드 상세 페이지에서 감시 등록창을 열어 보유 평단가가 정상적으로 인풋 박스에 채워지는지 확인합니다.
   - 실제로 등록을 진행했을 때 Supabase `auto_trading_rules` 테이블에 평단가로 `entry_price`가 인서트되는지 검증합니다.
2. **주문 후 자동 보정 검증**:
   - `auto_exit = True`를 지정하여 매수 주문(시장가 또는 지정가)을 테스트 모드로 보냅니다.
   - 처음에는 주문서상의 지정가로 `auto_trading_rules`에 등록되고 `entry_order_proposal_id`가 지정되는지 확인합니다.
   - 백그라운드 워커가 기동되어 `trade_proposals` 상태를 `EXECUTED`로 갱신하는 순간, 연관된 `auto_trading_rules`의 `entry_price`가 실제 체결 평단가로 정확히 업데이트되는지 DB 데이터를 검증합니다.
