export function getApiErrorMessage(payloadOrError, fallback = '요청 처리에 실패했습니다.') {
  const payload = payloadOrError || {}
  const error = payload.error || {}
  const title = error.title || payload.message || payload.error || payloadOrError?.message || fallback
  const detail = error.action || error.message || payload.detail || ''
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
