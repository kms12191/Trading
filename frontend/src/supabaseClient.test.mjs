import assert from 'node:assert/strict'
import { describe, it } from 'node:test'

import { normalizeWatchlistItem } from './supabaseClient.js'

describe('normalizeWatchlistItem', () => {
  it('treats six-letter overseas stock symbols as USD stocks', () => {
    const item = normalizeWatchlistItem({
      symbol: 'SPACEX',
      asset_type: 'STOCK',
      exchange: 'TOSS',
    })

    assert.equal(item.market_country, 'US')
    assert.equal(item.currency, 'USD')
    assert.equal(item.exchange, 'TOSS')
  })

  it('keeps six-digit Korean stock codes as KRW stocks', () => {
    const item = normalizeWatchlistItem({
      symbol: '005930',
      asset_type: 'STOCK',
    })

    assert.equal(item.market_country, 'KR')
    assert.equal(item.currency, 'KRW')
    assert.equal(item.exchange, 'KIS')
  })
})
