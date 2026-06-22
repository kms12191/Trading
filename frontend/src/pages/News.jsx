import { useCallback, useEffect, useMemo, useState } from 'react'
import Header from '../components/Header.jsx'
import { fetchNewsArticles } from '../lib/supabaseClient.js'

const marketOptions = [
  { value: 'ALL', label: '전체' },
  { value: 'DOMESTIC', label: '국내' },
  { value: 'GLOBAL', label: '해외' },
]

function formatDate(value) {
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

export default function News({ currentRoute }) {
  const [newsMarket, setNewsMarket] = useState('ALL')
  const [newsQuery, setNewsQuery] = useState('')
  const [newsItems, setNewsItems] = useState([])
  const [newsLoading, setNewsLoading] = useState(false)
  const [newsError, setNewsError] = useState('')
  const [expandedNews, setExpandedNews] = useState(null)
  const [lastFetchedAt, setLastFetchedAt] = useState('')

  const loadNews = useCallback(async () => {
    setNewsLoading(true)
    setNewsError('')
    try {
      const items = await fetchNewsArticles({
        market: newsMarket,
        query: newsQuery,
        limit: 20,
        offset: 0,
      })
      setNewsItems(items || [])
      setLastFetchedAt(items?.[0]?.fetched_at || '')
    } catch (error) {
      setNewsError(error.message)
    } finally {
      setNewsLoading(false)
    }
  }, [newsMarket, newsQuery])

  useEffect(() => {
    loadNews()
  }, [loadNews])

  const newsStats = useMemo(() => {
    const domestic = newsItems.filter((item) => item.market === 'DOMESTIC').length
    const global = newsItems.filter((item) => item.market === 'GLOBAL').length
    return { domestic, global, total: newsItems.length }
  }, [newsItems])

  return (
    <div className="min-h-screen bg-obsidian-bg text-[#e2e2ec] font-inter px-6 py-8">
      <Header currentRoute={currentRoute} />

      <main className="max-w-7xl mx-auto">
        <section className="ai-glass rounded-lg p-6">
          <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between mb-5">
            <div>
              <h2 className="text-2xl font-bold text-white">News Board</h2>
              <p className="text-sm text-slate-400 mt-1">Supabase DB에서 읽어오는 게시판형 뉴스 피드입니다.</p>
            </div>

            <div className="flex flex-col sm:flex-row gap-3">
              <select
                value={newsMarket}
                onChange={(e) => setNewsMarket(e.target.value)}
                className="bg-[#0F172A] border border-slate-700 rounded px-3 py-2 text-sm text-white"
              >
                {marketOptions.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
              <input
                type="text"
                value={newsQuery}
                onChange={(e) => setNewsQuery(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') loadNews()
                }}
                placeholder="종목명 또는 티커 검색"
                className="min-w-[240px] bg-[#0F172A] border border-slate-700 rounded px-3 py-2 text-sm text-white"
              />
              <button
                onClick={loadNews}
                disabled={newsLoading}
                className="bg-ai-cyan text-black font-semibold rounded px-4 py-2 text-sm disabled:opacity-60"
              >
                {newsLoading ? 'LOADING...' : '새로고침'}
              </button>
            </div>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6">
            <div className="bg-slate-surface border border-slate-700 rounded-lg p-4">
              <div className="text-xs uppercase tracking-wider text-slate-400">Total</div>
              <div className="text-2xl font-bold text-white mt-1">{newsStats.total}</div>
            </div>
            <div className="bg-slate-surface border border-slate-700 rounded-lg p-4">
              <div className="text-xs uppercase tracking-wider text-slate-400">Domestic</div>
              <div className="text-2xl font-bold text-white mt-1">{newsStats.domestic}</div>
            </div>
            <div className="bg-slate-surface border border-slate-700 rounded-lg p-4">
              <div className="text-xs uppercase tracking-wider text-slate-400">Global</div>
              <div className="text-2xl font-bold text-white mt-1">{newsStats.global}</div>
            </div>
          </div>

          <div className="mb-4 text-xs text-slate-500">Last synced: {lastFetchedAt ? formatDate(lastFetchedAt) : 'unknown'}</div>

          {newsError ? (
            <div className="p-4 rounded border border-red-800 bg-red-950/30 text-red-300 text-sm">{newsError}</div>
          ) : null}

          <div className="space-y-4">
            {newsLoading && newsItems.length === 0 ? (
              <div className="text-sm text-slate-400">뉴스를 불러오는 중입니다...</div>
            ) : null}

            {!newsLoading && newsItems.length === 0 && !newsError ? (
              <div className="text-sm text-slate-400">표시할 뉴스가 없습니다.</div>
            ) : null}

            {newsItems.map((item, index) => {
              const expanded = expandedNews === `${item.url}-${index}`
              return (
                <article
                  key={`${item.url}-${index}`}
                  className="bg-slate-surface border border-slate-700 rounded-lg p-5 hover:border-ai-cyan/40 transition-all"
                >
                  <div className="flex flex-col gap-3">
                    <div className="flex flex-wrap items-center gap-2 text-[11px] font-semibold uppercase tracking-wider">
                      <span className="px-2 py-1 rounded border border-ai-cyan/30 text-ai-cyan">
                        {item.market === 'DOMESTIC' ? '국내' : '해외'}
                      </span>
                      <span className="px-2 py-1 rounded border border-slate-700 text-slate-300">{item.source}</span>
                      {item.symbol ? (
                        <span className="px-2 py-1 rounded border border-slate-700 text-slate-300">{item.symbol}</span>
                      ) : null}
                      <span className="text-slate-500">{formatDate(item.published_at)}</span>
                    </div>

                    <div>
                      <h3 className="text-lg font-bold text-white leading-snug">{item.title}</h3>
                      <p className="text-sm text-slate-300 mt-2 leading-6">{item.summary}</p>
                    </div>

                    <div className="flex flex-wrap items-center justify-between gap-3">
                      <div className="text-xs text-slate-500">
                        {item.company_name ? `연관 종목: ${item.company_name}` : '연관 종목 정보 없음'}
                      </div>
                      <div className="flex gap-2">
                        <button
                          onClick={() => setExpandedNews(expanded ? null : `${item.url}-${index}`)}
                          className="text-xs border border-slate-700 hover:border-slate-500 rounded px-3 py-1.5 text-slate-300"
                        >
                          {expanded ? '접기' : '요약 보기'}
                        </button>
                        <a
                          href={item.url}
                          target="_blank"
                          rel="noreferrer"
                          className="text-xs bg-ai-cyan text-black rounded px-3 py-1.5 font-semibold"
                        >
                          원문 열기
                        </a>
                      </div>
                    </div>

                    {expanded ? (
                      <div className="mt-2 p-4 rounded bg-[#0c0e15] border border-slate-800 text-sm text-slate-300">
                        <div className="font-semibold text-white mb-1">Board Preview</div>
                        <p className="leading-6">{item.summary || '게시판 카드에서 바로 읽기 좋은 요약입니다.'}</p>
                      </div>
                    ) : null}
                  </div>
                </article>
              )
            })}
          </div>
        </section>
      </main>
    </div>
  )
}
