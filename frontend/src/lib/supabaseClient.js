const SUPABASE_URL = import.meta.env.VITE_SUPABASE_URL || ''
const SUPABASE_ANON_KEY = import.meta.env.VITE_SUPABASE_ANON_KEY || ''
const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:5050'

function buildHeaders() {
  return {
    apikey: SUPABASE_ANON_KEY,
    Authorization: `Bearer ${SUPABASE_ANON_KEY}`,
    'Content-Type': 'application/json',
  }
}

export async function fetchNewsArticles({ market = 'ALL', category = 'ALL', query = '', limit = 20, offset = 0 }) {
  if (!SUPABASE_URL || !SUPABASE_ANON_KEY) {
    throw new Error('Missing Supabase environment variables.')
  }

  const params = new URLSearchParams({
    select: 'id,market,source,source_article_id,title,summary,url,published_at,fetched_at,company_name,symbol,language,sentiment,content_hash,is_active,raw_payload,ai_summary,ai_summary_model,ai_summary_generated_at,ai_summary_prompt_version',
    order: 'published_at.desc',
    limit: String(limit),
    offset: String(offset),
    is_active: 'eq.true',
  })

  if (market && market !== 'ALL') {
    params.set('market', `eq.${market}`)
  }

  if (category === 'symbol') {
    params.set('symbol', 'not.eq.')
  } else if (category && category !== 'ALL') {
    params.set('raw_payload->>query_category', `eq.${category}`)
  }

  if (query.trim()) {
    const q = query.trim().replace(/%/g, '\\%').replace(/,/g, ' ')
    params.set(
      'or',
      `(title.ilike.%${q}%,summary.ilike.%${q}%,company_name.ilike.%${q}%,symbol.ilike.%${q}%)`,
    )
  }

  const headers = {
    ...buildHeaders(),
    Prefer: 'count=exact',
  }

  const response = await fetch(`${SUPABASE_URL}/rest/v1/news_articles?${params.toString()}`, {
    headers,
  })

  if (!response.ok) {
    throw new Error(`Supabase news query failed: ${response.status} ${response.statusText}`)
  }

  const data = await response.json()
  const contentRange = response.headers.get('content-range')
  let count = 0

  if (contentRange) {
    const [, total] = contentRange.split('/')
    count = Number(total) || data.length
  } else {
    count = data.length
  }

  return {
    items: Array.isArray(data) ? data : [],
    totalCount: count,
  }
}

export async function ensureNewsSummaries({ articleIds = [] }) {
  if (!Array.isArray(articleIds) || articleIds.length === 0) {
    return { items: [], generatedCount: 0 }
  }

  const response = await fetch(`${API_BASE_URL}/api/news/summaries/ensure`, {
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

