export function getApiErrorMessage(payloadOrError, fallback = '요청 처리에 실패했습니다.') {
  const payload = payloadOrError || {}
  const error = payload.error || {}
  const hasStructuredError = Boolean(error && typeof error === 'object' && (error.title || error.message || error.action))
  const rawTitle = error.title || payload.message || payload.error || payloadOrError?.message || fallback
  const detailParts = hasStructuredError
    ? [error.message, error.action]
    : [error.action || error.message || payload.detail]
  const lines = [rawTitle, ...detailParts]
    .flatMap((value) => String(value || '').split('\n'))
    .map((value) => value.trim())
    .filter(Boolean)
  const uniqueLines = lines.filter((line, index) => lines.indexOf(line) === index)
  const title = hasStructuredError ? uniqueLines.join('\n') : rawTitle
  const detail = hasStructuredError ? '' : (detailParts[0] || '')
  const raw = error.raw_message || ''

  return {
    title,
    detail,
    raw,
  }
}

export function buildApiErrorText(payloadOrError, fallback = '요청 처리에 실패했습니다.') {
  const message = getApiErrorMessage(payloadOrError, fallback)
  return message.detail ? `${message.title} ${message.detail}` : message.title
}
