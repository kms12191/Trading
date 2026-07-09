import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { createChart, CandlestickSeries } from 'lightweight-charts'
import { ensureNewsSummaries } from '../lib/supabaseClient.js'
import { deleteUserWatchlistItem, fetchUserWatchlist, supabase, updateUserWatchlistOrder } from '../supabaseClient'
import AssetLogo from '../components/AssetLogo.jsx'
import { SectionHeader } from '../components/DashboardComponents.jsx'
import { formatNewsDate, mergeLatestNews } from '../dashboardUtils.js'

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:5050'

const STOCK_INTERVALS = [
  { label: '1분', value: '1m' },
  { label: '5분', value: '5m' },
  { label: '15분', value: '15m' },
  { label: '30분', value: '30m' },
  { label: '1시간', value: '1h' },
  { label: '일봉', value: '1d' },
  { label: '주봉', value: '1w' },
  { label: '월봉', value: '1M' },
]

const CRYPTO_INTERVALS = [
  { label: '1분', value: '1m' },
  { label: '5분', value: '5m' },
  { label: '15분', value: '15m' },
  { label: '30분', value: '30m' },
  { label: '1시간', value: '1h' },
  { label: '4시간', value: '4h' },
  { label: '일봉', value: '1d' },
  { label: '주봉', value: '1w' },
  { label: '월봉', value: '1M' },
]

const WATCHLIST_MARKET_FILTERS = [
  { key: 'all', label: '전체' },
  { key: 'domestic', label: '국내주식' },
  { key: 'overseas', label: '해외주식' },
  { key: 'crypto', label: '코인' },
]

const HeartIcon = ({ className = '', filled = false }) => (
  <svg
    className={className}
    viewBox="0 0 24 24"
    fill={filled ? 'currentColor' : 'none'}
    stroke="currentColor"
    strokeWidth="2"
    strokeLinecap="round"
    strokeLinejoin="round"
    aria-hidden="true"
  >
    <path d="M20.84 4.61a5.5 5.5 0 0 0-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 0 0-7.78 7.78L12 21.23l8.84-8.84a5.5 5.5 0 0 0 0-7.78Z" />
  </svg>
)

function getWatchlistMarketFilterKey(item = {}) {
  const assetType = String(item.assetType || item.asset_type || '').toUpperCase()
  const marketCountry = String(item.marketCountry || item.market_country || '').toUpperCase()
  const market = String(item.market || '')

  if (assetType === 'CRYPTO' || market.includes('코인')) return 'crypto'
  if (marketCountry === 'US' || market.includes('해외')) return 'overseas'
  return 'domestic'
}

function normalizeCandleTime(rawTime) {
  if (typeof rawTime === 'number' && !Number.isNaN(rawTime)) return rawTime
  if (typeof rawTime !== 'string' || !rawTime.trim()) return null

  const value = rawTime.trim()
  if (/^\d+$/.test(value)) return Number.parseInt(value, 10)
  if (/^\d{4}-\d{2}-\d{2}$/.test(value)) return value

  const parsed = new Date(value.replace(' ', 'T'))
  return Number.isNaN(parsed.getTime()) ? null : Math.floor(parsed.getTime() / 1000)
}

function formatChartDateTime(unixSeconds) {
  const date = new Date(unixSeconds * 1000)
  return new Intl.DateTimeFormat('ko-KR', {
    timeZone: 'Asia/Seoul',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  }).format(date)
}

function formatChartTick(time) {
  if (typeof time === 'number') return formatChartDateTime(time)
  if (typeof time === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(time)) {
    const [, month, day] = time.split('-')
    return `${month}.${day}`
  }
  return String(time)
}

async function getAuthHeader() {
  const { data: { session } } = await supabase.auth.getSession()
  return session?.access_token ? `Bearer ${session.access_token}` : null
}

function getChartConfig(item, assetType) {
  const sourcePayload = item?.sourcePayload || {}
  const exchange = String(item?.exchange || item?.account || sourcePayload.exchange || (assetType === 'CRYPTO' ? 'COINONE' : 'TOSS')).toUpperCase()
  const brokerEnv = String(sourcePayload.broker_env || sourcePayload.env || (exchange === 'KIS' ? 'REAL' : 'REAL')).toUpperCase()
  return { exchange, brokerEnv }
}

function getCryptoChartConfig(chartMode = 'KRW') {
  if (chartMode === 'USD') return { exchange: 'BINANCE', brokerEnv: 'REAL' }
  if (chartMode === 'FUTURES') return { exchange: 'BINANCE_UM_FUTURES', brokerEnv: 'REAL' }
  return { exchange: 'COINONE', brokerEnv: 'REAL' }
}

function WatchlistCandlestickChart({ item, assetType, cryptoChartMode, onCryptoChartModeChange, onLatestPriceChange }) {
  const defaultInterval = assetType === 'CRYPTO' ? '1h' : '1d'
  const [chartInterval, setChartInterval] = useState(defaultInterval)
  const [candleData, setCandleData] = useState([])
  const [loadingChart, setLoadingChart] = useState(false)
  const [chartError, setChartError] = useState('')
  const chartContainerRef = useRef(null)
  const chartRef = useRef(null)
  const candleSeriesRef = useRef(null)
  const hasAppliedInitialFitRef = useRef(false)
  const abortControllerRef = useRef(null)

  useEffect(() => {
    setChartInterval(defaultInterval)
    setCandleData([])
    setChartError('')
    onLatestPriceChange?.(null)
    hasAppliedInitialFitRef.current = false
  }, [item?.id, defaultInterval, onLatestPriceChange])

  useEffect(() => {
    if (!chartContainerRef.current || chartRef.current) return

    const containerWidth = chartContainerRef.current.clientWidth || chartContainerRef.current.parentElement?.clientWidth || 800
    const chart = createChart(chartContainerRef.current, {
      layout: {
        background: { type: 'solid', color: '#0e1529' },
        textColor: '#94a3b8',
        fontSize: 11,
      },
      localization: {
        locale: 'ko-KR',
        timeFormatter: (time) => {
          if (typeof time === 'number') return formatChartDateTime(time)
          if (typeof time === 'string') return time
          return ''
        },
      },
      grid: {
        vertLines: { color: 'rgba(31, 41, 69, 0.4)' },
        horzLines: { color: 'rgba(31, 41, 69, 0.4)' },
      },
      rightPriceScale: {
        borderColor: '#1f2945',
        autoScale: true,
      },
      timeScale: {
        borderColor: '#1f2945',
        timeVisible: true,
        secondsVisible: false,
        tickMarkFormatter: (time) => formatChartTick(time),
      },
      width: containerWidth,
      height: 360,
    })

    const candleSeries = chart.addSeries(CandlestickSeries, {
      upColor: '#ef4444',
      downColor: '#3b82f6',
      borderVisible: false,
      wickUpColor: '#ef4444',
      wickDownColor: '#3b82f6',
    })

    chartRef.current = chart
    candleSeriesRef.current = candleSeries

    const handleResize = () => {
      if (!chartRef.current || !chartContainerRef.current) return
      const nextWidth = chartContainerRef.current.clientWidth || 800
      chartRef.current.applyOptions({ width: nextWidth })
    }

    window.addEventListener('resize', handleResize)
    window.setTimeout(handleResize, 50)

    return () => {
      window.removeEventListener('resize', handleResize)
      chart.remove()
      chartRef.current = null
      candleSeriesRef.current = null
      hasAppliedInitialFitRef.current = false
      if (chartContainerRef.current) chartContainerRef.current.innerHTML = ''
    }
  }, [])

  useEffect(() => {
    if (!item?.id) return

    let isMounted = true

    async function loadCandles() {
      if (abortControllerRef.current) abortControllerRef.current.abort()
      const controller = new AbortController()
      abortControllerRef.current = controller
      setLoadingChart(true)
      setChartError('')

      try {
        const { exchange, brokerEnv } = assetType === 'CRYPTO'
          ? getCryptoChartConfig(cryptoChartMode)
          : getChartConfig(item, assetType)
        const authHeader = await getAuthHeader()
        const params = new URLSearchParams({
          exchange,
          symbol: item.id,
          interval: chartInterval,
          broker_env: brokerEnv,
          count: '300',
        })
        const headers = authHeader ? { Authorization: authHeader } : {}
        const response = await fetch(`${API_BASE_URL}/api/chart/candles?${params.toString()}`, {
          headers,
          signal: controller.signal,
        })
        const payload = await response.json()

        if (!response.ok || !payload.success || !Array.isArray(payload.data) || payload.data.length === 0) {
          throw new Error(payload.message || '차트 데이터를 불러오지 못했습니다.')
        }

        const formatted = payload.data
          .map((candle) => ({
            time: normalizeCandleTime(candle.time),
            open: Number.parseFloat(candle.open),
            high: Number.parseFloat(candle.high),
            low: Number.parseFloat(candle.low),
            close: Number.parseFloat(candle.close),
            volume: Number.parseFloat(candle.volume || 0),
          }))
          .filter((candle) => {
            const validTime = (typeof candle.time === 'number' && !Number.isNaN(candle.time))
              || (typeof candle.time === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(candle.time))
            return validTime
              && !Number.isNaN(candle.open)
              && !Number.isNaN(candle.high)
              && !Number.isNaN(candle.low)
              && !Number.isNaN(candle.close)
          })
          .sort((a, b) => {
            if (typeof a.time === 'number' && typeof b.time === 'number') return a.time - b.time
            return String(a.time).localeCompare(String(b.time))
          })

        const seenTimes = new Set()
        const unique = []
        for (let index = formatted.length - 1; index >= 0; index -= 1) {
          const candle = formatted[index]
          if (!seenTimes.has(candle.time)) {
            seenTimes.add(candle.time)
            unique.push(candle)
          }
        }
        unique.reverse()

        if (!unique.length) throw new Error('표시 가능한 차트 데이터가 없습니다.')
        if (isMounted) {
          setCandleData(unique)
          const latestClose = unique[unique.length - 1]?.close
          onLatestPriceChange?.(Number.isFinite(latestClose) ? latestClose : null)
        }
      } catch (error) {
        if (error.name === 'AbortError') return
        if (isMounted) {
          setCandleData([])
          setChartError(error.message || '차트 데이터를 불러오지 못했습니다.')
          onLatestPriceChange?.(null)
        }
      } finally {
        if (isMounted) setLoadingChart(false)
      }
    }

    loadCandles()

    return () => {
      isMounted = false
      if (abortControllerRef.current) abortControllerRef.current.abort()
    }
  }, [item?.id, item?.exchange, item?.account, assetType, chartInterval, cryptoChartMode, onLatestPriceChange])

  useEffect(() => {
    if (!chartRef.current || !candleSeriesRef.current) return
    candleSeriesRef.current.setData(candleData)
    if (candleData.length && !hasAppliedInitialFitRef.current) {
      chartRef.current.timeScale().fitContent()
      hasAppliedInitialFitRef.current = true
    }
  }, [candleData])

  const intervalOptions = assetType === 'CRYPTO' ? CRYPTO_INTERVALS : STOCK_INTERVALS
  const cryptoChartModes = [
    { value: 'KRW', label: '₩', title: '원화 차트' },
    { value: 'USD', label: '$', title: '달러 차트' },
    { value: 'FUTURES', label: 'F', title: '선물 차트' },
  ]

  return (
    <div className="rounded-lg border border-[#1f2945]/60 bg-[#0e1529] p-3">
      <div className="mb-3 grid grid-cols-[minmax(0,1fr)_auto] items-center gap-2">
        <div className="min-w-0">
          <p className="truncate text-xs font-bold text-white">{item?.name || item?.id}</p>
          <p className="mt-0.5 truncate font-mono text-[10px] text-slate-500">
            {(assetType === 'CRYPTO' ? getCryptoChartConfig(cryptoChartMode) : getChartConfig(item, assetType)).exchange} · {item?.id}
          </p>
        </div>
        <div className="col-span-2 ml-auto flex min-w-0 flex-wrap justify-end gap-1 md:col-span-1">
          {assetType === 'CRYPTO' ? (
            <div className="flex shrink-0 gap-1 rounded border border-[#2b395b] bg-[#070b19] p-0.5">
              {cryptoChartModes.map((option) => (
                <button
                  key={option.value}
                  className={`h-6 min-w-7 rounded px-2 text-[10px] font-black transition ${cryptoChartMode === option.value ? 'bg-cyan-500 text-slate-950 shadow-[0_0_12px_rgba(34,211,238,0.18)]' : 'text-slate-400 hover:bg-cyan-500/10 hover:text-cyan-200'}`}
                  type="button"
                  title={option.title}
                  onClick={() => onCryptoChartModeChange?.(option.value)}
                >
                  {option.label}
                </button>
              ))}
            </div>
          ) : null}
          <div className="flex min-w-0 flex-wrap justify-end gap-1 rounded border border-[#2b395b] bg-[#1b253b] p-0.5">
            {intervalOptions.map((option) => (
              <button
                key={option.value}
                className={`rounded px-2 py-1 text-[10px] font-bold transition ${chartInterval === option.value ? 'bg-cyan-500 text-slate-950' : 'text-slate-400 hover:text-white'}`}
                type="button"
                onClick={() => setChartInterval(option.value)}
              >
                {option.label}
              </button>
            ))}
          </div>
        </div>
      </div>
      <div className="relative min-h-[360px] overflow-hidden rounded bg-[#0e1529]">
        {loadingChart ? (
          <div className="absolute inset-0 z-10 grid place-items-center bg-[#0e1529]/90">
            <span className="font-mono text-xs text-cyan-400 animate-pulse">시세 차트 로드 중...</span>
          </div>
        ) : null}
        {chartError ? (
          <div className="absolute inset-0 z-10 grid place-items-center bg-[#0e1529]/95 px-4 text-center text-xs text-red-300">
            {chartError}
          </div>
        ) : null}
        <div ref={chartContainerRef} className="w-full" />
      </div>
    </div>
  )
}

export default function WatchlistTab({ displayCurrency = 'KRW', exchangeRate = 1380 }) {
  const formatCurrency = (value, currency, targetDisplayCurrency = displayCurrency) => {
    const numeric = Number(value)
    const val = Number.isFinite(numeric) ? numeric : 0
    const rate = Number(exchangeRate) || 1380
    const getDollarFractionDigits = (displayValue) => {
      const absoluteValue = Math.abs(Number(displayValue))
      return absoluteValue > 0 && absoluteValue < 0.1 ? 3 : 1
    }

    if (targetDisplayCurrency === 'KRW') {
      if (currency === 'USD' || currency === 'USDT') {
        return `₩${(val * rate).toLocaleString(undefined, { minimumFractionDigits: 0, maximumFractionDigits: 1 })}`
      }
      return `₩${val.toLocaleString(undefined, { minimumFractionDigits: 0, maximumFractionDigits: 1 })}`
    }

    if (targetDisplayCurrency === 'USD') {
      if (currency === 'KRW') {
        const displayValue = val / rate
        return `$${displayValue.toLocaleString(undefined, { minimumFractionDigits: 0, maximumFractionDigits: getDollarFractionDigits(displayValue) })}`
      }
      return `$${val.toLocaleString(undefined, { minimumFractionDigits: 0, maximumFractionDigits: getDollarFractionDigits(val) })}`
    }

    if (currency === 'USD' || currency === 'USDT') {
      return `$${val.toLocaleString(undefined, { minimumFractionDigits: 0, maximumFractionDigits: getDollarFractionDigits(val) })}`
    }
    return `₩${val.toLocaleString(undefined, { minimumFractionDigits: 0, maximumFractionDigits: 1 })}`
  }
  const [selectedId, setSelectedId] = useState('')
  const [watchlistItems, setWatchlistItems] = useState([])
  const [watchlistLoading, setWatchlistLoading] = useState(false)
  const [watchlistError, setWatchlistError] = useState('')
  const [newsItems, setNewsItems] = useState([])
  const [newsLoading, setNewsLoading] = useState(false)
  const [newsError, setNewsError] = useState('')
  const [newsSyncing, setNewsSyncing] = useState(false)
  const [newsSyncMessage, setNewsSyncMessage] = useState({ text: '', isError: false })
  const [expandedNewsId, setExpandedNewsId] = useState('')
  const [summaryLoadingId, setSummaryLoadingId] = useState('')
  const [chartCurrentPrice, setChartCurrentPrice] = useState(null)
  const [cryptoChartMode, setCryptoChartMode] = useState('KRW')
  const [marketFilter, setMarketFilter] = useState('all')
  const [draggingWatchId, setDraggingWatchId] = useState('')
  const [dragOverWatchId, setDragOverWatchId] = useState('')
  const [removingWatchlistIds, setRemovingWatchlistIds] = useState(new Set())

  const filteredWatchlistItems = marketFilter === 'all'
    ? watchlistItems
    : watchlistItems.filter((item) => getWatchlistMarketFilterKey(item) === marketFilter)
  const selectedItem = filteredWatchlistItems.find((item) => item.id === selectedId) || filteredWatchlistItems[0]
  const useSlider = filteredWatchlistItems.length >= 5

  const assetType = selectedItem?.assetType || (selectedItem?.market === '코인' ? 'CRYPTO' : 'STOCK')
  const selectedCurrency = assetType === 'CRYPTO'
    ? (cryptoChartMode === 'KRW' ? 'KRW' : 'USDT')
    : (selectedItem?.currency || (selectedItem?.marketCountry === 'US' ? 'USD' : 'KRW'))
  const currentDisplayCurrency = assetType === 'CRYPTO'
    ? (cryptoChartMode === 'KRW' ? 'KRW' : 'USD')
    : (selectedCurrency === 'USD' || selectedCurrency === 'USDT' ? displayCurrency : 'KRW')
  const convertCryptoSavedPrice = (value) => {
    const numeric = Number(value)
    if (!Number.isFinite(numeric)) return NaN
    const savedCurrency = String(selectedItem?.currency || 'KRW').toUpperCase()
    const rate = Number(exchangeRate) || 1380
    if (assetType !== 'CRYPTO') return numeric
    if (cryptoChartMode === 'KRW') {
      return savedCurrency === 'USD' || savedCurrency === 'USDT' ? numeric * rate : numeric
    }
    return savedCurrency === 'KRW' ? numeric / rate : numeric
  }
  const baselinePrice = assetType === 'CRYPTO'
    ? convertCryptoSavedPrice(selectedItem?.latestPrice)
    : Number(selectedItem?.latestPrice)
  const fallbackCurrentPrice = assetType === 'CRYPTO'
    ? baselinePrice
    : Number(selectedItem?.latestPrice ?? selectedItem?.average)
  const currentPrice = Number.isFinite(Number(chartCurrentPrice)) ? Number(chartCurrentPrice) : fallbackCurrentPrice
  const hasBaselinePrice = Number.isFinite(baselinePrice) && baselinePrice > 0
  const hasCurrentPrice = Number.isFinite(currentPrice)
  const priceDelta = hasBaselinePrice && hasCurrentPrice ? currentPrice - baselinePrice : 0
  const priceDeltaRate = hasBaselinePrice ? (priceDelta / baselinePrice) * 100 : 0
  const priceDeltaTone = priceDelta > 0 ? 'text-red-400' : priceDelta < 0 ? 'text-blue-400' : 'text-white'
  const signedDeltaAmount = `${priceDelta > 0 ? '+' : priceDelta < 0 ? '-' : ''}${formatCurrency(Math.abs(priceDelta), selectedCurrency, currentDisplayCurrency)}`
  const signedDeltaRate = `${priceDeltaRate > 0 ? '+' : ''}${priceDeltaRate.toFixed(2)}%`
  const chartDetailCards = [
    { label: '종목명', value: selectedItem?.name || '-' },
    {
      label: '저장 당시 가격',
      value: hasBaselinePrice ? formatCurrency(baselinePrice, selectedCurrency, currentDisplayCurrency) : '-',
    },
    {
      label: '현재가',
      value: hasCurrentPrice ? formatCurrency(currentPrice, selectedCurrency, currentDisplayCurrency) : '-',
    },
    {
      label: '현재가 변동',
      value: hasBaselinePrice && hasCurrentPrice ? `${signedDeltaAmount} (${signedDeltaRate})` : '-',
      tone: priceDeltaTone,
    },
  ]

  function reorderWatchlistItems(sourceId, targetId) {
    if (!sourceId || !targetId || sourceId === targetId) return

    setWatchlistItems((current) => {
      const sourceIndex = current.findIndex((item) => item.id === sourceId)
      const targetIndex = current.findIndex((item) => item.id === targetId)

      if (sourceIndex < 0 || targetIndex < 0) return current

      const next = [...current]
      const [movedItem] = next.splice(sourceIndex, 1)
      next.splice(targetIndex, 0, movedItem)
      const orderedNext = next.map((item, index) => ({ ...item, sortOrder: index + 1 }))

      void updateUserWatchlistOrder(orderedNext).catch((error) => {
        setWatchlistError(error.message || '관심종목 순서를 저장하지 못했습니다.')
      })

      return orderedNext
    })
    setSelectedId(sourceId)
  }

  async function handleRemoveWatchlistItem(item) {
    if (!item?.id || removingWatchlistIds.has(item.id)) return

    const previousItems = watchlistItems
    setRemovingWatchlistIds((current) => new Set(current).add(item.id))
    setWatchlistError('')
    setWatchlistItems((current) => current.filter((watchItem) => watchItem.id !== item.id))
    setSelectedId((current) => {
      if (current !== item.id) return current
      const nextItem = previousItems.find((watchItem) => watchItem.id !== item.id)
      return nextItem?.id || ''
    })

    try {
      await deleteUserWatchlistItem(item)
    } catch (error) {
      setWatchlistItems(previousItems)
      setSelectedId((current) => current || item.id)
      setWatchlistError(error.message || '관심종목 해제에 실패했습니다.')
    } finally {
      setRemovingWatchlistIds((current) => {
        const next = new Set(current)
        next.delete(item.id)
        return next
      })
    }
  }

  async function loadWatchlistNewsForItem(item, isMounted = () => true) {
    if (!item) return

    setNewsLoading(true)
    setNewsError('')

    try {
      const params = new URLSearchParams({
        symbol: item.id || '',
        limit: '4',
      })
      const response = await fetch(`${API_BASE_URL}/api/news?${params.toString()}`)
      const payload = await response.json()

      if (!response.ok || !payload.success) {
        throw new Error(payload.message || '뉴스를 불러오지 못했습니다.')
      }

      if (!isMounted()) return
      setNewsItems(mergeLatestNews(payload.data?.items || []))
    } catch (error) {
      if (!isMounted()) return
      setNewsItems([])
      setNewsError(error.message || '뉴스를 불러오지 못했습니다.')
    } finally {
      if (isMounted()) setNewsLoading(false)
    }
  }

  async function handleRequestNewsSync() {
    if (!selectedItem) return

    setNewsSyncing(true)
    setNewsSyncMessage({ text: '', isError: false })
    try {
      const selectedAssetType = selectedItem.assetType || (selectedItem.market === '코인' ? 'CRYPTO' : 'STOCK')
      const response = await fetch(`${API_BASE_URL}/api/news/sync`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          symbol: selectedItem.id,
          display_name: selectedItem.name,
          market: selectedAssetType === 'STOCK' && selectedItem.marketCountry === 'US' ? 'GLOBAL' : 'DOMESTIC',
          asset_type: selectedAssetType,
        }),
      })
      const resData = await response.json()
      if (!response.ok || !resData.success) {
        setNewsSyncMessage({
          text: resData.message || '뉴스 수집 요청에 실패했습니다.',
          isError: true,
        })
        return
      }

      const insertedCount = Number(resData.data?.inserted || 0)
      const fetchedCount = Number(resData.data?.fetched || 0)
      setNewsSyncMessage({
        text: insertedCount > 0
          ? `뉴스 ${insertedCount}건을 새로 적재했습니다.`
          : fetchedCount > 0
            ? '수집은 완료됐지만 새로 적재된 뉴스는 없었습니다.'
            : '수집 요청을 보냈지만 가져온 뉴스가 없었습니다.',
        isError: false,
      })
      await loadWatchlistNewsForItem(selectedItem)
    } catch (error) {
      setNewsSyncMessage({
        text: `뉴스 수집 요청 오류: ${error.message}`,
        isError: true,
      })
    } finally {
      setNewsSyncing(false)
    }
  }

  useEffect(() => {
    let isMounted = true

    async function loadWatchlist() {
      setWatchlistLoading(true)
      setWatchlistError('')
      try {
        const items = await fetchUserWatchlist()
        if (!isMounted) return
        setWatchlistItems(items)
        setSelectedId((current) => current && items.some((item) => item.id === current) ? current : items[0]?.id || '')
      } catch (error) {
        if (!isMounted) return
        setWatchlistItems([])
        setSelectedId('')
        setWatchlistError(error.message || '관심종목을 불러오지 못했습니다.')
      } finally {
        if (isMounted) setWatchlistLoading(false)
      }
    }

    loadWatchlist()

    return () => {
      isMounted = false
    }
  }, [])

  useEffect(() => {
    setSelectedId((current) => {
      if (current && filteredWatchlistItems.some((item) => item.id === current)) return current
      return filteredWatchlistItems[0]?.id || ''
    })
  }, [marketFilter, watchlistItems])

  useEffect(() => {
    if (!selectedItem) return

    let isMounted = true
    setNewsSyncMessage({ text: '', isError: false })
    loadWatchlistNewsForItem(selectedItem, () => isMounted)

    return () => {
      isMounted = false
    }
  }, [selectedItem])

  async function handleToggleSummary(news) {
    const articleId = news?.id
    if (!articleId) return

    if (expandedNewsId === articleId) {
      setExpandedNewsId('')
      return
    }

    setExpandedNewsId(articleId)

    if (news.ai_summary) {
      return
    }

    setSummaryLoadingId(articleId)

    try {
      const response = await ensureNewsSummaries({ articleIds: [articleId] })
      const updatedItem = response?.items?.find((item) => item.id === articleId)

      if (updatedItem) {
        setNewsItems((current) =>
          current.map((item) =>
            item.id === articleId
              ? {
                  ...item,
                  ai_summary: updatedItem.ai_summary || item.ai_summary,
                  ai_summary_model: updatedItem.ai_summary_model || item.ai_summary_model,
                  ai_summary_generated_at: updatedItem.ai_summary_generated_at || item.ai_summary_generated_at,
                  ai_summary_prompt_version: updatedItem.ai_summary_prompt_version || item.ai_summary_prompt_version,
                }
              : item,
          ),
        )
      }

      setExpandedNewsId(articleId)
    } catch (error) {
      setNewsError(error.message || '요약 생성을 가져오지 못했습니다.')
    } finally {
      setSummaryLoadingId('')
    }
  }

  return (
    <main className="max-w-7xl mx-auto flex flex-col gap-6">
      <section className="bg-slate-surface border border-slate-700/80 rounded-lg p-5">
        <div className="mb-3 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <SectionHeader title="관심종목 명단" />
          <div className="inline-flex w-fit rounded-md border border-slate-700/80 bg-[#0f172a] p-1">
            {WATCHLIST_MARKET_FILTERS.map((filter) => (
              <button
                key={filter.key}
                className={`rounded px-2.5 py-1 text-[10px] font-bold transition ${
                  marketFilter === filter.key
                    ? 'bg-ai-cyan text-slate-950'
                    : 'text-slate-400 hover:text-white'
                }`}
                type="button"
                onClick={() => setMarketFilter(filter.key)}
              >
                {filter.label}
              </button>
            ))}
          </div>
        </div>
        <div className={useSlider ? 'flex snap-x gap-2 overflow-x-auto pb-2' : 'grid gap-2 md:grid-cols-2 xl:grid-cols-4'}>
          {filteredWatchlistItems.map((item) => {
            const isRemoving = removingWatchlistIds.has(item.id)
            return (
              <div
                key={item.id}
                className={`${useSlider ? 'min-w-60 snap-start' : 'w-full'} cursor-grab rounded-lg border px-4 py-3 text-left transition active:cursor-grabbing ${
                  selectedItem?.id === item.id
                    ? 'border-institutional-blue bg-institutional-blue text-white'
                    : 'border-transparent bg-[#0f172a] text-slate-300 hover:bg-white/5'
                } ${
                  draggingWatchId === item.id
                    ? 'opacity-50'
                    : dragOverWatchId === item.id
                      ? 'border-ai-cyan ring-1 ring-ai-cyan/50'
                      : ''
                }`}
                draggable
                role="button"
                tabIndex={0}
                onClick={() => setSelectedId(item.id)}
                onKeyDown={(event) => {
                  if (event.key === 'Enter' || event.key === ' ') {
                    event.preventDefault()
                    setSelectedId(item.id)
                  }
                }}
                onDragStart={(event) => {
                  event.dataTransfer.effectAllowed = 'move'
                  event.dataTransfer.setData('text/plain', item.id)
                  setDraggingWatchId(item.id)
                }}
                onDragOver={(event) => {
                  event.preventDefault()
                  event.dataTransfer.dropEffect = 'move'
                  if (draggingWatchId && draggingWatchId !== item.id) {
                    setDragOverWatchId(item.id)
                  }
                }}
                onDragLeave={() => {
                  if (dragOverWatchId === item.id) setDragOverWatchId('')
                }}
                onDrop={(event) => {
                  event.preventDefault()
                  const sourceId = event.dataTransfer.getData('text/plain') || draggingWatchId
                  reorderWatchlistItems(sourceId, item.id)
                  setDraggingWatchId('')
                  setDragOverWatchId('')
                }}
                onDragEnd={() => {
                  setDraggingWatchId('')
                  setDragOverWatchId('')
                }}
              >
                <div className="flex min-w-0 items-center gap-2">
                  <button
                    type="button"
                    className={`inline-flex h-7 w-7 shrink-0 items-center justify-center rounded-full transition-all disabled:cursor-not-allowed disabled:opacity-50 ${
                      selectedItem?.id === item.id
                        ? 'text-white hover:bg-white/15'
                        : 'text-rose-400 hover:bg-rose-500/10 hover:text-rose-300'
                    }`}
                    aria-label={`${item.name} 관심 종목 해제`}
                    title="관심 종목 해제"
                    disabled={isRemoving}
                    onClick={(event) => {
                      event.stopPropagation()
                      handleRemoveWatchlistItem(item)
                    }}
                    onDragStart={(event) => event.stopPropagation()}
                  >
                    <HeartIcon className="h-4 w-4" filled={!isRemoving} />
                  </button>
                  <div className="flex items-center gap-2 min-w-0">
                    <AssetLogo symbol={item.symbol} assetType={item.asset_type || item.assetType} name={item.name} size="h-6 w-6" />
                    <span className="block min-w-0 truncate font-bold">{item.name}</span>
                  </div>
                </div>
                <span className="mt-1 block text-xs opacity-70 font-mono">{item.market} · {item.account}</span>
              </div>
            )
          })}
          {!watchlistLoading && filteredWatchlistItems.length === 0 ? (
            <div className="rounded-lg border border-slate-800 bg-[#0f172a] p-4 text-sm text-slate-400">
              {watchlistItems.length === 0
                ? '관심종목이 없습니다. 하트를 눌러 관심 종목을 추가해주세요.'
                : '선택한 분류에 해당하는 관심종목이 없습니다.'}
            </div>
          ) : null}
        </div>
        {watchlistLoading ? <p className="mt-3 text-xs text-slate-500">관심종목을 불러오는 중입니다...</p> : null}
        {watchlistError ? <p className="mt-3 text-xs text-red-300">{watchlistError}</p> : null}
      </section>

      <section className="bg-slate-surface border border-slate-700/80 rounded-lg p-5">
        <div className="flex justify-between items-center mb-3">
          <SectionHeader title="관심 종목의 차트" action={selectedItem?.id} />
          {selectedItem && (
            <Link
              to={`/asset/${assetType}/${selectedItem.id}`}
              className="rounded bg-blue-600 hover:bg-blue-700 text-white font-bold text-xs px-3 py-1.5 transition active:scale-[0.98]"
            >
              수동 매매 터미널 이동 →
            </Link>
          )}
        </div>
        {selectedItem ? (
          <WatchlistCandlestickChart
            item={selectedItem}
            assetType={assetType}
            cryptoChartMode={cryptoChartMode}
            onCryptoChartModeChange={setCryptoChartMode}
            onLatestPriceChange={setChartCurrentPrice}
          />
        ) : (
          <div className="rounded-lg border border-slate-800 bg-[#0f172a]/70 p-8 text-center text-sm text-slate-500">
            차트를 표시할 관심종목이 없습니다.
          </div>
        )}
        <div className="mt-4 grid gap-3 md:grid-cols-4">
          {chartDetailCards.map((card) => (
            <div key={card.label} className="rounded-lg bg-[#0f172a] p-4">
              <p className="text-xs font-bold text-slate-500">{card.label}</p>
              <p className={`mt-2 font-mono font-bold ${card.tone || 'text-white'}`}>{card.value}</p>
            </div>
          ))}
        </div>
      </section>

      <section className="bg-slate-surface border border-slate-700/80 rounded-lg p-5">
        <SectionHeader title="선택 종목의 최근 뉴스" />
        <div className="grid gap-3 lg:grid-cols-2">
          {newsLoading && newsItems.length === 0 ? (
            <div className="rounded-lg border border-slate-800 bg-[#0f172a] p-4 text-sm text-slate-400 lg:col-span-2">
              최신 뉴스피드를 불러오는 중입니다...
            </div>
          ) : null}

          {newsError ? (
            <div className="rounded-lg border border-red-800 bg-red-950/30 p-4 text-sm text-red-300 lg:col-span-2">
              {newsError}
            </div>
          ) : null}

          {!newsLoading && newsItems.length === 0 && !newsError ? (
            <div className="flex flex-col items-center gap-3 rounded-lg border border-slate-800 bg-[#0f172a] p-8 text-center text-sm text-slate-400 lg:col-span-2">
              <p className="text-xs text-slate-500 font-mono">
                해당 종목의 저장된 뉴스가 없습니다.
              </p>
              <button
                type="button"
                onClick={handleRequestNewsSync}
                disabled={newsSyncing || !selectedItem}
                className="rounded-lg border border-cyan-500/40 bg-cyan-950/30 px-3 py-2 text-[11px] font-bold text-cyan-300 transition hover:bg-cyan-900/40 disabled:cursor-not-allowed disabled:opacity-50"
              >
                {newsSyncing ? '뉴스 수집 요청 중...' : '뉴스 수집 요청하기'}
              </button>
              {newsSyncMessage.text ? (
                <p className={`max-w-[320px] text-[11px] leading-5 ${newsSyncMessage.isError ? 'text-rose-300' : 'text-cyan-300'}`}>
                  {newsSyncMessage.text}
                </p>
              ) : null}
            </div>
          ) : null}

          {newsItems.map((news, index) => {
            const articleId = news.id || news.url || `${news.title}-${index}`
            const isExpanded = expandedNewsId === news.id
            const isLoadingSummary = summaryLoadingId === news.id

            return (
              <article key={articleId} className="rounded-lg border border-slate-800 bg-[#0f172a] p-4">
                <div className="flex items-center justify-between gap-3 text-xs text-slate-500">
                  <span className="font-bold text-ai-cyan">{news.source}</span>
                  <span className="font-mono">{formatNewsDate(news.published_at)}</span>
                </div>
                <h3 className="mt-3 break-words text-sm font-bold leading-6 text-white">{news.title}</h3>
                <p className="mt-2 text-xs text-slate-500">{news.company_name || news.symbol || selectedItem?.name}</p>

                <div className="mt-3 rounded-lg border border-slate-800 bg-black/20 p-3">
                  <p className="break-words whitespace-pre-line text-sm leading-6 text-slate-300">
                    {isExpanded
                      ? news.ai_summary || (isLoadingSummary ? '요약을 생성하는 중입니다...' : '요약 보기 버튼을 눌러 3줄 요약을 생성하세요.')
                      : '요약 보기 버튼을 눌러 3줄 요약을 생성하세요.'}
                  </p>
                  {isExpanded ? (
                    <p className="mt-2 text-[11px] text-slate-500">
                      {news.ai_summary_generated_at
                        ? `요약 저장 시각: ${formatNewsDate(news.ai_summary_generated_at)}`
                        : 'DB에 저장된 요약을 불러왔습니다.'}
                    </p>
                  ) : null}
                </div>

                <div className="mt-4 flex flex-wrap justify-end gap-2">
                  <button
                    className="rounded border border-slate-700 px-3 py-1.5 text-xs text-slate-300 hover:border-slate-500"
                    type="button"
                    disabled={isLoadingSummary}
                    onClick={() => {
                      if (isLoadingSummary) return
                      if (isExpanded) {
                        setExpandedNewsId('')
                        return
                      }
                      void handleToggleSummary(news)
                    }}
                  >
                    {isLoadingSummary ? '생성 중' : isExpanded ? '접기' : '요약 보기'}
                  </button>

                  <a
                    className="rounded bg-blue-600 px-3 py-1.5 text-xs font-semibold text-black"
                    href={news.url || '#'}
                    rel="noreferrer"
                    target="_blank"
                  >
                    원문 열기
                  </a>
                </div>
              </article>
            )
          })}
        </div>
      </section>
    </main>
  )
}
