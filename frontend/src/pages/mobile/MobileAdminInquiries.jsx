import { useCallback, useEffect, useMemo, useState } from 'react'
import Header from '../../components/Header.jsx'
import { supabase } from '../../supabaseClient.js'

// 배포 환경에서는 환경 변수의 API 주소를 사용하고, 없으면 로컬 백엔드 주소를 사용합니다.
const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:5050'

// 백엔드의 문의 상태 코드를 화면에 표시할 한글 문구로 변환합니다.
const inquiryStatusLabels = {
  RECEIVED: '답변 대기',
  WAITING: '답변 대기',
  COMPLETED: '답변 완료',
  NEED_MORE: '추가 확인',
  CANCELED: '취소됨',
}

// 문의 유형 코드를 화면용 한글 이름으로 변환합니다.
const inquiryTypeLabels = {
  account: 'API연동',
  order: '주문/체결',
  transfer: '입출금',
  'domestic-stock': '국내주식',
  'global-stock': '해외주식',
  crypto: '코인',
  system: '시스템 오류',
  etc: '기타',
}

// 문의 유형 선택창에 사용할 필터 목록을 생성합니다.
const inquiryTypeFilterItems = [
  { value: 'all', label: '전체' },
  ...Object.entries(inquiryTypeLabels).map(([value, label]) => ({ value, label })),
]

// 문의 상태에 따라 표시할 아이콘과 색상을 반환합니다.
const getInquiryStatusVisual = (status = '') => {
  const normalizedStatus = String(status).toUpperCase()
  if (normalizedStatus === 'COMPLETED') {
    return { icon: 'check', tone: 'text-emerald-400' }
  }
  return { icon: 'clock', tone: 'text-amber-300' }
}

// 상단 요약 카드의 구분값을 실제 상태 필터 값으로 변환합니다.
const getSummaryStatusFilter = (key) => {
  if (key === 'waiting') return 'WAITING'
  if (key === 'completed') return 'COMPLETED'
  return 'all'
}

// 선택한 처리 상태에 해당하는 문의만 필터링합니다.
const filterInquiriesByStatus = (inquiries, statusFilter = 'all') => {
  if (statusFilter === 'all') return inquiries
  if (statusFilter === 'WAITING') {
    return inquiries.filter((item) => item.status === 'RECEIVED' || item.status === 'WAITING')
  }
  return inquiries.filter((item) => item.status === statusFilter)
}

// 선택한 문의 유형에 해당하는 문의만 필터링합니다.
const filterInquiriesByType = (inquiries, typeFilter = 'all') => {
  if (typeFilter === 'all') return inquiries
  return inquiries.filter((item) => item.inquiryType === typeFilter)
}

// 날짜 값을 한국식 날짜 형식으로 변환하며, 잘못된 값은 '-'로 표시합니다.
const formatDate = (value) => {
  const date = value ? new Date(value) : null
  if (!date || Number.isNaN(date.getTime())) return '-'
  return date.toLocaleDateString('ko-KR', {
    year: '2-digit',
    month: '2-digit',
    day: '2-digit',
  })
}

// 화면에서 공통으로 사용하는 SVG 아이콘을 이름에 따라 출력합니다.
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

// 전체 문의, 답변 대기, 답변 완료 개수를 보여주는 요약 카드입니다.
function SummaryCard({ label, value, icon, tone, active = false }) {
  return (
    <button
      type="button"
      aria-pressed={active}
      data-summary-filter={icon === 'clock' ? 'waiting' : icon === 'check' ? 'completed' : 'total'}
      className={`rounded-lg border p-2.5 text-center transition ${
        active
          ? 'border-institutional-blue bg-institutional-blue/20'
          : 'border-slate-800 bg-[#0f172a] hover:border-slate-600'
      }`}
    >
      <div className="grid justify-items-center gap-1.5">
        <span className={`grid h-8 w-8 place-items-center rounded-full border border-current/30 bg-white/[0.03] ${tone}`}>
          <Icon name={icon} className="h-4 w-4" />
        </span>
        <p className="break-keep text-[10px] font-bold leading-4 text-slate-400">{label}</p>
      </div>
      <p className="mt-1 font-mono text-lg font-extrabold text-white">{value}</p>
    </button>
  )
}

// 문의 유형, 작성자, 상태, 작성일 등의 정보를 동일한 형태로 표시합니다.
function InquiryMeta({ label, value, emphasized = false, icon = '', iconTone = 'text-ai-cyan' }) {
  return (
    <div className="min-w-0 rounded-lg border border-slate-800 bg-[#0b1223] px-3 py-2">
      <p className="text-[10px] font-bold uppercase tracking-[0.12em] text-slate-500">{label}</p>
      <p className={`mt-1 flex min-w-0 items-center gap-1.5 text-xs leading-5 ${emphasized ? 'font-bold text-ai-cyan' : 'text-slate-300'}`}>
        {icon ? <Icon name={icon} className={`h-3.5 w-3.5 shrink-0 ${iconTone}`} /> : null}
        <span className="min-w-0 break-words">{value || '-'}</span>
      </p>
    </div>
  )
}

// 표시할 문의가 없을 때 보여주는 빈 목록 안내 화면입니다.
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

// 선택한 문의의 내용을 확인하고 답변을 작성하는 모달입니다.
function ReplyModal({ inquiry, isSubmitting, error, onClose, onSubmit }) {
  // 기존 답변이 있다면 답변 입력창의 초기값으로 사용합니다.
  const [answer, setAnswer] = useState(inquiry?.answer || '')

  // 선택된 문의가 없으면 모달을 렌더링하지 않습니다.
  if (!inquiry) return null

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4 backdrop-blur-sm">
      <div className="w-full max-w-2xl rounded-lg border border-slate-700 bg-slate-surface shadow-2xl">
        {/* 답변 모달의 제목과 선택된 문의 제목을 표시합니다. */}
        <div className="border-b border-slate-800 px-5 py-4">
          <p className="text-[10px] font-bold uppercase tracking-[0.16em] text-ai-cyan">Reply</p>
          <h2 className="mt-1 text-lg font-extrabold text-white">문의 답변</h2>
          <p className="mt-1 text-sm text-slate-400">{inquiry.title}</p>
        </div>
        {/* 문의 원문과 답변 입력창을 표시합니다. */}
        <div className="grid gap-4 p-5">
          <div className="rounded-lg border border-slate-800 bg-[#0f172a] p-4">
            <p className="text-xs font-bold text-slate-500">문의 내용</p>
            <p className="mt-2 max-h-80 overflow-y-auto whitespace-pre-wrap break-words pr-1 text-sm leading-6 text-slate-300 [overflow-wrap:anywhere]">{inquiry.content}</p>
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
        {/* 모달 닫기와 답변 등록 버튼 영역입니다. */}
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

// 관리자 문의 목록 조회, 필터링, 상세 확인, 답변 등록을 담당하는 메인 화면입니다.
export default function AdminInquiries({ isLoggedIn, userEmail, handleLogout, hideHeader = false }) {
  // 백엔드에서 불러온 전체 문의 목록입니다.
  const [inquiries, setInquiries] = useState([])
  // 현재 선택한 문의 유형 필터입니다.
  const [inquiryTypeFilter, setInquiryTypeFilter] = useState('all')
  // 목록에서 상세 내용이 펼쳐진 문의의 ID입니다.
  const [expandedInquiryId, setExpandedInquiryId] = useState(null)
  // 답변 모달에 표시할 문의이며, null이면 모달이 닫힙니다.
  const [replyInquiry, setReplyInquiry] = useState(null)
  // 문의 목록을 불러오는 중인지 나타냅니다.
  const [isLoading, setIsLoading] = useState(false)
  // 문의 목록 조회 중 발생한 오류 메시지입니다.
  const [loadError, setLoadError] = useState('')
  // 답변을 저장하는 중인지 나타냅니다.
  const [isSubmitting, setIsSubmitting] = useState(false)
  // 답변 저장 중 발생한 오류 메시지입니다.
  const [submitError, setSubmitError] = useState('')
  // 현재 사용자가 문의에 답변할 수 있는 관리자 권한을 가졌는지 나타냅니다.
  const [canReply, setCanReply] = useState(false)
  // 상단 요약 카드에서 선택한 문의 상태 필터입니다.
  const [statusFilter, setStatusFilter] = useState('all')

  // Supabase 로그인 토큰을 사용해 관리자 문의 목록을 백엔드에서 조회합니다.
  const fetchAdminInquiries = useCallback(async () => {
    setIsLoading(true)
    setLoadError('')
    try {
      // 보호된 관리자 API 호출에 사용할 현재 로그인 세션을 가져옵니다.
      const { data: { session } } = await supabase.auth.getSession()
      if (!session?.access_token) {
        throw new Error('로그인이 필요합니다.')
      }

      // access token을 Bearer 토큰으로 전달해 문의 목록 API를 호출합니다.
      const response = await fetch(`${API_BASE_URL}/api/admin/inquiries`, {
        headers: {
          Authorization: `Bearer ${session.access_token}`,
        },
      })
      // 응답이 JSON이 아니어도 오류 처리가 계속되도록 빈 객체로 대체합니다.
      const payload = await response.json().catch(() => ({}))
      if (!response.ok || payload.success === false) {
        throw new Error(payload.message || '문의 목록을 불러오지 못했습니다.')
      }

      // 응답 데이터가 없을 경우 빈 배열을 사용합니다.
      const rows = payload.data || []
      setInquiries(rows)
      setCanReply(Boolean(payload.canReply))
      setExpandedInquiryId((currentId) => (
        rows.some((item) => item.id === currentId) ? currentId : null
      ))
    // 목록 조회가 실패하면 기존 목록과 권한을 초기화하고 오류를 표시합니다.
    } catch (error) {
      setInquiries([])
      setCanReply(false)
      setLoadError(error.message || '문의 목록을 불러오지 못했습니다.')
    // 성공 여부와 관계없이 조회가 끝나면 로딩 상태를 해제합니다.
    } finally {
      setIsLoading(false)
    }
  }, [])

  // 컴포넌트가 처음 표시될 때 문의 목록을 한 번 불러옵니다.
  useEffect(() => {
    const timeoutId = window.setTimeout(fetchAdminInquiries, 0)
    return () => window.clearTimeout(timeoutId)
  }, [fetchAdminInquiries])

  // 원본 배열은 유지하면서 최신 문의가 위에 오도록 작성일 내림차순으로 정렬합니다.
  const sortedInquiries = useMemo(() => {
    return [...inquiries].sort((left, right) => {
      const leftTime = new Date(left.createdAt).getTime() || 0
      const rightTime = new Date(right.createdAt).getTime() || 0
      return rightTime - leftTime
    })
  }, [inquiries])

  // 정렬된 문의 목록에 상태 필터와 유형 필터를 차례로 적용합니다.
  const filteredInquiries = useMemo(() => {
    // 모바일 관리자 문의 목록은 상태 필터와 문의 유형 필터를 순서대로 적용합니다.
    return filterInquiriesByType(filterInquiriesByStatus(sortedInquiries, statusFilter), inquiryTypeFilter)
  }, [inquiryTypeFilter, sortedInquiries, statusFilter])

  // 상단 요약 카드에 표시할 전체, 답변 대기, 답변 완료 개수를 계산합니다.
  const summary = useMemo(() => ({
    total: inquiries.length,
    waiting: inquiries.filter((item) => item.status === 'RECEIVED' || item.status === 'WAITING').length,
    completed: inquiries.filter((item) => item.status === 'COMPLETED').length,
  }), [inquiries])

  // 작성한 답변을 백엔드에 저장하고 해당 문의의 화면 데이터를 갱신합니다.
  const handleReplySubmit = async (inquiryId, payload) => {
    setIsSubmitting(true)
    setSubmitError('')
    try {
      // 보호된 관리자 API 호출에 사용할 현재 로그인 세션을 가져옵니다.
      const { data: { session } } = await supabase.auth.getSession()
      if (!session?.access_token) {
        throw new Error('로그인이 필요합니다.')
      }

      // 선택한 문의의 답변을 수정하는 관리자 API를 호출합니다.
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

      // 전체 목록을 재조회하지 않고 저장된 문의 한 건만 최신 데이터로 교체합니다.
      setInquiries((current) => current.map((item) => (item.id === inquiryId ? result.data : item)))
      setReplyInquiry(null)
    // 답변 저장이 실패하면 오류 메시지를 모달에 표시합니다.
    } catch (error) {
      setSubmitError(error.message || '답변 저장에 실패했습니다.')
    // 성공 여부와 관계없이 답변 저장이 끝나면 제출 상태를 해제합니다.
    } finally {
      setIsSubmitting(false)
    }
  }

  // 요약 카드를 클릭하면 상태 필터를 변경하고 펼쳐진 문의를 닫습니다.
  const handleSummaryFilterChange = (key) => {
    setStatusFilter(getSummaryStatusFilter(key))
    setExpandedInquiryId(null)
  }

  return (
    <div className={hideHeader ? 'font-inter text-[#e2e2ec]' : 'min-h-screen bg-obsidian-bg font-inter text-[#e2e2ec]'}>
      <div className={hideHeader ? 'grid gap-6' : 'mx-auto grid max-w-7xl gap-6 px-6 py-8'}>
        {/* hideHeader가 false일 때만 공통 헤더를 표시합니다. */}
        {!hideHeader ? (
          <Header isLoggedIn={isLoggedIn} userEmail={userEmail} handleLogout={handleLogout} />
        ) : null}

        {/* 화면 제목, 문의 유형 필터, 상태별 요약 카드를 표시합니다. */}
        <section className="rounded-lg border border-slate-700/80 bg-slate-surface p-4 sm:p-5">
          <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
            <div>
              <p className="text-[10px] font-bold uppercase tracking-[0.16em] text-ai-cyan">Admin Support</p>
              <h1 className="mt-1 text-2xl font-extrabold text-white">{canReply ? '문의 답변 관리' : '문의 답변 확인'}</h1>
              <p className="mt-2 text-sm text-slate-400">
                {canReply ? '사용자 문의를 확인하고 답변을 작성하는 관리자 화면입니다.' : '내 문의와 등록된 답변 상태를 확인합니다.'}
              </p>
            </div>
            {/* 문의 유형을 변경하면 펼쳐진 상세 항목도 함께 닫습니다. */}
            <select
              value={inquiryTypeFilter}
              onChange={(event) => {
                setInquiryTypeFilter(event.target.value)
                setExpandedInquiryId(null)
              }}
              className="w-full rounded border border-slate-700 bg-[#0f172a] px-3 py-2 text-xs font-bold text-slate-300 outline-none transition focus:border-ai-cyan sm:w-auto"
              aria-label="문의 유형 필터"
            >
              {inquiryTypeFilterItems.map((item) => (
                <option key={item.value} value={item.value}>{item.label}</option>
              ))}
            </select>
          </div>

          <div
            className="mt-5 grid grid-cols-3 gap-2"
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

        {/* 로딩, 오류, 빈 목록 또는 문의 목록을 현재 상태에 맞게 표시합니다. */}
        <section className="rounded-lg border border-slate-700/80 bg-slate-surface p-3 sm:p-4">
          <div className="rounded-lg border border-slate-800">
            {/* 목록 조회 상태에 따라 로딩, 오류, 빈 화면, 문의 목록 중 하나를 표시합니다. */}
            {isLoading ? (
              <div className="border-t border-slate-800 px-4 py-10 text-center text-sm font-bold text-slate-400">문의 목록을 불러오는 중입니다.</div>
            ) : loadError ? (
              <div className="border-t border-slate-800 px-4 py-10 text-center text-sm font-bold text-rose-400">{loadError}</div>
            ) : filteredInquiries.length === 0 ? (
              <EmptyInquiryState />
            ) : filteredInquiries.map((item) => {
            // 필터링된 문의를 하나씩 목록으로 렌더링합니다.
              // 현재 문의가 선택된 문의인지 확인해 상세 영역 표시 여부를 결정합니다.
              const isExpanded = expandedInquiryId === item.id
              // 문의 상태에 맞는 아이콘과 색상을 가져옵니다.
              const statusVisual = getInquiryStatusVisual(item.status)
              return (
                <div key={item.id} className="border-t border-slate-800 first:border-t-0">
                  <button
                    type="button"
                    aria-expanded={isExpanded}
                    className="grid w-full gap-3 px-3 py-4 text-left text-sm text-slate-300 transition hover:bg-white/[0.03]"
                    onClick={() => setExpandedInquiryId(isExpanded ? null : item.id)}
                  >
                    <div className="min-w-0">
                      <p className="text-[10px] font-bold uppercase tracking-[0.12em] text-slate-500">제목</p>
                      <p className="mt-1 min-w-0 break-words text-base font-extrabold leading-6 text-white">{item.title}</p>
                    </div>
                    <div className="grid gap-2">
                      <InquiryMeta label="유형" value={inquiryTypeLabels[item.inquiryType] || '-'} />
                      <InquiryMeta label="작성자" value={item.userEmail} />
                      <InquiryMeta label="상태" value={inquiryStatusLabels[item.status] || item.status} icon={statusVisual.icon} iconTone={statusVisual.tone} emphasized />
                      <InquiryMeta label="작성일" value={formatDate(item.createdAt)} />
                    </div>
                  </button>

                  {/* 선택된 문의에만 문의 내용과 답변 등의 상세 정보를 표시합니다. */}
                  {isExpanded ? (
                    <div className="grid gap-3 bg-[#0f172a]/70 px-3 py-4 text-xs leading-5 text-slate-300 sm:px-4">
                      {/* 문의와 답변이 매우 길어도 카드 내부에서만 스크롤되도록 제한합니다. */}
                      <div className="min-w-0 rounded-lg border border-slate-800 bg-slate-surface p-3">
                        <p className="font-bold text-slate-500">문의 내용</p>
                        <p className="mt-2 max-h-80 overflow-y-auto whitespace-pre-wrap break-words pr-1 [overflow-wrap:anywhere]">{item.content}</p>
                      </div>
                      <div className="min-w-0 rounded-lg border border-slate-800 bg-slate-surface p-3">
                        <p className="font-bold text-slate-500">기존 답변</p>
                        <p className="mt-2 max-h-80 overflow-y-auto whitespace-pre-wrap break-words pr-1 [overflow-wrap:anywhere]">{item.answer || '아직 등록된 답변이 없습니다.'}</p>
                      </div>
                      <div className="rounded-lg border border-slate-800 bg-slate-surface p-3">
                        <p className="font-bold text-slate-500">첨부파일</p>
                        <p className="mt-2 grid grid-cols-[auto_minmax(0,1fr)] items-center gap-2">
                          <Icon name="paperclip" className="h-4 w-4 shrink-0 text-ai-cyan" />
                          <span className="min-w-0 break-words">{item.fileName || '첨부파일 없음'}</span>
                        </p>
                      </div>
                      <div className="rounded-lg border border-slate-800 bg-slate-surface p-3">
                        <p className="font-bold text-slate-500">처리 상태</p>
                        <p className="mt-2 break-words">{inquiryStatusLabels[item.status] || item.status}</p>
                      </div>
                      {/* 답변 권한이 있는 사용자에게만 답변 버튼을 표시합니다. */}
                      {canReply ? (
                        <div className="flex justify-stretch">
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

      {/* 답변할 문의가 선택되면 답변 작성 모달을 표시합니다. */}
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
