import { useEffect, useMemo, useState } from 'react'
import { supabase } from '../../supabaseClient'
import {
  buildAiFundConfigPayloads,
  buildTossStockSelectionPayload,
  canEditAiFundSettings,
  getNextAiFundActiveState,
} from '../adminAiFundDashboardModel'

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:5050'

const availabilityLabel = {
  POLICY_BLOCKED: '정책상 보류',
  NO_LONG_SIGNAL: '매수 신호 없음',
  LOW_CONFIDENCE: '확신도 부족',
  NO_PREDICTIONS: '예측 데이터 없음',
}

const exchangeLabels = {
  coinone: '코인원',
  binance: '바이낸스',
  toss: '토스 주식',
}

const riskPresetDefaults = {
  conservative: { takeProfitPct: 3, stopLossPct: -1, minSignalConfidence: 0.85, positionSizePct: 5, dailyMddLimitPct: -1 },
  neutral: { takeProfitPct: 5, stopLossPct: -2, minSignalConfidence: 0.75, positionSizePct: 10, dailyMddLimitPct: -2 },
  aggressive: { takeProfitPct: 8, stopLossPct: -4, minSignalConfidence: 0.65, positionSizePct: 20, dailyMddLimitPct: -4 },
}

function formatCurrency(value) {
  return `${Number(value || 0).toLocaleString('ko-KR')}원`
}

function formatPercent(value, digits = 1) {
  const numberValue = Number(value)
  if (!Number.isFinite(numberValue)) return '-'
  return `${numberValue.toFixed(digits)}%`
}

function CandidateCard({ eyebrow, symbol, confidence, reason }) {
  return (
    <article className="rounded-lg border border-slate-800 bg-[#0b1220] p-3">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="text-[10px] font-bold uppercase tracking-wide text-slate-500">{eyebrow}</p>
          <h3 className="mt-1 break-words text-base font-black text-white">{symbol}</h3>
        </div>
        <span className="shrink-0 rounded border border-emerald-500/40 bg-emerald-500/10 px-2 py-1 text-[11px] font-black text-emerald-300">
          {formatPercent(Number(confidence || 0) * 100)}
        </span>
      </div>
      <p className="mt-2 break-words text-[11px] leading-5 text-slate-400">{reason || '활성 ML 매수 신호'}</p>
    </article>
  )
}

function AvailabilityNotice({ title, availability }) {
  return (
    <div className="rounded-lg border border-amber-900/70 bg-amber-950/20 px-3 py-2 text-xs text-amber-100">
      <p className="font-bold">{title}: {availabilityLabel[availability?.status] || '후보 보류'}</p>
      <p className="mt-1 break-words text-[11px] leading-5 text-slate-400">
        {availability?.message || '현재 후보 상태를 확인하지 못했습니다.'}
        {availability?.market_regimes?.length ? ` 시장 국면: ${availability.market_regimes.join(', ')}` : ''}
      </p>
    </div>
  )
}

function RiskSlider({ label, valueText, inputProps, accentClassName = 'accent-emerald-500' }) {
  return (
    <label className="block rounded-lg border border-slate-800 bg-slate-950/70 px-3 py-2.5 text-[11px] font-bold text-slate-400">
      <span className="flex items-center justify-between gap-2">
        <span>{label}</span>
        <span className="font-mono text-slate-100">{valueText}</span>
      </span>
      <input {...inputProps} className={`mt-2.5 w-full ${accentClassName}`} />
    </label>
  )
}

export default function MobileAdminAiFundDashboard({ userId }) {
  const [selectedExchanges, setSelectedExchanges] = useState(['coinone', 'toss'])
  const [capital, setCapital] = useState(5000000)
  const [riskPreset, setRiskPreset] = useState('neutral')
  const [isActive, setIsActive] = useState(false)
  const [loading, setLoading] = useState(false)
  const [message, setMessage] = useState('')
  const [currentUserId, setCurrentUserId] = useState(userId || '')
  const [tradeLogs, setTradeLogs] = useState([])
  const [lastCheckTime, setLastCheckTime] = useState(new Date().toLocaleTimeString())
  const [assetScope, setAssetScope] = useState('ALL')
  const [maxOpenPositions, setMaxOpenPositions] = useState(3)
  const [krAllocation, setKrAllocation] = useState(50)
  const [usAllocation, setUsAllocation] = useState(50)
  const [stockCandidates, setStockCandidates] = useState([])
  const [stockAvailability, setStockAvailability] = useState({})
  const [candidatesLoading, setCandidatesLoading] = useState(false)
  const [cryptoSnapshots, setCryptoSnapshots] = useState({})
  const [cryptoCandidatesLoading, setCryptoCandidatesLoading] = useState(false)
  const [cryptoShortPerformance, setCryptoShortPerformance] = useState(null)
  const [cryptoShortLoading, setCryptoShortLoading] = useState(false)
  const [riskSettings, setRiskSettings] = useState(riskPresetDefaults.neutral)
  const [isGuideOpen, setIsGuideOpen] = useState(false)
  const settingsLocked = !canEditAiFundSettings(isActive)

  const cryptoCandidates = useMemo(() => (
    Object.entries(cryptoSnapshots).flatMap(([exchange, snapshot]) => (
      (snapshot.candidates || []).map((candidate) => ({ ...candidate, exchange }))
    ))
  ), [cryptoSnapshots])
  const selectedExchangeText = selectedExchanges.map((exchange) => exchangeLabels[exchange] || exchange).join(', ')

  useEffect(() => {
    if (!isGuideOpen) return undefined
    const closeOnEscape = (event) => {
      if (event.key === 'Escape') setIsGuideOpen(false)
    }
    window.addEventListener('keydown', closeOnEscape)
    return () => window.removeEventListener('keydown', closeOnEscape)
  }, [isGuideOpen])

  useEffect(() => {
    if (!currentUserId) {
      supabase.auth.getSession().then(({ data: { session } }) => {
        if (session?.user?.id) setCurrentUserId(session.user.id)
      })
    }
  }, [currentUserId])

  useEffect(() => {
    if (!currentUserId) return undefined

    const fetchConfigAndLogs = async () => {
      const { data: configData } = await supabase
        .from('admin_ai_fund_configs')
        .select('*')
        .eq('user_id', currentUserId)

      if (configData && configData.length > 0) {
        const activeExchanges = configData
          .filter((cfg) => cfg.is_active)
          .map((cfg) => cfg.exchange_type)
        setSelectedExchanges(activeExchanges.length > 0 ? activeExchanges : configData.map((cfg) => cfg.exchange_type))
        setIsActive(activeExchanges.length > 0)

        const firstCfg = configData[0]
        const tossConfig = configData.find((cfg) => cfg.exchange_type === 'toss')
        setCapital(firstCfg.allocated_capital || 5000000)
        setRiskPreset(firstCfg.risk_preset || 'neutral')
        setRiskSettings({
          takeProfitPct: Number(firstCfg.target_take_profit_pct ?? 5),
          stopLossPct: Number(firstCfg.stop_loss_pct ?? firstCfg.daily_mdd_limit_pct ?? -2),
          minSignalConfidence: Number(firstCfg.min_signal_confidence ?? 0.75),
          positionSizePct: Number(firstCfg.max_position_size && firstCfg.allocated_capital ? (firstCfg.max_position_size / firstCfg.allocated_capital) * 100 : 10),
          dailyMddLimitPct: Number(firstCfg.daily_mdd_limit_pct ?? -2),
        })
        if (tossConfig) {
          setAssetScope(tossConfig.asset_scope || 'ALL')
          setMaxOpenPositions(tossConfig.max_open_positions || 3)
          setKrAllocation(tossConfig.kr_allocation_pct ?? 50)
          setUsAllocation(tossConfig.us_allocation_pct ?? 50)
        }
      }

      const { data: logsData } = await supabase
        .from('admin_ai_trade_logs')
        .select('*')
        .eq('user_id', currentUserId)
        .order('created_at', { ascending: false })
        .limit(20)

      setTradeLogs(logsData || [])
      setLastCheckTime(new Date().toLocaleTimeString())
    }

    fetchConfigAndLogs()
    const tickerInterval = window.setInterval(() => {
      setLastCheckTime(new Date().toLocaleTimeString())
    }, 5000)

    const configChannel = supabase
      .channel('admin-ai-fund-changes-mobile')
      .on('postgres_changes', {
        event: '*',
        schema: 'public',
        table: 'admin_ai_fund_configs',
        filter: `user_id=eq.${currentUserId}`,
      }, (payload) => {
        if (payload.new) {
          setIsActive(payload.new.is_active || false)
          if (payload.new.allocated_capital) setCapital(payload.new.allocated_capital)
          if (payload.new.risk_preset) setRiskPreset(payload.new.risk_preset)
          setRiskSettings((previous) => ({
            takeProfitPct: Number(payload.new.target_take_profit_pct ?? previous.takeProfitPct),
            stopLossPct: Number(payload.new.stop_loss_pct ?? previous.stopLossPct),
            minSignalConfidence: Number(payload.new.min_signal_confidence ?? previous.minSignalConfidence),
            positionSizePct: Number(payload.new.max_position_size && payload.new.allocated_capital ? (payload.new.max_position_size / payload.new.allocated_capital) * 100 : previous.positionSizePct),
            dailyMddLimitPct: Number(payload.new.daily_mdd_limit_pct ?? previous.dailyMddLimitPct),
          }))
          if (payload.new.exchange_type === 'toss') {
            setAssetScope(payload.new.asset_scope || 'ALL')
            setMaxOpenPositions(payload.new.max_open_positions || 3)
            setKrAllocation(payload.new.kr_allocation_pct ?? 50)
            setUsAllocation(payload.new.us_allocation_pct ?? 50)
          }
        }
        setLastCheckTime(new Date().toLocaleTimeString())
      })
      .subscribe()

    const logChannel = supabase
      .channel('admin-ai-logs-changes-mobile')
      .on('postgres_changes', {
        event: 'INSERT',
        schema: 'public',
        table: 'admin_ai_trade_logs',
        filter: `user_id=eq.${currentUserId}`,
      }, (payload) => {
        if (payload.new) setTradeLogs((prev) => [payload.new, ...prev.slice(0, 19)])
        setLastCheckTime(new Date().toLocaleTimeString())
      })
      .subscribe()

    return () => {
      window.clearInterval(tickerInterval)
      supabase.removeChannel(configChannel)
      supabase.removeChannel(logChannel)
    }
  }, [currentUserId])

  const fetchStockCandidates = async () => {
    if (!currentUserId || !selectedExchanges.includes('toss')) {
      setStockCandidates([])
      setStockAvailability({})
      return
    }
    setCandidatesLoading(true)
    try {
      const { data: { session } } = await supabase.auth.getSession()
      if (!session?.access_token) throw new Error('로그인 세션이 만료되었습니다.')
      const response = await fetch(`${API_BASE_URL}/api/admin/ai-fund/stock-candidates?user_id=${encodeURIComponent(currentUserId)}`, {
        headers: { Authorization: `Bearer ${session.access_token}` },
      })
      const payload = await response.json()
      if (!response.ok || !payload.success) throw new Error(payload.message || '주식 후보를 불러오지 못했습니다.')
      setStockCandidates(payload.candidates || [])
      setStockAvailability(payload.availability || {})
    } catch (error) {
      setStockCandidates([])
      setStockAvailability({})
      setMessage(error.message)
    } finally {
      setCandidatesLoading(false)
    }
  }

  useEffect(() => {
    fetchStockCandidates()
  }, [currentUserId, selectedExchanges])

  const fetchCryptoCandidates = async () => {
    const cryptoExchanges = selectedExchanges.filter((exchange) => exchange === 'coinone' || exchange === 'binance')
    if (!currentUserId || !cryptoExchanges.length) {
      setCryptoSnapshots({})
      return
    }
    setCryptoCandidatesLoading(true)
    try {
      const { data: { session } } = await supabase.auth.getSession()
      if (!session?.access_token) throw new Error('로그인 세션이 만료되었습니다.')
      const results = await Promise.all(cryptoExchanges.map(async (exchange) => {
        const response = await fetch(`${API_BASE_URL}/api/admin/ai-fund/crypto-candidates?user_id=${encodeURIComponent(currentUserId)}&exchange_type=${exchange}`, {
          headers: { Authorization: `Bearer ${session.access_token}` },
        })
        const payload = await response.json()
        if (!response.ok || !payload.success) throw new Error(payload.message || '코인 후보를 불러오지 못했습니다.')
        return [exchange, payload]
      }))
      setCryptoSnapshots(Object.fromEntries(results))
    } catch (error) {
      setCryptoSnapshots({})
      setMessage(error.message)
    } finally {
      setCryptoCandidatesLoading(false)
    }
  }

  useEffect(() => {
    fetchCryptoCandidates()
  }, [currentUserId, selectedExchanges])

  const fetchCryptoShortPerformance = async () => {
    if (!currentUserId || !selectedExchanges.includes('binance')) {
      setCryptoShortPerformance(null)
      return
    }
    setCryptoShortLoading(true)
    try {
      const { data: { session } } = await supabase.auth.getSession()
      if (!session?.access_token) throw new Error('로그인 세션이 만료되었습니다.')
      const response = await fetch(`${API_BASE_URL}/api/admin/ai-fund/crypto-short-performance`, {
        headers: { Authorization: `Bearer ${session.access_token}` },
      })
      const payload = await response.json()
      if (!response.ok || !payload.success) throw new Error(payload.message || '숏 모델 성능을 불러오지 못했습니다.')
      setCryptoShortPerformance(payload)
    } catch (error) {
      setCryptoShortPerformance(null)
      setMessage(error.message)
    } finally {
      setCryptoShortLoading(false)
    }
  }

  useEffect(() => {
    fetchCryptoShortPerformance()
  }, [currentUserId, selectedExchanges])

  const toggleExchange = (exchangeKey) => {
    if (settingsLocked) return
    setMessage('')
    setSelectedExchanges((prev) => {
      if (prev.includes(exchangeKey)) {
        if (prev.length <= 1) {
          setMessage('최소 1개 이상의 운용 거래소를 선택해야 합니다.')
          return prev
        }
        return prev.filter((item) => item !== exchangeKey)
      }
      return [...prev, exchangeKey]
    })
  }

  const applyRiskPreset = (preset) => {
    if (settingsLocked) return
    setRiskPreset(preset)
    setRiskSettings(riskPresetDefaults[preset])
  }

  const updateRiskSetting = (key, value) => {
    if (settingsLocked) return
    setRiskPreset('custom')
    setRiskSettings((previous) => ({ ...previous, [key]: Number(value) }))
  }

  const handleToggleActive = async (nextActive = !isActive, completionMessage = '') => {
    if (nextActive && !window.confirm(`실제 주문을 시작합니다.\n\n거래소: ${selectedExchanges.map((exchange) => exchangeLabels[exchange] || exchange).join(', ')}\n전체 운용 한도: ${formatCurrency(capital)}\n1회 투자 비중: ${riskSettings.positionSizePct.toFixed(0)}%\n\n계속하시겠습니까?`)) return

    setLoading(true)
    setMessage('')
    try {
      const tossSelection = buildTossStockSelectionPayload({
        userId: currentUserId,
        capital,
        riskPreset,
        assetScope,
        maxOpenPositions,
        krAllocation,
        usAllocation,
      })
      if (selectedExchanges.includes('toss') && !tossSelection) {
        throw new Error('토스 주식 자동선별의 시장 배분과 최대 보유 종목 수를 확인해 주세요.')
      }
      const payloadList = buildAiFundConfigPayloads({
        exchanges: selectedExchanges,
        userId: currentUserId,
        capital,
        riskPreset,
        riskSettings,
        isActive: nextActive,
        tossSelection,
      })

      const { error } = await supabase
        .from('admin_ai_fund_configs')
        .upsert(payloadList, { onConflict: 'user_id,exchange_type' })

      if (error) throw error
      setIsActive(nextActive)
      setMessage(completionMessage || (nextActive ? `선택한 ${selectedExchanges.length}개 거래소의 AI 자동선별 운용을 시작했습니다.` : 'AI 위탁 운용이 일시정지되었습니다.'))
      if (nextActive) {
        fetchStockCandidates()
        fetchCryptoCandidates()
      }
    } catch (error) {
      setMessage(`오류: ${error.message}`)
    } finally {
      setLoading(false)
    }
  }

  const handleEmergencyKillSwitch = async () => {
    if (!window.confirm('긴급 셧다운을 실행하시겠습니까? 모든 AI 자동 매매가 즉시 정지됩니다.')) return
    setLoading(true)
    try {
      const { error } = await supabase
        .from('admin_ai_fund_configs')
        .update({ is_active: false })
        .eq('user_id', currentUserId)

      if (error) throw error
      setIsActive(false)
      setMessage('[긴급 셧다운 완료] 모든 AI 위탁 운용이 정지되었습니다.')
    } catch (error) {
      setMessage(`셧다운 오류: ${error.message}`)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="space-y-4 text-[#e2e2ec]">
      <section className="rounded-lg border border-emerald-500/20 bg-[#07111f] p-4">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <p className="text-[10px] font-black uppercase tracking-[0.16em] text-emerald-300">AI Fund</p>
            <h1 className="mt-1 break-words text-xl font-black text-white">AI 위탁 자동투자</h1>
            <p className="mt-1 text-[11px] leading-5 text-slate-400">Human-on-the-Loop 모델 기반 AI 자율 운용 및 리스크 관리 시스템</p>
          </div>
          <span className={`shrink-0 rounded-full border px-2.5 py-1 text-[10px] font-black ${isActive ? 'border-emerald-400/50 bg-emerald-400/10 text-emerald-300' : 'border-slate-600 bg-slate-900 text-slate-400'}`}>
            {isActive ? '운용 중' : '대기'}
          </span>
        </div>

        <div className="mt-4 grid grid-cols-2 gap-2">
          <div className="rounded-lg border border-slate-800 bg-slate-950/60 p-3">
            <p className="text-[10px] font-bold text-slate-500">운용 한도</p>
            <p className="mt-1 text-sm font-black text-white">{formatCurrency(capital)}</p>
          </div>
          <div className="rounded-lg border border-slate-800 bg-slate-950/60 p-3">
            <p className="text-[10px] font-bold text-slate-500">최근 확인</p>
            <p className="mt-1 text-sm font-black text-white">{lastCheckTime}</p>
          </div>
        </div>

        <div className="mt-3 rounded-lg border border-slate-800 bg-slate-950/70 p-3">
          <div className="flex items-start gap-3">
            <span className="relative mt-1 flex h-3 w-3 shrink-0">
              <span className={`absolute inline-flex h-full w-full rounded-full opacity-75 ${isActive ? 'animate-ping bg-emerald-400' : 'bg-slate-600'}`} />
              <span className={`relative inline-flex h-3 w-3 rounded-full ${isActive ? 'bg-emerald-500' : 'bg-slate-600'}`} />
            </span>
            <div className="min-w-0">
              <div className="flex flex-wrap items-center gap-2">
                <p className="text-xs font-black text-slate-100">
                  AI 운용 상태: {isActive ? `운용 중 (${selectedExchangeText} 감시)` : '운용 대기/일시정지'}
                </p>
                {isActive ? (
                  <span className="rounded border border-emerald-800 bg-emerald-950 px-2 py-0.5 text-[10px] font-mono text-emerald-400">
                    Live Scanner Active
                  </span>
                ) : null}
              </div>
              <p className="mt-1 break-words text-[11px] leading-5 text-slate-400">
                {isActive
                  ? `LightGBM ML 엔진 감시 중 | 선택 거래소: ${selectedExchangeText} | 최소 확신도 ${(riskSettings.minSignalConfidence * 100).toFixed(0)}% 이상 | 목표익절 +${riskSettings.takeProfitPct.toFixed(1)}% | 포지션 손절 ${riskSettings.stopLossPct.toFixed(1)}%`
                  : '운용 시작 시 코인은 거래소별 ML 후보에서, 주식은 국내·미국 활성 모델 후보에서 자동으로 종목을 선별합니다.'}
              </p>
              <p className="mt-1 text-[10px] text-slate-500">스캔 주기: 매 5초 실시간 업데이트</p>
            </div>
          </div>
        </div>

        <div className="mt-4 grid grid-cols-2 gap-2">
          <button
            type="button"
            onClick={() => handleToggleActive(getNextAiFundActiveState(isActive))}
            disabled={loading || !currentUserId}
            className={`h-9 rounded px-3 text-[11px] font-black transition disabled:cursor-not-allowed disabled:opacity-50 ${isActive ? 'bg-amber-600 text-white active:bg-amber-700' : 'bg-emerald-500 text-slate-950 active:bg-emerald-400'}`}
          >
            {loading ? '처리 중' : isActive ? '운용 일시정지' : '운용 시작'}
          </button>
          <button
            type="button"
            onClick={() => handleToggleActive(false, '실거래 설정을 저장했습니다.')}
            disabled={loading || settingsLocked || !currentUserId}
            className="h-9 rounded border border-slate-700 bg-slate-950 px-3 text-[11px] font-black text-slate-200 transition active:border-emerald-500 disabled:cursor-not-allowed disabled:opacity-50"
          >
            설정 저장
          </button>
        </div>
        <div className="mt-2 grid grid-cols-2 gap-2">
          <button type="button" onClick={() => setIsGuideOpen(true)} className="h-9 rounded border border-slate-700 px-3 text-[11px] font-bold text-slate-300 active:border-emerald-500">가이드</button>
          <button type="button" onClick={handleEmergencyKillSwitch} disabled={loading || !currentUserId} className="h-9 rounded border border-rose-500/60 bg-rose-950/30 px-3 text-[11px] font-black text-rose-300 disabled:cursor-not-allowed disabled:opacity-50">Emergency Stop</button>
        </div>
      </section>

      {message ? (
        <div className="rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-xs leading-5 text-slate-200">
          {message}
        </div>
      ) : null}

      <section className="space-y-3 rounded-lg border border-slate-800 bg-[#0f172a] p-4">
        <div>
          <h2 className="text-sm font-black text-white">운용 설정</h2>
          <p className="mt-1 text-[11px] leading-5 text-slate-400">
            {settingsLocked ? '실거래 운용 중입니다. 실수를 막기 위해 설정이 잠겨 있습니다.' : '실거래 설정값은 선택 거래소 전체에 함께 저장됩니다.'}
          </p>
        </div>
        <fieldset disabled={settingsLocked} className={`space-y-4 ${settingsLocked ? 'opacity-60' : ''}`}>
          <div>
            <p className="text-[11px] font-bold text-slate-400">거래소</p>
            <div className="mt-2 grid grid-cols-3 gap-2">
              {Object.entries(exchangeLabels).map(([key, label]) => {
                const selected = selectedExchanges.includes(key)
                return (
                  <button
                    key={key}
                    type="button"
                    onClick={() => toggleExchange(key)}
                    className={`h-10 rounded border px-2 text-[11px] font-black transition ${selected ? 'border-emerald-500 bg-emerald-500/15 text-emerald-300' : 'border-slate-700 bg-slate-950 text-slate-400'}`}
                  >
                    {selected ? '✓ ' : ''}{label}
                  </button>
                )
              })}
            </div>
          </div>

          <label className="block text-[11px] font-bold text-slate-400">
            위탁 할당 자금
            <input type="number" value={capital} onChange={(event) => setCapital(Number(event.target.value))} className="mt-2 h-10 w-full rounded border border-slate-700 bg-slate-950 px-3 text-base font-bold text-white outline-none focus:border-emerald-500" />
          </label>

          <div>
            <p className="text-[11px] font-bold text-slate-400">리스크 프리셋</p>
            <div className="mt-2 grid grid-cols-3 gap-2">
              {Object.entries({ conservative: '보수', neutral: '중립', aggressive: '공격' }).map(([key, label]) => (
                <button key={key} type="button" onClick={() => applyRiskPreset(key)} className={`h-9 rounded border text-[11px] font-black ${riskPreset === key ? 'border-emerald-500 bg-emerald-500/15 text-emerald-300' : 'border-slate-700 bg-slate-950 text-slate-400'}`}>
                  {label}
                </button>
              ))}
            </div>
          </div>

          <div className="space-y-2">
            <RiskSlider label="목표 익절" valueText={`+${riskSettings.takeProfitPct.toFixed(1)}%`} accentClassName="accent-emerald-500" inputProps={{ 'aria-label': '목표 익절', type: 'range', min: '1', max: '20', step: '0.5', value: riskSettings.takeProfitPct, onChange: (event) => updateRiskSetting('takeProfitPct', event.target.value) }} />
            <RiskSlider label="포지션 손절" valueText={`${riskSettings.stopLossPct.toFixed(1)}%`} accentClassName="accent-rose-500" inputProps={{ 'aria-label': '포지션 손절', type: 'range', min: '-10', max: '-0.5', step: '0.5', value: riskSettings.stopLossPct, onChange: (event) => updateRiskSetting('stopLossPct', event.target.value) }} />
            <RiskSlider label="최소 확신도" valueText={formatPercent(riskSettings.minSignalConfidence * 100, 0)} accentClassName="accent-sky-500" inputProps={{ 'aria-label': '최소 확신도', type: 'range', min: '0.3', max: '0.95', step: '0.01', value: riskSettings.minSignalConfidence, onChange: (event) => updateRiskSetting('minSignalConfidence', event.target.value) }} />
            <RiskSlider label="1회 투자 비중" valueText={formatPercent(riskSettings.positionSizePct, 0)} accentClassName="accent-violet-500" inputProps={{ 'aria-label': '1회 투자 비중', type: 'range', min: '1', max: '30', step: '1', value: riskSettings.positionSizePct, onChange: (event) => updateRiskSetting('positionSizePct', event.target.value) }} />
            <RiskSlider label="일간 손실 한도" valueText={`${riskSettings.dailyMddLimitPct.toFixed(1)}%`} accentClassName="accent-amber-500" inputProps={{ 'aria-label': '일간 손실 한도', type: 'range', min: '-10', max: '-0.5', step: '0.5', value: riskSettings.dailyMddLimitPct, onChange: (event) => updateRiskSetting('dailyMddLimitPct', event.target.value) }} />
          </div>

          {selectedExchanges.includes('toss') ? (
            <div className="space-y-3 rounded-lg border border-slate-800 bg-slate-950/60 p-3">
              <p className="text-[11px] font-black text-slate-300">토스 주식 선별 조건</p>
              <div className="grid grid-cols-3 gap-2">
                {[['KR', '국내'], ['US', '미국'], ['ALL', '전체']].map(([value, label]) => (
                  <button key={value} type="button" onClick={() => setAssetScope(value)} className={`h-9 rounded border text-[11px] font-black ${assetScope === value ? 'border-emerald-500 bg-emerald-500/15 text-emerald-300' : 'border-slate-700 text-slate-400'}`}>
                    {label}
                  </button>
                ))}
              </div>
              <label className="block text-[11px] font-bold text-slate-400">
                최대 보유 종목 수
                <input type="number" min="1" max="20" value={maxOpenPositions} onChange={(event) => setMaxOpenPositions(Number(event.target.value))} className="mt-2 h-10 w-full rounded border border-slate-700 bg-slate-900 px-3 text-base text-white outline-none" />
              </label>
              {assetScope === 'ALL' ? (
                <div className="grid grid-cols-2 gap-2">
                  <label className="text-[11px] font-bold text-slate-400">국내 배분<input type="number" min="0" max="100" value={krAllocation} onChange={(event) => setKrAllocation(Number(event.target.value))} className="mt-1 h-10 w-full rounded border border-slate-700 bg-slate-900 px-3 text-base text-white outline-none" /></label>
                  <label className="text-[11px] font-bold text-slate-400">미국 배분<input type="number" min="0" max="100" value={usAllocation} onChange={(event) => setUsAllocation(Number(event.target.value))} className="mt-1 h-10 w-full rounded border border-slate-700 bg-slate-900 px-3 text-base text-white outline-none" /></label>
                </div>
              ) : null}
            </div>
          ) : null}
        </fieldset>
      </section>

      {(selectedExchanges.includes('coinone') || selectedExchanges.includes('binance')) ? (
        <section className="space-y-3 rounded-lg border border-slate-800 bg-[#0f172a] p-4">
          <div className="flex items-center justify-between gap-3">
            <h2 className="text-sm font-black text-white">코인 후보</h2>
            <button type="button" onClick={fetchCryptoCandidates} disabled={cryptoCandidatesLoading} className="rounded-lg border border-slate-700 px-3 py-2 text-[11px] font-bold text-slate-200 disabled:opacity-50">
              {cryptoCandidatesLoading ? '확인 중' : '새로고침'}
            </button>
          </div>
          {cryptoCandidates.length ? cryptoCandidates.map((candidate) => (
            <CandidateCard key={`${candidate.exchange}-${candidate.symbol}`} eyebrow={exchangeLabels[candidate.exchange] || candidate.exchange} symbol={candidate.symbol} confidence={candidate.confidence_score} reason={candidate.selection_reason} />
          )) : (
            <p className="rounded-lg border border-slate-800 bg-slate-950/60 p-4 text-center text-xs text-slate-500">현재 조건을 통과한 코인 후보가 없습니다.</p>
          )}
          {Object.entries(cryptoSnapshots).filter(([, snapshot]) => !snapshot.candidates?.length).map(([exchange, snapshot]) => (
            <AvailabilityNotice key={exchange} title={exchangeLabels[exchange] || exchange} availability={snapshot.availability} />
          ))}
        </section>
      ) : null}

      {selectedExchanges.includes('binance') ? (
        <section className="space-y-3 rounded-lg border border-sky-900/70 bg-[#0f172a] p-4">
          <div className="flex items-center justify-between gap-3">
            <h2 className="text-sm font-black text-white">바이낸스 숏 모델</h2>
            <button type="button" onClick={fetchCryptoShortPerformance} disabled={cryptoShortLoading} className="rounded-lg border border-slate-700 px-3 py-2 text-[11px] font-bold text-slate-200 disabled:opacity-50">
              {cryptoShortLoading ? '확인 중' : '새로고침'}
            </button>
          </div>
          {cryptoShortPerformance ? (
            <div className="grid grid-cols-2 gap-2">
              <div className="rounded-lg border border-slate-800 bg-slate-950/70 p-3"><p className="text-[10px] text-slate-500">운영 상태</p><p className={`mt-1 text-xs font-black ${cryptoShortPerformance.status === 'READY_FOR_REVIEW' ? 'text-emerald-300' : 'text-amber-300'}`}>{cryptoShortPerformance.status === 'READY_FOR_REVIEW' ? '운영 검토 가능' : cryptoShortPerformance.status === 'TRAINING_PENDING' ? '학습 대기' : cryptoShortPerformance.status === 'BACKTEST_PENDING' ? '검증 대기' : '실거래 보류'}</p></div>
              <div className="rounded-lg border border-slate-800 bg-slate-950/70 p-3"><p className="text-[10px] text-slate-500">ROC-AUC</p><p className="mt-1 font-mono text-xs font-black text-white">{Number(cryptoShortPerformance.metrics?.roc_auc || 0).toFixed(3)}</p></div>
              <div className="rounded-lg border border-slate-800 bg-slate-950/70 p-3"><p className="text-[10px] text-slate-500">비용 반영 평균 수익</p><p className="mt-1 font-mono text-xs font-black text-white">{formatPercent(Number(cryptoShortPerformance.backtest?.top_avg_future_return_net || 0) * 100, 2)}</p></div>
              <div className="rounded-lg border border-slate-800 bg-slate-950/70 p-3"><p className="text-[10px] text-slate-500">순승률</p><p className="mt-1 font-mono text-xs font-black text-white">{formatPercent(Number(cryptoShortPerformance.backtest?.selection_win_rate_net || 0) * 100)}</p></div>
              <div className="col-span-2 rounded-lg border border-slate-800 bg-slate-950/70 p-3"><p className="text-[10px] text-slate-500">최대 낙폭 / 검증 건수</p><p className="mt-1 font-mono text-xs font-black text-white">{formatPercent(Number(cryptoShortPerformance.backtest?.max_drawdown_net || 0) * 100)} / {Number(cryptoShortPerformance.backtest?.selected_rows || 0)}</p></div>
            </div>
          ) : <p className="text-xs text-slate-500">숏 모델 성능 정보가 없습니다.</p>}
          {cryptoShortPerformance?.message ? <p className="rounded-lg border border-amber-900/70 bg-amber-950/20 px-3 py-2 text-[11px] leading-5 text-amber-100">{cryptoShortPerformance.message}</p> : null}
        </section>
      ) : null}

      {selectedExchanges.includes('toss') ? (
        <section className="space-y-3 rounded-lg border border-slate-800 bg-[#0f172a] p-4">
          <div className="flex items-center justify-between gap-3">
            <h2 className="text-sm font-black text-white">주식 후보</h2>
            <button type="button" onClick={fetchStockCandidates} disabled={candidatesLoading} className="rounded-lg border border-slate-700 px-3 py-2 text-[11px] font-bold text-slate-200 disabled:opacity-50">
              {candidatesLoading ? '확인 중' : '새로고침'}
            </button>
          </div>
          {stockCandidates.length ? stockCandidates.map((candidate) => (
            <CandidateCard key={`${candidate.market}-${candidate.symbol}`} eyebrow={candidate.market === 'KR' ? '국내' : '미국'} symbol={candidate.symbol} confidence={candidate.confidence_score} reason={candidate.selection_reason || '활성 ML 매수 신호'} />
          )) : (
            <p className="rounded-lg border border-slate-800 bg-slate-950/60 p-4 text-center text-xs text-slate-500">현재 조건을 통과한 주식 후보가 없습니다.</p>
          )}
          {!stockCandidates.length && Object.keys(stockAvailability).length > 0 ? Object.entries(stockAvailability).map(([market, availability]) => (
            <AvailabilityNotice key={market} title={market === 'KR' ? '국내주식' : '미국주식'} availability={availability} />
          )) : null}
        </section>
      ) : null}

      <section className="rounded-lg border border-slate-800 bg-slate-950 p-3">
        <div className="flex flex-col gap-2 text-[11px] leading-5 sm:flex-row sm:items-center sm:justify-between">
          <p className="text-slate-300">
            <strong>자동선별 Guard:</strong> 코인은 거래소별 ML 후보와 상장 상태를, 주식은 국내·미국 활성 모델의 정책 통과 후보를 확인한 뒤에만 주문 후보로 만듭니다.
          </p>
          <span className="w-fit shrink-0 rounded border border-emerald-800 bg-emerald-950 px-2 py-1 font-mono text-[10px] text-emerald-300">
            Exchange Filter Active
          </span>
        </div>
      </section>

      <section className="space-y-3 rounded-lg border border-slate-800 bg-[#0f172a] p-4">
        <div className="flex items-center justify-between gap-3">
          <h2 className="text-sm font-black text-white">체결 기록</h2>
          <span className="text-[11px] font-bold text-slate-500">{tradeLogs.length}건</span>
        </div>
        {tradeLogs.length ? tradeLogs.map((log) => (
          <article key={log.id} className="rounded-lg border border-slate-800 bg-slate-950/70 p-3">
            <div className="flex items-start justify-between gap-3">
              <div>
                <p className="text-[10px] font-bold uppercase text-slate-500">{log.exchange_type}</p>
                <h3 className="mt-1 text-base font-black text-white">{log.symbol}</h3>
              </div>
              <span className={`rounded border px-2 py-1 text-[10px] font-black ${log.side === 'BUY' ? 'border-rose-500/40 text-rose-300' : 'border-blue-500/40 text-blue-300'}`}>{log.side}</span>
            </div>
            <dl className="mt-3 grid grid-cols-2 gap-2 text-[11px]">
              <div><dt className="text-slate-500">시각</dt><dd className="mt-1 font-mono text-slate-200">{new Date(log.created_at).toLocaleTimeString()}</dd></div>
              <div><dt className="text-slate-500">확신도</dt><dd className="mt-1 font-mono text-emerald-300">{formatPercent(Number(log.confidence_score || 0) * 100)}</dd></div>
              <div><dt className="text-slate-500">체결가</dt><dd className="mt-1 font-mono text-slate-200">{formatCurrency(log.executed_price)}</dd></div>
              <div><dt className="text-slate-500">총 금액</dt><dd className="mt-1 font-mono text-slate-200">{formatCurrency(log.total_amount)}</dd></div>
              <div className="col-span-2"><dt className="text-slate-500">상태</dt><dd className="mt-1 w-fit rounded border border-emerald-800 bg-emerald-950 px-2 py-0.5 text-[10px] font-black text-emerald-400">{log.status}</dd></div>
            </dl>
          </article>
        )) : (
          <div className="rounded-lg border border-slate-800 bg-slate-950/60 p-4 text-center text-xs leading-5 text-slate-500">
            {isActive ? (
              <div className="space-y-2">
                <p className="font-bold text-emerald-400">AI가 {selectedExchanges.map((exchange) => exchange.toUpperCase()).join(' · ')} {selectedExchanges.length}개 거래소를 5초 간격으로 실시간 탐색 중입니다.</p>
                <p>현재 설정된 <strong>최소 확신도 {(riskSettings.minSignalConfidence * 100).toFixed(0)}% / 목표익절 +{riskSettings.takeProfitPct.toFixed(1)}% / 포지션 손절 {riskSettings.stopLossPct.toFixed(1)}%</strong> 을 달성한 고확신 상승 종목이 포착되면 자동으로 주문이 체결됩니다. 확신도가 미달하는 시점에는 자금을 안전하게 보존하기 위해 매수를 보류하고 있습니다.</p>
              </div>
            ) : (
              '운용 시작 후 AI가 매수를 진행하면 체결 기록이 여기에 표시됩니다.'
            )}
          </div>
        )}
      </section>

      {isGuideOpen ? (
        <div className="fixed inset-0 z-[80] flex items-center justify-center bg-slate-950/80 p-4" onClick={() => setIsGuideOpen(false)}>
          <section role="dialog" aria-modal="true" className="max-h-[calc(100vh-2rem)] w-full overflow-y-auto rounded-lg border border-slate-700 bg-slate-900 p-5 shadow-2xl" onClick={(event) => event.stopPropagation()}>
            <div className="flex items-start justify-between gap-3">
              <div>
                <h2 className="text-base font-black text-white">AI 위탁 자동투자 사용 가이드</h2>
                <p className="mt-1 text-xs leading-5 text-slate-400">종목은 직접 지정하지 않습니다. AI가 거래소별 후보를 자동 선별합니다.</p>
              </div>
              <button type="button" onClick={() => setIsGuideOpen(false)} className="rounded border border-slate-600 px-3 py-1.5 text-xs font-bold text-slate-200">닫기</button>
            </div>
            <div className="mt-5 space-y-4 text-sm leading-6 text-slate-300">
              <section>
                <h3 className="font-black text-emerald-300">1. 자동선별 거래소와 자금을 정합니다.</h3>
                <p className="mt-1">코인원·바이낸스를 선택하면 코인 후보를, 토스 주식을 선택하면 국내·미국 주식 후보를 AI가 찾습니다. 현재 선택된 거래소는 {selectedExchangeText}이며, 운용 한도는 {formatCurrency(capital)}입니다.</p>
              </section>
              <section>
                <h3 className="font-black text-emerald-300">2. 리스크 한도를 조정하고 설정을 저장합니다.</h3>
                <p className="mt-1">목표 익절, 포지션 손절, 최소 확신도, 1회 투자 비중, 일간 손실 한도를 정합니다. 현재 최소 확신도는 {(riskSettings.minSignalConfidence * 100).toFixed(0)}%이며, 이 값보다 낮은 신호는 매수하지 않습니다. 값을 바꾼 뒤에는 설정 저장을 누른 다음 운용을 시작하세요. 운용 중에는 설정이 잠깁니다.</p>
              </section>
              <section>
                <h3 className="font-black text-emerald-300">3. 후보를 확인한 뒤 운용을 시작합니다.</h3>
                <p className="mt-1">후보 목록에는 해당 시점에 조건을 통과한 종목만 표시됩니다. 비어 있으면 오류가 아니라, 현재 시점에 모델 확신도와 정책 조건을 함께 통과한 종목이 없다는 뜻입니다. AI 위탁 운용 시작을 누르면 선택한 거래소를 주기적으로 다시 스캔합니다.</p>
              </section>
              <section>
                <h3 className="font-black text-emerald-300">4. 체결 기록과 중지를 확인합니다.</h3>
                <p className="mt-1">조건을 통과해 주문이 체결되면 거래 기록에 남습니다. 잠시 멈추려면 운용 일시정지를, 전체 운용을 즉시 중단하려면 Emergency Stop을 사용합니다.</p>
              </section>
              <p className="rounded border border-amber-900/70 bg-amber-950/20 p-3 text-xs text-amber-100">최소 확신도를 낮추면 후보 수는 늘 수 있지만 신호 품질이 함께 보장되지는 않습니다. 후보가 없을 때는 임의 종목을 매수하지 않고 다음 스캔까지 보류합니다.</p>
            </div>
          </section>
        </div>
      ) : null}
    </div>
  )
}
