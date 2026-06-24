import { useEffect, useMemo, useState } from 'react'
import Header from '../components/Header.jsx'
import { supabase } from '../supabaseClient'

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:5050'

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

const automationPresets = [
  {
    key: 'stock-v7-full',
    label: '주식 v7 자동 수집+학습',
    summary: 'Toss stock_core_90 수집 후 v7 학습까지 한 번에 실행',
  },
  {
    key: 'crypto-v7-full',
    label: '코인 v7 자동 수집+학습',
    summary: 'Binance crypto_core_30 수집 후 v7 학습까지 한 번에 실행',
  },
]

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
  return formatReturnPercent(version?.backtests?.composite?.data?.[key])
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

function JobHistoryPanel({ jobs = [], loading, error }) {
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
            <th className="px-3 py-2">시작</th>
            <th className="px-3 py-2">종료</th>
          </tr>
        </thead>
        <tbody>
          {jobs.map((job) => (
            <tr key={job.id} className="border-t border-slate-800 align-top">
              <td className="px-3 py-2">
                <p className="font-semibold text-white">{job.label || job.exchange || job.id}</p>
                {job.output ? <p className="mt-1 break-all font-mono text-[10px] text-slate-500">{job.output}</p> : null}
                {job.failure_count ? (
                  <p className="mt-1 text-[10px] text-amber-300">실패 심볼 {job.failure_count}건</p>
                ) : null}
              </td>
              <td className="px-3 py-2">{job.type}</td>
              <td className="px-3 py-2">
                <span className={`rounded border px-2 py-1 text-[10px] font-bold ${
                  job.status === 'success'
                    ? 'border-emerald-500/40 text-emerald-300'
                    : job.status === 'failed'
                      ? 'border-red-500/40 text-red-300'
                      : 'border-ai-cyan/40 text-ai-cyan'
                }`}>
                  {job.status}
                </span>
              </td>
              <td className="px-3 py-2">
                <p className="break-all font-mono text-[10px] text-slate-400">{job.config || job.interval || '-'}</p>
              </td>
              <td className="px-3 py-2 break-words font-mono text-[10px] text-slate-400">{job.started_at || '-'}</td>
              <td className="px-3 py-2 break-words font-mono text-[10px] text-slate-400">{job.finished_at || '-'}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function RegistryPanel({ title, rows = [], loading, error, onActivate, activatingKey }) {
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
                <th className="px-3 py-2">작업</th>
                <th className="px-3 py-2">경로</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
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
                        <span className="rounded border border-slate-600 px-2 py-1 text-[10px] font-bold text-slate-300">LATEST</span>
                      ) : null}
                      {row.is_recommended ? (
                        <span className="rounded border border-emerald-500/40 px-2 py-1 text-[10px] font-bold text-emerald-300">PICK</span>
                      ) : null}
                      {row.is_serving ? (
                        <span className="rounded border border-ai-cyan/40 px-2 py-1 text-[10px] font-bold text-ai-cyan">SERVING</span>
                      ) : null}
                      {!row.is_latest && !row.is_recommended && !row.is_serving ? (
                        <span className="rounded border border-slate-700 px-2 py-1 text-[10px] font-bold text-slate-500">TRACKED</span>
                      ) : null}
                    </div>
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
                  <td className="px-3 py-2 break-all font-mono text-[10px] text-slate-500">
                    {row.summary_path || row.metrics_path || '-'}
                  </td>
                </tr>
              ))}
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
          {status ? 'READY' : 'CHECK'}
        </span>
      </div>
      <p className="mt-2 break-all whitespace-pre-line font-mono text-[10px] leading-5 text-slate-500">{detail}</p>
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
            status={data.datasets?.stock_raw?.exists}
            detail={`${data.datasets?.stock_raw?.rows ?? 0} rows\n${data.datasets?.stock_raw?.path || '-'}`}
          />
          <ReadinessItem
            label="코인 원천 CSV"
            status={data.datasets?.crypto_raw?.exists}
            detail={`${data.datasets?.crypto_raw?.rows ?? 0} rows\n${data.datasets?.crypto_raw?.path || '-'}`}
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
              <p className="mt-1 break-all font-mono text-[10px] text-slate-500">{report.path}</p>
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
                  <td className="px-2 py-2">{formatPercent(version.backtests?.composite?.data?.selection_win_rate_net)}</td>
                  <td className="px-2 py-2 font-mono">{formatReturnPercent(version.backtests?.composite?.data?.max_drawdown_net)}</td>
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
                        {version.version === selectedVersion ? 'ACTIVE' : version.updated ? 'READY' : 'NO DATA'}
                      </span>
                      {version.version === recommendedVersion ? (
                        <span className="rounded border border-emerald-500/30 px-2 py-1 text-[10px] font-bold text-emerald-300">
                          PICK
                        </span>
                      ) : null}
                      {version.version === servingVersion || version.is_serving ? (
                        <span className="rounded border border-fuchsia-500/30 px-2 py-1 text-[10px] font-bold text-fuchsia-300">
                          SERVING
                        </span>
                      ) : null}
                      {version.version === latestVersion ? (
                        <span className="rounded border border-slate-600 px-2 py-1 text-[10px] font-bold text-slate-300">
                          LATEST
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
  const versions = result?.versions || []
  const [selectedVersion, setSelectedVersion] = useState(result?.selected_version || '')

  useEffect(() => {
    setSelectedVersion(result?.serving_version || result?.recommended_version || result?.selected_version || '')
  }, [result?.serving_version, result?.recommended_version, result?.selected_version])

  const activeResult = useMemo(() => {
    if (!versions.length) return result
    return versions.find((item) => item.version === selectedVersion) || result
  }, [result, selectedVersion, versions])

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
          <div className="rounded-lg bg-[#0f172a] p-3">
            <p className="text-xs font-bold text-slate-400">구분력</p>
            <p className="mt-0.5 text-[10px] leading-4 text-slate-500">상승/비상승을 가르는 힘</p>
            <p className="mt-1 font-mono text-xl font-bold text-white">{formatMetric(metrics.roc_auc)}</p>
          </div>
          <div className="rounded-lg bg-[#0f172a] p-3">
            <p className="text-xs font-bold text-slate-400">시계열 CV 구분력</p>
            <p className="mt-0.5 text-[10px] leading-4 text-slate-500">기간을 나눠 다시 봤을 때의 평균 구분력</p>
            <p className="mt-1 font-mono text-xl font-bold text-white">{formatMetric(metrics.time_series_cv_average?.roc_auc || metrics.roc_auc)}</p>
          </div>
          <div className="rounded-lg bg-[#0f172a] p-3">
            <p className="text-xs font-bold text-slate-400">상위 10% 적중</p>
            <p className="mt-0.5 text-[10px] leading-4 text-slate-500">점수 상위 후보만 골랐을 때의 적중률</p>
            <p className="mt-1 font-mono text-xl font-bold text-white">{formatMetric(metrics.time_series_cv_average?.precision_at_top_10pct || metrics.precision_at_top_10pct)}</p>
          </div>
          <div className="rounded-lg bg-[#0f172a] p-3">
            <p className="text-xs font-bold text-slate-400">상승 적중도</p>
            <p className="mt-0.5 text-[10px] leading-4 text-slate-500">상승 후보 쪽 랭킹 품질</p>
            <p className="mt-1 font-mono text-xl font-bold text-white">{formatMetric(metrics.average_precision)}</p>
          </div>
          <div className="rounded-lg bg-[#0f172a] p-3">
            <p className="text-xs font-bold text-slate-400">Precision / Recall</p>
            <p className="mt-0.5 text-[10px] leading-4 text-slate-500">상승으로 찍은 것의 정확도 / 실제 상승을 놓치지 않는 비율</p>
            <p className="mt-1 font-mono text-sm font-bold text-white">
              {formatMetric(metrics.precision)} / {formatMetric(metrics.recall)}
            </p>
          </div>
          <div className="rounded-lg bg-[#0f172a] p-3">
            <p className="text-xs font-bold text-slate-400">전체 정답률</p>
            <p className="mt-0.5 text-[10px] leading-4 text-slate-500">전체 0/1 판단 정답 비율</p>
            <p className="mt-1 font-mono text-xl font-bold text-white">{formatMetric(metrics.accuracy)}</p>
          </div>
          <div className="rounded-lg bg-[#0f172a] p-3 sm:col-span-3">
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
        <div className="rounded-lg border border-slate-800 bg-[#0f172a] p-4 text-sm text-slate-400">
          아직 학습 결과 파일이 없습니다.
        </div>
      )}

      <div className="mt-5 grid gap-4 xl:grid-cols-2">
        <div className="rounded-lg border border-slate-800 bg-[#0f172a] p-4">
          <p className="text-xs font-bold uppercase tracking-wider text-slate-400">하락 위험 모델</p>
          {riskMetrics ? (
            <div className="mt-3 grid gap-2 sm:grid-cols-3">
              <div>
                <p className="text-[10px] text-slate-500">구분력</p>
                <p className="font-mono text-sm text-white">{formatMetric(riskMetrics.roc_auc)}</p>
              </div>
              <div>
                <p className="text-[10px] text-slate-500">상위후보 적중도</p>
                <p className="font-mono text-sm text-white">{formatMetric(riskMetrics.average_precision)}</p>
              </div>
              <div>
                <p className="text-[10px] text-slate-500">전체 정답률</p>
                <p className="font-mono text-sm text-white">{formatMetric(riskMetrics.accuracy)}</p>
              </div>
            </div>
          ) : (
            <p className="mt-3 text-sm text-slate-400">아직 risk_label 모델 결과가 없습니다.</p>
          )}
        </div>

        <div className="rounded-lg border border-slate-800 bg-[#0f172a] p-4">
          <p className="text-xs font-bold uppercase tracking-wider text-slate-400">백테스트 요약</p>
          <div className="mt-3 grid gap-3">
            <div className="rounded-lg border border-slate-800 bg-black/10 p-3">
              <p className="text-[10px] font-bold uppercase tracking-wider text-slate-500">상승 점수 기준</p>
              {upOnlyBacktest ? (
                <div className="mt-2 grid gap-1 text-xs text-slate-300">
                  <p>상위 {upOnlyBacktest.top_n}개 평균 수익률: <span className="font-mono text-white">{formatReturnPercent(upOnlyBacktest.top_avg_future_return)}</span></p>
                  <p>비용 반영 평균 수익률: <span className="font-mono text-white">{formatReturnPercent(upOnlyBacktest.top_avg_future_return_net)}</span></p>
                  <p>전체 평균 수익률: <span className="font-mono text-white">{formatReturnPercent(upOnlyBacktest.universe_avg_future_return)}</span></p>
                  <p>순 초과 수익률: <span className="font-mono text-ai-cyan">{formatReturnPercent(upOnlyBacktest.excess_return_net ?? upOnlyBacktest.excess_return)}</span></p>
                  <p>후보 승률: <span className="font-mono text-white">{formatPercent(upOnlyBacktest.selection_win_rate_net ?? upOnlyBacktest.selection_win_rate)}</span></p>
                </div>
              ) : (
                <p className="mt-2 text-sm text-slate-400">아직 단순 백테스트 결과가 없습니다.</p>
              )}
            </div>

            <div className="rounded-lg border border-slate-800 bg-black/10 p-3">
              <p className="text-[10px] font-bold uppercase tracking-wider text-slate-500">복합 점수 기준</p>
              {compositeBacktest ? (
                <div className="mt-2 grid gap-1 text-xs text-slate-300">
                  <p>상위 {compositeBacktest.top_n}개 평균 수익률: <span className="font-mono text-white">{formatReturnPercent(compositeBacktest.top_avg_future_return)}</span></p>
                  <p>비용 반영 평균 수익률: <span className="font-mono text-white">{formatReturnPercent(compositeBacktest.top_avg_future_return_net)}</span></p>
                  <p>전체 평균 수익률: <span className="font-mono text-white">{formatReturnPercent(compositeBacktest.universe_avg_future_return)}</span></p>
                  <p>순 초과 수익률: <span className="font-mono text-ai-cyan">{formatReturnPercent(compositeBacktest.excess_return_net ?? compositeBacktest.excess_return)}</span></p>
                  <p>후보 승률: <span className="font-mono text-white">{formatPercent(compositeBacktest.selection_win_rate_net ?? compositeBacktest.selection_win_rate)}</span></p>
                  <p>최대 낙폭: <span className="font-mono text-amber-300">{formatReturnPercent(compositeBacktest.max_drawdown_net)}</span></p>
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
        selectedVersion={selectedVersion}
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
                  <p className="break-words text-sm font-bold text-white">{row.display_name || row.symbol}</p>
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

export default function AdminMlData({ isLoggedIn, userEmail, handleLogout }) {
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
  const [registryLoading, setRegistryLoading] = useState(false)
  const [registryError, setRegistryError] = useState('')
  const [registryMessage, setRegistryMessage] = useState('')
  const [activatingRegistryKey, setActivatingRegistryKey] = useState('')
  const [readiness, setReadiness] = useState(null)
  const [readinessLoading, setReadinessLoading] = useState(false)
  const [readinessError, setReadinessError] = useState('')
  const [reportLoading, setReportLoading] = useState(false)
  const [reportMessage, setReportMessage] = useState('')
  const [reportHistory, setReportHistory] = useState([])
  const [reportHistoryLoading, setReportHistoryLoading] = useState(false)
  const [reportHistoryError, setReportHistoryError] = useState('')
  const [trainingLoadingKey, setTrainingLoadingKey] = useState('')
  const [trainingMessage, setTrainingMessage] = useState('')
  const [automationLoadingKey, setAutomationLoadingKey] = useState('')
  const [automationMessage, setAutomationMessage] = useState('')

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
      setRegistryRows(payload.data || { stock: [], crypto: [] })
    } catch (requestError) {
      setRegistryError(`서버 통신 실패: ${requestError.message}`)
    } finally {
      setRegistryLoading(false)
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

      const response = await fetch(`${API_BASE_URL}/api/ml/registry/activate`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${session.access_token}`,
        },
        body: JSON.stringify({
          asset_type: row.asset_type,
          model_version: row.model_version,
        }),
      })
      const payload = await response.json()
      if (!response.ok || !payload.success) {
        setRegistryMessage(payload.message || '서비스 반영에 실패했습니다.')
        return
      }

      setRegistryMessage(payload.message || '서비스 반영이 완료되었습니다.')
      await loadRegistry()
      await loadModelResults()
      await loadReadiness()
    } catch (requestError) {
      setRegistryMessage(`서버 통신 실패: ${requestError.message}`)
    } finally {
      setActivatingRegistryKey('')
    }
  }

  useEffect(() => {
    loadModelResults()
    loadJobHistory()
    loadRegistry()
    loadReadiness()
    loadReportHistory()
  }, [isLoggedIn])

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
          ? `${preset.label} 작업이 완료되었습니다. 실험 리포트도 갱신되었습니다: ${reportPath}`
          : `${preset.label} 작업이 완료되었습니다.`
      )
      await loadModelResults()
      await loadJobHistory()
      await loadRegistry()
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
          ? `${preset.label} 작업이 완료되었습니다. 실험 리포트도 갱신되었습니다: ${reportPath}`
          : `${preset.label} 작업이 완료되었습니다.`
      )
      await loadModelResults()
      await loadJobHistory()
      await loadRegistry()
      await loadReadiness()
      await loadReportHistory()
    } catch (requestError) {
      setAutomationMessage(`서버 통신 실패: ${requestError.message}`)
    } finally {
      setAutomationLoadingKey('')
    }
  }

  return (
    <div className="min-h-screen bg-obsidian-bg px-6 py-8 text-[#e2e2ec]">
      <Header isLoggedIn={isLoggedIn} userEmail={userEmail} handleLogout={handleLogout} />

      <main className="mx-auto flex max-w-7xl flex-col gap-6">
        <section className="ai-glass rounded-lg p-6">
          <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
            <div>
              <p className="text-[10px] font-bold uppercase tracking-[0.16em] text-ai-cyan">Admin ML Data</p>
              <h2 className="mt-2 text-2xl font-bold text-white">학습 데이터 수집 관리</h2>
              <p className="mt-2 text-sm leading-6 text-slate-400">
                로그인한 사용자의 저장된 API Key를 백엔드에서만 복호화해 학습용 캔들 CSV를 생성합니다.
              </p>
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

          <div className="grid gap-6 xl:grid-cols-2">
            <ModelResultCard title="주식 모델" result={modelResults?.stock} />
            <ModelResultCard title="코인 모델" result={modelResults?.crypto} />
          </div>
        </section>

        <section className="grid gap-6 xl:grid-cols-2">
          <RegistryPanel
            title="주식 레지스트리 상태"
            rows={registryRows.stock}
            loading={registryLoading}
            error={registryError}
            onActivate={handleActivateRegistry}
            activatingKey={activatingRegistryKey}
          />
          <RegistryPanel
            title="코인 레지스트리 상태"
            rows={registryRows.crypto}
            loading={registryLoading}
            error={registryError}
            onActivate={handleActivateRegistry}
            activatingKey={activatingRegistryKey}
          />
        </section>

        {registryMessage ? (
          <section className="rounded-lg border border-ai-cyan/30 bg-ai-cyan/5 p-4 text-sm text-ai-cyan">
            {registryMessage}
          </section>
        ) : null}

        <ReadinessPanel
          data={readiness}
          loading={readinessLoading}
          error={readinessError}
          onRefresh={loadReadiness}
        />

        <ExecutionChecklistPanel />

        <ReportPanel
          loading={reportLoading}
          message={reportMessage}
          onGenerate={handleGenerateReport}
        />

        <ReportHistoryPanel
          reports={reportHistory}
          loading={reportHistoryLoading}
          error={reportHistoryError}
          onRefresh={loadReportHistory}
        />

        <section className="grid gap-6 xl:grid-cols-[0.9fr_1.1fr]">
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
                  <p className="mt-1 break-all font-mono text-[10px] text-slate-500">{preset.config}</p>
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
                {automationPresets.map((preset) => (
                  <button
                    key={preset.key}
                    type="button"
                    onClick={() => handleRunFullAutomation(preset)}
                    disabled={automationLoadingKey === preset.key || !isLoggedIn}
                    className="rounded border border-slate-700 bg-[#0f172a] px-4 py-3 text-left transition hover:border-ai-cyan disabled:cursor-not-allowed disabled:opacity-50"
                  >
                    <p className="text-sm font-bold text-white">
                      {automationLoadingKey === preset.key ? '실행 중...' : preset.label}
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
          </div>

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

            <JobHistoryPanel jobs={jobHistory} loading={jobHistoryLoading} error={jobHistoryError} />
          </div>
        </section>
      </main>
    </div>
  )
}
