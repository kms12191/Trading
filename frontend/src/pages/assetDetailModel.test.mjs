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
  buildCandleSignature,
  formatDecimalMetric,
  formatDisclosureDate,
  formatMetric,
  formatNewsSource,
  formatPercent,
  formatProbability,
  formatRatio,
  formatRelativeTime,
  formatReturnPercent,
  formatSignalScore,
  formatSignedPercentValue,
  formatStaleness,
  formatTimestamp,
  getDisclosureToneClass,
  getOrderSideLabel,
  getOrderStatusLabel,
  getSupportedCryptoOrderExchanges,
  getOrderEntryAssetType,
  findTradableOrderAccount,
  getPolicyReasonLabel,
  getPolicyReasonLabels,
  getProbabilityLevel,
  getSignalGradeLabel,
  getSignalGradeTone,
  getStockWarningBadgeTone,
  getNewsSyncMessage,
  isActionableOrderStatus,
  isCancelReplaceExchange,
  isDomesticStockSymbol,
  isUsStockSymbol,
  normalizeCandleTime,
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

  it('resolves crypto order exchanges from listing and tradable metadata', () => {
    assert.deepEqual(
      getSupportedCryptoOrderExchanges({
        coinone_listed: true,
        coinone_tradable: true,
        binance_listed: false,
        binance_tradable: false,
      }),
      ['COINONE'],
    )
    assert.deepEqual(
      getSupportedCryptoOrderExchanges({
        coinone_listed: false,
        coinone_tradable: false,
        binance_listed: true,
        binance_tradable: true,
      }),
      ['BINANCE', 'BINANCE_UM_FUTURES'],
    )
    assert.deepEqual(
      getSupportedCryptoOrderExchanges({
        coinone_listed: true,
        coinone_tradable: true,
        binance_listed: true,
        binance_tradable: true,
      }),
      ['COINONE', 'BINANCE', 'BINANCE_UM_FUTURES'],
    )
    assert.deepEqual(
      getSupportedCryptoOrderExchanges({
        exchanges: ['BINANCE'],
      }),
      ['BINANCE', 'BINANCE_UM_FUTURES'],
    )
  })

  it('selects only a tradable order-entry account matching exchange, asset type, and environment', () => {
    const accounts = [
      { id: 'COINONE:REAL:key-1', exchange: 'COINONE', asset_type: 'CRYPTO_SPOT', broker_env: 'REAL', trade_enabled: true },
      { id: 'BINANCE:REAL:key-2', exchange: 'BINANCE', asset_type: 'CRYPTO_SPOT', broker_env: 'REAL', trade_enabled: false },
      { id: 'BINANCE_UM_FUTURES:MOCK:key-2', exchange: 'BINANCE_UM_FUTURES', asset_type: 'CRYPTO_FUTURES', broker_env: 'MOCK', trade_enabled: true },
    ]

    assert.equal(getOrderEntryAssetType('COINONE'), 'CRYPTO_SPOT')
    assert.equal(getOrderEntryAssetType('BINANCE_UM_FUTURES'), 'CRYPTO_FUTURES')
    assert.equal(getOrderEntryAssetType('TOSS'), 'STOCK')
    assert.equal(findTradableOrderAccount(accounts, 'COINONE', 'REAL')?.id, 'COINONE:REAL:key-1')
    assert.equal(findTradableOrderAccount(accounts, 'BINANCE', 'REAL'), null)
    assert.equal(findTradableOrderAccount(accounts, 'BINANCE_UM_FUTURES', 'MOCK')?.id, 'BINANCE_UM_FUTURES:MOCK:key-2')
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

  it('formats news, disclosure, timestamp and ML metric values', () => {
    const now = new Date('2026-07-15T12:00:00+09:00')
    assert.equal(formatRelativeTime('2026-07-15T11:59:30+09:00', now), '방금 전')
    assert.equal(formatRelativeTime('2026-07-15T11:40:00+09:00', now), '20분 전')
    assert.equal(formatRelativeTime('2026-07-15T09:00:00+09:00', now), '3시간 전')
    assert.equal(formatNewsSource('NAVER'), '네이버')
    assert.equal(formatNewsSource('finnhub'), 'Finnhub')
    assert.equal(formatDisclosureDate('20260715'), '2026.07.15')
    assert.match(getDisclosureToneClass('positive'), /emerald/)
    assert.equal(formatTimestamp(1_783_820_000), '07. 12. 10:33:20')
    assert.equal(formatProbability(0.456), '45.6%')
    assert.equal(formatSignalScore(1.234), '1.23')
    assert.equal(formatStaleness(90), '1시간 전')
    assert.equal(formatDecimalMetric(0.12345, 3), '0.123')
    assert.equal(formatRatio(1.234), '1.23x')
    assert.equal(formatMetric(0.98765, 4), '0.9877')
    assert.equal(formatPercent(0.1234, 1), '12.3%')
    assert.equal(formatReturnPercent(-0.1234, 2), '-12.34%')
    assert.equal(formatSignedPercentValue(3.45, 2), '+3.45%')
    assert.equal(getNewsSyncMessage(3), '최근 7일 이내 투자 관련 뉴스 3건을 확인했습니다.')
    assert.equal(getNewsSyncMessage(0), '최근 7일 이내 투자 관련 뉴스가 없습니다.')
  })

  it('labels ML probability, grade and policy reasons', () => {
    assert.deepEqual(
      getProbabilityLevel(0.7, 'up'),
      { label: '강함', tone: 'text-emerald-300', detail: '상승 쪽 신호가 비교적 뚜렷합니다.' },
    )
    assert.deepEqual(
      getProbabilityLevel(0.7, 'risk'),
      { label: '높음', tone: 'text-rose-300', detail: '하락 위험을 먼저 확인해야 합니다.' },
    )
    assert.equal(getSignalGradeLabel('STRONG_BUY_CANDIDATE'), '강한 후보')
    assert.match(getSignalGradeTone('RISKY'), /rose/)
    assert.equal(getPolicyReasonLabel('market_breadth'), '시장 폭 부족')
    assert.deepEqual(
      getPolicyReasonLabels({ policy_block_reason: 'market_breadth|sector_strength' }),
      ['시장 폭 부족', '섹터 강도 부족'],
    )
    assert.deepEqual(
      getPolicyReasonLabels({ policy_block_reason_labels: ['직접 라벨'] }),
      ['직접 라벨'],
    )
  })

  it('normalizes candle time and builds candle signatures', () => {
    assert.equal(normalizeCandleTime(123), 123)
    assert.equal(normalizeCandleTime('123'), 123)
    assert.equal(normalizeCandleTime('2026-07-15'), '2026-07-15')
    assert.equal(normalizeCandleTime('2026-07-15 12:00:00'), 1784084400)
    assert.equal(normalizeCandleTime(''), null)
    assert.equal(buildCandleSignature([]), '')
    assert.equal(
      buildCandleSignature([{ time: 1, close: 10, volume: 100 }, { time: 2, close: 20, volume: 200 }]),
      '2:2:20:200',
    )
  })
})
