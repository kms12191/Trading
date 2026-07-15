import assert from 'node:assert/strict'
import test from 'node:test'

import {
  buildSettingsSavePayloads,
  buildSettingsTestPayload,
  createInitialKeyStatus,
  formatApiErrorForSettings,
  normalizeKeysStatus,
  validateNickname,
} from './settingsModel.js'

test('설정 화면 기본 키 상태와 서버 상태를 화면용으로 정규화한다', () => {
  assert.deepEqual(createInitialKeyStatus().KIS_MOCK, { registered: false })
  assert.deepEqual(createInitialKeyStatus().BINANCE_REAL, { registered: false })

  const normalized = normalizeKeysStatus({
    TOSS: { registered: true },
    KIS: {
      registered: true,
      accounts: [
        { broker_env: 'MOCK', access_key: 'mock-key' },
        { broker_env: 'REAL', access_key: 'real-key' },
      ],
    },
    BINANCE: {
      registered: true,
      accounts: [
        { broker_env: 'TESTNET', access_key: 'testnet-key' },
        { broker_env: 'REAL', access_key: 'binance-real-key' },
      ],
    },
  })

  assert.equal(normalized.KIS_MOCK.access_key, 'mock-key')
  assert.equal(normalized.KIS_REAL.access_key, 'real-key')
  assert.equal(normalized.BINANCE_MOCK.access_key, 'testnet-key')
  assert.equal(normalized.BINANCE_REAL.access_key, 'binance-real-key')
})

test('닉네임 저장 전 길이와 허용 문자를 검증한다', () => {
  assert.deepEqual(validateNickname(' 강산_123 '), { ok: true, nickname: '강산_123' })
  assert.deepEqual(validateNickname('a'), {
    ok: false,
    message: '닉네임은 2자 이상 16자 이하로 입력해 주세요.',
  })
  assert.deepEqual(validateNickname('bad-name!'), {
    ok: false,
    message: '닉네임은 한글, 영문, 숫자, 밑줄만 사용할 수 있습니다.',
  })
})

test('거래소별 연결 테스트 payload를 생성한다', () => {
  const forms = {
    tossForm: { client_id: 'tid', client_secret: 'tsec', toss_account_seq: 'seq', broker_env: 'REAL' },
    kisMockForm: { appkey: 'mk', appsecret: 'ms', cano: '123', acnt_prdt_cd: '01', broker_env: 'MOCK' },
    kisRealForm: { appkey: 'rk', appsecret: 'rs', cano: '456', acnt_prdt_cd: '01', broker_env: 'REAL' },
    coinoneForm: { access_token: 'ca', secret_key: 'cs', broker_env: 'REAL' },
    binanceForm: { api_key: 'ba', secret_key: 'bs', broker_env: 'MOCK' },
    kisSubTab: 'REAL',
  }

  assert.deepEqual(buildSettingsTestPayload('KIS', forms), {
    exchange: 'KIS',
    appkey: 'rk',
    appsecret: 'rs',
    cano: '456',
    acnt_prdt_cd: '01',
    broker_env: 'REAL',
  })
  assert.equal(buildSettingsTestPayload('BINANCE', forms).api_key, 'ba')
})

test('저장 payload와 검증 payload를 함께 생성하고 필수값 누락을 반환한다', () => {
  const tossResult = buildSettingsSavePayloads('TOSS', {
    tossForm: {
      client_id: 'tid',
      client_secret: 'tsec',
      toss_account_seq: 'seq',
      toss_account_no: '001',
      broker_env: 'REAL',
    },
  })

  assert.equal(tossResult.ok, true)
  assert.equal(tossResult.payload.toss_account_no, '001')
  assert.equal(tossResult.testPayload.toss_account_seq, 'seq')
  assert.equal(tossResult.testPayload.toss_account_no, undefined)

  const failed = buildSettingsSavePayloads('COINONE', {
    coinoneForm: { access_token: '', secret_key: '', broker_env: 'REAL' },
  })
  assert.deepEqual(failed, {
    ok: false,
    message: 'Coinone Access Token과 Secret Key를 모두 입력해 주세요.',
  })
})

test('설정 화면 API 에러 문구를 제목과 상세로 합친다', () => {
  assert.equal(formatApiErrorForSettings({ title: '저장 실패', detail: '키를 확인해 주세요.' }), '저장 실패 키를 확인해 주세요.')
  assert.equal(formatApiErrorForSettings({ title: '저장 실패' }), '저장 실패')
})
