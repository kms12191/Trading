import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { supabase } from '../supabaseClient'
import { ASSET_ACCOUNTS_MOCK, FALLBACK_HOLDINGS } from '../dashboardConstants.js'
import { Rate, SectionHeader } from '../components/DashboardComponents.jsx'
import { getApiErrorMessage } from '../lib/apiError.js'

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:5050'
const TAG_REQUIRED_SYMBOLS = new Set(['XRP', 'XLM', 'EOS'])

export default function AssetsTab({ balance, allocation, displayCurrency = 'KRW', exchangeRate = 1500, showMockAssets = true }) {
  const [sortConfig, setSortConfig] = useState({ key: null, direction: 'asc' })
  const [withdrawAsset, setWithdrawAsset] = useState(null)
  const [withdrawForm, setWithdrawForm] = useState({
    amount: '',
    network: '',
    address: '',
    secondaryAddress: '',
    confirm: false,
  })
  const [withdrawPrecheck, setWithdrawPrecheck] = useState(null)
  const [withdrawMessage, setWithdrawMessage] = useState({ text: '', isError: false, detail: '' })
  const [withdrawLoading, setWithdrawLoading] = useState(false)
  const [withdrawSubmitting, setWithdrawSubmitting] = useState(false)
  const [transferRows, setTransferRows] = useState([])
  const [transferLoading, setTransferLoading] = useState(false)

  const parseNumeric = (val) => {
    if (typeof val === 'number') return val
    const text = String(val || '')
    const num = parseFloat(text.replace(/[^0-9.-]/g, ''))
    return Number.isFinite(num) ? num : 0
  }

  const handleSort = (key) => {
    let direction = 'asc'
    if (sortConfig.key === key && sortConfig.direction === 'asc') {
      direction = 'desc'
    }
    setSortConfig({ key, direction })
  }

  const getAuthHeader = async () => {
    const { data: { session } } = await supabase.auth.getSession()
    return session?.access_token ? `Bearer ${session.access_token}` : ''
  }

  const openWithdrawModal = (asset) => {
    setWithdrawAsset(asset)
    setWithdrawForm({
      amount: '',
      network: asset.id || asset.symbol || '',
      address: '',
      secondaryAddress: '',
      confirm: false,
    })
    setWithdrawPrecheck(null)
    setWithdrawMessage({ text: '', isError: false, detail: '' })
  }

  const closeWithdrawModal = () => {
    setWithdrawAsset(null)
    setWithdrawPrecheck(null)
    setWithdrawMessage({ text: '', isError: false, detail: '' })
  }

  const fetchTransferStatuses = async () => {
    const authHeader = await getAuthHeader()
    if (!authHeader) return
    setTransferLoading(true)
    try {
      const response = await fetch(`${API_BASE_URL}/api/transfer/withdraw/status?limit=10`, {
        headers: { Authorization: authHeader },
      })
      const payload = await response.json()
      if (response.ok && payload.success) {
        setTransferRows(payload.data || [])
      }
    } catch {
      // 상태 추적 실패는 자산 목록 표시를 막지 않습니다.
    } finally {
      setTransferLoading(false)
    }
  }

  useEffect(() => {
    if (withdrawAsset) {
      fetchTransferStatuses()
    }
  }, [withdrawAsset])

  const loadBinanceDepositAddress = async () => {
    if (!withdrawAsset) return
    const authHeader = await getAuthHeader()
    if (!authHeader) {
      setWithdrawMessage({ text: '로그인이 필요합니다.', isError: true, detail: '' })
      return
    }
    setWithdrawLoading(true)
    setWithdrawMessage({ text: '', isError: false, detail: '' })
    try {
      const params = new URLSearchParams({
        currency: withdrawAsset.id,
        network: withdrawForm.network || withdrawAsset.id,
      })
      const response = await fetch(`${API_BASE_URL}/api/transfer/binance/deposit-address?${params.toString()}`, {
        headers: { Authorization: authHeader },
      })
      const payload = await response.json()
      if (!response.ok || !payload.success) {
        throw payload
      }
      setWithdrawForm((prev) => ({
        ...prev,
        address: payload.data?.address || prev.address,
        secondaryAddress: payload.data?.tag || prev.secondaryAddress,
      }))
      setWithdrawMessage({ text: '바이낸스 입금 주소를 불러왔습니다.', isError: false, detail: '' })
    } catch (error) {
      const message = getApiErrorMessage(error, '바이낸스 입금 주소를 불러오지 못했습니다.')
      setWithdrawMessage({
        text: message.title,
        detail: message.detail,
        isError: true,
      })
    } finally {
      setWithdrawLoading(false)
    }
  }

  const runWithdrawPrecheck = async () => {
    if (!withdrawAsset) return
    const authHeader = await getAuthHeader()
    if (!authHeader) {
      setWithdrawMessage({ text: '로그인이 필요합니다.', isError: true, detail: '' })
      return
    }
    setWithdrawLoading(true)
    setWithdrawPrecheck(null)
    setWithdrawMessage({ text: '', isError: false, detail: '' })
    try {
      const response = await fetch(`${API_BASE_URL}/api/transfer/withdraw/precheck`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: authHeader,
        },
        body: JSON.stringify({
          currency: withdrawAsset.id,
          network: withdrawForm.network || withdrawAsset.id,
          amount: Number(withdrawForm.amount),
          address: withdrawForm.address,
          secondary_address: withdrawForm.secondaryAddress,
        }),
      })
      const payload = await response.json()
      if (!response.ok || !payload.success) {
        throw payload
      }
      setWithdrawPrecheck(payload.data)
      setWithdrawMessage({ text: '사전검증이 완료되었습니다. 주소와 수량을 다시 확인한 뒤 승인하세요.', isError: false, detail: '' })
    } catch (error) {
      const message = getApiErrorMessage(error, '출금 사전검증에 실패했습니다.')
      setWithdrawMessage({
        text: message.title,
        detail: message.detail,
        isError: true,
      })
    } finally {
      setWithdrawLoading(false)
    }
  }

  const approveWithdrawal = async () => {
    if (!withdrawAsset) return
    const authHeader = await getAuthHeader()
    if (!authHeader) {
      setWithdrawMessage({ text: '로그인이 필요합니다.', isError: true, detail: '' })
      return
    }
    if (!withdrawForm.confirm) {
      setWithdrawMessage({ text: '최종 승인 체크가 필요합니다.', isError: true, detail: '' })
      return
    }
    setWithdrawSubmitting(true)
    setWithdrawMessage({ text: '', isError: false, detail: '' })
    try {
      const response = await fetch(`${API_BASE_URL}/api/transfer/withdraw/approve`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: authHeader,
        },
        body: JSON.stringify({
          currency: withdrawAsset.id,
          network: withdrawForm.network || withdrawAsset.id,
          amount: Number(withdrawForm.amount),
          address: withdrawForm.address,
          secondary_address: withdrawForm.secondaryAddress,
          confirm: true,
        }),
      })
      const payload = await response.json()
      if (!response.ok || !payload.success) {
        throw payload
      }
      setWithdrawMessage({ text: `출금 요청이 접수되었습니다. 추적 ID: ${payload.proposal_id}`, isError: false, detail: '' })
      setWithdrawPrecheck(null)
      setWithdrawForm((prev) => ({ ...prev, confirm: false }))
      await fetchTransferStatuses()
    } catch (error) {
      const message = getApiErrorMessage(error, '출금 승인 처리에 실패했습니다.')
      setWithdrawMessage({
        text: message.title,
        detail: message.detail,
        isError: true,
      })
    } finally {
      setWithdrawSubmitting(false)
    }
  }

  const formatCurrency = (value, currency, targetDisplayCurrency = displayCurrency) => {
    const numeric = Number(value)
    const val = Number.isFinite(numeric) ? numeric : 0
    const rate = Number(exchangeRate) || 1500

    if (targetDisplayCurrency === 'KRW') {
      if (currency === 'USD' || currency === 'USDT') {
        return `₩${Math.round(val * rate).toLocaleString()}`
      }
      return `₩${Math.round(val).toLocaleString()}`
    }

    if (targetDisplayCurrency === 'USD') {
      if (currency === 'KRW') {
        return `$${(val / rate).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
      }
      return `$${val.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
    }

    if (currency === 'USD' || currency === 'USDT') {
      return `$${val.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
    }
    return `₩${Math.round(val).toLocaleString()}`
  }

  const displayAccounts = ASSET_ACCOUNTS_MOCK.map((account) => {
    let val = parseFloat(account.balance.replace(/[^0-9.-]/g, '')) || 0
    let currency = account.accountType === '달러' ? 'USD' : 'KRW'

    if (balance) {
      if (account.id === 'krw-stock') {
        if (balance.currency !== 'USD') {
          val = balance.available_cash ?? null
          currency = balance.currency || 'KRW'
        }
      } else if (account.id === 'usd-stock') {
        if (balance.currency === 'USD') {
          val = balance.available_cash ?? null
          currency = 'USD'
        }
      } else if (account.id === 'coin-wallet') {
        const cryptoHoldings = (balance.holdings || []).filter(h => ['COINONE', 'BINANCE', 'BINANCE_UM_FUTURES'].includes(String(h.raw_exchange || h.exchange || '').toUpperCase()))
        const cryptoEval = cryptoHoldings.reduce((sum, h) => {
          const evalAmount = parseNumeric(h.eval_amount)
          if (evalAmount > 0) return sum + evalAmount
          return sum + (Math.abs(parseNumeric(h.qty)) * parseNumeric(h.current_price))
        }, 0)
        // available_cash_breakdown에서 KRW 또는 USDT 등 가상자산에 묶인 현금자산 추출
        const krwCash = parseNumeric(balance.available_cash_breakdown?.KRW)
        const usdtCash = parseNumeric(balance.available_cash_breakdown?.USDT)
        const rate = Number(exchangeRate) || 1500
        val = cryptoEval + krwCash + (usdtCash * rate)
        currency = 'KRW'
      }
    }

    return {
      ...account,
      balance: val === null ? '-' : formatCurrency(val, currency),
    }
  })
  const rawHoldings = balance?.holdings?.length
    ? balance.holdings.map((stock, index) => {
      const exchangeName = stock.exchange || stock.account_type || '-'
      const isCoinone = String(exchangeName).toUpperCase() === 'COINONE'
      const isForeign = /[a-zA-Z]/.test(stock.symbol) && !/^[0-9a-zA-Z]{6,7}$/.test(stock.symbol) && !isCoinone
      const stockCurrency = stock.currency || (isForeign ? 'USD' : 'KRW')
      const currentDisplayCurrency = isForeign ? displayCurrency : 'KRW'
      const rawExchange = String(stock.raw_exchange || exchangeName || '').toUpperCase()
      const assetType = stock.asset_type || (['COINONE', 'BINANCE', 'BINANCE_UM_FUTURES'].includes(rawExchange) ? 'CRYPTO' : 'STOCK')
      const symbol = stock.symbol || stock.id || `holding-${index}`
      const profitRate = Number(stock.profit_rate)
      return {
        id: symbol,
        rowId: `${rawExchange || exchangeName}-${stock.env || 'REAL'}-${symbol}-${index}`,
        name: stock.name,
        exchange: exchangeName,
        assetType,
        source: stock.source || 'LIVE_BALANCE',
        quantity: `${stock.qty}`,
        average: formatCurrency(stock.avg_price, stockCurrency, currentDisplayCurrency),
        profit: formatCurrency(stock.profit, stockCurrency, currentDisplayCurrency),
        returnRate: `${profitRate >= 0 ? '+' : ''}${Number.isFinite(profitRate) ? profitRate.toFixed(2) : '0.00'}%`,
      }
    })
    : FALLBACK_HOLDINGS.map((stock) => {
      const isCoin = stock.account.includes('코인')
      const isForeign = ((/[a-zA-Z]/.test(stock.id || stock.symbol || '') && !/^[0-9a-zA-Z]{6,7}$/.test(stock.id || stock.symbol || '')) || stock.account.includes('해외')) && !isCoin
      const stockCurrency = isForeign ? 'USD' : 'KRW'
      const rawAvg = parseFloat(stock.average.replace(/[^0-9.-]/g, '')) || 0
      const currentDisplayCurrency = isForeign ? displayCurrency : 'KRW'
      const returnRateNum = parseFloat(stock.returnRate.replace(/[^0-9.-]/g, '')) || 0
      const qtyNum = parseFloat(stock.quantity.replace(/[^0-9.-]/g, '')) || 0
      const mockProfit = (rawAvg * qtyNum * returnRateNum) / 100
      const exchangeName = isCoin ? 'COINONE' : (isForeign ? 'TOSS' : 'KIS')
      return {
        ...stock,
        exchange: exchangeName,
        assetType: isCoin ? 'CRYPTO' : 'STOCK',
        source: 'MOCK',
        quantityNumeric: qtyNum,
        average: formatCurrency(rawAvg, stockCurrency, currentDisplayCurrency),
        profit: formatCurrency(mockProfit, stockCurrency, currentDisplayCurrency),
      }
    }).filter((stock) => showMockAssets || stock.exchange !== 'KIS')

  const holdings = rawHoldings

  const sortedHoldings = [...holdings].sort((a, b) => {
    if (!sortConfig.key) return 0
    let aVal = parseNumeric(a[sortConfig.key])
    let bVal = parseNumeric(b[sortConfig.key])
    return sortConfig.direction === 'asc' ? aVal - bVal : bVal - aVal
  })

  return (
    <main className="max-w-7xl mx-auto flex flex-col gap-6">
      <section className="bg-slate-surface border border-slate-700/80 rounded-lg p-5">
        <SectionHeader eyebrow="Private Asset" title="주식계좌 및 계좌번호" />
        <div className="grid gap-3">
          {displayAccounts.map((account) => (
            <div key={account.id} className="rounded-lg border border-slate-800 bg-[#0f172a] p-4">
              <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
                <div>
                  <div className="flex flex-wrap items-center gap-2">
                    <p className="font-bold text-white">{account.title}</p>
                    <span className="rounded-md bg-ai-cyan/10 px-2 py-1 text-xs font-bold text-ai-cyan">{account.accountType}</span>
                  </div>
                  <p className="mt-2 text-sm text-slate-400 font-mono">계좌번호 {account.maskedAccountNumber}</p>
                </div>
                <div className="md:text-right">
                  <p className="text-xs font-bold text-slate-500">{account.balanceLabel}</p>
                  <p className="mt-1 text-xl font-extrabold text-white font-mono">{account.balance}</p>
                </div>
              </div>
            </div>
          ))}
        </div>
      </section>

      <section className="bg-slate-surface border border-slate-700/80 rounded-lg p-5">
        <SectionHeader title="보유자산 현황 및 자산 배분 상태" />
        <div className="flex h-4 overflow-hidden rounded-full bg-[#0f172a]">
          {allocation.map((item) => (
            <span key={item.id} className={item.color} style={{ width: `${item.value}%` }} />
          ))}
        </div>
        <div className="mt-5 grid gap-3">
          {allocation.map((item) => (
            <div key={item.id} className="rounded-lg bg-[#0f172a] p-4">
              <div className="flex items-center justify-between gap-3">
                <span className="flex items-center gap-2 text-sm font-bold text-white">
                  <span className={`h-2 w-2 rounded-full ${item.color}`} />
                  {item.label}
                </span>
                <span className="font-mono font-bold text-slate-300">{item.value}%</span>
              </div>
              <div className="mt-3 h-2 rounded-full bg-white/5">
                <div className={`h-2 rounded-full ${item.color}`} style={{ width: `${item.value}%` }} />
              </div>
            </div>
          ))}
        </div>
      </section>

      <section className="bg-slate-surface border border-slate-700/80 rounded-lg overflow-hidden">
        <div className="p-5 pb-2">
          <SectionHeader title="투자종목 보유 현황" />
        </div>
        <div className="overflow-x-auto">
          <table className="w-full min-w-[760px] border-collapse text-sm">
            <thead className="border-y border-slate-800 bg-[#0f172a] text-xs text-slate-400">
              <tr>
                <th className="px-5 py-3 text-left font-bold">투자종목 명</th>
                <th className="px-5 py-3 text-left font-bold">거래소</th>
                <th className="px-5 py-3 text-left font-bold">
                  수량
                  <button onClick={() => handleSort('quantity')} className="inline-flex flex-col ml-1 align-middle text-[8px] leading-[6px] text-slate-500 hover:text-white cursor-pointer select-none">
                    <span className={sortConfig.key === 'quantity' && sortConfig.direction === 'asc' ? 'text-ai-cyan' : ''}>▲</span>
                    <span className={sortConfig.key === 'quantity' && sortConfig.direction === 'desc' ? 'text-ai-cyan' : ''}>▼</span>
                  </button>
                </th>
                <th className="px-5 py-3 text-left font-bold">평균단가</th>
                <th className="px-5 py-3 text-left font-bold">
                  평가손익
                  <button onClick={() => handleSort('profit')} className="inline-flex flex-col ml-1 align-middle text-[8px] leading-[6px] text-slate-500 hover:text-white cursor-pointer select-none">
                    <span className={sortConfig.key === 'profit' && sortConfig.direction === 'asc' ? 'text-ai-cyan' : ''}>▲</span>
                    <span className={sortConfig.key === 'profit' && sortConfig.direction === 'desc' ? 'text-ai-cyan' : ''}>▼</span>
                  </button>
                </th>
                <th className="px-5 py-3 text-left font-bold">
                  수익률
                  <button onClick={() => handleSort('returnRate')} className="inline-flex flex-col ml-1 align-middle text-[8px] leading-[6px] text-slate-500 hover:text-white cursor-pointer select-none">
                    <span className={sortConfig.key === 'returnRate' && sortConfig.direction === 'asc' ? 'text-ai-cyan' : ''}>▲</span>
                    <span className={sortConfig.key === 'returnRate' && sortConfig.direction === 'desc' ? 'text-ai-cyan' : ''}>▼</span>
                  </button>
                </th>
                <th className="px-5 py-3 text-right font-bold">자산 이동</th>
              </tr>
            </thead>
            <tbody>
              {sortedHoldings.map((item) => {
                const canWithdraw = String(item.exchange || '').toUpperCase() === 'COINONE'
                  && String(item.assetType || '').toUpperCase() === 'CRYPTO'
                  && item.source === 'LIVE_BALANCE'
                  && parseNumeric(item.quantity) > 0
                return (
                  <tr key={item.rowId || item.id} className="border-b border-slate-800/80 last:border-b-0 hover:bg-slate-800/20">
                    <td className="px-5 py-4 font-bold text-white">
                      <Link to={`/asset/${item.assetType || 'STOCK'}/${item.id}`} className="text-blue-400 hover:text-blue-300 hover:underline">
                        {item.name}
                      </Link>
                      <div className="text-[10px] text-slate-500 font-mono mt-0.5">{item.id}</div>
                    </td>
                    <td className="px-5 py-4 font-sans font-bold text-slate-400">
                      <span className="rounded bg-slate-800/60 border border-slate-700/60 px-1.5 py-0.5 text-[10px] uppercase">
                        {item.exchange}
                      </span>
                    </td>
                    <td className="px-5 py-4 font-mono">{item.quantity}</td>
                    <td className="px-5 py-4 font-mono">{item.average}</td>
                    <td className={`px-5 py-4 font-mono font-semibold ${parseNumeric(item.profit) > 0 ? 'text-red-400' : parseNumeric(item.profit) < 0 ? 'text-blue-400' : 'text-white'}`}>
                      {parseNumeric(item.profit) > 0 ? '+' : ''}{item.profit}
                    </td>
                    <td className="px-5 py-4"><Rate value={item.returnRate} /></td>
                    <td className="px-5 py-4 text-right">
                      {canWithdraw ? (
                        <button
                          type="button"
                          onClick={() => openWithdrawModal(item)}
                          className="rounded border border-amber-500/40 bg-amber-500/10 px-3 py-1.5 text-[11px] font-bold text-amber-200 transition hover:border-amber-300 hover:bg-amber-500/20"
                        >
                          바이낸스로 출금
                        </button>
                      ) : (
                        <span className="text-[10px] text-slate-600">-</span>
                      )}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      </section>

      {withdrawAsset ? (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/80 px-4 py-8 backdrop-blur-sm">
          <div className="max-h-[92vh] w-full max-w-4xl overflow-y-auto rounded-2xl border border-slate-700/80 bg-[#0b1220] p-5 shadow-2xl">
            <div className="flex flex-col gap-3 border-b border-slate-800 pb-4 sm:flex-row sm:items-start sm:justify-between">
              <div>
                <p className="text-[10px] font-bold uppercase tracking-[0.18em] text-amber-300">Coin Transfer</p>
                <h2 className="mt-1 text-lg font-bold text-white">
                  {withdrawAsset.id} 코인원 → 바이낸스 출금
                </h2>
                <p className="mt-1 text-xs leading-5 text-slate-400">
                  코인원 출금주소록에 등록되고 2차 인증이 완료된 주소만 출금됩니다. XRP/XLM/EOS는 Destination Tag/Memo가 필수입니다.
                </p>
              </div>
              <button
                type="button"
                onClick={closeWithdrawModal}
                className="rounded border border-slate-700 px-3 py-1.5 text-xs font-bold text-slate-300 transition hover:border-cyan-500/40 hover:text-white"
              >
                닫기
              </button>
            </div>

            <div className="mt-5 grid gap-4 lg:grid-cols-[1.1fr_0.9fr]">
              <div className="rounded-xl border border-slate-800 bg-[#0f172a] p-4">
                <div className="grid gap-3 sm:grid-cols-2">
                  <label className="flex flex-col gap-1.5 text-xs font-bold text-slate-300">
                    출금 수량
                    <input
                      type="number"
                      step="any"
                      value={withdrawForm.amount}
                      onChange={(e) => setWithdrawForm((prev) => ({ ...prev, amount: e.target.value, confirm: false }))}
                      placeholder={`최대 ${withdrawAsset.quantity}`}
                      className="rounded border border-slate-700 bg-[#070b19] px-3 py-2 font-mono text-sm text-white outline-none transition focus:border-cyan-400"
                    />
                  </label>
                  <label className="flex flex-col gap-1.5 text-xs font-bold text-slate-300">
                    네트워크
                    <input
                      type="text"
                      value={withdrawForm.network}
                      onChange={(e) => setWithdrawForm((prev) => ({ ...prev, network: e.target.value.toUpperCase(), confirm: false }))}
                      className="rounded border border-slate-700 bg-[#070b19] px-3 py-2 font-mono text-sm text-white outline-none transition focus:border-cyan-400"
                    />
                  </label>
                </div>

                <div className="mt-3 flex flex-col gap-1.5 text-xs font-bold text-slate-300">
                  <div className="flex items-center justify-between gap-2">
                    <span>바이낸스 입금 주소</span>
                    <button
                      type="button"
                      onClick={loadBinanceDepositAddress}
                      disabled={withdrawLoading}
                      className="rounded border border-slate-700 px-2 py-1 text-[10px] font-bold text-slate-300 transition hover:border-cyan-500/40 hover:text-white disabled:opacity-50"
                    >
                      {withdrawLoading ? '조회 중' : '주소 불러오기'}
                    </button>
                  </div>
                  <input
                    type="text"
                    value={withdrawForm.address}
                    onChange={(e) => setWithdrawForm((prev) => ({ ...prev, address: e.target.value, confirm: false }))}
                    placeholder="바이낸스 입금 주소"
                    className="rounded border border-slate-700 bg-[#070b19] px-3 py-2 font-mono text-xs text-white outline-none transition focus:border-cyan-400"
                  />
                </div>

                <label className="mt-3 flex flex-col gap-1.5 text-xs font-bold text-slate-300">
                  Destination Tag / Memo {TAG_REQUIRED_SYMBOLS.has(withdrawAsset.id) ? '(필수)' : '(선택)'}
                  <input
                    type="text"
                    value={withdrawForm.secondaryAddress}
                    onChange={(e) => setWithdrawForm((prev) => ({ ...prev, secondaryAddress: e.target.value, confirm: false }))}
                    placeholder="XRP 태그 또는 Memo"
                    className="rounded border border-slate-700 bg-[#070b19] px-3 py-2 font-mono text-sm text-white outline-none transition focus:border-cyan-400"
                  />
                </label>

                <div className="mt-4 flex flex-wrap gap-2">
                  <button
                    type="button"
                    onClick={runWithdrawPrecheck}
                    disabled={withdrawLoading}
                    className="rounded bg-cyan-500/90 px-4 py-2 text-xs font-extrabold text-slate-950 transition hover:bg-cyan-300 disabled:opacity-50"
                  >
                    {withdrawLoading ? '검증 중' : '사전검증'}
                  </button>
                  <button
                    type="button"
                    onClick={approveWithdrawal}
                    disabled={withdrawSubmitting || !withdrawPrecheck || !withdrawForm.confirm}
                    className="rounded border border-amber-400/70 bg-amber-400/10 px-4 py-2 text-xs font-extrabold text-amber-100 transition hover:bg-amber-400/20 disabled:cursor-not-allowed disabled:opacity-40"
                  >
                    {withdrawSubmitting ? '출금 요청 중' : '승인 후 출금'}
                  </button>
                </div>

                <label className="mt-4 flex items-start gap-2 rounded-lg border border-red-500/20 bg-red-500/10 p-3 text-xs leading-5 text-red-100">
                  <input
                    type="checkbox"
                    checked={withdrawForm.confirm}
                    onChange={(e) => setWithdrawForm((prev) => ({ ...prev, confirm: e.target.checked }))}
                    className="mt-1 accent-red-400"
                  />
                  <span>
                    주소, 네트워크, Destination Tag/Memo, 수량을 직접 확인했으며 승인 시 실제 코인원 출금 API가 호출됩니다.
                  </span>
                </label>

                {withdrawMessage.text ? (
                  <div className={`mt-3 rounded-lg border px-3 py-2 text-xs font-semibold ${
                    withdrawMessage.isError
                      ? 'border-red-500/30 bg-red-500/10 text-red-200'
                      : 'border-cyan-500/30 bg-cyan-500/10 text-cyan-100'
                  }`}>
                    <div>{withdrawMessage.text}</div>
                    {withdrawMessage.detail ? (
                      <div className="mt-1 text-[11px] font-medium leading-5 text-slate-200">
                        {withdrawMessage.detail}
                      </div>
                    ) : null}
                  </div>
                ) : null}
              </div>

              <div className="flex flex-col gap-4">
                <div className="rounded-xl border border-slate-800 bg-[#0f172a] p-4">
                  <h3 className="text-sm font-bold text-white">사전검증 결과</h3>
                  {withdrawPrecheck ? (
                    <div className="mt-3 space-y-2 text-xs text-slate-300">
                      <div className="flex justify-between gap-3">
                        <span className="text-slate-500">출금 가능 수량</span>
                        <span className="font-mono text-white">{withdrawPrecheck.available_qty} {withdrawPrecheck.currency}</span>
                      </div>
                      <div className="flex justify-between gap-3">
                        <span className="text-slate-500">주소 일치</span>
                        <span className={withdrawPrecheck.address_matches_binance ? 'text-emerald-300' : 'text-amber-300'}>
                          {withdrawPrecheck.address_matches_binance ? '일치' : '불일치/수동확인'}
                        </span>
                      </div>
                      <div className="flex justify-between gap-3">
                        <span className="text-slate-500">태그 일치</span>
                        <span className={withdrawPrecheck.tag_matches_binance ? 'text-emerald-300' : 'text-amber-300'}>
                          {withdrawPrecheck.tag_matches_binance ? '일치' : '불일치/수동확인'}
                        </span>
                      </div>
                      {withdrawPrecheck.warnings?.length ? (
                        <div className="rounded-lg border border-amber-500/20 bg-amber-500/10 p-3 text-amber-100">
                          {withdrawPrecheck.warnings.join(' / ')}
                        </div>
                      ) : null}
                    </div>
                  ) : (
                    <p className="mt-3 text-xs text-slate-500">사전검증 후 결과가 표시됩니다.</p>
                  )}
                </div>

                <div className="rounded-xl border border-slate-800 bg-[#0f172a] p-4">
                  <div className="flex items-center justify-between gap-2">
                    <h3 className="text-sm font-bold text-white">최근 출금 상태</h3>
                    <button
                      type="button"
                      onClick={fetchTransferStatuses}
                      disabled={transferLoading}
                      className="rounded border border-slate-700 px-2 py-1 text-[10px] font-bold text-slate-300 transition hover:border-cyan-500/40 hover:text-white disabled:opacity-50"
                    >
                      {transferLoading ? '갱신 중' : '상태 갱신'}
                    </button>
                  </div>
                  <div className="mt-3 max-h-56 overflow-y-auto space-y-2">
                    {transferRows.length > 0 ? transferRows.map((row) => (
                      <div key={row.id} className="rounded-lg border border-slate-800 bg-[#070b19] p-3 text-xs">
                        <div className="flex items-center justify-between gap-3">
                          <span className="font-mono font-bold text-white">{row.amount} {row.currency}</span>
                          <span className="rounded bg-slate-800 px-2 py-0.5 font-bold text-cyan-200">{row.status}</span>
                        </div>
                        <div className="mt-1 break-all text-[10px] text-slate-500">{row.external_transaction_id || row.id}</div>
                      </div>
                    )) : (
                      <p className="text-xs text-slate-500">최근 출금 요청이 없습니다.</p>
                    )}
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      ) : null}
    </main>
  )
}
