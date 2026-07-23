export const TAG_REQUIRED_SYMBOLS = new Set(['XRP', 'XLM', 'EOS'])

export const parseNumeric = (value) => {
  if (typeof value === 'number') return value
  const text = String(value || '')
  const number = parseFloat(text.replace(/[^0-9.-]/g, ''))
  return Number.isFinite(number) ? number : 0
}

export const formatNativeCurrency = (value, currency) => {
  const numeric = Number(value)
  if (!Number.isFinite(numeric)) return '-'
  const normalizedCurrency = String(currency || 'KRW').toUpperCase()
  if (normalizedCurrency === 'USD' || normalizedCurrency === 'USDT') {
    return `$${numeric.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
  }
  if (normalizedCurrency === 'KRW') {
    return `₩${Math.round(numeric).toLocaleString()}`
  }
  return `${numeric.toLocaleString()} ${normalizedCurrency}`
}

export const formatCryptoAmount = (value, currency) => {
  const numeric = Number(value)
  if (!Number.isFinite(numeric)) return '-'
  return `${numeric.toLocaleString(undefined, { minimumFractionDigits: 0, maximumFractionDigits: 8 })} ${currency || ''}`.trim()
}

export const normalizeExchangeCode = (value = '') => {
  const text = String(value || '').toUpperCase()
  if (text.includes('BINANCE_UM_FUTURES')) return 'BINANCE_UM_FUTURES'
  if (text.includes('BINANCE')) return 'BINANCE'
  if (text.includes('COINONE')) return 'COINONE'
  if (text.includes('TOSS')) return 'TOSS'
  if (text.includes('KIS')) return 'KIS'
  return text
}

export const getTransferRoute = (asset = {}) => {
  const exchange = normalizeExchangeCode(asset.rawExchange || asset.exchange)
  if (exchange === 'COINONE') {
    return {
      fromExchange: 'COINONE',
      toExchange: 'BINANCE',
      fromLabel: '코인원',
      toLabel: '바이낸스',
      addressLabel: '바이낸스 입금 주소',
      addressButtonLabel: '바이낸스 주소 불러오기',
    }
  }
  if (exchange === 'BINANCE') {
    return {
      fromExchange: 'BINANCE',
      toExchange: 'COINONE',
      fromLabel: '바이낸스',
      toLabel: '코인원',
      addressLabel: '코인원 입금 주소',
      addressButtonLabel: '코인원 주소 불러오기',
    }
  }
  return null
}

export const getBalanceCashEntries = (account = {}) => {
  const fallbackCurrency = String(account.available_cash_currency || account.currency || 'KRW').toUpperCase()
  const components = Array.isArray(account.available_cash_details?.components)
    ? account.available_cash_details.components
    : []

  if (components.length > 0) {
    return components
      .map((component) => {
        const amount = Number(component?.cash_buying_power)
        if (!Number.isFinite(amount)) return null
        return {
          currency: String(component?.currency || fallbackCurrency).toUpperCase(),
          amount,
        }
      })
      .filter(Boolean)
  }

  const fallbackAmount = Number(account.available_cash)
  if (!Number.isFinite(fallbackAmount)) return []
  return [{ currency: fallbackCurrency, amount: fallbackAmount }]
}

export const buildAccountSummaryCards = ({
  accountBalances = [],
  showMockAssets = true,
} = {}) => {
  const normalizedAccounts = (accountBalances || [])
    .filter(Boolean)
    .filter((account) => showMockAssets || String(account.env || '').toUpperCase() !== 'MOCK')

  const cardMap = new Map([
    ['domestic-stock', {
      id: 'domestic-stock',
      title: '국내 주식 계좌',
      accountType: '원화',
      balanceLabel: '잔고 포함',
      currency: 'KRW',
      amount: 0,
      sources: new Set(),
    }],
    ['overseas-stock', {
      id: 'overseas-stock',
      title: '해외 주식 계좌',
      accountType: '달러',
      balanceLabel: '잔고 포함',
      currency: 'USD',
      amount: 0,
      sources: new Set(),
    }],
    ['coinone-crypto', {
      id: 'coinone-crypto',
      title: '코인 계좌',
      accountType: '원화',
      balanceLabel: '잔고 포함',
      currency: 'KRW',
      amount: 0,
      sources: new Set(),
    }],
    ['binance-crypto', {
      id: 'binance-crypto',
      title: '코인 계좌',
      accountType: '달러',
      balanceLabel: '잔고 포함',
      currency: 'USD',
      amount: 0,
      sources: new Set(),
    }],
  ])

  const addSource = (cardId, source) => {
    const card = cardMap.get(cardId)
    if (!card || !source) return
    card.sources.add(source)
  }

  const addAmount = (cardId, amount, source) => {
    const card = cardMap.get(cardId)
    const numeric = Number(amount)
    if (!card || !Number.isFinite(numeric)) return
    card.amount += numeric
    if (source) card.sources.add(source)
  }

  normalizedAccounts.forEach((account) => {
    const exchange = String(account.raw_exchange || account.exchange || '').toUpperCase()
    const sourceLabel = `${exchange}${account.env ? ` ${account.env}` : ''}`
    const cashEntries = getBalanceCashEntries(account)

    if (['TOSS', 'KIS'].includes(exchange)) {
      addSource('domestic-stock', sourceLabel)
      addSource('overseas-stock', sourceLabel)
    } else if (exchange === 'COINONE') {
      addSource('coinone-crypto', sourceLabel)
    } else if (exchange === 'BINANCE' || exchange === 'BINANCE_UM_FUTURES') {
      addSource('binance-crypto', sourceLabel)
    }

    cashEntries.forEach((entry) => {
      const currency = String(entry.currency || '').toUpperCase()
      if (['TOSS', 'KIS'].includes(exchange)) {
        if (currency === 'KRW') addAmount('domestic-stock', entry.amount, sourceLabel)
        if (currency === 'USD' || currency === 'USDT') addAmount('overseas-stock', entry.amount, sourceLabel)
      } else if (exchange === 'COINONE') {
        if (currency === 'KRW') addAmount('coinone-crypto', entry.amount, sourceLabel)
      } else if (exchange === 'BINANCE' || exchange === 'BINANCE_UM_FUTURES') {
        if (currency === 'USD' || currency === 'USDT') addAmount('binance-crypto', entry.amount, sourceLabel)
      }
    })

    ;(account.holdings || []).forEach((holding) => {
      const holdingCurrency = String(holding.currency || account.currency || '').toUpperCase()
      const evalAmount = parseNumeric(holding.eval_amount) || Math.abs(parseNumeric(holding.qty)) * parseNumeric(holding.current_price)
      if (evalAmount <= 0) return

      if (['TOSS', 'KIS'].includes(exchange)) {
        if (holdingCurrency === 'USD' || holdingCurrency === 'USDT') addAmount('overseas-stock', evalAmount, sourceLabel)
        else addAmount('domestic-stock', evalAmount, sourceLabel)
      } else if (exchange === 'COINONE') {
        addAmount('coinone-crypto', evalAmount, sourceLabel)
      } else if (exchange === 'BINANCE' || exchange === 'BINANCE_UM_FUTURES') {
        addAmount('binance-crypto', evalAmount, sourceLabel)
      }
    })
  })

  return Array.from(cardMap.values())
    .map((card) => ({
      ...card,
      balance: formatNativeCurrency(card.amount, card.currency),
      sourceText: Array.from(card.sources).join(' · '),
    }))
    .filter((card) => card.sources.size > 0)
}

export const formatCurrency = (value, currency, targetDisplayCurrency = 'KRW', exchangeRate = 1500) => {
  const numeric = Number(value)
  const val = Number.isFinite(numeric) ? numeric : 0
  const rate = Number(exchangeRate) || 1500

  if (targetDisplayCurrency === 'KRW') {
    if (currency === 'USD' || currency === 'USDT') {
      return `₩${Math.round(val * rate).toLocaleString()}`
    }
    return `₩${Math.round(val).toLocaleString()}`
  }

  if (targetDisplayCurrency === 'USD') {
    if (currency === 'KRW') {
      return `$${(val / rate).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
    }
    return `$${val.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
  }

  if (currency === 'USD' || currency === 'USDT') {
    return `$${val.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
  }
  return `₩${Math.round(val).toLocaleString()}`
}

const getMaximumUnitFractionDigits = (displayValue, unitCurrency = '') => {
  if (unitCurrency === 'USD' || unitCurrency === 'USDT') return 4
  const numericValue = Number(displayValue)
  const absoluteValue = Number.isFinite(numericValue) ? Math.abs(numericValue) : 0
  if (unitCurrency === 'KRW' && absoluteValue > 0 && absoluteValue < 1) return 4
  return absoluteValue > 0 && absoluteValue < 0.1 ? 3 : 1
}

export const formatUnitCurrency = (value, currency, targetDisplayCurrency = 'KRW', exchangeRate = 1500) => {
  const numeric = Number(value)
  const val = Number.isFinite(numeric) ? numeric : 0
  const rate = Number(exchangeRate) || 1500

  if (targetDisplayCurrency === 'KRW') {
    const displayValue = (currency === 'USD' || currency === 'USDT') ? val * rate : val
    return `₩${displayValue.toLocaleString(undefined, { minimumFractionDigits: 0, maximumFractionDigits: getMaximumUnitFractionDigits(displayValue, 'KRW') })}`
  }

  if (targetDisplayCurrency === 'USD') {
    const displayValue = currency === 'KRW' ? val / rate : val
    return `$${displayValue.toLocaleString(undefined, { minimumFractionDigits: 0, maximumFractionDigits: getMaximumUnitFractionDigits(displayValue, 'USD') })}`
  }

  if (currency === 'USD' || currency === 'USDT') {
    return `$${val.toLocaleString(undefined, { minimumFractionDigits: 0, maximumFractionDigits: getMaximumUnitFractionDigits(val, currency) })}`
  }
  return `₩${val.toLocaleString(undefined, { minimumFractionDigits: 0, maximumFractionDigits: getMaximumUnitFractionDigits(val, 'KRW') })}`
}

export const buildHoldingRows = ({
  holdings = [],
  exchangeRate = 1500,
} = {}) => (

  holdings.map((stock, index) => {
    const exchangeName = stock.exchange || stock.account_type || '-'
    const rawExchange = normalizeExchangeCode(stock.raw_exchange || exchangeName)
    const isCoinone = rawExchange === 'COINONE'
    const isBinance = rawExchange === 'BINANCE' || rawExchange === 'BINANCE_UM_FUTURES'
    const symbolText = String(stock.symbol || stock.id || '').toUpperCase()
    const marketCountry = String(stock.market_country || stock.marketCountry || stock.market || '').toUpperCase()
    const isForeign = !isCoinone && !isBinance && (
      marketCountry === 'US'
      || marketCountry.includes('OVERSEAS')
      || marketCountry.includes('해외')
      || (/[A-Z]/.test(symbolText) && !/^\d{6}$/.test(symbolText))
    )
    const stockCurrency = isBinance ? 'USDT' : isForeign ? 'USD' : isCoinone ? 'KRW' : 'KRW'
    const currentDisplayCurrency = isBinance ? 'USD' : isForeign ? 'USD' : 'KRW'
    const assetType = stock.asset_type || (['COINONE', 'BINANCE', 'BINANCE_UM_FUTURES'].includes(rawExchange) ? 'CRYPTO' : 'STOCK')
    const symbol = stock.symbol || stock.id || `holding-${index}`
    const profitRate = Number(stock.profit_rate)
    return {
      id: symbol,
      rowId: `${rawExchange || exchangeName}-${stock.env || 'REAL'}-${symbol}-${index}`,
      name: stock.name,
      exchange: exchangeName,
      assetType,
      source: stock.source || 'LIVE_BALANCE',
      rawExchange,
      quantity: `${stock.qty}`,
      average: formatUnitCurrency(stock.avg_price, stockCurrency, currentDisplayCurrency, exchangeRate),
      currentPrice: formatUnitCurrency(stock.current_price, stockCurrency, currentDisplayCurrency, exchangeRate),
      profit: formatCurrency(stock.profit, stockCurrency, currentDisplayCurrency, exchangeRate),
      returnRate: `${profitRate >= 0 ? '+' : ''}${Number.isFinite(profitRate) ? profitRate.toFixed(2) : '0.00'}%`,
    }
  })
)

export const sortHoldings = (holdings, sortConfig = {}) => (
  [...holdings].sort((a, b) => {
    if (!sortConfig.key) return 0
    const aVal = parseNumeric(a[sortConfig.key])
    const bVal = parseNumeric(b[sortConfig.key])
    return sortConfig.direction === 'asc' ? aVal - bVal : bVal - aVal
  })
)

export const formatAllocationPercent = (item = {}) => {
  const rawPercent = Number(item.rawPercent ?? item.value)
  if (rawPercent > 0 && rawPercent < 1) return '1% 미만'
  if (rawPercent <= 0) return '0%'
  return `${rawPercent.toFixed(1)}%`
}

export const ALLOCATION_COLOR_HEX = {
  domestic: '#0047bb',
  overseas: '#00e0ff',
  coin: '#f59e0b',
  cash: '#64748b',
}

export const buildAllocationGradient = (allocation = {}) => {
  const allocationSegments = allocation.filter((item) => Number(item.value) > 0)
  const allocationTotal = allocationSegments.reduce((sum, item) => sum + Number(item.value), 0)
  let allocationGradientCursor = 0
  return allocationSegments.length > 0
    ? `conic-gradient(${allocationSegments.map((item) => {
      const start = allocationGradientCursor
      allocationGradientCursor += (Number(item.value) / allocationTotal) * 100
      return `${ALLOCATION_COLOR_HEX[item.id] || '#64748b'} ${start}% ${allocationGradientCursor}%`
    }).join(', ')})`
    : 'conic-gradient(#334155 0% 100%)'
}
