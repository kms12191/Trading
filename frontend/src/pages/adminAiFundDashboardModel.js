export function buildTossStockSelectionPayload({
  userId,
  capital,
  riskPreset,
  assetScope,
  maxOpenPositions,
  krAllocation,
  usAllocation,
}) {
  const scope = String(assetScope || 'ALL').toUpperCase()
  const parsedCapital = Number(capital)
  const parsedMaxOpenPositions = Number(maxOpenPositions)
  const parsedKrAllocation = Number(krAllocation)
  const parsedUsAllocation = Number(usAllocation)

  if (!userId || !Number.isFinite(parsedCapital) || parsedCapital <= 0 || !['KR', 'US', 'ALL'].includes(scope) || !Number.isInteger(parsedMaxOpenPositions) || parsedMaxOpenPositions < 1 || parsedMaxOpenPositions > 20) {
    return null
  }
  if (scope === 'ALL' && (!Number.isFinite(parsedKrAllocation) || !Number.isFinite(parsedUsAllocation) || parsedKrAllocation < 0 || parsedUsAllocation < 0 || Math.abs(parsedKrAllocation + parsedUsAllocation - 100) > 0.001)) {
    return null
  }

  return {
    user_id: userId,
    exchange_type: 'toss',
    allocated_capital: parsedCapital,
    risk_preset: riskPreset,
    asset_scope: scope,
    max_open_positions: parsedMaxOpenPositions,
    kr_allocation_pct: scope === 'US' ? 0 : scope === 'KR' ? 100 : parsedKrAllocation,
    us_allocation_pct: scope === 'KR' ? 0 : scope === 'US' ? 100 : parsedUsAllocation,
  }
}

export function buildAiFundConfigPayloads({
  exchanges,
  userId,
  capital,
  riskPreset,
  riskSettings,
  isActive,
  tossSelection,
}) {
  const presetSettings = riskPreset === 'conservative'
    ? { takeProfitPct: 3, stopLossPct: -1, minSignalConfidence: 0.85, positionSizePct: 5, dailyMddLimitPct: -1 }
    : riskPreset === 'aggressive'
      ? { takeProfitPct: 8, stopLossPct: -4, minSignalConfidence: 0.65, positionSizePct: 20, dailyMddLimitPct: -4 }
      : { takeProfitPct: 5, stopLossPct: -2, minSignalConfidence: 0.75, positionSizePct: 10, dailyMddLimitPct: -2 }
  const settings = { ...presetSettings, ...(riskSettings || {}) }
  const maxPositionSize = Number(capital) * (Number(settings.positionSizePct) / 100)
  const stockDefaults = {
    asset_scope: 'ALL',
    max_open_positions: 3,
    kr_allocation_pct: 50,
    us_allocation_pct: 50,
    selection_refresh_minutes: 60,
  }

  return exchanges.map((exchangeType) => ({
    user_id: userId,
    exchange_type: exchangeType,
    allocated_capital: Number(capital),
    max_position_size: maxPositionSize,
    risk_preset: riskPreset,
    min_signal_confidence: Number(settings.minSignalConfidence),
    target_take_profit_pct: Number(settings.takeProfitPct),
    stop_loss_pct: Number(settings.stopLossPct),
    daily_mdd_limit_pct: Number(settings.dailyMddLimitPct),
    operation_mode: 'LIVE',
    canary_max_order_amount: null,
    is_active: isActive,
    ...stockDefaults,
    ...(exchangeType === 'toss' ? tossSelection : {}),
  }))
}

export function canEditAiFundSettings(isActive) {
  return !isActive
}

export function getNextAiFundActiveState(isActive) {
  return !isActive
}
