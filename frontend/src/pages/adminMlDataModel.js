export const PROJECT_ROOT_PATH = '/Users/kangheesung/10-19_개발/13_프로젝트/13.05_트레이딩/teamproject'

export function formatPath(path) {
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

export function formatPathInText(text) {
  if (!text || typeof text !== 'string') return text
  let formatted = text.replaceAll(PROJECT_ROOT_PATH, '.')
  const idx = formatted.indexOf('/teamproject/')
  if (idx !== -1) {
    formatted = formatted.replaceAll(PROJECT_ROOT_PATH.substring(0, PROJECT_ROOT_PATH.indexOf('/teamproject') + 12), '.')
  }
  return formatted
}

export function buildJobLogClipboardText(job = {}) {
  return `=== Job Log: ${job.label || job.id} ===\n\n[TRAINING AUDIT]\n${JSON.stringify(job.training_audit || null, null, 2)}\n\n[GUARD REPORT]\n${JSON.stringify(job.guard_report || null, null, 2)}\n\n[SERVING AUDIT]\n${JSON.stringify(job.serving_audit_report || null, null, 2)}\n\n[STDOUT]\n${job.stdout || 'No stdout'}\n\n[STDERR]\n${job.stderr || 'No stderr'}`
}

export const presets = {
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

export const trainingPresets = [
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

export const tuningPresets = [
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

export const automationPresets = [
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
    summary: '일평균 100만$↑ & 상장 1년↑ 코인 동적 스크리닝 및 가변 슬리피지가 적용된 v8 학습 모델 (30m 캔들)',
    version: 'v8',
    isNew: true,
  },
  {
    key: 'kr-stock-v1-full',
    label: '국내주식 v1 자동 수집+학습',
    summary: 'KOSPI200/KOSDAQ150 거래대금 50억↑ 동적 스크리닝 및 가변 슬리피지 검증을 포함한 DART 연동 국내주식 모델',
    version: 'split-v1',
    isNew: true,
  },
  {
    key: 'us-stock-v1-full',
    label: '해외주식 v1 자동 수집+학습',
    summary: 'S&P500 거래대금 1000만$↑ 동적 스크리닝 및 가변 슬리피지 검증을 포함한 해외주식 모델 (DART 제외)',
    version: 'split-v1',
    isNew: true,
  },
]

export const operationalAutomationPresets = automationPresets.filter((preset) => ['v8', 'split-v1'].includes(preset.version))
export const legacyAutomationPresets = automationPresets.filter((preset) => !['v8', 'split-v1'].includes(preset.version))
export const v8TuningPresets = tuningPresets.filter((preset) => preset.version === 'v8')

export function formatMetric(value) {
  if (value === null || value === undefined || value === '') return '-'
  const numberValue = Number(value)
  if (Number.isNaN(numberValue)) return String(value)
  return numberValue.toFixed(4)
}

export function formatPercent(value) {
  if (value === null || value === undefined || value === '') return '-'
  const numberValue = Number(value)
  if (Number.isNaN(numberValue)) return String(value)
  return `${(numberValue * 100).toFixed(1)}%`
}

export function formatReturnPercent(value) {
  if (value === null || value === undefined || value === '') return '-'
  const numberValue = Number(value)
  if (Number.isNaN(numberValue)) return String(value)
  return `${(numberValue * 100).toFixed(2)}%`
}

export function formatVersionBacktest(version, key) {
  const compositeData = version?.backtests?.composite?.data
  if (!compositeData) return '-'
  let value = compositeData[key]
  if ((value === undefined || value === null) && typeof key === 'string' && key.endsWith('_net')) {
    value = compositeData[key.replace('_net', '')]
  }
  return formatReturnPercent(value)
}

export function formatSignedDelta(value, formatter = 'metric') {
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

export function getVersionSnapshot(version) {
  if (!version) return null

  return {
    cvRocAuc: Number(version.metrics?.time_series_cv_average?.roc_auc ?? version.metrics?.roc_auc ?? NaN),
    top10Precision: Number(version.metrics?.time_series_cv_average?.precision_at_top_10pct ?? version.metrics?.precision_at_top_10pct ?? NaN),
    riskCvRocAuc: Number(version.risk_metrics?.time_series_cv_average?.roc_auc ?? version.risk_metrics?.roc_auc ?? NaN),
    compositeExcessReturnNet: Number(version.backtests?.composite?.data?.excess_return_net ?? version.backtests?.composite?.data?.excess_return ?? NaN),
  }
}

export function formatTime(isoString) {
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

export const PROMOTION_CHECK_LABELS = {
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

export function getHealthTone(status) {
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

export function getHealthLabel(status) {
  if (status === 'healthy') return '정상'
  if (status === 'warning') return '경고'
  if (status === 'missing') return '누락'
  return '확인 필요'
}

export function getSignalGradeLabel(grade) {
  if (grade === 'STRONG_BUY_CANDIDATE') return '강한 후보'
  if (grade === 'WATCH') return '관찰'
  if (grade === 'RISKY') return '위험'
  if (grade === 'NO_SIGNAL') return '신호 없음'
  return grade || '미분류'
}

export function getSignalGradeTone(grade) {
  if (grade === 'STRONG_BUY_CANDIDATE') return 'border-emerald-500/50 bg-emerald-950/40 text-emerald-300'
  if (grade === 'WATCH') return 'border-ai-cyan/50 bg-ai-cyan/10 text-ai-cyan'
  if (grade === 'RISKY') return 'border-rose-500/50 bg-rose-950/40 text-rose-300'
  return 'border-slate-700 bg-slate-900/60 text-slate-400'
}

export function formatStaleness(minutes) {
  if (minutes === null || minutes === undefined || Number.isNaN(Number(minutes))) return '-'
  const numericMinutes = Number(minutes)
  if (numericMinutes < 60) return `${numericMinutes}분 전`
  if (numericMinutes < 1440) return `${Math.floor(numericMinutes / 60)}시간 전`
  return `${Math.floor(numericMinutes / 1440)}일 전`
}

export function getCheckLabel(name) {
  return PROMOTION_CHECK_LABELS[name] || name
}

export function findRegistryRow(rowsByAsset, assetType, modelVersion) {
  const assetKey = assetType === 'STOCK' ? 'stock' : 'crypto'
  return (rowsByAsset?.[assetKey] || []).find((row) => row.model_version === modelVersion || row.version === modelVersion)
}

export function getSimpleGuardStatus(guardReport) {
  if (!guardReport) {
    return { label: '검증 정보 없음', tone: 'border-slate-700 bg-slate-900/60 text-slate-400' }
  }
  if (guardReport.passed) {
    return { label: '교체 가능', tone: 'border-emerald-500/40 bg-emerald-950/20 text-emerald-300' }
  }
  return { label: '기준 미달', tone: 'border-amber-500/40 bg-amber-950/20 text-amber-300' }
}

export function formatCheckActual(value) {
  if (value === null || value === undefined || value === '') return '-'
  if (typeof value === 'object') return JSON.stringify(value)
  const numberValue = Number(value)
  if (Number.isNaN(numberValue)) return String(value)
  return numberValue.toFixed(4)
}

export function summarizeFailedChecks(guardReport, limit = 3) {
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

export function buildQualityDetail(dataset) {
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

export function findGuardCheck(guardReport, name) {
  return (guardReport?.checks || []).find((check) => check.name === name)
}

export function formatTrustValue(check) {
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
