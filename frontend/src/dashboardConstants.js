export const ASSET_PERIOD_OPTIONS = [
  { key: '1h', label: '1시간', hours: 1 },
  { key: '1d', label: '1일', days: 1 },
  { key: '1w', label: '1주', days: 7 },
  { key: '1m', label: '1개월', days: 30 },
]

export const ASSET_TREND_DATA = {
  '1w': {
    values: [86, 88, 87, 91, 94, 92, 97],
    description: '지난 1주 기준',
    delta: '+₩42,800',
  },
  '1m': {
    values: [68, 72, 70, 78, 76, 84, 88, 91, 86, 94, 101, 108],
    description: '지난 30일 기준',
    delta: '+₩235,400',
  },
  '3m': {
    values: [54, 58, 57, 61, 66, 64, 72, 75, 73, 80, 83, 89, 92, 96, 101, 108],
    description: '지난 3개월 기준',
    delta: '+₩618,200',
  },
  '1y': {
    values: [38, 42, 40, 47, 52, 49, 55, 63, 61, 68, 74, 71, 79, 86, 93, 108],
    description: '지난 1년 기준',
    delta: '+₩1,240,900',
  },
}

export const WATCHLIST_MOCK = [
  { id: '005930', name: '삼성전자', market: '국내 주식', account: 'KIS 모의', quantity: '18주', average: '72,400원', change: '+2.14%' },
  { id: '000660', name: 'SK하이닉스', market: '국내 주식', account: 'KIS 모의', quantity: '6주', average: '182,000원', change: '+7.82%' },
  { id: 'NVDA', name: 'NVIDIA', market: '해외 주식', account: '해외 위탁', quantity: '4주', average: '$126.40', change: '+4.31%' },
  { id: 'TSLA', name: 'Tesla', market: '해외 주식', account: '해외 위탁', quantity: '3주', average: '$188.20', change: '-1.26%' }
];

export const DASHBOARD_TABS = [
  { key: 'dashboard', label: '대시보드', enabled: true },
  { key: 'inquiry', label: '문의하기', enabled: true, route: '/inquiry', authOnly: true },
  { key: 'watchlist', label: '관심종목', enabled: true },
  { key: 'assets',    label: '내 자산',  enabled: true },
  { key: 'history',   label: '거래 내역', enabled: true },
  { key: 'settings',  label: '설정',     enabled: true },
  { key: 'admin',     label: '관리자',   enabled: true },
]

export const WATCH_CHARTS_MOCK = {
  '005930': [44, 47, 45, 51, 49, 55, 58, 62, 60, 66, 64, 71],
  '000660': [38, 42, 46, 44, 53, 57, 63, 66, 70, 74, 78, 83],
  NVDA: [52, 54, 51, 59, 62, 61, 66, 69, 73, 70, 76, 79],
  TSLA: [70, 68, 66, 69, 64, 62, 60, 58, 61, 57, 55, 54]
}

export const ASSET_ACCOUNTS_MOCK = [
  { id: 'krw-stock', title: '주식계좌', accountType: '원화', maskedAccountNumber: '123-45-****01', balanceLabel: '원화 잔고', balance: '1,186,900원' },
  { id: 'usd-stock', title: '해외주식계좌', accountType: '달러', maskedAccountNumber: '987-65-****09', balanceLabel: '달러 잔고', balance: '$842.16' },
  { id: 'coin-wallet', title: '코인계좌', accountType: '코인', maskedAccountNumber: 'UPBIT-****-001', balanceLabel: '코인 평가금', balance: '489,500원' }
]

export const FALLBACK_HOLDINGS = [
  { id: 'holding-005930', name: '삼성전자', account: '국내 주식', quantity: '18주', average: '72,400원', returnRate: '+2.14%', weight: 26 },
  { id: 'holding-000660', name: 'SK하이닉스', account: '국내 주식', quantity: '6주', average: '182,000원', returnRate: '+7.82%', weight: 24 },
  { id: 'holding-NVDA', name: 'NVIDIA', account: '해외 주식', quantity: '4주', average: '$126.40', returnRate: '+4.31%', weight: 14 },
  { id: 'holding-TSLA', name: 'Tesla', account: '해외 주식', quantity: '3주', average: '$188.20', returnRate: '-1.26%', weight: 12 },
  { id: 'holding-BTC', name: 'Bitcoin', account: '코인', quantity: '0.0038 BTC', average: '128,600,000원', returnRate: '+3.18%', weight: 9 }
]

export const TRADE_HISTORY_MOCK = [
  { id: 'trade-1', date: '2026-06-23', time: '14:18:35', exchange: 'TOSS', symbolName: '삼성전자', ticker: '005930', side: '매수', currency: 'KRW', price: '68,500', quantity: '100', amount: '₩6,850,000', status: '체결완료', exchangeRate: '-', fees: '1,370원', orderNumber: 'TOSS-260623-001' },
  { id: 'trade-2', date: '2026-06-23', time: '11:02:10', exchange: 'KIS', symbolName: 'NVIDIA Corp', ticker: 'NVDA', side: '매도', currency: 'USD', price: '$425.10', quantity: '50', amount: '$21,255.00', status: '체결완료', exchangeRate: '1,385.50 KRW', fees: '185원', orderNumber: 'KIS-260623-118' },
  { id: 'trade-3', date: '2026-06-22', time: '15:21:44', exchange: 'COINONE', symbolName: 'Bitcoin', ticker: 'BTC/KRW', side: '매수', currency: 'KRW', price: '45,200,000', quantity: '0.5', amount: '₩22,600,000', status: '체결완료', exchangeRate: '-', fees: '11,300원', orderNumber: 'COIN-260622-039' },
  { id: 'trade-4', date: '2026-06-22', time: '08:45:00', exchange: 'BINANCE', symbolName: 'Ethereum', ticker: 'ETH/USDT', side: '매도', currency: 'USD', price: '$1,780.50', quantity: '10.0', amount: '$17,805.00', status: '미체결', exchangeRate: '1,385.50 KRW', fees: '$8.90', orderNumber: 'BN-260622-204' },
  { id: 'trade-5', date: '2026-06-21', time: '09:41:08', exchange: 'TOSS', symbolName: 'SK하이닉스', ticker: '000660', side: '매수', currency: 'KRW', price: '124,000', quantity: '200', amount: '₩24,800,000', status: '체결완료', exchangeRate: '-', fees: '4,960원', orderNumber: 'TOSS-260621-091' }
]
