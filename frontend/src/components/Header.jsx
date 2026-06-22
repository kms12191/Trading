export default function Header({ currentRoute }) {
  return (
    <header className="max-w-7xl mx-auto mb-8 border-b border-slate-800 pb-4 flex flex-col gap-4 lg:flex-row lg:justify-between lg:items-center">
      <div>
        <h1 className="text-2xl font-bold tracking-tight text-white flex items-center gap-2 flex-wrap">
          SYNTHETIC INTELLIGENCE TERMINAL
          <span className="text-xs px-2 py-0.5 rounded border border-ai-cyan text-ai-cyan font-mono font-medium animate-pulse">
            MOCK TRADING
          </span>
        </h1>
        <p className="text-sm text-slate-400 mt-1">
          {currentRoute === 'news' ? 'News Feed Board' : 'Multi-Asset Trading Dashboard'}
        </p>
      </div>
      <div className="flex items-center gap-3">
        <nav className="flex gap-2">
          <a
            href="#/dashboard"
            className={`px-3 py-1.5 rounded text-xs font-semibold border transition-all ${
              currentRoute === 'dashboard'
                ? 'bg-ai-cyan text-black border-ai-cyan'
                : 'text-slate-300 border-slate-700 hover:border-slate-500'
            }`}
          >
            대시보드
          </a>
          <a
            href="#/news"
            className={`px-3 py-1.5 rounded text-xs font-semibold border transition-all ${
              currentRoute === 'news'
                ? 'bg-ai-cyan text-black border-ai-cyan'
                : 'text-slate-300 border-slate-700 hover:border-slate-500'
            }`}
          >
            뉴스
          </a>
        </nav>
        <span className="text-xs font-mono text-slate-500">SYSTEM TIME: 2026-06-22T11:53:27</span>
      </div>
    </header>
  )
}
