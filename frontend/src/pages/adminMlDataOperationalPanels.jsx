import { useEffect, useState } from 'react'
import { supabase } from '../supabaseClient'
import {
  buildQualityDetail,
  findRegistryRow,
  formatMetric,
  formatPath,
  formatPathInText,
  formatPercent,
  formatReturnPercent,
  formatStaleness,
  formatVersionBacktest,
  getSignalGradeLabel,
  getSignalGradeTone,
  getSimpleGuardStatus,
  summarizeFailedChecks,
} from './adminMlDataModel.js'
import { AuditBadge, GuardSummary } from './adminMlDataCorePanels.jsx'

export function ActiveSignalPanel({ title, data, loading, error, guardReport, onRefresh }) {
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

export function ServingAuditPanel({ data, loading, error, onRefresh, compactGuards = false }) {
  const guardGridClass = compactGuards ? 'mt-4 grid gap-2' : 'mt-4 grid gap-3 md:grid-cols-2'
  const guardCardClass = compactGuards
    ? 'min-w-0 rounded border border-slate-800 bg-black/10 p-3'
    : 'rounded border border-slate-800 bg-black/10 p-3'
  const guardTitleClass = compactGuards
    ? 'mb-2 break-keep text-[10px] font-bold uppercase tracking-wider text-slate-500'
    : 'mb-2 text-[10px] font-bold uppercase tracking-wider text-slate-500'

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

                <div className={guardGridClass}>
                  <div className={guardCardClass}>
                    <p className={guardTitleClass}>현재 서빙 기준</p>
                    <GuardSummary guardReport={report.current_guard} compact />
                  </div>
                  <div className={guardCardClass}>
                    <p className={guardTitleClass}>추천 후보 기준</p>
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

export function ModelSwitchPanel({ data, rowsByAsset, promotionChecks, loading, onActivate, activatingKey }) {
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

function RegistryStatusBadges({ row, compact = false }) {
  return (
    <>
      {row.is_latest ? (
        <span className="rounded border border-slate-600 px-2 py-1 text-[10px] font-bold text-slate-300">최신</span>
      ) : null}
      {row.is_recommended ? (
        <span className="rounded border border-emerald-500/40 px-2 py-1 text-[10px] font-bold text-emerald-300">추천</span>
      ) : null}
      {row.is_serving ? (
        <span className="rounded border border-ai-cyan/40 px-2 py-1 text-[10px] font-bold text-ai-cyan">
          {compact ? '서비스' : '서비스 적용'}
        </span>
      ) : null}
      {!row.is_latest && !row.is_recommended && !row.is_serving ? (
        <span className="rounded border border-slate-700 px-2 py-1 text-[10px] font-bold text-slate-500">분석 중</span>
      ) : null}
    </>
  )
}

function RegistryActivateButton({ row, onActivate, activatingKey, mobile = false }) {
  return (
    <button
      type="button"
      onClick={() => onActivate?.(row)}
      disabled={Boolean(activatingKey) || row.is_serving}
      className={`${mobile ? 'mt-3 w-full px-3 py-2 text-[11px]' : 'px-2 py-1 text-[10px]'} rounded border font-bold transition ${
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
  )
}

export function RegistryPanel({
  title,
  rows = [],
  loading,
  error,
  onActivate,
  activatingKey,
  promotionChecks = {},
  promotionChecksLoading = false,
  variant = 'desktop',
}) {
  const isMobile = variant === 'mobile'

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
      ) : isMobile ? (
        <div className="grid gap-2.5">
          {rows.map((row) => {
            const guardReport = promotionChecks[`${row.asset_type}:${row.model_version}`]

            return (
              <article key={`${row.asset_type}-${row.model_version}`} className="rounded-lg border border-slate-800 bg-[#0f172a] p-3 text-xs text-slate-300">
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <p className="truncate font-mono text-sm font-bold text-white">{row.model_version}</p>
                    <p className="mt-1 truncate text-[10px] text-slate-500">{row.version || '-'}</p>
                  </div>
                  <div className="flex shrink-0 flex-wrap justify-end gap-1">
                    <RegistryStatusBadges row={row} compact />
                  </div>
                </div>

                <div className="mt-3 grid grid-cols-2 gap-2">
                  <div className="rounded bg-slate-950/50 px-2.5 py-2">
                    <p className="text-[10px] font-bold text-slate-500">CV 구분력</p>
                    <p className="mt-1 font-mono text-[11px] text-white">{formatMetric(row.cv_roc_auc || row.roc_auc)}</p>
                  </div>
                  <div className="rounded bg-slate-950/50 px-2.5 py-2">
                    <p className="text-[10px] font-bold text-slate-500">상위 10%</p>
                    <p className="mt-1 font-mono text-[11px] text-white">{formatMetric(row.cv_top10_precision)}</p>
                  </div>
                </div>

                <div className="mt-3 rounded bg-slate-950/50 px-2.5 py-2">
                  {guardReport ? (
                    <GuardSummary guardReport={guardReport} compact />
                  ) : promotionChecksLoading ? (
                    <p className="text-[10px] text-slate-500">검증 중...</p>
                  ) : (
                    <p className="text-[10px] text-slate-500">검증 정보 없음</p>
                  )}
                </div>

                <p className="mt-2 truncate font-mono text-[10px] text-slate-500" title={row.summary_path || row.metrics_path}>
                  {formatPath(row.summary_path || row.metrics_path)}
                </p>

                <RegistryActivateButton row={row} onActivate={onActivate} activatingKey={activatingKey} mobile />
              </article>
            )
          })}
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
                        <RegistryStatusBadges row={row} />
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
                      <RegistryActivateButton row={row} onActivate={onActivate} activatingKey={activatingKey} />
                    </td>
                    <td className="px-3 py-2 font-mono text-[10px] text-slate-500">
                      <div className="max-w-[200px] truncate block" title={row.summary_path || row.metrics_path}>
                        {formatPath(row.summary_path || row.metrics_path)}
                      </div>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}

function ReadinessItem({ label, status, detail, mobile = false }) {
  return (
    <div className="rounded-lg border border-slate-800 bg-[#0f172a] p-3">
      <div className={mobile ? 'grid grid-cols-[minmax(0,1fr)_auto] items-start gap-3' : 'flex items-center justify-between gap-3'}>
        <p className={mobile ? 'min-w-0 break-keep text-sm font-bold leading-5 text-white' : 'text-xs font-bold text-white'}>{label}</p>
        <span className={`rounded border px-2 py-1 text-[10px] font-bold ${
          status ? 'border-emerald-500/40 text-emerald-300' : 'border-amber-500/40 text-amber-300'
        }`}>
          {status ? '준비 완료' : '확인 필요'}
        </span>
      </div>
      <p className={mobile
        ? 'mt-2 whitespace-pre-wrap break-words font-mono text-[10px] leading-5 text-slate-500'
        : 'mt-2 break-all whitespace-pre-line font-mono text-[10px] leading-5 text-slate-500'}
      >
        {formatPathInText(detail)}
      </p>
    </div>
  )
}

export function ReadinessPanel({ data, loading, error, onRefresh, variant = 'desktop' }) {
  const isMobile = variant === 'mobile'

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
        <div className={isMobile ? 'grid grid-cols-1 gap-3 sm:grid-cols-2' : 'grid gap-3 md:grid-cols-2 xl:grid-cols-3'}>
          <ReadinessItem
            mobile={isMobile}
            label="Toss 키"
            status={data.keys?.toss_ready}
            detail={data.keys?.toss_ready
              ? `Supabase 저장 키를 백엔드에서 복호화해 사용 가능\nsource: ${data.keys?.toss_source || '-'}\naccountSeq: ${data.keys?.toss_account_seq_ready ? 'READY' : 'CHECK'} / env: ${data.keys?.toss_broker_env || '-'} / records: ${data.keys?.toss_record_count ?? 0}`
              : `Toss 키 저장 또는 연결 확인 필요\nsource: ${data.keys?.toss_source || '-'}`}
          />
          <ReadinessItem
            mobile={isMobile}
            label="주식 원천 CSV"
            status={data.datasets?.stock_raw?.quality?.status === 'healthy'}
            detail={buildQualityDetail(data.datasets?.stock_raw)}
          />
          <ReadinessItem
            mobile={isMobile}
            label="코인 원천 CSV"
            status={data.datasets?.crypto_raw?.quality?.status === 'healthy'}
            detail={buildQualityDetail(data.datasets?.crypto_raw)}
          />
          <ReadinessItem
            mobile={isMobile}
            label="매크로 지표"
            status={data.datasets?.macro_raw?.exists}
            detail={`${data.datasets?.macro_raw?.rows ?? 0} rows\n${data.datasets?.macro_raw?.path || '-'}`}
          />
          <ReadinessItem
            mobile={isMobile}
            label="외부 피처"
            status={Boolean(data.feature_sources?.news_features?.exists || data.feature_sources?.crypto_market_features?.exists || data.feature_sources?.stock_event_features?.exists)}
            detail={`news ${data.feature_sources?.news_features?.rows ?? 0} / crypto ${data.feature_sources?.crypto_market_features?.rows ?? 0} / stock ${data.feature_sources?.stock_event_features?.rows ?? 0}`}
          />
          <ReadinessItem
            mobile={isMobile}
            label="SERVING 상태"
            status={Boolean(data.registry?.stock_serving || data.registry?.crypto_serving)}
            detail={`stock: ${data.registry?.stock_serving || '-'}\ncrypto: ${data.registry?.crypto_serving || '-'}`}
          />
        </div>
      )}
    </section>
  )
}

export function ExecutionChecklistPanel() {
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

export function ReportPanel({ loading, message, onGenerate }) {
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

export function ReportHistoryPanel({ reports = [], loading, error, onRefresh }) {
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

export function VersionComparisonTable({ versions = [], selectedVersion, recommendedVersion, latestVersion, servingVersion, onSelectVersion }) {
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

export function UniverseManagementPanel({ isLoggedIn }) {
  const [universeData, setUniverseData] = useState({ kr_stock: [], us_stock: [], crypto: [] })
  const [loading, setLoading] = useState(false)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')
  const [activeAsset, setActiveAsset] = useState('kr_stock')
  const [inputVal, setInputVal] = useState('')

  const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:5050'

  const loadUniverse = async () => {
    if (!isLoggedIn) return
    setLoading(true)
    setError('')
    setMessage('')
    try {
      const { data: { session } } = await supabase.auth.getSession()
      if (!session) {
        setError('로그인 세션이 만료되었습니다.')
        return
      }

      const response = await fetch(`${API_BASE_URL}/api/ml/universe`, {
        method: 'GET',
        headers: {
          'Authorization': `Bearer ${session.access_token}`,
        },
      })
      const payload = await response.json()
      if (!response.ok || !payload.success) {
        setError(payload.message || '유니버스 정보를 가져오는데 실패했습니다.')
        return
      }
      setUniverseData({
        kr_stock: payload.data.kr_stock || [],
        us_stock: payload.data.us_stock || [],
        crypto: payload.data.crypto || [],
      })
    } catch (err) {
      setError(`서버 통신 실패: ${err.message}`)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadUniverse()
  }, [isLoggedIn])

  const handleAddSymbol = (e) => {
    e.preventDefault()
    const sym = inputVal.trim().toUpperCase()
    if (!sym) return

    const currentList = universeData[activeAsset] || []
    if (currentList.includes(sym)) {
      alert('이미 존재하는 심볼입니다.')
      return
    }

    setUniverseData((prev) => ({
      ...prev,
      [activeAsset]: [...(prev[activeAsset] || []), sym],
    }))
    setInputVal('')
  }

  const handleRemoveSymbol = (symToRemove) => {
    setUniverseData((prev) => ({
      ...prev,
      [activeAsset]: (prev[activeAsset] || []).filter((sym) => sym !== symToRemove),
    }))
  }

  const handleSave = async () => {
    setSaving(true)
    setError('')
    setMessage('')
    try {
      const { data: { session } } = await supabase.auth.getSession()
      if (!session) {
        setError('로그인 세션이 만료되었습니다.')
        return
      }

      const response = await fetch(`${API_BASE_URL}/api/ml/universe`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${session.access_token}`,
        },
        body: JSON.stringify(universeData),
      })
      const payload = await response.json()
      if (!response.ok || !payload.success) {
        setError(payload.message || '유니버스 설정을 저장하는데 실패했습니다.')
        return
      }
      setMessage('동적 유니버스 설정이 성공적으로 저장되었습니다.')
      if (payload.data) {
        setUniverseData({
          kr_stock: payload.data.kr_stock || [],
          us_stock: payload.data.us_stock || [],
          crypto: payload.data.crypto || [],
        })
      }
    } catch (err) {
      setError(`저장 실패: ${err.message}`)
    } finally {
      setSaving(false)
    }
  }

  const assetLabels = {
    kr_stock: '국내 주식',
    us_stock: '해외 주식',
    crypto: '가상자산',
  }

  if (loading) {
    return (
      <div className="rounded-lg border border-slate-800 bg-[#0c0e15] p-6 text-center text-xs font-bold text-slate-400">
        <span className="material-symbols-outlined animate-spin text-ai-cyan mr-2">progress_activity</span>
        유니버스 데이터를 불러오는 중...
      </div>
    )
  }

  return (
    <div className="flex flex-col gap-6 rounded-lg border border-slate-800 bg-[#0c0e15] p-6 shadow-md">
      <div className="flex flex-col gap-1.5 border-b border-slate-800 pb-4">
        <div className="flex items-center gap-2">
          <span className="material-symbols-outlined text-ai-cyan">settings_suggest</span>
          <h3 className="text-sm font-bold uppercase tracking-wider text-white">동적 유니버스 설정 관리</h3>
        </div>
        <p className="text-[11px] text-slate-400">
          마켓별 모델 학습 및 피처 생성 시 활용되는 동적 수집 유니버스 종목 풀(active_universe.json)을 편집합니다.
        </p>
      </div>

      {error && (
        <div className="rounded border border-red-500/20 bg-red-500/5 px-4 py-3 text-xs text-red-400">
          {error}
        </div>
      )}

      {message && (
        <div className="rounded border border-emerald-500/20 bg-emerald-500/5 px-4 py-3 text-xs text-emerald-300">
          {message}
        </div>
      )}

      <div className="flex border-b border-slate-800">
        {Object.entries(assetLabels).map(([key, label]) => (
          <button
            key={key}
            type="button"
            onClick={() => {
              setActiveAsset(key)
              setError('')
              setMessage('')
            }}
            className={`px-4 py-2 text-xs font-bold border-b-2 transition ${
              activeAsset === key
                ? 'border-ai-cyan text-white bg-ai-cyan/5'
                : 'border-transparent text-slate-400 hover:text-white'
            }`}
          >
            {label} ({universeData[key]?.length || 0})
          </button>
        ))}
      </div>

      <form onSubmit={handleAddSymbol} className="flex gap-2">
        <input
          type="text"
          value={inputVal}
          onChange={(e) => setInputVal(e.target.value)}
          placeholder={`추가할 ${assetLabels[activeAsset]} 심볼/코드 입력 (예: ${
            activeAsset === 'kr_stock' ? '461350' : activeAsset === 'us_stock' ? 'NVDA' : 'BTCUSDT'
          })`}
          className="flex-1 rounded border border-slate-700 bg-[#11131a] px-3 py-2 text-xs text-white placeholder-slate-500 focus:border-ai-cyan focus:outline-none focus:ring-1 focus:ring-ai-cyan"
        />
        <button
          type="submit"
          className="flex items-center gap-1 rounded bg-ai-cyan/15 border border-ai-cyan/30 px-4 py-2 text-xs font-bold text-ai-cyan hover:bg-ai-cyan/20 active:scale-[0.98]"
        >
          <span className="material-symbols-outlined text-[14px]">add</span>
          추가
        </button>
      </form>

      <div className="min-h-[150px] max-h-[400px] overflow-y-auto rounded border border-slate-800 bg-[#090b11] p-4">
        {(!universeData[activeAsset] || universeData[activeAsset].length === 0) ? (
          <div className="flex h-full items-center justify-center text-xs text-slate-500 py-10">
            등록된 종목이 없습니다.
          </div>
        ) : (
          <div className="flex flex-wrap gap-2">
            {universeData[activeAsset].map((sym) => (
              <div
                key={sym}
                className="flex items-center gap-1.5 rounded-full border border-slate-700 bg-[#12151e] py-1 pl-3 pr-2 text-xs font-semibold text-slate-300 transition-colors hover:border-ai-cyan/40"
              >
                <span>{sym}</span>
                <button
                  type="button"
                  onClick={() => handleRemoveSymbol(sym)}
                  className="flex h-4 w-4 cursor-pointer items-center justify-center rounded-full text-slate-500 hover:bg-red-500/20 hover:text-red-400 focus:outline-none"
                >
                  <span className="material-symbols-outlined text-[12px] font-bold">close</span>
                </button>
              </div>
            ))}
          </div>
        )}
      </div>

      <div className="flex items-center justify-between border-t border-slate-800 pt-4">
        <span className="text-[10px] text-slate-500">
          * 변경 사항은 저장 버튼을 누르기 전까지 로컬 파일에 영구 기록되지 않습니다.
        </span>
        <div className="flex gap-2">
          <button
            type="button"
            onClick={loadUniverse}
            disabled={saving}
            className="rounded border border-slate-700 bg-transparent px-4 py-2 text-xs font-bold text-slate-300 hover:bg-white/5 disabled:opacity-50"
          >
            초기화
          </button>
          <button
            type="button"
            onClick={handleSave}
            disabled={saving}
            className="flex items-center gap-1.5 rounded bg-gradient-to-r from-blue-700 to-ai-cyan px-6 py-2 text-xs font-bold text-white shadow-md hover:opacity-90 active:scale-[0.98] disabled:opacity-50"
          >
            {saving ? (
              <>
                <span className="material-symbols-outlined animate-spin text-[14px]">progress_activity</span>
                저장 중...
              </>
            ) : (
              <>
                <span className="material-symbols-outlined text-[14px]">save</span>
                유니버스 설정 저장
              </>
            )}
          </button>
        </div>
      </div>
    </div>
  )
}

