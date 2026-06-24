import { createClient } from '@supabase/supabase-js'

const supabaseUrl = import.meta.env.VITE_SUPABASE_URL
const supabaseAnonKey = import.meta.env.VITE_SUPABASE_ANON_KEY

if (!supabaseUrl || !supabaseAnonKey) {
  console.warn('Supabase 환경변수가 설정되지 않았습니다. frontend/.env 파일을 확인해 주세요.')
}

export const supabase = createClient(supabaseUrl || '', supabaseAnonKey || '')

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
