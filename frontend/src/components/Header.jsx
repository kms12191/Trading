import React from 'react'
import { Link, useLocation } from 'react-router-dom'

// 공통 상단 네비게이션 헤더 컴포넌트
export default function Header({ isLoggedIn, userEmail, handleLogout }) {
  const location = useLocation()
  const currentPath = location.pathname

  return (
    <header className="max-w-7xl mx-auto mb-8 border-b border-slate-800 pb-4 flex flex-col gap-4 lg:flex-row lg:justify-between lg:items-center">
      <div>
        <Link to="/" className="inline-flex">
          <h1 className="text-2xl font-bold tracking-tight text-white flex items-center gap-3 flex-wrap hover:opacity-90 transition-opacity cursor-pointer">
            <img src="/logo.png" alt="Logo" className="w-8 h-8 object-contain" />
            <span>SYNTHETIC INTELLIGENCE TERMINAL</span>
            <span className="text-xs px-2 py-0.5 rounded border border-ai-cyan text-ai-cyan font-mono font-medium animate-pulse">
              MOCK TRADING
            </span>
          </h1>
        </Link>
        <p className="text-sm text-slate-400 mt-1">
          {currentPath === '/news'
            ? 'News Feed Board (시장 뉴스 보드)'
            : currentPath === '/'
              ? 'Home Market Panel (국내/해외/코인 시세 패널)'
              : 'Multi-Asset Trading Dashboard (멀티 자산 대시보드)'}
        </p>
      </div>

      <div className="flex items-center gap-6">
        <nav className="flex gap-2">
          <Link
            to="/dashboard"
            className={`px-3 py-1.5 rounded text-xs font-semibold border transition-all ${
              currentPath === '/dashboard'
                ? 'bg-ai-cyan text-black border-ai-cyan'
                : 'text-slate-300 border-slate-700 hover:border-slate-500'
            }`}
          >
            대시보드
          </Link>
          <Link
            to="/news"
            className={`px-3 py-1.5 rounded text-xs font-semibold border transition-all ${
              currentPath === '/news'
                ? 'bg-ai-cyan text-black border-ai-cyan'
                : 'text-slate-300 border-slate-700 hover:border-slate-500'
            }`}
          >
            뉴스
          </Link>
        </nav>

        <span className="hidden md:inline text-xs font-mono text-slate-500">SYSTEM TIME: 2026-06-22T11:53:27</span>

        <div className="flex items-center gap-4">
          {isLoggedIn ? (
            <div className="flex items-center gap-3 bg-[#1E293B] border border-slate-700/50 rounded-full pl-3 pr-1 py-1 text-xs">
              <span className="text-slate-300 font-medium truncate max-w-[150px]">{userEmail}</span>
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
