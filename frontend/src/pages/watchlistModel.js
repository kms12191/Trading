export const WATCHLIST_MARKET_FILTERS = [
  { key: 'all', label: '전체' },
  { key: 'domestic', label: '국내주식' },
  { key: 'overseas', label: '해외주식' },
  { key: 'crypto', label: '코인' },
]

export const STOCK_INTERVALS = [
  { label: '1분', value: '1m' },
  { label: '5분', value: '5m' },
  { label: '15분', value: '15m' },
  { label: '30분', value: '30m' },
  { label: '1시간', value: '1h' },
  { label: '일봉', value: '1d' },
  { label: '주봉', value: '1w' },
  { label: '월봉', value: '1M' },
]

export const CRYPTO_INTERVALS = [
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

export const getWatchlistMarketFilterKey = (item = {}) => {
  const assetType = String(item.assetType || item.asset_type || '').toUpperCase()
  const marketCountry = String(item.marketCountry || item.market_country || '').toUpperCase()
  const market = String(item.market || '')

  if (assetType === 'CRYPTO' || market.includes('코인')) return 'crypto'
  if (marketCountry === 'US' || market.includes('해외')) return 'overseas'
  return 'domestic'
}

export const normalizeWatchlistCandleTime = (rawTime) => {
  if (typeof rawTime === 'number' && !Number.isNaN(rawTime)) return rawTime
  if (typeof rawTime !== 'string' || !rawTime.trim()) return null

  const value = rawTime.trim()
  if (/^\d+$/.test(value)) return Number.parseInt(value, 10)
  if (/^\d{4}-\d{2}-\d{2}$/.test(value)) return value

  const parsed = new Date(value.replace(' ', 'T'))
  return Number.isNaN(parsed.getTime()) ? null : Math.floor(parsed.getTime() / 1000)
}

export const formatWatchlistCandles = (candles = []) => {
  const formatted = candles
    .map((candle) => ({
      time: normalizeWatchlistCandleTime(candle.time),
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
  return unique.reverse()
}

export const getWatchlistChartConfig = (item = {}, assetType = 'STOCK') => {
  const sourcePayload = item?.sourcePayload || {}
  const normalizedAssetType = String(assetType || '').toUpperCase()
  const exchange = String(
    item?.exchange
    || item?.account
    || sourcePayload.exchange
    || (normalizedAssetType === 'CRYPTO' ? 'COINONE' : 'TOSS'),
  ).toUpperCase()
  const brokerEnv = String(sourcePayload.broker_env || sourcePayload.env || 'REAL').toUpperCase()
  return { exchange, brokerEnv }
}

export const getCryptoWatchlistChartConfig = (chartMode = 'KRW') => {
  if (chartMode === 'USD') return { exchange: 'BINANCE', brokerEnv: 'REAL' }
  if (chartMode === 'FUTURES') return { exchange: 'BINANCE_UM_FUTURES', brokerEnv: 'REAL' }
  return { exchange: 'COINONE', brokerEnv: 'REAL' }
}

export const getWatchlistChartSymbol = (item = {}, assetType = 'STOCK', cryptoChartMode = 'KRW') => {
  const symbol = String(item?.id || item?.symbol || item?.ticker || '').trim().toUpperCase()
  if (String(assetType || '').toUpperCase() !== 'CRYPTO') return symbol
  if (cryptoChartMode === 'KRW') return symbol.replace(/(?:_?KRW|USDT)$/i, '')
  return symbol.endsWith('USDT') ? symbol : `${symbol.replace(/(?:_?KRW|USDT)$/i, '')}USDT`
}

export const getNextWatchlistSelectedId = (currentId, items = []) => {
  if (currentId && items.some((item) => item.id === currentId)) return currentId
  return items[0]?.id || ''
}
