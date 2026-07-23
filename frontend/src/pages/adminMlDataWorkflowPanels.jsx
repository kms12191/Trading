import { StatusPanel } from './adminMlDataCorePanels.jsx'
import { JobHistoryPanel } from './adminMlDataHistoryPanels.jsx'
import { RegistryPanel } from './adminMlDataOperationalPanels.jsx'
import { ModelResultCard } from './adminMlDataResultPanels.jsx'
import { formatPath } from './adminMlDataModel.js'

export function MlConsoleHeader({ showAdvancedTools, onToggleAdvanced, variant = 'desktop' }) {
  const isMobile = variant === 'mobile'

  return (
    <section className={isMobile ? 'ai-glass rounded-lg p-4' : 'ai-glass rounded-lg p-6'}>
      <div className={isMobile ? 'grid gap-3' : 'flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between'}>
        <div className={isMobile ? 'min-w-0' : ''}>
          <p className="text-[10px] font-bold uppercase tracking-[0.16em] text-ai-cyan">ML Operations</p>
          <h2 className={isMobile ? 'mt-1 text-xl font-bold text-white' : 'mt-2 text-2xl font-bold text-white'}>
            ML 운영 콘솔
          </h2>
          <p className={isMobile ? 'mt-1 break-keep text-xs leading-5 text-slate-400' : 'mt-2 text-sm leading-6 text-slate-400'}>
            기본 화면은 운영 상태, 서빙 감사, 활성 신호, v8 자동화 실행, 최근 작업 이력만 표시합니다.
          </p>
        </div>

        <button
          type="button"
          onClick={onToggleAdvanced}
          className={[
            'w-full rounded border border-slate-700 px-4 py-2 text-xs font-bold text-slate-300 transition hover:border-ai-cyan hover:text-white',
            isMobile ? 'bg-[#0f172a]' : 'sm:w-auto',
          ].join(' ')}
        >
          {showAdvancedTools ? '고급 도구 접기' : '고급 도구 열기'}
        </button>
      </div>
    </section>
  )
}

export function OperationalAutomationPanel({
  presets,
  loadingKey,
  message,
  isLoggedIn,
  onRun,
}) {
  return (
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
        {presets.map((preset) => (
          <button
            key={preset.key}
            type="button"
            onClick={() => onRun(preset)}
            disabled={loadingKey === preset.key || !isLoggedIn}
            className="rounded border border-ai-cyan/40 bg-[#0f172a] px-4 py-3 text-left transition hover:border-ai-cyan hover:bg-ai-cyan/10 disabled:cursor-not-allowed disabled:opacity-50"
          >
            <p className="flex items-center gap-2 text-sm font-bold text-white">
              {loadingKey === preset.key ? '실행 중...' : preset.label}
              <span className="rounded bg-ai-cyan px-1.5 py-0.5 text-[9px] font-bold uppercase tracking-wider text-[#0a0f1e]">
                {preset.version}
              </span>
            </p>
            <p className="mt-1 text-xs leading-5 text-slate-400">{preset.summary}</p>
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

export function AdvancedDataToolsPanel({
  presets,
  mode,
  selectedPreset,
  form,
  result,
  error,
  loading,
  onApplyPreset,
  onUpdateField,
  onExport,
}) {
  return (
    <>
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
                onClick={() => onApplyPreset(key)}
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
                onChange={(event) => onUpdateField('symbols', event.target.value)}
                className="rounded border border-slate-700 bg-[#0f172a] px-3 py-2 text-sm text-white outline-none transition focus:border-ai-cyan"
                placeholder="직접 입력 시 005930,NVDA 또는 BTCUSDT,ETHUSDT"
              />
            </label>

            <label className="flex flex-col gap-2">
              <span className="text-xs font-bold text-slate-400">프리셋</span>
              <input
                value={form.preset || ''}
                onChange={(event) => onUpdateField('preset', event.target.value)}
                className="rounded border border-slate-700 bg-[#0f172a] px-3 py-2 text-sm text-white outline-none transition focus:border-ai-cyan"
                placeholder="stock_core_90 / crypto_core_30"
              />
            </label>

            <label className="flex flex-col gap-2">
              <span className="text-xs font-bold text-slate-400">봉 간격</span>
              <input
                value={form.interval}
                onChange={(event) => onUpdateField('interval', event.target.value)}
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
                onChange={(event) => onUpdateField('count', event.target.value)}
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
                onChange={(event) => onUpdateField('sleepSeconds', event.target.value)}
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
                onChange={(event) => onUpdateField('retry', event.target.value)}
                className="rounded border border-slate-700 bg-[#0f172a] px-3 py-2 text-sm text-white outline-none transition focus:border-ai-cyan"
              />
            </label>

            <label className="flex flex-col gap-2">
              <span className="text-xs font-bold text-slate-400">재시도 대기초</span>
              <input
                type="number"
                min="1"
                value={form.retryWaitSeconds}
                onChange={(event) => onUpdateField('retryWaitSeconds', event.target.value)}
                className="rounded border border-slate-700 bg-[#0f172a] px-3 py-2 text-sm text-white outline-none transition focus:border-ai-cyan"
              />
            </label>

            <label className="flex flex-col gap-2">
              <span className="text-xs font-bold text-slate-400">청크 크기</span>
              <input
                type="number"
                min="0"
                value={form.chunkSize}
                onChange={(event) => onUpdateField('chunkSize', event.target.value)}
                className="rounded border border-slate-700 bg-[#0f172a] px-3 py-2 text-sm text-white outline-none transition focus:border-ai-cyan"
              />
            </label>

            <label className="flex flex-col gap-2">
              <span className="text-xs font-bold text-slate-400">청크 번호</span>
              <input
                type="number"
                min="1"
                value={form.chunkIndex}
                onChange={(event) => onUpdateField('chunkIndex', event.target.value)}
                className="rounded border border-slate-700 bg-[#0f172a] px-3 py-2 text-sm text-white outline-none transition focus:border-ai-cyan"
              />
            </label>

            <label className="flex items-center gap-3 rounded border border-slate-800 bg-[#0f172a]/70 px-3 py-2">
              <input
                type="checkbox"
                checked={form.append}
                onChange={(event) => onUpdateField('append', event.target.checked)}
                className="h-4 w-4 accent-ai-cyan"
              />
              <span className="text-sm font-bold text-slate-300">기존 CSV에 병합 저장</span>
            </label>

            <label className="flex items-center gap-3 rounded border border-slate-800 bg-[#0f172a]/70 px-3 py-2">
              <input
                type="checkbox"
                checked={form.includeMacro}
                onChange={(event) => onUpdateField('includeMacro', event.target.checked)}
                className="h-4 w-4 accent-ai-cyan"
              />
              <span className="text-sm font-bold text-slate-300">매크로 지표도 함께 갱신</span>
            </label>
          </div>

          <div className="mt-5 flex flex-wrap items-center gap-3">
            <button
              type="button"
              onClick={onExport}
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
  )
}

export function ModelResultsSection({
  results,
  loading,
  error,
  isLoggedIn,
  onRefresh,
}) {
  return (
    <section className="flex flex-col gap-4">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <p className="text-[10px] font-bold uppercase tracking-[0.16em] text-ai-cyan">Model Results</p>
          <h2 className="mt-1 text-xl font-bold text-white">최근 학습 결과와 예측 순위</h2>
        </div>
        <button
          type="button"
          onClick={onRefresh}
          disabled={loading || !isLoggedIn}
          className="w-full rounded border border-slate-700 px-4 py-2 text-xs font-bold text-slate-300 transition hover:border-ai-cyan hover:text-white disabled:cursor-not-allowed disabled:opacity-50 sm:w-auto"
        >
          {loading ? '불러오는 중' : '결과 새로고침'}
        </button>
      </div>

      {error ? (
        <div className="rounded-lg border border-red-800 bg-red-950/30 p-4 text-sm leading-6 text-red-300">
          {error}
        </div>
      ) : null}

      <div className="grid gap-6 grid-cols-1">
        <ModelResultCard title="주식 모델" result={results?.stock} />
        <ModelResultCard title="코인 모델" result={results?.crypto} />
      </div>
    </section>
  )
}

export function RegistryStatusSection({
  rowsByAsset,
  loading,
  error,
  message,
  activatingKey,
  promotionChecks,
  promotionChecksLoading,
  onActivate,
  variant = 'desktop',
}) {
  const panelVariant = variant === 'mobile' ? 'mobile' : undefined

  return (
    <>
      <section className="grid gap-6 grid-cols-1">
        <RegistryPanel
          title="주식 레지스트리 상태"
          rows={rowsByAsset.stock}
          loading={loading}
          error={error}
          onActivate={onActivate}
          activatingKey={activatingKey}
          promotionChecks={promotionChecks}
          promotionChecksLoading={promotionChecksLoading}
          variant={panelVariant}
        />
        <RegistryPanel
          title="코인 레지스트리 상태"
          rows={rowsByAsset.crypto}
          loading={loading}
          error={error}
          onActivate={onActivate}
          activatingKey={activatingKey}
          promotionChecks={promotionChecks}
          promotionChecksLoading={promotionChecksLoading}
          variant={panelVariant}
        />
      </section>

      {message ? (
        <section className="rounded-lg border border-ai-cyan/30 bg-ai-cyan/5 p-4 text-sm whitespace-pre-line text-ai-cyan">
          {message}
        </section>
      ) : null}
    </>
  )
}

export function AdvancedTrainingToolsPanel({
  trainingPresets,
  legacyAutomationPresets,
  tuningPresets,
  trainingLoadingKey,
  automationLoadingKey,
  tuningLoadingKey,
  trainingMessage,
  automationMessage,
  tuningMessage,
  tuneTrials,
  tuneUpdateConfig,
  isLoggedIn,
  onRunTraining,
  onRunFullAutomation,
  onRunTuning,
  onTrialsChange,
  onUpdateConfigChange,
}) {
  return (
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
            onClick={() => onRunTraining(preset)}
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
              onClick={() => onRunFullAutomation(preset)}
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
              onChange={(event) => onTrialsChange(Number(event.target.value))}
              className="rounded border border-slate-700 bg-[#0f172a] px-3 py-2 font-mono text-white outline-none focus:border-ai-cyan"
            />
          </label>

          <label className="flex items-center gap-2 rounded border border-slate-800 bg-[#0f172a]/70 px-3 py-2">
            <input
              type="checkbox"
              checked={tuneUpdateConfig}
              onChange={(event) => onUpdateConfigChange(event.target.checked)}
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
              onClick={() => onRunTuning(preset)}
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
              <p className="mt-1 break-all font-mono text-[9px] text-slate-500">{formatPath(preset.config)}</p>
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
  )
}

export function JobHistorySection({
  jobs,
  loading,
  error,
  isLoggedIn,
  onRefresh,
  onShowLog,
  variant = 'desktop',
}) {
  const panelVariant = variant === 'mobile' ? 'mobile' : undefined

  return (
    <div className="rounded-lg border border-slate-700/80 bg-slate-surface p-5">
      <div className="mb-4 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <p className="text-[10px] font-bold uppercase tracking-[0.16em] text-ai-cyan">Job History</p>
          <h2 className="mt-1 text-xl font-bold text-white">데이터셋/학습 작업 이력</h2>
        </div>
        <button
          type="button"
          onClick={onRefresh}
          disabled={loading || !isLoggedIn}
          className="w-full rounded border border-slate-700 px-4 py-2 text-xs font-bold text-slate-300 transition hover:border-ai-cyan hover:text-white disabled:cursor-not-allowed disabled:opacity-50 sm:w-auto"
        >
          {loading ? '불러오는 중' : '작업 이력 새로고침'}
        </button>
      </div>

      <JobHistoryPanel
        jobs={jobs}
        loading={loading}
        error={error}
        onShowLog={onShowLog}
        variant={panelVariant}
      />
    </div>
  )
}

export function AdvancedToolsContainer({
  activeSubTab,
  onSubTabChange,
  children,
}) {
  const tabs = [
    { id: 'hpo', label: 'Optuna HPO 튜닝' },
    { id: 'custom', label: '커스텀 수집 & 레포트' },
    { id: 'universe', label: '유니버스 종목 관리' },
  ]


  return (
    <section className="rounded-lg border border-slate-700 bg-[#0f172a] p-5 shadow-xl">
      <div className="flex flex-col gap-3 border-b border-slate-800 pb-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <p className="text-[10px] font-bold uppercase tracking-[0.16em] text-ai-cyan">Advanced Tools Console</p>
          <h2 className="mt-1 text-xl font-bold text-white">고급 도구 및 튜닝 모듈</h2>
        </div>
        <div className="flex rounded-lg border border-slate-800 bg-slate-900/90 p-1">
          {tabs.map((tab) => (
            <button
              key={tab.id}
              type="button"
              onClick={() => onSubTabChange(tab.id)}
              className={`rounded-md px-3.5 py-1.5 text-xs font-bold transition ${
                activeSubTab === tab.id
                  ? 'bg-ai-cyan text-[#07111f] shadow'
                  : 'text-slate-400 hover:text-white'
              }`}
            >
              {tab.label}
            </button>
          ))}
        </div>
      </div>
      <div className="mt-5">{children}</div>
    </section>
  )
}

