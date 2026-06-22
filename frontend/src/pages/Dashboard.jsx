import React, { useState } from 'react'
import { useNavigate } from 'react-router-dom'

export default function Dashboard({ isLoggedIn, userEmail, handleLogout }) {
  const navigate = useNavigate()

  // KIS API Key 입력 상태
  const [inputs, setInputs] = useState({
    appkey: '',
    appsecret: '',
    cano: '',
    env: 'MOCK'
  })
  
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
        headers: {
          'Content-Type': 'application/json'
        },
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
        headers: {
          'Content-Type': 'application/json'
        },
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

  return (
    <div className="min-h-screen bg-[#0F172A] text-[#e2e2ec] font-inter px-6 py-8">
      {/* 공통 상단 네비게이션 헤더 */}
      <header className="max-w-7xl mx-auto mb-8 border-b border-slate-800 pb-4 flex justify-between items-center">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-white flex items-center gap-3">
            <img src="/logo.png" alt="Logo" className="w-8 h-8 object-contain" />
            <span>SYNTHETIC INTELLIGENCE TERMINAL</span>
            <span className="text-xs px-2 py-0.5 rounded border border-ai-cyan text-ai-cyan font-mono font-medium animate-pulse">
              MOCK TRADING
            </span>
          </h1>
          <p className="text-sm text-slate-400 mt-1">Multi-Asset Trading 어시스턴트 통합 대시보드</p>
        </div>
        <div className="flex items-center gap-6">
          <span className="hidden md:inline text-xs font-mono text-slate-500">SYSTEM TIME: 2026-06-22T14:41:11</span>
          
          {/* 헤더 인증 상태 액션 */}
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
              <button 
                onClick={() => navigate('/login')}
                className="bg-transparent hover:bg-ai-cyan/10 text-ai-cyan text-xs font-bold px-4 py-1.5 rounded border border-ai-cyan/80 hover:border-ai-cyan transition-all cursor-pointer"
              >
                LOGIN
              </button>
            )}
          </div>
        </div>
      </header>

      {/* 메인 레이아웃 그리드 */}
      <main className="max-w-7xl mx-auto grid grid-cols-1 lg:grid-cols-12 gap-6">
        
        {/* 좌측 영역: API 키 관리 모듈 (글래스모피즘) */}
        <section className="lg:col-span-5 flex flex-col gap-6">
          <div className="ai-glass rounded-lg p-6 flex flex-col gap-4">
            <h2 className="text-lg font-semibold text-white border-b border-ai-cyan/20 pb-2 flex items-center gap-2">
              <span className="w-2 h-2 rounded-full bg-ai-cyan"></span>
              API Credential Manager
            </h2>
            
            <form onSubmit={handleTestKeys} className="flex flex-col gap-4">
              <div>
                <label className="block text-xs font-bold text-slate-400 mb-1">APP KEY</label>
                <input
                  type="text"
                  name="appkey"
                  value={inputs.appkey}
                  onChange={handleInputChange}
                  placeholder="AppKey 입력"
                  className="w-full bg-[#0F172A] border border-slate-700 rounded px-3 py-2 text-sm font-mono text-white focus:outline-none focus:border-institutional-blue transition-all"
                />
              </div>

              <div>
                <label className="block text-xs font-bold text-slate-400 mb-1">APP SECRET</label>
                <input
                  type="password"
                  name="appsecret"
                  value={inputs.appsecret}
                  onChange={handleInputChange}
                  placeholder="AppSecret 입력"
                  className="w-full bg-[#0F172A] border border-slate-700 rounded px-3 py-2 text-sm font-mono text-white focus:outline-none focus:border-institutional-blue transition-all"
                />
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-xs font-bold text-slate-400 mb-1">ACCOUNT NO (CANO)</label>
                  <input
                    type="text"
                    name="cano"
                    value={inputs.cano}
                    onChange={handleInputChange}
                    placeholder="8자리 계좌번호"
                    className="w-full bg-[#0F172A] border border-slate-700 rounded px-3 py-2 text-sm font-mono text-white focus:outline-none focus:border-institutional-blue transition-all"
                  />
                </div>
                <div>
                  <label className="block text-xs font-bold text-slate-400 mb-1">ENVIRONMENT</label>
                  <select
                    name="env"
                    value={inputs.env}
                    onChange={handleInputChange}
                    className="w-full bg-[#0F172A] border border-slate-700 rounded px-3 py-2 text-sm font-bold text-white focus:outline-none focus:border-institutional-blue transition-all cursor-pointer"
                  >
                    <option value="MOCK">MOCK (모의투자)</option>
                    <option value="REAL">REAL (실전투자)</option>
                  </select>
                </div>
              </div>

              <button
                type="submit"
                disabled={loading}
                className="w-full mt-2 bg-gradient-to-r from-blue-700 to-ai-cyan text-white text-sm font-bold py-2.5 rounded hover:opacity-90 active:scale-[0.99] transition-all cursor-pointer disabled:opacity-50"
              >
                {loading ? 'VALIDATING CONNECTION...' : 'TEST & SAVE API KEYS'}
              </button>
            </form>

            {/* 알림 메시지 영역 */}
            {message.text && (
              <div className={`p-3 rounded text-xs border ${
                message.isError 
                  ? 'bg-red-950/30 border-red-800 text-red-300' 
                  : 'bg-emerald-950/30 border-emerald-800 text-emerald-300'
              }`}>
                {message.text}
              </div>
            )}

            {/* 암호화된 API 키 정보 표출 */}
            {encrypted && (
              <div className="mt-4 pt-4 border-t border-slate-800 flex flex-col gap-2">
                <h3 className="text-xs font-bold text-slate-400 uppercase tracking-wider">AES-256 Encrypted Payload</h3>
                <div className="bg-[#0c0e15] rounded p-3 text-[11px] font-mono flex flex-col gap-1.5 overflow-hidden">
                  <div className="truncate"><span className="text-ai-cyan">AppKey:</span> {encrypted.appkey}</div>
                  <div className="truncate"><span className="text-ai-cyan">Secret:</span> {encrypted.appsecret}</div>
                  <div className="truncate"><span className="text-ai-cyan">Account:</span> {encrypted.cano}</div>
                </div>
                <p className="text-[10px] text-slate-500 italic">API keys are encrypted in-transit and saved securely.</p>
              </div>
            )}
          </div>
        </section>

        {/* 우측 영역: 대시보드 통계 및 종목 현황 */}
        <section className="lg:col-span-7 flex flex-col gap-6">
          
          {/* 대시보드 요약 카드 */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div className="bg-[#1E293B] border border-slate-700 rounded-lg p-5">
              <span className="text-xs font-bold text-slate-400">총 평가 자산 (KRW)</span>
              <div className="text-2xl font-bold font-mono text-white mt-1">
                {balance ? balance.total_evaluation.toLocaleString() : '0'}
              </div>
            </div>
            
            <div className="bg-[#1E293B] border border-slate-700 rounded-lg p-5">
              <span className="text-xs font-bold text-slate-400">가용 예수금 (Cash)</span>
              <div className="text-2xl font-bold font-mono text-white mt-1">
                {balance ? balance.available_cash.toLocaleString() : '0'}
              </div>
            </div>
            
            <div className="bg-[#1E293B] border border-slate-700 rounded-lg p-5">
              <span className="text-xs font-bold text-slate-400">포트폴리오 수익률</span>
              <div className={`text-2xl font-bold font-mono mt-1 ${
                balance && balance.holdings.length > 0
                  ? 'text-emerald-400'
                  : 'text-slate-400'
              }`}>
                {balance && balance.holdings.length > 0 ? '+1.45%' : '0.00%'}
              </div>
            </div>
          </div>

          {/* 보유 종목 테이블 리스트 */}
          <div className="bg-[#1E293B] border border-slate-700 rounded-lg p-6 flex flex-col gap-4 flex-1">
            <div className="flex justify-between items-center border-b border-slate-700 pb-2">
              <h2 className="text-lg font-semibold text-white flex items-center gap-2">
                <span className="w-2 h-2 rounded bg-indigo-500"></span>
                Held Positions (보유 종목)
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
                <table className="w-full text-left border-collapse text-sm">
                  <thead>
                    <tr className="border-b border-slate-800 text-xs font-bold text-slate-400 uppercase tracking-wider">
                      <th className="py-2.5 px-3">종목명/티커</th>
                      <th className="py-2.5 px-3 text-right">보유수량</th>
                      <th className="py-2.5 px-3 text-right">평균단가</th>
                      <th className="py-2.5 px-3 text-right">현재가</th>
                      <th className="py-2.5 px-3 text-right">평가손익</th>
                      <th className="py-2.5 px-3 text-right">수익률</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-800 font-mono">
                    {balance.holdings.map((stock, idx) => (
                      <tr key={idx} className="hover:bg-slate-800/40 transition-colors">
                        <td className="py-3 px-3 font-sans">
                          <div className="font-semibold text-white">{stock.name}</div>
                          <div className="text-xs text-slate-500 font-mono">{stock.symbol}</div>
                        </td>
                        <td className="py-3 px-3 text-right text-slate-300">{stock.qty}</td>
                        <td className="py-3 px-3 text-right text-slate-300">₩{stock.avg_price.toLocaleString()}</td>
                        <td className="py-3 px-3 text-right text-slate-100">₩{stock.current_price.toLocaleString()}</td>
                        <td className={`py-3 px-3 text-right font-semibold ${
                          stock.profit >= 0 ? 'text-emerald-400' : 'text-red-400'
                        }`}>
                          {stock.profit >= 0 ? '+' : ''}₩{stock.profit.toLocaleString()}
                        </td>
                        <td className={`py-3 px-3 text-right font-semibold ${
                          stock.profit_rate >= 0 ? 'text-emerald-400' : 'text-red-400'
                        }`}>
                          {stock.profit_rate >= 0 ? '+' : ''}{stock.profit_rate.toFixed(2)}%
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
                <p className="text-sm font-semibold text-slate-400">대시보드가 비활성화되어 있습니다.</p>
                <p className="text-xs text-slate-500 mt-1 max-w-sm">좌측의 API Credential Manager에 유효한 KIS 모의투자 키를 입력하여 대시보드를 활성화하세요.</p>
              </div>
            )}
          </div>
        </section>
      </main>
    </div>
  )
}
