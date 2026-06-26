import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { fetchNewsArticles, ensureNewsSummaries } from '../lib/supabaseClient.js'
import { WATCHLIST_MOCK, WATCH_CHARTS_MOCK } from '../dashboardConstants.js'
import { MiniSparkline, Rate, SectionHeader } from '../components/DashboardComponents.jsx'
import { formatNewsDate, getWatchlistNewsMarket, mergeLatestNews } from '../dashboardUtils.js'

export default function WatchlistTab({ displayCurrency = 'KRW', exchangeRate = 1380 }) {
  const formatCurrency = (value, currency, targetDisplayCurrency = displayCurrency) => {
    const numeric = Number(value)
    const val = Number.isFinite(numeric) ? numeric : 0
    const rate = Number(exchangeRate) || 1380

    if (targetDisplayCurrency === 'KRW') {
      if (currency === 'USD' || currency === 'USDT') {
        return `₩${Math.round(val * rate).toLocaleString()}`
      }
      return `₩${Math.round(val).toLocaleString()}`
    }

    if (targetDisplayCurrency === 'USD') {
      if (currency === 'KRW') {
        return `$${(val / rate).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
      }
      return `$${val.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
    }

    if (currency === 'USD' || currency === 'USDT') {
      return `$${val.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
    }
    return `₩${Math.round(val).toLocaleString()}`
  }
  const [selectedId, setSelectedId] = useState(WATCHLIST_MOCK[0]?.id || '')
  const [newsItems, setNewsItems] = useState([])
  const [newsLoading, setNewsLoading] = useState(false)
  const [newsError, setNewsError] = useState('')
  const [expandedNewsId, setExpandedNewsId] = useState('')
  const [summaryLoadingId, setSummaryLoadingId] = useState('')

  const selectedItem = WATCHLIST_MOCK.find((item) => item.id === selectedId) || WATCHLIST_MOCK[0]
  const useSlider = WATCHLIST_MOCK.length >= 5

  const assetType = selectedItem?.account?.includes('주식') ? 'STOCK' : 'CRYPTO'

  useEffect(() => {
    if (!selectedItem) return

    let isMounted = true
    const queries = [selectedItem.id, selectedItem.name].filter(Boolean)
    const uniqueQueries = [...new Set(queries)]

    async function loadWatchlistNews() {
      setNewsLoading(true)
      setNewsError('')

      try {
        const results = await Promise.all(
          uniqueQueries.map((query) =>
            fetchNewsArticles({
              market: getWatchlistNewsMarket(selectedItem),
              query,
              limit: 4,
              offset: 0,
            }),
          ),
        )

        if (!isMounted) return
        setNewsItems(mergeLatestNews(results.flatMap((result) => result.items || [])))
      } catch (error) {
        if (!isMounted) return
        setNewsItems([])
        setNewsError(error.message || '뉴스를 불러오지 못했습니다.')
      } finally {
        if (isMounted) setNewsLoading(false)
      }
    }

    loadWatchlistNews()

    return () => {
      isMounted = false
    }
  }, [selectedItem])

  async function handleToggleSummary(news) {
    const articleId = news?.id
    if (!articleId) return

    if (expandedNewsId === articleId) {
      setExpandedNewsId('')
      return
    }

    setExpandedNewsId(articleId)

    if (news.ai_summary) {
      return
    }

    setSummaryLoadingId(articleId)

    try {
      const response = await ensureNewsSummaries({ articleIds: [articleId] })
      const updatedItem = response?.items?.find((item) => item.id === articleId)

      if (updatedItem) {
        setNewsItems((current) =>
          current.map((item) =>
            item.id === articleId
              ? {
                  ...item,
                  ai_summary: updatedItem.ai_summary || item.ai_summary,
                  ai_summary_model: updatedItem.ai_summary_model || item.ai_summary_model,
                  ai_summary_generated_at: updatedItem.ai_summary_generated_at || item.ai_summary_generated_at,
                  ai_summary_prompt_version: updatedItem.ai_summary_prompt_version || item.ai_summary_prompt_version,
                }
              : item,
          ),
        )
      }

      setExpandedNewsId(articleId)
    } catch (error) {
      setNewsError(error.message || '요약 생성을 가져오지 못했습니다.')
    } finally {
      setSummaryLoadingId('')
    }
  }

  return (
    <main className="max-w-7xl mx-auto flex flex-col gap-6">
      <section className="bg-slate-surface border border-slate-700/80 rounded-lg p-5">
        <SectionHeader title="관심종목 명단" />
        <div className={useSlider ? 'flex snap-x gap-2 overflow-x-auto pb-2' : 'grid gap-2 md:grid-cols-2 xl:grid-cols-4'}>
          {WATCHLIST_MOCK.map((item) => (
            <button
              key={item.id}
              className={`${useSlider ? 'min-w-60 snap-start' : 'w-full'} rounded-lg px-4 py-3 text-left transition ${selectedItem?.id === item.id ? 'bg-institutional-blue text-white' : 'bg-[#0f172a] text-slate-300 hover:bg-white/5'
                }`}
              type="button"
              onClick={() => setSelectedId(item.id)}
            >
              <span className="block font-bold">{item.name}</span>
              <span className="mt-1 block text-xs opacity-70 font-mono">{item.market} · {item.account}</span>
            </button>
          ))}
        </div>
      </section>

      <section className="bg-slate-surface border border-slate-700/80 rounded-lg p-5">
        <div className="flex justify-between items-center mb-3">
          <SectionHeader title="관심 종목의 차트" action={selectedItem?.id} />
          {selectedItem && (
            <Link
              to={`/asset/${assetType}/${selectedItem.id}`}
              className="rounded bg-blue-600 hover:bg-blue-700 text-white font-bold text-xs px-3 py-1.5 transition active:scale-[0.98]"
            >
              수동 매매 터미널 이동 →
            </Link>
          )}
        </div>
        <div className="rounded-lg border border-slate-800 bg-[#0f172a]/70 p-4">
          <MiniSparkline values={WATCH_CHARTS_MOCK[selectedItem?.id]} />
        </div>
        <div className="mt-4 grid gap-3 md:grid-cols-5">
          {[
            ['종목명', selectedItem?.name],
            ['계좌종류', selectedItem?.account],
            ['수량', selectedItem?.quantity],
            ['평균 단가', (() => {
              if (!selectedItem) return '-'
              const isForeign = /[a-zA-Z]/.test(selectedItem.id) || selectedItem.market.includes('해외')
              const stockCurrency = isForeign ? 'USD' : 'KRW'
              const rawAvg = parseFloat(selectedItem.average.replace(/[^0-9.-]/g, '')) || 0
              const currentDisplayCurrency = isForeign ? displayCurrency : 'KRW'
              return formatCurrency(rawAvg, stockCurrency, currentDisplayCurrency)
            })()],
            ['등락율', selectedItem?.change],
          ].map(([label, value]) => (
            <div key={label} className="rounded-lg bg-[#0f172a] p-4">
              <p className="text-xs font-bold text-slate-500">{label}</p>
              <p className="mt-2 font-bold text-white font-mono">{label === '등락율' || label.startsWith('등락율') ? <Rate value={value} /> : value}</p>
            </div>
          ))}
        </div>
      </section>

      <section className="bg-slate-surface border border-slate-700/80 rounded-lg p-5">
        <SectionHeader title="관심종목 관련 최근 뉴스피드" />
        <div className="grid gap-3 lg:grid-cols-2">
          {newsLoading && newsItems.length === 0 ? (
            <div className="rounded-lg border border-slate-800 bg-[#0f172a] p-4 text-sm text-slate-400 lg:col-span-2">
              최신 뉴스피드를 불러오는 중입니다...
            </div>
          ) : null}

          {newsError ? (
            <div className="rounded-lg border border-red-800 bg-red-950/30 p-4 text-sm text-red-300 lg:col-span-2">
              {newsError}
            </div>
          ) : null}

          {!newsLoading && newsItems.length === 0 && !newsError ? (
            <div className="rounded-lg border border-slate-800 bg-[#0f172a] p-4 text-sm text-slate-400 lg:col-span-2">
              선택한 관심종목과 연결된 최신 뉴스가 없습니다.
            </div>
          ) : null}

          {newsItems.map((news, index) => {
            const articleId = news.id || news.url || `${news.title}-${index}`
            const isExpanded = expandedNewsId === news.id
            const isLoadingSummary = summaryLoadingId === news.id

            return (
              <article key={articleId} className="rounded-lg border border-slate-800 bg-[#0f172a] p-4">
                <div className="flex items-center justify-between gap-3 text-xs text-slate-500">
                  <span className="font-bold text-ai-cyan">{news.source}</span>
                  <span className="font-mono">{formatNewsDate(news.published_at)}</span>
                </div>
                <h3 className="mt-3 break-words text-sm font-bold leading-6 text-white">{news.title}</h3>
                <p className="mt-2 text-xs text-slate-500">{news.company_name || news.symbol || selectedItem?.name}</p>

                <div className="mt-3 rounded-lg border border-slate-800 bg-black/20 p-3">
                  <p className="break-words whitespace-pre-line text-sm leading-6 text-slate-300">
                    {isExpanded
                      ? news.ai_summary || (isLoadingSummary ? '요약을 생성하는 중입니다...' : '요약 보기 버튼을 눌러 3줄 요약을 생성하세요.')
                      : '요약 보기 버튼을 눌러 3줄 요약을 생성하세요.'}
                  </p>
                  {isExpanded ? (
                    <p className="mt-2 text-[11px] text-slate-500">
                      {news.ai_summary_generated_at
                        ? `요약 저장 시각: ${formatNewsDate(news.ai_summary_generated_at)}`
                        : 'DB에 저장된 요약을 불러왔습니다.'}
                    </p>
                  ) : null}
                </div>

                <div className="mt-4 flex flex-wrap justify-end gap-2">
                  <button
                    className="rounded border border-slate-700 px-3 py-1.5 text-xs text-slate-300 hover:border-slate-500"
                    type="button"
                    disabled={isLoadingSummary}
                    onClick={() => {
                      if (isLoadingSummary) return
                      if (isExpanded) {
                        setExpandedNewsId('')
                        return
                      }
                      void handleToggleSummary(news)
                    }}
                  >
                    {isLoadingSummary ? '생성 중' : isExpanded ? '접기' : '요약 보기'}
                  </button>

                  <a
                    className="rounded bg-ai-cyan px-3 py-1.5 text-xs font-semibold text-black"
                    href={news.url || '#'}
                    rel="noreferrer"
                    target="_blank"
                  >
                    원문 열기
                  </a>
                </div>
              </article>
            )
          })}
        </div>
      </section>
    </main>
  )
}
