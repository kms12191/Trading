import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const __filename = fileURLToPath(import.meta.url)
const __dirname = dirname(__filename)
const source = readFileSync(resolve(__dirname, 'AdminUsers.jsx'), 'utf8')

assert.equal(source.includes('갱신'), true, '관리자 유저 목록에 수동 갱신 버튼이 필요합니다.')
assert.equal(source.includes('유저 상세 관리'), true, '유저 클릭 시 상세 관리 모달을 열어야 합니다.')
assert.equal(source.includes('거래내역'), true, '관리 모달에는 거래내역 탭이 필요합니다.')
assert.equal(source.includes('권한'), true, '관리 모달에는 권한 탭이 필요합니다.')
assert.equal(source.includes('예상 비용'), true, '토큰 사용량에는 예상 비용을 표시해야 합니다.')
assert.equal(source.includes('통산 예상 비용'), true, '관리자 요약에는 통산 예상 비용을 표시해야 합니다.')
assert.equal(source.includes('GPT_4_1_MINI_PRICING'), true, '현재 사용 모델 기준 비용 상수가 필요합니다.')
assert.equal(source.includes('estimateCurrentModelCost'), true, '입력/출력 토큰 기준 비용 계산 함수가 필요합니다.')
assert.equal(source.includes('estimateBlendedCurrentModelCost'), true, '통산/유저별 총 토큰 기준 추정 비용 계산 함수가 필요합니다.')
assert.equal(
  source.includes('/trade-history?limit=100'),
  true,
  '관리 모달은 유저별 거래내역 API를 호출해야 합니다.',
)
assert.match(
  source,
  /fetch\(`\$\{API_BASE_URL\}\/api\/admin\/users\/\$\{modalUser\.id\}\/role`/,
  '관리 모달은 유저 role 변경 API를 호출해야 합니다.',
)
assert.equal(source.includes('보유자산'), false, '관리 모달에서 유저별 보유자산을 노출하면 안 됩니다.')
