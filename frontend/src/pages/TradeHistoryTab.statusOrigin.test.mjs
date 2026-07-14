import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const __filename = fileURLToPath(import.meta.url)
const __dirname = dirname(__filename)
const source = readFileSync(resolve(__dirname, 'TradeHistoryTab.jsx'), 'utf8')

for (const text of ['승인대기', '주문접수', '부분체결', '정정접수', '체결완료', '주문실패']) {
  assert.equal(source.includes(text), true, `거래 상태 문구 "${text}"가 필요합니다.`)
}

assert.equal(source.includes("'주문 완료'"), false, 'APPROVED/ORDERED를 주문 완료로 표시하면 안 됩니다.')
assert.equal(source.includes('AE 거래'), true, '앱 주문 출처는 AE 거래로 표시해야 합니다.')
assert.equal(source.includes('AE 자산이동'), true, '자산 이동 출처는 AE 자산이동으로 표시해야 합니다.')
assert.equal(source.includes('토스 앱/브로커'), true, '브로커 원장 출처는 토스 앱/브로커로 표시해야 합니다.')
assert.match(source, /isActionable:\s*isActionableOrderStatus\(rawStatus\)\s*&&\s*Boolean\(proposal\.external_order_id\s*\|\|\s*linkedBrokerOrder\?\.external_order_id\)/)
