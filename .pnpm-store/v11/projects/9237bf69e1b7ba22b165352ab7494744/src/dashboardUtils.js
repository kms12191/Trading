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
  const assetType = String(item?.assetType || item?.asset_type || '').toUpperCase()
  const market = String(item?.market || '')
  if (assetType === 'CRYPTO' || market.includes('코인')) return 'DOMESTIC'
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
