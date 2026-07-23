import { useState } from 'react'

// ─── SVG 아이콘 ────────────────────────────────────────────────
const IconSearch = () => (
  <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
    <circle cx="11" cy="11" r="8" />
    <line x1="21" y1="21" x2="16.65" y2="16.65" />
  </svg>
)
const IconChart = () => (
  <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
    <line x1="18" y1="20" x2="18" y2="10" />
    <line x1="12" y1="20" x2="12" y2="4" />
    <line x1="6" y1="20" x2="6" y2="14" />
  </svg>
)

const IconList = () => (
  <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
    <line x1="8" y1="6" x2="21" y2="6" />
    <line x1="8" y1="12" x2="21" y2="12" />
    <line x1="8" y1="18" x2="21" y2="18" />
    <line x1="3" y1="6" x2="3.01" y2="6" />
    <line x1="3" y1="12" x2="3.01" y2="12" />
    <line x1="3" y1="18" x2="3.01" y2="18" />
  </svg>
)
const StatusDot = ({ color }) => (
  <span
    className="inline-block shrink-0 rounded-full"
    style={{ width: 8, height: 8, background: color }}
  />
)

import {
  formatDecimalMetric,
  formatMetric,
  formatPercent,
  formatProbability,
  formatRatio,
  formatReturnPercent,
  formatSignalScore,
  formatStaleness,
  getPolicyReasonLabels,
  getProbabilityLevel,
  getSignalGradeLabel,
  getSignalGradeTone,
} from './assetDetailModel.js'

// 정책 차단 사유를 일반 유저 언어로 변환
const POLICY_REASON_PLAIN = {
  '시장 폭 부족': '시장 전체 상승 종목이 부족합니다',
  '섹터 폭 부족': '이 업종의 흐름이 약합니다',
  '섹터 강도 부족': '업종 전반이 힘을 잃고 있습니다',
  '시장 국면 보수적': '현재 시장은 보수적 대응이 필요합니다',
  '시장 과열 경계': '시장이 단기 과열 구간입니다',
  '하락 위험 차단': '하락 위험 신호가 감지됩니다',
}

const buildMlSignalInterpretation = (signal, resolvedAssetType, isResolvedUsStock) => {
  if (!signal) return null
  const up = getProbabilityLevel(signal.up_probability, 'up')
  const risk = getProbabilityLevel(signal.risk_probability, 'risk')
  const grade = String(signal.signal_grade || '')
  const position = String(signal.position || '').toUpperCase()
  const isRisky = grade === 'RISKY' || Number(signal.risk_probability) >= 0.6
  const isCandidate = grade === 'STRONG_BUY_CANDIDATE' || position === 'LONG'
  const actionLabel = isRisky ? '주의' : isCandidate ? '매수 후보' : '관망'
  const actionColor = isRisky ? '#f87171' : isCandidate ? '#34d399' : '#fbbf24'
  const actionTone = isRisky
    ? 'border-rose-500/40 bg-rose-950/30 text-rose-200'
    : isCandidate
      ? 'border-emerald-500/40 bg-emerald-950/25 text-emerald-200'
      : 'border-cyan-500/35 bg-cyan-950/20 text-cyan-100'
  const simpleReason = isRisky
    ? '지금은 매수보다 리스크 확인이 우선입니다. 하락 신호가 감지되고 있습니다.'
    : isCandidate
      ? '상승 가능성이 높고 현재 시장 환경도 우호적입니다.'
      : '아직 매수 진입 조건이 충분하지 않습니다. 조금 더 지켜보세요.'

  return {
    actionLabel,
    actionColor,
    actionTone,
    up,
    risk,
    simpleReason,
    modelScope: resolvedAssetType === 'CRYPTO'
      ? '코인 전용 모델'
      : isResolvedUsStock
        ? '해외주식 모델'
        : '국내주식 모델',
  }
}

// ─── 간단히 보기 ────────────────────────────────────────────────
function SimpleView({ mlSignal, resolvedAssetType, isResolvedUsStock }) {
  const interpretation = buildMlSignalInterpretation(mlSignal, resolvedAssetType, isResolvedUsStock)
  if (!interpretation) return null

  const policyReasons = getPolicyReasonLabels(mlSignal)
  const upPct = Math.round(Number(mlSignal.up_probability || 0) * 100)
  const riskPct = Math.round(Number(mlSignal.risk_probability || 0) * 100)
  const upBarWidth = Math.min(upPct, 100)
  const riskBarWidth = Math.min(riskPct, 100)

  return (
    <div className="flex flex-col gap-4">
      {/* 핵심 판단 */}
      <div className={`rounded-xl border px-4 py-4 ${interpretation.actionTone}`}>
        <p className="text-[10px] font-bold uppercase tracking-[0.16em] opacity-70">AI 참고 판단</p>
        <p className="mt-1 flex items-center gap-2 text-2xl font-black text-white">
          <StatusDot color={interpretation.actionColor} />
          {interpretation.actionLabel}
        </p>
        <p className="mt-2 text-xs leading-5 text-slate-200">{interpretation.simpleReason}</p>
      </div>

      {/* 핵심 지표 바 차트 */}
      <div className="flex flex-col gap-3 rounded-lg border border-[#1f2945] bg-[#070b19] px-3 py-3">
        <div>
          <div className="flex justify-between text-[10px] text-slate-400 mb-1">
            <span>상승 가능성</span>
            <span className={`font-bold ${interpretation.up.tone}`}>{interpretation.up.label} {upPct}%</span>
          </div>
          <div className="h-2 w-full rounded-full bg-slate-800">
            <div
              className="h-2 rounded-full bg-emerald-400 transition-all"
              style={{ width: `${upBarWidth}%` }}
            />
          </div>
        </div>
        <div>
          <div className="flex justify-between text-[10px] text-slate-400 mb-1">
            <span>하락 위험</span>
            <span className={`font-bold ${interpretation.risk.tone}`}>{interpretation.risk.label} {riskPct}%</span>
          </div>
          <div className="h-2 w-full rounded-full bg-slate-800">
            <div
              className="h-2 rounded-full bg-rose-400 transition-all"
              style={{ width: `${riskBarWidth}%` }}
            />
          </div>
        </div>
      </div>

      {/* 관망 이유 (일반 언어) */}
      {policyReasons.length > 0 && (
        <div className="rounded-lg border border-amber-900/40 bg-amber-950/10 px-3 py-3">
          <p className="mb-2 flex items-center gap-1.5 text-[10px] font-bold text-amber-300">
            <IconList />
            관망을 추천하는 이유
          </p>
          <ul className="flex flex-col gap-1.5">
            {policyReasons.slice(0, 4).map((r) => (
              <li key={r} className="flex items-start gap-2 text-[11px] text-amber-200/80">
                <span className="mt-0.5 shrink-0 text-amber-400">•</span>
                <span>{POLICY_REASON_PLAIN[r] ?? r}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* 면책 */}
      <p className="text-[9px] leading-4 text-slate-500">
        AI 신호는 주문 실행 근거가 아닌 참고 지표입니다. 최종 판단은 본인이 하세요.
        <br />예측 {formatStaleness(mlSignal.staleness_minutes)} · {mlSignal.predicted_at || mlSignal.date || '-'}
      </p>
    </div>
  )
}

// ─── 상세 보기 ────────────────────────────────────────────────
function DetailView({ mlSignal, resolvedAssetType, isResolvedUsStock }) {
  const interpretation = buildMlSignalInterpretation(mlSignal, resolvedAssetType, isResolvedUsStock)
  if (!interpretation) return null

  const performance = mlSignal.meta?.performance
  const policyReasons = getPolicyReasonLabels(mlSignal)

  return (
    <div className="flex flex-col gap-3">
      {/* AI 판단 박스 */}
      <div className={`rounded-lg border px-3 py-3 ${interpretation.actionTone}`}>
        <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
          <div>
            <p className="text-[10px] font-bold uppercase tracking-[0.16em] opacity-80">AI 참고 판단</p>
            <p className="mt-1 text-lg font-black text-white">{interpretation.actionLabel}</p>
          </div>
          <div className="flex flex-wrap gap-2 text-[10px] font-bold">
            <span className="rounded border border-white/15 bg-black/15 px-2 py-1">{interpretation.modelScope}</span>
            <span className="rounded border border-white/15 bg-black/15 px-2 py-1">
              {mlSignal.meta?.serving_version ? '서비스 모델' : '추천/최신 모델'}
            </span>
          </div>
        </div>
        <p className="mt-3 break-words text-xs leading-5 text-slate-100">{interpretation.simpleReason}</p>
        <div className="mt-3 grid grid-cols-1 gap-2 sm:grid-cols-2">
          <div className="rounded border border-white/10 bg-black/15 p-2">
            <p className="text-[10px] text-slate-300">상승 가능성</p>
            <p className={`mt-1 text-sm font-black ${interpretation.up.tone}`}>
              {interpretation.up.label} <span className="font-mono text-xs">({formatProbability(mlSignal.up_probability)})</span>
            </p>
            <p className="mt-1 text-[10px] leading-4 text-slate-300">{interpretation.up.detail}</p>
          </div>
          <div className="rounded border border-white/10 bg-black/15 p-2">
            <p className="text-[10px] text-slate-300">하락 위험</p>
            <p className={`mt-1 text-sm font-black ${interpretation.risk.tone}`}>
              {interpretation.risk.label} <span className="font-mono text-xs">({formatProbability(mlSignal.risk_probability)})</span>
            </p>
            <p className="mt-1 text-[10px] leading-4 text-slate-300">{interpretation.risk.detail}</p>
          </div>
        </div>
      </div>

      {/* 모델 품질 */}
      {performance && (
        <div className="rounded border border-emerald-900/30 bg-emerald-950/10 px-3 py-2">
          <div className="flex items-center justify-between gap-3">
            <span className="text-[9px] font-bold uppercase tracking-[0.18em] text-emerald-300">모델 정확도</span>
            <span className="text-[9px] text-slate-500">최근 활성 모델 기준</span>
          </div>
          <div className="mt-2 grid grid-cols-2 gap-2">
            <div className="rounded border border-[#1f2945] bg-[#070b19] p-2">
              <p className="text-[9px] text-slate-500">예측 정확도 (AUC)</p>
              <p className="mt-1 font-mono text-xs font-bold text-white">{formatMetric(performance.cv_roc_auc)}</p>
            </div>
            <div className="rounded border border-[#1f2945] bg-[#070b19] p-2">
              <p className="text-[9px] text-slate-500">상위 10% 적중률</p>
              <p className="mt-1 font-mono text-xs font-bold text-white">{formatPercent(performance.precision_at_top_10pct)}</p>
            </div>
            <div className="rounded border border-[#1f2945] bg-[#070b19] p-2">
              <p className="text-[9px] text-slate-500">복합 초과수익</p>
              <p className="mt-1 font-mono text-xs font-bold text-emerald-300">{formatReturnPercent(performance.composite_excess_return_net)}</p>
            </div>
            <div className="rounded border border-[#1f2945] bg-[#070b19] p-2">
              <p className="text-[9px] text-slate-500">최대 낙폭</p>
              <p className="mt-1 font-mono text-xs font-bold text-rose-300">{formatReturnPercent(performance.composite_max_drawdown_net)}</p>
            </div>
          </div>
        </div>
      )}

      {/* 신호 등급 배지 */}
      <div className="flex flex-wrap items-center gap-2">
        <span className={`rounded border px-2 py-1 text-[10px] font-black tracking-widest ${getSignalGradeTone(mlSignal.signal_grade)}`}>
          {getSignalGradeLabel(mlSignal.signal_grade)}
        </span>
        <span className="rounded border border-slate-700 bg-slate-900/70 px-2 py-1 text-[10px] font-bold text-slate-300">
          {mlSignal.position || 'HOLD'}
        </span>
        <span className="rounded border border-cyan-500/20 bg-cyan-950/20 px-2 py-1 text-[10px] font-bold text-cyan-300/60">
          {mlSignal.model_version || mlSignal.meta?.model_version || '-'}
        </span>
      </div>

      <p className="break-words text-[11px] leading-5 text-slate-300">
        {mlSignal.reason_summary || '현재 모델 신호를 요약할 수 없습니다.'}
      </p>

      {/* 정책 차단 사유 배지 */}
      {policyReasons.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {policyReasons.slice(0, 4).map((reason) => (
            <span
              key={reason}
              className="rounded border border-amber-800/50 bg-amber-950/20 px-2 py-1 text-[9px] font-bold text-amber-300"
            >
              {reason}
            </span>
          ))}
        </div>
      )}

      {/* 수치 지표 */}
      <div className="grid grid-cols-3 gap-2">
        <div className="rounded border border-[#1f2945] bg-[#070b19] p-2">
          <p className="text-[9px] text-slate-500">상승 확률</p>
          <p className="mt-1 font-mono text-xs font-bold text-emerald-300">{formatProbability(mlSignal.up_probability)}</p>
        </div>
        <div className="rounded border border-[#1f2945] bg-[#070b19] p-2">
          <p className="text-[9px] text-slate-500">하락 위험</p>
          <p className="mt-1 font-mono text-xs font-bold text-amber-300">{formatProbability(mlSignal.risk_probability)}</p>
        </div>
        <div className="rounded border border-[#1f2945] bg-[#070b19] p-2">
          <p className="text-[9px] text-slate-500">복합 점수</p>
          <p className="mt-1 font-mono text-xs font-bold text-cyan-300">{formatSignalScore(mlSignal.signal_score)}</p>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-2">
        <div className="rounded border border-[#1f2945] bg-[#070b19] p-2">
          <p className="text-[9px] text-slate-500">진입 거리</p>
          <p className="mt-1 font-mono text-xs font-bold text-white">{formatDecimalMetric(mlSignal.long_entry_distance, 3)}</p>
        </div>
        <div className="rounded border border-[#1f2945] bg-[#070b19] p-2">
          <p className="text-[9px] text-slate-500">거래량 확인</p>
          <p className={`mt-1 font-mono text-xs font-bold ${Number(mlSignal.volume_ratio_5 || 0) >= 0.7 ? 'text-emerald-300' : 'text-amber-300'}`}>
            {formatRatio(mlSignal.volume_ratio_5)}
          </p>
        </div>
        <div className="rounded border border-[#1f2945] bg-[#070b19] p-2">
          <p className="text-[9px] text-slate-500">시장 폭</p>
          <p className="mt-1 font-mono text-xs font-bold text-slate-200">{formatProbability(mlSignal.market_breadth_5)}</p>
        </div>
        <div className="rounded border border-[#1f2945] bg-[#070b19] p-2">
          <p className="text-[9px] text-slate-500">섹터 강도</p>
          <p className="mt-1 font-mono text-xs font-bold text-slate-200">{formatDecimalMetric(mlSignal.sector_strength_score, 2)}</p>
        </div>
      </div>

      {/* 요약 정보 */}
      <div className="rounded border border-[#1f2945] bg-[#070b19]/80 px-3 py-2 text-[10px] leading-4 text-slate-400">
        <div className="flex justify-between gap-3">
          <span>추천 티어</span>
          <span className="font-mono font-bold text-white">{mlSignal.recommendation_tier || mlSignal.position || '-'}</span>
        </div>
        <div className="mt-1 flex justify-between gap-3">
          <span>시장 국면</span>
          <span className="font-mono font-bold text-white">
            {mlSignal.market_regime_state === 'risk_off' ? '보수적 (risk_off)' : mlSignal.market_regime_state || '-'}
          </span>
        </div>
        <div className="mt-1 flex justify-between gap-3">
          <span>조정 스프레드</span>
          <span className="font-mono font-bold text-white">{formatDecimalMetric(mlSignal.adjusted_composite_spread, 3)}</span>
        </div>
      </div>

      {/* 면책 */}
      <div className="rounded border border-amber-900/40 bg-amber-950/10 px-3 py-2 text-[9px] leading-4 text-amber-300">
        AI 신호는 주문 실행 근거가 아니라 참고 지표입니다. 주문 전 사전검증과 사용자 승인을 우선합니다.
      </div>

      <p className="font-mono text-[10px] text-slate-500">
        예측 {formatStaleness(mlSignal.staleness_minutes)} · {mlSignal.predicted_at || mlSignal.date || '-'}
      </p>
    </div>
  )
}

// ─── 메인 컴포넌트 ────────────────────────────────────────────────
export default function AssetDetailMlSignalPanel({
  isMlSignalExpanded,
  setIsMlSignalExpanded,
  mlSignal,
  mlSignalLoading,
  mlSignalMessage,
  resolvedAssetType,
  isResolvedUsStock,
  onFetchMlSignal,
}) {
  const [viewMode, setViewMode] = useState('simple') // 'simple' | 'detail'

  return (
    <>
      <div className="bg-[#0e1529]/90 border border-cyan-500/30 rounded-xl p-4 flex flex-col gap-3 backdrop-blur-md">
        {/* 헤더 */}
        <div className="flex items-start justify-between gap-3 border-b border-[#1f2945] pb-2">
          <div>
            <span className="text-[10px] font-bold uppercase tracking-[0.16em] text-cyan-300">AI Signal</span>
            <h2 className="mt-1 text-xs font-bold text-white">ML 참고 신호</h2>
          </div>
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => setIsMlSignalExpanded((prev) => !prev)}
              className="rounded border border-slate-700 px-2 py-1 text-[10px] font-bold text-slate-300 transition hover:border-cyan-500/30 hover:text-white"
            >
              {isMlSignalExpanded ? '접기' : '펼치기'}
            </button>
            <button
              type="button"
              onClick={onFetchMlSignal}
              disabled={mlSignalLoading}
              className="rounded border border-cyan-500/30 px-2 py-1 text-[10px] font-bold text-cyan-300 transition hover:bg-cyan-950/30 disabled:opacity-50"
            >
              {mlSignalLoading ? '조회 중' : '갱신'}
            </button>
          </div>
        </div>

        {!isMlSignalExpanded ? (
          <div className="rounded border border-[#1f2945] bg-[#070b19] px-3 py-3 text-[11px] leading-5 text-slate-400">
            펼쳐서 ML 참고 신호를 확인할 수 있습니다.
          </div>
        ) : mlSignalLoading ? (
          <div className="rounded border border-[#1f2945] bg-[#070b19] px-3 py-4 text-center text-[11px] font-mono text-cyan-300">
            활성 모델 신호 확인 중...
          </div>
        ) : mlSignal ? (
          <>
            {/* 간단히/상세 보기 토글 */}
            <div className="flex rounded-lg border border-[#1f2945] bg-[#070b19] p-0.5">
              <button
                type="button"
                onClick={() => setViewMode('simple')}
                className={`flex flex-1 items-center justify-center gap-1.5 rounded-md px-3 py-1.5 text-[10px] font-bold transition ${
                  viewMode === 'simple'
                    ? 'bg-cyan-500/20 text-cyan-300 shadow-sm'
                    : 'text-slate-500 hover:text-slate-300'
                }`}
              >
                <IconSearch /> 간단히 보기
              </button>
              <button
                type="button"
                onClick={() => setViewMode('detail')}
                className={`flex flex-1 items-center justify-center gap-1.5 rounded-md px-3 py-1.5 text-[10px] font-bold transition ${
                  viewMode === 'detail'
                    ? 'bg-cyan-500/20 text-cyan-300 shadow-sm'
                    : 'text-slate-500 hover:text-slate-300'
                }`}
              >
                <IconChart /> 상세 보기
              </button>
            </div>

            {viewMode === 'simple' ? (
              <SimpleView
                mlSignal={mlSignal}
                resolvedAssetType={resolvedAssetType}
                isResolvedUsStock={isResolvedUsStock}
              />
            ) : (
              <DetailView
                mlSignal={mlSignal}
                resolvedAssetType={resolvedAssetType}
                isResolvedUsStock={isResolvedUsStock}
              />
            )}
          </>
        ) : (
          <div className="rounded border border-[#1f2945] bg-[#070b19] px-3 py-4 text-[11px] leading-5 text-slate-400">
            {mlSignalMessage || '현재 표시할 AI 시그널이 없습니다.'}
          </div>
        )}
      </div>
    </>
  )
}
