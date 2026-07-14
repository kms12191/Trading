import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const __filename = fileURLToPath(import.meta.url)
const __dirname = dirname(__filename)
const source = readFileSync(resolve(__dirname, 'TradeHistoryTab.jsx'), 'utf8')

assert.match(
  source,
  /<select[\s\S]*value=\{selectedExchange\}[\s\S]*onChange=\{\(event\) => setSelectedExchange\(event\.target\.value\)\}/,
  '거래소 필터는 selectedExchange와 연결된 드롭다운이어야 합니다.',
)

assert.equal(
  source.includes('<span>Exchange:</span>'),
  false,
  '거래소 필터 라벨은 영문 Exchange가 아니라 한글이어야 합니다.',
)

for (const label of ['전체', '토스증권', '한국투자증권', '코인원', '바이낸스 현물', '바이낸스 선물']) {
  assert.equal(source.includes(label), true, `"${label}" 거래소 라벨이 필요합니다.`)
}

assert.equal(
  /\['ALL', 'TOSS', 'KIS', 'COINONE', 'BINANCE', 'BINANCE_UM_FUTURES'\]\.map\(\(item\) => \(\s*<button/.test(source),
  false,
  '거래소 필터는 버튼 목록으로 렌더링하면 안 됩니다.',
)
