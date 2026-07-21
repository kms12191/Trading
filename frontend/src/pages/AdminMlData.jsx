import { useEffect, useEffectEvent, useMemo, useState } from 'react'
import Header from '../components/Header.jsx'
import { supabase } from '../supabaseClient'
import AdminInquiries from './AdminInquiries.jsx'
import AdminUsers from './AdminUsers.jsx'
import AdminSymbolReconciliation from './AdminSymbolReconciliation.jsx'
import {
  ActiveSignalPanel,
  AdvancedDataToolsPanel,
  AdvancedTrainingToolsPanel,
  ExecutionChecklistPanel,
  JobHistorySection,
  JobLogModal,
  ModelSwitchPanel,
  MlConsoleHeader,
  ModelResultsSection,
  OperationalAutomationPanel,
  OperationalTrustPanel,
  ReadinessPanel,
  RegistryStatusSection,
  ReportHistoryPanel,
  ReportPanel,
  ServingAuditPanel,
  UniverseManagementPanel,
  V8OptunaPanel,
} from './adminMlDataPanels.jsx'
import {
  formatPath,
  legacyAutomationPresets,
  operationalAutomationPresets,
  presets,
  summarizeFailedChecks,
  trainingPresets,
  tuningPresets,
  v8TuningPresets,
} from './adminMlDataModel.js'

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:5050'

export default function AdminMlData({ isLoggedIn, userEmail, handleLogout, hideHeader = false }) {
  const [adminTab, setAdminTab] = useState('ml')
  const [mode, setMode] = useState('crypto')
  const [form, setForm] = useState(presets.crypto)
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState(null)
  const [error, setError] = useState('')
  const [modelResults, setModelResults] = useState(null)
  const [modelResultsLoading, setModelResultsLoading] = useState(false)
  const [modelResultsError, setModelResultsError] = useState('')
  const [jobHistory, setJobHistory] = useState([])
  const [jobHistoryLoading, setJobHistoryLoading] = useState(false)
  const [jobHistoryError, setJobHistoryError] = useState('')
  const [registryRows, setRegistryRows] = useState({ stock: [], crypto: [] })
  const [promotionChecks, setPromotionChecks] = useState({})
  const [promotionChecksLoading, setPromotionChecksLoading] = useState(false)
  const [registryLoading, setRegistryLoading] = useState(false)
  const [registryError, setRegistryError] = useState('')
  const [registryMessage, setRegistryMessage] = useState('')
  const [activatingRegistryKey, setActivatingRegistryKey] = useState('')
  const [servingAudit, setServingAudit] = useState(null)
  const [servingAuditLoading, setServingAuditLoading] = useState(false)
  const [servingAuditError, setServingAuditError] = useState('')
  const [readiness, setReadiness] = useState(null)
  const [readinessLoading, setReadinessLoading] = useState(false)
  const [readinessError, setReadinessError] = useState('')
  const [reportLoading, setReportLoading] = useState(false)
  const [reportMessage, setReportMessage] = useState('')
  const [reportHistory, setReportHistory] = useState([])
  const [reportHistoryLoading, setReportHistoryLoading] = useState(false)
  const [reportHistoryError, setReportHistoryError] = useState('')
  const [activeSignals, setActiveSignals] = useState({ stock: null, crypto: null })
  const [activeSignalsLoading, setActiveSignalsLoading] = useState({ stock: false, crypto: false })
  const [activeSignalsError, setActiveSignalsError] = useState({ stock: '', crypto: '' })
  const [trainingLoadingKey, setTrainingLoadingKey] = useState('')
  const [trainingMessage, setTrainingMessage] = useState('')
  const [automationLoadingKey, setAutomationLoadingKey] = useState('')
  const [automationMessage, setAutomationMessage] = useState('')
  const [tuneTrials, setTuneTrials] = useState(20)
  const [tuneUpdateConfig, setTuneUpdateConfig] = useState(true)
  const [tuningLoadingKey, setTuningLoadingKey] = useState('')
  const [tuningMessage, setTuningMessage] = useState('')
  const [selectedLogJob, setSelectedLogJob] = useState(null)
  const [showAdvancedTools, setShowAdvancedTools] = useState(false)

  const selectedPreset = useMemo(() => presets[mode], [mode])

  const applyPreset = (nextMode) => {
    setMode(nextMode)
    setForm(presets[nextMode])
    setResult(null)
    setError('')
  }

  const updateField = (key, value) => {
    setForm((prev) => ({ ...prev, [key]: value }))
  }

  const loadModelResults = async () => {
    if (!isLoggedIn) return

    setModelResultsLoading(true)
    setModelResultsError('')

    try {
      const { data: { session } } = await supabase.auth.getSession()
      if (!session) {
        setModelResultsError('로그인 세션이 만료되었습니다.')
        return
      }

      const response = await fetch(`${API_BASE_URL}/api/ml/model-results`, {
        method: 'GET',
        headers: {
          'Authorization': `Bearer ${session.access_token}`,
        },
      })
      const payload = await response.json()
      if (!response.ok || !payload.success) {
        setModelResultsError(payload.message || '모델 결과 조회에 실패했습니다.')
        return
      }
      setModelResults(payload.data)
    } catch (requestError) {
      setModelResultsError(`서버 통신 실패: ${requestError.message}`)
    } finally {
      setModelResultsLoading(false)
    }
  }

  const loadJobHistory = async () => {
    if (!isLoggedIn) return

    setJobHistoryLoading(true)
    setJobHistoryError('')
    try {
      const { data: { session } } = await supabase.auth.getSession()
      if (!session) {
        setJobHistoryError('로그인 세션이 만료되었습니다.')
        return
      }

      const response = await fetch(`${API_BASE_URL}/api/ml/jobs?limit=20`, {
        method: 'GET',
        headers: {
          'Authorization': `Bearer ${session.access_token}`,
        },
      })
      const payload = await response.json()
      if (!response.ok || !payload.success) {
        setJobHistoryError(payload.message || '작업 이력 조회에 실패했습니다.')
        return
      }
      setJobHistory(payload.data.jobs || [])
    } catch (requestError) {
      setJobHistoryError(`서버 통신 실패: ${requestError.message}`)
    } finally {
      setJobHistoryLoading(false)
    }
  }

  const loadRegistry = async () => {
    if (!isLoggedIn) return

    setRegistryLoading(true)
    setRegistryError('')
    try {
      const { data: { session } } = await supabase.auth.getSession()
      if (!session) {
        setRegistryError('로그인 세션이 만료되었습니다.')
        return
      }

      const response = await fetch(`${API_BASE_URL}/api/ml/registry`, {
        method: 'GET',
        headers: {
          'Authorization': `Bearer ${session.access_token}`,
        },
      })
      const payload = await response.json()
      if (!response.ok || !payload.success) {
        setRegistryError(payload.message || '레지스트리 조회에 실패했습니다.')
        return
      }
      const nextRows = payload.data || { stock: [], crypto: [] }
      setRegistryRows(nextRows)
      await loadPromotionChecks(nextRows, session.access_token)
    } catch (requestError) {
      setRegistryError(`서버 통신 실패: ${requestError.message}`)
    } finally {
      setRegistryLoading(false)
    }
  }

  const loadPromotionChecks = async (rowsByAsset, accessToken) => {
    const allRows = [...(rowsByAsset?.stock || []), ...(rowsByAsset?.crypto || [])]
    if (!allRows.length) {
      setPromotionChecks({})
      return
    }

    setPromotionChecksLoading(true)
    try {
      let token = accessToken
      if (!token) {
        const { data: { session } } = await supabase.auth.getSession()
        token = session?.access_token
      }

      if (!token) {
        setPromotionChecks({})
        return
      }

      const entries = await Promise.all(
        allRows.map(async (row) => {
          try {
            const params = new URLSearchParams({
              asset_type: row.asset_type,
              model_version: row.model_version,
            })
            const response = await fetch(`${API_BASE_URL}/api/ml/registry/promotion-check?${params.toString()}`, {
              method: 'GET',
              headers: {
                'Authorization': `Bearer ${token}`,
              },
            })
            const payload = await response.json()
            if (!response.ok || !payload.success) {
              return [`${row.asset_type}:${row.model_version}`, null]
            }
            return [`${row.asset_type}:${row.model_version}`, payload.data]
          } catch {
            return [`${row.asset_type}:${row.model_version}`, null]
          }
        }),
      )

      setPromotionChecks(Object.fromEntries(entries.filter((entry) => entry[1])))
    } finally {
      setPromotionChecksLoading(false)
    }
  }

  const loadServingAudit = async () => {
    if (!isLoggedIn) return

    setServingAuditLoading(true)
    setServingAuditError('')
    try {
      const { data: { session } } = await supabase.auth.getSession()
      if (!session) {
        setServingAuditError('로그인 세션이 만료되었습니다.')
        return
      }

      const response = await fetch(`${API_BASE_URL}/api/ml/serving-audit`, {
        method: 'GET',
        headers: {
          'Authorization': `Bearer ${session.access_token}`,
        },
      })
      const payload = await response.json()
      if (!response.ok || !payload.success) {
        setServingAuditError(payload.message || '서빙 감사 조회에 실패했습니다.')
        return
      }
      setServingAudit(payload.data)
    } catch (requestError) {
      setServingAuditError(`서버 통신 실패: ${requestError.message}`)
    } finally {
      setServingAuditLoading(false)
    }
  }

  const loadActiveSignals = async (assetType) => {
    if (!isLoggedIn) return

    const assetKey = assetType === 'STOCK' ? 'stock' : 'crypto'
    setActiveSignalsLoading((prev) => ({ ...prev, [assetKey]: true }))
    setActiveSignalsError((prev) => ({ ...prev, [assetKey]: '' }))

    try {
      const { data: { session } } = await supabase.auth.getSession()
      if (!session) {
        setActiveSignalsError((prev) => ({ ...prev, [assetKey]: '로그인 세션이 만료되었습니다.' }))
        return
      }

      const params = new URLSearchParams({
        asset_type: assetType,
        limit: '8',
      })
      const response = await fetch(`${API_BASE_URL}/api/ml/predictions/active?${params.toString()}`, {
        method: 'GET',
        headers: {
          'Authorization': `Bearer ${session.access_token}`,
        },
      })
      const payload = await response.json()
      if (!response.ok || !payload.success) {
        setActiveSignals((prev) => ({ ...prev, [assetKey]: null }))
        setActiveSignalsError((prev) => ({
          ...prev,
          [assetKey]: response.status === 404
            ? '현재 안전 기준을 통과한 활성 신호가 없어 차단된 상태입니다.'
            : (payload.message || '활성 신호 조회에 실패했습니다.'),
        }))
        return
      }

      setActiveSignals((prev) => ({ ...prev, [assetKey]: payload.data }))
    } catch (requestError) {
      setActiveSignalsError((prev) => ({ ...prev, [assetKey]: `서버 통신 실패: ${requestError.message}` }))
    } finally {
      setActiveSignalsLoading((prev) => ({ ...prev, [assetKey]: false }))
    }
  }

  const loadReadiness = async () => {
    if (!isLoggedIn) return

    setReadinessLoading(true)
    setReadinessError('')
    try {
      const { data: { session } } = await supabase.auth.getSession()
      if (!session) {
        setReadinessError('로그인 세션이 만료되었습니다.')
        return
      }

      const response = await fetch(`${API_BASE_URL}/api/ml/readiness`, {
        method: 'GET',
        headers: {
          'Authorization': `Bearer ${session.access_token}`,
        },
      })
      const payload = await response.json()
      if (!response.ok || !payload.success) {
        setReadinessError(payload.message || '운영 준비 상태 조회에 실패했습니다.')
        return
      }
      setReadiness(payload.data)
    } catch (requestError) {
      setReadinessError(`서버 통신 실패: ${requestError.message}`)
    } finally {
      setReadinessLoading(false)
    }
  }

  const handleGenerateReport = async () => {
    if (!isLoggedIn) {
      setReportMessage('로그인 후 사용할 수 있습니다.')
      return
    }

    setReportLoading(true)
    setReportMessage('')
    try {
      const { data: { session } } = await supabase.auth.getSession()
      if (!session) {
        setReportMessage('로그인 세션이 만료되었습니다.')
        return
      }

      const response = await fetch(`${API_BASE_URL}/api/ml/report`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${session.access_token}`,
        },
        body: JSON.stringify({}),
      })
      const payload = await response.json()
      if (!response.ok || !payload.success) {
        setReportMessage(payload.message || '리포트 생성에 실패했습니다.')
        return
      }
      setReportMessage(`${payload.message} (${payload.data.output})`)
      await loadReportHistory()
    } catch (requestError) {
      setReportMessage(`서버 통신 실패: ${requestError.message}`)
    } finally {
      setReportLoading(false)
    }
  }

  const loadReportHistory = async () => {
    if (!isLoggedIn) return

    setReportHistoryLoading(true)
    setReportHistoryError('')
    try {
      const { data: { session } } = await supabase.auth.getSession()
      if (!session) {
        setReportHistoryError('로그인 세션이 만료되었습니다.')
        return
      }

      const response = await fetch(`${API_BASE_URL}/api/ml/reports?limit=10`, {
        method: 'GET',
        headers: {
          'Authorization': `Bearer ${session.access_token}`,
        },
      })
      const payload = await response.json()
      if (!response.ok || !payload.success) {
        setReportHistoryError(payload.message || '리포트 목록 조회에 실패했습니다.')
        return
      }
      setReportHistory(payload.data?.reports || [])
    } catch (requestError) {
      setReportHistoryError(`서버 통신 실패: ${requestError.message}`)
    } finally {
      setReportHistoryLoading(false)
    }
  }

  const handleActivateRegistry = async (row) => {
    if (!isLoggedIn) {
      setRegistryMessage('로그인 후 사용할 수 있습니다.')
      return
    }

    const activeKey = `${row.asset_type}:${row.model_version}`
    setActivatingRegistryKey(activeKey)
    setRegistryMessage('')
    try {
      const { data: { session } } = await supabase.auth.getSession()
      if (!session) {
        setRegistryMessage('로그인 세션이 만료되었습니다.')
        return
      }

      let response = await fetch(`${API_BASE_URL}/api/ml/registry/activate`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${session.access_token}`,
        },
        body: JSON.stringify({
          asset_type: row.asset_type,
          model_version: row.model_version,
          force: false,
        }),
      })
      let payload = await response.json()

      // 승격 기준 미달로 차단된 경우 (409)
      if (response.status === 409 && payload.success === false) {
        const failedSummary = summarizeFailedChecks(payload.data, 4)
        const confirmMsg = `${payload.message || '승격 기준 미달로 차단되었습니다.'}\n\n[실패 항목]\n${failedSummary.join('\n')}\n\n⚠️ 위험을 인지하고 강제로 서비스에 반영하시겠습니까?`
        
        if (window.confirm(confirmMsg)) {
          response = await fetch(`${API_BASE_URL}/api/ml/registry/activate`, {
            method: 'POST',
            headers: {
              'Content-Type': 'application/json',
              'Authorization': `Bearer ${session.access_token}`,
            },
            body: JSON.stringify({
              asset_type: row.asset_type,
              model_version: row.model_version,
              force: true,
            }),
          })
          payload = await response.json()
        } else {
          return
        }
      }

      if (!response.ok || !payload.success) {
        const failedSummary = summarizeFailedChecks(payload.data, 4)
        setRegistryMessage(
          failedSummary.length
            ? `${payload.message || '서비스 반영에 실패했습니다.'}\n${failedSummary.join('\n')}`
            : (payload.message || '서비스 반영에 실패했습니다.')
        )
        return
      }

      setRegistryMessage(payload.message || '서비스 반영이 완료되었습니다.')
      await loadRegistry()
      await loadModelResults()
      await loadServingAudit()
      await loadActiveSignals(row.asset_type)
      await loadReadiness()
    } catch (requestError) {
      setRegistryMessage(`서버 통신 실패: ${requestError.message}`)
    } finally {
      setActivatingRegistryKey('')
    }
  }

  const refreshAdminPanels = useEffectEvent(() => {
    loadModelResults()
    loadJobHistory()
    loadRegistry()
    loadServingAudit()
    loadReadiness()
    loadReportHistory()
    loadActiveSignals('STOCK')
    loadActiveSignals('CRYPTO')
  })

  useEffect(() => {
    if (!isLoggedIn) return
    const timer = window.setTimeout(() => {
      refreshAdminPanels()
    }, 0)

    return () => window.clearTimeout(timer)
  }, [isLoggedIn])

  const stockActiveGuardReport = activeSignals.stock?.model_version
    ? promotionChecks[`STOCK:${activeSignals.stock.model_version}`]
    : null
  const cryptoActiveGuardReport = activeSignals.crypto?.model_version
    ? promotionChecks[`CRYPTO:${activeSignals.crypto.model_version}`]
    : null

  const handleRunTraining = async (preset) => {
    if (!isLoggedIn) {
      setTrainingMessage('로그인 후 사용할 수 있습니다.')
      return
    }

    setTrainingLoadingKey(preset.key)
    setTrainingMessage('')
    try {
      const { data: { session } } = await supabase.auth.getSession()
      if (!session) {
        setTrainingMessage('로그인 세션이 만료되었습니다.')
        return
      }

      const response = await fetch(`${API_BASE_URL}/api/ml/jobs/train`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${session.access_token}`,
        },
        body: JSON.stringify({
          label: preset.label,
          config: preset.config,
          risk_config: preset.riskConfig,
          summary_output: preset.summaryOutput,
          skip_build_features: false,
        }),
      })
      const payload = await response.json()
      if (!response.ok || !payload.success) {
        setTrainingMessage(payload.message || '학습 실행에 실패했습니다.')
        return
      }

      const reportPath = payload?.data?.report?.timestamped_output || payload?.data?.report?.latest_output
      setTrainingMessage(
        reportPath
          ? `${preset.label} 작업이 완료되었습니다. 실험 리포트도 갱신되었습니다: ${formatPath(reportPath)}`
          : `${preset.label} 작업이 완료되었습니다.`
      )
      await loadModelResults()
      await loadJobHistory()
      await loadRegistry()
      await loadServingAudit()
      await loadActiveSignals(preset.config.includes('crypto') ? 'CRYPTO' : 'STOCK')
      await loadReadiness()
      await loadReportHistory()
    } catch (requestError) {
      setTrainingMessage(`서버 통신 실패: ${requestError.message}`)
    } finally {
      setTrainingLoadingKey('')
    }
  }

  const handleExport = async () => {
    if (!isLoggedIn) {
      setError('로그인 후 사용할 수 있습니다.')
      return
    }

    setLoading(true)
    setError('')
    setResult(null)

    try {
      const { data: { session } } = await supabase.auth.getSession()
      if (!session) {
        setError('로그인 세션이 만료되었습니다.')
        return
      }

      const response = await fetch(`${API_BASE_URL}/api/ml/export-candles`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${session.access_token}`,
        },
        body: JSON.stringify({
          asset_type: form.assetType,
          exchange: form.exchange,
          symbols: form.symbols,
          preset: form.preset,
          interval: form.interval,
          count: Number(form.count),
          sleep_seconds: Number(form.sleepSeconds),
          retry: Number(form.retry),
          retry_wait_seconds: Number(form.retryWaitSeconds),
          include_macro: form.includeMacro,
          chunk_size: Number(form.chunkSize || 0),
          chunk_index: Number(form.chunkIndex || 1),
          append: form.append,
        }),
      })

      const payload = await response.json()
      if (!response.ok || !payload.success) {
        setError(payload.message || 'CSV 생성에 실패했습니다.')
        return
      }

      setResult(payload)
      loadModelResults()
      loadRegistry()
      loadServingAudit()
      loadActiveSignals(form.assetType)
      loadReadiness()
    } catch (requestError) {
      setError(`서버 통신 실패: ${requestError.message}`)
    } finally {
      setLoading(false)
    }
  }

  const handleRunFullAutomation = async (preset) => {
    if (!isLoggedIn) {
      setAutomationMessage('로그인 후 사용할 수 있습니다.')
      return
    }

    setAutomationLoadingKey(preset.key)
    setAutomationMessage('')
    try {
      const { data: { session } } = await supabase.auth.getSession()
      if (!session) {
        setAutomationMessage('로그인 세션이 만료되었습니다.')
        return
      }

      const response = await fetch(`${API_BASE_URL}/api/ml/jobs/full-run`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${session.access_token}`,
        },
        body: JSON.stringify({
          preset_key: preset.key,
        }),
      })
      const payload = await response.json()
      if (!response.ok || !payload.success) {
        setAutomationMessage(payload.message || '자동 수집+학습 실행에 실패했습니다.')
        return
      }

      const reportPath = payload?.data?.report?.timestamped_output || payload?.data?.report?.latest_output
      setAutomationMessage(
        reportPath
          ? `${preset.label} 작업이 완료되었습니다. 실험 리포트도 갱신되었습니다: ${formatPath(reportPath)}`
          : `${preset.label} 작업이 완료되었습니다.`
      )
      await loadModelResults()
      await loadJobHistory()
      await loadRegistry()
      await loadServingAudit()
      // 국내/해외 분리 모델도 현재 registry asset_type은 STOCK으로 동기화합니다.
      await loadActiveSignals(preset.key.includes('crypto') ? 'CRYPTO' : 'STOCK')
      await loadReadiness()
      await loadReportHistory()
    } catch (requestError) {
      setAutomationMessage(`서버 통신 실패: ${requestError.message}`)
    } finally {
      setAutomationLoadingKey('')
    }
  }

  const handleRunTuning = async (preset) => {
    if (!isLoggedIn) {
      setTuningMessage('로그인 후 사용할 수 있습니다.')
      return
    }

    setTuningLoadingKey(preset.key)
    setTuningMessage('')
    try {
      const { data: { session } } = await supabase.auth.getSession()
      if (!session) {
        setTuningMessage('로그인 세션이 만료되었습니다.')
        return
      }

      const response = await fetch(`${API_BASE_URL}/api/ml/jobs/tune`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${session.access_token}`,
        },
        body: JSON.stringify({
          config: preset.config,
          trials: Number(tuneTrials),
          update_config: tuneUpdateConfig,
        }),
      })
      const payload = await response.json()
      if (!response.ok || !payload.success) {
        setTuningMessage(payload.message || '튜닝 실행에 실패했습니다.')
        return
      }

      // Optuna 로그가 payload.data.stdout에 포함되어 있음
      setTuningMessage(
        payload.data?.success
          ? `${preset.label} 작업이 완료되었습니다. (작업 ID: ${payload.data.job_id})`
          : `${preset.label} 작업이 완료되었으나 실패 사유가 있습니다.`
      )
      await loadModelResults()
      await loadJobHistory()
      await loadRegistry()
      await loadServingAudit()
      await loadActiveSignals(preset.config.includes('crypto') ? 'CRYPTO' : 'STOCK')
      await loadReadiness()
      await loadReportHistory()
    } catch (requestError) {
      setTuningMessage(`서버 통신 실패: ${requestError.message}`)
    } finally {
      setTuningLoadingKey('')
    }
  }

  return (
    <div className={hideHeader ? 'text-[#e2e2ec]' : 'min-h-screen bg-obsidian-bg px-6 py-8 text-[#e2e2ec]'}>
      {!hideHeader && (
        <Header isLoggedIn={isLoggedIn} userEmail={userEmail} handleLogout={handleLogout} />
      )}

      <main className="mx-auto flex max-w-7xl flex-col gap-6">
        {/* 관리자 내부 탭 */}
        <div className="flex overflow-x-auto border-b border-slate-800">
          <button
            type="button"
            onClick={() => setAdminTab('ml')}
            className={`shrink-0 px-4 py-3 text-sm font-bold border-b-2 transition sm:px-6 ${
              adminTab === 'ml'
                ? 'border-ai-cyan text-white bg-ai-cyan/5'
                : 'border-transparent text-slate-400 hover:text-white'
            }`}
          >
            ML 운영 콘솔
          </button>
          <button
            type="button"
            onClick={() => setAdminTab('inquiries')}
            className={`shrink-0 px-4 py-3 text-sm font-bold border-b-2 transition sm:px-6 ${
              adminTab === 'inquiries'
                ? 'border-ai-cyan text-white bg-ai-cyan/5'
                : 'border-transparent text-slate-400 hover:text-white'
            }`}
          >
            사용자 문의 관리
          </button>
          <button
            type="button"
            onClick={() => setAdminTab('users')}
            className={`shrink-0 px-4 py-3 text-sm font-bold border-b-2 transition sm:px-6 ${
              adminTab === 'users'
                ? 'border-ai-cyan text-white bg-ai-cyan/5'
                : 'border-transparent text-slate-400 hover:text-white'
            }`}
          >
            유저 관리
          </button>
          <button
            type="button"
            onClick={() => setAdminTab('symbols')}
            className={`shrink-0 px-4 py-3 text-sm font-bold border-b-2 transition sm:px-6 ${
              adminTab === 'symbols'
                ? 'border-ai-cyan text-white bg-ai-cyan/5'
                : 'border-transparent text-slate-400 hover:text-white'
            }`}
          >
            종목 정리
          </button>
          <button
            type="button"
            onClick={() => setAdminTab('universe')}
            className={`shrink-0 px-4 py-3 text-sm font-bold border-b-2 transition sm:px-6 ${
              adminTab === 'universe'
                ? 'border-ai-cyan text-white bg-ai-cyan/5'
                : 'border-transparent text-slate-400 hover:text-white'
            }`}
          >
            유니버스 설정
          </button>
        </div>

        {adminTab === 'ml' && (
          <>
            <MlConsoleHeader
              showAdvancedTools={showAdvancedTools}
              onToggleAdvanced={() => setShowAdvancedTools((prev) => !prev)}
            />

        <ReadinessPanel
          data={readiness}
          loading={readinessLoading}
          error={readinessError}
          onRefresh={loadReadiness}
        />

        <ServingAuditPanel
          data={servingAudit}
          loading={servingAuditLoading}
          error={servingAuditError}
          onRefresh={loadServingAudit}
        />

        <ModelSwitchPanel
          data={servingAudit}
          rowsByAsset={registryRows}
          promotionChecks={promotionChecks}
          loading={servingAuditLoading || registryLoading || promotionChecksLoading}
          onActivate={handleActivateRegistry}
          activatingKey={activatingRegistryKey}
        />

        <OperationalTrustPanel
          data={servingAudit}
          loading={servingAuditLoading}
          error={servingAuditError}
        />

        <section className="grid gap-6 grid-cols-1">
          <ActiveSignalPanel
            title="주식 활성 신호"
            data={activeSignals.stock}
            loading={activeSignalsLoading.stock}
            error={activeSignalsError.stock}
            guardReport={stockActiveGuardReport}
            onRefresh={() => loadActiveSignals('STOCK')}
          />
          <ActiveSignalPanel
            title="코인 활성 신호"
            data={activeSignals.crypto}
            loading={activeSignalsLoading.crypto}
            error={activeSignalsError.crypto}
            guardReport={cryptoActiveGuardReport}
            onRefresh={() => loadActiveSignals('CRYPTO')}
          />
        </section>

        <OperationalAutomationPanel
          presets={operationalAutomationPresets}
          loadingKey={automationLoadingKey}
          message={automationMessage}
          isLoggedIn={isLoggedIn}
          onRun={handleRunFullAutomation}
        />

        {showAdvancedTools ? (
        <>
        <V8OptunaPanel
          presets={v8TuningPresets}
          trials={tuneTrials}
          updateConfig={tuneUpdateConfig}
          loadingKey={tuningLoadingKey}
          message={tuningMessage}
          isLoggedIn={isLoggedIn}
          onTrialsChange={setTuneTrials}
          onUpdateConfigChange={setTuneUpdateConfig}
          onRun={handleRunTuning}
        />

        <AdvancedDataToolsPanel
          presets={presets}
          mode={mode}
          selectedPreset={selectedPreset}
          form={form}
          result={result}
          error={error}
          loading={loading}
          onApplyPreset={applyPreset}
          onUpdateField={updateField}
          onExport={handleExport}
        />
        </>
        ) : null}

        {showAdvancedTools ? (
        <ModelResultsSection
          results={modelResults}
          loading={modelResultsLoading}
          error={modelResultsError}
          isLoggedIn={isLoggedIn}
          onRefresh={loadModelResults}
        />
        ) : null}

        {showAdvancedTools ? (
        <RegistryStatusSection
          rowsByAsset={registryRows}
          loading={registryLoading}
          error={registryError}
          message={registryMessage}
          activatingKey={activatingRegistryKey}
          promotionChecks={promotionChecks}
          promotionChecksLoading={promotionChecksLoading}
          onActivate={handleActivateRegistry}
        />
        ) : null}

        {showAdvancedTools ? <ExecutionChecklistPanel /> : null}

        {showAdvancedTools ? (
        <ReportPanel
          loading={reportLoading}
          message={reportMessage}
          onGenerate={handleGenerateReport}
        />
        ) : null}

        {showAdvancedTools ? (
        <ReportHistoryPanel
          reports={reportHistory}
          loading={reportHistoryLoading}
          error={reportHistoryError}
          onRefresh={loadReportHistory}
        />
        ) : null}

        <section className="grid gap-6 grid-cols-1">
          {showAdvancedTools ? (
            <AdvancedTrainingToolsPanel
              trainingPresets={trainingPresets}
              legacyAutomationPresets={legacyAutomationPresets}
              tuningPresets={tuningPresets}
              trainingLoadingKey={trainingLoadingKey}
              automationLoadingKey={automationLoadingKey}
              tuningLoadingKey={tuningLoadingKey}
              trainingMessage={trainingMessage}
              automationMessage={automationMessage}
              tuningMessage={tuningMessage}
              tuneTrials={tuneTrials}
              tuneUpdateConfig={tuneUpdateConfig}
              isLoggedIn={isLoggedIn}
              onRunTraining={handleRunTraining}
              onRunFullAutomation={handleRunFullAutomation}
              onRunTuning={handleRunTuning}
              onTrialsChange={setTuneTrials}
              onUpdateConfigChange={setTuneUpdateConfig}
            />
          ) : null}

          <JobHistorySection
            jobs={jobHistory}
            loading={jobHistoryLoading}
            error={jobHistoryError}
            isLoggedIn={isLoggedIn}
            onRefresh={loadJobHistory}
            onShowLog={setSelectedLogJob}
          />
        </section>
        </>
        )}

        {adminTab === 'inquiries' && (
          <AdminInquiries
            isLoggedIn={isLoggedIn}
            userEmail={userEmail}
            handleLogout={handleLogout}
            hideHeader
          />
        )}

        {adminTab === 'users' && (
          <AdminUsers
            isLoggedIn={isLoggedIn}
            userEmail={userEmail}
            handleLogout={handleLogout}
            hideHeader
          />
        )}

        {adminTab === 'symbols' && (
          <AdminSymbolReconciliation />
        )}

        {adminTab === 'universe' && (
          <UniverseManagementPanel isLoggedIn={isLoggedIn} />
        )}
      </main>

      <JobLogModal
        job={selectedLogJob}
        onClose={() => setSelectedLogJob(null)}
      />
    </div>
  )
}
