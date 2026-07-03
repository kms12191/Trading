import { Link, useLocation } from 'react-router-dom'
import SymbolSearch from './SymbolSearch'

// 공통 상단 네비게이션 헤더 컴포넌트
// - 관리자 탭은 대시보드 사이드바로 이동됨
export default function Header({ isLoggedIn, userEmail, handleLogout }) {
  const { pathname } = useLocation()

  const navLinks = [
    { to: '/dashboard', label: '대시보드' },
    { to: '/news', label: '뉴스' }
  ]

  return (
    <header className="max-w-7xl mx-auto mb-8 border-b border-slate-800 pb-4 flex flex-col gap-4 lg:flex-row lg:justify-between lg:items-center">
      {/* 로고 + 페이지 설명 */}
      <div className="lg:translate-y-[2px]">
        <Link to="/" className="inline-flex">
          <div className="group flex items-center gap-3 hover:opacity-90 transition-opacity cursor-pointer">
            <img src="/logo.png" alt="Logo" className="w-8 h-8 object-contain" />
            
            {/* 그라데이션 타이포그래피 */}
            <span className="text-2xl font-extrabold tracking-tight text-transparent bg-clip-text bg-gradient-to-r from-white via-slate-200 to-cyan-300 hover:to-cyan-300 transition-all duration-300">
              ANTRY
            </span>
            <span className="text-xs px-2 py-0.5 rounded border border-ai-cyan text-ai-cyan font-mono font-medium animate-pulse">
               TRADING
            </span>
          </div>
        </Link>

      </div>

      {/* 우측 액션 영역 */}
      <div className="flex items-center gap-4">
        {/* 페이지 네비게이션 */}
        <nav className="flex gap-2">
          {navLinks.map(({ to, label }) => (
            <Link
              key={to}
              to={to}
              className={`px-3 py-1.5 rounded text-xs font-semibold border transition-all ${
                pathname === to
                  ? 'bg-blue-600 text-black border-blue-600'
                  : 'text-slate-300 border-slate-700 hover:border-slate-500'
              }`}
            >
              {label}
            </Link>
          ))}
        </nav>

        {/* 종목 퀵 검색 (md 이상에서만 표시) */}
        <div className="hidden md:flex">
          <SymbolSearch />
        </div>

        {/* 로그인/로그아웃 */}
        <div className="flex items-center">
          {isLoggedIn ? (
            <div className="flex items-center gap-3 bg-[#1E293B] border border-slate-700/50 rounded-full pl-3 pr-1 py-1 text-xs">
              <span className="text-slate-300 font-medium truncate max-w-[140px]">{userEmail}</span>
              <button
                onClick={handleLogout}
                className="bg-[#0F172A] hover:bg-red-950/20 hover:text-red-400 text-slate-400 text-[11px] font-bold px-3 py-1 rounded-full border border-slate-700/60 transition-colors cursor-pointer"
              >
                LOGOUT
              </button>
            </div>
          ) : (
            <Link
              to="/login"
              className="bg-transparent hover:bg-ai-cyan/10 text-ai-cyan text-xs font-bold px-4 py-1.5 rounded border border-ai-cyan/80 hover:border-ai-cyan transition-all cursor-pointer text-center"
            >
              LOGIN
            </Link>
          )}
        </div>
      </div>
    </header>
  )
}
