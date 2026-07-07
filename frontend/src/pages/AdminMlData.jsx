import { useEffect, useEffectEvent, useMemo, useState } from 'react'
import Header from '../components/Header.jsx'
import { supabase } from '../supabaseClient'
import AdminInquiryPanel from './AdminInquiryPanel.jsx'

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:5050'

const PROJECT_ROOT_PATH = '/Users/kangheesung/10-19_개발/13_프로젝트/13.05_트레이딩/teamproject'

function formatPath(path) {
  if (!path || typeof path !== 'string') return path || '-'
  if (path.startsWith(PROJECT_ROOT_PATH)) {
    return '.' + path.substring(PROJECT_ROOT_PATH.length)
  }
  const idx = path.indexOf('/teamproject/')
  if (idx !== -1) {
    return '.' + path.substring(idx + '/teamproject'.length)
  }
  return path
}

function formatPathInText(text) {
  if (!text || typeof text !== 'string') return text
  let formatted = text.replaceAll(PROJECT_ROOT_PATH, '.')
  const idx = formatted.indexOf('/teamproject/')
  if (idx !== -1) {
    formatted = formatted.replaceAll(PROJECT_ROOT_PATH.substring(0, PROJECT_ROOT_PATH.indexOf('/teamproject') + 12), '.')
  }
  return formatted
}

const presets = {
  stock: {
    title: 'Toss 주식 데이터',
    assetType: 'STOCK',
    exchange: 'TOSS',
    preset: 'stock_core_90',
    symbols: '',
    interval: '1d',
    count: 700,
    output: 'ml/data/raw/stock_candles.csv',
    sleepSeconds: 2,
    retry: 3,
    retryWaitSeconds: 60,
    includeMacro: true,
    chunkSize: 10,
    chunkIndex: 1,
    append: true,
  },
  crypto: {
    title: 'Binance 코인 데이터',
    assetType: 'CRYPTO',
    exchange: 'BINANCE',
    preset: 'crypto_core_30',
    symbols: '',
    interval: '1h',
    count: 2500,
    output: 'ml/data/raw/crypto_candles.csv',
    sleepSeconds: 0.2,
    retry: 2,
    retryWaitSeconds: 10,
    includeMacro: false,
    chunkSize: 10,
    chunkIndex: 1,
    append: true,
  },
}

const trainingPresets = [
  {
    key: 'stock-v6',
    label: '주식 v6 학습',
    config: 'ml/configs/lgbm_stock_v6.yaml',
    riskConfig: 'ml/configs/lgbm_stock_risk_v6.yaml',
    summaryOutput: 'ml/data/processed/stock_v6_summary.json',
  },
  {
    key: 'crypto-v6',
    label: '코인 v6 학습',
    config: 'ml/configs/lgbm_crypto_v6.yaml',
    riskConfig: 'ml/configs/lgbm_crypto_risk_v6.yaml',
    summaryOutput: 'ml/data/processed/crypto_v6_summary.json',
  },
  {
    key: 'stock-v7',
    label: '주식 v7 학습',
    config: 'ml/configs/lgbm_stock_v7.yaml',
    riskConfig: 'ml/configs/lgbm_stock_risk_v7.yaml',
    summaryOutput: 'ml/data/processed/stock_v7_summary.json',
  },
  {
    key: 'crypto-v7',
    label: '코인 v7 학습',
    config: 'ml/configs/lgbm_crypto_v7.yaml',
    riskConfig: 'ml/configs/lgbm_crypto_risk_v7.yaml',
    summaryOutput: 'ml/data/processed/crypto_v7_summary.json',
  },
]

const tuningPresets = [
  {
    key: 'stock-v7-tune',
    label: '주식 v7 HPO 튜닝',
    config: 'ml/configs/lgbm_stock_v7.yaml',
    defaultTrials: 20,
    summary: '주식 v7 모델에 대해 Optuna로 최적의 하이퍼파라미터(learning_rate, num_leaves 등)를 탐색합니다.',
    version: 'v7',
  },
  {
    key: 'crypto-v7-tune',
    label: '코인 v7 HPO 튜닝',
    config: 'ml/configs/lgbm_crypto_v7.yaml',
    defaultTrials: 20,
    summary: '코인 v7 모델에 대해 Optuna로 최적의 하이퍼파라미터를 탐색합니다.',
    version: 'v7',
  },
  {
    key: 'stock-v8-tune',
    label: '주식 v8 HPO 튜닝',
    config: 'ml/configs/lgbm_stock_v8.yaml',
    defaultTrials: 20,
    summary: '주식 v8 모델에 대해 Optuna로 하이퍼파라미터를 탐색합니다 (잔차 라벨 기반).',
    version: 'v8',
    isNew: true,
  },
  {
    key: 'crypto-v8-tune',
    label: '코인 v8 HPO 튜닝',
    config: 'ml/configs/lgbm_crypto_v8.yaml',
    defaultTrials: 20,
    summary: '코인 v8 모델에 대해 Optuna로 하이퍼파라미터를 탐색합니다 (30m 캔들 기반).',
    version: 'v8',
    isNew: true,
  },
]

const automationPresets = [
  {
    key: 'stock-v7-full',
    label: '주식 v7 자동 수집+학습',
    summary: 'Toss stock_core_90 수집 후 v7 학습까지 한 번에 실행',
    version: 'v7',
  },
  {
    key: 'crypto-v7-full',
    label: '코인 v7 자동 수집+학습',
    summary: 'Binance crypto_core_30 수집 후 v7 학습까지 한 번에 실행 (1h 캔들)',
    version: 'v7',
  },
  {
    key: 'stock-v8-full',
    label: '주식 v8 자동 수집+학습',
    summary: '잔차 수익률 라벨 + Ridge 앙상블 주식 모델 (KOSPI/NASDAQ 시장 노이즈 제거)',
    version: 'v8',
    isNew: true,
  },
  {
    key: 'crypto-v8-full',
    label: '코인 v8 자동 수집+학습',
    summary: '30m 캔들 5000개 수집 후 v8 학습 — 잔차 수익률 라벨 + Ridge 앙상블 (파일: crypto_candles_30m.csv)',
    version: 'v8',
    isNew: true,
  },
  {
    key: 'kr-stock-v1-full',
    label: '국내주식 v1 자동 수집+학습',
    summary: 'stock_kr_core_45 + DART 공시 피처를 포함한 국내주식 shadow 모델',
    version: 'split-v1',
    isNew: true,
  },
  {
    key: 'us-stock-v1-full',
    label: '해외주식 v1 자동 수집+학습',
    summary: 'stock_us_core_45 기반 해외주식 shadow 모델. DART 피처는 제외합니다.',
    version: 'split-v1',
    isNew: true,
  },
]

const operationalAutomationPresets = automationPresets.filter((preset) => ['v8', 'split-v1'].includes(preset.version))
const legacyAutomationPresets = automationPresets.filter((preset) => !['v8', 'split-v1'].includes(preset.version))
const v8TuningPresets = tuningPresets.filter((preset) => preset.version === 'v8')

function StatusPanel({ result, error, loading }) {
  if (loading) {
    return (
      <div className="rounded-lg border border-ai-cyan/30 bg-ai-cyan/5 p-4 text-sm text-ai-cyan">
        학습용 캔들 CSV를 생성하는 중입니다.
      </div>
    )
  }

  if (error) {
    return (
      <div className="rounded-lg border border-red-800 bg-red-950/30 p-4 text-sm leading-6 text-red-300">
        {error}
      </div>
    )
  }

  if (!result) {
    return (
      <div className="rounded-lg border border-slate-800 bg-[#0f172a] p-4 text-sm leading-6 text-slate-400">
        수집 버튼을 누르면 결과 파일 경로와 생성 행 수가 여기에 표시됩니다.
      </div>
    )
  }

  return (
    <div className="rounded-lg border border-emerald-500/30 bg-emerald-950/20 p-4 text-sm leading-6 text-emerald-200">
      <p className="font-bold text-emerald-300">{result.message}</p>
      <dl className="mt-3 grid gap-2 md:grid-cols-2">
        <div>
          <dt className="text-xs text-slate-500">거래소</dt>
          <dd className="font-mono text-white">{result.data.exchange}</dd>
        </div>
        <div>
          <dt className="text-xs text-slate-500">생성 행 수</dt>
          <dd className="font-mono text-white">{result.data.row_count}</dd>
        </div>
        <div>
          <dt className="text-xs text-slate-500">실패 심볼 수</dt>
          <dd className="font-mono text-white">{result.data.failure_count ?? 0}</dd>
        </div>
        <div className="md:col-span-2">
          <dt className="text-xs text-slate-500">파일 경로</dt>
          <dd className="break-all font-mono text-white">{result.data.output}</dd>
        </div>
        {result.data.failures?.length ? (
          <div className="md:col-span-2">
            <dt className="text-xs text-slate-500">실패 목록</dt>
            <dd className="mt-1 space-y-1">
              {result.data.failures.map((failure) => (
                <p key={`${failure.symbol}-${failure.reason}`} className="break-all font-mono text-xs text-amber-200">
                  {failure.symbol}: {failure.reason}
                </p>
              ))}
            </dd>
          </div>
        ) : null}
      </dl>
    </div>
  )
}

function JobLogModal({ job, onClose }) {
  if (!job) return null

  const handleCopy = () => {
    const text = `=== Job Log: ${job.label || job.id} ===\n\n[TRAINING AUDIT]\n${JSON.stringify(job.training_audit || null, null, 2)}\n\n[GUARD REPORT]\n${JSON.stringify(job.guard_report || null, null, 2)}\n\n[SERVING AUDIT]\n${JSON.stringify(job.serving_audit_report || null, null, 2)}\n\n[STDOUT]\n${job.stdout || 'No stdout'}\n\n[STDERR]\n${job.stderr || 'No stderr'}`
    navigator.clipboard.writeText(text)
    alert('로그가 클립보드에 복사되었습니다.')
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 backdrop-blur-sm">
      <div className="relative w-full max-w-4xl max-h-[85vh] flex flex-col rounded-lg border border-slate-700 bg-[#0f172a] text-[#e2e2ec] shadow-2xl">
        <div className="flex items-center justify-between border-b border-slate-800 px-5 py-4">
          <div className="flex items-center gap-2">
            <span className="rounded border border-ai-cyan/40 px-2 py-0.5 text-[10px] font-bold text-ai-cyan">
              {String(job.type || 'job').toUpperCase()}
            </span>
            <span className="text-sm font-bold text-white">
              {job.label || job.id} 작업 상세 로그
            </span>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="text-slate-400 hover:text-white text-xl font-bold transition-colors"
          >
            &times;
          </button>
        </div>

        <div className="flex-1 overflow-y-auto p-5 space-y-4 font-mono text-xs leading-5">
          {job.config || job.interval ? (
            <div className="rounded bg-black/30 p-3 border border-slate-800/60 text-slate-400">
              <p>설정: {job.config || '-'}</p>
              <p>인터벌: {job.interval || '-'}</p>
            </div>
          ) : null}

          {job.training_audit || job.guard_report || job.serving_audit_report ? (
            <div className="grid gap-4 xl:grid-cols-3">
              <div className="rounded border border-slate-800 bg-black/30 p-3">
                <p className="mb-2 text-[10px] font-bold uppercase tracking-wider text-slate-500">학습 감사</p>
                {job.training_audit?.promotion_guard ? (
                  <GuardSummary guardReport={job.training_audit.promotion_guard} />
                ) : (
                  <p className="text-[10px] text-slate-500">학습 감사 정보가 없습니다.</p>
                )}
              </div>
              <div className="rounded border border-slate-800 bg-black/30 p-3">
                <p className="mb-2 text-[10px] font-bold uppercase tracking-wider text-slate-500">승격 검증</p>
                <GuardSummary guardReport={job.guard_report} />
              </div>
              <div className="rounded border border-slate-800 bg-black/30 p-3">
                <p className="mb-2 text-[10px] font-bold uppercase tracking-wider text-slate-500">서빙 감사</p>
                {job.serving_audit_report ? (
                  <div className="space-y-2">
                    <AuditBadge status={job.serving_audit_report.status}>
                      {job.serving_audit_report.status === 'healthy' ? '전체 정상' : '경고'}
                    </AuditBadge>
                    <p className="text-[10px] text-slate-400">차단 항목 {job.serving_audit_report.blocking_count ?? 0}건</p>
                  </div>
                ) : job.training_audit?.serving_audit ? (
                  <div className="space-y-2">
                    <AuditBadge status={job.training_audit.serving_audit.status}>
                      {job.training_audit.serving_audit.status === 'healthy' ? '전체 정상' : '경고'}
                    </AuditBadge>
                    <p className="text-[10px] text-slate-400">차단 항목 {job.training_audit.serving_audit.blocking_count ?? 0}건</p>
                  </div>
                ) : (
                  <p className="text-[10px] text-slate-500">서빙 감사 정보가 없습니다.</p>
                )}
              </div>
            </div>
          ) : null}

          <div className="grid gap-4 md:grid-cols-2">
            <div className="flex flex-col rounded border border-slate-800 bg-black/40">
              <div className="flex items-center justify-between border-b border-slate-800 px-3 py-1.5 bg-black/20">
                <span className="text-[10px] font-bold uppercase tracking-wider text-emerald-400">STDOUT (출력)</span>
              </div>
              <pre className="h-[40vh] overflow-auto p-3 whitespace-pre-wrap text-emerald-200 text-[11px] leading-relaxed">
                {job.stdout || '출력 로그가 없습니다.'}
              </pre>
            </div>

            <div className="flex flex-col rounded border border-slate-800 bg-black/40">
              <div className="flex items-center justify-between border-b border-slate-800 px-3 py-1.5 bg-black/20">
                <span className="text-[10px] font-bold uppercase tracking-wider text-rose-400">STDERR (에러)</span>
              </div>
              <pre className="h-[40vh] overflow-auto p-3 whitespace-pre-wrap text-rose-300 text-[11px] leading-relaxed">
                {job.stderr || '에러 로그가 없습니다.'}
              </pre>
            </div>
          </div>
        </div>

        <div className="flex justify-end gap-3 border-t border-slate-800 px-5 py-3.5 bg-black/10">
          <button
            type="button"
            onClick={handleCopy}
            className="rounded border border-ai-cyan/40 px-4 py-2 text-xs font-bold text-ai-cyan transition hover:bg-ai-cyan/10"
          >
            전체 복사
          </button>
          <button
            type="button"
            onClick={onClose}
            className="rounded border border-slate-700 bg-slate-800 px-4 py-2 text-xs font-bold text-white transition hover:bg-slate-700"
          >
            닫기
          </button>
        </div>
      </div>
    </div>
  )
}

function formatMetric(value) {
  if (value === null || value === undefined || value === '') return '-'
  const numberValue = Number(value)
  if (Number.isNaN(numberValue)) return String(value)
  return numberValue.toFixed(4)
}

function formatPercent(value) {
  if (value === null || value === undefined || value === '') return '-'
  const numberValue = Number(value)
  if (Number.isNaN(numberValue)) return String(value)
  return `${(numberValue * 100).toFixed(1)}%`
}

function formatReturnPercent(value) {
  if (value === null || value === undefined || value === '') return '-'
  const numberValue = Number(value)
  if (Number.isNaN(numberValue)) return String(value)
  return `${(numberValue * 100).toFixed(2)}%`
}

function formatVersionBacktest(version, key) {
  const compositeData = version?.backtests?.composite?.data;
  if (!compositeData) return '-';
  let val = compositeData[key];
  if ((val === undefined || val === null) && typeof key === 'string' && key.endsWith('_net')) {
    val = compositeData[key.replace('_net', '')];
  }
  return formatReturnPercent(val);
}

function formatSignedDelta(value, formatter = 'metric') {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return '-'

  const numericValue = Number(value)
  const prefix = numericValue > 0 ? '+' : ''
  if (formatter === 'percent') {
    return `${prefix}${(numericValue * 100).toFixed(1)}%`
  }
  if (formatter === 'return') {
    return `${prefix}${(numericValue * 100).toFixed(2)}%`
  }
  return `${prefix}${numericValue.toFixed(4)}`
}

function getVersionSnapshot(version) {
  if (!version) return null

  return {
    cvRocAuc: Number(version.metrics?.time_series_cv_average?.roc_auc ?? version.metrics?.roc_auc ?? NaN),
    top10Precision: Number(version.metrics?.time_series_cv_average?.precision_at_top_10pct ?? version.metrics?.precision_at_top_10pct ?? NaN),
    riskCvRocAuc: Number(version.risk_metrics?.time_series_cv_average?.roc_auc ?? version.risk_metrics?.roc_auc ?? NaN),
    compositeExcessReturnNet: Number(version.backtests?.composite?.data?.excess_return_net ?? version.backtests?.composite?.data?.excess_return ?? NaN),
  }
}

function VersionDeltaPanel({ activeVersion, baselines = [] }) {
  const activeSnapshot = getVersionSnapshot(activeVersion)
  const visibleBaselines = baselines.filter((baseline) => baseline?.version && baseline.version !== activeVersion?.version)

  if (!activeVersion?.version || !activeSnapshot || !visibleBaselines.length) {
    return null
  }

  return (
    <div className="mt-5 rounded-lg border border-slate-800 bg-[#0f172a] p-4">
      <div className="mb-3">
        <p className="text-xs font-bold uppercase tracking-wider text-slate-400">버전 차이 요약</p>
        <p className="mt-1 text-xs leading-5 text-slate-500">
          현재 선택 버전이 비교 기준보다 얼마나 좋아졌는지 빠르게 확인합니다.
        </p>
      </div>
      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
        {visibleBaselines.map((baseline) => {
          const baselineSnapshot = getVersionSnapshot(baseline)
          if (!baselineSnapshot) return null

          return (
            <div key={`${activeVersion.version}-${baseline.version}`} className="rounded-lg border border-slate-800 bg-black/10 p-3">
              <div className="flex items-start justify-between gap-3">
                <div>
                  <p className="text-xs font-bold text-white">{baseline.label}</p>
                  <p className="mt-1 font-mono text-[10px] text-slate-500">
                    {baseline.version} {'->'} {activeVersion.version}
                  </p>
                </div>
                <span className="rounded border border-ai-cyan/30 px-2 py-1 text-[10px] font-bold text-ai-cyan">
                  DELTA
                </span>
              </div>
              <div className="mt-3 grid gap-2 text-xs text-slate-300">
                <p>
                  시계열 CV 구분력: <span className="font-mono text-white">{formatSignedDelta(activeSnapshot.cvRocAuc - baselineSnapshot.cvRocAuc)}</span>
                </p>
                <p>
                  상위 10% 적중: <span className="font-mono text-white">{formatSignedDelta(activeSnapshot.top10Precision - baselineSnapshot.top10Precision)}</span>
                </p>
                <p>
                  하락 구분력: <span className="font-mono text-white">{formatSignedDelta(activeSnapshot.riskCvRocAuc - baselineSnapshot.riskCvRocAuc)}</span>
                </p>
                <p>
                  복합 초과수익(순): <span className="font-mono text-ai-cyan">{formatSignedDelta(activeSnapshot.compositeExcessReturnNet - baselineSnapshot.compositeExcessReturnNet, 'return')}</span>
                </p>
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}

function formatTime(isoString) {
  if (!isoString) return '-'
  try {
    const date = new Date(isoString)
    if (Number.isNaN(date.getTime())) return isoString
    const pad = (n) => String(n).padStart(2, '0')
    const month = pad(date.getMonth() + 1)
    const day = pad(date.getDate())
    const hour = pad(date.getHours())
    const minute = pad(date.getMinutes())
    const second = pad(date.getSeconds())
    return `${month}-${day} ${hour}:${minute}:${second}`
  } catch {
    return isoString
  }
}

const PROMOTION_CHECK_LABELS = {
  dataset_quality: '데이터 품질',
  valid_rows: '검증 행 수',
  cv_roc_auc: '시계열 CV 구분력',
  precision_at_top_10pct: '상위 10% 적중',
  risk_cv_roc_auc: '하락 위험 구분력',
  composite_excess_return_net: '복합 초과수익(순)',
  composite_precision_at_top_n: '복합 상위후보 적중',
  max_drawdown_net: '최대 낙폭',
  vs_serving_cv_roc_auc_drop: '서빙 대비 CV 하락폭',
  vs_serving_excess_return_drop: '서빙 대비 수익 하락폭',
  vs_serving_precision_drop: '서빙 대비 적중 하락폭',
  meaningful_improvement: '의미 있는 개선',
}

function getHealthTone(status) {
  if (status === 'healthy') {
    return 'border-emerald-500/40 bg-emerald-950/20 text-emerald-300'
  }
  if (status === 'warning') {
    return 'border-amber-500/40 bg-amber-950/20 text-amber-300'
  }
  if (status === 'missing') {
    return 'border-red-500/40 bg-red-950/20 text-red-300'
  }
  return 'border-slate-700 bg-slate-900/40 text-slate-400'
}

function getHealthLabel(status) {
  if (status === 'healthy') return '정상'
  if (status === 'warning') return '경고'
  if (status === 'missing') return '누락'
  return '확인 필요'
}

function getSignalGradeLabel(grade) {
  if (grade === 'STRONG_BUY_CANDIDATE') return '강한 후보'
  if (grade === 'WATCH') return '관찰'
  if (grade === 'RISKY') return '위험'
  if (grade === 'NO_SIGNAL') return '신호 없음'
  return grade || '미분류'
}

function getSignalGradeTone(grade) {
  if (grade === 'STRONG_BUY_CANDIDATE') return 'border-emerald-500/50 bg-emerald-950/40 text-emerald-300'
  if (grade === 'WATCH') return 'border-ai-cyan/50 bg-ai-cyan/10 text-ai-cyan'
  if (grade === 'RISKY') return 'border-rose-500/50 bg-rose-950/40 text-rose-300'
  return 'border-slate-700 bg-slate-900/60 text-slate-400'
}

function formatStaleness(minutes) {
  if (minutes === null || minutes === undefined || Number.isNaN(Number(minutes))) return '-'
  const numericMinutes = Number(minutes)
  if (numericMinutes < 60) return `${numericMinutes}분 전`
  if (numericMinutes < 1440) return `${Math.floor(numericMinutes / 60)}시간 전`
  return `${Math.floor(numericMinutes / 1440)}일 전`
}

function getCheckLabel(name) {
  return PROMOTION_CHECK_LABELS[name] || name
}

function findRegistryRow(rowsByAsset, assetType, modelVersion) {
  const assetKey = assetType === 'STOCK' ? 'stock' : 'crypto'
  return (rowsByAsset?.[assetKey] || []).find((row) => row.model_version === modelVersion || row.version === modelVersion)
}

function getSimpleGuardStatus(guardReport) {
  if (!guardReport) {
    return { label: '검증 정보 없음', tone: 'border-slate-700 bg-slate-900/60 text-slate-400' }
  }
  if (guardReport.passed) {
    return { label: '교체 가능', tone: 'border-emerald-500/40 bg-emerald-950/20 text-emerald-300' }
  }
  return { label: '기준 미달', tone: 'border-amber-500/40 bg-amber-950/20 text-amber-300' }
}

function formatCheckActual(value) {
  if (value === null || value === undefined || value === '') return '-'
  if (typeof value === 'object') return JSON.stringify(value)
  const numberValue = Number(value)
  if (Number.isNaN(numberValue)) return String(value)
  return numberValue.toFixed(4)
}

function summarizeFailedChecks(guardReport, limit = 3) {
  const failedChecks = guardReport?.failed_checks || []
  if (!failedChecks.length) {
    return []
  }

  return failedChecks.slice(0, limit).map((check) => {
    const actual = formatCheckActual(check.actual)
    const threshold = typeof check.threshold === 'object'
      ? JSON.stringify(check.threshold)
      : formatCheckActual(check.threshold)
    const comparator = check.comparator ? ` ${check.comparator} ${threshold}` : ''
    return `${getCheckLabel(check.name)}: ${actual}${comparator}`
  })
}

function buildQualityDetail(dataset) {
  if (!dataset) {
    return '-'
  }

  const quality = dataset.quality
  if (!quality) {
    return `${dataset.rows ?? 0} rows\n${dataset.path || '-'}`
  }

  const issueSummary = quality.issues?.length ? quality.issues.join('\n') : '이상 징후 없음'
  const staleText = quality.staleness_hours === null || quality.staleness_hours === undefined
    ? '-'
    : `${quality.staleness_hours}h`

  return [
    `${dataset.rows ?? quality.row_count ?? 0} rows / symbols ${quality.unique_symbol_count ?? 0}`,
    `status: ${getHealthLabel(quality.status)} / stale: ${staleText}`,
    `dup ${quality.duplicate_symbol_date_count ?? 0} / missing ${quality.missing_required_value_count ?? 0} / price ${quality.invalid_price_row_count ?? 0} / volume ${quality.invalid_volume_row_count ?? 0}`,
    issueSummary,
    dataset.path || quality.path || '-',
  ].join('\n')
}

function AuditBadge({ status, children }) {
  return (
    <span className={`rounded border px-2 py-1 text-[10px] font-bold ${getHealthTone(status)}`}>
      {children || getHealthLabel(status)}
    </span>
  )
}

function GuardSummary({ guardReport, compact = false }) {
  if (!guardReport) {
    return <p className="text-[10px] text-slate-500">승격 검증 정보가 아직 없습니다.</p>
  }

  const failedLines = summarizeFailedChecks(guardReport, compact ? 2 : 5)
  const tooltipText = failedLines.length ? failedLines.join('\n') : '모든 승격 기준을 통과했습니다.'
  const failedCount = guardReport.failed_checks?.length ?? 0

  return (
    <div className="space-y-1 inline-block" title={tooltipText}>
      <div className="flex items-center gap-1 whitespace-nowrap">
        <AuditBadge status={guardReport.passed ? 'healthy' : 'warning'}>
          {guardReport.passed 
            ? '승격 통과' 
            : `차단 (실패 ${failedCount}건)`}
        </AuditBadge>
      </div>
      {!compact && failedLines.length ? (
        <div className="space-y-1 mt-1">
          {failedLines.map((line) => (
            <p key={line} className="break-all text-[10px] leading-4 text-amber-200">
              {line}
            </p>
          ))}
        </div>
      ) : !compact ? (
        <p className="text-[10px] text-emerald-300">모든 승격 기준을 통과했습니다.</p>
      ) : null}
    </div>
  )
}

function findGuardCheck(guardReport, name) {
  return (guardReport?.checks || []).find((check) => check.name === name)
}

function formatTrustValue(check) {
  if (!check) return '-'
  const value = check.actual
  if (value === null || value === undefined || value === '') return '-'
  if (typeof value === 'object') return JSON.stringify(value)
  const numeric = Number(value)
  if (Number.isNaN(numeric)) return String(value)

  if (
    check.name?.includes('precision')
    || check.name?.includes('return')
    || check.name?.includes('drawdown')
    || check.name?.includes('drop')
  ) {
    return formatReturnPercent(numeric)
  }

  return formatMetric(numeric)
}

function TrustMetric({ label, check, hint }) {
  const status = check?.passed ? 'healthy' : 'warning'
  return (
    <div className="rounded-lg border border-slate-800 bg-[#0f172a] p-3">
      <div className="flex items-center justify-between gap-2">
        <p className="text-xs font-bold text-white">{label}</p>
        <AuditBadge status={status}>{check?.passed ? '통과' : '확인'}</AuditBadge>
      </div>
      <p className="mt-2 font-mono text-lg font-bold text-ai-cyan">{formatTrustValue(check)}</p>
      <p className="mt-1 text-[10px] leading-4 text-slate-500">{hint}</p>
    </div>
  )
}

function OperationalTrustPanel({ data, loading, error }) {
  const assets = data?.assets || {}

  return (
    <section className="rounded-lg border border-slate-700/80 bg-slate-surface p-5">
      <div className="mb-4">
        <p className="text-[10px] font-bold uppercase tracking-[0.16em] text-ai-cyan">Operational Trust</p>
        <h2 className="mt-1 text-xl font-bold text-white">운영 신뢰도 검증</h2>
        <p className="mt-2 text-xs leading-5 text-slate-400">
          모델 정확도만 보지 않고 데이터 품질, 시계열 검증, 상위 후보 품질, 비용 반영 초과수익, 최대 낙폭을 함께 확인합니다.
        </p>
      </div>

      {loading ? (
        <div className="rounded-lg border border-slate-800 bg-[#0f172a] p-4 text-sm text-slate-400">
          운영 신뢰도 정보를 불러오는 중입니다.
        </div>
      ) : error ? (
        <div className="rounded-lg border border-red-800 bg-red-950/30 p-4 text-sm leading-6 text-red-300">
          {error}
        </div>
      ) : !data ? (
        <div className="rounded-lg border border-slate-800 bg-[#0f172a] p-4 text-sm text-slate-400">
          아직 운영 신뢰도 정보가 없습니다.
        </div>
      ) : (
        <div className="grid gap-4 xl:grid-cols-2">
          {Object.entries(assets).map(([assetKey, report]) => {
            const guard = report.current_guard || report.recommended_guard
            const failedCount = guard?.failed_checks?.length ?? 0
            const totalCount = guard?.checks?.length ?? 0
            const passedCount = Math.max(0, totalCount - failedCount)
            const status = guard?.passed ? 'healthy' : 'warning'
            const failedLines = summarizeFailedChecks(guard, 3)

            return (
              <div key={assetKey} className="rounded-lg border border-slate-800 bg-black/10 p-4">
                <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                  <div>
                    <p className="text-sm font-bold text-white">{report.asset_type === 'STOCK' ? '주식 모델' : '코인 모델'}</p>
                    <p className="mt-1 text-xs leading-5 text-slate-400">
                      {guard?.passed
                        ? '참고 신호 운영 기준을 통과했습니다. 그래도 주문 실행은 사용자 승인 흐름을 유지합니다.'
                        : '일부 기준이 부족합니다. 참고 신호 노출은 가능하지만 승격/자동화 판단은 보류해야 합니다.'}
                    </p>
                  </div>
                  <AuditBadge status={status}>{guard?.passed ? '참고 신호 가능' : '보강 필요'}</AuditBadge>
                </div>

                <div className="mt-3 flex flex-wrap gap-2 text-[10px]">
                  <span className="rounded border border-slate-700 px-2 py-1 font-bold text-slate-300">
                    통과 {passedCount}/{totalCount || '-'}
                  </span>
                  <span className="rounded border border-fuchsia-500/30 px-2 py-1 font-bold text-fuchsia-300">
                    SERVING {report.serving_version || '-'}
                  </span>
                  <span className="rounded border border-emerald-500/30 px-2 py-1 font-bold text-emerald-300">
                    PICK {report.recommended_version || '-'}
                  </span>
                </div>

                <div className="mt-4 grid gap-3 sm:grid-cols-2">
                  <TrustMetric
                    label="데이터 품질"
                    check={findGuardCheck(guard, 'dataset_quality')}
                    hint="중복, 결측, 이상치, 최신성 기준"
                  />
                  <TrustMetric
                    label="시계열 CV"
                    check={findGuardCheck(guard, 'cv_roc_auc')}
                    hint="기간을 나눠도 구분력이 유지되는지"
                  />
                  <TrustMetric
                    label="상위 후보 적중"
                    check={findGuardCheck(guard, 'precision_at_top_10pct')}
                    hint="모델이 자신 있는 후보의 품질"
                  />
                  <TrustMetric
                    label="비용 반영 초과수익"
                    check={findGuardCheck(guard, 'composite_excess_return_net')}
                    hint="수수료/슬리피지 반영 후 시장 대비 우위"
                  />
                  <TrustMetric
                    label="최대 낙폭"
                    check={findGuardCheck(guard, 'max_drawdown_net')}
                    hint="운영 중 감당해야 하는 최대 손실 구간"
                  />
                  <TrustMetric
                    label="하락 위험 모델"
                    check={findGuardCheck(guard, 'risk_cv_roc_auc')}
                    hint="위험 신호를 분리해서 볼 수 있는지"
                  />
                </div>

                {failedLines.length ? (
                  <div className="mt-4 rounded-lg border border-amber-500/30 bg-amber-950/10 p-3">
                    <p className="text-[10px] font-bold uppercase tracking-wider text-amber-300">보강 필요 항목</p>
                    <div className="mt-2 space-y-1">
                      {failedLines.map((line) => (
                        <p key={line} className="break-all text-[10px] leading-5 text-amber-100">{line}</p>
                      ))}
                    </div>
                  </div>
                ) : null}
              </div>
            )
          })}
        </div>
      )}
    </section>
  )
}

function V8OptunaPanel({
  presets,
  trials,
  updateConfig,
  loadingKey,
  message,
  isLoggedIn,
  onTrialsChange,
  onUpdateConfigChange,
  onRun,
}) {
  return (
    <section className="rounded-lg border border-slate-700/80 bg-slate-surface p-5">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <p className="text-[10px] font-bold uppercase tracking-[0.16em] text-ai-cyan">Optuna HPO</p>
          <h2 className="mt-1 text-xl font-bold text-white">v8 하이퍼파라미터 튜닝</h2>
          <p className="mt-2 text-xs leading-5 text-slate-400">
            v8 Optuna는 이미 구성되어 있습니다. 실행 전 피처를 자동 생성한 뒤 LightGBM 파라미터를 탐색합니다.
          </p>
        </div>
        <span className="w-fit rounded border border-emerald-500/40 bg-emerald-950/20 px-2 py-1 text-[10px] font-bold text-emerald-300">
          V8 READY
        </span>
      </div>

      <div className="mt-4 grid gap-4 sm:grid-cols-2">
        <label className="flex flex-col gap-1.5 text-xs">
          <span className="font-bold text-slate-400">탐색 시도 횟수</span>
          <input
            type="number"
            min="5"
            max="100"
            value={trials}
            onChange={(event) => onTrialsChange(Number(event.target.value))}
            className="rounded border border-slate-700 bg-[#0f172a] px-3 py-2 font-mono text-white outline-none focus:border-ai-cyan"
          />
        </label>
        <label className="flex items-center gap-2 rounded border border-slate-800 bg-[#0f172a]/70 px-3 py-2">
          <input
            type="checkbox"
            checked={updateConfig}
            onChange={(event) => onUpdateConfigChange(event.target.checked)}
            className="h-4 w-4 accent-ai-cyan"
          />
          <span className="font-bold text-slate-300">최적 파라미터 YAML 자동 저장</span>
        </label>
      </div>

      <div className="mt-4 grid gap-3 md:grid-cols-2">
        {presets.map((preset) => (
          <button
            key={preset.key}
            type="button"
            onClick={() => onRun(preset)}
            disabled={loadingKey === preset.key || !isLoggedIn}
            className="rounded border border-ai-cyan/40 bg-ai-cyan/5 px-4 py-3 text-left transition hover:border-ai-cyan hover:bg-ai-cyan/10 disabled:cursor-not-allowed disabled:opacity-50"
          >
            <p className="text-sm font-bold text-white">
              {loadingKey === preset.key ? '튜닝 진행 중...' : preset.label}
            </p>
            <p className="mt-1 text-xs leading-5 text-slate-400">{preset.summary}</p>
            <p className="mt-1 break-all font-mono text-[10px] text-slate-500">{formatPath(preset.config)}</p>
          </button>
        ))}
      </div>

      {message ? (
        <div className="mt-4 rounded-lg border border-ai-cyan/30 bg-ai-cyan/5 p-4 text-sm text-ai-cyan">
          {message}
        </div>
      ) : null}
    </section>
  )
}

function ActiveSignalPanel({ title, data, loading, error, guardReport, onRefresh }) {
  const overview = data?.overview
  const filteredOverview = data?.filtered_overview
  const performance = data?.performance
  const predictions = data?.predictions || []
  const gradeCounts = filteredOverview?.grade_counts || overview?.grade_counts || {}

  return (
    <section className="rounded-lg border border-slate-700/80 bg-slate-surface p-5">
      <div className="mb-4 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <p className="text-[10px] font-bold uppercase tracking-[0.16em] text-ai-cyan">Active Signals</p>
          <h2 className="mt-1 text-xl font-bold text-white">{title}</h2>
        </div>
        <button
          type="button"
          onClick={onRefresh}
          disabled={loading}
          className="w-full rounded border border-slate-700 px-4 py-2 text-xs font-bold text-slate-300 transition hover:border-ai-cyan hover:text-white disabled:cursor-not-allowed disabled:opacity-50 sm:w-auto"
        >
          {loading ? '불러오는 중' : '신호 새로고침'}
        </button>
      </div>

      {loading ? (
        <div className="rounded-lg border border-slate-800 bg-[#0f172a] p-4 text-sm text-slate-400">
          활성 신호를 불러오는 중입니다.
        </div>
      ) : error ? (
        <div className="space-y-3">
          <div className="rounded-lg border border-amber-800 bg-amber-950/20 p-4 text-sm leading-6 text-amber-200">
            {error}
          </div>
          {guardReport ? (
            <div className="rounded-lg border border-slate-800 bg-[#0f172a] p-4">
              <p className="mb-2 text-[10px] font-bold uppercase tracking-wider text-slate-500">차단 사유</p>
              <GuardSummary guardReport={guardReport} compact />
            </div>
          ) : null}
        </div>
      ) : !data ? (
        <div className="space-y-3">
          <div className="rounded-lg border border-slate-800 bg-[#0f172a] p-4 text-sm text-slate-400">
            아직 활성 신호 데이터가 없습니다.
          </div>
          {guardReport ? (
            <div className="rounded-lg border border-slate-800 bg-[#0f172a] p-4">
              <p className="mb-2 text-[10px] font-bold uppercase tracking-wider text-slate-500">현재 검증 상태</p>
              <GuardSummary guardReport={guardReport} compact />
            </div>
          ) : null}
        </div>
      ) : (
        <div className="space-y-4">
          <div className="rounded-lg border border-slate-800 bg-[#0f172a] p-4">
            <p className="mb-2 text-[10px] font-bold uppercase tracking-wider text-slate-500">승격 검증 요약</p>
            <GuardSummary guardReport={guardReport} compact />
          </div>

          <div className="flex flex-wrap gap-2 text-[10px]">
            <span className="rounded border border-fuchsia-500/30 px-2 py-1 font-bold text-fuchsia-300">SERVING {data.serving_version || '-'}</span>
            <span className="rounded border border-emerald-500/30 px-2 py-1 font-bold text-emerald-300">PICK {data.recommended_version || '-'}</span>
            <span className="rounded border border-slate-600 px-2 py-1 font-bold text-slate-300">LATEST {data.latest_version || '-'}</span>
            <span className="rounded border border-ai-cyan/30 px-2 py-1 font-bold text-ai-cyan">{data.model_version || '-'}</span>
          </div>

          <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
            <div className="rounded-lg border border-slate-800 bg-[#0f172a] p-3">
              <p className="text-[10px] text-slate-500">전체 예측 수</p>
              <p className="mt-1 font-mono text-lg font-bold text-white">{overview?.total_predictions ?? 0}</p>
            </div>
            <div className="rounded-lg border border-slate-800 bg-[#0f172a] p-3">
              <p className="text-[10px] text-slate-500">LONG / HOLD / SHORT</p>
              <p className="mt-1 font-mono text-sm font-bold text-white">
                {overview?.long_count ?? 0} / {overview?.hold_count ?? 0} / {overview?.short_count ?? 0}
              </p>
            </div>
            <div className="rounded-lg border border-slate-800 bg-[#0f172a] p-3">
              <p className="text-[10px] text-slate-500">평균 상승 확률</p>
              <p className="mt-1 font-mono text-lg font-bold text-emerald-300">{formatPercent(filteredOverview?.avg_up_probability)}</p>
            </div>
            <div className="rounded-lg border border-slate-800 bg-[#0f172a] p-3">
              <p className="text-[10px] text-slate-500">평균 하락 위험</p>
              <p className="mt-1 font-mono text-lg font-bold text-amber-300">{formatPercent(filteredOverview?.avg_risk_probability)}</p>
            </div>
          </div>

          <div className="grid gap-2 sm:grid-cols-2 xl:grid-cols-4">
            <div className="rounded-lg border border-emerald-500/20 bg-emerald-950/10 p-3">
              <p className="text-[10px] text-emerald-300">강한 후보</p>
              <p className="mt-1 font-mono text-lg font-bold text-white">{gradeCounts.strong_buy_candidate ?? 0}</p>
            </div>
            <div className="rounded-lg border border-ai-cyan/20 bg-ai-cyan/5 p-3">
              <p className="text-[10px] text-ai-cyan">관찰</p>
              <p className="mt-1 font-mono text-lg font-bold text-white">{gradeCounts.watch ?? 0}</p>
            </div>
            <div className="rounded-lg border border-rose-500/20 bg-rose-950/10 p-3">
              <p className="text-[10px] text-rose-300">위험</p>
              <p className="mt-1 font-mono text-lg font-bold text-white">{gradeCounts.risky ?? 0}</p>
            </div>
            <div className="rounded-lg border border-slate-800 bg-[#0f172a] p-3">
              <p className="text-[10px] text-slate-500">신호 없음</p>
              <p className="mt-1 font-mono text-lg font-bold text-white">{gradeCounts.no_signal ?? 0}</p>
            </div>
          </div>

          <div className="grid gap-3 xl:grid-cols-2">
            <div className="rounded-lg border border-slate-800 bg-[#0f172a] p-4">
              <p className="text-[10px] font-bold uppercase tracking-wider text-slate-500">성능 스냅샷</p>
              <div className="mt-3 grid gap-2 text-xs text-slate-300">
                <p>시계열 CV 구분력: <span className="font-mono text-white">{formatMetric(performance?.cv_roc_auc)}</span></p>
                <p>상위 10% 적중: <span className="font-mono text-white">{formatMetric(performance?.precision_at_top_10pct)}</span></p>
                <p>하락 구분력: <span className="font-mono text-white">{formatMetric(performance?.risk_cv_roc_auc)}</span></p>
                <p>복합 초과수익(순): <span className="font-mono text-ai-cyan">{formatReturnPercent(performance?.composite_excess_return_net)}</span></p>
                <p>복합 적중률: <span className="font-mono text-white">{formatMetric(performance?.composite_precision_at_top_n)}</span></p>
              </div>
            </div>

            <div className="rounded-lg border border-slate-800 bg-[#0f172a] p-4">
              <p className="text-[10px] font-bold uppercase tracking-wider text-slate-500">현재 필터 결과</p>
              <div className="mt-3 grid gap-2 text-xs text-slate-300">
                <p>표시 개수: <span className="font-mono text-white">{predictions.length}</span></p>
                <p>최대 점수: <span className="font-mono text-white">{formatMetric(filteredOverview?.max_signal_score)}</span></p>
                <p>최소 점수: <span className="font-mono text-white">{formatMetric(filteredOverview?.min_signal_score)}</span></p>
                <p>평균 점수: <span className="font-mono text-white">{formatMetric(filteredOverview?.avg_signal_score)}</span></p>
                <p>마지막 예측 시각: <span className="font-mono break-all text-white">{filteredOverview?.latest_prediction_time || overview?.latest_prediction_time || '-'}</span></p>
              </div>
            </div>
          </div>

          {predictions.length ? (
            <div className="grid gap-2">
              {predictions.slice(0, 8).map((row) => (
                <div
                  key={`${data.asset_type}-${row.symbol}-${row.date}`}
                  className="grid gap-3 rounded-lg border border-slate-800 bg-[#0f172a] p-3 sm:grid-cols-[1fr_auto_auto_auto]"
                >
                  <div className="min-w-0">
                    <div className="flex flex-wrap items-center gap-2">
                      <p className="break-words text-sm font-bold text-white">{row.display_name || row.symbol}</p>
                      {row.position ? (
                        <span className={`rounded px-1.5 py-0.5 text-[9px] font-black tracking-widest ${
                          row.position === 'SHORT'
                            ? 'bg-rose-950/80 text-rose-300 border border-rose-700/60'
                            : row.position === 'LONG'
                              ? 'bg-emerald-950/80 text-emerald-300 border border-emerald-700/60'
                              : 'bg-slate-900/80 text-slate-300 border border-slate-700/60'
                        }`}>
                          {row.position}
                        </span>
                      ) : null}
                      <span className={`rounded border px-1.5 py-0.5 text-[9px] font-black tracking-widest ${getSignalGradeTone(row.signal_grade)}`}>
                        {getSignalGradeLabel(row.signal_grade)}
                      </span>
                    </div>
                    <div className="mt-1 flex flex-wrap gap-1.5">
                      <span className="rounded border border-slate-700 px-1.5 py-0.5 font-mono text-[10px] text-slate-400">
                        {row.symbol}
                      </span>
                      {row.market ? (
                        <span className="rounded border border-slate-700 px-1.5 py-0.5 text-[10px] text-slate-400">
                          {row.market}
                        </span>
                      ) : null}
                    </div>
                    <p className="mt-1 break-words text-xs text-slate-500">
                      {row.reason_summary || row.date}
                    </p>
                    <p className="mt-1 font-mono text-[10px] text-slate-600">
                      예측 {formatStaleness(row.staleness_minutes)} · {row.predicted_at || row.date || '-'}
                    </p>
                  </div>
                  <div>
                    <p className="text-[10px] font-bold uppercase tracking-wider text-slate-500">상승 확률</p>
                    <p className="font-mono text-sm text-emerald-300">{formatPercent(row.up_probability)}</p>
                  </div>
                  <div>
                    <p className="text-[10px] font-bold uppercase tracking-wider text-slate-500">하락 위험</p>
                    <p className="font-mono text-sm text-amber-300">{formatPercent(row.risk_probability)}</p>
                  </div>
                  <div>
                    <p className="text-[10px] font-bold uppercase tracking-wider text-slate-500">복합 점수</p>
                    <p className="font-mono text-sm text-ai-cyan">{formatMetric(row.signal_score)}</p>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div className="rounded-lg border border-slate-800 bg-[#0f172a] p-4 text-sm text-slate-400">
              현재 필터에 맞는 활성 신호가 없습니다.
            </div>
          )}
        </div>
      )}
    </section>
  )
}

function ServingAuditPanel({ data, loading, error, onRefresh }) {
  return (
    <section className="rounded-lg border border-slate-700/80 bg-slate-surface p-5">
      <div className="mb-4 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <p className="text-[10px] font-bold uppercase tracking-[0.16em] text-ai-cyan">Serving Audit</p>
          <h2 className="mt-1 text-xl font-bold text-white">운영 모델 감사</h2>
        </div>
        <button
          type="button"
          onClick={onRefresh}
          disabled={loading}
          className="w-full rounded border border-slate-700 px-4 py-2 text-xs font-bold text-slate-300 transition hover:border-ai-cyan hover:text-white disabled:cursor-not-allowed disabled:opacity-50 sm:w-auto"
        >
          {loading ? '불러오는 중' : '감사 결과 새로고침'}
        </button>
      </div>

      {loading ? (
        <div className="rounded-lg border border-slate-800 bg-[#0f172a] p-4 text-sm text-slate-400">
          운영 감사 정보를 불러오는 중입니다.
        </div>
      ) : error ? (
        <div className="rounded-lg border border-red-800 bg-red-950/30 p-4 text-sm leading-6 text-red-300">
          {error}
        </div>
      ) : !data ? (
        <div className="rounded-lg border border-slate-800 bg-[#0f172a] p-4 text-sm text-slate-400">
          아직 운영 감사 정보가 없습니다.
        </div>
      ) : (
        <div className="space-y-4">
          <div className="flex flex-wrap items-center gap-2 rounded-lg border border-slate-800 bg-[#0f172a] p-4">
            <AuditBadge status={data.status}>{data.status === 'healthy' ? '전체 정상' : '즉시 확인 필요'}</AuditBadge>
            <span className="text-sm text-slate-300">차단 항목 {data.blocking_count ?? 0}건</span>
          </div>

          <div className="grid gap-3 xl:grid-cols-2">
            {Object.entries(data.assets || {}).map(([assetKey, report]) => (
              <div key={assetKey} className="rounded-lg border border-slate-800 bg-[#0f172a] p-4">
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div>
                    <p className="text-xs font-bold text-white">{report.asset_type === 'STOCK' ? '주식 모델' : '코인 모델'}</p>
                    <p className="mt-1 text-xs leading-5 text-slate-400">{report.message}</p>
                  </div>
                  <AuditBadge status={report.status} />
                </div>

                <div className="mt-3 flex flex-wrap gap-2 text-[10px]">
                  <span className="rounded border border-fuchsia-500/30 px-2 py-1 font-bold text-fuchsia-300">SERVING {report.serving_version || '-'}</span>
                  <span className="rounded border border-emerald-500/30 px-2 py-1 font-bold text-emerald-300">PICK {report.recommended_version || '-'}</span>
                  <span className="rounded border border-slate-600 px-2 py-1 font-bold text-slate-300">LATEST {report.latest_version || '-'}</span>
                </div>

                {report.actions?.length ? (
                  <div className="mt-3 space-y-1">
                    {report.actions.map((action) => (
                      <p key={action} className="text-[10px] leading-5 text-slate-300">{action}</p>
                    ))}
                  </div>
                ) : null}

                <div className="mt-4 grid gap-3 md:grid-cols-2">
                  <div className="rounded border border-slate-800 bg-black/10 p-3">
                    <p className="mb-2 text-[10px] font-bold uppercase tracking-wider text-slate-500">현재 서빙 기준</p>
                    <GuardSummary guardReport={report.current_guard} compact />
                  </div>
                  <div className="rounded border border-slate-800 bg-black/10 p-3">
                    <p className="mb-2 text-[10px] font-bold uppercase tracking-wider text-slate-500">추천 후보 기준</p>
                    <GuardSummary guardReport={report.recommended_guard} compact />
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </section>
  )
}

function ModelSwitchPanel({ data, rowsByAsset, promotionChecks, loading, onActivate, activatingKey }) {
  const reports = Object.values(data?.assets || {})

  return (
    <section className="rounded-lg border border-ai-cyan/30 bg-ai-cyan/5 p-5">
      <div>
        <p className="text-[10px] font-bold uppercase tracking-[0.16em] text-ai-cyan">Model Switch</p>
        <h2 className="mt-1 text-xl font-bold text-white">모델 교체 판단</h2>
        <p className="mt-2 text-xs leading-5 text-slate-400">
          자동학습 결과 중 추천 후보가 기준을 통과하면 여기에서 바로 서비스 모델로 바꿀 수 있습니다.
        </p>
      </div>

      {loading ? (
        <div className="mt-4 rounded-lg border border-slate-800 bg-[#0f172a] p-4 text-sm text-slate-400">
          모델 교체 정보를 불러오는 중입니다.
        </div>
      ) : !reports.length ? (
        <div className="mt-4 rounded-lg border border-slate-800 bg-[#0f172a] p-4 text-sm text-slate-400">
          아직 교체 판단에 사용할 서빙 감사 정보가 없습니다.
        </div>
      ) : (
        <div className="mt-4 grid gap-3 lg:grid-cols-2">
          {reports.map((report) => {
            const recommendedVersion = report.recommended_model_version || report.recommended_version
            const servingVersion = report.serving_model_version || report.serving_version
            const recommendedRow = findRegistryRow(rowsByAsset, report.asset_type, recommendedVersion)
            const guardReport = recommendedVersion ? promotionChecks?.[`${report.asset_type}:${recommendedVersion}`] : null
            const guardStatus = getSimpleGuardStatus(guardReport)
            const canActivate = Boolean(recommendedRow && !recommendedRow.is_serving)
            const failedChecks = summarizeFailedChecks(guardReport, 2)

            return (
              <article key={report.asset_type} className="rounded-lg border border-slate-800 bg-[#0f172a] p-4">
                <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                  <div>
                    <p className="text-sm font-bold text-white">{report.asset_type === 'STOCK' ? '주식 모델' : '코인 모델'}</p>
                    <p className="mt-1 text-xs leading-5 text-slate-400">{report.message}</p>
                  </div>
                  <span className={`rounded border px-2 py-1 text-[10px] font-bold ${guardStatus.tone}`}>
                    {guardStatus.label}
                  </span>
                </div>

                <div className="mt-4 grid gap-2 text-xs sm:grid-cols-2">
                  <div className="rounded border border-slate-800 bg-black/15 p-3">
                    <p className="text-[10px] text-slate-500">현재 사용 중</p>
                    <p className="mt-1 break-all font-mono font-bold text-white">{servingVersion || '-'}</p>
                  </div>
                  <div className="rounded border border-slate-800 bg-black/15 p-3">
                    <p className="text-[10px] text-slate-500">추천 후보</p>
                    <p className="mt-1 break-all font-mono font-bold text-emerald-300">{recommendedVersion || '-'}</p>
                  </div>
                </div>

                {failedChecks.length ? (
                  <div className="mt-3 rounded border border-amber-500/30 bg-amber-950/10 px-3 py-2">
                    {failedChecks.map((item) => (
                      <p key={item} className="text-[10px] leading-5 text-amber-200">{item}</p>
                    ))}
                  </div>
                ) : (
                  <p className="mt-3 text-[10px] leading-5 text-slate-400">
                    기준을 통과한 후보는 강제 옵션 없이 서비스 반영할 수 있습니다.
                  </p>
                )}

                <button
                  type="button"
                  onClick={() => recommendedRow && onActivate?.(recommendedRow)}
                  disabled={!canActivate || Boolean(activatingKey)}
                  className="mt-4 w-full rounded border border-ai-cyan/40 px-3 py-2 text-xs font-bold text-ai-cyan transition hover:bg-ai-cyan/10 disabled:cursor-not-allowed disabled:border-slate-700 disabled:text-slate-500"
                >
                  {recommendedRow?.is_serving
                    ? '이미 반영됨'
                    : activatingKey === `${recommendedRow?.asset_type}:${recommendedRow?.model_version}`
                      ? '반영 중...'
                      : canActivate
                        ? '추천 후보로 교체'
                        : '교체 후보 없음'}
                </button>
              </article>
            )
          })}
        </div>
      )}
    </section>
  )
}

function JobHistoryPanel({ jobs = [], loading, error, onShowLog }) {
  if (loading) {
    return (
      <div className="rounded-lg border border-slate-800 bg-[#0f172a] p-4 text-sm text-slate-400">
        작업 이력을 불러오는 중입니다.
      </div>
    )
  }

  if (error) {
    return (
      <div className="rounded-lg border border-red-800 bg-red-950/30 p-4 text-sm leading-6 text-red-300">
        {error}
      </div>
    )
  }

  if (!jobs.length) {
    return (
      <div className="rounded-lg border border-slate-800 bg-[#0f172a] p-4 text-sm text-slate-400">
        아직 기록된 작업이 없습니다.
      </div>
    )
  }

  return (
    <div className="overflow-x-auto rounded-lg border border-slate-800 bg-[#0f172a]">
      <table className="min-w-full text-left text-xs text-slate-300">
        <thead className="text-[10px] uppercase tracking-wider text-slate-500">
          <tr>
            <th className="px-3 py-2">작업</th>
            <th className="px-3 py-2">유형</th>
            <th className="px-3 py-2">상태</th>
            <th className="px-3 py-2">설정</th>
            <th className="px-3 py-2">검증</th>
            <th className="px-3 py-2">시작</th>
            <th className="px-3 py-2">종료</th>
            <th className="px-3 py-2 text-right">로그</th>
          </tr>
        </thead>
        <tbody>
          {jobs.map((job) => (
            <tr key={job.id} className="border-t border-slate-800 align-top transition hover:bg-white/5">
              <td className="px-3 py-2">
                <p className="font-semibold text-white truncate max-w-[150px]" title={job.label || job.exchange || job.id}>
                  {job.label || job.exchange || job.id}
                </p>
                {job.output ? (
                  <p className="mt-1 truncate font-mono text-[10px] text-slate-500 max-w-[150px]" title={job.output}>
                    {formatPath(job.output)}
                  </p>
                ) : null}
                {job.failure_count ? (
                  <p className="mt-1 text-[10px] text-amber-300">실패 심볼 {job.failure_count}건</p>
                ) : null}
              </td>
              <td className="px-3 py-2 font-mono text-[10px] text-slate-400">{job.type}</td>
              <td className="px-3 py-2">
                <span className={`rounded border px-2 py-0.5 text-[9px] font-bold ${
                  job.status === 'success'
                    ? 'border-emerald-500/40 text-emerald-300 bg-emerald-950/20'
                    : job.status === 'failed'
                      ? 'border-red-500/40 text-red-300 bg-red-950/20'
                      : 'border-ai-cyan/40 text-ai-cyan bg-ai-cyan/5'
                }`}>
                  {String(job.status || 'running').toUpperCase()}
                </span>
              </td>
              <td className="px-3 py-2">
                <p className="truncate font-mono text-[10px] text-slate-400 max-w-[150px]" title={job.config || job.interval || '-'}>
                  {formatPath(job.config) || job.interval || '-'}
                </p>
              </td>
              <td className="px-3 py-2">
                <div className="min-w-[180px] space-y-1">
                  {job.training_audit?.promotion_guard ? (
                    <GuardSummary guardReport={job.training_audit.promotion_guard} compact />
                  ) : job.guard_report ? (
                    <GuardSummary guardReport={job.guard_report} compact />
                  ) : job.serving_audit_report ? (
                    <div className="space-y-1">
                      <AuditBadge status={job.serving_audit_report.status}>
                        {job.serving_audit_report.status === 'healthy' ? '서빙 정상' : '서빙 경고'}
                      </AuditBadge>
                      <p className="text-[10px] text-slate-500">
                        차단 {job.serving_audit_report.blocking_count ?? 0}건
                      </p>
                    </div>
                  ) : (
                    <p className="text-[10px] text-slate-500">감사 정보 없음</p>
                  )}
                </div>
              </td>
              <td className="px-3 py-2 font-mono text-[10px] text-slate-400 whitespace-nowrap">{formatTime(job.started_at)}</td>
              <td className="px-3 py-2 font-mono text-[10px] text-slate-400 whitespace-nowrap">{formatTime(job.finished_at)}</td>
              <td className="px-3 py-2 text-right">
                <button
                  type="button"
                  onClick={() => onShowLog?.(job)}
                  className="rounded border border-slate-700 bg-slate-800/40 px-2 py-1 text-[10px] font-bold text-slate-300 transition hover:border-ai-cyan hover:text-white"
                >
                  로그 보기
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function RegistryPanel({ title, rows = [], loading, error, onActivate, activatingKey, promotionChecks = {}, promotionChecksLoading = false }) {
  return (
    <div className="rounded-lg border border-slate-700/80 bg-slate-surface p-5">
      <div className="mb-4">
        <p className="text-[10px] font-bold uppercase tracking-[0.16em] text-ai-cyan">Model Registry</p>
        <h3 className="mt-1 text-lg font-bold text-white">{title}</h3>
      </div>

      {loading ? (
        <div className="rounded-lg border border-slate-800 bg-[#0f172a] p-4 text-sm text-slate-400">
          레지스트리 상태를 불러오는 중입니다.
        </div>
      ) : error ? (
        <div className="rounded-lg border border-red-800 bg-red-950/30 p-4 text-sm leading-6 text-red-300">
          {error}
        </div>
      ) : !rows.length ? (
        <div className="rounded-lg border border-slate-800 bg-[#0f172a] p-4 text-sm text-slate-400">
          아직 레지스트리 정보가 없습니다.
        </div>
      ) : (
        <div className="overflow-x-auto rounded-lg border border-slate-800 bg-[#0f172a]">
          <table className="min-w-full text-left text-xs text-slate-300">
            <thead className="text-[10px] uppercase tracking-wider text-slate-500">
              <tr>
                <th className="px-3 py-2">모델 버전</th>
                <th className="px-3 py-2">CV 구분력</th>
                <th className="px-3 py-2">상위 10%</th>
                <th className="px-3 py-2">상태</th>
                <th className="px-3 py-2">승격 검증</th>
                <th className="px-3 py-2">작업</th>
                <th className="px-3 py-2">경로</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => {
                const guardReport = promotionChecks[`${row.asset_type}:${row.model_version}`]

                return (
                <tr key={`${row.asset_type}-${row.model_version}`} className="border-t border-slate-800 align-top">
                  <td className="px-3 py-2">
                    <p className="font-mono text-white">{row.model_version}</p>
                    <p className="mt-1 text-[10px] text-slate-500">{row.version || '-'}</p>
                  </td>
                  <td className="px-3 py-2 font-mono">{formatMetric(row.cv_roc_auc || row.roc_auc)}</td>
                  <td className="px-3 py-2 font-mono">{formatMetric(row.cv_top10_precision)}</td>
                  <td className="px-3 py-2">
                    <div className="flex flex-wrap gap-1">
                      {row.is_latest ? (
                        <span className="rounded border border-slate-600 px-2 py-1 text-[10px] font-bold text-slate-300">최신</span>
                      ) : null}
                      {row.is_recommended ? (
                        <span className="rounded border border-emerald-500/40 px-2 py-1 text-[10px] font-bold text-emerald-300">추천</span>
                      ) : null}
                      {row.is_serving ? (
                        <span className="rounded border border-ai-cyan/40 px-2 py-1 text-[10px] font-bold text-ai-cyan">서비스 적용</span>
                      ) : null}
                      {!row.is_latest && !row.is_recommended && !row.is_serving ? (
                        <span className="rounded border border-slate-700 px-2 py-1 text-[10px] font-bold text-slate-500">분석 중</span>
                      ) : null}
                    </div>
                  </td>
                  <td className="px-3 py-2">
                    {guardReport ? (
                      <GuardSummary guardReport={guardReport} compact />
                    ) : promotionChecksLoading ? (
                      <p className="text-[10px] text-slate-500">검증 중...</p>
                    ) : (
                      <p className="text-[10px] text-slate-500">검증 정보 없음</p>
                    )}
                  </td>
                  <td className="px-3 py-2">
                    <button
                      type="button"
                      onClick={() => onActivate?.(row)}
                      disabled={Boolean(activatingKey) || row.is_serving}
                      className={`rounded border px-2 py-1 text-[10px] font-bold transition ${
                        row.is_serving
                          ? 'border-slate-700 text-slate-500'
                          : 'border-ai-cyan/40 text-ai-cyan hover:bg-ai-cyan/10'
                      } disabled:cursor-not-allowed disabled:opacity-50`}
                    >
                      {activatingKey === `${row.asset_type}:${row.model_version}`
                        ? '반영 중...'
                        : row.is_serving
                          ? '반영됨'
                          : '서비스 반영'}
                    </button>
                  </td>
                  <td className="px-3 py-2 font-mono text-[10px] text-slate-500">
                    <div className="max-w-[200px] truncate block" title={row.summary_path || row.metrics_path}>
                      {formatPath(row.summary_path || row.metrics_path)}
                    </div>
                  </td>
                </tr>
              )})}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}

function ReadinessItem({ label, status, detail }) {
  return (
    <div className="rounded-lg border border-slate-800 bg-[#0f172a] p-3">
      <div className="flex items-center justify-between gap-3">
        <p className="text-xs font-bold text-white">{label}</p>
        <span className={`rounded border px-2 py-1 text-[10px] font-bold ${
          status ? 'border-emerald-500/40 text-emerald-300' : 'border-amber-500/40 text-amber-300'
        }`}>
          {status ? '준비 완료' : '확인 필요'}
        </span>
      </div>
      <p className="mt-2 break-all whitespace-pre-line font-mono text-[10px] leading-5 text-slate-500">{formatPathInText(detail)}</p>
    </div>
  )
}

function ReadinessPanel({ data, loading, error, onRefresh }) {
  return (
    <section className="rounded-lg border border-slate-700/80 bg-slate-surface p-5">
      <div className="mb-4 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <p className="text-[10px] font-bold uppercase tracking-[0.16em] text-ai-cyan">Readiness</p>
          <h2 className="mt-1 text-xl font-bold text-white">운영 준비 상태</h2>
        </div>
        <button
          type="button"
          onClick={onRefresh}
          disabled={loading}
          className="w-full rounded border border-slate-700 px-4 py-2 text-xs font-bold text-slate-300 transition hover:border-ai-cyan hover:text-white disabled:cursor-not-allowed disabled:opacity-50 sm:w-auto"
        >
          {loading ? '불러오는 중' : '준비 상태 새로고침'}
        </button>
      </div>

      {loading ? (
        <div className="rounded-lg border border-slate-800 bg-[#0f172a] p-4 text-sm text-slate-400">
          운영 준비 상태를 불러오는 중입니다.
        </div>
      ) : error ? (
        <div className="rounded-lg border border-red-800 bg-red-950/30 p-4 text-sm leading-6 text-red-300">
          {error}
        </div>
      ) : !data ? (
        <div className="rounded-lg border border-slate-800 bg-[#0f172a] p-4 text-sm text-slate-400">
          아직 준비 상태 정보가 없습니다.
        </div>
      ) : (
        <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
          <ReadinessItem
            label="Toss 키"
            status={data.keys?.toss_ready}
            detail={data.keys?.toss_ready
              ? `Supabase 저장 키를 백엔드에서 복호화해 사용 가능\nsource: ${data.keys?.toss_source || '-'}\naccountSeq: ${data.keys?.toss_account_seq_ready ? 'READY' : 'CHECK'} / env: ${data.keys?.toss_broker_env || '-'} / records: ${data.keys?.toss_record_count ?? 0}`
              : `Toss 키 저장 또는 연결 확인 필요\nsource: ${data.keys?.toss_source || '-'}`}
          />
          <ReadinessItem
            label="주식 원천 CSV"
            status={data.datasets?.stock_raw?.quality?.status === 'healthy'}
            detail={buildQualityDetail(data.datasets?.stock_raw)}
          />
          <ReadinessItem
            label="코인 원천 CSV"
            status={data.datasets?.crypto_raw?.quality?.status === 'healthy'}
            detail={buildQualityDetail(data.datasets?.crypto_raw)}
          />
          <ReadinessItem
            label="매크로 지표"
            status={data.datasets?.macro_raw?.exists}
            detail={`${data.datasets?.macro_raw?.rows ?? 0} rows\n${data.datasets?.macro_raw?.path || '-'}`}
          />
          <ReadinessItem
            label="외부 피처"
            status={Boolean(data.feature_sources?.news_features?.exists || data.feature_sources?.crypto_market_features?.exists || data.feature_sources?.stock_event_features?.exists)}
            detail={`news ${data.feature_sources?.news_features?.rows ?? 0} / crypto ${data.feature_sources?.crypto_market_features?.rows ?? 0} / stock ${data.feature_sources?.stock_event_features?.rows ?? 0}`}
          />
          <ReadinessItem
            label="SERVING 상태"
            status={Boolean(data.registry?.stock_serving || data.registry?.crypto_serving)}
            detail={`stock: ${data.registry?.stock_serving || '-'}\ncrypto: ${data.registry?.crypto_serving || '-'}`}
          />
        </div>
      )}
    </section>
  )
}

function ExecutionChecklistPanel() {
  const steps = [
    '운영 준비 상태에서 Toss 키와 원천 CSV 상태를 먼저 확인',
    '필요하면 CSV 생성 또는 stock-v7-full / crypto-v7-full 실행',
    '작업 이력 success와 summary 파일 생성 여부 확인',
    '버전 비교 표에서 SERVING / PICK / LATEST와 백테스트 비교',
    '레지스트리 패널에서 검토 완료 버전을 서비스 반영',
    'active-model 기준 선택 결과가 기대와 같은지 재확인',
  ]

  return (
    <section className="rounded-lg border border-slate-700/80 bg-slate-surface p-5">
      <div className="mb-4">
        <p className="text-[10px] font-bold uppercase tracking-[0.16em] text-ai-cyan">Checklist</p>
        <h2 className="mt-1 text-xl font-bold text-white">실행 순서</h2>
      </div>
      <div className="grid gap-3">
        {steps.map((step, index) => (
          <div key={step} className="flex gap-3 rounded-lg border border-slate-800 bg-[#0f172a] p-3">
            <div className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full border border-ai-cyan/40 font-mono text-[10px] font-bold text-ai-cyan">
              {index + 1}
            </div>
            <p className="text-sm leading-6 text-slate-300">{step}</p>
          </div>
        ))}
      </div>
    </section>
  )
}

function ReportPanel({ loading, message, onGenerate }) {
  return (
    <section className="rounded-lg border border-slate-700/80 bg-slate-surface p-5">
      <div className="mb-4">
        <p className="text-[10px] font-bold uppercase tracking-[0.16em] text-ai-cyan">Report</p>
        <h2 className="mt-1 text-xl font-bold text-white">실험 리포트 저장</h2>
      </div>
      <p className="text-sm leading-6 text-slate-400">
        현재 summary JSON과 serving 상태를 기준으로 Markdown 리포트를 생성합니다.
      </p>
      <div className="mt-4">
        <button
          type="button"
          onClick={onGenerate}
          disabled={loading}
          className="rounded border border-ai-cyan/40 px-4 py-2 text-xs font-bold text-ai-cyan transition hover:bg-ai-cyan/10 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {loading ? '리포트 생성 중...' : '리포트 생성'}
        </button>
      </div>
      {message ? (
        <div className="mt-4 rounded-lg border border-ai-cyan/30 bg-ai-cyan/5 p-4 text-sm text-ai-cyan">
          {message}
        </div>
      ) : null}
    </section>
  )
}

function ReportHistoryPanel({ reports = [], loading, error, onRefresh }) {
  return (
    <section className="rounded-lg border border-slate-700/80 bg-slate-surface p-5">
      <div className="mb-4 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <p className="text-[10px] font-bold uppercase tracking-[0.16em] text-ai-cyan">Reports</p>
          <h2 className="mt-1 text-xl font-bold text-white">최근 실험 리포트</h2>
        </div>
        <button
          type="button"
          onClick={onRefresh}
          disabled={loading}
          className="w-full rounded border border-slate-700 px-4 py-2 text-xs font-bold text-slate-300 transition hover:border-ai-cyan hover:text-white disabled:cursor-not-allowed disabled:opacity-50 sm:w-auto"
        >
          {loading ? '불러오는 중' : '리포트 목록 새로고침'}
        </button>
      </div>

      {loading ? (
        <div className="rounded-lg border border-slate-800 bg-[#0f172a] p-4 text-sm text-slate-400">
          리포트 목록을 불러오는 중입니다.
        </div>
      ) : error ? (
        <div className="rounded-lg border border-red-800 bg-red-950/30 p-4 text-sm leading-6 text-red-300">
          {error}
        </div>
      ) : !reports.length ? (
        <div className="rounded-lg border border-slate-800 bg-[#0f172a] p-4 text-sm text-slate-400">
          아직 생성된 실험 리포트가 없습니다.
        </div>
      ) : (
        <div className="grid gap-3">
          {reports.map((report) => (
            <div key={report.path} className="rounded-lg border border-slate-800 bg-[#0f172a] p-3">
              <p className="break-all font-mono text-sm text-white">{report.name}</p>
              <p className="mt-1 font-mono text-[10px] text-slate-500 truncate block" title={report.path}>
                {formatPath(report.path)}
              </p>
              <div className="mt-2 flex flex-wrap gap-2 text-[10px] text-slate-400">
                <span>{report.updated_at}</span>
                <span>{report.size_bytes} bytes</span>
              </div>
            </div>
          ))}
        </div>
      )}
    </section>
  )
}

function VersionComparisonTable({ versions = [], selectedVersion, recommendedVersion, latestVersion, servingVersion, onSelectVersion }) {
  if (!versions.length) {
    return null
  }

  return (
    <div className="mt-5 rounded-lg border border-slate-800 bg-[#0f172a] p-4">
      <div className="mb-3 flex items-center justify-between gap-3">
        <p className="text-xs font-bold uppercase tracking-wider text-slate-400">버전 비교</p>
        <div className="flex flex-wrap gap-2">
          <span className="rounded border border-ai-cyan/40 px-2 py-1 text-[10px] font-bold text-ai-cyan">
            현재 선택: {selectedVersion || '-'}
          </span>
          <span className="rounded border border-fuchsia-500/40 px-2 py-1 text-[10px] font-bold text-fuchsia-300">
            서비스 반영: {servingVersion || '-'}
          </span>
          <span className="rounded border border-emerald-500/40 px-2 py-1 text-[10px] font-bold text-emerald-300">
            추천: {recommendedVersion || '-'}
          </span>
          <span className="rounded border border-slate-600 px-2 py-1 text-[10px] font-bold text-slate-300">
            최신: {latestVersion || '-'}
          </span>
        </div>
      </div>

      <div className="overflow-x-auto">
        <table className="min-w-full text-left text-xs text-slate-300">
          <thead className="text-[10px] uppercase tracking-wider text-slate-500">
            <tr>
              <th className="px-2 py-2">버전</th>
              <th className="px-2 py-2">CV 구분력</th>
              <th className="px-2 py-2">상위 10% 적중</th>
              <th className="px-2 py-2">하락 구분력</th>
              <th className="px-2 py-2">복합 초과수익(순)</th>
              <th className="px-2 py-2">복합 승률</th>
              <th className="px-2 py-2">최대낙폭</th>
              <th className="px-2 py-2">검증 행 수</th>
              <th className="px-2 py-2">상태</th>
            </tr>
          </thead>
          <tbody>
            {versions
              .slice()
              .sort((a, b) => (b.version_number || 0) - (a.version_number || 0))
              .map((version) => (
                <tr
                  key={version.version}
                  className="cursor-pointer border-t border-slate-800 transition hover:bg-white/5"
                  onClick={() => onSelectVersion?.(version.version)}
                >
                  <td className="px-2 py-2 font-mono text-white">{version.version}</td>
                  <td className="px-2 py-2">{formatMetric(version.metrics?.time_series_cv_average?.roc_auc || version.metrics?.roc_auc)}</td>
                  <td className="px-2 py-2">{formatMetric(version.metrics?.time_series_cv_average?.precision_at_top_10pct || version.metrics?.precision_at_top_10pct)}</td>
                  <td className="px-2 py-2">{formatMetric(version.risk_metrics?.time_series_cv_average?.roc_auc || version.risk_metrics?.roc_auc)}</td>
                  <td className="px-2 py-2 font-mono">{formatVersionBacktest(version, 'excess_return_net')}</td>
                  <td className="px-2 py-2">{formatPercent(version.backtests?.composite?.data?.selection_win_rate_net ?? version.backtests?.composite?.data?.selection_win_rate)}</td>
                  <td className="px-2 py-2 font-mono">{formatReturnPercent(version.backtests?.composite?.data?.max_drawdown_net ?? version.backtests?.composite?.data?.max_drawdown)}</td>
                  <td className="px-2 py-2">{version.metrics?.valid_rows ?? '-'}</td>
                  <td className="px-2 py-2">
                    <div className="flex flex-wrap gap-1">
                      <span className={`rounded border px-2 py-1 text-[10px] font-bold ${
                        version.version === selectedVersion
                          ? 'border-ai-cyan/40 text-ai-cyan'
                          : version.updated
                            ? 'border-emerald-500/40 text-emerald-300'
                            : 'border-slate-700 text-slate-500'
                      }`}>
                        {version.version === selectedVersion ? '분석 중' : version.updated ? '준비 완료' : '데이터 없음'}
                      </span>
                      {version.version === recommendedVersion ? (
                        <span className="rounded border border-emerald-500/30 px-2 py-1 text-[10px] font-bold text-emerald-300">
                          추천
                        </span>
                      ) : null}
                      {version.version === servingVersion || version.is_serving ? (
                        <span className="rounded border border-fuchsia-500/30 px-2 py-1 text-[10px] font-bold text-fuchsia-300">
                          서비스 적용
                        </span>
                      ) : null}
                      {version.version === latestVersion ? (
                        <span className="rounded border border-slate-600 px-2 py-1 text-[10px] font-bold text-slate-300">
                          최신
                        </span>
                      ) : null}
                    </div>
                  </td>
                </tr>
              ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

function ModelResultCard({ title, result }) {
  const versions = useMemo(() => result?.versions || [], [result?.versions])
  const defaultSelectedVersion = result?.serving_version || result?.recommended_version || result?.selected_version || ''
  const [selectedVersion, setSelectedVersion] = useState(defaultSelectedVersion)
  const resolvedSelectedVersion = versions.some((item) => item.version === selectedVersion)
    ? selectedVersion
    : defaultSelectedVersion

  const activeResult = useMemo(() => {
    if (!versions.length) return result
    return versions.find((item) => item.version === resolvedSelectedVersion) || result
  }, [result, resolvedSelectedVersion, versions])

  const metrics = activeResult?.metrics
  const riskMetrics = activeResult?.risk_metrics
  const predictions = activeResult?.predictions || []
  const upOnlyBacktest = activeResult?.backtests?.up_only?.data
  const compositeBacktest = activeResult?.backtests?.composite?.data
  const comparisonBaselines = useMemo(() => {
    const candidates = [
      { label: '서비스 반영 기준', version: result?.serving_version },
      { label: '추천 기준', version: result?.recommended_version },
      { label: '최신 기준', version: result?.latest_version },
    ]

    return candidates
      .filter((candidate, index, array) => candidate.version && array.findIndex((item) => item.version === candidate.version) === index)
      .map((candidate) => ({
        ...candidate,
        ...versions.find((item) => item.version === candidate.version),
      }))
      .filter((candidate) => candidate.version)
  }, [result?.latest_version, result?.recommended_version, result?.serving_version, versions])

  const renderProgressBar = (value, minVal = 0.5, maxVal = 0.65) => {
    if (value === null || value === undefined || Number.isNaN(Number(value))) return null
    const num = Number(value)
    const percent = Math.max(0, Math.min(100, ((num - minVal) / (maxVal - minVal)) * 100))
    
    let colorClass = 'bg-red-500 shadow-[0_0_8px_rgba(239,68,68,0.5)]'
    if (num >= 0.55) {
      colorClass = 'bg-ai-cyan shadow-[0_0_8px_rgba(0,243,255,0.5)]'
    } else if (num >= 0.51) {
      colorClass = 'bg-amber-500 shadow-[0_0_8px_rgba(245,158,11,0.5)]'
    }

    return (
      <div className="mt-2 h-1.5 w-full rounded-full bg-slate-800 overflow-hidden">
        <div 
          className={`h-full rounded-full transition-all duration-500 ${colorClass}`}
          style={{ width: `${percent}%` }}
        />
      </div>
    )
  }

  const renderMetricValue = (val, isPercent = false, isReturn = false) => {
    if (val === null || val === undefined || Number.isNaN(Number(val))) {
      return <span className="font-mono text-slate-500">-</span>
    }
    const num = Number(val)
    const text = isPercent ? formatPercent(num) : (isReturn ? formatReturnPercent(num) : formatMetric(num))
    
    if (num > 0) {
      return <span className="font-mono text-emerald-400 font-bold">+{text}</span>
    } else if (num < 0) {
      return <span className="font-mono text-rose-500 font-bold">{text}</span>
    }
    return <span className="font-mono text-slate-300">{text}</span>
  }

  return (
    <article className="rounded-lg border border-slate-700/80 bg-slate-surface p-5">
      <div className="mb-4 flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <p className="text-[10px] font-bold uppercase tracking-[0.16em] text-ai-cyan">{activeResult?.asset_type || result?.asset_type || '-'}</p>
          <h3 className="mt-1 text-sm font-bold uppercase tracking-wider text-white">{title}</h3>
        </div>
        <span className={`w-fit rounded border px-2 py-1 text-[10px] font-bold ${
          activeResult?.updated ? 'border-emerald-500/40 text-emerald-300' : 'border-slate-700 text-slate-500'
        }`}>
          {activeResult?.updated ? 'READY' : 'NO DATA'}
        </span>
      </div>

      <div className="mb-4 flex flex-wrap gap-2">
        <span className="rounded border border-fuchsia-500/30 px-2 py-1 text-[10px] font-bold text-fuchsia-300">
          SERVING {result?.serving_version || '-'}
        </span>
        <span className="rounded border border-emerald-500/30 px-2 py-1 text-[10px] font-bold text-emerald-300">
          PICK {result?.recommended_version || '-'}
        </span>
        <span className="rounded border border-slate-600 px-2 py-1 text-[10px] font-bold text-slate-300">
          LATEST {result?.latest_version || '-'}
        </span>
      </div>

      {metrics ? (
        <div className="grid gap-3 sm:grid-cols-3">
          <div className="rounded-lg bg-[#0f172a] p-3 border border-slate-800 hover:border-slate-700 transition">
            <p className="text-xs font-bold text-slate-400">구분력 (ROC-AUC)</p>
            <p className="mt-0.5 text-[10px] leading-4 text-slate-500 font-sans">상승/비상승을 가르는 전체 힘</p>
            <p className="mt-1 font-mono text-xl font-bold text-white">{formatMetric(metrics.roc_auc)}</p>
            {renderProgressBar(metrics.roc_auc, 0.5, 0.65)}
          </div>
          <div className="rounded-lg bg-[#0f172a] p-3 border border-slate-800 hover:border-slate-700 transition">
            <p className="text-xs font-bold text-slate-400">시계열 CV 구분력</p>
            <p className="mt-0.5 text-[10px] leading-4 text-slate-500 font-sans">기간 분할 검증 평균 구분력</p>
            <p className="mt-1 font-mono text-xl font-bold text-white">{formatMetric(metrics.time_series_cv_average?.roc_auc || metrics.roc_auc)}</p>
            {renderProgressBar(metrics.time_series_cv_average?.roc_auc || metrics.roc_auc, 0.5, 0.65)}
          </div>
          <div className="rounded-lg bg-[#0f172a] p-3 border border-slate-800 hover:border-slate-700 transition">
            <p className="text-xs font-bold text-slate-400">상위 10% 적중</p>
            <p className="mt-0.5 text-[10px] leading-4 text-slate-500 font-sans">점수 상위 후보의 실제 상승 비율</p>
            <p className="mt-1 font-mono text-xl font-bold text-white">{formatMetric(metrics.time_series_cv_average?.precision_at_top_10pct || metrics.precision_at_top_10pct)}</p>
            {renderProgressBar(metrics.time_series_cv_average?.precision_at_top_10pct || metrics.precision_at_top_10pct, 0.1, 0.3)}
          </div>
          <div className="rounded-lg bg-[#0f172a] p-3 border border-slate-800 hover:border-slate-700 transition">
            <p className="text-xs font-bold text-slate-400">상승 적중도 (AP)</p>
            <p className="mt-0.5 text-[10px] leading-4 text-slate-500 font-sans font-sans">상승 후보 쪽 랭킹 신뢰도</p>
            <p className="mt-1 font-mono text-xl font-bold text-white">{formatMetric(metrics.average_precision)}</p>
          </div>
          <div className="rounded-lg bg-[#0f172a] p-3 border border-slate-800 hover:border-slate-700 transition">
            <p className="text-xs font-bold text-slate-400">Precision / Recall</p>
            <p className="mt-0.5 text-[10px] leading-4 text-slate-500 font-sans">예측 정확도 / 탐지 커버리지</p>
            <p className="mt-1 font-mono text-sm font-bold text-white">
              {formatMetric(metrics.precision)} / {formatMetric(metrics.recall)}
            </p>
          </div>
          <div className="rounded-lg bg-[#0f172a] p-3 border border-slate-800 hover:border-slate-700 transition">
            <p className="text-xs font-bold text-slate-400">전체 정답률</p>
            <p className="mt-0.5 text-[10px] leading-4 text-slate-500 font-sans">전체 0/1 매칭 비율</p>
            <p className="mt-1 font-mono text-xl font-bold text-white">{formatMetric(metrics.accuracy)}</p>
          </div>
          <div className="rounded-lg bg-[#0f172a] p-3 sm:col-span-3 border border-slate-800 font-sans">
            <p className="text-xs text-slate-500">학습/검증 구간</p>
            <p className="mt-1 break-words font-mono text-xs leading-5 text-slate-300">
              train {metrics.train_rows} rows: {metrics.train_start_date} ~ {metrics.train_end_date}
            </p>
            <p className="break-words font-mono text-xs leading-5 text-slate-300">
              valid {metrics.valid_rows} rows: {metrics.valid_start_date} ~ {metrics.valid_end_date}
            </p>
          </div>
        </div>
      ) : (
        <div className="rounded-lg border border-slate-800 bg-[#0f172a] p-4 text-sm text-slate-400 font-sans">
          아직 학습 결과 파일이 없습니다.
        </div>
      )}

      <div className="mt-5 grid gap-4 xl:grid-cols-2">
        <div className="rounded-lg border border-slate-800 bg-[#0f172a] p-4">
          <p className="text-xs font-bold uppercase tracking-wider text-slate-400">하락 위험 모델</p>
          {riskMetrics ? (
            <div className="mt-3 grid gap-2 sm:grid-cols-3">
              <div>
                <p className="text-[10px] text-slate-500 font-sans">구분력 (ROC-AUC)</p>
                <p className="font-mono text-sm text-white">{formatMetric(riskMetrics.roc_auc)}</p>
                {renderProgressBar(riskMetrics.roc_auc, 0.5, 0.65)}
              </div>
              <div>
                <p className="text-[10px] text-slate-500 font-sans">상위후보 적중도</p>
                <p className="font-mono text-sm text-white">{formatMetric(riskMetrics.average_precision)}</p>
              </div>
              <div>
                <p className="text-[10px] text-slate-500 font-sans">전체 정답률</p>
                <p className="font-mono text-sm text-white">{formatMetric(riskMetrics.accuracy)}</p>
              </div>
            </div>
          ) : (
            <p className="mt-3 text-sm text-slate-400 font-sans">아직 risk_label 모델 결과가 없습니다.</p>
          )}
        </div>

        <div className="rounded-lg border border-slate-800 bg-[#0f172a] p-4">
          <p className="text-xs font-bold uppercase tracking-wider text-slate-400">백테스트 요약</p>
          <div className="mt-3 grid gap-3">
            <div className="rounded-lg border border-slate-800 bg-black/10 p-3 font-sans">
              <p className="text-[10px] font-bold uppercase tracking-wider text-slate-500">상승 점수 기준</p>
              {upOnlyBacktest ? (
                <div className="mt-2 grid gap-1 text-xs text-slate-300">
                  <p>상위 {upOnlyBacktest.top_n}개 평균 수익률: {renderMetricValue(upOnlyBacktest.top_avg_future_return, false, true)}</p>
                  <p>비용 반영 평균 수익률: {renderMetricValue(upOnlyBacktest.top_avg_future_return_net, false, true)}</p>
                  <p>전체 평균 수익률: {renderMetricValue(upOnlyBacktest.universe_avg_future_return, false, true)}</p>
                  <p>순 초과 수익률: {renderMetricValue(upOnlyBacktest.excess_return_net ?? upOnlyBacktest.excess_return, false, true)}</p>
                  <p>후보 승률: <span className="font-mono text-white">{formatPercent(upOnlyBacktest.selection_win_rate_net ?? upOnlyBacktest.selection_win_rate)}</span></p>
                </div>
              ) : (
                <p className="mt-2 text-sm text-slate-400">아직 단순 백테스트 결과가 없습니다.</p>
              )}
            </div>

            <div className="rounded-lg border border-slate-800 bg-black/10 p-3 font-sans">
              <p className="text-[10px] font-bold uppercase tracking-wider text-slate-500">복합 점수 기준</p>
              {compositeBacktest ? (
                <div className="mt-2 grid gap-1 text-xs text-slate-300">
                  <p>상위 {compositeBacktest.top_n}개 평균 수익률: {renderMetricValue(compositeBacktest.top_avg_future_return, false, true)}</p>
                  <p>비용 반영 평균 수익률: {renderMetricValue(compositeBacktest.top_avg_future_return_net, false, true)}</p>
                  <p>전체 평균 수익률: {renderMetricValue(compositeBacktest.universe_avg_future_return, false, true)}</p>
                  <p>순 초과 수익률: {renderMetricValue(compositeBacktest.excess_return_net ?? compositeBacktest.excess_return, false, true)}</p>
                  <p>후보 승률: <span className="font-mono text-white">{formatPercent(compositeBacktest.selection_win_rate_net ?? compositeBacktest.selection_win_rate)}</span></p>
                  <p>최대 낙폭: <span className="font-mono text-rose-450 font-bold">{formatReturnPercent(compositeBacktest.max_drawdown_net)}</span></p>
                </div>
              ) : (
                <p className="mt-2 text-sm text-slate-400">아직 복합 백테스트 결과가 없습니다.</p>
              )}
            </div>
          </div>
        </div>
      </div>

      <VersionComparisonTable
        versions={versions}
        selectedVersion={resolvedSelectedVersion}
        recommendedVersion={result?.recommended_version}
        latestVersion={result?.latest_version}
        servingVersion={result?.serving_version}
        onSelectVersion={setSelectedVersion}
      />

      <VersionDeltaPanel activeVersion={activeResult} baselines={comparisonBaselines} />

      <div className="mt-5">
        <h4 className="mb-3 text-xs font-bold uppercase tracking-wider text-slate-400">예측 순위</h4>
        {predictions.length ? (
          <div className="grid gap-2">
            {predictions.slice(0, 10).map((row) => (
              <div
                key={`${row.model_version}-${row.symbol}`}
                className="grid gap-3 rounded-lg border border-slate-800 bg-[#0f172a] p-3 sm:grid-cols-[1fr_auto_auto_auto]"
              >
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-2">
                    <p className="break-words text-sm font-bold text-white">{row.display_name || row.symbol}</p>
                    {row.position ? (
                      <span className={`rounded px-1.5 py-0.5 text-[9px] font-black tracking-widest ${
                        row.position === 'SHORT'
                          ? 'bg-rose-950/80 text-rose-300 border border-rose-700/60'
                          : 'bg-emerald-950/80 text-emerald-300 border border-emerald-700/60'
                      }`}>
                        {row.position}
                      </span>
                    ) : null}
                  </div>
                  <div className="mt-1 flex flex-wrap gap-1.5">
                    <span className="rounded border border-slate-700 px-1.5 py-0.5 font-mono text-[10px] text-slate-400">
                      {row.symbol}
                    </span>
                    {row.market ? (
                      <span className="rounded border border-slate-700 px-1.5 py-0.5 text-[10px] text-slate-400">
                        {row.market}
                      </span>
                    ) : null}
                    {row.sector ? (
                      <span className="rounded border border-ai-cyan/30 px-1.5 py-0.5 text-[10px] text-ai-cyan">
                        {row.sector}
                      </span>
                    ) : null}
                  </div>
                  <p className="mt-1 break-words text-xs text-slate-500">{row.date}</p>
                </div>
                <div>
                  <p className="text-[10px] font-bold uppercase tracking-wider text-slate-500">상승 확률</p>
                  <p className="font-mono text-sm text-emerald-300">{formatPercent(row.up_probability)}</p>
                </div>
                <div>
                  <p className="text-[10px] font-bold uppercase tracking-wider text-slate-500">하락 위험</p>
                  <p className="font-mono text-sm text-amber-300">{formatPercent(row.risk_probability)}</p>
                </div>
                <div>
                  <p className="text-[10px] font-bold uppercase tracking-wider text-slate-500">복합 점수</p>
                  <p className="font-mono text-sm text-ai-cyan">{row.signal_score}</p>
                </div>
              </div>
            ))}
          </div>
        ) : (
          <div className="rounded-lg border border-slate-800 bg-[#0f172a] p-4 text-sm text-slate-400">
            아직 예측 CSV가 없습니다.
          </div>
        )}
      </div>
    </article>
  )
}

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
        <div className="flex border-b border-slate-800">
          <button
            type="button"
            onClick={() => setAdminTab('ml')}
            className={`px-6 py-3 text-sm font-bold border-b-2 transition ${
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
            className={`px-6 py-3 text-sm font-bold border-b-2 transition ${
              adminTab === 'inquiries'
                ? 'border-ai-cyan text-white bg-ai-cyan/5'
                : 'border-transparent text-slate-400 hover:text-white'
            }`}
          >
            사용자 문의 관리
          </button>
        </div>

        {adminTab === 'ml' && (
          <>
            <section className="ai-glass rounded-lg p-6">
          <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
            <div>
              <p className="text-[10px] font-bold uppercase tracking-[0.16em] text-ai-cyan">ML Operations</p>
              <h2 className="mt-2 text-2xl font-bold text-white">ML 운영 콘솔</h2>
              <p className="mt-2 text-sm leading-6 text-slate-400">
                기본 화면은 운영 상태, 서빙 감사, 활성 신호, v8 자동화 실행, 최근 작업 이력만 표시합니다.
              </p>
            </div>

            <button
              type="button"
              onClick={() => setShowAdvancedTools((prev) => !prev)}
              className="w-full rounded border border-slate-700 px-4 py-2 text-xs font-bold text-slate-300 transition hover:border-ai-cyan hover:text-white sm:w-auto"
            >
              {showAdvancedTools ? '고급 도구 접기' : '고급 도구 열기'}
            </button>
          </div>
        </section>

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

        <section className="rounded-lg border border-ai-cyan/30 bg-ai-cyan/5 p-5">
          <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
            <div>
              <p className="text-[10px] font-bold uppercase tracking-[0.16em] text-ai-cyan">Full Automation</p>
              <h2 className="mt-1 text-xl font-bold text-white">자동 수집 + 학습</h2>
              <p className="mt-2 text-xs leading-5 text-slate-400">
                운영 기본 버튼은 현재 후보군인 국내주식, 해외주식, 코인 자동학습만 노출합니다. 레거시 모델과 HPO는 고급 도구에서 실행합니다.
              </p>
            </div>
          </div>

          <div className="mt-4 grid gap-3 md:grid-cols-2">
            {operationalAutomationPresets.map((preset) => (
              <button
                key={preset.key}
                type="button"
                onClick={() => handleRunFullAutomation(preset)}
                disabled={automationLoadingKey === preset.key || !isLoggedIn}
                className="rounded border border-ai-cyan/40 bg-[#0f172a] px-4 py-3 text-left transition hover:border-ai-cyan hover:bg-ai-cyan/10 disabled:cursor-not-allowed disabled:opacity-50"
              >
                <p className="flex items-center gap-2 text-sm font-bold text-white">
                  {automationLoadingKey === preset.key ? '실행 중...' : preset.label}
                  <span className="rounded bg-ai-cyan px-1.5 py-0.5 text-[9px] font-bold uppercase tracking-wider text-[#0a0f1e]">
                    {preset.version}
                  </span>
                </p>
                <p className="mt-1 text-xs leading-5 text-slate-400">{preset.summary}</p>
              </button>
            ))}
          </div>

          {automationMessage ? (
            <div className="mt-4 rounded-lg border border-ai-cyan/30 bg-ai-cyan/5 p-4 text-sm text-ai-cyan">
              {automationMessage}
            </div>
          ) : null}
        </section>

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

        <section className="rounded-lg border border-slate-700/80 bg-slate-surface p-5">
          <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
            <div>
              <p className="text-[10px] font-bold uppercase tracking-[0.16em] text-ai-cyan">Advanced Data Tools</p>
              <h2 className="mt-1 text-lg font-bold text-white">학습 데이터 수동 수집</h2>
            </div>
            <div className="flex rounded-lg border border-slate-700 bg-[#0f172a] p-1">
              {Object.entries(presets).map(([key, preset]) => (
                <button
                  key={key}
                  type="button"
                  onClick={() => applyPreset(key)}
                  className={`rounded-md px-4 py-2 text-xs font-bold transition ${
                    mode === key ? 'bg-ai-cyan text-[#07111f]' : 'text-slate-400 hover:text-white'
                  }`}
                >
                  {preset.title}
                </button>
              ))}
            </div>
          </div>
        </section>

        <section className="grid gap-6 lg:grid-cols-[1.1fr_0.9fr]">
          <div className="rounded-lg border border-slate-700/80 bg-slate-surface p-5">
            <div className="mb-5 flex items-center justify-between gap-3">
              <div>
                <h3 className="text-sm font-bold uppercase tracking-wider text-white">{selectedPreset.title}</h3>
                <p className="mt-1 text-xs text-slate-500">{form.output}</p>
              </div>
              <span className="rounded border border-ai-cyan/40 px-2 py-1 text-[10px] font-bold text-ai-cyan">
                {form.exchange}
              </span>
            </div>

            <div className="grid gap-4 md:grid-cols-2">
              <label className="flex flex-col gap-2">
                <span className="text-xs font-bold text-slate-400">심볼</span>
                <input
                  value={form.symbols}
                  onChange={(event) => updateField('symbols', event.target.value)}
                  className="rounded border border-slate-700 bg-[#0f172a] px-3 py-2 text-sm text-white outline-none transition focus:border-ai-cyan"
                  placeholder="직접 입력 시 005930,NVDA 또는 BTCUSDT,ETHUSDT"
                />
              </label>

              <label className="flex flex-col gap-2">
                <span className="text-xs font-bold text-slate-400">프리셋</span>
                <input
                  value={form.preset || ''}
                  onChange={(event) => updateField('preset', event.target.value)}
                  className="rounded border border-slate-700 bg-[#0f172a] px-3 py-2 text-sm text-white outline-none transition focus:border-ai-cyan"
                  placeholder="stock_core_90 / crypto_core_30"
                />
              </label>

              <label className="flex flex-col gap-2">
                <span className="text-xs font-bold text-slate-400">봉 간격</span>
                <input
                  value={form.interval}
                  onChange={(event) => updateField('interval', event.target.value)}
                  className="rounded border border-slate-700 bg-[#0f172a] px-3 py-2 text-sm text-white outline-none transition focus:border-ai-cyan"
                />
              </label>

              <label className="flex flex-col gap-2">
                <span className="text-xs font-bold text-slate-400">수집 개수</span>
                <input
                  type="number"
                  min="1"
                  max="1000"
                  value={form.count}
                  onChange={(event) => updateField('count', event.target.value)}
                  className="rounded border border-slate-700 bg-[#0f172a] px-3 py-2 text-sm text-white outline-none transition focus:border-ai-cyan"
                />
              </label>

              <label className="flex flex-col gap-2">
                <span className="text-xs font-bold text-slate-400">자산 구분</span>
                <input
                  value={`${form.assetType} / ${form.exchange}`}
                  readOnly
                  className="rounded border border-slate-800 bg-[#0f172a]/70 px-3 py-2 text-sm text-slate-400 outline-none"
                />
              </label>

              <label className="flex flex-col gap-2">
                <span className="text-xs font-bold text-slate-400">요청 간 대기초</span>
                <input
                  type="number"
                  min="0"
                  step="0.1"
                  value={form.sleepSeconds}
                  onChange={(event) => updateField('sleepSeconds', event.target.value)}
                  className="rounded border border-slate-700 bg-[#0f172a] px-3 py-2 text-sm text-white outline-none transition focus:border-ai-cyan"
                />
              </label>

              <label className="flex flex-col gap-2">
                <span className="text-xs font-bold text-slate-400">429 재시도 횟수</span>
                <input
                  type="number"
                  min="0"
                  max="10"
                  value={form.retry}
                  onChange={(event) => updateField('retry', event.target.value)}
                  className="rounded border border-slate-700 bg-[#0f172a] px-3 py-2 text-sm text-white outline-none transition focus:border-ai-cyan"
                />
              </label>

              <label className="flex flex-col gap-2">
                <span className="text-xs font-bold text-slate-400">재시도 대기초</span>
                <input
                  type="number"
                  min="1"
                  value={form.retryWaitSeconds}
                  onChange={(event) => updateField('retryWaitSeconds', event.target.value)}
                  className="rounded border border-slate-700 bg-[#0f172a] px-3 py-2 text-sm text-white outline-none transition focus:border-ai-cyan"
                />
              </label>

              <label className="flex flex-col gap-2">
                <span className="text-xs font-bold text-slate-400">청크 크기</span>
                <input
                  type="number"
                  min="0"
                  value={form.chunkSize}
                  onChange={(event) => updateField('chunkSize', event.target.value)}
                  className="rounded border border-slate-700 bg-[#0f172a] px-3 py-2 text-sm text-white outline-none transition focus:border-ai-cyan"
                />
              </label>

              <label className="flex flex-col gap-2">
                <span className="text-xs font-bold text-slate-400">청크 번호</span>
                <input
                  type="number"
                  min="1"
                  value={form.chunkIndex}
                  onChange={(event) => updateField('chunkIndex', event.target.value)}
                  className="rounded border border-slate-700 bg-[#0f172a] px-3 py-2 text-sm text-white outline-none transition focus:border-ai-cyan"
                />
              </label>

              <label className="flex items-center gap-3 rounded border border-slate-800 bg-[#0f172a]/70 px-3 py-2">
                <input
                  type="checkbox"
                  checked={form.append}
                  onChange={(event) => updateField('append', event.target.checked)}
                  className="h-4 w-4 accent-ai-cyan"
                />
                <span className="text-sm font-bold text-slate-300">기존 CSV에 병합 저장</span>
              </label>

              <label className="flex items-center gap-3 rounded border border-slate-800 bg-[#0f172a]/70 px-3 py-2">
                <input
                  type="checkbox"
                  checked={form.includeMacro}
                  onChange={(event) => updateField('includeMacro', event.target.checked)}
                  className="h-4 w-4 accent-ai-cyan"
                />
                <span className="text-sm font-bold text-slate-300">매크로 지표도 함께 갱신</span>
              </label>
            </div>

            <div className="mt-5 flex flex-wrap items-center gap-3">
              <button
                type="button"
                onClick={handleExport}
                disabled={loading}
                className="rounded bg-ai-cyan px-5 py-2.5 text-sm font-bold text-[#07111f] transition hover:bg-ai-cyan/80 disabled:cursor-not-allowed disabled:opacity-50"
              >
                {loading ? 'CSV 생성 중' : 'CSV 생성'}
              </button>
              <p className="text-xs leading-5 text-slate-500">
                Toss는 요청 제한을 피하기 위해 종목 사이 대기와 429 재시도를 사용합니다.
              </p>
            </div>
          </div>

          <div className="rounded-lg border border-slate-700/80 bg-slate-surface p-5">
            <h3 className="mb-4 text-sm font-bold uppercase tracking-wider text-white">실행 결과</h3>
            <StatusPanel result={result} error={error} loading={loading} />
          </div>
        </section>
        </>
        ) : null}

        {showAdvancedTools ? (
        <section className="flex flex-col gap-4">
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <div>
              <p className="text-[10px] font-bold uppercase tracking-[0.16em] text-ai-cyan">Model Results</p>
              <h2 className="mt-1 text-xl font-bold text-white">최근 학습 결과와 예측 순위</h2>
            </div>
            <button
              type="button"
              onClick={loadModelResults}
              disabled={modelResultsLoading || !isLoggedIn}
              className="w-full rounded border border-slate-700 px-4 py-2 text-xs font-bold text-slate-300 transition hover:border-ai-cyan hover:text-white disabled:cursor-not-allowed disabled:opacity-50 sm:w-auto"
            >
              {modelResultsLoading ? '불러오는 중' : '결과 새로고침'}
            </button>
          </div>

          {modelResultsError ? (
            <div className="rounded-lg border border-red-800 bg-red-950/30 p-4 text-sm leading-6 text-red-300">
              {modelResultsError}
            </div>
          ) : null}

          <div className="grid gap-6 grid-cols-1">
            <ModelResultCard title="주식 모델" result={modelResults?.stock} />
            <ModelResultCard title="코인 모델" result={modelResults?.crypto} />
          </div>
        </section>
        ) : null}

        {showAdvancedTools ? (
        <>
        <section className="grid gap-6 grid-cols-1">
          <RegistryPanel
            title="주식 레지스트리 상태"
            rows={registryRows.stock}
            loading={registryLoading}
            error={registryError}
            onActivate={handleActivateRegistry}
            activatingKey={activatingRegistryKey}
            promotionChecks={promotionChecks}
            promotionChecksLoading={promotionChecksLoading}
          />
          <RegistryPanel
            title="코인 레지스트리 상태"
            rows={registryRows.crypto}
            loading={registryLoading}
            error={registryError}
            onActivate={handleActivateRegistry}
            activatingKey={activatingRegistryKey}
            promotionChecks={promotionChecks}
            promotionChecksLoading={promotionChecksLoading}
          />
        </section>

        {registryMessage ? (
          <section className="rounded-lg border border-ai-cyan/30 bg-ai-cyan/5 p-4 text-sm whitespace-pre-line text-ai-cyan">
            {registryMessage}
          </section>
        ) : null}
        </>
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
          <div className="rounded-lg border border-slate-700/80 bg-slate-surface p-5">
            <div className="flex items-center justify-between gap-3">
              <div>
                <p className="text-[10px] font-bold uppercase tracking-[0.16em] text-ai-cyan">Training Jobs</p>
                <h2 className="mt-1 text-xl font-bold text-white">백엔드 학습 실행</h2>
              </div>
            </div>

            <div className="mt-4 grid gap-3">
              {trainingPresets.map((preset) => (
                <button
                  key={preset.key}
                  type="button"
                  onClick={() => handleRunTraining(preset)}
                  disabled={trainingLoadingKey === preset.key || !isLoggedIn}
                  className="rounded border border-slate-700 bg-[#0f172a] px-4 py-3 text-left transition hover:border-ai-cyan disabled:cursor-not-allowed disabled:opacity-50"
                >
                  <p className="text-sm font-bold text-white">
                    {trainingLoadingKey === preset.key ? '실행 중...' : preset.label}
                  </p>
                  <p className="mt-1 break-all font-mono text-[10px] text-slate-500">{formatPath(preset.config)}</p>
                </button>
              ))}
            </div>

            <div className="mt-4 rounded-lg border border-slate-800 bg-[#0f172a] p-4 text-xs leading-6 text-slate-400">
              이 버튼은 백엔드에서 `run_pipeline_bundle.py`를 실행하고, 작업 이력을 `ml/data/ops/job_history.json`에 남깁니다.
            </div>

            {trainingMessage ? (
              <div className="mt-4 rounded-lg border border-ai-cyan/30 bg-ai-cyan/5 p-4 text-sm text-ai-cyan">
                {trainingMessage}
              </div>
            ) : null}

            <div className="mt-6 border-t border-slate-800 pt-6">
              <p className="text-[10px] font-bold uppercase tracking-[0.16em] text-ai-cyan">Full Automation</p>
              <h3 className="mt-1 text-sm font-bold text-white">백엔드 자동 수집 + 학습</h3>
              <div className="mt-4 grid gap-3">
                {legacyAutomationPresets.map((preset) => (
                  <button
                    key={preset.key}
                    type="button"
                    onClick={() => handleRunFullAutomation(preset)}
                    disabled={automationLoadingKey === preset.key || !isLoggedIn}
                    className={[
                      'rounded border px-4 py-3 text-left transition disabled:cursor-not-allowed disabled:opacity-50',
                      preset.isNew
                        ? 'border-ai-cyan/40 bg-ai-cyan/5 hover:border-ai-cyan hover:bg-ai-cyan/10'
                        : 'border-slate-700 bg-[#0f172a] hover:border-ai-cyan',
                    ].join(' ')}
                  >
                    <p className="flex items-center gap-2 text-sm font-bold text-white">
                      {automationLoadingKey === preset.key ? '실행 중...' : preset.label}
                      {preset.isNew && (
                        <span className="rounded bg-ai-cyan px-1.5 py-0.5 text-[9px] font-bold uppercase tracking-wider text-[#0a0f1e]">
                          NEW
                        </span>
                      )}
                    </p>
                    <p className="mt-1 text-xs leading-5 text-slate-400">{preset.summary}</p>
                  </button>
                ))}
              </div>

              <div className="mt-4 rounded-lg border border-slate-800 bg-[#0f172a] p-4 text-xs leading-6 text-slate-400">
                이 버튼은 데이터셋 수집과 `run_pipeline_bundle.py` 실행을 순차적으로 수행하고, 결과를 작업 이력과 모델 레지스트리에 반영합니다.
              </div>

              {automationMessage ? (
                <div className="mt-4 rounded-lg border border-ai-cyan/30 bg-ai-cyan/5 p-4 text-sm text-ai-cyan">
                  {automationMessage}
                </div>
              ) : null}
            </div>

            <div className="mt-6 border-t border-slate-800 pt-6">
              <p className="text-[10px] font-bold uppercase tracking-[0.16em] text-ai-cyan">Optuna HPO Tuning</p>
              <h3 className="mt-1 text-sm font-bold text-white">Optuna 하이퍼파라미터 최적화 (HPO)</h3>
              
              <div className="mt-4 grid gap-4 sm:grid-cols-2">
                <label className="flex flex-col gap-1.5 text-xs">
                  <span className="font-bold text-slate-400">탐색 시도 횟수 (Trials)</span>
                  <input
                    type="number"
                    min="5"
                    max="100"
                    value={tuneTrials}
                    onChange={(e) => setTuneTrials(Number(e.target.value))}
                    className="rounded border border-slate-700 bg-[#0f172a] px-3 py-2 text-white outline-none focus:border-ai-cyan font-mono"
                  />
                </label>
                
                <label className="flex items-center gap-2 rounded border border-slate-800 bg-[#0f172a]/70 px-3 py-2">
                  <input
                    type="checkbox"
                    checked={tuneUpdateConfig}
                    onChange={(e) => setTuneUpdateConfig(e.target.checked)}
                    className="h-4 w-4 accent-ai-cyan"
                  />
                  <span className="font-bold text-slate-300">최적 파라미터 자동 저장 (YAML)</span>
                </label>
              </div>

              <div className="mt-4 grid gap-3">
                {tuningPresets.map((preset) => (
                  <button
                    key={preset.key}
                    type="button"
                    onClick={() => handleRunTuning(preset)}
                    disabled={tuningLoadingKey === preset.key || !isLoggedIn}
                    className={[
                      'rounded border px-4 py-3 text-left transition disabled:cursor-not-allowed disabled:opacity-50',
                      preset.isNew
                        ? 'border-ai-cyan/40 bg-ai-cyan/5 hover:border-ai-cyan hover:bg-ai-cyan/10'
                        : 'border-slate-700 bg-[#0f172a] hover:border-ai-cyan',
                    ].join(' ')}
                  >
                    <p className="flex items-center gap-2 text-sm font-bold text-white">
                      {tuningLoadingKey === preset.key ? '튜닝 진행 중...' : preset.label}
                      {preset.isNew && (
                        <span className="rounded bg-ai-cyan px-1.5 py-0.5 text-[9px] font-bold uppercase tracking-wider text-[#0a0f1e]">
                          NEW
                        </span>
                      )}
                    </p>
                    <p className="mt-1 text-xs leading-5 text-slate-400">{preset.summary}</p>
                    <p className="mt-1 font-mono text-[9px] text-slate-500 break-all">{formatPath(preset.config)}</p>
                  </button>
                ))}
              </div>

              {tuningMessage ? (
                <div className="mt-4 rounded-lg border border-ai-cyan/30 bg-ai-cyan/5 p-4 text-sm text-ai-cyan">
                  {tuningMessage}
                </div>
              ) : null}
            </div>
          </div>
          ) : null}

          <div className="rounded-lg border border-slate-700/80 bg-slate-surface p-5">
            <div className="mb-4 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
              <div>
                <p className="text-[10px] font-bold uppercase tracking-[0.16em] text-ai-cyan">Job History</p>
                <h2 className="mt-1 text-xl font-bold text-white">데이터셋/학습 작업 이력</h2>
              </div>
              <button
                type="button"
                onClick={loadJobHistory}
                disabled={jobHistoryLoading || !isLoggedIn}
                className="w-full rounded border border-slate-700 px-4 py-2 text-xs font-bold text-slate-300 transition hover:border-ai-cyan hover:text-white disabled:cursor-not-allowed disabled:opacity-50 sm:w-auto"
              >
                {jobHistoryLoading ? '불러오는 중' : '작업 이력 새로고침'}
              </button>
            </div>

            <JobHistoryPanel
              jobs={jobHistory}
              loading={jobHistoryLoading}
              error={jobHistoryError}
              onShowLog={setSelectedLogJob}
            />
          </div>
        </section>
        </>
        )}

        {adminTab === 'inquiries' && <AdminInquiryPanel />}
      </main>

      <JobLogModal
        job={selectedLogJob}
        onClose={() => setSelectedLogJob(null)}
      />
    </div>
  )
}
