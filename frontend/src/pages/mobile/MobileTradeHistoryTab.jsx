import { useCallback, useEffect, useRef, useState } from 'react'
import { supabase } from '../../supabaseClient'
import { buildApiErrorText } from '../../lib/apiError.js'
import AssetLogo from '../../components/AssetLogo.jsx'
import {
  BROKER_HISTORY_SELECT_FIELDS,
  TRADE_EXCHANGE_LABELS,
  TRADE_EXCHANGE_OPTIONS,
  TRADE_HISTORY_SELECT_FIELDS,
  isCancelReplaceExchange,
  isDeletableTradeHistoryItem,
  isMissingBrokerHistoryTableError,
  mapBrokerHistoryToTrade,
  mapProposalToTrade,
  mapTransferToTrades,
  sortTradeHistoryRows,
} from '../tradeHistoryModel.js'

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:5050'

// 종목명 조회 결과는 거래내역 목록에서 반복 호출되지 않도록 파일 단위 캐시에 보관합니다.
const symbolDisplayNameCache = new Map()

const fetchSymbolDisplayNames = async (proposals = []) => {
  const symbols = Array.from(new Set(
    proposals
      .map((proposal) => String(proposal.symbol || proposal.ticker || '').trim().toUpperCase())
      .filter(Boolean),
  ))

  if (symbols.length === 0) return {}

  const cachedPairs = symbols
    .filter((symbol) => symbolDisplayNameCache.has(symbol))
    .map((symbol) => [symbol, symbolDisplayNameCache.get(symbol)])
  const uncachedSymbols = symbols.filter((symbol) => !symbolDisplayNameCache.has(symbol))

  const pairs = await Promise.all(
    uncachedSymbols.map(async (symbol) => {
      try {
        const response = await fetch(`${API_BASE_URL}/api/symbol/lookup?query=${encodeURIComponent(symbol)}`)
        const payload = await response.json()
        const displayName = payload?.success ? payload.data?.display_name : ''
        const resolvedName = displayName || symbol
        symbolDisplayNameCache.set(symbol, resolvedName)
        return [symbol, resolvedName]
      } catch {
        symbolDisplayNameCache.set(symbol, symbol)
        return [symbol, symbol]
      }
    }),
  )

  return Object.fromEntries([...cachedPairs, ...pairs])
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

export default function TradeHistoryTab({ mobileLayout = false }) {
  // 모바일 거래내역 탭은 체결/제안/출금 내역을 합쳐 필터링하고, 필요한 경우 주문 수정도 처리합니다.
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
  const realtimeRefreshTimerRef = useRef(null)
  const exchangeTone = {
    TOSS: 'border-blue-500/40 bg-blue-500/15 text-blue-300',
    KIS: 'border-rose-500/40 bg-rose-500/15 text-rose-300',
    COINONE: 'border-sky-500/40 bg-sky-500/15 text-sky-300',
    BINANCE: 'border-yellow-400/40 bg-yellow-400/15 text-yellow-300',
    BINANCE_UM_FUTURES: 'border-cyan-500/40 bg-cyan-500/15 text-cyan-300',
  }
  const mergeTrades = async (proposals = [], brokerOrders = [], transferRows = []) => {
    const hydratedRows = await hydrateTradeProposals(proposals)
    const brokerSymbolMap = await fetchSymbolDisplayNames(brokerOrders)
    return sortTradeHistoryRows([
      ...hydratedRows.map(mapProposalToTrade),
      ...brokerOrders.map((order) => mapBrokerHistoryToTrade(order, brokerSymbolMap)),
      ...transferRows.flatMap(mapTransferToTrades),
    ])
  }

  const fetchTransferHistory = async (authHeader) => {
    const response = await fetch(`${API_BASE_URL}/api/transfer/withdraw/status?limit=100`, {
      headers: {
        Authorization: authHeader,
      },
    })
    const payload = await response.json().catch(() => ({}))
    if (!response.ok || !payload.success) {
      throw new Error(buildApiErrorText(payload, '출금/입금 내역을 불러오지 못했습니다.'))
    }
    return Array.isArray(payload.data) ? payload.data : []
  }

  const getAuthHeader = useCallback(async () => {
    const { data: { session } } = await supabase.auth.getSession()
    if (!session?.access_token) {
      throw new Error('로그인 세션을 확인할 수 없습니다.')
    }
    return `Bearer ${session.access_token}`
  }, [])

  const syncTradeStatuses = useCallback(async () => {
    try {
      const authHeader = await getAuthHeader()
      await fetch(`${API_BASE_URL}/api/trade/orders/sync-status`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: authHeader,
        },
      })
    } catch {
      // 상태 동기화 실패는 거래내역 조회 자체를 막지 않습니다.
    }
  }, [getAuthHeader])

  useEffect(() => {
    let ignore = false
    let proposalChannel = null
    let brokerChannel = null
    let transferChannel = null

    const loadTradeHistory = async ({ runSync = false, showLoading = false } = {}) => {
      if (showLoading) {
        setLoading(true)
      }
      setTradeError('')

      try {
        const { data: { session }, error: sessionError } = await supabase.auth.getSession()
        if (sessionError || !session?.user?.id) {
          if (!ignore) {
            setTradeHistory([])
            setTradeError('로그인 세션을 확인할 수 없습니다.')
          }
          return
        }

        if (runSync) {
          await syncTradeStatuses()
        }

        const authHeader = `Bearer ${session.access_token}`
        const [
          { data: proposalRows, error: proposalError },
          { data: brokerRows, error: brokerError },
          { data: transferRows, error: transferError },
        ] = await Promise.all([
          supabase
            .from('trade_proposals')
            .select(TRADE_HISTORY_SELECT_FIELDS)
            .order('created_at', { ascending: false }),
          supabase
            .from('broker_order_history')
            .select(BROKER_HISTORY_SELECT_FIELDS)
            .order('ordered_at', { ascending: false }),
          fetchTransferHistory(authHeader)
            .then((data) => ({ data, error: null }))
            .catch((error) => ({ data: [], error })),
        ])

        if (ignore) return

        if (proposalError || (brokerError && !isMissingBrokerHistoryTableError(brokerError))) {
          setTradeHistory([])
          setTradeError('거래내역을 불러오지 못했습니다. 잠시 후 다시 시도해 주세요.')
        } else {
          setTradeHistory(await mergeTrades(
            proposalRows || [],
            brokerError ? [] : (brokerRows || []),
            transferError ? [] : (transferRows || []),
          ))
        }
      } catch {
        if (!ignore) {
          setTradeHistory([])
          setTradeError('거래내역을 불러오지 못했습니다. 잠시 후 다시 시도해 주세요.')
        }
      } finally {
        if (showLoading && !ignore) {
          setLoading(false)
        }
      }
    }

    const scheduleRealtimeRefresh = () => {
      if (realtimeRefreshTimerRef.current) {
        window.clearTimeout(realtimeRefreshTimerRef.current)
      }
      realtimeRefreshTimerRef.current = window.setTimeout(() => {
        loadTradeHistory({ runSync: false, showLoading: false })
      }, 250)
    }

    const subscribeTradeHistory = async () => {
      const { data: { session } } = await supabase.auth.getSession()
      if (!session?.user?.id || ignore) return

      proposalChannel = supabase
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
            scheduleRealtimeRefresh()
          },
        )
        .subscribe()

      brokerChannel = supabase
        .channel(`broker-trade-history-${session.user.id}`)
        .on(
          'postgres_changes',
          {
            event: '*',
            schema: 'public',
            table: 'broker_order_history',
            filter: `user_id=eq.${session.user.id}`,
          },
          () => {
            scheduleRealtimeRefresh()
          },
        )
        .subscribe()

      transferChannel = supabase
        .channel(`transfer-history-${session.user.id}`)
        .on(
          'postgres_changes',
          {
            event: '*',
            schema: 'public',
            table: 'asset_transfer_proposals',
            filter: `user_id=eq.${session.user.id}`,
          },
          () => {
            scheduleRealtimeRefresh()
          },
        )
        .subscribe()
    }

    const initializeTradeHistory = async () => {
      await loadTradeHistory({ runSync: true, showLoading: true })
      await subscribeTradeHistory()
    }

    initializeTradeHistory()

    return () => {
      ignore = true
      if (realtimeRefreshTimerRef.current) {
        window.clearTimeout(realtimeRefreshTimerRef.current)
      }
      if (proposalChannel) {
        supabase.removeChannel(proposalChannel)
      }
      if (brokerChannel) {
        supabase.removeChannel(brokerChannel)
      }
      if (transferChannel) {
        supabase.removeChannel(transferChannel)
      }
    }
  }, [syncTradeStatuses])

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

  const refreshTradeHistory = async () => {
    await syncTradeStatuses()
    const authHeader = await getAuthHeader()
    const [
      { data: proposalRows, error: proposalError },
      { data: brokerRows, error: brokerError },
      { data: transferRows, error: transferError },
    ] = await Promise.all([
      supabase
        .from('trade_proposals')
        .select(TRADE_HISTORY_SELECT_FIELDS)
        .order('created_at', { ascending: false }),
      supabase
        .from('broker_order_history')
        .select(BROKER_HISTORY_SELECT_FIELDS)
        .order('ordered_at', { ascending: false }),
      fetchTransferHistory(authHeader)
        .then((data) => ({ data, error: null }))
        .catch((error) => ({ data: [], error })),
    ])

    if (proposalError || (brokerError && !isMissingBrokerHistoryTableError(brokerError))) {
      throw proposalError || brokerError
    }
    const nextTrades = await mergeTrades(
      proposalRows || [],
      brokerError ? [] : (brokerRows || []),
      transferError ? [] : (transferRows || []),
    )
    setTradeHistory(nextTrades)
    if (selectedTrade) {
      const nextSelectedTrade = nextTrades.find((trade) => trade.id === selectedTrade.id)
      setSelectedTrade(nextSelectedTrade || null)
    }
  }

  const requestOrderAction = async (endpoint, body) => {
    const authHeader = await getAuthHeader()
    const controller = new AbortController()
    const timeoutId = window.setTimeout(() => controller.abort(), 30000)
    try {
      const response = await fetch(`${API_BASE_URL}${endpoint}`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: authHeader,
        },
        body: JSON.stringify(body),
        signal: controller.signal,
      })
      const payload = await response.json().catch(() => ({}))
      if (!response.ok || !payload.success) {
        throw payload
      }
      return payload
    } catch (error) {
      if (error?.name === 'AbortError') {
        throw new Error('주문 처리 요청 시간이 초과되었습니다. 백엔드와 거래소 응답 상태를 확인해 주세요.', { cause: error })
      }
      throw new Error(buildApiErrorText(error, '주문 처리 요청에 실패했습니다.'), { cause: error })
    } finally {
      window.clearTimeout(timeoutId)
    }
  }

  const handleSyncBrokerHistory = async () => {
    setActionLoadingId('sync-broker-history')
    setActionNotice('')
    try {
      const payload = await requestOrderAction('/api/trade/history/sync/toss', {
        broker_env: 'REAL',
        status_scope: 'ALL',
      })
      const syncedCount = payload?.data?.synced_count ?? 0
      setActionNotice(`토스 주문 원장 동기화 완료: ${syncedCount}건 반영`)
      await refreshTradeHistory()
    } catch (error) {
      if (isMissingBrokerHistoryTableError(error)) {
        setActionNotice('브로커 주문 원장 테이블이 아직 배포되지 않았습니다. Supabase 마이그레이션 적용 후 다시 시도해 주세요.')
      } else {
        setActionNotice(error.message)
      }
    } finally {
      setActionLoadingId('')
    }
  }

  const handleSyncOrderStatuses = async () => {
    setActionLoadingId('sync-order-statuses')
    setActionNotice('')
    try {
      const payload = await requestOrderAction('/api/trade/orders/sync-status', {})
      setActionNotice(`앱 주문 상태 갱신 완료: 확인 ${payload.checked_count ?? 0}건 / 반영 ${payload.synced_count ?? 0}건`)
      await refreshTradeHistory()
    } catch (error) {
      setActionNotice(error.message)
    } finally {
      setActionLoadingId('')
    }
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

  const handleDeleteTradeHistory = async (trade) => {
    if (!isDeletableTradeHistoryItem(trade)) return

    const confirmed = window.confirm(`${trade.symbolName} ${trade.status} 내역을 삭제할까요?`)
    if (!confirmed) return

    setActionLoadingId(`delete-${trade.id}`)
    setActionNotice('')
    try {
      const { data: { session }, error: sessionError } = await supabase.auth.getSession()
      if (sessionError || !session?.user?.id) {
        throw new Error('로그인 세션을 확인할 수 없습니다.')
      }

      const deleteTargetId = trade.deleteTargetId || trade.id
      const tableName = trade.sourceType === 'TRANSFER' ? 'asset_transfer_proposals' : 'trade_proposals'
      let query = supabase
        .from(tableName)
        .delete()
        .eq('id', deleteTargetId)
        .eq('user_id', session.user.id)

      if (trade.sourceType === 'TRANSFER') {
        query = query.in('status', ['FAILED', 'NEEDS_REVIEW', 'REJECTED'])
      } else {
        query = query.in('status', ['FAILED', 'REJECTED', 'EXPIRED', 'CANCELED', 'CANCELLED'])
      }

      const { error } = await query
      if (error) throw error

      setActionNotice('거래내역이 삭제되었습니다.')
      setTradeHistory((items) => items.filter((item) => (
        item.sourceType !== trade.sourceType
        || String(item.deleteTargetId || item.id) !== String(deleteTargetId)
      )))
      if (selectedTrade?.id === trade.id) {
        setSelectedTrade(null)
      }
      await refreshTradeHistory()
    } catch (error) {
      setActionNotice(error.message || '거래내역 삭제에 실패했습니다.')
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
            <span className="whitespace-pre-line">{actionNotice}</span>
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

      <section className={`rounded-lg border border-slate-700 bg-slate-surface/90 ${mobileLayout ? 'p-2.5' : 'p-2'}`}>
        <div className={`flex flex-col ${mobileLayout ? 'gap-3' : 'gap-2 lg:flex-row lg:items-center lg:justify-between'}`}>
          <div className={`flex flex-1 flex-col ${mobileLayout ? 'gap-2.5' : 'gap-2 md:flex-row md:items-center'}`}>
            <label className={`flex items-center gap-2 rounded border border-slate-700 bg-[#0f172a] text-sm text-slate-500 ${mobileLayout ? 'h-11 w-full px-3.5' : 'h-10 min-w-52 px-3'}`}>
              <span>⌕</span>
              <input
                className="w-full bg-transparent text-slate-200 outline-none placeholder:text-slate-500"
                placeholder="Search Ticker..."
                type="text"
                value={tradeSearchQuery}
                onChange={(event) => setTradeSearchQuery(event.target.value)}
              />
            </label>
            <div className={`flex items-center rounded border border-slate-700 bg-[#0f172a] text-sm font-bold text-slate-300 ${mobileLayout ? 'h-11 gap-1.5 px-3' : 'h-10 gap-2 px-3'}`}>
              <div className={mobileLayout ? 'relative min-w-0 flex-1' : ''}>
                <input
                  className={`bg-transparent font-mono text-xs outline-none [color-scheme:dark] ${mobileLayout ? `w-full min-w-0 text-center ${dateRange.start ? 'text-slate-200' : 'text-transparent'}` : 'w-32 text-slate-200'}`}
                  type="date"
                  value={dateRange.start}
                  aria-label="시작일"
                  onChange={(event) => setDateRange((prev) => ({ ...prev, start: event.target.value }))}
                />
                {mobileLayout && !dateRange.start ? (
                  <span className="pointer-events-none absolute inset-0 flex items-center justify-center font-mono text-xs text-slate-200">
                    연도-월-일
                  </span>
                ) : null}
              </div>
              <span className="shrink-0 text-slate-600">-</span>
              <div className={mobileLayout ? 'relative min-w-0 flex-1' : ''}>
                <input
                  className={`bg-transparent font-mono text-xs outline-none [color-scheme:dark] ${mobileLayout ? `w-full min-w-0 text-center ${dateRange.end ? 'text-slate-200' : 'text-transparent'}` : 'w-32 text-slate-200'}`}
                  type="date"
                  value={dateRange.end}
                  aria-label="종료일"
                  onChange={(event) => setDateRange((prev) => ({ ...prev, end: event.target.value }))}
                />
                {mobileLayout && !dateRange.end ? (
                  <span className="pointer-events-none absolute inset-0 flex items-center justify-center font-mono text-xs text-slate-200">
                    연도-월-일
                  </span>
                ) : null}
              </div>
            </div>
            <label className={`flex items-center gap-2 rounded border border-slate-700 bg-[#0f172a] text-sm text-slate-400 ${mobileLayout ? 'h-11 w-full px-3.5' : 'h-10 min-w-56 px-3'}`}>
              <span className="shrink-0 text-xs font-bold text-slate-500">거래소</span>
              <select
                className="min-w-0 flex-1 bg-transparent text-xs font-bold text-slate-200 outline-none [color-scheme:dark]"
                value={selectedExchange}
                onChange={(event) => setSelectedExchange(event.target.value)}
                aria-label="거래소 선택"
              >
                {TRADE_EXCHANGE_OPTIONS.map((item) => (
                  <option key={item} value={item}>
                    {TRADE_EXCHANGE_LABELS[item]}
                  </option>
                ))}
              </select>
            </label>
          </div>
          <button
            className={`rounded border px-4 text-sm font-bold transition ${
              mobileLayout ? 'h-11 w-full' : 'h-10'
            } ${
              isMoreFiltersOpen
                ? 'border-ai-cyan bg-ai-cyan/10 text-ai-cyan'
                : 'border-slate-700 bg-[#0f172a] text-slate-200 hover:border-ai-cyan'
            }`}
            type="button"
            onClick={() => setIsMoreFiltersOpen((prev) => !prev)}
          >
            More Filters
          </button>
          <button
            className={`rounded border border-blue-500/40 bg-blue-500/10 px-4 text-sm font-bold text-blue-300 transition hover:bg-blue-500/15 disabled:cursor-not-allowed disabled:opacity-50 ${mobileLayout ? 'h-11' : 'h-10'}`}
            type="button"
            disabled={Boolean(actionLoadingId)}
            onClick={handleSyncBrokerHistory}
          >
            {actionLoadingId === 'sync-broker-history' ? '토스 내역 불러오는 중' : '토스 실제 주문내역 불러오기'}
          </button>
          <button
            className={`rounded border border-cyan-500/40 bg-cyan-500/10 px-4 text-sm font-bold text-cyan-300 transition hover:bg-cyan-500/15 disabled:cursor-not-allowed disabled:opacity-50 ${mobileLayout ? 'h-11' : 'h-10'}`}
            type="button"
            disabled={Boolean(actionLoadingId)}
            onClick={handleSyncOrderStatuses}
          >
            {actionLoadingId === 'sync-order-statuses' ? '앱 주문 갱신 중' : '앱 주문 상태 갱신'}
          </button>
        </div>
        {isMoreFiltersOpen ? (
          <div className={`${mobileLayout ? 'mt-2.5 border-t border-slate-800 pt-2.5' : 'mt-3 flex justify-end border-t border-slate-800 pt-3'}`}>
            <div className={`w-full rounded border border-slate-800 bg-[#0f172a] ${mobileLayout ? 'p-2.5' : 'p-3 md:max-w-4xl'}`}>
              <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
                <div className={`flex flex-wrap items-center gap-2 ${mobileLayout ? '' : 'md:ml-[25px]'}`}>
                  <span className="w-10 text-xs font-bold text-slate-500">구분</span>
                  {['ALL', '매수', '매도', '출금', '입금'].map((item) => (
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
                <div className={`flex flex-wrap items-center gap-2 ${mobileLayout ? '' : 'md:flex-1 md:justify-end md:pr-[25px]'}`}>
                  <span className="w-10 text-xs font-bold text-slate-500">상태</span>
                  {['ALL', '승인대기', '주문접수', '미체결', '부분체결', '정정접수', '체결완료', '취소완료', '주문실패', '전송중', '출금완료', '입금완료', '출금실패'].map((item) => (
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
        {mobileLayout ? (
          <div className="flex flex-col">
            {!loading && !tradeError && filteredTrades.map((trade) => (
              <button
                key={trade.id}
                className="w-full border-b border-slate-700/70 px-3 py-3 text-left transition last:border-b-0 hover:bg-white/[0.04]"
                type="button"
                onClick={() => setSelectedTrade(trade)}
              >
                <div className="flex items-start justify-between gap-3">
                  <div className="flex min-w-0 items-center gap-3">
                    <AssetLogo symbol={trade.ticker} assetType={trade.assetType} name={trade.symbolName} size="h-9 w-9" />
                    <div className="min-w-0">
                      <p className="truncate font-bold leading-tight text-white">{trade.symbolName}</p>
                      <p className="mt-0.5 truncate text-xs font-mono text-slate-500">{trade.ticker}</p>
                      <p className="mt-1 truncate text-[11px] font-bold text-ai-cyan/80">{trade.sourceLabel}</p>
                    </div>
                  </div>
                  <div className="flex shrink-0 flex-col items-end gap-1">
                    <span className={`rounded border px-2 py-1 text-[11px] font-black ${exchangeTone[trade.exchange] || 'border-slate-600 bg-slate-700 text-slate-200'}`}>
                      {TRADE_EXCHANGE_LABELS[trade.exchange] || trade.exchange}
                    </span>
                    <span className="rounded-full border border-slate-600 bg-slate-700/30 px-2.5 py-1 text-[11px] font-bold text-slate-200">
                      {trade.status}
                    </span>
                  </div>
                </div>
                <div className="mt-3 grid grid-cols-3 gap-2">
                  <div className="rounded-md bg-[#0f172a] px-2.5 py-2">
                    <p className="text-[11px] font-bold text-slate-500">체결가</p>
                    <p className="mt-1 font-mono text-xs font-bold text-slate-100">{trade.price}</p>
                  </div>
                  <div className="rounded-md bg-[#0f172a] px-2.5 py-2">
                    <p className="text-[11px] font-bold text-slate-500">수량</p>
                    <p className="mt-1 font-mono text-xs font-bold text-slate-100">{trade.quantity}</p>
                  </div>
                  <div className="rounded-md bg-[#0f172a] px-2.5 py-2">
                    <p className="text-[11px] font-bold text-slate-500">정산금액</p>
                    <p className="mt-1 font-mono text-xs font-bold text-slate-100">{trade.amount}</p>
                  </div>
                </div>
                <div className="mt-3 flex items-center justify-between gap-3">
                  <div className="min-w-0">
                    <p className={`text-xs font-bold ${trade.side === '留ㅼ닔' || trade.side === '?낃툑'
                      ? 'text-emerald-300'
                      : 'text-rose-300'
                    }`}>
                      {trade.side} {trade.side === '留ㅼ닔'
                        ? '(Buy)'
                        : trade.side === '留ㅻ룄'
                          ? '(Sell)'
                          : ''}
                    </p>
                    <p className="mt-1 text-[11px] font-mono text-slate-500">{trade.date.replaceAll('-', '.')} {trade.time}</p>
                  </div>
                  {trade.isActionable && trade.sourceType === 'APP' ? (
                    <div className="flex shrink-0 flex-wrap justify-end gap-2">
                      <button
                        className="rounded border border-ai-cyan/40 px-2.5 py-1.5 text-[11px] font-bold text-ai-cyan transition hover:bg-ai-cyan/10 disabled:cursor-not-allowed disabled:opacity-50"
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
                        className="rounded border border-rose-400/40 px-2.5 py-1.5 text-[11px] font-bold text-rose-300 transition hover:bg-rose-400/10 disabled:cursor-not-allowed disabled:opacity-50"
                        type="button"
                        disabled={Boolean(actionLoadingId)}
                        onClick={(event) => {
                          event.stopPropagation()
                          handleOpenCancel(trade)
                        }}
                      >
                        Cancel
                      </button>
                    </div>
                  ) : null}
                </div>
              </button>
            ))}
            {loading ? (
              <div className="px-4 py-12 text-center text-sm text-slate-500">
                거래내역을 불러오는 중입니다.
              </div>
            ) : null}
            {!loading && tradeError ? (
              <div className="px-4 py-12 text-center text-sm text-rose-300">
                {tradeError}
              </div>
            ) : null}
            {!loading && !tradeError && filteredTrades.length === 0 ? (
              <div className="px-4 py-12 text-center text-sm text-slate-500">
                선택한 조건에 맞는 거래 내역이 없습니다.
              </div>
            ) : null}
          </div>
        ) : (
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
                      {TRADE_EXCHANGE_LABELS[trade.exchange] || trade.exchange}
                    </span>
                  </td>
                  <td className="px-4 py-4">
                    <div className="flex items-center gap-3">
                      <AssetLogo symbol={trade.ticker} assetType={trade.assetType} name={trade.symbolName} size="h-8 w-8" />
                      <div>
                        <p className="font-bold text-white leading-tight">{trade.symbolName}</p>
                        <p className="mt-0.5 text-xs text-slate-500 font-mono">{trade.ticker}</p>
                        <p className="mt-1 text-[11px] font-bold text-ai-cyan/80">{trade.sourceLabel}</p>
                      </div>
                    </div>
                  </td>
                  <td className="px-4 py-4">
                    <span className={`font-bold ${trade.side === '매수' || trade.side === '입금'
                      ? 'text-emerald-300'
                      : 'text-rose-300'
                    }`}>
                      {trade.side} {trade.side === '매수'
                        ? '(Buy)'
                        : trade.side === '매도'
                          ? '(Sell)'
                          : ''}
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
                        {trade.status}
                      </span>
                      {trade.isActionable && trade.sourceType === 'APP' ? (
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
                      {isDeletableTradeHistoryItem(trade) ? (
                        <button
                          className="rounded border border-slate-600 px-2.5 py-1 text-xs font-bold text-slate-300 transition hover:border-rose-400/60 hover:bg-rose-400/10 hover:text-rose-200 disabled:cursor-not-allowed disabled:opacity-50"
                          type="button"
                          disabled={Boolean(actionLoadingId)}
                          onClick={(event) => {
                            event.stopPropagation()
                            handleDeleteTradeHistory(trade)
                          }}
                        >
                          {actionLoadingId === `delete-${trade.id}` ? '삭제 중' : '삭제'}
                        </button>
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
        )}
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
                    <AssetLogo symbol={selectedTrade.ticker} assetType={selectedTrade.assetType} name={selectedTrade.symbolName} size="h-11 w-11" />
                    <div>
                      <p className="text-lg font-extrabold text-white">{selectedTrade.symbolName}</p>
                      <p className="mt-1 text-xs font-mono text-slate-400">{selectedTrade.ticker}</p>
                    </div>
                  </div>
                  <div className="text-right">
                      <p className="font-bold text-white">
                        {selectedTrade.sourceType === 'TRANSFER'
                          ? 'AE 자산이동'
                          : selectedTrade.sourceType === 'BROKER'
                            ? '토스 앱/브로커'
                            : '지정가'} {selectedTrade.side}
                      </p>
                      <p className="mt-1 text-xs font-bold text-ai-cyan">{selectedTrade.sourceLabel}</p>
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

              {selectedTrade.isActionable && selectedTrade.sourceType === 'APP' ? (
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

              {isDeletableTradeHistoryItem(selectedTrade) ? (
                <button
                  className="h-11 w-full rounded border border-slate-600 bg-[#0f172a] text-sm font-extrabold text-slate-300 transition hover:border-rose-400/60 hover:bg-rose-400/10 hover:text-rose-200 disabled:cursor-not-allowed disabled:opacity-50"
                  type="button"
                  disabled={Boolean(actionLoadingId)}
                  onClick={() => handleDeleteTradeHistory(selectedTrade)}
                >
                  {actionLoadingId === `delete-${selectedTrade.id}` ? '삭제 중' : '삭제'}
                </button>
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
                <div className="flex items-center justify-between">
                  <dt>원천</dt>
                  <dd className="text-right font-bold text-slate-300">
                    <span className="block">{selectedTrade.sourceLabel}</span>
                    <span className="block text-[11px] font-normal text-slate-500">{selectedTrade.sourceDescription}</span>
                  </dd>
                </div>
              </dl>
            </div>
          </aside>
        </div>
      )}
    </main>
  )
}
