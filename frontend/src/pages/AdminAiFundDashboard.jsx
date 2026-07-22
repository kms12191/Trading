import { useEffect, useState } from 'react'
import { supabase } from '../supabaseClient'

export default function AdminAiFundDashboard({ userId }) {
  const [exchangeType, setExchangeType] = useState('coinone')
  const [capital, setCapital] = useState(5000000)
  const [riskPreset, setRiskPreset] = useState('neutral')
  const [isActive, setIsActive] = useState(false)
  const [loading, setLoading] = useState(false)
  const [message, setMessage] = useState('')
  const [currentUserId, setCurrentUserId] = useState(userId || '')
  const [tradeLogs, setTradeLogs] = useState([])
  const [lastCheckTime, setLastCheckTime] = useState(new Date().toLocaleTimeString())
  const [configId, setConfigId] = useState(null)

  useEffect(() => {
    if (!currentUserId) {
      supabase.auth.getSession().then(({ data: { session } }) => {
        if (session?.user?.id) {
          setCurrentUserId(session.user.id)
        }
      })
    }
  }, [currentUserId])

  useEffect(() => {
    if (!currentUserId) return

    const fetchConfigAndLogs = async () => {
      const { data: configData } = await supabase
        .from('admin_ai_fund_configs')
        .select('*')
        .eq('user_id', currentUserId)
        .eq('exchange_type', exchangeType)
        .maybeSingle()

      if (configData) {
        setConfigId(configData.id || null)
        setCapital(configData.allocated_capital || 5000000)
        setRiskPreset(configData.risk_preset || 'neutral')
        setIsActive(configData.is_active || false)
      } else {
        setConfigId(null)
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
      supabase.removeChannel(configChannel)
      supabase.removeChannel(logChannel)
    }
  }, [currentUserId, exchangeType])

  const handleToggleActive = async () => {
    setLoading(true)
    setMessage('')
    try {
      const nextActive = !isActive
      const payload = {
        user_id: currentUserId,
        exchange_type: exchangeType,
        allocated_capital: capital,
        max_position_size: capital * (riskPreset === 'conservative' ? 0.05 : riskPreset === 'neutral' ? 0.1 : 0.2),
        risk_preset: riskPreset,
        min_signal_confidence: riskPreset === 'conservative' ? 0.85 : riskPreset === 'neutral' ? 0.75 : 0.65,
        daily_mdd_limit_pct: riskPreset === 'conservative' ? -1.0 : riskPreset === 'neutral' ? -2.0 : -4.0,
        is_active: nextActive,
      }
      if (configId) {
        payload.id = configId
      }

      const { data, error } = await supabase
        .from('admin_ai_fund_configs')
        .upsert(payload, { onConflict: 'user_id,exchange_type' })
        .select()

      if (error) throw error
      if (data && data.length > 0 && data[0].id) {
        setConfigId(data[0].id)
      }
      setIsActive(nextActive)
      setMessage(nextActive ? '✅ AI 위탁 운용이 시작되었습니다.' : '⏸ AI 위탁 운용이 일시정지되었습니다.')
    } catch (err) {
      setMessage(`❌ 오류: ${err.message}`)
    } finally {
      setLoading(false)
    }
  }


  const handleEmergencyKillSwitch = async () => {
    if (!confirm('🚨 긴급 셧다운을 실행하시겠습니까? 모든 AI 자동 매매가 즉시 정지됩니다.')) return
    setLoading(true)
    try {
      const { error } = await supabase
        .from('admin_ai_fund_configs')
        .update({ is_active: false })
        .eq('user_id', currentUserId)

      if (error) throw error
      setIsActive(false)
      setMessage('🚨 [긴급 셧다운 완료] 모든 AI 위탁 운용이 정지되었습니다.')
    } catch (err) {
      setMessage(`❌ 셧다운 오류: ${err.message}`)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="p-6 max-w-5xl mx-auto bg-slate-900 text-white rounded-xl shadow-2xl border border-slate-800 space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between border-b border-slate-800 pb-4">
        <div>
          <h1 className="text-xl font-bold text-emerald-400">관리자 전용 AI 위탁 자동투자 대시보드</h1>
          <p className="text-xs text-slate-400 mt-1">
            Human-on-the-Loop 모델 기반 AI 자율 운용 및 리스크 관리 시스템
          </p>
        </div>
        <button
          onClick={handleEmergencyKillSwitch}
          disabled={loading}
          className="px-4 py-2 bg-rose-600 hover:bg-rose-700 text-white font-bold text-xs rounded-lg shadow-lg transition-colors border border-rose-500 animate-pulse cursor-pointer"
        >
          🚨 Emergency Stop (Kill-Switch)
        </button>
      </div>

      {/* Live Status Bar */}
      <div className="p-4 rounded-lg bg-slate-950 border border-slate-800 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <span className={`inline-block w-3 h-3 rounded-full ${isActive ? 'bg-emerald-500 animate-ping' : 'bg-slate-600'}`} />
          <div>
            <span className="text-xs font-bold text-slate-200">
              AI 운용 상태: {isActive ? '🟢 운용 중 (시세/신호 실시간 감시)' : '⏸ 운용 대시/일시정지'}
            </span>
            <p className="text-[11px] text-slate-400 mt-0.5">
              {isActive
                ? `현재 LightGBM ML 신호 감시 중... (최소 확신도 기준: ${riskPreset === 'conservative' ? '85%' : riskPreset === 'neutral' ? '75%' : '65%'})`
                : '운용 시작 버튼을 누르면 AI가 할당 자금 범위 내에서 자동으로 매수/매도를 진행합니다.'}
            </p>
          </div>
        </div>
        <span className="text-[11px] font-mono text-slate-500">최근 점검: {lastCheckTime}</span>
      </div>

      {message && (
        <div className="p-3 text-xs rounded-md bg-slate-800 border border-slate-700 font-medium text-emerald-300">
          {message}
        </div>
      )}

      {/* Control Form */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div className="bg-slate-950 p-4 rounded-lg border border-slate-800 space-y-3">
          <label className="text-xs font-semibold text-slate-300 block">운용 거래소</label>
          <select
            value={exchangeType}
            onChange={(e) => setExchangeType(e.target.value)}
            className="w-full bg-slate-900 border border-slate-700 text-slate-200 text-xs rounded p-2"
          >
            <option value="coinone">코인원 (Coinone)</option>
            <option value="toss">토스증권 (Toss)</option>
            <option value="binance">바이낸스 (Binance)</option>
          </select>
        </div>

        <div className="bg-slate-950 p-4 rounded-lg border border-slate-800 space-y-3">
          <label className="text-xs font-semibold text-slate-300 block">위탁 할당 자금 (KRW)</label>
          <input
            type="number"
            value={capital}
            onChange={(e) => setCapital(Number(e.target.value))}
            className="w-full bg-slate-900 border border-slate-700 text-slate-200 text-xs rounded p-2"
          />
        </div>
      </div>

      {/* Risk Presets */}
      <div className="bg-slate-950 p-4 rounded-lg border border-slate-800 space-y-3">
        <label className="text-xs font-semibold text-slate-300 block">리스크 정책 프리셋</label>
        <div className="grid grid-cols-3 gap-2">
          {[
            { key: 'conservative', label: '보수적 (-1%)', desc: '확신도 85% 이상 / 1회 5%' },
            { key: 'neutral', label: '중립적 (-2%)', desc: '확신도 75% 이상 / 1회 10%' },
            { key: 'aggressive', label: '공격적 (-4%)', desc: '확신도 65% 이상 / 1회 20%' },
          ].map((preset) => (
            <button
              key={preset.key}
              type="button"
              onClick={() => setRiskPreset(preset.key)}
              className={`p-3 text-left rounded border transition ${
                riskPreset === preset.key
                  ? 'bg-emerald-600/20 border-emerald-500 text-emerald-300 font-bold'
                  : 'bg-slate-900 border-slate-800 text-slate-400 hover:border-slate-700'
              }`}
            >
              <div className="text-xs">{preset.label}</div>
              <div className="text-[10px] text-slate-400 mt-1">{preset.desc}</div>
            </button>
          ))}
        </div>
      </div>

      {/* Start/Pause Button */}
      <div className="pt-2 flex justify-end">
        <button
          onClick={handleToggleActive}
          disabled={loading}
          className={`px-6 py-2.5 rounded-lg text-xs font-bold transition-all shadow-md cursor-pointer ${
            isActive
              ? 'bg-amber-600 hover:bg-amber-700 text-white'
              : 'bg-emerald-600 hover:bg-emerald-700 text-white'
          }`}
        >
          {isActive ? '⏸ 운용 일시정지' : '▶ AI 위탁 운용 시작'}
        </button>
      </div>

      {/* Exchange Listing Guard Indicator */}
      <div className="p-3 bg-slate-950 rounded-lg border border-slate-800 flex items-center justify-between text-[11px]">
        <span className="text-slate-300">
          🛡️ <strong>거래소 상장 상태 자동 검증 Guard:</strong> 현재 선택된 <strong className="text-emerald-400 font-mono uppercase">{exchangeType}</strong> 거래소에 실제로 상장되어 매매 가능한 248개 종목만 엄격히 필터링하여 AI 매매 주문을 실행합니다.
        </span>
        <span className="px-2 py-1 rounded bg-emerald-950 text-emerald-300 border border-emerald-800 font-mono text-[10px]">
          Exchange Filter Active 🔒
        </span>
      </div>

      {/* AI Execution History Table */}

      <div className="bg-slate-950 p-4 rounded-lg border border-slate-800 space-y-3">
        <div className="flex items-center justify-between">
          <h2 className="text-xs font-bold text-slate-200">🤖 AI 실시간 자동 매매 기록 (Trade History)</h2>
          <span className="text-[11px] text-slate-500">총 {tradeLogs.length}건 기록됨</span>
        </div>

        {tradeLogs.length === 0 ? (
          <div className="p-8 text-center text-xs text-slate-500 bg-slate-900/50 rounded border border-slate-800/80">
            {isActive
              ? '💡 현재 AI가 코인원 시세를 분석 중입니다. ML 예측 확신도가 설정 기준을 충족하면 여기에 자동 매매 체결 기록이 생성됩니다.'
              : '운용 시작 후 AI가 매수를 진행하면 체결 기록이 여기에 표시됩니다.'}
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
