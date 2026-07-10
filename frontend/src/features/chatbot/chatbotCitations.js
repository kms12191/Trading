const SOURCE_LABELS = {
  DISCLOSURE: 'DART 공시',
  OBSIDIAN: '옵시디언 노트',
  APP_NOTE: '투자노트',
  MEMORY: '자동메모리',
  NEWS: '뉴스',
}

function normalizeText(value) {
  return String(value || '').replace(/\s+/g, ' ').trim()
}

function formatSimilarity(value) {
  const numeric = Number(value)
  if (!Number.isFinite(numeric)) return ''
  return `유사도 ${(numeric * 100).toFixed(1)}%`
}

export function buildChatbotCitations(toolResult) {
  const rows = Array.isArray(toolResult?.citations) ? toolResult.citations : []
  const seen = new Set()
  const citations = []

  for (const row of rows) {
    const sourceType = normalizeText(row?.source_type).toUpperCase()
    const sourceId = normalizeText(row?.source_id)
    const symbol = normalizeText(row?.symbol).toUpperCase()
    const key = `${sourceType}:${sourceId}:${symbol}`
    if (!sourceType || seen.has(key)) continue
    seen.add(key)

    const title = normalizeText(row?.title)
    citations.push({
      label: SOURCE_LABELS[sourceType] || sourceType,
      sourceId,
      title: symbol && title ? `${title} (${symbol})` : title || symbol || sourceId,
      summary: normalizeText(row?.summary),
      similarityText: formatSimilarity(row?.similarity),
    })
    if (citations.length >= 3) break
  }

  return citations
}
