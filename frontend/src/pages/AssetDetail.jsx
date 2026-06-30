import React, { useState, useEffect, useEffectEvent, useRef } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { createChart, CandlestickSeries } from 'lightweight-charts'
import { supabase } from '../supabaseClient'
import Header from '../components/Header.jsx'

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:5050'

export default function AssetDetail({ isLoggedIn, userEmail, handleLogout, userProfile }) {
  const { assetType, symbol } = useParams()
  const navigate = useNavigate()
  const normalizedRouteAssetType = String(assetType || '').toUpperCase() === 'STOCK' ? 'STOCK' : 'CRYPTO'
  const [resolvedAssetType, setResolvedAssetType] = useState(normalizedRouteAssetType)

  const getCurrencySign = () => {
    if (exchange === 'COINONE') return '₩';
    if (exchange === 'BINANCE') return '$';
    if (resolvedAssetType === 'STOCK') {
      return /^\d+$/.test(symbol) ? '₩' : '$';
    }
    return '$';
  };

  const getCurrencyDigits = () => {
    if (exchange === 'COINONE') return 0;
    if (exchange === 'BINANCE') return 4;
    if (resolvedAssetType === 'STOCK') {
      return /^\d+$/.test(symbol) ? 0 : 4;
    }
    return 4;
  };

  // 1. 거래소 기본값 세팅 (주식은 TOSS 실거래를 기본값으로, 코인은 COINONE)
  const defaultExchange = normalizedRouteAssetType === 'STOCK' ? 'TOSS' : 'COINONE'
  const [exchange, setExchange] = useState(defaultExchange)
  
  // 2. 환경 세팅 (TOSS는 실거래만 지원하므로 기본 REAL 설정)
  const [brokerEnv, setBrokerEnv] = useState('REAL')
  const [chartInterval, setChartInterval] = useState(normalizedRouteAssetType === 'STOCK' ? '1d' : '1h')
  
  // 3. 차트 및 시세 데이터 상태
  const [candleData, setCandleData] = useState([])
  const [loadingChart, setLoadingChart] = useState(true)
  const [currentPrice, setCurrentPrice] = useState(0)
  const [priceChangeRate, setPriceChangeRate] = useState(0)

  // 4. 주문 폼 상태
  const [side, setSide] = useState('BUY') // BUY | SELL
  const [orderType, setOrderType] = useState('LIMIT') // LIMIT | MARKET
  const [price, setPrice] = useState('')
  const [quantity, setQuantity] = useState('')
  const [autoExit, setAutoExit] = useState(false)
  const [targetProfitRate, setTargetProfitRate] = useState(5.0)
  const [stopLossRate, setStopLossRate] = useState(-3.0)

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
  const [mlSignal, setMlSignal] = useState(null)
  const [mlSignalLoading, setMlSignalLoading] = useState(false)
  const [mlSignalMessage, setMlSignalMessage] = useState('')

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
  const showLevel2Panel = false

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
    try {
      const response = await fetch(`${API_BASE_URL}/api/symbol/lookup?query=${symbol}`)
      const resData = await response.json()
      if (resData.success && resData.data && resData.data.display_name) {
        setDisplayName(resData.data.display_name)
        const mappedAssetType = String(resData.data.asset_type || '').toUpperCase() === 'STOCK' ? 'STOCK' : 'CRYPTO'
        setResolvedAssetType(mappedAssetType)
      } else {
        setDisplayName(symbol)
        setResolvedAssetType(normalizedRouteAssetType)
      }
    } catch (e) {
      console.error("종목명 로드 실패:", e)
      setDisplayName(symbol)
      setResolvedAssetType(normalizedRouteAssetType)
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
        
        if (resData.meta && typeof resData.meta.change_rate === 'number') {
          setPriceChangeRate(resData.meta.change_rate);
        } else if (chartInterval === '1d' && uniqueFormatted.length > 1) {
          const prevCandle = uniqueFormatted[uniqueFormatted.length - 2];
          const change = prevCandle.close !== 0 ? ((lastCandle.close - prevCandle.close) / prevCandle.close) * 100 : 0;
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
        setUserBalance(null)
        setBalanceMessage(resData.message || `${exchange} (${brokerEnv}) 잔고를 불러오지 못했습니다.`)
      }
    } catch (error) {
      console.error('잔고 로드 실패:', error)
      setUserBalance(null)
      setBalanceMessage(`잔고 로드 실패: ${error.message}`)
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
          action: side,
          order_type: orderType,
          quantity: Number(quantity),
          price: orderType === 'LIMIT' ? Number(price) : null,
          broker_env: brokerEnv,
        }),
      })
      const resData = await response.json()
      if (resData.success) {
        setOrderPrecheck(resData.data)
      } else {
        setOrderPrecheck(null)
        setPrecheckMessage(resData.message || '주문 사전검증에 실패했습니다.')
      }
    } catch (error) {
      setOrderPrecheck(null)
      setPrecheckMessage(`주문 사전검증 오류: ${error.message}`)
    } finally {
      setPrecheckLoading(false)
    }
  }

  // 거래소 토글 시 환경값 변경
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
    fetchCandles()
    fetchUserBalance()
    fetchNewsList()
    fetchSymbolMetadata()
  }, [exchange, symbol, chartInterval, brokerEnv])

  useEffect(() => {
    loadBrokerAvailability()
  }, [symbol])

  useEffect(() => {
    const timer = window.setTimeout(() => {
      refreshMlSignal()
    }, 0)
    return () => window.clearTimeout(timer)
  }, [isLoggedIn, resolvedAssetType, symbol])

  useEffect(() => {
    if (resolvedAssetType === 'STOCK') {
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

    if (!['COINONE', 'BINANCE'].includes(exchange)) {
      setExchange('COINONE')
    }
    if (brokerEnv !== 'REAL') {
      setBrokerEnv('REAL')
    }
    if (!['1m', '5m', '15m', '30m', '1h', '4h', '1d', '1w', '1M'].includes(chartInterval)) {
      setChartInterval('1h')
    }
  }, [resolvedAssetType, exchange, brokerEnv, chartInterval, brokerAvailability])

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
    const timeoutId = window.setTimeout(() => {
      fetchOrderPrecheck()
    }, isStockAsset ? 800 : 250)

    return () => window.clearTimeout(timeoutId)
  }, [exchange, symbol, side, orderType, price, quantity, brokerEnv, isStockAsset])

  // 3. TradingView Lightweight Charts 차트 초기 생성 및 리사이즈 대응
  useEffect(() => {
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
        height: 460,
      })

      const candleSeries = chart.addSeries(CandlestickSeries, {
        upColor: '#ef4444', // 한국 상승 빨강
        downColor: '#3b82f6', // 한국 하락 파랑
        borderVisible: false,
        wickUpColor: '#ef4444',
        wickDownColor: '#3b82f6',
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
  }, [])

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
  }, [candleData])

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
        action: side,
        order_type: orderType,
        quantity: parseFloat(quantity),
        price: orderType === 'LIMIT' ? parseFloat(price) : null,
        broker_env: brokerEnv,
        auto_exit: autoExit,
        target_profit_rate: autoExit ? parseFloat(targetProfitRate) : null,
        stop_loss_rate: autoExit ? parseFloat(stopLossRate) : null
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
          text: `주문이 성공적으로 전송되었습니다! 주문번호: ${resData.order_id || 'MOCK'}${autoExitMessage}`,
          isError: false
        })
        setQuantity('')
        fetchUserBalance() // 주문 성공 시 보유 자산 즉시 갱신
      } else {
        setTradeMessage({
          text: resData.message || '주문 전송에 실패했습니다.',
          isError: true
        })
      }
    } catch (error) {
      setTradeMessage({
        text: `네트워크 오류가 발생했습니다: ${error.message}`,
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
  const overallFeedStatus = getOverallFeedStatus()
  const isOrderBlocked = brokerEnv === 'REAL' && (
    orderPrecheck?.exceeds_real_order_limit ||
    orderPrecheck?.insufficient_cash ||
    orderPrecheck?.insufficient_holding
  )

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
              {displayName !== symbol ? `${displayName} (${symbol})` : symbol} <span className="text-xs text-slate-400 font-normal">({resolvedAssetType === 'STOCK' ? '주식' : '가상자산'})</span>
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
                {getCurrencySign()}{currentPrice.toLocaleString(undefined, { maximumFractionDigits: getCurrencyDigits() })}
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
          
          {/* [1열: 좌측 - 차트 및 요약 뉴스 탭 (6/12 cols)] */}
          <div className={`${showLevel2Panel ? 'lg:col-span-6' : 'lg:col-span-9'} flex flex-col gap-5`}>
            
            {/* 차트 카드 */}
            <div className="bg-[#0e1529]/90 border border-[#1f2945] rounded-xl p-4 flex flex-col gap-4 backdrop-blur-md">
              <div className="flex flex-col gap-3 sm:flex-row sm:justify-between sm:items-center">
                <div className="flex flex-col gap-1">
                  <div className="flex items-center gap-2">
                    <span className="w-1.5 h-3 bg-cyan-400 rounded-full" />
                    <span className="text-xs font-bold text-white">실시간 통합 차트</span>
                  </div>
                  <p className="text-[10px] text-slate-500 font-mono">
                    마지막 차트 확인 {formatTimestamp(marketFeeds.candles.checkedAt)}
                  </p>
                </div>
                
                {/* 캔들 주기 변경 탭 */}
                <div className="flex flex-wrap gap-1 bg-[#1b253b] p-0.5 rounded border border-[#2b395b] max-w-[70%] sm:max-w-none justify-end">
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
              </div>

              {/* 차트 영역 */}
              <div className="w-full relative min-h-[460px] bg-[#0e1529] rounded-lg overflow-hidden border border-[#1f2945]/60">
                {loadingChart && (
                  <div className="absolute inset-0 flex items-center justify-center bg-[#0e1529]/95 z-10 rounded">
                    <span className="text-xs text-cyan-400 font-mono animate-pulse">시세 차트 로드 중...</span>
                  </div>
                )}
                <div ref={chartContainerRef} className="w-full" />
              </div>
            </div>

            {/* 하단 RAG 뉴스 / 종목 정보 탭 카드 */}
            <div className="bg-[#0e1529]/90 border border-[#1f2945] rounded-xl p-5 backdrop-blur-md">
              <div className="flex border-b border-[#1f2945] pb-2 mb-4">
                {[
                  { id: 'news', label: '뉴스 및 공시' },
                  { id: 'community', label: '토론(커뮤니티)' }
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
                <div className="flex flex-col gap-4 max-h-[220px] overflow-y-auto pr-1">
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
                    <div className="py-8 text-center text-xs text-slate-500 font-mono">
                      해당 종목의 실시간 수집 뉴스가 존재하지 않습니다.
                    </div>
                  )}
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

          {/* [3열: 우측 - 주문 패널 & 내 보유 주식 (3/12 cols)] */}
          <div className={`${showLevel2Panel ? 'lg:col-span-3' : 'lg:col-span-3'} flex flex-col gap-5`}>

            {/* AI 시그널 카드 */}
            <div className="bg-[#0e1529]/90 border border-cyan-500/30 rounded-xl p-4 flex flex-col gap-3 backdrop-blur-md">
              <div className="flex items-start justify-between gap-3 border-b border-[#1f2945] pb-2">
                <div>
                  <span className="text-[10px] font-bold uppercase tracking-[0.16em] text-cyan-300">AI Signal</span>
                  <h2 className="mt-1 text-xs font-bold text-white">ML 참고 신호</h2>
                </div>
                <button
                  type="button"
                  onClick={fetchMlSignal}
                  disabled={mlSignalLoading}
                  className="rounded border border-cyan-500/30 px-2 py-1 text-[10px] font-bold text-cyan-300 transition hover:bg-cyan-950/30 disabled:opacity-50"
                >
                  {mlSignalLoading ? '조회 중' : '갱신'}
                </button>
              </div>

              {mlSignalLoading ? (
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

              {/* 매수/매도 토스형 2분할 버튼 */}
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
                      onChange={() => setOrderType('MARKET')}
                      className="accent-cyan-400"
                    />
                    시장가
                  </label>
                </div>
              </div>

              {/* 주문 제출 폼 */}
              <form onSubmit={handlePlaceOrder} className="flex flex-col gap-4">
                {/* 1. 가격 입력 */}
                <div className="flex flex-col gap-1.5">
                  <span className="text-[10px] text-slate-400 font-bold">주문 단가 ({resolvedAssetType === 'STOCK' ? 'KRW' : 'USD'})</span>
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
                    <div className="grid grid-cols-2 gap-1 bg-[#070b19] p-0.5 rounded border border-[#1f2945]">
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
                        바이낸스
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
                          {getCurrencySign()}{Number(orderPrecheck.reference_price || 0).toLocaleString(undefined, { maximumFractionDigits: getCurrencyDigits() })}
                        </span>
                      </div>
                      <div className="flex justify-between text-slate-300">
                        <span>금액 산정 기준</span>
                        <span className="text-white">{orderPrecheck.price_source}</span>
                      </div>
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
                {side === 'BUY' && (
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
                          현재 구현은 주문 체결 확정 이후가 아니라 주문 전송 성공 직후 감시 규칙을 등록합니다.
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
                  <div className={`p-2.5 rounded text-xs font-bold leading-relaxed border ${tradeMessage.isError ? 'bg-red-950/40 text-red-400 border-red-900/60' : 'bg-green-950/40 text-green-400 border-green-900/60'}`}>
                    {tradeMessage.text}
                  </div>
                )}

                {/* 주문 제출 버튼 */}
                <button
                  type="submit"
                  disabled={submitting || precheckLoading || isOrderBlocked}
                  className={`w-full py-2.5 rounded font-black text-[#070b19] text-xs tracking-wider transition-all active:scale-[0.98] cursor-pointer disabled:opacity-50 ${side === 'BUY' ? 'bg-[#ef4444] text-white hover:bg-red-600' : 'bg-[#3b82f6] text-white hover:bg-blue-600'}`}
                >
                  {submitting ? '주문 전송 중...' : `${side === 'BUY' ? '구매' : '판매'}하기`}
                </button>
              </form>
            </div>

            {/* 내 보유 주식 카드 (토스 WTS 스타일) */}
            <div className="bg-[#0e1529]/90 border border-[#1f2945] rounded-xl p-4 flex flex-col gap-3 backdrop-blur-md font-mono">
              <div className="flex items-center gap-2 border-b border-[#1f2945] pb-2">
                <span className="w-1.5 h-3 bg-cyan-400 rounded-full" />
                <span className="text-xs font-bold text-white">내 보유 현황</span>
              </div>

              {myHolding && myHolding.qty > 0 ? (
                <div className="flex flex-col gap-2.5 text-xs">
                  <div className="flex justify-between border-b border-[#1f2945]/30 py-1">
                    <span className="text-slate-400">보유 수량</span>
                    <span className="text-white font-bold">{myHolding.qty.toLocaleString()} 주</span>
                  </div>
                  <div className="flex justify-between border-b border-[#1f2945]/30 py-1">
                    <span className="text-slate-400">평균 단가</span>
                    <span className="text-white font-bold">
                      {getCurrencySign()}{myHolding.avg_price.toLocaleString(undefined, { maximumFractionDigits: getCurrencyDigits() })}
                    </span>
                  </div>
                  <div className="flex justify-between border-b border-[#1f2945]/30 py-1">
                    <span className="text-slate-400">현재 평가금</span>
                    <span className="text-white font-bold">
                      {getCurrencySign()}{(myHolding.current_price * myHolding.qty).toLocaleString(undefined, { maximumFractionDigits: getCurrencyDigits() })}
                    </span>
                  </div>
                  <div className="flex justify-between py-1 font-bold">
                    <span className="text-slate-400">평가 손익</span>
                    <span className={myHolding.profit >= 0 ? 'text-[#ef4444]' : 'text-[#3b82f6]'}>
                      {myHolding.profit >= 0 ? '+' : ''}{myHolding.profit.toLocaleString()} ({myHolding.profit_rate.toFixed(2)}%)
                    </span>
                  </div>
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
