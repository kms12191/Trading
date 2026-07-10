import { createClient } from '@supabase/supabase-js'

const viteEnv = import.meta.env || {}
const nodeEnv = typeof process !== 'undefined' ? process.env || {} : {}
const supabaseUrl = viteEnv.VITE_SUPABASE_URL || nodeEnv.VITE_SUPABASE_URL
const supabaseAnonKey = viteEnv.VITE_SUPABASE_ANON_KEY || nodeEnv.VITE_SUPABASE_ANON_KEY

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

function isKoreanStockCode(symbol) {
  return /^\d{6}$/.test(String(symbol || '').trim())
}

export function normalizeWatchlistItem(row = {}) {
  const symbol = String(row.symbol || row.code || row.id || '').trim().toUpperCase()
  const assetType = String(row.asset_type || row.assetType || 'STOCK').toUpperCase() === 'CRYPTO' ? 'CRYPTO' : 'STOCK'
  // exchange 결정: 주식이고 국내 규격이면 강제로 KIS로 보정
  let exchange = String(row.exchange || '').toUpperCase()
  if (assetType === 'CRYPTO') {
    exchange = exchange || 'COINONE'
  } else {
    if (isKoreanStockCode(symbol)) {
      exchange = 'KIS'
    } else {
      exchange = exchange || 'TOSS'
    }
  }

  // marketCountry 결정: 주식이고 국내 규격이면 강제로 KR로 보정
  let marketCountry = String(row.market_country || row.marketCountry || '').toUpperCase()
  if (assetType === 'CRYPTO') {
    marketCountry = 'KR'
  } else {
    if (isKoreanStockCode(symbol)) {
      marketCountry = 'KR'
    } else {
      marketCountry = marketCountry || 'US'
    }
  }

  // currency 결정
  let currency = String(row.currency || '').toUpperCase()
  if (assetType === 'CRYPTO') {
    currency = exchange === 'BINANCE' || exchange === 'BINANCE_UM_FUTURES' ? 'USDT' : 'KRW'
  } else {
    if (marketCountry === 'US') {
      currency = 'USD'
    } else {
      currency = 'KRW'
    }
  }
  const latestPrice = parseWatchNumber(row.latest_price ?? row.latestPrice ?? row.current_price ?? row.live_price ?? row.price)
  const changeRate = parseWatchNumber(row.change_rate ?? row.changeRate ?? row.live_change_rate ?? row.change)
  const averagePrice = parseWatchNumber(row.average_price ?? row.averagePrice ?? row.current_price ?? row.live_price ?? row.price)
  const quantity = parseWatchNumber(row.quantity ?? row.qty ?? 0)
  const sortOrder = parseWatchNumber(row.sort_order ?? row.sortOrder)

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
    sort_order: Number.isFinite(sortOrder) ? sortOrder : null,
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
    sortOrder: item.sort_order,
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
    .order('sort_order', { ascending: true, nullsFirst: false })
    .order('updated_at', { ascending: false })

  if (error) throw error
  const items = (data || []).map(toWatchlistViewItem)
  const seenCryptoSymbols = new Set()
  return items.filter((item) => {
    if (item.assetType !== 'CRYPTO') return true
    const symbol = String(item.id || '').toUpperCase()
    if (!symbol) return false
    if (seenCryptoSymbols.has(symbol)) return false
    seenCryptoSymbols.add(symbol)
    return true
  })
}

export async function upsertUserWatchlistItem(row) {
  const { data: { session } } = await supabase.auth.getSession()
  if (!session?.user?.id) {
    throw new Error('로그인이 필요한 서비스입니다.')
  }

  const item = normalizeWatchlistItem(row)
  const { count, error: countError } = await supabase
    .from('user_watchlist')
    .select('id', { count: 'exact', head: true })
    .eq('user_id', session.user.id)

  if (countError) throw countError

  if (!item.symbol) {
    throw new Error('관심종목 심볼을 확인할 수 없습니다.')
  }

  const payload = {
    ...item,
    user_id: session.user.id,
    sort_order: item.sort_order ?? (count || 0) + 1,
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

export async function updateUserWatchlistOrder(items = []) {
  const { data: { session } } = await supabase.auth.getSession()
  if (!session?.user?.id) {
    throw new Error('로그인이 필요한 서비스입니다.')
  }

  const rows = items
    .map((item, index) => {
      const normalized = normalizeWatchlistItem(item)
      return {
        user_id: session.user.id,
        symbol: normalized.symbol,
        asset_type: normalized.asset_type,
        exchange: normalized.exchange,
        sort_order: index + 1,
        updated_at: new Date().toISOString(),
      }
    })
    .filter((item) => item.symbol)

  if (rows.length === 0) return []

  const { data, error } = await supabase
    .from('user_watchlist')
    .upsert(rows, { onConflict: 'user_id,symbol,asset_type,exchange' })
    .select('*')

  if (error) throw error
  return data || []
}

export async function deleteUserWatchlistItem(row) {
  const { data: { session } } = await supabase.auth.getSession()
  if (!session?.user?.id) {
    throw new Error('로그인이 필요한 서비스입니다.')
  }

  const item = normalizeWatchlistItem(row)
  let query = supabase
    .from('user_watchlist')
    .delete()
    .eq('user_id', session.user.id)
    .eq('symbol', item.symbol)
    .eq('asset_type', item.asset_type)

  if (item.asset_type !== 'CRYPTO') {
    query = query.eq('exchange', item.exchange)
  }

  const { error } = await query

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
