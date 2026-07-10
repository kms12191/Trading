export function resolveWatchlistDisplayCurrency({
  assetType,
  selectedCurrency,
  cryptoChartMode,
}) {
  const normalizedAssetType = String(assetType || '').toUpperCase()
  const normalizedSelectedCurrency = String(selectedCurrency || 'KRW').toUpperCase()
  const normalizedCryptoChartMode = String(cryptoChartMode || 'KRW').toUpperCase()

  if (normalizedAssetType === 'CRYPTO') {
    return normalizedCryptoChartMode === 'KRW' ? 'KRW' : 'USD'
  }

  if (normalizedSelectedCurrency === 'USD' || normalizedSelectedCurrency === 'USDT') {
    return 'USD'
  }

  return 'KRW'
}
