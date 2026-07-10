import { useEffect, useId, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { supabase } from '../../supabaseClient'
import { buildApiErrorText } from '../../lib/apiError.js'
import { streamChatbotMessage } from './chatbotApi'
import { buildChatbotCitations } from './chatbotCitations'
import { buildDisclosurePresentation } from './chatbotDisclosurePresentation'
import { shouldSubmitChatbotInput } from './chatbotInput'
import {
  buildProposalPrecheckSummary,
  isProposalApprovalBlocked,
} from './chatbotProposalPrecheck'
import { getDefaultChatbotSize, resizeChatbotPanel } from './chatbotResize'
import {
  buildChatbotTimeline,
  formatChatbotProposalNumber,
} from './chatbotTimeline'
import { buildChatbotTraceBadges } from './chatbotTrace'

const INITIAL_MESSAGES = [
  {
    id: 'welcome',
    role: 'assistant',
    text: '안녕하세요. AE 트레이딩 챗봇입니다. \n시세, 보유자산, 매매 제안 흐름을 도와드릴게요.',
    createdAt: new Date().toISOString(),
  },
]

const QUICK_MESSAGES = [
  '내 보유자산 요약해줘',
  '시세 확인은 어떻게 해?',
  '매매 제안 만들어줘',
]

function getUserTimeZone() {
  return Intl.DateTimeFormat().resolvedOptions().timeZone || undefined
}

function formatMessageTime(createdAt) {
  if (!createdAt) return ''

  try {
    return new Intl.DateTimeFormat('ko-KR', {
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
  const actions = Array.isArray(message.actions) ? message.actions : []
  const disclosurePresentation = buildDisclosurePresentation(message.toolResult)
  const hasDisclosureCards = !isUser && disclosurePresentation.items.length > 0
  const citations = !isUser ? buildChatbotCitations(message.toolResult) : []
  const traceBadges = !isUser ? buildChatbotTraceBadges({ traceSteps: message.traceSteps, toolResult: message.toolResult }) : []

  return (
    <div className={`flex ${isUser ? 'justify-end' : 'justify-start'}`}>
      <div className={`flex flex-col gap-1 ${hasDisclosureCards ? 'w-full max-w-[96%]' : 'max-w-[84%]'} ${isUser ? 'items-end' : 'items-start'}`}>
        {!isUser && traceBadges.length > 0 && (
          <TraceBadges badges={traceBadges} />
        )}
        <div
          className={`${hasDisclosureCards ? 'w-full' : 'whitespace-pre-wrap break-words'} rounded-lg px-3 py-2 text-xs leading-5 ${
            isUser
              ? 'bg-blue-600 text-[#ffffff]'
              : 'border border-slate-700/80 bg-[#111827] text-slate-100'
          }`}
        >
          {hasDisclosureCards && !message.isStreaming ? (
            <DisclosureResults presentation={disclosurePresentation} />
          ) : (message.text || (message.isStreaming ? '...' : ''))}
        </div>
        {messageTime && (
          <time className="px-1 text-[10px] font-medium text-slate-500" dateTime={message.createdAt}>
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
                <div key={`${metric.label}-${metricIndex}`} className="grid min-w-0 grid-cols-[minmax(76px,0.8fr)_minmax(0,1.5fr)] gap-2 rounded border border-slate-700/60 bg-slate-950/30 px-2 py-1.5">
                  <dt className="break-words font-bold text-cyan-200">{metric.label}</dt>
                  <dd className="min-w-0 break-words text-slate-100">{metric.value}</dd>
                </div>
              ))}
            </dl>
          ) : null}

          {item.checks.length > 0 ? (
            <dl className="space-y-1">
              {item.checks.map((check, checkIndex) => (
                <div key={`${check.question}-${checkIndex}`} className="grid min-w-0 grid-cols-[minmax(76px,0.8fr)_minmax(0,1.5fr)] gap-2 rounded border border-cyan-950/80 bg-[#07111f]/70 px-2 py-1.5">
                  <dt className="break-words font-bold text-cyan-200">{check.question}</dt>
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

export default function ChatbotWidget({ enabled = true, isLoggedIn = false }) {
  const navigate = useNavigate()
  const [isOpen, setIsOpen] = useState(false)
  const [panelSize, setPanelSize] = useState(getDefaultChatbotSize)
  const [messages, setMessages] = useState(INITIAL_MESSAGES)
  const [input, setInput] = useState('')
  const [isSending, setIsSending] = useState(false)
  const [pendingProposals, setPendingProposals] = useState([])
  const [proposalActionId, setProposalActionId] = useState('')
  const widgetInstanceId = useId()
  const messageIdSequenceRef = useRef(0)
  const proposalActionIdRef = useRef('')
  const inputRef = useRef(null)
  const messagesEndRef = useRef(null)
  const resizeStateRef = useRef(null)

  useEffect(() => {
    if (!enabled || !isOpen) return

    window.requestAnimationFrame(() => {
      messagesEndRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' })
    })
  }, [enabled, isOpen, messages, pendingProposals, isSending])

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

      if (!error && active) setPendingProposals(data || [])

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
            setPendingProposals((items) => mergePendingProposal(items, payload.new))
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
    resizeStateRef.current = null
    setIsOpen(false)
    setPanelSize(getDefaultChatbotSize())
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
      closeChat()
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
      closeChat()
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

  const handleSubmit = (event) => {
    event.preventDefault()
    submitMessage()
  }

  return (
    <>
      {isOpen && (
        <section
          className="fixed bottom-24 right-4 z-40 flex h-[min(560px,calc(100vh-128px))] w-[min(390px,calc(100vw-32px))] flex-col overflow-hidden rounded-lg border border-ai-cyan/35 bg-[#070b14]/95 shadow-[0_18px_60px_rgba(0,0,0,0.45)] backdrop-blur md:right-6 md:h-auto md:w-auto"
          style={{
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
          <header className="flex items-center justify-between border-b border-slate-800 bg-[#0f172a] px-4 py-3">
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
            <button
              type="button"
              onClick={closeChat}
              className="grid h-8 w-8 shrink-0 place-items-center rounded border border-slate-700 text-sm font-bold text-slate-300 transition hover:border-ai-cyan hover:text-ai-cyan"
              aria-label="챗봇 닫기"
            >
              x
            </button>
          </header>

          <div className="flex flex-1 flex-col gap-3 overflow-y-auto px-4 py-4">
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

          <div className="border-t border-slate-800 bg-[#0b1120] p-3">
            {isLoggedIn ? (
              <div className="mb-3 flex flex-wrap gap-2">
                {QUICK_MESSAGES.map((message) => (
                  <button
                    key={message}
                    type="button"
                    onClick={() => submitMessage(message)}
                    disabled={isSending}
                    className="rounded border border-slate-700 px-2.5 py-1.5 text-[11px] font-bold text-slate-300 transition hover:border-ai-cyan hover:text-ai-cyan disabled:opacity-50"
                  >
                    {message}
                  </button>
                ))}
              </div>
            ) : null}
            <form onSubmit={handleSubmit} className="flex items-end gap-2">
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
                placeholder={isLoggedIn ? '메시지를 입력하세요' : '로그인 후 이용 가능합니다'}
                className="min-h-11 flex-1 resize-none rounded border border-slate-700 bg-[#111827] px-3 py-2 text-xs text-slate-100 outline-none transition placeholder:text-slate-500 focus:border-ai-cyan read-only:cursor-pointer read-only:border-ai-cyan/40"
              />
              <button
                type="submit"
                disabled={isLoggedIn ? isSending || !input.trim() : false}
                className="h-11 shrink-0 rounded bg-ai-cyan px-4 text-xs font-bold text-[#07111f] transition hover:brightness-110 disabled:cursor-not-allowed disabled:opacity-50"
              >
                {isLoggedIn ? '전송' : '로그인'}
              </button>
            </form>
          </div>
        </section>
      )}

      <button
        type="button"
        onClick={isOpen ? closeChat : openChat}
        className="fixed bottom-6 right-4 z-40 grid h-16 w-16 place-items-center overflow-hidden rounded-full border-2 border-ai-cyan/70 bg-[#07111f] shadow-[0_0_28px_rgba(0,242,254,0.28)] transition hover:scale-105 hover:border-ai-cyan md:right-6"
        aria-label={isOpen ? '챗봇 닫기' : '챗봇 열기'}
      >
        <img src="/chatbot-bot.png" alt="" className="h-full w-full object-cover object-top" />
      </button>
    </>
  )
}
