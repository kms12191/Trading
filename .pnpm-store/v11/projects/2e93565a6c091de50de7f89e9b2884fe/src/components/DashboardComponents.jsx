import { useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import { DASHBOARD_TABS } from '../dashboardConstants.js'

function Rate({ value }) {
  if (!value) return <span className="font-mono font-semibold text-white">0.00%</span>
  const isPositive = value.startsWith('+');
  const isNegative = value.startsWith('-');
  const tone = isPositive ? 'text-red-400' : isNegative ? 'text-blue-400' : 'text-white'
  return (
    <span className={`font-mono font-semibold ${tone}`}>
      {value}
    </span>
  )
}

const getEvenIndexes = (length, maxCount = 6) => {
  if (length <= 0) return []
  if (length <= maxCount) return Array.from({ length }, (_, index) => index)

  return Array.from({ length: maxCount }, (_, index) =>
    Math.round((index / Math.max(maxCount - 1, 1)) * (length - 1)),
  ).filter((index, itemIndex, items) => items.indexOf(index) === itemIndex)
}

const buildMinimumSeries = (values = [], labels = [], minCount = 6) => {
  const sourceValues = values.length ? values : [0]
  const sourceLabels = labels.length ? labels : sourceValues.map(() => '')

  if (sourceValues.length >= minCount) {
    return { values: sourceValues, labels: sourceLabels }
  }

  const lastValueIndex = Math.max(sourceValues.length - 1, 0)
  const displayValues = Array.from({ length: minCount }, (_, index) => {
    if (sourceValues.length === 1) return sourceValues[0]

    const position = (index / Math.max(minCount - 1, 1)) * lastValueIndex
    const lowerIndex = Math.floor(position)
    const upperIndex = Math.min(lastValueIndex, Math.ceil(position))
    const ratio = position - lowerIndex
    const lowerValue = sourceValues[lowerIndex]
    const upperValue = sourceValues[upperIndex]
    return lowerValue + (upperValue - lowerValue) * ratio
  })

  const displayLabels = Array.from({ length: minCount }, (_, index) => {
    if (sourceLabels.length === 1) return index === 0 || index === minCount - 1 ? sourceLabels[0] : ''
    const sourceIndex = Math.round((index / Math.max(minCount - 1, 1)) * Math.max(sourceLabels.length - 1, 0))
    return sourceLabels[sourceIndex] || ''
  })

  return { values: displayValues, labels: displayLabels }
}

function Sparkline({ values = [], labels = [], formatValue }) {
  const [hoverIndex, setHoverIndex] = useState(null)
  const { values: safeValues, labels: axisLabels } = buildMinimumSeries(values, labels, 6)
  const min = Math.min(...safeValues)
  const max = Math.max(...safeValues)
  const range = Math.max(max - min, 1)
  const chartPoints = safeValues
    .map((val, index) => {
      const x = (index / Math.max(safeValues.length - 1, 1)) * 100
      const y = 52 - ((val - min) / range) * 46
      return { value: val, x, y }
    })
  const points = chartPoints
    .map((point) => `${point.x},${point.y}`)
    .join(' ')
  const labelIndexes = getEvenIndexes(axisLabels.length, 6).filter((index) => axisLabels[index])
  const markerIndexes = getEvenIndexes(safeValues.length, 6)
  const activePoint = hoverIndex === null ? null : chartPoints[hoverIndex]
  const displayValue = formatValue || ((value) => value.toLocaleString())

  const handlePointerMove = (event) => {
    const bounds = event.currentTarget.getBoundingClientRect()
    const ratio = bounds.width > 0 ? (event.clientX - bounds.left) / bounds.width : 0
    const nextIndex = Math.min(
      safeValues.length - 1,
      Math.max(0, Math.round(ratio * (safeValues.length - 1))),
    )
    setHoverIndex(nextIndex)
  }

  return (
    <div>
      <div className="relative">
        <svg
          className="h-32 w-full"
          viewBox="0 0 100 56"
          preserveAspectRatio="none"
          role="img"
          aria-label="자산 가치 변화 추이"
          onMouseMove={handlePointerMove}
          onMouseLeave={() => setHoverIndex(null)}
        >
        <defs>
          <linearGradient id="assetFill" x1="0" x2="0" y1="0" y2="1">
            <stop offset="0%" stopColor="#00f2fe" stopOpacity="0.2" />
            <stop offset="100%" stopColor="#00f2fe" stopOpacity="0" />
          </linearGradient>
        </defs>
        <polyline points={`0,56 ${points} 100,56`} fill="url(#assetFill)" stroke="none" />
        <polyline points={points} fill="none" stroke="#00f2fe" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
          {activePoint ? (
            <>
              <line x1={activePoint.x} x2={activePoint.x} y1="4" y2="54" stroke="#94a3b8" strokeOpacity="0.35" strokeWidth="0.8" />
            </>
          ) : null}
        </svg>
        {markerIndexes.map((index) => {
          const point = chartPoints[index]
          const isActive = index === hoverIndex
          return (
            <span
              key={`marker-${index}`}
              className={`pointer-events-none absolute rounded-full border transition-all ${
                isActive
                  ? 'h-2.5 w-2.5 border-[#0f172a] bg-ai-cyan shadow-[0_0_0_2px_rgba(0,242,254,0.2)]'
                  : 'h-1.5 w-1.5 border-ai-cyan/80 bg-[#0f172a]'
              }`}
              style={{
                left: `${point.x}%`,
                top: `${(point.y / 56) * 100}%`,
                transform: 'translate(-50%, -50%)',
              }}
            />
          )
        })}
        {activePoint ? (
          <div
            className="pointer-events-none absolute z-10 min-w-[112px] -translate-x-1/2 rounded border border-ai-cyan/30 bg-[#08111f] px-3 py-2 text-center shadow-xl shadow-black/30"
            style={{
              left: `${activePoint.x}%`,
              top: `${Math.max(0, Math.min(78, (activePoint.y / 56) * 100 - 26))}%`,
            }}
          >
            <p className="font-mono text-xs font-extrabold text-white">{displayValue(activePoint.value)}</p>
            {axisLabels[hoverIndex] ? (
              <p className="mt-1 font-mono text-[10px] font-bold text-slate-400">{axisLabels[hoverIndex]}</p>
            ) : null}
          </div>
        ) : null}
      </div>
      {labelIndexes.length > 0 ? (
        <div className="mt-2 grid text-[10px] font-mono text-slate-500" style={{ gridTemplateColumns: `repeat(${labelIndexes.length}, minmax(0, 1fr))` }}>
          {labelIndexes.map((index, labelIndex) => (
            <span
              key={`${axisLabels[index]}-${index}`}
              className={labelIndex === 0 ? 'text-left' : labelIndex === labelIndexes.length - 1 ? 'text-right' : 'text-center'}
            >
              {axisLabels[index]}
            </span>
          ))}
        </div>
      ) : null}
    </div>
  )
}

// 섹션 헤더 컴포넌트

function SectionHeader({ eyebrow, title, action }) {
  return (
    <div className="mb-4 flex items-start justify-between gap-3">
      <div>
        {eyebrow && <p className="text-[10px] font-bold uppercase tracking-[0.16em] text-ai-cyan">{eyebrow}</p>}
        <h2 className="text-sm font-bold text-white uppercase tracking-wider">{title}</h2>
      </div>
      {action && (
        <button className="rounded border border-slate-700 px-2 py-1 text-[10px] font-bold text-slate-400 hover:border-ai-cyan hover:text-white transition-all cursor-pointer" type="button">
          {action}
        </button>
      )}
    </div>
  );
}

// 고정 목업 관심 종목 리스트

function SidebarNav({ activeTab, isOpen, isLoggedIn, onClose, onOpen, onTabChange }) {
  const navigate = useNavigate()
  const { pathname } = useLocation()
  const visibleTabs = DASHBOARD_TABS.filter((tab) => !tab.authOnly || isLoggedIn)
  const isRouteActive = (route, exact = false) => route && (exact ? pathname === route : pathname === route || pathname.startsWith(`${route}/`))

  if (!isOpen) {
    return (
      <button
        className="fixed left-4 top-4 z-40 grid h-11 w-11 place-items-center rounded-lg border border-slate-700 bg-[#0F172A] text-lg font-black text-white shadow-xl transition hover:border-ai-cyan hover:text-ai-cyan"
        type="button"
        aria-label="사이드바 열기"
        onClick={onOpen}
      >
        ☰
      </button>
    )
  }

  return (
    <aside className="shrink-0 border-b border-slate-800 bg-[#0F172A] lg:min-h-screen lg:w-64 lg:border-b-0 lg:border-r">
      <div className="sticky top-0 flex gap-3 overflow-x-auto p-4 lg:h-screen lg:flex-col lg:overflow-visible lg:p-5">
        <div className="flex items-center gap-3 lg:pb-5">
          <span className="grid h-10 w-10 place-items-center overflow-hidden rounded-lg">
            <img className="h-full w-full object-contain" src="/logo.png" alt="Trading AI" />
          </span>
          <div className="min-w-28">
            <p className="text-sm font-extrabold text-white">ANTRY</p>
            <p className="text-xs text-slate-500">Dashboard</p>
          </div>
          <button
            className="ml-auto grid h-8 w-8 place-items-center rounded-lg border border-slate-700 text-lg font-black text-slate-400 transition hover:border-ai-cyan hover:text-white"
            type="button"
            aria-label="사이드바 닫기"
            onClick={onClose}
          >
            ×
          </button>
        </div>

        {visibleTabs.map((tab) => {
          const hasActiveChild = tab.children?.some((child) => isRouteActive(child.route, true))
          const isActive = activeTab === tab.key || isRouteActive(tab.route) || hasActiveChild

          return (
            <div key={tab.key} className="shrink-0">
              <button
                className={`w-full rounded-lg px-4 py-3 text-left text-sm font-bold transition ${isActive
                    ? 'bg-institutional-blue text-white shadow-[0_10px_24px_rgba(0,71,187,0.25)]'
                    : tab.enabled
                      ? 'text-slate-400 hover:bg-white/5 hover:text-white'
                      : 'cursor-default text-slate-600'
                  }`}
                type="button"
                onClick={() => {
                  if (!tab.enabled) return
                  if (tab.route) {
                    navigate(tab.route)
                    return
                  }
                  onTabChange(tab.key)
                }}
              >
                {tab.label}
              </button>

              {tab.children && isActive ? (
                <div className="mt-2 grid gap-1 pl-4">
                  {tab.children.map((child) => {
                    const isChildActive = isRouteActive(child.route, true)

                    return (
                      <button
                        key={child.key}
                        type="button"
                        className={`rounded-md px-3 py-2 text-left text-xs font-bold transition ${
                          isChildActive
                            ? 'bg-ai-cyan text-slate-950 shadow-[0_8px_18px_rgba(0,242,254,0.16)]'
                            : 'border border-transparent text-slate-500 hover:border-slate-700 hover:bg-[#0f172a] hover:text-slate-200'
                        }`}
                        onClick={() => navigate(child.route)}
                      >
                        {child.label}
                      </button>
                    )
                  })}
                </div>
              ) : null}
            </div>
          )
        })}

        <div className="mt-auto hidden rounded-lg border border-ai-cyan/20 bg-white/[0.04] p-4 lg:block">
          <p className="text-xs font-bold text-ai-cyan">AI Layer</p>
          <p className="mt-2 text-sm leading-6 text-slate-300">매매 제안은 사용자 승인 전까지 실행되지 않습니다.</p>
        </div>
      </div>
    </aside>
  )
}

function MiniSparkline({ values = [], height = 'h-52' }) {
  const points = values
    .map((val, index) => `${(index / Math.max(values.length - 1, 1)) * 100},${110 - val}`)
    .join(' ')

  if (!values.length) {
    return <div className={`${height} grid place-items-center text-xs text-slate-500`}>차트 데이터가 없습니다.</div>
  }

  return (
    <svg className={`${height} w-full`} viewBox="0 0 100 56" preserveAspectRatio="none" role="img" aria-label="관심종목 가격 흐름">
      <defs>
        <linearGradient id="watchFill" x1="0" x2="0" y1="0" y2="1">
          <stop offset="0%" stopColor="#00e0ff" stopOpacity="0.24" />
          <stop offset="100%" stopColor="#00e0ff" stopOpacity="0" />
        </linearGradient>
      </defs>
      <polyline points={`0,56 ${points} 100,56`} fill="url(#watchFill)" stroke="none" />
      <polyline points={points} fill="none" stroke="#00e0ff" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}

export { Rate, Sparkline, SectionHeader, SidebarNav, MiniSparkline }
