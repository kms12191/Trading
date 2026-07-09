import { supabase } from '../../supabaseClient'

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:5050'

export async function sendChatbotMessage(message, options = {}) {
  const {
    data: { session },
  } = await supabase.auth.getSession()

  const headers = {
    'Content-Type': 'application/json',
  }

  if (session?.access_token) {
    headers.Authorization = `Bearer ${session.access_token}`
  }

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
