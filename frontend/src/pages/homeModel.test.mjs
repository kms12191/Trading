import assert from 'node:assert/strict'
import { describe, it } from 'node:test'

import {
  applyClientMarketFilters,
  changeClass,
  formatChange,
  formatHomeMarketPrice,
  formatHomeMarketValue,
  getHomeRowsByCategory,
  getHomeWatchlistKey,
  isForeignHomeMarketRow,
} from './homeModel.js'

describe('homeModel', () => {
  it('formats market rows with domestic and overseas price rules', () => {
    assert.equal(isForeignHomeMarketRow({ symbol: 'AAPL', asset_type: 'STOCK' }), true)
    assert.equal(isForeignHomeMarketRow({ symbol: '005930', market_country: 'KR' }), false)
    assert.equal(formatHomeMarketPrice({ symbol: 'AAPL', asset_type: 'STOCK', price: 195.5 }), '$195.5')
    assert.equal(formatHomeMarketPrice({ symbol: '005930', price: 75000 }), '75,000원')
    assert.equal(formatChange({ change_rate: 2.345 }), '+2.35%')
    assert.equal(changeClass('+1.00%'), 'text-red-400')
    assert.equal(changeClass('-1.00%'), 'text-sky-400')
  })

  it('formats market value and sorts client rows by ranking', () => {
    assert.equal(formatHomeMarketValue({ trading_value: 120_000_000 }, 'value', '거래대금'), '1억원')
    assert.equal(formatHomeMarketValue({ volume: 12_345 }, 'volume', '거래량'), '12,345')
    assert.equal(formatHomeMarketValue({ symbol: 'AAPL', asset_type: 'STOCK', change_rate: 5 }, 'value', '상승률'), '-')

    const rows = [
      { symbol: 'AAA', trading_value: 100, change_rate: -2 },
      { symbol: 'BBB', trading_value: 300, change_rate: 4 },
      { symbol: 'CCC', trading_value: 200, change_rate: 1 },
    ]
    assert.deepEqual(
      applyClientMarketFilters(rows, { region: '국내', ranking: '거래대금' }).map((row) => row.symbol),
      ['BBB', 'CCC', 'AAA'],
    )
    assert.deepEqual(
      applyClientMarketFilters(rows, { region: '국내', ranking: '하락률' }).map((row) => row.symbol),
      ['AAA', 'CCC', 'BBB'],
    )
  })

  it('derives mobile category rows and watchlist keys', () => {
    const stockRows = [
      { symbol: '005930', trading_value: 100, change_rate: 1 },
      { symbol: 'AAPL', asset_type: 'STOCK', trading_value: 300, change_rate: 5 },
    ]
    const coinRows = [
      { symbol: 'BTC', trading_value: 200, change_rate: -1 },
    ]

    assert.equal(getHomeWatchlistKey({ symbol: '005930' }, 'STOCK'), 'STOCK:KIS:005930')
    assert.equal(getHomeWatchlistKey({ id: '005930', assetType: 'STOCK', exchange: 'KIS' }, 'STOCK'), 'STOCK:KIS:005930')
    assert.equal(getHomeWatchlistKey({ symbol: 'AAPL', asset_type: 'STOCK' }, 'STOCK'), 'STOCK:TOSS:AAPL')
    assert.equal(getHomeWatchlistKey({ symbol: 'BTC', exchange: 'COINONE' }, 'CRYPTO'), 'CRYPTO:COINONE:BTC')
    assert.deepEqual(
      getHomeRowsByCategory({
        category: { key: 'foreign' },
        metric: { key: 'rise', valueKey: 'change' },
        stockRows,
        coinRows,
      }).map((row) => row.symbol),
      ['AAPL'],
    )
    assert.deepEqual(
      getHomeRowsByCategory({
        category: { key: 'coin' },
        metric: { key: 'tradingValue', valueKey: 'value' },
        stockRows,
        coinRows,
      }).map((row) => row.symbol),
      ['BTC'],
    )
  })
})
