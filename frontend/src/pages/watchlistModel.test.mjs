import assert from 'node:assert/strict'
import { describe, it } from 'node:test'

import {
  formatWatchlistCandles,
  getCryptoWatchlistChartConfig,
  getNextWatchlistSelectedId,
  getWatchlistChartSymbol,
  getWatchlistChartConfig,
  getWatchlistMarketFilterKey,
  normalizeWatchlistCandleTime,
} from './watchlistModel.js'

describe('watchlistModel', () => {
  it('classifies watchlist items for market filters', () => {
    assert.equal(getWatchlistMarketFilterKey({ assetType: 'CRYPTO' }), 'crypto')
    assert.equal(getWatchlistMarketFilterKey({ market: '코인' }), 'crypto')
    assert.equal(getWatchlistMarketFilterKey({ marketCountry: 'US' }), 'overseas')
    assert.equal(getWatchlistMarketFilterKey({ market: '해외 주식' }), 'overseas')
    assert.equal(getWatchlistMarketFilterKey({ marketCountry: 'KR' }), 'domestic')
  })

  it('normalizes candle time and returns sorted unique candles', () => {
    assert.equal(normalizeWatchlistCandleTime(1710000000), 1710000000)
    assert.equal(normalizeWatchlistCandleTime('2026-07-15'), '2026-07-15')
    assert.equal(normalizeWatchlistCandleTime('1710000001'), 1710000001)
    assert.equal(normalizeWatchlistCandleTime('bad-time'), null)

    const candles = formatWatchlistCandles([
      { time: '2026-07-15', open: '1', high: '2', low: '0.5', close: '1.5', volume: '10' },
      { time: '2026-07-15', open: '2', high: '3', low: '1', close: '2.5', volume: '20' },
      { time: '2026-07-14', open: '1', high: '1', low: '1', close: '1' },
      { time: '', open: '1', high: '1', low: '1', close: '1' },
    ])

    assert.equal(candles.length, 2)
    assert.equal(candles[0].time, '2026-07-14')
    assert.equal(candles[1].close, 2.5)
    assert.equal(candles[1].volume, 20)
  })

  it('resolves chart config and selected item id', () => {
    assert.deepEqual(getCryptoWatchlistChartConfig('USD'), { exchange: 'BINANCE', brokerEnv: 'REAL' })
    assert.deepEqual(getCryptoWatchlistChartConfig('FUTURES'), { exchange: 'BINANCE_UM_FUTURES', brokerEnv: 'REAL' })
    assert.deepEqual(getCryptoWatchlistChartConfig('KRW'), { exchange: 'COINONE', brokerEnv: 'REAL' })
    assert.deepEqual(
      getWatchlistChartConfig({ id: 'AAPL', account: 'TOSS', sourcePayload: { broker_env: 'MOCK' } }, 'STOCK'),
      { exchange: 'TOSS', brokerEnv: 'MOCK' },
    )
    assert.deepEqual(
      getWatchlistChartConfig({ id: 'BTC' }, 'CRYPTO'),
      { exchange: 'COINONE', brokerEnv: 'REAL' },
    )
    assert.equal(getWatchlistChartSymbol({ id: 'DOGE' }, 'CRYPTO', 'KRW'), 'DOGE')
    assert.equal(getWatchlistChartSymbol({ id: 'DOGE' }, 'CRYPTO', 'USD'), 'DOGEUSDT')
    assert.equal(getWatchlistChartSymbol({ id: 'DOGE_KRW' }, 'CRYPTO', 'FUTURES'), 'DOGEUSDT')
    assert.equal(getWatchlistChartSymbol({ id: 'DOGEUSDT' }, 'CRYPTO', 'USD'), 'DOGEUSDT')
    assert.equal(getNextWatchlistSelectedId('B', [{ id: 'A' }, { id: 'B' }]), 'B')
    assert.equal(getNextWatchlistSelectedId('C', [{ id: 'A' }, { id: 'B' }]), 'A')
    assert.equal(getNextWatchlistSelectedId('C', []), '')
  })
})
