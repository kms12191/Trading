import assert from 'node:assert/strict'
import test from 'node:test'

import { buildChatbotCitations } from './chatbotCitations.js'

test('builds compact citation labels from recommendation evidence', () => {
  const citations = buildChatbotCitations({
    citations: [
      {
        source_type: 'DISCLOSURE',
        source_id: '20260701000001',
        title: '삼성전자',
        symbol: '005930',
        summary: '삼성전자는 신규 공급계약과 실적 개선 가능성이 함께 언급됐습니다.',
        similarity: 0.9123,
      },
    ],
  })

  assert.deepEqual(citations, [
    {
      label: 'DART 공시',
      sourceId: '20260701000001',
      title: '삼성전자 (005930)',
      summary: '삼성전자는 신규 공급계약과 실적 개선 가능성이 함께 언급됐습니다.',
      similarityText: '유사도 91.2%',
    },
  ])
})

test('deduplicates and limits citations for compact chat rendering', () => {
  const citations = buildChatbotCitations({
    citations: [
      { source_type: 'OBSIDIAN', source_id: 'note-1', title: '투자노트', summary: '첫 번째 근거' },
      { source_type: 'OBSIDIAN', source_id: 'note-1', title: '투자노트', summary: '중복 근거' },
      { source_type: 'APP_NOTE', source_id: 'note-2', title: '앱노트', summary: '두 번째 근거' },
      { source_type: 'DISCLOSURE', source_id: 'dart-3', title: '공시', summary: '세 번째 근거' },
      { source_type: 'DISCLOSURE', source_id: 'dart-4', title: '공시2', summary: '네 번째 근거' },
    ],
  })

  assert.equal(citations.length, 3)
  assert.deepEqual(citations.map((citation) => citation.sourceId), ['note-1', 'note-2', 'dart-3'])
})
