import assert from 'node:assert/strict'
import test from 'node:test'

import {
  buildPrecheckRequest,
  canAdvanceOrderStep,
  createEmptyOrderDraft,
  getOrderEntryLabels,
  invalidatePrecheck,
} from './orderEntryModel.js'

test('새 매매 요청은 계좌와 주문 방향을 임의 선택하지 않는다', () => {
  const draft = createEmptyOrderDraft()

  assert.equal(draft.account, null)
  assert.equal(draft.intent, '')
  assert.equal(draft.selected_symbol, null)
  assert.equal(draft.symbol_query, '')
  assert.equal(draft.quantity, '')
  assert.equal(draft.order_type, '')
  assert.equal(draft.price, '')
})

test('계좌와 거래 목적을 모두 선택해야 1단계를 통과한다', () => {
  const draft = createEmptyOrderDraft()

  assert.equal(canAdvanceOrderStep(draft, 1), false)
  assert.equal(canAdvanceOrderStep({ ...draft, account: { id: 'a' }, intent: 'BUY' }, 1), true)
})

test('검색 문자열만 입력하고 결과 종목을 선택하지 않으면 2단계를 통과하지 못한다', () => {
  const draft = {
    ...createEmptyOrderDraft(),
    account: { id: 'a', exchange: 'TOSS', asset_type: 'STOCK', broker_env: 'REAL' },
    intent: 'BUY',
    symbol_query: '삼성전자',
    quantity: '1',
    order_type: 'LIMIT',
    price: '70000',
  }

  assert.equal(canAdvanceOrderStep(draft, 2), false)
  assert.equal(canAdvanceOrderStep({ ...draft, selected_symbol: { symbol: '005930' } }, 2), true)
})

test('주문 입력값 변경은 기존 사전검증 토큰을 즉시 무효화한다', () => {
  const draft = {
    ...createEmptyOrderDraft(),
    precheck: { can_create_proposal: true },
    precheck_token: 'signed-token',
  }

  const next = invalidatePrecheck(draft, { quantity: '2' })

  assert.equal(next.quantity, '2')
  assert.equal(next.precheck, null)
  assert.equal(next.precheck_token, '')
})

test('자산 유형별 수량과 통화 및 선물 거래 목적 용어를 반환한다', () => {
  assert.deepEqual(getOrderEntryLabels({ exchange: 'TOSS', asset_type: 'STOCK', currency: 'USD' }, 'BUY'), {
    quantity: '주',
    currency: 'USD',
    intent: '매수',
  })
  assert.deepEqual(getOrderEntryLabels({ exchange: 'COINONE', asset_type: 'CRYPTO_SPOT', currency: 'KRW' }, 'SELL'), {
    quantity: '개',
    currency: 'KRW',
    intent: '매도',
  })
  assert.deepEqual(getOrderEntryLabels({ exchange: 'BINANCE_UM_FUTURES', asset_type: 'CRYPTO_FUTURES', currency: 'USDT' }, 'OPEN_SHORT'), {
    quantity: '계약 수량',
    currency: 'USDT',
    intent: '신규 숏',
  })
})

test('사전검증 요청은 선택된 계좌와 종목만 사용한다', () => {
  const request = buildPrecheckRequest({
    ...createEmptyOrderDraft(),
    account: {
      id: 'BINANCE_UM_FUTURES:MOCK:key-1',
      exchange: 'BINANCE_UM_FUTURES',
      asset_type: 'CRYPTO_FUTURES',
      broker_env: 'MOCK',
    },
    intent: 'CLOSE_POSITION',
    selected_symbol: { symbol: 'BTCUSDT', position_side: 'SHORT' },
    quantity: '0.002',
    order_type: 'LIMIT',
    price: '50000',
    leverage: 3,
    margin_type: 'ISOLATED',
    idempotency_key: '55555555-5555-4555-8555-555555555555',
  })

  assert.deepEqual(request, {
    account_id: 'BINANCE_UM_FUTURES:MOCK:key-1',
    exchange: 'BINANCE_UM_FUTURES',
    asset_type: 'CRYPTO_FUTURES',
    broker_env: 'MOCK',
    intent: 'CLOSE_POSITION',
    symbol: 'BTCUSDT',
    symbol_selected: true,
    position_side: 'SHORT',
    quantity: 0.002,
    order_type: 'LIMIT',
    price: 50000,
    leverage: 3,
    margin_type: 'ISOLATED',
    idempotency_key: '55555555-5555-4555-8555-555555555555',
  })
})
