export const createInitialKeyStatus = () => ({
  TOSS: { registered: false },
  KIS: { registered: false },
  KIS_MOCK: { registered: false },
  KIS_REAL: { registered: false },
  COINONE: { registered: false },
  BINANCE: { registered: false },
  BINANCE_REAL: { registered: false },
  BINANCE_MOCK: { registered: false },
})

export const normalizeKeysStatus = (raw = {}) => {
  const processed = {
    ...raw,
    KIS_MOCK: { registered: false },
    KIS_REAL: { registered: false },
    BINANCE_REAL: { registered: false },
    BINANCE_MOCK: { registered: false },
  }

  raw.KIS?.accounts?.forEach((account) => {
    if (account.broker_env === 'MOCK') {
      processed.KIS_MOCK = account
    } else if (account.broker_env === 'REAL') {
      processed.KIS_REAL = account
    }
  })

  raw.BINANCE?.accounts?.forEach((account) => {
    if (['MOCK', 'DEMO', 'TESTNET'].includes(account.broker_env)) {
      processed.BINANCE_MOCK = account
    } else if (account.broker_env === 'REAL') {
      processed.BINANCE_REAL = account
    }
  })

  return processed
}

export const validateNickname = (value) => {
  const nickname = String(value || '').trim()

  if (nickname.length < 2 || nickname.length > 16) {
    return { ok: false, message: '닉네임은 2자 이상 16자 이하로 입력해 주세요.' }
  }

  if (!/^[가-힣a-zA-Z0-9_]+$/.test(nickname)) {
    return { ok: false, message: '닉네임은 한글, 영문, 숫자, 밑줄만 사용할 수 있습니다.' }
  }

  return { ok: true, nickname }
}

export const formatApiErrorForSettings = (message) => (
  message?.detail ? `${message.title} ${message.detail}` : message?.title
)

const getSelectedKisForm = ({ kisSubTab, kisMockForm, kisRealForm }) => (
  kisSubTab === 'MOCK' ? kisMockForm : kisRealForm
)

export const buildSettingsTestPayload = (exchange, forms = {}) => {
  if (exchange === 'TOSS') {
    const { tossForm = {} } = forms
    return {
      exchange,
      client_id: tossForm.client_id,
      client_secret: tossForm.client_secret,
      toss_account_seq: tossForm.toss_account_seq,
      broker_env: tossForm.broker_env,
    }
  }

  if (exchange === 'KIS') {
    const form = getSelectedKisForm(forms) || {}
    return {
      exchange,
      appkey: form.appkey,
      appsecret: form.appsecret,
      cano: form.cano,
      acnt_prdt_cd: form.acnt_prdt_cd,
      broker_env: form.broker_env,
    }
  }

  if (exchange === 'COINONE') {
    const { coinoneForm = {} } = forms
    return {
      exchange,
      access_token: coinoneForm.access_token,
      secret_key: coinoneForm.secret_key,
      broker_env: coinoneForm.broker_env,
    }
  }

  if (exchange === 'BINANCE') {
    const { binanceForm = {} } = forms
    return {
      exchange,
      api_key: binanceForm.api_key,
      secret_key: binanceForm.secret_key,
      broker_env: binanceForm.broker_env,
    }
  }

  return { exchange }
}

export const buildSettingsSavePayloads = (exchange, forms = {}) => {
  if (exchange === 'TOSS') {
    const { tossForm = {} } = forms
    if (!tossForm.client_id || !tossForm.client_secret) {
      return { ok: false, message: 'Toss Client ID와 Secret을 모두 입력해 주세요.' }
    }
    return {
      ok: true,
      payload: {
        exchange,
        client_id: tossForm.client_id,
        client_secret: tossForm.client_secret,
        toss_account_seq: tossForm.toss_account_seq,
        toss_account_no: tossForm.toss_account_no,
        broker_env: tossForm.broker_env,
      },
      testPayload: buildSettingsTestPayload(exchange, forms),
    }
  }

  if (exchange === 'KIS') {
    const form = getSelectedKisForm(forms) || {}
    const kisSubTab = forms.kisSubTab || form.broker_env || ''
    if (!form.appkey || !form.appsecret || !form.cano) {
      return { ok: false, message: `KIS ${kisSubTab} AppKey, Secret, 계좌번호를 모두 입력해 주세요.` }
    }
    return {
      ok: true,
      payload: buildSettingsTestPayload(exchange, forms),
      testPayload: buildSettingsTestPayload(exchange, forms),
    }
  }

  if (exchange === 'COINONE') {
    const { coinoneForm = {} } = forms
    if (!coinoneForm.access_token || !coinoneForm.secret_key) {
      return { ok: false, message: 'Coinone Access Token과 Secret Key를 모두 입력해 주세요.' }
    }
    return {
      ok: true,
      payload: buildSettingsTestPayload(exchange, forms),
      testPayload: buildSettingsTestPayload(exchange, forms),
    }
  }

  if (exchange === 'BINANCE') {
    const { binanceForm = {} } = forms
    if (!binanceForm.api_key || !binanceForm.secret_key) {
      return { ok: false, message: 'Binance API Key와 Secret Key를 모두 입력해 주세요.' }
    }
    return {
      ok: true,
      payload: buildSettingsTestPayload(exchange, forms),
      testPayload: buildSettingsTestPayload(exchange, forms),
    }
  }

  return {
    ok: true,
    payload: { exchange },
    testPayload: { exchange },
  }
}
