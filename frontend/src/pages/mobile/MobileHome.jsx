import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import AssetLogo from '../../components/AssetLogo.jsx'
import MobileHeader from '../../components/mobile/MobileHeader.jsx'
import useMobileHomeMarket, { getMobileHomeWatchlistKey } from '../../hooks/useMobileHomeMarket.js'
import { preserveMobileDeviceParam } from './mobileRouteUtils.js'

const INITIAL_RANKING_LIMIT = 10
const EXPANDED_RANKING_LIMIT = 50

// 모바일 홈 상단 랭킹은 자산군 탭과 지표 탭을 조합해 같은 목록 UI에서 재사용합니다.
const CATEGORY_TABS = [
  { key: 'domestic', label: '국내', assetType: 'STOCK', region: '국내' },
  { key: 'foreign', label: '해외', assetType: 'STOCK', region: '해외' },
  { key: 'coin', label: '코인', assetType: 'CRYPTO' },
]

const METRIC_TABS = [
  { key: 'tradingValue', label: '거래대금', ranking: '거래대금', valueKey: 'value' },
  { key: 'volume', label: '거래량', ranking: '거래량', valueKey: 'volume' },
  { key: 'rise', label: '상승률', ranking: '상승률', valueKey: 'change' },
  { key: 'fall', label: '하락률', ranking: '하락률', valueKey: 'change' },
]

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
  return explicitForeign || (assetType === 'STOCK' && /^[A-Z.-]+$/.test(symbol))
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

function changeClass(value) {
  if (String(value).startsWith('+')) return 'text-red-400'
  if (String(value).startsWith('-')) return 'text-sky-400'
  return 'text-slate-400'
}

function formatValue(row, valueKey) {
  if (valueKey === 'change') return formatChange(row)

  const direct = valueKey === 'volume'
    ? row.trading_volume ?? row.volume
    : row.trading_value ?? row.value

  const numeric = typeof direct === 'string'
    ? Number(direct.replace(/,/g, '').replace(/[^0-9.-]/g, ''))
    : Number(direct)

  if (typeof direct === 'string' && direct && (!Number.isFinite(numeric) || /[가-힣A-Za-z]/.test(direct))) {
    return direct
  }

  if (!Number.isFinite(numeric) || numeric <= 0) return '-'
  if (valueKey === 'volume') {
    if (numeric >= 100_000_000) return `${(numeric / 100_000_000).toFixed(1)}억`
    if (numeric >= 10_000) return `${Math.round(numeric / 10_000).toLocaleString('ko-KR')}만`
    return Math.round(numeric).toLocaleString('ko-KR')
  }
  if (numeric >= 1_000_000_000_000) return `${(numeric / 1_000_000_000_000).toFixed(1)}조원`
  if (numeric >= 100_000_000) return `${Math.round(numeric / 100_000_000).toLocaleString('ko-KR')}억원`
  return `${Math.round(numeric).toLocaleString('ko-KR')}원`
}

function numericChange(row) {
  const raw = row.change_rate ?? row.changeRate ?? row.change_percent ?? row.changePercent ?? row.live_change_rate ?? row.change
  const value = Number(String(raw ?? '').replace('%', '').replace('+', ''))
  return Number.isFinite(value) ? value : 0
}

function numericMetric(row, valueKey) {
  if (valueKey === 'change') return numericChange(row)
  const raw = valueKey === 'volume' ? row.trading_volume ?? row.volume : row.trading_value ?? row.value
  const text = String(raw ?? '').replace(/,/g, '').trim()
  const numberPart = Number(text.replace(/[^0-9.-]/g, ''))
  if (!Number.isFinite(numberPart)) return 0
  if (text.includes('조')) return numberPart * 1_000_000_000_000
  if (text.includes('억')) return numberPart * 100_000_000
  if (text.includes('만')) return numberPart * 10_000
  return numberPart
}

function getRowsByCategory({ category, metric, stockRows, coinRows }) {
  const sourceRows = category.key === 'coin'
    ? coinRows
    : stockRows.filter((row) => (category.key === 'foreign' ? isForeignRow(row) : !isForeignRow(row)))

  const sortedRows = [...sourceRows]
  if (metric.key === 'rise') {
    sortedRows.sort((a, b) => numericChange(b) - numericChange(a))
  } else if (metric.key === 'fall') {
    sortedRows.sort((a, b) => numericChange(a) - numericChange(b))
  } else {
    sortedRows.sort((a, b) => numericMetric(b, metric.valueKey) - numericMetric(a, metric.valueKey))
  }

  return sortedRows.slice(0, EXPANDED_RANKING_LIMIT).map((row, index) => ({ ...row, rank: index + 1 }))
}

function getMetricTabs(categoryKey) {
  if (categoryKey === 'foreign') {
    return METRIC_TABS.filter((item) => item.key !== 'tradingValue')
  }
  return METRIC_TABS
}

function SegmentTabs({ items, activeKey, onChange }) {
  return (
    <div className="flex max-w-full min-w-0 gap-2 overflow-x-auto pb-1">
      {items.map((item) => (
        <button
          key={item.key}
          type="button"
          onClick={() => onChange(item)}
          className={`h-10 shrink-0 rounded-lg border px-4 text-sm font-extrabold transition ${
            activeKey === item.key
              ? 'border-ai-cyan bg-ai-cyan/10 text-ai-cyan shadow-[0_0_16px_rgba(0,224,255,0.12)]'
              : 'border-slate-700 bg-[#0f172a] text-slate-300 active:bg-white/[0.04]'
          }`}
        >
          {item.label}
        </button>
      ))}
    </div>
  )
}

function RankingCard({ row, category, metric, favoriteKeys, onToggleFavorite }) {
  const symbol = row.code || row.symbol
  const assetPath = preserveMobileDeviceParam(`/asset/${category.assetType}/${symbol}`)
  const isFavorite = favoriteKeys.has(getMobileHomeWatchlistKey(row, category.assetType))
  const metricValue = formatValue(row, metric.valueKey)
  const isChangeMetric = metric.valueKey === 'change'
  const secondLabel = isChangeMetric ? metric.label : '등락률'
  const secondValue = isChangeMetric ? metricValue : formatChange(row)
  const thirdLabel = isChangeMetric ? '거래량' : metric.label
  const thirdValue = isChangeMetric ? formatValue(row, 'volume') : metricValue

  return (
    <Link
      to={assetPath}
      className="block max-w-full overflow-hidden rounded-2xl border border-slate-800 bg-[#061321]/95 p-4 text-inherit no-underline shadow-[0_14px_28px_rgba(0,0,0,0.18)] active:bg-white/[0.04]"
    >
      <div className="flex items-start gap-3">
        <AssetLogo symbol={symbol} assetType={category.assetType} name={row.name} size="h-10 w-10" />
        <div className="min-w-0 flex-1">
          <div className="flex items-start justify-between gap-2">
            <div className="min-w-0">
              <p className="truncate text-base font-black text-white">{row.name || symbol}</p>
              <p className="mt-0.5 truncate font-mono text-[11px] font-bold text-slate-500">{symbol}</p>
            </div>
            <span className="rounded-full border border-slate-700 bg-[#0f172a] px-2 py-1 font-mono text-xs font-black text-slate-300">
              #{row.rank}
            </span>
          </div>

          <div className="mt-4 grid grid-cols-[minmax(0,1fr)_minmax(0,0.9fr)_minmax(0,1fr)] gap-2 text-right">
            <div className="min-w-0">
              <p className="text-[10px] font-bold text-slate-500">현재가</p>
              <p className="mt-1 truncate font-mono text-xs font-black text-slate-100">{formatPrice(row)}</p>
            </div>
            <div className="min-w-0">
              <p className="text-[10px] font-bold text-slate-500">{secondLabel}</p>
              <p className={`mt-1 truncate font-mono text-xs font-black ${changeClass(secondValue)}`}>{secondValue}</p>
            </div>
            <div className="min-w-0">
              <p className="text-[10px] font-bold text-slate-500">{thirdLabel}</p>
              <p className="mt-1 truncate font-mono text-xs font-black text-ai-cyan">
                {thirdValue}
              </p>
            </div>
          </div>
        </div>

        <button
          type="button"
          onClick={(event) => {
            event.preventDefault()
            event.stopPropagation()
            onToggleFavorite?.(row, category.assetType)
          }}
          className={`text-2xl leading-none transition ${isFavorite ? 'text-red-400' : 'text-slate-500'}`}
          aria-label="관심종목"
          aria-pressed={isFavorite}
        >
          {isFavorite ? '♥' : '♡'}
        </button>
      </div>
    </Link>
  )
}

export default function MobileHome({ isLoggedIn, handleLogout }) {
  // 홈 화면은 관심종목과 시장 랭킹을 가볍게 보여주는 모바일 첫 진입 화면입니다.
  const [activeCategoryKey, setActiveCategoryKey] = useState('domestic')
  const [activeMetricKey, setActiveMetricKey] = useState('tradingValue')
  const [visibleLimit, setVisibleLimit] = useState(INITIAL_RANKING_LIMIT)

  const activeCategory = CATEGORY_TABS.find((item) => item.key === activeCategoryKey) || CATEGORY_TABS[0]
  const metricTabs = getMetricTabs(activeCategory.key)
  const activeMetric = metricTabs.find((item) => item.key === activeMetricKey) || metricTabs[0]
  const {
    stockRows,
    coinRows,
    status,
    message,
    favoriteKeys,
    marketState,
    loadOverview,
    handleToggleFavorite,
  } = useMobileHomeMarket({ isLoggedIn, activeCategory, activeMetric })
  const rankingRows = useMemo(
    () => getRowsByCategory({ category: activeCategory, metric: activeMetric, stockRows, coinRows }),
    [activeCategory, activeMetric, stockRows, coinRows],
  )
  const visibleRows = rankingRows.slice(0, visibleLimit)
  const canShowMore = visibleLimit < rankingRows.length

  const handleCategoryChange = (item) => {
    setActiveCategoryKey(item.key)
    setVisibleLimit(INITIAL_RANKING_LIMIT)
    const nextMetricTabs = getMetricTabs(item.key)
    if (!nextMetricTabs.some((metric) => metric.key === activeMetricKey)) {
      setActiveMetricKey(nextMetricTabs[0].key)
    }
  }

  const handleMetricChange = (item) => {
    setActiveMetricKey(item.key)
    setVisibleLimit(INITIAL_RANKING_LIMIT)
  }

  const statusText = message || (status === 'loading' ? '시장 데이터를 불러오는 중입니다.' : marketState.label)

  return (
    <div className="min-h-screen overflow-x-hidden bg-obsidian-bg text-[#e2e2ec] font-inter">
      <div className="w-full max-w-full px-3 py-4 sm:px-4">
        <MobileHeader isLoggedIn={isLoggedIn} handleLogout={handleLogout} />

        <main className="mx-auto grid w-full max-w-md min-w-0 gap-5 pb-8">
          <section className="min-w-0 rounded-2xl border border-ai-cyan/20 bg-gradient-to-br from-[#082033] via-[#061827] to-[#07111d] p-5 shadow-[0_18px_36px_rgba(0,0,0,0.22)]">
            <p className="text-[11px] font-black uppercase tracking-[0.18em] text-ai-cyan">ANTRY MARKET</p>
            <h1 className="mt-2 text-2xl font-black leading-tight text-white">오늘의 시장 랭킹</h1>
            <p className="mt-2 text-xs font-bold leading-5 text-slate-400">
              국내, 해외, 코인 중 하나를 선택해 원하는 기준으로 빠르게 확인합니다.
            </p>
            <div className="mt-4 flex items-center justify-between gap-3 rounded-2xl border border-slate-700/80 bg-[#061321]/80 px-4 py-3">
              <p className="min-w-0 text-xs font-bold text-slate-400">{statusText}</p>
              <button
                type="button"
                onClick={() => loadOverview(true)}
                disabled={status === 'loading'}
                className="h-9 shrink-0 rounded-lg border border-ai-cyan/60 px-3 text-xs font-black text-ai-cyan transition active:bg-ai-cyan/10 disabled:border-slate-700 disabled:text-slate-500"
              >
                새로고침
              </button>
            </div>
          </section>

          <section className="grid min-w-0 gap-3 overflow-hidden rounded-2xl border border-slate-800 bg-[#08111f] p-4">
            <SegmentTabs items={CATEGORY_TABS} activeKey={activeCategory.key} onChange={handleCategoryChange} />
            <SegmentTabs items={metricTabs} activeKey={activeMetric.key} onChange={handleMetricChange} />
          </section>

          <section className="grid min-w-0 gap-3">
            <div className="flex items-end justify-between gap-3">
              <div>
                <p className="text-[10px] font-black uppercase tracking-[0.18em] text-ai-cyan">Ranking</p>
                <h2 className="mt-1 text-xl font-black text-white">
                  {activeCategory.label} {activeMetric.label}
                </h2>
              </div>
              <p className="text-xs font-black text-slate-500">
                {Math.min(visibleLimit, rankingRows.length)} / {rankingRows.length}
              </p>
            </div>

            {status === 'loading' ? (
              <div className="rounded-2xl border border-slate-800 bg-[#061321] px-4 py-10 text-center text-sm font-bold text-slate-500">
                시장 데이터를 불러오는 중입니다.
              </div>
            ) : rankingRows.length === 0 ? (
              <div className="rounded-2xl border border-slate-800 bg-[#061321] px-4 py-10 text-center text-sm font-bold text-slate-500">
                표시할 랭킹 데이터가 없습니다.
              </div>
            ) : visibleRows.map((row) => (
              <RankingCard
                key={`${activeCategory.key}-${activeMetric.key}-${row.rank}-${row.symbol || row.code || row.name}`}
                row={row}
                category={activeCategory}
                metric={activeMetric}
                favoriteKeys={favoriteKeys}
                onToggleFavorite={handleToggleFavorite}
              />
            ))}

            {status !== 'loading' && canShowMore ? (
              <button
                type="button"
                onClick={() => setVisibleLimit(EXPANDED_RANKING_LIMIT)}
                className="h-12 rounded-2xl border border-ai-cyan/40 bg-ai-cyan/10 text-sm font-black text-ai-cyan transition active:bg-ai-cyan/20"
              >
                더보기
              </button>
            ) : null}
          </section>
        </main>
      </div>
    </div>
  )
}
