export const inquiryTypes = [
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

export const inquiryStatusLabels = {
  RECEIVED: '답변 대기',
  WAITING: '답변 대기',
  COMPLETED: '답변 완료',
  NEED_MORE: '추가 확인 필요',
  CANCELED: '취소됨',
}

export const inquiryStatusItems = [
  { key: 'all', label: '전체', dot: 'bg-ai-cyan' },
  { key: 'WAITING', label: inquiryStatusLabels.WAITING, dot: 'bg-amber-400' },
  { key: 'COMPLETED', label: inquiryStatusLabels.COMPLETED, dot: 'bg-emerald-400' },
]

export const summaryItems = [
  { key: 'total', label: '전체 문의', icon: 'inbox', tone: 'text-ai-cyan' },
  { key: 'waiting', label: '답변 대기', icon: 'clock', tone: 'text-amber-400' },
  { key: 'completed', label: '답변 완료', icon: 'check', tone: 'text-emerald-400' },
]

export const faqItems = [
  {
    question: '주식 계좌는 어떤 증권사와 연동할 수 있나요?',
    answer: '현재 주식 계좌는 토스증권과 KIS(한국투자증권 Open API)를 지원합니다.\n\n토스증권은 국내/해외 주식 계좌 연동에 사용할 수 있습니다. 토스증권 계좌를 만든 뒤 Open API 사용 신청을 진행하면 API Key와 Secret Key를 발급받을 수 있습니다.\n\nKIS는 실전 계좌와 모의투자 계좌 연동에 사용할 수 있습니다. KIS Developers에 로그인한 뒤 API신청 메뉴에서 실전 또는 모의투자 사용 신청을 진행하면 AppKey, AppSecret, 계좌번호를 확인할 수 있습니다.',
    links: [
      { label: '토스증권', href: 'https://www.tossinvest.com/' },
      { label: 'KIS Developers', href: 'https://apiportal.koreainvestment.com/' },
    ],
  },
  {
    question: '코인 거래소는 어디와 연동할 수 있나요?',
    answer: '현재 코인 거래소는 코인원과 바이낸스를 지원합니다.\n\n코인원은 원화 기반 코인 계좌 연동에 사용할 수 있습니다. 코인원 계정에 로그인한 뒤 API 관리 메뉴에서 API Key와 Secret Key를 발급받을 수 있습니다.\n\n바이낸스는 현물과 USD-M 선물 연동에 사용할 수 있습니다. 바이낸스 계정에 로그인한 뒤 API Management에서 API Key와 Secret Key를 발급받을 수 있습니다.\n\n코인원에서 바이낸스로 출금 주소록을 설정할 때는 테더(USDT) 기준으로 진행해 주세요.\n\n들어가는 방법\n1. 바이낸스 내 정보 대시보드 > Deposit > Crypto Deposit으로 이동\n2. 코인을 USDT로 선택하고 네트워크와 입금 주소 확인\n3. 코인원 로그인 > 입출금 > 출금 주소록 > 주소 추가로 이동\n4. 가상자산은 USDT, 거래소는 바이낸스 또는 직접 입력 선택\n5. 바이낸스에서 확인한 네트워크와 입금 주소 입력\n6. 주소 별칭은 바이낸스 USDT처럼 입력 후 본인 인증 완료\n\n바이낸스 현물 주문을 사용하려면 API 제한 설정에서 IP 주소 제한을 먼저 설정한 뒤 Enable Reading과 Enable Spot & Margin Trading을 켜 주세요. Symbol Whitelist를 사용하는 경우에는 거래할 심볼만 선택해 주세요.\n\n바이낸스 USD-M 선물을 사용하려면 먼저 Binance 상단 메뉴의 Futures > USD-M Futures로 들어가 선물 계정을 열고 안내/퀴즈 절차를 완료해야 합니다. 이후 다시 API Management로 돌아와 해당 API Key의 제한 설정에서 Enable Futures 권한을 켜 주세요. 퀴즈를 완료했는데도 Enable Futures가 선택되지 않으면, 선물 계정 활성화 전에 만든 키일 수 있으므로 새 API Key를 만들어 다시 시도해 주세요.\n\n출금 권한과 Universal Transfer 권한은 일반적인 조회/주문 연동에는 필요하지 않으므로 켜지 않는 것을 권장합니다.',
    links: [
      { label: '코인원 API 안내', href: 'https://coinone.co.kr/user/api/guide' },
      { label: '코인원 출금 주소록', href: 'https://coinone.co.kr/balance/transfer/withdrawal-address' },
      { label: 'Binance API', href: 'https://www.binance.com/en/binance-api' },
    ],
  },
  {
    question: 'API 키가 필요한 이유와 발급·등록 방법은 무엇인가요?',
    answer: 'API 키는 계좌 잔고, 보유 종목, 시세, 주문 가능 여부를 증권사·거래소와 안전하게 연동하기 위해 필요합니다.\n\nANTRY에 등록하는 방법\n1. ANTRY에 로그인합니다.\n2. 내 정보 > 설정으로 이동합니다.\n3. API Key 입력 화면에서 TOSS, KIS, COINONE, BINANCE 중 연동할 항목을 선택합니다.\n4. 발급받은 API Key와 Secret Key를 입력합니다.\n5. KIS는 계좌번호도 함께 입력합니다.\n6. 연결 테스트를 눌러 정상 연결 여부를 확인합니다.\n7. 문제가 없으면 저장합니다.\n\n등록한 키를 수정하는 방법\n1. 내 정보 > 설정으로 이동합니다.\n2. 수정할 증권사 또는 거래소 항목을 선택합니다.\n3. 기존 값을 새 API Key, Secret Key, 계좌번호로 바꿉니다.\n4. 다시 연결 테스트를 실행합니다.\n5. 정상 연결이 확인되면 저장합니다.',
  },
  {
    question: '평가금액이나 수익률이 실제 계좌와 다르게 보일 때는 왜 그런가요?',
    answer: '실시간 시세 반영 시점이나 환율 적용 시점에 따라 일시적인 차이가 발생할 수 있습니다. 새로고침 후에도 문제가 지속되면 문의해 주세요.',
  },
  {
    question: '매수·매도 주문이 실패할 때 확인해야 할 원인은 무엇인가요?',
    answer: '잔고 부족, API 인증 만료, 거래 가능 시간 종료 또는 증권사·거래소 서버 문제 등 다양한 원인이 있을 수 있습니다.',
  },
  {
    question: '주식·코인 시세는 실시간으로 반영되나요?',
    answer: '홈 화면의 주식·코인 시세는 장중에는 약 60초마다 자동 갱신되고, 장 마감 후에는 약 10분마다 갱신됩니다.\n\n종목 상세 화면은 더 짧은 주기로 갱신됩니다. 주식 차트는 약 20~30초, 코인 차트는 약 5~15초 기준으로 갱신되며, 체결·호가성 데이터는 주식 약 10초, 코인 약 2초 기준으로 갱신됩니다.\n\n단, 거래소·증권사 API 정책, 장 운영 상태, 네트워크 상태에 따라 실제 반영 시점은 달라질 수 있습니다.',
  },
  {
    question: '개인정보와 API 키는 서비스에서 어떻게 보호하나요?',
    answer: '개인정보와 API 키는 보안 정책에 따라 안전하게 관리되며, 외부에 노출되지 않도록 보호됩니다.',
  },
]

export const inquiryColumns = [
  { key: 'title', label: '제목' },
  { key: 'type', label: '유형' },
  { key: 'status', label: '상태' },
  { key: 'createdAt', label: '작성일' },
]

export const inquiryHomeSections = {
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

export const customerCenterItems = [
  { label: '답변 시간', value: '영업일 기준 1~3일 이내' },
  { label: '문의 가능 항목', value: '계좌, 주문/체결, 입출금, 시스템 오류' },
  { label: '첨부파일', value: '5MB 이하의 JPG, PNG, PDF, 문서 파일 지원' },
]

export const initialFormState = {
  type: '',
  title: '',
  content: '',
  fileName: '',
}

export const INQUIRY_FILE_BUCKET = 'inquiry-files'
export const MAX_INQUIRY_FILE_SIZE = 5 * 1024 * 1024
export const ALLOWED_INQUIRY_FILE_EXTENSIONS = new Set(['jpg', 'jpeg', 'png', 'pdf', 'txt', 'doc', 'docx', 'xls', 'xlsx'])
export const HISTORY_PAGE_SIZE = 10
export const INITIAL_FAQ_VISIBLE_COUNT = 3

export const inquiryTypeLabels = Object.fromEntries(
  inquiryTypes.filter((item) => item.value).map((item) => [item.value, item.label]),
)

export const getInquiryFileExtension = (fileName = '') => {
  const parts = fileName.split('.')
  return parts.length > 1 ? parts.pop().toLowerCase() : ''
}

export const validateInquiryFile = (file) => {
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

export const createInquiryFilePath = (
  userId,
  inquiryId,
  file,
  createId = () => crypto.randomUUID(),
) => {
  const extension = getInquiryFileExtension(file.name)
  return `${userId}/${inquiryId}/${createId()}.${extension}`
}

export const formatInquiryDate = (value) => {
  const date = value ? new Date(value) : null
  if (!date || Number.isNaN(date.getTime())) return '-'
  return date.toLocaleDateString('ko-KR', {
    year: '2-digit',
    month: '2-digit',
    day: '2-digit',
  })
}

export const toInquiryViewItem = (row = {}) => ({
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

export const sortInquiries = (inquiries, sortOrder = 'desc') => (
  [...inquiries].sort((left, right) => {
    const leftTime = new Date(left.createdAtValue).getTime() || 0
    const rightTime = new Date(right.createdAtValue).getTime() || 0
    return sortOrder === 'asc' ? leftTime - rightTime : rightTime - leftTime
  })
)

export const paginateInquiries = (inquiries, page, pageSize = HISTORY_PAGE_SIZE) => {
  const startIndex = (page - 1) * pageSize
  return inquiries.slice(startIndex, startIndex + pageSize)
}

export const filterInquiriesByStatus = (inquiries, statusFilter = 'all') => {
  if (statusFilter === 'all') return inquiries
  if (statusFilter === 'WAITING') {
    return inquiries.filter((item) => item.statusCode === 'WAITING' || item.statusCode === 'RECEIVED')
  }
  return inquiries.filter((item) => item.statusCode === statusFilter)
}

export const filterRecentInquiries = (inquiries, statusFilter = 'all', limit = 5) => {
  return filterInquiriesByStatus(inquiries, statusFilter).slice(0, limit)
}

export const getInquirySummaryCounts = (inquiries) => {
  const waiting = inquiries.filter((item) => item.statusCode === 'WAITING' || item.statusCode === 'RECEIVED')
  const completed = inquiries.filter((item) => item.statusCode === 'COMPLETED')

  return {
    total: inquiries.length,
    waiting: waiting.length,
    completed: completed.length,
  }
}

export const validateInquiryForm = ({ formState, selectedFile }) => ({
  type: formState.type ? '' : '문의 유형을 선택해주세요.',
  title: formState.title.trim() ? '' : '제목을 입력해주세요.',
  content: formState.content.trim() ? '' : '문의 내용을 입력해주세요.',
  file: validateInquiryFile(selectedFile),
})
