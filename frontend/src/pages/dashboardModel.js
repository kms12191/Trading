import { mergeCompletedTransfersIntoCash } from '../lib/transferBalanceAdjustments.js'
import { DASHBOARD_TAB_KEYS, DEFAULT_DASHBOARD_TAB } from '../dashboardConstants.js'

export const BALANCE_EXCHANGE_ORDER = ['TOSS', 'KIS', 'COINONE', 'BINANCE', 'BINANCE_UM_FUTURES']
export const TRADE_PROPOSAL_HOLDING_FIELDS = 'id,exchange,asset_type,ticker,symbol,side,price,volume,order_amount,market_country,currency,status,broker_env,created_at'
export const TRANSFER_PROPOSAL_FIELDS = 'id,from_exchange,to_exchange,currency,amount,status,received_amount,expected_receive_amount,withdraw_fee,fee_currency,precheck_payload,binance_deposit_payload,created_at,submitted_at,completed_at,updated_at'
export const DASHBOARD_TAB_SET = new Set(DASHBOARD_TAB_KEYS)

export const normalizeDashboardTab = (tab) => (
  DASHBOARD_TAB_SET.has(tab) ? tab : DEFAULT_DASHBOARD_TAB
)

export const toNumber = (value) => {
  const numericValue = Number(value)
  return Number.isFinite(numericValue) ? numericValue : 0
}

export const sortDashboardHoldings = (holdingsList, holdingsSort = {}) => {
  if (!Array.isArray(holdingsList)) return []
  if (!holdingsSort?.key) return holdingsList

  return [...holdingsList].sort((a, b) => {
    const aVal = toNumber(a?.[holdingsSort.key])
    const bVal = toNumber(b?.[holdingsSort.key])
    return holdingsSort.direction === 'asc' ? aVal - bVal : bVal - aVal
  })
}

export const formatKrw = (value) => `₩${Math.round(toNumber(value)).toLocaleString()}`

export const formatCurrency = (value, currency, displayCurrency = 'KRW', exchangeRate = 1500) => {
  const numeric = toNumber(value)
  const rate = toNumber(exchangeRate) || 1500

  if (displayCurrency === 'KRW') {
    if (currency === 'USD' || currency === 'USDT') {
      return `₩${Math.round(numeric * rate).toLocaleString()}`
    }
    return `₩${Math.round(numeric).toLocaleString()}`
  }

  if (displayCurrency === 'USD') {
    if (currency === 'KRW') {
      return `$${(numeric / rate).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
    }
    return `$${numeric.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
  }

  if (currency === 'USD' || currency === 'USDT') {
    return `$${numeric.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
  }
  return `₩${Math.round(numeric).toLocaleString()}`
}

export const formatUnitCurrency = (value, currency, displayCurrency = 'KRW', exchangeRate = 1500) => {
  const numeric = toNumber(value)
  const rate = toNumber(exchangeRate) || 1500
  const getMaximumFractionDigits = (displayValue, unitCurrency = '') => {
    if (unitCurrency === 'USD' || unitCurrency === 'USDT') return 4
    const absoluteValue = Math.abs(toNumber(displayValue))
    if (unitCurrency === 'KRW' && absoluteValue > 0 && absoluteValue < 1) return 4
    return absoluteValue > 0 && absoluteValue < 0.1 ? 3 : 1
  }

  if (displayCurrency === 'KRW') {
    const displayValue = (currency === 'USD' || currency === 'USDT') ? numeric * rate : numeric
    return `₩${displayValue.toLocaleString(undefined, { minimumFractionDigits: 0, maximumFractionDigits: getMaximumFractionDigits(displayValue, 'KRW') })}`
  }

  if (displayCurrency === 'USD') {
    const displayValue = currency === 'KRW' ? numeric / rate : numeric
    return `$${displayValue.toLocaleString(undefined, { minimumFractionDigits: 0, maximumFractionDigits: getMaximumFractionDigits(displayValue, 'USD') })}`
  }

  if (currency === 'USD' || currency === 'USDT') {
    return `$${numeric.toLocaleString(undefined, { minimumFractionDigits: 0, maximumFractionDigits: getMaximumFractionDigits(numeric, currency) })}`
  }
  return `₩${numeric.toLocaleString(undefined, { minimumFractionDigits: 0, maximumFractionDigits: getMaximumFractionDigits(numeric, 'KRW') })}`
}

export const formatNullableCurrency = (value, currency, displayCurrency = 'KRW', exchangeRate = 1500) => {
  if (value === null || value === undefined || value === '') return '-'
  return formatCurrency(value, currency, displayCurrency, exchangeRate)
}

export const DASHBOARD_SUMMARY_CURRENCIES = ['KRW', 'USD', 'USDT']

export const normalizeSummaryCurrency = (currency, source = '') => {
  const normalizedCurrency = String(currency || '').toUpperCase()
  const normalizedSource = String(source || '').toUpperCase()

  if (normalizedSource.includes('BINANCE')) return 'USDT'
  if (DASHBOARD_SUMMARY_CURRENCIES.includes(normalizedCurrency)) return normalizedCurrency
  return 'KRW'
}

export const formatSummaryCurrency = (value, currency) => {
  const numeric = toNumber(value)
  if (currency === 'KRW') {
    return `KRW ${Math.round(numeric).toLocaleString()}`
  }
  if (currency === 'USDT') {
    return `USDT ${numeric.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
  }
  return `USD ${numeric.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
}

export const getSummarySourceLabel = (source = '') => {
  const normalized = String(source || '').toUpperCase()
  if (normalized.includes('BINANCE_UM_FUTURES')) return '바이낸스 선물'
  if (normalized.includes('BINANCE')) return '바이낸스 현물'
  if (normalized.includes('COINONE')) return '코인원'
  if (normalized.includes('TOSS')) return '토스'
  if (normalized.includes('KIS')) return '한투'
  return source || '-'
}

export const createCurrencySourceMap = () => (
  Object.fromEntries(DASHBOARD_SUMMARY_CURRENCIES.map((currency) => [currency, {}]))
)

export const addCurrencySourceAmount = (sourceMap, currency, source, amount) => {
  const normalizedCurrency = DASHBOARD_SUMMARY_CURRENCIES.includes(currency) ? currency : 'KRW'
  const numeric = toNumber(amount)

  const label = source || '-'
  const current = sourceMap[normalizedCurrency][label] || { source: label, amount: 0 }
  current.amount += numeric
  sourceMap[normalizedCurrency][label] = current
}

export const flattenCurrencySourceMap = (sourceMap) => (
  Object.fromEntries(
    DASHBOARD_SUMMARY_CURRENCIES.map((currency) => [
      currency,
      Object.values(sourceMap[currency] || {}).sort((a, b) => {
        if (currency === 'KRW') {
          const order = ['토스', '한투', '코인원']
          const aIndex = order.indexOf(a.source)
          const bIndex = order.indexOf(b.source)
          if (aIndex !== bIndex) return (aIndex === -1 ? order.length : aIndex) - (bIndex === -1 ? order.length : bIndex)
        }
        return b.amount - a.amount
      }),
    ]),
  )
)

export const SUMMARY_DETAIL_SOURCE_ORDER = {
  KRW: ['토스', '한투', '코인원'],
  USD: ['토스'],
  USDT: ['바이낸스 현물', '바이낸스 선물'],
}

export const fillSummaryDetailEntries = (entries = [], currency = 'KRW') => {
  const order = SUMMARY_DETAIL_SOURCE_ORDER[currency] || []
  const bySource = new Map(entries.map((entry) => [entry.source, entry]))

  order.forEach((source) => {
    if (!bySource.has(source)) {
      bySource.set(source, { source, amount: 0 })
    }
  })

  return Array.from(bySource.values()).sort((a, b) => {
    const aIndex = order.indexOf(a.source)
    const bIndex = order.indexOf(b.source)
    if (aIndex !== bIndex) return (aIndex === -1 ? order.length : aIndex) - (bIndex === -1 ? order.length : bIndex)
    return b.amount - a.amount
  })
}

export const formatNativeCurrency = (value, currency) => {
  const numeric = Number(value)
  if (!Number.isFinite(numeric)) return '-'
  if (currency === 'USD' || currency === 'USDT') {
    return `$${numeric.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
  }
  if (currency === 'KRW') {
    return `₩${Math.round(numeric).toLocaleString()}`
  }
  return `${numeric.toLocaleString()} ${currency}`
}

export const getAccountDisplayLabel = (item = {}) => {
  const exchange = String(item.raw_exchange || item.exchange || '-').toUpperCase()
  const env = String(item.env || '').toUpperCase()
  if (!env) return exchange
  return `${exchange} ${env === 'MOCK' ? '모의' : '실거래'}`
}

export const getAccountTone = (exchange = '') => {
  const normalized = String(exchange || '').toUpperCase()
  if (normalized.includes('TOSS')) return 'border-cyan-500/30 bg-cyan-950/20'
  if (normalized.includes('KIS')) return 'border-blue-500/30 bg-blue-950/20'
  if (normalized.includes('COINONE')) return 'border-amber-500/30 bg-amber-950/20'
  if (normalized.includes('BINANCE_UM_FUTURES')) return 'border-cyan-500/30 bg-cyan-950/20'
  if (normalized.includes('BINANCE')) return 'border-emerald-500/30 bg-emerald-950/20'
  return 'border-slate-700/80 bg-slate-900/70'
}

export const buildCashEntriesFromItem = (item = {}) => {
  const sourceLabel = getAccountDisplayLabel(item)
  const cashCurrency = String(item.available_cash_currency || item.currency || 'KRW').toUpperCase()
  const rawComponents = Array.isArray(item.available_cash_details?.components) && item.available_cash_details.components.length > 0
    ? item.available_cash_details.components
    : (
      item.available_cash !== null && item.available_cash !== undefined && item.available_cash !== '' && Number.isFinite(Number(item.available_cash))
        ? [{ currency: cashCurrency, cash_buying_power: Number(item.available_cash) }]
        : []
    )

  const entries = rawComponents
    .map((component) => {
      const currency = String(component?.currency || cashCurrency).toUpperCase()
      const amount = Number(
        component?.cash_buying_power
        ?? component?.cashBuyingPower
        ?? component?.buying_power
        ?? component?.buyingPower
        ?? component?.amount
        ?? component?.available
        ?? component?.availableCash
        ?? component?.free
        ?? component?.balance
      )
      if (!currency || !Number.isFinite(amount)) return null
      return {
        currency,
        amount,
        sourceLabel,
        exchange: String(item.raw_exchange || item.exchange || '').toUpperCase(),
        env: String(item.env || '').toUpperCase(),
      }
    })
    .filter(Boolean)

  if (
    entries.length === 0
    && item.available_cash !== null
    && item.available_cash !== undefined
    && item.available_cash !== ''
    && Number.isFinite(Number(item.available_cash))
  ) {
    return [{
      currency: cashCurrency,
      amount: Number(item.available_cash),
      sourceLabel,
      exchange: String(item.raw_exchange || item.exchange || '').toUpperCase(),
      env: String(item.env || '').toUpperCase(),
    }]
  }

  return entries
}

export const parsePriceNumber = (value) => {
  if (typeof value === 'number') return Number.isFinite(value) ? value : null
  const numeric = Number(String(value ?? '').replace(/,/g, '').replace(/[^0-9.-]/g, ''))
  return Number.isFinite(numeric) ? numeric : null
}

export const getWatchlistCurrentPrice = (item = {}) => {
  const payload = item.sourcePayload || {}
  return parsePriceNumber(
    item.currentPrice
    ?? payload.current_price
    ?? payload.currentPrice
    ?? payload.live_price
    ?? payload.livePrice
    ?? payload.price,
  )
}

const normalizeWatchlistSymbol = (value = '') => (
  String(value || '').trim().toUpperCase().replace(/(?:_?KRW|USDT)$/i, '')
)

export const resolveDashboardWatchlistCurrentPrice = (item = {}, holdings = []) => {
  const watchSymbol = normalizeWatchlistSymbol(item.id || item.symbol || item.ticker)
  const watchAssetType = getDashboardWatchlistAssetType(item)
  const watchExchange = String(item.exchange || item.account || item.sourcePayload?.exchange || '').toUpperCase()

  if (watchSymbol && Array.isArray(holdings)) {
    const matchingHoldings = holdings.filter((holding) => {
      const holdingSymbol = normalizeWatchlistSymbol(holding.symbol || holding.ticker || holding.id)
      if (holdingSymbol !== watchSymbol) return false

      const holdingAssetType = String(
        holding.asset_type
        || (['COINONE', 'BINANCE', 'BINANCE_UM_FUTURES'].includes(String(holding.exchange || '').toUpperCase()) ? 'CRYPTO' : 'STOCK'),
      ).toUpperCase()
      return holdingAssetType === watchAssetType
    })

    const exactExchangeHolding = matchingHoldings.find((holding) => {
      const holdingExchange = String(holding.raw_exchange || holding.exchange || holding.account_type || '').toUpperCase()
      return watchExchange && holdingExchange.includes(watchExchange)
    })
    const holdingPrice = parsePriceNumber((exactExchangeHolding || matchingHoldings[0])?.current_price)
    if (Number.isFinite(holdingPrice) && holdingPrice > 0) return holdingPrice
  }

  return getWatchlistCurrentPrice(item)
}

export const getDashboardWatchlistAssetType = (item = {}) => {
  const assetType = String(item.assetType || item.asset_type || '').toUpperCase()
  const market = String(item.market || '').toUpperCase()
  const account = String(item.account || item.exchange || '').toUpperCase()
  return assetType === 'CRYPTO' || /COIN|CRYPTO|BINANCE|COINONE|BTC|ETH|USDT/.test(`${market} ${account}`) ? 'CRYPTO' : 'STOCK'
}

export const getDashboardWatchlistCurrency = (item = {}) => {
  const sourcePayload = item.sourcePayload || {}
  const currency = String(item.currency || sourcePayload.currency || '').toUpperCase()
  if (currency) return currency

  const assetType = getDashboardWatchlistAssetType(item)
  if (assetType === 'CRYPTO') {
    const exchange = String(item.exchange || item.account || sourcePayload.exchange || '').toUpperCase()
    return exchange.includes('BINANCE') ? 'USDT' : 'KRW'
  }

  const marketCountry = String(item.marketCountry || item.market_country || sourcePayload.market_country || '').toUpperCase()
  const market = String(item.market || sourcePayload.market || '').toUpperCase()
  const symbol = String(item.id || item.symbol || sourcePayload.symbol || '').toUpperCase()
  if (marketCountry === 'US' || market.includes('해외') || (/[A-Z]/.test(symbol) && !/^\d{6}$/.test(symbol))) {
    return 'USD'
  }
  return 'KRW'
}

export const getDashboardWatchlistChartConfig = (item = {}) => {
  const assetType = getDashboardWatchlistAssetType(item)
  const sourcePayload = item.sourcePayload || {}
  const exchange = String(
    item.exchange
    || item.account
    || sourcePayload.exchange
    || (assetType === 'CRYPTO' ? 'COINONE' : 'TOSS'),
  ).toUpperCase()
  const brokerEnv = String(
    sourcePayload.broker_env
    || sourcePayload.env
    || (exchange === 'KIS' ? 'REAL' : 'REAL'),
  ).toUpperCase()

  return {
    exchange,
    brokerEnv,
    interval: assetType === 'CRYPTO' ? '1h' : '1d',
  }
}

export const formatSignedRate = (value) => {
  const numericValue = toNumber(value)
  return `${numericValue >= 0 ? '+' : ''}${numericValue.toFixed(2)}%`
}

export const formatAllocationPercent = (item = {}) => {
  const rawPercent = Number(item.rawPercent ?? item.value)
  if (rawPercent > 0 && rawPercent < 1) return '1% 미만'
  if (rawPercent <= 0) return '0%'
  return `${rawPercent.toFixed(1)}%`
}

export const getHoldingMarketType = (holding = {}) => {
  const symbol = String(holding.symbol || holding.ticker || holding.id || '').toUpperCase()
  const exchange = String(holding.exchange || holding.raw_exchange || '').toUpperCase()
  const accountType = String(holding.account || holding.account_type || '').toUpperCase()
  const assetType = String(holding.asset_type || '').toUpperCase()
  const market = String(holding.market || holding.market_country || '').toUpperCase()
  const currency = String(holding.currency || '').toUpperCase()
  const combined = `${symbol} ${exchange} ${accountType} ${assetType} ${market} ${currency}`

  if (/CRYPTO|COIN|COINONE|BINANCE|BTC|ETH|XRP|SOL|USDT|코인/.test(combined)) {
    return 'coin'
  }

  if (/OVERSEAS|FOREIGN|GLOBAL|NASDAQ|NYSE|AMEX|US|USD|해외/.test(combined)) {
    return 'overseas'
  }

  if (/DOMESTIC|KR|KRW|KOSPI|KOSDAQ|국내/.test(combined) || /^[0-9a-zA-Z]{6,7}$/.test(symbol)) {
    return 'domestic'
  }

  return /[A-Z]/.test(symbol) && !/^[0-9a-zA-Z]{6,7}$/.test(symbol) ? 'overseas' : 'domestic'
}

export const getHoldingEvaluationKrw = (holding = {}, exchangeRate = 1500) => {
  const currency = String(holding.currency || '').toUpperCase()
  const rate = toNumber(exchangeRate) || 1500
  const rawValue = toNumber(holding.eval_amount) > 0
    ? toNumber(holding.eval_amount)
    : toNumber(holding.current_price) * Math.abs(toNumber(holding.qty))

  return currency === 'USD' || currency === 'USDT' ? rawValue * rate : rawValue
}

export const getHoldingEvaluationNative = (holding = {}) => {
  const directValue = toNumber(holding.eval_amount)
  if (directValue > 0) return directValue
  return toNumber(holding.current_price) * Math.abs(toNumber(holding.qty))
}

export const getHoldingsTotalNative = (holdings = []) => (
  holdings.reduce((sum, holding) => sum + getHoldingEvaluationNative(holding), 0)
)

export const getHoldingProfitBasis = (holding = {}) => {
  const qty = Math.abs(toNumber(holding.qty))
  const avgPrice = toNumber(holding.avg_price)
  const currentPrice = toNumber(holding.current_price)
  const profit = toNumber(holding.profit)
  const invested = avgPrice > 0
    ? avgPrice * qty
    : Math.max(0, currentPrice * qty - profit)

  return { profit, invested }
}

export const getAccountExchangeCode = (account = {}) => {
  const exchangeText = String(account.raw_exchange || account.exchange || '').toUpperCase()
  if (exchangeText.includes('BINANCE_UM_FUTURES')) return 'BINANCE_UM_FUTURES'
  if (exchangeText.includes('BINANCE')) return 'BINANCE'
  if (exchangeText.includes('COINONE')) return 'COINONE'
  if (exchangeText.includes('TOSS')) return 'TOSS'
  if (exchangeText.includes('KIS')) return 'KIS'
  return exchangeText
}

export const isCryptoAccount = (account = {}) => ['COINONE', 'BINANCE', 'BINANCE_UM_FUTURES'].includes(getAccountExchangeCode(account))

export const toKrwAmount = (value, currency = 'KRW', exchangeRate = 1500) => {
  const numeric = toNumber(value)
  const rate = toNumber(exchangeRate) || 1500
  const normalizedCurrency = String(currency || 'KRW').toUpperCase()
  return normalizedCurrency === 'USD' || normalizedCurrency === 'USDT' ? numeric * rate : numeric
}

export const toPositiveKrwAmount = (value, currency = 'KRW', exchangeRate = 1500) => Math.max(0, toKrwAmount(value, currency, exchangeRate))

export const getAccountCashKrw = (account = {}, exchangeRate = 1500) => {
  const cashEntries = buildCashEntriesFromItem(account)
  if (cashEntries.length > 0) {
    return cashEntries.reduce((sum, entry) => sum + toPositiveKrwAmount(entry.amount, entry.currency, exchangeRate), 0)
  }

  if (account.available_cash === null || account.available_cash === undefined || account.available_cash === '') {
    return 0
  }

  return toPositiveKrwAmount(
    account.available_cash,
    account.available_cash_currency || account.currency || 'KRW',
    exchangeRate,
  )
}

export const getPortfolioProfitRate = (accountBalance) => {
  if (!accountBalance) return 0

  const directRate = accountBalance.portfolio_profit_rate
    ?? accountBalance.total_profit_rate
    ?? accountBalance.profit_rate

  if (directRate !== undefined && directRate !== null) {
    return toNumber(directRate)
  }

  const holdings = Array.isArray(accountBalance.holdings) ? accountBalance.holdings : []
  if (holdings.length === 0) return 0

  const totalProfit = holdings.reduce((sum, item) => sum + toNumber(item.profit), 0)
  const investedAmount = holdings.reduce((sum, item) => {
    const qty = toNumber(item.qty)
    const avgPrice = toNumber(item.avg_price)
    const currentPrice = toNumber(item.current_price)
    const profit = toNumber(item.profit)
    const estimatedCost = avgPrice > 0 ? avgPrice * qty : Math.max(0, currentPrice * qty - profit)
    return sum + estimatedCost
  }, 0)

  if (investedAmount <= 0) return 0
  return (totalProfit / investedAmount) * 100
}

export const mergeAccountBalances = (items, showMockAssets = true) => {
  const validItems = items.filter(Boolean)
  const filteredItems = validItems.filter((item) => showMockAssets || item.env !== 'MOCK')
  const representativeRate = filteredItems.find((item) => item.exchange_rate)?.exchange_rate || 1500

  let totalEvaluationKrw = 0
  let availableCashKrw = 0
  let hasCashValue = false
  const cashAvailableSources = []
  const cashUnavailableSources = []
  const cashBreakdown = {}
  const cashBreakdownEntries = []
  const totalByCurrency = { KRW: 0, USD: 0, USDT: 0 }
  const profitByCurrency = {
    KRW: { profit: 0, invested: 0 },
    USD: { profit: 0, invested: 0 },
    USDT: { profit: 0, invested: 0 },
  }
  const totalBreakdownByCurrency = createCurrencySourceMap()
  const cashBreakdownByCurrency = createCurrencySourceMap()

  const addHoldingProfit = (currency, holding) => {
    const normalizedCurrency = DASHBOARD_SUMMARY_CURRENCIES.includes(currency) ? currency : 'KRW'
    const basis = getHoldingProfitBasis(holding)
    profitByCurrency[normalizedCurrency].profit += basis.profit
    profitByCurrency[normalizedCurrency].invested += basis.invested
  }

  const holdings = filteredItems.flatMap((item) => {
    const exchange = item.exchange
    const rawExchange = item.raw_exchange || item.exchange
    const sourceLabel = getSummarySourceLabel(rawExchange || exchange)
    const rate = toNumber(item.exchange_rate) || representativeRate
    const itemCurrency = item.currency || 'KRW'
    const cashCurrency = item.available_cash_currency || itemCurrency
    const summaryCurrency = normalizeSummaryCurrency(itemCurrency, rawExchange)
    const itemHoldings = Array.isArray(item.holdings) ? item.holdings : []
    const holdingCurrencies = new Set(
      itemHoldings
        .map((holding) => normalizeSummaryCurrency(holding.currency || itemCurrency, rawExchange))
        .filter(Boolean),
    )
    const shouldSplitByHoldings = itemHoldings.length > 0 && (
      String(rawExchange || '').toUpperCase().includes('TOSS') || holdingCurrencies.size > 1
    )

    let itemEval = toNumber(item.total_evaluation)
    if (shouldSplitByHoldings) {
      itemHoldings.forEach((holding) => {
        const holdingCurrency = normalizeSummaryCurrency(holding.currency || itemCurrency, rawExchange)
        const holdingValue = getHoldingEvaluationNative(holding)
        totalByCurrency[holdingCurrency] += holdingValue
        addCurrencySourceAmount(totalBreakdownByCurrency, holdingCurrency, sourceLabel, holdingValue)
        addHoldingProfit(holdingCurrency, holding)
      })
      if (itemHoldings.length === 0) {
        addCurrencySourceAmount(totalBreakdownByCurrency, summaryCurrency, sourceLabel, 0)
      }
    } else {
      const holdingsValue = getHoldingsTotalNative(itemHoldings)
      totalByCurrency[summaryCurrency] += holdingsValue
      addCurrencySourceAmount(totalBreakdownByCurrency, summaryCurrency, sourceLabel, holdingsValue)
      itemHoldings.forEach((holding) => addHoldingProfit(summaryCurrency, holding))
    }

    if (itemCurrency === 'USD' || itemCurrency === 'USDT') {
      itemEval = itemEval * rate
    }

    totalEvaluationKrw += itemEval

    if (item.available_cash !== null && item.available_cash !== undefined && item.available_cash !== '' && Number.isFinite(Number(item.available_cash))) {
      let itemCash = Number(item.available_cash)
      if (cashCurrency === 'USD' || cashCurrency === 'USDT') {
        itemCash = itemCash * rate
      }
      availableCashKrw += itemCash
      hasCashValue = true
      cashAvailableSources.push(exchange)
    } else {
      cashUnavailableSources.push(exchange)
    }

    const cashEntries = buildCashEntriesFromItem(item)
    for (const entry of cashEntries) {
      cashBreakdown[entry.currency] = (cashBreakdown[entry.currency] || 0) + entry.amount
      cashBreakdownEntries.push(entry)
      const entryCurrency = normalizeSummaryCurrency(entry.currency, rawExchange)
      totalByCurrency[entryCurrency] += entry.amount
      addCurrencySourceAmount(cashBreakdownByCurrency, entryCurrency, sourceLabel, entry.amount)
    }

    return (item.holdings || []).map((holding) => ({
      ...holding,
      exchange: holding.exchange || exchange,
      raw_exchange: holding.raw_exchange || item.raw_exchange || exchange,
      account_type: holding.account_type || exchange,
      env: item.env || 'REAL',
    }))
  })

  return {
    total_evaluation: totalEvaluationKrw,
    total_by_currency: totalByCurrency,
    profit_rate_by_currency: Object.fromEntries(
      DASHBOARD_SUMMARY_CURRENCIES.map((currency) => {
        const item = profitByCurrency[currency]
        return [currency, item.invested > 0 ? (item.profit / item.invested) * 100 : 0]
      }),
    ),
    total_breakdown_by_currency: flattenCurrencySourceMap(totalBreakdownByCurrency),
    cash_breakdown_by_currency: flattenCurrencySourceMap(cashBreakdownByCurrency),
    available_cash: hasCashValue ? availableCashKrw : null,
    currency: 'KRW', // 통합 잔고는 항상 KRW 기준
    exchange_rate: representativeRate,
    holdings,
    sources: filteredItems.map((item) => item.exchange),
    cash_supported_sources: [...new Set(cashAvailableSources)],
    cash_unavailable_sources: [...new Set(cashUnavailableSources)],
    available_cash_breakdown: cashBreakdown,
    available_cash_breakdown_entries: cashBreakdownEntries,
  }
}

export const getHoldingIdentity = (holding = {}) => {
  const symbol = String(holding.symbol || holding.ticker || holding.id || '').trim().toUpperCase()
  const exchangeText = String(holding.raw_exchange || holding.exchange || holding.account_type || '').toUpperCase()
  const rawExchange = normalizeExchangeText(exchangeText)
  const env = String(holding.env || (exchangeText.includes('모의') ? 'MOCK' : exchangeText.includes('실전') ? 'REAL' : 'REAL')).toUpperCase()
  const assetType = String(holding.asset_type || (['COINONE', 'BINANCE', 'BINANCE_UM_FUTURES'].includes(rawExchange) ? 'CRYPTO' : 'STOCK')).toUpperCase()
  return symbol ? `${assetType}:${rawExchange}:${env}:${symbol}` : ''
}

export const normalizeExchangeText = (exchangeText = '') => {
  const normalized = String(exchangeText || '').toUpperCase()
  return normalized.includes('KIS') ? 'KIS'
    : normalized.includes('TOSS') ? 'TOSS'
      : normalized.includes('COINONE') ? 'COINONE'
        : normalized.includes('BINANCE_UM_FUTURES') ? 'BINANCE_UM_FUTURES'
          : normalized.includes('BINANCE') ? 'BINANCE'
            : normalized
}

export const getHoldingAccountScope = (holding = {}) => {
  const exchangeText = String(holding.raw_exchange || holding.exchange || holding.account_type || '').toUpperCase()
  const exchange = normalizeExchangeText(exchangeText)
  const env = String(holding.env || (exchangeText.includes('모의') ? 'MOCK' : 'REAL')).toUpperCase()
  return exchange ? `${exchange}:${env}` : ''
}

export const buildLiveAccountScopes = (liveHoldings = [], liveSources = []) => {
  const scopes = new Set(liveHoldings.map(getHoldingAccountScope).filter(Boolean))
  liveSources.forEach((source) => {
    const exchange = normalizeExchangeText(source)
    if (exchange) scopes.add(`${exchange}:REAL`)
  })
  return scopes
}

export const buildEstimatedHoldingsFromTrades = (tradeRows = [], liveHoldings = [], showMockAssets = true, liveSources = []) => {
  const liveKeys = new Set(liveHoldings.map(getHoldingIdentity).filter(Boolean))
  const liveAccountScopes = buildLiveAccountScopes(liveHoldings, liveSources)
  const hasAuthoritativeLiveAccount = (item = {}) => {
    const exchange = String(item.raw_exchange || item.exchange || '').toUpperCase()
    if (!['COINONE', 'BINANCE', 'BINANCE_UM_FUTURES'].includes(exchange)) return false
    const env = String(item.env || 'REAL').toUpperCase()
    return liveAccountScopes.has(`${exchange}:${env}`)
  }
  if (tradeRows.some((row) => row.source === 'DB_ESTIMATED')) {
    return tradeRows.filter((item) => item.qty > 0 && (showMockAssets || item.env !== 'MOCK') && !liveKeys.has(getHoldingIdentity(item)) && !hasAuthoritativeLiveAccount(item))
  }
  const grouped = new Map()

  tradeRows.forEach((row) => {
    const status = String(row.status || '').toUpperCase()
    const env = String(row.broker_env || 'REAL').toUpperCase()
    if (status !== 'EXECUTED') return
    if (!showMockAssets && env === 'MOCK') return

    const symbol = String(row.symbol || row.ticker || '').trim().toUpperCase()
    if (!symbol) return

    const exchange = String(row.exchange || '').toUpperCase()
    const assetType = String(row.asset_type || (['COINONE', 'BINANCE', 'BINANCE_UM_FUTURES'].includes(exchange) ? 'CRYPTO' : 'STOCK')).toUpperCase()
    const key = `${assetType}:${exchange}:${env}:${symbol}`
    const side = String(row.side || '').toUpperCase()
    const price = toNumber(row.price)
    const volume = toNumber(row.volume) || (price > 0 ? toNumber(row.order_amount) / price : 0)
    if (volume <= 0) return

    const current = grouped.get(key) || {
      symbol,
      name: row.display_name || symbol,
      asset_type: assetType,
      exchange: exchange === 'KIS' ? `KIS ${env === 'MOCK' ? '모의' : '실전'}` : (exchange || '-'),
      raw_exchange: exchange || '-',
      account_type: exchange ? `${exchange} ${env === 'MOCK' ? '모의' : '실전'}` : '-',
      env,
      currency: row.currency || (['BINANCE', 'BINANCE_UM_FUTURES'].includes(exchange) ? 'USD' : 'KRW'),
      qty: 0,
      buyQty: 0,
      buyAmount: 0,
      lastPrice: 0,
    }

    if (side === 'SELL') {
      current.qty -= volume
    } else {
      current.qty += volume
      current.buyQty += volume
      current.buyAmount += price * volume
    }
    if (price > 0) current.lastPrice = price
    grouped.set(key, current)
  })

  return Array.from(grouped.values())
    .filter((item) => item.qty > 0 && !liveKeys.has(getHoldingIdentity(item)) && !hasAuthoritativeLiveAccount(item))
    .map((item) => {
      const avgPrice = item.buyQty > 0 ? item.buyAmount / item.buyQty : item.lastPrice
      const currentPrice = item.lastPrice || avgPrice
      return {
        symbol: item.symbol,
        name: item.name,
        qty: item.qty,
        avg_price: avgPrice,
        current_price: currentPrice,
        profit: 0,
        profit_rate: 0,
        currency: item.currency,
        exchange: item.exchange,
        raw_exchange: item.raw_exchange,
        account_type: item.account_type,
        asset_type: item.asset_type,
        env: item.env,
        source: 'DB_ESTIMATED',
      }
    })
}

export const mergeBalanceWithTradeEstimates = (mergedBalance, tradeRows = [], showMockAssets = true) => {
  const holdings = Array.isArray(mergedBalance?.holdings) ? mergedBalance.holdings : []
  const estimatedHoldings = buildEstimatedHoldingsFromTrades(tradeRows, holdings, showMockAssets, mergedBalance?.sources || [])
  return {
    ...mergedBalance,
    holdings: [...holdings, ...estimatedHoldings],
  }
}

export const mergeBalanceWithCompletedTransfers = (mergedBalance, transferRows = []) => {
  return mergeCompletedTransfersIntoCash(mergedBalance, transferRows)
}

export const getBalanceRequestLabel = (exchange, env) => {
  if (exchange === 'KIS') {
    return `KIS ${env === 'REAL' ? '실전' : '모의'}`
  }
  if (exchange === 'BINANCE') {
    return `BINANCE 현물 ${env === 'REAL' ? '실거래' : '모의'}`
  }
  if (exchange === 'BINANCE_UM_FUTURES') {
    return `BINANCE 선물 ${env === 'REAL' ? '실거래' : '모의'}`
  }

  return exchange
}

export const getBalanceAccountLabel = (exchange, env, account = {}) => {
  const baseLabel = getBalanceRequestLabel(exchange, env)
  const accountNo = exchange === 'KIS'
    ? account.kis_account_no
    : exchange === 'TOSS'
      ? account.toss_account_no
      : ''
  return accountNo ? `${baseLabel} ${accountNo}` : baseLabel
}

export const buildBalanceRequests = (keyStatus) =>
  BALANCE_EXCHANGE_ORDER.flatMap((exchange) => {
    const statusExchange = exchange === 'BINANCE_UM_FUTURES' ? 'BINANCE' : exchange
    const status = keyStatus[statusExchange]
    if (!status?.registered) return []

    const accounts = Array.isArray(status.accounts) && status.accounts.length > 0
      ? status.accounts
      : [status]

    return accounts.map((account) => {
      const env = String(account?.broker_env || status.broker_env || (exchange === 'KIS' ? 'MOCK' : 'REAL')).toUpperCase()
      return {
        exchange,
        env,
        label: getBalanceAccountLabel(exchange, env, account),
      }
    })
  })
