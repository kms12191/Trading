import assert from 'node:assert/strict'
import test from 'node:test'

import { parseChatbotSseBuffer, resetChatbotSseParser } from './chatbotStream.js'

test('parses chatbot SSE trace delta and done events', () => {
  resetChatbotSseParser()
  const events = parseChatbotSseBuffer([
    'event: trace',
    'data: {"kind":"request","label":"요청 분석"}',
    '',
    'event: delta',
    'data: {"text":"추천 후보"}',
    '',
    'event: done',
    'data: {"reply":"추천 후보","meta":{"source":"PROJECT_TOOL"}}',
    '',
    '',
  ].join('\n'))

  assert.deepEqual(events, [
    { event: 'trace', data: { kind: 'request', label: '요청 분석' } },
    { event: 'delta', data: { text: '추천 후보' } },
    { event: 'done', data: { reply: '추천 후보', meta: { source: 'PROJECT_TOOL' } } },
  ])
})

test('keeps incomplete SSE frame in remainder', () => {
  resetChatbotSseParser()
  const events = parseChatbotSseBuffer('event: delta\ndata: {"text":"추천"}\n')

  assert.deepEqual(events, [])
  assert.equal(parseChatbotSseBuffer.remainder, 'event: delta\ndata: {"text":"추천"}\n')
})
