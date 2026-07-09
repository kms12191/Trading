import assert from 'node:assert/strict'

import {
  CHATBOT_DEFAULT_SIZE,
  CHATBOT_MAX_SIZE,
  getDefaultChatbotSize,
  resizeChatbotPanel,
} from './chatbotResize.js'

const viewport = { width: 1280, height: 900 }

assert.deepEqual(getDefaultChatbotSize(), CHATBOT_DEFAULT_SIZE)

assert.deepEqual(
  resizeChatbotPanel({
    startSize: CHATBOT_DEFAULT_SIZE,
    startClientX: 800,
    startClientY: 300,
    clientX: 700,
    clientY: 260,
    direction: 'corner',
    viewport,
  }),
  {
    width: CHATBOT_DEFAULT_SIZE.width + 100,
    height: CHATBOT_DEFAULT_SIZE.height + 40,
  },
)

assert.deepEqual(
  resizeChatbotPanel({
    startSize: CHATBOT_DEFAULT_SIZE,
    startClientX: 800,
    startClientY: 300,
    clientX: 900,
    clientY: 500,
    direction: 'corner',
    viewport,
  }),
  CHATBOT_DEFAULT_SIZE,
)

assert.deepEqual(
  resizeChatbotPanel({
    startSize: CHATBOT_DEFAULT_SIZE,
    startClientX: 800,
    startClientY: 300,
    clientX: -1000,
    clientY: -1000,
    direction: 'corner',
    viewport,
  }),
  CHATBOT_MAX_SIZE,
)

console.log('chatbot resize tests passed')
