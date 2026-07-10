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
