import { useMemo, useState } from 'react'
import Header from '../components/Header.jsx'

const inquiryMenuItems = [
  { key: 'home', label: '문의 홈', icon: 'message' },
  { key: 'history', label: '문의 내역', icon: 'document' },
]

const inquiryTypes = [
  { value: '', label: '문의 유형을 선택해주세요' },
  { value: 'account', label: '계좌' },
  { value: 'order', label: '주문/체결' },
  { value: 'transfer', label: '입출금' },
  { value: 'domestic-stock', label: '국내주식' },
  { value: 'global-stock', label: '해외주식' },
  { value: 'crypto', label: '코인' },
  { value: 'system', label: '시스템 오류' },
  { value: 'etc', label: '기타' },
]

const inquiryStatusItems = [
  { key: 'all', label: '전체', dot: 'bg-blue-400' },
  { key: 'received', label: '접수 완료', dot: 'bg-blue-400' },
  { key: 'waiting', label: '답변 대기', dot: 'bg-amber-400' },
  { key: 'completed', label: '답변 완료', dot: 'bg-emerald-400' },
  { key: 'need-more', label: '추가 확인 필요', dot: 'bg-violet-400' },
]

const summaryItems = [
  { key: 'total', label: '전체 문의', icon: 'inbox', tone: 'text-blue-400' },
  { key: 'waiting', label: '답변 대기', icon: 'clock', tone: 'text-amber-400' },
  { key: 'completed', label: '답변 완료', icon: 'check', tone: 'text-emerald-400' },
  { key: 'needMore', label: '추가 확인 필요', icon: 'question', tone: 'text-violet-400' },
]

// 자주 묻는 질문은 배열로 관리해서 안내 문구를 쉽게 추가하거나 DB 설정값으로 교체할 수 있게 둔다.
const checklistItems = [
  '주문/체결 문의는 종목명과 주문시간을 함께 입력해주세요.',
  '입출금 문의는 거래일과 금액을 함께 입력해주세요.',
  '시스템 오류는 오류 화면 캡처를 첨부해주세요.',
  '계좌 문의는 증권사 또는 거래소 이름을 함께 입력해주세요.',
  '해외주식 문의는 종목 티커와 거래 통화를 함께 적어주세요.',
  '답변 확인이 필요한 문의는 연락 가능한 이메일 정보를 확인해주세요.',
  '개인정보와 계좌 비밀번호는 문의 내용에 직접 입력하지 마세요.',
]

const inquiryColumns = [
  { key: 'title', label: '제목' },
  { key: 'type', label: '유형' },
  { key: 'status', label: '상태' },
  { key: 'createdAt', label: '작성일' },
]

const inquiryHomeSections = {
  checklist: {
    title: '자주 묻는 질문',
    icon: 'info',
  },
  recent: {
    title: '최근 문의 목록',
    icon: 'document',
    emptyMessage: '최근 문의 사항이 없습니다.',
  },
}

const faqItems = [
  {
    question: '문의 답변은 어디에서 확인하나요?',
    answer: '문의 내역에서 접수된 문의와 답변 상태를 확인할 수 있습니다.',
  },
  {
    question: '첨부파일은 꼭 등록해야 하나요?',
    answer: '첨부파일은 선택 항목이며, 오류 화면이나 주문 내역이 있을 때만 첨부하면 됩니다.',
  },
  {
    question: '주문/체결 문의에는 어떤 정보가 필요한가요?',
    answer: '종목명, 주문 시간, 주문 구분을 함께 남기면 확인이 더 빠릅니다.',
  },
]

const guideItems = [
  '운영시간은 평일 09:00-18:00 기준으로 안내됩니다.',
  '개인정보와 계좌 비밀번호는 문의 내용에 직접 입력하지 마세요.',
  '답변이 필요한 문의는 문의 내역에서 상태가 갱신됩니다.',
]

const initialFormState = {
  type: '',
  title: '',
  content: '',
  fileName: '',
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
    info: (
      <>
        <circle cx="12" cy="12" r="8.5" />
        <path strokeLinecap="round" strokeLinejoin="round" d="M12 11v5M12 8h.01" />
      </>
    ),
    inbox: (
      <>
        <path strokeLinecap="round" strokeLinejoin="round" d="M4.5 13.5l2-7h11l2 7v5h-15z" />
        <path strokeLinecap="round" strokeLinejoin="round" d="M4.5 13.5h4l1.5 2h4l1.5-2h4" />
      </>
    ),
    message: (
      <>
        <path strokeLinecap="round" strokeLinejoin="round" d="M4.5 5.5h15v10h-8l-4.5 4v-4H4.5z" />
        <path strokeLinecap="round" strokeLinejoin="round" d="M8 10.5h.01M12 10.5h.01M16 10.5h.01" />
      </>
    ),
    paperclip: (
      <path strokeLinecap="round" strokeLinejoin="round" d="M8.5 12.5l5.7-5.7a3 3 0 114.2 4.2l-7.1 7.1a4.5 4.5 0 01-6.4-6.4l7.1-7.1" />
    ),
    question: (
      <>
        <circle cx="12" cy="12" r="8.5" />
        <path strokeLinecap="round" strokeLinejoin="round" d="M9.8 9a2.4 2.4 0 114.3 1.5c-.9.8-1.6 1.2-1.6 2.5M12 16.5h.01" />
      </>
    ),
  }

  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" aria-hidden="true">
      {icons[name] || icons.info}
    </svg>
  )
}

function Widget({ children, className = '' }) {
  return (
    <section className={`min-h-0 rounded-lg border border-slate-700/80 bg-[#0c1019]/72 p-3 ${className}`}>
      {children}
    </section>
  )
}

function WidgetTitle({ title, icon, action }) {
  return (
    <div className="mb-3 flex items-center justify-between gap-3">
      <div className="flex items-center gap-2">
        {icon ? (
          <span className="grid h-8 w-8 place-items-center rounded-lg border border-blue-500/25 bg-blue-500/10 text-blue-400">
            <Icon name={icon} className="h-4.5 w-4.5" />
          </span>
        ) : null}
        <h2 className="text-base font-extrabold text-white">{title}</h2>
      </div>
      {action}
    </div>
  )
}

function EmptyState({ message, icon = 'inbox' }) {
  return (
    <div className="grid h-full min-h-24 place-items-center border-t border-slate-800 px-4 py-5 text-center text-sm text-slate-500">
      <div>
        <span className="mx-auto mb-2 grid h-11 w-11 place-items-center rounded-lg border border-slate-700/70 bg-[#07111f] text-slate-500">
          <Icon name={icon} className="h-6 w-6" />
        </span>
        <p>{message}</p>
      </div>
    </div>
  )
}

function InquiryTable({ inquiries, emptyMessage, emptyIcon = 'inbox' }) {
  const [expandedInquiryId, setExpandedInquiryId] = useState(null)

  return (
    <div className="flex h-full min-h-0 flex-col overflow-hidden rounded-lg border border-slate-800">
      <div className="grid grid-cols-[minmax(180px,1.5fr)_120px_130px_120px] bg-[#07111f] text-xs font-bold text-slate-400">
        {inquiryColumns.map((column) => (
          <div key={column.key} className="px-4 py-2.5">
            {column.label}
          </div>
        ))}
      </div>

      <div className="min-h-0 flex-1">
        {inquiries.length > 0 ? (
          inquiries.map((item) => {
            const rowId = item.id || `${item.title}-${item.createdAt}`
            const isExpanded = expandedInquiryId === rowId

            return (
              <div key={rowId} className="border-t border-slate-800 text-sm text-slate-300">
                {/* 문의 행을 버튼처럼 만들어 DB 데이터가 들어오면 클릭으로 상세 내용을 펼칠 수 있게 한다. */}
                <button
                  type="button"
                  aria-expanded={isExpanded}
                  className="grid w-full grid-cols-[minmax(180px,1.5fr)_120px_130px_120px] text-left transition hover:bg-white/[0.03]"
                  onClick={() => setExpandedInquiryId(isExpanded ? null : rowId)}
                >
                  {inquiryColumns.map((column) => (
                    <span key={column.key} className="px-4 py-3">
                      {item[column.key] || '-'}
                    </span>
                  ))}
                </button>

                {isExpanded ? (
                  <div className="grid gap-3 bg-[#07111f]/70 px-4 py-4 text-xs leading-5 text-slate-300 md:grid-cols-2">
                    <div className="rounded-lg border border-slate-800 bg-[#0c1019] p-3">
                      <p className="font-bold text-slate-500">문의 내용</p>
                      <p className="mt-2 whitespace-pre-wrap">{item.content || '등록된 문의 내용이 없습니다.'}</p>
                    </div>
                    <div className="rounded-lg border border-slate-800 bg-[#0c1019] p-3">
                      <p className="font-bold text-slate-500">답변 내용</p>
                      <p className="mt-2 whitespace-pre-wrap">{item.answer || '아직 등록된 답변이 없습니다.'}</p>
                    </div>
                    <div className="rounded-lg border border-slate-800 bg-[#0c1019] p-3">
                      <p className="font-bold text-slate-500">첨부파일</p>
                      <p className="mt-2">{item.fileName || '첨부파일 없음'}</p>
                    </div>
                    <div className="rounded-lg border border-slate-800 bg-[#0c1019] p-3">
                      <p className="font-bold text-slate-500">처리 상태</p>
                      <p className="mt-2">{item.status || '-'}</p>
                    </div>
                  </div>
                ) : null}
              </div>
            )
          })
        ) : (
          <EmptyState message={emptyMessage} icon={emptyIcon} />
        )}
      </div>
    </div>
  )
}

export default function Inquiry({ isLoggedIn, userEmail, handleLogout }) {
  const [activeMenu, setActiveMenu] = useState('home')
  const [isSidebarOpen, setIsSidebarOpen] = useState(true)
  const [formState, setFormState] = useState(initialFormState)
  const [formErrors, setFormErrors] = useState({})
  const inquiries = useMemo(() => [], [])

  const waitingInquiries = useMemo(
    () => inquiries.filter((item) => item.status === '답변 대기' || item.status === '접수 완료'),
    [inquiries],
  )
  const completedInquiries = useMemo(
    () => inquiries.filter((item) => item.status === '답변 완료'),
    [inquiries],
  )
  // 문의 데이터가 DB에서 들어오면 문의 내역 상단 현황 카드가 상태별 개수를 자동 계산한다.
  const summaryCounts = useMemo(() => ({
    total: inquiries.length,
    waiting: waitingInquiries.length,
    completed: completedInquiries.length,
    needMore: inquiries.filter((item) => item.status === '추가 확인 필요').length,
  }), [completedInquiries.length, inquiries, waitingInquiries.length])

  const updateField = (field, value) => {
    setFormState((prev) => ({ ...prev, [field]: value }))
    setFormErrors((prev) => ({ ...prev, [field]: '' }))
  }

  const handleSubmit = (event) => {
    event.preventDefault()

    setFormErrors({
      type: formState.type ? '' : '문의 유형을 선택해주세요.',
      title: formState.title.trim() ? '' : '제목을 입력해주세요.',
      content: formState.content.trim() ? '' : '문의 내용을 입력해주세요.',
    })
  }

  const renderInquiryForm = () => (
    <Widget className="h-full">
      <WidgetTitle title="문의 작성" />
      <form className="grid h-[calc(100%-40px)] min-h-0 grid-rows-[auto_auto_minmax(74px,1fr)_auto_auto] gap-2.5" onSubmit={handleSubmit}>
        <div className="grid grid-cols-[98px_minmax(0,1fr)] items-center gap-3">
          <label className="text-xs font-bold text-slate-400" htmlFor="inquiry-type">문의 유형 <span className="text-red-400">*</span></label>
          <select
            id="inquiry-type"
            value={formState.type}
            onChange={(event) => updateField('type', event.target.value)}
            className="w-full rounded border border-slate-700 bg-[#07111f] px-3 py-1.5 text-sm text-white focus:border-ai-cyan focus:outline-none"
            required
          >
            {inquiryTypes.map((item) => (
              <option key={item.value || 'placeholder'} value={item.value}>
                {item.label}
              </option>
            ))}
          </select>
        </div>

        <div className="grid grid-cols-[98px_minmax(0,1fr)] items-center gap-3">
          <label className="text-xs font-bold text-slate-400" htmlFor="inquiry-title">제목 <span className="text-red-400">*</span></label>
          <input
            id="inquiry-title"
            type="text"
            value={formState.title}
            onChange={(event) => updateField('title', event.target.value)}
            placeholder="제목을 입력해주세요"
            className="w-full rounded border border-slate-700 bg-[#07111f] px-3 py-1.5 text-sm text-white placeholder:text-slate-600 focus:border-ai-cyan focus:outline-none"
            required
          />
        </div>

        <div className="grid min-h-0 grid-cols-[98px_minmax(0,1fr)] gap-3">
          <label className="pt-2 text-xs font-bold text-slate-400" htmlFor="inquiry-content">문의 내용 <span className="text-red-400">*</span></label>
          <textarea
            id="inquiry-content"
            value={formState.content}
            onChange={(event) => updateField('content', event.target.value)}
            placeholder="문의 내용을 입력해주세요"
            className="h-full min-h-[74px] resize-none rounded border border-slate-700 bg-[#07111f] px-3 py-2 text-sm leading-5 text-white placeholder:text-slate-600 focus:border-ai-cyan focus:outline-none"
            required
          />
        </div>

        <div className="grid grid-cols-[98px_minmax(0,1fr)] items-center gap-3">
          <p className="text-xs font-bold text-slate-400">첨부파일</p>
          <div className="flex items-center gap-3 rounded border border-slate-800 bg-[#07111f] px-3 py-1.5">
            <label className="inline-flex cursor-pointer items-center gap-2 rounded border border-slate-700 px-3 py-1 text-xs font-bold text-slate-300 transition hover:border-ai-cyan hover:text-white">
              <Icon name="paperclip" className="h-4 w-4" />
              파일 선택
              <input
                type="file"
                className="sr-only"
                onChange={(event) => updateField('fileName', event.target.files?.[0]?.name || '')}
              />
            </label>
            <span className="min-w-0 truncate text-xs text-slate-500">{formState.fileName || '선택된 파일이 없습니다.'}</span>
          </div>
        </div>

        <div className="pl-[110px]">
          <button type="submit" className="w-full rounded bg-blue-600 px-5 py-2 text-sm font-bold text-white transition hover:bg-blue-500">
            문의 등록
          </button>
        </div>

        {formErrors.type || formErrors.title || formErrors.content ? (
          <div className="sr-only" aria-live="polite">
            {Object.values(formErrors).filter(Boolean).join(' ')}
          </div>
        ) : null}
      </form>
    </Widget>
  )

  const renderChecklistPanel = () => (
    <Widget className="grid max-h-[420px] min-h-0 grid-rows-[auto_minmax(0,1fr)]">
      <WidgetTitle title={inquiryHomeSections.checklist.title} icon={inquiryHomeSections.checklist.icon} />
      {/* 질문이 많아져도 문의 홈 레이아웃은 유지하고, 카드 내부에서만 스크롤되게 한다. */}
      <div className="min-h-0 space-y-2 overflow-y-auto pr-1">
        {checklistItems.map((item) => (
          <div key={item} className="flex items-center gap-3 rounded-lg border border-slate-800 bg-[#111a29] px-3 py-2">
            <span className="grid h-6 w-6 shrink-0 place-items-center rounded-full border border-blue-500/30 bg-blue-500/10 text-blue-400">
              <Icon name="info" className="h-4 w-4" />
            </span>
            <p className="text-xs font-semibold leading-5 text-slate-300">{item}</p>
          </div>
        ))}
      </div>
    </Widget>
  )

  const renderRecentPanel = () => (
    <Widget className="grid min-h-0 grid-rows-[auto_minmax(0,1fr)]">
      <WidgetTitle
        title={inquiryHomeSections.recent.title}
        icon={inquiryHomeSections.recent.icon}
        action={(
          <select className="rounded border border-slate-700 bg-[#07111f] px-3 py-1.5 text-xs font-bold text-slate-300">
            <option>최신순</option>
            <option>과거순</option>
          </select>
        )}
      />
      <div className="flex min-h-0 flex-col gap-3">
        <div className="flex flex-wrap gap-2">
          {inquiryStatusItems.map((item) => (
            <button
              key={item.key}
              type="button"
              className={`rounded border px-3 py-1.5 text-xs font-bold transition ${
                item.key === 'all'
                  ? 'border-blue-600 bg-blue-600 text-white'
                  : 'border-slate-700 bg-[#07111f] text-slate-400 hover:border-slate-500'
              }`}
            >
              {item.key !== 'all' ? <span className={`mr-2 inline-block h-2 w-2 rounded-full ${item.dot}`} /> : null}
              {item.label}
            </button>
          ))}
        </div>
        <InquiryTable inquiries={inquiries} emptyMessage={inquiryHomeSections.recent.emptyMessage} emptyIcon="inbox" />
      </div>
    </Widget>
  )

  const renderInquirySummaryPanel = () => (
    <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
      {summaryItems.map((item) => (
        <div key={item.key} className="rounded-lg border border-slate-800 bg-[#07111f] p-3">
          <div className="flex items-center gap-3">
            <span className={`grid h-9 w-9 place-items-center rounded-full border border-current/30 bg-white/[0.03] ${item.tone}`}>
              <Icon name={item.icon} className="h-4.5 w-4.5" />
            </span>
            <p className="text-xs font-bold text-slate-400">{item.label}</p>
          </div>
          <p className="mt-2 font-mono text-xl font-extrabold text-white">
            {inquiries.length ? summaryCounts[item.key] : '-'}
          </p>
        </div>
      ))}
    </div>
  )

  const renderHome = () => (
    <main className="mx-auto grid max-w-7xl grid-cols-1 gap-6">
      <Widget className="shrink-0">
        <div className="flex items-center justify-between gap-4">
        <div className="flex items-center gap-4">
          <span className="grid h-12 w-12 shrink-0 place-items-center rounded-lg border border-blue-500/20 bg-blue-500/10 text-blue-400">
            <Icon name="message" className="h-7 w-7" />
          </span>
          <div>
            <h1 className="text-2xl font-extrabold text-white">1:1 문의 센터</h1>
            <p className="mt-1 text-sm text-slate-400">계좌, 주문, 입출금, 시스템 문의를 한 곳에서 관리합니다</p>
          </div>
        </div>
        <div className="flex shrink-0 flex-wrap justify-end gap-2">
          {[ 'DB 연동 예정'].map((label) => (
            <span key={label} className="rounded border border-ai-cyan/30 bg-ai-cyan/10 px-3 py-1.5 text-xs font-bold text-ai-cyan">
              {label}
            </span>
          ))}
        </div>
      </div>
      </Widget>

      <div className="grid grid-cols-1 gap-6 xl:grid-cols-[minmax(360px,0.78fr)_minmax(520px,1fr)]">
        {renderInquiryForm()}
        {/* 문의 홈 오른쪽 영역은 현황 카드 대신 자주 묻는 질문에 집중해서 보여준다. */}
        {renderChecklistPanel()}
      </div>

      {renderRecentPanel()}
    </main>
  )

  const renderTableSection = ({ eyebrow, title, description, rows, emptyMessage, showSummary = false }) => (
    <section className="grid h-full min-h-0 grid-rows-[auto_minmax(0,1fr)] rounded-lg border border-slate-700/80 bg-slate-surface p-4">
      <div className="mb-4">
        <p className="text-[10px] font-bold uppercase tracking-[0.16em] text-ai-cyan">{eyebrow}</p>
        <h1 className="mt-1 text-xl font-extrabold text-white">{title}</h1>
        <p className="mt-2 text-sm text-slate-400">{description}</p>
      </div>
      <div className={showSummary ? 'grid min-h-0 grid-rows-[auto_minmax(0,1fr)] gap-4' : 'min-h-0'}>
        {showSummary ? renderInquirySummaryPanel() : null}
        <InquiryTable inquiries={rows} emptyMessage={emptyMessage} />
      </div>
    </section>
  )

  const renderFaq = () => (
    <section className="h-full rounded-lg border border-slate-700/80 bg-slate-surface p-4">
      <h1 className="text-xl font-extrabold text-white">자주 묻는 질문</h1>
      <div className="mt-4 grid gap-3">
        {faqItems.map((item) => (
          <div key={item.question} className="rounded-lg border border-slate-800 bg-[#0c1019] p-4">
            <p className="text-sm font-bold text-white">{item.question}</p>
            <p className="mt-2 text-sm leading-6 text-slate-400">{item.answer}</p>
          </div>
        ))}
      </div>
    </section>
  )

  const renderGuide = () => (
    <section className="h-full rounded-lg border border-slate-700/80 bg-slate-surface p-4">
      <h1 className="text-xl font-extrabold text-white">이용 안내</h1>
      <div className="mt-4 grid gap-3">
        {guideItems.map((item) => (
          <div key={item} className="flex gap-3 rounded-lg border border-slate-800 bg-[#0c1019] p-4">
            <span className="mt-1.5 h-2 w-2 shrink-0 rounded-full bg-ai-cyan" />
            <p className="text-sm leading-6 text-slate-300">{item}</p>
          </div>
        ))}
      </div>
    </section>
  )

  const sectionRenderers = {
    home: renderHome,
    history: () => renderTableSection({
      eyebrow: 'History',
      title: '문의 내역',
      description: '등록한 문의 내역이 DB로 연결되면 이 영역에 표시됩니다.',
      rows: inquiries,
      emptyMessage: '문의 내역이 없습니다.',
      showSummary: true,
    }),
    waiting: () => renderTableSection({
      eyebrow: 'Waiting',
      title: '답변 대기',
      description: '접수 완료 또는 답변 대기 상태의 문의만 모아 보여줍니다.',
      rows: waitingInquiries,
      emptyMessage: '답변 대기 중인 문의가 없습니다.',
    }),
    completed: () => renderTableSection({
      eyebrow: 'Completed',
      title: '처리 완료',
      description: '답변 완료된 문의가 DB로 연결되면 이 영역에 표시됩니다.',
      rows: completedInquiries,
      emptyMessage: '처리 완료된 문의가 없습니다.',
    }),
    faq: renderFaq,
    guide: renderGuide,
  }

  return (
    <div className="min-h-screen bg-obsidian-bg font-inter text-[#e2e2ec]">
      <div className="flex min-h-screen flex-col lg:flex-row">
        {!isSidebarOpen ? (
          <button
            type="button"
            aria-label="문의 사이드바 열기"
            onClick={() => setIsSidebarOpen(true)}
            className="fixed left-4 top-4 z-40 grid h-11 w-11 shrink-0 place-items-center rounded-lg border border-slate-700 bg-[#0F172A] text-slate-300 shadow-xl transition hover:border-ai-cyan hover:text-ai-cyan"
          >
            <Icon name="message" className="h-5 w-5" />
          </button>
        ) : null}

        {isSidebarOpen ? (
        <aside className="shrink-0 border-b border-slate-800 bg-[#0F172A] lg:min-h-screen lg:w-64 lg:border-b-0 lg:border-r">
          <div className="sticky top-0 flex gap-3 overflow-x-auto p-4 lg:h-screen lg:flex-col lg:overflow-visible lg:p-5">
          <div className="flex items-center gap-3 lg:pb-5">
            <span className="grid h-10 w-10 place-items-center overflow-hidden rounded-lg">
              <img className="h-full w-full object-contain" src="/logo.png" alt="ANTRY" />
            </span>
            <div>
              <p className="text-sm font-extrabold text-white">ANTRY</p>
              <p className="text-xs text-slate-500">Inquiry Center</p>
            </div>
            <button
              type="button"
              aria-label="문의 사이드바 닫기"
              onClick={() => setIsSidebarOpen(false)}
              className="ml-auto grid h-8 w-8 place-items-center rounded-lg border border-slate-700 text-slate-400 transition hover:border-ai-cyan hover:text-white"
            >
              ×
            </button>
          </div>

          <nav className="flex gap-2 overflow-x-auto lg:flex-col lg:overflow-visible">
            {inquiryMenuItems.map((item) => {
              const isActive = activeMenu === item.key
              return (
                <button
                  key={item.key}
                  type="button"
                  onClick={() => setActiveMenu(item.key)}
                  className={`inline-flex shrink-0 items-center gap-3 rounded-lg px-4 py-3 text-left text-sm font-bold transition ${
                    isActive
                      ? 'bg-institutional-blue text-white shadow-[0_10px_24px_rgba(0,71,187,0.25)]'
                      : 'text-slate-400 hover:bg-white/5 hover:text-white'
                  }`}
                >
                  <Icon name={item.icon} className="h-5 w-5 shrink-0" />
                  {item.label}
                </button>
              )
            })}
          </nav>

          <div className="mt-auto hidden rounded-lg border border-ai-cyan/20 bg-white/[0.04] p-4 lg:block">
            <p className="text-xs font-bold text-ai-cyan">Support Layer</p>
            <p className="mt-2 text-sm leading-6 text-slate-300">문의 데이터는 추후 API 응답으로 교체될 수 있습니다.</p>
          </div>
          </div>
        </aside>
        ) : null}

        <div className={`min-w-0 flex-1 px-6 py-8 ${!isSidebarOpen ? 'pt-20 lg:pt-8' : ''}`}>
          <Header isLoggedIn={isLoggedIn} userEmail={userEmail} handleLogout={handleLogout} />
          {sectionRenderers[activeMenu]?.()}
        </div>
      </div>
    </div>
  )
}
