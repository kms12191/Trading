const EMPTY_ANSWERS = new Set(['확인 필요', '원문 확인 필요', '후속 확인 필요', '원공시 비교 필요', '제목 기반', '및'])
const LOW_SIGNAL_LABELS = new Set(['주요내용', '주요 내용', '핵심내용', '핵심 내용', '실현가능성', '실현 가능성'])
const PLACEHOLDER_DATE_LABELS = new Set(['추진일정', '추진 일정', '실현가능성', '실현 가능성'])
const DUPLICATE_CHECK_METRICS = {
  '조정 기준가': ['기준가'],
  '실시일': ['권리락 실시일'],
  '권리락 사유': ['사유'],
}
const DISCLOSURE_LABEL_ALIASES = {
  처분규모: '처분예정금액',
  처분예정금액: '처분예정금액',
  처분목적: '처분목적',
  처분목적및방법: '처분목적',
  처분예정기간: '처분예정기간',
  취득규모: '취득예정금액',
  취득예정금액: '취득예정금액',
  취득목적: '취득목적',
  취득예상기간: '취득예정기간',
  취득예정기간: '취득예정기간',
}

export function normalizeDisclosureText(value) {
  return String(value || '')
    .replace(/\s+/g, ' ')
    .trim()
    .replace(/공시\s+공시(?=(?:로|를|가|는|의|에|입니다|$))/g, '공시')
}

function formatDisclosureDate(value) {
  const text = normalizeDisclosureText(value)
  if (/^\d{8}$/.test(text)) {
    return `${text.slice(0, 4)}-${text.slice(4, 6)}-${text.slice(6, 8)}`
  }
  return text
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
  const checkKey = disclosureLabelKey(check.question)
  const duplicateLabels = DUPLICATE_CHECK_METRICS[check.question] || []
  return metricLabels.has(checkKey) || duplicateLabels.some((label) => metricLabels.has(disclosureLabelKey(label)))
}

function disclosureLabelKey(label) {
  const compactLabel = normalizeDisclosureText(label).replace(/\s+/g, '')
  return DISCLOSURE_LABEL_ALIASES[compactLabel] || compactLabel
}

function isPlaceholderDate(label, value) {
  return PLACEHOLDER_DATE_LABELS.has(label) && /^\d{4}-01-01$/.test(value)
}

function isUsefulDisclosurePair(label, value) {
  return Boolean(
    label
    && value
    && !LOW_SIGNAL_LABELS.has(label)
    && !EMPTY_ANSWERS.has(value)
    && !isPlaceholderDate(label, value),
  )
}

export function buildDisclosurePresentation(toolResult) {
  const compoundResult = toolResult?.source === 'COMPOUND_INFO' ? toolResult.secondary : toolResult
  const disclosureResult = compoundResult?.source === 'NEWS_DISCLOSURE_COMBINED' ? compoundResult.disclosure : compoundResult

  if (disclosureResult?.source !== 'DISCLOSURE_DB' || !Array.isArray(disclosureResult.items)) {
    return { items: [], sourceUrl: '' }
  }

  const items = disclosureResult.items.map((item) => {
    const analysis = item?.analysis || {}
    const metrics = (Array.isArray(analysis.metrics) ? analysis.metrics : [])
      .map(normalizeMetric)
      .filter((metric) => isUsefulDisclosurePair(metric.label, metric.value))
      .slice(0, 6)
    const metricLabels = new Set(metrics.map((metric) => disclosureLabelKey(metric.label)))
    const checks = (Array.isArray(analysis.check_items) ? analysis.check_items : [])
      .map(normalizeCheck)
      .filter((check) => (
        isUsefulDisclosurePair(check.question, check.answer)
        && !duplicatesMetric(check, metricLabels)
      ))
      .slice(0, 3)

    const summary = normalizeDisclosureText(analysis.plain_summary || item?.summary)

    return {
      corpName: normalizeDisclosureText(item?.corp_name) || 'DART',
      title: normalizeDisclosureText(item?.report_nm) || '공시 제목 없음',
      publishedAt: formatDisclosureDate(item?.rcept_dt || item?.published_at),
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
    sourceUrl: String(disclosureResult.source_url || ''),
  }
}
