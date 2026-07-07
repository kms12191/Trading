import { useMemo, useState } from 'react'
import Header from '../components/Header.jsx'

const inquiryStatusLabels = {
  RECEIVED: '답변 대기',
  WAITING: '답변 대기',
  COMPLETED: '답변 완료',
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

const mockInquiries = [
  {
    id: 'mock-1',
    title: '평가금액이 실제 계좌와 다르게 표시됩니다.',
    inquiryType: 'account',
    status: 'RECEIVED',
    userEmail: 'user01@example.com',
    content: '대시보드의 평가금액과 증권사 앱의 평가금액이 다르게 보입니다. 새로고침 후에도 동일합니다.',
    answer: '',
    fileName: 'account-balance.png',
    createdAt: '2026-07-07T09:20:00+09:00',
  },
  {
    id: 'mock-2',
    title: '주문 실패 사유를 확인하고 싶습니다.',
    inquiryType: 'order',
    status: 'WAITING',
    userEmail: 'trader@example.com',
    content: '매수 주문 버튼을 눌렀는데 실패로 표시됩니다. 잔고는 충분한 상태입니다.',
    answer: '',
    fileName: '',
    createdAt: '2026-07-06T14:05:00+09:00',
  },
  {
    id: 'mock-3',
    title: '첨부파일 등록 문의',
    inquiryType: 'etc',
    status: 'COMPLETED',
    userEmail: 'helpme@example.com',
    content: 'PDF 파일 첨부가 가능한지 궁금합니다.',
    answer: 'PDF 파일은 5MB 이하인 경우 첨부할 수 있습니다.',
    fileName: '',
    createdAt: '2026-07-05T18:30:00+09:00',
  },
]

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
    message: (
      <>
        <path strokeLinecap="round" strokeLinejoin="round" d="M4.5 5.5h15v10h-8l-4.5 4v-4H4.5z" />
        <path strokeLinecap="round" strokeLinejoin="round" d="M8 10.5h.01M12 10.5h.01M16 10.5h.01" />
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

function SummaryCard({ label, value, icon, tone }) {
  return (
    <div className="rounded-lg border border-slate-800 bg-[#0f172a] p-4">
      <div className="flex items-center gap-3">
        <span className={`grid h-10 w-10 place-items-center rounded-full border border-current/30 bg-white/[0.03] ${tone}`}>
          <Icon name={icon} className="h-5 w-5" />
        </span>
        <p className="text-xs font-bold text-slate-400">{label}</p>
      </div>
      <p className="mt-3 font-mono text-2xl font-extrabold text-white">{value}</p>
    </div>
  )
}

function ReplyModal({ inquiry, onClose }) {
  const [answer, setAnswer] = useState(inquiry?.answer || '')
  const [status, setStatus] = useState(inquiry?.status === 'COMPLETED' ? 'COMPLETED' : 'COMPLETED')

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
          <label className="grid gap-2 sm:max-w-xs">
            <span className="text-xs font-bold text-slate-400">처리 상태</span>
            <select
              value={status}
              onChange={(event) => setStatus(event.target.value)}
              className="rounded border border-slate-700 bg-[#0f172a] px-3 py-2 text-sm font-bold text-slate-300 outline-none transition focus:border-ai-cyan"
            >
              <option value="WAITING">답변 대기</option>
              <option value="COMPLETED">답변 완료</option>
              <option value="CANCELED">취소됨</option>
            </select>
          </label>
        </div>
        <div className="flex justify-end gap-2 border-t border-slate-800 px-5 py-4">
          <button
            type="button"
            className="rounded border border-slate-700 px-4 py-2 text-xs font-bold text-slate-300 transition hover:border-slate-500 hover:text-white"
            onClick={onClose}
          >
            취소
          </button>
          <button
            type="button"
            className="rounded bg-ai-cyan px-4 py-2 text-xs font-bold text-slate-950 transition hover:bg-cyan-300"
            onClick={onClose}
          >
            답변 등록
          </button>
        </div>
      </div>
    </div>
  )
}

export default function AdminInquiries({ isLoggedIn, userEmail, handleLogout }) {
  const [sortOrder, setSortOrder] = useState('desc')
  const [expandedInquiryId, setExpandedInquiryId] = useState(mockInquiries[0]?.id || null)
  const [replyInquiry, setReplyInquiry] = useState(null)

  const sortedInquiries = useMemo(() => {
    return [...mockInquiries].sort((left, right) => {
      const leftTime = new Date(left.createdAt).getTime() || 0
      const rightTime = new Date(right.createdAt).getTime() || 0
      return sortOrder === 'asc' ? leftTime - rightTime : rightTime - leftTime
    })
  }, [sortOrder])

  const summary = useMemo(() => ({
    total: mockInquiries.length,
    waiting: mockInquiries.filter((item) => item.status === 'RECEIVED' || item.status === 'WAITING').length,
    completed: mockInquiries.filter((item) => item.status === 'COMPLETED').length,
  }), [])

  return (
    <div className="min-h-screen bg-obsidian-bg font-inter text-[#e2e2ec]">
      <div className="mx-auto grid max-w-7xl gap-6 px-6 py-8">
        <Header isLoggedIn={isLoggedIn} userEmail={userEmail} handleLogout={handleLogout} />

        <section className="rounded-lg border border-slate-700/80 bg-slate-surface p-5">
          <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
            <div>
              <p className="text-[10px] font-bold uppercase tracking-[0.16em] text-ai-cyan">Admin Support</p>
              <h1 className="mt-1 text-2xl font-extrabold text-white">문의 답변 관리</h1>
              <p className="mt-2 text-sm text-slate-400">사용자 문의를 확인하고 답변을 작성하는 관리자 화면입니다.</p>
            </div>
            <select
              value={sortOrder}
              onChange={(event) => setSortOrder(event.target.value)}
              className="rounded border border-slate-700 bg-[#0f172a] px-3 py-2 text-xs font-bold text-slate-300 outline-none transition focus:border-ai-cyan"
              aria-label="문의 정렬"
            >
              <option value="desc">최신순</option>
              <option value="asc">과거순</option>
            </select>
          </div>

          <div className="mt-5 grid gap-3 sm:grid-cols-3">
            <SummaryCard label="전체 문의" value={summary.total} icon="document" tone="text-ai-cyan" />
            <SummaryCard label="답변 대기" value={summary.waiting} icon="clock" tone="text-amber-400" />
            <SummaryCard label="답변 완료" value={summary.completed} icon="check" tone="text-emerald-400" />
          </div>
        </section>

        <section className="rounded-lg border border-slate-700/80 bg-slate-surface p-4">
          <div className="grid grid-cols-[minmax(180px,1.5fr)_120px_180px_120px_120px] rounded-t-lg bg-[#0f172a] text-xs font-bold text-slate-400">
            <div className="px-4 py-3">제목</div>
            <div className="px-4 py-3">유형</div>
            <div className="px-4 py-3">작성자</div>
            <div className="px-4 py-3">상태</div>
            <div className="px-4 py-3">작성일</div>
          </div>

          <div className="overflow-hidden rounded-b-lg border border-t-0 border-slate-800">
            {sortedInquiries.map((item) => {
              const isExpanded = expandedInquiryId === item.id
              return (
                <div key={item.id} className="border-t border-slate-800 first:border-t-0">
                  <button
                    type="button"
                    aria-expanded={isExpanded}
                    className="grid w-full grid-cols-[minmax(180px,1.5fr)_120px_180px_120px_120px] text-left text-sm text-slate-300 transition hover:bg-white/[0.03]"
                    onClick={() => setExpandedInquiryId(isExpanded ? null : item.id)}
                  >
                    <span className="px-4 py-3 font-bold text-white">{item.title}</span>
                    <span className="px-4 py-3">{inquiryTypeLabels[item.inquiryType] || '-'}</span>
                    <span className="truncate px-4 py-3">{item.userEmail}</span>
                    <span className="px-4 py-3">{inquiryStatusLabels[item.status] || item.status}</span>
                    <span className="px-4 py-3">{formatDate(item.createdAt)}</span>
                  </button>

                  {isExpanded ? (
                    <div className="grid gap-3 bg-[#0f172a]/70 px-4 py-4 text-xs leading-5 text-slate-300 md:grid-cols-2">
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
                      <div className="flex justify-end md:col-span-2">
                        <button
                          type="button"
                          className="inline-flex items-center gap-2 rounded border border-ai-cyan/40 px-3 py-1.5 text-xs font-bold text-ai-cyan transition hover:border-ai-cyan hover:bg-ai-cyan/10"
                          onClick={() => setReplyInquiry(item)}
                        >
                          <Icon name="reply" className="h-4 w-4" />
                          답변
                        </button>
                      </div>
                    </div>
                  ) : null}
                </div>
              )
            })}
          </div>
        </section>
      </div>

      <ReplyModal inquiry={replyInquiry} onClose={() => setReplyInquiry(null)} />
    </div>
  )
}
