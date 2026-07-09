const TRANSFER_NON_DEDUCTIBLE_STATUSES = new Set([
  'FAILED',
  'CANCELED',
  'CANCELLED',
  'REJECTED',
  'EXPIRED',
])

const toNumber = (value) => {
  const numericValue = Number(value)
  return Number.isFinite(numericValue) ? numericValue : 0
}

const isEstimatedHoldingSource = (holding = {}) => {
  const source = String(holding.source || '').toUpperCase()
  return source === 'DB_ESTIMATED' || source === 'TRADE_ESTIMATED' || source === 'ESTIMATED'
}

export const getTransferReceivedAmount = (row = {}) => {
  const receivedAmount = toNumber(row.received_amount)
  if (receivedAmount > 0) return receivedAmount
  const depositAmount = toNumber(row.binance_deposit_payload?.amount)
  if (depositAmount > 0) return depositAmount
  const expectedAmount = toNumber(row.expected_receive_amount)
  if (expectedAmount > 0) return expectedAmount
  return 0
}

export const getCoinoneTransferDeductionAmount = (row = {}) => {
  const status = String(row.status || '').toUpperCase()
  if (TRANSFER_NON_DEDUCTIBLE_STATUSES.has(status)) return 0

  const amount = toNumber(row.amount)
  const fee = toNumber(row.withdraw_fee ?? row.withdrawal_fee ?? row.precheck_payload?.withdrawal_fee)
  return amount + fee
}

export const deductCoinoneTransfersFromEstimatedHoldings = (mergedBalance, transferRows = []) => {
  const holdings = Array.isArray(mergedBalance?.holdings) ? mergedBalance.holdings : []
  const deductions = new Map()

  ;(transferRows || []).forEach((row) => {
    const fromExchange = String(row.from_exchange || '').toUpperCase()
    const toExchange = String(row.to_exchange || '').toUpperCase()
    const currency = String(row.currency || '').trim().toUpperCase()
    const amount = getCoinoneTransferDeductionAmount(row)
    if (!fromExchange.includes('COINONE') || !toExchange.includes('BINANCE') || !currency || amount <= 0) return
    deductions.set(currency, (deductions.get(currency) || 0) + amount)
  })

  if (deductions.size === 0) return mergedBalance

  const adjustedHoldings = holdings
    .map((holding) => {
      const rawExchange = String(holding.raw_exchange || holding.exchange || holding.account_type || '').toUpperCase()
      const symbol = String(holding.symbol || holding.ticker || holding.id || '').trim().toUpperCase()
      const deductionAmount = deductions.get(symbol) || 0

      if (rawExchange !== 'COINONE' || deductionAmount <= 0 || !isEstimatedHoldingSource(holding)) {
        return holding
      }

      const nextQty = Math.max(0, toNumber(holding.qty) - deductionAmount)
      const avgPrice = toNumber(holding.avg_price)
      const currentPrice = toNumber(holding.current_price)
      return {
        ...holding,
        qty: nextQty,
        eval_amount: currentPrice > 0 ? currentPrice * nextQty : toNumber(holding.eval_amount),
        profit: avgPrice > 0 && currentPrice > 0 ? (currentPrice - avgPrice) * nextQty : toNumber(holding.profit),
        profit_rate: avgPrice > 0 && currentPrice > 0 ? ((currentPrice - avgPrice) / avgPrice) * 100 : toNumber(holding.profit_rate),
        transfer_deducted_qty: deductionAmount,
      }
    })
    .filter((holding) => toNumber(holding.qty) > 0)

  return {
    ...mergedBalance,
    holdings: adjustedHoldings,
  }
}

export const mergeCompletedTransfersIntoCash = (mergedBalance, transferRows = []) => {
  const exchangeRate = toNumber(mergedBalance?.exchange_rate) || 1500
  const completedDeposits = (transferRows || [])
    .filter((row) => String(row.status || '').toUpperCase() === 'COMPLETED')
    .map((row) => {
      const currency = String(row.currency || '').trim().toUpperCase()
      const amount = getTransferReceivedAmount(row)
      if (!currency || amount <= 0) return null
      return { currency, amount }
    })
    .filter(Boolean)

  if (completedDeposits.length === 0) return mergedBalance

  const availableCashBreakdown = { ...(mergedBalance?.available_cash_breakdown || {}) }
  const cashBreakdownByCurrency = { ...(mergedBalance?.cash_breakdown_by_currency || {}) }
  const availableCashBreakdownEntries = Array.isArray(mergedBalance?.available_cash_breakdown_entries)
    ? [...mergedBalance.available_cash_breakdown_entries]
    : []
  let availableCash = toNumber(mergedBalance?.available_cash)

  completedDeposits.forEach((deposit) => {
    const sourceLabel = '바이낸스 입금확인'
    availableCashBreakdown[deposit.currency] = toNumber(availableCashBreakdown[deposit.currency]) + deposit.amount
    availableCash += deposit.currency === 'USD' || deposit.currency === 'USDT'
      ? deposit.amount * exchangeRate
      : deposit.amount

    const cashEntries = Array.isArray(cashBreakdownByCurrency[deposit.currency])
      ? [...cashBreakdownByCurrency[deposit.currency]]
      : []
    cashEntries.push({ source: sourceLabel, amount: deposit.amount })
    cashBreakdownByCurrency[deposit.currency] = cashEntries
    availableCashBreakdownEntries.push({
      currency: deposit.currency,
      amount: deposit.amount,
      sourceLabel,
      exchange: 'BINANCE',
      env: 'REAL',
    })
  })

  return {
    ...mergedBalance,
    available_cash: availableCash,
    available_cash_breakdown: availableCashBreakdown,
    cash_breakdown_by_currency: cashBreakdownByCurrency,
    available_cash_breakdown_entries: availableCashBreakdownEntries,
    cash_supported_sources: [...new Set([...(mergedBalance?.cash_supported_sources || []), 'BINANCE_TRANSFER'])],
  }
}
