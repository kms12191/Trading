import assert from 'node:assert/strict'
import test from 'node:test'
import { buildAiFundConfigPayloads, buildTossStockSelectionPayload, canEditAiFundSettings, getNextAiFundActiveState } from './adminAiFundDashboardModel.js'

test('토스 주식 자동선별 저장값은 시장 배분과 최대 보유 종목 수를 포함한다', () => {
  assert.deepEqual(
    buildTossStockSelectionPayload({
      userId: 'user-1',
      capital: 5000000,
      riskPreset: 'neutral',
      assetScope: 'ALL',
      maxOpenPositions: 3,
      krAllocation: 50,
      usAllocation: 50,
    }),
    {
      user_id: 'user-1',
      exchange_type: 'toss',
      allocated_capital: 5000000,
      risk_preset: 'neutral',
      asset_scope: 'ALL',
      max_open_positions: 3,
      kr_allocation_pct: 50,
      us_allocation_pct: 50,
    },
  )
})

test('시장 배분이 잘못되면 토스 자동선별 저장값을 만들지 않는다', () => {
  assert.equal(
    buildTossStockSelectionPayload({
      userId: 'user-1',
      capital: 5000000,
      riskPreset: 'neutral',
      assetScope: 'ALL',
      maxOpenPositions: 3,
      krAllocation: 70,
      usAllocation: 20,
    }),
    null,
  )
})

test('코인과 토스를 함께 저장해도 모든 행에 asset_scope 기본값을 보낸다', () => {
  const payloads = buildAiFundConfigPayloads({
    exchanges: ['coinone', 'toss'],
    userId: 'user-1',
    capital: 5000000,
    riskPreset: 'neutral',
    isActive: true,
    tossSelection: buildTossStockSelectionPayload({
      userId: 'user-1', capital: 5000000, riskPreset: 'neutral', assetScope: 'ALL', maxOpenPositions: 3, krAllocation: 50, usAllocation: 50,
    }),
  })

  assert.deepEqual(payloads.map((payload) => payload.asset_scope), ['ALL', 'ALL'])
  assert.deepEqual(payloads.map((payload) => payload.max_open_positions), [3, 3])
})

test('사용자 지정 리스크 값은 프리셋 대신 모든 거래소 설정에 그대로 저장한다', () => {
  const payloads = buildAiFundConfigPayloads({
    exchanges: ['coinone', 'binance'],
    userId: 'user-1',
    capital: 5000000,
    riskPreset: 'custom',
    riskSettings: {
      takeProfitPct: 6.5,
      stopLossPct: -3.5,
      minSignalConfidence: 0.72,
      positionSizePct: 12,
      dailyMddLimitPct: -4,
    },
    isActive: true,
    tossSelection: null,
  })

  assert.deepEqual(payloads.map((payload) => payload.max_position_size), [600000, 600000])
  assert.deepEqual(payloads.map((payload) => payload.target_take_profit_pct), [6.5, 6.5])
  assert.deepEqual(payloads.map((payload) => payload.stop_loss_pct), [-3.5, -3.5])
  assert.deepEqual(payloads.map((payload) => payload.min_signal_confidence), [0.72, 0.72])
  assert.deepEqual(payloads.map((payload) => payload.daily_mdd_limit_pct), [-4, -4])
})

test('AI 위탁 대시보드 저장값은 항상 실거래 모드로 설정한다', () => {
  const payloads = buildAiFundConfigPayloads({
    exchanges: ['coinone', 'toss'],
    userId: 'user-1',
    capital: 50000,
    riskPreset: 'neutral',
    riskSettings: { positionSizePct: 10 },
    isActive: false,
    tossSelection: buildTossStockSelectionPayload({
      userId: 'user-1', capital: 50000, riskPreset: 'neutral', assetScope: 'ALL', maxOpenPositions: 3, krAllocation: 50, usAllocation: 50,
    }),
  })

  assert.deepEqual(payloads.map((payload) => payload.operation_mode), ['LIVE', 'LIVE'])
  assert.deepEqual(payloads.map((payload) => payload.canary_max_order_amount), [null, null])
})

test('운용 중에는 AI 위탁 설정을 변경할 수 없다', () => {
  assert.equal(canEditAiFundSettings(true), false)
  assert.equal(canEditAiFundSettings(false), true)
})

test('운용 제어 버튼은 명시적인 불리언 상태만 전달한다', () => {
  assert.equal(getNextAiFundActiveState(false), true)
  assert.equal(getNextAiFundActiveState(true), false)
})
