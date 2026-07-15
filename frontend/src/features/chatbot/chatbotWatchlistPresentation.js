function normalizeText(value, fallback = '-') {
  const text = String(value || '').trim()
  return text || fallback
}

export function buildWatchlistPresentation(toolResult) {
  const source = String(toolResult?.source || '').toUpperCase()
  const view = String(toolResult?.view || '').toLowerCase()
  const rows = Array.isArray(toolResult?.items) ? toolResult.items : []
  if (source !== 'USER_WATCHLIST' || view === 'focus' || rows.length === 0) {
    return { shouldRender: false, count: 0, items: [] }
  }

  const items = rows.map((row) => ({
    name: normalizeText(row?.name || row?.symbol || row?.content),
    symbol: normalizeText(row?.symbol),
    assetType: normalizeText(row?.asset_type || row?.assetType),
    exchange: normalizeText(row?.exchange),
  }))

  return {
    shouldRender: items.length > 0,
    title: '\uad00\uc2ec\uc885\ubaa9',
    count: items.length,
    items,
  }
}
