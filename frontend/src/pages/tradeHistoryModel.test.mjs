import assert from 'node:assert/strict'
import test from 'node:test'

import {
  buildBrokerOrderLookup,
  filterUnlinkedBrokerOrders,
  formatCurrency,
  formatCryptoAmount,
  formatUnitCurrency,
  isActionableOrderStatus,
  isDeletableTradeHistoryItem,
  mapAiFundOrderToTrade,
  mapBrokerHistoryToTrade,
  mapProposalToTrade,
  mapTradeStatus,
  mapTransferToTrades,
  sortTradeHistoryRows,
} from './tradeHistoryModel.js'

test('거래 상태와 금액 표시를 화면용 문구로 변환한다', () => {
  assert.equal(mapTradeStatus('PARTIALLY_FILLED'), '부분체결')
  assert.equal(mapTradeStatus('CANCELLED'), '취소완료')
  assert.equal(isActionableOrderStatus('OPEN'), true)
  assert.equal(isActionableOrderStatus('EXECUTED'), false)
  assert.equal(formatCurrency(1234.5, 'KRW'), '₩1,235')
  assert.equal(formatCurrency(12.3, 'USD'), '$12.30')
  assert.equal(formatUnitCurrency(0.123456, 'USD'), '$0.1235')
  assert.equal(formatUnitCurrency(1.23456, 'USDT'), '$1.2346')
  assert.equal(formatUnitCurrency(0.123456, 'KRW'), '₩0.1235')
  assert.equal(formatUnitCurrency(1.23456, 'KRW'), '₩1.2')
  assert.equal(formatCryptoAmount(1.234567891, 'xrp'), '1.23456789 XRP')
})

test('브로커 원장과 연결된 앱 주문은 중복 원장을 제외하고 수수료를 반영한다', () => {
  const proposal = {
    id: 'proposal-1',
    exchange: 'TOSS',
    broker_env: 'REAL',
    external_order_id: 'order-1',
    symbol: 'AAPL',
    side: 'BUY',
    price: 10,
    volume: 2,
    currency: 'USD',
    status: 'OPEN',
    created_at: '2026-07-15T00:00:00Z',
  }
  const brokerOrder = {
    id: 'broker-1',
    exchange: 'TOSS',
    broker_env: 'REAL',
    external_order_id: 'order-1',
    status: 'EXECUTED',
    commission: 0.3,
    tax: 0.2,
  }
  const lookup = buildBrokerOrderLookup([proposal], [brokerOrder])
  const row = mapProposalToTrade(proposal, lookup)

  assert.equal(row.status, '체결완료')
  assert.equal(row.sourceDescription, 'AE에서 생성·승인한 주문이며 토스 원장과 연결됨')
  assert.equal(row.fees, '$0.50')
  assert.deepEqual(filterUnlinkedBrokerOrders([brokerOrder], lookup), [])
})

test('독립 브로커 원장을 거래내역 행으로 변환한다', () => {
  const row = mapBrokerHistoryToTrade({
    id: 'broker-2',
    exchange: 'TOSS',
    market_country: 'KR',
    symbol: '005930',
    side: 'SELL',
    price: 70000,
    quantity: 3,
    status: 'EXECUTED',
    ordered_at: '2026-07-15T01:02:03Z',
    commission: 10,
    tax: 20,
  }, { '005930': '삼성전자' })

  assert.equal(row.id, 'broker-broker-2')
  assert.equal(row.symbolName, '삼성전자')
  assert.equal(row.side, '매도')
  assert.equal(row.amount, '₩210,000')
  assert.equal(row.fees, '₩30')
})

test('AI 위탁 체결 원장을 일반 거래내역 행으로 변환한다', () => {
  const row = mapAiFundOrderToTrade({
    id: 'ai-order-1',
    exchange_type: 'coinone',
    symbol: 'BTT',
    side: 'BUY',
    status: 'FILLED',
    requested_qty: 25000000,
    filled_qty: 25000000,
    requested_price: 0.000402,
    average_fill_price: 0.0004,
    fee_amount: 2,
    exchange_order_id: 'exchange-1',
    created_at: '2026-07-23T00:44:25Z',
  })

  assert.equal(row.sourceType, 'AI_FUND')
  assert.equal(row.exchange, 'COINONE')
  assert.equal(row.status, '체결완료')
  assert.equal(row.quantity, '25,000,000')
  assert.equal(row.amount, '₩10,000')
  assert.equal(row.fees, '₩2')
})

test('완료된 자산 이동은 출금과 입금 행을 함께 만든다', () => {
  const rows = mapTransferToTrades({
    id: 'transfer-1',
    status: 'COMPLETED',
    currency: 'XRP',
    amount: 10,
    received_amount: 9.9,
    withdraw_fee: 0.1,
    fee_currency: 'XRP',
    from_exchange: 'COINONE',
    to_exchange: 'BINANCE',
    created_at: '2026-07-15T00:00:00Z',
    completed_at: '2026-07-15T00:10:00Z',
  })

  assert.equal(rows.length, 2)
  assert.equal(rows[0].side, '출금')
  assert.equal(rows[0].quantity, '-10 XRP')
  assert.equal(rows[0].status, '출금완료')
  assert.equal(rows[1].side, '입금')
  assert.equal(rows[1].quantity, '+9.9 XRP')
  assert.equal(rows[1].status, '입금완료')
})

test('거래내역 삭제 가능 조건과 정렬을 계산한다', () => {
  assert.equal(isDeletableTradeHistoryItem({ sourceType: 'APP', status: '주문실패' }), true)
  assert.equal(isDeletableTradeHistoryItem({ sourceType: 'BROKER', status: '주문실패' }), false)

  const rows = sortTradeHistoryRows([
    { id: 'old', date: '2026-07-14', time: '09:00:00' },
    { id: 'new', date: '2026-07-15', time: '09:00:00' },
  ])
  assert.deepEqual(rows.map((row) => row.id), ['new', 'old'])
})
