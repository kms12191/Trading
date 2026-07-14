import { useEffect, useId, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { supabase } from '../../supabaseClient'
import { buildApiErrorText } from '../../lib/apiError.js'
import { streamChatbotMessage } from './chatbotApi'
import { buildChatbotCitations } from './chatbotCitations'
import { buildDisclosurePresentation } from './chatbotDisclosurePresentation'
import { shouldSubmitChatbotInput } from './chatbotInput'
import { buildMlRecommendationPresentation } from './chatbotMlRecommendationPresentation'
import { buildNewsPresentation } from './chatbotNewsPresentation'
import {
  buildProposalPrecheckSummary,
  isChatbotApprovalProposal,
  isProposalApprovalBlocked,
} from './chatbotProposalPrecheck'
import { getDefaultChatbotSize, resizeChatbotPanel } from './chatbotResize'
import {
  buildChatbotTimeline,
  formatChatbotProposalNumber,
} from './chatbotTimeline'
import { buildChatbotTraceBadges } from './chatbotTrace'
import { buildTradeHistoryPresentation } from './chatbotTradeHistoryPresentation'
import { buildWatchlistPresentation } from './chatbotWatchlistPresentation'

const INITIAL_MESSAGES = [
  {
    id: 'welcome',
    role: 'assistant',
    text: '안녕하세요. 고객님!\n\n궁금하신 내용을 직접 입력해 주세요.',
    createdAt: new Date().toISOString(),
    timelineOrder: 0,
  },
]

function getUserTimeZone() {
  return Intl.DateTimeFormat().resolvedOptions().timeZone || undefined
}

function formatMessageTime(createdAt) {
  if (!createdAt) return ''

  try {
    const formatted = new Intl.DateTimeFormat('ko-KR', {
      hour: 'numeric',
      minute: '2-digit',
      hour12: true,
      timeZone: getUserTimeZone(),
    }).formatToParts(new Date(createdAt))
    const dayPeriod = formatted.find((part) => part.type === 'dayPeriod')?.value || ''
    const hour = formatted.find((part) => part.type === 'hour')?.value || ''
    const minute = formatted.find((part) => part.type === 'minute')?.value || ''
    return [dayPeriod, hour && minute ? `${hour}:${minute}` : ''].filter(Boolean).join(' ')
  } catch {
    try {
      return new Date(createdAt).toTimeString().slice(0, 5)
    } catch {
      return ''
    }
  }
}

function formatMessageDateTime(createdAt) {
  if (!createdAt) return ''

  try {
    return new Intl.DateTimeFormat('ko-KR', {
      month: '2-digit',
      day: '2-digit',
      hour: 'numeric',
      minute: '2-digit',
      hour12: true,
      timeZone: getUserTimeZone(),
    }).format(new Date(createdAt))
  } catch {
    return ''
  }
}

function mergePendingProposal(items, proposal) {
  if (!proposal?.id || proposal.status !== 'PENDING') {
    return items.filter((item) => item.id !== proposal?.id)
  }
  const next = items.filter((item) => item.id !== proposal.id)
  return [proposal, ...next]
}

function ProposalPrecheckSummary({ proposal }) {
  const summary = buildProposalPrecheckSummary(proposal)
  if (!summary) return null

  return (
    <div className={`space-y-1 rounded border px-2 py-2 text-[10px] ${
      summary.status === 'OK'
        ? 'border-emerald-500/30 bg-emerald-500/5 text-emerald-100'
        : 'border-amber-500/40 bg-amber-500/10 text-amber-100'
    }`}>
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
        <span className="font-bold">{summary.status === 'OK' ? '사전검증 완료' : '사전검증 확인 필요'}</span>
        {summary.estimatedAmountText && <span>예상 {summary.estimatedAmountText}</span>}
        {summary.availableCashText && <span>주문가능 {summary.availableCashText}</span>}
      </div>
      {summary.warnings.length > 0 && (
        <ul className="space-y-1 text-amber-100/90">
          {summary.warnings.slice(0, 3).map((warning) => (
            <li key={warning} className="break-words">- {warning}</li>
          ))}
        </ul>
      )}
    </div>
  )
}

function TradeProposalCard({ proposal, proposalActionId, onApprove, onReject }) {
  const approvalBlocked = isProposalApprovalBlocked(proposal)
  const orderType = String(proposal.ord_type || proposal.order_type || '').toUpperCase()
  const priceText = orderType === 'MARKET' && proposal.price == null
    ? '시장가'
    : formatChatbotProposalNumber(proposal.price)

  return (
    <article className="space-y-2 rounded border border-slate-700 border-l-2 border-l-ai-cyan bg-[#0b1120] p-3">
      <div className="flex flex-wrap items-center justify-between gap-2 text-xs">
        <div className="min-w-0">
          <p className="text-[10px] font-bold text-ai-cyan">승인 대기 매매 제안</p>
          <strong className="break-words text-slate-100">{proposal.symbol || proposal.ticker}</strong>
        </div>
        <span className={proposal.side === 'BUY' ? 'text-emerald-300' : 'text-rose-300'}>
          {proposal.side === 'BUY' ? '매수' : '매도'}
        </span>
      </div>
      <p className="break-words text-[11px] text-slate-400">
        {proposal.exchange} · {proposal.broker_env || 'REAL'} · 수량 {formatChatbotProposalNumber(proposal.volume)} · 가격 {priceText}
      </p>
      <ProposalPrecheckSummary proposal={proposal} />
      <div className="flex flex-wrap gap-2">
        <button
          type="button"
          disabled={Boolean(proposalActionId) || approvalBlocked}
          onClick={() => onApprove(proposal)}
          title={approvalBlocked ? '사전검증을 통과한 제안만 승인할 수 있습니다.' : undefined}
          className="min-h-10 min-w-32 flex-1 rounded bg-ai-cyan px-3 py-2 text-[11px] font-bold text-[#07111f] disabled:cursor-not-allowed disabled:opacity-50"
        >
          승인 후 실행
        </button>
        <button
          type="button"
          disabled={Boolean(proposalActionId)}
          onClick={() => onReject(proposal.id)}
          className="min-h-10 min-w-16 rounded border border-rose-500/50 px-3 py-2 text-[11px] font-bold text-rose-300 disabled:cursor-not-allowed disabled:opacity-50"
        >
          거절
        </button>
      </div>
    </article>
  )
}

function ChatMessage({ message, onAction }) {
  const isUser = message.role === 'user'
  const messageTime = formatMessageTime(message.createdAt)
  const messageDateTime = formatMessageDateTime(message.createdAt)
  const actions = Array.isArray(message.actions) ? message.actions : []
  const disclosurePresentation = buildDisclosurePresentation(message.toolResult)
  const newsPresentation = buildNewsPresentation(message.toolResult)
  const mlRecommendationPresentation = buildMlRecommendationPresentation(message.toolResult)
  const tradeHistoryPresentation = buildTradeHistoryPresentation(message.toolResult)
  const watchlistPresentation = buildWatchlistPresentation(message.toolResult)
  const hasDisclosureCards = !isUser && disclosurePresentation.items.length > 0
  const hasNewsCards = !isUser && newsPresentation.items.length > 0
  const hasMlRecommendationCards = !isUser && mlRecommendationPresentation.shouldRender
  const hasTradeHistoryTable = !isUser && tradeHistoryPresentation.shouldRender
  const hasWatchlistTable = !isUser && watchlistPresentation.shouldRender
  const citations = !isUser ? buildChatbotCitations(message.toolResult) : []
  const traceBadges = !isUser ? buildChatbotTraceBadges({ traceSteps: message.traceSteps, toolResult: message.toolResult }) : []
  const hasMessageBody = hasDisclosureCards || hasNewsCards || hasMlRecommendationCards || hasTradeHistoryTable || hasWatchlistTable || Boolean(message.text) || !message.isStreaming

  if (!hasMessageBody && traceBadges.length === 0) {
    return null
  }

  return (
    <div className={`flex ${isUser ? 'justify-end' : 'justify-start'}`}>
      <div className={`flex flex-col gap-1 ${hasDisclosureCards || hasNewsCards || hasMlRecommendationCards || hasTradeHistoryTable || hasWatchlistTable ? 'w-full max-w-[96%]' : 'max-w-[84%]'} ${isUser ? 'items-end' : 'items-start'}`}>
        {!isUser && traceBadges.length > 0 && (
          <TraceBadges badges={traceBadges} />
        )}
        {hasMessageBody && (
          <div
            className={`${hasDisclosureCards || hasNewsCards || hasMlRecommendationCards || hasTradeHistoryTable || hasWatchlistTable ? 'w-full' : 'whitespace-pre-wrap break-words'} rounded-lg px-3 py-2 text-xs leading-5 ${
              isUser
                ? 'bg-blue-600 text-[#ffffff]'
                : 'border border-slate-700/80 bg-[#111827] text-slate-100'
            }`}
          >
            {hasMlRecommendationCards && !message.isStreaming ? (
              <MlRecommendationResults presentation={mlRecommendationPresentation} />
            ) : hasNewsCards && hasDisclosureCards && !message.isStreaming ? (
              <div className="space-y-3">
                <NewsResults presentation={newsPresentation} />
                <DisclosureResults presentation={disclosurePresentation} />
              </div>
            ) : hasNewsCards && !message.isStreaming ? (
              <NewsResults presentation={newsPresentation} />
            ) : hasTradeHistoryTable && !message.isStreaming ? (
              <TradeHistoryResults presentation={tradeHistoryPresentation} />
            ) : hasWatchlistTable && !message.isStreaming ? (
              <WatchlistResults presentation={watchlistPresentation} />
            ) : hasDisclosureCards && !message.isStreaming ? (
              <DisclosureResults presentation={disclosurePresentation} />
            ) : message.text}
          </div>
        )}
        {hasMessageBody && messageTime && (
          <time
            className="max-w-full shrink-0 whitespace-nowrap px-1 text-[10px] font-medium leading-4 text-slate-500"
            dateTime={message.createdAt}
            title={messageDateTime || undefined}
          >
            {messageTime}
          </time>
        )}
        {!isUser && actions.length > 0 && (
          <div className="flex flex-wrap gap-2 px-1">
            {actions.map((action, index) => (
              <button
                key={`${action.type || 'action'}-${action.to || index}`}
                type="button"
                onClick={() => onAction(action)}
                className="rounded border border-ai-cyan/60 bg-ai-cyan/10 px-2.5 py-1.5 text-[11px] font-bold text-ai-cyan transition hover:bg-ai-cyan hover:text-[#07111f]"
              >
                {action.label || '이동'}
              </button>
            ))}
          </div>
        )}
        {!isUser && citations.length > 0 && (
          <CitationList citations={citations} />
        )}
      </div>
    </div>
  )
}

function WatchlistResults({ presentation }) {
  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between gap-2 border-b border-slate-700/70 pb-2">
        <p className="font-bold text-cyan-200">{presentation.title || '관심종목'}</p>
        <span className="shrink-0 rounded border border-cyan-500/30 bg-cyan-950/30 px-2 py-0.5 text-[10px] font-bold text-cyan-100">
          {presentation.count}건
        </span>
      </div>

      <div className="overflow-x-auto rounded border border-slate-700/80">
        <table className="w-full min-w-[520px] border-collapse text-left text-[11px]">
          <thead className="bg-slate-900/80 text-[10px] uppercase tracking-[0.08em] text-slate-400">
            <tr>
              <th className="whitespace-nowrap px-2.5 py-2 font-bold">종목명</th>
              <th className="whitespace-nowrap px-2.5 py-2 font-bold">종목코드</th>
              <th className="whitespace-nowrap px-2.5 py-2 font-bold">분류</th>
              <th className="whitespace-nowrap px-2.5 py-2 font-bold">거래소</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-800/80">
            {presentation.items.map((item) => (
              <tr key={`${item.exchange}-${item.assetType}-${item.symbol}`} className="bg-slate-950/20">
                <td className="whitespace-nowrap px-2.5 py-2 font-bold text-slate-100">{item.name}</td>
                <td className="whitespace-nowrap px-2.5 py-2 font-mono text-cyan-100">{item.symbol}</td>
                <td className="whitespace-nowrap px-2.5 py-2 text-slate-200">{item.assetType}</td>
                <td className="whitespace-nowrap px-2.5 py-2 font-mono text-slate-300">{item.exchange}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

function TradeHistoryResults({ presentation }) {
  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between gap-2 border-b border-slate-700/70 pb-2">
        <p className="font-bold text-cyan-200">{presentation.title || '거래내역'}</p>
        <span className="shrink-0 rounded border border-cyan-500/30 bg-cyan-950/30 px-2 py-0.5 text-[10px] font-bold text-cyan-100">
          {presentation.count}건
        </span>
      </div>

      <div className="overflow-x-auto rounded border border-slate-700/80">
        <table className="w-full min-w-[760px] border-collapse text-left text-[11px]">
          <thead className="bg-slate-950/70 text-[10px] uppercase tracking-[0.08em] text-slate-400">
            <tr>
              <th className="whitespace-nowrap px-2.5 py-2 font-bold">일시</th>
              <th className="whitespace-nowrap px-2.5 py-2 font-bold">거래소</th>
              <th className="px-2.5 py-2 font-bold">종목</th>
              <th className="whitespace-nowrap px-2.5 py-2 font-bold">구분</th>
              <th className="whitespace-nowrap px-2.5 py-2 text-right font-bold">체결가</th>
              <th className="whitespace-nowrap px-2.5 py-2 text-right font-bold">수량</th>
              <th className="whitespace-nowrap px-2.5 py-2 text-right font-bold">정산금액</th>
              <th className="whitespace-nowrap px-2.5 py-2 font-bold">상태</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-800/90">
            {presentation.items.map((item, index) => (
              <tr key={`${item.date}-${item.exchange}-${item.assetName}-${index}`} className="bg-slate-950/25">
                <td className="whitespace-nowrap px-2.5 py-2 font-mono text-slate-300">
                  {item.date.replaceAll('-', '.')} {item.time}
                </td>
                <td className="whitespace-nowrap px-2.5 py-2 font-mono text-slate-200">{item.exchange}</td>
                <td className="min-w-0 px-2.5 py-2 font-bold text-slate-100">
                  <span className="block max-w-40 truncate" title={item.assetName}>{item.assetName}</span>
                  <span className="mt-0.5 block font-mono text-[10px] font-medium text-slate-500">{item.symbol}</span>
                </td>
                <td className="whitespace-nowrap px-2.5 py-2 text-slate-200">{item.side}</td>
                <td className="whitespace-nowrap px-2.5 py-2 text-right font-mono font-bold text-slate-100">{item.priceText}</td>
                <td className="whitespace-nowrap px-2.5 py-2 text-right font-mono font-bold text-slate-100">{item.quantityText}</td>
                <td className="whitespace-nowrap px-2.5 py-2 text-right font-mono font-bold text-cyan-100">{item.amountText}</td>
                <td className="whitespace-nowrap px-2.5 py-2 text-slate-200">{item.status}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

function MlRecommendationResults({ presentation }) {
  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-start justify-between gap-2 border-b border-slate-700/70 pb-2">
        <div className="min-w-0">
          <p className="font-bold text-cyan-100">{presentation.title}</p>
          <p className="mt-0.5 text-[10px] leading-4 text-slate-400">주문 실행 근거가 아니라 검토 출발점입니다.</p>
        </div>
        {presentation.modelVersion ? (
          <span className="shrink-0 rounded border border-slate-600/70 bg-slate-950/50 px-2 py-0.5 text-[10px] font-medium text-slate-300">
            {presentation.modelVersion}
          </span>
        ) : null}
      </div>

      <div className="space-y-2">
        {presentation.items.map((item) => (
          <article key={`${item.rank}-${item.symbol}`} className="rounded border border-slate-700/80 bg-slate-950/35 px-3 py-2.5">
            <div className="flex min-w-0 items-start justify-between gap-2">
              <div className="min-w-0">
                <p className="text-[10px] font-bold text-cyan-300">#{item.rank}</p>
                <h4 className="break-words text-sm font-bold leading-5 text-slate-50">
                  {item.title}
                </h4>
              </div>
            </div>

            <div className="mt-2 grid grid-cols-3 gap-1.5">
              <SignalMetric label="점수" value={item.scoreText} tone="cyan" />
              <SignalMetric label="상승" value={item.upText} tone="emerald" />
              <SignalMetric label="위험" value={item.riskText} tone="amber" />
            </div>

            {item.reason ? (
              <p className="mt-2 break-words text-[11px] leading-5 text-slate-300">{item.reason}</p>
            ) : null}
          </article>
        ))}
      </div>
    </div>
  )
}

function SignalMetric({ label, value, tone }) {
  const toneClass = {
    cyan: 'border-cyan-500/25 bg-cyan-950/25 text-cyan-100',
    emerald: 'border-emerald-500/25 bg-emerald-950/25 text-emerald-100',
    amber: 'border-amber-500/25 bg-amber-950/25 text-amber-100',
  }[tone] || 'border-slate-600/60 bg-slate-950/40 text-slate-100'

  return (
    <div className={`min-w-0 rounded border px-2 py-1.5 ${toneClass}`}>
      <p className="text-[9px] font-medium text-slate-400">{label}</p>
      <p className="mt-0.5 truncate font-mono text-[12px] font-bold">{value}</p>
    </div>
  )
}

function NewsResults({ presentation }) {
  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between gap-2 border-b border-slate-700/70 pb-2">
        <p className="font-bold text-cyan-200">뉴스 요약</p>
        <span className="shrink-0 rounded border border-cyan-500/30 bg-cyan-950/30 px-2 py-0.5 text-[10px] font-bold text-cyan-100">
          {presentation.items.length}건
        </span>
      </div>

      {presentation.items.map((item, index) => (
        <article key={`${item.url || item.title}-${index}`} className="space-y-2 rounded border border-[#334155] bg-[#0f172a]/80 p-3">
          <div className="space-y-1.5">
            <div className="flex flex-wrap items-center gap-1.5">
              <span className="rounded border border-cyan-500/25 bg-cyan-950/25 px-1.5 py-0.5 text-[10px] font-bold text-cyan-200">
                {item.market}
              </span>
              <span className="rounded border border-slate-600/60 bg-slate-900/50 px-1.5 py-0.5 text-[10px] font-medium text-slate-200">
                {item.source}
              </span>
              <span className="rounded border border-slate-600/60 bg-slate-900/50 px-1.5 py-0.5 text-[10px] font-medium text-slate-200">
                {item.category}
              </span>
              {item.symbol ? (
                <span className="rounded border border-slate-600/60 bg-slate-900/50 px-1.5 py-0.5 text-[10px] font-medium text-slate-200">
                  {item.symbol}
                </span>
              ) : null}
              {item.publishedAt ? <span className="text-[10px] text-slate-500">{item.publishedAt}</span> : null}
            </div>
            <h4 className="break-words font-bold leading-5 text-slate-100">
              {index + 1}. {item.title}
            </h4>
          </div>

          {item.summaryLines.length > 0 ? (
            <div className="rounded border border-slate-700/70 bg-slate-950/40 px-2 py-1.5 text-slate-200">
              <p className="mb-1 font-bold text-cyan-100">AI 3줄 요약</p>
              <div className="space-y-1">
                {item.summaryLines.map((line, lineIndex) => (
                  <p key={`${item.title}-${lineIndex}`} className="break-words leading-5">
                    {line}
                  </p>
                ))}
              </div>
            </div>
          ) : null}

          <dl className="space-y-1">
            <div className="grid min-w-0 grid-cols-[max-content_minmax(0,1fr)] gap-2 rounded border border-slate-700/60 bg-slate-950/30 px-2 py-1.5">
              <dt className="whitespace-nowrap font-bold text-cyan-200">연관 키워드</dt>
              <dd className="min-w-0 break-words text-slate-100">{item.companyName || '정보 없음'}</dd>
            </div>
          </dl>

          {item.url ? (
            <a href={item.url} target="_blank" rel="noopener noreferrer" className="inline-flex rounded border border-blue-500/50 bg-blue-600 px-2.5 py-1.5 font-bold text-white transition hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-cyan-300">
              원문 열기
            </a>
          ) : null}
        </article>
      ))}
    </div>
  )
}

function TraceBadges({ badges }) {
  return (
    <div className="flex max-w-full flex-wrap gap-1 px-1">
      {badges.map((badge) => (
        <span
          key={`${badge.kind}-${badge.label}`}
          className="rounded border border-cyan-500/30 bg-cyan-950/35 px-1.5 py-0.5 text-[10px] font-bold text-cyan-100"
        >
          {badge.label}
        </span>
      ))}
    </div>
  )
}

function CitationList({ citations }) {
  return (
    <div className="w-full max-w-full space-y-1 rounded border border-slate-700/70 bg-slate-950/45 px-2.5 py-2 text-[10px] text-slate-300">
      <p className="font-bold text-cyan-200">근거</p>
      <ul className="space-y-1.5">
        {citations.map((citation, index) => (
          <li key={`${citation.label}-${citation.sourceId || index}`} className="min-w-0 break-words">
            <span className="font-bold text-slate-100">{citation.label}</span>
            {citation.title ? <span> · {citation.title}</span> : null}
            {citation.similarityText ? <span className="text-slate-500"> · {citation.similarityText}</span> : null}
            {citation.summary ? <p className="mt-0.5 text-slate-400">{citation.summary}</p> : null}
          </li>
        ))}
      </ul>
    </div>
  )
}

function DisclosureResults({ presentation }) {
  const disclosureToneClass = (sentiment) => {
    if (sentiment === 'positive') return 'border-emerald-500/40 bg-emerald-950/30 text-emerald-200'
    if (sentiment === 'negative') return 'border-rose-500/40 bg-rose-950/30 text-rose-200'
    if (sentiment === 'caution') return 'border-amber-500/40 bg-amber-950/30 text-amber-200'
    return 'border-cyan-500/30 bg-cyan-950/30 text-cyan-200'
  }

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between gap-2 border-b border-slate-700/70 pb-2">
        <p className="font-bold text-cyan-200">DART 공시 요약</p>
        <span className="shrink-0 rounded border border-cyan-500/30 bg-cyan-950/30 px-2 py-0.5 text-[10px] font-bold text-cyan-100">
          {presentation.items.length}건
        </span>
      </div>

      {presentation.items.map((item, index) => (
        <article key={`${item.url || item.title}-${index}`} className="space-y-2 rounded border border-[#334155] bg-[#0f172a]/80 p-3">
          <div className="space-y-1.5">
            <div className="flex flex-wrap items-center gap-1.5">
              <span className="rounded border border-cyan-500/25 bg-cyan-950/25 px-1.5 py-0.5 text-[10px] font-bold text-cyan-200">
                {item.corpName}
              </span>
              <span className={`rounded border px-1.5 py-0.5 text-[10px] font-bold ${disclosureToneClass(item.sentiment)}`}>
                {item.sentimentLabel}
              </span>
              <span className="rounded border border-slate-600/60 bg-slate-900/50 px-1.5 py-0.5 text-[10px] font-medium text-slate-200">
                신뢰도 {item.confidence}
              </span>
              <span className="text-[10px] text-slate-500">{item.source}</span>
            </div>
            <h4 className="break-words font-bold leading-5 text-slate-100">
              {index + 1}. {item.title}
            </h4>
          </div>

          {item.headline ? <p className="break-words font-bold text-cyan-100">{item.headline}</p> : null}
          {item.summary ? (
            <p className="break-words rounded border border-slate-700/70 bg-slate-950/40 px-2 py-1.5 leading-5 text-slate-200">
              {item.summary}
            </p>
          ) : null}

          {item.metrics.length > 0 ? (
            <dl className="space-y-1">
              {item.metrics.map((metric, metricIndex) => (
                <div key={`${metric.label}-${metricIndex}`} className="grid min-w-0 grid-cols-[max-content_minmax(0,1fr)] gap-2 rounded border border-slate-700/60 bg-slate-950/30 px-2 py-1.5">
                  <dt className="whitespace-nowrap font-bold text-cyan-200">{metric.label}</dt>
                  <dd className="min-w-0 break-words text-slate-100">{metric.value}</dd>
                </div>
              ))}
            </dl>
          ) : null}

          {item.checks.length > 0 ? (
            <dl className="space-y-1">
              {item.checks.map((check, checkIndex) => (
                <div key={`${check.question}-${checkIndex}`} className="grid min-w-0 grid-cols-[max-content_minmax(0,1fr)] gap-2 rounded border border-cyan-950/80 bg-[#07111f]/70 px-2 py-1.5">
                  <dt className="whitespace-nowrap font-bold text-cyan-200">{check.question}</dt>
                  <dd className="min-w-0 break-words text-slate-100">{check.answer}</dd>
                </div>
              ))}
            </dl>
          ) : null}

          {item.risk ? <p className="break-words text-amber-200/90">확인 포인트: {item.risk}</p> : null}
          {item.url ? (
            <a href={item.url} target="_blank" rel="noopener noreferrer" className="inline-flex rounded border border-blue-500/50 bg-blue-600 px-2.5 py-1.5 font-bold text-white transition hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-cyan-300">
              원문 열기
            </a>
          ) : null}
        </article>
      ))}

      {presentation.sourceUrl ? (
        <div className="border-t border-slate-700/70 pt-2">
          <a href={presentation.sourceUrl} target="_blank" rel="noopener noreferrer" className="break-words font-bold text-cyan-300 underline decoration-cyan-700 underline-offset-2 hover:text-cyan-100 focus:outline-none focus:ring-2 focus:ring-cyan-300">
            DART 전자공시시스템에서 전체 보기
          </a>
        </div>
      ) : null}
    </div>
  )
}

function ChatOrderForm({ onClose, onSubmit }) {
  const [exchange, setExchange] = useState('TOSS')
  const [brokerEnv, setBrokerEnv] = useState('REAL')
  const [side, setSide] = useState('BUY')
  const [symbolQuery, setSymbolQuery] = useState('')
  const [quantity, setQuantity] = useState('1')
  const [orderType, setOrderType] = useState('LIMIT')
  const [price, setPrice] = useState('')

  const [isConditional, setIsConditional] = useState(false)
  const [conditionalCategory, setConditionalCategory] = useState('SELL_STOP_LIMIT') // SELL_STOP_LIMIT, BUY_TRIGGER
  const [targetProfitRate, setTargetProfitRate] = useState('3')
  const [stopLossRate, setStopLossRate] = useState('-3')
  const [buyTriggerPrice, setBuyTriggerPrice] = useState('')
  const [conditionalMode, setConditionalMode] = useState('PROPOSAL')

  const handleSubmitForm = (e) => {
    e.preventDefault()
    if (!symbolQuery.trim()) {
      alert('종목명을 입력하세요.')
      return
    }
    const qtyVal = parseFloat(quantity)
    if (isNaN(qtyVal) || qtyVal <= 0) {
      alert('올바른 수량을 입력하세요.')
      return
    }

    let priceVal = null
    if (orderType === 'LIMIT') {
      priceVal = parseFloat(price)
      if (isNaN(priceVal) || priceVal <= 0) {
        alert('올바른 지정가를 입력하세요.')
        return
      }
    }

    let condPriceVal = null
    let profitRateVal = 0.0
    let lossRateVal = 0.0
    let condType = 'BUY_LIMIT'

    if (isConditional) {
      if (conditionalCategory === 'BUY_TRIGGER') {
        condPriceVal = parseFloat(buyTriggerPrice)
        if (isNaN(condPriceVal) || condPriceVal <= 0) {
          alert('올바른 조건매수 가격을 입력하세요.')
          return
        }
        condType = 'BUY_LIMIT'
      } else {
        profitRateVal = parseFloat(targetProfitRate)
        lossRateVal = parseFloat(stopLossRate)
        if (isNaN(profitRateVal) || isNaN(lossRateVal)) {
          alert('올바른 익절/손절 비율을 입력하세요.')
          return
        }
        condType = 'STOP_LIMIT'
      }
    }

    onSubmit({
      is_structured_order: true,
      exchange,
      broker_env: brokerEnv,
      side,
      symbol_query: symbolQuery,
      quantity: qtyVal,
      order_type: orderType,
      price: priceVal,
      is_conditional: isConditional,
      conditional_type: condType,
      conditional_price: condPriceVal,
      target_profit_rate: profitRateVal,
      stop_loss_rate: lossRateVal,
      conditional_mode: conditionalMode,
    })
  }

  const isMockDisabled = exchange === 'TOSS' || exchange === 'COINONE'
  const isMarketDisabled = exchange === 'COINONE'

  return (
    <form onSubmit={handleSubmitForm} className="space-y-2 rounded-lg border border-slate-700 bg-slate-900/90 p-3.5 text-xs text-slate-100 backdrop-blur-md">
      <div className="flex items-center justify-between border-b border-slate-800 pb-1.5">
        <h3 className="font-bold text-ai-cyan">반자율 주문 제안 생성기</h3>
        <button type="button" onClick={onClose} className="text-slate-400 hover:text-slate-200">닫기</button>
      </div>

      <div className="grid grid-cols-2 gap-2">
        <div>
          <label className="mb-1 block text-[10px] text-slate-400">거래소</label>
          <select
            value={exchange}
            onChange={(e) => {
              const val = e.target.value
              setExchange(val)
              if (val === 'TOSS' || val === 'COINONE') {
                setBrokerEnv('REAL')
              }
              if (val === 'COINONE') {
                setOrderType('LIMIT')
              }
            }}
            className="w-full rounded border border-slate-700 bg-slate-950 p-1 text-slate-200 outline-none focus:border-ai-cyan"
          >
            <option value="TOSS">TOSS (주식)</option>
            <option value="COINONE">COINONE (코인)</option>
            <option value="KIS">한국투자증권</option>
            <option value="BINANCE">BINANCE (선물)</option>
          </select>
        </div>

        <div>
          <label className="mb-1 block text-[10px] text-slate-400">투자 환경</label>
          <select
            value={brokerEnv}
            disabled={isMockDisabled}
            onChange={(e) => setBrokerEnv(e.target.value)}
            className="w-full rounded border border-slate-700 bg-slate-950 p-1 text-slate-200 outline-none focus:border-ai-cyan disabled:cursor-not-allowed disabled:opacity-50"
          >
            <option value="REAL">실제투자 (REAL)</option>
            <option value="MOCK">모의투자 (MOCK)</option>
          </select>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-2">
        <div>
          <label className="mb-1 block text-[10px] text-slate-400">구분</label>
          <div className="flex rounded border border-slate-700 bg-slate-950 p-0.5">
            <button
              type="button"
              onClick={() => setSide('BUY')}
              className={`flex-1 rounded py-0.5 font-bold ${side === 'BUY' ? 'bg-emerald-600 text-white' : 'text-slate-400'}`}
            >
              매수
            </button>
            <button
              type="button"
              onClick={() => setSide('SELL')}
              className={`flex-1 rounded py-0.5 font-bold ${side === 'SELL' ? 'bg-rose-600 text-white' : 'text-slate-400'}`}
            >
              매도
            </button>
          </div>
        </div>

        <div>
          <label className="mb-1 block text-[10px] text-slate-400">주문 유형</label>
          <div className="flex rounded border border-slate-700 bg-slate-950 p-0.5">
            <button
              type="button"
              onClick={() => setOrderType('LIMIT')}
              className={`flex-1 rounded py-0.5 font-bold ${orderType === 'LIMIT' ? 'bg-blue-600 text-white' : 'text-slate-400'}`}
            >
              지정가
            </button>
            <button
              type="button"
              disabled={isMarketDisabled}
              onClick={() => setOrderType('MARKET')}
              className={`flex-1 rounded py-0.5 font-bold disabled:cursor-not-allowed disabled:opacity-40 ${orderType === 'MARKET' ? 'bg-blue-600 text-white' : 'text-slate-400'}`}
            >
              시장가
            </button>
          </div>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-2">
        <div>
          <label className="mb-1 block text-[10px] text-slate-400">종목</label>
          <input
            type="text"
            value={symbolQuery}
            onChange={(e) => setSymbolQuery(e.target.value)}
            placeholder="예: 이노스페이스, AAPL"
            className="w-full rounded border border-slate-700 bg-slate-950 p-1 text-slate-200 outline-none focus:border-ai-cyan"
          />
        </div>

        <div>
          <label className="mb-1 block text-[10px] text-slate-400">수량</label>
          <input
            type="number"
            step="any"
            value={quantity}
            onChange={(e) => setQuantity(e.target.value)}
            placeholder="수량"
            className="w-full rounded border border-slate-700 bg-slate-950 p-1 text-slate-200 outline-none focus:border-ai-cyan font-mono"
          />
        </div>
      </div>

      {orderType === 'LIMIT' && (
        <div>
          <label className="mb-1 block text-[10px] text-slate-400">주문 단가</label>
          <input
            type="number"
            step="any"
            value={price}
            onChange={(e) => setPrice(e.target.value)}
            placeholder="단가 입력"
            className="w-full rounded border border-slate-700 bg-slate-950 p-1 text-slate-200 outline-none focus:border-ai-cyan font-mono"
          />
        </div>
      )}

      <div className="border-t border-slate-800 pt-2">
        <label className="flex items-center gap-1.5 cursor-pointer text-slate-300 font-bold">
          <input
            type="checkbox"
            checked={isConditional}
            onChange={(e) => setIsConditional(e.target.checked)}
            className="rounded border-slate-700 bg-slate-950 text-ai-cyan focus:ring-0 focus:ring-offset-0"
          />
          조건감시(스케줄링) 설정 추가
        </label>
      </div>

      {isConditional && (
        <div className="space-y-2 rounded border border-slate-800 bg-slate-950/40 p-2">
          <div className="grid grid-cols-2 gap-2">
            <div>
              <label className="mb-1 block text-[10px] text-slate-400">감시 구분</label>
              <select
                value={conditionalCategory}
                onChange={(e) => setConditionalCategory(e.target.value)}
                className="w-full rounded border border-slate-700 bg-slate-950 p-1 text-slate-200 outline-none focus:border-ai-cyan"
              >
                <option value="SELL_STOP_LIMIT">조건 매도 (수익률 % 감시)</option>
                <option value="BUY_TRIGGER">조건 매수 (지정 가격 도달)</option>
              </select>
            </div>

            <div>
              <label className="mb-1 block text-[10px] text-slate-400">실행 모드</label>
              <select
                value={conditionalMode}
                onChange={(e) => setConditionalMode(e.target.value)}
                className="w-full rounded border border-slate-700 bg-slate-950 p-1 text-slate-200 outline-none focus:border-ai-cyan"
              >
                <option value="PROPOSAL">제안 생성 (PROPOSAL)</option>
                <option value="AUTO">자동 주문 (AUTO)</option>
              </select>
            </div>
          </div>

          {conditionalCategory === 'SELL_STOP_LIMIT' ? (
            <div className="grid grid-cols-2 gap-2 border-t border-slate-800/80 pt-1.5">
              <div>
                <label className="mb-1 block text-[10px] text-slate-400">익절 목표 (%)</label>
                <input
                  type="number"
                  step="any"
                  value={targetProfitRate}
                  onChange={(e) => setTargetProfitRate(e.target.value)}
                  placeholder="예: 5 (+5%)"
                  className="w-full rounded border border-slate-700 bg-slate-950 p-1 text-slate-200 outline-none focus:border-ai-cyan font-mono"
                />
              </div>
              <div>
                <label className="mb-1 block text-[10px] text-slate-400">손절 제한 (%)</label>
                <input
                  type="number"
                  step="any"
                  value={stopLossRate}
                  onChange={(e) => setStopLossRate(e.target.value)}
                  placeholder="예: -3 (-3%)"
                  className="w-full rounded border border-slate-700 bg-slate-950 p-1 text-slate-200 outline-none focus:border-ai-cyan font-mono"
                />
              </div>
            </div>
          ) : (
            <div className="border-t border-slate-800/80 pt-1.5">
              <label className="mb-1 block text-[10px] text-slate-400">감시 기준가격</label>
              <div className="flex items-center gap-1.5">
                <input
                  type="number"
                  step="any"
                  value={buyTriggerPrice}
                  onChange={(e) => setBuyTriggerPrice(e.target.value)}
                  placeholder="기준가격 입력"
                  className="flex-1 rounded border border-slate-700 bg-slate-950 p-1.5 text-slate-200 outline-none focus:border-ai-cyan font-mono"
                />
                <span className="text-[10px] text-slate-400">원/USD 이하 도달 시 매수</span>
              </div>
            </div>
          )}
        </div>
      )}

      <button
        type="submit"
        className="w-full rounded bg-ai-cyan py-1.5 text-xs font-bold text-[#07111f] transition hover:brightness-110"
      >
        매매 제안 전송
      </button>
    </form>
  )
}

export default function ChatbotWidget({
  enabled = true,
  isLoggedIn = false,
  presentation = 'floating',
  onClose = null,
}) {
  const navigate = useNavigate()
  const isMobilePage = presentation === 'mobile-page'
  const [isOpen, setIsOpen] = useState(isMobilePage)
  const [panelSize, setPanelSize] = useState(getDefaultChatbotSize)
  const [messages, setMessages] = useState(INITIAL_MESSAGES)
  const [input, setInput] = useState('')
  const [isSending, setIsSending] = useState(false)
  const [showOrderForm, setShowOrderForm] = useState(false)
  const [pendingProposals, setPendingProposals] = useState([])
  const [proposalActionId, setProposalActionId] = useState('')
  const widgetInstanceId = useId()
  const messageIdSequenceRef = useRef(0)
  const timelineOrderSequenceRef = useRef(0)
  const proposalActionIdRef = useRef('')
  const inputRef = useRef(null)
  const messagesEndRef = useRef(null)
  const resizeStateRef = useRef(null)

  useEffect(() => {
    const handleOpenChatbot = () => {
      if (!enabled || isMobilePage) return

      setPanelSize(getDefaultChatbotSize())
      setIsOpen(true)
      window.setTimeout(() => inputRef.current?.focus(), 80)
    }

    window.addEventListener('antry:open-chatbot', handleOpenChatbot)
    return () => {
      window.removeEventListener('antry:open-chatbot', handleOpenChatbot)
    }
  }, [enabled, isMobilePage])

  useEffect(() => {
    if (!enabled || (!isOpen && !isMobilePage)) return

    window.requestAnimationFrame(() => {
      messagesEndRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' })
    })
  }, [enabled, isMobilePage, isOpen, messages, pendingProposals, isSending])

  useEffect(() => {
    let active = true
    let channel = null

    if (!enabled || !isLoggedIn) {
      queueMicrotask(() => {
        if (active) setPendingProposals([])
      })
      return () => {
        active = false
      }
    }

    const loadPendingProposals = async () => {
      const { data: { session } } = await supabase.auth.getSession()
      const userId = session?.user?.id
      if (!userId || !active) return

      const { data, error } = await supabase
        .from('trade_proposals')
        .select('id,exchange,asset_type,symbol,ticker,side,price,volume,order_amount,ord_type,broker_env,market_country,currency,status,raw_order_payload,created_at')
        .eq('user_id', userId)
        .eq('status', 'PENDING')
        .order('created_at', { ascending: false })
        .limit(10)

      if (!error && active) {
        const proposals = [...(data || [])].reverse().filter(isChatbotApprovalProposal).map((proposal) => ({
          ...proposal,
          timelineOrder: ++timelineOrderSequenceRef.current,
        }))
        setPendingProposals(proposals)
      }

      channel = supabase
        .channel(`chatbot-trade-proposals-${userId}`)
        .on(
          'postgres_changes',
          {
            event: '*',
            schema: 'public',
            table: 'trade_proposals',
            filter: `user_id=eq.${userId}`,
          },
          (payload) => {
            if (!active) return
            if (payload.eventType === 'DELETE') {
              setPendingProposals((items) => items.filter((item) => item.id !== payload.old?.id))
              return
            }
            if (!isChatbotApprovalProposal(payload.new)) {
              setPendingProposals((items) => items.filter((item) => item.id !== payload.new?.id))
              return
            }
            setPendingProposals((items) => {
              const existing = items.find((item) => item.id === payload.new?.id)
              return mergePendingProposal(items, {
                ...payload.new,
                timelineOrder: existing?.timelineOrder ?? ++timelineOrderSequenceRef.current,
              })
            })
          },
        )
        .subscribe()
    }

    loadPendingProposals()
    return () => {
      active = false
      if (channel) supabase.removeChannel(channel)
    }
  }, [enabled, isLoggedIn])

  if (!enabled) return null

  const openChat = () => {
    setPanelSize(getDefaultChatbotSize())
    setIsOpen(true)
    window.setTimeout(() => inputRef.current?.focus(), 80)
  }

  const closeChat = () => {
    if (isMobilePage) {
      onClose?.()
      return
    }

    resizeStateRef.current = null
    setIsOpen(false)
    setPanelSize(getDefaultChatbotSize())
  }

  const resetConversation = () => {
    setInput('')
    setIsSending(false)
    setMessages(INITIAL_MESSAGES.map((message) => ({
      ...message,
      createdAt: new Date().toISOString(),
    })))
    setPendingProposals([])
    messageIdSequenceRef.current = 0
    timelineOrderSequenceRef.current = 0
  }

  const startResize = (event, direction) => {
    if (window.matchMedia('(max-width: 767px)').matches) return

    event.preventDefault()
    resizeStateRef.current = {
      direction,
      startClientX: event.clientX,
      startClientY: event.clientY,
      startSize: panelSize,
    }

    const handlePointerMove = (moveEvent) => {
      const resizeState = resizeStateRef.current
      if (!resizeState) return

      setPanelSize(
        resizeChatbotPanel({
          ...resizeState,
          clientX: moveEvent.clientX,
          clientY: moveEvent.clientY,
          viewport: {
            width: window.innerWidth,
            height: window.innerHeight,
          },
        }),
      )
    }

    const stopResize = () => {
      resizeStateRef.current = null
      window.removeEventListener('mousemove', handlePointerMove)
      window.removeEventListener('mouseup', stopResize)
    }

    window.addEventListener('mousemove', handlePointerMove)
    window.addEventListener('mouseup', stopResize)
  }

  const handleAction = (action) => {
    if (action?.type === 'navigate' && action.to) {
      navigate(action.to)
      if (!isMobilePage) closeChat()
    }
  }

  const nextMessageId = (role) => {
    messageIdSequenceRef.current += 1
    return `${widgetInstanceId}-${role}-${messageIdSequenceRef.current}`
  }

  const handleRejectProposal = async (proposalId) => {
    if (proposalActionIdRef.current) return
    proposalActionIdRef.current = proposalId
    setProposalActionId(proposalId)
    try {
      const { data: { session } } = await supabase.auth.getSession()
      if (!session?.access_token) throw new Error('로그인이 필요합니다.')
      const response = await fetch(`${import.meta.env.VITE_API_BASE_URL || 'http://localhost:5050'}/api/trade/proposal/reject`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${session.access_token}`,
        },
        body: JSON.stringify({ proposal_id: proposalId }),
      })
      const payload = await response.json().catch(() => ({}))
      if (!response.ok || payload.success === false) {
        throw new Error(buildApiErrorText(payload, '매매 제안 거절에 실패했습니다.'))
      }
      setPendingProposals((items) => items.filter((item) => item.id !== proposalId))
      addMessage('assistant', '매매 제안이 정상적으로 거절(취소)되었습니다.')
    } catch (error) {
      addMessage('assistant', buildApiErrorText(error, '매매 제안 거절에 실패했습니다.'))
    } finally {
      proposalActionIdRef.current = ''
      setProposalActionId('')
    }
  }

  const handleApproveProposal = async (proposal) => {
    if (proposalActionIdRef.current || isProposalApprovalBlocked(proposal)) return
    proposalActionIdRef.current = proposal.id
    setProposalActionId(proposal.id)
    try {
      const { data: { session } } = await supabase.auth.getSession()
      if (!session?.access_token) throw new Error('로그인이 필요합니다.')
      const response = await fetch(`${import.meta.env.VITE_API_BASE_URL || 'http://localhost:5050'}/api/trade/proposal/approve`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${session.access_token}`,
        },
        body: JSON.stringify({ proposal_id: proposal.id }),
      })
      const payload = await response.json().catch(() => ({}))
      if (!response.ok || payload.success === false) {
        throw new Error(buildApiErrorText(payload, '매매 제안 승인에 실패했습니다.'))
      }
      setPendingProposals((items) => items.filter((item) => item.id !== proposal.id))
      const successMsg = payload.message || `${proposal.symbol || proposal.ticker} ${proposal.side === 'BUY' ? '매수' : '매도'} 주문이 성공적으로 제출되었습니다.`
      addMessage('assistant', successMsg)
    } catch (error) {
      addMessage('assistant', buildApiErrorText(error, '매매 제안 승인에 실패했습니다.'))
    } finally {
      proposalActionIdRef.current = ''
      setProposalActionId('')
    }
  }

  const addMessage = (role, text, actions = [], toolResult = null, traceSteps = []) => {
    const id = nextMessageId(role)
    const createdAt = new Date().toISOString()
    setMessages((prev) => [
      ...prev,
      {
        id,
        role,
        text,
        actions,
        toolResult,
        traceSteps,
        isStreaming: false,
        createdAt,
        timelineOrder: ++timelineOrderSequenceRef.current,
      },
    ])
  }

  const addStreamingAssistantMessage = () => {
    const id = nextMessageId('assistant')
    setMessages((prev) => [
      ...prev,
      {
        id,
        role: 'assistant',
        text: '',
        actions: [],
        toolResult: null,
        traceSteps: [],
        isStreaming: true,
        createdAt: new Date().toISOString(),
        timelineOrder: ++timelineOrderSequenceRef.current,
      },
    ])
    return id
  }

  const appendAssistantDelta = (messageId, text) => {
    if (!text) return
    setMessages((prev) => prev.map((message) => (
      message.id === messageId
        ? { ...message, text: `${message.text || ''}${text}` }
        : message
    )))
  }

  const appendAssistantTrace = (messageId, traceStep) => {
    if (!traceStep?.kind && !traceStep?.label) return
    setMessages((prev) => prev.map((message) => {
      if (message.id !== messageId) return message
      const traceSteps = Array.isArray(message.traceSteps) ? message.traceSteps : []
      if (traceSteps.some((step) => step.kind === traceStep.kind && step.label === traceStep.label)) {
        return message
      }
      return { ...message, traceSteps: [...traceSteps, traceStep] }
    }))
  }

  const completeAssistantStream = (messageId, payload) => {
    setMessages((prev) => prev.map((message) => (
      message.id === messageId
        ? {
          ...message,
          text: payload?.reply || message.text,
          actions: payload?.actions || [],
          toolResult: payload?.meta?.tool_result || null,
          traceSteps: payload?.meta?.trace_steps || message.traceSteps || [],
          isStreaming: false,
        }
        : message
    )))
  }

  const submitMessage = async (text = input) => {
    if (!isLoggedIn) {
      navigate('/login')
      if (!isMobilePage) closeChat()
      return
    }

    const trimmed = text.trim()
    if (!trimmed || isSending) return

    setInput('')
    addMessage('user', trimmed)
    setIsSending(true)
    const assistantMessageId = addStreamingAssistantMessage()

    try {
      await streamChatbotMessage(
        trimmed,
        {
          onTrace: (traceStep) => appendAssistantTrace(assistantMessageId, traceStep),
          onDelta: (textChunk) => appendAssistantDelta(assistantMessageId, textChunk),
          onDone: (payload) => completeAssistantStream(assistantMessageId, payload),
        },
        { timezone: getUserTimeZone() },
      )
    } catch (error) {
      completeAssistantStream(assistantMessageId, {
        reply: error.message || '챗봇 연결 중 문제가 발생했습니다.',
        actions: [],
        meta: {},
      })
    } finally {
      setIsSending(false)
      window.setTimeout(() => inputRef.current?.focus(), 80)
    }
  }

  const handleFormSubmit = async (structuredPayload) => {
    setShowOrderForm(false)
    if (!isLoggedIn) {
      navigate('/login')
      closeChat()
      return
    }
    if (isSending) return

    const priceText = structuredPayload.order_type === 'LIMIT' ? `${structuredPayload.price.toLocaleString()}원 지정가` : '시장가'
    let condText = ''
    if (structuredPayload.is_conditional) {
      if (structuredPayload.conditional_type === 'BUY_LIMIT') {
        condText = ` (조건매수: ${structuredPayload.conditional_price.toLocaleString()}원 이하 감시, 실행: ${structuredPayload.conditional_mode})`
      } else {
        condText = ` (조건매도: 익절 +${structuredPayload.target_profit_rate}%, 손절 ${structuredPayload.stop_loss_rate}%, 실행: ${structuredPayload.conditional_mode})`
      }
    }
    const displayMsg = `[주문 폼 전송] ${structuredPayload.exchange} (${structuredPayload.broker_env}) ${structuredPayload.symbol_query} ${structuredPayload.quantity}주 ${structuredPayload.side === 'BUY' ? '매수' : '매도'} ${priceText}${condText}`

    addMessage('user', displayMsg)
    setIsSending(true)
    const assistantMessageId = addStreamingAssistantMessage()

    try {
      await streamChatbotMessage(
        displayMsg,
        {
          onTrace: (traceStep) => appendAssistantTrace(assistantMessageId, traceStep),
          onDelta: (textChunk) => appendAssistantDelta(assistantMessageId, textChunk),
          onDone: (payload) => completeAssistantStream(assistantMessageId, payload),
        },
        {
          timezone: getUserTimeZone(),
          structured_order: structuredPayload
        },
      )
    } catch (error) {
      completeAssistantStream(assistantMessageId, {
        reply: error.message || '챗봇 연결 중 문제가 발생했습니다.',
        actions: [],
        meta: {},
      })
    } finally {
      setIsSending(false)
      window.setTimeout(() => inputRef.current?.focus(), 80)
    }
  }

  const handleSubmit = (event) => {
    event.preventDefault()
    submitMessage()
  }

  return (
    <>
      {(isOpen || isMobilePage) && (
        <section
          className={isMobilePage
            ? 'flex min-h-dvh flex-col overflow-hidden bg-obsidian-bg text-slate-100'
            : 'fixed bottom-24 right-4 z-40 flex h-[min(560px,calc(100vh-128px))] w-[min(390px,calc(100vw-32px))] flex-col overflow-hidden rounded-lg border border-ai-cyan/35 bg-[#070b14]/95 shadow-[0_18px_60px_rgba(0,0,0,0.45)] backdrop-blur md:right-6 md:h-auto md:w-auto'}
          style={isMobilePage ? undefined : {
            width: `${panelSize.width}px`,
            height: `${panelSize.height}px`,
            maxWidth: 'min(720px, calc(90vw))',
            maxHeight: 'min(760px, calc(85vh))',
          }}
        >
          <div
            className="absolute left-0 top-0 z-10 hidden h-5 w-5 cursor-nwse-resize md:block"
            onMouseDown={(event) => startResize(event, 'corner')}
            aria-hidden="true"
          />
          <div
            className="absolute left-0 top-5 z-10 hidden h-[calc(100%-20px)] w-2 cursor-ew-resize md:block"
            onMouseDown={(event) => startResize(event, 'x')}
            aria-hidden="true"
          />
          <div
            className="absolute left-5 top-0 z-10 hidden h-2 w-[calc(100%-20px)] cursor-ns-resize md:block"
            onMouseDown={(event) => startResize(event, 'y')}
            aria-hidden="true"
          />
          <header className={isMobilePage
            ? 'grid grid-cols-[1fr_auto_1fr] items-center px-5 pb-6 pt-[calc(env(safe-area-inset-top)+18px)]'
            : 'flex items-center justify-between border-b border-slate-800 bg-[#0f172a] px-4 py-3'}
          >
            {isMobilePage ? (
              <>
                <div className="flex items-center gap-3">
                  <button
                    type="button"
                    onClick={resetConversation}
                    className="grid h-10 w-10 place-items-center rounded-full text-ai-cyan transition active:bg-ai-cyan/10"
                    aria-label="Reset chat"
                  >
                    <span className="material-symbols-outlined text-[30px] leading-none">refresh</span>
                  </button>
                </div>
                <h1 className="text-center text-2xl font-black tracking-tight text-white">챗봇 상담</h1>
                <div className="flex justify-end gap-2">
                  {isLoggedIn ? (
                    <button
                      type="button"
                      onClick={() => setShowOrderForm((prev) => !prev)}
                      disabled={isSending}
                      className="h-10 shrink-0 rounded-full border border-ai-cyan/60 bg-ai-cyan/10 px-3 text-xs font-bold text-ai-cyan transition active:bg-ai-cyan active:text-[#07111f] disabled:opacity-50"
                      aria-label="매매 요청 폼 열기"
                    >
                      매매 요청
                    </button>
                  ) : null}
                  <button
                    type="button"
                    onClick={closeChat}
                    className="grid h-12 w-12 place-items-center rounded-full text-slate-200 transition active:bg-ai-cyan/10 active:text-ai-cyan"
                    aria-label="Close chatbot"
                  >
                    <span className="material-symbols-outlined text-[42px] leading-none">close</span>
                  </button>
                </div>
              </>
            ) : (
              <>
                <div className="flex min-w-0 items-center gap-3">
                  <img
                    src="/chatbot-bot.png"
                    alt="AE 챗봇"
                    className="h-10 w-10 shrink-0 rounded-full border border-ai-cyan/50 object-cover object-top"
                  />
                  <div className="min-w-0">
                    <p className="truncate text-sm font-bold text-white">AE Trading Bot</p>
                  </div>
                </div>
                <div className="flex shrink-0 items-center gap-2">
                  {isLoggedIn ? (
                    <button
                      type="button"
                      onClick={() => setShowOrderForm((prev) => !prev)}
                      disabled={isSending}
                      className="h-8 rounded border border-ai-cyan/60 bg-ai-cyan/10 px-3 text-xs font-bold text-ai-cyan transition hover:bg-ai-cyan hover:text-[#07111f] disabled:opacity-50"
                      aria-label="매매 요청 폼 열기"
                    >
                      매매 요청
                    </button>
                  ) : null}
                  <button
                    type="button"
                    onClick={closeChat}
                    className="grid h-8 w-8 shrink-0 place-items-center rounded border border-slate-700 text-sm font-bold text-slate-300 transition hover:border-ai-cyan hover:text-ai-cyan"
                    aria-label="챗봇 닫기"
                  >
                    x
                  </button>
                </div>
              </>
            )}
          </header>

          <div className={isMobilePage
            ? 'flex flex-1 flex-col gap-3 overflow-y-auto px-5 pb-6 pt-2'
            : 'flex flex-1 flex-col gap-3 overflow-y-auto px-4 py-4'}
          >
            {isMobilePage ? (
              <div className="mb-1 flex h-14 w-14 items-center justify-center overflow-hidden rounded-full border border-ai-cyan/40 bg-ai-cyan/10">
                <img src="/chatbot-bot.png" alt="" className="h-full w-full object-cover object-top" />
              </div>
            ) : null}
            {buildChatbotTimeline(messages, pendingProposals).map((item) => (
              item.type === 'message'
                ? <ChatMessage key={item.id} message={item.data} onAction={handleAction} />
                : (
                  <TradeProposalCard
                    key={item.id}
                    proposal={item.data}
                    proposalActionId={proposalActionId}
                    onApprove={handleApproveProposal}
                    onReject={handleRejectProposal}
                  />
                )
            ))}
            {isSending && (
              <div className="w-fit rounded-lg border border-slate-700/80 bg-[#111827] px-3 py-2 text-xs text-slate-400">
                답변 작성 중...
              </div>
            )}
            <div ref={messagesEndRef} aria-hidden="true" />
          </div>

          <div className={isMobilePage
            ? 'border-t border-ai-cyan/10 bg-[#061321]/95 px-4 pb-[calc(env(safe-area-inset-bottom)+14px)] pt-4 shadow-[0_-14px_34px_rgba(0,0,0,0.42)] backdrop-blur-xl'
            : 'border-t border-slate-800 bg-[#0b1120] p-3'}
          >
            {showOrderForm && (
              <div className="mb-3 max-h-[320px] overflow-y-auto rounded-lg border border-slate-800 bg-[#070b14]/90 p-0.5">
                <ChatOrderForm
                  onClose={() => setShowOrderForm(false)}
                  onSubmit={handleFormSubmit}
                />
              </div>
            )}
            <form onSubmit={handleSubmit} className={isMobilePage ? 'flex items-center gap-3' : 'flex items-end gap-2'}>
              {isMobilePage ? (
                <>
                  <button
                    type="button"
                    onClick={() => setIsQuickMenuOpen((open) => !open)}
                    className="grid h-11 w-11 shrink-0 place-items-center rounded-full text-slate-400 transition active:bg-ai-cyan/10 active:text-ai-cyan"
                    aria-label={isQuickMenuOpen ? 'Close chatbot categories' : 'Open chatbot categories'}
                    aria-expanded={isQuickMenuOpen}
                  >
                    <span className="material-symbols-outlined text-[34px] leading-none">menu</span>
                  </button>
                  <div className="h-12 w-px shrink-0 bg-slate-700" aria-hidden="true" />
                </>
              ) : null}
              <textarea
                ref={inputRef}
                value={input}
                onChange={(event) => setInput(event.target.value)}
                onClick={() => {
                  if (!isLoggedIn) navigate('/login')
                }}
                onKeyDown={(event) => {
                  if (shouldSubmitChatbotInput(event)) {
                    event.preventDefault()
                    submitMessage()
                  }
                }}
                rows={2}
                readOnly={!isLoggedIn}
                placeholder={isLoggedIn ? (isMobilePage ? '궁금한 점을 입력해 주세요.' : '메시지를 입력하세요') : '로그인 후 이용 가능합니다'}
                className={isMobilePage
                  ? 'max-h-28 min-h-12 flex-1 resize-none border-none bg-transparent px-0 py-3 text-lg leading-6 text-slate-100 outline-none placeholder:text-slate-400 read-only:cursor-pointer'
                  : 'min-h-11 flex-1 resize-none rounded border border-slate-700 bg-[#111827] px-3 py-2 text-xs text-slate-100 outline-none transition placeholder:text-slate-500 focus:border-ai-cyan read-only:cursor-pointer read-only:border-ai-cyan/40'}
              />
              <button
                type="submit"
                disabled={isLoggedIn ? isSending || !input.trim() : false}
                className={isMobilePage
                  ? 'grid h-12 w-12 shrink-0 place-items-center rounded-full text-ai-cyan transition active:bg-ai-cyan/10 disabled:cursor-not-allowed disabled:opacity-40'
                  : 'h-11 shrink-0 rounded bg-ai-cyan px-4 text-xs font-bold text-[#07111f] transition hover:brightness-110 disabled:cursor-not-allowed disabled:opacity-50'}
              >
                {isMobilePage ? (
                  <span className="material-symbols-outlined rotate-[-28deg] text-[42px] leading-none">send</span>
                ) : (
                  isLoggedIn ? '전송' : '로그인'
                )}
              </button>
            </form>
          </div>
        </section>
      )}

      {!isMobilePage ? (
        <button
          type="button"
          onClick={isOpen ? closeChat : openChat}
          className="fixed bottom-6 right-4 z-40 hidden h-16 w-16 place-items-center overflow-hidden rounded-full border-2 border-ai-cyan/70 bg-[#07111f] shadow-[0_0_28px_rgba(0,242,254,0.28)] transition hover:scale-105 hover:border-ai-cyan md:right-6 md:grid"
          aria-label={isOpen ? '챗봇 닫기' : '챗봇 열기'}
        >
          <img src="/chatbot-bot.png" alt="" className="h-full w-full object-cover object-top" />
        </button>
      ) : null}
    </>
  )
}
