import { useEffect, useState } from 'react'
import { supabase } from '../supabaseClient'
import Header from '../components/Header.jsx'
import Settings from './Settings'
import { ASSET_PERIOD_OPTIONS, WATCHLIST_MOCK } from '../dashboardConstants.js'
import { Rate, SectionHeader, SidebarNav, Sparkline } from '../components/DashboardComponents.jsx'
import { getAssetPeriodRange } from '../dashboardUtils.js'
import WatchlistTab from './WatchlistTab.jsx'
import AssetsTab from './AssetsTab.jsx'
import TradeHistoryTab from './TradeHistoryTab.jsx'

const DASHBOARD_API_BASE_URL = 'http://localhost:5050'
const BALANCE_EXCHANGE_ORDER = ['TOSS', 'KIS', 'COINONE', 'BINANCE']

const toNumber = (value) => {
  const numericValue = Number(value)
  return Number.isFinite(numericValue) ? numericValue : 0
}

const formatKrw = (value) => `₩${Math.round(toNumber(value)).toLocaleString()}`

const formatSignedRate = (value) => {
  const numericValue = toNumber(value)
  return `${numericValue >= 0 ? '+' : ''}${numericValue.toFixed(2)}%`
}

const getTrendPointValue = (item) => toNumber(item?.total_evaluation ?? item?.value)

const getTrendPointTime = (item) => item?.snapshot_at || item?.snapshot_date || item?.date || ''

const buildCurrentBalanceTrend = (currentValue, periodKey) => {
  const pointCount = periodKey === '1h' ? 6 : periodKey === '1d' ? 8 : periodKey === '1w' ? 7 : 8
  return Array.from({ length: pointCount }, () => toNumber(currentValue))
}

const buildFallbackTrendLabels = (periodKey) => {
  const now = new Date()
  const count = periodKey === '1h' ? 6 : periodKey === '1d' ? 8 : periodKey === '1w' ? 7 : 8
  const stepMs = periodKey === '1h'
    ? 10 * 60 * 1000
    : periodKey === '1d'
      ? 3 * 60 * 60 * 1000
      : periodKey === '1w'
        ? 24 * 60 * 60 * 1000
        : 4 * 24 * 60 * 60 * 1000

  return Array.from({ length: count }, (_, index) => {
    const value = new Date(now.getTime() - (count - 1 - index) * stepMs)
    return formatTrendAxisLabel(value.toISOString(), periodKey)
  })
}

const formatTrendAxisLabel = (value, periodKey) => {
  if (!value) return ''
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return String(value).slice(5, 10)

  if (periodKey === '1h' || periodKey === '1d') {
    return date.toLocaleTimeString('ko-KR', { hour: '2-digit', minute: '2-digit' })
  }

  return date.toLocaleDateString('ko-KR', { month: '2-digit', day: '2-digit' })
}

const getTrendQueryRange = (periodKey, dateRange) => {
  const end = new Date()
  const start = new Date(end)

  if (periodKey === 'custom') {
    const customStart = dateRange.start ? new Date(`${dateRange.start}T00:00:00`) : start
    const customEnd = dateRange.end ? new Date(`${dateRange.end}T23:59:59`) : end
    return { start: customStart.toISOString(), end: customEnd.toISOString() }
  }

  if (periodKey === '1h') {
    start.setHours(end.getHours() - 1)
  } else if (periodKey === '1d') {
    start.setDate(end.getDate() - 1)
  } else if (periodKey === '1w') {
    start.setDate(end.getDate() - 7)
  } else {
    start.setMonth(end.getMonth() - 1)
  }

  return { start: start.toISOString(), end: end.toISOString() }
}

const formatTrendDelta = (values) => {
  if (!values.length) return '+0'
  const delta = values[values.length - 1] - values[0]
  return `${delta >= 0 ? '+' : '-'}${formatKrw(Math.abs(delta))}`
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

const mergeAccountBalances = (items) => {
  const validItems = items.filter(Boolean)
  const holdings = validItems.flatMap((item) =>
    (item.holdings || []).map((holding) => ({
      ...holding,
      exchange: holding.exchange || item.exchange,
      account_type: holding.account_type || item.exchange,
    })),
  )

  return {
    total_evaluation: validItems.reduce((sum, item) => sum + toNumber(item.total_evaluation), 0),
    available_cash: validItems.reduce((sum, item) => sum + toNumber(item.available_cash), 0),
    holdings,
    sources: validItems.map((item) => item.exchange),
  }
}

export default function Dashboard({ isLoggedIn, userEmail, handleLogout, userProfile, setUserProfile }) {
  const [inputs, setInputs] = useState({
    appkey: '',
    appsecret: '',
    cano: '',
    env: 'MOCK'
  })
  const [activeTab, setActiveTab] = useState('dashboard')
  const [isSidebarOpen, setIsSidebarOpen] = useState(true)
  const [selectedAssetPeriod, setSelectedAssetPeriod] = useState('1h')
  const [assetDateRange, setAssetDateRange] = useState(() => getAssetPeriodRange('1h'))
  const [isAssetCalendarOpen, setIsAssetCalendarOpen] = useState(false)

  const [encrypted, setEncrypted] = useState(null)
  const [loading, setLoading] = useState(false)
  const [message, setMessage] = useState({ text: '', isError: false })
  const [balance, setBalance] = useState(null)
  const [balanceLoading, setBalanceLoading] = useState(false)
  const [balanceError, setBalanceError] = useState('')
  const [assetTrendRows, setAssetTrendRows] = useState([])
  const [assetTrendLoading, setAssetTrendLoading] = useState(false)
  const [assetTrendSource, setAssetTrendSource] = useState('current-balance')

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
      const registeredExchanges = BALANCE_EXCHANGE_ORDER.filter((exchange) => keyStatus[exchange]?.registered)

      if (registeredExchanges.length === 0) {
        setBalance({ total_evaluation: 0, available_cash: 0, holdings: [], sources: [] })
        setBalanceError('등록된 거래소 API 키가 없습니다.')
        return
      }

      const results = await Promise.all(
        registeredExchanges.map(async (exchange) => {
          const env = keyStatus[exchange]?.broker_env || (exchange === 'KIS' ? 'MOCK' : 'REAL')
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
                exchange,
                error: payload.message || `${exchange} 잔고 조회 실패`,
              }
            }

            return { ...payload.data, exchange }
          } catch (error) {
            return {
              exchange,
              error: error.message || `${exchange} 잔고 조회 실패`,
            }
          }
        }),
      )

      const failedResults = results.filter((item) => item?.error)
      const mergedBalance = mergeAccountBalances(results.filter((item) => !item?.error))
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

  const loadAssetTrend = async () => {
    if (!isLoggedIn) {
      setAssetTrendRows([])
      setAssetTrendSource('current-balance')
      return
    }

    setAssetTrendLoading(true)

    try {
      const { data: { session } } = await supabase.auth.getSession()
      if (!session?.access_token) {
        setAssetTrendRows([])
        setAssetTrendSource('current-balance')
        return
      }

      const trendRange = getTrendQueryRange(selectedAssetPeriod, assetDateRange)
      const params = new URLSearchParams(trendRange)
      const response = await fetch(`${DASHBOARD_API_BASE_URL}/api/dashboard/asset-trend?${params.toString()}`, {
        headers: {
          Authorization: `Bearer ${session.access_token}`,
        },
      })
      const payload = await response.json()

      if (!response.ok || !payload.success) {
        throw new Error(payload.message || 'Asset trend request failed.')
      }

      const rows = payload.data?.items || []
      setAssetTrendRows(rows)
      setAssetTrendSource(rows.length > 0 ? payload.data?.source || 'portfolio_snapshots' : 'current-balance')
    } catch (error) {
      setAssetTrendRows([])
      setAssetTrendSource('current-balance')
    } finally {
      setAssetTrendLoading(false)
    }
  }

  useEffect(() => {
    loadAccountBalance()
  }, [isLoggedIn])

  useEffect(() => {
    loadAssetTrend()
  }, [isLoggedIn, selectedAssetPeriod, assetDateRange.start, assetDateRange.end])

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
        setBalance(resData.data)
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
      const isOverseas = /[A-Z]/.test(symbol) && !isCoin
      const stockEval = toNumber(stock.current_price) * toNumber(stock.qty)

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
  const assetTrendPoints = assetTrendRows.filter((item) => getTrendPointValue(item) > 0)
  const assetTrendDbValues = assetTrendPoints.map(getTrendPointValue)
  const assetTrendValues = assetTrendDbValues.length > 0
    ? assetTrendDbValues
    : buildCurrentBalanceTrend(balance?.total_evaluation, selectedAssetPeriod)
  const assetTrendLabels = assetTrendDbValues.length > 0
    ? assetTrendPoints.map((item) => formatTrendAxisLabel(getTrendPointTime(item), selectedAssetPeriod))
    : buildFallbackTrendLabels(selectedAssetPeriod)
  const assetTrendSummary = assetTrendSource === 'portfolio_snapshots'
    ? `${assetDateRange.start || '시작일'} ~ ${assetDateRange.end || '종료일'}`
    : `현재 계정 자산 기준 · ${assetDateRange.start || '시작일'} ~ ${assetDateRange.end || '종료일'}`
  const assetTrendDelta = formatTrendDelta(assetTrendValues)

  const handleAssetPeriodChange = (periodKey) => {
    setSelectedAssetPeriod(periodKey)
    setAssetDateRange(getAssetPeriodRange(periodKey))
  }

  const handleAssetDateChange = (field, value) => {
    setSelectedAssetPeriod('custom')
    setAssetDateRange((prev) => ({ ...prev, [field]: value }))
  }

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

              {/* 자산 요약 카드 */}
              <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                <div className="bg-slate-surface border border-slate-700/80 rounded-lg p-5">
                  <span className="text-xs font-bold text-slate-400">총 평가 자산 (KRW)</span>
                  <div className="text-xl font-bold font-mono text-white mt-1">
                    {balanceLoading ? '조회 중' : formatKrw(balance?.total_evaluation)}
                  </div>
                </div>

                <div className="bg-slate-surface border border-slate-700/80 rounded-lg p-5">
                  <span className="text-xs font-bold text-slate-400">가용 예수금 (Cash)</span>
                  <div className="text-xl font-bold font-mono text-white mt-1">
                    {balanceLoading ? '조회 중' : formatKrw(balance?.available_cash)}
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

              <section className="grid grid-cols-1 gap-6">
                {/* 총 자산 가치 그래프 (Sparkline) */}
                <div className="bg-slate-surface border border-slate-700/80 rounded-lg p-5 flex flex-col gap-3">
                  <div className="mb-1 flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                    <div>
                      <p className="text-[10px] font-bold uppercase tracking-[0.16em] text-ai-cyan">Portfolio Trend</p>
                      <h2 className="text-sm font-bold text-white uppercase tracking-wider">자산 가치 변화 추이</h2>
                    </div>
                    <button
                      className={`rounded border px-2 py-1 text-[10px] font-bold transition-all ${
                        isAssetCalendarOpen
                          ? 'border-ai-cyan bg-ai-cyan/10 text-ai-cyan'
                          : 'border-slate-700 text-slate-400 hover:border-ai-cyan hover:text-white'
                      }`}
                      type="button"
                      onClick={() => setIsAssetCalendarOpen((prev) => !prev)}
                    >
                      기간 변경
                    </button>
                  </div>
                  <div className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
                    <div>
                      <p className="text-2xl font-bold text-white font-mono">{balanceLoading ? '조회 중' : formatKrw(balance?.total_evaluation)}</p>
                      <p className="text-[11px] text-slate-400 mt-1">
                        {assetTrendSummary} <span className="text-emerald-400 font-bold font-mono">{assetTrendDelta}</span>
                      </p>
                    </div>
                    <div className="flex gap-1.5 text-[10px] font-bold text-slate-400">
                      {ASSET_PERIOD_OPTIONS.map((item) => (
                        <button
                          key={item.key}
                          className={`rounded border px-2.5 py-1 cursor-pointer transition-all ${
                            selectedAssetPeriod === item.key
                              ? 'border-ai-cyan/30 bg-ai-cyan/10 text-ai-cyan'
                              : 'border-transparent bg-[#0f172a] text-slate-400 hover:bg-slate-800 hover:text-white'
                          }`}
                          type="button"
                          onClick={() => handleAssetPeriodChange(item.key)}
                        >
                          {item.label}
                        </button>
                      ))}
                    </div>
                  </div>
                  {isAssetCalendarOpen ? (
                    <div className="grid gap-2 rounded border border-slate-800 bg-[#0f172a] p-3 sm:grid-cols-[1fr_auto_1fr] sm:items-center">
                      <input
                        className="h-10 rounded border border-slate-700 bg-transparent px-3 font-mono text-xs text-slate-200 outline-none [color-scheme:dark] focus:border-ai-cyan"
                        type="date"
                        value={assetDateRange.start}
                        onChange={(event) => handleAssetDateChange('start', event.target.value)}
                      />
                      <span className="hidden text-slate-600 sm:block">-</span>
                      <input
                        className="h-10 rounded border border-slate-700 bg-transparent px-3 font-mono text-xs text-slate-200 outline-none [color-scheme:dark] focus:border-ai-cyan"
                        type="date"
                        value={assetDateRange.end}
                        onChange={(event) => handleAssetDateChange('end', event.target.value)}
                      />
                    </div>
                  ) : null}
                  <div className="mt-2 rounded border border-slate-800 bg-[#0f172a]/60 p-4">
                    <Sparkline values={assetTrendValues} labels={assetTrendLabels} />
                    <div className="mt-3 flex items-center justify-between text-[10px] font-bold text-slate-500">
                      <span>
                        {assetTrendLoading
                          ? '자산 추이 불러오는 중'
                          : assetTrendSource === 'portfolio_snapshots'
                            ? 'DB 자산 스냅샷 기준'
                            : '현재 계정 자산 기준'}
                      </span>
                      <span>{assetTrendValues.length}개 포인트</span>
                    </div>
                  </div>
                </div>

              </section>

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
                    <button
                      className="rounded border border-slate-700 px-2 py-1 text-[10px] font-bold text-slate-400 transition-all hover:border-ai-cyan hover:text-white"
                      type="button"
                      onClick={() => setActiveTab('watchlist')}
                    >
                      관리
                    </button>
                  </div>
                  <div className="overflow-x-auto max-h-[180px] overflow-y-auto">
                    <table className="w-full border-collapse text-xs">
                      <thead className="border-b border-slate-800 text-slate-400 bg-[#0c0e15]/50 sticky top-0">
                        <tr>
                          <th className="px-3 py-2 text-left font-bold">종목명</th>
                          <th className="px-3 py-2 text-left font-bold">시장</th>
                          <th className="px-3 py-2 text-right font-bold">평균가</th>
                          <th className="px-3 py-2 text-right font-bold">등락률</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-slate-800/40">
                        {WATCHLIST_MOCK.map((item) => (
                          <tr key={item.id} className="hover:bg-slate-800/20 transition-colors">
                            <td className="px-3 py-2.5 font-bold text-white">{item.name}</td>
                            <td className="px-3 py-2.5 text-slate-400">{item.market}</td>
                            <td className="px-3 py-2.5 text-right font-mono text-slate-300">{item.average}</td>
                            <td className="px-3 py-2.5 text-right"><Rate value={item.change} /></td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>

              </div>

              {/* 보유 재산 현황 (실제 holdings 연동 테이블) */}
              <div className="bg-slate-surface border border-slate-700/80 rounded-lg p-6 flex flex-col gap-4">
                <div className="flex justify-between items-center border-b border-slate-800 pb-2">
                  <h2 className="text-sm font-bold text-white flex items-center gap-2 uppercase tracking-wider">
                    <span className="w-2 h-2 rounded bg-indigo-500" />
                    Held Positions (보유 주식 자산 현황)
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
                          <th className="py-2 px-3 text-right font-bold">보유수량</th>
                          <th className="py-2 px-3 text-right font-bold">평균단가</th>
                          <th className="py-2 px-3 text-right font-bold">현재가</th>
                          <th className="py-2 px-3 text-right font-bold">평가손익</th>
                          <th className="py-2 px-3 text-right font-bold">수익률</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-slate-800 font-mono">
                        {balance.holdings.map((stock) => (
                          <tr key={stock.symbol} className="hover:bg-slate-800/40 transition-colors">
                            <td className="py-3 px-3 font-sans">
                              <div className="font-semibold text-white">{stock.name}</div>
                              <div className="text-[10px] text-slate-500 font-mono">{stock.symbol}</div>
                            </td>
                            <td className="py-3 px-3 text-right text-slate-300">{stock.qty}</td>
                            <td className="py-3 px-3 text-right text-slate-300">₩{stock.avg_price.toLocaleString()}</td>
                            <td className="py-3 px-3 text-right text-slate-100">₩{stock.current_price.toLocaleString()}</td>
                            <td className={`py-3 px-3 text-right font-semibold ${stock.profit >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                              {stock.profit >= 0 ? '+' : ''}₩{stock.profit.toLocaleString()}
                            </td>
                            <td className={`py-3 px-3 text-right font-semibold`}>
                              <Rate value={(stock.profit_rate >= 0 ? '+' : '') + stock.profit_rate.toFixed(2) + '%'} />
                            </td>
                          </tr>
                        ))}
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

          {activeTab === 'watchlist' && <WatchlistTab />}
          {activeTab === 'assets' && <AssetsTab balance={balance} allocation={allocation} />}
          {activeTab === 'history' && <TradeHistoryTab />}
          {activeTab === 'settings' && (
            <Settings
              isLoggedIn={isLoggedIn}
              userEmail={userEmail}
              handleLogout={handleLogout}
              userProfile={userProfile}
              setUserProfile={setUserProfile}
              hideHeader={true}
            />
          )}
        </div>
      </div>
    </div>
  )
}
