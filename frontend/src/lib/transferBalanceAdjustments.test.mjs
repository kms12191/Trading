import assert from 'node:assert/strict'
import { describe, it } from 'node:test'

import {
  deductCoinoneTransfersFromEstimatedHoldings,
  getCoinoneTransferDeductionAmount,
  mergeCompletedTransfersIntoCash,
} from './transferBalanceAdjustments.js'

describe('transfer balance adjustments', () => {
  it('keeps Coinone live holdings because exchange balances already reflect withdrawals', () => {
    const balance = {
      holdings: [
        {
          symbol: 'XRP',
          qty: 4.6,
          avg_price: 700,
          current_price: 720,
          raw_exchange: 'COINONE',
          source: 'LIVE_BALANCE',
        },
      ],
    }
    const transfers = [
      {
        from_exchange: 'COINONE',
        to_exchange: 'BINANCE',
        currency: 'XRP',
        amount: 5,
        withdraw_fee: 0.4,
        status: 'COMPLETED',
      },
    ]

    const adjusted = deductCoinoneTransfersFromEstimatedHoldings(balance, transfers)

    assert.equal(adjusted.holdings.length, 1)
    assert.equal(adjusted.holdings[0].qty, 4.6)
  })

  it('deducts the Coinone withdrawal amount plus fee from estimated holdings', () => {
    const balance = {
      holdings: [
        {
          symbol: 'DOGE',
          qty: 50,
          avg_price: 110,
          current_price: 110,
          eval_amount: 5500,
          profit: 0,
          profit_rate: 0,
          raw_exchange: 'COINONE',
          source: 'DB_ESTIMATED',
        },
        {
          symbol: 'DOGE',
          qty: 30,
          raw_exchange: 'BINANCE',
        },
      ],
    }
    const transfers = [
      {
        from_exchange: 'COINONE',
        to_exchange: 'BINANCE',
        currency: 'DOGE',
        amount: 30,
        withdraw_fee: 20,
        status: 'COMPLETED',
      },
    ]

    const adjusted = deductCoinoneTransfersFromEstimatedHoldings(balance, transfers)

    assert.deepEqual(
      adjusted.holdings.map((holding) => `${holding.raw_exchange}:${holding.symbol}:${holding.qty}`),
      ['BINANCE:DOGE:30'],
    )
  })

  it('uses precheck withdrawal fee when older transfer rows have no top-level fee', () => {
    const deduction = getCoinoneTransferDeductionAmount({
      amount: 30,
      status: 'PENDING',
      precheck_payload: {
        withdrawal_fee: 20,
      },
    })

    assert.equal(deduction, 50)
  })

  it('deducts rows with localized exchange labels and top-level withdrawal fee', () => {
    const adjusted = deductCoinoneTransfersFromEstimatedHoldings(
      {
        holdings: [
          {
            symbol: 'DOGE',
            qty: 50,
            raw_exchange: 'COINONE',
            source: 'DB_ESTIMATED',
          },
        ],
      },
      [
        {
          from_exchange: 'COINONE 실거래',
          to_exchange: 'BINANCE 현물',
          currency: 'DOGE',
          amount: 30,
          withdrawal_fee: 20,
          status: 'WITHDRAWAL_REQUESTED',
        },
      ],
    )

    assert.deepEqual(adjusted.holdings, [])
  })

  it('does not deduct failed transfer rows', () => {
    const deduction = getCoinoneTransferDeductionAmount({
      amount: 30,
      withdraw_fee: 20,
      status: 'FAILED',
    })

    assert.equal(deduction, 0)
  })

  it('adds completed Binance deposits to cash without adding exchange valuation', () => {
    const adjusted = mergeCompletedTransfersIntoCash(
      {
        total_evaluation: 0,
        total_by_currency: { KRW: 0, USD: 0, USDT: 0 },
        total_breakdown_by_currency: { USDT: [] },
        cash_breakdown_by_currency: { USDT: [] },
        available_cash: 0,
        available_cash_breakdown: {},
        available_cash_breakdown_entries: [],
        cash_supported_sources: [],
        holdings: [],
        sources: [],
        exchange_rate: 1500,
      },
      [
        {
          id: 'transfer-1',
          from_exchange: 'COINONE',
          to_exchange: 'BINANCE',
          currency: 'USDT',
          status: 'COMPLETED',
          received_amount: 2.17,
        },
      ],
    )

    assert.equal(adjusted.total_evaluation, 0)
    assert.deepEqual(adjusted.total_breakdown_by_currency.USDT, [])
    assert.deepEqual(adjusted.total_by_currency, { KRW: 0, USD: 0, USDT: 0 })
    assert.deepEqual(adjusted.holdings, [])
    assert.equal(adjusted.available_cash, 3255)
    assert.deepEqual(adjusted.available_cash_breakdown, { USDT: 2.17 })
    assert.deepEqual(adjusted.cash_breakdown_by_currency.USDT, [
      { source: '바이낸스 입금확인', amount: 2.17 },
    ])
  })
})
