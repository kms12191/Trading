import assert from 'node:assert/strict'
import test from 'node:test'

import { shouldSubmitChatbotInput } from './chatbotInput.js'

test('does not submit while Korean IME composition is active', () => {
  assert.equal(shouldSubmitChatbotInput({
    key: 'Enter',
    shiftKey: false,
    keyCode: 229,
    nativeEvent: { isComposing: true },
  }), false)
})

test('submits plain Enter after composition ends', () => {
  assert.equal(shouldSubmitChatbotInput({
    key: 'Enter',
    shiftKey: false,
    keyCode: 13,
    nativeEvent: { isComposing: false },
  }), true)
})

test('does not submit Shift Enter', () => {
  assert.equal(shouldSubmitChatbotInput({
    key: 'Enter',
    shiftKey: true,
    nativeEvent: { isComposing: false },
  }), false)
})
