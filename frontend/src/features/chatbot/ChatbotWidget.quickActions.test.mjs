import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, resolve } from 'node:path'

const __filename = fileURLToPath(import.meta.url)
const __dirname = dirname(__filename)
const source = readFileSync(resolve(__dirname, 'ChatbotWidget.jsx'), 'utf8')

assert.equal(
  source.includes('const QUICK_MESSAGES'),
  false,
  '챗봇 하단 퀵 메시지 배열은 제거되어야 합니다.',
)

for (const label of ['자산 요약', '시세 확인', '뉴스 분석', '공시 조회', '투자 리스크', '이용 가이드']) {
  assert.equal(
    source.includes(label),
    false,
    `하단 기능 버튼 문구 "${label}"는 남아 있으면 안 됩니다.`,
  )
}

assert.match(
  source,
  /aria-label="매매 요청 폼 열기"[\s\S]*?>\s*매매 요청\s*<\/button>/,
  '챗봇 헤더에 매매 요청 버튼이 있어야 합니다.',
)
