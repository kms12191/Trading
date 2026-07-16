import assert from 'node:assert/strict'
import test from 'node:test'

import {
  buildAccountSummaryCards,
  buildHoldingRows,
  formatAllocationPercent,
  formatCurrency,
  formatNativeCurrency,
  formatUnitCurrency,
  getBalanceCashEntries,
  getTransferRoute,
  normalizeExchangeCode,
  parseNumeric,
  sortHoldings,
} from './assetsTabModel.js'

test('자산 숫자와 통화 표시를 안정적으로 변환한다', () => {
  assert.equal(parseNumeric('₩12,300'), 12300)
  assert.equal(parseNumeric('-$10.5'), -10.5)
  assert.equal(parseNumeric('bad'), 0)
  assert.equal(formatNativeCurrency(1200, 'KRW'), '₩1,200')
  assert.equal(formatNativeCurrency(12.3, 'USD'), '$12.30')
  assert.equal(formatCurrency(10, 'USD', 'KRW', 1500), '₩15,000')
  assert.equal(formatCurrency(1500, 'KRW', 'USD', 1500), '$1.00')
  assert.equal(formatUnitCurrency(0.05, 'USD', 'USD', 1500), '$0.05')
})

test('거래소 코드를 정규화하고 출금 경로를 계산한다', () => {
  assert.equal(normalizeExchangeCode('binance_um_futures real'), 'BINANCE_UM_FUTURES')
  assert.equal(normalizeExchangeCode('coinone'), 'COINONE')
  assert.equal(getTransferRoute({ exchange: 'COINONE' })?.toExchange, 'BINANCE')
  assert.equal(getTransferRoute({ rawExchange: 'BINANCE' })?.toExchange, 'COINONE')
  assert.equal(getTransferRoute({ exchange: 'TOSS' }), null)
})

test('계좌 현금 구성과 계좌 요약 카드를 만든다', () => {
  const cashEntries = getBalanceCashEntries({
    currency: 'KRW',
    available_cash_details: {
      components: [
        { currency: 'KRW', cash_buying_power: 1000 },
        { currency: 'USD', cash_buying_power: 2 },
      ],
    },
  })
  assert.deepEqual(cashEntries, [
    { currency: 'KRW', amount: 1000 },
    { currency: 'USD', amount: 2 },
  ])

  const cards = buildAccountSummaryCards({
    accountBalances: [
      {
        exchange: 'TOSS',
        env: 'REAL',
        available_cash_details: { components: [{ currency: 'KRW', cash_buying_power: 10000 }] },
        holdings: [{ symbol: '005930', currency: 'KRW', qty: 1, current_price: 70000 }],
      },
      {
        exchange: 'BINANCE',
        env: 'MOCK',
        available_cash: 100,
        available_cash_currency: 'USDT',
      },
    ],
    showMockAssets: false,
  })

  assert.deepEqual(cards.map((card) => card.id), ['domestic-stock', 'overseas-stock'])
  assert.equal(cards.find((card) => card.id === 'domestic-stock')?.amount, 80000)
})

test('보유 종목 표시 행과 정렬을 계산한다', () => {
  const rows = buildHoldingRows({
    holdings: [
      {
        exchange: 'COINONE',
        symbol: 'XRP',
        name: '리플',
        qty: 10,
        avg_price: 500,
        current_price: 600,
        profit: 1000,
        profit_rate: 20,
      },
      {
        exchange: 'TOSS',
        symbol: 'SPACEX',
        name: '스페이스X',
        market_country: 'US',
        currency: 'KRW',
        qty: 1,
        avg_price: 100,
        current_price: 110,
        profit: 10,
        profit_rate: 10,
      },
    ],
    displayCurrency: 'KRW',
    exchangeRate: 1500,
  })

  assert.equal(rows[0].assetType, 'CRYPTO')
  assert.equal(rows[0].currentPrice, '₩600')
  assert.equal(rows[1].assetType, 'STOCK')
  assert.equal(rows[1].currentPrice, '$110')
  assert.deepEqual(sortHoldings(rows, { key: 'profit', direction: 'desc' }).map((row) => row.id), ['XRP', 'SPACEX'])
})

test('배분 비율 표시를 보정한다', () => {
  assert.equal(formatAllocationPercent({ rawPercent: 0.4, value: 0.4 }), '1% 미만')
  assert.equal(formatAllocationPercent({ rawPercent: 0 }), '0%')
  assert.equal(formatAllocationPercent({ rawPercent: 12.345 }), '12.3%')
})
