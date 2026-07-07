import { useEffect, useMemo, useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import Header from '../components/Header.jsx'
import { deleteUserWatchlistItem, fetchUserWatchlist, normalizeWatchlistItem, upsertUserWatchlistItem } from '../supabaseClient'

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:5050'

const marketFilters = {
  region: ['국내', '해외'],
  ranking: ['거래대금', '거래량', '상승률', '하락률'],
}

function changeClass(value) {
  if (String(value).startsWith('+')) return 'text-red-400'
  if (String(value).startsWith('-')) return 'text-sky-400'
  return 'text-slate-400'
}

function formatNumber(value, decimals = 0) {
  const numberValue = Number(value)
  if (!Number.isFinite(numberValue)) return '-'
  return numberValue.toLocaleString('ko-KR', {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  })
}

function isForeignRow(row = {}) {
  const marketText = String(
    row.market_segment
    ?? row.market_country
    ?? row.region
    ?? row.country
    ?? '',
  ).toUpperCase()
  const assetType = String(row.asset_type ?? row.assetType ?? '').toUpperCase()
  const symbol = String(row.symbol ?? row.code ?? row.ticker ?? '').toUpperCase()
  const explicitForeign = ['US', 'USA', 'NASDAQ', 'NYSE', 'AMEX', '해외'].some((token) => marketText.includes(token))
  return explicitForeign || (assetType === 'STOCK' && /^[A-Z.\-]+$/.test(symbol))
}

function formatPrice(row) {
  if (typeof row.price === 'string' && row.price) {
    if (row.price === '-') return '-'
    if (isForeignRow(row)) return row.price.startsWith('$') ? row.price : `$${row.price}`
    return row.price.endsWith('원') ? row.price : `${row.price}원`
  }

  const price = row.price ?? row.current_price ?? row.live_price
  if (price === undefined || price === null || price === '') return '-'
  if (isForeignRow(row)) return `$${formatNumber(price, Number(price) % 1 === 0 ? 0 : 1)}`
  return `${formatNumber(price, Number(price) % 1 === 0 ? 0 : 1)}원`
}

function formatChange(row) {
  if (typeof row.change === 'string' && row.change) return row.change
  const change = Number(row.change_rate ?? row.changeRate ?? row.change_percent ?? row.changePercent ?? row.live_change_rate)
  if (!Number.isFinite(change)) return '-'
  return `${change > 0 ? '+' : ''}${change.toFixed(2)}%`
}

function formatValue(row, valueKey, ranking) {
  if (isForeignRow(row) && valueKey !== 'volume' && ['상승률', '하락률'].includes(ranking)) return '-'

  const direct = valueKey === 'volume'
    ? row.trading_volume ?? row.volume
    : row.trading_value ?? row.value

  if (typeof direct === 'string' && direct) return direct

  const numeric = Number(direct)
  if (!Number.isFinite(numeric) || numeric <= 0) return '-'
  if (valueKey === 'volume') return Math.round(numeric).toLocaleString('ko-KR')
  if (numeric >= 100_000_000_0000) return `${(numeric / 100_000_000_0000).toFixed(1)}조원`
  if (numeric >= 100_000_000) return `${Math.round(numeric / 100_000_000).toLocaleString('ko-KR')}억원`
  return `${Math.round(numeric).toLocaleString('ko-KR')}원`
}

function getWatchlistKey(row = {}, assetType = 'STOCK') {
  const item = normalizeWatchlistItem({ ...row, asset_type: assetType })
  return `${item.asset_type}:${item.exchange}:${item.symbol}`
}

function RankIcon({ label }) {
  const text = String(label || '?').trim().slice(0, 2).toUpperCase()
  return (
    <div className="grid h-9 w-9 shrink-0 place-items-center rounded-full bg-gradient-to-br from-ai-cyan/90 to-blue-700 text-[10px] font-black text-white shadow-[0_0_18px_rgba(0,224,255,0.18)]">
      {text}
    </div>
  )
}

function FilterChip({ label, active = false, onClick }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={[
        'h-10 rounded border px-4 text-[13px] font-semibold transition',
        active
          ? 'border-ai-cyan bg-ai-cyan/10 text-ai-cyan'
          : 'border-slate-700 bg-[#0f172a] text-slate-300 hover:border-ai-cyan hover:text-white',
      ].join(' ')}
    >
      {label}
    </button>
  )
}

function FilterBar({ title, children }) {
  return (
    <div className="flex flex-col gap-2 rounded-lg border border-slate-800/80 bg-[#07111d]/70 px-3 py-3">
      <div className="text-[11px] font-semibold uppercase tracking-[0.2em] text-slate-500">{title}</div>
      <div className="flex flex-wrap items-center gap-2">{children}</div>
    </div>
  )
}

function RankingTable({ rows, titleType = 'stock', ranking = '거래대금', favoriteKeys = new Set(), onToggleFavorite }) {
  const isStock = titleType === 'stock'
  const nameHeader = isStock ? '종목명' : '코인명'
  const showVolume = ranking === '거래량'
  const valueHeader = showVolume ? '거래량' : '거래대금'
  const valueKey = showVolume ? 'volume' : 'value'

  return (
    <>
      <div className="hidden overflow-hidden rounded-lg border border-slate-600/80 bg-[#061321]/90 shadow-[0_0_28px_rgba(0,224,255,0.06)] md:block">
        <div className="border-b border-slate-700 bg-slate-800/70 px-4 py-3">
          <div className="grid grid-cols-[34px_42px_minmax(150px,1.8fr)_minmax(92px,1fr)_minmax(78px,0.8fr)_minmax(92px,1fr)] items-center gap-3 text-[12px] font-semibold text-slate-300">
            <div />
            <div className="text-center">순위</div>
            <div>{nameHeader}</div>
            <div className="text-right">현재가</div>
            <div className="text-right">등락률</div>
            <div className="text-right">{valueHeader}</div>
          </div>
        </div>

        <div className="divide-y divide-slate-700/70">
          {rows.length === 0 ? (
            <div className="px-4 py-10 text-center text-sm text-slate-500">표시할 데이터가 없습니다.</div>
          ) : rows.map((row) => {
            const symbol = row.code || row.symbol
            const assetType = isStock ? 'STOCK' : 'CRYPTO'
            const assetPath = `/asset/${assetType}/${symbol}`
            const isFavorite = favoriteKeys.has(getWatchlistKey(row, assetType))

            return (
              <Link
                key={`${titleType}-${row.rank}-${symbol}`}
                to={assetPath}
                className="grid min-h-[58px] grid-cols-[34px_42px_minmax(150px,1.8fr)_minmax(92px,1fr)_minmax(78px,0.8fr)_minmax(92px,1fr)] items-center gap-3 px-4 py-2 text-[14px] text-inherit no-underline transition-colors hover:bg-white/[0.04] active:bg-white/[0.08]"
              >
                <button
                  type="button"
                  onClick={(event) => {
                    event.preventDefault()
                    event.stopPropagation()
                    onToggleFavorite?.(row, assetType)
                  }}
                  className={`text-[24px] leading-none transition ${isFavorite ? 'text-red-400 hover:text-red-300' : 'text-slate-400 hover:text-ai-cyan'}`}
                  aria-label="관심 종목"
                  aria-pressed={isFavorite}
                >
                  {isFavorite ? '♥' : '♡'}
                </button>
                <div className="text-center text-[16px] text-slate-100 tabular-nums">{row.rank}</div>
                <div className="flex min-w-0 items-center gap-3">
                  <RankIcon label={row.symbol || row.code || row.name} />
                  <div className="min-w-0">
                    <div className="truncate text-[15px] font-semibold text-slate-100">{row.name}</div>
                    <div className="mt-0.5 truncate text-[12px] text-slate-500">{symbol}</div>
                  </div>
                </div>
                <div className="text-right text-[15px] tabular-nums text-slate-100">{formatPrice(row)}</div>
                <div className={`text-right text-[15px] font-medium tabular-nums ${changeClass(formatChange(row))}`}>
                  {formatChange(row)}
                </div>
                <div className="text-right text-[15px] tabular-nums text-slate-200">{formatValue(row, valueKey, ranking)}</div>
              </Link>
            )
          })}
        </div>
      </div>

      <div className="divide-y divide-slate-700/70 overflow-hidden rounded-lg border border-slate-700 bg-[#061321]/90 md:hidden">
        {rows.length === 0 ? (
          <div className="px-4 py-8 text-center text-sm text-slate-500">표시할 데이터가 없습니다.</div>
        ) : rows.map((row) => {
          const symbol = row.code || row.symbol
          const assetType = titleType === 'stock' ? 'STOCK' : 'CRYPTO'
          const assetPath = `/asset/${assetType}/${symbol}`
          const isFavorite = favoriteKeys.has(getWatchlistKey(row, assetType))
          const valueKeyMobile = showVolume ? 'volume' : 'value'

          return (
            <Link
              key={`${titleType}-${row.rank}-${symbol}-mobile`}
              to={assetPath}
              className="block p-4 text-inherit no-underline transition-colors hover:bg-white/[0.02] active:bg-white/[0.04]"
            >
              <div className="flex items-center gap-3">
                <div className="w-6 text-center text-slate-300">{row.rank}</div>
                <RankIcon label={row.symbol || row.code || row.name} />
                <div className="min-w-0 flex-1">
                  <div className="truncate font-semibold text-slate-100">{row.name}</div>
                  <div className="mt-0.5 text-[11px] text-slate-500">{symbol}</div>
                </div>
                <button
                  type="button"
                  onClick={(event) => {
                    event.preventDefault()
                    event.stopPropagation()
                    onToggleFavorite?.(row, assetType)
                  }}
                  className={`text-[22px] transition ${isFavorite ? 'text-red-400 hover:text-red-300' : 'text-slate-400 hover:text-ai-cyan'}`}
                  aria-label="관심 종목"
                  aria-pressed={isFavorite}
                >
                  {isFavorite ? '♥' : '♡'}
                </button>
              </div>
              <div className="mt-3 grid grid-cols-3 gap-2 text-right text-[13px]">
                <div>
                  <div className="text-[10px] text-slate-500">현재가</div>
                  <div className="mt-1 text-slate-100">{formatPrice(row)}</div>
                </div>
                <div>
                  <div className="text-[10px] text-slate-500">등락률</div>
                  <div className={`mt-1 ${changeClass(formatChange(row))}`}>{formatChange(row)}</div>
                </div>
                <div>
                  <div className="text-[10px] text-slate-500">{valueHeader}</div>
                  <div className="mt-1 text-slate-200">{formatValue(row, valueKeyMobile, ranking)}</div>
                </div>
              </div>
            </Link>
          )
        })}
      </div>
    </>
  )
}

export default function MarketRankings({ isLoggedIn, userEmail, handleLogout }) {
  const navigate = useNavigate()
  const [searchParams, setSearchParams] = useSearchParams()
  const [rows, setRows] = useState([])
  const [status, setStatus] = useState('loading')
  const [message, setMessage] = useState('')
  const [totalCount, setTotalCount] = useState(0)
  const [favoriteKeys, setFavoriteKeys] = useState(new Set())

  const assetType = searchParams.get('assetType') === 'coin' ? 'coin' : 'stock'
  const stockRegion = searchParams.get('region') === '해외' ? '해외' : '국내'
  const stockRanking = useMemo(() => {
    const requested = searchParams.get('ranking') || '거래대금'
    if (stockRegion === '해외' && requested === '거래대금') return '거래량'
    return marketFilters.ranking.includes(requested) ? requested : '거래대금'
  }, [searchParams, stockRegion])
  const coinRanking = useMemo(() => {
    const requested = searchParams.get('ranking') || '거래대금'
    return marketFilters.ranking.includes(requested) ? requested : '거래대금'
  }, [searchParams])
  const activeRanking = assetType === 'coin' ? coinRanking : stockRanking
  const stockRankingOptions = stockRegion === '해외'
    ? marketFilters.ranking.filter((label) => label !== '거래대금')
    : marketFilters.ranking

  const updateParams = (patch) => {
    const next = new URLSearchParams(searchParams)
    Object.entries(patch).forEach(([key, value]) => {
      if (value === null || value === undefined || value === '') next.delete(key)
      else next.set(key, value)
    })
    setSearchParams(next)
  }

  const loadFavorites = async () => {
    if (!isLoggedIn) {
      setFavoriteKeys(new Set())
      return
    }

    try {
      const items = await fetchUserWatchlist()
      setFavoriteKeys(new Set(items.map((item) => getWatchlistKey(item, item.assetType))))
    } catch (error) {
      console.warn('Failed to load watchlist.', error)
      setFavoriteKeys(new Set())
    }
  }

  const handleToggleFavorite = async (row, targetAssetType) => {
    if (!isLoggedIn) {
      alert('로그인이 필요한 서비스입니다.')
      navigate('/login')
      return
    }

    const key = getWatchlistKey(row, targetAssetType)
    const nextKeys = new Set(favoriteKeys)
    const isFavorite = nextKeys.has(key)

    try {
      if (isFavorite) {
        nextKeys.delete(key)
        setFavoriteKeys(nextKeys)
        await deleteUserWatchlistItem({ ...row, asset_type: targetAssetType })
      } else {
        nextKeys.add(key)
        setFavoriteKeys(nextKeys)
        await upsertUserWatchlistItem({ ...row, asset_type: targetAssetType })
      }
    } catch (error) {
      await loadFavorites()
      alert(error.message || '관심 종목 처리 중 문제가 발생했습니다.')
    }
  }

  useEffect(() => {
    loadFavorites()
  }, [isLoggedIn])

  useEffect(() => {
    let cancelled = false

    async function loadRankings() {
      try {
        setStatus('loading')
        setMessage('')

        const params = new URLSearchParams({
          asset_type: assetType === 'coin' ? 'CRYPTO' : 'STOCK',
          limit: '100',
          ranking: activeRanking,
        })

        if (assetType === 'stock') {
          params.set('region', stockRegion)
        }

        const response = await fetch(`${API_BASE_URL}/api/market/rankings?${params.toString()}`)
        const payload = await response.json()

        if (!response.ok || !payload.success) {
          throw new Error(payload.message || '랭킹 데이터를 불러오지 못했습니다.')
        }

        if (cancelled) return

        setRows(Array.isArray(payload.data?.items) ? payload.data.items : [])
        setTotalCount(Number(payload.data?.totalCount) || 0)
        setStatus('ready')
      } catch (error) {
        if (cancelled) return
        setRows([])
        setTotalCount(0)
        setStatus('error')
        setMessage(error.message || '랭킹 데이터를 불러오지 못했습니다.')
      }
    }

    loadRankings()

    return () => {
      cancelled = true
    }
  }, [assetType, activeRanking, stockRegion])

  return (
    <div className="min-h-screen bg-obsidian-bg font-inter text-[#e2e2ec]">
      <div className="px-4 py-4 sm:px-6 sm:py-6">
        <Header isLoggedIn={isLoggedIn} userEmail={userEmail} handleLogout={handleLogout} />

        <main className="mx-auto flex w-full max-w-7xl flex-col gap-6">
          <section className="ai-glass rounded-lg p-4 sm:p-6">
            <div className="flex flex-col gap-5">
              <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
                <div>
                  <p className="text-[11px] font-semibold uppercase tracking-[0.24em] text-slate-500">Market Rankings</p>
                  <h1 className="mt-2 text-2xl font-bold text-white">주식 · 코인 더보기</h1>
                  <p className="mt-2 text-sm text-slate-400">홈에서는 10개만 보여주고, 여기서는 현재 필터 기준으로 최대 100개까지 확인합니다.</p>
                </div>
                <div className="inline-flex rounded-lg border border-slate-700 bg-[#07111d]/80 p-1">
                  <button
                    type="button"
                    onClick={() => setSearchParams(new URLSearchParams({ assetType: 'stock', region: stockRegion, ranking: stockRanking }))}
                    className={`rounded px-4 py-2 text-sm font-semibold transition ${assetType === 'stock' ? 'bg-ai-cyan/12 text-ai-cyan' : 'text-slate-300 hover:text-white'}`}
                  >
                    주식
                  </button>
                  <button
                    type="button"
                    onClick={() => setSearchParams(new URLSearchParams({ assetType: 'coin', ranking: coinRanking }))}
                    className={`rounded px-4 py-2 text-sm font-semibold transition ${assetType === 'coin' ? 'bg-ai-cyan/12 text-ai-cyan' : 'text-slate-300 hover:text-white'}`}
                  >
                    코인
                  </button>
                </div>
              </div>

              {assetType === 'stock' ? (
                <FilterBar title="주식 필터">
                  {marketFilters.region.map((label) => (
                    <FilterChip
                      key={`stock-region-${label}`}
                      label={label}
                      active={stockRegion === label}
                      onClick={() => updateParams({
                        assetType: 'stock',
                        region: label,
                        ranking: label === '해외' && stockRanking === '거래대금' ? '거래량' : stockRanking,
                      })}
                    />
                  ))}
                  <span className="mx-1 hidden h-7 w-px bg-slate-700 md:block" />
                  {stockRankingOptions.map((label) => (
                    <FilterChip
                      key={`stock-ranking-${label}`}
                      label={label}
                      active={stockRanking === label}
                      onClick={() => updateParams({ assetType: 'stock', ranking: label })}
                    />
                  ))}
                </FilterBar>
              ) : (
                <FilterBar title="코인 필터">
                  {marketFilters.ranking.map((label) => (
                    <FilterChip
                      key={`coin-ranking-${label}`}
                      label={label}
                      active={coinRanking === label}
                      onClick={() => updateParams({ assetType: 'coin', ranking: label })}
                    />
                  ))}
                </FilterBar>
              )}
            </div>
          </section>

          <section className="rounded-lg border border-slate-700 bg-[#061321]/80 p-4 sm:p-5">
            <div className="mb-4 flex flex-col gap-2 border-b border-slate-800 pb-3 sm:flex-row sm:items-center sm:justify-between">
              <div className="text-sm text-slate-300">
                {assetType === 'coin' ? '코인' : stockRegion} 기준 <span className="font-semibold text-white">{totalCount.toLocaleString('ko-KR')}</span>개 조회됨 (최대 100개 표시)
              </div>
              <div className="text-xs text-slate-500">
                {status === 'loading' ? 'LOADING' : activeRanking}
              </div>
            </div>

            {message ? (
              <div className="mb-4 rounded-lg border border-red-500/20 bg-red-500/5 px-4 py-3 text-sm text-red-200">
                {message}
              </div>
            ) : null}

            <RankingTable
              rows={rows}
              titleType={assetType}
              ranking={activeRanking}
              favoriteKeys={favoriteKeys}
              onToggleFavorite={handleToggleFavorite}
            />
          </section>
        </main>
      </div>
    </div>
  )
}
