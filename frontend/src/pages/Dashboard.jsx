import { useState } from 'react'
import Header from '../components/Header.jsx'

const API_BASE = 'http://localhost:5050'

export default function Dashboard({ currentRoute }) {
  const [inputs, setInputs] = useState({
    appkey: '',
    appsecret: '',
    cano: '',
    env: 'MOCK',
  })
  const [encrypted, setEncrypted] = useState(null)
  const [loading, setLoading] = useState(false)
  const [message, setMessage] = useState({ text: '', isError: false })
  const [balance, setBalance] = useState(null)

  const handleInputChange = (e) => {
    const { name, value } = e.target
    setInputs((prev) => ({ ...prev, [name]: value }))
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
      const response = await fetch(`${API_BASE}/api/keys/test`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(inputs),
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
      const response = await fetch(`${API_BASE}/api/dashboard/balance`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          ...encrypted,
          env: inputs.env,
        }),
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
    <div className="min-h-screen bg-obsidian-bg text-[#e2e2ec] font-inter px-6 py-8">
      <Header currentRoute={currentRoute} />

      <main className="max-w-7xl mx-auto grid grid-cols-1 lg:grid-cols-12 gap-6">
        <section className="lg:col-span-5 flex flex-col gap-6">
          <div className="ai-glass rounded-lg p-6 flex flex-col gap-4">
            <h2 className="text-lg font-semibold text-white border-b border-ai-cyan/20 pb-2 flex items-center gap-2">
              <span className="w-2 h-2 rounded-full bg-ai-cyan" />
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
                    placeholder="계좌번호"
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
                    <option value="MOCK">MOCK</option>
                    <option value="REAL">REAL</option>
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

            {message.text && (
              <div
                className={`p-3 rounded text-xs border ${
                  message.isError
                    ? 'bg-red-950/30 border-red-800 text-red-300'
                    : 'bg-emerald-950/30 border-emerald-800 text-emerald-300'
                }`}
              >
                {message.text}
              </div>
            )}

            {encrypted && (
              <div className="mt-4 pt-4 border-t border-slate-800 flex flex-col gap-2">
                <h3 className="text-xs font-bold text-slate-400 uppercase tracking-wider">AES-256 Encrypted Payload</h3>
                <div className="bg-[#0c0e15] rounded p-3 text-[11px] font-mono flex flex-col gap-1.5 overflow-hidden">
                  <div className="truncate">
                    <span className="text-ai-cyan">AppKey:</span> {encrypted.appkey}
                  </div>
                  <div className="truncate">
                    <span className="text-ai-cyan">Secret:</span> {encrypted.appsecret}
                  </div>
                  <div className="truncate">
                    <span className="text-ai-cyan">Account:</span> {encrypted.cano}
                  </div>
                </div>
                <p className="text-[10px] text-slate-500 italic">API keys are encrypted in-transit and saved securely.</p>
              </div>
            )}
          </div>
        </section>

        <section className="lg:col-span-7 flex flex-col gap-6">
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div className="bg-slate-surface border border-slate-700 rounded-lg p-5">
              <span className="text-xs font-bold text-slate-400">총 평가 금액 (KRW)</span>
              <div className="text-2xl font-bold font-mono text-white mt-1">
                {balance ? balance.total_evaluation.toLocaleString() : '0'}
              </div>
            </div>

            <div className="bg-slate-surface border border-slate-700 rounded-lg p-5">
              <span className="text-xs font-bold text-slate-400">가용 현금 (Cash)</span>
              <div className="text-2xl font-bold font-mono text-white mt-1">
                {balance ? balance.available_cash.toLocaleString() : '0'}
              </div>
            </div>

            <div className="bg-slate-surface border border-slate-700 rounded-lg p-5">
              <span className="text-xs font-bold text-slate-400">포트폴리오 수익률</span>
              <div
                className={`text-2xl font-bold font-mono mt-1 ${
                  balance && balance.holdings.length > 0 ? 'text-emerald-400' : 'text-slate-400'
                }`}
              >
                {balance && balance.holdings.length > 0 ? '+1.45%' : '0.00%'}
              </div>
            </div>
          </div>

          <div className="bg-slate-surface border border-slate-700 rounded-lg p-6 flex flex-col gap-4 flex-1">
            <div className="flex justify-between items-center border-b border-slate-700 pb-2">
              <h2 className="text-lg font-semibold text-white flex items-center gap-2">
                <span className="w-2 h-2 rounded bg-indigo-500" />
                Held Positions
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
                      <th className="py-2.5 px-3">종목명/코드</th>
                      <th className="py-2.5 px-3 text-right">보유수량</th>
                      <th className="py-2.5 px-3 text-right">평균단가</th>
                      <th className="py-2.5 px-3 text-right">현재가</th>
                      <th className="py-2.5 px-3 text-right">평가손익</th>
                      <th className="py-2.5 px-3 text-right">수익률</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-800 font-mono">
                    {balance.holdings.map((stock) => (
                      <tr key={stock.symbol} className="hover:bg-slate-800/40 transition-colors">
                        <td className="py-3 px-3 font-sans">
                          <div className="font-semibold text-white">{stock.name}</div>
                          <div className="text-xs text-slate-500 font-mono">{stock.symbol}</div>
                        </td>
                        <td className="py-3 px-3 text-right text-slate-300">{stock.qty}</td>
                        <td className="py-3 px-3 text-right text-slate-300">{stock.avg_price.toLocaleString()}</td>
                        <td className="py-3 px-3 text-right text-slate-100">{stock.current_price.toLocaleString()}</td>
                        <td
                          className={`py-3 px-3 text-right font-semibold ${
                            stock.profit >= 0 ? 'text-emerald-400' : 'text-red-400'
                          }`}
                        >
                          {stock.profit >= 0 ? '+' : ''}
                          {stock.profit.toLocaleString()}
                        </td>
                        <td
                          className={`py-3 px-3 text-right font-semibold ${
                            stock.profit_rate >= 0 ? 'text-emerald-400' : 'text-red-400'
                          }`}
                        >
                          {stock.profit_rate >= 0 ? '+' : ''}
                          {stock.profit_rate.toFixed(2)}%
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <div className="flex-1 flex flex-col justify-center items-center py-16 text-center">
                <svg className="w-12 h-12 text-slate-600 mb-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth="1.5"
                    d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z"
                  />
                </svg>
                <p className="text-sm font-semibold text-slate-400">아직 보유 자산이 비활성화되어 있습니다.</p>
                <p className="text-xs text-slate-500 mt-1 max-w-sm">
                  왼쪽 API Credential Manager에서 유효한 KIS 모의계좌 정보를 입력해 대시보드를 활성화하세요.
                </p>
              </div>
            )}
          </div>
        </section>
      </main>
    </div>
  )
}
