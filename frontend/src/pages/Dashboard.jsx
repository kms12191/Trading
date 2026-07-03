import { useEffect, useState } from 'react'
import { fetchUserWatchlist, supabase } from '../supabaseClient'
import Header from '../components/Header.jsx'
import Settings from './Settings'
import { Rate, SectionHeader, SidebarNav } from '../components/DashboardComponents.jsx'
import WatchlistTab from './WatchlistTab.jsx'
import AssetsTab from './AssetsTab.jsx'
import TradeHistoryTab from './TradeHistoryTab.jsx'
import AdminMlData from './AdminMlData.jsx'
import { getApiErrorMessage } from '../lib/apiError.js'

const DASHBOARD_API_BASE_URL = 'http://localhost:5050'
const BALANCE_EXCHANGE_ORDER = ['TOSS', 'KIS', 'COINONE', 'BINANCE', 'BINANCE_UM_FUTURES']
const TRADE_PROPOSAL_HOLDING_FIELDS = 'id,exchange,asset_type,ticker,symbol,side,price,volume,order_amount,market_country,currency,status,broker_env,created_at'

const toNumber = (value) => {
  const numericValue = Number(value)
  return Number.isFinite(numericValue) ? numericValue : 0
}

const formatKrw = (value) => `₩${Math.round(toNumber(value)).toLocaleString()}`

const formatCurrency = (value, currency, displayCurrency = 'KRW', exchangeRate = 1500) => {
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

const formatUnitCurrency = (value, currency, displayCurrency = 'KRW', exchangeRate = 1500) => {
  const numeric = toNumber(value)
  const rate = toNumber(exchangeRate) || 1500

  if (displayCurrency === 'KRW') {
    const displayValue = (currency === 'USD' || currency === 'USDT') ? numeric * rate : numeric
    return `₩${displayValue.toLocaleString(undefined, { minimumFractionDigits: 0, maximumFractionDigits: 1 })}`
  }

  if (displayCurrency === 'USD') {
    const displayValue = currency === 'KRW' ? numeric / rate : numeric
    return `$${displayValue.toLocaleString(undefined, { minimumFractionDigits: 0, maximumFractionDigits: 1 })}`
  }

  if (currency === 'USD' || currency === 'USDT') {
    return `$${numeric.toLocaleString(undefined, { minimumFractionDigits: 0, maximumFractionDigits: 1 })}`
  }
  return `₩${numeric.toLocaleString(undefined, { minimumFractionDigits: 0, maximumFractionDigits: 1 })}`
}

const formatNullableCurrency = (value, currency, displayCurrency = 'KRW', exchangeRate = 1500) => {
  if (value === null || value === undefined || value === '') return '-'
  return formatCurrency(value, currency, displayCurrency, exchangeRate)
}

const formatNativeCurrency = (value, currency) => {
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

const getAccountDisplayLabel = (item = {}) => {
  const exchange = String(item.raw_exchange || item.exchange || '-').toUpperCase()
  const env = String(item.env || '').toUpperCase()
  if (!env) return exchange
  return `${exchange} ${env === 'MOCK' ? '모의' : '실거래'}`
}

const getAccountTone = (exchange = '') => {
  const normalized = String(exchange || '').toUpperCase()
  if (normalized.includes('TOSS')) return 'border-cyan-500/30 bg-cyan-950/20'
  if (normalized.includes('KIS')) return 'border-blue-500/30 bg-blue-950/20'
  if (normalized.includes('COINONE')) return 'border-amber-500/30 bg-amber-950/20'
  if (normalized.includes('BINANCE_UM_FUTURES')) return 'border-cyan-500/30 bg-cyan-950/20'
  if (normalized.includes('BINANCE')) return 'border-emerald-500/30 bg-emerald-950/20'
  return 'border-slate-700/80 bg-slate-900/70'
}

const buildCashEntriesFromItem = (item = {}) => {
  const sourceLabel = getAccountDisplayLabel(item)
  const cashCurrency = String(item.available_cash_currency || item.currency || 'KRW').toUpperCase()
  const rawComponents = Array.isArray(item.available_cash_details?.components) && item.available_cash_details.components.length > 0
    ? item.available_cash_details.components
    : (
      item.available_cash !== null && item.available_cash !== undefined && item.available_cash !== '' && Number.isFinite(Number(item.available_cash))
        ? [{ currency: cashCurrency, cash_buying_power: Number(item.available_cash) }]
        : []
    )

  return rawComponents
    .map((component) => {
      const currency = String(component?.currency || cashCurrency).toUpperCase()
      const amount = Number(component?.cash_buying_power)
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
}

const parsePriceNumber = (value) => {
  if (typeof value === 'number') return Number.isFinite(value) ? value : null
  const numeric = Number(String(value ?? '').replace(/,/g, '').replace(/[^0-9.-]/g, ''))
  return Number.isFinite(numeric) ? numeric : null
}

const getWatchlistCurrentPrice = (item = {}) => {
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

const getDashboardWatchlistAssetType = (item = {}) => {
  const assetType = String(item.assetType || item.asset_type || '').toUpperCase()
  const market = String(item.market || '').toUpperCase()
  const account = String(item.account || item.exchange || '').toUpperCase()
  return assetType === 'CRYPTO' || /COIN|CRYPTO|BINANCE|COINONE|BTC|ETH|USDT/.test(`${market} ${account}`) ? 'CRYPTO' : 'STOCK'
}

const getDashboardWatchlistChartConfig = (item = {}) => {
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

const fetchDashboardWatchlistCurrentPrice = async (item = {}, authHeader = '') => {
  if (!item.id) return null

  const { exchange, brokerEnv, interval } = getDashboardWatchlistChartConfig(item)
  const params = new URLSearchParams({
    exchange,
    symbol: item.id,
    interval,
    broker_env: brokerEnv,
    count: '300',
  })
  const headers = authHeader ? { Authorization: authHeader } : {}
  const response = await fetch(`${DASHBOARD_API_BASE_URL}/api/chart/candles?${params.toString()}`, { headers })
  const payload = await response.json()

  if (!response.ok || !payload.success || !Array.isArray(payload.data) || payload.data.length === 0) {
    return null
  }

  const latestCandle = payload.data[payload.data.length - 1]
  return parsePriceNumber(latestCandle?.close)
}

const RefreshIcon = ({ className = '' }) => (
  <svg
    className={className}
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth="2"
    strokeLinecap="round"
    strokeLinejoin="round"
    aria-hidden="true"
  >
    <path d="M21 12a9 9 0 1 1-2.64-6.36" />
    <path d="M21 3v6h-6" />
  </svg>
)

const formatSignedRate = (value) => {
  const numericValue = toNumber(value)
  return `${numericValue >= 0 ? '+' : ''}${numericValue.toFixed(2)}%`
}

const getHoldingMarketType = (holding = {}) => {
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

const getHoldingEvaluationKrw = (holding = {}, exchangeRate = 1500) => {
  const currency = String(holding.currency || '').toUpperCase()
  const rate = toNumber(exchangeRate) || 1500
  const rawValue = toNumber(holding.eval_amount) > 0
    ? toNumber(holding.eval_amount)
    : toNumber(holding.current_price) * Math.abs(toNumber(holding.qty))

  return currency === 'USD' || currency === 'USDT' ? rawValue * rate : rawValue
}

const getPortfolioProfitRate = (accountBalance) => {
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

const mergeAccountBalances = (items, showMockAssets = true) => {
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

  const holdings = filteredItems.flatMap((item) => {
    const exchange = item.exchange
    const rate = toNumber(item.exchange_rate) || representativeRate
    const itemCurrency = item.currency || 'KRW'
    const cashCurrency = item.available_cash_currency || itemCurrency

    let itemEval = toNumber(item.total_evaluation)

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

const getHoldingIdentity = (holding = {}) => {
  const symbol = String(holding.symbol || holding.ticker || holding.id || '').trim().toUpperCase()
  const exchangeText = String(holding.raw_exchange || holding.exchange || holding.account_type || '').toUpperCase()
  const rawExchange = exchangeText.includes('KIS') ? 'KIS'
    : exchangeText.includes('TOSS') ? 'TOSS'
      : exchangeText.includes('COINONE') ? 'COINONE'
        : exchangeText.includes('BINANCE_UM_FUTURES') ? 'BINANCE_UM_FUTURES'
          : exchangeText.includes('BINANCE') ? 'BINANCE'
            : exchangeText
  const env = String(holding.env || (exchangeText.includes('모의') ? 'MOCK' : exchangeText.includes('실전') ? 'REAL' : 'REAL')).toUpperCase()
  const assetType = String(holding.asset_type || (['COINONE', 'BINANCE', 'BINANCE_UM_FUTURES'].includes(rawExchange) ? 'CRYPTO' : 'STOCK')).toUpperCase()
  return symbol ? `${assetType}:${rawExchange}:${env}:${symbol}` : ''
}

const fetchTradeSymbolNameMap = async (tradeRows = []) => {
  const symbols = Array.from(new Set(
    tradeRows
      .map((row) => String(row.symbol || row.ticker || '').trim().toUpperCase())
      .filter(Boolean),
  ))

  if (symbols.length === 0) return {}

  const pairs = await Promise.all(
    symbols.map(async (symbol) => {
      try {
        const response = await fetch(`${DASHBOARD_API_BASE_URL}/api/symbol/lookup?query=${encodeURIComponent(symbol)}`)
        const payload = await response.json()
        const displayName = payload?.success ? payload.data?.display_name : ''
        return [symbol, displayName || symbol]
      } catch {
        return [symbol, symbol]
      }
    }),
  )

  return Object.fromEntries(pairs)
}

const buildEstimatedHoldingsFromTrades = (tradeRows = [], liveHoldings = [], showMockAssets = true) => {
  const liveKeys = new Set(liveHoldings.map(getHoldingIdentity).filter(Boolean))
  if (tradeRows.some((row) => row.source === 'DB_ESTIMATED')) {
    return tradeRows.filter((item) => item.qty > 0 && (showMockAssets || item.env !== 'MOCK') && !liveKeys.has(getHoldingIdentity(item)))
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
    .filter((item) => item.qty > 0 && !liveKeys.has(getHoldingIdentity(item)))
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

const mergeBalanceWithTradeEstimates = (mergedBalance, tradeRows = [], showMockAssets = true) => {
  const holdings = Array.isArray(mergedBalance?.holdings) ? mergedBalance.holdings : []
  const estimatedHoldings = buildEstimatedHoldingsFromTrades(tradeRows, holdings, showMockAssets)
  return {
    ...mergedBalance,
    holdings: [...holdings, ...estimatedHoldings],
  }
}

const getBalanceRequestLabel = (exchange, env) => {
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

const getBalanceAccountLabel = (exchange, env, account = {}) => {
  const baseLabel = getBalanceRequestLabel(exchange, env)
  const accountNo = exchange === 'KIS'
    ? account.kis_account_no
    : exchange === 'TOSS'
      ? account.toss_account_no
      : ''
  return accountNo ? `${baseLabel} ${accountNo}` : baseLabel
}

const buildBalanceRequests = (keyStatus) =>
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

export default function Dashboard({ isLoggedIn, userEmail, handleLogout, userProfile }) {
  const [inputs, setInputs] = useState({
    appkey: '',
    appsecret: '',
    cano: '',
    env: 'MOCK'
  })
  const [activeTab, setActiveTab] = useState('dashboard')
  const [isSidebarOpen, setIsSidebarOpen] = useState(true)

  const [encrypted, setEncrypted] = useState(null)
  const [loading, setLoading] = useState(false)
  const [message, setMessage] = useState({ text: '', isError: false })
  const [balance, setBalance] = useState(null)
  const [balanceLoading, setBalanceLoading] = useState(false)
  const [showMockAssets, setShowMockAssets] = useState(true)
  const [rawBalances, setRawBalances] = useState([])
  const [executedTradeRows, setExecutedTradeRows] = useState([])
  const [dashboardWatchlist, setDashboardWatchlist] = useState([])
  const [watchlistLoading, setWatchlistLoading] = useState(false)
  const [watchlistError, setWatchlistError] = useState('')
  const [watchlistRefreshCooldown, setWatchlistRefreshCooldown] = useState(0)
  const [balanceRefreshCooldown, setBalanceRefreshCooldown] = useState(0)

  const [holdingsSort, setHoldingsSort] = useState({ key: null, direction: 'asc' })

  const handleHoldingsSort = (key) => {
    let direction = 'asc'
    if (holdingsSort.key === key && holdingsSort.direction === 'asc') {
      direction = 'desc'
    }
    setHoldingsSort({ key, direction })
  }

  const getSortedHoldings = (holdingsList) => {
    if (!holdingsList) return []
    if (!holdingsSort.key) return holdingsList
    return [...holdingsList].sort((a, b) => {
      let aVal = toNumber(a[holdingsSort.key])
      let bVal = toNumber(b[holdingsSort.key])
      return holdingsSort.direction === 'asc' ? aVal - bVal : bVal - aVal
    })
  }
  const [balanceError, setBalanceError] = useState('')

  const [displayCurrency, setDisplayCurrency] = useState('KRW')
  const [isCashDetailModalOpen, setIsCashDetailModalOpen] = useState(false)

  const handleInputChange = (e) => {
    const { name, value } = e.target
    setInputs(prev => ({ ...prev, [name]: value }))
  }

  const handleTestKeys = async (e) => {
    e.preventDefault()
    if (!inputs.appkey || !inputs.appsecret || !inputs.cano) {
      setMessage({ text: 'Please fill in all API Key fields.', isError: true })
      return
    }

    setLoading(true)
    setMessage({ text: '', isError: false })

    try {
      const response = await fetch('http://localhost:5050/api/keys/test', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(inputs)
      })

      const resData = await response.json()

      if (resData.success) {
        setMessage({ text: resData.message, isError: false })
        setEncrypted(resData.data.encrypted)
        setBalance(resData.data.balance)
      } else {
        const message = getApiErrorMessage(resData, 'Key validation failed.')
        setMessage({ text: message.detail ? `${message.title} ${message.detail}` : message.title, isError: true })
      }
    } catch (error) {
      const message = getApiErrorMessage(error, 'Failed to connect to backend server.')
      setMessage({ text: message.detail ? `${message.title} ${message.detail}` : message.title, isError: true })
    } finally {
      setLoading(false)
    }
  }

  const loadAccountBalance = async () => {
    if (!isLoggedIn) {
      setBalance(null)
      setBalanceError('')
      return
    }

    setBalanceLoading(true)
    setBalanceError('')

    try {
      const { data: { session } } = await supabase.auth.getSession()
      if (!session?.access_token) {
        setBalance(null)
        setBalanceError('로그인 세션을 확인할 수 없습니다.')
        return
      }

      const authHeader = `Bearer ${session.access_token}`
      const statusResponse = await fetch(`${DASHBOARD_API_BASE_URL}/api/keys/status`, {
        headers: { Authorization: authHeader },
      })
      const statusPayload = await statusResponse.json()

      if (!statusResponse.ok || !statusPayload.success) {
        throw statusPayload
      }

      const keyStatus = statusPayload.data || {}
      const balanceRequests = buildBalanceRequests(keyStatus)

      if (balanceRequests.length === 0) {
        setBalance({ total_evaluation: 0, available_cash: 0, holdings: [], sources: [] })
        setBalanceError('등록된 거래소 API 키가 없습니다.')
        return
      }

      const results = await Promise.all(
        balanceRequests.map(async ({ exchange, env, label }) => {
          try {
            const response = await fetch(`${DASHBOARD_API_BASE_URL}/api/dashboard/balance`, {
              method: 'POST',
              headers: {
                'Content-Type': 'application/json',
                Authorization: authHeader,
              },
              body: JSON.stringify({ exchange, env }),
            })
            const payload = await response.json()

            if (!response.ok || !payload.success) {
              const message = getApiErrorMessage(payload, `${exchange} 잔고 조회 실패`)
              return {
                exchange: label,
                env,
                error: message.detail ? `${message.title} ${message.detail}` : message.title,
              }
            }

            return { ...payload.data, exchange: label, raw_exchange: exchange, env }
          } catch (error) {
            const message = getApiErrorMessage(error, `${exchange} 잔고 조회 실패`)
            return {
              exchange: label,
              env,
              error: message.detail ? `${message.title} ${message.detail}` : message.title,
            }
          }
        }),
      )

      const failedResults = results.filter((item) => item?.error)
      const successResults = results.filter((item) => !item?.error)
      try {
        await fetch(`${DASHBOARD_API_BASE_URL}/api/trade/orders/sync-status`, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            Authorization: authHeader,
          },
        })
      } catch {
        // 거래내역 상태 동기화 실패는 잔고 조회 자체를 막지 않습니다.
      }

      let tradeRows = []
      const { data: proposalRows, error: proposalError } = await supabase
        .from('trade_proposals')
        .select(TRADE_PROPOSAL_HOLDING_FIELDS)
        .eq('status', 'EXECUTED')
        .order('created_at', { ascending: true })

      if (proposalError) {
        setBalanceError(`거래내역 보정 조회 실패: ${proposalError.message}`)
      } else {
        const baseRows = proposalRows || []
        const symbolNameMap = await fetchTradeSymbolNameMap(baseRows)
        tradeRows = baseRows.map((row) => {
          const symbol = String(row.symbol || row.ticker || '').trim().toUpperCase()
          return {
            ...row,
            display_name: symbolNameMap[symbol] || symbol,
          }
        })
      }

      try {
        const estimatedResponse = await fetch(`${DASHBOARD_API_BASE_URL}/api/trade/estimated-holdings`, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            Authorization: authHeader,
          },
          body: JSON.stringify({ show_mock_assets: showMockAssets }),
        })
        const estimatedPayload = await estimatedResponse.json()
        if (estimatedResponse.ok && estimatedPayload.success) {
          tradeRows = estimatedPayload.data?.holdings || []
        } else {
          setBalanceError(estimatedPayload.message || '거래내역 기반 보유종목 보정 조회에 실패했습니다.')
        }
      } catch (error) {
        setBalanceError(`거래내역 기반 보유종목 보정 조회 실패: ${error.message}`)
      }

      setExecutedTradeRows(tradeRows)
      setRawBalances(successResults)
      const mergedBalance = mergeBalanceWithTradeEstimates(
        mergeAccountBalances(successResults, showMockAssets),
        tradeRows,
        showMockAssets,
      )
      setBalance(mergedBalance)

      if (mergedBalance.sources.length === 0) {
        setBalanceError(
          failedResults.length > 0
            ? `잔고 조회 실패: ${failedResults.map((item) => `${item.exchange} - ${item.error}`).join(' / ')}`
            : '등록된 계정은 있지만 조회 가능한 잔고가 없습니다.'
        )
      } else if (failedResults.length > 0) {
        setBalanceError(`일부 계정 조회 실패: ${failedResults.map((item) => item.exchange).join(', ')}`)
      }
    } catch (error) {
      const message = getApiErrorMessage(error, '계정 자산 조회에 실패했습니다.')
      setBalance(null)
      setBalanceError(message.detail ? `${message.title} ${message.detail}` : message.title)
    } finally {
      setBalanceLoading(false)
    }
  }

  const handleBalanceRefresh = () => {
    if (balanceRefreshCooldown > 0 || balanceLoading)

      return
    setBalanceRefreshCooldown(60)
    loadAccountBalance()
  }

  useEffect(() => {
    loadAccountBalance()
  }, [isLoggedIn])

  useEffect(() => {
    loadDashboardWatchlist()
  }, [isLoggedIn, activeTab])



  useEffect(() => {
    if (watchlistRefreshCooldown <= 0) return undefined

    const timerId = window.setInterval(() => {
      setWatchlistRefreshCooldown((seconds) => Math.max(seconds - 1, 0))
    }, 1000)

    return () => window.clearInterval(timerId)
  }, [watchlistRefreshCooldown])

  const loadDashboardWatchlist = async ({ manual = false } = {}) => {
    if (manual && watchlistRefreshCooldown > 0) return

    if (!isLoggedIn) {
      setDashboardWatchlist([])
      setWatchlistError('')
      return
    }

    if (manual) {
      setWatchlistRefreshCooldown(60)
    }

    setWatchlistLoading(true)
    setWatchlistError('')
    try {
      const items = await fetchUserWatchlist()
      const { data: { session } } = await supabase.auth.getSession()
      const authHeader = session?.access_token ? `Bearer ${session.access_token}` : ''
      const itemsWithCurrentPrice = await Promise.all(
        items.map(async (item) => {
          try {
            const currentPrice = await fetchDashboardWatchlistCurrentPrice(item, authHeader)
            return currentPrice === null ? item : { ...item, currentPrice }
          } catch {
            return item
          }
        }),
      )
      setDashboardWatchlist(itemsWithCurrentPrice)
    } catch (error) {
      setDashboardWatchlist([])
      setWatchlistError(error.message || '관심종목을 불러오지 못했습니다.')
    } finally {
      setWatchlistLoading(false)
    }
  }

  useEffect(() => {
    if (balanceRefreshCooldown <= 0) return undefined

    const timerId = window.setInterval(() => {
      setBalanceRefreshCooldown((seconds) => Math.max(seconds - 1, 0))
    }, 1000)

    return () => window.clearInterval(timerId)
  }, [balanceRefreshCooldown])

  useEffect(() => {
    if (rawBalances.length > 0) {
      setBalance(mergeBalanceWithTradeEstimates(
        mergeAccountBalances(rawBalances, showMockAssets),
        executedTradeRows,
        showMockAssets,
      ))
    }
  }, [rawBalances, showMockAssets, executedTradeRows])

  // 자산 배분 데이터
  const getAllocationData = () => {
    if (!balance || !balance.holdings || balance.holdings.length === 0) {
      return [
        { id: 'domestic', label: '국내 주식', value: 0, color: 'bg-institutional-blue' },
        { id: 'overseas', label: '해외 주식', value: 0, color: 'bg-ai-cyan' },
        { id: 'coin', label: '코인', value: 0, color: 'bg-amber-400' },
        { id: 'cash', label: '현금', value: 100, color: 'bg-slate-500' }
      ]
    }

    let domesticValue = 0
    let overseasValue = 0
    let coinValue = 0

    balance.holdings.forEach((stock) => {
      const symbol = String(stock.symbol || '').toUpperCase()
      const accountType = String(stock.account || stock.account_type || stock.asset_type || stock.exchange || '').toUpperCase()
      const isCoin = /BTC|ETH|XRP|SOL|USDT|KRW|COINONE|BINANCE|CRYPTO|코인/.test(`${symbol} ${accountType}`)
      const isOverseas = getHoldingMarketType(stock) === 'overseas' && !isCoin
      const stockEval = getHoldingEvaluationKrw(stock, balance.exchange_rate)

      if (isCoin) {
        coinValue += stockEval
      } else if (isOverseas) {
        overseasValue += stockEval
      } else {
        domesticValue += stockEval
      }
    })

    const cashValue = Math.max(0, toNumber(balance.available_cash))
    const allocationTotal = domesticValue + overseasValue + coinValue + cashValue

    if (allocationTotal <= 0) {
      return [
        { id: 'domestic', label: '국내 주식', value: 0, color: 'bg-institutional-blue' },
        { id: 'overseas', label: '해외 주식', value: 0, color: 'bg-ai-cyan' },
        { id: 'coin', label: '코인', value: 0, color: 'bg-amber-400' },
        { id: 'cash', label: '현금', value: 100, color: 'bg-slate-500' }
      ]
    }

    const buckets = [
      { id: 'domestic', label: '국내 주식', amount: domesticValue, color: 'bg-blue-600' },
      { id: 'overseas', label: '해외 주식', amount: overseasValue, color: 'bg-ai-cyan' },
      { id: 'coin', label: '코인', amount: coinValue, color: 'bg-amber-400' },
      { id: 'cash', label: '현금', amount: cashValue, color: 'bg-slate-500' }
    ].map((item) => {
      const exactValue = (item.amount / allocationTotal) * 100
      return {
        ...item,
        value: Math.floor(exactValue),
        remainder: exactValue - Math.floor(exactValue),
      }
    })

    let remainingPercent = 100 - buckets.reduce((sum, item) => sum + item.value, 0)
    buckets
      .slice()
      .sort((a, b) => b.remainder - a.remainder)
      .forEach((item) => {
        if (remainingPercent <= 0) return
        item.value += 1
        remainingPercent -= 1
      })

    return buckets.map(({ id, label, value, color }) => ({ id, label, value, color }))
  }

  const allocation = getAllocationData()
  const filteredBalanceAccounts = rawBalances.filter((item) => showMockAssets || item.env !== 'MOCK')
  const accountCashSummaries = filteredBalanceAccounts.map((item) => ({
    key: `${item.raw_exchange || item.exchange}-${item.env}`,
    label: getAccountDisplayLabel(item),
    tone: getAccountTone(item.raw_exchange || item.exchange),
    entries: buildCashEntriesFromItem(item),
    availableCash: item.available_cash,
    availableCashCurrency: item.available_cash_currency || item.currency || 'KRW',
    exchangeRate: item.exchange_rate || balance?.exchange_rate || 1500,
    source: item.available_cash_source || '',
    supported: item.available_cash !== null && item.available_cash !== undefined && item.available_cash !== '',
  }))

  return (
    <div className="min-h-screen bg-obsidian-bg text-[#e2e2ec] font-inter">
      <div className="flex min-h-screen flex-col lg:flex-row">
        <SidebarNav
          activeTab={activeTab}
          isOpen={isSidebarOpen}
          isLoggedIn={isLoggedIn}
          onClose={() => setIsSidebarOpen(false)}
          onOpen={() => setIsSidebarOpen(true)}
          onTabChange={setActiveTab}
        />

        <div className={`min-w-0 flex-1 px-6 py-8 ${!isSidebarOpen ? 'pt-20 lg:pt-8' : ''}`}>
          {/* 공통 통합 헤더 네비게이션 */}
          <Header isLoggedIn={isLoggedIn} userEmail={userEmail} handleLogout={handleLogout} userProfile={userProfile} />

          {/* 메인 레이아웃 2단 그리드 */}
          {activeTab === 'dashboard' && (
            <main className="max-w-7xl mx-auto flex flex-col gap-6">

              {/* 계정 필터 및 통화 단위 토글 스위치 영역 */}
              <div className="flex flex-col sm:flex-row sm:justify-between sm:items-center gap-3 mb-1 bg-slate-surface/40 border border-slate-800/60 p-3 rounded-lg">
                {/* 실시간 적용 환율 상태 모니터링 뱃지 */}
                <div className="flex items-center gap-2 text-xs text-slate-400 font-sans">
                  <span className={`w-1.5 h-1.5 rounded-full ${(!balance?.exchange_rate || balance.exchange_rate === 1500) ? 'bg-amber-400' : 'bg-[#38bdf8] animate-pulse'}`} />
                  <span className="font-bold">적용 환율:</span>
                  <span className="font-mono font-bold text-white">
                    ₩{toNumber(balance?.exchange_rate || 1500).toLocaleString(undefined, { maximumFractionDigits: 1 })}
                  </span>
                  {(!balance?.exchange_rate || balance.exchange_rate === 1500) ? (
                    <span className="px-1.5 py-0.5 rounded bg-amber-500/10 border border-amber-500/20 text-[10px] font-bold text-amber-400">
                      임시 고정 환율 적용됨
                    </span>
                  ) : (
                    <span className="px-1.5 py-0.5 rounded bg-emerald-500/10 border border-emerald-500/20 text-[10px] font-bold text-emerald-400">
                      실시간 API (Live)
                    </span>
                  )}
                </div>

                <div className="flex items-center gap-3 self-end sm:self-auto">
                  {/* 모의계좌 포함 / 실거래 전용 필터 */}
                  <div className="inline-flex rounded-md bg-[#0f172a] p-1 border border-slate-700/80">
                    <button
                      onClick={() => setShowMockAssets(true)}
                      className={`px-3 py-1 text-xs font-bold rounded transition-all cursor-pointer ${showMockAssets
                          ? 'bg-slate-700 text-white shadow'
                          : 'text-slate-400 hover:text-white'
                        }`}
                      type="button"
                    >
                      모의계좌 포함
                    </button>
                    <button
                      onClick={() => setShowMockAssets(false)}
                      className={`px-3 py-1 text-xs font-bold rounded transition-all cursor-pointer ${!showMockAssets
                          ? 'bg-slate-700 text-white shadow'
                          : 'text-slate-400 hover:text-white'
                        }`}
                      type="button"
                    >
                      실거래 전용
                    </button>
                  </div>

                  {/* 원화/달러 보기 토글 스위치 */}
                  <div className="inline-flex rounded-md bg-[#0f172a] p-1 border border-slate-700/80">
                    <button
                      onClick={() => setDisplayCurrency('USD')}
                      className={`px-3 py-1 text-xs font-bold rounded transition-all cursor-pointer ${displayCurrency === 'USD'
                          ? 'bg-slate-700 text-white shadow'
                          : 'text-slate-400 hover:text-white'
                        }`}
                      type="button"
                    >
                      $
                    </button>
                    <button
                      onClick={() => setDisplayCurrency('KRW')}
                      className={`px-3 py-1 text-xs font-bold rounded transition-all cursor-pointer ${displayCurrency === 'KRW'
                          ? 'bg-slate-700 text-white shadow'
                          : 'text-slate-400 hover:text-white'
                        }`}
                      type="button"
                    >
                      원
                    </button>
                  </div>
                </div>
              </div>

              {/* 자산 요약 카드 */}
              <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                <div className="bg-slate-surface border border-slate-700/80 rounded-lg p-5">
                  <span className="text-xs font-bold text-slate-400">총 평가 자산 ({balance?.currency || 'KRW'})</span>
                  <div className="text-xl font-bold font-mono text-white mt-1">
                    {balanceLoading ? '조회 중' : formatCurrency(balance?.total_evaluation, balance?.currency, 'KRW', balance?.exchange_rate)}
                  </div>
                </div>

                <div className="bg-slate-surface border border-slate-700/80 rounded-lg p-5">
                  <div className="flex items-start justify-between gap-3">
                    <span className="text-xs font-bold text-slate-400">가용 예수금 (KRW)</span>
                    <button
                      type="button"
                      onClick={() => setIsCashDetailModalOpen(true)}
                      className="rounded border border-slate-700 px-2 py-1 text-[10px] font-bold text-slate-300 transition hover:border-cyan-500/40 hover:text-white"
                    >
                      상세 보기
                    </button>
                  </div>
                  <div className="text-xl font-bold font-mono text-white mt-1">
                    {balanceLoading ? '조회 중' : formatNullableCurrency(balance?.available_cash, balance?.currency, 'KRW', balance?.exchange_rate)}
                  </div>
                  {balance?.cash_unavailable_sources?.length > 0 ? (
                    <p className="mt-2 text-[11px] leading-5 text-amber-300/90">
                      일부 계좌 예수금은 아직 합산되지 않았습니다: {balance.cash_unavailable_sources.join(', ')}
                    </p>
                  ) : null}
                </div>

                <div className="bg-slate-surface border border-slate-700/80 rounded-lg p-5">
                  <span className="text-xs font-bold text-slate-400">포트폴리오 수익률</span>
                  <div className="mt-1">
                    <Rate value={formatSignedRate(getPortfolioProfitRate(balance))} />
                  </div>
                </div>
              </div>

              {balanceError ? (
                <div className="whitespace-pre-line rounded-lg border border-amber-500/30 bg-amber-500/10 px-4 py-3 text-xs font-semibold text-amber-200">
                  {balanceError}
                </div>
              ) : null}

              {/* 자산 배분 상태 및 관심 종목 그리드 */}
              <div className="grid grid-cols-1 md:grid-cols-12 gap-6">

                {/* 자산 배분 상태 (Allocation) */}
                <div className="bg-slate-surface border border-slate-700/80 rounded-lg p-5 md:col-span-5 flex flex-col gap-4">
                  <SectionHeader title="자산 배분 상태" />
                  <div className="flex h-3.5 overflow-hidden rounded-full bg-[#0c0e15] border border-slate-800">
                    {allocation.map((item) => (
                      <span key={item.id} className={`${item.color} h-full transition-all`} style={{ width: `${item.value}%` }} />
                    ))}
                  </div>
                  <div className="flex flex-col gap-2">
                    {allocation.map((item) => (
                      <div key={item.id} className="flex items-center justify-between rounded bg-[#0c0e15]/40 px-3 py-2 border border-slate-800/40 text-xs">
                        <span className="flex items-center gap-2 font-bold">
                          <span className={`w-2 h-2 rounded-full ${item.color}`} />
                          {item.label}
                        </span>
                        <span className="font-mono font-bold text-slate-300">{item.value}%</span>
                      </div>
                    ))}
                  </div>
                </div>

                {/* 관심 종목 명단 */}
                <div className="bg-slate-surface border border-slate-700/80 rounded-lg p-5 md:col-span-7 flex flex-col gap-3">
                  <div className="mb-1 flex items-start justify-between gap-3">
                    <h2 className="text-sm font-bold text-white uppercase tracking-wider">관심 종목 명단 (시세 모니터링)</h2>
                    <div className="flex shrink-0 gap-2">
                      <button
                        className="inline-flex items-center gap-1 rounded border border-slate-700 px-2 py-1 text-[10px] font-bold text-slate-400 transition-all hover:border-ai-cyan hover:text-white disabled:cursor-not-allowed disabled:opacity-50"
                        type="button"
                        disabled={watchlistLoading || watchlistRefreshCooldown > 0}
                        onClick={() => loadDashboardWatchlist({ manual: true })}
                      >
                        <RefreshIcon className={`h-3 w-3 ${watchlistLoading ? 'animate-spin' : ''}`} />
                        {watchlistLoading
                          ? '갱신 중'
                          : watchlistRefreshCooldown > 0
                            ? `${watchlistRefreshCooldown}초`
                            : '새로 고침'}
                      </button>
                      <button
                        className="rounded border border-slate-700 px-2 py-1 text-[10px] font-bold text-slate-400 transition-all hover:border-ai-cyan hover:text-white"
                        type="button"
                        onClick={() => setActiveTab('watchlist')}
                      >
                        관리
                      </button>
                    </div>
                  </div>
                  <div className="overflow-x-auto max-h-[180px] overflow-y-auto">
                    <table className="w-full border-collapse text-xs">
                      <thead className="border-b border-slate-800 text-slate-400 bg-[#0c0e15]/50 sticky top-0">
                        <tr>
                          <th className="px-3 py-2 text-left font-bold">종목명</th>
                          <th className="px-3 py-2 text-left font-bold">시장</th>
                          <th className="px-3 py-2 text-right font-bold">저장 당시 가격</th>
                          <th className="px-3 py-2 text-right font-bold">현재가</th>
                          <th className="px-3 py-2 text-right font-bold">현재가 변동</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-slate-800/40">
                        {dashboardWatchlist.map((item) => {
                          const stockCurrency = item.currency || (item.marketCountry === 'US' ? 'USD' : 'KRW')
                          const savedPrice = parsePriceNumber(item.latestPrice ?? item.average)
                          const currentPrice = getWatchlistCurrentPrice(item) ?? savedPrice
                          const hasSavedPrice = Number.isFinite(savedPrice) && savedPrice > 0
                          const hasCurrentPrice = Number.isFinite(currentPrice)
                          const priceDelta = hasSavedPrice && hasCurrentPrice ? currentPrice - savedPrice : 0
                          const priceDeltaRate = hasSavedPrice ? (priceDelta / savedPrice) * 100 : 0
                          const priceDeltaTone = priceDelta > 0 ? 'text-red-400' : priceDelta < 0 ? 'text-blue-400' : 'text-white'
                          const signedDeltaAmount = `${priceDelta > 0 ? '+' : priceDelta < 0 ? '-' : ''}${formatUnitCurrency(Math.abs(priceDelta), stockCurrency, stockCurrency === 'USD' || stockCurrency === 'USDT' ? displayCurrency : 'KRW', balance?.exchange_rate || 1380)}`
                          const signedDeltaRate = `${priceDeltaRate > 0 ? '+' : ''}${priceDeltaRate.toFixed(2)}%`
                          const exchangeRate = balance?.exchange_rate || 1380
                          const currentDisplayCurrency = stockCurrency === 'USD' || stockCurrency === 'USDT' ? displayCurrency : 'KRW'
                          return (
                            <tr key={item.id} className="hover:bg-slate-800/20 transition-colors">
                              <td className="px-3 py-2.5 font-bold text-white">{item.name}</td>
                              <td className="px-3 py-2.5 text-slate-400">{item.market}</td>
                              <td className="px-3 py-2.5 text-right font-mono text-slate-300">
                                {hasSavedPrice ? formatUnitCurrency(savedPrice, stockCurrency, currentDisplayCurrency, exchangeRate) : '-'}
                              </td>
                              <td className="px-3 py-2.5 text-right font-mono text-slate-300">
                                {hasCurrentPrice ? formatUnitCurrency(currentPrice, stockCurrency, currentDisplayCurrency, exchangeRate) : '-'}
                              </td>
                              <td className={`px-3 py-2.5 text-right font-mono font-bold ${priceDeltaTone}`}>
                                {hasSavedPrice && hasCurrentPrice ? `${signedDeltaAmount} (${signedDeltaRate})` : '-'}
                              </td>
                            </tr>
                          )
                        })}
                        {!watchlistLoading && dashboardWatchlist.length === 0 ? (
                          <tr>
                            <td className="px-3 py-8 text-center text-slate-500" colSpan={5}>
                              관심종목이 없습니다. 하트를 눌러 관심 종목을 추가해주세요.
                            </td>
                          </tr>
                        ) : null}
                      </tbody>
                    </table>
                    {watchlistError ? <p className="mt-2 whitespace-pre-line text-xs text-red-300">{watchlistError}</p> : null}
                  </div>
                </div>

              </div>

              {/* 보유 재산 현황 (실제 holdings 연동 테이블) */}
              <div className="bg-slate-surface border border-slate-700/80 rounded-lg p-6 flex flex-col gap-4">
                <div className="flex justify-between items-center border-b border-slate-800 pb-2">
                  <h2 className="text-sm font-bold text-white flex items-center gap-2 uppercase tracking-wider">
                    <span />
                    보유 주식 자산 현황
                  </h2>
                  <button
                    type="button"
                    onClick={handleBalanceRefresh}
                    disabled={!isLoggedIn || balanceLoading || balanceRefreshCooldown > 0}
                    className="inline-flex items-center gap-1 text-xs border border-slate-700 hover:border-ai-cyan hover:text-white rounded px-2.5 py-1 text-slate-300 font-medium transition-all cursor-pointer disabled:cursor-not-allowed disabled:opacity-50"
                  >
                    <RefreshIcon className={`h-3.5 w-3.5 ${balanceLoading ? 'animate-spin' : ''}`} />
                    {balanceLoading
                      ? '갱신 중'
                      : balanceRefreshCooldown > 0
                        ? `${balanceRefreshCooldown}초`
                        : '새로 고침'}
                  </button>
                </div>

                {balance && balance.holdings.length > 0 ? (
                  <div className="overflow-x-auto">
                    <table className="w-full text-left border-collapse text-xs">
                      <thead>
                        <tr className="border-b border-slate-800 text-slate-400 bg-[#0c0e15]/30">
                          <th className="py-2 px-3 font-bold">종목명/코드</th>
                          <th className="py-2 px-3 font-bold">거래소</th>
                          <th className="py-2 px-3 text-right font-bold">
                            보유수량
                            <button onClick={() => handleHoldingsSort('qty')} className="inline-flex flex-col ml-1 align-middle text-[8px] leading-[6px] text-slate-500 hover:text-white cursor-pointer select-none">
                              <span className={holdingsSort.key === 'qty' && holdingsSort.direction === 'asc' ? 'text-ai-cyan' : ''}>▲</span>
                              <span className={holdingsSort.key === 'qty' && holdingsSort.direction === 'desc' ? 'text-ai-cyan' : ''}>▼</span>
                            </button>
                          </th>
                          <th className="py-2 px-3 text-right font-bold">평균단가</th>
                          <th className="py-2 px-3 text-right font-bold">현재가</th>
                          <th className="py-2 px-3 text-right font-bold">
                            평가손익
                            <button onClick={() => handleHoldingsSort('profit')} className="inline-flex flex-col ml-1 align-middle text-[8px] leading-[6px] text-slate-500 hover:text-white cursor-pointer select-none">
                              <span className={holdingsSort.key === 'profit' && holdingsSort.direction === 'asc' ? 'text-ai-cyan' : ''}>▲</span>
                              <span className={holdingsSort.key === 'profit' && holdingsSort.direction === 'desc' ? 'text-ai-cyan' : ''}>▼</span>
                            </button>
                          </th>
                          <th className="py-2 px-3 text-right font-bold">
                            수익률
                            <button onClick={() => handleHoldingsSort('profit_rate')} className="inline-flex flex-col ml-1 align-middle text-[8px] leading-[6px] text-slate-500 hover:text-white cursor-pointer select-none">
                              <span className={holdingsSort.key === 'profit_rate' && holdingsSort.direction === 'asc' ? 'text-ai-cyan' : ''}>▲</span>
                              <span className={holdingsSort.key === 'profit_rate' && holdingsSort.direction === 'desc' ? 'text-ai-cyan' : ''}>▼</span>
                            </button>
                          </th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-slate-800 font-mono">
                        {getSortedHoldings(balance.holdings).map((stock, index) => {
                          const exchangeName = stock.exchange || stock.account_type || '-'
                          const isCoinone = String(exchangeName).toUpperCase() === 'COINONE'
                          const isForeign = /[a-zA-Z]/.test(stock.symbol) && !/^[0-9a-zA-Z]{6,7}$/.test(stock.symbol) && !isCoinone
                          const stockCurrency = stock.currency || (isForeign ? 'USD' : 'KRW')
                          const exchangeRate = balance.exchange_rate || 1380
                          const currentDisplayCurrency = isForeign ? displayCurrency : 'KRW'
                          const profitRate = Number(stock.profit_rate)

                          return (
                            <tr key={`${exchangeName}-${stock.env || 'REAL'}-${stock.symbol}-${index}`} className="hover:bg-slate-800/40 transition-colors">
                              <td className="py-3 px-3 font-sans">
                                <div className="font-semibold text-white">{stock.name}</div>
                                <div className="text-[10px] text-slate-500 font-mono">{stock.symbol}</div>
                              </td>
                              <td className="py-3 px-3 text-left font-sans font-bold text-slate-400">
                                <span className="rounded bg-slate-800/60 border border-slate-700/60 px-1.5 py-0.5 text-[10px] uppercase">
                                  {exchangeName}
                                </span>
                              </td>
                              <td className="py-3 px-3 text-right text-slate-300">{stock.qty}</td>
                              <td className="py-3 px-3 text-right text-slate-300">
                                {formatUnitCurrency(stock.avg_price, stockCurrency, currentDisplayCurrency, exchangeRate)}
                              </td>
                              <td className="py-3 px-3 text-right text-slate-100">
                                {formatUnitCurrency(stock.current_price, stockCurrency, currentDisplayCurrency, exchangeRate)}
                              </td>
                              <td className={`py-3 px-3 text-right font-semibold ${stock.profit > 0 ? 'text-red-400' : stock.profit < 0 ? 'text-blue-400' : 'text-white'}`}>
                                {stock.profit > 0 ? '+' : ''}{formatCurrency(stock.profit, stockCurrency, currentDisplayCurrency, exchangeRate)}
                              </td>
                              <td className={`py-3 px-3 text-right font-semibold`}>
                                <Rate value={(profitRate >= 0 ? '+' : '') + (Number.isFinite(profitRate) ? profitRate.toFixed(2) : '0.00') + '%'} />
                              </td>
                            </tr>
                          )
                        })}
                      </tbody>
                    </table>
                  </div>
                ) : (
                  <div className="flex-1 flex flex-col justify-center items-center py-16 text-center">
                    <svg className="w-12 h-12 text-slate-600 mb-3" fill="none" stroke="currentColor" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.5" d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z"></path>
                    </svg>
                    <p className="text-xs font-semibold text-slate-400">대시보드 자산 데이터가 비활성화되어 있습니다.</p>
                    <p className="text-[11px] text-slate-500 mt-1 max-w-sm">백엔드에서 계좌 자산 데이터가 연결되면 보유 종목과 평가 손익이 표시됩니다.</p>
                  </div>
                )}
              </div>
            </main>
          )}

          {isCashDetailModalOpen ? (
            <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/75 px-4 py-8 backdrop-blur-sm">
              <div className="w-full max-w-4xl rounded-2xl border border-slate-700/80 bg-[#0b1220] p-5 shadow-2xl">
                <div className="flex items-start justify-between gap-4 border-b border-slate-800 pb-3">
                  <div>
                    <p className="text-[10px] font-bold uppercase tracking-[0.18em] text-cyan-300">Cash Detail</p>
                    <h2 className="mt-1 text-base font-bold text-white">거래소별 + 통화별 예수금 상세</h2>
                    <p className="mt-1 text-xs text-slate-400">토스는 공식 `buying-power`, 한투는 계좌 예수금 응답 기준으로 표시합니다.</p>
                  </div>
                  <button
                    type="button"
                    onClick={() => setIsCashDetailModalOpen(false)}
                    className="rounded border border-slate-700 px-3 py-1.5 text-xs font-bold text-slate-300 transition hover:border-cyan-500/40 hover:text-white"
                  >
                    닫기
                  </button>
                </div>
                <div className="mt-4 overflow-x-auto">
                  <table className="w-full border-collapse text-xs">
                    <thead className="border-b border-slate-800 bg-[#0c0e15]/60 text-slate-400">
                      <tr>
                        <th className="px-3 py-2 text-left font-bold">계좌</th>
                        <th className="px-3 py-2 text-left font-bold">통화</th>
                        <th className="px-3 py-2 text-right font-bold">원금액</th>
                        <th className="px-3 py-2 text-right font-bold">KRW 환산</th>
                        <th className="px-3 py-2 text-left font-bold">소스</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-800/50">
                      {accountCashSummaries.flatMap((account) => (
                        account.entries.length > 0
                          ? account.entries.map((entry, index) => (
                            <tr key={`${account.key}-${entry.currency}-${index}`} className="hover:bg-slate-900/40">
                              <td className="px-3 py-3 font-bold text-white">{account.label}</td>
                              <td className="px-3 py-3 text-slate-300">{entry.currency}</td>
                              <td className="px-3 py-3 text-right font-mono text-slate-200">{formatNativeCurrency(entry.amount, entry.currency)}</td>
                              <td className="px-3 py-3 text-right font-mono text-cyan-300">
                                {formatCurrency(entry.amount, entry.currency, 'KRW', account.exchangeRate)}
                              </td>
                              <td className="px-3 py-3 text-slate-500">{account.source || '-'}</td>
                            </tr>
                          ))
                          : [{
                            key: `${account.key}-empty`,
                            label: account.label,
                            source: account.source || '-',
                          }].map((empty) => (
                            <tr key={empty.key} className="hover:bg-slate-900/40">
                              <td className="px-3 py-3 font-bold text-white">{empty.label}</td>
                              <td className="px-3 py-3 text-slate-500" colSpan={3}>표시 가능한 통화별 예수금 없음</td>
                              <td className="px-3 py-3 text-slate-500">{empty.source}</td>
                            </tr>
                          ))
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            </div>
          ) : null}

          {activeTab === 'watchlist' && <WatchlistTab displayCurrency={displayCurrency} exchangeRate={balance?.exchange_rate} />}
          {activeTab === 'assets' && <AssetsTab balance={balance} allocation={allocation} displayCurrency={displayCurrency} exchangeRate={balance?.exchange_rate} showMockAssets={showMockAssets} />}
          {activeTab === 'history' && <TradeHistoryTab />}
          {activeTab === 'admin' && (
            <AdminMlData
              isLoggedIn={isLoggedIn}
              userEmail={userEmail}
              handleLogout={handleLogout}
              hideHeader={true}
            />
          )}
          {activeTab === 'settings' && (
            <Settings
              isLoggedIn={isLoggedIn}
              userEmail={userEmail}
              handleLogout={handleLogout}
              userProfile={userProfile}
              hideHeader={true}
            />
          )}
        </div>
      </div>
    </div>
  )
}
