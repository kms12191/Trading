import assert from 'node:assert/strict'
import { describe, it } from 'node:test'

import {
  buildBalanceRequests,
  getDashboardWatchlistAssetType,
  getDashboardWatchlistChartConfig,
  getDashboardWatchlistCurrency,
  getHoldingEvaluationKrw,
  getHoldingEvaluationNative,
  formatUnitCurrency,
  mergeAccountBalances,
  mergeBalanceWithCompletedTransfers,
  mergeBalanceWithTradeEstimates,
  normalizeDashboardTab,
  resolveDashboardWatchlistCurrentPrice,
  sortDashboardHoldings,
  toKrwAmount,
} from './dashboardModel.js'

describe('dashboardModel', () => {
  it('normalizes dashboard tab with fallback', () => {
    assert.equal(normalizeDashboardTab('assets'), 'assets')
    assert.equal(normalizeDashboardTab('unknown-tab'), 'dashboard')
    assert.equal(normalizeDashboardTab(null), 'dashboard')
  })

  it('converts currencies to KRW using the representative exchange rate', () => {
    assert.equal(toKrwAmount(10, 'USD', 1500), 15000)
    assert.equal(toKrwAmount(2, 'USDT', 1400), 2800)
    assert.equal(toKrwAmount(3000, 'KRW', 1500), 3000)
    assert.equal(toKrwAmount('bad-value', 'USD', 1500), 0)
  })

  it('formats USD and USDT unit prices up to 4 decimal places', () => {
    assert.equal(formatUnitCurrency(0.123456, 'USD', 'USD'), '$0.1235')
    assert.equal(formatUnitCurrency(1.23456, 'USDT', 'USD'), '$1.2346')
    assert.equal(formatUnitCurrency(325.64, 'USD', 'USD'), '$325.64')
  })

  it('formats KRW crypto unit prices under 1 won up to 4 decimal places', () => {
    assert.equal(formatUnitCurrency(0.123456, 'KRW', 'KRW'), '₩0.1235')
    assert.equal(formatUnitCurrency(1.23456, 'KRW', 'KRW'), '₩1.2')
  })

  it('calculates holding evaluation in native and KRW values', () => {
    const usHolding = {
      qty: 3,
      current_price: 10,
      currency: 'USD',
    }
    const krHolding = {
      qty: 2,
      current_price: 50000,
      currency: 'KRW',
    }

    assert.equal(getHoldingEvaluationNative(usHolding), 30)
    assert.equal(getHoldingEvaluationKrw(usHolding, 1500), 45000)
    assert.equal(getHoldingEvaluationNative(krHolding), 100000)
    assert.equal(getHoldingEvaluationKrw(krHolding, 1500), 100000)
  })

  it('merges account balances and filters mock accounts', () => {
    const items = [
      {
        exchange: 'TOSS',
        raw_exchange: 'TOSS',
        env: 'REAL',
        currency: 'KRW',
        total_evaluation: 100000,
        available_cash: 50000,
        holdings: [
          {
            symbol: '005930',
            name: '삼성전자',
            qty: 1,
            avg_price: 70000,
            current_price: 80000,
            profit: 10000,
            currency: 'KRW',
          },
        ],
      },
      {
        exchange: 'KIS',
        raw_exchange: 'KIS',
        env: 'MOCK',
        currency: 'KRW',
        total_evaluation: 90000,
        available_cash: 10000,
        holdings: [
          {
            symbol: '000660',
            name: 'SK하이닉스',
            qty: 1,
            avg_price: 80000,
            current_price: 90000,
            profit: 10000,
            currency: 'KRW',
          },
        ],
      },
    ]

    const withMock = mergeAccountBalances(items, true)
    const withoutMock = mergeAccountBalances(items, false)

    assert.equal(withMock.total_evaluation, 190000)
    assert.equal(withMock.available_cash, 60000)
    assert.equal(withMock.holdings.length, 2)
    assert.equal(withoutMock.total_evaluation, 100000)
    assert.equal(withoutMock.available_cash, 50000)
    assert.equal(withoutMock.holdings.length, 1)
  })

  it('adds estimated trade holdings without duplicating live holdings', () => {
    const mergedBalance = {
      holdings: [
        {
          symbol: 'BTC',
          raw_exchange: 'COINONE',
          exchange: 'COINONE',
          env: 'REAL',
          asset_type: 'CRYPTO',
        },
      ],
      sources: ['COINONE'],
    }
    const tradeRows = [
      {
        status: 'EXECUTED',
        exchange: 'BINANCE',
        asset_type: 'CRYPTO',
        symbol: 'ETH',
        side: 'BUY',
        price: 2000,
        volume: 0.5,
        currency: 'USD',
        broker_env: 'REAL',
      },
    ]

    const result = mergeBalanceWithTradeEstimates(mergedBalance, tradeRows, true)

    assert.equal(result.holdings.length, 2)
    assert.equal(result.holdings[1].symbol, 'ETH')
    assert.equal(result.holdings[1].source, 'DB_ESTIMATED')
  })

  it('delegates completed transfer cash adjustments', () => {
    const mergedBalance = {
      available_cash: 100000,
      available_cash_breakdown: { KRW: 100000 },
      available_cash_breakdown_entries: [],
      cash_breakdown_by_currency: { KRW: [], USD: [], USDT: [] },
    }
    const transferRows = [
      {
        status: 'COMPLETED',
        from_exchange: 'COINONE',
        to_exchange: 'BINANCE',
        currency: 'XRP',
        amount: 10,
        received_amount: 9,
        expected_receive_amount: 9,
      },
    ]

    const result = mergeBalanceWithCompletedTransfers(mergedBalance, transferRows)

    assert.ok(result)
    assert.equal(typeof result, 'object')
  })

  it('classifies dashboard watchlist metadata', () => {
    const stockItem = { id: 'AAPL', market: '해외 주식', account: 'TOSS' }
    const cryptoItem = { id: 'BTC', market: '코인', account: 'COINONE' }
    const binanceItem = { id: 'ETHUSDT', market: '코인', account: 'BINANCE' }

    assert.equal(getDashboardWatchlistAssetType(stockItem), 'STOCK')
    assert.equal(getDashboardWatchlistCurrency(stockItem), 'USD')
    assert.deepEqual(getDashboardWatchlistChartConfig(stockItem), { exchange: 'TOSS', brokerEnv: 'REAL', interval: '1d' })
    assert.equal(getDashboardWatchlistAssetType(cryptoItem), 'CRYPTO')
    assert.equal(getDashboardWatchlistCurrency(cryptoItem), 'KRW')
    assert.deepEqual(getDashboardWatchlistChartConfig(cryptoItem), { exchange: 'COINONE', brokerEnv: 'REAL', interval: '1h' })
    assert.equal(getDashboardWatchlistCurrency(binanceItem), 'USDT')
    assert.deepEqual(getDashboardWatchlistChartConfig(binanceItem), { exchange: 'BINANCE', brokerEnv: 'REAL', interval: '1h' })
  })

  it('uses matching holding current price before chart or saved watchlist prices', () => {
    const watchlistItem = {
      id: 'AAPL',
      currentPrice: 210,
      latestPrice: 205,
      assetType: 'STOCK',
      exchange: 'TOSS',
    }
    const holdings = [
      {
        symbol: 'AAPL',
        current_price: 325.64,
        asset_type: 'STOCK',
        exchange: 'TOSS',
      },
    ]

    assert.equal(resolveDashboardWatchlistCurrentPrice(watchlistItem, holdings), 325.64)
  })

  it('builds balance requests from registered key status', () => {
    const requests = buildBalanceRequests({
      TOSS: { registered: true, broker_env: 'REAL', accounts: [{ broker_env: 'REAL', toss_account_no: '123' }] },
      KIS: { registered: true, broker_env: 'MOCK' },
      COINONE: { registered: false },
      BINANCE: { registered: true, broker_env: 'REAL' },
    })

    assert.deepEqual(
      requests.map((request) => `${request.exchange}:${request.env}`),
      ['TOSS:REAL', 'KIS:MOCK', 'BINANCE:REAL', 'BINANCE_UM_FUTURES:REAL'],
    )
  })

  it('sorts dashboard holdings by numeric fields and preserves order without a key', () => {
    const holdings = [
      { symbol: 'A', profit: 1000, profit_rate: 2 },
      { symbol: 'B', profit: -500, profit_rate: -1 },
      { symbol: 'C', profit: 2500, profit_rate: 5 },
    ]

    assert.deepEqual(sortDashboardHoldings(holdings, { key: null }).map((item) => item.symbol), ['A', 'B', 'C'])
    assert.deepEqual(sortDashboardHoldings(holdings, { key: 'profit', direction: 'desc' }).map((item) => item.symbol), ['C', 'A', 'B'])
    assert.deepEqual(sortDashboardHoldings(holdings, { key: 'profit_rate', direction: 'asc' }).map((item) => item.symbol), ['B', 'A', 'C'])
    assert.deepEqual(sortDashboardHoldings(null, { key: 'profit' }), [])
  })
})
