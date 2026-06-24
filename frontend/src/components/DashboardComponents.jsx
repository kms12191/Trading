import { ASSET_TREND_DATA, DASHBOARD_TABS } from '../dashboardConstants.js'

function Rate({ value }) {
  if (!value) return <span className="text-slate-400">0.00%</span>;
  const isPositive = value.startsWith('+');
  const isNegative = value.startsWith('-');
  return (
    <span className={`font-mono font-semibold ${isPositive ? 'text-emerald-400' : isNegative ? 'text-red-400' : 'text-slate-400'}`}>
      {value}
    </span>
  )
}

function Sparkline({ values = ASSET_TREND_DATA['1m'].values }) {
  const min = Math.min(...values)
  const max = Math.max(...values)
  const range = Math.max(max - min, 1)
  const points = values
    .map((val, index) => {
      const x = (index / Math.max(values.length - 1, 1)) * 100
      const y = 52 - ((val - min) / range) * 46
      return `${x},${y}`
    })
    .join(' ');

  return (
    <svg className="h-32 w-full" viewBox="0 0 100 56" preserveAspectRatio="none" role="img" aria-label="총 자산 가치 그래프">
      <defs>
        <linearGradient id="assetFill" x1="0" x2="0" y1="0" y2="1">
          <stop offset="0%" stopColor="#00f2fe" stopOpacity="0.2" />
          <stop offset="100%" stopColor="#00f2fe" stopOpacity="0" />
        </linearGradient>
      </defs>
      <polyline points={`0,56 ${points} 100,56`} fill="url(#assetFill)" stroke="none" />
      <polyline points={points} fill="none" stroke="#00f2fe" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
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

function SidebarNav({ activeTab, isOpen, onClose, onOpen, onTabChange }) {
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
            <p className="text-sm font-extrabold text-white">AE STOCK</p>
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

        {DASHBOARD_TABS.map((tab) => (
          <button
            key={tab.key}
            className={`shrink-0 rounded-lg px-4 py-3 text-left text-sm font-bold transition ${activeTab === tab.key
                ? 'bg-institutional-blue text-white shadow-[0_10px_24px_rgba(0,71,187,0.25)]'
                : tab.enabled
                  ? 'text-slate-400 hover:bg-white/5 hover:text-white'
                  : 'cursor-default text-slate-600'
              }`}
            type="button"
            onClick={() => {
              if (tab.enabled) onTabChange(tab.key)
            }}
          >
            {tab.label}
          </button>
        ))}

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
