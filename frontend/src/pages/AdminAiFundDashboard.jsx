import { useEffect, useState } from 'react'
import { supabase } from '../supabaseClient'
import { buildAiFundConfigPayloads, buildTossStockSelectionPayload, canEditAiFundSettings, getNextAiFundActiveState } from './adminAiFundDashboardModel'

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:5050'
const availabilityLabel = {
  POLICY_BLOCKED: '정책상 보류',
  NO_LONG_SIGNAL: '매수 신호 없음',
  LOW_CONFIDENCE: '확신도 부족',
  NO_PREDICTIONS: '예측 데이터 없음',
}
const riskPresetDefaults = {
  conservative: { takeProfitPct: 3, stopLossPct: -1, minSignalConfidence: 0.85, positionSizePct: 5, dailyMddLimitPct: -1 },
  neutral: { takeProfitPct: 5, stopLossPct: -2, minSignalConfidence: 0.75, positionSizePct: 10, dailyMddLimitPct: -2 },
  aggressive: { takeProfitPct: 8, stopLossPct: -4, minSignalConfidence: 0.65, positionSizePct: 20, dailyMddLimitPct: -4 },
}

export default function AdminAiFundDashboard({ userId }) {
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
        if (session?.user?.id) {
          setCurrentUserId(session.user.id)
        }
      })
    }
  }, [currentUserId])

  const toggleExchange = (exKey) => {
    if (settingsLocked) return
    setMessage('')
    setSelectedExchanges((prev) => {
      if (prev.includes(exKey)) {
        if (prev.length <= 1) {
          setMessage('최소 1개 이상의 운용 거래소를 선택해야 합니다.')
          return prev
        }
        return prev.filter((item) => item !== exKey)
      } else {
        return [...prev, exKey]
      }
    })
  }

  useEffect(() => {
    if (!currentUserId) return

    const fetchConfigAndLogs = async () => {
      const { data: configData } = await supabase
        .from('admin_ai_fund_configs')
        .select('*')
        .eq('user_id', currentUserId)

      if (configData && configData.length > 0) {
        const activeExchanges = configData
          .filter((cfg) => cfg.is_active)
          .map((cfg) => cfg.exchange_type)
        if (activeExchanges.length > 0) {
          setSelectedExchanges(activeExchanges)
          setIsActive(true)
        } else {
          setSelectedExchanges(configData.map((cfg) => cfg.exchange_type))
          setIsActive(false)
        }

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

      if (logsData) {
        setTradeLogs(logsData)
      }
      setLastCheckTime(new Date().toLocaleTimeString())
    }

    fetchConfigAndLogs()

    // 5-second live ticker for active monitoring pulse
    const tickerInterval = setInterval(() => {
      setLastCheckTime(new Date().toLocaleTimeString())
    }, 5000)

    // Realtime Subscriptions
    const configChannel = supabase
      .channel('admin-ai-fund-changes')
      .on(
        'postgres_changes',
        {
          event: '*',
          schema: 'public',
          table: 'admin_ai_fund_configs',
          filter: `user_id=eq.${currentUserId}`,
        },
        (payload) => {
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
        }
      )
      .subscribe()

    const logChannel = supabase
      .channel('admin-ai-logs-changes')
      .on(
        'postgres_changes',
        {
          event: 'INSERT',
          schema: 'public',
          table: 'admin_ai_trade_logs',
          filter: `user_id=eq.${currentUserId}`,
        },
        (payload) => {
          if (payload.new) {
            setTradeLogs((prev) => [payload.new, ...prev.slice(0, 19)])
          }
          setLastCheckTime(new Date().toLocaleTimeString())
        }
      )
      .subscribe()

    return () => {
      clearInterval(tickerInterval)
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

  const handleToggleActive = async (nextActive = !isActive, completionMessage = '') => {
    if (nextActive && !window.confirm(`실제 주문을 시작합니다.\n\n거래소: ${selectedExchanges.join(', ')}\n전체 운용 한도: ${Number(capital || 0).toLocaleString()}원\n1회 투자 비중: ${riskSettings.positionSizePct.toFixed(0)}%\n\n계속하시겠습니까?`)) {
      return
    }
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
      setMessage(
        completionMessage || (nextActive
          ? `선택한 ${selectedExchanges.length}개 거래소의 AI 자동선별 운용을 시작했습니다.`
          : 'AI 위탁 운용이 일시정지되었습니다.')
      )
      if (nextActive) fetchStockCandidates()
      if (nextActive) fetchCryptoCandidates()
    } catch (err) {
      setMessage(`오류: ${err.message}`)
    } finally {
      setLoading(false)
    }
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

  const handleEmergencyKillSwitch = async () => {
    if (!confirm('긴급 셧다운을 실행하시겠습니까? 모든 AI 자동 매매가 즉시 정지됩니다.')) return
    setLoading(true)
    try {
      const { error } = await supabase
        .from('admin_ai_fund_configs')
        .update({ is_active: false })
        .eq('user_id', currentUserId)

      if (error) throw error
      setIsActive(false)
      setMessage('[긴급 셧다운 완료] 모든 AI 위탁 운용이 정지되었습니다.')
    } catch (err) {
      setMessage(`셧다운 오류: ${err.message}`)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="p-6 max-w-5xl mx-auto bg-slate-900 text-white rounded-xl shadow-2xl border border-slate-800 space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between border-b border-slate-800 pb-4">
        <div>
          <div className="flex flex-wrap items-center gap-2">
            <h1 className="text-xl font-bold text-emerald-400">관리자 전용 AI 위탁 자동투자 대시보드</h1>
            <button type="button" onClick={() => setIsGuideOpen(true)} className="rounded border border-emerald-700 bg-emerald-950/50 px-2.5 py-1 text-[11px] font-semibold text-emerald-300 transition-colors hover:border-emerald-400 hover:text-emerald-100">가이드 보기</button>
          </div>
          <p className="text-xs text-slate-400 mt-1">
            Human-on-the-Loop 모델 기반 AI 자율 운용 및 리스크 관리 시스템
          </p>
        </div>
        <button
          onClick={handleEmergencyKillSwitch}
          disabled={loading}
          className="px-4 py-2 bg-rose-600 hover:bg-rose-700 text-white font-bold text-xs rounded-lg shadow-lg transition-colors border border-rose-500 animate-pulse cursor-pointer"
        >
          Emergency Stop (Kill-Switch)
        </button>
      </div>

      {isGuideOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/80 p-4" onClick={() => setIsGuideOpen(false)}>
          <section role="dialog" aria-modal="true" aria-labelledby="ai-fund-guide-title" className="max-h-[calc(100vh-2rem)] w-full max-w-2xl overflow-y-auto rounded-lg border border-slate-700 bg-slate-900 shadow-2xl" onClick={(event) => event.stopPropagation()}>
            <div className="sticky top-0 flex items-center justify-between border-b border-slate-800 bg-slate-900 px-5 py-4">
              <div>
                <h2 id="ai-fund-guide-title" className="text-base font-bold text-white">AI 위탁 자동투자 사용 가이드</h2>
                <p className="mt-1 text-xs text-slate-400">종목은 직접 지정하지 않습니다. AI가 거래소별 후보를 자동 선별합니다.</p>
              </div>
              <button type="button" onClick={() => setIsGuideOpen(false)} className="rounded border border-slate-600 px-3 py-1.5 text-xs font-semibold text-slate-200 hover:border-slate-400">닫기</button>
            </div>

            <div className="space-y-5 p-5 text-sm leading-6 text-slate-300">
              <section>
                <h3 className="font-bold text-emerald-300">1. 자동선별 거래소와 자금을 정합니다.</h3>
                <p className="mt-1">코인원·바이낸스를 선택하면 코인 후보를, 토스 주식을 선택하면 국내·미국 주식 후보를 AI가 찾습니다. 현재 선택된 거래소는 {selectedExchanges.map((exchange) => ({ coinone: '코인원', binance: '바이낸스', toss: '토스 주식' }[exchange])).join(', ')}이며, 운용 한도는 {Number(capital || 0).toLocaleString()}원입니다.</p>
              </section>

              <section>
                <h3 className="font-bold text-emerald-300">2. 리스크 한도를 조정하고 설정을 저장합니다.</h3>
                <p className="mt-1">목표 익절, 포지션 손절, 최소 확신도, 1회 투자 비중, 일간 손실 한도를 정합니다. 현재 최소 확신도는 {(riskSettings.minSignalConfidence * 100).toFixed(0)}%이며, 이 값보다 낮은 신호는 매수하지 않습니다. 값을 바꾼 뒤에는 <strong className="text-white">설정 저장</strong>을 누른 다음 운용을 시작하세요. 운용 중에는 설정이 잠깁니다.</p>
              </section>

              <section>
                <h3 className="font-bold text-emerald-300">3. 후보를 확인한 뒤 운용을 시작합니다.</h3>
                <p className="mt-1">후보 표에는 해당 시점에 조건을 통과한 종목만 표시됩니다. 비어 있으면 오류가 아니라, 현재 시점에 모델 확신도와 정책 조건을 함께 통과한 종목이 없다는 뜻입니다. <strong className="text-white">AI 위탁 운용 시작</strong>을 누르면 선택한 거래소를 주기적으로 다시 스캔합니다.</p>
              </section>

              <section>
                <h3 className="font-bold text-emerald-300">4. 체결 기록과 중지를 확인합니다.</h3>
                <p className="mt-1">조건을 통과해 주문이 체결되면 아래 거래 기록에 남습니다. 잠시 멈추려면 <strong className="text-white">운용 일시정지</strong>를, 전체 운용을 즉시 중단하려면 오른쪽 위 <strong className="text-rose-300">Emergency Stop</strong>을 사용합니다.</p>
              </section>

              <div className="border-l-2 border-amber-500 bg-amber-950/30 px-4 py-3 text-xs text-amber-100">
                최소 확신도를 낮추면 후보 수는 늘 수 있지만 신호 품질이 함께 보장되지는 않습니다. 후보가 없을 때는 임의 종목을 매수하지 않고 다음 스캔까지 보류합니다.
              </div>
            </div>
          </section>
        </div>
      )}

      {/* Live Status Bar */}
      <div className="p-4 rounded-lg bg-slate-950 border border-slate-800 flex flex-col md:flex-row items-start md:items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <span className="relative flex h-3.5 w-3.5">
            <span className={`animate-ping absolute inline-flex h-full w-full rounded-full opacity-75 ${isActive ? 'bg-emerald-400' : 'bg-slate-600'}`} />
            <span className={`relative inline-flex rounded-full h-3.5 w-3.5 ${isActive ? 'bg-emerald-500' : 'bg-slate-600'}`} />
          </span>
          <div>
            <div className="flex items-center gap-2">
              <span className="text-xs font-bold text-slate-200">
                AI 운용 상태: {isActive ? `운용 중 (${selectedExchanges.join(', ')} 다중 거래소 감시)` : '운용 대기/일시정지'}
              </span>
              {isActive && (
                <span className="px-2 py-0.5 rounded text-[10px] bg-emerald-950 text-emerald-400 border border-emerald-800 font-mono animate-pulse">
                  Live Scanner Active
                </span>
              )}
            </div>

            <p className="text-[11px] text-slate-400 mt-1">
              {isActive
                ? `LightGBM ML 엔진 감시 중 | 선택 거래소: ${selectedExchanges.join(', ')} | 최소 확신도: ${(riskSettings.minSignalConfidence * 100).toFixed(0)}% 이상 | 목표익절: +${riskSettings.takeProfitPct.toFixed(1)}% | 포지션 손절: ${riskSettings.stopLossPct.toFixed(1)}%`
                : '운용 시작 시 코인은 거래소별 ML 후보에서, 주식은 국내·미국 활성 모델 후보에서 자동으로 종목을 선별합니다.'}
            </p>
          </div>
        </div>
        <div className="text-right">
          <span className="text-[11px] font-mono text-slate-400 block">최근 실시간 점검: {lastCheckTime}</span>
          <span className="text-[10px] text-slate-500 block mt-0.5">스캔 주기: 매 5초 실시간 업데이트</span>
        </div>
      </div>

      {message && (
        <div className="p-3 text-xs rounded-md bg-slate-800 border border-slate-700 font-medium text-emerald-300">
          {message}
        </div>
      )}

      <section className="sticky top-3 z-20 space-y-3 rounded-lg border border-emerald-900/80 bg-slate-900/95 p-4 shadow-xl backdrop-blur">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h2 className="text-sm font-bold text-white">운용 제어</h2>
            <p className="mt-1 text-[11px] text-slate-400">{settingsLocked ? '실거래 운용 중입니다. 실수를 막기 위해 설정이 잠겨 있습니다.' : '실거래 설정값은 선택 거래소 전체에 함께 저장됩니다.'}</p>
          </div>
          <div className="flex gap-2">
            <button type="button" onClick={() => handleToggleActive(false, '실거래 설정을 저장했습니다.')} disabled={loading || settingsLocked} className="rounded-lg border border-slate-600 px-3 py-2.5 text-xs font-semibold text-slate-200 hover:border-emerald-500 disabled:cursor-not-allowed disabled:opacity-50">설정 저장</button>
            <button
              onClick={() => handleToggleActive(getNextAiFundActiveState(isActive))}
              disabled={loading}
              className={`min-w-36 rounded-lg px-5 py-2.5 text-xs font-bold shadow-md transition-colors ${isActive ? 'bg-amber-600 text-white hover:bg-amber-700' : 'bg-emerald-600 text-white hover:bg-emerald-700'} disabled:cursor-not-allowed disabled:opacity-50`}
            >
              {loading ? '설정 저장 중' : isActive ? '운용 일시정지' : 'AI 위탁 운용 시작'}
            </button>
          </div>
        </div>

        <fieldset disabled={settingsLocked} className={`space-y-3 ${settingsLocked ? 'opacity-55' : ''}`}>
        <div className="grid gap-3 lg:grid-cols-[1.5fr_0.7fr]">
          <div>
            <p className="text-[11px] font-semibold text-slate-300">자동선별 거래소</p>
            <div className="mt-2 grid grid-cols-3 gap-2">
              {[
                { key: 'coinone', label: '코인원' },
                { key: 'toss', label: '토스 주식' },
                { key: 'binance', label: '바이낸스' },
              ].map((item) => {
                const isSelected = selectedExchanges.includes(item.key)
                return <button key={item.key} type="button" onClick={() => toggleExchange(item.key)} className={`rounded border px-2 py-2 text-xs font-semibold transition ${isSelected ? 'border-emerald-500 bg-emerald-500/15 text-emerald-300' : 'border-slate-700 bg-slate-950 text-slate-400 hover:border-slate-600'}`}>{isSelected && '✓ '}{item.label}</button>
              })}
            </div>
          </div>
          <label className="text-[11px] font-semibold text-slate-300">위탁 할당 자금 (KRW)
            <input type="number" value={capital} onChange={(event) => setCapital(Number(event.target.value))} className="mt-2 w-full rounded border border-slate-700 bg-slate-950 p-2 text-sm font-mono text-white" />
          </label>
        </div>

        <div className="border-t border-slate-800 pt-3">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <p className="text-[11px] font-semibold text-slate-300">리스크 제어 {riskPreset === 'custom' && <span className="ml-1 text-emerald-300">사용자 지정</span>}</p>
            <div className="flex gap-1.5">
              {Object.entries({ conservative: '보수', neutral: '중립', aggressive: '공격' }).map(([key, label]) => <button key={key} type="button" onClick={() => applyRiskPreset(key)} className={`rounded border px-2 py-1 text-[10px] font-semibold ${riskPreset === key ? 'border-emerald-500 bg-emerald-500/15 text-emerald-300' : 'border-slate-700 text-slate-400 hover:border-slate-600'}`}>{label}</button>)}
            </div>
          </div>
          <div className="mt-3 grid gap-3 sm:grid-cols-2 xl:grid-cols-5">
            <label className="text-[10px] text-slate-400">목표 익절 <span className="float-right text-emerald-300">+{riskSettings.takeProfitPct.toFixed(1)}%</span><input aria-label="목표 익절" type="range" min="1" max="20" step="0.5" value={riskSettings.takeProfitPct} onChange={(event) => updateRiskSetting('takeProfitPct', event.target.value)} className="mt-2 w-full accent-emerald-500" /></label>
            <label className="text-[10px] text-slate-400">포지션 손절 <span className="float-right text-rose-300">{riskSettings.stopLossPct.toFixed(1)}%</span><input aria-label="포지션 손절" type="range" min="-10" max="-0.5" step="0.5" value={riskSettings.stopLossPct} onChange={(event) => updateRiskSetting('stopLossPct', event.target.value)} className="mt-2 w-full accent-rose-500" /></label>
            <label className="text-[10px] text-slate-400">최소 확신도 <span className="float-right text-sky-300">{(riskSettings.minSignalConfidence * 100).toFixed(0)}%</span><input aria-label="최소 확신도" type="range" min="0.3" max="0.95" step="0.01" value={riskSettings.minSignalConfidence} onChange={(event) => updateRiskSetting('minSignalConfidence', event.target.value)} className="mt-2 w-full accent-sky-500" /></label>
            <label className="text-[10px] text-slate-400">1회 투자 비중 <span className="float-right text-violet-300">{riskSettings.positionSizePct.toFixed(0)}%</span><input aria-label="1회 투자 비중" type="range" min="1" max="30" step="1" value={riskSettings.positionSizePct} onChange={(event) => updateRiskSetting('positionSizePct', event.target.value)} className="mt-2 w-full accent-violet-500" /></label>
            <label className="text-[10px] text-slate-400">일간 손실 한도 <span className="float-right text-amber-300">{riskSettings.dailyMddLimitPct.toFixed(1)}%</span><input aria-label="일간 손실 한도" type="range" min="-10" max="-0.5" step="0.5" value={riskSettings.dailyMddLimitPct} onChange={(event) => updateRiskSetting('dailyMddLimitPct', event.target.value)} className="mt-2 w-full accent-amber-500" /></label>
          </div>
        </div>
        </fieldset>
      </section>

      {(selectedExchanges.includes('coinone') || selectedExchanges.includes('binance')) && (
        <section className="border border-slate-800 bg-slate-950 p-4 space-y-4">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <h2 className="text-sm font-bold text-white">코인 자동선별</h2>
              <p className="mt-1 text-[11px] text-slate-400">현재 위험도 프리셋의 확신도 기준을 통과한 코인만 주문 후보로 표시합니다.</p>
            </div>
            <button type="button" onClick={fetchCryptoCandidates} disabled={cryptoCandidatesLoading} className="rounded border border-slate-700 px-3 py-2 text-xs font-semibold text-slate-200 hover:border-emerald-500 disabled:opacity-50">
              {cryptoCandidatesLoading ? '후보 확인 중' : '후보 새로고침'}
            </button>
          </div>
          <div className="overflow-x-auto border border-slate-800">
            <table className="w-full text-left text-xs">
              <thead className="border-b border-slate-800 text-slate-400"><tr><th className="px-3 py-2">운용 거래소</th><th className="px-3 py-2">AI 후보</th><th className="px-3 py-2">확신도</th><th className="px-3 py-2">선별 근거</th></tr></thead>
              <tbody className="divide-y divide-slate-800">
                {Object.entries(cryptoSnapshots).flatMap(([exchange, snapshot]) => (snapshot.candidates || []).map((candidate) => <tr key={`${exchange}-${candidate.symbol}`}><td className="px-3 py-2 font-semibold uppercase text-slate-300">{exchange}</td><td className="px-3 py-2 font-bold text-white">{candidate.symbol}</td><td className="px-3 py-2 font-mono text-emerald-300">{(Number(candidate.confidence_score) * 100).toFixed(1)}%</td><td className="px-3 py-2 text-slate-400">{candidate.selection_reason}</td></tr>))}
                {!Object.values(cryptoSnapshots).some((snapshot) => snapshot.candidates?.length) && <tr><td colSpan="4" className="px-3 py-5 text-center text-slate-500">현재 조건을 통과한 코인 후보가 없습니다.</td></tr>}
              </tbody>
            </table>
          </div>
          {Object.entries(cryptoSnapshots).filter(([, snapshot]) => !snapshot.candidates?.length).map(([exchange, snapshot]) => (
            <div key={exchange} className="border border-amber-900/70 bg-amber-950/20 px-3 py-2 text-xs text-amber-100">
              <p className="font-semibold uppercase">{exchange}: {availabilityLabel[snapshot.availability?.status] || '후보 보류'}</p>
              <p className="mt-1 text-[11px] text-slate-400">{snapshot.availability?.message || '현재 후보 상태를 확인하지 못했습니다.'}</p>
            </div>
          ))}
        </section>
      )}

      {selectedExchanges.includes('binance') && (
        <section className="border border-sky-900/70 bg-slate-950 p-4 space-y-4">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <h2 className="text-sm font-bold text-white">바이낸스 선물 숏 모델</h2>
              <p className="mt-1 text-[11px] text-slate-400">하락 수익 예측 모델의 자동 학습 및 비용 반영 검증 결과입니다. 현재는 실주문과 연결되지 않습니다.</p>
            </div>
            <button type="button" onClick={fetchCryptoShortPerformance} disabled={cryptoShortLoading} className="rounded border border-slate-700 px-3 py-2 text-xs font-semibold text-slate-200 hover:border-sky-500 disabled:opacity-50">
              {cryptoShortLoading ? '성능 확인 중' : '성능 새로고침'}
            </button>
          </div>
          {cryptoShortPerformance ? (
            <div className="grid gap-3 md:grid-cols-5">
              <div className="border border-slate-800 bg-slate-900/60 p-3"><p className="text-[10px] text-slate-500">운영 상태</p><p className={`mt-1 text-xs font-bold ${cryptoShortPerformance.status === 'READY_FOR_REVIEW' ? 'text-emerald-300' : 'text-amber-300'}`}>{cryptoShortPerformance.status === 'READY_FOR_REVIEW' ? '운영 검토 가능' : cryptoShortPerformance.status === 'TRAINING_PENDING' ? '학습 대기' : cryptoShortPerformance.status === 'BACKTEST_PENDING' ? '검증 대기' : '실거래 보류'}</p></div>
              <div className="border border-slate-800 bg-slate-900/60 p-3"><p className="text-[10px] text-slate-500">ROC-AUC</p><p className="mt-1 text-xs font-mono font-bold text-white">{Number(cryptoShortPerformance.metrics?.roc_auc || 0).toFixed(3)}</p></div>
              <div className="border border-slate-800 bg-slate-900/60 p-3"><p className="text-[10px] text-slate-500">비용 반영 평균 수익</p><p className="mt-1 text-xs font-mono font-bold text-white">{(Number(cryptoShortPerformance.backtest?.top_avg_future_return_net || 0) * 100).toFixed(2)}%</p></div>
              <div className="border border-slate-800 bg-slate-900/60 p-3"><p className="text-[10px] text-slate-500">순승률</p><p className="mt-1 text-xs font-mono font-bold text-white">{(Number(cryptoShortPerformance.backtest?.selection_win_rate_net || 0) * 100).toFixed(1)}%</p></div>
              <div className="border border-slate-800 bg-slate-900/60 p-3"><p className="text-[10px] text-slate-500">최대 낙폭 / 검증 건수</p><p className="mt-1 text-xs font-mono font-bold text-white">{(Number(cryptoShortPerformance.backtest?.max_drawdown_net || 0) * 100).toFixed(1)}% / {Number(cryptoShortPerformance.backtest?.selected_rows || 0)}</p></div>
            </div>
          ) : <p className="text-xs text-slate-500">숏 모델 성능 정보를 불러오는 중입니다.</p>}
          {cryptoShortPerformance && <p className="border border-amber-900/70 bg-amber-950/20 px-3 py-2 text-[11px] text-amber-100">{cryptoShortPerformance.message}</p>}
        </section>
      )}

      {selectedExchanges.includes('toss') && (
        <section className="border border-slate-800 bg-slate-950 p-4 space-y-4">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <h2 className="text-sm font-bold text-white">토스 주식 자동선별</h2>
              <p className="mt-1 text-[11px] text-slate-400">AI가 국내·미국 활성 모델의 후보군에서 종목을 직접 고릅니다.</p>
            </div>
            <button type="button" onClick={fetchStockCandidates} disabled={candidatesLoading} className="rounded border border-slate-700 px-3 py-2 text-xs font-semibold text-slate-200 hover:border-emerald-500 disabled:opacity-50">
              {candidatesLoading ? '후보 확인 중' : '후보 새로고침'}
            </button>
          </div>
          <fieldset disabled={settingsLocked} className={`space-y-4 ${settingsLocked ? 'opacity-55' : ''}`}>
          <div className="grid gap-4 md:grid-cols-[1fr_180px]">
            <div>
              <p className="text-[11px] font-semibold text-slate-300">주식 시장 범위</p>
              <div className="mt-2 grid grid-cols-3 gap-2">
                {[['KR', '국내주식'], ['US', '미국주식'], ['ALL', '국내·미국']].map(([value, label]) => (
                  <button key={value} type="button" onClick={() => setAssetScope(value)} className={`rounded border px-3 py-2 text-xs font-semibold ${assetScope === value ? 'border-emerald-500 bg-emerald-500/15 text-emerald-300' : 'border-slate-700 text-slate-400 hover:border-slate-600'}`}>
                    {label}
                  </button>
                ))}
              </div>
            </div>
            <label className="text-[11px] font-semibold text-slate-300">최대 보유 종목 수
              <input type="number" min="1" max="20" value={maxOpenPositions} onChange={(event) => setMaxOpenPositions(Number(event.target.value))} className="mt-2 w-full rounded border border-slate-700 bg-slate-900 px-3 py-2 text-xs text-white" />
            </label>
          </div>
          {assetScope === 'ALL' && (
            <div className="grid gap-3 sm:grid-cols-2">
              <label className="text-[11px] text-slate-400">국내주식 배분 (%)<input type="number" min="0" max="100" value={krAllocation} onChange={(event) => setKrAllocation(Number(event.target.value))} className="mt-1 w-full rounded border border-slate-700 bg-slate-900 px-3 py-2 text-xs text-white" /></label>
              <label className="text-[11px] text-slate-400">미국주식 배분 (%)<input type="number" min="0" max="100" value={usAllocation} onChange={(event) => setUsAllocation(Number(event.target.value))} className="mt-1 w-full rounded border border-slate-700 bg-slate-900 px-3 py-2 text-xs text-white" /></label>
            </div>
          )}
          </fieldset>
          <div className="overflow-x-auto border border-slate-800">
            <table className="w-full text-left text-xs">
              <thead className="border-b border-slate-800 text-slate-400"><tr><th className="px-3 py-2">시장</th><th className="px-3 py-2">AI 후보</th><th className="px-3 py-2">확신도</th><th className="px-3 py-2">선별 근거</th></tr></thead>
              <tbody className="divide-y divide-slate-800">
                {stockCandidates.length ? stockCandidates.map((candidate) => <tr key={`${candidate.market}-${candidate.symbol}`}><td className="px-3 py-2 font-semibold text-slate-300">{candidate.market === 'KR' ? '국내' : '미국'}</td><td className="px-3 py-2 font-bold text-white">{candidate.symbol}</td><td className="px-3 py-2 font-mono text-emerald-300">{(Number(candidate.confidence_score) * 100).toFixed(1)}%</td><td className="px-3 py-2 text-slate-400">{candidate.selection_reason || '활성 ML 매수 신호'}</td></tr>) : <tr><td colSpan="4" className="px-3 py-5 text-center text-slate-500">현재 조건을 통과한 주식 후보가 없습니다.</td></tr>}
              </tbody>
            </table>
          </div>
          {!stockCandidates.length && Object.keys(stockAvailability).length > 0 && (
            <div className="grid gap-2 sm:grid-cols-2">
              {Object.entries(stockAvailability).map(([market, availability]) => (
                <div key={market} className="border border-amber-900/70 bg-amber-950/20 px-3 py-2 text-xs text-amber-100">
                  <p className="font-semibold">{market === 'KR' ? '국내주식' : '미국주식'}: {availabilityLabel[availability.status] || '후보 보류'}</p>
                  <p className="mt-1 text-[11px] text-slate-400">{availability.message} {availability.market_regimes?.length ? `시장 국면: ${availability.market_regimes.join(', ')}` : ''}</p>
                </div>
              ))}
            </div>
          )}
        </section>
      )}


      {/* Exchange Listing Guard Indicator */}
      <div className="p-3 bg-slate-950 rounded-lg border border-slate-800 flex items-center justify-between text-[11px]">
        <span className="text-slate-300">
          <strong>자동선별 Guard:</strong> 코인은 거래소별 ML 후보와 상장 상태를, 주식은 국내·미국 활성 모델의 정책 통과 후보를 확인한 뒤에만 주문 후보로 만듭니다.
        </span>
        <span className="px-2 py-1 rounded bg-emerald-950 text-emerald-300 border border-emerald-800 font-mono text-[10px]">
          Exchange Filter Active
        </span>
      </div>

      {/* AI Execution History Table */}

      <div className="bg-slate-950 p-4 rounded-lg border border-slate-800 space-y-3">
        <div className="flex items-center justify-between">
          <h2 className="text-xs font-bold text-slate-200">AI 실시간 자동 매매 기록 (Trade History)</h2>

          <span className="text-[11px] text-slate-500">총 {tradeLogs.length}건 기록됨</span>
        </div>

        {tradeLogs.length === 0 ? (
          <div className="p-6 text-center text-xs text-slate-400 bg-slate-900/60 rounded border border-slate-800 space-y-2">
            {isActive ? (
              <>
                <div className="flex items-center justify-center gap-2 text-emerald-400 font-bold">
                  <span className="inline-block w-2 h-2 rounded-full bg-emerald-400 animate-ping" />
                  <span>
                    AI가 {selectedExchanges.map((e) => e.toUpperCase()).join(' · ')} {selectedExchanges.length}개 거래소를 5초 간격으로 실시간 탐색 중입니다
                  </span>
                </div>
                <p className="text-[11px] text-slate-400 max-w-lg mx-auto leading-relaxed">
                  현재 설정된{' '}
                  <strong>
                    최소 확신도 {(riskSettings.minSignalConfidence * 100).toFixed(0)}% / 목표익절 +{riskSettings.takeProfitPct.toFixed(1)}% / 포지션 손절 {riskSettings.stopLossPct.toFixed(1)}%
                  </strong>
                  을 달성한 고확신 상승 종목이 포착되면 자동으로 주문이 체결됩니다. 확신도가 미달하는 시점에는 자금을 안전하게 보존하기 위해 매수를 보류하고 있습니다.
                </p>
              </>
            ) : (
              '운용 시작 후 AI가 매수를 진행하면 체결 기록이 여기에 표시됩니다.'
            )}
          </div>

        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs border-collapse">
              <thead>
                <tr className="border-b border-slate-800 text-slate-400">
                  <th className="py-2 px-3">시각</th>
                  <th className="py-2 px-3">거래소</th>
                  <th className="py-2 px-3">종목</th>
                  <th className="py-2 px-3">구분</th>
                  <th className="py-2 px-3">ML 확신도</th>
                  <th className="py-2 px-3">체결가</th>
                  <th className="py-2 px-3">총 금액</th>
                  <th className="py-2 px-3">상태</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800/60">
                {tradeLogs.map((log) => (
                  <tr key={log.id} className="hover:bg-slate-900/80">
                    <td className="py-2 px-3 text-slate-400 font-mono">
                      {new Date(log.created_at).toLocaleTimeString()}
                    </td>
                    <td className="py-2 px-3 uppercase text-slate-300 font-bold">{log.exchange_type}</td>
                    <td className="py-2 px-3 font-bold text-white">{log.symbol}</td>
                    <td className={`py-2 px-3 font-bold ${log.side === 'BUY' ? 'text-rose-400' : 'text-blue-400'}`}>
                      {log.side}
                    </td>
                    <td className="py-2 px-3 font-mono text-emerald-400">
                      {(Number(log.confidence_score) * 100).toFixed(1)}%
                    </td>
                    <td className="py-2 px-3 font-mono text-slate-200">
                      {Number(log.executed_price).toLocaleString()}원
                    </td>
                    <td className="py-2 px-3 font-mono font-bold text-slate-100">
                      {Number(log.total_amount).toLocaleString()}원
                    </td>
                    <td className="py-2 px-3">
                      <span className="px-2 py-0.5 rounded text-[10px] bg-emerald-950 text-emerald-400 border border-emerald-800">
                        {log.status}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  )
}
