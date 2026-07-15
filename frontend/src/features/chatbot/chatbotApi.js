import { supabase } from '../../supabaseClient'
import { buildApiErrorText } from '../../lib/apiError.js'
import { parseChatbotSseBuffer, resetChatbotSseParser } from './chatbotStream'

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:5050'

export async function sendChatbotMessage(message, options = {}) {
  const {
    data: { session },
  } = await supabase.auth.getSession()

  if (!session?.access_token) {
    throw new Error('로그인 후 이용 가능합니다.')
  }

  const headers = {
    'Content-Type': 'application/json',
  }

  headers.Authorization = `Bearer ${session.access_token}`

  const response = await fetch(`${API_BASE_URL}/api/chatbot/message`, {
    method: 'POST',
    headers,
    body: JSON.stringify({
      message,
      timezone: options.timezone,
      structured_order: options.structured_order,
    }),
  })

  const payload = await response.json().catch(() => ({}))

  if (!response.ok || payload.success === false) {
    throw new Error(buildApiErrorText(payload, '챗봇 응답을 불러오지 못했습니다.'))
  }

  return payload.data
}

async function orderEntryRequest(path, options = {}) {
  const {
    data: { session },
  } = await supabase.auth.getSession()

  if (!session?.access_token) {
    throw new Error('로그인 후 이용 가능합니다.')
  }

  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${session.access_token}`,
      ...(options.headers || {}),
    },
  })
  const payload = await response.json().catch(() => ({}))
  if (!response.ok || payload.success === false) {
    throw new Error(buildApiErrorText(payload, '매매 요청 정보를 처리하지 못했습니다.'))
  }
  return payload.data
}

function withQuery(path, params) {
  const query = new URLSearchParams(
    Object.entries(params || {}).filter(([, value]) => value !== undefined && value !== null && value !== ''),
  )
  return `${path}?${query.toString()}`
}

export function fetchOrderEntryAccounts() {
  return orderEntryRequest('/api/trade/order-entry/accounts')
}

export function searchOrderEntrySymbols(params) {
  return orderEntryRequest(withQuery('/api/trade/order-entry/symbols', params))
}

export function fetchOrderEntryHoldings(params) {
  return orderEntryRequest(withQuery('/api/trade/order-entry/holdings', params))
}

export function fetchOrderEntryContext(params) {
  return orderEntryRequest(withQuery('/api/trade/order-entry/context', params))
}

export function precheckOrderEntry(order) {
  return orderEntryRequest('/api/trade/precheck', {
    method: 'POST',
    body: JSON.stringify(order),
  })
}

export function createOrderEntryProposal(order, precheckToken, timezone) {
  return sendChatbotMessage('[매매 요청] 구조화 주문 제안 생성', {
    timezone,
    structured_order: {
      is_structured_order: true,
      ...order,
      precheck_token: precheckToken,
    },
  })
}

export async function streamChatbotMessage(message, handlers = {}, options = {}) {
  const {
    data: { session },
  } = await supabase.auth.getSession()

  if (!session?.access_token) {
    throw new Error('로그인 후 이용 가능합니다.')
  }

  const response = await fetch(`${API_BASE_URL}/api/chatbot/stream`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${session.access_token}`,
    },
    body: JSON.stringify({
      message,
      timezone: options.timezone,
      structured_order: options.structured_order,
    }),
  })

  if (!response.ok || !response.body) {
    const payload = await response.json().catch(() => ({}))
    throw new Error(buildApiErrorText(payload, '챗봇 스트림을 불러오지 못했습니다.'))
  }

  resetChatbotSseParser()
  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let donePayload = null

  const handleEvent = (event) => {
    if (event.event === 'trace') handlers.onTrace?.(event.data)
    if (event.event === 'delta') handlers.onDelta?.(event.data?.text || '')
    if (event.event === 'done') {
      donePayload = event.data
      handlers.onDone?.(event.data)
    }
    if (event.event === 'error') {
      handlers.onError?.(event.data)
      throw new Error(buildApiErrorText(event.data, '챗봇 스트림 처리 중 문제가 발생했습니다.'))
    }
  }

  while (true) {
    const { value, done } = await reader.read()
    if (done) break
    const chunk = decoder.decode(value, { stream: true })
    for (const event of parseChatbotSseBuffer(chunk)) {
      handleEvent(event)
    }
  }

  const tail = decoder.decode()
  for (const event of parseChatbotSseBuffer(`${tail}\n\n`)) {
    handleEvent(event)
  }

  if (!donePayload) {
    throw new Error('챗봇 스트림이 완료되지 않았습니다. 잠시 후 다시 시도해 주세요.')
  }

  return donePayload
}
