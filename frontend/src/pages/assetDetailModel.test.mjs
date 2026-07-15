import assert from 'node:assert/strict'
import { describe, it } from 'node:test'

import {
  getAssetChartPriceFormat,
  getAssetCurrencyDigits,
  getAssetCurrencySign,
  getAssetPriceDigits,
  getAutoExecutionModeLabel,
  getAutoRuleStatusLabel,
  getAutoTriggerLabel,
  getOrderSideLabel,
  getOrderStatusLabel,
  getStockWarningBadgeTone,
  isActionableOrderStatus,
  isCancelReplaceExchange,
  isDomesticStockSymbol,
  isUsStockSymbol,
  normalizeStockSymbol,
} from './assetDetailModel.js'

describe('assetDetailModel', () => {
  it('normalizes and classifies stock symbols', () => {
    assert.equal(normalizeStockSymbol(' aapl '), 'AAPL')
    assert.equal(isDomesticStockSymbol('005930'), true)
    assert.equal(isDomesticStockSymbol('AAPL'), false)
    assert.equal(isUsStockSymbol('AAPL'), true)
    assert.equal(isUsStockSymbol('005930'), false)
    assert.equal(isUsStockSymbol('005930', 'US'), true)
    assert.equal(isUsStockSymbol('AAPL', 'KR'), false)
  })

  it('classifies actionable order statuses and cancel-replace exchanges', () => {
    assert.equal(isActionableOrderStatus('open'), true)
    assert.equal(isActionableOrderStatus('executed'), false)
    assert.equal(isCancelReplaceExchange('COINONE'), true)
    assert.equal(isCancelReplaceExchange('BINANCE_UM_FUTURES'), true)
    assert.equal(isCancelReplaceExchange('TOSS'), false)
  })

  it('returns Korean labels for order and auto rule states', () => {
    assert.equal(getOrderStatusLabel('PENDING'), '미체결')
    assert.equal(getOrderStatusLabel('APPROVED'), '접수 완료')
    assert.equal(getOrderStatusLabel('EXECUTED'), '체결완료')
    assert.equal(getOrderStatusLabel('CANCELLED'), '취소완료')
    assert.equal(getOrderStatusLabel('FAILED'), '실패')
    assert.equal(getOrderStatusLabel('UNKNOWN_STATUS'), 'UNKNOWN_STATUS')
    assert.equal(getOrderSideLabel('SELL'), '매도')
    assert.equal(getOrderSideLabel('BUY'), '매수')
    assert.equal(getAutoRuleStatusLabel('RUNNING'), '감시 중')
    assert.equal(getAutoRuleStatusLabel('COMPLETED'), '완료')
    assert.equal(getAutoRuleStatusLabel('STOPPED'), '정지')
    assert.equal(getAutoExecutionModeLabel('AUTO'), '조건 도달 시 자동 매도')
    assert.equal(getAutoExecutionModeLabel('PROPOSAL'), '조건 도달 시 매도 제안')
    assert.equal(getAutoTriggerLabel('TAKE_PROFIT'), '익절 도달')
    assert.equal(getAutoTriggerLabel('STOP_LOSS'), '손절 도달')
    assert.equal(getAutoTriggerLabel(''), '아직 미도달')
  })

  it('returns stock warning badge tone with fallback', () => {
    assert.match(getStockWarningBadgeTone('TRADING_SUSPENDED'), /rose/)
    assert.equal(
      getStockWarningBadgeTone('UNKNOWN_WARNING'),
      'border-slate-600 bg-slate-800/70 text-slate-200',
    )
  })

  it('calculates asset price display digits and chart price format', () => {
    assert.equal(getAssetCurrencySign({ exchange: 'COINONE', assetType: 'CRYPTO', isUsStock: false }), '₩')
    assert.equal(getAssetCurrencySign({ exchange: 'BINANCE', assetType: 'CRYPTO', isUsStock: false }), '$')
    assert.equal(getAssetCurrencySign({ exchange: 'TOSS', assetType: 'STOCK', isUsStock: true }), '$')
    assert.equal(getAssetCurrencyDigits({ exchange: 'COINONE', assetType: 'CRYPTO', isUsStock: false }), 0)
    assert.equal(getAssetCurrencyDigits({ exchange: 'BINANCE', assetType: 'CRYPTO', isUsStock: false }), 6)
    assert.equal(getAssetPriceDigits(0.0004, { exchange: 'BINANCE', assetType: 'CRYPTO', isUsStock: false }), 8)
    assert.equal(getAssetPriceDigits(0.5, { exchange: 'BINANCE', assetType: 'CRYPTO', isUsStock: false }), 6)
    assert.equal(getAssetPriceDigits(50, { exchange: 'BINANCE', assetType: 'CRYPTO', isUsStock: false }), 4)
    assert.equal(getAssetPriceDigits(500, { exchange: 'BINANCE', assetType: 'CRYPTO', isUsStock: false }), 2)
    assert.deepEqual(
      getAssetChartPriceFormat(0.0004, { exchange: 'BINANCE', assetType: 'CRYPTO', isUsStock: false, currentPrice: 1 }),
      { type: 'price', precision: 8, minMove: 0.00000001 },
    )
  })
})
