export function parseChatbotSseBuffer(buffer) {
  const text = `${parseChatbotSseBuffer.remainder || ''}${String(buffer || '')}`
  const frames = text.split(/\n\n/)
  parseChatbotSseBuffer.remainder = frames.pop() || ''

  return frames
    .map((frame) => {
      const lines = frame.split(/\n/)
      const eventLine = lines.find((line) => line.startsWith('event:'))
      const dataLines = lines.filter((line) => line.startsWith('data:'))
      const event = eventLine ? eventLine.replace(/^event:\s*/, '').trim() : 'message'
      const dataText = dataLines.map((line) => line.replace(/^data:\s?/, '')).join('\n')
      if (!dataText) return null
      try {
        return { event, data: JSON.parse(dataText) }
      } catch {
        return { event, data: { raw: dataText } }
      }
    })
    .filter(Boolean)
}

parseChatbotSseBuffer.remainder = ''

export function resetChatbotSseParser() {
  parseChatbotSseBuffer.remainder = ''
}
