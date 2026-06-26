import { useState } from 'react'
import { Link } from 'react-router-dom'
import { ASSET_ACCOUNTS_MOCK, FALLBACK_HOLDINGS } from '../dashboardConstants.js'
import { Rate, SectionHeader } from '../components/DashboardComponents.jsx'

export default function AssetsTab({ balance, allocation, displayCurrency = 'KRW', exchangeRate = 1500, showMockAssets = true }) {
  const [sortConfig, setSortConfig] = useState({ key: null, direction: 'asc' })

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
          val = balance.available_cash || 0
          currency = balance.currency || 'KRW'
        }
      } else if (account.id === 'usd-stock') {
        if (balance.currency === 'USD') {
          val = balance.available_cash || 0
          currency = 'USD'
        }
      }
    }

    const accCurrency = balance.currency || 'KRW'
    return {
      ...account,
      balance: formatCurrency(val, currency),
    }
  })
  const rawHoldings = balance?.holdings?.length
    ? balance.holdings.map((stock) => {
      const isForeign = /[a-zA-Z]/.test(stock.symbol)
      const stockCurrency = stock.currency || (isForeign ? 'USD' : 'KRW')
      const currentDisplayCurrency = isForeign ? displayCurrency : 'KRW'
      const exchangeName = stock.exchange || stock.account_type || (isForeign ? 'TOSS' : 'KIS')
      return {
        id: stock.symbol,
        name: stock.name,
        exchange: exchangeName,
        quantity: `${stock.qty}`,
        average: formatCurrency(stock.avg_price, stockCurrency, currentDisplayCurrency),
        profit: formatCurrency(stock.profit, stockCurrency, currentDisplayCurrency),
        returnRate: `${stock.profit_rate >= 0 ? '+' : ''}${stock.profit_rate.toFixed(2)}%`,
      }
    })
    : FALLBACK_HOLDINGS.map((stock) => {
      const isForeign = /[a-zA-Z]/.test(stock.id || stock.symbol || '') || stock.account.includes('해외') || stock.account.includes('코인')
      const stockCurrency = isForeign ? 'USD' : 'KRW'
      const rawAvg = parseFloat(stock.average.replace(/[^0-9.-]/g, '')) || 0
      const currentDisplayCurrency = isForeign ? displayCurrency : 'KRW'
      const returnRateNum = parseFloat(stock.returnRate.replace(/[^0-9.-]/g, '')) || 0
      const qtyNum = parseFloat(stock.quantity.replace(/[^0-9.-]/g, '')) || 0
      const mockProfit = (rawAvg * qtyNum * returnRateNum) / 100
      const exchangeName = stock.account.includes('코인') ? 'COINONE' : (isForeign ? 'TOSS' : 'KIS')
      return {
        ...stock,
        exchange: exchangeName,
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
              </tr>
            </thead>
            <tbody>
              {sortedHoldings.map((item) => (
                <tr key={item.id} className="border-b border-slate-800/80 last:border-b-0 hover:bg-slate-800/20">
                  <td className="px-5 py-4 font-bold text-white">
                    <Link to={`/asset/STOCK/${item.id}`} className="text-blue-400 hover:text-blue-300 hover:underline">
                      {item.name}
                    </Link>
                  </td>
                  <td className="px-5 py-4 font-sans font-bold text-slate-400">
                    <span className="rounded bg-slate-800/60 border border-slate-700/60 px-1.5 py-0.5 text-[10px] uppercase">
                      {item.exchange}
                    </span>
                  </td>
                  <td className="px-5 py-4 font-mono">{item.quantity}</td>
                  <td className="px-5 py-4 font-mono">{item.average}</td>
                  <td className={`px-5 py-4 font-mono font-semibold ${parseNumeric(item.profit) >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                    {parseNumeric(item.profit) >= 0 ? '+' : ''}{item.profit}
                  </td>
                  <td className="px-5 py-4"><Rate value={item.returnRate} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </main>
  )
}
