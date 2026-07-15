import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'
import { fileURLToPath } from 'node:url'
import { dirname, resolve } from 'node:path'

const __filename = fileURLToPath(import.meta.url)
const __dirname = dirname(__filename)

test('상단 버튼 외 자연어 주문 폼 진입과 조건감시 입력이 없다', () => {
  const source = readFileSync(resolve(__dirname, 'ChatbotWidget.jsx'), 'utf8')

  assert.match(source, /<OrderEntryFlow/)
  assert.equal(source.includes("action?.type === 'open_order_form'"), false)
  assert.equal(source.includes('normalizeOrderFormPrefill'), false)
  assert.equal(source.includes('ChatOrderForm'), false)
  assert.equal(source.includes('조건감시'), false)
  assert.equal(source.includes('챗봇이 인식한 임시 입력값입니다'), false)
  assert.equal(source.includes('alert('), false)
})
