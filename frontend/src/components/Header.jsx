import { Link, useLocation } from 'react-router-dom'
import { useState } from 'react'
import SymbolSearch from './SymbolSearch'

// 공통 상단 네비게이션 헤더 컴포넌트
// - 관리자 탭은 대시보드 사이드바로 이동됨
export default function Header({ isLoggedIn, userEmail, handleLogout }) {
  const { pathname } = useLocation()
  const [guestNotice, setGuestNotice] = useState('')

  const navLinks = [
    { to: '/dashboard', label: '대시보드', memberOnly: true },
    { to: '/news', label: '뉴스', memberOnly: true }
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
        <div className="relative flex flex-col gap-1">
          <nav className="flex gap-2">
            {navLinks.map(({ to, label, memberOnly }) => {
              const isActive = pathname === to
              const isLocked = memberOnly && !isLoggedIn

              return isLocked ? (
                <button
                  key={to}
                  type="button"
                  aria-disabled="true"
                  title="회원만 이용할 수 있는 서비스입니다."
                  onClick={() => setGuestNotice('회원만 이용할 수 있는 서비스입니다.')}
                  className="rounded border border-slate-800 px-3 py-1.5 text-xs font-semibold text-slate-500 transition-all hover:border-ai-cyan/40 hover:text-ai-cyan"
                >
                  {label}
                </button>
              ) : (
                <Link
                  key={to}
                  to={to}
                  className={`px-3 py-1.5 rounded text-xs font-semibold border transition-all ${
                    isActive
                      ? 'bg-blue-600 text-black border-blue-600'
                      : 'text-slate-300 border-slate-700 hover:border-slate-500'
                  }`}
                >
                  {label}
                </Link>
              )
            })}
          </nav>
        </div>

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
      {guestNotice && !isLoggedIn ? (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-[#07080c]/70 px-4 backdrop-blur-sm">
          <section
            role="dialog"
            aria-modal="true"
            aria-labelledby="member-only-title"
            className="w-full max-w-sm rounded-lg border border-ai-cyan/45 bg-[#061321] p-6 text-center shadow-[0_22px_70px_rgba(0,0,0,0.55)]"
          >
            <p className="text-[10px] font-bold uppercase tracking-[0.2em] text-ai-cyan">Member Only</p>
            <h2 id="member-only-title" className="mt-3 break-keep text-xl font-extrabold leading-7 text-white">
              {guestNotice}
            </h2>
            <div className="mt-5 grid grid-cols-2 gap-2">
              <button
                type="button"
                onClick={() => setGuestNotice('')}
                className="h-10 rounded border border-slate-700 text-sm font-bold text-slate-300 transition hover:border-ai-cyan hover:text-ai-cyan"
              >
                닫기
              </button>
              <Link
                to="/login"
                className="grid h-10 place-items-center rounded bg-blue-600 text-sm font-bold text-white transition hover:bg-blue-700 active:scale-[0.99]"
              >
                로그인
              </Link>
            </div>
          </section>
        </div>
      ) : null}
    </header>
  )
}
