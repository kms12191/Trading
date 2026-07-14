import assert from 'node:assert/strict'
import test from 'node:test'

import { buildWatchlistPresentation } from './chatbotWatchlistPresentation.js'

test('normalizes USER_WATCHLIST list results for table rendering', () => {
  const result = buildWatchlistPresentation({
    source: 'USER_WATCHLIST',
    view: 'list',
    items: [
      {
        name: '이스트',
        symbol: '067390',
        asset_type: 'STOCK',
        exchange: 'TOSS',
      },
    ],
  })

  assert.equal(result.shouldRender, true)
  assert.equal(result.count, 1)
  assert.deepEqual(result.items[0], {
    name: '이스트',
    symbol: '067390',
    assetType: 'STOCK',
    exchange: 'TOSS',
  })
})

test('does not replace watchlist focus guidance with a table', () => {
  const result = buildWatchlistPresentation({
    source: 'USER_WATCHLIST',
    view: 'focus',
    items: [
      {
        name: '삼성전자',
        symbol: '005930',
      },
    ],
  })

  assert.equal(result.shouldRender, false)
})
