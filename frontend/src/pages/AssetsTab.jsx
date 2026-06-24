import { ASSET_ACCOUNTS_MOCK, FALLBACK_HOLDINGS } from '../dashboardConstants.js'
import { Rate, SectionHeader } from '../components/DashboardComponents.jsx'

export default function AssetsTab({ balance, allocation }) {
  const displayAccounts = ASSET_ACCOUNTS_MOCK.map((account) => {
    if (account.id !== 'krw-stock' || !balance) return account

    return {
      ...account,
      balance: `₩${(balance.available_cash || 0).toLocaleString()}`,
    }
  })
  const holdings = balance?.holdings?.length
    ? balance.holdings.map((stock) => ({
      id: stock.symbol,
      name: stock.name,
      account: /[a-zA-Z]/.test(stock.symbol) ? '해외 주식' : '국내 주식',
      quantity: `${stock.qty}`,
      average: `₩${stock.avg_price.toLocaleString()}`,
      returnRate: `${stock.profit_rate >= 0 ? '+' : ''}${stock.profit_rate.toFixed(2)}%`,
    }))
    : FALLBACK_HOLDINGS

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
                {['투자종목 명', '계좌 종류', '수량', '평균단가', '수익률'].map((head) => (
                  <th key={head} className="px-5 py-3 text-left font-bold">{head}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {holdings.map((item) => (
                <tr key={item.id} className="border-b border-slate-800/80 last:border-b-0">
                  <td className="px-5 py-4 font-bold text-white">{item.name}</td>
                  <td className="px-5 py-4 text-slate-300">{item.account}</td>
                  <td className="px-5 py-4 font-mono">{item.quantity}</td>
                  <td className="px-5 py-4 font-mono">{item.average}</td>
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
