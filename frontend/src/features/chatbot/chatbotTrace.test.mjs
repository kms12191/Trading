import assert from 'node:assert/strict'
import test from 'node:test'

import { buildChatbotTraceBadges, getNextTypewriterText } from './chatbotTrace.js'

test('builds trace badges from backend trace steps first', () => {
  const badges = buildChatbotTraceBadges({
    traceSteps: [
      { kind: 'ml', label: 'ML 신호' },
      { kind: 'rag', label: 'RAG 벡터검색' },
      { kind: 'disclosure', label: 'DART 공시' },
      { kind: 'rag', label: 'RAG 벡터검색' },
    ],
    toolResult: { source: 'TAVILY' },
  })

  assert.deepEqual(badges.map((badge) => badge.label), ['ML 신호', 'RAG 벡터검색', 'DART 공시'])
})

test('infers trace badges from tool result source when backend trace is absent', () => {
  assert.deepEqual(
    buildChatbotTraceBadges({ toolResult: { source: 'TAVILY_FALLBACK' } }).map((badge) => badge.label),
    ['Tavily 웹검색'],
  )
  assert.deepEqual(
    buildChatbotTraceBadges({ toolResult: { source: 'DISCLOSURE_DB', citations: [{ source_type: 'DISCLOSURE' }] } }).map((badge) => badge.label),
    ['Supabase DB 조회', 'DART 공시', 'RAG 벡터검색'],
  )
})

test('reveals chatbot text in conversation-sized chunks', () => {
  const fullText = '활성 ML 신호 기준 추천 후보입니다.\n1. 삼성전자(005930)'

  assert.equal(getNextTypewriterText('', fullText, 12), '활성 ML 신호 기준')
  assert.equal(getNextTypewriterText('활성 ML 신호 기준', fullText, 12), '활성 ML 신호 기준 추천 후보입니다.')
  assert.equal(getNextTypewriterText(fullText, fullText, 12), fullText)
})
