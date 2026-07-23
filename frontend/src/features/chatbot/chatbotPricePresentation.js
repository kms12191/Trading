const PRICE_SOURCES = new Set(['ASSET_PRICE', 'ASSET_PRICE_OUTLOOK'])

function normalizePriceText(value) {
  return String(value || '').replace(/\s+/g, ' ').trim()
}

function formatPrice(value, currency) {
  const number = Number(value)
  if (!Number.isFinite(number) || number <= 0) return '-'
  const normalizedCurrency = String(currency || '').toUpperCase()
  const isDollarCurrency = normalizedCurrency === 'USD' || normalizedCurrency === 'USDT'
  return new Intl.NumberFormat('ko-KR', {
    maximumFractionDigits: isDollarCurrency ? 4 : 0,
  }).format(number)
}

export function buildPricePresentation(toolResult) {
  const priceResult = toolResult?.source === 'COMPOUND_INFO' ? toolResult.price : toolResult
  if (!PRICE_SOURCES.has(priceResult?.source)) return { shouldRender: false }

  const data = priceResult || {}
  const currentPrice = Number(data.current_price)
  if (!Number.isFinite(currentPrice) || currentPrice <= 0) return { shouldRender: false }

  const currency = normalizePriceText(data.currency).toUpperCase() || 'KRW'
  const changeRate = Number(data.change_rate)
  return {
    shouldRender: true,
    symbol: normalizePriceText(data.symbol),
    displayName: normalizePriceText(data.display_name),
    currency,
    priceText: formatPrice(currentPrice, currency),
    changeRateText: Number.isFinite(changeRate) ? `${changeRate >= 0 ? '+' : ''}${changeRate.toFixed(2)}%` : '-',
    changeTone: changeRate > 0 ? 'positive' : changeRate < 0 ? 'negative' : 'neutral',
  }
}
