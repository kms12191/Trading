import { useState, useEffect, useEffectEvent, useRef } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { createChart, CandlestickSeries } from 'lightweight-charts'
import { supabase, deleteUserWatchlistItem, ensureNewsSummaries, fetchUserWatchlist, normalizeWatchlistItem, upsertUserWatchlistItem } from '../supabaseClient'
import Header from '../components/Header.jsx'
import MemberOnlyModal from '../components/MemberOnlyModal.jsx'
import { getApiErrorMessage } from '../lib/apiError.js'
import { buildManualOrderFingerprint, resolveManualOrderIdempotency, shouldResetManualOrderIdempotency } from '../lib/manualOrderIdempotency.js'
import AssetDetailChartPanel from './assetDetailChartPanel.jsx'
import AssetDetailHeader from './assetDetailHeader.jsx'
import {
  ACTIONABLE_ORDER_STATUSES,
  buildCandleSignature,
  formatDecimalMetric,
  formatDisclosureDate,
  formatMetric,
  formatNewsSource,
  formatPercent,
  formatProbability,
  formatRatio,
  formatRelativeTime as formatTime,
  formatReturnPercent,
  formatSignalScore,
  formatSignedPercentValue,
  formatStaleness,
  getAssetChartPriceFormat,
  getAssetCurrencyDigits,
  getAssetCurrencySign,
  getAssetPriceDigits,
  getAutoExecutionModeLabel,
  getAutoRuleStatusLabel,
  getAutoTriggerLabel,
  getDisclosureToneClass,
  getOrderSideLabel,
  getOrderStatusLabel,
  getPolicyReasonLabels,
  getProbabilityLevel,
  getSignalGradeLabel,
  getSignalGradeTone,
  isActionableOrderStatus,
  isCancelReplaceExchange,
  isUsStockSymbol,
  normalizeCandleTime,
  normalizeStockSymbol,
} from './assetDetailModel.js'

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:5050'
const OPEN_ORDER_SELECT_FIELDS = 'id,exchange,asset_type,ticker,symbol,side,price,volume,ord_type,currency,broker_env,external_order_id,status,created_at'
const AUTO_RULE_SELECT_FIELDS = 'id,exchange,asset_type,ticker,symbol,broker_env,entry_price,investment_amount,quantity,target_profit_rate,stop_loss_rate,execution_mode,trigger_side,trigger_price,triggered_at,last_checked_at,last_error,status,created_at,updated_at'

export default function AssetDetail({ isLoggedIn, userEmail, handleLogout, userProfile }) {
  const { assetType, symbol } = useParams()
  const navigate = useNavigate()
  const normalizedRouteAssetType = String(assetType || '').toUpperCase() === 'STOCK' ? 'STOCK' : 'CRYPTO'
  const [resolvedAssetType, setResolvedAssetType] = useState(normalizedRouteAssetType)
  const [resolvedSymbol, setResolvedSymbol] = useState(normalizeStockSymbol(symbol))
  const [resolvedMarket, setResolvedMarket] = useState('')
  const isResolvedUsStock = resolvedAssetType === 'STOCK' && isUsStockSymbol(resolvedSymbol, resolvedMarket)

  // API 권한 체크 헬퍼
  const getBinancePermissions = () => {
    if (!brokerAvailability || !isLoggedIn) return null;
    const binanceData = brokerAvailability['BINANCE'];
    if (!binanceData || !binanceData.accounts) return null;
    
    const activeAccount = binanceData.accounts.find(
      acc => String(acc.broker_env).toUpperCase() === String(brokerEnv).toUpperCase()
    );
    return activeAccount?.api_permissions || null;
  };

  const isBinancePermissionMissing = () => {
    if (brokerEnv !== 'REAL') return false;
    
    const perms = getBinancePermissions();
    if (!perms || Object.keys(perms).length === 0) return false;
    
    if (exchange === 'BINANCE') {
      return perms.spot_trade_enabled === false;
    }
    if (exchange === 'BINANCE_UM_FUTURES') {
      return perms.futures_trade_enabled === false;
    }
    return false;
  };

  const getCurrencySign = () => {
    return getAssetCurrencySign({ exchange, assetType: resolvedAssetType, isUsStock: isResolvedUsStock })
  };

  const getCurrencyDigits = () => {
    return getAssetCurrencyDigits({ exchange, assetType: resolvedAssetType, isUsStock: isResolvedUsStock })
  };

  const getPriceDigitsForValue = (value) => {
    return getAssetPriceDigits(value, { exchange, assetType: resolvedAssetType, isUsStock: isResolvedUsStock })
  }

  const formatUnitPrice = (value) => {
    const numeric = Number(value)
    if (!Number.isFinite(numeric)) return '-'
    const digits = getPriceDigitsForValue(numeric)
    return `${getCurrencySign()}${numeric.toLocaleString(undefined, { minimumFractionDigits: digits, maximumFractionDigits: digits })}`
  }

  const getChartPriceFormat = (value) => {
    return getAssetChartPriceFormat(value, { exchange, assetType: resolvedAssetType, isUsStock: isResolvedUsStock, currentPrice })
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
  const [oppositeCurrentPrice, setOppositeCurrentPrice] = useState(null)

  // 4. 주문 폼 상태
  const [side, setSide] = useState('BUY') // BUY | SELL
  const [orderType, setOrderType] = useState('LIMIT') // LIMIT | MARKET
  const [price, setPrice] = useState('')
  const [quantity, setQuantity] = useState('')
  const [autoExit, setAutoExit] = useState(false)
  const [targetProfitRate, setTargetProfitRate] = useState(5.0)
  const [stopLossRate, setStopLossRate] = useState(-3.0)
  const [autoExitExecutionMode, setAutoExitExecutionMode] = useState('PROPOSAL')
  const [autoExitRateType, setAutoExitRateType] = useState('PRICE') // PRICE | ROE
  const [autoRestartOnPartialFill, setAutoRestartOnPartialFill] = useState(true)
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
  const getAutoExitTargetPrices = () => {
    const entryPrice = parseFloat(price) || currentPrice || 0
    if (entryPrice <= 0) return null
    
    const rawTP = parseFloat(targetProfitRate) || 0
    const rawSL = parseFloat(stopLossRate) || 0
    const lev = isFuturesOrder ? (Number(futuresLeverage) || 1) : 1
    
    // 최종 가격 변동 비율 (%)
    const tpPercent = autoExitRateType === 'ROE' ? (rawTP / lev) : rawTP
    const slPercent = autoExitRateType === 'ROE' ? (rawSL / lev) : rawSL
    
    // 숏 포지션(숏 진입) 여부 판별
    const isShort = isFuturesOrder && futuresIntent === 'SHORT_OPEN'
    
    let tpPrice
    let slPrice
    
    if (isShort) {
      // 숏은 가격 하락 시 익절, 상승 시 손절
      tpPrice = entryPrice * (1 - tpPercent / 100)
      slPrice = entryPrice * (1 - slPercent / 100)
    } else {
      // 롱 및 국내 주식 매수는 가격 상승 시 익절, 하락 시 손절
      tpPrice = entryPrice * (1 + tpPercent / 100)
      slPrice = entryPrice * (1 + slPercent / 100)
    }
    
    return {
      tpPrice,
      slPrice,
      tpPercent,
      slPercent
    }
  }

  const effectiveSide = isFuturesOrder ? currentFuturesIntent.side : side
  const effectiveReduceOnly = isFuturesOrder ? currentFuturesIntent.reduceOnly : false

  // 5. 트랜잭션 UI 상태
  const [submitting, setSubmitting] = useState(false)
  const [tradeMessage, setTradeMessage] = useState({ text: '', isError: false })

  // 6. 실시간 호가, 체결, 보유자산 상태 (WTS 연동 고도화)
  const [, setTrades] = useState([])
  const [userBalance, setUserBalance] = useState(null)
  const [balanceMessage, setBalanceMessage] = useState('')
  const [activeTab, setActiveTab] = useState('news') // news | community
  const [newsList, setNewsList] = useState([])
  const [loadingNews, setLoadingNews] = useState(false)
  const [newsSyncing, setNewsSyncing] = useState(false)
  const [newsSyncMessage, setNewsSyncMessage] = useState({ text: '', isError: false })
  const [selectedNewsId, setSelectedNewsId] = useState('')
  const [summaryLoadingId, setSummaryLoadingId] = useState('')
  const [memberOnlyMessage, setMemberOnlyMessage] = useState('')
  const [disclosureList, setDisclosureList] = useState([])
  const [loadingDisclosures, setLoadingDisclosures] = useState(false)
  const [selectedDisclosureId, setSelectedDisclosureId] = useState('')
  const [disclosureAnalyses, setDisclosureAnalyses] = useState({})
  const [disclosureAnalysisLoadingId, setDisclosureAnalysisLoadingId] = useState('')
  const [disclosureSyncing, setDisclosureSyncing] = useState(false)
  const [disclosureSyncMessage, setDisclosureSyncMessage] = useState({ text: '', isError: false })
  const [communityPosts, setCommunityPosts] = useState([])
  const [communityProfiles, setCommunityProfiles] = useState({})
  const [communityCurrentUserId, setCommunityCurrentUserId] = useState('')
  const [communityDraft, setCommunityDraft] = useState('')
  const [communityReplyParentId, setCommunityReplyParentId] = useState('')
  const [communityReplyDraft, setCommunityReplyDraft] = useState('')
  const [communityLoading, setCommunityLoading] = useState(false)
  const [communitySubmitting, setCommunitySubmitting] = useState(false)
  const [communityActionId, setCommunityActionId] = useState('')
  const [communityMessage, setCommunityMessage] = useState({ text: '', isError: false })
  const [displayName, setDisplayName] = useState(symbol)
  const [stockWarnings, setStockWarnings] = useState([])
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

  // URL 파라미터 변경 시 렌더링 도중에 상태 즉시 동기화 (컴포넌트 재사용 버그 원천 차단)
  const [prevSymbol, setPrevSymbol] = useState(symbol)
  const [prevAssetType, setPrevAssetType] = useState(assetType)

  if (symbol !== prevSymbol || assetType !== prevAssetType) {
    setPrevSymbol(symbol)
    setPrevAssetType(assetType)
    setResolvedSymbol(normalizeStockSymbol(symbol))
    setResolvedAssetType(normalizedRouteAssetType)
    setSymbolLookupReady(false)
  }
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
  const [editingRuleId, setEditingRuleId] = useState(null)
  const [editTargetProfit, setEditTargetProfit] = useState('')
  const [editStopLoss, setEditStopLoss] = useState('')
  const [editQuantity, setEditQuantity] = useState('')
  const [ruleUpdating, setRuleUpdating] = useState(false)

  const [showAddRuleForm, setShowAddRuleForm] = useState(false)
  const [addRulePrice, setAddRulePrice] = useState('')
  const [addRuleQty, setAddRuleQty] = useState('')
  const [addRuleProfitRate, setAddRuleProfitRate] = useState('5.0')
  const [addRuleStopRate, setAddRuleStopRate] = useState('-3.0')
  const [addRuleExecutionMode, setAddRuleExecutionMode] = useState('PROPOSAL')
  const [addRuleAutoRestart, setAddRuleAutoRestart] = useState(true)

  const handleAddRule = async () => {
    if (!addRulePrice || parseFloat(addRulePrice) <= 0) {
      alert('진입 가격을 정확하게 입력해주세요.')
      return
    }
    if (!addRuleQty || parseFloat(addRuleQty) <= 0) {
      alert('수량을 정확하게 입력해주세요.')
      return
    }
    if (!addRuleProfitRate || !addRuleStopRate) {
      alert('익절 및 손절 비율을 올바르게 입력해주세요.')
      return
    }

    setRuleUpdating(true)
    try {
      const authHeader = await getAuthHeader()
      if (!authHeader) {
        alert('로그인이 필요합니다.')
        return
      }
      const response = await fetch(`${API_BASE_URL}/api/trade/auto-trading-rule`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': authHeader,
        },
        body: JSON.stringify({
          exchange,
          asset_type: normalizedRouteAssetType,
          symbol: getExchangeSymbol(exchange),
          entry_price: parseFloat(addRulePrice),
          quantity: parseFloat(addRuleQty),
          target_profit_rate: parseFloat(addRuleProfitRate),
          stop_loss_rate: parseFloat(addRuleStopRate),
          execution_mode: addRuleExecutionMode,
          auto_restart_on_partial_fill: addRuleAutoRestart,
          broker_env: brokerEnv,
        }),
      })
      const result = await response.json()
      if (result.success) {
        setShowAddRuleForm(false)
        setAddRulePrice('')
        setAddRuleQty('')
        setAddRuleAutoRestart(true)
        loadAutoTradingRules()
      } else {
        alert(result.message || '조건감시 규칙 등록에 실패했습니다.')
      }
    } catch (error) {
      console.error('Add rule error:', error)
      alert('서버 통신 오류가 발생했습니다.')
    } finally {
      setRuleUpdating(false)
    }
  }

  const chartContainerRef = useRef(null)
  const chartRef = useRef(null)
  const candleSeriesRef = useRef(null)
  const hasAppliedInitialFitRef = useRef(false)
  const abortControllerRef = useRef(null)
  const metadataAbortControllerRef = useRef(null)
  const lastCandleSignatureRef = useRef('')
  const orderbookTradesInFlightRef = useRef(false)
  const candlesInFlightRef = useRef(false)
  const manualOrderIdempotencyRef = useRef(null)

  const isIntradayInterval = !['1d', '1w', '1M'].includes(chartInterval)
  const effectiveOrderPrice = orderType === 'LIMIT' ? Number(price || 0) : currentPrice
  const totalEstimatedAmount = effectiveOrderPrice * Number(quantity || 0)
  const isStockAsset = resolvedAssetType === 'STOCK'
  const orderCurrencyCode = exchange === 'COINONE'
    ? 'KRW'
    : exchange === 'BINANCE'
      ? 'USD'
      : (isResolvedUsStock ? 'USD' : 'KRW')
  const showLevel2Panel = false
  const [balanceCooldown, setBalanceCooldown] = useState(0)
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

  const normalizeCryptoBaseSymbol = (value) => {
    let normalized = String(value || '').trim().toUpperCase()
    if (!normalized) return ''
    normalized = normalized.replace('_', '-').replace('/', '-')
    const parts = normalized.split('-').filter(Boolean)
    if (parts.length === 2) {
      if (['KRW', 'USDT', 'BUSD', 'USDC'].includes(parts[0])) return parts[1]
      if (['KRW', 'USDT', 'BUSD', 'USDC'].includes(parts[1])) return parts[0]
    }
    for (const suffix of ['USDT', 'BUSD', 'USDC', 'KRW']) {
      if (normalized.endsWith(suffix) && normalized.length > suffix.length) {
        return normalized.slice(0, -suffix.length)
      }
    }
    return normalized
  }

  const getDetailBaseSymbol = () => (
    resolvedAssetType === 'CRYPTO'
      ? normalizeCryptoBaseSymbol(symbol)
      : normalizeStockSymbol(resolvedSymbol || symbol)
  )

  const getExchangeSymbol = (targetExchange = exchange) => {
    if (resolvedAssetType !== 'CRYPTO') return normalizeStockSymbol(resolvedSymbol || symbol)
    const baseSymbol = getDetailBaseSymbol()
    if (!baseSymbol) return ''
    if (targetExchange === 'COINONE') return baseSymbol
    if (['BINANCE', 'BINANCE_UM_FUTURES'].includes(targetExchange)) return `${baseSymbol}USDT`
    return baseSymbol
  }

  const getSymbolQueryCandidates = () => {
    const rawSymbol = String(symbol || '').trim().toUpperCase()
    if (resolvedAssetType !== 'CRYPTO') {
      const canonicalSymbol = normalizeStockSymbol(resolvedSymbol || rawSymbol)
      return [...new Set([
        canonicalSymbol,
        rawSymbol,
        canonicalSymbol.replace(/^A(?=\d{6}$)/, ''),
        rawSymbol.replace(/^A(?=\d{6}$)/, ''),
      ].filter(Boolean))]
    }
    const baseSymbol = normalizeCryptoBaseSymbol(rawSymbol)
    return [...new Set([
      baseSymbol,
      `${baseSymbol}USDT`,
      `KRW-${baseSymbol}`,
      `${baseSymbol}KRW`,
      `${baseSymbol}/USDT`,
      `${baseSymbol}/KRW`,
    ].filter(Boolean))]
  }

  const buildSymbolOrFilter = () => getSymbolQueryCandidates()
    .flatMap((candidate) => [`symbol.eq.${candidate}`, `ticker.eq.${candidate}`])
    .join(',')

  const loadOpenOrders = async () => {
    const { data: { session } } = await supabase.auth.getSession()
    if (!session?.user?.id || !symbol) {
      setOpenOrders([])
      return
    }

    setOpenOrdersLoading(true)
    try {
      let query = supabase
        .from('trade_proposals')
        .select(OPEN_ORDER_SELECT_FIELDS)
        .eq('exchange', exchange)
        .in('status', ACTIONABLE_ORDER_STATUSES)
        .or(buildSymbolOrFilter())
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

  const handleStartEditRule = (rule) => {
    setEditingRuleId(rule.id)
    setEditTargetProfit(String(rule.target_profit_rate || 5.0))
    const rawStopRate = Number(rule.stop_loss_rate || -3.0)
    setEditStopLoss(String(rawStopRate > 0 ? -Math.abs(rawStopRate) : rawStopRate))
    setEditQuantity(String(rule.quantity || ''))
  }

  const handleUpdateRule = async (ruleId) => {
    if (!editTargetProfit || !editStopLoss) {
      alert('익절 및 손절 비율을 올바르게 입력해주세요.')
      return
    }
    setRuleUpdating(true)
    try {
      const authHeader = await getAuthHeader()
      if (!authHeader) {
        alert('로그인이 필요합니다.')
        return
      }
      const response = await fetch(`${API_BASE_URL}/api/trade/auto-trading-rule`, {
        method: 'PATCH',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': authHeader,
        },
        body: JSON.stringify({
          rule_id: ruleId,
          target_profit_rate: parseFloat(editTargetProfit),
          stop_loss_rate: parseFloat(editStopLoss),
          quantity: editQuantity ? parseFloat(editQuantity) : null,
          status: 'RUNNING',
        }),
      })
      const result = await response.json()
      if (result.success) {
        setEditingRuleId(null)
        loadAutoTradingRules()
      } else {
        alert(result.message || '조건감시 규칙 수정에 실패했습니다.')
      }
    } catch (error) {
      console.error('Update rule error:', error)
      alert('서버 통신 오류가 발생했습니다.')
    } finally {
      setRuleUpdating(false)
    }
  }

  const handleStopRule = async (ruleId) => {
    if (!confirm('해당 조건감시를 정지하시겠습니까?')) return
    setRuleUpdating(true)
    try {
      const authHeader = await getAuthHeader()
      if (!authHeader) {
        alert('로그인이 필요합니다.')
        return
      }
      const response = await fetch(`${API_BASE_URL}/api/trade/auto-trading-rule?rule_id=${ruleId}`, {
        method: 'DELETE',
        headers: {
          'Authorization': authHeader,
        },
      })
      const result = await response.json()
      if (result.success) {
        loadAutoTradingRules()
      } else {
        alert(result.message || '조건감시 정지에 실패했습니다.')
      }
    } catch (error) {
      console.error('Stop rule error:', error)
      alert('서버 통신 오류가 발생했습니다.')
    } finally {
      setRuleUpdating(false)
    }
  }

  const loadAutoTradingRules = async () => {
    const { data: { session } } = await supabase.auth.getSession()
    if (!session?.user?.id || !symbol) {
      setAutoRules([])
      return
    }

    setAutoRulesLoading(true)
    
    // 반대 환경(REAL/MOCK)의 실시간 시세도 비동기로 함께 확보하여 감시 수익률 계산에 대입
    const oppositeEnv = brokerEnv === 'REAL' ? 'MOCK' : 'REAL'
    const authHeader = await getAuthHeader()
    const fetchHeaders = {}
    if (authHeader) {
      fetchHeaders['Authorization'] = authHeader
    }
    fetch(`${API_BASE_URL}/api/chart/candles?exchange=${exchange}&symbol=${encodeURIComponent(getExchangeSymbol(exchange))}&interval=1m&limit=1&broker_env=${oppositeEnv}`, {
      headers: fetchHeaders
    })
      .then(res => res.json())
      .then(data => {
        if (data.success && data.data && data.data.length > 0) {
          const lastCandle = data.data[data.data.length - 1]
          const priceVal = lastCandle && typeof lastCandle === 'object' ? (lastCandle.close ?? lastCandle[4] ?? lastCandle.closePrice) : null
          if (priceVal) {
            setOppositeCurrentPrice(Number(priceVal))
          }
        }
      })
      .catch(err => console.error('반대 환경 시세 조회 실패:', err))

    try {
      const primaryResult = await supabase
        .from('auto_trading_rules')
        .select(AUTO_RULE_SELECT_FIELDS)
        .eq('exchange', exchange)
        .or(buildSymbolOrFilter())
        .order('created_at', { ascending: false })
        .limit(5)

      if (primaryResult.error) {
        const legacyResult = await supabase
          .from('auto_trading_rules')
          .select('id,exchange,asset_type,ticker,entry_price,investment_amount,target_profit_rate,stop_loss_rate,status,created_at,updated_at')
          .eq('exchange', exchange)
          .in('ticker', getSymbolQueryCandidates())
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

    let query = supabase
      .from('trade_proposals')
      .select('id,exchange,broker_env,symbol,ticker,side,status,volume,price,created_at')
      .eq('user_id', session.user.id)
      .eq('exchange', exchange)
      .or(buildSymbolOrFilter())
      .order('created_at', { ascending: false })

    if (brokerEnv) {
      query = query.eq('broker_env', brokerEnv)
    }

    const { data, error } = await query

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
    if (metadataAbortControllerRef.current) {
      metadataAbortControllerRef.current.abort()
    }
    const controller = new AbortController()
    metadataAbortControllerRef.current = controller

    setSymbolLookupReady(false)
    try {
      const response = await fetch(`${API_BASE_URL}/api/symbol/lookup?query=${symbol}&asset_type=${normalizedRouteAssetType}`, {
        signal: controller.signal
      })
      const resData = await response.json()
      if (resData.success && resData.data && resData.data.display_name) {
        setDisplayName(resData.data.display_name)
        const mappedAssetType = String(resData.data.asset_type || '').toUpperCase() === 'STOCK' ? 'STOCK' : 'CRYPTO'
        setResolvedAssetType(mappedAssetType)
        setResolvedSymbol(normalizeStockSymbol(resData.data.symbol || symbol))
        setResolvedMarket(String(resData.data.market || '').trim().toUpperCase())
        setSymbolLookupReady(true)
      } else {
        const params = new URLSearchParams({
          query: symbol || '',
          assetType: normalizedRouteAssetType,
        })
        navigate(`/search/not-found?${params.toString()}`, { replace: true })
      }
    } catch (error) {
      if (error.name === 'AbortError') {
        return
      }
      console.error("종목명 로드 실패:", error)
      const params = new URLSearchParams({
        query: symbol || '',
        assetType: normalizedRouteAssetType,
      })
      navigate(`/search/not-found?${params.toString()}`, { replace: true })
    } finally {
      if (metadataAbortControllerRef.current === controller) {
        metadataAbortControllerRef.current = null
      }
    }
  }

  // 관심종목(즐겨찾기) 상태 조회
  const loadFavoriteStatus = async () => {
    if (!isLoggedIn) {
      setIsFavorite(false)
      return
    }
    try {
      const favoritePayload = normalizeWatchlistItem({
        symbol,
        name: displayName,
        exchange,
        asset_type: resolvedAssetType,
      })
      const items = await fetchUserWatchlist()
      const hasMatch = items.some(item => 
        item.id === favoritePayload.symbol &&
        item.assetType === favoritePayload.asset_type &&
        (favoritePayload.asset_type === 'CRYPTO' || item.exchange === favoritePayload.exchange)
      )
      setIsFavorite(hasMatch)
    } catch (e) {
      console.warn('즐겨찾기 상태 로드 실패:', e)
    }
  }

  const fetchStockWarnings = async () => {
    if (resolvedAssetType !== 'STOCK') {
      setStockWarnings([])
      return
    }

    const authHeader = await getAuthHeader()
    if (!authHeader) {
      setStockWarnings([])
      return
    }

    try {
      const params = new URLSearchParams({
        symbol: getExchangeSymbol('TOSS'),
        exchange: 'TOSS',
        broker_env: brokerEnv,
      })
      const response = await fetch(`${API_BASE_URL}/api/stocks/warnings?${params.toString()}`, {
        headers: {
          Authorization: authHeader,
        },
      })
      const payload = await response.json().catch(() => ({}))
      if (!response.ok || !payload.success) {
        throw payload
      }
      setStockWarnings(Array.isArray(payload.data?.warnings) ? payload.data.warnings : [])
    } catch {
      setStockWarnings([])
    }
  }

  // 관심종목(즐겨찾기) 토글 처리
  const getFavoritePriceSnapshot = async () => {
    const parsePositivePrice = (value) => {
      const numeric = Number(value)
      return Number.isFinite(numeric) && numeric > 0 ? numeric : null
    }
    const parseChangeRate = (value) => {
      const numeric = Number(value)
      return Number.isFinite(numeric) ? numeric : null
    }

    const loadedPrice = parsePositivePrice(currentPrice)
    const loadedChangeRate = parseChangeRate(priceChangeRate)
    if (loadedPrice) {
      return {
        latest_price: loadedPrice,
        average_price: loadedPrice,
        change_rate: loadedChangeRate,
      }
    }

    const authHeader = await getAuthHeader()
    const headers = authHeader ? { Authorization: authHeader } : {}
    const chartSymbol = getExchangeSymbol(exchange)
    const quoteParams = new URLSearchParams({
      exchange,
      symbol: chartSymbol,
      broker_env: brokerEnv,
    })

    try {
      const response = await fetch(`${API_BASE_URL}/api/chart/quote?${quoteParams.toString()}`, { headers })
      const payload = await response.json().catch(() => ({}))
      const data = payload?.data || {}
      const quotePrice = parsePositivePrice(data.current_price ?? data.price ?? data.latest_price ?? data.close)
      const quoteChangeRate = parseChangeRate(data.change_rate)
      if (quotePrice) {
        setCurrentPrice(quotePrice)
        if (quoteChangeRate !== null) setPriceChangeRate(quoteChangeRate)
        return {
          latest_price: quotePrice,
          average_price: quotePrice,
          change_rate: quoteChangeRate,
        }
      }
    } catch {
      // 관심종목 저장은 가격 보정 실패와 무관하게 계속 진행합니다.
    }

    const candleParams = new URLSearchParams({
      exchange,
      symbol: chartSymbol,
      interval: chartInterval,
      broker_env: brokerEnv,
      count: '2',
    })

    try {
      const response = await fetch(`${API_BASE_URL}/api/chart/candles?${candleParams.toString()}`, { headers })
      const payload = await response.json().catch(() => ({}))
      const candles = Array.isArray(payload?.data) ? payload.data : []
      const lastCandle = candles[candles.length - 1] || {}
      const candlePrice = parsePositivePrice(lastCandle.close)
      if (candlePrice) {
        setCurrentPrice(candlePrice)
        return {
          latest_price: candlePrice,
          average_price: candlePrice,
          change_rate: loadedChangeRate,
        }
      }
    } catch {
      // 최종 fallback은 가격 없이 저장하는 기존 동작입니다.
    }

    return {
      latest_price: null,
      average_price: null,
      change_rate: loadedChangeRate,
    }
  }

  const handleToggleFavorite = async () => {
    if (!isLoggedIn) {
      alert("로그인이 필요한 서비스입니다.")
      return
    }

    const basePayload = {
      symbol: getExchangeSymbol(exchange),
      name: displayName,
      exchange: exchange,
      asset_type: resolvedAssetType,
      market_country: resolvedAssetType === 'CRYPTO'
        ? 'KR'
        : (resolvedMarket || (isResolvedUsStock ? 'US' : 'KR')),
      currency: resolvedAssetType === 'CRYPTO'
        ? (exchange === 'BINANCE' || exchange === 'BINANCE_UM_FUTURES' ? 'USDT' : 'KRW')
        : ((resolvedMarket === 'US' || isResolvedUsStock) ? 'USD' : 'KRW'),
      quantity: 0
    }

    try {
      const itemPayload = normalizeWatchlistItem(
        isFavorite
          ? basePayload
          : {
            ...basePayload,
            ...(await getFavoritePriceSnapshot()),
          }
      )

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
      const newsSymbol = resolvedAssetType === 'STOCK' ? getExchangeSymbol(exchange) : getDetailBaseSymbol()
      const response = await fetch(`${API_BASE_URL}/api/news?symbol=${encodeURIComponent(newsSymbol)}&limit=10`)
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

  const handleToggleNewsSummary = async (item) => {
    const articleId = item?.id
    if (!articleId) return

    if (!isLoggedIn) {
      setMemberOnlyMessage('뉴스 요약은 회원만 이용할 수 있습니다.')
      return
    }

    if (selectedNewsId === articleId) {
      setSelectedNewsId('')
      return
    }

    setSelectedNewsId(articleId)

    if (item.ai_summary) {
      return
    }

    setSummaryLoadingId(articleId)

    try {
      const response = await ensureNewsSummaries({ articleIds: [articleId] })
      const updatedItem = response?.items?.find((newsItem) => newsItem.id === articleId) || response?.items?.[0]

      if (updatedItem) {
        setNewsList((current) =>
          current.map((newsItem) =>
            newsItem.id === articleId
              ? {
                  ...newsItem,
                  ai_summary: updatedItem.ai_summary || newsItem.ai_summary,
                  ai_summary_model: updatedItem.ai_summary_model || newsItem.ai_summary_model,
                  ai_summary_generated_at: updatedItem.ai_summary_generated_at || newsItem.ai_summary_generated_at,
                  ai_summary_prompt_version: updatedItem.ai_summary_prompt_version || newsItem.ai_summary_prompt_version,
                }
              : newsItem,
          ),
        )
      }
    } catch (error) {
      setNewsSyncMessage({
        text: error.message || '뉴스 요약을 불러오지 못했습니다.',
        isError: true,
      })
    } finally {
      setSummaryLoadingId('')
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
          symbol: resolvedAssetType === 'STOCK' ? getExchangeSymbol(exchange) : getDetailBaseSymbol(),
          display_name: displayName,
          market: isStockAsset && isResolvedUsStock ? 'GLOBAL' : 'DOMESTIC',
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
      const response = await fetch(`${API_BASE_URL}/api/disclosures?symbol=${encodeURIComponent(getExchangeSymbol(exchange))}&limit=10`)
      const resData = await response.json()
      if (resData.success && resData.data && resData.data.items) {
        setDisclosureList(resData.data.items)
        setSelectedDisclosureId('')
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

  const handleToggleDisclosureAnalysis = async (item) => {
    const disclosureId = item?.id || ''
    const rceptNo = item?.rcept_no || ''
    if (!disclosureId || !rceptNo) return

    if (!isLoggedIn) {
      setMemberOnlyMessage('공시 요약은 회원만 이용할 수 있습니다.')
      return
    }

    if (selectedDisclosureId === disclosureId && disclosureAnalyses[rceptNo]) {
      setSelectedDisclosureId('')
      return
    }

    setSelectedDisclosureId(disclosureId)
    if (disclosureAnalyses[rceptNo]) return

    setDisclosureAnalysisLoadingId(disclosureId)
    try {
      const response = await fetch(`${API_BASE_URL}/api/disclosures/${rceptNo}/analysis`)
      const resData = await response.json()
      if (!response.ok || !resData.success) {
        throw new Error(resData.message || '공시 분석을 불러오지 못했습니다.')
      }
      const analysis = resData.data?.analysis
      if (analysis) {
        setDisclosureAnalyses((prev) => ({
          ...prev,
          [rceptNo]: analysis,
        }))
      }
    } catch (error) {
      setDisclosureAnalyses((prev) => ({
        ...prev,
        [rceptNo]: {
          sentiment: 'info',
          sentiment_label: '정보',
          sentiment_message: '공시 분석을 불러오지 못했습니다.',
          confidence: 'low',
          headline: error.message || '공시 분석을 불러오지 못했습니다.',
          key_points: ['잠시 후 다시 시도하거나 원문을 확인해 주세요.'],
          risk_points: [],
          metrics: [],
          analysis_source: 'ERROR',
        },
      }))
    } finally {
      setDisclosureAnalysisLoadingId('')
    }
  }

  const fetchCommunityPosts = async () => {
    const { data: { session } } = await supabase.auth.getSession()
    setCommunityCurrentUserId(session?.user?.id || '')

    if (!session?.user?.id || !symbol) {
      setCommunityPosts([])
      setCommunityProfiles({})
      return
    }

    setCommunityLoading(true)
    setCommunityMessage({ text: '', isError: false })

    try {
      const normalizedSymbol = String(symbol || '').trim().toUpperCase()
      const { data, error } = await supabase
        .from('community_posts')
        .select('id,user_id,parent_id,asset_type,symbol,exchange,content,status,created_at,updated_at')
        .eq('asset_type', resolvedAssetType)
        .eq('symbol', normalizedSymbol)
        .eq('status', 'ACTIVE')
        .order('created_at', { ascending: false })
        .limit(80)

      if (error) throw error

      const posts = data || []
      setCommunityPosts(posts)

      const userIds = [...new Set(posts.map((post) => post.user_id).filter(Boolean))]
      if (userIds.length === 0) {
        setCommunityProfiles({})
        return
      }

      const { data: profileRows, error: profileError } = await supabase
        .from('public_profiles')
        .select('id,nickname,role')
        .in('id', userIds)

      if (profileError) throw profileError

      const nextProfiles = {}
      ;(profileRows || []).forEach((profile) => {
        nextProfiles[profile.id] = profile
      })
      setCommunityProfiles(nextProfiles)
    } catch (error) {
      const message = getApiErrorMessage(error, '커뮤니티 글을 불러오지 못했습니다.')
      setCommunityPosts([])
      setCommunityProfiles({})
      setCommunityMessage({
        text: message.detail ? `${message.title} ${message.detail}` : message.title,
        isError: true,
      })
    } finally {
      setCommunityLoading(false)
    }
  }

  const handleSubmitCommunityPost = async (event) => {
    event.preventDefault()
    const content = communityDraft.trim()

    if (content.length < 1 || content.length > 500) {
      setCommunityMessage({ text: '커뮤니티 글은 1자 이상 500자 이하로 입력해 주세요.', isError: true })
      return
    }

    const { data: { session } } = await supabase.auth.getSession()
    if (!session?.user?.id) {
      setCommunityMessage({ text: '로그인 후 커뮤니티 글을 작성할 수 있습니다.', isError: true })
      return
    }

    setCommunitySubmitting(true)
    setCommunityMessage({ text: '', isError: false })

    try {
      const normalizedSymbol = String(symbol || '').trim().toUpperCase()
      const { error } = await supabase
        .from('community_posts')
        .insert({
          user_id: session.user.id,
          asset_type: resolvedAssetType,
          symbol: normalizedSymbol,
          exchange,
          content,
          status: 'ACTIVE',
        })

      if (error) throw error

      setCommunityDraft('')
      await fetchCommunityPosts()
    } catch (error) {
      const message = getApiErrorMessage(error, '커뮤니티 글 작성에 실패했습니다.')
      setCommunityMessage({
        text: message.detail ? `${message.title} ${message.detail}` : message.title,
        isError: true,
      })
    } finally {
      setCommunitySubmitting(false)
    }
  }

  const handleSubmitCommunityReply = async (event, parentPost) => {
    event.preventDefault()
    const content = communityReplyDraft.trim()

    if (!parentPost?.id || parentPost.parent_id) {
      setCommunityMessage({ text: '답글은 원댓글에만 작성할 수 있습니다.', isError: true })
      return
    }

    if (content.length < 1 || content.length > 500) {
      setCommunityMessage({ text: '답글은 1자 이상 500자 이하로 입력해 주세요.', isError: true })
      return
    }

    const { data: { session } } = await supabase.auth.getSession()
    if (!session?.user?.id) {
      setCommunityMessage({ text: '로그인 후 답글을 작성할 수 있습니다.', isError: true })
      return
    }

    setCommunitySubmitting(true)
    setCommunityMessage({ text: '', isError: false })

    try {
      const normalizedSymbol = String(symbol || '').trim().toUpperCase()
      const { error } = await supabase
        .from('community_posts')
        .insert({
          user_id: session.user.id,
          parent_id: parentPost.id,
          asset_type: resolvedAssetType,
          symbol: normalizedSymbol,
          exchange,
          content,
          status: 'ACTIVE',
        })

      if (error) throw error

      setCommunityReplyParentId('')
      setCommunityReplyDraft('')
      await fetchCommunityPosts()
    } catch (error) {
      const message = getApiErrorMessage(error, '답글 작성에 실패했습니다.')
      setCommunityMessage({
        text: message.detail ? `${message.title} ${message.detail}` : message.title,
        isError: true,
      })
    } finally {
      setCommunitySubmitting(false)
    }
  }

  const handleUpdateCommunityStatus = async (post, status) => {
    if (!post?.id) return
    const confirmMessage = status === 'HIDDEN'
      ? '이 커뮤니티 글을 관리자 숨김 처리할까요?'
      : '이 커뮤니티 글을 삭제할까요?'
    if (!window.confirm(confirmMessage)) return

    setCommunityActionId(post.id)
    setCommunityMessage({ text: '', isError: false })

    try {
      const { error } = await supabase
        .from('community_posts')
        .update({
          status,
          updated_at: new Date().toISOString(),
        })
        .eq('id', post.id)

      if (error) throw error

      await fetchCommunityPosts()
    } catch (error) {
      const fallback = status === 'HIDDEN'
        ? '커뮤니티 글 숨김 처리에 실패했습니다.'
        : '커뮤니티 글 삭제에 실패했습니다.'
      const message = getApiErrorMessage(error, fallback)
      setCommunityMessage({
        text: message.detail ? `${message.title} ${message.detail}` : message.title,
        isError: true,
      })
    } finally {
      setCommunityActionId('')
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
      // 코인은 ML 예측 CSV 심볼 형식(DOGEUSDT 등)에 맞게 변환
      const mlSymbol = resolvedAssetType === 'CRYPTO'
        ? getExchangeSymbol('BINANCE')
        : getExchangeSymbol(exchange)
      // 국내/해외 개별 모델 구분은 lookup으로 확정된 시장과 종목코드 기준을 함께 사용합니다.
      const mlAssetType = resolvedAssetType === 'CRYPTO'
        ? 'CRYPTO'
        : (isResolvedUsStock ? 'STOCK_US' : 'STOCK_KR')
      const params = new URLSearchParams({
        asset_type: mlAssetType,
        symbols: mlSymbol,
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

  const buildMlSignalInterpretation = (signal) => {
    if (!signal) return null
    const up = getProbabilityLevel(signal.up_probability, 'up')
    const risk = getProbabilityLevel(signal.risk_probability, 'risk')
    const grade = String(signal.signal_grade || '')
    const position = String(signal.position || '').toUpperCase()
    const isRisky = grade === 'RISKY' || Number(signal.risk_probability) >= 0.6
    const isCandidate = grade === 'STRONG_BUY_CANDIDATE' || position === 'LONG'
    const actionLabel = isRisky ? '주의' : isCandidate ? '후보' : '관망'
    const actionTone = isRisky
      ? 'border-rose-500/40 bg-rose-950/30 text-rose-200'
      : isCandidate
        ? 'border-emerald-500/40 bg-emerald-950/25 text-emerald-200'
        : 'border-cyan-500/35 bg-cyan-950/20 text-cyan-100'
    const reason = isRisky
      ? '하락 위험 또는 정책 차단 신호가 있어 매수보다 리스크 확인이 먼저입니다.'
      : isCandidate
        ? '상승 신호가 우세하고 현재 정책 필터를 통과한 후보입니다.'
        : '매수/매도 결론보다 관찰이 더 적합한 상태입니다.'

    return {
      actionLabel,
      actionTone,
      up,
      risk,
      reason,
      modelScope: resolvedAssetType === 'CRYPTO'
        ? '코인 전용 모델'
        : isResolvedUsStock
          ? '해외주식 모델'
          : '국내주식 모델',
    }
  }

  const normalizeHoldingSymbol = (value) => {
    const normalized = String(value || '').trim().toUpperCase()
    if (/^A\d{6}$/.test(normalized)) {
      return normalized.slice(1)
    }
    if (resolvedAssetType === 'CRYPTO') {
      return normalizeCryptoBaseSymbol(normalized)
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
      const [, month, day] = time.split('-')
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
      const chartSymbol = getExchangeSymbol(chartEx)
      const url = `${API_BASE_URL}/api/chart/candles?exchange=${chartEx}&symbol=${encodeURIComponent(chartSymbol)}&interval=${chartInterval}&broker_env=${chartEnv}&count=300`
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

          if (chartRef.current && candleSeriesRef.current) {
            try {
              candleSeriesRef.current.setData(uniqueFormatted)
              chartRef.current.timeScale().fitContent()
              hasAppliedInitialFitRef.current = true
            } catch (err) {
              console.error('API 로드 즉시 데이터 주입 실패:', err)
            }
          }
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
        

        
        setPrice(prev => prev === '' ? lastCandle.close.toString() : prev);
      } else {
        console.error('시세 데이터를 가져오지 못했습니다:', resData.message);
        setCandleData([])
        if (candleSeriesRef.current) {
          try {
            candleSeriesRef.current.setData([])
          } catch {
            return
          }
        }
      }
    } catch (error) {
      if (error.name === 'AbortError') {
        return
      }
      console.error('시세 API 호출 오류:', error)
      setCandleData([])
      if (candleSeriesRef.current) {
        try {
          candleSeriesRef.current.setData([])
        } catch {
          return
        }
      }
    } finally {
      candlesInFlightRef.current = false
      if (abortControllerRef.current === controller) {
        setLoadingChart(false)
      }
    }
  }

  // 1-b. 경량 시세(전일대비) 독립 조회
  const fetchQuote = async () => {
    try {
      const authHeader = await getAuthHeader()
      const chartEx = exchange
      const chartEnv = brokerEnv
      const chartSymbol = resolvedSymbol || symbol
      const headers = {}
      if (authHeader) headers['Authorization'] = authHeader

      // 1차: quote API 조회
      const url = `${API_BASE_URL}/api/chart/quote?exchange=${chartEx}&symbol=${encodeURIComponent(chartSymbol)}&broker_env=${chartEnv}`
      const res = await fetch(url, { headers })
      if (res.ok) {
        const json = await res.json()
        if (json.success && json.data && typeof json.data.change_rate === 'number' && json.data.change_rate !== 0) {
          setPriceChangeRate(json.data.change_rate)
          return
        }
      }

      // 2차 fallback: 일봉 캔들 2개로 직접 계산
      const candleUrl = `${API_BASE_URL}/api/chart/candles?exchange=${chartEx}&symbol=${encodeURIComponent(chartSymbol)}&interval=1d&broker_env=${chartEnv}&count=2`
      const candleRes = await fetch(candleUrl, { headers })
      if (candleRes.ok) {
        const candleJson = await candleRes.json()
        if (candleJson.success && candleJson.data && candleJson.data.length >= 2) {
          const prevClose = parseFloat(candleJson.data[candleJson.data.length - 2].close || 0)
          const todayClose = parseFloat(candleJson.data[candleJson.data.length - 1].close || 0)
          if (prevClose > 0) {
            setPriceChangeRate(((todayClose - prevClose) / prevClose) * 100)
            return
          }
        }
        // 캔들 meta에 change_rate가 있으면 사용
        if (candleJson.meta && typeof candleJson.meta.change_rate === 'number' && candleJson.meta.change_rate !== 0) {
          setPriceChangeRate(candleJson.meta.change_rate)
        }
      }
    } catch {
      return
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
      const trUrl = `${API_BASE_URL}/api/chart/trades?exchange=${chartEx}&symbol=${encodeURIComponent(getExchangeSymbol(chartEx))}&broker_env=${chartEnv}`;
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

  useEffect(() => {
    if (balanceCooldown <= 0) return
    const timer = window.setInterval(() => {
      setBalanceCooldown(prev => prev - 1)
    }, 1000)
    return () => window.clearInterval(timer)
  }, [balanceCooldown])

  const handleRefreshBalance = async () => {
    if (balanceCooldown > 0) return
    setBalanceCooldown(5) // 5초 쿨다운
    await fetchUserBalance()
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
          symbol: getExchangeSymbol(exchange),
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

  // 0. 종목 변경 즉시 시세 및 관련 데이터 초기화
  useEffect(() => {
    setSymbolLookupReady(false)
    setResolvedSymbol(normalizeStockSymbol(symbol))
    setResolvedAssetType(normalizedRouteAssetType)

    setCandleData([])
    setCurrentPrice(0)
    setPriceChangeRate(0)
    setLoadingChart(true)
    setNewsList([])
    setDisclosureList([])
    setStockWarnings([])
    setOrderPrecheck(null)
    setPrecheckMessage('')
    setDisplayName(symbol)

    // 비동기 꼬임 방지를 위한 Ref 변수 강제 초기화
    hasAppliedInitialFitRef.current = false
    lastCandleSignatureRef.current = ''
    candlesInFlightRef.current = false
  }, [symbol, normalizedRouteAssetType])

  // 거래소 토글 시 환경값 변경

  const handleExchangeChange = (newEx, newEnv = 'REAL') => {
    // 해외 주식인 경우 KIS 선택 차단
    if (isResolvedUsStock && newEx === 'KIS') {
      alert("해외주식은 Toss API만 지원합니다.");
      return;
    }

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

  const refreshMlSignal = useEffectEvent(() => {
    fetchMlSignal()
  })

  const fetchSymbolMetadataEvent = useEffectEvent(() => {
    fetchSymbolMetadata()
  })

  const loadBrokerAvailabilityEvent = useEffectEvent(() => {
    loadBrokerAvailability()
  })

  const loadTradeHoldingContextEvent = useEffectEvent(() => {
    loadTradeHoldingContext()
  })

  const fetchStockWarningsEvent = useEffectEvent(() => {
    fetchStockWarnings()
  })

  const fetchCandlesEvent = useEffectEvent((options) => {
    fetchCandles(options)
  })

  const fetchQuoteEvent = useEffectEvent(() => {
    fetchQuote()
  })

  const fetchUserBalanceEvent = useEffectEvent(() => {
    fetchUserBalance()
  })

  const loadOpenOrdersEvent = useEffectEvent(() => {
    loadOpenOrders()
  })

  const loadAutoTradingRulesEvent = useEffectEvent(() => {
    loadAutoTradingRules()
  })

  const fetchNewsListEvent = useEffectEvent(() => {
    fetchNewsList()
  })

  const fetchDisclosureListEvent = useEffectEvent(() => {
    fetchDisclosureList()
  })

  const fetchCommunityPostsEvent = useEffectEvent(() => {
    fetchCommunityPosts()
  })

  const loadFavoriteStatusEvent = useEffectEvent(() => {
    loadFavoriteStatus()
  })

  const fetchOrderbookAndTradesEvent = useEffectEvent(() => {
    fetchOrderbookAndTrades()
  })

  const fetchOrderPrecheckEvent = useEffectEvent(() => {
    fetchOrderPrecheck()
  })

  const getChartSetupSnapshot = useEffectEvent(() => ({
    candleData,
    currentPrice,
  }))

  const formatChartTickEvent = useEffectEvent((time) => formatChartTick(time))

  const getChartPriceFormatEvent = useEffectEvent((value) => getChartPriceFormat(value))

  useEffect(() => {
    fetchSymbolMetadataEvent()
    loadBrokerAvailabilityEvent()
    loadTradeHoldingContextEvent()
  }, [symbol, normalizedRouteAssetType])

  useEffect(() => {
    if (!symbolLookupReady) return

    setNewsSyncMessage({ text: '', isError: false })
    fetchStockWarningsEvent()
    fetchCandlesEvent()
    fetchQuoteEvent()
    fetchUserBalanceEvent()
    loadTradeHoldingContextEvent()
    loadOpenOrdersEvent()
    loadAutoTradingRulesEvent()
    fetchNewsListEvent()
    fetchDisclosureListEvent()
    fetchCommunityPostsEvent()
  }, [exchange, symbol, resolvedSymbol, chartInterval, brokerEnv, symbolLookupReady, resolvedAssetType])

  // 전일대비 독립 폴링 (30초)
  useEffect(() => {
    const quoteIntervalId = window.setInterval(() => {
      if (document.visibilityState === 'visible') {
        fetchQuoteEvent()
      }
    }, 30000)
    return () => window.clearInterval(quoteIntervalId)
  }, [exchange, symbol, resolvedSymbol, brokerEnv])

  useEffect(() => {
    loadFavoriteStatusEvent()
  }, [isLoggedIn, symbol, resolvedAssetType, exchange])

  useEffect(() => {
    if (!isLoggedIn || !symbolLookupReady || !symbol) return undefined

    const channel = supabase
      .channel(`community-posts-${resolvedAssetType}-${String(symbol).toUpperCase()}`)
      .on(
        'postgres_changes',
        {
          event: '*',
          schema: 'public',
          table: 'community_posts',
          filter: `symbol=eq.${String(symbol).trim().toUpperCase()}`,
        },
        () => {
          fetchCommunityPostsEvent()
        },
      )
      .subscribe()

    return () => {
      supabase.removeChannel(channel)
    }
  }, [isLoggedIn, symbolLookupReady, resolvedAssetType, symbol])

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

      if (isResolvedUsStock) {
        if (exchange !== 'TOSS' || brokerEnv !== 'REAL') {
          setExchange('TOSS')
          setBrokerEnv('REAL')
        }
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
    
    if (!['COINONE', 'BINANCE', 'BINANCE_UM_FUTURES'].includes(exchange)) {
      const routeSymbol = String(symbol || '').toUpperCase()
      setExchange(routeSymbol.endsWith('USDT') || routeSymbol.endsWith('BUSD') ? 'BINANCE' : 'COINONE')
    }

    if (['COINONE', 'TOSS'].includes(exchange) && brokerEnv !== 'REAL') {
      setBrokerEnv('REAL')
    }
    if (!['1m', '5m', '15m', '30m', '1h', '4h', '1d', '1w', '1M'].includes(chartInterval)) {
      setChartInterval('1h')
    }
  }, [resolvedAssetType, exchange, brokerEnv, chartInterval, brokerAvailability, tradeHoldingContext, symbol, resolvedSymbol, isResolvedUsStock])

  useEffect(() => {
    const intervalId = window.setInterval(() => {
      if (document.visibilityState === 'visible') {
        fetchCandlesEvent({ silent: true })
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
      fetchOrderbookAndTradesEvent()
    }, isStockAsset ? 1200 : 0)
    const intervalId = window.setInterval(fetchOrderbookAndTradesEvent, level2PollMs)
    const visibilityHandler = () => {
      if (document.visibilityState === 'visible') {
        fetchOrderbookAndTradesEvent()
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
      fetchOrderPrecheckEvent()
    }, isStockAsset ? 800 : 250)

    return () => window.clearTimeout(timeoutId)
  }, [exchange, symbol, effectiveSide, orderType, price, quantity, brokerEnv, isStockAsset, effectiveReduceOnly, futuresLeverage, futuresMarginType])

  // 3. TradingView Lightweight Charts 차트 초기 생성 및 리사이즈 대응
  useEffect(() => {
    if (!symbolLookupReady) return
    if (!chartContainerRef.current || chartRef.current) return

    let chart = null
    try {
      const containerWidth = chartContainerRef.current.clientWidth || chartContainerRef.current.parentElement?.clientWidth || 800

      chart = createChart(chartContainerRef.current, {
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
          tickMarkFormatter: (time) => formatChartTickEvent(time),
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
        priceFormat: getChartPriceFormatEvent(getChartSetupSnapshot().currentPrice),
      })

      chartRef.current = chart
      candleSeriesRef.current = candleSeries

      // 차트 생성 시점에 이미 로드된 캔들 데이터가 있다면 즉시 주입하여 비동기 완료 순서로 인한 차트 누락(검은 화면) 방지
      const chartSetupSnapshot = getChartSetupSnapshot()
      if (chartSetupSnapshot.candleData && chartSetupSnapshot.candleData.length > 0) {
        try {
          candleSeries.setData(chartSetupSnapshot.candleData)
          chart.timeScale().fitContent()
          hasAppliedInitialFitRef.current = true
        } catch (err) {
          console.error('차트 생성 시 초기 데이터 주입 실패:', err)
        }
      }

      const handleResize = () => {
        if (chart && chartContainerRef.current) {
          try {
            const newWidth = chartContainerRef.current.clientWidth || 800
            chart.applyOptions({ width: newWidth })
          } catch (err) {
            console.error('차트 리사이즈 조절 에러:', err)
          }
        }
      }

      window.addEventListener('resize', handleResize)

      setTimeout(() => {
        if (chart && chartContainerRef.current) {
          const fitWidth = chartContainerRef.current.clientWidth || 800
          chart.applyOptions({ width: fitWidth })
        }
      }, 50)

      return () => {
        window.removeEventListener('resize', handleResize)
        try {
          if (chart) {
            chart.remove()
          }
        } catch (e) {
          console.error('차트 소멸 정리 에러:', e)
        }
        chartRef.current = null
        candleSeriesRef.current = null
        hasAppliedInitialFitRef.current = false
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

      // 데이터가 성공적으로 들어왔을 때, 컨테이너 크기를 최종적으로 한번 더 정밀 싱크
      if (chartContainerRef.current) {
        const nextWidth = chartContainerRef.current.clientWidth || 800
        const nextHeight = isChartExpanded ? 720 : 300
        chartRef.current.applyOptions({ width: nextWidth, height: nextHeight })
      }

      if (!hasAppliedInitialFitRef.current) {
        chartRef.current.timeScale().fitContent()
        hasAppliedInitialFitRef.current = true
      }
    } catch (err) {
      console.error('차트 데이터 갱신 실패:', err)
    }
  }, [candleData, isChartExpanded])

  useEffect(() => {
    if (!candleSeriesRef.current) return
    candleSeriesRef.current.applyOptions({
      priceFormat: getChartPriceFormatEvent(currentPrice),
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

    if (isTradingSuspended) {
      setTradeMessage({ text: tradeRestrictionMessage, isError: true })
      setSubmitting(false)
      return
    }

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
        symbol: getExchangeSymbol(exchange),
        action: effectiveSide,
        order_type: orderType,
        quantity: parseFloat(quantity),
        price: orderType === 'LIMIT' ? parseFloat(price) : null,
        broker_env: brokerEnv,
        auto_exit: autoExit,
        target_profit_rate: autoExit ? (
          autoExitRateType === 'ROE' && exchange === 'BINANCE_UM_FUTURES'
            ? parseFloat(targetProfitRate) / (Number(futuresLeverage) || 1)
            : parseFloat(targetProfitRate)
        ) : null,
        stop_loss_rate: autoExit ? (
          autoExitRateType === 'ROE' && exchange === 'BINANCE_UM_FUTURES'
            ? parseFloat(stopLossRate) / (Number(futuresLeverage) || 1)
            : parseFloat(stopLossRate)
        ) : null,
        auto_exit_execution_mode: autoExit ? autoExitExecutionMode : 'PROPOSAL',
        auto_restart_on_partial_fill: autoExit ? autoRestartOnPartialFill : false,
        position_side: exchange === 'BINANCE_UM_FUTURES' ? 'BOTH' : null,
        reduce_only: exchange === 'BINANCE_UM_FUTURES' ? effectiveReduceOnly : false,
        leverage: exchange === 'BINANCE_UM_FUTURES' ? Number(futuresLeverage) : null,
        margin_type: exchange === 'BINANCE_UM_FUTURES' ? futuresMarginType : null
      }
      const orderFingerprint = buildManualOrderFingerprint(payload)
      const idempotencyState = resolveManualOrderIdempotency(
        manualOrderIdempotencyRef.current,
        orderFingerprint,
        () => crypto.randomUUID(),
      )
      manualOrderIdempotencyRef.current = idempotencyState
      payload.idempotency_key = idempotencyState.key

      const response = await fetch(`${API_BASE_URL}/api/trade/order`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': authHeader,
          'Idempotency-Key': idempotencyState.key
        },
        body: JSON.stringify(payload)
      })

      const resData = await response.json()

      if (shouldResetManualOrderIdempotency(resData)) {
        manualOrderIdempotencyRef.current = null
      }
      if (resData.success) {
        const autoExitMessage = resData.auto_exit ? ` / ${resData.auto_exit}` : ''
        setTradeMessage({
          text: `주문이 성공적으로 전송되었습니다!${autoExitMessage}`,
          isError: false
        })
        setQuantity('')
        setAutoRestartOnPartialFill(true)
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
  const baseAvailableCash = (() => {
    if (!userBalance) return NaN;
    if (exchange === 'TOSS') {
      const components = userBalance.available_cash_details?.components || [];
      const targetCurrency = isResolvedUsStock ? 'USD' : 'KRW';
      const found = components.find(c => String(c.currency).toUpperCase() === targetCurrency);
      if (found && found.cash_buying_power != null) {
        return Number(found.cash_buying_power);
      }
    }
    return Number(userBalance.available_cash ?? NaN);
  })();
  const overallFeedStatus = getOverallFeedStatus()
  const isTradingSuspended = resolvedAssetType === 'STOCK' && stockWarnings.some((warning) => String(warning.warning_type || '').toUpperCase() === 'TRADING_SUSPENDED')
  const tradeRestrictionMessage = isTradingSuspended
    ? '거래중지 종목으로 확인되어 주문을 비활성화했습니다. 거래 재개 후 다시 시도해 주세요.'
    : orderPrecheck?.is_market_closed
      ? orderPrecheck.market_status_message || '현재는 거래가 불가능한 장외 시간(또는 휴장일)입니다.'
      : ''
  const isOrderBlocked = isTradingSuspended || orderPrecheck?.is_market_closed || (brokerEnv === 'REAL' && (
    orderPrecheck?.futures_real_blocked ||
    orderPrecheck?.insufficient_cash ||
    orderPrecheck?.insufficient_holding
  ))
  const chartCardClassName = isChartExpanded
    ? 'fixed inset-3 z-50 flex flex-col gap-4 rounded-2xl border border-cyan-500/40 bg-[#0e1529] p-4 shadow-2xl shadow-cyan-950/40 backdrop-blur-xl sm:inset-6'
    : 'bg-[#0e1529]/90 border border-[#1f2945] rounded-xl p-4 flex flex-col gap-4 backdrop-blur-md'
  const chartPanelClassName = isChartExpanded
    ? 'w-full relative h-[72vh] min-h-[520px] bg-[#0e1529] rounded-lg overflow-hidden border border-cyan-500/20'
    : 'w-full relative h-[300px] min-h-[300px] bg-[#0e1529] rounded-lg overflow-hidden border border-[#1f2945]/60'
  const holdingSummaryLabel = myHolding && myHoldingAbsQty > 0
    ? `${myHoldingAbsQty.toLocaleString()} ${exchange === 'BINANCE_UM_FUTURES' ? '계약' : '주'}`
    : dbEstimatedHolding
      ? `${dbEstimatedHolding.estimatedQty.toLocaleString()} ${dbEstimatedHolding.exchange === 'BINANCE_UM_FUTURES' ? '계약' : resolvedAssetType === 'CRYPTO' ? '개' : '주'} 추정`
      : '보유 없음'
  const availableCashLabel = orderPrecheck?.available_cash != null
    ? `${getCurrencySign()}${Number(orderPrecheck.available_cash).toLocaleString(undefined, { maximumFractionDigits: getCurrencyDigits() })}`
    : Number.isFinite(baseAvailableCash)
      ? `${getCurrencySign()}${baseAvailableCash.toLocaleString(undefined, { maximumFractionDigits: getCurrencyDigits() })}`
      : '잔고 조회 필요'
  const getEstimatedHoldingUnit = (holding) => {
    if (holding?.exchange === 'BINANCE_UM_FUTURES') return '계약'
    if (resolvedAssetType === 'CRYPTO') return '개'
    return '주'
  }
  const getEstimatedHoldingCurrencySign = (holding) => (
    ['BINANCE', 'BINANCE_UM_FUTURES'].includes(String(holding?.exchange || '').toUpperCase()) ? '$'
      : ['COINONE', 'KIS', 'TOSS'].includes(String(holding?.exchange || '').toUpperCase()) ? '₩'
        : getCurrencySign()
  )
  const getEstimatedHoldingNotice = (holding) => {
    const estimatedExchange = String(holding?.exchange || exchange || '').toUpperCase()
    if (estimatedExchange === 'BINANCE_UM_FUTURES') {
      return '거래내역에는 선물 주문 기록이 있지만, 현재 선택 계좌의 실제 선물 포지션 API에서는 확인되지 않았습니다. 청산 주문은 실제 바이낸스 선물 포지션 수량이 있어야 성공합니다. 거래내역 상태 동기화를 먼저 실행해 보세요.'
    }
    if (estimatedExchange === 'BINANCE') {
      return '거래내역에는 체결 매수 기록이 있지만, 현재 선택 계좌의 실제 바이낸스 현물 잔고 API에서는 확인되지 않았습니다. 매도 주문은 실제 바이낸스 현물 잔고에 수량이 있어야 성공합니다.'
    }
    if (estimatedExchange === 'COINONE') {
      return '거래내역에는 체결 매수 기록이 있지만, 현재 선택 계좌의 실제 코인원 잔고 API에서는 확인되지 않았습니다. 매도 주문은 실제 코인원 잔고에 수량이 있어야 성공합니다.'
    }
    if (estimatedExchange === 'TOSS') {
      return '거래내역에는 체결 매수 기록이 있지만, 현재 선택 계좌의 실제 토스증권 잔고 API에서는 확인되지 않았습니다. 매도 주문은 실제 토스증권 잔고에 수량이 있어야 성공합니다.'
    }
    return '거래내역에는 체결 매수 기록이 있지만, 현재 선택 계좌의 실제 KIS 잔고 API에서는 확인되지 않았습니다. 매도 주문은 실제 KIS 잔고에 수량이 있어야 성공합니다.'
  }

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

  const communityReplyMap = communityPosts.reduce((map, post) => {
    if (!post.parent_id) return map
    const replies = map[post.parent_id] || []
    replies.push(post)
    map[post.parent_id] = replies
    return map
  }, {})
  Object.values(communityReplyMap).forEach((replies) => {
    replies.sort((left, right) => new Date(left.created_at) - new Date(right.created_at))
  })
  const communityRootPosts = communityPosts.filter((post) => !post.parent_id)

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
        <MemberOnlyModal
          message={memberOnlyMessage}
          onClose={() => setMemberOnlyMessage('')}
        />

        {/* 뒤로가기 버튼 */}
        <div className="mt-2 mb-4">
          <button
            onClick={() => navigate('/')}
            className="flex items-center gap-2 text-xs font-bold text-slate-400 hover:text-white transition-all bg-transparent border-none cursor-pointer outline-none"
          >
            <span>← 홈으로 돌아가기</span>
          </button>
        </div>

        <AssetDetailHeader
          assetType={resolvedAssetType}
          exchange={exchange}
          brokerEnv={brokerEnv}
          overallFeedStatus={overallFeedStatus}
          symbol={symbol}
          displayName={displayName}
          isUsStock={isResolvedUsStock}
          isFavorite={isFavorite}
          stockWarnings={stockWarnings}
          showLevel2Panel={showLevel2Panel}
          marketFeeds={marketFeeds}
          feedReasonSummary={feedReasonSummary}
          currentPrice={currentPrice}
          priceChangeRate={priceChangeRate}
          formatUnitPrice={formatUnitPrice}
          onToggleFavorite={handleToggleFavorite}
        />

        {/* 2. 메인 3열(3-column) WTS 레이아웃 */}
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-5">
          
          {/* [1열: 좌측 - 컴팩트 차트 및 저비용 정보 패널] */}
          <div className={`${showLevel2Panel ? 'lg:col-span-6' : 'lg:col-span-8'} flex flex-col gap-5`}>
            
            <AssetDetailChartPanel
              assetType={resolvedAssetType}
              chartInterval={chartInterval}
              chartCardClassName={chartCardClassName}
              chartPanelClassName={chartPanelClassName}
              chartContainerRef={chartContainerRef}
              isChartExpanded={isChartExpanded}
              loadingChart={loadingChart}
              marketFeeds={marketFeeds}
              onIntervalChange={setChartInterval}
              onToggleExpanded={() => setIsChartExpanded((prev) => !prev)}
              onCloseExpanded={() => setIsChartExpanded(false)}
            />

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
                    트리거는 조건이 실제로 발동된 사유입니다.
                  </p>
                </div>
                <div className="flex gap-2">
                  <button
                    type="button"
                    onClick={() => {
                      setAddRulePrice(myHolding && myHolding.avg_price ? String(myHolding.avg_price) : String(currentPrice || ''))
                      setAddRuleQty(myHolding ? String(myHolding.qty || '') : '')
                      setShowAddRuleForm(!showAddRuleForm)
                    }}
                    className="rounded bg-cyan-500 px-3 py-2 text-[10px] font-black text-[#070b19] transition hover:bg-cyan-400 cursor-pointer"
                  >
                    {showAddRuleForm ? '등록 닫기' : '새로운 감시 등록'}
                  </button>
                  <button
                    type="button"
                    onClick={loadAutoTradingRules}
                    disabled={autoRulesLoading}
                    className="rounded border border-emerald-500/30 px-3 py-2 text-[10px] font-black text-emerald-300 transition hover:bg-emerald-950/30 disabled:cursor-not-allowed disabled:opacity-50 cursor-pointer"
                  >
                    {autoRulesLoading ? '조회 중' : '감시 새로고침'}
                  </button>
                </div>
              </div>

              {showAddRuleForm && (
                <div className="mb-4 rounded-lg border border-[#1f2945] bg-[#070b19] p-3 text-xs">
                  <p className="mb-2 text-[10px] font-bold text-cyan-300">주문 없이 독립적으로 감시 규칙을 등록합니다. (보유 중인 자산에만 권장)</p>
                  <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
                    <div>
                      <label className="block text-[9px] text-slate-500 mb-1 font-bold">진입 가격 ({getCurrencySign()})</label>
                      <input
                        type="number"
                        value={addRulePrice}
                        onChange={(e) => setAddRulePrice(e.target.value)}
                        className="w-full rounded border border-slate-700 bg-slate-950 px-2 py-1 text-xs text-white focus:border-cyan-400 focus:outline-none"
                      />
                    </div>
                    <div>
                      <label className="block text-[9px] text-slate-500 mb-1 font-bold">감시 수량</label>
                      <input
                        type="number"
                        step="0.0001"
                        value={addRuleQty}
                        onChange={(e) => setAddRuleQty(e.target.value)}
                        className="w-full rounded border border-slate-700 bg-slate-950 px-2 py-1 text-xs text-white focus:border-cyan-400 focus:outline-none"
                        placeholder="예: 2"
                      />
                    </div>
                    <div>
                      <label className="block text-[9px] text-green-400 mb-1 font-bold">목표 익절 (%)</label>
                      <input
                        type="number"
                        step="0.1"
                        value={addRuleProfitRate}
                        onChange={(e) => setAddRuleProfitRate(e.target.value)}
                        className="w-full rounded border border-slate-700 bg-slate-950 px-2 py-1 text-xs text-white focus:border-cyan-400 focus:outline-none"
                      />
                    </div>
                    <div>
                      <label className="block text-[9px] text-red-400 mb-1 font-bold">손실 제한 (%)</label>
                      <input
                        type="number"
                        step="0.1"
                        value={addRuleStopRate}
                        onChange={(e) => setAddRuleStopRate(e.target.value)}
                        className="w-full rounded border border-slate-700 bg-slate-950 px-2 py-1 text-xs text-white focus:border-cyan-400 focus:outline-none"
                      />
                    </div>
                  </div>

                  <div className="mt-2.5 flex items-center gap-2 select-none cursor-pointer">
                    <input
                      type="checkbox"
                      id="rule-auto-restart"
                      checked={addRuleAutoRestart}
                      onChange={(e) => setAddRuleAutoRestart(e.target.checked)}
                      className="accent-cyan-400 rounded"
                    />
                    <label htmlFor="rule-auto-restart" className="text-[10px] text-slate-400 font-bold cursor-pointer">
                      부분 체결 시 남은 수량 자동 재감시
                    </label>
                  </div>

                  <div className="mt-3 flex flex-wrap gap-2.5 items-center justify-between border-t border-[#1f2945]/40 pt-2.5">
                    <div className="flex gap-2">
                      <button
                        type="button"
                        onClick={() => setAddRuleExecutionMode('PROPOSAL')}
                        className={`rounded px-2.5 py-1 text-[10px] font-bold border transition cursor-pointer ${
                          addRuleExecutionMode === 'PROPOSAL'
                            ? 'border-cyan-400 bg-cyan-950/20 text-cyan-300'
                            : 'border-slate-800 text-slate-500 hover:text-slate-400'
                        }`}
                      >
                        매도 제안만 생성
                      </button>
                      <button
                        type="button"
                        onClick={() => setAddRuleExecutionMode('AUTO')}
                        className={`rounded px-2.5 py-1 text-[10px] font-bold border transition cursor-pointer ${
                          addRuleExecutionMode === 'AUTO'
                            ? 'border-rose-400 bg-rose-950/20 text-rose-300'
                            : 'border-slate-800 text-slate-500 hover:text-slate-400'
                        }`}
                      >
                        조건 도달 시 자동 매도
                      </button>
                    </div>

                    <div className="flex gap-2">
                      <button
                        type="button"
                        onClick={() => setShowAddRuleForm(false)}
                        className="rounded border border-slate-700 px-3 py-1 text-[10px] text-slate-300 hover:bg-slate-800 transition cursor-pointer"
                      >
                        취소
                      </button>
                      <button
                        type="button"
                        disabled={ruleUpdating}
                        onClick={handleAddRule}
                        className="rounded bg-cyan-500 px-3 py-1 text-[10px] font-black text-[#070b19] hover:bg-cyan-400 transition disabled:opacity-50 cursor-pointer"
                      >
                        {ruleUpdating ? '등록 중...' : '감시 등록'}
                      </button>
                    </div>
                  </div>
                </div>
              )}

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
                    const rawStopRate = Number(rule.stop_loss_rate || 0)
                    const stopRate = rawStopRate > 0 ? -Math.abs(rawStopRate) : rawStopRate
                    const targetPrice = entryPrice > 0 ? entryPrice * (1 + targetRate / 100) : 0
                    const stopPrice = entryPrice > 0 ? entryPrice * (1 + stopRate / 100) : 0
                    const isRunning = String(rule.status || '').toUpperCase() === 'RUNNING'
                    const ruleEnv = rule.broker_env || brokerEnv
                    const activePrice = ruleEnv === brokerEnv ? currentPrice : (oppositeCurrentPrice || currentPrice)

                    const currentReturnRate = entryPrice > 0 && activePrice > 0
                      ? ((Number(activePrice) - entryPrice) / entryPrice) * 100
                      : null
                    const currentReturnClass = currentReturnRate === null
                      ? 'text-slate-300'
                      : currentReturnRate >= 0
                        ? 'text-rose-300'
                        : 'text-blue-300'

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
                        {editingRuleId === rule.id ? (
                          <div className="mt-1 rounded border border-slate-700 bg-slate-900/40 p-2.5">
                            <div className="grid grid-cols-3 gap-2.5 text-xs">
                              <div>
                                <label className="block text-[9px] text-slate-500 mb-1 font-bold">익절 비율 (%)</label>
                                <input
                                  type="number"
                                  step="0.01"
                                  value={editTargetProfit}
                                  onChange={(e) => setEditTargetProfit(e.target.value)}
                                  className="w-full rounded border border-slate-700 bg-slate-950 px-2 py-1 text-xs text-white focus:border-cyan-400 focus:outline-none"
                                />
                              </div>
                              <div>
                                <label className="block text-[9px] text-slate-500 mb-1 font-bold">손절 비율 (%)</label>
                                <input
                                  type="number"
                                  step="0.01"
                                  value={editStopLoss}
                                  onChange={(e) => setEditStopLoss(e.target.value)}
                                  className="w-full rounded border border-slate-700 bg-slate-950 px-2 py-1 text-xs text-white focus:border-cyan-400 focus:outline-none"
                                />
                              </div>
                              <div>
                                <label className="block text-[9px] text-slate-500 mb-1 font-bold">수량</label>
                                <input
                                  type="number"
                                  step="0.0001"
                                  value={editQuantity}
                                  onChange={(e) => setEditQuantity(e.target.value)}
                                  className="w-full rounded border border-slate-700 bg-slate-950 px-2 py-1 text-xs text-white focus:border-cyan-400 focus:outline-none"
                                  placeholder="미입력 시 전량"
                                />
                              </div>
                            </div>
                            <div className="mt-3 flex justify-end gap-2 text-[10px]">
                              <button
                                type="button"
                                onClick={() => setEditingRuleId(null)}
                                className="rounded border border-slate-700 px-2.5 py-1 text-slate-300 hover:bg-slate-800 transition cursor-pointer"
                              >
                                취소
                              </button>
                              <button
                                type="button"
                                disabled={ruleUpdating}
                                onClick={() => handleUpdateRule(rule.id)}
                                className="rounded bg-emerald-500 px-2.5 py-1 font-black text-slate-950 hover:bg-emerald-400 disabled:opacity-50 transition cursor-pointer"
                              >
                                {ruleUpdating ? '저장 중...' : '저장'}
                              </button>
                            </div>
                          </div>
                        ) : (
                          <>
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
                            <div className="mt-3 grid grid-cols-1 gap-2 border-t border-[#1f2945] pt-3 text-[10px] text-slate-500 sm:grid-cols-4">
                              <div>
                                <p>마지막 확인</p>
                                <p className="font-mono text-slate-300">
                                  {rule.last_checked_at ? new Date(rule.last_checked_at).toLocaleString('ko-KR') : '-'}
                                </p>
                              </div>
                              <div>
                                <p>현재 수익률</p>
                                <p className={`font-mono font-bold ${currentReturnClass}`}>
                                  {formatSignedPercentValue(currentReturnRate)}
                                </p>
                                <p className="font-mono text-[10px] text-slate-600">
                                  현재가 {activePrice > 0 ? `${formatUnitPrice(activePrice)}${ruleEnv !== brokerEnv ? ` (${ruleEnv})` : ''}` : '-'}
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
                                <p className="truncate text-amber-300">{isRunning ? (rule.last_error || '-') : '-'}</p>
                              </div>
                            </div>
                            {isRunning || String(rule.status || '').toUpperCase() === 'FAILED' ? (
                              <div className="mt-3 flex justify-end gap-2 border-t border-[#1f2945]/40 pt-2.5">
                                <button
                                  type="button"
                                  onClick={() => handleStartEditRule(rule)}
                                  className="rounded border border-slate-700 bg-slate-900/30 px-2.5 py-1 text-[10px] text-slate-300 hover:border-slate-500 hover:text-white transition cursor-pointer"
                                >
                                  조건 수정
                                </button>
                                <button
                                  type="button"
                                  disabled={ruleUpdating}
                                  onClick={() => handleStopRule(rule.id)}
                                  className="rounded border border-rose-900/60 bg-rose-950/10 px-2.5 py-1 text-[10px] text-rose-300 hover:border-rose-700 hover:bg-rose-950/20 transition cursor-pointer disabled:opacity-50"
                                >
                                  감시 정지
                                </button>
                              </div>
                            ) : (
                              <div className="mt-3 flex justify-end gap-2 border-t border-[#1f2945]/40 pt-2.5">
                                <button
                                  type="button"
                                  disabled={ruleUpdating}
                                  onClick={() => {
                                    if (confirm('해당 조건감시 기록을 화면에서 완전히 삭제하시겠습니까?')) {
                                      handleStopRule(rule.id)
                                    }
                                  }}
                                  className="rounded border border-rose-950 bg-rose-950/20 px-2.5 py-1 text-[10px] text-rose-400 hover:border-rose-800 hover:bg-rose-950/40 transition cursor-pointer disabled:opacity-50"
                                >
                                  감시 삭제
                                </button>
                              </div>
                            )}
                          </>
                        )}
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
                  { id: 'community', label: '커뮤니티' }
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
                <div className="max-h-[360px] overflow-y-auto pr-1">
                  <section className="min-h-[220px] rounded-lg border border-[#1f2945]/70 bg-[#07111f]/70 p-4">
                    <div className="mb-3 flex items-center justify-between gap-3 border-b border-[#1f2945]/50 pb-2">
                      <h3 className="text-sm font-bold text-cyan-200">뉴스</h3>
                      <span className="rounded-full border border-cyan-500/30 bg-cyan-950/30 px-2.5 py-1 text-[11px] font-bold text-cyan-100">
                        총 {Math.min(newsList.length, 10)}개
                      </span>
                    </div>

                    <div className="flex flex-col gap-3">
                      {loadingNews ? (
                        <div className="py-8 text-center text-xs text-cyan-400/80 font-mono animate-pulse">
                          뉴스 로드 중...
                        </div>
                      ) : newsList.length > 0 ? (
                        <>
                          {newsList.slice(0, 10).map(item => (
                            <div key={item.id} className="flex flex-col gap-2 border-b border-[#1f2945]/30 px-1 py-2 transition-all hover:bg-slate-800/10">
                              <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
                                <button
                                  type="button"
                                  onClick={() => handleToggleNewsSummary(item)}
                                  className="min-w-0 text-left text-xs text-[#e2e2ec] hover:text-cyan-200"
                                >
                                  <span className="block w-full max-w-full overflow-hidden text-ellipsis whitespace-nowrap pr-2 font-bold leading-5">
                                    {item.title}
                                  </span>
                                  <span className="mt-1.5 flex flex-wrap items-center gap-1.5">
                                    <span className="rounded border border-cyan-500/25 bg-cyan-950/25 px-1.5 py-0.5 text-[11px] font-bold text-cyan-200">
                                      {formatNewsSource(item.source)}
                                    </span>
                                    <span className="rounded border border-cyan-500/20 bg-cyan-950/10 px-1.5 py-0.5 text-[11px] font-[550] text-white">
                                      {formatTime(item.published_at)}
                                    </span>
                                  </span>
                                </button>
                                <div className="flex shrink-0 items-center gap-2">
                                  <button
                                    type="button"
                                    onClick={() => handleToggleNewsSummary(item)}
                                    disabled={summaryLoadingId === item.id}
                                    className="rounded border border-cyan-500/30 px-2 py-1 text-[10px] font-bold text-cyan-300 transition hover:bg-cyan-950/30 disabled:cursor-not-allowed disabled:opacity-60"
                                  >
                                    {summaryLoadingId === item.id ? '\uc0dd\uc131 \uc911' : selectedNewsId === item.id ? '\uc811\uae30' : '\uc694\uc57d \ubcf4\uae30'}
                                  </button>
                                  <a
                                    href={item.url}
                                    target="_blank"
                                    rel="noopener noreferrer"
                                    className="rounded border border-slate-700 px-2 py-1 text-[10px] font-bold text-slate-300 transition hover:border-cyan-500/40 hover:text-white"
                                  >
                                    {'\uc6d0\ubb38 \uc5f4\uae30'}
                                  </a>
                                </div>
                              </div>
                              {selectedNewsId === item.id ? (
                                <p className="rounded border border-cyan-500/20 bg-cyan-950/20 px-3 py-2 text-[11px] leading-5 text-slate-300">
                                  {item.ai_summary || (summaryLoadingId === item.id ? '\uc694\uc57d\uc744 \uc0dd\uc131\ud558\ub294 \uc911\uc785\ub2c8\ub2e4...' : '\uc694\uc57d \ubcf4\uae30 \ubc84\ud2bc\uc744 \ub20c\ub7ec 3\uc904 \uc694\uc57d\uc744 \uc0dd\uc131\ud558\uc138\uc694.')}
                                </p>
                              ) : null}
                            </div>
                          ))}
                        </>
                      ) : (
                        <div className="flex flex-col items-center gap-3 py-8 text-center">
                          <p className="text-xs text-slate-500 font-mono">
                            해당 종목의 저장된 뉴스가 없습니다.
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
                <div className="max-h-[360px] overflow-y-auto pr-1">
                  <section className="min-h-[220px] rounded-lg border border-[#1f2945]/70 bg-[#07111f]/70 p-4">
                    <div className="mb-3 flex items-center justify-between gap-3 border-b border-[#1f2945]/50 pb-2">
                      <h3 className="text-sm font-bold text-cyan-200">공시</h3>
                      <span className="rounded-full border border-cyan-500/30 bg-cyan-950/30 px-2.5 py-1 text-[11px] font-bold text-cyan-100">
                        총 {Math.min(disclosureList.length, 10)}개
                      </span>
                    </div>
                    <div className="flex flex-col gap-3">
                      {loadingDisclosures ? (
                        <div className="py-8 text-center text-xs text-cyan-400/80 font-mono animate-pulse">
                          DART 공시 로드 중...
                        </div>
                      ) : disclosureList.length > 0 ? (
                        <>
                          {disclosureList.slice(0, 10).map(item => {
                              const analysis = disclosureAnalyses[item.rcept_no]
                              const isOpen = selectedDisclosureId === item.id
                              const isLoadingAnalysis = disclosureAnalysisLoadingId === item.id
                              const risks = Array.isArray(analysis?.risk_points) ? analysis.risk_points : []
                              const metrics = Array.isArray(analysis?.metrics) ? analysis.metrics : []
                              const checkItems = Array.isArray(analysis?.check_items) ? analysis.check_items : []
                              const metricLabels = new Set(metrics.map(metric => metric?.label).filter(Boolean))
                              const duplicateCheckMetricMap = {
                                '계약 규모': ['계약금액', '매출액대비'],
                                '계약 상대': ['계약상대'],
                                '계약 기간': ['계약기간'],
                                '해지 규모': ['해지금액', '매출액대비'],
                                '해지 사유': ['해지사유'],
                                '사채 규모': ['사채의 권면총액'],
                                '전환 조건': ['전환가액', '행사가액', '교환가액', '청구금액'],
                                '청구 기간': ['전환청구기간', '행사청구기간'],
                                '최종 발행가': ['확정발행가액', '발행가액'],
                                '발행 주식 수': ['발행주식수', '신주의 수'],
                                '확정일': ['확정일'],
                                '주식 배정': ['1주당 배정'],
                                '신주 규모': ['보통주 신주', '기타주식 신주'],
                                '상장 일정': ['상장예정일', '배정기준일'],
                                '조정 기준가': ['기준가'],
                                '실시일': ['권리락 실시일'],
                                '권리락 사유': ['사유'],
                                '배당 규모': ['1주당 배당금', '시가배당율', '배당금총액'],
                                '환원 규모': ['취득예정금액', '소각예정금액', '취득예정주식'],
                                '소각 규모': ['소각예정금액', '소각예정주식'],
                                '소각 일정': ['소각예정일'],
                                '처분 규모': ['처분예정금액', '처분예정주식'],
                                '변경 후 대표': ['변경후 대표이사'],
                                '변경 사유': ['변경사유'],
                                '투자 규모': ['투자금액', '자기자본대비'],
                                '투자 목적': ['투자목적', '투자대상'],
                                '정지 규모': ['영업정지금액', '매출액대비'],
                                '정지 사유': ['영업정지사유'],
                                '감자 비율': ['감자비율'],
                                '감자 일정': ['감자기준일', '상장예정일'],
                                '분할 비율': ['분할비율'],
                                '병합 비율': ['병합비율'],
                                '거래정지 일정': ['매매거래정지기간', '신주권상장예정일'],
                                '거래정지 사유': ['거래정지사유'],
                                '정지 기간': ['거래정지일', '해제일시'],
                                '위험 사유': ['위험사유', '상장폐지사유'],
                                '심사 일정': ['심사일정', '개선기간'],
                                '발생 규모': ['발생금액', '자기자본대비'],
                                '회사 대응': ['향후대책', '발생사실'],
                                '신청 사유': ['신청사유'],
                                '법원 일정': ['관할법원', '신청일자', '결정내용'],
                                '새 최대주주': ['변경후 최대주주', '지분율'],
                                '합병 조건': ['합병비율', '합병기일'],
                                '소송 규모': ['소송가액'],
                                '보증 규모': ['채무보증금액', '자기자본대비'],
                                '보증 대상': ['채무자', '채권자'],
                                '보증 기간': ['채무보증기간'],
                                '발행 결과': ['실제발행금액', '실제발행주식수'],
                                '납입 일정': ['납입일', '상장예정일'],
                                '발행 규모': ['발행총액'],
                                '조달 목적': ['자금조달의 목적'],
                                '행사 물량': ['행사주식수', '발행주식총수 대비'],
                                '실적 규모': ['매출액', '영업이익', '당기순이익'],
                                '증감 방향': ['전년동기대비', '직전분기대비'],
                                '변동 규모': ['영업이익', '당기순이익', '전년대비'],
                                '변동 사유': ['변동사유'],
                                '계획 구체성': ['목표지표', '주주환원계획'],
                                '실행 일정': ['이행기간', '공시주기'],
                                '핵심 내용': ['주요내용', '계약금액', '전망매출액'],
                                '실현 가능성': ['추진일정', '계약상대'],
                                '답변 내용': ['답변내용', '진행사항'],
                                '후속 일정': ['답변일', '조회공시요구일'],
                              }
                              const visibleCheckItems = checkItems.filter((check) => {
                                const duplicateMetricLabels = duplicateCheckMetricMap[check?.question] || []
                                if (duplicateMetricLabels.some(label => metricLabels.has(label))) return false
                                return check?.answer && check.answer !== '확인 필요'
                              })

                              return (
                                <div key={item.id} className="flex flex-col gap-2 border-b border-[#1f2945]/30 px-1 py-2 transition-all hover:bg-slate-800/10">
                                  <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
                                    <button
                                      type="button"
                                      onClick={() => handleToggleDisclosureAnalysis(item)}
                                      className="min-w-0 text-left text-xs text-[#e2e2ec] hover:text-cyan-200"
                                    >
                                      <span className="block w-full max-w-full overflow-hidden text-ellipsis whitespace-nowrap pr-2 font-bold leading-5">
                                        {item.report_nm}
                                      </span>
                                      <span className="mt-1.5 flex flex-wrap items-center gap-1.5">
                                        <span className="rounded border border-cyan-500/25 bg-cyan-950/25 px-1.5 py-0.5 text-[11px] font-bold text-cyan-200">
                                          {item.corp_name || 'DART'}
                                        </span>
                                        <span className="rounded border border-cyan-500/20 bg-cyan-950/10 px-1.5 py-0.5 text-[11px] font-[550] text-white">
                                          {formatDisclosureDate(item.rcept_dt)}
                                        </span>
                                      </span>
                                    </button>
                                    <div className="flex shrink-0 items-center gap-2">
                                      <button
                                        type="button"
                                        onClick={() => handleToggleDisclosureAnalysis(item)}
                                        disabled={isLoadingAnalysis}
                                        className="rounded border border-cyan-500/30 px-2 py-1 text-[10px] font-bold text-cyan-300 transition hover:bg-cyan-950/30 disabled:cursor-not-allowed disabled:opacity-60"
                                      >
                                        {isLoadingAnalysis ? '분석 중' : isOpen ? '접기' : '요약 보기'}
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
                                  {isOpen ? (
                                    <div className="rounded border border-cyan-500/20 bg-cyan-950/20 px-3 py-2 text-[11px] leading-5 text-slate-300">
                                      {isLoadingAnalysis && !analysis ? (
                                        <p className="text-cyan-300">DART 상세 공시를 확인하는 중입니다...</p>
                                      ) : analysis ? (
                                        <div className="space-y-2">
                                          <div className="flex flex-wrap items-center gap-1.5">
                                            <span className={`rounded border px-2 py-0.5 text-[11px] font-bold ${getDisclosureToneClass(analysis.sentiment)}`}>
                                              {analysis.sentiment_label || '정보'}
                                            </span>
                                            <span className="rounded border border-slate-600/60 bg-slate-900/50 px-2 py-0.5 text-[10px] font-medium text-slate-200">
                                              신뢰도 {analysis.confidence === 'high' ? '높음' : analysis.confidence === 'medium' ? '보통' : '낮음'}
                                            </span>
                                            <span className="text-[10px] text-slate-500">
                                              {analysis.analysis_source === 'OPENDART_DOCUMENT' ? 'DART 상세 기반' : '제목 기반'}
                                            </span>
                                          </div>
                                          <p className="font-bold text-slate-100">{analysis.headline}</p>
                                          {analysis.plain_summary ? (
                                            <p className="rounded border border-[#1f2945]/60 bg-slate-950/30 px-2 py-1.5 text-[11px] leading-5 text-slate-200">
                                              {analysis.plain_summary}
                                            </p>
                                          ) : null}
                                          {metrics.length > 0 ? (
                                            <div className="grid gap-1 sm:grid-cols-2">
                                              {metrics.slice(0, 6).map((metric, index) => (
                                                <div key={`${metric.label}-${index}`} className="rounded border border-[#1f2945]/60 bg-slate-950/30 px-2 py-1">
                                                  <span className="text-cyan-200">{metric.label}</span>
                                                  <span className="mx-1 text-slate-600">·</span>
                                                  <span className="text-white">{String(metric.value || '').length > 28 ? `${String(metric.value).slice(0, 28)}...` : metric.value}</span>
                                                </div>
                                              ))}
                                            </div>
                                          ) : null}
                                          {visibleCheckItems.length > 0 ? (
                                            <div className="grid gap-1 sm:grid-cols-2">
                                              {visibleCheckItems.slice(0, 3).map((check, index) => (
                                                <div key={`${check.question}-${index}`} className="rounded border border-[#1f2945]/60 bg-[#07111f]/70 px-2 py-1">
                                                  <span className="text-cyan-200">{check.question}</span>
                                                  <span className="mx-1 text-slate-600">·</span>
                                                  <span className="text-slate-100">{String(check.answer || '').length > 24 ? `${String(check.answer).slice(0, 24)}...` : check.answer}</span>
                                                </div>
                                              ))}
                                            </div>
                                          ) : null}
                                          {risks.length > 0 ? (
                                            <p className="text-amber-200/90">확인 포인트: {risks[0]}</p>
                                          ) : null}
                                        </div>
                                      ) : (
                                        <p>{item.summary || item.report_nm || '저장된 요약이 없습니다.'}</p>
                                      )}
                                    </div>
                                  ) : null}
                                </div>
                              )
                          })}
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
                <div className="max-h-[420px] overflow-y-auto pr-1">
                  <section className="min-h-[260px] rounded-lg border border-[#1f2945]/70 bg-[#07111f]/70 p-4">
                    <div className="mb-3 flex flex-col gap-2 border-b border-[#1f2945]/50 pb-3 sm:flex-row sm:items-center sm:justify-between">
                      <div>
                        <h3 className="text-sm font-bold text-cyan-200">커뮤니티</h3>
                        <p className="mt-1 text-[11px] text-slate-500">{displayName} 의견을 남기고 확인합니다.</p>
                      </div>
                      <span className="w-fit rounded-full border border-cyan-500/30 bg-cyan-950/30 px-2.5 py-1 text-[11px] font-bold text-cyan-100">
                        총 {communityPosts.length}개
                      </span>
                    </div>

                    <form onSubmit={handleSubmitCommunityPost} className="mb-4 flex flex-col gap-2">
                      <textarea
                        value={communityDraft}
                        onChange={(event) => setCommunityDraft(event.target.value)}
                        maxLength={500}
                        placeholder={isLoggedIn ? '이 종목에 대한 의견을 입력해 주세요.' : '로그인 후 커뮤니티 글을 작성할 수 있습니다.'}
                        disabled={!isLoggedIn || communitySubmitting}
                        className="min-h-[88px] w-full resize-none rounded border border-[#1f2945] bg-slate-950/50 px-3 py-2 text-xs leading-5 text-slate-100 outline-none transition focus:border-cyan-500/50 disabled:cursor-not-allowed disabled:opacity-60"
                      />
                      <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
                        <span className={`text-[11px] ${communityDraft.trim().length > 500 ? 'text-rose-300' : 'text-slate-500'}`}>
                          {communityDraft.trim().length}/500
                        </span>
                        <button
                          type="submit"
                          disabled={!isLoggedIn || communitySubmitting || communityDraft.trim().length === 0}
                          className="rounded border border-cyan-500/40 bg-cyan-950/30 px-3 py-2 text-[11px] font-bold text-cyan-200 transition hover:bg-cyan-900/30 disabled:cursor-not-allowed disabled:opacity-50"
                        >
                          {communitySubmitting ? '등록 중...' : '글 등록'}
                        </button>
                      </div>
                    </form>

                    {communityMessage.text ? (
                      <p className={`mb-3 rounded border px-3 py-2 text-[11px] leading-5 ${communityMessage.isError ? 'border-rose-500/30 bg-rose-950/20 text-rose-200' : 'border-cyan-500/30 bg-cyan-950/20 text-cyan-200'}`}>
                        {communityMessage.text}
                      </p>
                    ) : null}

                    <div className="flex flex-col gap-3">
                      {communityLoading ? (
                        <div className="py-8 text-center text-xs font-mono text-cyan-400/80 animate-pulse">
                          커뮤니티 로드 중...
                        </div>
                      ) : communityRootPosts.length > 0 ? (
                        communityRootPosts.map((post) => {
                          const profile = communityProfiles[post.user_id] || {}
                          const canDelete = communityCurrentUserId && communityCurrentUserId === post.user_id
                          const canHide = userProfile?.role === 'ADMIN' && !canDelete
                          const replies = communityReplyMap[post.id] || []
                          return (
                            <article key={post.id} className="rounded border border-[#1f2945]/60 bg-[#1b253b]/35 p-3">
                              <div className="flex flex-col gap-1.5 sm:flex-row sm:items-center sm:justify-between">
                                <div className="flex min-w-0 flex-wrap items-center gap-1.5 text-[10px]">
                                  <span className="max-w-[160px] truncate font-bold text-cyan-300">
                                    {profile.nickname || '익명 사용자'}
                                  </span>
                                  {profile.role === 'ADMIN' ? (
                                    <span className="rounded border border-amber-400/30 bg-amber-500/10 px-1.5 py-0.5 font-bold text-amber-200">
                                      ADMIN
                                    </span>
                                  ) : null}
                                  <span className="text-slate-500">{formatTime(post.created_at)}</span>
                                </div>
                                <div className="flex shrink-0 gap-1.5">
                                  {isLoggedIn ? (
                                    <button
                                      type="button"
                                      onClick={() => {
                                        setCommunityReplyParentId(communityReplyParentId === post.id ? '' : post.id)
                                        setCommunityReplyDraft('')
                                      }}
                                      className="rounded border border-cyan-500/25 px-2 py-1 text-[10px] font-bold text-cyan-300 transition hover:bg-cyan-950/30"
                                    >
                                      답글
                                    </button>
                                  ) : null}
                                  {(canDelete || canHide) ? (
                                    <>
                                    {canDelete ? (
                                      <button
                                        type="button"
                                        disabled={communityActionId === post.id}
                                        onClick={() => handleUpdateCommunityStatus(post, 'DELETED')}
                                        className="rounded border border-slate-700 px-2 py-1 text-[10px] font-bold text-slate-400 transition hover:border-rose-500/40 hover:text-rose-200 disabled:cursor-not-allowed disabled:opacity-50"
                                      >
                                        삭제
                                      </button>
                                    ) : null}
                                    {canHide ? (
                                      <button
                                        type="button"
                                        disabled={communityActionId === post.id}
                                        onClick={() => handleUpdateCommunityStatus(post, 'HIDDEN')}
                                        className="rounded border border-amber-600/40 px-2 py-1 text-[10px] font-bold text-amber-300 transition hover:bg-amber-950/30 disabled:cursor-not-allowed disabled:opacity-50"
                                      >
                                        숨김
                                      </button>
                                    ) : null}
                                    </>
                                  ) : null}
                                </div>
                              </div>
                              <p className="mt-2 whitespace-pre-wrap break-words text-xs leading-5 text-[#e2e2ec]">
                                {post.content}
                              </p>
                              {communityReplyParentId === post.id ? (
                                <form onSubmit={(event) => handleSubmitCommunityReply(event, post)} className="mt-3 rounded border border-cyan-500/20 bg-cyan-950/10 p-2">
                                  <textarea
                                    value={communityReplyDraft}
                                    onChange={(event) => setCommunityReplyDraft(event.target.value)}
                                    maxLength={500}
                                    placeholder="답글을 입력해 주세요."
                                    disabled={communitySubmitting}
                                    className="min-h-[64px] w-full resize-none rounded border border-[#1f2945] bg-slate-950/60 px-2.5 py-2 text-[11px] leading-5 text-slate-100 outline-none transition focus:border-cyan-500/50 disabled:cursor-not-allowed disabled:opacity-60"
                                  />
                                  <div className="mt-2 flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
                                    <span className="text-[10px] text-slate-500">{communityReplyDraft.trim().length}/500</span>
                                    <div className="flex justify-end gap-2">
                                      <button
                                        type="button"
                                        onClick={() => {
                                          setCommunityReplyParentId('')
                                          setCommunityReplyDraft('')
                                        }}
                                        className="rounded border border-slate-700 px-2.5 py-1 text-[10px] font-bold text-slate-400 transition hover:text-slate-200"
                                      >
                                        취소
                                      </button>
                                      <button
                                        type="submit"
                                        disabled={communitySubmitting || communityReplyDraft.trim().length === 0}
                                        className="rounded border border-cyan-500/40 bg-cyan-950/30 px-2.5 py-1 text-[10px] font-bold text-cyan-200 transition hover:bg-cyan-900/30 disabled:cursor-not-allowed disabled:opacity-50"
                                      >
                                        {communitySubmitting ? '등록 중...' : '답글 등록'}
                                      </button>
                                    </div>
                                  </div>
                                </form>
                              ) : null}
                              {replies.length > 0 ? (
                                <div className="mt-3 flex flex-col gap-2 border-l-2 border-cyan-500/20 pl-3">
                                  {replies.map((reply) => {
                                    const replyProfile = communityProfiles[reply.user_id] || {}
                                    const canDeleteReply = communityCurrentUserId && communityCurrentUserId === reply.user_id
                                    const canHideReply = userProfile?.role === 'ADMIN' && !canDeleteReply
                                    return (
                                      <div key={reply.id} className="rounded border border-[#1f2945]/50 bg-slate-950/30 p-2.5">
                                        <div className="flex flex-col gap-1.5 sm:flex-row sm:items-center sm:justify-between">
                                          <div className="flex min-w-0 flex-wrap items-center gap-1.5 text-[10px]">
                                            <span className="text-cyan-400">↳</span>
                                            <span className="max-w-[140px] truncate font-bold text-cyan-300">
                                              {replyProfile.nickname || '익명 사용자'}
                                            </span>
                                            {replyProfile.role === 'ADMIN' ? (
                                              <span className="rounded border border-amber-400/30 bg-amber-500/10 px-1.5 py-0.5 font-bold text-amber-200">
                                                ADMIN
                                              </span>
                                            ) : null}
                                            <span className="text-slate-500">{formatTime(reply.created_at)}</span>
                                          </div>
                                          {(canDeleteReply || canHideReply) ? (
                                            <div className="flex shrink-0 gap-1.5">
                                              {canDeleteReply ? (
                                                <button
                                                  type="button"
                                                  disabled={communityActionId === reply.id}
                                                  onClick={() => handleUpdateCommunityStatus(reply, 'DELETED')}
                                                  className="rounded border border-slate-700 px-2 py-1 text-[10px] font-bold text-slate-400 transition hover:border-rose-500/40 hover:text-rose-200 disabled:cursor-not-allowed disabled:opacity-50"
                                                >
                                                  삭제
                                                </button>
                                              ) : null}
                                              {canHideReply ? (
                                                <button
                                                  type="button"
                                                  disabled={communityActionId === reply.id}
                                                  onClick={() => handleUpdateCommunityStatus(reply, 'HIDDEN')}
                                                  className="rounded border border-amber-600/40 px-2 py-1 text-[10px] font-bold text-amber-300 transition hover:bg-amber-950/30 disabled:cursor-not-allowed disabled:opacity-50"
                                                >
                                                  숨김
                                                </button>
                                              ) : null}
                                            </div>
                                          ) : null}
                                        </div>
                                        <p className="mt-1.5 whitespace-pre-wrap break-words text-[11px] leading-5 text-[#e2e2ec]">
                                          {reply.content}
                                        </p>
                                      </div>
                                    )
                                  })}
                                </div>
                              ) : null}
                            </article>
                          )
                        })
                      ) : (
                        <div className="rounded border border-[#1f2945] bg-[#070b19] px-3 py-8 text-center">
                          <p className="text-xs text-slate-500 font-mono">
                            아직 이 종목의 커뮤니티 글이 없습니다.
                          </p>
                        </div>
                      )}
                    </div>
                  </section>
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
                    const interpretation = buildMlSignalInterpretation(mlSignal)
                    if (!interpretation) return null

                    return (
                      <div className={`rounded-lg border px-3 py-3 ${interpretation.actionTone}`}>
                        <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                          <div>
                            <p className="text-[10px] font-bold uppercase tracking-[0.16em] opacity-80">AI 참고 판단</p>
                            <p className="mt-1 text-lg font-black text-white">{interpretation.actionLabel}</p>
                          </div>
                          <div className="flex flex-wrap gap-2 text-[10px] font-bold">
                            <span className="rounded border border-white/15 bg-black/15 px-2 py-1">{interpretation.modelScope}</span>
                            <span className="rounded border border-white/15 bg-black/15 px-2 py-1">
                              {mlSignal.meta?.serving_version ? '서비스 모델' : '추천/최신 모델'}
                            </span>
                          </div>
                        </div>
                        <p className="mt-3 break-words text-xs leading-5 text-slate-100">{interpretation.reason}</p>
                        <div className="mt-3 grid grid-cols-1 gap-2 sm:grid-cols-2">
                          <div className="rounded border border-white/10 bg-black/15 p-2">
                            <p className="text-[10px] text-slate-300">상승 가능성</p>
                            <p className={`mt-1 text-sm font-black ${interpretation.up.tone}`}>
                              {interpretation.up.label} <span className="font-mono text-xs">({formatProbability(mlSignal.up_probability)})</span>
                            </p>
                            <p className="mt-1 text-[10px] leading-4 text-slate-300">{interpretation.up.detail}</p>
                          </div>
                          <div className="rounded border border-white/10 bg-black/15 p-2">
                            <p className="text-[10px] text-slate-300">하락 위험</p>
                            <p className={`mt-1 text-sm font-black ${interpretation.risk.tone}`}>
                              {interpretation.risk.label} <span className="font-mono text-xs">({formatProbability(mlSignal.risk_probability)})</span>
                            </p>
                            <p className="mt-1 text-[10px] leading-4 text-slate-300">{interpretation.risk.detail}</p>
                          </div>
                        </div>
                      </div>
                    )
                  })()}

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
                    disabled={isTradingSuspended}
                    className={`text-xs font-bold py-1.5 rounded transition-all cursor-pointer ${side === 'BUY' ? 'bg-[#ef4444] text-white' : 'text-slate-400 hover:text-white'}`}
                  >
                    구매
                  </button>
                  <button
                    type="button"
                    onClick={() => setSide('SELL')}
                    disabled={isTradingSuspended}
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
                      disabled={isTradingSuspended}
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
                      disabled={exchange === 'COINONE' || isTradingSuspended}
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
                    disabled={orderType === 'MARKET' || isTradingSuspended}
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
                    disabled={isTradingSuspended}
                    required
                  />
                </div>

                {/* 3. 거래 계좌 스위처 토글 */}
                <div className="flex flex-col gap-1.5">
                  <div className="flex justify-between items-center">
                    <span className="text-[10px] text-slate-400 font-bold">주문 거래소 계좌</span>
                    {isResolvedUsStock && (
                      <span className="text-[9px] font-bold text-orange-400">해외주식은 toss api만 지원합니다</span>
                    )}
                  </div>
                  {resolvedAssetType === 'STOCK' ? (
                    <div className="grid grid-cols-3 gap-1 bg-[#070b19] p-0.5 rounded border border-[#1f2945]">
                      <button
                        type="button"
                        onClick={() => handleExchangeChange('KIS', 'MOCK')}
                        disabled={isTradingSuspended || isResolvedUsStock}
                        className={`text-[10px] font-bold py-1.5 rounded transition-all ${
                          isResolvedUsStock
                            ? 'opacity-30 cursor-not-allowed text-slate-600 bg-transparent'
                            : exchange === 'KIS' && brokerEnv === 'MOCK'
                            ? 'bg-[#1b253b] text-cyan-400 border border-cyan-900/60 cursor-pointer'
                            : 'text-slate-400 hover:text-white cursor-pointer'
                        }`}
                      >
                        한투 모의
                      </button>
                      <button
                        type="button"
                        onClick={() => handleExchangeChange('KIS', 'REAL')}
                        disabled={isTradingSuspended || isResolvedUsStock}
                        className={`text-[10px] font-bold py-1.5 rounded transition-all ${
                          isResolvedUsStock
                            ? 'opacity-30 cursor-not-allowed text-slate-600 bg-transparent'
                            : exchange === 'KIS' && brokerEnv === 'REAL'
                            ? 'bg-[#1b253b] text-cyan-400 border border-cyan-900/60 cursor-pointer'
                            : 'text-slate-400 hover:text-white cursor-pointer'
                        }`}
                      >
                        한투 실거래
                      </button>
                      <button
                        type="button"
                        onClick={() => handleExchangeChange('TOSS', 'REAL')}
                        disabled={isTradingSuspended}
                        className={`text-[10px] font-bold py-1.5 rounded transition-all cursor-pointer ${exchange === 'TOSS' && brokerEnv === 'REAL' ? 'bg-[#1b253b] text-cyan-400 border border-cyan-900/60' : 'text-slate-400 hover:text-white'}`}
                      >
                        토스 실거래
                      </button>
                    </div>
                  ) : (
                    <div className="flex flex-col gap-1.5">
                      <div className="grid grid-cols-3 gap-1 bg-[#070b19] p-0.5 rounded border border-[#1f2945]">
                        <button
                          type="button"
                          onClick={() => handleExchangeChange('COINONE', 'REAL')}
                          disabled={isTradingSuspended}
                          className={`text-[10px] font-bold py-1.5 rounded transition-all cursor-pointer ${exchange === 'COINONE' ? 'bg-[#1b253b] text-cyan-400 border border-cyan-900/60' : 'text-slate-400 hover:text-white'}`}
                        >
                          코인원
                        </button>
                        <button
                          type="button"
                          onClick={() => handleExchangeChange('BINANCE', brokerEnv)}
                          disabled={isTradingSuspended}
                          className={`text-[10px] font-bold py-1.5 rounded transition-all cursor-pointer ${exchange === 'BINANCE' ? 'bg-[#1b253b] text-cyan-400 border border-cyan-900/60' : 'text-slate-400 hover:text-white'}`}
                        >
                          바이낸스 현물
                        </button>
                        <button
                          type="button"
                          onClick={() => handleExchangeChange('BINANCE_UM_FUTURES', brokerEnv)}
                          disabled={isTradingSuspended}
                          className={`text-[10px] font-bold py-1.5 rounded transition-all cursor-pointer ${exchange === 'BINANCE_UM_FUTURES' ? 'bg-[#1b253b] text-cyan-400 border border-cyan-900/60' : 'text-slate-400 hover:text-white'}`}
                        >
                          바이낸스 선물
                        </button>
                      </div>

                      {['BINANCE', 'BINANCE_UM_FUTURES'].includes(exchange) && (
                        <div className="flex items-center justify-between bg-[#070b19] border border-[#1f2945] p-1 rounded">
                          <span className="text-[10px] font-bold text-slate-400 pl-1.5">거래 환경</span>
                          <div className="flex gap-1">
                            <button
                              type="button"
                              onClick={() => handleExchangeChange(exchange, 'REAL')}
                              className={`text-[9px] font-bold px-2.5 py-1 rounded transition-all cursor-pointer ${brokerEnv === 'REAL' ? 'bg-[#1b253b] text-cyan-400 border border-cyan-900/60' : 'text-slate-500 hover:text-white bg-transparent'}`}
                            >
                              실거래 (REAL)
                            </button>
                            <button
                              type="button"
                              onClick={() => handleExchangeChange(exchange, 'MOCK')}
                              className={`text-[9px] font-bold px-2.5 py-1 rounded transition-all cursor-pointer ${brokerEnv === 'MOCK' ? 'bg-[#1b253b] text-cyan-400 border border-cyan-900/60' : 'text-slate-500 hover:text-white bg-transparent'}`}
                            >
                              모의투자 (MOCK)
                            </button>
                          </div>
                        </div>
                      )}
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
                          ? (tradeRestrictionMessage || orderPrecheck.warnings?.join(' ') || '실거래 주문 조건을 다시 확인해 주세요.')
                          : '현재 입력값 기준으로 즉시 주문 가능 범위를 확인했습니다.'}
                      </div>
                    </>
                  )}
                  {!orderPrecheck && precheckMessage && (
                    <div className="whitespace-pre-line rounded border border-amber-900/60 bg-amber-950/20 px-2 py-1 leading-relaxed text-amber-300">
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
                        
                        {/* 감시 기준 선택 (선물일 때만 노출) */}
                        {isFuturesOrder && (
                          <div className="flex items-center justify-between px-1">
                            <span className="text-[10px] text-slate-400">감시 기준 설정</span>
                            <div className="flex gap-1 bg-[#070b19] border border-[#1f2945] p-0.5 rounded text-[9px]">
                              <button
                                type="button"
                                onClick={() => setAutoExitRateType('PRICE')}
                                className={`px-2 py-0.5 rounded transition ${
                                  autoExitRateType === 'PRICE'
                                    ? 'bg-[#1f2945] text-cyan-300 font-bold'
                                    : 'text-slate-500 hover:text-slate-400'
                                }`}
                              >
                                자산 가격 (%)
                              </button>
                              <button
                                type="button"
                                onClick={() => setAutoExitRateType('ROE')}
                                className={`px-2 py-0.5 rounded transition ${
                                  autoExitRateType === 'ROE'
                                    ? 'bg-[#1f2945] text-purple-300 font-bold'
                                    : 'text-slate-500 hover:text-slate-400'
                                }`}
                              >
                                투자금(ROE) (%)
                              </button>
                            </div>
                          </div>
                        )}

                        <div className="flex items-center gap-2 px-1 py-0.5 select-none cursor-pointer">
                          <input
                            type="checkbox"
                            id="order-auto-restart"
                            checked={autoRestartOnPartialFill}
                            onChange={(e) => setAutoRestartOnPartialFill(e.target.checked)}
                            className="accent-cyan-400 rounded"
                          />
                          <label htmlFor="order-auto-restart" className="text-[10px] text-slate-400 font-bold cursor-pointer">
                            부분 체결 시 남은 수량 자동 재감시
                          </label>
                        </div>

                        <div className="grid grid-cols-2 gap-2 bg-[#070b19] border border-[#1f2945] rounded p-2.5">
                          <div className="flex flex-col gap-1">
                            <label className="text-[9px] font-bold text-green-400">
                              목표 익절 (%) {autoExitRateType === 'ROE' && <span className="text-purple-400 font-normal">(ROE)</span>}
                            </label>
                            <input
                              type="number"
                              step="0.1"
                              value={targetProfitRate}
                              onChange={(e) => setTargetProfitRate(e.target.value)}
                              className="bg-slate-800 border border-slate-700 text-[#e2e2ec] font-mono rounded py-0.5 text-xs text-center"
                            />
                            {getAutoExitTargetPrices() && (
                              <span className="text-[8px] text-slate-400 font-mono text-center mt-0.5 break-all">
                                목표가: {formatUnitPrice(getAutoExitTargetPrices().tpPrice)}
                                {autoExitRateType === 'ROE' && ` (가격 ${getAutoExitTargetPrices().tpPercent.toFixed(2)}%)`}
                              </span>
                            )}
                          </div>
                          <div className="flex flex-col gap-1">
                            <label className="text-[9px] font-bold text-red-400">
                              손실 제한 (%) {autoExitRateType === 'ROE' && <span className="text-purple-400 font-normal">(ROE)</span>}
                            </label>
                            <input
                              type="number"
                              step="0.1"
                              value={stopLossRate}
                              onChange={(e) => setStopLossRate(e.target.value)}
                              className="bg-slate-800 border border-slate-700 text-[#e2e2ec] font-mono rounded py-0.5 text-xs text-center"
                            />
                            {getAutoExitTargetPrices() && (
                              <span className="text-[8px] text-slate-400 font-mono text-center mt-0.5 break-all">
                                손절가: {formatUnitPrice(getAutoExitTargetPrices().slPrice)}
                                {autoExitRateType === 'ROE' && ` (가격 ${getAutoExitTargetPrices().slPercent.toFixed(2)}%)`}
                              </span>
                            )}
                          </div>
                        </div>
                      </div>
                    )}
                  </div>
                )}

                {isTradingSuspended && (
                  <div className="text-[10px] text-rose-300 bg-rose-950/20 p-2 rounded border border-rose-900/50 leading-relaxed font-mono">
                    {tradeRestrictionMessage}
                  </div>
                )}

                {/* 결과 메세지 */}
                {tradeMessage.text && (
                  <div className={`whitespace-pre-line p-2.5 rounded text-xs font-bold leading-relaxed border ${tradeMessage.isError ? 'bg-red-950/40 text-red-400 border-red-900/60' : 'bg-green-950/40 text-green-400 border-green-900/60'}`}>
                    {tradeMessage.text}
                  </div>
                )}

                {/* API 권한 경고 배지 */}
                {isBinancePermissionMissing() && (
                  <div className="bg-rose-950/40 border border-rose-800/60 rounded p-2.5 text-[10px] text-rose-300 font-bold leading-relaxed">
                    ⚠️ 해당 API Key는 바이낸스 {exchange === 'BINANCE' ? '현물(Spot)' : '선물(Futures)'} 거래 권한이 없습니다. 
                    바이낸스 API 관리자 페이지에서 권한을 활성화한 후 API 연결을 다시 테스트해 주세요.
                  </div>
                )}

                {/* 주문 제출 버튼 */}
                <button
                  type="submit"
                  disabled={submitting || precheckLoading || isOrderBlocked || isBinancePermissionMissing()}
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
                <div className="flex items-center gap-1.5">
                  <button
                    type="button"
                    onClick={handleRefreshBalance}
                    disabled={balanceCooldown > 0}
                    className={`rounded border px-2 py-1 text-[10px] font-black transition ${
                      balanceCooldown > 0
                        ? 'text-slate-500 border-slate-800/40 bg-slate-900/20 cursor-not-allowed'
                        : 'text-cyan-400 border-cyan-500/20 hover:bg-cyan-950/30 hover:border-cyan-500/40'
                    }`}
                  >
                    {balanceCooldown > 0 ? `대기 ${balanceCooldown}초` : '새로고침'}
                  </button>
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
                    <span className="font-bold text-white">
                      {dbEstimatedHolding.estimatedQty.toLocaleString()} {getEstimatedHoldingUnit(dbEstimatedHolding)}
                    </span>
                  </div>
                  <div className="flex justify-between border-b border-amber-400/20 py-1">
                    <span className="text-slate-300">기록 계좌</span>
                    <span className="font-bold text-white">{dbEstimatedHolding.exchange} ({dbEstimatedHolding.brokerEnv})</span>
                  </div>
                  {dbEstimatedHolding.avgPrice > 0 ? (
                    <div className="flex justify-between border-b border-amber-400/20 py-1">
                      <span className="text-slate-300">추정 평균가</span>
                      <span className="font-bold text-white">
                        {getEstimatedHoldingCurrencySign(dbEstimatedHolding)}
                        {dbEstimatedHolding.avgPrice.toLocaleString(undefined, { minimumFractionDigits: 0, maximumFractionDigits: 1 })}
                      </span>
                    </div>
                  ) : null}
                  <p className="leading-relaxed text-amber-200">
                    {getEstimatedHoldingNotice(dbEstimatedHolding)}
                  </p>
                </div>
              ) : balanceMessage ? (
                <div className="whitespace-pre-line rounded border border-amber-900/50 bg-amber-950/20 px-3 py-3 text-[11px] leading-relaxed text-amber-300">
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
