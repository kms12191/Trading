import { useState } from 'react'
import Header from '../components/Header.jsx'
import Settings from './Settings'
import { ASSET_PERIOD_OPTIONS, ASSET_TREND_DATA, WATCHLIST_MOCK } from '../dashboardConstants.js'
import { Rate, SectionHeader, SidebarNav, Sparkline } from '../components/DashboardComponents.jsx'
import { getAssetPeriodRange, getCustomTrendValues } from '../dashboardUtils.js'
import WatchlistTab from './WatchlistTab.jsx'
import AssetsTab from './AssetsTab.jsx'
import TradeHistoryTab from './TradeHistoryTab.jsx'

export default function Dashboard({ isLoggedIn, userEmail, handleLogout, userProfile }) {
  const [inputs, setInputs] = useState({
    appkey: '',
    appsecret: '',
    cano: '',
    env: 'MOCK'
  })
  const [activeTab, setActiveTab] = useState('dashboard')
  const [isSidebarOpen, setIsSidebarOpen] = useState(true)
  const [selectedAssetPeriod, setSelectedAssetPeriod] = useState('1m')
  const [assetDateRange, setAssetDateRange] = useState(() => getAssetPeriodRange('1m'))
  const [isAssetCalendarOpen, setIsAssetCalendarOpen] = useState(false)

  const [encrypted, setEncrypted] = useState(null)
  const [loading, setLoading] = useState(false)
  const [message, setMessage] = useState({ text: '', isError: false })
  const [balance, setBalance] = useState(null)

  const handleInputChange = (e) => {
    const { name, value } = e.target
    setInputs(prev => ({ ...prev, [name]: value }))
  }

  const handleTestKeys = async (e) => {
    e.preventDefault()
    if (!inputs.appkey || !inputs.appsecret || !inputs.cano) {
      setMessage({ text: 'Please fill in all API Key fields.', isError: true })
      return
    }

    setLoading(true)
    setMessage({ text: '', isError: false })

    try {
      const response = await fetch('http://localhost:5050/api/keys/test', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(inputs)
      })

      const resData = await response.json()

      if (resData.success) {
        setMessage({ text: resData.message, isError: false })
        setEncrypted(resData.data.encrypted)
        setBalance(resData.data.balance)
      } else {
        setMessage({ text: resData.message || 'Key validation failed.', isError: true })
      }
    } catch (error) {
      setMessage({ text: `Failed to connect to backend server: ${error.message}`, isError: true })
    } finally {
      setLoading(false)
    }
  }

  const refreshBalance = async () => {
    if (!encrypted) return
    setLoading(true)
    try {
      const response = await fetch('http://localhost:5050/api/dashboard/balance', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          ...encrypted,
          env: inputs.env
        })
      })
      const resData = await response.json()
      if (resData.success) {
        setBalance(resData.data)
      } else {
        setMessage({ text: resData.message || 'Failed to refresh balance.', isError: true })
      }
    } catch (error) {
      setMessage({ text: `Refresh error: ${error.message}`, isError: true })
    } finally {
      setLoading(false)
    }
  }

  // 자산 배분 비중 동적 계산 헬퍼 함수
  const getAllocationData = () => {
    if (!balance || !balance.holdings || balance.holdings.length === 0) {
      return [
        { id: 'domestic', label: '국내 주식', value: 0, color: 'bg-institutional-blue' },
        { id: 'overseas', label: '해외 주식', value: 0, color: 'bg-ai-cyan' },
        { id: 'cash', label: '현금', value: 100, color: 'bg-slate-500' }
      ]
    }

    const totalEval = balance.total_evaluation || 0
    if (totalEval === 0) {
      return [
        { id: 'domestic', label: '국내 주식', value: 0, color: 'bg-institutional-blue' },
        { id: 'overseas', label: '해외 주식', value: 0, color: 'bg-ai-cyan' },
        { id: 'cash', label: '현금', value: 100, color: 'bg-slate-500' }
      ]
    }

    let domesticValue = 0
    let overseasValue = 0

    balance.holdings.forEach(stock => {
      // 심볼에 영문 알파벳이 있으면 해외 주식으로 대략적 분류
      const isOverseas = /[a-zA-Z]/.test(stock.symbol)
      const stockEval = stock.current_price * stock.qty
      if (isOverseas) {
        overseasValue += stockEval
      } else {
        domesticValue += stockEval
      }
    })

    const domesticPercent = Math.round((domesticValue / totalEval) * 100)
    const overseasPercent = Math.round((overseasValue / totalEval) * 100)
    const cashPercent = 100 - domesticPercent - overseasPercent

    return [
      { id: 'domestic', label: '국내 주식', value: domesticPercent, color: 'bg-blue-600' },
      { id: 'overseas', label: '해외 주식', value: overseasPercent, color: 'bg-ai-cyan' },
      { id: 'cash', label: '현금', value: Math.max(0, cashPercent), color: 'bg-slate-500' }
    ]
  }

  const allocation = getAllocationData()
  const assetTrendValues = selectedAssetPeriod === 'custom'
    ? getCustomTrendValues(assetDateRange)
    : ASSET_TREND_DATA[selectedAssetPeriod]?.values || ASSET_TREND_DATA['1m'].values
  const assetTrendSummary = selectedAssetPeriod === 'custom'
    ? `${assetDateRange.start || '시작일'} ~ ${assetDateRange.end || '종료일'}`
    : ASSET_TREND_DATA[selectedAssetPeriod]?.description || ASSET_TREND_DATA['1m'].description
  const assetTrendDelta = selectedAssetPeriod === 'custom'
    ? '+₩235,400'
    : ASSET_TREND_DATA[selectedAssetPeriod]?.delta || ASSET_TREND_DATA['1m'].delta

  const handleAssetPeriodChange = (periodKey) => {
    setSelectedAssetPeriod(periodKey)
    setAssetDateRange(getAssetPeriodRange(periodKey))
  }

  const handleAssetDateChange = (field, value) => {
    setSelectedAssetPeriod('custom')
    setAssetDateRange((prev) => ({ ...prev, [field]: value }))
  }

  // 투자 성향 가이드 텍스트 매퍼
  const getProfileDescription = (profile) => {
    switch (profile) {
      case '안정형': return '원금 보존이 최우선이며 안전 자산 위주로 포트폴리오를 구성합니다.'
      case '안정추구형': return '원금 손실을 최소화하면서 예적금보다 약간 높은 수익을 기대합니다.'
      case '위험중립형': return '안정성과 수익성을 균형 있게 추구하며 적절한 위험을 감수합니다.'
      case '적극투자형': return '높은 수익을 위해 상당한 위험을 감수하며 투자 자산 비중이 높습니다.'
      case '공격투자형': return '매우 높은 수익을 기대하며 자산 손실 위험을 적극적으로 감수합니다.'
      default: return '설문 조사를 통해 본인의 상세 투자 성향을 측정할 수 있습니다.'
    }
  }

  return (
    <div className="min-h-screen bg-obsidian-bg text-[#e2e2ec] font-inter">
      <div className="flex min-h-screen flex-col lg:flex-row">
        <SidebarNav
          activeTab={activeTab}
          isOpen={isSidebarOpen}
          onClose={() => setIsSidebarOpen(false)}
          onOpen={() => setIsSidebarOpen(true)}
          onTabChange={setActiveTab}
        />

        <div className={`min-w-0 flex-1 px-6 py-8 ${!isSidebarOpen ? 'pt-20 lg:pt-8' : ''}`}>
          {/* 공통 통합 헤더 네비게이션 */}
          <Header isLoggedIn={isLoggedIn} userEmail={userEmail} handleLogout={handleLogout} userProfile={userProfile} />

          {/* 메인 레이아웃 2단 그리드 */}
          {activeTab === 'dashboard' && (
            <main className="max-w-7xl mx-auto flex flex-col gap-6">

              {/* 자산 요약 카드 */}
              <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                <div className="bg-slate-surface border border-slate-700/80 rounded-lg p-5">
                  <span className="text-xs font-bold text-slate-400">총 평가 자산 (KRW)</span>
                  <div className="text-xl font-bold font-mono text-white mt-1">
                    {balance ? `₩${balance.total_evaluation.toLocaleString()}` : '₩0'}
                  </div>
                </div>

                <div className="bg-slate-surface border border-slate-700/80 rounded-lg p-5">
                  <span className="text-xs font-bold text-slate-400">가용 예수금 (Cash)</span>
                  <div className="text-xl font-bold font-mono text-white mt-1">
                    {balance ? `₩${balance.available_cash.toLocaleString()}` : '₩0'}
                  </div>
                </div>

                <div className="bg-slate-surface border border-slate-700/80 rounded-lg p-5">
                  <span className="text-xs font-bold text-slate-400">포트폴리오 수익률</span>
                  <div className="mt-1">
                    <Rate value={balance && balance.holdings.length > 0 ? '+1.45%' : '0.00%'} />
                  </div>
                </div>
              </div>

              <section className="grid grid-cols-1 gap-6 xl:grid-cols-[minmax(0,1.45fr)_minmax(320px,0.55fr)]">
                {/* 총 자산 가치 그래프 (Sparkline) */}
                <div className="bg-slate-surface border border-slate-700/80 rounded-lg p-5 flex flex-col gap-3">
                  <div className="mb-1 flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                    <div>
                      <p className="text-[10px] font-bold uppercase tracking-[0.16em] text-ai-cyan">Portfolio Trend</p>
                      <h2 className="text-sm font-bold text-white uppercase tracking-wider">자산 가치 변화 추이 (예시)</h2>
                    </div>
                    <button
                      className={`rounded border px-2 py-1 text-[10px] font-bold transition-all ${
                        isAssetCalendarOpen
                          ? 'border-ai-cyan bg-ai-cyan/10 text-ai-cyan'
                          : 'border-slate-700 text-slate-400 hover:border-ai-cyan hover:text-white'
                      }`}
                      type="button"
                      onClick={() => setIsAssetCalendarOpen((prev) => !prev)}
                    >
                      기간 변경
                    </button>
                  </div>
                  <div className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
                    <div>
                      <p className="text-2xl font-bold text-white font-mono">{balance ? `₩${balance.total_evaluation.toLocaleString()}` : '₩5,109,700'}</p>
                      <p className="text-[11px] text-slate-400 mt-1">
                        {assetTrendSummary} <span className="text-emerald-400 font-bold font-mono">{assetTrendDelta}</span>
                      </p>
                    </div>
                    <div className="flex gap-1.5 text-[10px] font-bold text-slate-400">
                      {ASSET_PERIOD_OPTIONS.map((item) => (
                        <button
                          key={item.key}
                          className={`rounded border px-2.5 py-1 cursor-pointer transition-all ${
                            selectedAssetPeriod === item.key
                              ? 'border-ai-cyan/30 bg-ai-cyan/10 text-ai-cyan'
                              : 'border-transparent bg-[#0f172a] text-slate-400 hover:bg-slate-800 hover:text-white'
                          }`}
                          type="button"
                          onClick={() => handleAssetPeriodChange(item.key)}
                        >
                          {item.label}
                        </button>
                      ))}
                    </div>
                  </div>
                  {isAssetCalendarOpen ? (
                    <div className="grid gap-2 rounded border border-slate-800 bg-[#0f172a] p-3 sm:grid-cols-[1fr_auto_1fr] sm:items-center">
                      <input
                        className="h-10 rounded border border-slate-700 bg-transparent px-3 font-mono text-xs text-slate-200 outline-none [color-scheme:dark] focus:border-ai-cyan"
                        type="date"
                        value={assetDateRange.start}
                        onChange={(event) => handleAssetDateChange('start', event.target.value)}
                      />
                      <span className="hidden text-slate-600 sm:block">-</span>
                      <input
                        className="h-10 rounded border border-slate-700 bg-transparent px-3 font-mono text-xs text-slate-200 outline-none [color-scheme:dark] focus:border-ai-cyan"
                        type="date"
                        value={assetDateRange.end}
                        onChange={(event) => handleAssetDateChange('end', event.target.value)}
                      />
                    </div>
                  ) : null}
                  <div className="mt-2 rounded border border-slate-800 bg-[#0f172a]/60 p-4">
                    <Sparkline values={assetTrendValues} />
                  </div>
                </div>

                {/* AI Profile (유저 실제 투자 성향 연동) */}
                <div className="ai-glass rounded-lg p-6 flex flex-col gap-4">
                  <SectionHeader eyebrow="AI Profile" title="나의 투자 성향 분석" />
                  {isLoggedIn && userProfile ? (
                    <div className="rounded-lg border border-ai-cyan/20 bg-[#0c0e15]/60 p-4">
                      <p className="text-base font-extrabold text-white">
                        당신은 <span className="text-ai-cyan">{userProfile.invest_type || '미정'}</span> 성향입니다.
                      </p>
                      <div className="mt-2 text-xs text-slate-400 flex justify-between">
                        <span>진단 점수:</span>
                        <span className="font-bold text-white">{userProfile.invest_score || 0} / 50점</span>
                      </div>
                      <p className="mt-3 text-xs leading-5 text-slate-300 border-t border-slate-800/80 pt-3">
                        {getProfileDescription(userProfile.invest_type)}
                      </p>
                    </div>
                  ) : (
                    <div className="grid min-h-40 place-items-center rounded border border-slate-800 bg-[#0c0e15]/40 p-5 text-center text-xs text-slate-400">
                      로그인 후 투자 성향 진단을 완료하시면 성향 맞춤형 포트폴리오 관리가 제공됩니다.
                    </div>
                  )}
                </div>
              </section>

              {/* 자산 배분 상태 및 관심 종목 그리드 */}
              <div className="grid grid-cols-1 md:grid-cols-12 gap-6">

                {/* 자산 배분 상태 (Allocation) */}
                <div className="bg-slate-surface border border-slate-700/80 rounded-lg p-5 md:col-span-5 flex flex-col gap-4">
                  <SectionHeader title="자산 배분 상태" />
                  <div className="flex h-3.5 overflow-hidden rounded-full bg-[#0c0e15] border border-slate-800">
                    {allocation.map((item) => (
                      <span key={item.id} className={`${item.color} h-full transition-all`} style={{ width: `${item.value}%` }} />
                    ))}
                  </div>
                  <div className="flex flex-col gap-2">
                    {allocation.map((item) => (
                      <div key={item.id} className="flex items-center justify-between rounded bg-[#0c0e15]/40 px-3 py-2 border border-slate-800/40 text-xs">
                        <span className="flex items-center gap-2 font-bold">
                          <span className={`w-2 h-2 rounded-full ${item.color}`} />
                          {item.label}
                        </span>
                        <span className="font-mono font-bold text-slate-300">{item.value}%</span>
                      </div>
                    ))}
                  </div>
                </div>

                {/* 관심 종목 명단 */}
                <div className="bg-slate-surface border border-slate-700/80 rounded-lg p-5 md:col-span-7 flex flex-col gap-3">
                  <div className="mb-1 flex items-start justify-between gap-3">
                    <h2 className="text-sm font-bold text-white uppercase tracking-wider">관심 종목 명단 (시세 모니터링)</h2>
                    <button
                      className="rounded border border-slate-700 px-2 py-1 text-[10px] font-bold text-slate-400 transition-all hover:border-ai-cyan hover:text-white"
                      type="button"
                      onClick={() => setActiveTab('watchlist')}
                    >
                      관리
                    </button>
                  </div>
                  <div className="overflow-x-auto max-h-[180px] overflow-y-auto">
                    <table className="w-full border-collapse text-xs">
                      <thead className="border-b border-slate-800 text-slate-400 bg-[#0c0e15]/50 sticky top-0">
                        <tr>
                          <th className="px-3 py-2 text-left font-bold">종목명</th>
                          <th className="px-3 py-2 text-left font-bold">시장</th>
                          <th className="px-3 py-2 text-right font-bold">평균가</th>
                          <th className="px-3 py-2 text-right font-bold">등락률</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-slate-800/40">
                        {WATCHLIST_MOCK.map((item) => (
                          <tr key={item.id} className="hover:bg-slate-800/20 transition-colors">
                            <td className="px-3 py-2.5 font-bold text-white">{item.name}</td>
                            <td className="px-3 py-2.5 text-slate-400">{item.market}</td>
                            <td className="px-3 py-2.5 text-right font-mono text-slate-300">{item.average}</td>
                            <td className="px-3 py-2.5 text-right"><Rate value={item.change} /></td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>

              </div>

              {/* 보유 재산 현황 (실제 holdings 연동 테이블) */}
              <div className="bg-slate-surface border border-slate-700/80 rounded-lg p-6 flex flex-col gap-4">
                <div className="flex justify-between items-center border-b border-slate-800 pb-2">
                  <h2 className="text-sm font-bold text-white flex items-center gap-2 uppercase tracking-wider">
                    <span className="w-2 h-2 rounded bg-indigo-500" />
                    Held Positions (보유 주식 자산 현황)
                  </h2>
                  {encrypted && (
                    <button
                      onClick={refreshBalance}
                      disabled={loading}
                      className="text-xs border border-slate-700 hover:border-slate-500 rounded px-2.5 py-1 text-slate-300 font-medium transition-all cursor-pointer disabled:opacity-50"
                    >
                      {loading ? 'LOADING...' : 'REFRESH'}
                    </button>
                  )}
                </div>

                {balance && balance.holdings.length > 0 ? (
                  <div className="overflow-x-auto">
                    <table className="w-full text-left border-collapse text-xs">
                      <thead>
                        <tr className="border-b border-slate-800 text-slate-400 bg-[#0c0e15]/30">
                          <th className="py-2 px-3 font-bold">종목명/코드</th>
                          <th className="py-2 px-3 text-right font-bold">보유수량</th>
                          <th className="py-2 px-3 text-right font-bold">평균단가</th>
                          <th className="py-2 px-3 text-right font-bold">현재가</th>
                          <th className="py-2 px-3 text-right font-bold">평가손익</th>
                          <th className="py-2 px-3 text-right font-bold">수익률</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-slate-800 font-mono">
                        {balance.holdings.map((stock) => (
                          <tr key={stock.symbol} className="hover:bg-slate-800/40 transition-colors">
                            <td className="py-3 px-3 font-sans">
                              <div className="font-semibold text-white">{stock.name}</div>
                              <div className="text-[10px] text-slate-500 font-mono">{stock.symbol}</div>
                            </td>
                            <td className="py-3 px-3 text-right text-slate-300">{stock.qty}</td>
                            <td className="py-3 px-3 text-right text-slate-300">₩{stock.avg_price.toLocaleString()}</td>
                            <td className="py-3 px-3 text-right text-slate-100">₩{stock.current_price.toLocaleString()}</td>
                            <td className={`py-3 px-3 text-right font-semibold ${stock.profit >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                              {stock.profit >= 0 ? '+' : ''}₩{stock.profit.toLocaleString()}
                            </td>
                            <td className={`py-3 px-3 text-right font-semibold`}>
                              <Rate value={(stock.profit_rate >= 0 ? '+' : '') + stock.profit_rate.toFixed(2) + '%'} />
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                ) : (
                  <div className="flex-1 flex flex-col justify-center items-center py-16 text-center">
                    <svg className="w-12 h-12 text-slate-600 mb-3" fill="none" stroke="currentColor" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.5" d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z"></path>
                    </svg>
                    <p className="text-xs font-semibold text-slate-400">대시보드 자산 데이터가 비활성화되어 있습니다.</p>
                    <p className="text-[11px] text-slate-500 mt-1 max-w-sm">백엔드에서 계좌 자산 데이터가 연결되면 보유 종목과 평가 손익이 표시됩니다.</p>
                  </div>
                )}
              </div>
            </main>
          )}

          {activeTab === 'watchlist' && <WatchlistTab />}
          {activeTab === 'assets' && <AssetsTab balance={balance} allocation={allocation} />}
          {activeTab === 'history' && <TradeHistoryTab />}
          {activeTab === 'settings' && (
            <Settings
              isLoggedIn={isLoggedIn}
              userEmail={userEmail}
              handleLogout={handleLogout}
              userProfile={userProfile}
              hideHeader={true}
            />
          )}
        </div>
      </div>
    </div>
  )
}
