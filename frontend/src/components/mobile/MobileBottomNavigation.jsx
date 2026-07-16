import { useEffect, useMemo, useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import { supabase } from '../../supabaseClient'
import { DASHBOARD_ROUTE, DASHBOARD_TABS } from '../../dashboardConstants.js'
import SymbolSearch from '../SymbolSearch.jsx'
import MobileMemberOnlySheet from './MobileMemberOnlySheet.jsx'

function Icon({ name, className = 'h-6 w-6' }) {
  const icons = {
    home: (
      <>
        <path strokeLinecap="round" strokeLinejoin="round" d="M4 10.5 12 4l8 6.5" />
        <path strokeLinecap="round" strokeLinejoin="round" d="M6.5 10v9h11v-9" />
        <path strokeLinecap="round" strokeLinejoin="round" d="M10 19v-5h4v5" />
      </>
    ),
    search: (
      <>
        <circle cx="10.5" cy="10.5" r="5.5" />
        <path strokeLinecap="round" strokeLinejoin="round" d="m15 15 4 4" />
      </>
    ),
    news: (
      <>
        <path strokeLinecap="round" strokeLinejoin="round" d="M6 5.5h10.5A1.5 1.5 0 0 1 18 7v11H6z" />
        <path strokeLinecap="round" strokeLinejoin="round" d="M18 9.5h1.5v7A1.5 1.5 0 0 1 18 18" />
        <path strokeLinecap="round" strokeLinejoin="round" d="M8.5 9h5M8.5 12h7M8.5 15h4" />
      </>
    ),
    dashboard: <path strokeLinecap="round" strokeLinejoin="round" d="M5 5h6v6H5zM13 5h6v4h-6zM13 11h6v8h-6zM5 13h6v6H5z" />,
    close: <path strokeLinecap="round" strokeLinejoin="round" d="M6 6l12 12M18 6 6 18" />,
    chevron: <path strokeLinecap="round" strokeLinejoin="round" d="m9 6 6 6-6 6" />,
  }

  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.9" aria-hidden="true">
      {icons[name]}
    </svg>
  )
}

function MobileSheet({ title, subtitle, onClose, children }) {
  return (
    <div className="fixed inset-0 z-[70] bg-slate-950/70 backdrop-blur-sm">
      <button
        type="button"
        className="absolute inset-0 h-full w-full cursor-default"
        aria-label="닫기"
        onClick={onClose}
      />
      <section className="absolute inset-x-0 bottom-0 max-h-[82vh] overflow-y-auto rounded-t-[28px] border border-slate-700/80 bg-[#08111f] px-5 pb-[calc(env(safe-area-inset-bottom)+24px)] pt-4 shadow-2xl">
        <div className="mx-auto mb-4 h-1.5 w-12 rounded-full bg-slate-700" />
        <div className="mb-5 flex items-start justify-between gap-3">
          <div>
            <p className="text-[10px] font-bold uppercase tracking-[0.18em] text-ai-cyan">{subtitle}</p>
            <h2 className="mt-1 text-xl font-extrabold text-white">{title}</h2>
          </div>
          <button
            type="button"
            className="grid h-10 w-10 shrink-0 place-items-center rounded-full border border-slate-700 bg-[#0f172a] text-slate-300"
            aria-label="닫기"
            onClick={onClose}
          >
            <Icon name="close" className="h-5 w-5" />
          </button>
        </div>
        {children}
      </section>
    </div>
  )
}

function preserveDeviceParam(to, search) {
  const device = new URLSearchParams(search).get('device')
  if (!device) return to

  const [pathname, query = ''] = to.split('?')
  const params = new URLSearchParams(query)
  params.set('device', device)
  return `${pathname}?${params.toString()}`
}

function SearchSheet({ onClose }) {
  return (
    <MobileSheet title="종목 검색" subtitle="Search" onClose={onClose}>
      <div className="rounded-2xl border border-slate-800 bg-[#0f172a] p-4">
        <p className="mb-3 text-sm font-bold leading-6 text-slate-300">
          종목명이나 코드를 입력하면 상세 화면으로 이동합니다.
        </p>
        <SymbolSearch
          className="w-full flex-col items-stretch gap-3 [&_button]:h-11 [&_button]:w-full [&_input]:h-11 [&_input]:w-full [&_input]:text-base"
          onSearchComplete={onClose}
        />
      </div>
    </MobileSheet>
  )
}

function DashboardSheet({ isLoggedIn, onClose }) {
  const navigate = useNavigate()
  const location = useLocation()
  const [role, setRole] = useState('USER')

  useEffect(() => {
    if (!isLoggedIn) {
      return
    }
    supabase.auth.getSession().then(({ data: { session } }) => {
      if (session) {
        supabase
          .from('profiles')
          .select('role')
          .eq('id', session.user.id)
          .maybeSingle()
          .then(({ data }) => {
            if (data?.role) {
              setRole(data.role)
            }
          })
      }
    })
  }, [isLoggedIn])

  const visibleTabs = DASHBOARD_TABS.filter((tab) => {
    if (tab.authOnly && !isLoggedIn) return false
    if (tab.adminOnly && role !== 'ADMIN') return false
    return true
  })

  const goToTab = (tab) => {
    if (!tab.enabled) return

    if (tab.route) {
      navigate(preserveDeviceParam(tab.route, location.search))
    } else {
      navigate(preserveDeviceParam(`${DASHBOARD_ROUTE}?tab=${encodeURIComponent(tab.key)}`, location.search))
    }
    onClose()
  }

  return (
    <MobileSheet title="대시보드 메뉴" subtitle="Dashboard" onClose={onClose}>
      <div className="grid gap-2">
        {visibleTabs.map((tab) => {
          const currentTab = new URLSearchParams(location.search).get('tab')
          const isActive = location.pathname === tab.route
            || location.pathname.startsWith(`${tab.route}/`)
            || (location.pathname === DASHBOARD_ROUTE && currentTab === tab.key)
            || (location.pathname === DASHBOARD_ROUTE && tab.key === 'dashboard' && !location.search)

          return (
            <button
              key={tab.key}
              type="button"
              disabled={!tab.enabled}
              className={`flex items-center justify-between rounded-2xl border px-4 py-4 text-left transition ${
                isActive
                  ? 'border-ai-cyan/50 bg-ai-cyan/10 text-white'
                  : tab.enabled
                    ? 'border-slate-800 bg-[#0f172a] text-slate-300 active:bg-slate-800'
                    : 'border-slate-900 bg-[#0f172a]/50 text-slate-600'
              }`}
              onClick={() => goToTab(tab)}
            >
              <span>
                <span className="block text-sm font-extrabold">{tab.label}</span>
                <span className="mt-1 block text-xs font-bold text-slate-500">
                  {tab.route ? '전용 화면으로 이동' : '대시보드에서 열기'}
                </span>
              </span>
              <Icon name="chevron" className="h-5 w-5 shrink-0 text-slate-500" />
            </button>
          )
        })}
      </div>
    </MobileSheet>
  )
}

export default function MobileBottomNavigation({ isLoggedIn }) {
  const navigate = useNavigate()
  const location = useLocation()
  const [activeSheet, setActiveSheet] = useState('')

  const items = useMemo(() => [
    {
      key: 'home',
      label: '홈',
      icon: 'home',
      active: location.pathname === '/',
      onClick: () => navigate(preserveDeviceParam('/', location.search)),
    },
    {
      key: 'search',
      label: '검색',
      icon: 'search',
      active: activeSheet === 'search',
      onClick: () => setActiveSheet('search'),
    },
    {
      key: 'news',
      label: '뉴스',
      icon: 'news',
      active: location.pathname === '/news',
      onClick: () => {
        if (!isLoggedIn) {
          setActiveSheet('memberOnly')
          return
        }
        navigate(preserveDeviceParam('/news', location.search))
      },
    },
    {
      key: 'dashboard',
      label: '대시보드',
      icon: 'dashboard',
      active: activeSheet === 'dashboard' || location.pathname === DASHBOARD_ROUTE || location.pathname.startsWith('/inquiry'),
      onClick: () => setActiveSheet(isLoggedIn ? 'dashboard' : 'memberOnly'),
    },
  ], [activeSheet, isLoggedIn, location.pathname, location.search, navigate])

  return (
    <>
      <nav className="fixed inset-x-0 bottom-0 z-50 border-t border-ai-cyan/10 bg-[#061321]/95 px-3 pb-[calc(env(safe-area-inset-bottom)+8px)] pt-2 shadow-[0_-14px_34px_rgba(0,0,0,0.42)] backdrop-blur-xl">
        <div className="mx-auto grid max-w-md grid-cols-4 gap-1">
          {items.map((item) => (
            <button
              key={item.key}
              type="button"
              className={`flex min-h-[64px] flex-col items-center justify-center gap-1 rounded-2xl text-xs font-extrabold transition ${
                item.active
                  ? 'border border-ai-cyan/25 bg-ai-cyan/10 text-ai-cyan shadow-[0_0_18px_rgba(0,224,255,0.12)]'
                  : 'border border-transparent text-slate-500 active:bg-white/[0.04] active:text-slate-200'
              }`}
              aria-current={item.active ? 'page' : undefined}
              onClick={item.onClick}
            >
              <Icon name={item.icon} className="h-6 w-6" />
              <span>{item.label}</span>
            </button>
          ))}
        </div>
      </nav>

      {activeSheet === 'search' ? <SearchSheet onClose={() => setActiveSheet('')} /> : null}
      {activeSheet === 'dashboard' ? (
        <DashboardSheet isLoggedIn={isLoggedIn} onClose={() => setActiveSheet('')} />
      ) : null}
      {activeSheet === 'memberOnly' ? (
        <MobileMemberOnlySheet onClose={() => setActiveSheet('')} Sheet={MobileSheet} />
      ) : null}
    </>
  )
}
