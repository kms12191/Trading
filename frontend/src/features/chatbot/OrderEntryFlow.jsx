import { useEffect, useMemo, useState } from 'react'

import {
  createOrderEntryProposal,
  fetchOrderEntryAccounts,
  fetchOrderEntryContext,
  fetchOrderEntryHoldings,
  precheckOrderEntry,
  searchOrderEntrySymbols,
} from './chatbotApi'
import {
  applyQuantityRatio,
  buildPrecheckRequest,
  canAdvanceOrderStep,
  createEmptyOrderDraft,
  getAvailableIntents,
  getOrderEntryLabels,
  invalidatePrecheck,
  isFuturesAccount,
  isHoldingsIntent,
} from './orderEntryModel'

const INTENT_LABELS = {
  BUY: '매수',
  SELL: '매도',
  OPEN_LONG: '신규 롱',
  OPEN_SHORT: '신규 숏',
  CLOSE_POSITION: '포지션 청산',
}

function formatNumber(value, maximumFractionDigits = 8) {
  const number = Number(value)
  if (!Number.isFinite(number)) return '-'
  return new Intl.NumberFormat('ko-KR', { maximumFractionDigits }).format(number)
}

function StepHeader({ step }) {
  const labels = ['계좌와 거래 목적', '종목과 주문 조건', '사전검증과 확인']
  return (
    <div className="grid grid-cols-3 gap-1.5">
      {labels.map((label, index) => {
        const number = index + 1
        const active = number === step
        const complete = number < step
        return (
          <div
            key={label}
            className={`rounded border px-2 py-2 text-center text-[10px] ${
              active
                ? 'border-ai-cyan bg-ai-cyan/10 text-ai-cyan'
                : complete
                  ? 'border-emerald-500/40 bg-emerald-500/5 text-emerald-200'
                  : 'border-slate-700 text-slate-500'
            }`}
          >
            <strong className="mr-1 font-mono">{number}</strong>{label}
          </div>
        )
      })}
    </div>
  )
}

function ErrorNotice({ message }) {
  if (!message) return null
  return (
    <p role="alert" className="rounded border border-rose-500/40 bg-rose-500/10 px-3 py-2 text-[11px] leading-5 text-rose-100">
      {message}
    </p>
  )
}

export default function OrderEntryFlow({ onClose, onProposalCreated }) {
  const [step, setStep] = useState(1)
  const [draft, setDraft] = useState(createEmptyOrderDraft)
  const [accounts, setAccounts] = useState([])
  const [symbols, setSymbols] = useState([])
  const [holdings, setHoldings] = useState([])
  const [loading, setLoading] = useState(true)
  const [working, setWorking] = useState(false)
  const [error, setError] = useState('')

  const labels = getOrderEntryLabels(draft.account, draft.intent)
  const futures = isFuturesAccount(draft.account)
  const needsHoldings = isHoldingsIntent(draft.intent)
  const riskConfirmationRequired = futures && (Number(draft.leverage) > 5 || draft.margin_type === 'CROSSED')

  useEffect(() => {
    let active = true
    fetchOrderEntryAccounts()
      .then((data) => {
        if (active) setAccounts(data.accounts || [])
      })
      .catch((requestError) => {
        if (active) setError(requestError.message)
      })
      .finally(() => {
        if (active) setLoading(false)
      })
    return () => {
      active = false
    }
  }, [])

  useEffect(() => {
    if (!draft.account || !needsHoldings) {
      return undefined
    }
    let active = true
    fetchOrderEntryHoldings({
      exchange: draft.account.exchange,
      broker_env: draft.account.broker_env,
      asset_type: draft.account.asset_type,
    })
      .then((data) => {
        if (active) setHoldings(data.holdings || [])
      })
      .catch((requestError) => {
        if (active) setError(requestError.message)
      })
      .finally(() => {
        if (active) setWorking(false)
      })
    return () => {
      active = false
    }
  }, [draft.account, needsHoldings])

  useEffect(() => {
    const query = draft.symbol_query.trim()
    if (!draft.account || needsHoldings || query.length < 1) {
      return undefined
    }
    let active = true
    const timer = window.setTimeout(() => {
      searchOrderEntrySymbols({
        exchange: draft.account.exchange,
        broker_env: draft.account.broker_env,
        asset_type: draft.account.asset_type,
        query,
      })
        .then((data) => {
          if (active) setSymbols(data.symbols || [])
        })
        .catch((requestError) => {
          if (active) setError(requestError.message)
        })
    }, 250)
    return () => {
      active = false
      window.clearTimeout(timer)
    }
  }, [draft.account, draft.symbol_query, needsHoldings])

  useEffect(() => {
    if (!draft.account || !draft.selected_symbol?.symbol) return undefined
    let active = true
    fetchOrderEntryContext({
      exchange: draft.account.exchange,
      broker_env: draft.account.broker_env,
      asset_type: draft.account.asset_type,
      symbol: draft.selected_symbol.symbol,
    })
      .then((context) => {
        if (!active) return
        setDraft((current) => invalidatePrecheck(current, {
          context,
          leverage: Math.min(Number(current.leverage) || 1, Number(context.service_max_leverage) || 1),
        }))
      })
      .catch((requestError) => {
        if (active) setError(requestError.message)
      })
      .finally(() => {
        if (active) setWorking(false)
      })
    return () => {
      active = false
    }
  }, [draft.account, draft.selected_symbol])

  const selectedAvailableQuantity = useMemo(
    () => draft.selected_symbol?.available_qty ?? draft.selected_symbol?.quantity,
    [draft.selected_symbol],
  )

  const updateDraft = (changes) => {
    setError('')
    setDraft((current) => invalidatePrecheck(current, changes))
  }

  const selectAccount = (account) => {
    setStep(1)
    setSymbols([])
    setHoldings([])
    setDraft((current) => ({
      ...createEmptyOrderDraft(),
      idempotency_key: current.idempotency_key,
      account,
    }))
  }

  const selectSymbol = (symbol) => {
    setWorking(true)
    updateDraft({
      selected_symbol: symbol,
      symbol_query: symbol.name || symbol.symbol,
      quantity: '',
      price: '',
      context: null,
    })
  }

  const moveNext = () => {
    if (!canAdvanceOrderStep(draft, step)) {
      setError(step === 1
        ? '계좌와 거래 목적을 모두 선택해 주세요.'
        : '검색 결과 또는 보유 목록에서 종목을 선택하고 주문 조건을 확인해 주세요.')
      return
    }
    setError('')
    setStep((current) => Math.min(current + 1, 3))
  }

  const runPrecheck = async () => {
    if (riskConfirmationRequired && !draft.risk_confirmed) {
      setError('5배 초과 레버리지 또는 교차 마진 위험을 확인해 주세요.')
      return
    }
    setWorking(true)
    setError('')
    try {
      const order = buildPrecheckRequest(draft)
      const precheck = await precheckOrderEntry(order)
      setDraft((current) => ({
        ...current,
        precheck,
        precheck_token: precheck.precheck_token || '',
      }))
    } catch (requestError) {
      setError(requestError.message)
    } finally {
      setWorking(false)
    }
  }

  const createProposal = async () => {
    if (!canAdvanceOrderStep(draft, 3)) {
      setError('검증 토큰이 만료되었거나 주문 조건이 변경되었습니다. 다시 검증해 주세요.')
      return
    }
    setWorking(true)
    setError('')
    try {
      const order = buildPrecheckRequest(draft)
      const result = await createOrderEntryProposal(
        order,
        draft.precheck_token,
        Intl.DateTimeFormat().resolvedOptions().timeZone,
      )
      onProposalCreated?.(result)
      onClose()
    } catch (requestError) {
      setError(requestError.message)
    } finally {
      setWorking(false)
    }
  }

  return (
    <section className="space-y-3 rounded-lg border border-ai-cyan/30 bg-[#07111f] p-3.5 text-xs text-slate-100 shadow-xl">
      <div className="flex items-center justify-between border-b border-slate-800 pb-2">
        <div>
          <h3 className="font-bold text-ai-cyan">매매 요청</h3>
          <p className="mt-0.5 text-[10px] text-slate-500">제안 생성 후 승인 카드에서 실행 여부를 결정합니다.</p>
        </div>
        <button type="button" onClick={onClose} className="rounded px-2 py-1 text-slate-400 hover:bg-slate-800 hover:text-white">닫기</button>
      </div>

      <StepHeader step={step} />

      {step === 1 && (
        <div className="space-y-3">
          <div className="space-y-2">
            <p className="font-bold text-slate-200">연결 계좌</p>
            {loading ? <p className="text-slate-400">계좌를 확인하고 있습니다.</p> : null}
            {!loading && accounts.length === 0 ? (
              <p className="rounded border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-amber-100">연결된 거래 계좌가 없습니다. API 설정에서 계좌를 먼저 연결해 주세요.</p>
            ) : null}
            <div className="grid gap-2 md:grid-cols-2">
              {accounts.map((account) => (
                <button
                  key={account.id}
                  type="button"
                  disabled={!account.trade_enabled}
                  onClick={() => selectAccount(account)}
                  className={`rounded border p-3 text-left transition disabled:cursor-not-allowed disabled:opacity-50 ${
                    draft.account?.id === account.id
                      ? 'border-ai-cyan bg-ai-cyan/10'
                      : 'border-slate-700 bg-slate-900/80 hover:border-slate-500'
                  }`}
                >
                  <span className="flex items-center justify-between gap-2">
                    <strong>{account.broker}</strong>
                    <span className="rounded border border-slate-600 px-1.5 py-0.5 text-[9px] text-slate-300">{account.broker_env}</span>
                  </span>
                  <span className="mt-1 block text-[10px] text-slate-400">주문 가능 {formatNumber(account.available_cash)} {account.currency}</span>
                  <span className={`mt-1 block text-[10px] ${account.trade_enabled ? 'text-emerald-300' : 'text-amber-300'}`}>{account.status_message}</span>
                </button>
              ))}
            </div>
          </div>

          {draft.account ? (
            <div className="space-y-2">
              <p className="font-bold text-slate-200">거래 목적</p>
              <div className="grid grid-cols-2 gap-2 md:grid-cols-3">
                {getAvailableIntents(draft.account).map((intent) => (
                  <button
                    key={intent}
                    type="button"
                    onClick={() => {
                      setHoldings([])
                      setSymbols([])
                      setWorking(isHoldingsIntent(intent))
                      updateDraft({ intent, selected_symbol: null, symbol_query: '', quantity: '', price: '' })
                    }}
                    className={`min-h-10 rounded border px-3 py-2 font-bold ${
                      draft.intent === intent
                        ? 'border-ai-cyan bg-ai-cyan text-[#07111f]'
                        : 'border-slate-700 text-slate-300 hover:border-ai-cyan/60'
                    }`}
                  >
                    {INTENT_LABELS[intent]}
                  </button>
                ))}
              </div>
            </div>
          ) : null}
        </div>
      )}

      {step === 2 && (
        <div className="space-y-3">
          <div>
            <p className="mb-2 font-bold text-slate-200">{needsHoldings ? '보유 종목·포지션 선택' : '거래 가능 종목 검색'}</p>
            {!needsHoldings ? (
              <input
                type="search"
                value={draft.symbol_query}
                onChange={(event) => {
                  if (!event.target.value.trim()) setSymbols([])
                  updateDraft({ symbol_query: event.target.value, selected_symbol: null, context: null })
                }}
                placeholder="종목명 또는 심볼 입력"
                className="w-full rounded border border-slate-700 bg-slate-950 px-3 py-2 outline-none focus:border-ai-cyan"
              />
            ) : null}
            <div className="mt-2 max-h-44 space-y-1 overflow-y-auto">
              {(needsHoldings ? holdings : symbols).map((symbol) => (
                <button
                  key={`${symbol.symbol}-${symbol.position_side || ''}`}
                  type="button"
                  disabled={symbol.tradable === false}
                  onClick={() => selectSymbol(symbol)}
                  className={`flex w-full items-center justify-between gap-3 rounded border px-3 py-2 text-left ${
                    draft.selected_symbol?.symbol === symbol.symbol && draft.selected_symbol?.position_side === symbol.position_side
                      ? 'border-ai-cyan bg-ai-cyan/10'
                      : 'border-slate-700 bg-slate-900/70 hover:border-slate-500'
                  } disabled:opacity-50`}
                >
                  <span className="min-w-0">
                    <strong className="block truncate">{symbol.name || symbol.symbol}</strong>
                    <span className="font-mono text-[10px] text-slate-400">{symbol.symbol}{symbol.position_side ? ` · ${symbol.position_side}` : ''} · {symbol.market || symbol.currency}</span>
                  </span>
                  <span className="shrink-0 text-right font-mono text-[10px]">
                    <span className="block">{formatNumber(symbol.current_price)} {symbol.currency || draft.account.currency}</span>
                    {needsHoldings ? <span className="text-slate-400">가능 {formatNumber(symbol.available_qty)}</span> : <span className={Number(symbol.change_rate) >= 0 ? 'text-emerald-300' : 'text-rose-300'}>{formatNumber(symbol.change_rate, 2)}%</span>}
                  </span>
                </button>
              ))}
            </div>
          </div>

          {draft.selected_symbol ? (
            <div className="grid gap-3 rounded border border-slate-700 bg-slate-900/60 p-3 md:grid-cols-2">
              <label className="space-y-1">
                <span className="text-[10px] text-slate-400">수량 ({labels.quantity})</span>
                <input
                  type="number"
                  min="0"
                  step="any"
                  value={draft.quantity}
                  onChange={(event) => updateDraft({ quantity: event.target.value })}
                  className="w-full rounded border border-slate-700 bg-slate-950 px-3 py-2 font-mono outline-none focus:border-ai-cyan"
                />
              </label>
              <div className="space-y-1">
                <span className="text-[10px] text-slate-400">주문 유형</span>
                <div className="grid grid-cols-2 gap-1">
                  {['LIMIT', 'MARKET'].map((orderType) => (
                    <button
                      key={orderType}
                      type="button"
                      disabled={(draft.account.exchange === 'COINONE' && orderType === 'MARKET') || (draft.account.broker_env === 'REAL' && orderType === 'MARKET')}
                      onClick={() => updateDraft({ order_type: orderType, price: '' })}
                      className={`rounded border px-2 py-2 font-bold disabled:cursor-not-allowed disabled:opacity-40 ${draft.order_type === orderType ? 'border-blue-400 bg-blue-500/20 text-blue-100' : 'border-slate-700 text-slate-400'}`}
                    >
                      {orderType === 'LIMIT' ? '지정가' : '시장가'}
                    </button>
                  ))}
                </div>
              </div>
              {draft.order_type === 'LIMIT' ? (
                <label className="space-y-1 md:col-span-2">
                  <span className="text-[10px] text-slate-400">지정가 ({labels.currency})</span>
                  <div className="flex gap-2">
                    <input
                      type="number"
                      min="0"
                      step="any"
                      value={draft.price}
                      onChange={(event) => updateDraft({ price: event.target.value })}
                      placeholder="가격 직접 입력"
                      className="min-w-0 flex-1 rounded border border-slate-700 bg-slate-950 px-3 py-2 font-mono outline-none focus:border-ai-cyan"
                    />
                    <button
                      type="button"
                      disabled={!draft.context?.current_price}
                      onClick={() => updateDraft({ price: String(draft.context.current_price) })}
                      className="rounded border border-ai-cyan/50 px-3 py-2 font-bold text-ai-cyan disabled:opacity-40"
                    >
                      현재가 적용
                    </button>
                  </div>
                </label>
              ) : null}
              {needsHoldings ? (
                <div className="flex gap-1 md:col-span-2">
                  {[0.25, 0.5, 1].map((ratio) => (
                    <button
                      key={ratio}
                      type="button"
                      onClick={() => updateDraft({ quantity: applyQuantityRatio(selectedAvailableQuantity, ratio) })}
                      className="flex-1 rounded border border-slate-700 px-2 py-1.5 text-[10px] font-bold text-slate-300 hover:border-ai-cyan"
                    >
                      {ratio === 1 ? '전량' : `${ratio * 100}%`}
                    </button>
                  ))}
                </div>
              ) : null}
              {futures ? (
                <>
                  <label className="space-y-1">
                    <span className="text-[10px] text-slate-400">레버리지</span>
                    <select value={draft.leverage} onChange={(event) => updateDraft({ leverage: Number(event.target.value), risk_confirmed: false })} className="w-full rounded border border-slate-700 bg-slate-950 px-3 py-2">
                      {(draft.context?.leverage_options || [1]).map((value) => <option key={value} value={value}>{value}x</option>)}
                    </select>
                  </label>
                  <label className="space-y-1">
                    <span className="text-[10px] text-slate-400">마진 모드</span>
                    <select value={draft.margin_type} onChange={(event) => updateDraft({ margin_type: event.target.value, risk_confirmed: false })} className="w-full rounded border border-slate-700 bg-slate-950 px-3 py-2">
                      <option value="ISOLATED">격리 (ISOLATED)</option>
                      <option value="CROSSED">교차 (CROSSED)</option>
                    </select>
                  </label>
                  {riskConfirmationRequired ? (
                    <label className="flex items-start gap-2 rounded border border-amber-500/40 bg-amber-500/10 p-2 text-[10px] text-amber-100 md:col-span-2">
                      <input type="checkbox" checked={draft.risk_confirmed} onChange={(event) => updateDraft({ risk_confirmed: event.target.checked })} />
                      높은 레버리지 또는 교차 마진은 청산 위험과 다른 포지션의 증거금 영향을 키울 수 있음을 확인했습니다.
                    </label>
                  ) : null}
                </>
              ) : null}
            </div>
          ) : null}
        </div>
      )}

      {step === 3 && (
        <div className="space-y-3">
          <div className="grid gap-2 rounded border border-slate-700 bg-slate-900/70 p-3 md:grid-cols-2">
            <p><span className="text-slate-500">계좌</span><strong className="ml-2">{draft.account?.broker} · {draft.account?.broker_env}</strong></p>
            <p><span className="text-slate-500">종목</span><strong className="ml-2">{draft.selected_symbol?.name || draft.selected_symbol?.symbol}</strong></p>
            <p><span className="text-slate-500">방향</span><strong className="ml-2">{labels.intent}</strong></p>
            <p><span className="text-slate-500">수량</span><strong className="ml-2 font-mono">{formatNumber(draft.quantity)} {labels.quantity}</strong></p>
            <p><span className="text-slate-500">가격</span><strong className="ml-2 font-mono">{draft.order_type === 'MARKET' ? '시장가' : `${formatNumber(draft.price)} ${labels.currency}`}</strong></p>
            {futures ? <p><span className="text-slate-500">선물 설정</span><strong className="ml-2">{draft.leverage}x · {draft.margin_type}</strong></p> : null}
          </div>

          {draft.precheck ? (
            <div className={`space-y-2 rounded border p-3 ${draft.precheck.can_create_proposal ? 'border-emerald-500/40 bg-emerald-500/5' : 'border-amber-500/40 bg-amber-500/10'}`}>
              <p className="font-bold text-slate-200">주문 가능</p>
              <div className="grid gap-2 md:grid-cols-3">
                <p><span className="block text-[10px] text-slate-500">예상 주문금액</span><strong>{formatNumber(draft.precheck.estimated_amount)} {labels.currency}</strong></p>
                <p><span className="block text-[10px] text-slate-500">원화 환산 명목금액</span><strong>{formatNumber(draft.precheck.estimated_amount_krw)} KRW</strong></p>
                <p><span className="block text-[10px] text-slate-500">주문 가능 잔액</span><strong>{formatNumber(draft.precheck.available_cash)} {labels.currency}</strong></p>
                {needsHoldings ? <p><span className="block text-[10px] text-slate-500">매도·청산 가능 수량</span><strong>{formatNumber(Math.abs(Number(draft.precheck.holding_qty)))} {labels.quantity}</strong></p> : null}
                {futures ? <p><span className="block text-[10px] text-slate-500">필요 증거금</span><strong>{formatNumber(draft.precheck.required_margin)} USDT</strong></p> : null}
                <p><span className="block text-[10px] text-slate-500">API 거래 권한</span><strong className={draft.precheck.insufficient_permission ? 'text-rose-200' : 'text-emerald-200'}>{draft.precheck.insufficient_permission ? '확인 필요' : '사용 가능'}</strong></p>
              </div>
              <div className="border-t border-slate-700/70 pt-2">
                <p className="font-bold text-slate-200">위험 확인</p>
                <p className="mt-1 text-[10px] text-slate-400">
                  {futures
                    ? `${draft.precheck.futures_options?.leverage || draft.leverage}x · ${draft.precheck.futures_options?.margin_type || draft.margin_type} · 명목금액 기준 실거래 하드캡 적용`
                    : '현재가·보유량·거래 시간·실거래 하드캡을 서버에서 확인했습니다.'}
                </p>
              </div>
              <p className="text-[10px] text-slate-400">최신 시세 확인 {draft.precheck.checked_at || '-'}</p>
              {(draft.precheck.blockers || []).map((blocker) => <p key={blocker} className="text-[11px] text-rose-200">{blocker}</p>)}
              {(draft.precheck.warnings || []).filter((warning) => !(draft.precheck.blockers || []).includes(warning)).map((warning) => <p key={warning} className="text-[11px] text-amber-200">{warning}</p>)}
            </div>
          ) : (
            <p className="rounded border border-slate-700 bg-slate-900/60 px-3 py-2 text-slate-400">검증하기를 눌러 최신 시세, 잔고, 보유량, 거래 권한과 위험 정보를 확인해 주세요.</p>
          )}

          <div className="grid grid-cols-2 gap-2">
            <button type="button" disabled={working} onClick={runPrecheck} className="min-h-10 rounded border border-ai-cyan/60 px-3 py-2 font-bold text-ai-cyan disabled:opacity-50">
              {draft.precheck ? '다시 검증하기' : '검증하기'}
            </button>
            <button type="button" disabled={working || !canAdvanceOrderStep(draft, 3)} onClick={createProposal} className="min-h-10 rounded bg-ai-cyan px-3 py-2 font-bold text-[#07111f] disabled:cursor-not-allowed disabled:opacity-40">
              매매 제안 만들기
            </button>
          </div>
        </div>
      )}

      <ErrorNotice message={error} />
      {working ? <p className="text-center text-[10px] text-ai-cyan">최신 계좌 정보를 확인하고 있습니다.</p> : null}

      {step < 3 ? (
        <div className="flex justify-end gap-2 border-t border-slate-800 pt-3">
          {step > 1 ? <button type="button" onClick={() => setStep((current) => current - 1)} className="rounded border border-slate-700 px-4 py-2 text-slate-300">이전</button> : null}
          <button type="button" onClick={moveNext} disabled={!canAdvanceOrderStep(draft, step)} className="rounded bg-ai-cyan px-4 py-2 font-bold text-[#07111f] disabled:cursor-not-allowed disabled:opacity-40">다음</button>
        </div>
      ) : (
        <button type="button" onClick={() => setStep(2)} className="text-left text-[10px] font-bold text-slate-400 hover:text-ai-cyan">주문 조건 수정</button>
      )}
    </section>
  )
}
