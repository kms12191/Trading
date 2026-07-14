import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const __filename = fileURLToPath(import.meta.url)
const __dirname = dirname(__filename)
const source = readFileSync(resolve(__dirname, 'TradeHistoryTab.jsx'), 'utf8')

assert.equal(
  source.includes('const buildBrokerOrderLookup'),
  true,
  '브로커 원장 주문을 외부 주문번호 기준으로 조회하는 헬퍼가 필요합니다.',
)
assert.equal(
  source.includes('const filterUnlinkedBrokerOrders'),
  true,
  'AE 거래와 연결된 브로커 원장 행은 별도 행에서 제외해야 합니다.',
)
assert.match(
  source,
  /hydratedRows\.map\(\(proposal\) => mapProposalToTrade\(proposal,\s*brokerOrderLookup\)\)/,
  'AE 거래 행은 연결된 브로커 원장 상태를 반영해야 합니다.',
)
assert.match(
  source,
  /filterUnlinkedBrokerOrders\(brokerOrders,\s*brokerOrderLookup\)/,
  '브로커 원장 목록은 AE 거래와 연결되지 않은 주문만 표시해야 합니다.',
)
