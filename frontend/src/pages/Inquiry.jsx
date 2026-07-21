import { useCallback, useEffect, useMemo, useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import Header from '../components/Header.jsx'
import { SidebarNav } from '../components/DashboardComponents.jsx'
import { DASHBOARD_QUERY_TABS, DASHBOARD_ROUTE, INQUIRY_ROUTES } from '../dashboardConstants.js'
import { setBrowserTab } from '../lib/browserTab.js'
import { supabase } from '../supabaseClient.js'
import {
  HISTORY_PAGE_SIZE,
  INQUIRY_FILE_BUCKET,
  createInquiryFilePath,
  customerCenterItems,
  faqItems,
  filterInquiriesByStatus,
  filterInquiriesByType,
  filterRecentInquiries,
  getInquirySummaryCounts,
  initialFormState,
  inquiryColumns,
  inquiryHomeSections,
  inquiryStatusItems,
  inquiryTypeFilterItems,
  inquiryTypes,
  paginateInquiries,
  sortInquiries,
  summaryItems,
  toInquiryViewItem,
  validateInquiryFile,
  validateInquiryForm,
} from './inquiryModel.js'

const dashboardQueryTabs = new Set(DASHBOARD_QUERY_TABS)

const getSummaryStatusFilter = (key) => {
  if (key === 'waiting') return 'WAITING'
  if (key === 'completed') return 'COMPLETED'
  return 'all'
}

function Icon({ name, className = 'h-5 w-5' }) {
  const icons = {
    check: <path strokeLinecap="round" strokeLinejoin="round" d="M5 12.5l4 4 10-10" />,
    chevronLeft: <path strokeLinecap="round" strokeLinejoin="round" d="M15 6l-6 6 6 6" />,
    chevronRight: <path strokeLinecap="round" strokeLinejoin="round" d="M9 6l6 6-6 6" />,
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

function Pagination({ currentPage, totalPages, totalItems, pageSize, onPageChange }) {
  if (totalPages <= 1) return null

  const startItem = (currentPage - 1) * pageSize + 1
  const endItem = Math.min(currentPage * pageSize, totalItems)

  return (
    <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-slate-800 bg-[#0f172a] px-4 py-3 text-xs font-bold text-slate-400">
      <span>
        {startItem}-{endItem} / {totalItems}
      </span>
      <div className="flex items-center gap-2">
        <button
          type="button"
          disabled={currentPage === 1}
          className="grid h-8 w-8 place-items-center rounded border border-slate-700 text-slate-300 transition hover:border-ai-cyan hover:text-ai-cyan disabled:cursor-not-allowed disabled:opacity-40"
          onClick={() => onPageChange(currentPage - 1)}
          aria-label="이전 페이지"
        >
          <Icon name="chevronLeft" className="h-4 w-4" />
        </button>
        <span className="min-w-16 text-center text-slate-300">
          {currentPage} / {totalPages}
        </span>
        <button
          type="button"
          disabled={currentPage === totalPages}
          className="grid h-8 w-8 place-items-center rounded border border-slate-700 text-slate-300 transition hover:border-ai-cyan hover:text-ai-cyan disabled:cursor-not-allowed disabled:opacity-40"
          onClick={() => onPageChange(currentPage + 1)}
          aria-label="다음 페이지"
        >
          <Icon name="chevronRight" className="h-4 w-4" />
        </button>
      </div>
    </div>
  )
}

function BackToCustomerCenterButton({ className = '', onClick }) {
  return (
    <button
      type="button"
      aria-label="고객센터로 뒤로가기"
      className={`inline-flex items-center gap-2 rounded-full border border-slate-600 bg-[#0f172a] px-4 py-2 text-xs font-bold text-slate-200 transition hover:border-ai-cyan hover:text-ai-cyan ${className}`}
      onClick={onClick}
    >
      <Icon name="chevronLeft" className="h-4 w-4" />
      뒤로가기
    </button>
  )
}

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
                    <div className="min-w-0 rounded-lg border border-slate-800 bg-slate-surface p-3">
                      <p className="font-bold text-slate-500">문의 내용</p>
                      <p className="mt-2 max-h-80 overflow-y-auto whitespace-pre-wrap break-words pr-1 [overflow-wrap:anywhere]">{item.content || '등록된 문의 내용이 없습니다.'}</p>
                    </div>
                    <div className="min-w-0 rounded-lg border border-slate-800 bg-slate-surface p-3">
                      <p className="font-bold text-slate-500">답변 내용</p>
                      <p className="mt-2 max-h-80 overflow-y-auto whitespace-pre-wrap break-words pr-1 [overflow-wrap:anywhere]">{item.answer || '아직 등록된 답변이 없습니다.'}</p>
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
  const [inquiryTypeFilter, setInquiryTypeFilter] = useState('all')
  const [historyPage, setHistoryPage] = useState(1)
  const [expandedFaqIndex, setExpandedFaqIndex] = useState(null)
  const [inquiriesLoading, setInquiriesLoading] = useState(false)
  const [submitLoading, setSubmitLoading] = useState(false)
  const [deletingInquiryIds, setDeletingInquiryIds] = useState(() => new Set())
  const [inquiryMessage, setInquiryMessage] = useState('')
  const [inquiryError, setInquiryError] = useState('')
  const navigate = useNavigate()
  const { pathname } = useLocation()

  useEffect(() => {
    return setBrowserTab({ title: 'ANTRY - 고객센터' })
  }, [])

  const isWriteView = pathname === INQUIRY_ROUTES.write
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
    const timerId = window.setTimeout(() => {
      loadInquiries()
    }, 0)
    return () => window.clearTimeout(timerId)
  }, [loadInquiries])

  const sortedInquiries = useMemo(() => {
    return sortInquiries(inquiries, 'desc')
  }, [inquiries])

  const filteredHistoryInquiries = useMemo(() => {
    return filterInquiriesByType(filterInquiriesByStatus(sortedInquiries, statusFilter), inquiryTypeFilter)
  }, [inquiryTypeFilter, sortedInquiries, statusFilter])

  const historyTotalPages = Math.max(1, Math.ceil(filteredHistoryInquiries.length / HISTORY_PAGE_SIZE))
  const currentHistoryPage = Math.min(historyPage, historyTotalPages)
  const paginatedHistoryInquiries = useMemo(() => {
    return paginateInquiries(filteredHistoryInquiries, currentHistoryPage, HISTORY_PAGE_SIZE)
  }, [currentHistoryPage, filteredHistoryInquiries])

  const filteredRecentInquiries = useMemo(() => {
    return filterRecentInquiries(filterInquiriesByType(sortedInquiries, inquiryTypeFilter), statusFilter, 5)
  }, [inquiryTypeFilter, sortedInquiries, statusFilter])

  const summaryCounts = useMemo(() => getInquirySummaryCounts(inquiries), [inquiries])

  const handleSummaryFilterChange = (key) => {
    setStatusFilter(getSummaryStatusFilter(key))
    setHistoryPage(1)
  }

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

    const nextErrors = validateInquiryForm({ formState, selectedFile })
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
                <div className="whitespace-pre-line border-t border-slate-800 px-16 pb-4 pt-3 text-sm leading-6 text-slate-400">
                  {item.answer}
                  {item.links?.length ? (
                    <div className="mt-3 flex flex-wrap gap-2 whitespace-normal">
                      {item.links.map((link) => (
                        <a
                          key={link.href}
                          href={link.href}
                          target="_blank"
                          rel="noreferrer"
                          className="rounded border border-ai-cyan/30 bg-ai-cyan/10 px-3 py-1.5 text-xs font-bold text-ai-cyan transition hover:bg-ai-cyan/20"
                        >
                          {link.label}
                        </a>
                      ))}
                    </div>
                  ) : null}
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

  const renderTypeFilterSelect = (id) => (
    <select
      id={id}
      value={inquiryTypeFilter}
      onChange={(event) => {
        setInquiryTypeFilter(event.target.value)
        setHistoryPage(1)
      }}
      className="rounded border border-slate-700 bg-[#0f172a] px-3 py-1.5 text-xs font-bold text-slate-300 focus:border-ai-cyan focus:outline-none"
      aria-label="문의 유형 필터"
    >
      {inquiryTypeFilterItems.map((item) => (
        <option key={item.value} value={item.value}>{item.label}</option>
      ))}
    </select>
  )

  const renderRecentPanel = () => (
    <Widget className="grid min-h-0 grid-rows-[auto_minmax(0,1fr)]">
      <WidgetTitle
        title={inquiryHomeSections.recent.title}
        icon={inquiryHomeSections.recent.icon}
        action={renderTypeFilterSelect('recent-inquiry-type-filter')}
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
      {summaryItems.map((item) => {
        const filterKey = getSummaryStatusFilter(item.key)
        const isActive = statusFilter === filterKey
        return (
        <button
          key={item.key}
          type="button"
          aria-pressed={isActive}
          className={`rounded-lg border p-3 text-left transition ${
            isActive
              ? 'border-institutional-blue bg-institutional-blue/20'
              : 'border-slate-800 bg-[#0f172a] hover:border-slate-600'
          }`}
          onClick={() => handleSummaryFilterChange(item.key)}
        >
          <div className="flex items-center gap-3">
            <span className={`grid h-9 w-9 place-items-center rounded-full border border-current/30 bg-white/[0.03] ${item.tone}`}>
              <Icon name={item.icon} className="h-4.5 w-4.5" />
            </span>
            <p className="text-xs font-bold text-slate-400">{item.label}</p>
          </div>
          <p className="mt-2 font-mono text-xl font-extrabold text-white">
            {inquiries.length ? summaryCounts[item.key] : '-'}
          </p>
        </button>
        )
      })}
    </div>
  )

  const renderHome = () => (
    <main className="mx-auto grid max-w-7xl grid-cols-1 gap-6">
      <Widget className="shrink-0">
        <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex items-center gap-4">
            <span className="grid h-12 w-12 shrink-0 place-items-center rounded-lg border border-ai-cyan/20 bg-ai-cyan/10 text-ai-cyan">
              <Icon name="message" className="h-7 w-7" />
            </span>
            <div>
              <h1 className="text-2xl font-extrabold text-white">1:1 문의 센터</h1>
              <p className="mt-1 text-sm text-slate-400">계좌, 주문, 입출금, 시스템 문의를 한곳에서 관리합니다.</p>
            </div>
          </div>
          <BackToCustomerCenterButton onClick={() => navigate(INQUIRY_ROUTES.home)} />
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
          {renderTypeFilterSelect('history-inquiry-type-filter')}
        </div>
        <div className="grid min-h-0 grid-rows-[auto_minmax(0,1fr)] gap-4">
          {renderInquirySummaryPanel()}
          <div className="grid min-h-0 grid-rows-[minmax(0,1fr)_auto] gap-3">
            {renderInquiryList(paginatedHistoryInquiries, '문의 내역이 없습니다.', 'inbox', { showDeleteAction: true })}
            <Pagination
              currentPage={currentHistoryPage}
              totalPages={historyTotalPages}
              totalItems={filteredHistoryInquiries.length}
              pageSize={HISTORY_PAGE_SIZE}
              onPageChange={setHistoryPage}
            />
          </div>
          <div className="flex justify-end">
            <BackToCustomerCenterButton onClick={() => navigate(INQUIRY_ROUTES.home)} />
          </div>
        </div>
      </section>
    </main>
  )

  const renderCustomerCenterHero = () => (
    <Widget className="shrink-0">
      <div className="flex items-center gap-4">
        <span className="grid h-12 w-12 shrink-0 place-items-center rounded-lg border border-ai-cyan/20 bg-ai-cyan/10 text-ai-cyan">
          <Icon name="question" className="h-7 w-7" />
        </span>
        <div>
          <p className="text-[10px] font-bold uppercase tracking-[0.16em] text-ai-cyan">Customer Center</p>
          <h1 className="mt-1 text-2xl font-extrabold text-white">고객센터</h1>
          <p className="mt-1 text-sm text-slate-400">자주 묻는 질문을 확인하고 필요한 경우 1:1 문의를 남겨주세요.</p>
        </div>
      </div>
    </Widget>
  )

  const renderHelpActions = () => (
    <Widget>
      <div className="mb-4">
        <h2 className="text-lg font-extrabold text-white">다른 도움이 필요하신가요?</h2>
        <p className="mt-1 text-sm text-slate-400">필요한 메뉴로 이동해 문의를 남기거나 처리 상태를 확인할 수 있습니다.</p>
      </div>
      <div className="grid gap-3 md:grid-cols-2">
        <button
          type="button"
          className="group flex items-center gap-4 rounded-lg border border-slate-700 bg-[#0f172a] p-4 text-left transition hover:border-ai-cyan hover:bg-white/[0.03]"
          onClick={() => navigate(INQUIRY_ROUTES.write)}
        >
          <span className="grid h-11 w-11 shrink-0 place-items-center rounded-lg border border-slate-700 bg-slate-surface text-ai-cyan">
            <Icon name="message" className="h-5 w-5" />
          </span>
          <span>
            <span className="block text-sm font-extrabold text-white group-hover:text-ai-cyan">1:1 문의하기</span>
            <span className="mt-1 block text-xs font-bold text-slate-400">자세한 상담이 필요할 때</span>
          </span>
        </button>
        <button
          type="button"
          className="group flex items-center gap-4 rounded-lg border border-slate-700 bg-[#0f172a] p-4 text-left transition hover:border-ai-cyan hover:bg-white/[0.03]"
          onClick={() => navigate(INQUIRY_ROUTES.history)}
        >
          <span className="grid h-11 w-11 shrink-0 place-items-center rounded-lg border border-slate-700 bg-slate-surface text-ai-cyan">
            <Icon name="document" className="h-5 w-5" />
          </span>
          <span>
            <span className="block text-sm font-extrabold text-white group-hover:text-ai-cyan">내 문의 내역</span>
            <span className="mt-1 block text-xs font-bold text-slate-400">등록한 문의와 답변 상태 확인</span>
          </span>
        </button>
      </div>
    </Widget>
  )

  const renderCustomerCenterInfo = () => (
    <Widget>
      <WidgetTitle title="고객센터 안내" icon="clock" />
      <div className="grid gap-3 md:grid-cols-3">
        {customerCenterItems.map((item) => (
          <div key={item.label} className="rounded-lg border border-slate-800 bg-[#0f172a] p-4">
            <p className="text-xs font-bold text-slate-500">{item.label}</p>
            <p className="mt-2 text-sm font-bold leading-6 text-slate-200">{item.value}</p>
          </div>
        ))}
      </div>
    </Widget>
  )

  const renderFaq = () => (
    <main className="mx-auto grid max-w-7xl grid-cols-1 gap-6">
      {renderCustomerCenterHero()}
      {renderChecklistPanel()}
      {renderHelpActions()}
      {renderCustomerCenterInfo()}
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
          {isWriteView ? renderHome() : isHistoryView ? renderHistory() : renderFaq()}
        </div>
      </div>
    </div>
  )
}
