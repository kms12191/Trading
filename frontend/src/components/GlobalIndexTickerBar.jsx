import { useEffect, useState } from 'react'

const INDEX_ENDPOINT = 'http://localhost:5050/api/market/indices'
const REFRESH_INTERVAL_MS = 30000

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
          setItems(Array.isArray(payload.data?.items) ? payload.data.items : [])
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
    <div className="fixed inset-x-0 bottom-0 z-30 border-t border-slate-700/80 bg-[#f7f8fb]/95 text-slate-900 shadow-[0_-6px_24px_rgba(15,23,42,0.08)] backdrop-blur">
      <div className="mx-auto flex w-full max-w-[1600px] items-center gap-4 overflow-x-auto px-4 py-3 sm:px-6">
        <div className="shrink-0 text-[11px] font-bold uppercase tracking-[0.26em] text-slate-500">
          Indices
        </div>

        <div className="flex min-w-max items-center gap-6">
          {items.map((item) => (
            <div key={item.key} className="flex shrink-0 items-center gap-2 text-sm">
              <span className="whitespace-nowrap font-medium text-slate-600">{item.label}</span>
              <span className="whitespace-nowrap font-semibold text-slate-900">
                {formatValue(item.value, item.currency)}
              </span>
              <span className={`whitespace-nowrap font-medium ${changeClass(item.direction)}`}>
                {formatDelta(item.change)} ({formatPercent(item.changePercent)})
              </span>
            </div>
          ))}
        </div>

        {errorMessage && (
          <div className="ml-auto shrink-0 whitespace-nowrap text-xs text-amber-600">
            {errorMessage}
          </div>
        )}
      </div>
    </div>
  )
}
