function toTimestamp(value) {
  const timestamp = Date.parse(value || '')
  return Number.isFinite(timestamp) ? timestamp : Number.MAX_SAFE_INTEGER
}

export function formatChatbotProposalNumber(value) {
  if (value === null || value === undefined || value === '') return '-'
  const numeric = Number(value)
  if (!Number.isFinite(numeric)) return '-'
  return numeric.toLocaleString('ko-KR', { maximumFractionDigits: 8 })
}

export function buildChatbotTimeline(messages = [], pendingProposals = []) {
  return [
    ...messages.map((message) => ({
      type: 'message',
      id: `message-${message.id}`,
      createdAt: message.createdAt,
      data: message,
    })),
    ...pendingProposals.map((proposal) => ({
      type: 'proposal',
      id: `proposal-${proposal.id}`,
      createdAt: proposal.created_at,
      data: proposal,
    })),
  ].sort((left, right) => toTimestamp(left.createdAt) - toTimestamp(right.createdAt))
}
