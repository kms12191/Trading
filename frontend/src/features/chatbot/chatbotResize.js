export const CHATBOT_DEFAULT_SIZE = {
  width: 390,
  height: 560,
}

export const CHATBOT_MIN_SIZE = {
  width: 390,
  height: 560,
}

export const CHATBOT_MAX_SIZE = {
  width: 720,
  height: 760,
}

export function getDefaultChatbotSize() {
  return { ...CHATBOT_DEFAULT_SIZE }
}

function clamp(value, min, max) {
  return Math.min(Math.max(value, min), max)
}

export function getChatbotMaxSize(viewport = {}) {
  const width = Number(viewport.width || globalThis.window?.innerWidth || CHATBOT_DEFAULT_SIZE.width)
  const height = Number(viewport.height || globalThis.window?.innerHeight || CHATBOT_DEFAULT_SIZE.height)

  return {
    width: Math.min(CHATBOT_MAX_SIZE.width, Math.floor(width * 0.9)),
    height: Math.min(CHATBOT_MAX_SIZE.height, Math.floor(height * 0.85)),
  }
}

export function resizeChatbotPanel({
  startSize,
  startClientX,
  startClientY,
  clientX,
  clientY,
  direction,
  viewport,
}) {
  const maxSize = getChatbotMaxSize(viewport)
  const deltaX = Number(startClientX) - Number(clientX)
  const deltaY = Number(startClientY) - Number(clientY)
  const shouldResizeWidth = direction === 'x' || direction === 'corner'
  const shouldResizeHeight = direction === 'y' || direction === 'corner'

  return {
    width: shouldResizeWidth
      ? clamp(Number(startSize.width) + deltaX, CHATBOT_MIN_SIZE.width, maxSize.width)
      : Number(startSize.width),
    height: shouldResizeHeight
      ? clamp(Number(startSize.height) + deltaY, CHATBOT_MIN_SIZE.height, maxSize.height)
      : Number(startSize.height),
  }
}
