import assert from 'node:assert/strict'
import test from 'node:test'

import {
  buildDisclosurePresentation,
  normalizeDisclosureText,
} from './chatbotDisclosurePresentation.js'

test('normalizes repeated whitespace and duplicated disclosure wording', () => {
  assert.equal(normalizeDisclosureText('권리락              (무상증자)'), '권리락 (무상증자)')
  assert.equal(
    normalizeDisclosureText('정정 공시 공시로 세부 조건 확인이 필요합니다.'),
    '정정 공시로 세부 조건 확인이 필요합니다.',
  )
})

test('keeps complete summary and metric values for wrapping instead of truncating them', () => {
  const longSummary = '기존 공급계약의 금액과 기간, 계약 상대방, 매출 반영 일정이 변경된 정정 공시입니다. 변경 전후 조건을 원문에서 비교해야 합니다.'
  const longMetric = '해당 상장회사의 이사, 감사 또는 피용자 1명과 관계회사 임직원 전체'

  const result = buildDisclosurePresentation({
    source: 'DISCLOSURE_DB',
    items: [
      {
        corp_name: '이노스페이스',
        report_nm: '[기재정정]단일판매ㆍ공급계약체결',
        url: 'https://dart.fss.or.kr/example',
        analysis: {
          headline: '공급계약 정정 내용 확인이 필요합니다.',
          plain_summary: longSummary,
          metrics: [
            { label: '부여대상', value: longMetric },
            { label: '기준가', value: '12,660원' },
          ],
          check_items: [
            { question: '정정 내용', answer: '원문 확인 필요' },
            { question: '조정 기준가', answer: '12,660원' },
          ],
          risk_points: ['계약 규모와 일정 변경 여부를 확인해야 합니다.'],
        },
      },
    ],
  })

  assert.equal(result.items[0].summary, longSummary)
  assert.equal(result.items[0].headline, '')
  assert.equal(result.items[0].metrics[0].value, longMetric)
  assert.equal(result.items[0].checks.length, 0)
})

test('normalizes disclosure items from combined news and disclosure search results', () => {
  const result = buildDisclosurePresentation({
    source: 'NEWS_DISCLOSURE_COMBINED',
    news: {
      source: 'NAVER_API',
      items: [{ title: '뉴스' }],
    },
    disclosure: {
      source: 'DISCLOSURE_DB',
      items: [
        {
          corp_name: '삼성전자',
          report_nm: '주요사항보고서',
          analysis: {
            plain_summary: '자기주식 처분 공시입니다.',
            metrics: [{ label: '처분예정금액', value: '322,755,945,000원' }],
          },
        },
      ],
    },
  })

  assert.equal(result.items.length, 1)
  assert.equal(result.items[0].corpName, '삼성전자')
  assert.equal(result.items[0].summary, '자기주식 처분 공시입니다.')
  assert.deepEqual(result.items[0].metrics, [{ label: '처분예정금액', value: '322,755,945,000원' }])
})

test('filters placeholder disclosure table fields from chatbot cards', () => {
  const result = buildDisclosurePresentation({
    source: 'DISCLOSURE_DB',
    items: [
      {
        corp_name: '삼성전자',
        report_nm: '장래사업ㆍ경영계획(공정공시)',
        analysis: {
          plain_summary: '삼성전자는 반도체 및 신사업 분야 투자를 추진할 계획입니다.',
          metrics: [
            { label: '주요내용', value: '및' },
            { label: '투자 규모', value: '약 2,450조 원' },
            { label: '추진일정', value: '2026-01-01' },
          ],
          check_items: [
            { question: '핵심 내용', answer: '및' },
            { question: '실현 가능성', answer: '2026-01-01' },
            { question: '확인 포인트', answer: '세부 투자 일정과 금액 확정 여부' },
          ],
        },
      },
    ],
  })

  assert.deepEqual(result.items[0].metrics, [{ label: '투자 규모', value: '약 2,450조 원' }])
  assert.deepEqual(result.items[0].checks, [{ question: '확인 포인트', answer: '세부 투자 일정과 금액 확정 여부' }])
})

test('deduplicates disclosure metrics and checks with equivalent labels', () => {
  const result = buildDisclosurePresentation({
    source: 'DISCLOSURE_DB',
    items: [
      {
        corp_name: '삼성전자',
        report_nm: '주요사항보고서(자기주식처분결정)',
        analysis: {
          plain_summary: '자기주식 처분 공시입니다.',
          metrics: [
            { label: '처분예정금액', value: '322,755,945,000원' },
            { label: '처분목적', value: '임원 등 성과급의 자기주식 지급' },
            { label: '처분예정기간', value: '2026년 07월 13일' },
          ],
          check_items: [
            { question: '처분 목적', answer: '임원 등 성과급의 자기주식 지급' },
            { question: '처분 규모', answer: '322,755,945,000원' },
          ],
        },
      },
    ],
  })

  assert.deepEqual(result.items[0].metrics, [
    { label: '처분예정금액', value: '322,755,945,000원' },
    { label: '처분목적', value: '임원 등 성과급의 자기주식 지급' },
    { label: '처분예정기간', value: '2026년 07월 13일' },
  ])
  assert.deepEqual(result.items[0].checks, [])
})
