import { supabase } from '../../supabaseClient'
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
    }),
  })

  const payload = await response.json().catch(() => ({}))

  if (!response.ok || payload.success === false) {
    throw new Error(payload?.error?.title || payload?.message || '챗봇 응답을 불러오지 못했습니다.')
  }

  return payload.data
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
    }),
  })

  if (!response.ok || !response.body) {
    const payload = await response.json().catch(() => ({}))
    throw new Error(payload?.error?.title || payload?.message || '챗봇 스트림을 불러오지 못했습니다.')
  }

  resetChatbotSseParser()
  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let donePayload = null

  while (true) {
    const { value, done } = await reader.read()
    if (done) break
    const chunk = decoder.decode(value, { stream: true })
    for (const event of parseChatbotSseBuffer(chunk)) {
      if (event.event === 'trace') handlers.onTrace?.(event.data)
      if (event.event === 'delta') handlers.onDelta?.(event.data?.text || '')
      if (event.event === 'done') {
        donePayload = event.data
        handlers.onDone?.(event.data)
      }
      if (event.event === 'error') {
        handlers.onError?.(event.data)
        throw new Error(event.data?.error?.title || event.data?.message || '챗봇 스트림 처리 중 문제가 발생했습니다.')
      }
    }
  }

  const tail = decoder.decode()
  for (const event of parseChatbotSseBuffer(`${tail}\n\n`)) {
    if (event.event === 'done') {
      donePayload = event.data
      handlers.onDone?.(event.data)
    }
  }

  return donePayload
}
