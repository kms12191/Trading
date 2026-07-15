const INTENT_LABELS = {
  BUY: '매수',
  SELL: '매도',
  OPEN_LONG: '신규 롱',
  OPEN_SHORT: '신규 숏',
  CLOSE_POSITION: '포지션 청산',
}

export function createEmptyOrderDraft() {
  return {
    account: null,
    intent: '',
    symbol_query: '',
    selected_symbol: null,
    quantity: '',
    order_type: '',
    price: '',
    leverage: 1,
    margin_type: 'ISOLATED',
    risk_confirmed: false,
    idempotency_key: crypto.randomUUID(),
    context: null,
    precheck: null,
    precheck_token: '',
  }
}

export function invalidatePrecheck(draft, changes = {}) {
  return {
    ...draft,
    ...changes,
    precheck: null,
    precheck_token: '',
  }
}

export function isFuturesAccount(account) {
  return account?.exchange === 'BINANCE_UM_FUTURES' || account?.asset_type === 'CRYPTO_FUTURES'
}

export function isHoldingsIntent(intent) {
  return intent === 'SELL' || intent === 'CLOSE_POSITION'
}

export function getAvailableIntents(account) {
  if (!account) return []
  return isFuturesAccount(account)
    ? ['OPEN_LONG', 'OPEN_SHORT', 'CLOSE_POSITION']
    : ['BUY', 'SELL']
}

export function canAdvanceOrderStep(draft, step) {
  if (step === 1) {
    return Boolean(draft.account?.id && getAvailableIntents(draft.account).includes(draft.intent))
  }
  if (step === 2) {
    const quantity = Number(draft.quantity)
    const hasQuantity = Number.isFinite(quantity) && quantity > 0
    const hasOrderType = ['LIMIT', 'MARKET'].includes(draft.order_type)
    const price = Number(draft.price)
    const hasPrice = draft.order_type !== 'LIMIT' || (Number.isFinite(price) && price > 0)
    const hasSelectedSymbol = Boolean(draft.selected_symbol?.symbol)
    return canAdvanceOrderStep(draft, 1) && hasSelectedSymbol && hasQuantity && hasOrderType && hasPrice
  }
  return Boolean(draft.precheck?.can_create_proposal && draft.precheck_token)
}

export function getOrderEntryLabels(account, intent) {
  const assetType = account?.asset_type
  const quantity = assetType === 'STOCK'
    ? '주'
    : assetType === 'CRYPTO_FUTURES'
      ? '계약 수량'
      : '개'
  const currency = account?.currency || (assetType === 'STOCK' ? 'KRW' : 'USDT')
  return {
    quantity,
    currency,
    intent: INTENT_LABELS[intent] || '',
  }
}

export function buildPrecheckRequest(draft) {
  if (!canAdvanceOrderStep(draft, 2)) {
    throw new Error('계좌, 거래 목적, 종목, 수량과 주문 유형을 모두 확인해 주세요.')
  }
  const isFutures = isFuturesAccount(draft.account)
  return {
    account_id: draft.account.id,
    exchange: draft.account.exchange,
    asset_type: draft.account.asset_type,
    broker_env: draft.account.broker_env,
    intent: draft.intent,
    symbol: draft.selected_symbol.symbol,
    symbol_selected: true,
    ...(isFutures && draft.selected_symbol.position_side
      ? { position_side: draft.selected_symbol.position_side }
      : {}),
    quantity: Number(draft.quantity),
    order_type: draft.order_type,
    price: draft.order_type === 'LIMIT' ? Number(draft.price) : null,
    ...(isFutures
      ? {
          leverage: Number(draft.leverage),
          margin_type: draft.margin_type,
        }
      : {}),
    idempotency_key: draft.idempotency_key,
  }
}

export function applyQuantityRatio(availableQuantity, ratio) {
  const available = Number(availableQuantity)
  const normalizedRatio = Number(ratio)
  if (!Number.isFinite(available) || available <= 0 || !Number.isFinite(normalizedRatio)) return ''
  return String(available * normalizedRatio)
}
