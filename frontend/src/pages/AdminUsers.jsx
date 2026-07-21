import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import Header from '../components/Header.jsx'
import { supabase } from '../supabaseClient.js'
import { buildApiErrorText } from '../lib/apiError.js'

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:5050'
const USER_PAGE_SIZE = 100
const MODEL_PRICING = {
  'gemini-3.5-pro': { inputPerMillionUsd: 1.25, outputPerMillionUsd: 5.00, blendedPerMillionUsd: 2.1875 },
  'gemini-3.5-flash': { inputPerMillionUsd: 0.075, outputPerMillionUsd: 0.30, blendedPerMillionUsd: 0.13125 },
  'gpt-4.1-mini': { inputPerMillionUsd: 0.15, outputPerMillionUsd: 0.60, blendedPerMillionUsd: 0.2625 },
}
const DEFAULT_PRICING = { inputPerMillionUsd: 0.15, outputPerMillionUsd: 0.60, blendedPerMillionUsd: 0.2625 }

const numberFormatter = new Intl.NumberFormat('ko-KR')
const usdFormatter = new Intl.NumberFormat('en-US', {
  style: 'currency',
  currency: 'USD',
  minimumFractionDigits: 4,
  maximumFractionDigits: 4,
})

function formatNumber(value) {
  return numberFormatter.format(Number(value || 0))
}

function formatCurrency(value, currency = 'KRW') {
  if (value === null || value === undefined || value === '') return '-'
  const numericValue = Number(value)
  if (!Number.isFinite(numericValue)) return '-'
  const prefix = currency === 'USD' ? '$' : '₩'
  return `${prefix}${numberFormatter.format(numericValue)}`
}

function formatUsd(value) {
  const numericValue = Number(value)
  if (!Number.isFinite(numericValue)) return '$0.0000'
  return usdFormatter.format(numericValue)
}

function estimateCurrentModelCost({ promptTokens = 0, completionTokens = 0 } = {}, modelName = '') {
  const model = String(modelName || '').trim().toLowerCase()
  const pricing = MODEL_PRICING[model] || DEFAULT_PRICING
  const promptCost = (Number(promptTokens || 0) / 1_000_000) * pricing.inputPerMillionUsd
  const completionCost = (Number(completionTokens || 0) / 1_000_000) * pricing.outputPerMillionUsd
  return promptCost + completionCost
}

function estimateBlendedCurrentModelCost(totalTokens = 0, modelName = '') {
  const model = String(modelName || '').trim().toLowerCase()
  const pricing = MODEL_PRICING[model] || DEFAULT_PRICING
  return (Number(totalTokens || 0) / 1_000_000) * pricing.blendedPerMillionUsd
}

function sumDailyCost(dailyRows = []) {
  return dailyRows.reduce((total, row) => total + estimateCurrentModelCost({
    promptTokens: row.promptTokens,
    completionTokens: row.completionTokens,
  }), 0)
}

function formatDateTime(value) {
  const date = value ? new Date(value) : null
  if (!date || Number.isNaN(date.getTime())) return '-'
  return date.toLocaleString('ko-KR', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })
}

function formatStatus(status) {
  if (!status) return '-'
  const upper = String(status).toUpperCase()
  const statusMap = {
    PENDING: '대기 중',
    APPROVED: '승인됨',
    REJECTED: '거부됨',
    FAILED: '실패',
    COMPLETED: '완료됨',
    FILLED: '체결 완료',
    PARTIALLY_FILLED: '부분 체결',
    CANCELLED: '취소됨',
    CANCELED: '취소됨',
    EXECUTED: '체결 완료',
  }
  return statusMap[upper] || status
}

function SummaryCard({ label, value, detail }) {
  return (
    <div className="rounded-lg border border-slate-800 bg-[#0f172a] p-4">
      <p className="text-xs font-bold text-slate-400">{label}</p>
      <p className="mt-2 font-mono text-2xl font-extrabold text-white">{value}</p>
      {detail ? <p className="mt-1 text-xs text-slate-500">{detail}</p> : null}
    </div>
  )
}

function MobileSummaryCard({ label, value, detail }) {
  return (
    <div className="min-w-0 rounded-lg border border-slate-800 bg-[#0f172a] p-3">
      <p className="break-keep text-xs font-bold leading-5 text-slate-400">{label}</p>
      <p className="mt-2 break-words font-mono text-xl font-extrabold leading-7 text-white [overflow-wrap:anywhere]">{value}</p>
      {detail ? <p className="mt-1 break-words text-xs leading-5 text-slate-500 [overflow-wrap:anywhere]">{detail}</p> : null}
    </div>
  )
}

export default function AdminUsers({ isLoggedIn, userEmail, handleLogout, hideHeader = false }) {
  const [users, setUsers] = useState([])
  const [summary, setSummary] = useState({ totalUsers: 0, todayTokens: 0, tokens30d: 0, activeUsers24h: 0 })
  const [query, setQuery] = useState('')
  const [committedQuery, setCommittedQuery] = useState('')
  const [sort, setSort] = useState('tokens_30d')
  const [order, setOrder] = useState('desc')
  const [page, setPage] = useState(0)
  const [selectedUserId, setSelectedUserId] = useState('')
  const [isUserModalOpen, setIsUserModalOpen] = useState(false)
  const [activeModalTab, setActiveModalTab] = useState('usage')
  const [detail, setDetail] = useState(null)
  const [tradeRows, setTradeRows] = useState([])
  const [loading, setLoading] = useState(false)
  const [refreshing, setRefreshing] = useState(false)
  const [detailLoading, setDetailLoading] = useState(false)
  const [tradeLoading, setTradeLoading] = useState(false)
  const [roleLoading, setRoleLoading] = useState(false)
  const [error, setError] = useState('')
  const [detailError, setDetailError] = useState('')
  const [tradeError, setTradeError] = useState('')
  const [roleDraft, setRoleDraft] = useState('USER')
  const [roleNotice, setRoleNotice] = useState('')
  const listRequestSequence = useRef(0)
  const detailRequestSequence = useRef(0)
  const tradeRequestSequence = useRef(0)

  const selectedUser = useMemo(
    () => users.find((item) => item.id === selectedUserId) || null,
    [selectedUserId, users],
  )
  const modalUser = selectedUser

  const authHeaders = useCallback(async () => {
    const { data: { session } } = await supabase.auth.getSession()
    if (!session?.access_token) throw new Error('로그인이 필요합니다.')
    return { Authorization: `Bearer ${session.access_token}` }
  }, [])

  const totalUsers = Number(summary.totalUsers || 0)
  const visibleUsersTotalTokens = users.reduce((total, item) => total + Number(item.usage?.totalTokens || 0), 0)
  const summaryTotalTokens = Number(summary.totalTokens ?? visibleUsersTotalTokens)
  const totalPages = Math.max(1, Math.ceil(totalUsers / USER_PAGE_SIZE))
  const pageStart = users.length ? page * USER_PAGE_SIZE + 1 : 0
  const pageEnd = users.length ? page * USER_PAGE_SIZE + users.length : 0

  const loadUsers = useCallback(async ({ pageOverride = 0, queryOverride = '', signal } = {}) => {
    const requestSequence = listRequestSequence.current + 1
    listRequestSequence.current = requestSequence
    setLoading(true)
    setError('')
    try {
      const headers = await authHeaders()
      if (signal?.aborted) return
      const params = new URLSearchParams({
        sort,
        order,
        limit: String(USER_PAGE_SIZE),
        offset: String(pageOverride * USER_PAGE_SIZE),
      })
      if (queryOverride) params.set('q', queryOverride)
      const response = await fetch(`${API_BASE_URL}/api/admin/users?${params.toString()}`, { headers, signal })
      const payload = await response.json().catch(() => ({}))
      if (!response.ok || payload.success === false) {
        throw new Error(buildApiErrorText(payload, '유저 목록을 불러오지 못했습니다.'))
      }
      if (listRequestSequence.current !== requestSequence) return
      const rows = payload.data || []
      setUsers(rows)
      setSummary(payload.summary || {})
      setSelectedUserId((current) => (rows.some((item) => item.id === current) ? current : ''))
    } catch (requestError) {
      if (requestError.name === 'AbortError' || listRequestSequence.current !== requestSequence) return
      setUsers([])
      setSummary({ totalUsers: 0, todayTokens: 0, tokens30d: 0, totalTokens: 0, activeUsers24h: 0 })
      setError(requestError.message || '유저 목록을 불러오지 못했습니다.')
    } finally {
      if (listRequestSequence.current === requestSequence) {
        setLoading(false)
      }
    }
  }, [authHeaders, order, sort])

  useEffect(() => {
    const controller = new AbortController()
    const timeoutId = window.setTimeout(() => {
      loadUsers({ pageOverride: page, queryOverride: committedQuery, signal: controller.signal })
    }, 0)
    return () => {
      window.clearTimeout(timeoutId)
      controller.abort()
    }
  }, [committedQuery, loadUsers, page])

  const handleSearch = () => {
    const nextQuery = query.trim()
    if (nextQuery !== committedQuery) {
      setCommittedQuery(nextQuery)
      if (page !== 0) {
        setPage(0)
      }
      return
    }

    if (page !== 0) {
      setPage(0)
    } else {
      loadUsers({ pageOverride: 0, queryOverride: nextQuery })
    }
  }

  const loadUserDetail = useCallback(async ({ userId, signal } = {}) => {
    if (!userId) return
    const requestSequence = detailRequestSequence.current + 1
    detailRequestSequence.current = requestSequence
    setDetail(null)
    setDetailLoading(true)
    setDetailError('')
    try {
      const headers = await authHeaders()
      if (signal?.aborted) return

      const response = await fetch(`${API_BASE_URL}/api/admin/users/${userId}/chatbot-usage?days=30&limit=50`, {
        headers,
        signal,
      })
      const payload = await response.json().catch(() => ({}))
      if (!response.ok || payload.success === false) {
        throw new Error(buildApiErrorText(payload, '유저 사용량을 불러오지 못했습니다.'))
      }
      if (detailRequestSequence.current === requestSequence) {
        setDetail(payload)
      }
    } catch (requestError) {
      if (requestError.name === 'AbortError' || detailRequestSequence.current !== requestSequence) return
      setDetail(null)
      setDetailError(requestError.message || '유저 사용량을 불러오지 못했습니다.')
    } finally {
      if (detailRequestSequence.current === requestSequence) {
        setDetailLoading(false)
      }
    }
  }, [authHeaders])

  const loadUserTradeHistory = useCallback(async ({ userId, signal } = {}) => {
    if (!userId) return
    const requestSequence = tradeRequestSequence.current + 1
    tradeRequestSequence.current = requestSequence
    setTradeRows([])
    setTradeLoading(true)
    setTradeError('')
    try {
      const headers = await authHeaders()
      if (signal?.aborted) return

      const response = await fetch(`${API_BASE_URL}/api/admin/users/${userId}/trade-history?limit=100`, {
        headers,
        signal,
      })
      const payload = await response.json().catch(() => ({}))
      if (!response.ok || payload.success === false) {
        throw new Error(buildApiErrorText(payload, '유저 거래내역을 불러오지 못했습니다.'))
      }
      if (tradeRequestSequence.current === requestSequence) {
        setTradeRows(payload.data || [])
      }
    } catch (requestError) {
      if (requestError.name === 'AbortError' || tradeRequestSequence.current !== requestSequence) return
      setTradeRows([])
      setTradeError(requestError.message || '유저 거래내역을 불러오지 못했습니다.')
    } finally {
      if (tradeRequestSequence.current === requestSequence) {
        setTradeLoading(false)
      }
    }
  }, [authHeaders])

  const handleOpenUserModal = (item) => {
    setSelectedUserId(item.id)
    setActiveModalTab('usage')
    setRoleDraft(item.role === 'ADMIN' ? 'ADMIN' : 'USER')
    setRoleNotice('')
    setTradeRows([])
    setTradeError('')
    setIsUserModalOpen(true)
  }

  const handleCloseUserModal = () => {
    setIsUserModalOpen(false)
    setDetail(null)
    setTradeRows([])
    setDetailError('')
    setTradeError('')
    setRoleNotice('')
  }

  const handleRefresh = async () => {
    setRefreshing(true)
    try {
      await loadUsers({ pageOverride: page, queryOverride: committedQuery })
      if (isUserModalOpen && modalUser?.id) {
        await loadUserDetail({ userId: modalUser.id })
        if (activeModalTab === 'trades') {
          await loadUserTradeHistory({ userId: modalUser.id })
        }
      }
    } finally {
      setRefreshing(false)
    }
  }

  const handleUpdateRole = async () => {
    if (!modalUser?.id) return
    const nextRole = roleDraft === 'ADMIN' ? 'ADMIN' : 'USER'
    const confirmed = window.confirm(`${modalUser.email || modalUser.nickname || modalUser.id} 권한을 ${nextRole}로 변경할까요?`)
    if (!confirmed) return

    setRoleLoading(true)
    setRoleNotice('')
    try {
      const headers = await authHeaders()
      const response = await fetch(`${API_BASE_URL}/api/admin/users/${modalUser.id}/role`, {
        method: 'PATCH',
        headers: {
          ...headers,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ role: nextRole }),
      })
      const payload = await response.json().catch(() => ({}))
      if (!response.ok || payload.success === false) {
        throw new Error(buildApiErrorText(payload, '유저 권한을 변경하지 못했습니다.'))
      }
      const updatedUser = payload.data || { ...modalUser, role: nextRole }
      setUsers((current) => current.map((item) => (item.id === updatedUser.id ? { ...item, ...updatedUser } : item)))
      setRoleDraft(updatedUser.role === 'ADMIN' ? 'ADMIN' : 'USER')
      setRoleNotice('권한이 변경되었습니다.')
      await loadUsers({ pageOverride: page, queryOverride: committedQuery })
    } catch (requestError) {
      setRoleNotice(requestError.message || '유저 권한을 변경하지 못했습니다.')
    } finally {
      setRoleLoading(false)
    }
  }

  useEffect(() => {
    const userId = modalUser?.id
    if (!isUserModalOpen || !userId) {
      return undefined
    }

    const controller = new AbortController()
    const timeoutId = window.setTimeout(() => {
      loadUserDetail({ userId, signal: controller.signal })
    }, 0)
    return () => {
      window.clearTimeout(timeoutId)
      controller.abort()
    }
  }, [isUserModalOpen, loadUserDetail, modalUser?.id])

  useEffect(() => {
    const userId = modalUser?.id
    if (!isUserModalOpen || activeModalTab !== 'trades' || !userId) {
      return undefined
    }

    const controller = new AbortController()
    const timeoutId = window.setTimeout(() => {
      loadUserTradeHistory({ userId, signal: controller.signal })
    }, 0)
    return () => {
      window.clearTimeout(timeoutId)
      controller.abort()
    }
  }, [isUserModalOpen, activeModalTab, loadUserTradeHistory, modalUser?.id])

  return (
    <div className={hideHeader ? 'font-inter text-[#e2e2ec]' : 'min-h-screen bg-obsidian-bg font-inter text-[#e2e2ec]'}>
      <div className={hideHeader ? 'grid gap-6' : 'mx-auto grid max-w-7xl gap-6 px-6 py-8'}>
        {!hideHeader ? <Header isLoggedIn={isLoggedIn} userEmail={userEmail} handleLogout={handleLogout} /> : null}

        <section className="rounded-lg border border-slate-700/80 bg-slate-surface p-4 sm:p-5">
          {/* hideHeader는 모바일 관리자 안에 포함될 때만 켜지므로, PC 화면은 기존 배치를 그대로 사용합니다. */}
          <div className={hideHeader ? 'grid gap-4' : 'flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between'}>
            <div className={hideHeader ? 'min-w-0' : undefined}>
              <p className="text-[10px] font-bold uppercase tracking-[0.16em] text-ai-cyan">Admin Users</p>
              <h1 className={hideHeader ? 'mt-1 break-keep text-xl font-extrabold text-white' : 'mt-1 text-2xl font-extrabold text-white'}>유저 관리</h1>
              <p className={hideHeader ? 'mt-2 break-keep text-sm leading-6 text-slate-400' : 'mt-2 text-sm text-slate-400'}>사용자별 실제 챗봇 토큰 사용량과 최근 사용 흐름을 확인합니다.</p>
            </div>
            <div className={hideHeader ? 'grid w-full min-w-0 grid-cols-2 gap-2' : 'grid gap-2 sm:grid-cols-[minmax(220px,1fr)_150px_120px_auto_auto]'}>
              <input
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === 'Enter') handleSearch()
                }}
                className={hideHeader ? 'col-span-2 min-w-0 rounded border border-slate-700 bg-[#0f172a] px-3 py-2 text-sm text-white outline-none transition focus:border-ai-cyan' : 'rounded border border-slate-700 bg-[#0f172a] px-3 py-2 text-sm text-white outline-none transition focus:border-ai-cyan'}
                placeholder="이메일 또는 닉네임 검색"
              />
              <select value={sort} onChange={(event) => {
                setPage(0)
                setSort(event.target.value)
              }} className="rounded border border-slate-700 bg-[#0f172a] px-3 py-2 text-xs font-bold text-slate-300 outline-none focus:border-ai-cyan">
                <option value="tokens_30d">30일 토큰</option>
                <option value="today_tokens">오늘 토큰</option>
                <option value="tokens_7d">7일 토큰</option>
                <option value="total_tokens">전체 토큰</option>
                <option value="recent_used_at">최근 사용</option>
              </select>
              <select value={order} onChange={(event) => {
                setPage(0)
                setOrder(event.target.value)
              }} className="rounded border border-slate-700 bg-[#0f172a] px-3 py-2 text-xs font-bold text-slate-300 outline-none focus:border-ai-cyan">
                <option value="desc">내림차순</option>
                <option value="asc">오름차순</option>
              </select>
              <button type="button" onClick={handleSearch} className="rounded bg-ai-cyan px-4 py-2 text-xs font-bold text-slate-950 transition hover:bg-cyan-300">
                조회
              </button>
              <button
                type="button"
                onClick={handleRefresh}
                disabled={loading || refreshing}
                className="rounded border border-slate-700 px-4 py-2 text-xs font-bold text-slate-200 transition hover:border-ai-cyan hover:text-ai-cyan disabled:cursor-not-allowed disabled:opacity-50"
              >
                {refreshing ? '갱신 중' : '갱신'}
              </button>
            </div>
          </div>

          {hideHeader ? (
            <div className="mt-5 grid min-w-0 grid-cols-2 gap-3">
              {/* 모바일 관리자에서는 요약 카드가 한 줄로 찌그러지지 않도록 별도 카드 컴포넌트를 사용합니다. */}
              <MobileSummaryCard label="전체 유저" value={formatNumber(summary.totalUsers)} />
              <MobileSummaryCard label="오늘 실제 토큰" value={formatNumber(summary.todayTokens)} />
              <MobileSummaryCard label="30일 실제 토큰" value={formatNumber(summary.tokens30d)} />
              <MobileSummaryCard
                label="30일 예상 비용"
                value={formatUsd(estimateBlendedCurrentModelCost(summary.tokens30d))}
                detail="Blended 기준 추정"
              />
              <MobileSummaryCard
                label="통산 예상 비용"
                value={formatUsd(estimateBlendedCurrentModelCost(summaryTotalTokens))}
                detail={`전체 ${formatNumber(summaryTotalTokens)} tokens`}
              />
              <MobileSummaryCard label="24시간 활성 유저" value={formatNumber(summary.activeUsers24h)} />
            </div>
          ) : (
            <div className="mt-5 grid gap-3 sm:grid-cols-2 xl:grid-cols-6">
              <SummaryCard label="전체 유저" value={formatNumber(summary.totalUsers)} />
              <SummaryCard label="오늘 실제 토큰" value={formatNumber(summary.todayTokens)} />
              <SummaryCard label="30일 실제 토큰" value={formatNumber(summary.tokens30d)} />
              <SummaryCard
                label="30일 예상 비용"
                value={formatUsd(estimateBlendedCurrentModelCost(summary.tokens30d))}
                detail="Blended 기준 추정"
              />
              <SummaryCard
                label="통산 예상 비용"
                value={formatUsd(estimateBlendedCurrentModelCost(summaryTotalTokens))}
                detail={`전체 ${formatNumber(summaryTotalTokens)} tokens`}
              />
              <SummaryCard label="24시간 활성 유저" value={formatNumber(summary.activeUsers24h)} />
            </div>
          )}
        </section>

        <section className="grid gap-5">
          <div className="overflow-hidden rounded-lg border border-slate-700/80 bg-slate-surface p-3 sm:p-4">
            {/* 모바일 관리자에서는 PC 표 형태를 유지하되, 오른쪽 열은 표 내부 가로 스크롤로 확인합니다. */}
            <div className={hideHeader ? 'overflow-x-auto' : 'md:overflow-x-auto'}>
              <div className={hideHeader ? 'min-w-[960px]' : 'md:min-w-[760px]'}>
                <div className={hideHeader ? 'grid grid-cols-[minmax(170px,1.2fr)_80px_100px_repeat(4,minmax(90px,1fr))_105px_120px] rounded-t-lg bg-[#0f172a] text-xs font-bold text-slate-400' : 'hidden grid-cols-[minmax(170px,1.2fr)_80px_100px_repeat(4,minmax(90px,1fr))_105px_120px] rounded-t-lg bg-[#0f172a] text-xs font-bold text-slate-400 md:grid'}>
                  <div className="px-3 py-3">유저</div>
                  <div className="px-3 py-3">권한</div>
                  <div className="px-3 py-3">최근 모델</div>
                  <div className="px-3 py-3 text-right">오늘</div>
                  <div className="px-3 py-3 text-right">7일</div>
                  <div className="px-3 py-3 text-right">30일</div>
                  <div className="px-3 py-3 text-right">전체</div>
                  <div className="px-3 py-3 text-right">예상 비용</div>
                  <div className="px-3 py-3">최근 사용</div>
                </div>
                <div className="overflow-hidden rounded-lg border border-slate-800 md:rounded-t-none md:border-t-0">
                  {loading ? (
                    <div className="px-4 py-10 text-center text-sm font-bold text-slate-400">유저 목록을 불러오는 중입니다.</div>
                  ) : error ? (
                    <div className="px-4 py-10 text-center text-sm font-bold text-rose-400">{error}</div>
                  ) : users.length === 0 ? (
                    <div className="px-4 py-10 text-center text-sm font-bold text-slate-500">표시할 유저가 없습니다.</div>
                  ) : users.map((item) => (
                    <button
                      key={item.id}
                      type="button"
                      onClick={() => handleOpenUserModal(item)}
                      className={`${hideHeader ? 'grid w-full grid-cols-[minmax(170px,1.2fr)_80px_100px_repeat(4,minmax(90px,1fr))_105px_120px] gap-0 border-t border-slate-800 px-0 py-0 text-left text-sm first:border-t-0 hover:bg-white/[0.03]' : 'grid w-full grid-cols-2 gap-2 border-t border-slate-800 px-4 py-4 text-left text-sm first:border-t-0 hover:bg-white/[0.03] md:grid-cols-[minmax(170px,1.2fr)_80px_100px_repeat(4,minmax(90px,1fr))_105px_120px] md:gap-0 md:px-0 md:py-0'} ${selectedUser?.id === item.id ? 'bg-ai-cyan/5' : ''}`}
                    >
                      <span className={hideHeader ? 'min-w-0 px-3 py-3' : 'min-w-0 md:px-3 md:py-3'}>
                        <span className="block truncate font-bold text-white">{item.email || item.nickname || '-'}</span>
                        <span className="block truncate text-xs text-slate-500">{item.nickname || item.id}</span>
                      </span>
                      <span className={hideHeader ? 'px-3 py-3 text-xs font-bold text-ai-cyan' : 'text-xs font-bold text-ai-cyan md:px-3 md:py-3'}>{item.role}</span>
                      <span className={hideHeader ? 'truncate px-3 py-3 text-xs text-slate-400' : 'text-xs text-slate-400 truncate md:px-3 md:py-3'} title={item.usage?.recentModel || '-'}>
                        {item.usage?.recentModel || '-'}
                      </span>
                      <span className={hideHeader ? 'block px-3 py-3 text-right font-mono text-xs text-slate-300' : 'flex items-center justify-between gap-2 font-mono text-xs text-slate-300 md:block md:px-3 md:py-3 md:text-right'}>
                        <span className={hideHeader ? 'hidden' : 'font-inter font-bold text-slate-500 md:hidden'}>오늘</span>
                        <span>{formatNumber(item.usage?.todayTokens)}</span>
                      </span>
                      <span className={hideHeader ? 'block px-3 py-3 text-right font-mono text-xs text-slate-300' : 'flex items-center justify-between gap-2 font-mono text-xs text-slate-300 md:block md:px-3 md:py-3 md:text-right'}>
                        <span className={hideHeader ? 'hidden' : 'font-inter font-bold text-slate-500 md:hidden'}>7일</span>
                        <span>{formatNumber(item.usage?.tokens7d)}</span>
                      </span>
                      <span className={hideHeader ? 'block px-3 py-3 text-right font-mono text-xs text-white' : 'flex items-center justify-between gap-2 font-mono text-xs text-white md:block md:px-3 md:py-3 md:text-right'}>
                        <span className={hideHeader ? 'hidden' : 'font-inter font-bold text-slate-500 md:hidden'}>30일</span>
                        <span>{formatNumber(item.usage?.tokens30d)}</span>
                      </span>
                      <span className={hideHeader ? 'block px-3 py-3 text-right font-mono text-xs text-slate-300' : 'flex items-center justify-between gap-2 font-mono text-xs text-slate-300 md:block md:px-3 md:py-3 md:text-right'}>
                        <span className={hideHeader ? 'hidden' : 'font-inter font-bold text-slate-500 md:hidden'}>전체</span>
                        <span>{formatNumber(item.usage?.totalTokens)}</span>
                      </span>
                      <span className={hideHeader ? 'block px-3 py-3 text-right font-mono text-xs text-emerald-300' : 'flex items-center justify-between gap-2 font-mono text-xs text-emerald-300 md:block md:px-3 md:py-3 md:text-right'}>
                        <span className={hideHeader ? 'hidden' : 'font-inter font-bold text-slate-500 md:hidden'}>예상 비용</span>
                        <span>{formatUsd(estimateBlendedCurrentModelCost(item.usage?.tokens30d, item.usage?.recentModel))}</span>
                      </span>
                      <span className={hideHeader ? 'px-3 py-3 text-xs text-slate-500' : 'col-span-2 text-xs text-slate-500 md:col-span-1 md:px-3 md:py-3'}>{formatDateTime(item.usage?.recentUsedAt)}</span>
                    </button>
                  ))}
                </div>
              </div>
            </div>

            <div className="mt-3 flex flex-col gap-2 text-xs text-slate-500 sm:flex-row sm:items-center sm:justify-between">
              <span>
                {pageStart ? `${formatNumber(totalUsers)}명 중 ${formatNumber(pageStart)}-${formatNumber(pageEnd)}명` : '표시할 유저가 없습니다.'}
              </span>
              <div className="grid grid-cols-2 gap-2 sm:flex">
                <button
                  type="button"
                  onClick={() => setPage((current) => Math.max(0, current - 1))}
                  disabled={loading || page <= 0}
                  className="rounded border border-slate-700 px-3 py-2 font-bold text-slate-300 transition hover:border-ai-cyan hover:text-white disabled:cursor-not-allowed disabled:opacity-40"
                >
                  이전
                </button>
                <button
                  type="button"
                  onClick={() => setPage((current) => current + 1)}
                  disabled={loading || page + 1 >= totalPages}
                  className="rounded border border-slate-700 px-3 py-2 font-bold text-slate-300 transition hover:border-ai-cyan hover:text-white disabled:cursor-not-allowed disabled:opacity-40"
                >
                  다음
                </button>
              </div>
            </div>
          </div>
        </section>

        {/* 모바일 관리자에서 열린 상세 모달은 화면 높이에 맞춰 내부 스크롤을 조금 더 확보합니다. */}
        {isUserModalOpen && modalUser ? (
          <div className={hideHeader ? 'fixed inset-0 z-50 grid place-items-center bg-black/70 px-3 py-4 sm:px-4 sm:py-6' : 'fixed inset-0 z-50 grid place-items-center bg-black/70 px-4 py-6'}>
            <div className={hideHeader ? 'max-h-[92vh] w-full max-w-5xl overflow-hidden rounded-lg border border-slate-700 bg-[#111827] shadow-2xl' : 'max-h-[90vh] w-full max-w-5xl overflow-hidden rounded-lg border border-slate-700 bg-[#111827] shadow-2xl'}>
              <div className="flex items-start justify-between gap-4 border-b border-slate-800 px-5 py-4">
                <div className="min-w-0">
                  <p className="text-[10px] font-bold uppercase tracking-[0.16em] text-ai-cyan">Admin User</p>
                  <h2 className="mt-1 text-xl font-extrabold text-white">유저 상세 관리</h2>
                  <p className="mt-1 truncate text-xs text-slate-400">{modalUser.email || modalUser.nickname || modalUser.id}</p>
                  <p className="mt-1 text-xs font-bold text-slate-500">{modalUser.nickname || modalUser.id}</p>
                </div>
                <button
                  type="button"
                  onClick={handleCloseUserModal}
                  className="grid h-8 w-8 shrink-0 place-items-center rounded border border-slate-700 text-sm font-bold text-slate-300 transition hover:border-ai-cyan hover:text-ai-cyan"
                  aria-label="유저 상세 관리 닫기"
                >
                  x
                </button>
              </div>

              <div className="border-b border-slate-800 px-5 py-3">
                <div className="flex flex-wrap items-center gap-2">
                  {[
                    ['usage', '사용량'],
                    ['trades', '거래내역'],
                    ['role', '권한'],
                  ].map(([tabId, label]) => (
                    <button
                      key={tabId}
                      type="button"
                      onClick={() => setActiveModalTab(tabId)}
                      className={`rounded px-3 py-2 text-xs font-bold transition ${activeModalTab === tabId ? 'bg-ai-cyan text-slate-950' : 'bg-slate-800 text-slate-300 hover:bg-slate-700'}`}
                    >
                      {label}
                    </button>
                  ))}
                  <button
                    type="button"
                    onClick={handleRefresh}
                    disabled={refreshing || detailLoading || tradeLoading}
                    className="ml-auto rounded border border-slate-700 px-3 py-2 text-xs font-bold text-slate-200 transition hover:border-ai-cyan hover:text-ai-cyan disabled:cursor-not-allowed disabled:opacity-50"
                  >
                    {refreshing ? '갱신 중' : '갱신'}
                  </button>
                </div>
              </div>

              <div className={hideHeader ? 'max-h-[70vh] overflow-y-auto px-4 py-4 sm:px-5 sm:py-5' : 'max-h-[68vh] overflow-y-auto px-5 py-5'}>
                {activeModalTab === 'usage' ? (
                  detailLoading ? (
                    <div className="py-10 text-center text-sm font-bold text-slate-400">상세 사용량을 불러오는 중입니다.</div>
                  ) : detailError ? (
                    <div className="py-10 text-center text-sm font-bold text-rose-400">{detailError}</div>
                  ) : detail ? (
                    <div className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_320px]">
                      <div className="rounded-lg border border-slate-800 bg-[#0f172a] p-4">
                        <div className="flex items-start justify-between gap-3">
                          <div>
                            <p className="text-xs font-bold text-slate-400">일별 실제 토큰</p>
                            <p className="mt-1 text-[11px] text-slate-500">
                              일별 실제 입력/출력 분리 계산
                            </p>
                          </div>
                          <div className="text-right">
                            <p className="text-[11px] font-bold text-slate-500">30일 예상 비용</p>
                            <p className="font-mono text-sm font-extrabold text-emerald-300">{formatUsd(sumDailyCost(detail.daily || []))}</p>
                          </div>
                        </div>
                        <div className="mt-3 grid gap-2">
                          {(detail.daily || []).slice(0, 14).map((row) => {
                            const maxTokens = Math.max(...(detail.daily || []).map((item) => Number(item.totalTokens || 0)), 1)
                            const width = `${Math.max(4, Math.round((Number(row.totalTokens || 0) / maxTokens) * 100))}%`
                            const rowCost = estimateCurrentModelCost({
                              promptTokens: row.promptTokens,
                              completionTokens: row.completionTokens,
                            })
                            return (
                              <div key={row.date} className="grid gap-1">
                                <div className="flex items-center justify-between text-xs">
                                  <span className="text-slate-400">{row.date}</span>
                                  <span className="font-mono text-white">{formatNumber(row.totalTokens)} · {formatUsd(rowCost)}</span>
                                </div>
                                <div className="h-2 rounded bg-slate-800">
                                  <div className="h-2 rounded bg-ai-cyan" style={{ width }} />
                                </div>
                              </div>
                            )
                          })}
                          {(detail.daily || []).length === 0 ? <p className="text-sm font-bold text-slate-500">실제 토큰 로그가 없습니다.</p> : null}
                        </div>
                      </div>
                      <div className="grid gap-4">
                        {/* 모델별 호출 통계 카드 추가 */}
                        <div className="rounded-lg border border-slate-800 bg-[#0f172a] p-4">
                          <p className="text-xs font-bold text-slate-400">모델별 호출 통계</p>
                          <div className="mt-2 grid gap-2">
                            {Object.entries(detail.byModel || {}).map(([modelName, value]) => (
                              <div key={modelName} className="grid grid-cols-[1fr_auto] gap-2 text-xs">
                                <span className="truncate text-slate-400 font-bold" title={modelName}>{modelName}</span>
                                <span className="font-mono text-white text-right">
                                  {formatNumber(value.requestCount)}회 · {formatNumber(value.totalTokens)}T ({formatUsd(estimateCurrentModelCost({
                                    promptTokens: value.promptTokens,
                                    completionTokens: value.completionTokens,
                                  }, modelName))})
                                </span>
                              </div>
                            ))}
                            {Object.keys(detail.byModel || {}).length === 0 ? (
                              <p className="text-[11px] text-slate-500">모델 호출 이력이 없습니다.</p>
                            ) : null}
                          </div>
                        </div>

                        <div className="rounded-lg border border-slate-800 bg-[#0f172a] p-4">
                          <p className="text-xs font-bold text-slate-400">요청 유형별 합계</p>
                          <div className="mt-2 grid gap-2">
                            {Object.entries(detail.byRequestType || {}).map(([type, value]) => (
                              <div key={type} className="flex items-center justify-between gap-3 text-xs">
                                <span className="truncate text-slate-400">{type}</span>
                                <span className="font-mono text-white">
                                  {formatNumber(value.requestCount)}회 · {formatNumber(value.totalTokens)}T
                                </span>
                              </div>
                            ))}
                          </div>
                        </div>

                        <div className="rounded-lg border border-slate-800 bg-[#0f172a] p-4">
                          <p className="text-xs font-bold text-slate-400">최근 요청 로그</p>
                          <div className="mt-2 grid gap-2">
                            {(detail.recentLogs || []).slice(0, 8).map((log) => {
                              const uniqueKey = `${log.createdAt}-${log.requestType}-${log.totalTokens}-${log.model || ''}`;
                              return (
                                <div key={uniqueKey} className="grid grid-cols-[1fr_auto] gap-3 text-xs">
                                  <span className="min-w-0 truncate text-slate-400">
                                    <span className="block truncate">{formatDateTime(log.createdAt)} · {log.requestType}</span>
                                    <span className="block truncate text-[10px] text-slate-500 font-semibold">{log.model || 'unknown'}</span>
                                  </span>
                                  <span className="font-mono text-white self-center">
                                    {formatNumber(log.totalTokens)} · {formatUsd(estimateCurrentModelCost({
                                      promptTokens: log.promptTokens,
                                      completionTokens: log.completionTokens,
                                    }, log.model))}
                                  </span>
                                </div>
                              );
                            })}
                          </div>
                        </div>
                      </div>
                    </div>
                  ) : null
                ) : null}

                {activeModalTab === 'trades' ? (
                  tradeLoading ? (
                    <div className="py-10 text-center text-sm font-bold text-slate-400">거래내역을 불러오는 중입니다.</div>
                  ) : tradeError ? (
                    <div className="py-10 text-center text-sm font-bold text-rose-400">{tradeError}</div>
                  ) : (
                    <div className={hideHeader ? 'overflow-x-auto rounded-lg border border-slate-800' : 'overflow-hidden rounded-lg border border-slate-800'}>
                      {/* 모바일 모달의 거래내역 표는 열을 줄이지 않고 내부 스크롤로 전체 항목을 확인합니다. */}
                      <div className={`${hideHeader ? 'min-w-[920px] ' : ''}grid grid-cols-[130px_100px_minmax(120px,1.2fr)_minmax(110px,1fr)_80px_90px_90px_110px_110px] bg-[#0f172a] text-xs font-bold text-slate-400`}>
                        <div className="px-3 py-3">일시</div>
                        <div className="px-3 py-3">거래소</div>
                        <div className="px-3 py-3">종목</div>
                        <div className="px-3 py-3">주문번호</div>
                        <div className="px-3 py-3">구분</div>
                        <div className="px-3 py-3 text-right">수량</div>
                        <div className="px-3 py-3 text-right">단가</div>
                        <div className="px-3 py-3 text-right">금액</div>
                        <div className="px-3 py-3">상태</div>
                      </div>
                      {tradeRows.length === 0 ? (
                        <div className="px-4 py-10 text-center text-sm font-bold text-slate-500">표시할 거래내역이 없습니다.</div>
                      ) : tradeRows.map((row) => (
                        <div key={row.id} className={`${hideHeader ? 'min-w-[920px] ' : ''}grid grid-cols-[130px_100px_minmax(120px,1.2fr)_minmax(110px,1fr)_80px_90px_90px_110px_110px] border-t border-slate-800 text-xs`}>
                          <div className="px-3 py-3 text-slate-400">{formatDateTime(row.occurredAt)}</div>
                          <div className="px-3 py-3 font-bold text-ai-cyan">{row.exchange}</div>
                          <div className="min-w-0 px-3 py-3">
                            <span className="block truncate font-bold text-white">{row.symbol}</span>
                            <span className="block truncate text-[11px] text-slate-500">{row.sourceLabel}</span>
                          </div>
                          <div className="min-w-0 px-3 py-3">
                            <span className="block truncate font-mono text-slate-400" title={row.externalOrderId}>
                              {row.externalOrderId || '-'}
                            </span>
                          </div>
                          <div className="px-3 py-3 font-bold text-slate-200">{row.side}</div>
                          <div className="px-3 py-3 text-right font-mono text-slate-300">{row.quantity ?? '-'}</div>
                          <div className="px-3 py-3 text-right font-mono text-slate-300">{formatCurrency(row.price, row.currency)}</div>
                          <div className="px-3 py-3 text-right font-mono text-white">{formatCurrency(row.orderAmount, row.currency)}</div>
                          <div className="px-3 py-3 font-bold text-slate-300">{formatStatus(row.status)}</div>
                        </div>
                      ))}
                    </div>
                  )
                ) : null}

                {activeModalTab === 'role' ? (
                  <div className="max-w-lg rounded-lg border border-slate-800 bg-[#0f172a] p-4">
                    <p className="text-xs font-bold text-slate-400">권한 변경</p>
                    <p className="mt-2 text-sm text-slate-300">관리자 화면 접근 권한을 제어합니다. 자기 자신의 권한은 변경할 수 없습니다.</p>
                    <div className="mt-4 grid gap-2">
                      <label className="text-xs font-bold text-slate-500" htmlFor="admin-user-role">Role</label>
                      <select
                        id="admin-user-role"
                        value={roleDraft}
                        onChange={(event) => setRoleDraft(event.target.value)}
                        className="rounded border border-slate-700 bg-[#111827] px-3 py-2 text-sm font-bold text-white outline-none focus:border-ai-cyan"
                      >
                        <option value="USER">USER</option>
                        <option value="ADMIN">ADMIN</option>
                      </select>
                      <button
                        type="button"
                        onClick={handleUpdateRole}
                        disabled={roleLoading || roleDraft === modalUser.role}
                        className="mt-2 rounded bg-ai-cyan px-4 py-2 text-xs font-bold text-slate-950 transition hover:bg-cyan-300 disabled:cursor-not-allowed disabled:opacity-50"
                      >
                        {roleLoading ? '변경 중' : '권한 변경'}
                      </button>
                      {roleNotice ? <p className="text-xs font-bold text-slate-400">{roleNotice}</p> : null}
                    </div>
                  </div>
                ) : null}
              </div>
            </div>
          </div>
        ) : null}
      </div>
    </div>
  )
}
