import { useState } from 'react'
import { TRADE_HISTORY_MOCK } from '../dashboardConstants.js'

export default function TradeHistoryTab() {
  const tradeHistory = TRADE_HISTORY_MOCK
  const [selectedTrade, setSelectedTrade] = useState(null)
  const [selectedExchange, setSelectedExchange] = useState('ALL')
  const [tradeSearchQuery, setTradeSearchQuery] = useState('')
  const [isMoreFiltersOpen, setIsMoreFiltersOpen] = useState(false)
  const [selectedTradeSide, setSelectedTradeSide] = useState('ALL')
  const [selectedTradeStatus, setSelectedTradeStatus] = useState('ALL')
  const [dateRange, setDateRange] = useState({
    start: '2026-06-21',
    end: '2026-06-23',
  })
  const exchangeTone = {
    TOSS: 'border-blue-500/40 bg-blue-500/15 text-blue-300',
    KIS: 'border-rose-500/40 bg-rose-500/15 text-rose-300',
    COINONE: 'border-sky-500/40 bg-sky-500/15 text-sky-300',
    BINANCE: 'border-yellow-400/40 bg-yellow-400/15 text-yellow-300',
  }
  const filteredTrades = tradeHistory.filter((trade) => {
    const query = tradeSearchQuery.trim().toLowerCase()
    const searchMatched = !query
      || trade.symbolName.toLowerCase().includes(query)
      || trade.ticker.toLowerCase().includes(query)
      || trade.exchange.toLowerCase().includes(query)
    const exchangeMatched = selectedExchange === 'ALL' || trade.exchange === selectedExchange
    const startMatched = !dateRange.start || trade.date >= dateRange.start
    const endMatched = !dateRange.end || trade.date <= dateRange.end
    const sideMatched = selectedTradeSide === 'ALL' || trade.side === selectedTradeSide
    const statusMatched = selectedTradeStatus === 'ALL' || trade.status === selectedTradeStatus

    return searchMatched && exchangeMatched && startMatched && endMatched && sideMatched && statusMatched
  })

  return (
    <main className="relative max-w-7xl mx-auto flex flex-col gap-3">
      <section className="rounded-lg border border-slate-700 bg-slate-surface/90 p-2">
        <div className="flex flex-col gap-2 lg:flex-row lg:items-center lg:justify-between">
          <div className="flex flex-1 flex-col gap-2 md:flex-row md:items-center">
            <label className="flex h-10 min-w-52 items-center gap-2 rounded border border-slate-700 bg-[#0f172a] px-3 text-sm text-slate-500">
              <span>⌕</span>
              <input
                className="w-full bg-transparent text-slate-200 outline-none placeholder:text-slate-500"
                placeholder="Search Ticker..."
                type="text"
                value={tradeSearchQuery}
                onChange={(event) => setTradeSearchQuery(event.target.value)}
              />
            </label>
            <div className="flex h-10 items-center gap-2 rounded border border-slate-700 bg-[#0f172a] px-3 text-sm font-bold text-slate-300">
              <input
                className="w-32 bg-transparent font-mono text-xs text-slate-200 outline-none [color-scheme:dark]"
                type="date"
                value={dateRange.start}
                onChange={(event) => setDateRange((prev) => ({ ...prev, start: event.target.value }))}
              />
              <span className="text-slate-600">-</span>
              <input
                className="w-32 bg-transparent font-mono text-xs text-slate-200 outline-none [color-scheme:dark]"
                type="date"
                value={dateRange.end}
                onChange={(event) => setDateRange((prev) => ({ ...prev, end: event.target.value }))}
              />
            </div>
            <div className="flex flex-wrap items-center gap-2 text-sm text-slate-400">
              <span>Exchange:</span>
              {['ALL', 'TOSS', 'KIS', 'COINONE', 'BINANCE'].map((item) => (
                <button
                  key={item}
                  className={`rounded px-3 py-2 text-xs font-bold transition ${selectedExchange === item
                      ? 'bg-ai-cyan text-[#07111f]'
                      : 'bg-slate-700/70 text-slate-200 hover:bg-slate-600'
                    }`}
                  type="button"
                  onClick={() => setSelectedExchange(item)}
                >
                  {item}
                </button>
              ))}
            </div>
          </div>
          <button
            className={`h-10 rounded border px-4 text-sm font-bold transition ${
              isMoreFiltersOpen
                ? 'border-ai-cyan bg-ai-cyan/10 text-ai-cyan'
                : 'border-slate-700 bg-[#0f172a] text-slate-200 hover:border-ai-cyan'
            }`}
            type="button"
            onClick={() => setIsMoreFiltersOpen((prev) => !prev)}
          >
            More Filters
          </button>
        </div>
        {isMoreFiltersOpen ? (
          <div className="mt-3 flex justify-end border-t border-slate-800 pt-3">
            <div className="w-full rounded border border-slate-800 bg-[#0f172a] p-3 md:max-w-2xl">
              <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="w-10 text-xs font-bold text-slate-500">구분</span>
                  {['ALL', '매수', '매도'].map((item) => (
                    <button
                      key={item}
                      className={`rounded px-3 py-1.5 text-xs font-bold transition ${
                        selectedTradeSide === item
                          ? 'bg-ai-cyan text-[#07111f]'
                          : 'bg-slate-700/70 text-slate-200 hover:bg-slate-600'
                      }`}
                      type="button"
                      onClick={() => setSelectedTradeSide(item)}
                    >
                      {item === 'ALL' ? '전체' : item}
                    </button>
                  ))}
                </div>
                <div className="flex flex-wrap items-center gap-2">
                  <span className="w-10 text-xs font-bold text-slate-500">상태</span>
                  {['ALL', '체결완료', '미체결'].map((item) => (
                    <button
                      key={item}
                      className={`rounded px-3 py-1.5 text-xs font-bold transition ${
                        selectedTradeStatus === item
                          ? 'bg-ai-cyan text-[#07111f]'
                          : 'bg-slate-700/70 text-slate-200 hover:bg-slate-600'
                      }`}
                      type="button"
                      onClick={() => setSelectedTradeStatus(item)}
                    >
                      {item === 'ALL' ? '전체' : item}
                    </button>
                  ))}
                </div>
              </div>
            </div>
          </div>
        ) : null}
      </section>

      <section className="bg-slate-surface border border-slate-700/80 rounded-lg overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full min-w-[1040px] border-collapse text-sm">
            <thead className="border-b border-slate-700 bg-slate-800/70 text-xs text-slate-300">
              <tr>
                {['일시 (Date)', '거래소 (Exchange)', '종목명 (Asset/Ticker)', '구분 (Side)', '체결가 (Price)', '수량 (Qty)', '정산금액 (Total)', '상태 (Status)'].map((head) => (
                  <th key={head} className="px-4 py-3 text-left font-bold">{head}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {filteredTrades.map((trade) => (
                <tr
                  key={trade.id}
                  className="cursor-pointer border-b border-slate-700/70 last:border-b-0 hover:bg-white/[0.04]"
                  onClick={() => setSelectedTrade(trade)}
                >
                  <td className="px-4 py-4 font-mono text-xs text-slate-300">{trade.date.replaceAll('-', '.')} {trade.time}</td>
                  <td className="px-4 py-4">
                    <span className={`rounded border px-2 py-1 text-xs font-black ${exchangeTone[trade.exchange] || 'border-slate-600 bg-slate-700 text-slate-200'}`}>
                      {trade.exchange}
                    </span>
                  </td>
                  <td className="px-4 py-4">
                    <p className="font-bold text-white">{trade.symbolName}</p>
                    <p className="mt-1 text-xs text-slate-500 font-mono">{trade.ticker}</p>
                  </td>
                  <td className="px-4 py-4">
                    <span className={`font-bold ${trade.side === '매수'
                        ? 'text-emerald-300'
                        : 'text-rose-300'
                      }`}>
                      {trade.side} {trade.side === '매수' ? '(Buy)' : '(Sell)'}
                    </span>
                  </td>
                  <td className="px-4 py-4 font-mono font-bold text-slate-100">{trade.price}</td>
                  <td className="px-4 py-4 font-mono font-bold text-slate-100">{trade.quantity}</td>
                  <td className="px-4 py-4 font-mono font-bold text-slate-100">{trade.amount}</td>
                  <td className="px-4 py-4">
                    <span className={`rounded-full px-3 py-1 text-xs font-bold ${trade.status === '체결완료'
                        ? 'bg-slate-600/60 text-slate-200'
                        : 'border border-slate-600 bg-slate-700/30 text-slate-200'
                      }`}>
                      {trade.status}{trade.status === '미체결' ? ' (Pending)' : ''}
                    </span>
                  </td>
                </tr>
              ))}
              {filteredTrades.length === 0 && (
                <tr>
                  <td className="px-4 py-12 text-center text-sm text-slate-500" colSpan={8}>
                    선택한 조건에 맞는 거래 내역이 없습니다.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </section>

      {selectedTrade && (
        <div className="fixed inset-0 z-50 flex justify-end">
          <button className="flex-1 bg-black/55 backdrop-blur-[1px]" type="button" aria-label="거래 상세 닫기" onClick={() => setSelectedTrade(null)} />
          <aside className="h-full w-full max-w-md border-l border-slate-700 bg-[#0f172a] shadow-2xl">
            <div className="flex items-center justify-between border-b border-slate-700 px-6 py-6">
              <h2 className="text-lg font-extrabold text-white">거래 상세 내역</h2>
              <button className="grid h-8 w-8 place-items-center rounded text-2xl text-slate-300 hover:bg-white/5 hover:text-white" type="button" aria-label="닫기" onClick={() => setSelectedTrade(null)}>
                ×
              </button>
            </div>

            <div className="space-y-6 p-6">
              <div className="rounded-lg border border-slate-700 bg-slate-800/70 p-4">
                <div className="flex items-center justify-between gap-4">
                  <div className="flex items-center gap-4">
                    <div className="grid h-11 w-11 place-items-center rounded-lg border border-slate-600 bg-[#0f172a] text-lg font-bold text-ai-cyan">
                      {selectedTrade.symbolName.slice(0, 1)}
                    </div>
                    <div>
                      <p className="text-lg font-extrabold text-white">{selectedTrade.symbolName}</p>
                      <p className="mt-1 text-xs font-mono text-slate-400">{selectedTrade.ticker}</p>
                    </div>
                  </div>
                  <div className="text-right">
                    <p className="font-bold text-white">지정가 {selectedTrade.side}</p>
                    <span className={`mt-2 inline-flex rounded-full px-3 py-1 text-xs font-bold ${selectedTrade.status === '체결완료' ? 'bg-emerald-400/15 text-emerald-300' : 'bg-slate-700 text-slate-200'
                      }`}>
                      {selectedTrade.status}
                    </span>
                  </div>
                </div>
              </div>

              <dl className="space-y-4 border-t border-slate-700 pt-5 text-sm">
                {[
                  ['체결 단가 (Execution Price)', selectedTrade.price],
                  ['수량 (Quantity)', selectedTrade.quantity],
                  ['주문 금액 (Total Amount)', selectedTrade.amount],
                  ['적용 환율 (Exchange Rate)', selectedTrade.exchangeRate],
                  ['수수료 (Fees)', selectedTrade.fees],
                ].map(([label, value]) => (
                  <div key={label} className="flex items-center justify-between gap-4">
                    <dt className="font-bold text-slate-400">{label}</dt>
                    <dd className="font-mono font-bold text-slate-100">{value}</dd>
                  </div>
                ))}
              </dl>

              <div className="flex items-center justify-between rounded-lg border border-slate-700 bg-slate-800/70 px-4 py-3">
                <span className="font-extrabold text-white">총 정산 금액</span>
                <span className="font-mono text-2xl font-extrabold text-emerald-300">{selectedTrade.amount}</span>
              </div>

              <dl className="space-y-2 border-t border-slate-800 pt-4 text-xs text-slate-500">
                <div className="flex items-center justify-between">
                  <dt>주문 일시</dt>
                  <dd className="font-mono">{selectedTrade.date} {selectedTrade.time}</dd>
                </div>
                <div className="flex items-center justify-between">
                  <dt>주문 번호</dt>
                  <dd className="font-mono">{selectedTrade.orderNumber}</dd>
                </div>
                <div className="flex items-center justify-between">
                  <dt>거래소</dt>
                  <dd className="font-mono">{selectedTrade.exchange}</dd>
                </div>
              </dl>
            </div>
          </aside>
        </div>
      )}
    </main>
  )
}
