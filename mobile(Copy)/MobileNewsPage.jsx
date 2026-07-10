import { useCallback, useEffect, useMemo, useState } from 'react'
import Header from '../../components/Header.jsx'
import { ensureNewsSummaries, fetchNewsArticles } from '../../lib/supabaseClient.js'

const PAGE_SIZE = 10

const marketOptions = [
  { value: 'ALL', label: '전체' },
  { value: 'DOMESTIC', label: '국내' },
  { value: 'GLOBAL', label: '해외' },
]

const categoryOptions = [
  { value: 'ALL', label: '전체 카테고리' },
  { value: 'market', label: '시장' },
  { value: 'macro', label: '매크로' },
  { value: 'sentiment', label: '수급/심리' },
  { value: 'sector', label: '섹터' },
  { value: 'symbol', label: '종목' },
]

const categoryGuide = [
  {
    key: 'market',
    title: '시장',
    description: '코스피, 코스닥, 증시, 환율, 금리 흐름입니다.',
  },
  {
    key: 'macro',
    title: '매크로',
    description: '인플레이션, FOMC, 연준, 미국 국채 이슈입니다.',
  },
  {
    key: 'sentiment',
    title: '수급/심리',
    description: '외국인·기관 수급, 공매도, 신용융자 이슈입니다.',
  },
  {
    key: 'sector',
    title: '섹터',
    description: '반도체, 이차전지, 바이오, AI 같은 업종 흐름입니다.',
  },
  {
    key: 'symbol',
    title: '종목',
    description: '현재는 AAPL, MSFT, NVDA 관련 기사 위주입니다.',
  },
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

function getCategoryLabel(item) {
  const category = item.raw_payload?.query_category
  if (!category && item.symbol) return '종목'
  return categoryOptions.find((option) => option.value === category)?.label || '일반'
}

export default function News({ isLoggedIn, userEmail, handleLogout, hideHeader = false, maxVisiblePages = 9, mobileLayout = false }) {
  const [newsMarket, setNewsMarket] = useState('ALL')
  const [newsCategory, setNewsCategory] = useState('ALL')
  const [newsQuery, setNewsQuery] = useState('')
  const [newsItems, setNewsItems] = useState([])
  const [newsLoading, setNewsLoading] = useState(false)
  const [newsError, setNewsError] = useState('')
  const [expandedNews, setExpandedNews] = useState(null)
  const [isCategoryGuideOpen, setIsCategoryGuideOpen] = useState(true)
  const [summaryLoadingId, setSummaryLoadingId] = useState('')
  const [lastFetchedAt, setLastFetchedAt] = useState('')
  const [page, setPage] = useState(1)
  const [totalCount, setTotalCount] = useState(0)

  const totalPages = useMemo(() => Math.max(1, Math.ceil(totalCount / PAGE_SIZE)), [totalCount])

  const pageNumbers = useMemo(() => {
    const maxVisible = maxVisiblePages
    let start = Math.max(1, page - Math.floor(maxVisible / 2))
    let end = start + maxVisible - 1

    if (end > totalPages) {
      end = totalPages
      start = Math.max(1, end - maxVisible + 1)
    }

    const numbers = []
    for (let i = start; i <= end; i += 1) {
      numbers.push(i)
    }
    return numbers
  }, [maxVisiblePages, page, totalPages])

  const loadNews = useCallback(async () => {
    setNewsLoading(true)
    setNewsError('')

    try {
      const res = await fetchNewsArticles({
        market: newsMarket,
        category: newsCategory,
        query: newsQuery,
        limit: PAGE_SIZE,
        offset: (page - 1) * PAGE_SIZE,
      })

      const items = res?.items || []
      setNewsItems(items)
      setTotalCount(res?.totalCount || 0)
      setLastFetchedAt(items?.[0]?.fetched_at || '')
    } catch (error) {
      setNewsError(error.message)
    } finally {
      setNewsLoading(false)
    }
  }, [newsCategory, newsMarket, newsQuery, page])

  useEffect(() => {
    loadNews()
  }, [loadNews])

  const handleSummaryToggle = useCallback(
    async (item) => {
      const isExpanded = expandedNews === item.id
      if (isExpanded) {
        setExpandedNews(null)
        return
      }

      setExpandedNews(item.id)

      if (item.ai_summary) {
        return
      }

      setSummaryLoadingId(item.id)
      try {
        const summaryResult = await ensureNewsSummaries({ articleIds: [item.id] })
        const summaryItem = summaryResult.items?.[0]

        if (summaryItem?.ai_summary) {
          setNewsItems((prevItems) =>
            prevItems.map((newsItem) =>
              newsItem.id === item.id
                ? {
                    ...newsItem,
                    ai_summary: summaryItem.ai_summary,
                    ai_summary_model: summaryItem.ai_summary_model,
                    ai_summary_generated_at: summaryItem.ai_summary_generated_at,
                    ai_summary_prompt_version: summaryItem.ai_summary_prompt_version,
                  }
                : newsItem,
            ),
          )
        }
      } catch (error) {
        setNewsError(error.message)
      } finally {
        setSummaryLoadingId('')
      }
    },
    [expandedNews],
  )

  return (
    <div className={`min-h-screen bg-obsidian-bg font-inter text-[#e2e2ec] ${mobileLayout ? 'px-0 py-0' : 'px-4 py-6 sm:px-6 sm:py-8'}`}>
      {!hideHeader ? <Header isLoggedIn={isLoggedIn} userEmail={userEmail} handleLogout={handleLogout} /> : null}

      <main className="mx-auto max-w-7xl">
        <section className="ai-glass rounded-lg p-4 sm:p-6">
          <div className="mb-5 flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
            <div>
              <h2 className="text-2xl font-bold text-white">News Board</h2>
              <p className="mt-1 text-sm text-slate-400">
                Supabase에 적재된 국내·해외 뉴스를 게시판 형태로 보여줍니다.
              </p>
            </div>

            <div className="grid grid-cols-1 gap-3 sm:grid-cols-[140px_170px_minmax(220px,1fr)]">
              <select
                value={newsMarket}
                onChange={(event) => {
                  setNewsMarket(event.target.value)
                  setPage(1)
                }}
                className="rounded border border-slate-700 bg-[#0F172A] px-3 py-2 text-sm text-white"
              >
                {marketOptions.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>

              <select
                value={newsCategory}
                onChange={(event) => {
                  setNewsCategory(event.target.value)
                  setPage(1)
                }}
                className="rounded border border-slate-700 bg-[#0F172A] px-3 py-2 text-sm text-white"
              >
                {categoryOptions.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>

              <input
                type="text"
                value={newsQuery}
                onChange={(event) => {
                  setNewsQuery(event.target.value)
                  setPage(1)
                }}
                onKeyDown={(event) => {
                  if (event.key === 'Enter') {
                    setPage(1)
                    loadNews()
                  }
                }}
                placeholder="종목명, 티커, 키워드 검색"
                className="min-w-0 rounded border border-slate-700 bg-[#0F172A] px-3 py-2 text-sm text-white"
              />
            </div>
          </div>

          <div className="mb-6 rounded-xl border border-slate-800 bg-[#0c1019]/80 p-4">
            <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
              <div>
                <h3 className="text-sm font-semibold text-white">카테고리 기준</h3>
                <p className="mt-1 text-xs text-slate-400">검색 아래에서 각 카테고리 의미를 바로 확인할 수 있습니다.</p>
              </div>
              <div className="flex items-center gap-3">
                <div className="text-[11px] text-slate-500">종목은 검색창 직접 입력이 더 정확합니다.</div>
                <button
                  type="button"
                  onClick={() => setIsCategoryGuideOpen((prev) => !prev)}
                  className="rounded border border-slate-700 px-3 py-1.5 text-[11px] text-slate-300 hover:border-ai-cyan/50 hover:text-white"
                >
                  {isCategoryGuideOpen ? '접기' : '펼치기'}
                </button>
              </div>
            </div>

            {isCategoryGuideOpen ? (
              <div className="mt-4 grid grid-cols-1 gap-3 lg:grid-cols-2 xl:grid-cols-3">
                {categoryGuide.map((item) => {
                  const isActive = newsCategory === item.key
                  return (
                    <div
                      key={item.key}
                      className={
                        isActive
                          ? 'rounded-lg border border-ai-cyan/50 bg-ai-cyan/10 p-3'
                          : 'rounded-lg border border-slate-800 bg-[#0a0d14] p-3'
                      }
                    >
                      <div className="text-sm font-semibold text-white">{item.title}</div>
                      <p className="mt-1 text-xs leading-5 text-slate-400">{item.description}</p>
                    </div>
                  )
                })}
              </div>
            ) : null}
          </div>

          <div className="mb-4 text-xs text-slate-500">
            마지막 적재: {lastFetchedAt ? formatDate(lastFetchedAt) : '아직 표시할 적재 기록이 없습니다.'}
          </div>

          {newsError ? (
            <div className="rounded border border-red-800 bg-red-950/30 p-4 text-sm text-red-300">{newsError}</div>
          ) : null}

          <div className="space-y-4">
            {newsLoading && newsItems.length === 0 ? (
              <div className="text-sm text-slate-400">뉴스를 불러오는 중입니다...</div>
            ) : null}

            {!newsLoading && newsItems.length === 0 && !newsError ? (
              <div className="text-sm text-slate-400">
                표시할 뉴스가 없습니다. 백엔드에서 `POST /api/news/sync`를 실행해 적재 상태를 확인해 주세요.
              </div>
            ) : null}

            {newsItems.map((item, index) => {
              const expanded = expandedNews === item.id
              const displaySummary = item.ai_summary || ''
              return (
                <article
                  key={`${item.url}-${index}`}
                  className="rounded-lg border border-slate-700 bg-slate-surface p-4 transition-all hover:border-ai-cyan/40 sm:p-5"
                >
                  <div className="flex flex-col gap-3">
                    <div className="flex flex-wrap items-center gap-2 text-[11px] font-semibold uppercase tracking-wider">
                      <span className="rounded border border-ai-cyan/30 px-2 py-1 text-ai-cyan">
                        {item.market === 'DOMESTIC' ? '국내' : '해외'}
                      </span>
                      <span className="rounded border border-slate-700 px-2 py-1 text-slate-300">{item.source}</span>
                      <span className="rounded border border-slate-700 px-2 py-1 text-slate-300">
                        {getCategoryLabel(item)}
                      </span>
                      {item.symbol ? (
                        <span className="rounded border border-slate-700 px-2 py-1 text-slate-300">{item.symbol}</span>
                      ) : null}
                      <span className="text-slate-500">{formatDate(item.published_at)}</span>
                    </div>

                    <div>
                      <h3 className="break-words text-lg font-bold leading-snug text-white">{item.title}</h3>
                      <p className="mt-2 break-words text-sm leading-6 text-slate-300">
                        {displaySummary || '요약 보기를 눌러 3줄 요약을 생성하세요.'}
                      </p>
                    </div>

                    <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                      <div className="break-words text-xs text-slate-500">
                        {item.company_name ? `연관 키워드: ${item.company_name}` : '연관 키워드 정보 없음'}
                      </div>
                      <div className="flex flex-wrap gap-2">
                        <button
                          onClick={() => handleSummaryToggle(item)}
                          className="rounded border border-slate-700 px-3 py-1.5 text-xs text-slate-300 hover:border-slate-500"
                        >
                          {expanded ? '접기' : summaryLoadingId === item.id ? '생성 중' : '요약 보기'}
                        </button>
                        <a
                          href={item.url}
                          target="_blank"
                          rel="noreferrer"
                          className="inline-flex items-center justify-center rounded bg-blue-600 px-3 py-1.5 text-xs font-bold text-white transition-all hover:bg-blue-700 active:scale-95"
                        >
                          원문 열기
                        </a>
                      </div>
                    </div>

                    {expanded ? (
                      <div className="mt-2 rounded border border-slate-800 bg-[#0c0e15] p-4 text-sm text-slate-300">
                        <div className="mb-1 font-semibold text-white">AI 3줄 요약</div>
                        <p className="whitespace-pre-line break-words leading-6">
                          {displaySummary || '요약 생성 중입니다.'}
                        </p>
                      </div>
                    ) : null}
                  </div>
                </article>
              )
            })}
          </div>

          <div className="mt-8 flex flex-wrap items-center justify-center gap-1.5">
            <button
              disabled={page === 1}
              onClick={() => setPage(1)}
              className="rounded border border-slate-700 px-2.5 py-1.5 text-xs text-slate-300 hover:border-slate-500 disabled:cursor-not-allowed disabled:opacity-30"
            >
              처음
            </button>
            <button
              disabled={page === 1}
              onClick={() => setPage((prev) => prev - 1)}
              className="rounded border border-slate-700 px-2.5 py-1.5 text-xs text-slate-300 hover:border-slate-500 disabled:cursor-not-allowed disabled:opacity-30"
            >
              이전
            </button>

            {pageNumbers.map((num) => (
              <button
                key={num}
                onClick={() => setPage(num)}
                className={
                  num === page
                    ? 'rounded bg-ai-cyan px-3 py-1.5 text-xs font-semibold text-black'
                    : 'rounded border border-slate-700 px-3 py-1.5 text-xs text-slate-300 hover:border-ai-cyan/50'
                }
              >
                {num}
              </button>
            ))}

            <button
              disabled={page >= totalPages}
              onClick={() => setPage((prev) => prev + 1)}
              className="rounded border border-slate-700 px-2.5 py-1.5 text-xs text-slate-300 hover:border-slate-500 disabled:cursor-not-allowed disabled:opacity-30"
            >
              다음
            </button>
            <button
              disabled={page >= totalPages}
              onClick={() => setPage(totalPages)}
              className="rounded border border-slate-700 px-2.5 py-1.5 text-xs text-slate-300 hover:border-slate-500 disabled:cursor-not-allowed disabled:opacity-30"
            >
              마지막
            </button>
          </div>
        </section>
      </main>
    </div>
  )
}
