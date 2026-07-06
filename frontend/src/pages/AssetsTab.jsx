import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { supabase } from '../supabaseClient'
import { Rate, SectionHeader } from '../components/DashboardComponents.jsx'
import { getApiErrorMessage } from '../lib/apiError.js'

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:5050'
const TAG_REQUIRED_SYMBOLS = new Set(['XRP', 'XLM', 'EOS'])

export default function AssetsTab({
  balance,
  allocation,
  accountBalances = [],
  displayCurrency = 'KRW',
  exchangeRate = 1500,
  showMockAssets = true,
  setShowMockAssets,
  balanceLoading = false,
}) {
  const [sortConfig, setSortConfig] = useState({ key: null, direction: 'asc' })
  const [withdrawAsset, setWithdrawAsset] = useState(null)
  const [withdrawForm, setWithdrawForm] = useState({
    amount: '',
    network: '',
    address: '',
    secondaryAddress: '',
    confirm: false,
  })
  const [withdrawPrecheck, setWithdrawPrecheck] = useState(null)
  const [withdrawMessage, setWithdrawMessage] = useState({ text: '', isError: false, detail: '' })
  const [withdrawLoading, setWithdrawLoading] = useState(false)
  const [withdrawSubmitting, setWithdrawSubmitting] = useState(false)
  const [transferRows, setTransferRows] = useState([])
  const [transferLoading, setTransferLoading] = useState(false)

  const parseNumeric = (val) => {
    if (typeof val === 'number') return val
    const text = String(val || '')
    const num = parseFloat(text.replace(/[^0-9.-]/g, ''))
    return Number.isFinite(num) ? num : 0
  }

  const formatNativeCurrency = (value, currency) => {
    const numeric = Number(value)
    if (!Number.isFinite(numeric)) return '-'
    const normalizedCurrency = String(currency || 'KRW').toUpperCase()
    if (normalizedCurrency === 'USD' || normalizedCurrency === 'USDT') {
      return `$${numeric.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
    }
    if (normalizedCurrency === 'KRW') {
      return `₩${Math.round(numeric).toLocaleString()}`
    }
    return `${numeric.toLocaleString()} ${normalizedCurrency}`
  }

  const getBalanceCashEntries = (account = {}) => {
    const fallbackCurrency = String(account.available_cash_currency || account.currency || 'KRW').toUpperCase()
    const components = Array.isArray(account.available_cash_details?.components)
      ? account.available_cash_details.components
      : []

    if (components.length > 0) {
      return components
        .map((component) => {
          const amount = Number(component?.cash_buying_power)
          if (!Number.isFinite(amount)) return null
          return {
            currency: String(component?.currency || fallbackCurrency).toUpperCase(),
            amount,
          }
        })
        .filter(Boolean)
    }

    const fallbackAmount = Number(account.available_cash)
    if (!Number.isFinite(fallbackAmount)) return []
    return [{ currency: fallbackCurrency, amount: fallbackAmount }]
  }

  const buildAccountSummaryCards = () => {
    const normalizedAccounts = (accountBalances || [])
      .filter(Boolean)
      .filter((account) => showMockAssets || String(account.env || '').toUpperCase() !== 'MOCK')

    const cardMap = new Map([
      ['domestic-stock', {
        id: 'domestic-stock',
        title: '국내 주식 계좌',
        accountType: '원화',
        balanceLabel: '잔고 포함',
        currency: 'KRW',
        amount: 0,
        sources: new Set(),
      }],
      ['overseas-stock', {
        id: 'overseas-stock',
        title: '해외 주식 계좌',
        accountType: '달러',
        balanceLabel: '잔고 포함',
        currency: 'USD',
        amount: 0,
        sources: new Set(),
      }],
      ['coinone-crypto', {
        id: 'coinone-crypto',
        title: '코인 계좌',
        accountType: '원화',
        balanceLabel: '잔고 포함',
        currency: 'KRW',
        amount: 0,
        sources: new Set(),
      }],
      ['binance-crypto', {
        id: 'binance-crypto',
        title: '코인 계좌',
        accountType: '달러',
        balanceLabel: '잔고 포함',
        currency: 'USD',
        amount: 0,
        sources: new Set(),
      }],
    ])

    const addSource = (cardId, source) => {
      const card = cardMap.get(cardId)
      if (!card || !source) return
      card.sources.add(source)
    }

    const addAmount = (cardId, amount, source) => {
      const card = cardMap.get(cardId)
      const numeric = Number(amount)
      if (!card || !Number.isFinite(numeric)) return
      card.amount += numeric
      if (source) card.sources.add(source)
    }

    normalizedAccounts.forEach((account) => {
      const exchange = String(account.raw_exchange || account.exchange || '').toUpperCase()
      const sourceLabel = `${exchange}${account.env ? ` ${account.env}` : ''}`
      const cashEntries = getBalanceCashEntries(account)

      if (['TOSS', 'KIS'].includes(exchange)) {
        addSource('domestic-stock', sourceLabel)
        addSource('overseas-stock', sourceLabel)
      } else if (exchange === 'COINONE') {
        addSource('coinone-crypto', sourceLabel)
      } else if (exchange === 'BINANCE' || exchange === 'BINANCE_UM_FUTURES') {
        addSource('binance-crypto', sourceLabel)
      }

      cashEntries.forEach((entry) => {
        const currency = String(entry.currency || '').toUpperCase()
        if (['TOSS', 'KIS'].includes(exchange)) {
          if (currency === 'KRW') addAmount('domestic-stock', entry.amount, sourceLabel)
          if (currency === 'USD' || currency === 'USDT') addAmount('overseas-stock', entry.amount, sourceLabel)
        } else if (exchange === 'COINONE') {
          if (currency === 'KRW') addAmount('coinone-crypto', entry.amount, sourceLabel)
        } else if (exchange === 'BINANCE' || exchange === 'BINANCE_UM_FUTURES') {
          if (currency === 'USD' || currency === 'USDT') addAmount('binance-crypto', entry.amount, sourceLabel)
        }
      })

      ;(account.holdings || []).forEach((holding) => {
        const holdingCurrency = String(holding.currency || account.currency || '').toUpperCase()
        const evalAmount = parseNumeric(holding.eval_amount) || Math.abs(parseNumeric(holding.qty)) * parseNumeric(holding.current_price)
        if (evalAmount <= 0) return

        if (['TOSS', 'KIS'].includes(exchange)) {
          if (holdingCurrency === 'USD' || holdingCurrency === 'USDT') addAmount('overseas-stock', evalAmount, sourceLabel)
          else addAmount('domestic-stock', evalAmount, sourceLabel)
        } else if (exchange === 'COINONE') {
          addAmount('coinone-crypto', evalAmount, sourceLabel)
        } else if (exchange === 'BINANCE' || exchange === 'BINANCE_UM_FUTURES') {
          addAmount('binance-crypto', evalAmount, sourceLabel)
        }
      })
    })

    return Array.from(cardMap.values())
      .map((card) => ({
        ...card,
        balance: formatNativeCurrency(card.amount, card.currency),
        sourceText: Array.from(card.sources).join(' · '),
      }))
      .filter((card) => card.sources.size > 0)
  }

  const handleSort = (key) => {
    let direction = 'asc'
    if (sortConfig.key === key && sortConfig.direction === 'asc') {
      direction = 'desc'
    }
    setSortConfig({ key, direction })
  }

  const getAuthHeader = async () => {
    const { data: { session } } = await supabase.auth.getSession()
    return session?.access_token ? `Bearer ${session.access_token}` : ''
  }

  const openWithdrawModal = (asset) => {
    setWithdrawAsset(asset)
    setWithdrawForm({
      amount: '',
      network: asset.id || asset.symbol || '',
      address: '',
      secondaryAddress: '',
      confirm: false,
    })
    setWithdrawPrecheck(null)
    setWithdrawMessage({ text: '', isError: false, detail: '' })
  }

  const closeWithdrawModal = () => {
    setWithdrawAsset(null)
    setWithdrawPrecheck(null)
    setWithdrawMessage({ text: '', isError: false, detail: '' })
  }

  const fetchTransferStatuses = async () => {
    const authHeader = await getAuthHeader()
    if (!authHeader) return
    setTransferLoading(true)
    try {
      const response = await fetch(`${API_BASE_URL}/api/transfer/withdraw/status?limit=10`, {
        headers: { Authorization: authHeader },
      })
      const payload = await response.json()
      if (response.ok && payload.success) {
        setTransferRows(payload.data || [])
      }
    } catch {
      // 상태 추적 실패는 자산 목록 표시를 막지 않습니다.
    } finally {
      setTransferLoading(false)
    }
  }

  useEffect(() => {
    if (withdrawAsset) {
      fetchTransferStatuses()
    }
  }, [withdrawAsset])

  const loadBinanceDepositAddress = async () => {
    if (!withdrawAsset) return
    const authHeader = await getAuthHeader()
    if (!authHeader) {
      setWithdrawMessage({ text: '로그인이 필요합니다.', isError: true, detail: '' })
      return
    }
    setWithdrawLoading(true)
    setWithdrawMessage({ text: '', isError: false, detail: '' })
    try {
      const params = new URLSearchParams({
        currency: withdrawAsset.id,
        network: withdrawForm.network || withdrawAsset.id,
      })
      const response = await fetch(`${API_BASE_URL}/api/transfer/binance/deposit-address?${params.toString()}`, {
        headers: { Authorization: authHeader },
      })
      const payload = await response.json()
      if (!response.ok || !payload.success) {
        throw payload
      }
      setWithdrawForm((prev) => ({
        ...prev,
        address: payload.data?.address || prev.address,
        secondaryAddress: payload.data?.tag || prev.secondaryAddress,
      }))
      setWithdrawMessage({ text: '바이낸스 입금 주소를 불러왔습니다.', isError: false, detail: '' })
    } catch (error) {
      const message = getApiErrorMessage(error, '바이낸스 입금 주소를 불러오지 못했습니다.')
      setWithdrawMessage({
        text: message.title,
        detail: message.detail,
        isError: true,
      })
    } finally {
      setWithdrawLoading(false)
    }
  }

  const runWithdrawPrecheck = async () => {
    if (!withdrawAsset) return
    const authHeader = await getAuthHeader()
    if (!authHeader) {
      setWithdrawMessage({ text: '로그인이 필요합니다.', isError: true, detail: '' })
      return
    }
    setWithdrawLoading(true)
    setWithdrawPrecheck(null)
    setWithdrawMessage({ text: '', isError: false, detail: '' })
    try {
      const response = await fetch(`${API_BASE_URL}/api/transfer/withdraw/precheck`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: authHeader,
        },
        body: JSON.stringify({
          currency: withdrawAsset.id,
          network: withdrawForm.network || withdrawAsset.id,
          amount: Number(withdrawForm.amount),
          address: withdrawForm.address,
          secondary_address: withdrawForm.secondaryAddress,
        }),
      })
      const payload = await response.json()
      if (!response.ok || !payload.success) {
        throw payload
      }
      setWithdrawPrecheck(payload.data)
      setWithdrawMessage({ text: '사전검증이 완료되었습니다. 주소와 수량을 다시 확인한 뒤 승인하세요.', isError: false, detail: '' })
    } catch (error) {
      const message = getApiErrorMessage(error, '출금 사전검증에 실패했습니다.')
      setWithdrawMessage({
        text: message.title,
        detail: message.detail,
        isError: true,
      })
    } finally {
      setWithdrawLoading(false)
    }
  }

  const approveWithdrawal = async () => {
    if (!withdrawAsset) return
    const authHeader = await getAuthHeader()
    if (!authHeader) {
      setWithdrawMessage({ text: '로그인이 필요합니다.', isError: true, detail: '' })
      return
    }
    if (!withdrawForm.confirm) {
      setWithdrawMessage({ text: '최종 승인 체크가 필요합니다.', isError: true, detail: '' })
      return
    }
    setWithdrawSubmitting(true)
    setWithdrawMessage({ text: '', isError: false, detail: '' })
    try {
      const response = await fetch(`${API_BASE_URL}/api/transfer/withdraw/approve`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: authHeader,
        },
        body: JSON.stringify({
          currency: withdrawAsset.id,
          network: withdrawForm.network || withdrawAsset.id,
          amount: Number(withdrawForm.amount),
          address: withdrawForm.address,
          secondary_address: withdrawForm.secondaryAddress,
          confirm: true,
        }),
      })
      const payload = await response.json()
      if (!response.ok || !payload.success) {
        throw payload
      }
      setWithdrawMessage({ text: `출금 요청이 접수되었습니다. 추적 ID: ${payload.proposal_id}`, isError: false, detail: '' })
      setWithdrawPrecheck(null)
      setWithdrawForm((prev) => ({ ...prev, confirm: false }))
      await fetchTransferStatuses()
    } catch (error) {
      const message = getApiErrorMessage(error, '출금 승인 처리에 실패했습니다.')
      setWithdrawMessage({
        text: message.title,
        detail: message.detail,
        isError: true,
      })
    } finally {
      setWithdrawSubmitting(false)
    }
  }

  const formatCurrency = (value, currency, targetDisplayCurrency = displayCurrency) => {
    const numeric = Number(value)
    const val = Number.isFinite(numeric) ? numeric : 0
    const rate = Number(exchangeRate) || 1500

    if (targetDisplayCurrency === 'KRW') {
      if (currency === 'USD' || currency === 'USDT') {
        return `₩${Math.round(val * rate).toLocaleString()}`
      }
      return `₩${Math.round(val).toLocaleString()}`
    }

    if (targetDisplayCurrency === 'USD') {
      if (currency === 'KRW') {
        return `$${(val / rate).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
      }
      return `$${val.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
    }

    if (currency === 'USD' || currency === 'USDT') {
      return `$${val.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
    }
    return `₩${Math.round(val).toLocaleString()}`
  }

  const formatUnitCurrency = (value, currency, targetDisplayCurrency = displayCurrency) => {
    const numeric = Number(value)
    const val = Number.isFinite(numeric) ? numeric : 0
    const rate = Number(exchangeRate) || 1500

    if (targetDisplayCurrency === 'KRW') {
      const displayValue = (currency === 'USD' || currency === 'USDT') ? val * rate : val
      return `₩${displayValue.toLocaleString(undefined, { minimumFractionDigits: 0, maximumFractionDigits: 1 })}`
    }

    if (targetDisplayCurrency === 'USD') {
      const displayValue = currency === 'KRW' ? val / rate : val
      return `$${displayValue.toLocaleString(undefined, { minimumFractionDigits: 0, maximumFractionDigits: 1 })}`
    }

    if (currency === 'USD' || currency === 'USDT') {
      return `$${val.toLocaleString(undefined, { minimumFractionDigits: 0, maximumFractionDigits: 1 })}`
    }
    return `₩${val.toLocaleString(undefined, { minimumFractionDigits: 0, maximumFractionDigits: 1 })}`
  }

  const displayAccounts = buildAccountSummaryCards()
  const rawHoldings = balance?.holdings?.length
    ? balance.holdings.map((stock, index) => {
      const exchangeName = stock.exchange || stock.account_type || '-'
      const isCoinone = String(exchangeName).toUpperCase() === 'COINONE'
      const isForeign = /[a-zA-Z]/.test(stock.symbol) && !/^[0-9a-zA-Z]{6,7}$/.test(stock.symbol) && !isCoinone
      const stockCurrency = stock.currency || (isForeign ? 'USD' : 'KRW')
      const currentDisplayCurrency = isForeign ? displayCurrency : 'KRW'
      const rawExchange = String(stock.raw_exchange || exchangeName || '').toUpperCase()
      const assetType = stock.asset_type || (['COINONE', 'BINANCE', 'BINANCE_UM_FUTURES'].includes(rawExchange) ? 'CRYPTO' : 'STOCK')
      const symbol = stock.symbol || stock.id || `holding-${index}`
      const profitRate = Number(stock.profit_rate)
      return {
        id: symbol,
        rowId: `${rawExchange || exchangeName}-${stock.env || 'REAL'}-${symbol}-${index}`,
        name: stock.name,
        exchange: exchangeName,
        assetType,
        source: stock.source || 'LIVE_BALANCE',
        quantity: `${stock.qty}`,
        average: formatUnitCurrency(stock.avg_price, stockCurrency, currentDisplayCurrency),
        profit: formatCurrency(stock.profit, stockCurrency, currentDisplayCurrency),
        returnRate: `${profitRate >= 0 ? '+' : ''}${Number.isFinite(profitRate) ? profitRate.toFixed(2) : '0.00'}%`,
      }
    })
    : []

  const holdings = rawHoldings

  const sortedHoldings = [...holdings].sort((a, b) => {
    if (!sortConfig.key) return 0
    let aVal = parseNumeric(a[sortConfig.key])
    let bVal = parseNumeric(b[sortConfig.key])
    return sortConfig.direction === 'asc' ? aVal - bVal : bVal - aVal
  })
  const appliedExchangeRate = Number(exchangeRate) || 1500
  const isLiveExchangeRate = Boolean(exchangeRate) && appliedExchangeRate !== 1500
  const allocationColorHex = {
    domestic: '#0047bb',
    overseas: '#00e0ff',
    coin: '#f59e0b',
    cash: '#64748b',
  }
  const formatAllocationPercent = (item = {}) => {
    const rawPercent = Number(item.rawPercent ?? item.value)
    if (rawPercent > 0 && rawPercent < 1) return '1% 미만'
    if (rawPercent <= 0) return '0%'
    return `${rawPercent.toFixed(1)}%`
  }
  const allocationSegments = allocation.filter((item) => Number(item.value) > 0)
  const allocationTotal = allocationSegments.reduce((sum, item) => sum + Number(item.value), 0)
  let allocationGradientCursor = 0
  const allocationGradient = allocationSegments.length > 0
    ? `conic-gradient(${allocationSegments.map((item) => {
      const start = allocationGradientCursor
      allocationGradientCursor += (Number(item.value) / allocationTotal) * 100
      return `${allocationColorHex[item.id] || '#64748b'} ${start}% ${allocationGradientCursor}%`
    }).join(', ')})`
    : 'conic-gradient(#334155 0% 100%)'

  return (
    <main className="max-w-7xl mx-auto flex flex-col gap-6">
      <div className="grid gap-6 xl:grid-cols-[minmax(0,2fr)_minmax(300px,1fr)]">
      <section className="bg-slate-surface border border-slate-700/80 rounded-lg p-5">
        <div className="mb-4 flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
          <div>
            <p className="text-[10px] font-bold uppercase tracking-[0.16em] text-ai-cyan">Private Asset</p>
            <div className="mt-1 flex flex-col gap-2 sm:flex-row sm:items-center">
              <h2 className="text-sm font-bold uppercase tracking-wider text-white">계좌별 자산 요약</h2>
              {setShowMockAssets ? (
                <div className="inline-flex w-fit rounded-md border border-slate-700/80 bg-[#0f172a] p-1">
                  <button
                    type="button"
                    onClick={() => setShowMockAssets(true)}
                    className={`rounded px-3 py-1 text-xs font-bold transition-all ${showMockAssets
                      ? 'bg-slate-700 text-white shadow'
                      : 'text-slate-400 hover:text-white'
                    }`}
                  >
                    모의계좌 포함
                  </button>
                  <button
                    type="button"
                    onClick={() => setShowMockAssets(false)}
                    className={`rounded px-3 py-1 text-xs font-bold transition-all ${!showMockAssets
                      ? 'bg-slate-700 text-white shadow'
                      : 'text-slate-400 hover:text-white'
                    }`}
                  >
                    실거래 전용
                  </button>
                </div>
              ) : null}
            </div>
          </div>
          <div className="flex flex-wrap items-center gap-2 text-xs text-slate-400 sm:justify-end">
            <span className={`h-1.5 w-1.5 rounded-full ${isLiveExchangeRate ? 'bg-[#38bdf8] animate-pulse' : 'bg-amber-400'}`} />
            <span className="font-bold">적용 환율</span>
            <span className="font-mono font-bold text-white">
              ₩{appliedExchangeRate.toLocaleString(undefined, { maximumFractionDigits: 1 })}
            </span>
            <span className={`rounded border px-1.5 py-0.5 text-[10px] font-bold ${
              isLiveExchangeRate
                ? 'border-emerald-500/20 bg-emerald-500/10 text-emerald-400'
                : 'border-amber-500/20 bg-amber-500/10 text-amber-400'
            }`}>
              {isLiveExchangeRate ? '실시간 API (Live)' : '임시 고정 환율'}
            </span>
          </div>
        </div>
        <div className="grid gap-3">
          {balanceLoading ? (
            <div className="rounded-lg border border-slate-800 bg-[#0f172a] p-4 text-center">
              <div className="flex flex-col items-center justify-center gap-2 py-4 text-slate-400">
                <span className="h-5 w-5 animate-spin rounded-full border-2 border-slate-600 border-t-ai-cyan" />
                <p className="text-sm font-bold text-slate-300">계좌 자산을 불러오는 중입니다.</p>
              </div>
            </div>
          ) : displayAccounts.length === 0 ? (
            <div className="rounded-lg border border-slate-800 bg-[#0f172a] p-4 text-center">
              <p className="text-sm font-bold text-slate-300">표시할 계좌 자산이 없습니다.</p>
              <p className="mt-1 text-xs text-slate-500">거래소 API 키를 연결하고 새로 고침하면 계좌별 자산이 표시됩니다.</p>
            </div>
          ) : displayAccounts.map((account) => (
            <div key={account.id} className="rounded-lg border border-slate-800 bg-[#0f172a] p-4">
              <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
                <div>
                  <div className="flex flex-wrap items-center gap-2">
                    <p className="font-bold text-white">{account.title}</p>
                    <span className="rounded-md bg-ai-cyan/10 px-2 py-1 text-xs font-bold text-ai-cyan">{account.accountType}</span>
                  </div>
                  {account.sourceText ? (
                    <p className="mt-2 text-xs text-slate-500">{account.sourceText}</p>
                  ) : null}
                </div>
                <div className="md:text-right">
                  <p className="text-xs font-bold text-slate-500">{account.balanceLabel}</p>
                  <p className="mt-1 text-xl font-extrabold text-white font-mono">{account.balance}</p>
                </div>
              </div>
            </div>
          ))}
        </div>
      </section>

      <section className="bg-slate-surface border border-slate-700/80 rounded-lg p-5">
        <SectionHeader title="보유자산 현황 및 자산 배분 상태" />
        <div className="mt-4 flex justify-center">
          <div
            className="flex aspect-square w-full max-w-[220px] items-center justify-center rounded-full border border-slate-700/70 shadow-inner"
            style={{ background: allocationGradient }}
          >
            <div className="flex h-[62%] w-[62%] flex-col items-center justify-center rounded-full border border-slate-800 bg-[#0f172a] text-center">
              <span className="text-[10px] font-bold uppercase tracking-[0.16em] text-slate-500">Total</span>
              <span className="font-mono text-lg font-black text-white">100%</span>
            </div>
          </div>
        </div>
        <div className="mt-5 grid gap-2">
          {allocation.map((item) => (
            <div key={item.id} className="flex items-center justify-between gap-3 rounded-lg bg-[#0f172a] px-3 py-2.5">
              <span className="flex min-w-0 items-center gap-2 text-xs font-bold text-white">
                <span
                  className="h-2.5 w-2.5 shrink-0 rounded-full"
                  style={{ backgroundColor: allocationColorHex[item.id] || '#64748b' }}
                />
                <span className="truncate">{item.label}</span>
              </span>
              <span className="shrink-0 font-mono text-xs font-bold text-slate-300">{formatAllocationPercent(item)}</span>
            </div>
          ))}
        </div>
      </section>
      </div>

      <section className="bg-slate-surface border border-slate-700/80 rounded-lg overflow-hidden">
        <div className="p-5 pb-2">
          <SectionHeader title="투자종목 보유 현황" />
        </div>
        <div className="overflow-x-auto">
          <table className="w-full min-w-[760px] border-collapse text-sm">
            <thead className="border-y border-slate-800 bg-[#0f172a] text-xs text-slate-400">
              <tr>
                <th className="px-5 py-3 text-left font-bold">투자종목 명</th>
                <th className="px-5 py-3 text-left font-bold">거래소</th>
                <th className="px-5 py-3 text-left font-bold">
                  수량
                  <button onClick={() => handleSort('quantity')} className="inline-flex flex-col ml-1 align-middle text-[8px] leading-[6px] text-slate-500 hover:text-white cursor-pointer select-none">
                    <span className={sortConfig.key === 'quantity' && sortConfig.direction === 'asc' ? 'text-ai-cyan' : ''}>▲</span>
                    <span className={sortConfig.key === 'quantity' && sortConfig.direction === 'desc' ? 'text-ai-cyan' : ''}>▼</span>
                  </button>
                </th>
                <th className="px-5 py-3 text-left font-bold">평균단가</th>
                <th className="px-5 py-3 text-left font-bold">
                  평가손익
                  <button onClick={() => handleSort('profit')} className="inline-flex flex-col ml-1 align-middle text-[8px] leading-[6px] text-slate-500 hover:text-white cursor-pointer select-none">
                    <span className={sortConfig.key === 'profit' && sortConfig.direction === 'asc' ? 'text-ai-cyan' : ''}>▲</span>
                    <span className={sortConfig.key === 'profit' && sortConfig.direction === 'desc' ? 'text-ai-cyan' : ''}>▼</span>
                  </button>
                </th>
                <th className="px-5 py-3 text-left font-bold">
                  수익률
                  <button onClick={() => handleSort('returnRate')} className="inline-flex flex-col ml-1 align-middle text-[8px] leading-[6px] text-slate-500 hover:text-white cursor-pointer select-none">
                    <span className={sortConfig.key === 'returnRate' && sortConfig.direction === 'asc' ? 'text-ai-cyan' : ''}>▲</span>
                    <span className={sortConfig.key === 'returnRate' && sortConfig.direction === 'desc' ? 'text-ai-cyan' : ''}>▼</span>
                  </button>
                </th>
                <th className="px-5 py-3 text-right font-bold">자산 이동</th>
              </tr>
            </thead>
            <tbody>
              {balanceLoading ? (
                <tr>
                  <td colSpan="7" className="px-5 py-12 text-center">
                    <div className="flex flex-col items-center justify-center gap-2 text-slate-400">
                      <span className="h-5 w-5 animate-spin rounded-full border-2 border-slate-600 border-t-ai-cyan" />
                      <p className="text-sm font-bold text-slate-300">데이터를 불러오는 중입니다.</p>
                      <p className="text-xs text-slate-500">연결된 계좌의 보유 종목을 확인하고 있습니다.</p>
                    </div>
                  </td>
                </tr>
              ) : sortedHoldings.length === 0 ? (
                <tr>
                  <td colSpan="7" className="px-5 py-12 text-center">
                    <div className="flex flex-col items-center justify-center gap-2 text-slate-400">
                      <p className="text-sm font-bold text-slate-300">표시할 보유 종목이 없습니다.</p>
                      <p className="text-xs text-slate-500">계좌를 연결했거나 새로 고침을 완료하면 실제 보유 종목이 표시됩니다.</p>
                    </div>
                  </td>
                </tr>
              ) : sortedHoldings.map((item) => {
                const canWithdraw = String(item.exchange || '').toUpperCase() === 'COINONE'
                  && String(item.assetType || '').toUpperCase() === 'CRYPTO'
                  && item.source === 'LIVE_BALANCE'
                  && parseNumeric(item.quantity) > 0
                return (
                  <tr key={item.rowId || item.id} className="border-b border-slate-800/80 last:border-b-0 hover:bg-slate-800/20">
                    <td className="px-5 py-4 font-bold text-white">
                      <Link to={`/asset/${item.assetType || 'STOCK'}/${item.id}`} className="text-blue-400 hover:text-blue-300 hover:underline">
                        {item.name}
                      </Link>
                      <div className="text-[10px] text-slate-500 font-mono mt-0.5">{item.id}</div>
                    </td>
                    <td className="px-5 py-4 font-sans font-bold text-slate-400">
                      <span className="rounded bg-slate-800/60 border border-slate-700/60 px-1.5 py-0.5 text-[10px] uppercase">
                        {item.exchange}
                      </span>
                    </td>
                    <td className="px-5 py-4 font-mono">{item.quantity}</td>
                    <td className="px-5 py-4 font-mono">{item.average}</td>
                    <td className={`px-5 py-4 font-mono font-semibold ${parseNumeric(item.profit) > 0 ? 'text-red-400' : parseNumeric(item.profit) < 0 ? 'text-blue-400' : 'text-white'}`}>
                      {parseNumeric(item.profit) > 0 ? '+' : ''}{item.profit}
                    </td>
                    <td className="px-5 py-4"><Rate value={item.returnRate} /></td>
                    <td className="px-5 py-4 text-right">
                      {canWithdraw ? (
                        <button
                          type="button"
                          onClick={() => openWithdrawModal(item)}
                          className="rounded border border-amber-500/40 bg-amber-500/10 px-3 py-1.5 text-[11px] font-bold text-amber-200 transition hover:border-amber-300 hover:bg-amber-500/20"
                        >
                          바이낸스로 출금
                        </button>
                      ) : (
                        <span className="text-[10px] text-slate-600">-</span>
                      )}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      </section>

      {withdrawAsset ? (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/80 px-4 py-8 backdrop-blur-sm">
          <div className="max-h-[92vh] w-full max-w-4xl overflow-y-auto rounded-2xl border border-slate-700/80 bg-[#0b1220] p-5 shadow-2xl">
            <div className="flex flex-col gap-3 border-b border-slate-800 pb-4 sm:flex-row sm:items-start sm:justify-between">
              <div>
                <p className="text-[10px] font-bold uppercase tracking-[0.18em] text-amber-300">Coin Transfer</p>
                <h2 className="mt-1 text-lg font-bold text-white">
                  {withdrawAsset.id} 코인원 → 바이낸스 출금
                </h2>
                <p className="mt-1 text-xs leading-5 text-slate-400">
                  코인원 출금주소록에 등록되고 2차 인증이 완료된 주소만 출금됩니다. XRP/XLM/EOS는 Destination Tag/Memo가 필수입니다.
                </p>
              </div>
              <button
                type="button"
                onClick={closeWithdrawModal}
                className="rounded border border-slate-700 px-3 py-1.5 text-xs font-bold text-slate-300 transition hover:border-cyan-500/40 hover:text-white"
              >
                닫기
              </button>
            </div>

            <div className="mt-5 grid gap-4 lg:grid-cols-[1.1fr_0.9fr]">
              <div className="rounded-xl border border-slate-800 bg-[#0f172a] p-4">
                <div className="grid gap-3 sm:grid-cols-2">
                  <label className="flex flex-col gap-1.5 text-xs font-bold text-slate-300">
                    출금 수량
                    <input
                      type="number"
                      step="any"
                      value={withdrawForm.amount}
                      onChange={(e) => setWithdrawForm((prev) => ({ ...prev, amount: e.target.value, confirm: false }))}
                      placeholder={`최대 ${withdrawAsset.quantity}`}
                      className="rounded border border-slate-700 bg-[#070b19] px-3 py-2 font-mono text-sm text-white outline-none transition focus:border-cyan-400"
                    />
                  </label>
                  <label className="flex flex-col gap-1.5 text-xs font-bold text-slate-300">
                    네트워크
                    <input
                      type="text"
                      value={withdrawForm.network}
                      onChange={(e) => setWithdrawForm((prev) => ({ ...prev, network: e.target.value.toUpperCase(), confirm: false }))}
                      className="rounded border border-slate-700 bg-[#070b19] px-3 py-2 font-mono text-sm text-white outline-none transition focus:border-cyan-400"
                    />
                  </label>
                </div>

                <div className="mt-3 flex flex-col gap-1.5 text-xs font-bold text-slate-300">
                  <div className="flex items-center justify-between gap-2">
                    <span>바이낸스 입금 주소</span>
                    <button
                      type="button"
                      onClick={loadBinanceDepositAddress}
                      disabled={withdrawLoading}
                      className="rounded border border-slate-700 px-2 py-1 text-[10px] font-bold text-slate-300 transition hover:border-cyan-500/40 hover:text-white disabled:opacity-50"
                    >
                      {withdrawLoading ? '조회 중' : '주소 불러오기'}
                    </button>
                  </div>
                  <input
                    type="text"
                    value={withdrawForm.address}
                    onChange={(e) => setWithdrawForm((prev) => ({ ...prev, address: e.target.value, confirm: false }))}
                    placeholder="바이낸스 입금 주소"
                    className="rounded border border-slate-700 bg-[#070b19] px-3 py-2 font-mono text-xs text-white outline-none transition focus:border-cyan-400"
                  />
                </div>

                <label className="mt-3 flex flex-col gap-1.5 text-xs font-bold text-slate-300">
                  Destination Tag / Memo {TAG_REQUIRED_SYMBOLS.has(withdrawAsset.id) ? '(필수)' : '(선택)'}
                  <input
                    type="text"
                    value={withdrawForm.secondaryAddress}
                    onChange={(e) => setWithdrawForm((prev) => ({ ...prev, secondaryAddress: e.target.value, confirm: false }))}
                    placeholder="XRP 태그 또는 Memo"
                    className="rounded border border-slate-700 bg-[#070b19] px-3 py-2 font-mono text-sm text-white outline-none transition focus:border-cyan-400"
                  />
                </label>

                <div className="mt-4 flex flex-wrap gap-2">
                  <button
                    type="button"
                    onClick={runWithdrawPrecheck}
                    disabled={withdrawLoading}
                    className="rounded bg-cyan-500/90 px-4 py-2 text-xs font-extrabold text-slate-950 transition hover:bg-cyan-300 disabled:opacity-50"
                  >
                    {withdrawLoading ? '검증 중' : '사전검증'}
                  </button>
                  <button
                    type="button"
                    onClick={approveWithdrawal}
                    disabled={withdrawSubmitting || !withdrawPrecheck || !withdrawForm.confirm}
                    className="rounded border border-amber-400/70 bg-amber-400/10 px-4 py-2 text-xs font-extrabold text-amber-100 transition hover:bg-amber-400/20 disabled:cursor-not-allowed disabled:opacity-40"
                  >
                    {withdrawSubmitting ? '출금 요청 중' : '승인 후 출금'}
                  </button>
                </div>

                <label className="mt-4 flex items-start gap-2 rounded-lg border border-red-500/20 bg-red-500/10 p-3 text-xs leading-5 text-red-100">
                  <input
                    type="checkbox"
                    checked={withdrawForm.confirm}
                    onChange={(e) => setWithdrawForm((prev) => ({ ...prev, confirm: e.target.checked }))}
                    className="mt-1 accent-red-400"
                  />
                  <span>
                    주소, 네트워크, Destination Tag/Memo, 수량을 직접 확인했으며 승인 시 실제 코인원 출금 API가 호출됩니다.
                  </span>
                </label>

                {withdrawMessage.text ? (
                  <div className={`mt-3 rounded-lg border px-3 py-2 text-xs font-semibold ${
                    withdrawMessage.isError
                      ? 'border-red-500/30 bg-red-500/10 text-red-200'
                      : 'border-cyan-500/30 bg-cyan-500/10 text-cyan-100'
                  }`}>
                    <div>{withdrawMessage.text}</div>
                    {withdrawMessage.detail ? (
                      <div className="mt-1 text-[11px] font-medium leading-5 text-slate-200">
                        {withdrawMessage.detail}
                      </div>
                    ) : null}
                  </div>
                ) : null}
              </div>

              <div className="flex flex-col gap-4">
                <div className="rounded-xl border border-slate-800 bg-[#0f172a] p-4">
                  <h3 className="text-sm font-bold text-white">사전검증 결과</h3>
                  {withdrawPrecheck ? (
                    <div className="mt-3 space-y-2 text-xs text-slate-300">
                      <div className="flex justify-between gap-3">
                        <span className="text-slate-500">출금 가능 수량</span>
                        <span className="font-mono text-white">{withdrawPrecheck.available_qty} {withdrawPrecheck.currency}</span>
                      </div>
                      <div className="flex justify-between gap-3">
                        <span className="text-slate-500">주소 일치</span>
                        <span className={withdrawPrecheck.address_matches_binance ? 'text-emerald-300' : 'text-amber-300'}>
                          {withdrawPrecheck.address_matches_binance ? '일치' : '불일치/수동확인'}
                        </span>
                      </div>
                      <div className="flex justify-between gap-3">
                        <span className="text-slate-500">태그 일치</span>
                        <span className={withdrawPrecheck.tag_matches_binance ? 'text-emerald-300' : 'text-amber-300'}>
                          {withdrawPrecheck.tag_matches_binance ? '일치' : '불일치/수동확인'}
                        </span>
                      </div>
                      {withdrawPrecheck.warnings?.length ? (
                        <div className="rounded-lg border border-amber-500/20 bg-amber-500/10 p-3 text-amber-100">
                          {withdrawPrecheck.warnings.join(' / ')}
                        </div>
                      ) : null}
                    </div>
                  ) : (
                    <p className="mt-3 text-xs text-slate-500">사전검증 후 결과가 표시됩니다.</p>
                  )}
                </div>

                <div className="rounded-xl border border-slate-800 bg-[#0f172a] p-4">
                  <div className="flex items-center justify-between gap-2">
                    <h3 className="text-sm font-bold text-white">최근 출금 상태</h3>
                    <button
                      type="button"
                      onClick={fetchTransferStatuses}
                      disabled={transferLoading}
                      className="rounded border border-slate-700 px-2 py-1 text-[10px] font-bold text-slate-300 transition hover:border-cyan-500/40 hover:text-white disabled:opacity-50"
                    >
                      {transferLoading ? '갱신 중' : '상태 갱신'}
                    </button>
                  </div>
                  <div className="mt-3 max-h-56 overflow-y-auto space-y-2">
                    {transferRows.length > 0 ? transferRows.map((row) => (
                      <div key={row.id} className="rounded-lg border border-slate-800 bg-[#070b19] p-3 text-xs">
                        <div className="flex items-center justify-between gap-3">
                          <span className="font-mono font-bold text-white">{row.amount} {row.currency}</span>
                          <span className="rounded bg-slate-800 px-2 py-0.5 font-bold text-cyan-200">{row.status}</span>
                        </div>
                        <div className="mt-1 break-all text-[10px] text-slate-500">{row.external_transaction_id || row.id}</div>
                      </div>
                    )) : (
                      <p className="text-xs text-slate-500">최근 출금 요청이 없습니다.</p>
                    )}
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      ) : null}
    </main>
  )
}
