function formatWon(value) {
  const numeric = Number(value)
  if (!Number.isFinite(numeric)) return ''
  return `${numeric.toLocaleString('ko-KR', { maximumFractionDigits: 0 })}원`
}

function uniqueTexts(values) {
  const seen = new Set()
  return values.filter((value) => {
    const text = String(value || '').trim()
    if (!text || seen.has(text)) return false
    seen.add(text)
    return true
  })
}

const APPROVAL_BLOCKER_FIELDS = [
  'insufficient_cash',
  'insufficient_holding',
  'is_market_closed',
  'insufficient_permission',
  'futures_real_blocked',
  'exceeds_real_order_limit',
]

export function isProposalApprovalBlocked(proposal) {
  const payload = proposal?.raw_order_payload || {}
  const precheck = payload.precheck
  if (payload.precheck_status !== 'OK' || !precheck || typeof precheck !== 'object') {
    return true
  }
  return APPROVAL_BLOCKER_FIELDS.some((field) => Boolean(precheck[field]))
}

export function buildProposalPrecheckSummary(proposal) {
  const payload = proposal?.raw_order_payload || {}
  const precheck = payload.precheck || null
  const precheckStatus = payload.precheck_status || ''
  if (!precheck && !precheckStatus) return null

  const warnings = []
  if (precheck?.insufficient_cash) warnings.push('예수금이 부족할 수 있습니다.')
  if (precheck?.insufficient_holding) warnings.push('보유 수량보다 많은 매도 주문입니다.')
  if (precheck?.is_market_closed) warnings.push(precheck.market_status_message || '현재는 거래 가능 시간이 아닙니다.')
  if (Array.isArray(precheck?.warnings)) warnings.push(...precheck.warnings)
  if (!precheck && payload.precheck_error) warnings.push(payload.precheck_error)

  const cleanWarnings = uniqueTexts(warnings)
  return {
    status: cleanWarnings.length > 0 || precheckStatus === 'FAILED' ? 'WARNING' : 'OK',
    estimatedAmountText: formatWon(precheck?.estimated_amount_krw),
    availableCashText: formatWon(precheck?.available_cash),
    warnings: cleanWarnings,
  }
}
