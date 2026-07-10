import assert from 'node:assert/strict'
import test from 'node:test'

import { buildChatbotTimeline, formatChatbotProposalNumber } from './chatbotTimeline.js'

test('places a newly created proposal after the request that created it', () => {
  const timeline = buildChatbotTimeline(
    [{ id: 'm1', createdAt: '2026-07-10T01:00:00Z' }],
    [{ id: 'p1', created_at: '2026-07-10T01:00:01Z', status: 'PENDING' }],
  )

  assert.deepEqual(timeline.map((item) => item.type), ['message', 'proposal'])
})

test('sorts messages and proposals together by creation time', () => {
  const timeline = buildChatbotTimeline(
    [
      { id: 'm2', createdAt: '2026-07-10T01:00:02Z' },
      { id: 'm1', createdAt: '2026-07-10T01:00:00Z' },
    ],
    [{ id: 'p1', created_at: '2026-07-10T01:00:01Z' }],
  )

  assert.deepEqual(timeline.map((item) => item.id), [
    'message-m1',
    'proposal-p1',
    'message-m2',
  ])
})

test('does not format a missing market price as zero', () => {
  assert.equal(formatChatbotProposalNumber(null), '-')
  assert.equal(formatChatbotProposalNumber(undefined), '-')
  assert.equal(formatChatbotProposalNumber(''), '-')
})
