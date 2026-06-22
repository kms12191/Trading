const SUPABASE_URL = import.meta.env.VITE_SUPABASE_URL || ''
const SUPABASE_ANON_KEY = import.meta.env.VITE_SUPABASE_ANON_KEY || ''

function buildHeaders() {
  return {
    apikey: SUPABASE_ANON_KEY,
    Authorization: `Bearer ${SUPABASE_ANON_KEY}`,
    'Content-Type': 'application/json',
  }
}

export async function fetchNewsArticles({ market = 'ALL', query = '', limit = 20, offset = 0 }) {
  if (!SUPABASE_URL || !SUPABASE_ANON_KEY) {
    throw new Error('Missing Supabase environment variables.')
  }

  const params = new URLSearchParams({
    select: 'id,market,source,source_article_id,title,summary,url,published_at,fetched_at,company_name,symbol,language,sentiment,content_hash,is_active',
    order: 'published_at.desc',
    limit: String(limit),
    offset: String(offset),
    is_active: 'eq.true',
  })

  if (market && market !== 'ALL') {
    params.set('market', `eq.${market}`)
  }

  if (query.trim()) {
    const q = query.trim().replace(/%/g, '\\%').replace(/,/g, ' ')
    params.set(
      'or',
      `(title.ilike.%${q}%,summary.ilike.%${q}%,company_name.ilike.%${q}%,symbol.ilike.%${q}%)`,
    )
  }

  const response = await fetch(`${SUPABASE_URL}/rest/v1/news_articles?${params.toString()}`, {
    headers: buildHeaders(),
  })

  if (!response.ok) {
    throw new Error(`Supabase news query failed: ${response.status} ${response.statusText}`)
  }

  return response.json()
}

