export const ACTIONABLE_ORDER_STATUSES = [
  'PENDING',
  'APPROVED',
  'ORDERED',
  'OPEN',
  'PARTIALLY_FILLED',
  'MODIFIED',
]

export const STOCK_WARNING_BADGE_META = {
  TRADING_SUSPENDED: {
    tone: 'border-rose-500/50 bg-rose-500/15 text-rose-200',
  },
  LIQUIDATION_TRADING: {
    tone: 'border-rose-500/40 bg-rose-500/12 text-rose-300',
  },
  INVESTMENT_RISK: {
    tone: 'border-orange-500/40 bg-orange-500/12 text-orange-300',
  },
  INVESTMENT_WARNING: {
    tone: 'border-amber-500/40 bg-amber-500/12 text-amber-300',
  },
  OVERHEATED: {
    tone: 'border-yellow-500/40 bg-yellow-500/12 text-yellow-200',
  },
  VI_STATIC_AND_DYNAMIC: {
    tone: 'border-sky-500/40 bg-sky-500/12 text-sky-300',
  },
  VI_STATIC: {
    tone: 'border-sky-500/40 bg-sky-500/12 text-sky-300',
  },
  VI_DYNAMIC: {
    tone: 'border-sky-500/40 bg-sky-500/12 text-sky-300',
  },
  STOCK_WARRANTS: {
    tone: 'border-fuchsia-500/40 bg-fuchsia-500/12 text-fuchsia-300',
  },
}

export const normalizeStockSymbol = (value) => String(value || '').trim().toUpperCase()

export const isDomesticStockSymbol = (value) => /^\d{6}$/.test(normalizeStockSymbol(value))

export const isUsStockSymbol = (value, market = '') => {
  const normalizedMarket = String(market || '').trim().toUpperCase()
  if (['KR', 'KOSPI', 'KOSDAQ', 'KONEX', '국내'].includes(normalizedMarket)) return false
  if (['US', 'USA', 'NASDAQ', 'NYSE', 'AMEX'].includes(normalizedMarket)) return true
  return !isDomesticStockSymbol(value)
}

export const getAssetCurrencySign = ({ exchange = '', assetType = '', isUsStock = false } = {}) => {
  const normalizedExchange = String(exchange || '').toUpperCase()
  const normalizedAssetType = String(assetType || '').toUpperCase()

  if (normalizedExchange === 'COINONE') return '₩'
  if (normalizedExchange === 'BINANCE' || normalizedExchange === 'BINANCE_UM_FUTURES') return '$'
  if (normalizedAssetType === 'STOCK') return isUsStock ? '$' : '₩'
  return '$'
}

export const getAssetCurrencyDigits = ({ exchange = '', assetType = '', isUsStock = false } = {}) => {
  const normalizedExchange = String(exchange || '').toUpperCase()
  const normalizedAssetType = String(assetType || '').toUpperCase()

  if (normalizedExchange === 'COINONE') return 0
  if (normalizedExchange === 'BINANCE' || normalizedExchange === 'BINANCE_UM_FUTURES') return 6
  if (normalizedAssetType === 'STOCK') return isUsStock ? 4 : 0
  return 4
}

export const getAssetPriceDigits = (value, context = {}) => {
  const numeric = Math.abs(Number(value))
  if (!Number.isFinite(numeric)) return getAssetCurrencyDigits(context)

  const normalizedExchange = String(context.exchange || '').toUpperCase()
  if (normalizedExchange === 'COINONE') {
    return numeric > 0 && numeric < 1 ? 4 : 0
  }
  if (normalizedExchange === 'BINANCE' || normalizedExchange === 'BINANCE_UM_FUTURES') {
    if (numeric > 0 && numeric < 0.01) return 8
    if (numeric > 0 && numeric < 1) return 6
    if (numeric < 100) return 4
    return 4
  }
  if (context.isUsStock) {
    if (numeric > 0 && numeric < 1) return 6
    return 4
  }
  return getAssetCurrencyDigits(context)
}

export const getAssetChartPriceFormat = (value, context = {}) => {
  const digits = getAssetPriceDigits(value || context.currentPrice, context)
  return {
    type: 'price',
    precision: digits,
    minMove: 1 / (10 ** digits),
  }
}

export const isActionableOrderStatus = (status) => (
  ACTIONABLE_ORDER_STATUSES.includes(String(status || '').toUpperCase())
)

export const isCancelReplaceExchange = (exchange) => (
  ['COINONE', 'BINANCE', 'BINANCE_UM_FUTURES'].includes(String(exchange || '').toUpperCase())
)

const normalizeExchangeList = (values = []) => (
  Array.isArray(values)
    ? values.map((value) => String(value || '').trim().toUpperCase()).filter(Boolean)
    : []
)

const hasBooleanExchangeMetadata = (metadata = {}) => (
  ['coinone_listed', 'coinone_tradable', 'binance_listed', 'binance_tradable']
    .some((key) => typeof metadata[key] === 'boolean')
)

export const getSupportedCryptoOrderExchanges = (metadata = {}) => {
  if (!metadata || typeof metadata !== 'object') return []

  if (hasBooleanExchangeMetadata(metadata)) {
    const supported = []
    if (metadata.coinone_listed === true && metadata.coinone_tradable === true) {
      supported.push('COINONE')
    }
    if (metadata.binance_listed === true && metadata.binance_tradable === true) {
      supported.push('BINANCE', 'BINANCE_UM_FUTURES')
    }
    return supported
  }

  const legacyOptions = normalizeExchangeList(metadata.exchange_options?.length ? metadata.exchange_options : metadata.exchanges)
  const supported = []
  if (legacyOptions.includes('COINONE')) supported.push('COINONE')
  if (legacyOptions.includes('BINANCE') || legacyOptions.includes('BINANCE_UM_FUTURES')) {
    supported.push('BINANCE', 'BINANCE_UM_FUTURES')
  }
  return [...new Set(supported)]
}

export const getOrderEntryAssetType = (exchange = '') => {
  const normalizedExchange = String(exchange || '').toUpperCase()
  if (normalizedExchange === 'TOSS' || normalizedExchange === 'KIS') return 'STOCK'
  if (normalizedExchange === 'BINANCE_UM_FUTURES') return 'CRYPTO_FUTURES'
  return 'CRYPTO_SPOT'
}

export const findTradableOrderAccount = (accounts = [], exchange = '', brokerEnv = '') => {
  const normalizedExchange = String(exchange || '').toUpperCase()
  const normalizedBrokerEnv = String(brokerEnv || '').toUpperCase()
  const expectedAssetType = getOrderEntryAssetType(normalizedExchange)
  if (!Array.isArray(accounts) || !normalizedExchange || !normalizedBrokerEnv) return null

  return accounts.find((account) => (
    String(account?.exchange || '').toUpperCase() === normalizedExchange
    && String(account?.asset_type || '').toUpperCase() === expectedAssetType
    && String(account?.broker_env || '').toUpperCase() === normalizedBrokerEnv
    && account?.trade_enabled !== false
    && String(account?.id || '').trim()
  )) || null
}

export const getStockWarningBadgeTone = (warningType) => (
  STOCK_WARNING_BADGE_META[String(warningType || '').toUpperCase()]?.tone
  || 'border-slate-600 bg-slate-800/70 text-slate-200'
)

export const getOrderStatusLabel = (status) => {
  const normalized = String(status || '').toUpperCase()
  if (['PENDING', 'OPEN', 'PARTIALLY_FILLED', 'MODIFIED'].includes(normalized)) return '미체결'
  if (['APPROVED', 'ORDERED'].includes(normalized)) return '접수 완료'
  if (normalized === 'EXECUTED') return '체결완료'
  if (['CANCELED', 'CANCELLED'].includes(normalized)) return '취소완료'
  if (['FAILED', 'REJECTED', 'EXPIRED'].includes(normalized)) return '실패'
  return normalized || '-'
}

export const getOrderSideLabel = (side) => (
  String(side || '').toUpperCase() === 'SELL' ? '매도' : '매수'
)

export const getAutoRuleStatusLabel = (status) => {
  const normalized = String(status || '').toUpperCase()
  if (normalized === 'RUNNING') return '감시 중'
  if (normalized === 'COMPLETED') return '완료'
  if (normalized === 'STOPPED') return '정지'
  return normalized || '-'
}

export const getAutoExecutionModeLabel = (mode) => {
  const normalized = String(mode || '').toUpperCase()
  if (normalized === 'AUTO') return '조건 도달 시 자동 매도'
  return '조건 도달 시 매도 제안'
}

export const getAutoTriggerLabel = (triggerSide) => {
  const normalized = String(triggerSide || '').toUpperCase()
  if (normalized === 'TAKE_PROFIT') return '익절 도달'
  if (normalized === 'STOP_LOSS') return '손절 도달'
  return '아직 미도달'
}

export const formatRelativeTime = (isoString, now = new Date()) => {
  if (!isoString) return ''
  try {
    const date = new Date(isoString)
    const diffMs = now - date
    const diffMins = Math.floor(diffMs / 60000)
    if (diffMins < 1) return '방금 전'
    if (diffMins < 60) return `${diffMins}분 전`
    const diffHours = Math.floor(diffMins / 60)
    if (diffHours < 24) return `${diffHours}시간 전`
    return date.toLocaleDateString()
  } catch {
    return ''
  }
}

export const formatNewsSource = (source) => {
  const normalized = String(source || '').trim().toUpperCase()
  if (normalized === 'NAVER') return '네이버'
  if (normalized === 'FINNHUB') return 'Finnhub'
  return source || 'NEWS'
}

export const sortNewsByPublishedAtDesc = (items = []) => {
  return [...items].sort((left, right) => {
    const rightTime = new Date(right?.published_at || 0).getTime()
    const leftTime = new Date(left?.published_at || 0).getTime()
    return (Number.isFinite(rightTime) ? rightTime : 0) - (Number.isFinite(leftTime) ? leftTime : 0)
  })
}

export const getNewsSyncMessage = (visibleCount) => {
  const count = Number(visibleCount)
  if (Number.isFinite(count) && count > 0) {
    return `최근 7일 이내 투자 관련 뉴스 ${count}건을 확인했습니다.`
  }
  return '최근 7일 이내 투자 관련 뉴스가 없습니다.'
}

export const formatDisclosureDate = (value) => {
  const text = String(value || '').trim()
  if (/^\d{8}$/.test(text)) {
    return `${text.slice(0, 4)}.${text.slice(4, 6)}.${text.slice(6, 8)}`
  }
  return text || '-'
}

export const getDisclosureToneClass = (sentiment) => {
  if (sentiment === 'positive') return 'border-emerald-400/35 bg-emerald-500/10 text-emerald-200'
  if (sentiment === 'negative') return 'border-rose-400/35 bg-rose-500/10 text-rose-200'
  if (sentiment === 'caution') return 'border-amber-400/35 bg-amber-500/10 text-amber-200'
  return 'border-cyan-400/25 bg-cyan-500/10 text-cyan-100'
}

export const formatTimestamp = (value) => {
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

export const formatProbability = (value) => {
  if (value === null || value === undefined || value === '') return '-'
  const numberValue = Number(value)
  if (Number.isNaN(numberValue)) return '-'
  return `${(numberValue * 100).toFixed(1)}%`
}

export const formatSignalScore = (value) => {
  if (value === null || value === undefined || value === '') return '-'
  const numberValue = Number(value)
  if (Number.isNaN(numberValue)) return '-'
  return numberValue.toFixed(2)
}

export const formatStaleness = (minutes) => {
  if (minutes === null || minutes === undefined || Number.isNaN(Number(minutes))) return '-'
  const numericMinutes = Number(minutes)
  if (numericMinutes < 60) return `${numericMinutes}분 전`
  if (numericMinutes < 1440) return `${Math.floor(numericMinutes / 60)}시간 전`
  return `${Math.floor(numericMinutes / 1440)}일 전`
}

export const getProbabilityLevel = (value, type = 'up') => {
  const numberValue = Number(value)
  if (Number.isNaN(numberValue)) return { label: '확인 전', tone: 'text-slate-300', detail: '아직 판단할 수 있는 신호가 없습니다.' }
  if (type === 'risk') {
    if (numberValue >= 0.6) return { label: '높음', tone: 'text-rose-300', detail: '하락 위험을 먼저 확인해야 합니다.' }
    if (numberValue >= 0.4) return { label: '보통', tone: 'text-amber-300', detail: '손실 가능성을 함께 봐야 합니다.' }
    return { label: '낮음', tone: 'text-emerald-300', detail: '급락 위험 신호는 크지 않습니다.' }
  }
  if (numberValue >= 0.65) return { label: '강함', tone: 'text-emerald-300', detail: '상승 쪽 신호가 비교적 뚜렷합니다.' }
  if (numberValue >= 0.55) return { label: '우세', tone: 'text-cyan-300', detail: '상승 쪽 신호가 약간 우세합니다.' }
  if (numberValue >= 0.45) return { label: '중립', tone: 'text-slate-300', detail: '방향성이 뚜렷하지 않습니다.' }
  return { label: '약함', tone: 'text-amber-300', detail: '상승 신호가 약합니다.' }
}

export const getSignalGradeLabel = (grade) => {
  if (grade === 'STRONG_BUY_CANDIDATE') return '강한 후보'
  if (grade === 'WATCH') return '관찰'
  if (grade === 'RISKY') return '위험'
  if (grade === 'NO_SIGNAL') return '신호 없음'
  return grade || '미분류'
}

export const getSignalGradeTone = (grade) => {
  if (grade === 'STRONG_BUY_CANDIDATE') return 'border-emerald-500/50 bg-emerald-950/40 text-emerald-300'
  if (grade === 'WATCH') return 'border-cyan-500/50 bg-cyan-950/30 text-cyan-300'
  if (grade === 'RISKY') return 'border-rose-500/50 bg-rose-950/40 text-rose-300'
  return 'border-slate-700 bg-slate-900/70 text-slate-400'
}

export const getPolicyReasonLabel = (reason) => {
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

export const getPolicyReasonLabels = (signal) => {
  if (!signal) return []
  if (Array.isArray(signal.policy_block_reason_labels) && signal.policy_block_reason_labels.length > 0) {
    return signal.policy_block_reason_labels
  }
  return String(signal.policy_block_reason || '')
    .split('|')
    .map((item) => item.trim())
    .filter(Boolean)
    .map(getPolicyReasonLabel)
}

export const formatDecimalMetric = (value, digits = 2) => {
  if (value === null || value === undefined || value === '') return '-'
  const numberValue = Number(value)
  if (Number.isNaN(numberValue)) return '-'
  return numberValue.toFixed(digits)
}

export const formatRatio = (value) => {
  if (value === null || value === undefined || value === '') return '-'
  const numberValue = Number(value)
  if (Number.isNaN(numberValue)) return '-'
  return `${numberValue.toFixed(2)}x`
}

export const formatMetric = (value, digits = 4) => formatDecimalMetric(value, digits)

export const formatPercent = (value, digits = 1) => {
  if (value === null || value === undefined || value === '') return '-'
  const numberValue = Number(value)
  if (Number.isNaN(numberValue)) return '-'
  return `${(numberValue * 100).toFixed(digits)}%`
}

export const formatReturnPercent = (value, digits = 2) => {
  if (value === null || value === undefined || value === '') return '-'
  const numberValue = Number(value)
  if (Number.isNaN(numberValue)) return '-'
  return `${(numberValue * 100).toFixed(digits)}%`
}

export const formatSignedPercentValue = (value, digits = 2) => {
  if (value === null || value === undefined || value === '') return '-'
  const numberValue = Number(value)
  if (Number.isNaN(numberValue)) return '-'
  const sign = numberValue > 0 ? '+' : ''
  return `${sign}${numberValue.toFixed(digits)}%`
}

export const normalizeCandleTime = (rawTime) => {
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

export const buildCandleSignature = (items = []) => {
  if (!items.length) return ''
  const lastItem = items[items.length - 1]
  return `${items.length}:${lastItem.time}:${lastItem.close}:${lastItem.volume}`
}
