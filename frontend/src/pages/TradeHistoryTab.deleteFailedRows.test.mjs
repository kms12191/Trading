import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const __filename = fileURLToPath(import.meta.url)
const __dirname = dirname(__filename)
const desktopSource = readFileSync(resolve(__dirname, 'TradeHistoryTab.jsx'), 'utf8')
const mobileSource = readFileSync(resolve(__dirname, 'mobile/MobileTradeHistoryTab.jsx'), 'utf8')

for (const source of [desktopSource, mobileSource]) {
  assert.equal(
    source.includes('const DELETABLE_TRADE_STATUSES'),
    true,
    '삭제 가능한 거래 상태 목록이 필요합니다.',
  )
  for (const status of ['주문실패', '취소완료', '출금실패']) {
    assert.equal(source.includes(`'${status}'`), true, `${status} 상태는 삭제 대상이어야 합니다.`)
  }
  assert.equal(source.includes('const isDeletableTradeHistoryItem'), true, '삭제 가능 여부 헬퍼가 필요합니다.')
  assert.equal(source.includes('handleDeleteTradeHistory'), true, '거래내역 삭제 핸들러가 필요합니다.')
  assert.equal(source.includes('trade_proposals'), true, '주문 실패/취소 내역 삭제는 trade_proposals를 대상으로 해야 합니다.')
  assert.equal(source.includes('asset_transfer_proposals'), true, '출금 실패 내역 삭제는 asset_transfer_proposals를 대상으로 해야 합니다.')
  assert.equal(source.includes('삭제'), true, '삭제 버튼 문구가 필요합니다.')
}
