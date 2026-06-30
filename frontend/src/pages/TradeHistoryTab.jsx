import { useState, useEffect } from 'react'
import { supabase } from '../supabaseClient'

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:5050'

const formatNumber = (value, options = {}) => {
  const numericValue = Number(value)
  if (!Number.isFinite(numericValue)) return '-'
  return numericValue.toLocaleString('ko-KR', options)
}

const formatCurrency = (value, currency = 'KRW') => {
  const numericValue = Number(value)
  if (!Number.isFinite(numericValue)) return '-'
  const prefix = currency === 'USD' ? '$' : '₩'
  return `${prefix}${formatNumber(numericValue, {
    minimumFractionDigits: currency === 'USD' ? 2 : 0,
    maximumFractionDigits: currency === 'USD' ? 2 : 0,
  })}`
}

const mapTradeStatus = (status) => {
  const normalizedStatus = String(status || '').toUpperCase()
  if (['PENDING', 'APPROVED'].includes(normalizedStatus)) return '미체결'
  if (normalizedStatus === 'EXECUTED') return '체결완료'
  if (normalizedStatus === 'REJECTED') return '거절'
  if (normalizedStatus === 'FAILED') return '실패'
  if (normalizedStatus === 'CANCELED') return '취소완료'
  if (normalizedStatus === 'MODIFIED') return '미체결'
  return normalizedStatus || '-'
}

const mapTradeSide = (side) => (String(side || '').toUpperCase() === 'SELL' ? '매도' : '매수')

const TRADE_HISTORY_SELECT_FIELDS = 'id,exchange,asset_type,ticker,symbol,side,price,volume,order_amount,ord_type,market_country,currency,broker_env,client_order_id,external_order_id,external_order_org_no,status,failure_reason,created_at'

const isCancelReplaceExchange = (exchange) => ['COINONE', 'BINANCE'].includes(String(exchange || '').toUpperCase())

const fetchSymbolDisplayNames = async (proposals = []) => {
  const symbols = Array.from(new Set(
    proposals
      .map((proposal) => String(proposal.symbol || proposal.ticker || '').trim().toUpperCase())
      .filter(Boolean),
  ))

  if (symbols.length === 0) return {}

  const pairs = await Promise.all(
    symbols.map(async (symbol) => {
      try {
        const response = await fetch(`${API_BASE_URL}/api/symbol/lookup?query=${encodeURIComponent(symbol)}`)
        const payload = await response.json()
        const displayName = payload?.success ? payload.data?.display_name : ''
        return [symbol, displayName || symbol]
      } catch {
        return [symbol, symbol]
      }
    }),
  )

  return Object.fromEntries(pairs)
}

const hydrateTradeProposals = async (proposals = []) => {
  const symbolNameMap = await fetchSymbolDisplayNames(proposals)
  return proposals.map((proposal) => {
    const symbol = String(proposal.symbol || proposal.ticker || '').trim().toUpperCase()
    return {
      ...proposal,
      display_name: symbolNameMap[symbol] || symbol || proposal.symbol || proposal.ticker,
    }
  })
}

const mapProposalToTrade = (proposal) => {
  const createdAt = proposal.created_at ? new Date(proposal.created_at) : null
  const isValidDate = createdAt && !Number.isNaN(createdAt.getTime())
  const date = isValidDate ? createdAt.toISOString().slice(0, 10) : '-'
  const time = isValidDate
    ? createdAt.toLocaleTimeString('ko-KR', {
      hour12: false,
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
    })
    : '-'
  const currency = proposal.currency || (proposal.exchange === 'BINANCE' ? 'USD' : 'KRW')
  const price = proposal.price ?? null
  const quantity = proposal.volume ?? null
  const computedAmount = proposal.order_amount ?? (
    price !== null && quantity !== null ? Number(price) * Number(quantity) : null
  )
  const ticker = proposal.symbol || proposal.ticker || '-'
  const displayName = proposal.display_name || ticker

  return {
    id: proposal.id,
    rawStatus: proposal.status,
    brokerEnv: proposal.broker_env || 'REAL',
    orderOrgNo: proposal.external_order_org_no || '',
    marketCountry: proposal.market_country || '',
    rawPrice: price,
    rawQuantity: quantity,
    date,
    time,
    exchange: proposal.exchange || '-',
    symbolName: displayName,
    ticker,
    side: mapTradeSide(proposal.side),
    currency,
    price: price === null ? '-' : formatCurrency(price, currency),
    quantity: quantity === null ? '-' : formatNumber(quantity, { maximumFractionDigits: 8 }),
    amount: computedAmount === null ? '-' : formatCurrency(computedAmount, currency),
    status: mapTradeStatus(proposal.status),
    exchangeRate: '-',
    fees: '-',
    orderNumber: proposal.external_order_id || proposal.client_order_id || proposal.id,
  }
}

export default function TradeHistoryTab() {
  const [tradeHistory, setTradeHistory] = useState([])
  const [loading, setLoading] = useState(true)
  const [tradeError, setTradeError] = useState('')
  const [actionNotice, setActionNotice] = useState('')
  const [actionLoadingId, setActionLoadingId] = useState('')
  const [modifyDraft, setModifyDraft] = useState({ price: '', quantity: '' })
  const [isModifyPanelOpen, setIsModifyPanelOpen] = useState(false)
  const [selectedTrade, setSelectedTrade] = useState(null)
  const [selectedExchange, setSelectedExchange] = useState('ALL')
  const [tradeSearchQuery, setTradeSearchQuery] = useState('')
  const [isMoreFiltersOpen, setIsMoreFiltersOpen] = useState(false)
  const [selectedTradeSide, setSelectedTradeSide] = useState('ALL')
  const [selectedTradeStatus, setSelectedTradeStatus] = useState('ALL')
  const [dateRange, setDateRange] = useState({
    start: '',
    end: '',
  })
  const exchangeTone = {
    TOSS: 'border-blue-500/40 bg-blue-500/15 text-blue-300',
    KIS: 'border-rose-500/40 bg-rose-500/15 text-rose-300',
    COINONE: 'border-sky-500/40 bg-sky-500/15 text-sky-300',
    BINANCE: 'border-yellow-400/40 bg-yellow-400/15 text-yellow-300', 
  }

  useEffect(() => {
    let ignore = false
    let channel = null

    const loadTradeHistory = async () => {
      setLoading(true)
      setTradeError('')

      const { data: { session }, error: sessionError } = await supabase.auth.getSession()
      if (sessionError || !session?.user?.id) {
        if (!ignore) {
          setTradeHistory([])
          setTradeError('로그인 세션을 확인할 수 없습니다.')
          setLoading(false)
        }
        return
      }

      const { data, error } = await supabase
        .from('trade_proposals')
        .select(TRADE_HISTORY_SELECT_FIELDS)
        .order('created_at', { ascending: false })

      if (ignore) return

      if (error) {
        setTradeHistory([])
        setTradeError('거래내역을 불러오지 못했습니다. 잠시 후 다시 시도해 주세요.')
      } else {
        const hydratedRows = await hydrateTradeProposals(data || [])
        setTradeHistory(hydratedRows.map(mapProposalToTrade))
      }
      setLoading(false)
    }

    const subscribeTradeHistory = async () => {
      const { data: { session } } = await supabase.auth.getSession()
      if (!session?.user?.id || ignore) return

      channel = supabase
        .channel(`trade-history-${session.user.id}`)
        .on(
          'postgres_changes',
          {
            event: '*',
            schema: 'public',
            table: 'trade_proposals',
            filter: `user_id=eq.${session.user.id}`,
          },
          () => {
            loadTradeHistory()
          },
        )
        .subscribe()
    }

    loadTradeHistory()
    subscribeTradeHistory()

    return () => {
      ignore = true
      if (channel) {
        supabase.removeChannel(channel)
      }
    }
  }, [])

  const handleOpenModify = (trade) => {
    setSelectedTrade(trade)
    setModifyDraft({
      price: trade.rawPrice ?? '',
      quantity: trade.marketCountry === 'US' ? '' : (trade.rawQuantity ?? ''),
    })
    setIsModifyPanelOpen(true)
    setActionNotice('')
  }

  const getPrimaryActionLabel = (trade) => (
    isCancelReplaceExchange(trade.exchange) ? '취소 후 재주문' : '주문 정정'
  )

  const getAuthHeader = async () => {
    const { data: { session } } = await supabase.auth.getSession()
    if (!session?.access_token) {
      throw new Error('로그인 세션을 확인할 수 없습니다.')
    }
    return `Bearer ${session.access_token}`
  }

  const refreshTradeHistory = async () => {
    const { data, error } = await supabase
      .from('trade_proposals')
      .select(TRADE_HISTORY_SELECT_FIELDS)
      .order('created_at', { ascending: false })

    if (error) throw error
    const hydratedRows = await hydrateTradeProposals(data || [])
    const nextTrades = hydratedRows.map(mapProposalToTrade)
    setTradeHistory(nextTrades)
    if (selectedTrade) {
      const nextSelectedTrade = nextTrades.find((trade) => trade.id === selectedTrade.id)
      setSelectedTrade(nextSelectedTrade || null)
    }
  }

  const requestOrderAction = async (endpoint, body) => {
    const authHeader = await getAuthHeader()
    const response = await fetch(`${API_BASE_URL}${endpoint}`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: authHeader,
      },
      body: JSON.stringify(body),
    })
    const payload = await response.json().catch(() => ({}))
    if (!response.ok || !payload.success) {
      throw new Error(payload.message || '주문 처리 요청에 실패했습니다.')
    }
    return payload
  }

  const handleOpenCancel = async (trade) => {
    setSelectedTrade(trade)
    const confirmed = window.confirm(`${trade.ticker} ${trade.side} 주문을 취소할까요?`)
    if (!confirmed) return

    setActionLoadingId(`cancel-${trade.id}`)
    setActionNotice('')
    try {
      const payload = await requestOrderAction('/api/trade/order/cancel', {
        proposal_id: trade.id,
        broker_env: trade.brokerEnv,
      })
      setActionNotice(payload.message || '주문 취소 요청이 완료되었습니다.')
      await refreshTradeHistory()
    } catch (error) {
      setActionNotice(error.message)
    } finally {
      setActionLoadingId('')
    }
  }

  const handleSubmitModify = async () => {
    if (!selectedTrade) return
    const price = String(modifyDraft.price).trim()
    const quantity = String(modifyDraft.quantity).trim()
    if (!price && !quantity) {
      setActionNotice('정정할 가격 또는 수량을 입력해 주세요.')
      return
    }

    setActionLoadingId(`modify-${selectedTrade.id}`)
    setActionNotice('')
    try {
      const isCancelReplace = isCancelReplaceExchange(selectedTrade.exchange)
      const payload = await requestOrderAction(
        isCancelReplace ? '/api/trade/order/cancel-replace' : '/api/trade/order/modify',
        {
        proposal_id: selectedTrade.id,
        broker_env: selectedTrade.brokerEnv,
        price: price || undefined,
        quantity: quantity || undefined,
        },
      )
      setActionNotice(payload.message || (isCancelReplace ? '취소 후 재주문 요청이 완료되었습니다.' : '주문 정정 요청이 완료되었습니다.'))
      setIsModifyPanelOpen(false)
      await refreshTradeHistory()
    } catch (error) {
      setActionNotice(error.message)
    } finally {
      setActionLoadingId('')
    }
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
      {actionNotice ? (
        <section className="rounded-lg border border-ai-cyan/30 bg-ai-cyan/10 px-4 py-3 text-sm font-bold text-ai-cyan">
          <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
            <span>{actionNotice}</span>
            <button
              className="h-8 rounded border border-ai-cyan/40 px-3 text-xs text-slate-100 transition hover:bg-ai-cyan/10"
              type="button"
              onClick={() => setActionNotice('')}
            >
              닫기
            </button>
          </div>
        </section>
      ) : null}

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
                  {['ALL', '체결완료', '미체결', '취소완료', '거절', '실패'].map((item) => (
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
              {!loading && !tradeError && filteredTrades.map((trade) => (
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
                    <div className="flex flex-col items-start gap-2">
                      <span className={`rounded-full px-3 py-1 text-xs font-bold ${trade.status === '체결완료'
                        ? 'bg-slate-600/60 text-slate-200'
                        : 'border border-slate-600 bg-slate-700/30 text-slate-200'
                      }`}>
                        {trade.status}{trade.status === '미체결' ? ' (Pending)' : ''}
                      </span>
                      {trade.status === '미체결' ? (
                        <div className="flex flex-wrap gap-2">
                          <button
                            className="rounded border border-ai-cyan/40 px-2.5 py-1 text-xs font-bold text-ai-cyan transition hover:bg-ai-cyan/10 disabled:cursor-not-allowed disabled:opacity-50"
                            type="button"
                            disabled={Boolean(actionLoadingId)}
                            onClick={(event) => {
                              event.stopPropagation()
                              handleOpenModify(trade)
                            }}
                          >
                            {getPrimaryActionLabel(trade)}
                          </button>
                          <button
                            className="rounded border border-rose-400/40 px-2.5 py-1 text-xs font-bold text-rose-300 transition hover:bg-rose-400/10 disabled:cursor-not-allowed disabled:opacity-50"
                            type="button"
                            disabled={Boolean(actionLoadingId)}
                            onClick={(event) => {
                              event.stopPropagation()
                              handleOpenCancel(trade)
                            }}
                          >
                            {actionLoadingId === `cancel-${trade.id}` ? '취소 중' : '주문 취소'}
                          </button>
                        </div>
                      ) : null}
                    </div>
                  </td>
                </tr>
              ))}
              {loading && (
                <tr>
                  <td className="px-4 py-12 text-center text-sm text-slate-500" colSpan={8}>
                    거래내역을 불러오는 중입니다.
                  </td>
                </tr>
              )}
              {!loading && tradeError && (
                <tr>
                  <td className="px-4 py-12 text-center text-sm text-rose-300" colSpan={8}>
                    {tradeError}
                  </td>
                </tr>
              )}
              {!loading && !tradeError && filteredTrades.length === 0 && (
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

              {selectedTrade.status === '미체결' ? (
                <div className="space-y-3">
                  <div className="grid grid-cols-2 gap-2">
                    <button
                      className="h-11 rounded border border-ai-cyan/40 bg-ai-cyan/10 text-sm font-extrabold text-ai-cyan transition hover:bg-ai-cyan/15 disabled:cursor-not-allowed disabled:opacity-50"
                      type="button"
                      disabled={Boolean(actionLoadingId)}
                      onClick={() => handleOpenModify(selectedTrade)}
                    >
                      {getPrimaryActionLabel(selectedTrade)}
                    </button>
                    <button
                      className="h-11 rounded border border-rose-400/40 bg-rose-400/10 text-sm font-extrabold text-rose-300 transition hover:bg-rose-400/15 disabled:cursor-not-allowed disabled:opacity-50"
                      type="button"
                      disabled={Boolean(actionLoadingId)}
                      onClick={() => handleOpenCancel(selectedTrade)}
                    >
                      {actionLoadingId === `cancel-${selectedTrade.id}` ? '취소 중' : '주문 취소'}
                    </button>
                  </div>

                  {isModifyPanelOpen ? (
                    <div className="rounded-lg border border-ai-cyan/20 bg-ai-cyan/[0.04] p-3">
                      <div className="grid gap-2">
                        <label className="grid gap-1 text-xs font-bold text-slate-400">
                          {isCancelReplaceExchange(selectedTrade.exchange) ? '재주문 가격' : '정정 가격'}
                          <input
                            className="h-10 rounded border border-slate-700 bg-[#0f172a] px-3 font-mono text-sm text-slate-100 outline-none transition focus:border-ai-cyan"
                            inputMode="decimal"
                            placeholder={isCancelReplaceExchange(selectedTrade.exchange) ? '재주문 가격' : '가격'}
                            type="text"
                            value={modifyDraft.price}
                            onChange={(event) => setModifyDraft((prev) => ({ ...prev, price: event.target.value }))}
                          />
                        </label>
                        {selectedTrade.marketCountry !== 'US' ? (
                          <label className="grid gap-1 text-xs font-bold text-slate-400">
                            {isCancelReplaceExchange(selectedTrade.exchange) ? '재주문 수량' : '정정 수량'}
                            <input
                              className="h-10 rounded border border-slate-700 bg-[#0f172a] px-3 font-mono text-sm text-slate-100 outline-none transition focus:border-ai-cyan"
                              inputMode="decimal"
                              placeholder={isCancelReplaceExchange(selectedTrade.exchange) ? '재주문 수량' : '수량'}
                              type="text"
                              value={modifyDraft.quantity}
                              onChange={(event) => setModifyDraft((prev) => ({ ...prev, quantity: event.target.value }))}
                            />
                          </label>
                        ) : (
                          <p className="text-xs font-bold text-slate-500">Toss 해외주식은 가격 정정만 지원합니다.</p>
                        )}
                      </div>
                      <div className="mt-3 grid grid-cols-2 gap-2">
                        <button
                          className="h-10 rounded border border-ai-cyan/40 bg-ai-cyan/10 text-sm font-extrabold text-ai-cyan transition hover:bg-ai-cyan/15 disabled:cursor-not-allowed disabled:opacity-50"
                          type="button"
                          disabled={Boolean(actionLoadingId)}
                          onClick={handleSubmitModify}
                        >
                          {actionLoadingId === `modify-${selectedTrade.id}`
                            ? (isCancelReplaceExchange(selectedTrade.exchange) ? '재주문 중' : '정정 중')
                            : (isCancelReplaceExchange(selectedTrade.exchange) ? '재주문 요청' : '정정 요청')}
                        </button>
                        <button
                          className="h-10 rounded border border-slate-700 bg-[#0f172a] text-sm font-bold text-slate-300 transition hover:border-slate-500"
                          type="button"
                          onClick={() => setIsModifyPanelOpen(false)}
                        >
                          취소
                        </button>
                      </div>
                    </div>
                  ) : null}
                </div>
              ) : null}

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
