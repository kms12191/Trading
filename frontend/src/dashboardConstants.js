export const DASHBOARD_ROUTE = '/dashboard'
export const DEFAULT_DASHBOARD_TAB = 'dashboard'
export const DASHBOARD_QUERY_TABS = ['watchlist', 'assets', 'history', 'settings', 'admin']
export const DASHBOARD_TAB_KEYS = [DEFAULT_DASHBOARD_TAB, ...DASHBOARD_QUERY_TABS]

export const INQUIRY_ROUTES = {
  home: '/inquiry',
  faq: '/inquiry/faq',
  history: '/inquiry/history',
}

export const DASHBOARD_TABS = [
  { key: 'dashboard', label: '대시보드', enabled: true },
  { key: 'watchlist', label: '관심종목', enabled: true },
  { key: 'assets', label: '내 자산', enabled: true },
  { key: 'history', label: '거래 내역', enabled: true },
  {
    key: 'inquiry',
    label: '문의하기',
    enabled: true,
    route: INQUIRY_ROUTES.home,
    authOnly: true,
    children: [
      { key: 'inquiry-home', label: '문의하기', route: INQUIRY_ROUTES.home },
      { key: 'inquiry-history', label: '문의 내역', route: INQUIRY_ROUTES.history },
      { key: 'inquiry-faq', label: '자주 묻는 질문', route: INQUIRY_ROUTES.faq },
    ],
  },
  { key: 'settings', label: '설정', enabled: true },
  { key: 'admin', label: '관리자', enabled: true },
]
