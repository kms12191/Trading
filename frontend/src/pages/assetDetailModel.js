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
  if (normalizedExchange === 'COINONE') return 0
  if (normalizedExchange === 'BINANCE' || normalizedExchange === 'BINANCE_UM_FUTURES') {
    if (numeric > 0 && numeric < 0.01) return 8
    if (numeric > 0 && numeric < 1) return 6
    if (numeric < 100) return 4
    return 2
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
