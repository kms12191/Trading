import { useCallback, useEffect, useMemo, useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import Header from '../components/Header.jsx'
import { SidebarNav } from '../components/DashboardComponents.jsx'
import { DASHBOARD_QUERY_TABS, DASHBOARD_ROUTE, INQUIRY_ROUTES } from '../dashboardConstants.js'
import { supabase } from '../supabaseClient.js'

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

const inquiryStatusLabels = {
  RECEIVED: '답변 대기',
  WAITING: '답변 대기',
  COMPLETED: '답변 완료',
  NEED_MORE: '추가 확인 필요',
  CANCELED: '취소됨',
}

const inquiryStatusItems = [
  { key: 'all', label: '전체', dot: 'bg-ai-cyan' },
  { key: 'WAITING', label: inquiryStatusLabels.WAITING, dot: 'bg-amber-400' },
  { key: 'COMPLETED', label: inquiryStatusLabels.COMPLETED, dot: 'bg-emerald-400' },
]

const summaryItems = [
  { key: 'total', label: '전체 문의', icon: 'inbox', tone: 'text-ai-cyan' },
  { key: 'waiting', label: '답변 대기', icon: 'clock', tone: 'text-amber-400' },
  { key: 'completed', label: '답변 완료', icon: 'check', tone: 'text-emerald-400' },
]

const faqItems = [
  {
    question: '어떤 증권사와 거래소를 지원하나요?',
    answer: '현재 지원하는 증권사와 거래소만 연동할 수 있습니다. 지원 목록은 계좌 연동 화면에서 확인할 수 있습니다.',
  },
  {
    question: 'API 키는 안전하게 보관되나요?',
    answer: 'API 키는 암호화하여 저장되며, 서비스 운영에 필요한 인증 목적으로만 사용됩니다.',
  },
  {
    question: '평가금액 또는 수익률이 실제와 다른 것 같습니다.',
    answer: '실시간 시세 반영 시점이나 환율 적용 시점에 따라 일시적인 차이가 발생할 수 있습니다. 새로고침 후에도 문제가 지속되면 문의해 주세요.',
  },
  {
    question: '주문이 실패하는 이유는 무엇인가요?',
    answer: '잔고 부족, API 인증 만료, 거래 가능 시간 종료 또는 증권사·거래소 서버 문제 등 다양한 원인이 있을 수 있습니다.',
  },
  {
    question: '시세는 실시간으로 제공되나요?',
    answer: '가능한 범위 내에서 실시간 데이터를 제공합니다. 일부 데이터는 API 정책에 따라 지연될 수 있습니다.',
  },
  {
    question: '첨부파일은 어떤 형식을 지원하며 용량 제한이 있나요?',
    answer: '이미지(JPG, PNG) 및 문서(PDF 등)를 첨부할 수 있으며, 파일당 최대 5MB까지 업로드할 수 있습니다.',
  },
  {
    question: '개인정보와 API 키는 어떻게 보호되나요?',
    answer: '개인정보와 API 키는 보안 정책에 따라 안전하게 관리되며, 외부에 노출되지 않도록 보호됩니다.',
  },
  {
    question: '문의 답변은 얼마나 걸리나요?',
    answer: '영업일 기준 1~3일 이내 답변을 드리는 것을 목표로 합니다.',
  },
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

const initialFormState = {
  type: '',
  title: '',
  content: '',
  fileName: '',
}

const INQUIRY_FILE_BUCKET = 'inquiry-files'
const MAX_INQUIRY_FILE_SIZE = 5 * 1024 * 1024
const ALLOWED_INQUIRY_FILE_EXTENSIONS = new Set(['jpg', 'jpeg', 'png', 'pdf', 'txt', 'doc', 'docx', 'xls', 'xlsx'])

const dashboardQueryTabs = new Set(DASHBOARD_QUERY_TABS)
const inquiryTypeLabels = Object.fromEntries(inquiryTypes.filter((item) => item.value).map((item) => [item.value, item.label]))

const getInquiryFileExtension = (fileName = '') => {
  const parts = fileName.split('.')
  return parts.length > 1 ? parts.pop().toLowerCase() : ''
}

const validateInquiryFile = (file) => {
  if (!file) return ''

  const extension = getInquiryFileExtension(file.name)
  if (!ALLOWED_INQUIRY_FILE_EXTENSIONS.has(extension)) {
    return '첨부할 수 없는 파일 형식입니다. jpg, jpeg, png, pdf, txt, doc, docx, xls, xlsx 파일만 등록할 수 있습니다.'
  }

  if (file.size > MAX_INQUIRY_FILE_SIZE) {
    return '첨부파일은 최대 5MB까지 등록할 수 있습니다.'
  }

  return ''
}

const createInquiryFilePath = (userId, inquiryId, file) => {
  const extension = getInquiryFileExtension(file.name)
  const fileId = crypto.randomUUID()
  return `${userId}/${inquiryId}/${fileId}.${extension}`
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
    trash: (
      <>
        <path strokeLinecap="round" strokeLinejoin="round" d="M5.5 7h13M10 7V5h4v2M7.5 7l.7 12h7.6l.7-12" />
        <path strokeLinecap="round" strokeLinejoin="round" d="M10.5 10.5v5M13.5 10.5v5" />
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
    <section className={`min-h-0 rounded-lg border border-slate-700/80 bg-slate-surface p-5 ${className}`}>
      {children}
    </section>
  )
}

function WidgetTitle({ title, icon, action }) {
  return (
    <div className="mb-3 flex items-center justify-between gap-3">
      <div className="flex items-center gap-2">
        {icon ? (
          <span className="grid h-8 w-8 place-items-center rounded-lg border border-ai-cyan/25 bg-ai-cyan/10 text-ai-cyan">
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
        <span className="mx-auto mb-2 grid h-11 w-11 place-items-center rounded-lg border border-slate-700/70 bg-[#0f172a] text-slate-500">
          <Icon name={icon} className="h-6 w-6" />
        </span>
        <p>{message}</p>
      </div>
    </div>
  )
}

const formatInquiryDate = (value) => {
  const date = value ? new Date(value) : null
  if (!date || Number.isNaN(date.getTime())) return '-'
  return date.toLocaleDateString('ko-KR', {
    year: '2-digit',
    month: '2-digit',
    day: '2-digit',
  })
}

const toInquiryViewItem = (row = {}) => ({
  id: row.id,
  type: inquiryTypeLabels[row.inquiry_type] || row.inquiry_type || '-',
  status: inquiryStatusLabels[row.status] || row.status || '-',
  statusCode: row.status,
  title: row.title || '-',
  content: row.content || '',
  answer: row.answer || '',
  fileName: row.file_name || '',
  attachmentPath: row.attachment_path || '',
  mimeType: row.mime_type || '',
  fileSize: row.file_size || null,
  createdAt: formatInquiryDate(row.created_at),
  createdAtValue: row.created_at || '',
})

function InquiryTable({
  inquiries,
  emptyMessage,
  emptyIcon = 'inbox',
  onDownloadAttachment,
  showDeleteAction = false,
  onDeleteInquiry,
  deletingInquiryIds = new Set(),
}) {
  const [expandedInquiryId, setExpandedInquiryId] = useState(null)

  return (
    <div className="flex h-full min-h-0 flex-col overflow-hidden rounded-lg border border-slate-800">
      <div className="grid grid-cols-[minmax(180px,1.5fr)_120px_130px_120px] bg-[#0f172a] text-xs font-bold text-slate-400">
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
                  <div className="grid gap-3 bg-[#0f172a]/70 px-4 py-4 text-xs leading-5 text-slate-300 md:grid-cols-2">
                    <div className="rounded-lg border border-slate-800 bg-slate-surface p-3">
                      <p className="font-bold text-slate-500">문의 내용</p>
                      <p className="mt-2 whitespace-pre-wrap">{item.content || '등록된 문의 내용이 없습니다.'}</p>
                    </div>
                    <div className="rounded-lg border border-slate-800 bg-slate-surface p-3">
                      <p className="font-bold text-slate-500">답변 내용</p>
                      <p className="mt-2 whitespace-pre-wrap">{item.answer || '아직 등록된 답변이 없습니다.'}</p>
                    </div>
                    <div className="rounded-lg border border-slate-800 bg-slate-surface p-3">
                      <p className="font-bold text-slate-500">첨부파일</p>
                      {item.attachmentPath ? (
                        <button
                          type="button"
                          className="mt-2 inline-flex max-w-full items-center gap-2 rounded border border-slate-700 px-3 py-1 text-left text-xs font-bold text-ai-cyan transition hover:border-ai-cyan hover:text-cyan-200"
                          onClick={() => onDownloadAttachment?.(item)}
                        >
                          <Icon name="paperclip" className="h-4 w-4 shrink-0" />
                          <span className="truncate">{item.fileName || '첨부파일 다운로드'}</span>
                        </button>
                      ) : (
                        <p className="mt-2">{item.fileName || '첨부파일 없음'}</p>
                      )}
                    </div>
                    <div className="rounded-lg border border-slate-800 bg-slate-surface p-3">
                      <p className="font-bold text-slate-500">처리 상태</p>
                      <p className="mt-2">{item.status || '-'}</p>
                    </div>
                    {showDeleteAction && item.statusCode === 'RECEIVED' ? (
                      <div className="flex justify-end md:col-span-2">
                        <button
                          type="button"
                          disabled={deletingInquiryIds.has(item.id)}
                          className="inline-flex items-center gap-2 rounded border border-red-500/40 px-3 py-1.5 text-xs font-bold text-red-300 transition hover:border-red-400 hover:bg-red-500/10 disabled:cursor-not-allowed disabled:opacity-60"
                          onClick={() => onDeleteInquiry?.(item)}
                        >
                          <Icon name="trash" className="h-4 w-4" />
                          {deletingInquiryIds.has(item.id) ? '삭제 중' : '삭제'}
                        </button>
                      </div>
                    ) : null}
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
  const [isSidebarOpen, setIsSidebarOpen] = useState(true)
  const [formState, setFormState] = useState(initialFormState)
  const [selectedFile, setSelectedFile] = useState(null)
  const [fileInputKey, setFileInputKey] = useState(0)
  const [formErrors, setFormErrors] = useState({})
  const [inquiries, setInquiries] = useState([])
  const [statusFilter, setStatusFilter] = useState('all')
  const [inquirySortOrder, setInquirySortOrder] = useState('desc')
  const [expandedFaqIndex, setExpandedFaqIndex] = useState(null)
  const [inquiriesLoading, setInquiriesLoading] = useState(false)
  const [submitLoading, setSubmitLoading] = useState(false)
  const [deletingInquiryIds, setDeletingInquiryIds] = useState(() => new Set())
  const [inquiryMessage, setInquiryMessage] = useState('')
  const [inquiryError, setInquiryError] = useState('')
  const navigate = useNavigate()
  const { pathname } = useLocation()
  const isFaqView = pathname === INQUIRY_ROUTES.faq
  const isHistoryView = pathname === INQUIRY_ROUTES.history

  const loadInquiries = useCallback(async () => {
    if (!isLoggedIn) {
      setInquiries([])
      return
    }

    setInquiriesLoading(true)
    setInquiryError('')
    try {
      const { data, error } = await supabase
        .from('inquiries')
        .select('id,user_id,inquiry_type,title,content,file_name,attachment_path,mime_type,file_size,status,answer,answered_at,created_at,updated_at')
        .order('created_at', { ascending: false })

      if (error) throw error
      setInquiries((data || []).map(toInquiryViewItem))
    } catch (error) {
      setInquiryError(error.message || '문의 내역을 불러오지 못했습니다.')
    } finally {
      setInquiriesLoading(false)
    }
  }, [isLoggedIn])

  useEffect(() => {
    loadInquiries()
  }, [loadInquiries])

  const sortedInquiries = useMemo(() => {
    return [...inquiries].sort((left, right) => {
      const leftTime = new Date(left.createdAtValue).getTime() || 0
      const rightTime = new Date(right.createdAtValue).getTime() || 0
      return inquirySortOrder === 'asc' ? leftTime - rightTime : rightTime - leftTime
    })
  }, [inquiries, inquirySortOrder])

  const filteredRecentInquiries = useMemo(() => {
    const filtered = statusFilter === 'all'
      ? sortedInquiries
      : statusFilter === 'WAITING'
        ? sortedInquiries.filter((item) => item.statusCode === 'WAITING' || item.statusCode === 'RECEIVED')
      : sortedInquiries.filter((item) => item.statusCode === statusFilter)
    return filtered.slice(0, 5)
  }, [sortedInquiries, statusFilter])

  const waitingInquiries = useMemo(
    () => inquiries.filter((item) => item.statusCode === 'WAITING' || item.statusCode === 'RECEIVED'),
    [inquiries],
  )
  const completedInquiries = useMemo(
    () => inquiries.filter((item) => item.statusCode === 'COMPLETED'),
    [inquiries],
  )
  const summaryCounts = useMemo(() => ({
    total: inquiries.length,
    waiting: waitingInquiries.length,
    completed: completedInquiries.length,
  }), [completedInquiries.length, inquiries, waitingInquiries.length])

  const updateField = (field, value) => {
    setFormState((prev) => ({ ...prev, [field]: value }))
    setFormErrors((prev) => ({ ...prev, [field]: '' }))
    setInquiryMessage('')
    setInquiryError('')
  }

  const handleFileChange = (event) => {
    const file = event.target.files?.[0] || null
    const fileError = validateInquiryFile(file)

    if (fileError) {
      event.target.value = ''
      setSelectedFile(null)
      setFormState((prev) => ({ ...prev, fileName: '' }))
      setFormErrors((prev) => ({ ...prev, file: fileError }))
      setInquiryMessage('')
      setInquiryError(fileError)
      return
    }

    setSelectedFile(file)
    setFormState((prev) => ({ ...prev, fileName: file?.name || '' }))
    setFormErrors((prev) => ({ ...prev, file: '' }))
    setInquiryMessage('')
    setInquiryError('')
  }

  const handleDownloadAttachment = async (item) => {
    if (!item?.attachmentPath) return

    setInquiryError('')
    try {
      const { data, error } = await supabase.storage
        .from(INQUIRY_FILE_BUCKET)
        .createSignedUrl(item.attachmentPath, 60)

      if (error) throw error
      if (data?.signedUrl) {
        window.open(data.signedUrl, '_blank', 'noopener,noreferrer')
      }
    } catch (error) {
      setInquiryError(error.message || '첨부파일 다운로드 링크를 생성하지 못했습니다.')
    }
  }

  const handleDeleteInquiry = async (item) => {
    if (!item?.id || item.statusCode !== 'RECEIVED') {
      setInquiryError('답변 대기 상태의 문의만 삭제할 수 있습니다.')
      return
    }

    const confirmed = window.confirm('문의 내역을 삭제하시겠습니까? 첨부파일이 있으면 함께 삭제됩니다.')
    if (!confirmed) return

    setInquiryMessage('')
    setInquiryError('')
    setDeletingInquiryIds((prev) => new Set(prev).add(item.id))

    try {
      if (item.attachmentPath) {
        const { error: storageError } = await supabase.storage
          .from(INQUIRY_FILE_BUCKET)
          .remove([item.attachmentPath])

        if (storageError && !/not found|does not exist/i.test(storageError.message || '')) {
          throw new Error('첨부파일 삭제에 실패했습니다. 다시 시도해주세요.')
        }
      }

      const { data: deletedRows, error: deleteError } = await supabase
        .from('inquiries')
        .delete()
        .eq('id', item.id)
        .eq('status', 'RECEIVED')
        .select('id')

      if (deleteError) throw deleteError
      if (!deletedRows?.length) {
        throw new Error('삭제할 수 없는 상태이거나 이미 삭제된 문의입니다.')
      }

      setInquiries((prev) => prev.filter((inquiry) => inquiry.id !== item.id))
      setInquiryMessage('문의가 삭제되었습니다.')
    } catch (error) {
      setInquiryError(error.message || '문의 삭제에 실패했습니다.')
    } finally {
      setDeletingInquiryIds((prev) => {
        const next = new Set(prev)
        next.delete(item.id)
        return next
      })
    }
  }

  const handleDashboardTabChange = (tabKey) => {
    if (dashboardQueryTabs.has(tabKey)) {
      navigate(`${DASHBOARD_ROUTE}?tab=${tabKey}`)
      return
    }
    navigate(DASHBOARD_ROUTE)
  }

  const handleSubmit = async (event) => {
    event.preventDefault()

    const nextErrors = {
      type: formState.type ? '' : '문의 유형을 선택해주세요.',
      title: formState.title.trim() ? '' : '제목을 입력해주세요.',
      content: formState.content.trim() ? '' : '문의 내용을 입력해주세요.',
      file: validateInquiryFile(selectedFile),
    }
    setFormErrors(nextErrors)
    setInquiryMessage('')
    setInquiryError('')

    if (Object.values(nextErrors).some(Boolean)) return

    setSubmitLoading(true)
    try {
      const { data: { session }, error: sessionError } = await supabase.auth.getSession()
      if (sessionError) throw sessionError
      if (!session?.user?.id) {
        throw new Error('로그인이 필요합니다.')
      }

      const { data: insertedInquiry, error } = await supabase
        .from('inquiries')
        .insert({
          user_id: session.user.id,
          inquiry_type: formState.type,
          title: formState.title.trim(),
          content: formState.content.trim(),
          file_name: null,
          attachment_path: null,
          mime_type: null,
          file_size: null,
        })
        .select('id,user_id,inquiry_type,title,content,file_name,attachment_path,mime_type,file_size,status,answer,answered_at,created_at,updated_at')
        .single()

      if (error) throw error

      let savedInquiry = insertedInquiry

      if (selectedFile) {
        const attachmentPath = createInquiryFilePath(session.user.id, insertedInquiry.id, selectedFile)
        const { error: uploadError } = await supabase.storage
          .from(INQUIRY_FILE_BUCKET)
          .upload(attachmentPath, selectedFile, {
            cacheControl: '3600',
            contentType: selectedFile.type || undefined,
            upsert: false,
          })

        if (uploadError) {
          await supabase.from('inquiries').delete().eq('id', insertedInquiry.id)
          throw uploadError
        }

        const { data: updatedInquiry, error: updateError } = await supabase
          .from('inquiries')
          .update({
            file_name: selectedFile.name,
            attachment_path: attachmentPath,
            mime_type: selectedFile.type || null,
            file_size: selectedFile.size,
          })
          .eq('id', insertedInquiry.id)
          .select('id,user_id,inquiry_type,title,content,file_name,attachment_path,mime_type,file_size,status,answer,answered_at,created_at,updated_at')
          .single()

        if (updateError) {
          await supabase.storage.from(INQUIRY_FILE_BUCKET).remove([attachmentPath])
          await supabase.from('inquiries').delete().eq('id', insertedInquiry.id)
          throw updateError
        }

        savedInquiry = updatedInquiry
      }

      setInquiries((prev) => [toInquiryViewItem(savedInquiry), ...prev])
      setFormState(initialFormState)
      setSelectedFile(null)
      setFileInputKey((prev) => prev + 1)
      setStatusFilter('all')
      setInquiryMessage('문의가 등록되었습니다.')
    } catch (error) {
      setInquiryError(error.message || '문의 등록에 실패했습니다.')
    } finally {
      setSubmitLoading(false)
    }
  }

  const renderInquiryForm = () => (
    <Widget className="h-full">
      <WidgetTitle title="문의 작성" />
      <form className="grid min-h-0 gap-3 lg:grid-cols-2" onSubmit={handleSubmit}>
        <div className="grid grid-cols-[98px_minmax(0,1fr)] items-center gap-3">
          <label className="text-xs font-bold text-slate-400" htmlFor="inquiry-type">문의 유형 <span className="text-red-400">*</span></label>
          <select
            id="inquiry-type"
            value={formState.type}
            onChange={(event) => updateField('type', event.target.value)}
            className="w-full rounded border border-slate-700 bg-[#0f172a] px-3 py-1.5 text-sm text-white focus:border-ai-cyan focus:outline-none"
            required
          >
            {inquiryTypes.map((item) => (
              <option key={item.value || 'placeholder'} value={item.value}>
                {item.label}
              </option>
            ))}
          </select>
        </div>

        <div className="grid grid-cols-[60px_minmax(0,1fr)] items-center gap-1.5">
          <label className="text-xs font-bold text-slate-400" htmlFor="inquiry-title">제목 <span className="text-red-400">*</span></label>
          <input
            id="inquiry-title"
            type="text"
            value={formState.title}
            onChange={(event) => updateField('title', event.target.value)}
            placeholder="제목을 입력해주세요"
            className="w-full rounded border border-slate-700 bg-[#0f172a] px-3 py-1.5 text-sm text-white placeholder:text-slate-600 focus:border-ai-cyan focus:outline-none"
            required
          />
        </div>

        <div className="grid min-h-0 grid-cols-[98px_minmax(0,1fr)] gap-3 lg:col-span-2">
          <label className="pt-2 text-xs font-bold text-slate-400" htmlFor="inquiry-content">문의 내용 <span className="text-red-400">*</span></label>
          <textarea
            id="inquiry-content"
            value={formState.content}
            onChange={(event) => updateField('content', event.target.value)}
            placeholder="문의 내용을 입력해주세요"
            className="h-full min-h-44 resize-none rounded border border-slate-700 bg-[#0f172a] px-3 py-2 text-sm leading-5 text-white placeholder:text-slate-600 focus:border-ai-cyan focus:outline-none"
            required
          />
        </div>

        <div className="grid grid-cols-[98px_minmax(0,1fr)] items-center gap-3 lg:col-span-2">
          <p className="text-xs font-bold text-slate-400">첨부파일</p>
          <div className="flex items-center gap-3 rounded border border-slate-800 bg-[#0f172a] px-3 py-1.5">
            <label className="inline-flex cursor-pointer items-center gap-2 rounded border border-slate-700 px-3 py-1 text-xs font-bold text-slate-300 transition hover:border-ai-cyan hover:text-white">
              <Icon name="paperclip" className="h-4 w-4" />
              파일 선택
              <input
                key={fileInputKey}
                type="file"
                className="sr-only"
                accept=".jpg,.jpeg,.png,.pdf,.txt,.doc,.docx,.xls,.xlsx"
                onChange={handleFileChange}
              />
            </label>
            <span className="min-w-0 truncate text-xs text-slate-500">{formState.fileName || '선택된 파일이 없습니다.'}</span>
          </div>
          {formErrors.file ? (
            <p className="col-start-2 text-xs font-bold text-red-300">{formErrors.file}</p>
          ) : null}
        </div>

        <div className="flex justify-end lg:col-span-2">
          <button
            type="submit"
            disabled={submitLoading}
            className="w-full rounded bg-ai-cyan px-5 py-2 text-sm font-bold text-slate-950 transition hover:bg-cyan-300 disabled:cursor-not-allowed disabled:opacity-60 sm:w-auto sm:min-w-40"
          >
            {submitLoading ? '등록 중' : '문의 등록'}
          </button>
        </div>

        {inquiryMessage ? (
          <p className="text-xs font-bold text-emerald-300 lg:col-span-2">{inquiryMessage}</p>
        ) : null}

        {inquiryError ? (
          <p className="whitespace-pre-line text-xs font-bold text-red-300 lg:col-span-2">{inquiryError}</p>
        ) : null}

        {formErrors.type || formErrors.title || formErrors.content || formErrors.file ? (
          <div className="sr-only" aria-live="polite">
            {Object.values(formErrors).filter(Boolean).join(' ')}
          </div>
        ) : null}
      </form>
    </Widget>
  )

  const renderChecklistPanel = () => (
    <Widget className="grid min-h-0 grid-rows-[auto_minmax(0,1fr)]">
      <WidgetTitle title={inquiryHomeSections.checklist.title} icon={inquiryHomeSections.checklist.icon} />
      <div className="min-h-0 space-y-2 overflow-y-auto pr-1">
        {faqItems.map((item, index) => {
          const isExpanded = expandedFaqIndex === index

          return (
            <div key={item.question} className="overflow-hidden rounded-lg border border-slate-800 bg-[#0f172a]">
              <button
                type="button"
                aria-expanded={isExpanded}
                className="flex w-full items-center justify-between gap-4 px-5 py-4 text-left transition hover:bg-white/[0.03]"
                onClick={() => setExpandedFaqIndex(isExpanded ? null : index)}
              >
                <span className="flex min-w-0 items-center gap-3">
                  <span className="grid h-8 w-8 shrink-0 place-items-center rounded-full border border-ai-cyan/30 bg-ai-cyan/10 text-ai-cyan">
                    <Icon name="info" className="h-4 w-4" />
                  </span>
                  <span className="text-sm font-bold leading-6 text-slate-200">{item.question}</span>
                </span>
                <span className="shrink-0 text-lg font-bold text-slate-500">{isExpanded ? '-' : '+'}</span>
              </button>
              {isExpanded ? (
                <div className="border-t border-slate-800 px-16 pb-4 pt-3 text-sm leading-6 text-slate-400">
                  {item.answer}
                </div>
              ) : null}
            </div>
          )
        })}
      </div>
    </Widget>
  )

  const renderInquiryList = (rows, emptyMessage, emptyIcon = 'inbox', options = {}) => (
    <>
      {inquiriesLoading ? (
        <div className="rounded-lg border border-slate-800 bg-[#0f172a] px-4 py-6 text-center text-sm font-bold text-slate-400">
          문의 내역을 불러오는 중입니다.
        </div>
      ) : (
        <InquiryTable
          inquiries={rows}
          emptyMessage={emptyMessage}
          emptyIcon={emptyIcon}
          onDownloadAttachment={handleDownloadAttachment}
          showDeleteAction={Boolean(options.showDeleteAction)}
          onDeleteInquiry={handleDeleteInquiry}
          deletingInquiryIds={deletingInquiryIds}
        />
      )}
      {inquiryError ? <p className="whitespace-pre-line text-xs font-bold text-red-300">{inquiryError}</p> : null}
    </>
  )

  const renderSortSelect = (id) => (
    <select
      id={id}
      value={inquirySortOrder}
      onChange={(event) => setInquirySortOrder(event.target.value)}
      className="rounded border border-slate-700 bg-[#0f172a] px-3 py-1.5 text-xs font-bold text-slate-300 focus:border-ai-cyan focus:outline-none"
      aria-label="문의 정렬"
    >
      <option value="desc">최신순</option>
      <option value="asc">과거순</option>
    </select>
  )

  const renderRecentPanel = () => (
    <Widget className="grid min-h-0 grid-rows-[auto_minmax(0,1fr)]">
      <WidgetTitle
        title={inquiryHomeSections.recent.title}
        icon={inquiryHomeSections.recent.icon}
        action={renderSortSelect('recent-inquiry-sort')}
      />
      <div className="flex min-h-0 flex-col gap-3">
        <div className="flex flex-wrap gap-2">
          {inquiryStatusItems.map((item) => (
            <button
              key={item.key}
              type="button"
              className={`rounded border px-3 py-1.5 text-xs font-bold transition ${
                statusFilter === item.key
                  ? 'border-institutional-blue bg-institutional-blue text-white'
                  : 'border-slate-700 bg-[#0f172a] text-slate-400 hover:border-slate-500'
              }`}
              onClick={() => setStatusFilter(item.key)}
            >
              {item.key !== 'all' ? <span className={`mr-2 inline-block h-2 w-2 rounded-full ${item.dot}`} /> : null}
              {item.label}
            </button>
          ))}
        </div>
        {renderInquiryList(filteredRecentInquiries, inquiryHomeSections.recent.emptyMessage, 'inbox')}
      </div>
    </Widget>
  )

  const renderInquirySummaryPanel = () => (
    <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
      {summaryItems.map((item) => (
        <div key={item.key} className="rounded-lg border border-slate-800 bg-[#0f172a] p-3">
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
        <div className="flex items-center gap-4">
          <span className="grid h-12 w-12 shrink-0 place-items-center rounded-lg border border-ai-cyan/20 bg-ai-cyan/10 text-ai-cyan">
            <Icon name="message" className="h-7 w-7" />
          </span>
          <div>
            <h1 className="text-2xl font-extrabold text-white">1:1 문의 센터</h1>
            <p className="mt-1 text-sm text-slate-400">계좌, 주문, 입출금, 시스템 문의를 한곳에서 관리합니다.</p>
          </div>
        </div>
      </Widget>

      {renderInquiryForm()}
      {renderRecentPanel()}
    </main>
  )

  const renderHistory = () => (
    <main className="mx-auto grid max-w-7xl grid-cols-1 gap-6">
      <section className="grid h-full min-h-0 grid-rows-[auto_minmax(0,1fr)] rounded-lg border border-slate-700/80 bg-slate-surface p-4">
        <div className="mb-4 flex items-start justify-between gap-3">
          <div>
            <p className="text-[10px] font-bold uppercase tracking-[0.16em] text-ai-cyan">History</p>
            <h1 className="mt-1 text-xl font-extrabold text-white">문의 내역</h1>
            <p className="mt-2 text-sm text-slate-400">등록한 문의와 답변 상태를 확인합니다.</p>
          </div>
          {renderSortSelect('history-inquiry-sort')}
        </div>
        <div className="grid min-h-0 grid-rows-[auto_minmax(0,1fr)] gap-4">
          {renderInquirySummaryPanel()}
          {renderInquiryList(sortedInquiries, '문의 내역이 없습니다.', 'inbox', { showDeleteAction: true })}
        </div>
      </section>
    </main>
  )

  const renderFaq = () => (
    <main className="mx-auto grid max-w-7xl grid-cols-1 gap-6">
      {renderChecklistPanel()}
    </main>
  )

  return (
    <div className="min-h-screen bg-obsidian-bg font-inter text-[#e2e2ec]">
      <div className="flex min-h-screen flex-col lg:flex-row">
        <SidebarNav
          activeTab="inquiry"
          isOpen={isSidebarOpen}
          isLoggedIn={isLoggedIn}
          onClose={() => setIsSidebarOpen(false)}
          onOpen={() => setIsSidebarOpen(true)}
          onTabChange={handleDashboardTabChange}
        />

        <div className={`min-w-0 flex-1 px-6 py-8 ${!isSidebarOpen ? 'pt-20 lg:pt-8' : ''}`}>
          <Header isLoggedIn={isLoggedIn} userEmail={userEmail} handleLogout={handleLogout} />
          {isFaqView ? renderFaq() : isHistoryView ? renderHistory() : renderHome()}
        </div>
      </div>
    </div>
  )
}
