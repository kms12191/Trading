import { useEffect, useState } from 'react'
import { fetchUserWatchlist, supabase } from '../supabaseClient'
import Header from '../components/Header.jsx'
import Settings from './Settings'
import { Rate, SectionHeader, SidebarNav } from '../components/DashboardComponents.jsx'
import WatchlistTab from './WatchlistTab.jsx'
import AssetsTab from './AssetsTab.jsx'
import TradeHistoryTab from './TradeHistoryTab.jsx'
import AdminMlData from './AdminMlData.jsx'

const DASHBOARD_API_BASE_URL = 'http://localhost:5050'
const BALANCE_EXCHANGE_ORDER = ['TOSS', 'KIS', 'COINONE', 'BINANCE']

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

  if (/DOMESTIC|KR|KRW|KOSPI|KOSDAQ|국내/.test(combined) || /^\d{6}$/.test(symbol)) {
    return 'domestic'
  }

  return /[A-Z]/.test(symbol) ? 'overseas' : 'domestic'
}

const getHoldingEvaluationKrw = (holding = {}, exchangeRate = 1500) => {
  const currency = String(holding.currency || '').toUpperCase()
  const rate = toNumber(exchangeRate) || 1500
  const rawValue = toNumber(holding.eval_amount) > 0
    ? toNumber(holding.eval_amount)
    : toNumber(holding.current_price) * toNumber(holding.qty)

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
  
  const holdings = filteredItems.flatMap((item) => {
    const exchange = item.exchange
    const rate = toNumber(item.exchange_rate) || representativeRate
    const itemCurrency = item.currency || 'KRW'
    
    let itemEval = toNumber(item.total_evaluation)
    let itemCash = toNumber(item.available_cash)
    
    if (itemCurrency === 'USD' || itemCurrency === 'USDT') {
      itemEval = itemEval * rate
      itemCash = itemCash * rate
    }
    
    totalEvaluationKrw += itemEval
    availableCashKrw += itemCash
    
    return (item.holdings || []).map((holding) => ({
      ...holding,
      exchange: holding.exchange || exchange,
      account_type: holding.account_type || exchange,
      env: item.env || 'REAL',
    }))
  })

  return {
    total_evaluation: totalEvaluationKrw,
    available_cash: availableCashKrw,
    currency: 'KRW', // 통합 잔고는 항상 KRW 기준
    exchange_rate: representativeRate,
    holdings,
    sources: filteredItems.map((item) => item.exchange),
  }
}

const getBalanceRequestLabel = (exchange, env) => {
  if (exchange === 'KIS') {
    return `KIS ${env === 'REAL' ? '실전' : '모의'}`
  }

  return exchange
}

const buildBalanceRequests = (keyStatus) =>
  BALANCE_EXCHANGE_ORDER.flatMap((exchange) => {
    const status = keyStatus[exchange]
    if (!status?.registered) return []

    const accounts = Array.isArray(status.accounts) && status.accounts.length > 0
      ? status.accounts
      : [status]

    return accounts.map((account) => {
      const env = String(account?.broker_env || status.broker_env || (exchange === 'KIS' ? 'MOCK' : 'REAL')).toUpperCase()
      return {
        exchange,
        env,
        label: getBalanceRequestLabel(exchange, env),
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
  const [dashboardWatchlist, setDashboardWatchlist] = useState([])
  const [watchlistLoading, setWatchlistLoading] = useState(false)
  const [watchlistError, setWatchlistError] = useState('')

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
        setMessage({ text: resData.message || 'Key validation failed.', isError: true })
      }
    } catch (error) {
      setMessage({ text: `Failed to connect to backend server: ${error.message}`, isError: true })
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
        throw new Error(statusPayload.message || '계정 API 연동 상태를 불러오지 못했습니다.')
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
              return {
                exchange: label,
                env,
                error: payload.message || `${exchange} 잔고 조회 실패`,
              }
            }

            return { ...payload.data, exchange: label, raw_exchange: exchange, env }
          } catch (error) {
            return {
              exchange: label,
              env,
              error: error.message || `${exchange} 잔고 조회 실패`,
            }
          }
        }),
      )

      const failedResults = results.filter((item) => item?.error)
      const successResults = results.filter((item) => !item?.error)
      setRawBalances(successResults)
      const mergedBalance = mergeAccountBalances(successResults, showMockAssets)
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
      setBalance(null)
      setBalanceError(`계정 자산 조회 실패: ${error.message}`)
    } finally {
      setBalanceLoading(false)
    }
  }

  useEffect(() => {
    loadAccountBalance()
  }, [isLoggedIn])

  useEffect(() => {
    loadDashboardWatchlist()
  }, [isLoggedIn, activeTab])

  const loadDashboardWatchlist = async () => {
    if (!isLoggedIn) {
      setDashboardWatchlist([])
      setWatchlistError('')
      return
    }

    setWatchlistLoading(true)
    setWatchlistError('')
    try {
      const items = await fetchUserWatchlist()
      setDashboardWatchlist(items)
    } catch (error) {
      setDashboardWatchlist([])
      setWatchlistError(error.message || '관심종목을 불러오지 못했습니다.')
    } finally {
      setWatchlistLoading(false)
    }
  }

  useEffect(() => {
    if (rawBalances.length > 0) {
      setBalance(mergeAccountBalances(rawBalances, showMockAssets))
    }
  }, [rawBalances, showMockAssets])

  const refreshBalance = async () => {
    if (!encrypted) {
      await loadAccountBalance()
      return
    }

    setLoading(true)
    try {
      const response = await fetch('http://localhost:5050/api/dashboard/balance', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          ...encrypted,
          env: inputs.env
        })
      })
      const resData = await response.json()
      if (resData.success) {
        const freshData = { ...resData.data, exchange: encrypted.exchange || 'KIS', env: inputs.env }
        setRawBalances([freshData])
        setBalance(mergeAccountBalances([freshData], showMockAssets))
      } else {
        setMessage({ text: resData.message || 'Failed to refresh balance.', isError: true })
      }
    } catch (error) {
      setMessage({ text: `Refresh error: ${error.message}`, isError: true })
    } finally {
      setLoading(false)
    }
  }

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

  return (
    <div className="min-h-screen bg-obsidian-bg text-[#e2e2ec] font-inter">
      <div className="flex min-h-screen flex-col lg:flex-row">
        <SidebarNav
          activeTab={activeTab}
          isOpen={isSidebarOpen}
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
                      className={`px-3 py-1 text-xs font-bold rounded transition-all cursor-pointer ${
                        showMockAssets
                          ? 'bg-slate-700 text-white shadow'
                          : 'text-slate-400 hover:text-white'
                      }`}
                      type="button"
                    >
                      모의계좌 포함
                    </button>
                    <button
                      onClick={() => setShowMockAssets(false)}
                      className={`px-3 py-1 text-xs font-bold rounded transition-all cursor-pointer ${
                        !showMockAssets
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
                      className={`px-3 py-1 text-xs font-bold rounded transition-all cursor-pointer ${
                        displayCurrency === 'USD'
                          ? 'bg-slate-700 text-white shadow'
                          : 'text-slate-400 hover:text-white'
                      }`}
                      type="button"
                    >
                      $
                    </button>
                    <button
                      onClick={() => setDisplayCurrency('KRW')}
                      className={`px-3 py-1 text-xs font-bold rounded transition-all cursor-pointer ${
                        displayCurrency === 'KRW'
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
                  <span className="text-xs font-bold text-slate-400">가용 예수금 (KRW)</span>
                  <div className="text-xl font-bold font-mono text-white mt-1">
                    {balanceLoading ? '조회 중' : formatCurrency(balance?.available_cash, balance?.currency, 'KRW', balance?.exchange_rate)}
                  </div>
                </div>

                <div className="bg-slate-surface border border-slate-700/80 rounded-lg p-5">
                  <span className="text-xs font-bold text-slate-400">포트폴리오 수익률</span>
                  <div className="mt-1">
                    <Rate value={formatSignedRate(getPortfolioProfitRate(balance))} />
                  </div>
                </div>
              </div>

              {balanceError ? (
                <div className="rounded-lg border border-amber-500/30 bg-amber-500/10 px-4 py-3 text-xs font-semibold text-amber-200">
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
                        className="rounded border border-slate-700 px-2 py-1 text-[10px] font-bold text-slate-400 transition-all hover:border-ai-cyan hover:text-white disabled:cursor-not-allowed disabled:opacity-50"
                        type="button"
                        disabled={watchlistLoading}
                        onClick={loadDashboardWatchlist}
                      >
                        {watchlistLoading ? '갱신 중' : '새로 고침'}
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
                          const signedDeltaAmount = `${priceDelta > 0 ? '+' : priceDelta < 0 ? '-' : ''}${formatCurrency(Math.abs(priceDelta), stockCurrency, stockCurrency === 'USD' || stockCurrency === 'USDT' ? displayCurrency : 'KRW', balance?.exchange_rate || 1380)}`
                          const signedDeltaRate = `${priceDeltaRate > 0 ? '+' : ''}${priceDeltaRate.toFixed(2)}%`
                          const exchangeRate = balance?.exchange_rate || 1380
                          const currentDisplayCurrency = stockCurrency === 'USD' || stockCurrency === 'USDT' ? displayCurrency : 'KRW'
                          return (
                            <tr key={item.id} className="hover:bg-slate-800/20 transition-colors">
                              <td className="px-3 py-2.5 font-bold text-white">{item.name}</td>
                              <td className="px-3 py-2.5 text-slate-400">{item.market}</td>
                              <td className="px-3 py-2.5 text-right font-mono text-slate-300">
                                {hasSavedPrice ? formatCurrency(savedPrice, stockCurrency, currentDisplayCurrency, exchangeRate) : '-'}
                              </td>
                              <td className="px-3 py-2.5 text-right font-mono text-slate-300">
                                {hasCurrentPrice ? formatCurrency(currentPrice, stockCurrency, currentDisplayCurrency, exchangeRate) : '-'}
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
                    {watchlistError ? <p className="mt-2 text-xs text-red-300">{watchlistError}</p> : null}
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
                  {encrypted && (
                    <button
                      onClick={refreshBalance}
                      disabled={loading}
                      className="text-xs border border-slate-700 hover:border-slate-500 rounded px-2.5 py-1 text-slate-300 font-medium transition-all cursor-pointer disabled:opacity-50"
                    >
                      {loading ? 'LOADING...' : 'REFRESH'}
                    </button>
                  )}
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
                          const isForeign = /[a-zA-Z]/.test(stock.symbol)
                          const stockCurrency = stock.currency || (isForeign ? 'USD' : 'KRW')
                          const exchangeRate = balance.exchange_rate || 1380
                          const currentDisplayCurrency = isForeign ? displayCurrency : 'KRW'
                          const exchangeName = stock.exchange || stock.account_type || '-'

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
                                {formatCurrency(stock.avg_price, stockCurrency, currentDisplayCurrency, exchangeRate)}
                              </td>
                              <td className="py-3 px-3 text-right text-slate-100">
                                {formatCurrency(stock.current_price, stockCurrency, currentDisplayCurrency, exchangeRate)}
                              </td>
                              <td className={`py-3 px-3 text-right font-semibold ${stock.profit > 0 ? 'text-red-400' : stock.profit < 0 ? 'text-blue-400' : 'text-white'}`}>
                                {stock.profit > 0 ? '+' : ''}{formatCurrency(stock.profit, stockCurrency, currentDisplayCurrency, exchangeRate)}
                              </td>
                              <td className={`py-3 px-3 text-right font-semibold`}>
                                <Rate value={(stock.profit_rate >= 0 ? '+' : '') + stock.profit_rate.toFixed(2) + '%'} />
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
