import { useEffect, useMemo, useRef, useState } from 'react'
import Header from '../components/Header.jsx'
import { supabase } from '../supabaseClient.js'
import { getApiErrorMessage } from '../lib/apiError.js'

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:5050'
const USER_PAGE_SIZE = 100

const numberFormatter = new Intl.NumberFormat('ko-KR')

function formatNumber(value) {
  return numberFormatter.format(Number(value || 0))
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

function SummaryCard({ label, value, detail }) {
  return (
    <div className="rounded-lg border border-slate-800 bg-[#0f172a] p-4">
      <p className="text-xs font-bold text-slate-400">{label}</p>
      <p className="mt-2 font-mono text-2xl font-extrabold text-white">{value}</p>
      {detail ? <p className="mt-1 text-xs text-slate-500">{detail}</p> : null}
    </div>
  )
}

export default function AdminUsers({ isLoggedIn, userEmail, handleLogout, hideHeader = false }) {
  const [users, setUsers] = useState([])
  const [summary, setSummary] = useState({ totalUsers: 0, todayTokens: 0, tokens30d: 0, activeUsers24h: 0 })
  const [query, setQuery] = useState('')
  const [sort, setSort] = useState('tokens_30d')
  const [order, setOrder] = useState('desc')
  const [page, setPage] = useState(0)
  const [selectedUserId, setSelectedUserId] = useState('')
  const [detail, setDetail] = useState(null)
  const [loading, setLoading] = useState(false)
  const [detailLoading, setDetailLoading] = useState(false)
  const [error, setError] = useState('')
  const [detailError, setDetailError] = useState('')
  const listRequestSequence = useRef(0)
  const detailRequestSequence = useRef(0)

  const selectedUser = useMemo(
    () => users.find((item) => item.id === selectedUserId) || users[0] || null,
    [selectedUserId, users],
  )

  const authHeaders = async () => {
    const { data: { session } } = await supabase.auth.getSession()
    if (!session?.access_token) throw new Error('로그인이 필요합니다.')
    return { Authorization: `Bearer ${session.access_token}` }
  }

  const totalUsers = Number(summary.totalUsers || 0)
  const totalPages = Math.max(1, Math.ceil(totalUsers / USER_PAGE_SIZE))
  const pageStart = users.length ? page * USER_PAGE_SIZE + 1 : 0
  const pageEnd = users.length ? page * USER_PAGE_SIZE + users.length : 0

  const loadUsers = async ({ pageOverride = page, signal } = {}) => {
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
      if (query.trim()) params.set('q', query.trim())
      const response = await fetch(`${API_BASE_URL}/api/admin/users?${params.toString()}`, { headers, signal })
      const payload = await response.json().catch(() => ({}))
      if (!response.ok || payload.success === false) {
        throw new Error(getApiErrorMessage(payload, '유저 목록을 불러오지 못했습니다.'))
      }
      if (listRequestSequence.current !== requestSequence) return
      const rows = payload.data || []
      setUsers(rows)
      setSummary(payload.summary || {})
      setSelectedUserId((current) => (rows.some((item) => item.id === current) ? current : rows[0]?.id || ''))
    } catch (requestError) {
      if (requestError.name === 'AbortError' || listRequestSequence.current !== requestSequence) return
      setUsers([])
      setSummary({ totalUsers: 0, todayTokens: 0, tokens30d: 0, activeUsers24h: 0 })
      setError(requestError.message || '유저 목록을 불러오지 못했습니다.')
    } finally {
      if (listRequestSequence.current === requestSequence) {
        setLoading(false)
      }
    }
  }

  useEffect(() => {
    const controller = new AbortController()
    loadUsers({ signal: controller.signal })
    return () => controller.abort()
  }, [sort, order, page])

  const handleSearch = () => {
    if (page === 0) {
      loadUsers({ pageOverride: 0 })
    } else {
      setPage(0)
    }
  }

  useEffect(() => {
    const userId = selectedUser?.id
    const requestSequence = detailRequestSequence.current + 1
    detailRequestSequence.current = requestSequence

    if (!userId) {
      setDetail(null)
      setDetailLoading(false)
      setDetailError('')
      return undefined
    }

    const controller = new AbortController()
    setDetail(null)
    setDetailLoading(true)
    setDetailError('')

    const loadDetail = async () => {
      try {
        const headers = await authHeaders()
        if (controller.signal.aborted) return

        const response = await fetch(`${API_BASE_URL}/api/admin/users/${userId}/chatbot-usage?days=30&limit=50`, {
          headers,
          signal: controller.signal,
        })
        const payload = await response.json().catch(() => ({}))
        if (!response.ok || payload.success === false) {
          throw new Error(getApiErrorMessage(payload, '유저 사용량을 불러오지 못했습니다.'))
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
    }

    loadDetail()
    return () => controller.abort()
  }, [selectedUser?.id])

  return (
    <div className={hideHeader ? 'font-inter text-[#e2e2ec]' : 'min-h-screen bg-obsidian-bg font-inter text-[#e2e2ec]'}>
      <div className={hideHeader ? 'grid gap-6' : 'mx-auto grid max-w-7xl gap-6 px-6 py-8'}>
        {!hideHeader ? <Header isLoggedIn={isLoggedIn} userEmail={userEmail} handleLogout={handleLogout} /> : null}

        <section className="rounded-lg border border-slate-700/80 bg-slate-surface p-4 sm:p-5">
          <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
            <div>
              <p className="text-[10px] font-bold uppercase tracking-[0.16em] text-ai-cyan">Admin Users</p>
              <h1 className="mt-1 text-2xl font-extrabold text-white">유저 관리</h1>
              <p className="mt-2 text-sm text-slate-400">사용자별 실제 챗봇 토큰 사용량과 최근 사용 흐름을 확인합니다.</p>
            </div>
            <div className="grid gap-2 sm:grid-cols-[minmax(220px,1fr)_150px_120px_auto]">
              <input
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === 'Enter') handleSearch()
                }}
                className="rounded border border-slate-700 bg-[#0f172a] px-3 py-2 text-sm text-white outline-none transition focus:border-ai-cyan"
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
            </div>
          </div>

          <div className="mt-5 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <SummaryCard label="전체 유저" value={formatNumber(summary.totalUsers)} />
            <SummaryCard label="오늘 실제 토큰" value={formatNumber(summary.todayTokens)} />
            <SummaryCard label="30일 실제 토큰" value={formatNumber(summary.tokens30d)} />
            <SummaryCard label="24시간 활성 유저" value={formatNumber(summary.activeUsers24h)} />
          </div>
        </section>

        <section className="grid gap-5 xl:grid-cols-[minmax(0,1.2fr)_minmax(360px,0.8fr)]">
          <div className="overflow-hidden rounded-lg border border-slate-700/80 bg-slate-surface p-3 sm:p-4">
            <div className="lg:overflow-x-auto">
              <div className="lg:min-w-[760px]">
                <div className="hidden grid-cols-[minmax(170px,1.2fr)_90px_repeat(4,minmax(95px,1fr))_120px] rounded-t-lg bg-[#0f172a] text-xs font-bold text-slate-400 lg:grid">
                  <div className="px-3 py-3">유저</div>
                  <div className="px-3 py-3">권한</div>
                  <div className="px-3 py-3 text-right">오늘</div>
                  <div className="px-3 py-3 text-right">7일</div>
                  <div className="px-3 py-3 text-right">30일</div>
                  <div className="px-3 py-3 text-right">전체</div>
                  <div className="px-3 py-3">최근 사용</div>
                </div>
                <div className="overflow-hidden rounded-lg border border-slate-800 lg:rounded-t-none lg:border-t-0">
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
                      onClick={() => setSelectedUserId(item.id)}
                      className={`grid w-full grid-cols-2 gap-2 border-t border-slate-800 px-4 py-4 text-left text-sm first:border-t-0 hover:bg-white/[0.03] lg:grid-cols-[minmax(170px,1.2fr)_90px_repeat(4,minmax(95px,1fr))_120px] lg:px-0 lg:py-0 ${selectedUser?.id === item.id ? 'bg-ai-cyan/5' : ''}`}
                    >
                      <span className="min-w-0 lg:px-3 lg:py-3">
                        <span className="block truncate font-bold text-white">{item.email || item.nickname || '-'}</span>
                        <span className="block truncate text-xs text-slate-500">{item.nickname || item.id}</span>
                      </span>
                      <span className="text-xs font-bold text-ai-cyan lg:px-3 lg:py-3">{item.role}</span>
                      <span className="flex items-center justify-between gap-2 font-mono text-xs text-slate-300 lg:block lg:px-3 lg:py-3 lg:text-right">
                        <span className="font-inter font-bold text-slate-500 lg:hidden">오늘</span>
                        <span>{formatNumber(item.usage?.todayTokens)}</span>
                      </span>
                      <span className="flex items-center justify-between gap-2 font-mono text-xs text-slate-300 lg:block lg:px-3 lg:py-3 lg:text-right">
                        <span className="font-inter font-bold text-slate-500 lg:hidden">7일</span>
                        <span>{formatNumber(item.usage?.tokens7d)}</span>
                      </span>
                      <span className="flex items-center justify-between gap-2 font-mono text-xs text-white lg:block lg:px-3 lg:py-3 lg:text-right">
                        <span className="font-inter font-bold text-slate-500 lg:hidden">30일</span>
                        <span>{formatNumber(item.usage?.tokens30d)}</span>
                      </span>
                      <span className="flex items-center justify-between gap-2 font-mono text-xs text-slate-300 lg:block lg:px-3 lg:py-3 lg:text-right">
                        <span className="font-inter font-bold text-slate-500 lg:hidden">전체</span>
                        <span>{formatNumber(item.usage?.totalTokens)}</span>
                      </span>
                      <span className="col-span-2 text-xs text-slate-500 lg:col-span-1 lg:px-3 lg:py-3">{formatDateTime(item.usage?.recentUsedAt)}</span>
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

          <div className="rounded-lg border border-slate-700/80 bg-slate-surface p-4">
            <h2 className="text-sm font-bold text-white">사용량 상세</h2>
            <p className="mt-1 truncate text-xs text-slate-500">{selectedUser?.email || '유저를 선택하세요.'}</p>
            {detailLoading ? (
              <div className="mt-6 text-sm font-bold text-slate-400">상세 사용량을 불러오는 중입니다.</div>
            ) : detailError ? (
              <div className="mt-6 text-sm font-bold text-rose-400">{detailError}</div>
            ) : detail ? (
              <div className="mt-4 grid gap-5">
                <div className="grid gap-2">
                  {(detail.daily || []).slice(0, 14).map((row) => {
                    const maxTokens = Math.max(...(detail.daily || []).map((item) => Number(item.totalTokens || 0)), 1)
                    const width = `${Math.max(4, Math.round((Number(row.totalTokens || 0) / maxTokens) * 100))}%`
                    return (
                      <div key={row.date} className="grid gap-1">
                        <div className="flex items-center justify-between text-xs">
                          <span className="text-slate-400">{row.date}</span>
                          <span className="font-mono text-white">{formatNumber(row.totalTokens)}</span>
                        </div>
                        <div className="h-2 rounded bg-slate-800">
                          <div className="h-2 rounded bg-ai-cyan" style={{ width }} />
                        </div>
                      </div>
                    )
                  })}
                </div>
                <div className="rounded-lg border border-slate-800 bg-[#0f172a] p-3">
                  <p className="text-xs font-bold text-slate-400">요청 유형별 합계</p>
                  <div className="mt-2 grid gap-2">
                    {Object.entries(detail.byRequestType || {}).map(([type, value]) => (
                      <div key={type} className="flex items-center justify-between gap-3 text-xs">
                        <span className="truncate text-slate-400">{type}</span>
                        <span className="font-mono text-white">{formatNumber(value.totalTokens)}</span>
                      </div>
                    ))}
                  </div>
                </div>
                <div className="rounded-lg border border-slate-800 bg-[#0f172a] p-3">
                  <p className="text-xs font-bold text-slate-400">최근 요청 로그</p>
                  <div className="mt-2 grid gap-2">
                    {(detail.recentLogs || []).slice(0, 8).map((log) => (
                      <div key={`${log.createdAt}-${log.requestType}-${log.totalTokens}`} className="grid grid-cols-[1fr_auto] gap-3 text-xs">
                        <span className="min-w-0 truncate text-slate-400">{formatDateTime(log.createdAt)} · {log.requestType}</span>
                        <span className="font-mono text-white">{formatNumber(log.totalTokens)}</span>
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            ) : null}
          </div>
        </section>
      </div>
    </div>
  )
}
