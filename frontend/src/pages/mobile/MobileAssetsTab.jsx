import { useState } from 'react'
import { Link } from 'react-router-dom'
import { supabase } from '../../supabaseClient'
import { Rate, SectionHeader } from '../../components/DashboardComponents.jsx'
import { getApiErrorMessage } from '../../lib/apiError.js'
import AssetLogo from '../../components/AssetLogo.jsx'
import { preserveMobileDeviceParam } from './mobileRouteUtils.js'
import {
  ALLOCATION_COLOR_HEX as allocationColorHex,
  TAG_REQUIRED_SYMBOLS,
  buildAccountSummaryCards,
  buildAllocationGradient,
  buildHoldingRows,
  formatAllocationPercent,
  formatCryptoAmount,
  getTransferRoute,
  normalizeExchangeCode,
  parseNumeric,
  sortHoldings,
} from '../assetsTabModel.js'

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:5050'

export default function AssetsTab({
  balance,
  allocation,
  accountBalances = [],
  displayCurrency = 'KRW',
  exchangeRate = 1500,
  showMockAssets = true,
  setShowMockAssets,
  balanceLoading = false,
  mobileLayout = false,
  loadAccountBalance,
}) {
  // 모바일 자산 탭은 계좌별 잔고, 입출금, 내부 이체 상태를 한 탭에서 처리합니다.
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

  const [internalTransferOpen, setInternalTransferOpen] = useState(false)
  const [transferDirection, setTransferDirection] = useState('MAIN_UMFUTURE')
  const [transferAmount, setTransferAmount] = useState('')
  const [transferConfirm, setTransferConfirm] = useState(false)
  const [transferMessage, setTransferMessage] = useState({ text: '', isError: false, detail: '' })
  const [transferSubmitting, setTransferSubmitting] = useState(false)

  const openInternalTransferModal = () => {
    setInternalTransferOpen(true)
    setTransferDirection('MAIN_UMFUTURE')
    setTransferAmount('')
    setTransferConfirm(false)
    setTransferMessage({ text: '', isError: false, detail: '' })
  }

  const closeInternalTransferModal = () => {
    setInternalTransferOpen(false)
    setTransferMessage({ text: '', isError: false, detail: '' })
  }

  const getBinanceAvailableCash = (direction) => {
    const targetExchange = direction === 'MAIN_UMFUTURE' ? 'BINANCE' : 'BINANCE_UM_FUTURES'
    const account = accountBalances.find((acc) => {
      const matchExchange = String(acc.raw_exchange || acc.exchange || '').toUpperCase() === targetExchange
      const isMock = String(acc.env || '').toUpperCase() === 'MOCK'
      return matchExchange && !isMock
    })
    return account ? Number(account.available_cash || 0) : 0
  }

  const handleInternalTransferSubmit = async (e) => {
    if (e) e.preventDefault()
    
    const authHeader = await getAuthHeader()
    if (!authHeader) {
      setTransferMessage({ text: '로그인이 필요합니다.', isError: true, detail: '' })
      return
    }

    const amountNum = Number(transferAmount)
    if (!transferAmount || isNaN(amountNum) || amountNum <= 0) {
      setTransferMessage({ text: '올바른 수량을 입력해주세요.', isError: true, detail: '' })
      return
    }

    const availableCash = getBinanceAvailableCash(transferDirection)
    if (amountNum > availableCash) {
      setTransferMessage({ text: '잔고가 부족합니다.', isError: true, detail: '' })
      return
    }

    if (!transferConfirm) {
      setTransferMessage({ text: '최종 이체 동의 체크가 필요합니다.', isError: true, detail: '' })
      return
    }

    setTransferSubmitting(true)
    setTransferMessage({ text: '', isError: false, detail: '' })

    try {
      const response = await fetch(`${API_BASE_URL}/api/transfer/binance/internal`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: authHeader,
        },
        body: JSON.stringify({
          direction: transferDirection,
          amount: amountNum,
        }),
      })

      const payload = await response.json()
      if (!response.ok || !payload.success) {
        throw payload
      }

      setTransferMessage({ text: '이체가 성공적으로 완료되었습니다.', isError: false, detail: '' })
      
      if (loadAccountBalance) {
        await loadAccountBalance()
      }

      setTimeout(() => {
        closeInternalTransferModal()
        setTransferSubmitting(false)
      }, 1500)
    } catch (error) {
      const message = getApiErrorMessage(error, '바이낸스 내부 이체에 실패했습니다.')
      setTransferMessage({
        text: message.title,
        detail: message.detail,
        isError: true,
      })
      setTransferSubmitting(false)
    }
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
    const transferRoute = getTransferRoute(asset)
    setWithdrawAsset(asset)
    setWithdrawForm({
      amount: '',
      network: asset.id || asset.symbol || '',
      address: '',
      secondaryAddress: '',
      confirm: false,
      fromExchange: transferRoute?.fromExchange || 'COINONE',
      toExchange: transferRoute?.toExchange || 'BINANCE',
    })
    setWithdrawPrecheck(null)
    setWithdrawMessage({ text: '', isError: false, detail: '' })
    void fetchTransferStatuses()
  }

  const closeWithdrawModal = () => {
    setWithdrawAsset(null)
    setWithdrawPrecheck(null)
    setWithdrawMessage({ text: '', isError: false, detail: '' })
  }

  async function fetchTransferStatuses() {
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

  const loadDestinationDepositAddress = async () => {
    if (!withdrawAsset) return
    const authHeader = await getAuthHeader()
    if (!authHeader) {
      setWithdrawMessage({ text: '로그인이 필요합니다.', isError: true, detail: '' })
      return
    }
    setWithdrawLoading(true)
    setWithdrawMessage({ text: '', isError: false, detail: '' })
    try {
      const route = getTransferRoute(withdrawAsset)
      const params = new URLSearchParams({
        currency: withdrawAsset.id,
        network: withdrawForm.network || withdrawAsset.id,
      })
      const addressPath = route?.toExchange === 'COINONE'
        ? '/api/transfer/coinone/deposit-address'
        : '/api/transfer/binance/deposit-address'
      const response = await fetch(`${API_BASE_URL}${addressPath}?${params.toString()}`, {
        headers: { Authorization: authHeader },
      })
      const payload = await response.json()
      if (!response.ok || !payload.success) {
        throw payload
      }
      setWithdrawForm((prev) => ({
        ...prev,
        address: payload.data?.address || prev.address,
        secondaryAddress: payload.data?.tag || payload.data?.secondary_address || prev.secondaryAddress,
      }))
      setWithdrawMessage({ text: `${route?.toLabel || '도착 거래소'} 입금 주소를 불러왔습니다.`, isError: false, detail: '' })
    } catch (error) {
      const message = getApiErrorMessage(error, '입금 주소를 불러오지 못했습니다.')
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
          from_exchange: withdrawForm.fromExchange,
          to_exchange: withdrawForm.toExchange,
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
          from_exchange: withdrawForm.fromExchange,
          to_exchange: withdrawForm.toExchange,
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

  const displayAccounts = buildAccountSummaryCards({ accountBalances, showMockAssets })
  const rawHoldings = buildHoldingRows({
    holdings: balance?.holdings?.length ? balance.holdings : [],
    displayCurrency,
    exchangeRate,
  })

  const holdings = rawHoldings

  const sortedHoldings = sortHoldings(holdings, sortConfig)
  const appliedExchangeRate = Number(exchangeRate) || 1500
  const isLiveExchangeRate = Boolean(exchangeRate) && appliedExchangeRate !== 1500
  const allocationGradient = buildAllocationGradient(allocation)

  return (
    <main className={`max-w-7xl mx-auto flex min-w-0 flex-col ${mobileLayout ? 'max-w-full gap-3 overflow-x-hidden' : 'gap-6'}`}>
      <div className={`grid min-w-0 grid-cols-1 ${mobileLayout ? 'max-w-full gap-3 overflow-x-hidden' : 'gap-6'}`}>
      <section className={`bg-slate-surface border border-slate-700/80 rounded-lg ${mobileLayout ? 'p-3' : 'p-5'}`}>
        <div className={`${mobileLayout ? 'mb-2 gap-2' : 'mb-4 gap-3'} flex flex-col sm:flex-row sm:items-start sm:justify-between`}>
          <div>
            <p className="text-[10px] font-bold uppercase tracking-[0.16em] text-ai-cyan">Private Asset</p>
            <div className={`${mobileLayout ? 'mt-0.5 gap-1.5' : 'mt-1 gap-2'} flex flex-col sm:flex-row sm:items-center`}>
              <h2 className="whitespace-nowrap text-sm font-bold uppercase tracking-wider text-white">계좌별 자산 요약</h2>
              {setShowMockAssets ? (
                <div className="inline-flex w-fit rounded-md border border-slate-700/80 bg-[#0f172a] p-1">
                  <button
                    type="button"
                    onClick={() => setShowMockAssets(true)}
                    className={`min-w-[68px] rounded px-3 py-1 text-center text-xs font-bold leading-tight transition-all ${showMockAssets
                      ? 'bg-slate-700 text-white shadow'
                      : 'text-slate-400 hover:text-white'
                    }`}
                  >
                    모의계좌 포함
                  </button>
                  <button
                    type="button"
                    onClick={() => setShowMockAssets(false)}
                    className={`min-w-[68px] rounded px-3 py-1 text-center text-xs font-bold leading-tight transition-all ${!showMockAssets
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
        <div className={`grid ${mobileLayout ? 'grid-cols-1 gap-2' : 'gap-3'}`}>
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
            <div key={account.id} className={`rounded-lg border border-slate-800 bg-[#0f172a] ${mobileLayout ? 'px-3 py-2.5' : 'p-4'}`}>
              <div className={`${mobileLayout ? 'gap-2' : 'gap-3'} flex flex-col md:flex-row md:items-center md:justify-between`}>
                <div>
                  <div className="flex flex-wrap items-center gap-2">
                    <p className={`${mobileLayout ? 'text-xs' : ''} font-bold text-white`}>{account.title}</p>
                    <span className={`rounded-md bg-ai-cyan/10 ${mobileLayout ? 'px-1.5 py-0.5 text-[10px]' : 'px-2 py-1 text-xs'} font-bold text-ai-cyan`}>{account.accountType}</span>
                  </div>
                  {account.sourceText && !mobileLayout ? (
                    <p className="mt-2 text-xs text-slate-500">{account.sourceText}</p>
                  ) : null}
                </div>
                <div className="flex flex-col items-start md:items-end gap-2 shrink-0">
                  <div className="md:text-right">
                    <p className="text-[10px] font-bold text-slate-500">{account.balanceLabel}</p>
                    <p className={`mt-1 ${mobileLayout ? 'text-sm' : 'text-xl'} font-extrabold text-white font-mono`}>{account.balance}</p>
                  </div>
                  {!showMockAssets && (account.id === 'binance-crypto' || account.sources?.has('BINANCE') || account.sources?.has('BINANCE_UM_FUTURES') || (account.sourceText && (account.sourceText.includes('BINANCE') || account.sourceText.includes('BINANCE_UM_FUTURES')))) && (
                    <button
                      type="button"
                      onClick={openInternalTransferModal}
                      className="w-full md:w-auto text-center rounded border border-cyan-500/40 bg-cyan-500/10 px-3 py-1.5 text-[11px] font-bold text-cyan-200 transition hover:border-cyan-300 hover:bg-cyan-500/20 active:bg-cyan-500/30 cursor-pointer"
                    >
                      바이낸스 내부 이체
                    </button>
                  )}
                </div>
              </div>
            </div>
          ))}
        </div>
      </section>

      <section className={`bg-slate-surface border border-slate-700/80 rounded-lg ${mobileLayout ? 'p-3' : 'p-5'}`}>
        <SectionHeader title="자산 배분 상태" />
        {mobileLayout ? (
          <div className="mt-3 flex h-3 overflow-hidden rounded-full border border-slate-800 bg-[#0c0e15]">
            {allocation.map((item) => (
              <span
                key={item.id}
                className={`${item.color} h-full transition-all`}
                style={{ width: `${item.value}%` }}
              />
            ))}
          </div>
        ) : (
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
        )}
        <div className={`${mobileLayout ? 'mt-2 grid-cols-1' : 'mt-5'} grid gap-2`}>
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

      <section className="bg-slate-surface border border-slate-700/80 rounded-lg overflow-hidden min-w-0 max-w-full">
        <div className={`${mobileLayout ? 'px-3.5 pt-3.5 pb-2' : 'p-5 pb-2'}`}>
          <SectionHeader title="투자종목 보유 현황" />
        </div>
        {mobileLayout ? (
          <div className="grid min-w-0 max-w-full gap-2 overflow-x-hidden px-3 pb-3">
            {balanceLoading ? (
              <div className="rounded-lg border border-slate-800 bg-[#0f172a] px-4 py-8 text-center">
                <div className="flex flex-col items-center justify-center gap-2 text-slate-400">
                  <span className="h-5 w-5 animate-spin rounded-full border-2 border-slate-600 border-t-ai-cyan" />
                  <p className="text-sm font-bold text-slate-300">데이터를 불러오는 중입니다.</p>
                </div>
              </div>
            ) : sortedHoldings.length === 0 ? (
              <div className="rounded-lg border border-slate-800 bg-[#0f172a] px-4 py-8 text-center">
                <p className="text-sm font-bold text-slate-300">표시할 보유 종목이 없습니다.</p>
                <p className="mt-1 text-xs text-slate-500">계좌를 연결하거나 새로 고침하면 보유 종목이 표시됩니다.</p>
              </div>
            ) : sortedHoldings.map((item) => {
              const itemExchange = normalizeExchangeCode(item.rawExchange || item.exchange)
              const canWithdraw = ['COINONE', 'BINANCE'].includes(itemExchange)
                && String(item.assetType || '').toUpperCase() === 'CRYPTO'
                && item.source === 'LIVE_BALANCE'
                && parseNumeric(item.quantity) > 0
                && (itemExchange === 'COINONE' || String(item.id || '').toUpperCase() === 'XRP')
              const transferRoute = getTransferRoute(item)

              return (
                <article key={item.rowId || item.id} className="min-w-0 max-w-full rounded-lg border border-slate-800 bg-[#0f172a] p-3">
                  <div className="flex min-w-0 items-start justify-between gap-2">
                    <div className="flex min-w-0 flex-1 items-center gap-3">
                      <AssetLogo symbol={item.id} assetType={item.assetType} name={item.name} size="h-9 w-9" />
                      <div className="min-w-0">
                        <Link to={preserveMobileDeviceParam(`/asset/${item.assetType || 'STOCK'}/${item.id}`)} className="block truncate text-sm font-bold text-blue-400 no-underline">
                          {item.name}
                        </Link>
                        <div className="mt-0.5 flex min-w-0 flex-wrap items-center gap-1.5">
                          <span className="truncate font-mono text-[10px] text-slate-500">{item.id}</span>
                          <span className="max-w-full truncate rounded border border-slate-700/60 bg-slate-800/60 px-1.5 py-0.5 text-[10px] font-bold uppercase text-slate-400">
                            {item.exchange}
                          </span>
                        </div>
                      </div>
                    </div>
                    <div className="shrink-0 max-w-[92px] text-right text-xs leading-tight">
                      <Rate value={item.returnRate} />
                    </div>
                  </div>

                  <div className="mt-3 grid grid-cols-1 gap-2">
                    <div className="grid min-w-0 grid-cols-[auto_minmax(0,1fr)] items-center gap-3 rounded-md bg-slate-950/50 px-2.5 py-2">
                      <p className="text-[10px] font-bold text-slate-500">수량</p>
                      <p className="min-w-0 truncate text-right font-mono text-xs font-bold text-slate-100">{item.quantity}</p>
                    </div>
                    <div className="grid min-w-0 grid-cols-[auto_minmax(0,1fr)] items-center gap-3 rounded-md bg-slate-950/50 px-2.5 py-2">
                      <p className="text-[10px] font-bold text-slate-500">평균가</p>
                      <p className="min-w-0 truncate text-right font-mono text-xs font-bold text-slate-100">{item.average}</p>
                    </div>
                    <div className="grid min-w-0 grid-cols-[auto_minmax(0,1fr)] items-center gap-3 rounded-md bg-slate-950/50 px-2.5 py-2">
                      <p className="text-[10px] font-bold text-slate-500">손익</p>
                      <p className={`min-w-0 truncate text-right font-mono text-xs font-bold ${parseNumeric(item.profit) > 0 ? 'text-red-400' : parseNumeric(item.profit) < 0 ? 'text-blue-400' : 'text-white'}`}>
                        {parseNumeric(item.profit) > 0 ? '+' : ''}{item.profit}
                      </p>
                    </div>
                  </div>

                  {canWithdraw ? (
                    <button
                      type="button"
                      onClick={() => openWithdrawModal(item)}
                      className="mt-3 w-full rounded border border-amber-500/40 bg-amber-500/10 px-3 py-2 text-[11px] font-bold text-amber-200 transition active:bg-amber-500/20"
                    >
                      {transferRoute?.toLabel || '외부'}로 출금
                    </button>
                  ) : null}
                </article>
              )
            })}
          </div>
        ) : null}
        <div className={mobileLayout ? 'hidden' : 'overflow-x-auto'}>
          <table className="w-full min-w-[760px] table-fixed border-collapse text-sm">
            <thead className="block border-y border-slate-800 bg-[#0c0e15]/100 text-xs text-slate-400 [&>tr]:table [&>tr]:w-full [&>tr]:table-fixed">
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
            <tbody className="block max-h-[460px] overflow-y-auto [&>tr]:table [&>tr]:w-full [&>tr]:table-fixed">
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
                const itemExchange = normalizeExchangeCode(item.rawExchange || item.exchange)
                const canWithdraw = ['COINONE', 'BINANCE'].includes(itemExchange)
                  && String(item.assetType || '').toUpperCase() === 'CRYPTO'
                  && item.source === 'LIVE_BALANCE'
                  && parseNumeric(item.quantity) > 0
                  && (itemExchange === 'COINONE' || String(item.id || '').toUpperCase() === 'XRP')
                const transferRoute = getTransferRoute(item)
                return (
                  <tr key={item.rowId || item.id} className="border-b border-slate-800/80 last:border-b-0 hover:bg-slate-800/20">
                    <td className="px-5 py-4 font-bold text-white">
                      <div className="flex items-center gap-3">
                        <AssetLogo symbol={item.id} assetType={item.assetType} name={item.name} size="h-8 w-8" />
                        <div className="min-w-0">
                          <Link to={preserveMobileDeviceParam(`/asset/${item.assetType || 'STOCK'}/${item.id}`)} className="text-blue-400 hover:text-blue-300 hover:underline block truncate">
                            {item.name}
                          </Link>
                          <div className="text-[10px] text-slate-500 font-mono mt-0.5">{item.id}</div>
                        </div>
                      </div>
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
                          {transferRoute?.toLabel || '외부'}로 출금
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
                  {withdrawAsset.id} {getTransferRoute(withdrawAsset)?.fromLabel || '출발 거래소'} → {getTransferRoute(withdrawAsset)?.toLabel || '도착 거래소'} 출금
                </h2>
                <p className="mt-1 text-xs leading-5 text-slate-400">
                  XRP 출금은 Destination Tag/Memo가 필수입니다. 주소와 태그를 도착 거래소 입금 주소 조회값과 대조한 뒤 승인합니다.
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
                    <span>{getTransferRoute(withdrawAsset)?.addressLabel || '입금 주소'}</span>
                    <button
                      type="button"
                      onClick={loadDestinationDepositAddress}
                      disabled={withdrawLoading}
                      className="rounded border border-slate-700 px-2 py-1 text-[10px] font-bold text-slate-300 transition hover:border-cyan-500/40 hover:text-white disabled:opacity-50"
                    >
                      {withdrawLoading ? '조회 중' : getTransferRoute(withdrawAsset)?.addressButtonLabel || '주소 불러오기'}
                    </button>
                  </div>
                  <input
                    type="text"
                    value={withdrawForm.address}
                    onChange={(e) => setWithdrawForm((prev) => ({ ...prev, address: e.target.value, confirm: false }))}
                    placeholder={getTransferRoute(withdrawAsset)?.addressLabel || '입금 주소'}
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
                    주소, 네트워크, Destination Tag/Memo, 수량을 직접 확인했으며 승인 시 실제 {getTransferRoute(withdrawAsset)?.fromLabel || '출발 거래소'} 출금 API가 호출됩니다.
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
                        <span className="font-mono text-white">{formatCryptoAmount(withdrawPrecheck.available_qty, withdrawPrecheck.currency)}</span>
                      </div>
                      <div className="flex justify-between gap-3">
                        <span className="text-slate-500">출금 수수료</span>
                        <span className="font-mono text-amber-200">{formatCryptoAmount(withdrawPrecheck.withdrawal_fee, withdrawPrecheck.currency)}</span>
                      </div>
                      <div className="flex justify-between gap-3">
                        <span className="text-slate-500">예상 수령 수량</span>
                        <span className="font-mono text-cyan-100">{formatCryptoAmount(withdrawPrecheck.estimated_receive_amount, withdrawPrecheck.currency)}</span>
                      </div>
                      <div className="flex justify-between gap-3">
                        <span className="text-slate-500">최소 출금 수량</span>
                        <span className="font-mono text-slate-200">{formatCryptoAmount(withdrawPrecheck.withdrawal_min_amount, withdrawPrecheck.currency)}</span>
                      </div>
                      <div className="flex justify-between gap-3">
                        <span className="text-slate-500">주소 일치</span>
                        <span className={withdrawPrecheck.address_matches_destination ? 'text-emerald-300' : 'text-amber-300'}>
                          {withdrawPrecheck.address_matches_destination ? '일치' : '불일치/수동확인'}
                        </span>
                      </div>
                      <div className="flex justify-between gap-3">
                        <span className="text-slate-500">태그 일치</span>
                        <span className={withdrawPrecheck.tag_matches_destination ? 'text-emerald-300' : 'text-amber-300'}>
                          {withdrawPrecheck.tag_matches_destination ? '일치' : '불일치/수동확인'}
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

      {internalTransferOpen ? (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/80 px-4 py-8 backdrop-blur-sm">
          <div className="max-h-[92vh] w-full max-w-xl overflow-y-auto rounded-2xl border border-slate-700/80 bg-[#0b1220] p-5 shadow-2xl">
            <div className="flex flex-col gap-3 border-b border-slate-800 pb-4 sm:flex-row sm:items-start sm:justify-between">
              <div>
                <p className="text-[10px] font-bold uppercase tracking-[0.18em] text-cyan-300">Binance Internal Transfer</p>
                <div className="mt-1 flex items-center gap-2">
                  <h2 className="text-lg font-bold text-white">바이낸스 내부 이체</h2>
                  <span className="bg-red-500/10 text-red-400 border border-red-500/20 px-2 py-0.5 rounded text-[10px] font-bold shrink-0">실거래 전용</span>
                </div>
                <p className="mt-1 text-xs leading-5 text-slate-400">
                  바이낸스 현물(Spot) 계좌와 USD-M 선물(Futures) 계좌 간에 자금을 즉시 이체합니다.
                </p>
              </div>
              <button
                type="button"
                onClick={closeInternalTransferModal}
                className="rounded border border-slate-700 px-3 py-1.5 text-xs font-bold text-slate-300 transition hover:border-cyan-500/40 hover:text-white cursor-pointer"
              >
                닫기
              </button>
            </div>

            <div className="mt-5 space-y-4">
              {/* 이체 방향 토글 */}
              <div className="rounded-xl border border-slate-800 bg-[#0f172a] p-4 space-y-3">
                <p className="text-xs font-bold text-slate-300">이체 방향</p>
                <div className="grid grid-cols-2 gap-2 p-1 rounded-lg bg-[#070b19] border border-slate-800">
                  <button
                    type="button"
                    onClick={() => {
                      setTransferDirection('MAIN_UMFUTURE')
                      setTransferAmount('')
                      setTransferConfirm(false)
                    }}
                    className={`py-2 text-xs font-bold rounded transition-all cursor-pointer ${
                      transferDirection === 'MAIN_UMFUTURE'
                        ? 'bg-slate-700 text-white shadow'
                        : 'text-slate-400 hover:text-white'
                    }`}
                  >
                    현물 (Spot) ➡️ 선물 (Futures)
                  </button>
                  <button
                    type="button"
                    onClick={() => {
                      setTransferDirection('UMFUTURE_MAIN')
                      setTransferAmount('')
                      setTransferConfirm(false)
                    }}
                    className={`py-2 text-xs font-bold rounded transition-all cursor-pointer ${
                      transferDirection === 'UMFUTURE_MAIN'
                        ? 'bg-slate-700 text-white shadow'
                        : 'text-slate-400 hover:text-white'
                    }`}
                  >
                    선물 (Futures) ➡️ 현물 (Spot)
                  </button>
                </div>
              </div>

              {/* 보유 잔고 표시 및 수량 입력 */}
              <div className="rounded-xl border border-slate-800 bg-[#0f172a] p-4 space-y-3">
                <div className="flex items-center justify-between text-xs">
                  <span className="font-bold text-slate-300">이체 가능 잔고</span>
                  <span className="font-mono font-bold text-cyan-300">
                    {getBinanceAvailableCash(transferDirection).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 4 })} USDT
                  </span>
                </div>
                
                <div className="flex flex-col gap-1.5 text-xs font-bold text-slate-300">
                  <span>이체 수량 (USDT)</span>
                  <div className="flex gap-2">
                    <input
                      type="number"
                      step="any"
                      value={transferAmount}
                      onChange={(e) => {
                        setTransferAmount(e.target.value)
                        setTransferConfirm(false)
                      }}
                      placeholder="이체할 USDT 수량 입력"
                      className="flex-1 rounded border border-slate-700 bg-[#070b19] px-3 py-2 font-mono text-sm text-white outline-none transition focus:border-cyan-400"
                    />
                    <button
                      type="button"
                      onClick={() => {
                        setTransferAmount(String(getBinanceAvailableCash(transferDirection)))
                        setTransferConfirm(false)
                      }}
                      className="rounded border border-slate-700 px-3 py-2 text-xs font-bold text-slate-300 hover:border-cyan-500/40 hover:text-white cursor-pointer"
                    >
                      최대
                    </button>
                  </div>
                </div>
              </div>

              {/* 경고 및 동의 체크박스 */}
              <label className="flex items-start gap-2 rounded-lg border border-red-500/20 bg-red-500/10 p-3 text-xs leading-5 text-red-100 cursor-pointer">
                <input
                  type="checkbox"
                  checked={transferConfirm}
                  onChange={(e) => setTransferConfirm(e.target.checked)}
                  className="mt-1 accent-red-400 cursor-pointer"
                />
                <span>
                  현물 지갑과 선물 지갑 간에 자금이 즉시 이동하며, 취소할 수 없습니다.
                </span>
              </label>

              {/* 상태 메시지 */}
              {transferMessage.text ? (
                <div className={`rounded-lg border px-3 py-2 text-xs font-semibold ${
                  transferMessage.isError
                    ? 'border-red-500/30 bg-red-500/10 text-red-200'
                    : 'border-cyan-500/30 bg-cyan-500/10 text-cyan-100'
                }`}>
                  <div>{transferMessage.text}</div>
                  {transferMessage.detail ? (
                    <div className="mt-1 text-[11px] font-medium leading-5 text-slate-200">
                      {transferMessage.detail}
                    </div>
                  ) : null}
                </div>
              ) : null}

              {/* 버튼 그룹 */}
              <div className="flex gap-2 justify-end border-t border-slate-800 pt-4">
                <button
                  type="button"
                  onClick={closeInternalTransferModal}
                  className="rounded border border-slate-700 px-4 py-2 text-xs font-bold text-slate-300 hover:border-cyan-500/40 hover:text-white cursor-pointer"
                >
                  취소
                </button>
                <button
                  type="button"
                  onClick={handleInternalTransferSubmit}
                  disabled={transferSubmitting || !transferConfirm || !transferAmount || Number(transferAmount) <= 0}
                  className="rounded bg-cyan-500/90 px-4 py-2 text-xs font-extrabold text-slate-950 transition hover:bg-cyan-300 disabled:opacity-40 disabled:cursor-not-allowed cursor-pointer flex items-center gap-1.5"
                >
                  {transferSubmitting && (
                    <span className="h-3 w-3 animate-spin rounded-full border border-slate-950 border-t-transparent" />
                  )}
                  {transferSubmitting ? '이체 진행 중' : '이체 실행'}
                </button>
              </div>
            </div>
          </div>
        </div>
      ) : null}
    </main>
  )
}
