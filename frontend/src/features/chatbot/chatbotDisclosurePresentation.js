const EMPTY_ANSWERS = new Set(['확인 필요', '원문 확인 필요', '후속 확인 필요', '원공시 비교 필요', '제목 기반'])
const DUPLICATE_CHECK_METRICS = {
  '조정 기준가': ['기준가'],
  '실시일': ['권리락 실시일'],
  '권리락 사유': ['사유'],
}

export function normalizeDisclosureText(value) {
  return String(value || '')
    .replace(/\s+/g, ' ')
    .trim()
    .replace(/공시\s+공시(?=(?:로|를|가|는|의|에|입니다|$))/g, '공시')
}

function normalizeMetric(metric) {
  return {
    label: normalizeDisclosureText(metric?.label),
    value: normalizeDisclosureText(metric?.value),
  }
}

function normalizeCheck(check) {
  return {
    question: normalizeDisclosureText(check?.question),
    answer: normalizeDisclosureText(check?.answer),
  }
}

function confidenceLabel(confidence) {
  if (confidence === 'high') return '높음'
  if (confidence === 'medium') return '보통'
  return '낮음'
}

function sourceLabel(source) {
  return source === 'OPENDART_DOCUMENT' ? 'DART 상세 기반' : '제목 기반'
}

function duplicatesMetric(check, metricLabels) {
  const duplicateLabels = DUPLICATE_CHECK_METRICS[check.question] || []
  return metricLabels.has(check.question) || duplicateLabels.some((label) => metricLabels.has(label))
}

export function buildDisclosurePresentation(toolResult) {
  if (toolResult?.source !== 'DISCLOSURE_DB' || !Array.isArray(toolResult.items)) {
    return { items: [], sourceUrl: '' }
  }

  const items = toolResult.items.map((item) => {
    const analysis = item?.analysis || {}
    const metrics = (Array.isArray(analysis.metrics) ? analysis.metrics : [])
      .map(normalizeMetric)
      .filter((metric) => metric.label && metric.value)
      .slice(0, 6)
    const metricLabels = new Set(metrics.map((metric) => metric.label))
    const checks = (Array.isArray(analysis.check_items) ? analysis.check_items : [])
      .map(normalizeCheck)
      .filter((check) => (
        check.question
        && check.answer
        && !EMPTY_ANSWERS.has(check.answer)
        && !duplicatesMetric(check, metricLabels)
      ))
      .slice(0, 3)

    const summary = normalizeDisclosureText(analysis.plain_summary || item?.summary)

    return {
      corpName: normalizeDisclosureText(item?.corp_name) || 'DART',
      title: normalizeDisclosureText(item?.report_nm) || '공시 제목 없음',
      url: String(item?.url || ''),
      sentiment: normalizeDisclosureText(analysis.sentiment),
      sentimentLabel: normalizeDisclosureText(analysis.sentiment_label) || '정보',
      confidence: confidenceLabel(normalizeDisclosureText(analysis.confidence)),
      source: sourceLabel(normalizeDisclosureText(analysis.analysis_source)),
      headline: summary ? '' : normalizeDisclosureText(analysis.headline),
      summary,
      metrics,
      checks,
      risk: normalizeDisclosureText(Array.isArray(analysis.risk_points) ? analysis.risk_points[0] : ''),
    }
  })

  return {
    items,
    sourceUrl: String(toolResult.source_url || ''),
  }
}
