export const TRADE_HISTORY_SELECT_FIELDS = 'id,exchange,asset_type,ticker,symbol,side,price,volume,order_amount,ord_type,market_country,currency,broker_env,client_order_id,external_order_id,external_order_org_no,status,failure_reason,created_at'
export const BROKER_HISTORY_SELECT_FIELDS = 'id,exchange,broker_env,symbol,market_country,side,price,quantity,order_amount,status,raw_status,currency,client_order_id,external_order_id,filled_quantity,average_filled_price,filled_amount,commission,tax,ordered_at,filled_at,settlement_date'
export const AI_FUND_ORDER_SELECT_FIELDS = 'id,exchange_type,symbol,side,status,requested_qty,requested_price,filled_qty,average_fill_price,fee_amount,client_order_id,exchange_order_id,created_at'
export const TRADE_EXCHANGE_OPTIONS = ['ALL', 'TOSS', 'KIS', 'COINONE', 'BINANCE', 'BINANCE_UM_FUTURES']
export const TRADE_EXCHANGE_LABELS = {
  ALL: '전체',
  TOSS: '토스증권',
  KIS: '한국투자증권',
  COINONE: '코인원',
  BINANCE: '바이낸스 현물',
  BINANCE_UM_FUTURES: '바이낸스 선물',
}
export const TRADE_SIDE_OPTIONS = ['ALL', '매수', '매도', '출금', '입금']
export const TRADE_STATUS_OPTIONS = ['ALL', '승인대기', '주문접수', '미체결', '부분체결', '정정접수', '체결완료', '취소완료', '주문실패', '전송중', '출금완료', '입금완료', '출금실패']

const DELETABLE_TRADE_STATUSES = new Set(['주문실패', '취소완료', '출금실패'])
const DELETABLE_SOURCE_TYPES = new Set(['APP', 'TRANSFER'])

export const formatNumber = (value, options = {}) => {
  const numericValue = Number(value)
  if (!Number.isFinite(numericValue)) return '-'
  return numericValue.toLocaleString('ko-KR', options)
}

export const formatCurrency = (value, currency = 'KRW') => {
  const numericValue = Number(value)
  if (!Number.isFinite(numericValue)) return '-'
  const prefix = currency === 'USD' ? '$' : '₩'
  return `${prefix}${formatNumber(numericValue, {
    minimumFractionDigits: currency === 'USD' ? 2 : 0,
    maximumFractionDigits: currency === 'USD' ? 2 : 0,
  })}`
}

export const formatUnitCurrency = (value, currency = 'KRW') => {
  const numericValue = Number(value)
  if (!Number.isFinite(numericValue)) return '-'
  const prefix = currency === 'USD' ? '$' : '₩'
  return `${prefix}${formatNumber(numericValue, {
    minimumFractionDigits: 0,
    maximumFractionDigits: 1,
  })}`
}

export const isActionableOrderStatus = (status) => (
  ['APPROVED', 'ORDERED', 'OPEN', 'PARTIALLY_FILLED', 'MODIFIED'].includes(String(status || '').toUpperCase())
)

export const mapTradeStatus = (status) => {
  const normalizedStatus = String(status || '').toUpperCase()
  if (normalizedStatus === 'PENDING') return '승인대기'
  if (['APPROVED', 'ORDERED'].includes(normalizedStatus)) return '주문접수'
  if (normalizedStatus === 'OPEN') return '미체결'
  if (normalizedStatus === 'PARTIALLY_FILLED') return '부분체결'
  if (normalizedStatus === 'MODIFIED') return '정정접수'
  if (normalizedStatus === 'EXECUTED') return '체결완료'
  if (['FAILED', 'REJECTED', 'EXPIRED'].includes(normalizedStatus)) return '주문실패'
  if (['CANCELED', 'CANCELLED'].includes(normalizedStatus)) return '취소완료'
  return normalizedStatus || '-'
}

export const mapTradeSide = (side) => (String(side || '').toUpperCase() === 'SELL' ? '매도' : '매수')

export const isMissingBrokerHistoryTableError = (error) => {
  const message = String(error?.message || error?.details || error?.hint || '').toLowerCase()
  return message.includes('broker_order_history') && (
    message.includes('not found')
    || message.includes('does not exist')
    || message.includes('could not find')
    || message.includes('pgrst')
  )
}

export const isCancelReplaceExchange = (exchange) => ['COINONE', 'BINANCE', 'BINANCE_UM_FUTURES'].includes(String(exchange || '').toUpperCase())

export const isDeletableTradeHistoryItem = (trade) => (
  DELETABLE_SOURCE_TYPES.has(trade?.sourceType)
  && DELETABLE_TRADE_STATUSES.has(trade?.status)
)

const normalizeOrderIdentityPart = (value) => String(value || '').trim()

export const getOrderIdentityKeys = (row = {}) => {
  const exchange = normalizeOrderIdentityPart(row.exchange).toUpperCase()
  const brokerEnv = normalizeOrderIdentityPart(row.broker_env || row.brokerEnv || 'REAL').toUpperCase()
  if (!exchange || !brokerEnv) return []

  return [
    ['external', row.external_order_id],
    ['client', row.client_order_id],
  ]
    .map(([type, value]) => [type, normalizeOrderIdentityPart(value)])
    .filter(([, value]) => value)
    .map(([type, value]) => `${exchange}|${brokerEnv}|${type}|${value}`)
}

export const buildBrokerOrderLookup = (proposals = [], brokerOrders = []) => {
  const proposalOrderKeys = new Set(proposals.flatMap(getOrderIdentityKeys))
  const brokerByKey = new Map()
  const linkedBrokerOrderIds = new Set()

  brokerOrders.forEach((order) => {
    const orderKeys = getOrderIdentityKeys(order)
    orderKeys.forEach((key) => {
      if (!brokerByKey.has(key)) {
        brokerByKey.set(key, order)
      }
    })
    if (orderKeys.some((key) => proposalOrderKeys.has(key))) {
      linkedBrokerOrderIds.add(String(order.id))
    }
  })

  return { brokerByKey, linkedBrokerOrderIds }
}

export const findLinkedBrokerOrder = (proposal, brokerOrderLookup) => {
  if (!brokerOrderLookup?.brokerByKey) return null
  for (const key of getOrderIdentityKeys(proposal)) {
    const brokerOrder = brokerOrderLookup.brokerByKey.get(key)
    if (brokerOrder) return brokerOrder
  }
  return null
}

export const filterUnlinkedBrokerOrders = (brokerOrders = [], brokerOrderLookup) => (
  brokerOrders.filter((order) => !brokerOrderLookup?.linkedBrokerOrderIds?.has(String(order.id)))
)

export const formatCryptoAmount = (value, symbol = '') => {
  const numericValue = Number(value)
  if (!Number.isFinite(numericValue)) return '-'
  const suffix = symbol ? ` ${String(symbol).toUpperCase()}` : ''
  return `${formatNumber(numericValue, { maximumFractionDigits: 8 })}${suffix}`
}

export const formatSignedCryptoAmount = (value, symbol = '') => {
  const numericValue = Number(value)
  if (!Number.isFinite(numericValue)) return '-'
  const sign = numericValue > 0 ? '+' : ''
  return `${sign}${formatCryptoAmount(numericValue, symbol)}`
}

export const getTransferDateParts = (value) => {
  const parsed = value ? new Date(value) : null
  const isValidDate = parsed && !Number.isNaN(parsed.getTime())
  return {
    date: isValidDate ? parsed.toISOString().slice(0, 10) : '-',
    time: isValidDate
      ? parsed.toLocaleTimeString('ko-KR', {
        hour12: false,
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit',
      })
      : '-',
  }
}

export const getTransferFee = (row = {}) => (
  Number(row.withdraw_fee ?? row.precheck_payload?.withdrawal_fee ?? 0)
)

export const getTransferReceivedAmount = (row = {}) => {
  const receivedAmount = Number(row.received_amount)
  if (Number.isFinite(receivedAmount) && receivedAmount > 0) return receivedAmount
  const depositAmount = Number(row.binance_deposit_payload?.amount)
  if (Number.isFinite(depositAmount) && depositAmount > 0) return depositAmount
  const expectedAmount = Number(row.expected_receive_amount ?? row.precheck_payload?.estimated_receive_amount)
  if (Number.isFinite(expectedAmount) && expectedAmount > 0) return expectedAmount
  return 0
}

export const mapTransferStatus = (status, type) => {
  const normalizedStatus = String(status || '').toUpperCase()
  if (normalizedStatus === 'COMPLETED') return type === 'DEPOSIT' ? '입금완료' : '출금완료'
  if (['FAILED', 'NEEDS_REVIEW', 'REJECTED'].includes(normalizedStatus)) return '출금실패'
  if (['APPROVED', 'SUBMITTED', 'WITHDRAWAL_REGISTER', 'WITHDRAWAL_WAIT', 'PENDING'].includes(normalizedStatus)) return '전송중'
  return normalizedStatus || '-'
}

export const mapProposalToTrade = (proposal, brokerOrderLookup) => {
  const linkedBrokerOrder = findLinkedBrokerOrder(proposal, brokerOrderLookup)
  const createdAt = proposal.created_at ? new Date(proposal.created_at) : null
  const isValidDate = createdAt && !Number.isNaN(createdAt.getTime())
  const date = isValidDate ? createdAt.toISOString().slice(0, 10) : '-'
  const time = isValidDate
    ? createdAt.toLocaleTimeString('ko-KR', {
      hour12: false,
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
    })
    : '-'
  const currency = proposal.currency || (proposal.exchange === 'BINANCE' ? 'USD' : 'KRW')
  const price = proposal.price ?? null
  const quantity = proposal.volume ?? null
  const computedAmount = proposal.order_amount ?? (
    price !== null && quantity !== null ? Number(price) * Number(quantity) : null
  )
  const ticker = proposal.symbol || proposal.ticker || '-'
  const displayName = proposal.display_name || ticker
  const rawStatus = linkedBrokerOrder?.status || linkedBrokerOrder?.raw_status || proposal.status
  const orderNumber = proposal.external_order_id
    || linkedBrokerOrder?.external_order_id
    || proposal.client_order_id
    || linkedBrokerOrder?.client_order_id
    || proposal.id
  const hasLinkedBrokerOrder = Boolean(linkedBrokerOrder)

  return {
    id: proposal.id,
    deleteTargetId: proposal.id,
    sourceType: 'APP',
    sourceLabel: 'AE 거래',
    sourceDescription: hasLinkedBrokerOrder
      ? 'AE에서 생성·승인한 주문이며 토스 원장과 연결됨'
      : 'AE에서 생성·승인한 앱 주문',
    rawStatus,
    isActionable: isActionableOrderStatus(rawStatus) && Boolean(proposal.external_order_id || linkedBrokerOrder?.external_order_id),
    brokerEnv: proposal.broker_env || 'REAL',
    orderOrgNo: proposal.external_order_org_no || '',
    marketCountry: proposal.market_country || '',
    rawPrice: price,
    rawQuantity: quantity,
    date,
    time,
    exchange: proposal.exchange || '-',
    symbolName: displayName,
    ticker,
    assetType: proposal.asset_type || (['COINONE', 'BINANCE'].includes(proposal.exchange) ? 'CRYPTO' : 'STOCK'),
    side: mapTradeSide(proposal.side),
    currency,
    price: price === null ? '-' : formatUnitCurrency(price, currency),
    quantity: quantity === null ? '-' : formatNumber(quantity, { maximumFractionDigits: 8 }),
    amount: computedAmount === null ? '-' : formatCurrency(computedAmount, currency),
    status: mapTradeStatus(rawStatus),
    exchangeRate: '-',
    fees: linkedBrokerOrder && (linkedBrokerOrder.commission || linkedBrokerOrder.tax)
      ? formatCurrency((Number(linkedBrokerOrder.commission || 0) + Number(linkedBrokerOrder.tax || 0)), currency)
      : '-',
    orderNumber,
  }
}

export const mapBrokerHistoryToTrade = (order, symbolNameMap = {}) => {
  const orderedAt = order.ordered_at ? new Date(order.ordered_at) : null
  const isValidDate = orderedAt && !Number.isNaN(orderedAt.getTime())
  const date = isValidDate ? orderedAt.toISOString().slice(0, 10) : '-'
  const time = isValidDate
    ? orderedAt.toLocaleTimeString('ko-KR', {
      hour12: false,
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
    })
    : '-'
  const symbol = String(order.symbol || '-').trim().toUpperCase()
  const displayName = symbolNameMap[symbol] || symbol || '-'
  const currency = order.currency || (order.market_country === 'US' ? 'USD' : 'KRW')
  const rawPrice = order.average_filled_price ?? order.price ?? null
  const rawQuantity = order.filled_quantity ?? order.quantity ?? null
  const computedAmount = order.filled_amount ?? order.order_amount ?? (
    rawPrice !== null && rawQuantity !== null ? Number(rawPrice) * Number(rawQuantity) : null
  )
  const normalizedStatus = String(order.status || order.raw_status || '').toUpperCase()

  return {
    id: `broker-${order.id}`,
    sourceType: 'BROKER',
    sourceLabel: '토스 앱/브로커',
    sourceDescription: '거래소 앱 또는 브로커 원장에서 불러온 주문',
    rawStatus: normalizedStatus,
    isActionable: false,
    brokerEnv: order.broker_env || 'REAL',
    orderOrgNo: '',
    marketCountry: order.market_country || '',
    rawPrice,
    rawQuantity,
    date,
    time,
    exchange: order.exchange || '-',
    symbolName: displayName,
    ticker: symbol,
    assetType: order.asset_type || (['COINONE', 'BINANCE'].includes(order.exchange) ? 'CRYPTO' : 'STOCK'),
    side: mapTradeSide(order.side),
    currency,
    price: rawPrice === null ? '-' : formatUnitCurrency(rawPrice, currency),
    quantity: rawQuantity === null ? '-' : formatNumber(rawQuantity, { maximumFractionDigits: 8 }),
    amount: computedAmount === null ? '-' : formatCurrency(computedAmount, currency),
    status: mapTradeStatus(normalizedStatus),
    exchangeRate: '-',
    fees: (order.commission || order.tax)
      ? formatCurrency((Number(order.commission || 0) + Number(order.tax || 0)), currency)
      : '-',
    orderNumber: order.external_order_id || order.client_order_id || order.id,
  }
}

export const mapAiFundOrderToTrade = (order = {}) => {
  const createdAt = order.created_at ? new Date(order.created_at) : null
  const isValidDate = createdAt && !Number.isNaN(createdAt.getTime())
  const date = isValidDate ? createdAt.toISOString().slice(0, 10) : '-'
  const time = isValidDate
    ? createdAt.toLocaleTimeString('ko-KR', { hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit' })
    : '-'
  const rawStatus = String(order.status || '').toUpperCase()
  const rawPrice = order.average_fill_price ?? order.requested_price ?? null
  const rawQuantity = order.filled_qty > 0 ? order.filled_qty : order.requested_qty ?? null
  const amount = rawPrice !== null && rawQuantity !== null ? Number(rawPrice) * Number(rawQuantity) : null
  const ticker = String(order.symbol || '-').toUpperCase()

  return {
    id: `ai-fund-${order.id}`,
    sourceType: 'AI_FUND',
    sourceLabel: 'AI 위탁운용',
    sourceDescription: 'AI 위탁운용 엔진이 거래소에 제출하고 대사한 주문',
    rawStatus: rawStatus,
    isActionable: false,
    brokerEnv: 'REAL',
    orderOrgNo: '',
    marketCountry: '',
    rawPrice,
    rawQuantity,
    date,
    time,
    exchange: String(order.exchange_type || '-').toUpperCase(),
    symbolName: ticker,
    ticker,
    assetType: 'CRYPTO',
    side: mapTradeSide(order.side),
    currency: 'KRW',
    price: rawPrice === null ? '-' : formatUnitCurrency(rawPrice, 'KRW'),
    quantity: rawQuantity === null ? '-' : formatNumber(rawQuantity, { maximumFractionDigits: 8 }),
    amount: amount === null ? '-' : formatCurrency(amount, 'KRW'),
    status: rawStatus === 'FILLED' ? '체결완료' : mapTradeStatus(rawStatus),
    exchangeRate: '-',
    fees: Number(order.fee_amount || 0) > 0 ? formatCurrency(order.fee_amount, 'KRW') : '-',
    orderNumber: order.exchange_order_id || order.client_order_id || order.id,
  }
}

export const mapTransferToTrades = (transfer) => {
  const currency = String(transfer.currency || '').toUpperCase()
  const fee = getTransferFee(transfer)
  const feeCurrency = transfer.fee_currency || currency
  const withdrawParts = getTransferDateParts(transfer.submitted_at || transfer.created_at)
  const depositParts = getTransferDateParts(transfer.completed_at || transfer.updated_at || transfer.created_at)
  const fromExchange = transfer.from_exchange || 'COINONE'
  const toExchange = transfer.to_exchange || 'BINANCE'
  const amount = Number(transfer.amount)
  const receivedAmount = getTransferReceivedAmount(transfer)
  const feeText = fee > 0 ? `수수료 ${formatCryptoAmount(fee, feeCurrency)}` : '-'
  const rows = [
    {
      id: `transfer-withdraw-${transfer.id}`,
      deleteTargetId: transfer.id,
      sourceType: 'TRANSFER',
      sourceLabel: 'AE 자산이동',
      sourceDescription: 'AE에서 요청한 자산 이동',
      rawStatus: transfer.status,
      isActionable: false,
      brokerEnv: 'REAL',
      orderOrgNo: '',
      marketCountry: '',
      rawPrice: null,
      rawQuantity: Number.isFinite(amount) ? -amount : null,
      date: withdrawParts.date,
      time: withdrawParts.time,
      exchange: fromExchange,
      symbolName: `${currency} 출금`,
      ticker: currency,
      side: '출금',
      currency,
      price: '-',
      quantity: Number.isFinite(amount) ? formatCryptoAmount(-amount, currency) : '-',
      amount: feeText,
      status: mapTransferStatus(transfer.status, 'WITHDRAW'),
      exchangeRate: '-',
      fees: fee > 0 ? formatCryptoAmount(fee, feeCurrency) : '-',
      orderNumber: transfer.external_transaction_id || transfer.id,
    },
  ]

  if (String(transfer.status || '').toUpperCase() === 'COMPLETED' && receivedAmount > 0) {
    rows.push({
      id: `transfer-deposit-${transfer.id}`,
      deleteTargetId: transfer.id,
      sourceType: 'TRANSFER',
      sourceLabel: 'AE 자산이동',
      sourceDescription: 'AE에서 요청한 자산 이동',
      rawStatus: transfer.status,
      isActionable: false,
      brokerEnv: 'REAL',
      orderOrgNo: '',
      marketCountry: '',
      rawPrice: null,
      rawQuantity: receivedAmount,
      date: depositParts.date,
      time: depositParts.time,
      exchange: toExchange,
      symbolName: `${currency} 입금`,
      ticker: currency,
      side: '입금',
      currency,
      price: '-',
      quantity: formatSignedCryptoAmount(receivedAmount, currency),
      amount: '-',
      status: mapTransferStatus(transfer.status, 'DEPOSIT'),
      exchangeRate: '-',
      fees: '-',
      orderNumber: transfer.external_transaction_id || transfer.id,
    })
  }

  return rows
}

export const sortTradeHistoryRows = (rows = []) => (
  [...rows].sort((a, b) => {
    const left = new Date(`${a.date}T${a.time === '-' ? '00:00:00' : a.time}`).getTime()
    const right = new Date(`${b.date}T${b.time === '-' ? '00:00:00' : b.time}`).getTime()
    return right - left
  })
)
