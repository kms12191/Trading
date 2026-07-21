import assert from 'node:assert/strict'
import test from 'node:test'

import {
  HISTORY_PAGE_SIZE,
  createInquiryFilePath,
  filterInquiriesByType,
  filterRecentInquiries,
  formatInquiryDate,
  getInquirySummaryCounts,
  paginateInquiries,
  sortInquiries,
  toInquiryViewItem,
  validateInquiryFile,
  validateInquiryForm,
} from './inquiryModel.js'

test('문의 원장을 화면 행으로 변환하고 날짜와 상태 라벨을 보정한다', () => {
  const item = toInquiryViewItem({
    id: 'inquiry-1',
    inquiry_type: 'order',
    status: 'RECEIVED',
    title: '주문 문의',
    content: '체결 확인',
    answer: null,
    file_name: 'proof.pdf',
    attachment_path: 'u/i/proof.pdf',
    mime_type: 'application/pdf',
    file_size: 1024,
    created_at: '2026-07-15T00:00:00Z',
  })

  assert.equal(item.type, '주문/체결')
  assert.equal(item.inquiryType, 'order')
  assert.equal(item.status, '답변 대기')
  assert.equal(item.statusCode, 'RECEIVED')
  assert.equal(item.answer, '')
  assert.equal(item.createdAtValue, '2026-07-15T00:00:00Z')
  assert.match(item.createdAt, /^\d{2}\. \d{2}\. \d{2}\.$/)
  assert.equal(formatInquiryDate('bad-date'), '-')
})

test('첨부파일 확장자와 크기를 검증하고 저장 경로를 만든다', () => {
  assert.equal(validateInquiryFile(null), '')
  assert.match(validateInquiryFile({ name: 'virus.exe', size: 10 }), /첨부할 수 없는 파일 형식/)
  assert.match(validateInquiryFile({ name: 'large.pdf', size: 5 * 1024 * 1024 + 1 }), /최대 5MB/)
  assert.equal(validateInquiryFile({ name: 'ok.PDF', size: 5 * 1024 }), '')
  assert.equal(
    createInquiryFilePath('user-1', 'inq-1', { name: 'Proof.PDF' }, () => 'fixed-id'),
    'user-1/inq-1/fixed-id.pdf',
  )
})

test('문의 목록을 정렬, 필터링, 페이지 분할한다', () => {
  const rows = [
    { id: 'old', statusCode: 'COMPLETED', createdAtValue: '2026-07-14T00:00:00Z' },
    { id: 'new', statusCode: 'RECEIVED', createdAtValue: '2026-07-15T00:00:00Z' },
    { id: 'wait', statusCode: 'WAITING', createdAtValue: '2026-07-13T00:00:00Z' },
  ]

  assert.deepEqual(sortInquiries(rows, 'desc').map((row) => row.id), ['new', 'old', 'wait'])
  assert.deepEqual(sortInquiries(rows, 'asc').map((row) => row.id), ['wait', 'old', 'new'])
  assert.deepEqual(filterRecentInquiries(rows, 'WAITING', 5).map((row) => row.id), ['new', 'wait'])
  assert.deepEqual(filterRecentInquiries(rows, 'COMPLETED', 5).map((row) => row.id), ['old'])
  assert.deepEqual(filterInquiriesByType([
    { id: 'api', inquiryType: 'account' },
    { id: 'order', inquiryType: 'order' },
  ], 'account').map((row) => row.id), ['api'])
  assert.deepEqual(paginateInquiries(rows, 1, 2).map((row) => row.id), ['old', 'new'])
  assert.equal(HISTORY_PAGE_SIZE, 10)
})

test('문의 요약과 등록 폼 오류를 계산한다', () => {
  assert.deepEqual(getInquirySummaryCounts([
    { statusCode: 'RECEIVED' },
    { statusCode: 'WAITING' },
    { statusCode: 'COMPLETED' },
  ]), {
    total: 3,
    waiting: 2,
    completed: 1,
  })

  assert.deepEqual(validateInquiryForm({
    formState: { type: '', title: ' ', content: '' },
    selectedFile: { name: 'bad.zip', size: 1 },
  }), {
    type: '문의 유형을 선택해주세요.',
    title: '제목을 입력해주세요.',
    content: '문의 내용을 입력해주세요.',
    file: '첨부할 수 없는 파일 형식입니다. jpg, jpeg, png, pdf, txt, doc, docx, xls, xlsx 파일만 등록할 수 있습니다.',
  })
})
