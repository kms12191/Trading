import assert from 'node:assert/strict'
import { describe, it } from 'node:test'

import { resolveWatchlistDisplayCurrency } from './watchlistDisplay.js'

describe('resolveWatchlistDisplayCurrency', () => {
  it('keeps overseas stock prices in USD even when global display currency is KRW', () => {
    assert.equal(resolveWatchlistDisplayCurrency({
      assetType: 'STOCK',
      selectedCurrency: 'USD',
      displayCurrency: 'KRW',
      cryptoChartMode: 'KRW',
    }), 'USD')
  })

  it('keeps domestic stock prices in KRW', () => {
    assert.equal(resolveWatchlistDisplayCurrency({
      assetType: 'STOCK',
      selectedCurrency: 'KRW',
      displayCurrency: 'USD',
      cryptoChartMode: 'USD',
    }), 'KRW')
  })

  it('uses the crypto chart mode for crypto prices', () => {
    assert.equal(resolveWatchlistDisplayCurrency({
      assetType: 'CRYPTO',
      selectedCurrency: 'USDT',
      displayCurrency: 'KRW',
      cryptoChartMode: 'USD',
    }), 'USD')
  })
})
