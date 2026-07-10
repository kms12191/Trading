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

test('preserves structured error fields and request id', () => {
  resetChatbotSseParser()
  const [event] = parseChatbotSseBuffer([
    'event: error',
    'data: {"message":"스트림 실패","error":{"title":"API 키 확인 필요","message":"키가 없습니다.","action":"설정에서 등록하세요."},"meta":{"request_id":"req-1"}}',
    '',
    '',
  ].join('\n'))

  assert.equal(event.event, 'error')
  assert.equal(event.data.error.title, 'API 키 확인 필요')
  assert.equal(event.data.error.message, '키가 없습니다.')
  assert.equal(event.data.error.action, '설정에서 등록하세요.')
  assert.equal(event.data.meta.request_id, 'req-1')
})
