import AssetLogo from '../components/AssetLogo.jsx'
import { getStockWarningBadgeTone } from './assetDetailModel.js'

export default function AssetDetailHeader({
  assetType,
  exchange,
  brokerEnv,
  overallFeedStatus,
  symbol,
  displayName,
  isUsStock,
  isFavorite,
  stockWarnings,
  showLevel2Panel,
  marketFeeds,
  feedReasonSummary,
  currentPrice,
  priceChangeRate,
  formatUnitPrice,
  onToggleFavorite,
}) {
  return (
    <div className="bg-[#0e1529]/90 border border-[#1f2945] rounded-xl p-5 mb-5 backdrop-blur-md flex flex-col md:flex-row justify-between items-start md:items-center gap-4">
      <div>
        <div className="flex items-center gap-2">
          <span className="text-[9px] font-bold text-cyan-400 bg-cyan-950/60 px-2 py-0.5 rounded border border-cyan-900/60 uppercase tracking-widest font-mono">
            {assetType} · {exchange} ({brokerEnv})
          </span>
          <span className={`text-[9px] font-bold px-2 py-0.5 rounded border uppercase tracking-widest font-mono ${overallFeedStatus.tone}`}>
            {overallFeedStatus.label}
          </span>
        </div>

        <div className="mt-1.5 flex flex-wrap items-center gap-3">
          <AssetLogo symbol={symbol} assetType={assetType} name={displayName} size="h-10 w-10" />
          <h1 className="text-xl font-bold font-mono text-white flex items-center gap-2 min-w-0">
            <span className="break-all">
              {displayName !== symbol ? `${displayName} (${symbol})` : symbol}
            </span>
            <span className="text-xs text-slate-400 font-normal shrink-0">
              ({assetType === 'STOCK' ? '주식' : '가상자산'})
            </span>
          </h1>
          {isUsStock ? (
            <span className="text-[10px] font-bold text-orange-400 bg-orange-950/40 border border-orange-900/60 px-2 py-1 rounded shrink-0">
              해외주식은 toss api만 지원합니다
            </span>
          ) : null}
          <button
            type="button"
            onClick={onToggleFavorite}
            className={`text-[22px] leading-none transition cursor-pointer focus:outline-none ${
              isFavorite ? 'text-red-400 hover:text-red-300' : 'text-slate-400 hover:text-cyan-400'
            }`}
            aria-label="즐겨찾기"
            aria-pressed={isFavorite}
          >
            {isFavorite ? '♥' : '♡'}
          </button>
          {stockWarnings.slice(0, 3).map((warning) => (
            <span
              key={`${warning.warning_type}-${warning.start_date || 'active'}`}
              className={`inline-flex items-center rounded-full border px-2.5 py-1 text-[11px] font-bold leading-none ${getStockWarningBadgeTone(warning.warning_type)}`}
              title={warning.label}
            >
              {warning.label}
            </span>
          ))}
          {stockWarnings.length > 3 ? (
            <span className="inline-flex items-center rounded-full border border-slate-600 bg-slate-800/70 px-2.5 py-1 text-[11px] font-bold leading-none text-slate-200">
              +{stockWarnings.length - 3}
            </span>
          ) : null}
        </div>

        <p className="mt-2 text-[10px] text-slate-500 font-mono">
          {showLevel2Panel
            ? `차트 ${marketFeeds.candles.source} · 호가 ${marketFeeds.orderbook.source} · 체결 ${marketFeeds.trades.source}`
            : `차트 ${marketFeeds.candles.source} · 호가/체결 비활성화`}
        </p>
        {feedReasonSummary ? (
          <p className="mt-1 text-[10px] text-amber-300/80 font-mono">
            원인 {feedReasonSummary}
          </p>
        ) : null}
      </div>

      <div className="flex flex-wrap items-center gap-x-8 gap-y-2">
        <div className="flex flex-col">
          <span className="text-[10px] text-slate-400 font-bold">현재가</span>
          <span className="text-lg font-bold font-mono text-white mt-0.5">
            {formatUnitPrice(currentPrice)}
          </span>
        </div>

        <div className="flex flex-col">
          <span className="text-[10px] text-slate-400 font-bold">전일대비</span>
          <span className={`text-sm font-bold font-mono mt-0.5 flex items-center ${priceChangeRate >= 0 ? 'text-[#ef4444]' : 'text-[#3b82f6]'}`}>
            {priceChangeRate >= 0 ? '▲' : '▼'} {Math.abs(priceChangeRate).toFixed(2)}%
          </span>
        </div>
      </div>
    </div>
  )
}
