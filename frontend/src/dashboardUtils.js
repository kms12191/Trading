import { ASSET_PERIOD_OPTIONS, ASSET_TREND_DATA } from './dashboardConstants.js'

export function toDateInputValue(date) {
  return date.toISOString().slice(0, 10)
}

export function getAssetPeriodRange(periodKey) {
  const option = ASSET_PERIOD_OPTIONS.find((item) => item.key === periodKey) || ASSET_PERIOD_OPTIONS[1]
  const end = new Date()
  const start = new Date(end)
  start.setDate(end.getDate() - option.days)

  return {
    start: toDateInputValue(start),
    end: toDateInputValue(end),
  }
}

export function getCustomTrendValues(dateRange) {
  if (!dateRange.start || !dateRange.end) return ASSET_TREND_DATA['1m'].values

  const start = new Date(dateRange.start)
  const end = new Date(dateRange.end)
  const days = Math.max(1, Math.round((end - start) / 86400000))

  if (days <= 10) return ASSET_TREND_DATA['1w'].values
  if (days <= 45) return ASSET_TREND_DATA['1m'].values
  if (days <= 140) return ASSET_TREND_DATA['3m'].values
  return ASSET_TREND_DATA['1y'].values
}

// 자산 추이 그래프 Sparkline 컴포넌트

export function formatNewsDate(value) {
  if (!value) return '-'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return new Intl.DateTimeFormat('ko-KR', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  }).format(date)
}

export function getWatchlistNewsMarket(item) {
  return /[a-zA-Z]/.test(item?.id || '') ? 'GLOBAL' : 'DOMESTIC'
}

export function mergeLatestNews(items) {
  const seen = new Set()
  return items
    .filter((item) => {
      const key = item.id || item.url || item.source_article_id || item.title
      if (!key || seen.has(key)) return false
      seen.add(key)
      return true
    })
    .sort((a, b) => new Date(b.published_at || 0) - new Date(a.published_at || 0))
    .slice(0, 4)
}
