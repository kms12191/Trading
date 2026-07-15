import { formatTimestamp } from './assetDetailModel.js'

const STOCK_INTERVALS = [
  { label: '1분', val: '1m' },
  { label: '5분', val: '5m' },
  { label: '15분', val: '15m' },
  { label: '30분', val: '30m' },
  { label: '1시간', val: '1h' },
  { label: '일봉', val: '1d' },
  { label: '주봉', val: '1w' },
  { label: '월봉', val: '1M' },
]

const CRYPTO_INTERVALS = [
  { label: '1분', val: '1m' },
  { label: '5분', val: '5m' },
  { label: '15분', val: '15m' },
  { label: '30분', val: '30m' },
  { label: '1시간', val: '1h' },
  { label: '4시간', val: '4h' },
  { label: '일봉', val: '1d' },
  { label: '주봉', val: '1w' },
  { label: '월봉', val: '1M' },
]

export default function AssetDetailChartPanel({
  assetType,
  chartInterval,
  chartCardClassName,
  chartPanelClassName,
  chartContainerRef,
  isChartExpanded,
  loadingChart,
  marketFeeds,
  onIntervalChange,
  onToggleExpanded,
  onCloseExpanded,
}) {
  const intervals = assetType === 'STOCK' ? STOCK_INTERVALS : CRYPTO_INTERVALS

  return (
    <>
      {isChartExpanded ? (
        <button
          type="button"
          aria-label="차트 크게보기 닫기"
          onClick={onCloseExpanded}
          className="fixed inset-0 z-40 bg-black/60 backdrop-blur-sm"
        />
      ) : null}
      <div className={chartCardClassName}>
        <div className="flex flex-col gap-3 sm:flex-row sm:justify-between sm:items-center">
          <div className="flex flex-col gap-1">
            <div className="flex items-center gap-2">
              <span className="w-1.5 h-3 bg-cyan-400 rounded-full" />
              <span className="text-xs font-bold text-white">
                {isChartExpanded ? '실시간 통합 차트 크게보기' : '컴팩트 차트'}
              </span>
            </div>
            <p className="text-[10px] text-slate-500 font-mono">
              마지막 차트 확인 {formatTimestamp(marketFeeds.candles.checkedAt)}
            </p>
          </div>

          <div className="flex flex-wrap items-center justify-end gap-2">
            <div className="flex flex-wrap gap-1 bg-[#1b253b] p-0.5 rounded border border-[#2b395b] justify-end">
              {intervals.map((item) => (
                <button
                  key={item.val}
                  type="button"
                  onClick={() => onIntervalChange(item.val)}
                  className={`text-[9px] sm:text-[10px] font-bold px-1.5 sm:px-2.5 py-0.5 rounded transition-all cursor-pointer ${chartInterval === item.val ? 'bg-cyan-500 text-slate-950 font-black' : 'text-slate-400 hover:text-white'}`}
                >
                  {item.label}
                </button>
              ))}
            </div>
            <button
              type="button"
              onClick={onToggleExpanded}
              className="rounded border border-cyan-500/30 px-3 py-1 text-[10px] font-black text-cyan-300 transition hover:bg-cyan-950/40"
            >
              {isChartExpanded ? '닫기' : '크게보기'}
            </button>
          </div>
        </div>

        <div className={chartPanelClassName}>
          <div className={`absolute inset-0 flex items-center justify-center bg-[#0e1529]/95 z-10 rounded transition-opacity duration-200 ${loadingChart ? 'opacity-100' : 'opacity-0 pointer-events-none hidden'}`}>
            <span className="text-xs text-cyan-400 font-mono animate-pulse">시세 차트 로드 중...</span>
          </div>
          <div ref={chartContainerRef} className="h-full w-full" />
        </div>
      </div>
    </>
  )
}
