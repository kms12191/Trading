export const DASHBOARD_ROUTE = '/dashboard'
export const DEFAULT_DASHBOARD_TAB = 'dashboard'
export const DASHBOARD_QUERY_TABS = ['watchlist', 'assets', 'history', 'settings', 'admin']
export const DASHBOARD_TAB_KEYS = [DEFAULT_DASHBOARD_TAB, ...DASHBOARD_QUERY_TABS]

export const INQUIRY_ROUTES = {
  home: '/inquiry',
  faq: '/inquiry/faq',
  write: '/inquiry/write',
  history: '/inquiry/history',
}

export const DASHBOARD_TABS = [
  { key: 'dashboard', label: '대시보드', enabled: true },
  { key: 'watchlist', label: '관심종목', enabled: true },
  { key: 'assets', label: '내 자산', enabled: true },
  { key: 'history', label: '거래 내역', enabled: true },
  {
    key: 'inquiry',
    enabled: true,
    label: '고객센터',
    route: INQUIRY_ROUTES.home,
    authOnly: true,
  },
  { key: 'settings', label: '설정', enabled: true },
  { key: 'admin', label: '관리자', enabled: true },
]
