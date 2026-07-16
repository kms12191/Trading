export const HOME_CATEGORY_TABS = [
  { key: 'domestic', label: '국내', assetType: 'STOCK', region: '국내' },
  { key: 'foreign', label: '해외', assetType: 'STOCK', region: '해외' },
  { key: 'coin', label: '코인', assetType: 'CRYPTO' },
]

export const HOME_METRIC_TABS = [
  { key: 'tradingValue', label: '거래대금', ranking: '거래대금', valueKey: 'value' },
  { key: 'volume', label: '거래량', ranking: '거래량', valueKey: 'volume' },
  { key: 'rise', label: '상승률', ranking: '상승률', valueKey: 'change' },
  { key: 'fall', label: '하락률', ranking: '하락률', valueKey: 'change' },
]

const EXPANDED_RANKING_LIMIT = 50

export const formatHomeNumber = (value, decimals = 0) => {
  const numberValue = Number(value)
  if (!Number.isFinite(numberValue)) return '-'
  return numberValue.toLocaleString('ko-KR', {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  })
}

export const isForeignHomeMarketRow = (row = {}) => {
  const marketText = String(
    row.market_segment
      ?? row.market_country
      ?? row.region
      ?? row.country
      ?? '',
  ).toUpperCase()
  const assetType = String(row.asset_type ?? row.assetType ?? '').toUpperCase()
  const symbol = String(row.symbol ?? row.code ?? row.ticker ?? '').toUpperCase()
  const explicitForeign = ['US', 'USA', 'NASDAQ', 'NYSE', 'AMEX', '해외'].some((token) => marketText.includes(token))
  return explicitForeign || (assetType === 'STOCK' && /^[A-Z.-]+$/.test(symbol))
}

export const formatHomeMarketPrice = (row = {}) => {
  if (typeof row.price === 'string' && row.price) {
    if (row.price === '-') return '-'
    if (isForeignHomeMarketRow(row)) return row.price.startsWith('$') ? row.price : `$${row.price}`
    return row.price.endsWith('원') ? row.price : `${row.price}원`
  }
  const price = row.price ?? row.current_price ?? row.live_price
  if (price === undefined || price === null || price === '') return '-'
  if (isForeignHomeMarketRow(row)) return `$${formatHomeNumber(price, Number(price) % 1 === 0 ? 0 : 1)}`
  return `${formatHomeNumber(price, Number(price) % 1 === 0 ? 0 : 1)}원`
}

export const formatChange = (row = {}) => {
  if (typeof row.change === 'string' && row.change) return row.change
  const change = Number(row.change_rate ?? row.changeRate ?? row.change_percent ?? row.changePercent ?? row.live_change_rate)
  if (!Number.isFinite(change)) return '-'
  return `${change > 0 ? '+' : ''}${change.toFixed(2)}%`
}

export const changeClass = (value) => {
  if (String(value).startsWith('+')) return 'text-red-400'
  if (String(value).startsWith('-')) return 'text-sky-400'
  return 'text-slate-400'
}

export const numericHomeMarketChange = (row = {}) => {
  const raw = row.change_rate ?? row.changeRate ?? row.change_percent ?? row.changePercent ?? row.live_change_rate ?? row.change
  const value = Number(String(raw ?? '').replace('%', '').replace('+', ''))
  return Number.isFinite(value) ? value : 0
}

export const numericHomeMarketMetric = (row = {}, metric = '거래대금') => {
  const valueKey = metric === '거래량' || metric === 'volume' ? 'volume' : metric
  if (valueKey === 'change') return numericHomeMarketChange(row)

  const raw = valueKey === 'volume' || valueKey === '거래량'
    ? row.trading_volume ?? row.volume
    : row.trading_value ?? row.value
  const text = String(raw ?? '').replace(/,/g, '').trim()
  const numberPart = Number(text.replace(/[^0-9.-]/g, ''))
  if (!Number.isFinite(numberPart)) return 0
  if (text.includes('조')) return numberPart * 1_000_000_000_000
  if (text.includes('억')) return numberPart * 100_000_000
  if (text.includes('만')) return numberPart * 10_000
  return numberPart
}

export const formatHomeMarketValue = (row = {}, valueKey = 'value', ranking = '거래대금') => {
  if (valueKey === 'change') return formatChange(row)
  if (isForeignHomeMarketRow(row) && valueKey !== 'volume' && ['상승률', '하락률'].includes(ranking)) return '-'

  const direct = valueKey === 'volume'
    ? row.trading_volume ?? row.volume
    : row.trading_value ?? row.value

  const numeric = typeof direct === 'string'
    ? Number(direct.replace(/,/g, '').replace(/[^0-9.-]/g, ''))
    : Number(direct)

  if (typeof direct === 'string' && direct && (!Number.isFinite(numeric) || /[가-힣A-Za-z]/.test(direct))) {
    return direct
  }
  if (!Number.isFinite(numeric) || numeric <= 0) return '-'
  if (valueKey === 'volume') return Math.round(numeric).toLocaleString('ko-KR')
  if (numeric >= 1_000_000_000_000) return `${(numeric / 1_000_000_000_000).toFixed(1)}조원`
  if (numeric >= 100_000_000) return `${Math.round(numeric / 100_000_000).toLocaleString('ko-KR')}억원`
  return `${Math.round(numeric).toLocaleString('ko-KR')}원`
}

export const matchesHomeMarketRegion = (row, region) => {
  if (!region) return true
  const isForeign = isForeignHomeMarketRow(row)
  return region === '해외' ? isForeign : !isForeign
}

export const applyClientMarketFilters = (rows = [], activeFilters = {}) => {
  const filtered = [...rows].filter((row) => matchesHomeMarketRegion(row, activeFilters.region))
  const ranking = activeFilters.ranking || activeFilters.metric || '거래대금'

  if (ranking === '상승률') {
    filtered.sort((a, b) => numericHomeMarketChange(b) - numericHomeMarketChange(a))
  } else if (ranking === '하락률') {
    filtered.sort((a, b) => numericHomeMarketChange(a) - numericHomeMarketChange(b))
  } else {
    filtered.sort((a, b) => numericHomeMarketMetric(b, ranking) - numericHomeMarketMetric(a, ranking))
  }

  return filtered.map((row, index) => ({ ...row, rank: index + 1 }))
}

export const getHomeRowsByCategory = ({ category = {}, metric = {}, stockRows = [], coinRows = [] } = {}) => {
  const sourceRows = category.key === 'coin'
    ? coinRows
    : stockRows.filter((row) => (category.key === 'foreign' ? isForeignHomeMarketRow(row) : !isForeignHomeMarketRow(row)))

  const sortedRows = [...sourceRows]
  if (metric.key === 'rise') {
    sortedRows.sort((a, b) => numericHomeMarketChange(b) - numericHomeMarketChange(a))
  } else if (metric.key === 'fall') {
    sortedRows.sort((a, b) => numericHomeMarketChange(a) - numericHomeMarketChange(b))
  } else {
    sortedRows.sort((a, b) => numericHomeMarketMetric(b, metric.valueKey) - numericHomeMarketMetric(a, metric.valueKey))
  }

  return sortedRows.slice(0, EXPANDED_RANKING_LIMIT).map((row, index) => ({ ...row, rank: index + 1 }))
}

export const getHomeMetricTabs = (categoryKey) => {
  if (categoryKey === 'foreign') {
    return HOME_METRIC_TABS.filter((item) => item.key !== 'tradingValue')
  }
  return HOME_METRIC_TABS
}

export const getHomeWatchlistKey = (row = {}, assetType = 'STOCK') => {
  const normalizedAssetType = String(row.asset_type || row.assetType || assetType || 'STOCK').toUpperCase()
  const symbol = String(row.symbol || row.code || row.ticker || row.id || '').toUpperCase()
  const isKoreanStock = normalizedAssetType === 'STOCK' && /^\d{6}$/.test(symbol)
  const exchange = String(
    row.exchange
    || row.account
    || (normalizedAssetType === 'CRYPTO' ? 'COINONE' : isKoreanStock ? 'KIS' : 'TOSS'),
  ).toUpperCase()
  return `${normalizedAssetType}:${exchange}:${symbol}`
}
