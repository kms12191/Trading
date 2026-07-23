import assert from 'node:assert/strict'
import test from 'node:test'

import { buildPricePresentation } from './chatbotPricePresentation.js'

test('extracts the price card from a compound price and news result', () => {
  const result = buildPricePresentation({
    source: 'COMPOUND_INFO',
    price: {
      source: 'ASSET_PRICE',
      symbol: '003680',
      display_name: '한성기업',
      current_price: 9300,
      change_rate: 9.93,
      currency: 'KRW',
    },
    secondary: { source: 'NEWS_DB', items: [] },
  })

  assert.equal(result.shouldRender, true)
  assert.equal(result.priceText, '9,300')
  assert.equal(result.changeRateText, '+9.93%')
})

test('does not render a price card when the quote is unavailable', () => {
  assert.deepEqual(
    buildPricePresentation({ source: 'ASSET_PRICE', current_price: null }),
    { shouldRender: false },
  )
})

test('keeps USD price precision up to 4 decimal places', () => {
  const result = buildPricePresentation({
    source: 'ASSET_PRICE',
    symbol: 'DOGE',
    display_name: 'DOGE',
    current_price: 0.123456,
    currency: 'USD',
  })

  assert.equal(result.priceText, '0.1235')
})
