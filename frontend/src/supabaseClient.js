import { createClient } from '@supabase/supabase-js'

const supabaseUrl = import.meta.env.VITE_SUPABASE_URL
const supabaseAnonKey = import.meta.env.VITE_SUPABASE_ANON_KEY

if (!supabaseUrl || !supabaseAnonKey) {
  console.warn('Supabase 환경변수가 설정되지 않았습니다. frontend/.env 파일을 확인해 주세요.')
}

export const supabase = createClient(supabaseUrl || '', supabaseAnonKey || '')

function parseWatchNumber(value) {
  if (typeof value === 'number') return Number.isFinite(value) ? value : null
  const normalized = String(value ?? '').replace(/,/g, '').replace(/[^0-9.-]/g, '')
  const numeric = Number(normalized)
  return Number.isFinite(numeric) ? numeric : null
}

export function normalizeWatchlistItem(row = {}) {
  const symbol = String(row.symbol || row.code || row.id || '').trim().toUpperCase()
  const assetType = String(row.asset_type || row.assetType || 'STOCK').toUpperCase() === 'CRYPTO' ? 'CRYPTO' : 'STOCK'
  const exchange = String(row.exchange || (assetType === 'CRYPTO' ? 'COINONE' : (/^\d{6}$/.test(symbol) ? 'KIS' : 'TOSS'))).toUpperCase()
  const marketCountry = String(row.market_country || row.marketCountry || (assetType === 'CRYPTO' ? 'KR' : (/^\d{6}$/.test(symbol) ? 'KR' : 'US'))).toUpperCase()
  const currency = String(row.currency || (assetType === 'CRYPTO' ? (exchange === 'BINANCE' ? 'USDT' : 'KRW') : (marketCountry === 'US' ? 'USD' : 'KRW'))).toUpperCase()
  const latestPrice = parseWatchNumber(row.latest_price ?? row.latestPrice ?? row.current_price ?? row.live_price ?? row.price)
  const changeRate = parseWatchNumber(row.change_rate ?? row.changeRate ?? row.live_change_rate ?? row.change)
  const averagePrice = parseWatchNumber(row.average_price ?? row.averagePrice ?? row.current_price ?? row.live_price ?? row.price)
  const quantity = parseWatchNumber(row.quantity ?? row.qty ?? 0)

  return {
    symbol,
    name: row.name || row.display_name || symbol,
    exchange,
    asset_type: assetType,
    market_country: marketCountry,
    currency,
    latest_price: latestPrice,
    change_rate: changeRate,
    average_price: averagePrice,
    quantity: quantity || 0,
    source_payload: row.source_payload || row.sourcePayload || row,
  }
}

export function toWatchlistViewItem(row = {}) {
  const item = normalizeWatchlistItem(row)
  const rawChange = Number(row.change_rate ?? item.change_rate)
  const rawAverage = Number(row.average_price ?? item.average_price ?? item.latest_price)
  const isCrypto = item.asset_type === 'CRYPTO'
  const market = isCrypto ? '코인' : item.market_country === 'US' ? '해외 주식' : '국내 주식'
  const account = item.exchange || (isCrypto ? 'COINONE' : item.market_country === 'US' ? 'TOSS' : 'KIS')

  return {
    id: item.symbol,
    name: item.name,
    market,
    account,
    exchange: item.exchange,
    assetType: item.asset_type,
    marketCountry: item.market_country,
    currency: item.currency,
    quantity: item.quantity ? `${item.quantity}` : '-',
    average: Number.isFinite(rawAverage) ? `${rawAverage}` : '-',
    change: Number.isFinite(rawChange) ? `${rawChange > 0 ? '+' : ''}${rawChange.toFixed(2)}%` : '0.00%',
    latestPrice: item.latest_price,
    sourcePayload: item.source_payload,
  }
}

export async function fetchUserWatchlist() {
  const { data: { session } } = await supabase.auth.getSession()
  if (!session?.user?.id) return []

  const { data, error } = await supabase
    .from('user_watchlist')
    .select('*')
    .eq('user_id', session.user.id)
    .order('updated_at', { ascending: false })

  if (error) throw error
  return (data || []).map(toWatchlistViewItem)
}

export async function upsertUserWatchlistItem(row) {
  const { data: { session } } = await supabase.auth.getSession()
  if (!session?.user?.id) {
    throw new Error('로그인이 필요한 서비스입니다.')
  }

  const item = normalizeWatchlistItem(row)
  if (!item.symbol) {
    throw new Error('관심종목 심볼을 확인할 수 없습니다.')
  }

  const payload = {
    ...item,
    user_id: session.user.id,
    updated_at: new Date().toISOString(),
  }

  const { data, error } = await supabase
    .from('user_watchlist')
    .upsert(payload, { onConflict: 'user_id,symbol,asset_type,exchange' })
    .select()
    .single()

  if (error) throw error
  return toWatchlistViewItem(data)
}

export async function deleteUserWatchlistItem(row) {
  const { data: { session } } = await supabase.auth.getSession()
  if (!session?.user?.id) {
    throw new Error('로그인이 필요한 서비스입니다.')
  }

  const item = normalizeWatchlistItem(row)
  const { error } = await supabase
    .from('user_watchlist')
    .delete()
    .eq('user_id', session.user.id)
    .eq('symbol', item.symbol)
    .eq('asset_type', item.asset_type)
    .eq('exchange', item.exchange)

  if (error) throw error
}

export async function fetchNewsArticles({ market, category = 'ALL', query, limit, offset }) {
  let q = supabase
    .from('news_articles')
    .select('*', { count: 'exact' })
    .order('published_at', { ascending: false })
    .range(offset, offset + limit - 1)

  if (market && market !== 'ALL') {
    q = q.eq('market', market)
  }

  if (category === 'symbol') {
    q = q.not('symbol', 'eq', '')
  } else if (category && category !== 'ALL') {
    q = q.eq('raw_payload->>query_category', category)
  }

  if (query) {
    q = q.or(
      `title.ilike.%${query}%,summary.ilike.%${query}%,company_name.ilike.%${query}%,symbol.ilike.%${query}%`,
    )
  }

  const { data, count, error } = await q

  if (error) throw error

  return {
    items: data,
    totalCount: count || 0,
  }
}

export async function ensureNewsSummaries({ articleIds = [] }) {
  const apiBaseUrl = import.meta.env.VITE_API_BASE_URL || 'http://localhost:5050'

  if (!Array.isArray(articleIds) || articleIds.length === 0) {
    return { items: [], generatedCount: 0 }
  }

  const response = await fetch(`${apiBaseUrl}/api/news/summaries/ensure`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ article_ids: articleIds }),
  })

  if (!response.ok) {
    throw new Error(`News summary request failed: ${response.status} ${response.statusText}`)
  }

  const payload = await response.json()
  return payload?.data || { items: [], generatedCount: 0 }
}
