const TRACE_LABELS = {
  ml: 'ML 신호',
  rag: 'RAG 벡터검색',
  disclosure: 'DART 공시',
  tavily: 'Tavily 웹검색',
  db: 'Supabase DB 조회',
  precheck: '주문 사전검증',
}

function normalizeText(value) {
  return String(value || '').replace(/\s+/g, ' ').trim()
}

function addBadge(badges, seen, kind, label) {
  const normalizedKind = normalizeText(kind).toLowerCase()
  const normalizedLabel = normalizeText(label) || TRACE_LABELS[normalizedKind]
  if (!normalizedKind || !normalizedLabel || seen.has(normalizedKind)) return
  seen.add(normalizedKind)
  badges.push({ kind: normalizedKind, label: normalizedLabel })
}

export function buildChatbotTraceBadges({ traceSteps = [], toolResult = null } = {}) {
  const badges = []
  const seen = new Set()

  if (Array.isArray(traceSteps) && traceSteps.length > 0) {
    traceSteps.forEach((step) => addBadge(badges, seen, step?.kind, step?.label))
    return badges
  }

  const source = normalizeText(toolResult?.source).toUpperCase()
  const citations = Array.isArray(toolResult?.citations) ? toolResult.citations : []
  if (source.includes('TAVILY')) addBadge(badges, seen, 'tavily', TRACE_LABELS.tavily)
  if (['DISCLOSURE_DB', 'NEWS_DB', 'VECTOR_DB', 'HOME_MARKET', 'OPEN_ORDERS'].includes(source)) {
    addBadge(badges, seen, 'db', TRACE_LABELS.db)
  }
  if (source === 'ML_ACTIVE_SIGNAL') addBadge(badges, seen, 'ml', TRACE_LABELS.ml)
  if (source === 'DISCLOSURE_DB' || citations.some((row) => normalizeText(row?.source_type).toUpperCase() === 'DISCLOSURE')) {
    addBadge(badges, seen, 'disclosure', TRACE_LABELS.disclosure)
  }
  if (source === 'VECTOR_DB' || citations.length > 0) addBadge(badges, seen, 'rag', TRACE_LABELS.rag)
  if (toolResult?.raw_order_payload?.precheck_status) addBadge(badges, seen, 'precheck', TRACE_LABELS.precheck)

  return badges
}

export function getNextTypewriterText(currentText, fullText, chunkSize = 14) {
  const current = String(currentText || '')
  const full = String(fullText || '')
  if (!full || current.length >= full.length) return full

  const nextTarget = Math.min(current.length + chunkSize, full.length)
  const sentenceAllowance = current.length === 0 ? 4 : 16
  const sentenceBreakCandidates = [
    full.indexOf('\n', current.length + 1),
    full.indexOf('. ', current.length + 1),
    full.indexOf('다.', current.length + 1),
    full.indexOf('다. ', current.length + 1),
    full.indexOf('요.', current.length + 1),
    full.indexOf('요. ', current.length + 1),
  ].filter((index) => index > current.length && index <= nextTarget + sentenceAllowance)
  const spaceBreak = full.lastIndexOf(' ', nextTarget)
  const nextBreakCandidates = sentenceBreakCandidates.length > 0
    ? sentenceBreakCandidates
    : [spaceBreak].filter((index) => index > current.length)

  const nextIndex = nextBreakCandidates.length > 0
    ? (() => {
      const boundary = Math.min(...nextBreakCandidates)
      return full[boundary + 1] === '.' ? boundary + 2 : boundary + 1
    })()
    : nextTarget
  return full.slice(0, Math.min(nextIndex, full.length)).trimEnd()
}
