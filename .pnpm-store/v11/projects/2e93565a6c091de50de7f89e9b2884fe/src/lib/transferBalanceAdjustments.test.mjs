import assert from 'node:assert/strict'
import { describe, it } from 'node:test'

import {
  deductCoinoneTransfersFromEstimatedHoldings,
  getCoinoneTransferDeductionAmount,
} from './transferBalanceAdjustments.js'

describe('transfer balance adjustments', () => {
  it('deducts the Coinone withdrawal amount plus fee from live holdings', () => {
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
})
