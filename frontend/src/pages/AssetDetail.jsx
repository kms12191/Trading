import React, { useState, useEffect, useEffectEvent, useRef } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { createChart, CandlestickSeries } from 'lightweight-charts'
import { supabase, deleteUserWatchlistItem, fetchUserWatchlist, upsertUserWatchlistItem } from '../supabaseClient'
import Header from '../components/Header.jsx'
import { getApiErrorMessage } from '../lib/apiError.js'

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:5050'
const OPEN_ORDER_SELECT_FIELDS = 'id,exchange,asset_type,ticker,symbol,side,price,volume,ord_type,currency,broker_env,external_order_id,status,created_at'
const AUTO_RULE_SELECT_FIELDS = 'id,exchange,asset_type,ticker,symbol,broker_env,entry_price,investment_amount,quantity,target_profit_rate,stop_loss_rate,execution_mode,trigger_side,trigger_price,triggered_at,last_checked_at,last_error,status,created_at,updated_at'
const ACTIONABLE_ORDER_STATUSES = ['PENDING', 'APPROVED', 'ORDERED', 'OPEN', 'PARTIALLY_FILLED', 'MODIFIED']

const isActionableOrderStatus = (status) => ACTIONABLE_ORDER_STATUSES.includes(String(status || '').toUpperCase())
const isCancelReplaceExchange = (exchange) => ['COINONE', 'BINANCE', 'BINANCE_UM_FUTURES'].includes(String(exchange || '').toUpperCase())

const getOrderStatusLabel = (status) => {
  const normalized = String(status || '').toUpperCase()
  if (['PENDING', 'OPEN', 'PARTIALLY_FILLED', 'MODIFIED'].includes(normalized)) return '미체결'
  if (['APPROVED', 'ORDERED'].includes(normalized)) return '주문 완료'
  if (normalized === 'EXECUTED') return '체결완료'
  if (['CANCELED', 'CANCELLED'].includes(normalized)) return '취소완료'
  if (['FAILED', 'REJECTED', 'EXPIRED'].includes(normalized)) return '실패'
  return normalized || '-'
}

const getOrderSideLabel = (side) => (String(side || '').toUpperCase() === 'SELL' ? '매도' : '매수')

const getAutoRuleStatusLabel = (status) => {
  const normalized = String(status || '').toUpperCase()
  if (normalized === 'RUNNING') return '감시 중'
  if (normalized === 'COMPLETED') return '완료'
  if (normalized === 'STOPPED') return '정지'
  return normalized || '-'
}

const getAutoExecutionModeLabel = (mode) => {
  const normalized = String(mode || '').toUpperCase()
  if (normalized === 'AUTO') return '조건 도달 시 자동 매도'
  return '조건 도달 시 매도 제안'
}

const getAutoTriggerLabel = (triggerSide) => {
  const normalized = String(triggerSide || '').toUpperCase()
  if (normalized === 'TAKE_PROFIT') return '익절 도달'
  if (normalized === 'STOP_LOSS') return '손절 도달'
  return '-'
}

export default function AssetDetail({ isLoggedIn, userEmail, handleLogout, userProfile }) {
  const { assetType, symbol } = useParams()
  const navigate = useNavigate()
  const normalizedRouteAssetType = String(assetType || '').toUpperCase() === 'STOCK' ? 'STOCK' : 'CRYPTO'
  const [resolvedAssetType, setResolvedAssetType] = useState(normalizedRouteAssetType)

  const getCurrencySign = () => {
    if (exchange === 'COINONE') return '₩';
    if (exchange === 'BINANCE' || exchange === 'BINANCE_UM_FUTURES') return '$';
    if (resolvedAssetType === 'STOCK') {
      return /^\d+$/.test(symbol) ? '₩' : '$';
    }
    return '$';
  };

  const getCurrencyDigits = () => {
    if (exchange === 'COINONE') return 0;
    if (exchange === 'BINANCE' || exchange === 'BINANCE_UM_FUTURES') return 6;
    if (resolvedAssetType === 'STOCK') {
      return /^\d+$/.test(symbol) ? 0 : 4;
    }
    return 4;
  };

  const getPriceDigitsForValue = (value) => {
    const numeric = Math.abs(Number(value))
    if (!Number.isFinite(numeric)) return getCurrencyDigits()
    if (exchange === 'COINONE') return 0
    if (exchange === 'BINANCE' || exchange === 'BINANCE_UM_FUTURES') {
      if (numeric > 0 && numeric < 0.01) return 8
      if (numeric > 0 && numeric < 1) return 6
      if (numeric < 100) return 4
      return 2
    }
    if (resolvedAssetType === 'STOCK' && !/^\d+$/.test(symbol)) {
      if (numeric > 0 && numeric < 1) return 6
      return 4
    }
    return getCurrencyDigits()
  }

  const formatUnitPrice = (value) => {
    const numeric = Number(value)
    if (!Number.isFinite(numeric)) return '-'
    const digits = getPriceDigitsForValue(numeric)
    return `${getCurrencySign()}${numeric.toLocaleString(undefined, { minimumFractionDigits: digits, maximumFractionDigits: digits })}`
  }

  const getChartPriceFormat = (value) => {
    const digits = getPriceDigitsForValue(value || currentPrice)
    return {
      type: 'price',
      precision: digits,
      minMove: 1 / (10 ** digits),
    }
  }

  // 1. 거래소 기본값 세팅 (주식은 TOSS 실거래를 기본값으로, 코인은 COINONE. 단, USDT 마켓 코인은 BINANCE)
  const defaultExchange = (() => {
    if (normalizedRouteAssetType === 'STOCK') return 'TOSS';
    const symUpper = String(symbol || '').toUpperCase();
    if (symUpper.endsWith('USDT') || symUpper.endsWith('BUSD')) {
      return 'BINANCE';
    }
    return 'COINONE';
  })();
  const [exchange, setExchange] = useState(defaultExchange)
  
  // 2. 환경 세팅 (TOSS는 실거래만 지원하므로 기본 REAL 설정)
  const [brokerEnv, setBrokerEnv] = useState('REAL')
  const [chartInterval, setChartInterval] = useState(normalizedRouteAssetType === 'STOCK' ? '1d' : '1h')
  
  // 3. 차트 및 시세 데이터 상태
  const [candleData, setCandleData] = useState([])
  const [loadingChart, setLoadingChart] = useState(true)
  const [currentPrice, setCurrentPrice] = useState(0)
  const [priceChangeRate, setPriceChangeRate] = useState(0)
  const [previousClosePrice, setPreviousClosePrice] = useState(null)
  const [hasAuthoritativeChangeRate, setHasAuthoritativeChangeRate] = useState(false)

  // 4. 주문 폼 상태
  const [side, setSide] = useState('BUY') // BUY | SELL
  const [orderType, setOrderType] = useState('LIMIT') // LIMIT | MARKET
  const [price, setPrice] = useState('')
  const [quantity, setQuantity] = useState('')
  const [autoExit, setAutoExit] = useState(false)
  const [targetProfitRate, setTargetProfitRate] = useState(5.0)
  const [stopLossRate, setStopLossRate] = useState(-3.0)
  const [autoExitExecutionMode, setAutoExitExecutionMode] = useState('PROPOSAL')
  const [futuresIntent, setFuturesIntent] = useState('LONG_OPEN')
  const [futuresLeverage, setFuturesLeverage] = useState(1)
  const [futuresMarginType, setFuturesMarginType] = useState('CROSSED')

  const isFuturesOrder = exchange === 'BINANCE_UM_FUTURES'
  const futuresIntentMeta = {
    LONG_OPEN: { label: '롱 진입', side: 'BUY', reduceOnly: false, tone: 'red' },
    LONG_CLOSE: { label: '롱 청산', side: 'SELL', reduceOnly: true, tone: 'slate' },
    SHORT_OPEN: { label: '숏 진입', side: 'SELL', reduceOnly: false, tone: 'blue' },
    SHORT_CLOSE: { label: '숏 청산', side: 'BUY', reduceOnly: true, tone: 'slate' },
  }
  const currentFuturesIntent = futuresIntentMeta[futuresIntent] || futuresIntentMeta.LONG_OPEN
  const effectiveSide = isFuturesOrder ? currentFuturesIntent.side : side
  const effectiveReduceOnly = isFuturesOrder ? currentFuturesIntent.reduceOnly : false

  // 5. 트랜잭션 UI 상태
  const [submitting, setSubmitting] = useState(false)
  const [tradeMessage, setTradeMessage] = useState({ text: '', isError: false })

  // 6. 실시간 호가, 체결, 보유자산 상태 (WTS 연동 고도화)
  const [orderbook, setOrderbook] = useState(null)
  const [trades, setTrades] = useState([])
  const [userBalance, setUserBalance] = useState(null)
  const [balanceMessage, setBalanceMessage] = useState('')
  const [activeTab, setActiveTab] = useState('news') // news | community
  const [newsList, setNewsList] = useState([])
  const [loadingNews, setLoadingNews] = useState(false)
  const [newsSyncing, setNewsSyncing] = useState(false)
  const [newsSyncMessage, setNewsSyncMessage] = useState({ text: '', isError: false })
  const [disclosureList, setDisclosureList] = useState([])
  const [loadingDisclosures, setLoadingDisclosures] = useState(false)
  const [selectedDisclosureId, setSelectedDisclosureId] = useState('')
  const [disclosureSyncing, setDisclosureSyncing] = useState(false)
  const [disclosureSyncMessage, setDisclosureSyncMessage] = useState({ text: '', isError: false })
  const [displayName, setDisplayName] = useState(symbol)
  const [marketFeeds, setMarketFeeds] = useState({
    candles: { source: 'IDLE', isMock: false, degradedReason: '' },
    orderbook: { source: 'OFF', isMock: false, degradedReason: '' },
    trades: { source: 'OFF', isMock: false, degradedReason: '' },
  })
  const [orderPrecheck, setOrderPrecheck] = useState(null)
  const [precheckLoading, setPrecheckLoading] = useState(false)
  const [precheckMessage, setPrecheckMessage] = useState('')
  const [brokerAvailability, setBrokerAvailability] = useState(null)
  const [tradeHoldingContext, setTradeHoldingContext] = useState(null)
  const [mlSignal, setMlSignal] = useState(null)
  const [mlSignalLoading, setMlSignalLoading] = useState(false)
  const [mlSignalMessage, setMlSignalMessage] = useState('')
  const [isMlSignalExpanded, setIsMlSignalExpanded] = useState(false)
  const [isFavorite, setIsFavorite] = useState(false)
  const [symbolLookupReady, setSymbolLookupReady] = useState(false)
  const [isChartExpanded, setIsChartExpanded] = useState(false)
  const [openOrders, setOpenOrders] = useState([])
  const [openOrdersLoading, setOpenOrdersLoading] = useState(false)
  const [orderActionLoadingId, setOrderActionLoadingId] = useState('')
  const [orderManagementMessage, setOrderManagementMessage] = useState({ text: '', isError: false })
  const [modifyOrderId, setModifyOrderId] = useState('')
  const [modifyDraft, setModifyDraft] = useState({ price: '', quantity: '' })
  const [autoRules, setAutoRules] = useState([])
  const [autoRulesLoading, setAutoRulesLoading] = useState(false)
  const [autoRulesMessage, setAutoRulesMessage] = useState('')

  const chartContainerRef = useRef(null)
  const chartRef = useRef(null)
  const candleSeriesRef = useRef(null)
  const hasAppliedInitialFitRef = useRef(false)
  const abortControllerRef = useRef(null)
  const lastCandleSignatureRef = useRef('')
  const orderbookTradesInFlightRef = useRef(false)
  const candlesInFlightRef = useRef(false)

  const isIntradayInterval = !['1d', '1w', '1M'].includes(chartInterval)
  const effectiveOrderPrice = orderType === 'LIMIT' ? Number(price || 0) : currentPrice
  const totalEstimatedAmount = effectiveOrderPrice * Number(quantity || 0)
  const isStockAsset = resolvedAssetType === 'STOCK'
  const orderCurrencyCode = exchange === 'COINONE'
    ? 'KRW'
    : exchange === 'BINANCE'
      ? 'USD'
      : (/^\d+$/.test(symbol) ? 'KRW' : 'USD')
  const showLevel2Panel = false
  const selectedDisclosure = disclosureList.find((item) => item.id === selectedDisclosureId) || disclosureList[0] || null

  const [isMarketClosed, setIsMarketClosed] = useState(false)
  const chartPollMs = isMarketClosed
    ? 60000
    : (isStockAsset ? (isIntradayInterval ? 20000 : 30000) : (isIntradayInterval ? 5000 : 15000))
  const level2PollMs = isMarketClosed
    ? 30000
    : (isStockAsset ? 10000 : 2000)

  // 세션 토큰 헤더 획득 헬퍼
  const getAuthHeader = async () => {
    const { data: { session } } = await supabase.auth.getSession()
    if (!session) return null
    return `Bearer ${session.access_token}`
  }

  const loadOpenOrders = async () => {
    const { data: { session } } = await supabase.auth.getSession()
    if (!session?.user?.id || !symbol) {
      setOpenOrders([])
      return
    }

    setOpenOrdersLoading(true)
    try {
      const normalizedSymbol = String(symbol || '').trim().toUpperCase()
      let query = supabase
        .from('trade_proposals')
        .select(OPEN_ORDER_SELECT_FIELDS)
        .eq('exchange', exchange)
        .in('status', ACTIONABLE_ORDER_STATUSES)
        .or(`symbol.eq.${normalizedSymbol},ticker.eq.${normalizedSymbol}`)
        .order('created_at', { ascending: false })
        .limit(8)

      if (brokerEnv) {
        query = query.eq('broker_env', brokerEnv)
      }

      const { data, error } = await query
      if (error) throw error
      setOpenOrders((data || []).filter((order) => isActionableOrderStatus(order.status)))
    } catch (error) {
      const message = getApiErrorMessage(error, '미체결 주문을 불러오지 못했습니다.')
      setOpenOrders([])
      setOrderManagementMessage({
        text: message.detail ? `${message.title} ${message.detail}` : message.title,
        isError: true,
      })
    } finally {
      setOpenOrdersLoading(false)
    }
  }

  const loadAutoTradingRules = async () => {
    const { data: { session } } = await supabase.auth.getSession()
    if (!session?.user?.id || !symbol) {
      setAutoRules([])
      return
    }

    setAutoRulesLoading(true)
    try {
      const normalizedSymbol = String(symbol || '').trim().toUpperCase()
      const primaryResult = await supabase
        .from('auto_trading_rules')
        .select(AUTO_RULE_SELECT_FIELDS)
        .eq('exchange', exchange)
        .or(`symbol.eq.${normalizedSymbol},ticker.eq.${normalizedSymbol}`)
        .order('created_at', { ascending: false })
        .limit(5)

      if (primaryResult.error) {
        const legacyResult = await supabase
          .from('auto_trading_rules')
          .select('id,exchange,asset_type,ticker,entry_price,investment_amount,target_profit_rate,stop_loss_rate,status,created_at,updated_at')
          .eq('exchange', exchange)
          .eq('ticker', normalizedSymbol)
          .order('created_at', { ascending: false })
          .limit(5)
        if (legacyResult.error) throw primaryResult.error
        setAutoRules(legacyResult.data || [])
      } else {
        setAutoRules(primaryResult.data || [])
      }
      setAutoRulesMessage('')
    } catch (error) {
      const message = getApiErrorMessage(error, '조건감시 상태를 불러오지 못했습니다.')
      setAutoRules([])
      setAutoRulesMessage(message.detail ? `${message.title} ${message.detail}` : message.title)
    } finally {
      setAutoRulesLoading(false)
    }
  }

  const requestOrderAction = async (endpoint, body) => {
    const authHeader = await getAuthHeader()
    if (!authHeader) {
      throw new Error('로그인이 필요합니다.')
    }

    const response = await fetch(`${API_BASE_URL}${endpoint}`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: authHeader,
      },
      body: JSON.stringify(body),
    })
    const payload = await response.json().catch(() => ({}))
    if (!response.ok || !payload.success) {
      const message = getApiErrorMessage(payload, '주문 처리 요청에 실패했습니다.')
      throw new Error(message.detail ? `${message.title} ${message.detail}` : message.title)
    }
    return payload
  }

  const handleSyncOpenOrders = async () => {
    setOrderActionLoadingId('sync-open-orders')
    setOrderManagementMessage({ text: '', isError: false })
    try {
      await requestOrderAction('/api/trade/orders/sync-status', {})
      await loadOpenOrders()
      await fetchUserBalance()
      setOrderManagementMessage({ text: '주문 상태를 최신 정보로 갱신했습니다.', isError: false })
    } catch (error) {
      setOrderManagementMessage({ text: error.message, isError: true })
    } finally {
      setOrderActionLoadingId('')
    }
  }

  const handleCancelOpenOrder = async (order) => {
    const confirmed = window.confirm(`${order.symbol || order.ticker} ${getOrderSideLabel(order.side)} 주문을 취소할까요?`)
    if (!confirmed) return

    setOrderActionLoadingId(`cancel-${order.id}`)
    setOrderManagementMessage({ text: '', isError: false })
    try {
      const payload = await requestOrderAction('/api/trade/order/cancel', {
        proposal_id: order.id,
        broker_env: order.broker_env || brokerEnv,
      })
      await loadOpenOrders()
      await fetchUserBalance()
      setOrderManagementMessage({ text: payload.message || '주문 취소 요청이 완료되었습니다.', isError: false })
    } catch (error) {
      setOrderManagementMessage({ text: error.message, isError: true })
    } finally {
      setOrderActionLoadingId('')
    }
  }

  const handleOpenModifyOrder = (order) => {
    setModifyOrderId(order.id)
    setModifyDraft({
      price: order.price ? String(order.price) : '',
      quantity: order.volume ? String(order.volume) : '',
    })
    setOrderManagementMessage({ text: '', isError: false })
  }

  const handleSubmitModifyOrder = async (order) => {
    const nextPrice = String(modifyDraft.price || '').trim()
    const nextQuantity = String(modifyDraft.quantity || '').trim()
    if (!nextPrice && !nextQuantity) {
      setOrderManagementMessage({ text: '정정할 가격 또는 수량을 입력해 주세요.', isError: true })
      return
    }

    const isCancelReplace = isCancelReplaceExchange(order.exchange)
    setOrderActionLoadingId(`modify-${order.id}`)
    setOrderManagementMessage({ text: '', isError: false })
    try {
      const payload = await requestOrderAction(
        isCancelReplace ? '/api/trade/order/cancel-replace' : '/api/trade/order/modify',
        {
          proposal_id: order.id,
          broker_env: order.broker_env || brokerEnv,
          price: nextPrice || undefined,
          quantity: nextQuantity || undefined,
        },
      )
      setModifyOrderId('')
      setModifyDraft({ price: '', quantity: '' })
      await loadOpenOrders()
      await fetchUserBalance()
      setOrderManagementMessage({
        text: payload.message || (isCancelReplace ? '취소 후 재주문 요청이 완료되었습니다.' : '주문 정정 요청이 완료되었습니다.'),
        isError: false,
      })
    } catch (error) {
      setOrderManagementMessage({ text: error.message, isError: true })
    } finally {
      setOrderActionLoadingId('')
    }
  }

  const pickPreferredStockBroker = (statusMap) => {
    if (!statusMap) return null

    const candidates = [
      { exchange: 'TOSS', brokerEnv: 'REAL' },
      { exchange: 'KIS', brokerEnv: 'REAL' },
      { exchange: 'KIS', brokerEnv: 'MOCK' },
    ]

    for (const candidate of candidates) {
      const exData = statusMap[candidate.exchange]
      if (exData && exData.accounts) {
        const hasRegistered = exData.accounts.some(
          acc => acc.broker_env === candidate.brokerEnv && acc.registered
        )
        if (hasRegistered) {
          return candidate
        }
      }
    }

    return null
  }

  const isRegisteredStockBroker = (statusMap, targetExchange, targetEnv) => {
    if (!statusMap) return false
    const exData = statusMap[targetExchange]
    if (!exData || !exData.accounts) return false
    return exData.accounts.some(acc => acc.broker_env === targetEnv && acc.registered)
  }

  const loadTradeHoldingContext = async () => {
    const { data: { session } } = await supabase.auth.getSession()
    if (!session?.user?.id || !symbol) {
      setTradeHoldingContext(null)
      return
    }

    const normalizedSymbol = String(symbol).trim().toUpperCase()
    const { data, error } = await supabase
      .from('trade_proposals')
      .select('id,exchange,broker_env,symbol,ticker,side,status,volume,price,created_at')
      .or(`symbol.eq.${normalizedSymbol},ticker.eq.${normalizedSymbol}`)
      .order('created_at', { ascending: false })

    if (error || !data?.length) {
      setTradeHoldingContext(null)
      return
    }

    const rows = data || []
    const latestBrokerRow = rows.find((row) => row.exchange && row.broker_env) || rows[0]
    const executedRows = rows.filter((row) => String(row.status || '').toUpperCase() === 'EXECUTED')
    const quantity = executedRows.reduce((sum, row) => {
      const sideValue = String(row.side || '').toUpperCase()
      const volume = Number(row.volume || 0)
      if (!Number.isFinite(volume) || volume <= 0) return sum
      return sideValue === 'SELL' ? sum - volume : sum + volume
    }, 0)
    const buyAmount = executedRows.reduce((sum, row) => {
      const sideValue = String(row.side || '').toUpperCase()
      const volume = Number(row.volume || 0)
      const rowPrice = Number(row.price || 0)
      if (sideValue !== 'BUY' || !Number.isFinite(volume) || !Number.isFinite(rowPrice)) return sum
      return sum + (volume * rowPrice)
    }, 0)
    const buyQuantity = executedRows.reduce((sum, row) => {
      const sideValue = String(row.side || '').toUpperCase()
      const volume = Number(row.volume || 0)
      if (sideValue !== 'BUY' || !Number.isFinite(volume)) return sum
      return sum + volume
    }, 0)

    setTradeHoldingContext({
      exchange: latestBrokerRow?.exchange || '',
      brokerEnv: latestBrokerRow?.broker_env || '',
      estimatedQty: Math.max(quantity, 0),
      avgPrice: buyQuantity > 0 ? buyAmount / buyQuantity : 0,
      latestStatus: latestBrokerRow?.status || '',
      latestSide: latestBrokerRow?.side || '',
    })
  }

  const loadBrokerAvailability = async () => {
    const authHeader = await getAuthHeader()
    if (!authHeader) {
      setBrokerAvailability(null)
      return
    }

    try {
      const response = await fetch(`${API_BASE_URL}/api/keys/status`, {
        headers: {
          Authorization: authHeader,
        },
      })
      const resData = await response.json()
      if (resData.success && resData.data) {
        setBrokerAvailability(resData.data)
      }
    } catch (error) {
      console.error('브로커 등록 상태 로드 실패:', error)
    }
  }

  // 종목 메타데이터(한글명 등) 조회
  const fetchSymbolMetadata = async () => {
    setSymbolLookupReady(false)
    try {
      const response = await fetch(`${API_BASE_URL}/api/symbol/lookup?query=${symbol}&asset_type=${normalizedRouteAssetType}`)
      const resData = await response.json()
      if (resData.success && resData.data && resData.data.display_name) {
        setDisplayName(resData.data.display_name)
        const mappedAssetType = String(resData.data.asset_type || '').toUpperCase() === 'STOCK' ? 'STOCK' : 'CRYPTO'
        setResolvedAssetType(mappedAssetType)
        setSymbolLookupReady(true)
      } else {
        const params = new URLSearchParams({
          query: symbol || '',
          assetType: normalizedRouteAssetType,
        })
        navigate(`/search/not-found?${params.toString()}`, { replace: true })
      }
    } catch (e) {
      console.error("종목명 로드 실패:", e)
      const params = new URLSearchParams({
        query: symbol || '',
        assetType: normalizedRouteAssetType,
      })
      navigate(`/search/not-found?${params.toString()}`, { replace: true })
    }
  }

  // 관심종목(즐겨찾기) 상태 조회
  const loadFavoriteStatus = async () => {
    if (!isLoggedIn) {
      setIsFavorite(false)
      return
    }
    try {
      const items = await fetchUserWatchlist()
      const hasMatch = items.some(item => 
        item.id === symbol && 
        item.assetType === resolvedAssetType && 
        item.exchange === exchange
      )
      setIsFavorite(hasMatch)
    } catch (e) {
      console.warn('즐겨찾기 상태 로드 실패:', e)
    }
  }

  // 관심종목(즐겨찾기) 토글 처리
  const handleToggleFavorite = async () => {
    if (!isLoggedIn) {
      alert("로그인이 필요한 서비스입니다.")
      return
    }

    const itemPayload = {
      symbol: symbol,
      name: displayName,
      exchange: exchange,
      asset_type: resolvedAssetType,
      latest_price: currentPrice || null,
      change_rate: priceChangeRate || null,
      average_price: currentPrice || null,
      quantity: 0
    }

    try {
      if (isFavorite) {
        await deleteUserWatchlistItem(itemPayload)
        setIsFavorite(false)
      } else {
        await upsertUserWatchlistItem(itemPayload)
        setIsFavorite(true)
      }
    } catch (error) {
      alert(error.message || "즐겨찾기 갱신 실패")
    }
  }

  // 실시간 크롤링 뉴스 로드 (종목 한글명/코드 자동 필터링)
  const fetchNewsList = async () => {
    setLoadingNews(true)
    try {
      const response = await fetch(`${API_BASE_URL}/api/news?symbol=${symbol}&limit=6`)
      const resData = await response.json()
      if (resData.success && resData.data && resData.data.items) {
        setNewsList(resData.data.items)
      }
    } catch (e) {
      console.error("뉴스 로드 실패:", e)
    } finally {
      setLoadingNews(false)
    }
  }

  const handleRequestNewsSync = async () => {
    setNewsSyncing(true)
    setNewsSyncMessage({ text: '', isError: false })
    try {
      const response = await fetch(`${API_BASE_URL}/api/news/sync`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          symbol,
          display_name: displayName,
          market: isStockAsset && !/^\d+$/.test(symbol) ? 'GLOBAL' : 'DOMESTIC',
          asset_type: resolvedAssetType,
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
      await fetchNewsList()
    } catch (error) {
      setNewsSyncMessage({
        text: `뉴스 수집 요청 오류: ${error.message}`,
        isError: true,
      })
    } finally {
      setNewsSyncing(false)
    }
  }

  const fetchDisclosureList = async () => {
    if (resolvedAssetType !== 'STOCK') {
      setDisclosureList([])
      setSelectedDisclosureId('')
      return
    }

    setLoadingDisclosures(true)
    try {
      const response = await fetch(`${API_BASE_URL}/api/disclosures?symbol=${symbol}&limit=10`)
      const resData = await response.json()
      if (resData.success && resData.data && resData.data.items) {
        setDisclosureList(resData.data.items)
        setSelectedDisclosureId(resData.data.items[0]?.id || '')
      }
    } catch (error) {
      console.error('공시 목록 로드 실패:', error)
    } finally {
      setLoadingDisclosures(false)
    }
  }

  const handleRequestDisclosureSync = async () => {
    setDisclosureSyncing(true)
    setDisclosureSyncMessage({ text: '', isError: false })
    try {
      const response = await fetch(`${API_BASE_URL}/api/disclosures/sync`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ mode: 'incremental' }),
      })
      const resData = await response.json()
      if (!response.ok || !resData.success) {
        setDisclosureSyncMessage({
          text: resData.message || '공시 수집 요청에 실패했습니다.',
          isError: true,
        })
        return
      }

      setDisclosureSyncMessage({
        text: `공시 ${Number(resData.data?.saved || 0)}건을 확인했습니다.`,
        isError: false,
      })
      await fetchDisclosureList()
    } catch (error) {
      setDisclosureSyncMessage({
        text: `공시 수집 요청 오류: ${error.message}`,
        isError: true,
      })
    } finally {
      setDisclosureSyncing(false)
    }
  }

  const fetchMlSignal = async () => {
    if (!isLoggedIn) {
      setMlSignal(null)
      setMlSignalMessage('로그인 후 AI 시그널을 확인할 수 있습니다.')
      return
    }

    const authHeader = await getAuthHeader()
    if (!authHeader) {
      setMlSignal(null)
      setMlSignalMessage('로그인 세션이 만료되었습니다.')
      return
    }

    setMlSignalLoading(true)
    setMlSignalMessage('')
    try {
      const params = new URLSearchParams({
        asset_type: resolvedAssetType,
        symbols: symbol,
        limit: '1',
      })
      const response = await fetch(`${API_BASE_URL}/api/ml/predictions/active?${params.toString()}`, {
        headers: {
          Authorization: authHeader,
        },
      })
      const resData = await response.json()
      if (!response.ok || !resData.success) {
        setMlSignal(null)
        setMlSignalMessage(
          response.status === 404
            ? '현재 이 종목에 표시할 활성 AI 시그널이 없습니다.'
            : (resData.message || 'AI 시그널 조회에 실패했습니다.')
        )
        return
      }

      const firstSignal = resData.data?.predictions?.[0] || null
      setMlSignal(firstSignal ? { ...firstSignal, meta: resData.data } : null)
      setMlSignalMessage(firstSignal ? '' : '현재 이 종목에 표시할 활성 AI 시그널이 없습니다.')
    } catch (error) {
      setMlSignal(null)
      setMlSignalMessage(`AI 시그널 통신 실패: ${error.message}`)
    } finally {
      setMlSignalLoading(false)
    }
  }

  // 시간 표시 포맷 헬퍼
  const formatTime = (isoString) => {
    if (!isoString) return '';
    try {
      const date = new Date(isoString);
      const now = new Date();
      const diffMs = now - date;
      const diffMins = Math.floor(diffMs / 60000);
      if (diffMins < 1) return '방금 전';
      if (diffMins < 60) return `${diffMins}분 전`;
      const diffHours = Math.floor(diffMins / 60);
      if (diffHours < 24) return `${diffHours}시간 전`;
      return date.toLocaleDateString();
    } catch (e) {
      return '';
    }
  }

  const formatTimestamp = (value) => {
    if (!value) return '-'
    const date = typeof value === 'number'
      ? new Date(value > 1_000_000_000_000 ? value : value * 1000)
      : new Date(value)
    if (Number.isNaN(date.getTime())) return '-'
    return date.toLocaleString('ko-KR', {
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
      hour12: false,
    })
  }

  const formatProbability = (value) => {
    if (value === null || value === undefined || value === '') return '-'
    const numberValue = Number(value)
    if (Number.isNaN(numberValue)) return '-'
    return `${(numberValue * 100).toFixed(1)}%`
  }

  const formatSignalScore = (value) => {
    if (value === null || value === undefined || value === '') return '-'
    const numberValue = Number(value)
    if (Number.isNaN(numberValue)) return '-'
    return numberValue.toFixed(2)
  }

  const formatStaleness = (minutes) => {
    if (minutes === null || minutes === undefined || Number.isNaN(Number(minutes))) return '-'
    const numericMinutes = Number(minutes)
    if (numericMinutes < 60) return `${numericMinutes}분 전`
    if (numericMinutes < 1440) return `${Math.floor(numericMinutes / 60)}시간 전`
    return `${Math.floor(numericMinutes / 1440)}일 전`
  }

  const getSignalGradeLabel = (grade) => {
    if (grade === 'STRONG_BUY_CANDIDATE') return '강한 후보'
    if (grade === 'WATCH') return '관찰'
    if (grade === 'RISKY') return '위험'
    if (grade === 'NO_SIGNAL') return '신호 없음'
    return grade || '미분류'
  }

  const getSignalGradeTone = (grade) => {
    if (grade === 'STRONG_BUY_CANDIDATE') return 'border-emerald-500/50 bg-emerald-950/40 text-emerald-300'
    if (grade === 'WATCH') return 'border-cyan-500/50 bg-cyan-950/30 text-cyan-300'
    if (grade === 'RISKY') return 'border-rose-500/50 bg-rose-950/40 text-rose-300'
    return 'border-slate-700 bg-slate-900/70 text-slate-400'
  }

  const getPolicyReasonLabel = (reason) => {
    const labels = {
      market_breadth: '시장 폭 부족',
      sector_breadth: '섹터 폭 부족',
      sector_strength: '섹터 강도 부족',
      market_regime: '시장 국면 보수적',
      market_drawdown: '시장 낙폭 부담',
      hard_market_drawdown: '시장 급락 차단',
      news_stress: '뉴스 스트레스',
      exception_entry: '예외 진입',
      relative_risk_override: '상대 위험 완화',
      override: '정책 예외',
    }
    return labels[reason] || reason
  }

  const getPolicyReasonLabels = (signal) => {
    if (!signal) return []
    if (Array.isArray(signal.policy_block_reason_labels) && signal.policy_block_reason_labels.length > 0) {
      return signal.policy_block_reason_labels
    }
    return String(signal.policy_block_reason || '')
      .split('|')
      .map(item => item.trim())
      .filter(Boolean)
      .map(getPolicyReasonLabel)
  }

  const formatDecimalMetric = (value, digits = 2) => {
    if (value === null || value === undefined || value === '') return '-'
    const numberValue = Number(value)
    if (Number.isNaN(numberValue)) return '-'
    return numberValue.toFixed(digits)
  }

  const formatRatio = (value) => {
    if (value === null || value === undefined || value === '') return '-'
    const numberValue = Number(value)
    if (Number.isNaN(numberValue)) return '-'
    return `${numberValue.toFixed(2)}x`
  }

  const formatMetric = (value, digits = 4) => {
    if (value === null || value === undefined || value === '') return '-'
    const numberValue = Number(value)
    if (Number.isNaN(numberValue)) return '-'
    return numberValue.toFixed(digits)
  }

  const formatPercent = (value, digits = 1) => {
    if (value === null || value === undefined || value === '') return '-'
    const numberValue = Number(value)
    if (Number.isNaN(numberValue)) return '-'
    return `${(numberValue * 100).toFixed(digits)}%`
  }

  const formatReturnPercent = (value, digits = 2) => {
    if (value === null || value === undefined || value === '') return '-'
    const numberValue = Number(value)
    if (Number.isNaN(numberValue)) return '-'
    return `${(numberValue * 100).toFixed(digits)}%`
  }

  const normalizeCandleTime = (rawTime) => {
    if (typeof rawTime === 'number' && !Number.isNaN(rawTime)) {
      return rawTime
    }

    if (typeof rawTime !== 'string' || !rawTime.trim()) {
      return null
    }

    const value = rawTime.trim()
    if (/^\d+$/.test(value)) {
      return Number.parseInt(value, 10)
    }

    if (/^\d{4}-\d{2}-\d{2}$/.test(value)) {
      return value
    }

    const parsed = new Date(value.replace(' ', 'T'))
    if (!Number.isNaN(parsed.getTime())) {
      return Math.floor(parsed.getTime() / 1000)
    }

    return null
  }

  const buildCandleSignature = (items) => {
    if (!items.length) return ''
    const lastItem = items[items.length - 1]
    return `${items.length}:${lastItem.time}:${lastItem.close}:${lastItem.volume}`
  }

  const normalizeHoldingSymbol = (value) => {
    const normalized = String(value || '').trim().toUpperCase()
    if (/^A\d{6}$/.test(normalized)) {
      return normalized.slice(1)
    }
    return normalized
  }

  const formatChartDateTime = (unixSeconds) => {
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

  const formatChartTick = (time) => {
    if (typeof time === 'number') {
      return formatChartDateTime(time)
    }
    if (typeof time === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(time)) {
      const [year, month, day] = time.split('-')
      return `${month}.${day}`
    }
    return String(time)
  }

  const getOverallFeedStatus = () => {
    const sources = Object.values(marketFeeds).filter((item) => item.source !== 'OFF')
    if (!sources.length) {
      return { label: 'LIVE', tone: 'text-emerald-300 bg-emerald-950/40 border-emerald-800/60' }
    }
    if (sources.some((item) => item.isMock || item.source === 'MOCK')) {
      return { label: 'MOCK', tone: 'text-amber-300 bg-amber-950/40 border-amber-800/60' }
    }
    if (sources.some((item) => item.source === 'CACHE')) {
      return { label: 'DELAYED', tone: 'text-sky-300 bg-sky-950/40 border-sky-800/60' }
    }
    return { label: 'LIVE', tone: 'text-emerald-300 bg-emerald-950/40 border-emerald-800/60' }
  }

  const feedReasonSummary = [marketFeeds.candles, marketFeeds.orderbook, marketFeeds.trades]
    .filter((item) => item.isMock && item.degradedReason)
    .map((item) => item.degradedReason)
    .join(' · ')

  // 1. 시세 캔들 로드
  const fetchCandles = async ({ silent = false } = {}) => {
    if (candlesInFlightRef.current) {
      return
    }
    if (abortControllerRef.current) {
      abortControllerRef.current.abort()
    }
    const controller = new AbortController()
    abortControllerRef.current = controller
    candlesInFlightRef.current = true

    if (!silent) {
      setLoadingChart(true)
    }
    const authHeader = await getAuthHeader()
    
    try {
      const chartEx = exchange;
      const chartEnv = brokerEnv;
      const url = `${API_BASE_URL}/api/chart/candles?exchange=${chartEx}&symbol=${symbol}&interval=${chartInterval}&broker_env=${chartEnv}&count=300`
      const headers = {}
      if (authHeader) {
        headers['Authorization'] = authHeader
      }

      const response = await fetch(url, { 
        headers,
        signal: controller.signal
      })
      const resData = await response.json()

      if (resData.success && resData.data && resData.data.length > 0) {
        const rawFormatted = resData.data
          .map(item => {
            const finalTime = normalizeCandleTime(item.time)
            return {
              time: finalTime,
              open: parseFloat(item.open),
              high: parseFloat(item.high),
              low: parseFloat(item.low),
              close: parseFloat(item.close),
              volume: parseFloat(item.volume || 0)
            };
          })
          .filter(item => {
            const isValidTime = (typeof item.time === 'number' && !Number.isNaN(item.time)) || 
              (typeof item.time === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(item.time));
            return isValidTime && 
              !Number.isNaN(item.open) && 
              !Number.isNaN(item.high) && 
              !Number.isNaN(item.low) && 
              !Number.isNaN(item.close);
          });

        if (rawFormatted.length === 0) {
          console.error('유효한 시세 데이터 포맷이 없습니다.');
          if (abortControllerRef.current === controller) {
            setLoadingChart(false);
          }
          return;
        }

        rawFormatted.sort((a, b) => {
          if (typeof a.time === 'number' && typeof b.time === 'number') {
            return a.time - b.time;
          }
          return a.time.toString().localeCompare(b.time.toString());
        });

        const uniqueFormatted = [];
        const seenTimes = new Set();
        for (let i = rawFormatted.length - 1; i >= 0; i--) {
          const item = rawFormatted[i];
          if (!seenTimes.has(item.time)) {
            seenTimes.add(item.time);
            uniqueFormatted.push(item);
          }
        }
        uniqueFormatted.reverse();

        if (uniqueFormatted.length === 0) {
          console.error('중복 제거 후 시세 데이터가 없습니다.');
          if (abortControllerRef.current === controller) {
            setLoadingChart(false);
          }
          return;
        }

        const signature = buildCandleSignature(uniqueFormatted)
        if (signature !== lastCandleSignatureRef.current) {
          lastCandleSignatureRef.current = signature
          setCandleData(uniqueFormatted)
        }
        if (resData.meta?.cache_ttl_seconds && resData.meta.cache_ttl_seconds > 600) {
          setIsMarketClosed(true)
        } else {
          setIsMarketClosed(false)
        }
        setMarketFeeds(prev => ({
          ...prev,
          candles: {
            source: resData.meta?.source || 'LIVE',
            isMock: Boolean(resData.meta?.is_mock),
            degradedReason: resData.meta?.degraded_reason || '',
            checkedAt: Date.now(),
          },
        }))
        
        const lastCandle = uniqueFormatted[uniqueFormatted.length - 1];
        setCurrentPrice(lastCandle.close);
        
        if (chartInterval === '1d' && uniqueFormatted.length > 1) {
          const prevCandle = uniqueFormatted[uniqueFormatted.length - 2]
          setPreviousClosePrice(Number(prevCandle.close || 0) || null)
        } else {
          setPreviousClosePrice(null)
        }

        setHasAuthoritativeChangeRate(false)

        if (resData.meta && typeof resData.meta.change_rate === 'number') {
          setHasAuthoritativeChangeRate(true);
          setPriceChangeRate(resData.meta.change_rate);
        } else if (chartInterval === '1d' && uniqueFormatted.length > 1) {
          const prevCandle = uniqueFormatted[uniqueFormatted.length - 2];
          const referenceCurrentPrice = Number(resData.meta?.current_price ?? lastCandle.close ?? 0);
          const previousClose = Number(prevCandle.close || 0);
          const change = previousClose !== 0 ? ((referenceCurrentPrice - previousClose) / previousClose) * 100 : 0;
          setHasAuthoritativeChangeRate(false);
          setPriceChangeRate(change);
        } else {
          setPriceChangeRate(0);
        }
        
        setPrice(prev => prev === '' ? lastCandle.close.toString() : prev);
      } else {
        console.error('시세 데이터를 가져오지 못했습니다:', resData.message);
      }
    } catch (error) {
      if (error.name === 'AbortError') {
        return
      }
      console.error('시세 API 호출 오류:', error)
    } finally {
      candlesInFlightRef.current = false
      if (abortControllerRef.current === controller) {
        setLoadingChart(false)
      }
    }
  }

  // 2. 실시간 호가/체결 데이터 로드 (폴링)
  const fetchOrderbookAndTrades = async () => {
    if (orderbookTradesInFlightRef.current || document.visibilityState !== 'visible') {
      return
    }
    orderbookTradesInFlightRef.current = true
    try {
      const chartEx = exchange;
      const chartEnv = brokerEnv;
      const authHeader = await getAuthHeader()
      
      const headers = {}
      if (authHeader) {
        headers['Authorization'] = authHeader
      }


      
      // 체결 조회
      const trUrl = `${API_BASE_URL}/api/chart/trades?exchange=${chartEx}&symbol=${symbol}&broker_env=${chartEnv}`;
      const trRes = await fetch(trUrl, { headers });
      const trData = await trRes.json();
      if (trData.success) {
        setTrades(trData.data);
        const isMockTr = Boolean(trData.meta?.is_mock ?? trData.is_mock);
        if (isMockTr) {
          setIsMarketClosed(true);
        }
        setMarketFeeds(prev => ({
          ...prev,
          trades: {
            source: trData.meta?.source || (isMockTr ? 'MOCK' : 'LIVE'),
            isMock: isMockTr,
            degradedReason: trData.meta?.degraded_reason || '',
            checkedAt: Date.now(),
          },
        }))
        if (Array.isArray(trData.data) && trData.data.length > 0) {
          setCurrentPrice(prevPrice => trData.data[0].price || prevPrice)
        }
      }
    } catch (e) {
      console.error("실시간 호가/체결 갱신 오류:", e);
    } finally {
      orderbookTradesInFlightRef.current = false
    }
  }

  // 3. 실시간 유저 자산 잔고 로드
  const fetchUserBalance = async () => {
    const authHeader = await getAuthHeader()
    if (!authHeader) {
      setUserBalance(null)
      setBalanceMessage('로그인 후 보유현황을 확인할 수 있어요.')
      return
    }

    try {
      const payload = {
        exchange: exchange,
        env: brokerEnv
      }
      const response = await fetch(`${API_BASE_URL}/api/dashboard/balance`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': authHeader
        },
        body: JSON.stringify(payload)
      })
      const resData = await response.json()
      if (resData.success) {
        setUserBalance(resData.data)
        setBalanceMessage('')
      } else {
        const message = getApiErrorMessage(resData, `${exchange} (${brokerEnv}) 잔고를 불러오지 못했습니다.`)
        setUserBalance(null)
        setBalanceMessage(message.detail ? `${message.title} ${message.detail}` : message.title)
      }
    } catch (error) {
      const message = getApiErrorMessage(error, '잔고를 불러오지 못했습니다.')
      setUserBalance(null)
      setBalanceMessage(message.detail ? `${message.title} ${message.detail}` : message.title)
    }
  }

  const fetchOrderPrecheck = async () => {
    const authHeader = await getAuthHeader()
    if (!authHeader) {
      setOrderPrecheck(null)
      setPrecheckMessage('')
      return
    }

    if (!quantity || Number(quantity) <= 0) {
      setOrderPrecheck(null)
      setPrecheckMessage('')
      return
    }

    if (orderType === 'LIMIT' && (!price || Number(price) <= 0)) {
      setOrderPrecheck(null)
      setPrecheckMessage('지정가를 입력하면 주문 가능 금액을 미리 계산합니다.')
      return
    }

    setPrecheckLoading(true)
    setPrecheckMessage('')

    try {
      const response = await fetch(`${API_BASE_URL}/api/trade/precheck`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': authHeader,
        },
        body: JSON.stringify({
          exchange,
          symbol,
          action: effectiveSide,
          order_type: orderType,
          quantity: Number(quantity),
          price: orderType === 'LIMIT' ? Number(price) : null,
          broker_env: brokerEnv,
          position_side: exchange === 'BINANCE_UM_FUTURES' ? 'BOTH' : null,
          reduce_only: exchange === 'BINANCE_UM_FUTURES' ? effectiveReduceOnly : false,
          leverage: exchange === 'BINANCE_UM_FUTURES' ? Number(futuresLeverage) : null,
          margin_type: exchange === 'BINANCE_UM_FUTURES' ? futuresMarginType : null,
        }),
      })
      const resData = await response.json()
      if (resData.success) {
        setOrderPrecheck(resData.data)
      } else {
        const message = getApiErrorMessage(resData, '주문 사전검증에 실패했습니다.')
        setOrderPrecheck(null)
        setPrecheckMessage(message.detail ? `${message.title} ${message.detail}` : message.title)
      }
    } catch (error) {
      const message = getApiErrorMessage(error, '주문 사전검증에 실패했습니다.')
      setOrderPrecheck(null)
      setPrecheckMessage(message.detail ? `${message.title} ${message.detail}` : message.title)
    } finally {
      setPrecheckLoading(false)
    }
  }

  // 거래소 토글 시 환경값 변경
  useEffect(() => {
    if (hasAuthoritativeChangeRate) return
    if (chartInterval !== '1d') {
      setPriceChangeRate(0)
      return
    }
    if (!previousClosePrice) return
    if (!currentPrice) return

    const change = ((Number(currentPrice) - Number(previousClosePrice)) / Number(previousClosePrice)) * 100
    setPriceChangeRate(Number.isFinite(change) ? change : 0)
  }, [currentPrice, previousClosePrice, chartInterval, hasAuthoritativeChangeRate])

  const handleExchangeChange = (newEx, newEnv = 'REAL') => {
    // 가상자산은 Real만 가용하므로 항상 통과, 주식의 경우 KIS MOCK은 기본 제공 폴백이므로 항상 통과
    const isMockKis = newEx === 'KIS' && newEnv === 'MOCK'
    const isCrypto = resolvedAssetType === 'CRYPTO'
    const isValid = isCrypto || isMockKis || isRegisteredStockBroker(brokerAvailability, newEx, newEnv)

    if (resolvedAssetType === 'STOCK' && !isValid) {
      const displayName = newEx === 'KIS' ? '한국투자증권 실거래' : '토스증권 실거래'
      alert(`등록된 ${displayName} API Key가 없습니다. 대시보드 상단에서 API Key를 등록한 후에 사용해 주세요.`)
      return
    }

    setExchange(newEx)
    setBrokerEnv(newEnv)
    setPrice('')
    setQuantity('')
  }

  // 호가 클릭 시 단가 자동 입력 매핑
  const handlePriceClick = (clickedPrice) => {
    if (orderType === 'LIMIT') {
      setPrice(clickedPrice.toString());
    }
  }

  const refreshMlSignal = useEffectEvent(() => {
    fetchMlSignal()
  })

  useEffect(() => {
    fetchSymbolMetadata()
  }, [symbol, normalizedRouteAssetType])

  useEffect(() => {
    if (!symbolLookupReady) return

    setNewsSyncMessage({ text: '', isError: false })
    fetchCandles()
    fetchUserBalance()
    loadOpenOrders()
    loadAutoTradingRules()
    fetchNewsList()
    fetchDisclosureList()
  }, [exchange, symbol, chartInterval, brokerEnv, symbolLookupReady])

  useEffect(() => {
    fetchSymbolMetadata()
    loadBrokerAvailability()
    loadTradeHoldingContext()
  }, [symbol])

  useEffect(() => {
    loadFavoriteStatus()
  }, [isLoggedIn, symbol, resolvedAssetType, exchange])

  useEffect(() => {
    const timer = window.setTimeout(() => {
      refreshMlSignal()
    }, 0)
    return () => window.clearTimeout(timer)
  }, [isLoggedIn, resolvedAssetType, symbol])

  useEffect(() => {
    if (resolvedAssetType === 'STOCK') {
      if (
        tradeHoldingContext?.exchange &&
        tradeHoldingContext?.brokerEnv &&
        tradeHoldingContext?.estimatedQty > 0 &&
        (exchange !== tradeHoldingContext.exchange || brokerEnv !== tradeHoldingContext.brokerEnv)
      ) {
        setExchange(tradeHoldingContext.exchange)
        setBrokerEnv(tradeHoldingContext.brokerEnv)
        return
      }

      const preferredBroker = pickPreferredStockBroker(brokerAvailability)
      const currentBrokerValid = isRegisteredStockBroker(brokerAvailability, exchange, brokerEnv)
      if (preferredBroker && !currentBrokerValid) {
        setExchange(preferredBroker.exchange)
        setBrokerEnv(preferredBroker.brokerEnv)
        return
      }
      if (!preferredBroker) {
        if (!['TOSS', 'KIS'].includes(exchange)) {
          setExchange('KIS')
        }
        if (brokerEnv !== 'MOCK' && exchange === 'KIS') {
          setBrokerEnv('MOCK')
        }
      }
      if (!['1m', '5m', '15m', '30m', '1h', '1d', '1w', '1M'].includes(chartInterval)) {
        setChartInterval('1d')
      }
      return
    }
    
    const symUpper = String(symbol || '').toUpperCase()
    const isUsdtMarket = symUpper.endsWith('USDT') || symUpper.endsWith('BUSD')

    if (isUsdtMarket) {
      if (!['BINANCE', 'BINANCE_UM_FUTURES'].includes(exchange)) {
        setExchange('BINANCE')
      }
    } else {
      if (!['COINONE', 'BINANCE', 'BINANCE_UM_FUTURES'].includes(exchange)) {
        setExchange('COINONE')
      }
    }

    if (exchange !== 'BINANCE_UM_FUTURES' && brokerEnv !== 'REAL') {
      setBrokerEnv('REAL')
    }
    if (!['1m', '5m', '15m', '30m', '1h', '4h', '1d', '1w', '1M'].includes(chartInterval)) {
      setChartInterval('1h')
    }
  }, [resolvedAssetType, exchange, brokerEnv, chartInterval, brokerAvailability, tradeHoldingContext, symbol])

  useEffect(() => {
    const intervalId = window.setInterval(() => {
      if (document.visibilityState === 'visible') {
        fetchCandles({ silent: true })
      }
    }, chartPollMs)

    return () => window.clearInterval(intervalId)
  }, [exchange, symbol, chartInterval, brokerEnv, chartPollMs])

  useEffect(() => {
    if (!showLevel2Panel) {
      setMarketFeeds((prev) => ({
        ...prev,
        orderbook: { source: 'OFF', isMock: false, degradedReason: '', checkedAt: undefined },
        trades: { source: 'OFF', isMock: false, degradedReason: '', checkedAt: undefined },
      }))
      return
    }
    const timeoutId = window.setTimeout(() => {
      fetchOrderbookAndTrades()
    }, isStockAsset ? 1200 : 0)
    const intervalId = window.setInterval(fetchOrderbookAndTrades, level2PollMs)
    const visibilityHandler = () => {
      if (document.visibilityState === 'visible') {
        fetchOrderbookAndTrades()
      }
    }
    document.addEventListener('visibilitychange', visibilityHandler)
    return () => {
      window.clearTimeout(timeoutId)
      window.clearInterval(intervalId)
      document.removeEventListener('visibilitychange', visibilityHandler)
    }
  }, [exchange, symbol, brokerEnv, level2PollMs, isStockAsset, showLevel2Panel]);

  useEffect(() => {
    if (exchange === 'COINONE' && orderType === 'MARKET') {
      setOrderType('LIMIT')
    }
  }, [exchange, orderType])

  useEffect(() => {
    const timeoutId = window.setTimeout(() => {
      fetchOrderPrecheck()
    }, isStockAsset ? 800 : 250)

    return () => window.clearTimeout(timeoutId)
  }, [exchange, symbol, effectiveSide, orderType, price, quantity, brokerEnv, isStockAsset, effectiveReduceOnly, futuresLeverage, futuresMarginType])

  // 3. TradingView Lightweight Charts 차트 초기 생성 및 리사이즈 대응
  useEffect(() => {
    if (!symbolLookupReady) return
    if (!chartContainerRef.current || chartRef.current) return

    try {
      const containerWidth = chartContainerRef.current.clientWidth || chartContainerRef.current.parentElement?.clientWidth || 800

      const chart = createChart(chartContainerRef.current, {
        layout: {
          background: { type: 'solid', color: '#0e1529' }, // Obsidian Navy 테마
          textColor: '#94a3b8',
          fontSize: 11,
        },
        localization: {
          locale: 'ko-KR',
          timeFormatter: (time) => {
            if (typeof time === 'number') {
              return formatChartDateTime(time)
            }
            if (typeof time === 'string') {
              return time
            }
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
        height: 300,
      })

      const candleSeries = chart.addSeries(CandlestickSeries, {
        upColor: '#ef4444', // 한국 상승 빨강
        downColor: '#3b82f6', // 한국 하락 파랑
        borderVisible: false,
        wickUpColor: '#ef4444',
        wickDownColor: '#3b82f6',
        priceFormat: getChartPriceFormat(currentPrice),
      })

      chartRef.current = chart
      candleSeriesRef.current = candleSeries

      const handleResize = () => {
        if (chartRef.current && chartContainerRef.current) {
          try {
            const newWidth = chartContainerRef.current.clientWidth || 800
            chartRef.current.applyOptions({ width: newWidth })
          } catch (err) {
            console.error('차트 리사이즈 조절 에러:', err)
          }
        }
      }

      window.addEventListener('resize', handleResize)

      setTimeout(() => {
        if (chartRef.current && chartContainerRef.current) {
          const fitWidth = chartContainerRef.current.clientWidth || 800
          chartRef.current.applyOptions({ width: fitWidth })
        }
      }, 50)

      return () => {
        window.removeEventListener('resize', handleResize)
        try {
          chart.remove()
        } catch (e) {
          console.error('차트 소멸 정리 에러:', e)
        }
        chartRef.current = null
        candleSeriesRef.current = null
        hasAppliedInitialFitRef.current = false
        if (chartContainerRef.current) {
          chartContainerRef.current.innerHTML = ''
        }
      }
    } catch (err) {
      console.error('TradingView 차트 생성 치명적 에러:', err)
    }
  }, [symbolLookupReady])

  // 4. 차트 데이터만 갱신하고 초기 1회만 fitContent 적용
  useEffect(() => {
    if (!candleData.length || !chartRef.current || !candleSeriesRef.current) return

    try {
      candleSeriesRef.current.setData(candleData)

      if (!hasAppliedInitialFitRef.current) {
        chartRef.current.timeScale().fitContent()
        hasAppliedInitialFitRef.current = true
      }
    } catch (err) {
      console.error('차트 데이터 갱신 실패:', err)
    }
  }, [candleData, symbolLookupReady])

  useEffect(() => {
    if (!candleSeriesRef.current) return
    candleSeriesRef.current.applyOptions({
      priceFormat: getChartPriceFormat(currentPrice),
    })
  }, [currentPrice, exchange, resolvedAssetType, symbol])

  useEffect(() => {
    if (!chartRef.current || !chartContainerRef.current) return

    const nextHeight = isChartExpanded ? 720 : 300
    const nextWidth = chartContainerRef.current.clientWidth || 800
    chartRef.current.applyOptions({ width: nextWidth, height: nextHeight })
  }, [isChartExpanded])

  // 5. 수동 주문 제출 핸들러
  const handlePlaceOrder = async (e) => {
    e.preventDefault()
    setSubmitting(true)
    setTradeMessage({ text: '', isError: false })

    const authHeader = await getAuthHeader()
    if (!authHeader) {
      setTradeMessage({ text: '로그인이 필요합니다.', isError: true })
      setSubmitting(false)
      return
    }

    if (!quantity || parseFloat(quantity) <= 0) {
      setTradeMessage({ text: '올바른 주문 수량을 입력하세요.', isError: true })
      setSubmitting(false)
      return
    }

    if (orderType === 'LIMIT' && (!price || parseFloat(price) <= 0)) {
      setTradeMessage({ text: '올바른 지정가 단가를 입력하세요.', isError: true })
      setSubmitting(false)
      return
    }

    if (exchange === 'COINONE' && orderType !== 'LIMIT') {
      setTradeMessage({ text: '코인원 주문은 현재 지정가만 지원합니다.', isError: true })
      setSubmitting(false)
      return
    }

    if (exchange === 'BINANCE_UM_FUTURES') {
      const leverage = Number(futuresLeverage)
      if (!Number.isInteger(leverage) || leverage < 1 || leverage > 125) {
        setTradeMessage({ text: '선물 레버리지는 1~125 사이 정수로 입력해 주세요.', isError: true })
        setSubmitting(false)
        return
      }
    }

    if (brokerEnv === 'REAL' && orderPrecheck?.exceeds_real_order_limit) {
      setTradeMessage({ text: '실거래 1회 주문 한도를 초과했습니다. 수량 또는 단가를 조정해 주세요.', isError: true })
      setSubmitting(false)
      return
    }

    if (brokerEnv === 'REAL' && orderPrecheck?.insufficient_cash) {
      setTradeMessage({ text: '예수금보다 큰 주문입니다. 수량 또는 단가를 조정해 주세요.', isError: true })
      setSubmitting(false)
      return
    }

    if (brokerEnv === 'REAL' && orderPrecheck?.insufficient_holding) {
      setTradeMessage({ text: '보유 수량을 초과하는 매도 주문입니다.', isError: true })
      setSubmitting(false)
      return
    }

    try {
      const payload = {
        exchange,
        symbol,
        action: effectiveSide,
        order_type: orderType,
        quantity: parseFloat(quantity),
        price: orderType === 'LIMIT' ? parseFloat(price) : null,
        broker_env: brokerEnv,
        auto_exit: autoExit,
        target_profit_rate: autoExit ? parseFloat(targetProfitRate) : null,
        stop_loss_rate: autoExit ? parseFloat(stopLossRate) : null,
        auto_exit_execution_mode: autoExit ? autoExitExecutionMode : 'PROPOSAL',
        position_side: exchange === 'BINANCE_UM_FUTURES' ? 'BOTH' : null,
        reduce_only: exchange === 'BINANCE_UM_FUTURES' ? effectiveReduceOnly : false,
        leverage: exchange === 'BINANCE_UM_FUTURES' ? Number(futuresLeverage) : null,
        margin_type: exchange === 'BINANCE_UM_FUTURES' ? futuresMarginType : null
      }

      const response = await fetch(`${API_BASE_URL}/api/trade/order`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': authHeader
        },
        body: JSON.stringify(payload)
      })

      const resData = await response.json()

      if (resData.success) {
        const autoExitMessage = resData.auto_exit ? ` / ${resData.auto_exit}` : ''
        setTradeMessage({
          text: `주문이 성공적으로 전송되었습니다!${autoExitMessage}`,
          isError: false
        })
        setQuantity('')
        fetchUserBalance() // 주문 성공 시 보유 자산 즉시 갱신
        loadOpenOrders()
        loadAutoTradingRules()
      } else {
        const message = getApiErrorMessage(resData, '주문 전송에 실패했습니다.')
        setTradeMessage({
          text: message.detail ? `${message.title} ${message.detail}` : message.title,
          isError: true
        })
      }
    } catch (error) {
      const message = getApiErrorMessage(error, '네트워크 오류가 발생했습니다.')
      setTradeMessage({
        text: message.detail ? `${message.title} ${message.detail}` : message.title,
        isError: true
      })
    } finally {
      setSubmitting(false)
    }
  }

  // 보유 주식 필터링
  const normalizedCurrentSymbol = normalizeHoldingSymbol(symbol)
  const myHolding = userBalance?.holdings?.find((holding) => {
    const normalizedHoldingSymbol = normalizeHoldingSymbol(holding.symbol)
    return (
      normalizedHoldingSymbol === normalizedCurrentSymbol ||
      normalizedCurrentSymbol.includes(normalizedHoldingSymbol) ||
      normalizedHoldingSymbol.includes(normalizedCurrentSymbol)
    )
  });
  const dbEstimatedHolding = !myHolding && tradeHoldingContext?.estimatedQty > 0
    ? tradeHoldingContext
    : null
  const myHoldingQty = Number(myHolding?.qty || 0)
  const myHoldingAbsQty = Math.abs(myHoldingQty)
  const myHoldingEvalAmount = Number(myHolding?.eval_amount ?? (Number(myHolding?.current_price || 0) * myHoldingAbsQty))
  const myHoldingDirection = myHolding?.position_direction || (myHoldingQty < 0 ? 'SHORT' : 'LONG')
  const baseAvailableCash = Number(userBalance?.available_cash ?? NaN)
  const overallFeedStatus = getOverallFeedStatus()
  const isOrderBlocked = brokerEnv === 'REAL' && (
    orderPrecheck?.exceeds_real_order_limit ||
    orderPrecheck?.futures_real_blocked ||
    orderPrecheck?.insufficient_cash ||
    orderPrecheck?.insufficient_holding
  )
  const chartCardClassName = isChartExpanded
    ? 'fixed inset-3 z-50 flex flex-col gap-4 rounded-2xl border border-cyan-500/40 bg-[#0e1529] p-4 shadow-2xl shadow-cyan-950/40 backdrop-blur-xl sm:inset-6'
    : 'bg-[#0e1529]/90 border border-[#1f2945] rounded-xl p-4 flex flex-col gap-4 backdrop-blur-md'
  const chartPanelClassName = isChartExpanded
    ? 'w-full relative h-[72vh] min-h-[520px] bg-[#0e1529] rounded-lg overflow-hidden border border-cyan-500/20'
    : 'w-full relative h-[300px] min-h-[300px] bg-[#0e1529] rounded-lg overflow-hidden border border-[#1f2945]/60'
  const holdingSummaryLabel = myHolding && myHoldingAbsQty > 0
    ? `${myHoldingAbsQty.toLocaleString()} ${exchange === 'BINANCE_UM_FUTURES' ? '계약' : '주'}`
    : dbEstimatedHolding
      ? `${dbEstimatedHolding.estimatedQty.toLocaleString()} 주 추정`
      : '보유 없음'
  const availableCashLabel = orderPrecheck?.available_cash != null
    ? `${getCurrencySign()}${Number(orderPrecheck.available_cash).toLocaleString(undefined, { maximumFractionDigits: getCurrencyDigits() })}`
    : Number.isFinite(baseAvailableCash)
      ? `${getCurrencySign()}${baseAvailableCash.toLocaleString(undefined, { maximumFractionDigits: getCurrencyDigits() })}`
      : '잔고 조회 필요'

  const handleFillFullExitOrder = () => {
    const exitQty = myHoldingAbsQty || dbEstimatedHolding?.estimatedQty || 0
    if (!exitQty || exitQty <= 0) {
      setTradeMessage({ text: '현재 선택 계좌에서 자동 입력할 보유 수량이 없습니다.', isError: true })
      return
    }

    setQuantity(String(exitQty))
    if (orderType === 'LIMIT' && currentPrice > 0) {
      setPrice(String(currentPrice))
    }
    if (exchange === 'BINANCE_UM_FUTURES') {
      setFuturesIntent(myHoldingDirection === 'SHORT' ? 'SHORT_CLOSE' : 'LONG_CLOSE')
    } else {
      setSide('SELL')
    }
    setTradeMessage({ text: '보유 수량 기준으로 청산/매도 주문값을 채웠습니다. 전송 전 사전검증을 확인하세요.', isError: false })
  }

  if (!symbolLookupReady) {
    return (
      <div className="min-h-screen bg-[#070b19] text-[#e2e2ec] font-inter">
        <div className="max-w-7xl mx-auto px-4 py-4">
          <Header isLoggedIn={isLoggedIn} userEmail={userEmail} handleLogout={handleLogout} userProfile={userProfile} />
        </div>
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-[#070b19] text-[#e2e2ec] font-inter">
      <div className="max-w-7xl mx-auto px-4 py-4">
        
        {/* 상단 네비게이션 헤더 */}
        <Header isLoggedIn={isLoggedIn} userEmail={userEmail} handleLogout={handleLogout} userProfile={userProfile} />

        {/* 뒤로가기 버튼 */}
        <div className="mt-2 mb-4">
          <button
            onClick={() => navigate('/dashboard')}
            className="flex items-center gap-2 text-xs font-bold text-slate-400 hover:text-white transition-all bg-transparent border-none cursor-pointer outline-none"
          >
            <span>← 대시보드로 돌아가기</span>
          </button>
        </div>

        {/* 1. 상단 토스 WTS 스타일 메타 정보 헤더 바 */}
        <div className="bg-[#0e1529]/90 border border-[#1f2945] rounded-xl p-5 mb-5 backdrop-blur-md flex flex-col md:flex-row justify-between items-start md:items-center gap-4">
          <div>
            <div className="flex items-center gap-2">
              <span className="text-[9px] font-bold text-cyan-400 bg-cyan-950/60 px-2 py-0.5 rounded border border-cyan-900/60 uppercase tracking-widest font-mono">
                {resolvedAssetType} · {exchange} ({brokerEnv})
              </span>
              <span className={`text-[9px] font-bold px-2 py-0.5 rounded border uppercase tracking-widest font-mono ${overallFeedStatus.tone}`}>
                {overallFeedStatus.label}
              </span>
            </div>
            <h1 className="text-xl font-bold font-mono text-white mt-1.5 flex items-center gap-2">
              {displayName !== symbol ? `${displayName} (${symbol})` : symbol}{' '}
              <span className="text-xs text-slate-400 font-normal">
                ({resolvedAssetType === 'STOCK' ? '주식' : '가상자산'})
              </span>
              <button
                type="button"
                onClick={handleToggleFavorite}
                className={`text-[22px] leading-none transition ml-1.5 cursor-pointer focus:outline-none ${
                  isFavorite ? 'text-red-400 hover:text-red-300' : 'text-slate-400 hover:text-cyan-400'
                }`}
                aria-label="즐겨찾기"
                aria-pressed={isFavorite}
              >
                {isFavorite ? '♥' : '♡'}
              </button>
            </h1>
            <p className="mt-2 text-[10px] text-slate-500 font-mono">
              {showLevel2Panel
                ? `차트 ${marketFeeds.candles.source} · 호가 ${marketFeeds.orderbook.source} · 체결 ${marketFeeds.trades.source}`
                : `차트 ${marketFeeds.candles.source} · 호가/체결 비활성화`}
            </p>
            {feedReasonSummary ? (
              <p className="mt-1 text-[10px] text-amber-300/80 font-mono">
                원인 {feedReasonSummary}
              </p>
            ) : null}
          </div>
          
          <div className="flex flex-wrap items-center gap-x-8 gap-y-2">
            {/* 현재가 */}
            <div className="flex flex-col">
              <span className="text-[10px] text-slate-400 font-bold">현재가</span>
              <span className="text-lg font-bold font-mono text-white mt-0.5">
                {formatUnitPrice(currentPrice)}
              </span>
            </div>

            {/* 등락률 */}
            <div className="flex flex-col">
              <span className="text-[10px] text-slate-400 font-bold">전일대비</span>
              <span className={`text-sm font-bold font-mono mt-0.5 flex items-center ${priceChangeRate >= 0 ? 'text-[#ef4444]' : 'text-[#3b82f6]'}`}>
                {priceChangeRate >= 0 ? '▲' : '▼'} {Math.abs(priceChangeRate).toFixed(2)}%
              </span>
            </div>


          </div>
        </div>

        {/* 2. 메인 3열(3-column) WTS 레이아웃 */}
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-5">
          
          {/* [1열: 좌측 - 컴팩트 차트 및 저비용 정보 패널] */}
          <div className={`${showLevel2Panel ? 'lg:col-span-6' : 'lg:col-span-8'} flex flex-col gap-5`}>
            
            {/* 차트 카드 */}
            {isChartExpanded && (
              <button
                type="button"
                aria-label="차트 크게보기 닫기"
                onClick={() => setIsChartExpanded(false)}
                className="fixed inset-0 z-40 bg-black/60 backdrop-blur-sm"
              />
            )}
            <div className={chartCardClassName}>
              <div className="flex flex-col gap-3 sm:flex-row sm:justify-between sm:items-center">
                <div className="flex flex-col gap-1">
                  <div className="flex items-center gap-2">
                    <span className="w-1.5 h-3 bg-cyan-400 rounded-full" />
                    <span className="text-xs font-bold text-white">{isChartExpanded ? '실시간 통합 차트 크게보기' : '컴팩트 차트'}</span>
                  </div>
                  <p className="text-[10px] text-slate-500 font-mono">
                    마지막 차트 확인 {formatTimestamp(marketFeeds.candles.checkedAt)}
                  </p>
                </div>
                
                {/* 캔들 주기 변경 탭 */}
                <div className="flex flex-wrap items-center justify-end gap-2">
                  <div className="flex flex-wrap gap-1 bg-[#1b253b] p-0.5 rounded border border-[#2b395b] justify-end">
                    {resolvedAssetType === 'STOCK' ? (
                      <>
                        {[
                          { label: '1분', val: '1m' },
                          { label: '5분', val: '5m' },
                          { label: '15분', val: '15m' },
                          { label: '30분', val: '30m' },
                          { label: '1시간', val: '1h' },
                          { label: '일봉', val: '1d' },
                          { label: '주봉', val: '1w' },
                          { label: '월봉', val: '1M' }
                        ].map((item) => (
                          <button
                            key={item.val}
                            onClick={() => setChartInterval(item.val)}
                            className={`text-[9px] sm:text-[10px] font-bold px-1.5 sm:px-2.5 py-0.5 rounded transition-all cursor-pointer ${chartInterval === item.val ? 'bg-cyan-500 text-slate-950 font-black' : 'text-slate-400 hover:text-white'}`}
                          >
                            {item.label}
                          </button>
                        ))}
                      </>
                    ) : (
                      <>
                        {[
                          { label: '1분', val: '1m' },
                          { label: '5분', val: '5m' },
                          { label: '15분', val: '15m' },
                          { label: '30분', val: '30m' },
                          { label: '1시간', val: '1h' },
                          { label: '4시간', val: '4h' },
                          { label: '일봉', val: '1d' },
                          { label: '주봉', val: '1w' },
                          { label: '월봉', val: '1M' }
                        ].map((item) => (
                          <button
                            key={item.val}
                            onClick={() => setChartInterval(item.val)}
                            className={`text-[9px] sm:text-[10px] font-bold px-1.5 sm:px-2.5 py-0.5 rounded transition-all cursor-pointer ${chartInterval === item.val ? 'bg-cyan-500 text-slate-950 font-black' : 'text-slate-400 hover:text-white'}`}
                          >
                            {item.label}
                          </button>
                        ))}
                      </>
                    )}
                  </div>
                  <button
                    type="button"
                    onClick={() => setIsChartExpanded((prev) => !prev)}
                    className="rounded border border-cyan-500/30 px-3 py-1 text-[10px] font-black text-cyan-300 transition hover:bg-cyan-950/40"
                  >
                    {isChartExpanded ? '닫기' : '크게보기'}
                  </button>
                </div>
              </div>

              {/* 차트 영역 */}
              <div className={chartPanelClassName}>
                {loadingChart && (
                  <div className="absolute inset-0 flex items-center justify-center bg-[#0e1529]/95 z-10 rounded">
                    <span className="text-xs text-cyan-400 font-mono animate-pulse">시세 차트 로드 중...</span>
                  </div>
                )}
                <div ref={chartContainerRef} className="h-full w-full" />
              </div>
            </div>

            <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
              <div className="rounded-xl border border-[#1f2945] bg-[#0e1529]/90 p-4 backdrop-blur-md">
                <p className="text-[10px] font-bold tracking-[0.08em] text-slate-500">보유 현황</p>
                <p className="mt-2 font-mono text-sm font-black text-white">{holdingSummaryLabel}</p>
                <p className="mt-1 text-[10px] text-slate-500">현재 선택 계좌 기준</p>
              </div>
              <div className="rounded-xl border border-[#1f2945] bg-[#0e1529]/90 p-4 backdrop-blur-md">
                <p className="text-[10px] font-bold tracking-[0.08em] text-slate-500">주문 가능 금액</p>
                <p className="mt-2 font-mono text-sm font-black text-cyan-300">{availableCashLabel}</p>
                <p className="mt-1 text-[10px] text-slate-500">주문 입력 시 사전검증 반영</p>
              </div>
              <div className="rounded-xl border border-[#1f2945] bg-[#0e1529]/90 p-4 backdrop-blur-md">
                <p className="text-[10px] font-bold tracking-[0.08em] text-slate-500">주문 관리</p>
                <p className="mt-2 font-mono text-sm font-black text-amber-300">{openOrders.length}건 미체결</p>
                <p className="mt-1 text-[10px] text-slate-500">현재 종목 취소/정정 가능</p>
              </div>
            </div>

            <div className="rounded-xl border border-[#1f2945] bg-[#0e1529]/90 p-4 backdrop-blur-md">
              <div className="mb-3 flex flex-col gap-3 border-b border-[#1f2945] pb-3 sm:flex-row sm:items-center sm:justify-between">
                <div>
                  <div className="flex items-center gap-2">
                    <span className="w-1.5 h-3 rounded-full bg-amber-300" />
                    <span className="text-xs font-bold text-white">미체결 주문 관리</span>
                  </div>
                  <p className="mt-1 text-[10px] text-slate-500">
                    현재 종목과 선택 계좌 기준으로 취소/정정을 처리합니다.
                  </p>
                </div>
                <button
                  type="button"
                  onClick={handleSyncOpenOrders}
                  disabled={Boolean(orderActionLoadingId)}
                  className="rounded border border-cyan-500/30 px-3 py-2 text-[10px] font-black text-cyan-300 transition hover:bg-cyan-950/40 disabled:cursor-not-allowed disabled:opacity-50"
                >
                  {orderActionLoadingId === 'sync-open-orders' ? '갱신 중' : '상태 새로고침'}
                </button>
              </div>

              {orderManagementMessage.text ? (
                <div className={`mb-3 rounded border px-3 py-2 text-[11px] leading-5 ${
                  orderManagementMessage.isError
                    ? 'border-rose-900/60 bg-rose-950/30 text-rose-300'
                    : 'border-cyan-900/60 bg-cyan-950/20 text-cyan-300'
                }`}>
                  {orderManagementMessage.text}
                </div>
              ) : null}

              {openOrdersLoading ? (
                <div className="rounded border border-[#1f2945] bg-[#070b19] px-3 py-6 text-center text-[11px] font-mono text-cyan-300">
                  미체결 주문을 불러오는 중...
                </div>
              ) : openOrders.length > 0 ? (
                <div className="flex flex-col gap-2">
                  {openOrders.map((order) => {
                    const isEditing = modifyOrderId === order.id
                    const orderSideLabel = getOrderSideLabel(order.side)
                    const orderStatusLabel = getOrderStatusLabel(order.status)
                    const isCancelReplace = isCancelReplaceExchange(order.exchange)

                    return (
                      <div key={order.id} className="rounded-lg border border-[#1f2945] bg-[#070b19]/90 p-3">
                        <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                          <div className="min-w-0">
                            <div className="flex flex-wrap items-center gap-2">
                              <span className={`rounded px-2 py-1 text-[10px] font-black ${
                                String(order.side || '').toUpperCase() === 'SELL'
                                  ? 'bg-blue-500/15 text-blue-300'
                                  : 'bg-red-500/15 text-red-300'
                              }`}>
                                {orderSideLabel}
                              </span>
                              <span className="rounded border border-slate-700 px-2 py-1 text-[10px] font-bold text-slate-300">
                                {orderStatusLabel}
                              </span>
                              <span className="font-mono text-[10px] text-slate-500">
                                {order.exchange} · {order.broker_env || brokerEnv}
                              </span>
                            </div>
                            <div className="mt-2 grid grid-cols-2 gap-x-4 gap-y-1 text-[11px] sm:grid-cols-4">
                              <div>
                                <p className="text-slate-500">가격</p>
                                <p className="font-mono font-bold text-white">{formatUnitPrice(order.price)}</p>
                              </div>
                              <div>
                                <p className="text-slate-500">수량</p>
                                <p className="font-mono font-bold text-white">{Number(order.volume || 0).toLocaleString()}</p>
                              </div>
                              <div>
                                <p className="text-slate-500">유형</p>
                                <p className="font-mono font-bold text-white">{order.ord_type || 'LIMIT'}</p>
                              </div>
                              <div>
                                <p className="text-slate-500">주문번호</p>
                                <p className="max-w-[120px] truncate font-mono font-bold text-slate-300">{order.external_order_id || '-'}</p>
                              </div>
                            </div>
                          </div>
                          <div className="flex shrink-0 flex-wrap gap-2">
                            <button
                              type="button"
                              onClick={() => handleOpenModifyOrder(order)}
                              disabled={Boolean(orderActionLoadingId)}
                              className="rounded border border-cyan-500/30 px-3 py-1.5 text-[10px] font-bold text-cyan-300 transition hover:bg-cyan-950/30 disabled:cursor-not-allowed disabled:opacity-50"
                            >
                              {isCancelReplace ? '취소 후 재주문' : '정정'}
                            </button>
                            <button
                              type="button"
                              onClick={() => handleCancelOpenOrder(order)}
                              disabled={Boolean(orderActionLoadingId)}
                              className="rounded border border-rose-500/30 px-3 py-1.5 text-[10px] font-bold text-rose-300 transition hover:bg-rose-950/30 disabled:cursor-not-allowed disabled:opacity-50"
                            >
                              {orderActionLoadingId === `cancel-${order.id}` ? '취소 중' : '취소'}
                            </button>
                          </div>
                        </div>

                        {isEditing ? (
                          <div className="mt-3 rounded border border-cyan-900/40 bg-cyan-950/10 p-3">
                            <div className="mb-2 text-[10px] font-bold text-cyan-300">
                              {isCancelReplace ? '새 주문 값 입력' : '정정 값 입력'}
                            </div>
                            <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
                              <label className="flex flex-col gap-1 text-[10px] font-bold text-slate-400">
                                가격
                                <input
                                  type="number"
                                  step="any"
                                  value={modifyDraft.price}
                                  onChange={(event) => setModifyDraft((prev) => ({ ...prev, price: event.target.value }))}
                                  className="rounded border border-slate-700 bg-[#070b19] px-2 py-2 font-mono text-xs text-white outline-none focus:border-cyan-400"
                                />
                              </label>
                              <label className="flex flex-col gap-1 text-[10px] font-bold text-slate-400">
                                수량
                                <input
                                  type="number"
                                  step="any"
                                  value={modifyDraft.quantity}
                                  onChange={(event) => setModifyDraft((prev) => ({ ...prev, quantity: event.target.value }))}
                                  className="rounded border border-slate-700 bg-[#070b19] px-2 py-2 font-mono text-xs text-white outline-none focus:border-cyan-400"
                                />
                              </label>
                            </div>
                            <div className="mt-3 flex justify-end gap-2">
                              <button
                                type="button"
                                onClick={() => {
                                  setModifyOrderId('')
                                  setModifyDraft({ price: '', quantity: '' })
                                }}
                                className="rounded border border-slate-700 px-3 py-1.5 text-[10px] font-bold text-slate-300 transition hover:text-white"
                              >
                                닫기
                              </button>
                              <button
                                type="button"
                                onClick={() => handleSubmitModifyOrder(order)}
                                disabled={Boolean(orderActionLoadingId)}
                                className="rounded border border-cyan-500/40 bg-cyan-950/30 px-3 py-1.5 text-[10px] font-black text-cyan-300 transition hover:bg-cyan-900/40 disabled:cursor-not-allowed disabled:opacity-50"
                              >
                                {orderActionLoadingId === `modify-${order.id}` ? '처리 중' : isCancelReplace ? '재주문 요청' : '정정 요청'}
                              </button>
                            </div>
                          </div>
                        ) : null}
                      </div>
                    )
                  })}
                </div>
              ) : (
                <div className="rounded border border-[#1f2945] bg-[#070b19] px-3 py-6 text-center text-[11px] text-slate-500">
                  현재 선택한 계좌의 미체결 주문이 없습니다.
                </div>
              )}
            </div>

            <div className="rounded-xl border border-[#1f2945] bg-[#0e1529]/90 p-4 backdrop-blur-md">
              <div className="mb-3 flex flex-col gap-3 border-b border-[#1f2945] pb-3 sm:flex-row sm:items-center sm:justify-between">
                <div>
                  <div className="flex items-center gap-2">
                    <span className="w-1.5 h-3 rounded-full bg-emerald-300" />
                    <span className="text-xs font-bold text-white">조건감시 상태</span>
                  </div>
                  <p className="mt-1 text-[10px] text-slate-500">
                    익절/손절 감시 규칙은 백그라운드 워커가 조건 도달 여부를 확인합니다.
                  </p>
                </div>
                <button
                  type="button"
                  onClick={loadAutoTradingRules}
                  disabled={autoRulesLoading}
                  className="rounded border border-emerald-500/30 px-3 py-2 text-[10px] font-black text-emerald-300 transition hover:bg-emerald-950/30 disabled:cursor-not-allowed disabled:opacity-50"
                >
                  {autoRulesLoading ? '조회 중' : '감시 새로고침'}
                </button>
              </div>

              {autoRulesMessage ? (
                <div className="mb-3 rounded border border-amber-900/60 bg-amber-950/20 px-3 py-2 text-[11px] leading-5 text-amber-300">
                  {autoRulesMessage}
                </div>
              ) : null}

              {autoRulesLoading ? (
                <div className="rounded border border-[#1f2945] bg-[#070b19] px-3 py-6 text-center text-[11px] font-mono text-emerald-300">
                  조건감시 규칙을 확인하는 중...
                </div>
              ) : autoRules.length > 0 ? (
                <div className="flex flex-col gap-2">
                  {autoRules.map((rule) => {
                    const entryPrice = Number(rule.entry_price || 0)
                    const targetRate = Number(rule.target_profit_rate || 0)
                    const stopRate = Number(rule.stop_loss_rate || 0)
                    const targetPrice = entryPrice > 0 ? entryPrice * (1 + targetRate / 100) : 0
                    const stopPrice = entryPrice > 0 ? entryPrice * (1 + stopRate / 100) : 0
                    const isRunning = String(rule.status || '').toUpperCase() === 'RUNNING'

                    return (
                      <div key={rule.id} className="rounded-lg border border-[#1f2945] bg-[#070b19]/90 p-3">
                        <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
                          <div className="flex flex-wrap items-center gap-2">
                            <span className={`rounded px-2 py-1 text-[10px] font-black ${
                              isRunning
                                ? 'bg-emerald-500/15 text-emerald-300'
                                : 'bg-slate-700/50 text-slate-300'
                            }`}>
                              {getAutoRuleStatusLabel(rule.status)}
                            </span>
                            <span className="font-mono text-[10px] text-slate-500">
                              {rule.exchange} · {rule.broker_env || brokerEnv} · {rule.asset_type || resolvedAssetType}
                            </span>
                            <span className={`rounded px-2 py-1 text-[10px] font-black ${
                              String(rule.execution_mode || '').toUpperCase() === 'AUTO'
                                ? 'bg-rose-500/15 text-rose-300'
                                : 'bg-cyan-500/15 text-cyan-300'
                            }`}>
                              {getAutoExecutionModeLabel(rule.execution_mode)}
                            </span>
                          </div>
                          <span className="font-mono text-[10px] text-slate-500">
                            {rule.created_at ? new Date(rule.created_at).toLocaleString('ko-KR') : '-'}
                          </span>
                        </div>
                        <div className="grid grid-cols-2 gap-2 text-[11px] sm:grid-cols-4">
                          <div>
                            <p className="text-slate-500">진입가</p>
                            <p className="font-mono font-bold text-white">{entryPrice > 0 ? formatUnitPrice(entryPrice) : '-'}</p>
                          </div>
                          <div>
                            <p className="text-slate-500">익절 조건</p>
                            <p className="font-mono font-bold text-emerald-300">+{targetRate.toLocaleString()}%</p>
                            <p className="font-mono text-[10px] text-slate-500">{targetPrice > 0 ? formatUnitPrice(targetPrice) : '-'}</p>
                          </div>
                          <div>
                            <p className="text-slate-500">손절 조건</p>
                            <p className="font-mono font-bold text-rose-300">{stopRate.toLocaleString()}%</p>
                            <p className="font-mono text-[10px] text-slate-500">{stopPrice > 0 ? formatUnitPrice(stopPrice) : '-'}</p>
                          </div>
                          <div>
                            <p className="text-slate-500">감시 금액</p>
                            <p className="font-mono font-bold text-white">
                              {Number(rule.investment_amount || 0) > 0
                                ? `${getCurrencySign()}${Number(rule.investment_amount).toLocaleString(undefined, { maximumFractionDigits: getCurrencyDigits() })}`
                                : '-'}
                            </p>
                            <p className="font-mono text-[10px] text-slate-500">
                              수량 {Number(rule.quantity || 0) > 0 ? Number(rule.quantity).toLocaleString(undefined, { maximumFractionDigits: 8 }) : '-'}
                            </p>
                          </div>
                        </div>
                        <div className="mt-3 grid grid-cols-1 gap-2 border-t border-[#1f2945] pt-3 text-[10px] text-slate-500 sm:grid-cols-3">
                          <div>
                            <p>마지막 확인</p>
                            <p className="font-mono text-slate-300">
                              {rule.last_checked_at ? new Date(rule.last_checked_at).toLocaleString('ko-KR') : '-'}
                            </p>
                          </div>
                          <div>
                            <p>트리거</p>
                            <p className="font-mono text-slate-300">
                              {getAutoTriggerLabel(rule.trigger_side)}
                              {Number(rule.trigger_price || 0) > 0 ? ` · ${formatUnitPrice(rule.trigger_price)}` : ''}
                            </p>
                          </div>
                          <div>
                            <p>최근 오류</p>
                            <p className="truncate text-amber-300">{rule.last_error || '-'}</p>
                          </div>
                        </div>
                      </div>
                    )
                  })}
                </div>
              ) : (
                <div className="rounded border border-[#1f2945] bg-[#070b19] px-3 py-6 text-center text-[11px] text-slate-500">
                  현재 종목에 등록된 조건감시 규칙이 없습니다.
                </div>
              )}
            </div>

            {/* 하단 RAG 뉴스 / 종목 정보 탭 카드 */}
            <div className="bg-[#0e1529]/90 border border-[#1f2945] rounded-xl p-5 backdrop-blur-md">
              <div className="flex border-b border-[#1f2945] pb-2 mb-4">
                {[
                  { id: 'news', label: '뉴스' },
                  { id: 'disclosure', label: '공시' },
                  { id: 'community', label: '토론' }
                ].map(t => (
                  <button
                    key={t.id}
                    onClick={() => setActiveTab(t.id)}
                    className={`text-xs font-bold px-4 py-2 border-b-2 transition-all cursor-pointer ${activeTab === t.id ? 'border-cyan-400 text-cyan-400' : 'border-transparent text-slate-400 hover:text-white'}`}
                  >
                    {t.label}
                  </button>
                ))}
              </div>

              {activeTab === 'news' && (
                <div className="max-h-[280px] overflow-y-auto pr-1">
                  <section className="min-h-[220px] rounded-lg border border-[#1f2945]/70 bg-[#07111f]/70 p-4">
                    <div className="mb-3 flex items-center justify-between border-b border-[#1f2945]/50 pb-2">
                      <h3 className="text-xs font-bold text-cyan-300">뉴스</h3>
                      <span className="text-[10px] font-mono text-slate-500">{newsList.length}건</span>
                    </div>

                    <div className="flex flex-col gap-3">
                      {loadingNews ? (
                        <div className="py-8 text-center text-xs text-cyan-400/80 font-mono animate-pulse">
                          실시간 크롤링 뉴스 분석 중...
                        </div>
                      ) : newsList.length > 0 ? (
                        <>
                          <div className="border-l-2 border-cyan-500 pl-3 py-1.5 bg-cyan-950/20 rounded-r">
                            <span className="text-[10px] text-cyan-400 font-bold uppercase tracking-wider">AI RAG 뉴스 핵심 요약</span>
                            <p className="text-xs text-[#e2e2ec] mt-1 leading-relaxed">
                              {newsList.find(n => n.ai_summary)?.ai_summary || newsList[0]?.summary || `${symbol} 종목에 대한 실시간 수집 뉴스를 분석 중입니다.`}
                            </p>
                          </div>
                          {newsList.map(item => (
                            <div key={item.id} className="flex justify-between items-center text-xs py-2 border-b border-[#1f2945]/30 hover:bg-slate-800/10 px-1 rounded transition-all">
                              <a
                                href={item.url}
                                target="_blank"
                                rel="noopener noreferrer"
                                className="text-[#e2e2ec] truncate max-w-[80%] hover:underline cursor-pointer"
                              >
                                {item.title}
                              </a>
                              <span className="text-[10px] text-slate-500 font-mono">{formatTime(item.published_at)}</span>
                            </div>
                          ))}
                        </>
                      ) : (
                        <div className="flex flex-col items-center gap-3 py-8 text-center">
                          <p className="text-xs text-slate-500 font-mono">
                            해당 종목의 실시간 수집 뉴스가 존재하지 않습니다.
                          </p>
                          <button
                            type="button"
                            onClick={handleRequestNewsSync}
                            disabled={newsSyncing}
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
                      )}
                    </div>
                  </section>
                </div>
              )}

              {activeTab === 'disclosure' && (
                <div className="max-h-[280px] overflow-y-auto pr-1">
                  <section className="min-h-[220px] rounded-lg border border-[#1f2945]/70 bg-[#07111f]/70 p-4">
                    <div className="mb-3 flex items-center justify-between border-b border-[#1f2945]/50 pb-2">
                      <h3 className="text-xs font-bold text-cyan-300">공시</h3>
                      <span className="text-[10px] font-mono text-slate-500">{disclosureList.length}건 · DART</span>
                    </div>
                    <div className="flex flex-col gap-3">
                      {loadingDisclosures ? (
                        <div className="py-8 text-center text-xs text-cyan-400/80 font-mono animate-pulse">
                          DART 공시 로드 중...
                        </div>
                      ) : disclosureList.length > 0 ? (
                        <>
                          <div className="border-l-2 border-cyan-500 pl-3 py-1.5 bg-cyan-950/20 rounded-r">
                            <span className="text-[10px] text-cyan-400 font-bold uppercase tracking-wider">DART 공시 요약보기</span>
                            <p className="text-xs text-[#e2e2ec] mt-1 leading-relaxed">
                              {selectedDisclosure?.summary || selectedDisclosure?.report_nm || `${symbol} 종목의 최근 공시를 확인 중입니다.`}
                            </p>
                          </div>
                          {disclosureList.map(item => (
                            <div key={item.id} className="flex flex-col gap-2 border-b border-[#1f2945]/30 px-1 py-2 transition-all hover:bg-slate-800/10 sm:flex-row sm:items-center sm:justify-between">
                              <button
                                type="button"
                                onClick={() => setSelectedDisclosureId(item.id)}
                                className="min-w-0 text-left text-xs text-[#e2e2ec] hover:text-cyan-200"
                              >
                                <span className="block truncate font-bold">{item.report_nm}</span>
                                <span className="mt-0.5 block text-[10px] font-mono text-slate-500">{item.corp_name} · {item.rcept_dt}</span>
                              </button>
                              <div className="flex shrink-0 items-center gap-2">
                                <button
                                  type="button"
                                  onClick={() => setSelectedDisclosureId(item.id)}
                                  className="rounded border border-cyan-500/30 px-2 py-1 text-[10px] font-bold text-cyan-300 transition hover:bg-cyan-950/30"
                                >
                                  요약 보기
                                </button>
                                <a
                                  href={item.url}
                                  target="_blank"
                                  rel="noopener noreferrer"
                                  className="rounded border border-slate-700 px-2 py-1 text-[10px] font-bold text-slate-300 transition hover:border-cyan-500/40 hover:text-white"
                                >
                                  원문 열기
                                </a>
                              </div>
                            </div>
                          ))}
                        </>
                      ) : (
                        <div className="flex flex-col items-center gap-3 py-8 text-center">
                          <p className="text-xs text-slate-500 font-mono">
                            해당 종목의 저장된 DART 공시가 없습니다.
                          </p>
                          <button
                            type="button"
                            onClick={handleRequestDisclosureSync}
                            disabled={disclosureSyncing}
                            className="rounded-lg border border-cyan-500/40 bg-cyan-950/30 px-3 py-2 text-[11px] font-bold text-cyan-300 transition hover:bg-cyan-900/40 disabled:cursor-not-allowed disabled:opacity-50"
                          >
                            {disclosureSyncing ? '공시 수집 요청 중...' : '최근 공시 수집 요청하기'}
                          </button>
                          {disclosureSyncMessage.text ? (
                            <p className={`max-w-[320px] text-[11px] leading-5 ${disclosureSyncMessage.isError ? 'text-rose-300' : 'text-cyan-300'}`}>
                              {disclosureSyncMessage.text}
                            </p>
                          ) : null}
                        </div>
                      )}
                    </div>
                  </section>
                </div>
              )}

              {activeTab === 'community' && (
                <div className="flex flex-col gap-3 max-h-[220px] overflow-y-auto pr-1 text-xs">
                  <div className="bg-[#1b253b]/40 p-3 rounded border border-[#1f2945]/40 flex flex-col gap-1">
                    <div className="flex justify-between text-[10px] text-slate-400">
                      <span className="font-bold text-cyan-400">또치어제자</span>
                      <span>5분 전</span>
                    </div>
                    <p className="text-[#e2e2ec] mt-1 leading-relaxed">진짜 하이닉스 수급 장난아니네요. 다음 타겟은 300만원 갑니다.</p>
                  </div>
                  <div className="bg-[#1b253b]/40 p-3 rounded border border-[#1f2945]/40 flex flex-col gap-1">
                    <div className="flex justify-between text-[10px] text-slate-400">
                      <span className="font-bold text-cyan-400">부자냥냥이</span>
                      <span>20분 전</span>
                    </div>
                    <p className="text-[#e2e2ec] mt-1 leading-relaxed">익절률 5% 조건 주문 걸어놨는데 바로 체결됬네요 꿀맛!</p>
                  </div>
                </div>
              )}
            </div>
          </div>

          {/* [2열: 우측 - 주문 패널 & 내 보유 주식] */}
          <div className={`${showLevel2Panel ? 'lg:col-span-3' : 'lg:col-span-4'} flex flex-col gap-5`}>

            {/* AI 시그널 카드 */}
            <div className="bg-[#0e1529]/90 border border-cyan-500/30 rounded-xl p-4 flex flex-col gap-3 backdrop-blur-md">
              <div className="flex items-start justify-between gap-3 border-b border-[#1f2945] pb-2">
                <div>
                  <span className="text-[10px] font-bold uppercase tracking-[0.16em] text-cyan-300">AI Signal</span>
                  <h2 className="mt-1 text-xs font-bold text-white">ML 참고 신호</h2>
                </div>
                <div className="flex items-center gap-2">
                  <button
                    type="button"
                    onClick={() => setIsMlSignalExpanded((prev) => !prev)}
                    className="rounded border border-slate-700 px-2 py-1 text-[10px] font-bold text-slate-300 transition hover:border-cyan-500/30 hover:text-white"
                  >
                    {isMlSignalExpanded ? '접기' : '펼치기'}
                  </button>
                  <button
                    type="button"
                    onClick={fetchMlSignal}
                    disabled={mlSignalLoading}
                    className="rounded border border-cyan-500/30 px-2 py-1 text-[10px] font-bold text-cyan-300 transition hover:bg-cyan-950/30 disabled:opacity-50"
                  >
                    {mlSignalLoading ? '조회 중' : '갱신'}
                  </button>
                </div>
              </div>

              {!isMlSignalExpanded ? (
                <div className="rounded border border-[#1f2945] bg-[#070b19] px-3 py-3 text-[11px] leading-5 text-slate-400">
                  펼쳐서 ML 참고 신호를 확인할 수 있습니다.
                </div>
              ) : mlSignalLoading ? (
                <div className="rounded border border-[#1f2945] bg-[#070b19] px-3 py-4 text-center text-[11px] font-mono text-cyan-300">
                  활성 모델 신호 확인 중...
                </div>
              ) : mlSignal ? (
                <div className="flex flex-col gap-3">
                  {(() => {
                    const performance = mlSignal.meta?.performance
                    if (!performance) return null

                    return (
                      <div className="rounded border border-emerald-900/30 bg-emerald-950/10 px-3 py-2">
                        <div className="flex items-center justify-between gap-3">
                          <span className="text-[9px] font-bold uppercase tracking-[0.18em] text-emerald-300">Model Quality</span>
                          <span className="text-[9px] text-slate-500">최근 활성 모델 기준</span>
                        </div>
                        <div className="mt-2 grid grid-cols-2 gap-2">
                          <div className="rounded border border-[#1f2945] bg-[#070b19] p-2">
                            <p className="text-[9px] text-slate-500">CV ROC AUC</p>
                            <p className="mt-1 font-mono text-xs font-bold text-white">{formatMetric(performance.cv_roc_auc)}</p>
                          </div>
                          <div className="rounded border border-[#1f2945] bg-[#070b19] p-2">
                            <p className="text-[9px] text-slate-500">상위 10% 적중</p>
                            <p className="mt-1 font-mono text-xs font-bold text-white">{formatPercent(performance.precision_at_top_10pct)}</p>
                          </div>
                          <div className="rounded border border-[#1f2945] bg-[#070b19] p-2">
                            <p className="text-[9px] text-slate-500">복합 초과수익</p>
                            <p className="mt-1 font-mono text-xs font-bold text-emerald-300">{formatReturnPercent(performance.composite_excess_return_net)}</p>
                          </div>
                          <div className="rounded border border-[#1f2945] bg-[#070b19] p-2">
                            <p className="text-[9px] text-slate-500">최대 낙폭</p>
                            <p className="mt-1 font-mono text-xs font-bold text-rose-300">{formatReturnPercent(performance.composite_max_drawdown_net)}</p>
                          </div>
                        </div>
                      </div>
                    )
                  })()}

                  <div className="flex flex-wrap items-center gap-2">
                    <span className={`rounded border px-2 py-1 text-[10px] font-black tracking-widest ${getSignalGradeTone(mlSignal.signal_grade)}`}>
                      {getSignalGradeLabel(mlSignal.signal_grade)}
                    </span>
                    <span className="rounded border border-slate-700 bg-slate-900/70 px-2 py-1 text-[10px] font-bold text-slate-300">
                      {mlSignal.position || 'HOLD'}
                    </span>
                    <span className="rounded border border-cyan-500/20 bg-cyan-950/20 px-2 py-1 text-[10px] font-bold text-cyan-300">
                      {mlSignal.model_version || mlSignal.meta?.model_version || '-'}
                    </span>
                  </div>

                  <p className="break-words text-[11px] leading-5 text-slate-300">
                    {mlSignal.reason_summary || '현재 모델 신호를 요약할 수 없습니다.'}
                  </p>

                  {getPolicyReasonLabels(mlSignal).length > 0 && (
                    <div className="flex flex-wrap gap-1.5">
                      {getPolicyReasonLabels(mlSignal).slice(0, 4).map((reason) => (
                        <span
                          key={reason}
                          className="rounded border border-slate-700/80 bg-slate-900/70 px-2 py-1 text-[9px] font-bold text-slate-300"
                        >
                          {reason}
                        </span>
                      ))}
                    </div>
                  )}

                  <div className="grid grid-cols-3 gap-2">
                    <div className="rounded border border-[#1f2945] bg-[#070b19] p-2">
                      <p className="text-[9px] text-slate-500">상승 확률</p>
                      <p className="mt-1 font-mono text-xs font-bold text-emerald-300">{formatProbability(mlSignal.up_probability)}</p>
                    </div>
                    <div className="rounded border border-[#1f2945] bg-[#070b19] p-2">
                      <p className="text-[9px] text-slate-500">하락 위험</p>
                      <p className="mt-1 font-mono text-xs font-bold text-amber-300">{formatProbability(mlSignal.risk_probability)}</p>
                    </div>
                    <div className="rounded border border-[#1f2945] bg-[#070b19] p-2">
                      <p className="text-[9px] text-slate-500">복합 점수</p>
                      <p className="mt-1 font-mono text-xs font-bold text-cyan-300">{formatSignalScore(mlSignal.signal_score)}</p>
                    </div>
                  </div>

                  <div className="grid grid-cols-2 gap-2">
                    <div className="rounded border border-[#1f2945] bg-[#070b19] p-2">
                      <p className="text-[9px] text-slate-500">진입 거리</p>
                      <p className="mt-1 font-mono text-xs font-bold text-white">{formatDecimalMetric(mlSignal.long_entry_distance, 3)}</p>
                    </div>
                    <div className="rounded border border-[#1f2945] bg-[#070b19] p-2">
                      <p className="text-[9px] text-slate-500">거래량 확인</p>
                      <p className={`mt-1 font-mono text-xs font-bold ${Number(mlSignal.volume_ratio_5 || 0) >= 0.7 ? 'text-emerald-300' : 'text-amber-300'}`}>
                        {formatRatio(mlSignal.volume_ratio_5)}
                      </p>
                    </div>
                    <div className="rounded border border-[#1f2945] bg-[#070b19] p-2">
                      <p className="text-[9px] text-slate-500">시장 폭</p>
                      <p className="mt-1 font-mono text-xs font-bold text-slate-200">{formatProbability(mlSignal.market_breadth_5)}</p>
                    </div>
                    <div className="rounded border border-[#1f2945] bg-[#070b19] p-2">
                      <p className="text-[9px] text-slate-500">섹터 강도</p>
                      <p className="mt-1 font-mono text-xs font-bold text-slate-200">{formatDecimalMetric(mlSignal.sector_strength_score, 2)}</p>
                    </div>
                  </div>

                  <div className="rounded border border-[#1f2945] bg-[#070b19]/80 px-3 py-2 text-[10px] leading-4 text-slate-400">
                    <div className="flex justify-between gap-3">
                      <span>추천 티어</span>
                      <span className="font-mono font-bold text-white">{mlSignal.recommendation_tier || mlSignal.position || '-'}</span>
                    </div>
                    <div className="mt-1 flex justify-between gap-3">
                      <span>정책 국면</span>
                      <span className="font-mono font-bold text-white">{mlSignal.market_regime_state || '-'}</span>
                    </div>
                    <div className="mt-1 flex justify-between gap-3">
                      <span>조정 스프레드</span>
                      <span className="font-mono font-bold text-white">{formatDecimalMetric(mlSignal.adjusted_composite_spread, 3)}</span>
                    </div>
                  </div>

                  <div className="rounded border border-amber-900/40 bg-amber-950/10 px-3 py-2 text-[9px] leading-4 text-amber-300">
                    AI 신호는 주문 실행 근거가 아니라 참고 지표입니다. 주문 전 사전검증과 사용자 승인을 우선합니다.
                  </div>

                  <p className="font-mono text-[10px] text-slate-500">
                    예측 {formatStaleness(mlSignal.staleness_minutes)} · {mlSignal.predicted_at || mlSignal.date || '-'}
                  </p>
                </div>
              ) : (
                <div className="rounded border border-[#1f2945] bg-[#070b19] px-3 py-4 text-[11px] leading-5 text-slate-400">
                  {mlSignalMessage || '현재 표시할 AI 시그널이 없습니다.'}
                </div>
              )}
            </div>
            
            {/* 주문 입력 폼 카드 */}
            <div className="bg-[#0e1529]/90 border border-[#1f2945] rounded-xl p-4 flex flex-col gap-4 backdrop-blur-md">
              <div className="flex justify-between items-center border-b border-[#1f2945] pb-2">
                <span className="text-xs font-bold text-white">수동 주문 제어</span>
                <span className="text-[9px] font-bold text-slate-500">Human-in-the-Loop</span>
              </div>

              {exchange === 'BINANCE_UM_FUTURES' ? (
                <div className="grid grid-cols-2 gap-1 bg-[#1b253b] p-0.5 rounded border border-[#2b395b]">
                  {Object.entries(futuresIntentMeta).map(([key, item]) => (
                    <button
                      key={key}
                      type="button"
                      onClick={() => setFuturesIntent(key)}
                      className={`text-xs font-bold py-1.5 rounded transition-all cursor-pointer ${
                        futuresIntent === key
                          ? item.tone === 'red'
                            ? 'bg-[#ef4444] text-white'
                            : item.tone === 'blue'
                              ? 'bg-[#3b82f6] text-white'
                              : 'bg-slate-600 text-white'
                          : 'text-slate-400 hover:text-white'
                      }`}
                    >
                      {item.label}
                    </button>
                  ))}
                </div>
              ) : (
                <div className="grid grid-cols-2 gap-1 bg-[#1b253b] p-0.5 rounded border border-[#2b395b]">
                  <button
                    type="button"
                    onClick={() => setSide('BUY')}
                    className={`text-xs font-bold py-1.5 rounded transition-all cursor-pointer ${side === 'BUY' ? 'bg-[#ef4444] text-white' : 'text-slate-400 hover:text-white'}`}
                  >
                    구매
                  </button>
                  <button
                    type="button"
                    onClick={() => setSide('SELL')}
                    className={`text-xs font-bold py-1.5 rounded transition-all cursor-pointer ${side === 'SELL' ? 'bg-[#3b82f6] text-white' : 'text-slate-400 hover:text-white'}`}
                  >
                    판매
                  </button>
                </div>
              )}
              {exchange === 'BINANCE_UM_FUTURES' && (
                <p className="text-[9px] leading-relaxed text-slate-500">
                  청산 버튼은 Reduce Only로 전송되어 포지션이 반대로 뒤집히는 것을 방지합니다.
                </p>
              )}

              {/* 지정가/시장가 선택 */}
              <div className="flex justify-between items-center text-xs">
                <span className="text-slate-400 font-bold">호가 구분</span>
                <div className="flex gap-4">
                  <label className="flex items-center gap-1.5 text-slate-300 cursor-pointer select-none">
                    <input
                      type="radio"
                      name="orderType"
                      value="LIMIT"
                      checked={orderType === 'LIMIT'}
                      onChange={() => setOrderType('LIMIT')}
                      className="accent-cyan-400"
                    />
                    지정가
                  </label>
                  <label className="flex items-center gap-1.5 text-slate-300 cursor-pointer select-none">
                    <input
                      type="radio"
                      name="orderType"
                      value="MARKET"
                      checked={orderType === 'MARKET'}
                      onChange={() => {
                        if (exchange !== 'COINONE') setOrderType('MARKET')
                      }}
                      disabled={exchange === 'COINONE'}
                      className="accent-cyan-400"
                    />
                    시장가
                  </label>
                </div>
              </div>
              {exchange === 'COINONE' && (
                <p className="text-[10px] leading-relaxed text-slate-500">
                  코인원 실주문은 안전 검증이 완료된 지정가 주문만 지원합니다.
                </p>
              )}
              {exchange === 'BINANCE_UM_FUTURES' && (
                <div className="rounded border border-cyan-900/50 bg-cyan-950/20 p-3 text-[10px] leading-relaxed text-cyan-100">
                  <div className="mb-2 font-bold text-cyan-300">바이낸스 USD-M 선물 주문 옵션</div>
                  <div className="mt-2 grid grid-cols-1 gap-2 sm:grid-cols-2">
                    <div>
                      <label className="mb-1 block text-[9px] font-bold text-slate-400">레버리지 배수</label>
                      <div className="flex items-center gap-2">
                        <input
                          type="number"
                          min="1"
                          max="125"
                          step="1"
                          value={futuresLeverage}
                          onChange={(event) => setFuturesLeverage(event.target.value)}
                          className="w-full rounded border border-slate-700 bg-[#070b19] px-2 py-1.5 font-mono text-xs text-white focus:border-cyan-400 focus:outline-none"
                        />
                        <span className="font-mono font-bold text-cyan-300">x</span>
                      </div>
                    </div>
                    <div>
                      <label className="mb-1 block text-[9px] font-bold text-slate-400">마진 모드</label>
                      <div className="grid grid-cols-2 gap-1">
                        {[
                          { key: 'CROSSED', label: '교차' },
                          { key: 'ISOLATED', label: '격리' },
                        ].map((item) => (
                          <button
                            key={item.key}
                            type="button"
                            onClick={() => setFuturesMarginType(item.key)}
                            className={`rounded border px-2 py-1.5 font-bold transition ${
                              futuresMarginType === item.key
                                ? 'border-cyan-400 bg-cyan-400/15 text-white'
                                : 'border-slate-700 text-slate-400 hover:text-white'
                            }`}
                          >
                            {item.label}
                          </button>
                        ))}
                      </div>
                    </div>
                  </div>
                  <div className="mt-2 rounded border border-slate-800 bg-slate-950/40 px-2 py-1.5 text-slate-300">
                    주문 방식: {effectiveReduceOnly ? '청산 전용 Reduce Only' : '신규 진입 또는 포지션 추가'}
                  </div>
                  <div className="mt-2 text-[9px] text-slate-400">
                    앱은 기본적으로 One-way 호환 주문을 전송합니다. Hedge Mode 전용 LONG/SHORT 슬롯 주문은 별도 고급 옵션으로 분리하는 편이 안전합니다.
                  </div>
                </div>
              )}

              {/* 주문 제출 폼 */}
              <form onSubmit={handlePlaceOrder} className="flex flex-col gap-4">
                {/* 1. 가격 입력 */}
                <div className="flex flex-col gap-1.5">
                  <span className="text-[10px] text-slate-400 font-bold">주문 단가 ({orderCurrencyCode})</span>
                  <input
                    type="number"
                    disabled={orderType === 'MARKET'}
                    value={orderType === 'MARKET' ? currentPrice : price}
                    onChange={(e) => setPrice(e.target.value)}
                    placeholder="단가를 입력하세요"
                    className="w-full bg-[#070b19] border border-[#1f2945] text-[#e2e2ec] font-mono rounded px-3 py-2 text-xs focus:outline-none focus:border-cyan-400 disabled:opacity-50 disabled:bg-[#12192b]"
                  />
                </div>

                {/* 2. 수량 입력 */}
                <div className="flex flex-col gap-1.5">
                  <span className="text-[10px] text-slate-400 font-bold">주문 수량</span>
                  <input
                    type="number"
                    step="any"
                    value={quantity}
                    onChange={(e) => setQuantity(e.target.value)}
                    placeholder="수량을 입력하세요"
                    className="w-full bg-[#070b19] border border-[#1f2945] text-[#e2e2ec] font-mono rounded px-3 py-2 text-xs focus:outline-none focus:border-cyan-400"
                    required
                  />
                </div>

                {/* 3. 거래 계좌 스위처 토글 */}
                <div className="flex flex-col gap-1.5">
                  <span className="text-[10px] text-slate-400 font-bold">주문 거래소 계좌</span>
                  {resolvedAssetType === 'STOCK' ? (
                    <div className="grid grid-cols-3 gap-1 bg-[#070b19] p-0.5 rounded border border-[#1f2945]">
                      <button
                        type="button"
                        onClick={() => handleExchangeChange('KIS', 'MOCK')}
                        className={`text-[10px] font-bold py-1.5 rounded transition-all cursor-pointer ${exchange === 'KIS' && brokerEnv === 'MOCK' ? 'bg-[#1b253b] text-cyan-400 border border-cyan-900/60' : 'text-slate-400 hover:text-white'}`}
                      >
                        한투 모의
                      </button>
                      <button
                        type="button"
                        onClick={() => handleExchangeChange('KIS', 'REAL')}
                        className={`text-[10px] font-bold py-1.5 rounded transition-all cursor-pointer ${exchange === 'KIS' && brokerEnv === 'REAL' ? 'bg-[#1b253b] text-cyan-400 border border-cyan-900/60' : 'text-slate-400 hover:text-white'}`}
                      >
                        한투 실거래
                      </button>
                      <button
                        type="button"
                        onClick={() => handleExchangeChange('TOSS', 'REAL')}
                        className={`text-[10px] font-bold py-1.5 rounded transition-all cursor-pointer ${exchange === 'TOSS' && brokerEnv === 'REAL' ? 'bg-[#1b253b] text-cyan-400 border border-cyan-900/60' : 'text-slate-400 hover:text-white'}`}
                      >
                        토스 실거래
                      </button>
                    </div>
                  ) : (
                    <div className="grid grid-cols-3 gap-1 bg-[#070b19] p-0.5 rounded border border-[#1f2945]">
                      <button
                        type="button"
                        onClick={() => handleExchangeChange('COINONE', 'REAL')}
                        className={`text-[10px] font-bold py-1.5 rounded transition-all cursor-pointer ${exchange === 'COINONE' ? 'bg-[#1b253b] text-cyan-400 border border-cyan-900/60' : 'text-slate-400 hover:text-white'}`}
                      >
                        코인원
                      </button>
                      <button
                        type="button"
                        onClick={() => handleExchangeChange('BINANCE', 'REAL')}
                        className={`text-[10px] font-bold py-1.5 rounded transition-all cursor-pointer ${exchange === 'BINANCE' ? 'bg-[#1b253b] text-cyan-400 border border-cyan-900/60' : 'text-slate-400 hover:text-white'}`}
                      >
                        바이낸스 현물
                      </button>
                      <button
                        type="button"
                        onClick={() => handleExchangeChange('BINANCE_UM_FUTURES', 'MOCK')}
                        className={`text-[10px] font-bold py-1.5 rounded transition-all cursor-pointer ${exchange === 'BINANCE_UM_FUTURES' ? 'bg-[#1b253b] text-cyan-400 border border-cyan-900/60' : 'text-slate-400 hover:text-white'}`}
                      >
                        선물 모의
                      </button>
                    </div>
                  )}
                </div>

                {/* 4. 총 주문 예정 금액 */}
                <div className="bg-[#070b19] border border-[#1f2945] rounded p-3 flex justify-between items-center text-xs">
                  <span className="text-slate-400 font-bold">예정 금액</span>
                  <span className="font-mono font-bold text-white">
                    {getCurrencySign()}{totalEstimatedAmount.toLocaleString(undefined, { maximumFractionDigits: getCurrencyDigits() })}
                  </span>
                </div>

                <div className="bg-[#070b19] border border-[#1f2945] rounded p-3 flex flex-col gap-2 text-[10px] font-mono">
                  <div className="flex items-center justify-between">
                    <span className="text-slate-400 font-bold">주문 사전검증</span>
                    <span className={`font-bold ${precheckLoading ? 'text-cyan-400' : 'text-slate-500'}`}>
                      {precheckLoading ? '검증 중...' : '대기'}
                    </span>
                  </div>
                  {orderPrecheck && (
                    <>
                      <div className="flex justify-between text-slate-300">
                        <span>기준가</span>
                        <span className="text-white">
                          {formatUnitPrice(orderPrecheck.reference_price || 0)}
                        </span>
                      </div>
                      <div className="flex justify-between text-slate-300">
                        <span>금액 산정 기준</span>
                        <span className="text-white">{orderPrecheck.price_source}</span>
                      </div>
                      {exchange === 'BINANCE_UM_FUTURES' && orderPrecheck.futures_options && (
                        <>
                          <div className="flex justify-between text-slate-300">
                            <span>선물 옵션</span>
                            <span className="text-white">
                              {currentFuturesIntent.label} · {orderPrecheck.futures_options.margin_type} · {orderPrecheck.futures_options.leverage}x
                            </span>
                          </div>
                          {orderPrecheck.futures_options.max_leverage && (
                            <div className="flex justify-between text-slate-300">
                              <span>심볼 최대 레버리지</span>
                              <span className="text-white">{orderPrecheck.futures_options.max_leverage}x</span>
                            </div>
                          )}
                          {orderPrecheck.futures_options.position_mode && (
                            <div className="flex justify-between text-slate-300">
                              <span>계정 포지션 모드</span>
                              <span className="text-white">
                                {orderPrecheck.futures_options.position_mode === 'HEDGE' ? 'Hedge Mode' : 'One-way Mode'}
                              </span>
                            </div>
                          )}
                          <div className="flex justify-between text-slate-300">
                            <span>명목 주문금액</span>
                            <span className="text-white">
                              {getCurrencySign()}{Number(orderPrecheck.estimated_amount || 0).toLocaleString(undefined, { maximumFractionDigits: getCurrencyDigits() })}
                            </span>
                          </div>
                          <div className="flex justify-between text-slate-300">
                            <span>예상 필요 증거금</span>
                            <span className="text-white">
                              {getCurrencySign()}{Number(orderPrecheck.required_margin || 0).toLocaleString(undefined, { maximumFractionDigits: getCurrencyDigits() })}
                            </span>
                          </div>
                        </>
                      )}
                      {orderPrecheck.available_cash != null && (
                        <div className="flex justify-between text-slate-300">
                          <span>주문 가능 현금</span>
                          <span className="text-white">
                            {getCurrencySign()}{Number(orderPrecheck.available_cash).toLocaleString(undefined, { maximumFractionDigits: getCurrencyDigits() })}
                          </span>
                        </div>
                      )}
                      {orderPrecheck.holding_qty != null && (
                        <div className="flex justify-between text-slate-300">
                          <span>보유 수량</span>
                          <span className="text-white">{Number(orderPrecheck.holding_qty).toLocaleString()}</span>
                        </div>
                      )}
                      {orderPrecheck.exchange_order_test && (
                        <div className="rounded border border-emerald-900/60 bg-emerald-950/20 px-2 py-1.5 leading-relaxed text-emerald-300">
                          거래소 테스트 주문 검증 통과
                          {orderPrecheck.exchange_order_test.commission_rates_requested ? ' · 수수료율 조회 완료' : ''}
                        </div>
                      )}
                      <div className={`rounded border px-2 py-1 leading-relaxed ${
                        isOrderBlocked
                          ? 'border-red-900/60 bg-red-950/30 text-red-300'
                          : 'border-emerald-900/60 bg-emerald-950/20 text-emerald-300'
                      }`}>
                        {isOrderBlocked
                          ? (orderPrecheck.warnings?.join(' ') || '실거래 주문 조건을 다시 확인해 주세요.')
                          : '현재 입력값 기준으로 즉시 주문 가능 범위를 확인했습니다.'}
                      </div>
                    </>
                  )}
                  {!orderPrecheck && precheckMessage && (
                    <div className="rounded border border-amber-900/60 bg-amber-950/20 px-2 py-1 leading-relaxed text-amber-300">
                      {precheckMessage}
                    </div>
                  )}
                </div>

                {/* 5. 자동 감시 조건 체크박스 */}
                {((!isFuturesOrder && side === 'BUY') || (isFuturesOrder && futuresIntent === 'LONG_OPEN')) && (
                  <div className="border-t border-[#1f2945] pt-3 mt-1 flex flex-col gap-2.5">
                    <label className="flex items-center gap-2 text-[11px] text-slate-300 cursor-pointer select-none">
                      <input
                        type="checkbox"
                        checked={autoExit}
                        onChange={(e) => setAutoExit(e.target.checked)}
                        className="accent-cyan-400 rounded"
                      />
                      주문 전송 후 자동 감시 조건 등록
                    </label>

                    {autoExit && (
                      <div className="flex flex-col gap-2">
                        <div className="rounded border border-amber-900/50 bg-amber-950/20 px-2 py-1.5 text-[9px] leading-relaxed text-amber-300">
                          주문 전송 성공 직후 감시 규칙을 등록합니다. 실거래 자동매도는 1회 주문 한도와 거래소/API 권한 검증을 통과해야 실행됩니다.
                        </div>
                        <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
                          <button
                            type="button"
                            onClick={() => setAutoExitExecutionMode('PROPOSAL')}
                            className={`rounded border px-3 py-2 text-left transition ${
                              autoExitExecutionMode === 'PROPOSAL'
                                ? 'border-cyan-400 bg-cyan-950/30 text-cyan-200'
                                : 'border-[#1f2945] bg-[#070b19] text-slate-400 hover:text-slate-200'
                            }`}
                          >
                            <span className="block text-[10px] font-black">매도 제안만 생성</span>
                            <span className="mt-1 block text-[9px] leading-relaxed">조건 도달 시 승인 카드만 만들고 직접 주문은 보내지 않습니다.</span>
                          </button>
                          <button
                            type="button"
                            onClick={() => setAutoExitExecutionMode('AUTO')}
                            className={`rounded border px-3 py-2 text-left transition ${
                              autoExitExecutionMode === 'AUTO'
                                ? 'border-rose-400 bg-rose-950/25 text-rose-200'
                                : 'border-[#1f2945] bg-[#070b19] text-slate-400 hover:text-slate-200'
                            }`}
                          >
                            <span className="block text-[10px] font-black">조건 도달 시 자동 매도</span>
                            <span className="mt-1 block text-[9px] leading-relaxed">감시 워커가 조건 충족 시 매도 주문을 직접 전송합니다.</span>
                          </button>
                        </div>
                        <div className="grid grid-cols-2 gap-2 bg-[#070b19] border border-[#1f2945] rounded p-2.5">
                          <div className="flex flex-col gap-1">
                            <label className="text-[9px] font-bold text-green-400">목표 익절 (%)</label>
                            <input
                              type="number"
                              step="0.1"
                              value={targetProfitRate}
                              onChange={(e) => setTargetProfitRate(e.target.value)}
                              className="bg-slate-800 border border-slate-700 text-[#e2e2ec] font-mono rounded py-0.5 text-xs text-center"
                            />
                          </div>
                          <div className="flex flex-col gap-1">
                            <label className="text-[9px] font-bold text-red-400">손실 제한 (%)</label>
                            <input
                              type="number"
                              step="0.1"
                              value={stopLossRate}
                              onChange={(e) => setStopLossRate(e.target.value)}
                              className="bg-slate-800 border border-slate-700 text-[#e2e2ec] font-mono rounded py-0.5 text-xs text-center"
                            />
                          </div>
                        </div>
                      </div>
                    )}
                  </div>
                )}

                {/* 안전 가드 텍스트 */}
                {brokerEnv === 'REAL' ? (
                  <div className="text-[9px] text-amber-500 bg-amber-950/20 p-2 rounded border border-amber-900/40 leading-relaxed font-mono">
                    실거래 1회 한도 10만원 하드 캐핑 안전 가드 작동 중
                  </div>
                ) : (
                  <div className="text-[9px] text-slate-500 bg-slate-900/40 p-2 rounded border border-[#1f2945]/40 leading-relaxed font-mono">
                    모의투자 테스트 모드 - 주문 한도 무제한
                  </div>
                )}

                {/* 결과 메세지 */}
                {tradeMessage.text && (
                  <div className={`whitespace-pre-line p-2.5 rounded text-xs font-bold leading-relaxed border ${tradeMessage.isError ? 'bg-red-950/40 text-red-400 border-red-900/60' : 'bg-green-950/40 text-green-400 border-green-900/60'}`}>
                    {tradeMessage.text}
                  </div>
                )}

                {/* 주문 제출 버튼 */}
                <button
                  type="submit"
                  disabled={submitting || precheckLoading || isOrderBlocked}
                  className={`w-full py-2.5 rounded font-black text-[#070b19] text-xs tracking-wider transition-all active:scale-[0.98] cursor-pointer disabled:opacity-50 ${
                    isFuturesOrder
                      ? currentFuturesIntent.tone === 'red'
                        ? 'bg-[#ef4444] text-white hover:bg-red-600'
                        : currentFuturesIntent.tone === 'blue'
                          ? 'bg-[#3b82f6] text-white hover:bg-blue-600'
                          : 'bg-slate-600 text-white hover:bg-slate-500'
                      : side === 'BUY'
                        ? 'bg-[#ef4444] text-white hover:bg-red-600'
                        : 'bg-[#3b82f6] text-white hover:bg-blue-600'
                  }`}
                >
                  {submitting ? '주문 전송 중...' : `${isFuturesOrder ? currentFuturesIntent.label : side === 'BUY' ? '구매' : '판매'}하기`}
                </button>
              </form>
            </div>

            {/* 내 보유 주식 카드 (토스 WTS 스타일) */}
            <div className="bg-[#0e1529]/90 border border-[#1f2945] rounded-xl p-4 flex flex-col gap-3 backdrop-blur-md font-mono">
              <div className="flex items-center justify-between gap-3 border-b border-[#1f2945] pb-2">
                <div className="flex items-center gap-2">
                  <span className="w-1.5 h-3 bg-cyan-400 rounded-full" />
                  <span className="text-xs font-bold text-white">내 보유 현황</span>
                </div>
                {(myHoldingAbsQty > 0 || dbEstimatedHolding?.estimatedQty > 0) && (
                  <button
                    type="button"
                    onClick={handleFillFullExitOrder}
                    className="rounded border border-rose-500/30 px-2.5 py-1 text-[10px] font-black text-rose-300 transition hover:bg-rose-950/30"
                  >
                    {exchange === 'BINANCE_UM_FUTURES' ? '전량 청산 입력' : '전량 매도 입력'}
                  </button>
                )}
              </div>

              {myHolding && myHoldingAbsQty > 0 ? (
                <div className="flex flex-col gap-2.5 text-xs">
                  {exchange === 'BINANCE_UM_FUTURES' && (
                    <div className="flex justify-between border-b border-[#1f2945]/30 py-1">
                      <span className="text-slate-400">포지션 방향</span>
                      <span className={myHoldingDirection === 'SHORT' ? 'font-bold text-[#3b82f6]' : 'font-bold text-[#ef4444]'}>
                        {myHoldingDirection === 'SHORT' ? '숏' : '롱'}
                      </span>
                    </div>
                  )}
                  <div className="flex justify-between border-b border-[#1f2945]/30 py-1">
                    <span className="text-slate-400">보유 수량</span>
                    <span className="text-white font-bold">{myHoldingAbsQty.toLocaleString()} {exchange === 'BINANCE_UM_FUTURES' ? '계약' : '주'}</span>
                  </div>
                  <div className="flex justify-between border-b border-[#1f2945]/30 py-1">
                    <span className="text-slate-400">평균 단가</span>
                    <span className="text-white font-bold">
                      {formatUnitPrice(myHolding.avg_price)}
                      {exchange === 'BINANCE_UM_FUTURES' && myHolding.avg_price_source === 'ACCOUNT_FALLBACK' && (
                        <span className="ml-1 text-[9px] text-amber-300">추정</span>
                      )}
                    </span>
                  </div>
                  <div className="flex justify-between border-b border-[#1f2945]/30 py-1">
                    <span className="text-slate-400">현재 평가금</span>
                    <span className="text-white font-bold">
                      {getCurrencySign()}{myHoldingEvalAmount.toLocaleString(undefined, { maximumFractionDigits: getCurrencyDigits() })}
                    </span>
                  </div>
                  <div className="flex justify-between py-1 font-bold">
                    <span className="text-slate-400">평가 손익</span>
                    <span className={Number(myHolding.profit || 0) >= 0 ? 'text-[#ef4444]' : 'text-[#3b82f6]'}>
                      {Number(myHolding.profit || 0) >= 0 ? '+' : ''}{Number(myHolding.profit || 0).toLocaleString()} ({Number(myHolding.profit_rate || 0).toFixed(2)}%)
                    </span>
                  </div>
                </div>
              ) : dbEstimatedHolding ? (
                <div className="flex flex-col gap-2.5 rounded border border-amber-400/40 bg-amber-400/10 px-3 py-3 text-xs">
                  <div className="flex items-center justify-between gap-3">
                    <span className="font-bold text-amber-300">거래내역 기준 추정 보유</span>
                  </div>
                  <div className="flex justify-between border-b border-amber-400/20 py-1">
                    <span className="text-slate-300">추정 수량</span>
                    <span className="font-bold text-white">{dbEstimatedHolding.estimatedQty.toLocaleString()} 주</span>
                  </div>
                  <div className="flex justify-between border-b border-amber-400/20 py-1">
                    <span className="text-slate-300">기록 계좌</span>
                    <span className="font-bold text-white">{dbEstimatedHolding.exchange} ({dbEstimatedHolding.brokerEnv})</span>
                  </div>
                  {dbEstimatedHolding.avgPrice > 0 ? (
                    <div className="flex justify-between border-b border-amber-400/20 py-1">
                      <span className="text-slate-300">추정 평균가</span>
                      <span className="font-bold text-white">₩{dbEstimatedHolding.avgPrice.toLocaleString(undefined, { minimumFractionDigits: 0, maximumFractionDigits: 1 })}</span>
                    </div>
                  ) : null}
                  <p className="leading-relaxed text-amber-200">
                    거래내역에는 체결 매수 기록이 있지만, 현재 선택 계좌의 실제 잔고 API에서는 확인되지 않았습니다. 매도 주문은 실제 KIS 잔고에 수량이 있어야 성공합니다.
                  </p>
                </div>
              ) : balanceMessage ? (
                <div className="rounded border border-amber-900/50 bg-amber-950/20 px-3 py-3 text-[11px] leading-relaxed text-amber-300">
                  {balanceMessage}
                </div>
              ) : (
                <div className="flex flex-col items-center justify-center py-6 text-slate-500 text-xs">
                  <svg className="w-8 h-8 text-slate-600 mb-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.5" d="M20 13V6a2 2 0 00-2-2H6a2 2 0 00-2 2v7m16 0a2 2 0 01-2 2H6a2 2 0 01-2-2m16 0v5a2 2 0 01-2 2H6a2 2 0 01-2-2v-5m16 0h-4M4 13h4" />
                  </svg>
                  <span>{symbol} 종목은 현재 선택한 계좌에서 보유하지 않고 있어요</span>
                </div>
              )}
            </div>

          </div>

        </div>

      </div>
    </div>
  )
}
