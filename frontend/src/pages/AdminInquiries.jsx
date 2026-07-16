import { useCallback, useEffect, useMemo, useState } from 'react'
import Header from '../components/Header.jsx'
import { supabase } from '../supabaseClient.js'

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:5050'

const inquiryStatusLabels = {
  RECEIVED: '답변 대기',
  WAITING: '답변 대기',
  COMPLETED: '답변 완료',
  NEED_MORE: '추가 확인',
  CANCELED: '취소됨',
}

const inquiryTypeLabels = {
  account: '계좌',
  order: '주문/체결',
  transfer: '입출금',
  'domestic-stock': '국내주식',
  'global-stock': '해외주식',
  crypto: '코인',
  system: '시스템 오류',
  etc: '기타',
}

const getInquiryStatusVisual = (status = '') => {
  const normalizedStatus = String(status).toUpperCase()
  if (normalizedStatus === 'COMPLETED') {
    return { icon: 'check', tone: 'text-emerald-400' }
  }
  return { icon: 'clock', tone: 'text-amber-300' }
}

const getSummaryStatusFilter = (key) => {
  if (key === 'waiting') return 'WAITING'
  if (key === 'completed') return 'COMPLETED'
  return 'all'
}

const filterInquiriesByStatus = (inquiries, statusFilter = 'all') => {
  if (statusFilter === 'all') return inquiries
  if (statusFilter === 'WAITING') {
    return inquiries.filter((item) => item.status === 'RECEIVED' || item.status === 'WAITING')
  }
  return inquiries.filter((item) => item.status === statusFilter)
}

const formatDate = (value) => {
  const date = value ? new Date(value) : null
  if (!date || Number.isNaN(date.getTime())) return '-'
  return date.toLocaleDateString('ko-KR', {
    year: '2-digit',
    month: '2-digit',
    day: '2-digit',
  })
}

function Icon({ name, className = 'h-5 w-5' }) {
  const icons = {
    check: <path strokeLinecap="round" strokeLinejoin="round" d="M5 12.5l4 4 10-10" />,
    clock: (
      <>
        <circle cx="12" cy="12" r="8.5" />
        <path strokeLinecap="round" strokeLinejoin="round" d="M12 7.5V12l3 2" />
      </>
    ),
    document: (
      <>
        <path strokeLinecap="round" strokeLinejoin="round" d="M7 3.5h6l4 4v13H7z" />
        <path strokeLinecap="round" strokeLinejoin="round" d="M13 3.5v4h4M9.5 11.5h5M9.5 15h5" />
      </>
    ),
    paperclip: <path strokeLinecap="round" strokeLinejoin="round" d="M8.5 12.5l5.7-5.7a3 3 0 114.2 4.2l-7.1 7.1a4.5 4.5 0 01-6.4-6.4l7.1-7.1" />,
    reply: (
      <>
        <path strokeLinecap="round" strokeLinejoin="round" d="M9 9l-4 4 4 4" />
        <path strokeLinecap="round" strokeLinejoin="round" d="M5 13h8a5 5 0 015 5v1" />
      </>
    ),
  }

  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" aria-hidden="true">
      {icons[name] || icons.document}
    </svg>
  )
}

function SummaryCard({ label, value, icon, tone, active = false, onClick }) {
  return (
    <button
      type="button"
      aria-pressed={active}
      data-summary-filter={icon === 'clock' ? 'waiting' : icon === 'check' ? 'completed' : 'total'}
      className={`rounded-lg border p-4 text-left transition ${
        active
          ? 'border-institutional-blue bg-institutional-blue/20'
          : 'border-slate-800 bg-[#0f172a] hover:border-slate-600'
      }`}
      onClick={onClick}
    >
      <div className="flex items-center gap-3">
        <span className={`grid h-10 w-10 place-items-center rounded-full border border-current/30 bg-white/[0.03] ${tone}`}>
          <Icon name={icon} className="h-5 w-5" />
        </span>
        <p className="text-xs font-bold text-slate-400">{label}</p>
      </div>
      <p className="mt-3 font-mono text-2xl font-extrabold text-white">{value}</p>
    </button>
  )
}

function EmptyInquiryState() {
  return (
    <div className="grid min-h-48 place-items-center border-t border-slate-800 px-4 py-10 text-center text-sm text-slate-500">
      <div>
        <span className="mx-auto mb-3 grid h-12 w-12 place-items-center rounded-lg border border-slate-700/70 bg-[#0f172a] text-slate-500">
          <Icon name="document" className="h-6 w-6" />
        </span>
        <p className="font-bold text-slate-300">문의 내용이 없습니다.</p>
        <p className="mt-1 text-xs text-slate-500">사용자가 문의를 등록하면 이곳에 표시됩니다.</p>
      </div>
    </div>
  )
}

function ReplyModal({ inquiry, isSubmitting, error, onClose, onSubmit }) {
  const [answer, setAnswer] = useState(inquiry?.answer || '')

  if (!inquiry) return null

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4 backdrop-blur-sm">
      <div className="w-full max-w-2xl rounded-lg border border-slate-700 bg-slate-surface shadow-2xl">
        <div className="border-b border-slate-800 px-5 py-4">
          <p className="text-[10px] font-bold uppercase tracking-[0.16em] text-ai-cyan">Reply</p>
          <h2 className="mt-1 text-lg font-extrabold text-white">문의 답변</h2>
          <p className="mt-1 text-sm text-slate-400">{inquiry.title}</p>
        </div>
        <div className="grid gap-4 p-5">
          <div className="rounded-lg border border-slate-800 bg-[#0f172a] p-4">
            <p className="text-xs font-bold text-slate-500">문의 내용</p>
            <p className="mt-2 whitespace-pre-wrap text-sm leading-6 text-slate-300">{inquiry.content}</p>
          </div>
          <label className="grid gap-2">
            <span className="text-xs font-bold text-slate-400">답변 내용</span>
            <textarea
              value={answer}
              onChange={(event) => setAnswer(event.target.value)}
              className="min-h-40 resize-none rounded border border-slate-700 bg-[#0f172a] px-3 py-2 text-sm leading-6 text-white outline-none transition focus:border-ai-cyan"
              placeholder="문의에 대한 답변을 입력해주세요."
            />
          </label>
          {error ? <p className="text-xs font-bold text-rose-400">{error}</p> : null}
        </div>
        <div className="flex justify-end gap-2 border-t border-slate-800 px-5 py-4">
          <button
            type="button"
            className="rounded border border-slate-700 px-4 py-2 text-xs font-bold text-slate-300 transition hover:border-slate-500 hover:text-white"
            onClick={onClose}
            disabled={isSubmitting}
          >
            취소
          </button>
          <button
            type="button"
            className="rounded bg-ai-cyan px-4 py-2 text-xs font-bold text-slate-950 transition hover:bg-cyan-300 disabled:cursor-not-allowed disabled:opacity-60"
            onClick={() => onSubmit(inquiry.id, { answer, status: 'COMPLETED' })}
            disabled={isSubmitting}
          >
            {isSubmitting ? '저장 중...' : '답변 등록'}
          </button>
        </div>
      </div>
    </div>
  )
}

export default function AdminInquiries({ isLoggedIn, userEmail, handleLogout, hideHeader = false }) {
  const [inquiries, setInquiries] = useState([])
  const [sortOrder, setSortOrder] = useState('desc')
  const [expandedInquiryId, setExpandedInquiryId] = useState(null)
  const [replyInquiry, setReplyInquiry] = useState(null)
  const [isLoading, setIsLoading] = useState(false)
  const [loadError, setLoadError] = useState('')
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [submitError, setSubmitError] = useState('')
  const [canReply, setCanReply] = useState(false)
  const [statusFilter, setStatusFilter] = useState('all')

  const fetchAdminInquiries = useCallback(async () => {
    setIsLoading(true)
    setLoadError('')
    try {
      const { data: { session } } = await supabase.auth.getSession()
      if (!session?.access_token) {
        throw new Error('로그인이 필요합니다.')
      }

      const response = await fetch(`${API_BASE_URL}/api/admin/inquiries`, {
        headers: {
          Authorization: `Bearer ${session.access_token}`,
        },
      })
      const payload = await response.json().catch(() => ({}))
      if (!response.ok || payload.success === false) {
        throw new Error(payload.message || '문의 목록을 불러오지 못했습니다.')
      }

      const rows = payload.data || []
      setInquiries(rows)
      setCanReply(Boolean(payload.canReply))
      setExpandedInquiryId((currentId) => (
        rows.some((item) => item.id === currentId) ? currentId : null
      ))
    } catch (error) {
      setInquiries([])
      setCanReply(false)
      setLoadError(error.message || '문의 목록을 불러오지 못했습니다.')
    } finally {
      setIsLoading(false)
    }
  }, [])

  useEffect(() => {
    const timeoutId = window.setTimeout(fetchAdminInquiries, 0)
    return () => window.clearTimeout(timeoutId)
  }, [fetchAdminInquiries])

  const sortedInquiries = useMemo(() => {
    return [...inquiries].sort((left, right) => {
      const leftTime = new Date(left.createdAt).getTime() || 0
      const rightTime = new Date(right.createdAt).getTime() || 0
      return sortOrder === 'asc' ? leftTime - rightTime : rightTime - leftTime
    })
  }, [inquiries, sortOrder])

  const filteredInquiries = useMemo(() => {
    return filterInquiriesByStatus(sortedInquiries, statusFilter)
  }, [sortedInquiries, statusFilter])

  const summary = useMemo(() => ({
    total: inquiries.length,
    waiting: inquiries.filter((item) => item.status === 'RECEIVED' || item.status === 'WAITING').length,
    completed: inquiries.filter((item) => item.status === 'COMPLETED').length,
  }), [inquiries])

  const handleReplySubmit = async (inquiryId, payload) => {
    setIsSubmitting(true)
    setSubmitError('')
    try {
      const { data: { session } } = await supabase.auth.getSession()
      if (!session?.access_token) {
        throw new Error('로그인이 필요합니다.')
      }

      const response = await fetch(`${API_BASE_URL}/api/admin/inquiries/${inquiryId}/reply`, {
        method: 'PATCH',
        headers: {
          Authorization: `Bearer ${session.access_token}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(payload),
      })
      const result = await response.json().catch(() => ({}))
      if (!response.ok || result.success === false) {
        throw new Error(result.message || '답변 저장에 실패했습니다.')
      }

      setInquiries((current) => current.map((item) => (item.id === inquiryId ? result.data : item)))
      setReplyInquiry(null)
    } catch (error) {
      setSubmitError(error.message || '답변 저장에 실패했습니다.')
    } finally {
      setIsSubmitting(false)
    }
  }

  const handleSummaryFilterChange = (key) => {
    setStatusFilter(getSummaryStatusFilter(key))
    setExpandedInquiryId(null)
  }

  return (
    <div className={hideHeader ? 'font-inter text-[#e2e2ec]' : 'min-h-screen bg-obsidian-bg font-inter text-[#e2e2ec]'}>
      <div className={hideHeader ? 'grid gap-6' : 'mx-auto grid max-w-7xl gap-6 px-6 py-8'}>
        {!hideHeader ? (
          <Header isLoggedIn={isLoggedIn} userEmail={userEmail} handleLogout={handleLogout} />
        ) : null}

        <section className="rounded-lg border border-slate-700/80 bg-slate-surface p-4 sm:p-5">
          <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
            <div>
              <p className="text-[10px] font-bold uppercase tracking-[0.16em] text-ai-cyan">Admin Support</p>
              <h1 className="mt-1 text-2xl font-extrabold text-white">{canReply ? '문의 답변 관리' : '문의 답변 확인'}</h1>
              <p className="mt-2 text-sm text-slate-400">
                {canReply ? '사용자 문의를 확인하고 답변을 작성하는 관리자 화면입니다.' : '내 문의와 등록된 답변 상태를 확인합니다.'}
              </p>
            </div>
            <select
              value={sortOrder}
              onChange={(event) => setSortOrder(event.target.value)}
              className="w-full rounded border border-slate-700 bg-[#0f172a] px-3 py-2 text-xs font-bold text-slate-300 outline-none transition focus:border-ai-cyan sm:w-auto"
              aria-label="문의 정렬"
            >
              <option value="desc">최신순</option>
              <option value="asc">과거순</option>
            </select>
          </div>

          <div
            className="mt-5 grid gap-3 sm:grid-cols-3"
            onClick={(event) => {
              const summaryCard = event.target.closest('[data-summary-filter]')
              if (!summaryCard || !event.currentTarget.contains(summaryCard)) return
              handleSummaryFilterChange(summaryCard.dataset.summaryFilter)
            }}
          >
            <SummaryCard
              label="전체 문의"
              value={summary.total}
              icon="document"
              tone="text-ai-cyan"
              active={statusFilter === 'all'}
            />
            <SummaryCard
              label="답변 대기"
              value={summary.waiting}
              icon="clock"
              tone="text-amber-400"
              active={statusFilter === 'WAITING'}
            />
            <SummaryCard
              label="답변 완료"
              value={summary.completed}
              icon="check"
              tone="text-emerald-400"
              active={statusFilter === 'COMPLETED'}
            />
          </div>
        </section>

        <section className="overflow-hidden rounded-lg border border-slate-700/80 bg-slate-surface p-3 sm:p-4">
          <div className="hidden grid-cols-[minmax(180px,1.5fr)_120px_180px_120px_120px] rounded-t-lg bg-[#0f172a] text-xs font-bold text-slate-400 lg:grid">
            <div className="px-4 py-3">제목</div>
            <div className="px-4 py-3">유형</div>
            <div className="px-4 py-3">작성자</div>
            <div className="px-4 py-3">상태</div>
            <div className="px-4 py-3">작성일</div>
          </div>

          <div className="overflow-hidden rounded-lg border border-slate-800 lg:rounded-b-lg lg:rounded-t-none lg:border-t-0">
            {isLoading ? (
              <div className="border-t border-slate-800 px-4 py-10 text-center text-sm font-bold text-slate-400">문의 목록을 불러오는 중입니다.</div>
            ) : loadError ? (
              <div className="border-t border-slate-800 px-4 py-10 text-center text-sm font-bold text-rose-400">{loadError}</div>
            ) : filteredInquiries.length === 0 ? (
              <EmptyInquiryState />
            ) : filteredInquiries.map((item) => {
              const isExpanded = expandedInquiryId === item.id
              const statusVisual = getInquiryStatusVisual(item.status)
              return (
                <div key={item.id} className="border-t border-slate-800 first:border-t-0">
                  <button
                    type="button"
                    aria-expanded={isExpanded}
                    className="grid w-full grid-cols-1 gap-2 px-4 py-4 text-left text-sm text-slate-300 transition hover:bg-white/[0.03] sm:grid-cols-2 lg:grid-cols-[minmax(180px,1.5fr)_120px_180px_120px_120px] lg:gap-0 lg:px-0 lg:py-0"
                    onClick={() => setExpandedInquiryId(isExpanded ? null : item.id)}
                  >
                    <span className="min-w-0 font-bold text-white sm:col-span-2 lg:col-span-1 lg:px-4 lg:py-3">{item.title}</span>
                    <span className="text-xs text-slate-400 lg:px-4 lg:py-3 lg:text-sm lg:text-slate-300">{inquiryTypeLabels[item.inquiryType] || '-'}</span>
                    <span className="min-w-0 truncate text-xs text-slate-400 lg:px-4 lg:py-3 lg:text-sm lg:text-slate-300">{item.userEmail}</span>
                    <span className="inline-flex items-center gap-1.5 text-xs font-bold text-slate-200 lg:px-4 lg:py-3 lg:text-sm lg:font-normal lg:text-slate-300">
                      <Icon name={statusVisual.icon} className={`h-3.5 w-3.5 shrink-0 ${statusVisual.tone}`} />
                      <span>{inquiryStatusLabels[item.status] || item.status}</span>
                    </span>
                    <span className="text-xs text-slate-500 sm:text-right lg:px-4 lg:py-3 lg:text-left lg:text-sm lg:text-slate-300">{formatDate(item.createdAt)}</span>
                  </button>

                  {isExpanded ? (
                    <div className="grid gap-3 bg-[#0f172a]/70 px-3 py-4 text-xs leading-5 text-slate-300 sm:px-4 md:grid-cols-2">
                      <div className="rounded-lg border border-slate-800 bg-slate-surface p-3">
                        <p className="font-bold text-slate-500">문의 내용</p>
                        <p className="mt-2 whitespace-pre-wrap">{item.content}</p>
                      </div>
                      <div className="rounded-lg border border-slate-800 bg-slate-surface p-3">
                        <p className="font-bold text-slate-500">기존 답변</p>
                        <p className="mt-2 whitespace-pre-wrap">{item.answer || '아직 등록된 답변이 없습니다.'}</p>
                      </div>
                      <div className="rounded-lg border border-slate-800 bg-slate-surface p-3">
                        <p className="font-bold text-slate-500">첨부파일</p>
                        <p className="mt-2 flex items-center gap-2">
                          <Icon name="paperclip" className="h-4 w-4 text-ai-cyan" />
                          {item.fileName || '첨부파일 없음'}
                        </p>
                      </div>
                      <div className="rounded-lg border border-slate-800 bg-slate-surface p-3">
                        <p className="font-bold text-slate-500">처리 상태</p>
                        <p className="mt-2">{inquiryStatusLabels[item.status] || item.status}</p>
                      </div>
                      {canReply ? (
                        <div className="flex justify-stretch md:col-span-2 md:justify-end">
                          <button
                            type="button"
                            className="inline-flex w-full items-center justify-center gap-2 rounded border border-ai-cyan/40 px-3 py-2 text-xs font-bold text-ai-cyan transition hover:border-ai-cyan hover:bg-ai-cyan/10 sm:w-auto sm:py-1.5"
                            onClick={() => {
                              setSubmitError('')
                              setReplyInquiry(item)
                            }}
                          >
                            <Icon name="reply" className="h-4 w-4" />
                            답변
                          </button>
                        </div>
                      ) : null}
                    </div>
                  ) : null}
                </div>
              )
            })}
          </div>
        </section>
      </div>

      <ReplyModal
        key={replyInquiry?.id || 'reply-empty'}
        inquiry={replyInquiry}
        isSubmitting={isSubmitting}
        error={submitError}
        onClose={() => setReplyInquiry(null)}
        onSubmit={handleReplySubmit}
      />
    </div>
  )
}
