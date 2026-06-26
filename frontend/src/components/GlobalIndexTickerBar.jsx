import { useEffect, useState } from 'react'

const INDEX_ENDPOINT = 'http://localhost:5050/api/market/indices'
const REFRESH_INTERVAL_MS = 60000
const ALLOWED_INDEX_KEYS = ['USDKRW', 'KOSPI', 'KOSDAQ', 'NASDAQ100_F', 'SP500']
const INDEX_LABELS = {
  USDKRW: 'USD/KRW',
  KOSPI: 'KOSPI',
  KOSDAQ: 'KOSDAQ',
  NASDAQ100_F: 'NASDAQ 100',
  SP500: 'S&P 500',
}

function formatValue(value, currency) {
  const numeric = Number(value)
  if (!Number.isFinite(numeric)) return '-'

  let minimumFractionDigits = 2

  if (currency === 'KRW' && numeric >= 100) {
    minimumFractionDigits = 0
  }

  if (currency === 'KRW' && numeric < 2000) {
    minimumFractionDigits = 2
  }

  return numeric.toLocaleString('ko-KR', {
    minimumFractionDigits,
    maximumFractionDigits: minimumFractionDigits,
  })
}

function formatDelta(value) {
  const numeric = Number(value)
  if (!Number.isFinite(numeric)) return '-'
  const prefix = numeric > 0 ? '+' : ''
  return `${prefix}${numeric.toLocaleString('ko-KR', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })}`
}

function formatPercent(value) {
  const numeric = Number(value)
  if (!Number.isFinite(numeric)) return '-'
  const prefix = numeric > 0 ? '+' : ''
  return `${prefix}${numeric.toFixed(2)}%`
}

function changeClass(direction) {
  if (direction === 'up') return 'text-rose-400'
  if (direction === 'down') return 'text-sky-400'
  return 'text-slate-400'
}

function getDisplayItems(items) {
  const byKey = new Map(items.map((item) => [item.key, item]))

  // We only surface the KIS-backed feeds that are wired into the market index store.
  return ALLOWED_INDEX_KEYS
    .map((key) => {
      const item = byKey.get(key)
      if (!item) return null
      return {
        ...item,
        label: INDEX_LABELS[key] || item.label || key,
      }
    })
    .filter(Boolean)
}

export default function GlobalIndexTickerBar() {
  const [items, setItems] = useState([])
  const [errorMessage, setErrorMessage] = useState('')

  useEffect(() => {
    let disposed = false

    const loadIndices = async () => {
      try {
        const response = await fetch(INDEX_ENDPOINT)
        const payload = await response.json()

        if (!response.ok || !payload.success) {
          throw new Error(payload.message || '지수 데이터를 불러오지 못했습니다.')
        }

        if (!disposed) {
          const nextItems = Array.isArray(payload.data?.items) ? payload.data.items : []
          setItems(getDisplayItems(nextItems))
          setErrorMessage('')
        }
      } catch (error) {
        if (!disposed) {
          setErrorMessage(error.message || '지수 데이터를 불러오지 못했습니다.')
        }
      }
    }

    loadIndices()
    const intervalId = window.setInterval(loadIndices, REFRESH_INTERVAL_MS)

    return () => {
      disposed = true
      window.clearInterval(intervalId)
    }
  }, [])

  if (!items.length && !errorMessage) {
    return null
  }

  return (
    <div className="fixed inset-x-0 bottom-0 z-30 border-t border-[#1f2945] bg-[#07101d]/92 text-slate-100 shadow-[0_-10px_30px_rgba(2,6,23,0.45)] backdrop-blur-xl">
      <div className="mx-auto flex w-full max-w-[1600px] items-center gap-3 overflow-x-auto px-4 py-3 sm:px-6">
        <div className="shrink-0 rounded-full border border-cyan-900/60 bg-cyan-950/30 px-3 py-1 text-[10px] font-bold uppercase tracking-[0.24em] text-cyan-300">
          Market
        </div>

        <div className="flex min-w-max items-center gap-2">
          {items.map((item) => (
            <div
              key={item.key}
              className="flex shrink-0 items-center gap-3 rounded-lg border border-[#1f2945] bg-[#0b1628]/95 px-3 py-2 text-sm"
            >
              <div className="flex flex-col">
                <span className="whitespace-nowrap text-[10px] font-bold uppercase tracking-[0.18em] text-slate-500">
                  {item.label}
                </span>
                <span className="whitespace-nowrap font-semibold text-slate-100">
                  {formatValue(item.value, item.currency)}
                </span>
              </div>
              <span className={`whitespace-nowrap text-xs font-bold ${changeClass(item.direction)}`}>
                {formatDelta(item.change)} ({formatPercent(item.changePercent)})
              </span>
            </div>
          ))}
        </div>

        {errorMessage && (
          <div className="ml-auto shrink-0 whitespace-nowrap rounded border border-amber-900/60 bg-amber-950/30 px-2 py-1 text-[11px] text-amber-300">
            {errorMessage}
          </div>
        )}
      </div>
    </div>
  )
}
