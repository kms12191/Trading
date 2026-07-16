import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import AssetLogo from './AssetLogo.jsx'

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:5050'

// 종목 퀵 검색 공통 컴포넌트
// - 심볼/종목명 입력 + 자동완성 드롭다운 + 상세 페이지 이동 기능
// - 검색 대상은 백엔드의 종목 검색 결과에 맡기고, 사용자가 주식/코인을 직접 고르지 않게 한다.
export default function SymbolSearch({ className = '', onSearchComplete }) {
  const [query, setQuery] = useState('')
  const [suggestions, setSuggestions] = useState([])
  const [showSuggestions, setShowSuggestions] = useState(false)
  const navigate = useNavigate()

  const navigateToSearchNotFound = (searchText) => {
    const params = new URLSearchParams({
      query: searchText,
      assetType: 'ALL',
    })
    navigate(`/search/not-found?${params.toString()}`)
  }

  // 제출 시 종목 매핑 후 상세 페이지로 이동한다.
  const handleSubmit = async (e) => {
    e.preventDefault()
    const trimmed = query.trim()
    if (!trimmed) return

    try {
      const res = await fetch(
        `${API_BASE_URL}/api/symbol/lookup?query=${encodeURIComponent(trimmed)}`
      )
      const resData = await res.json()
      if (resData.success && resData.data) {
        const { symbol, asset_type } = resData.data
        navigate(`/asset/${String(asset_type || 'STOCK').toUpperCase()}/${symbol}`)
      } else {
        navigateToSearchNotFound(trimmed)
      }
    } catch {
      navigateToSearchNotFound(trimmed)
    }
    setQuery('')
    setSuggestions([])
    setShowSuggestions(false)
    onSearchComplete?.()
  }

  // 입력 변경 시 실시간 자동완성 후보를 조회한다.
  const handleInputChange = async (e) => {
    const val = e.target.value
    setQuery(val)

    if (val.trim().length > 0) {
      try {
        const res = await fetch(
          `${API_BASE_URL}/api/symbol/search?query=${encodeURIComponent(val)}`
        )
        const resData = await res.json()
        if (resData.success && resData.data) {
          setSuggestions(resData.data)
          setShowSuggestions(true)
        }
      } catch {
        // 자동완성 실패는 검색 제출 흐름을 막지 않는다.
      }
    } else {
      setSuggestions([])
      setShowSuggestions(false)
    }
  }

  // 추천 종목 클릭 시 즉시 상세 페이지로 이동한다.
  const handleSuggestionClick = (item) => {
    navigate(`/asset/${String(item.asset_type || 'STOCK').toUpperCase()}/${item.symbol}`)
    setQuery('')
    setSuggestions([])
    setShowSuggestions(false)
    onSearchComplete?.()
  }

  const getMarketLabel = (item) => {
    if (Array.isArray(item.markets) && item.markets.length > 0) {
      return item.markets.join(' · ')
    }
    return item.market || ''
  }

  return (
    <form
      onSubmit={handleSubmit}
      className={`flex items-center gap-2 ${className}`}
      autoComplete="off"
    >
      <div className="relative">
        <input
          type="text"
          value={query}
          onChange={handleInputChange}
          onFocus={() => { if (query.trim()) setShowSuggestions(true) }}
          onBlur={() => setTimeout(() => setShowSuggestions(false), 200)}
          placeholder="005930 · AAPL · 삼성전자 · BTC"
          className="w-56 rounded border border-slate-700 bg-[#0f172a] px-3 py-1.5 font-mono text-xs text-[#e2e2ec] transition-colors focus:border-blue-500 focus:outline-none"
          required
        />

        {showSuggestions && suggestions.length > 0 && (
          <div className="absolute left-0 right-0 z-50 mt-1 max-h-60 overflow-y-auto rounded-lg border border-[#1f2945] bg-[#090d1a]/95 shadow-2xl backdrop-blur-md">
            {suggestions.map((item) => (
              <div
                key={`${item.asset_type || 'STOCK'}-${item.symbol}`}
                onMouseDown={() => handleSuggestionClick(item)}
                className="flex cursor-pointer items-center justify-between border-b border-[#1f2945]/30 px-3 py-2.5 transition-all last:border-none hover:bg-blue-950/40 gap-3"
              >
                <div className="flex items-center gap-2.5 min-w-0">
                  <AssetLogo symbol={item.symbol} assetType={item.asset_type} name={item.display_name} size="h-6 w-6" />
                  <div className="flex min-w-0 flex-col">
                    <span className="truncate text-xs font-bold text-white">{item.display_name}</span>
                    <span className="truncate font-mono text-[9px] text-slate-500">
                      {item.symbol}{getMarketLabel(item) ? ` · ${getMarketLabel(item)}` : ''}
                    </span>
                    {item.symbol_badge ? (
                      <span className="mt-1 w-fit rounded border border-amber-500/50 bg-amber-500/10 px-1.5 py-0.5 text-[9px] font-bold text-amber-200">
                        {item.symbol_badge}
                      </span>
                    ) : null}
                  </div>
                </div>
                <span className="ml-2 shrink-0 rounded border border-cyan-900/60 bg-cyan-950/60 px-1.5 py-0.5 font-mono text-[9px] font-bold uppercase tracking-widest text-cyan-400">
                  {item.asset_type === 'CRYPTO' ? '코인' : '주식'}
                </span>
              </div>
            ))}
          </div>
        )}
      </div>

      <button
        type="submit"
        className="shrink-0 cursor-pointer rounded bg-blue-600 px-3 py-1.5 text-xs font-bold text-white transition-all hover:bg-blue-700 active:scale-95"
      >
        이동
      </button>
    </form>
  )
}
