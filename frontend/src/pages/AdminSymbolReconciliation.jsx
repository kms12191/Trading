import { useEffect, useMemo, useState } from 'react'
import { supabase } from '../supabaseClient'
import { buildApiErrorText } from '../lib/apiError.js'

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:5050'

const STATUS_LABELS = {
  ALL: '전체',
  NORMAL: '정상',
  SUSPICIOUS: '의심',
  DEACTIVATION_CANDIDATE: '비활성 예정',
  INACTIVE: '비활성',
  DELETABLE: '삭제 가능',
}

const STATUS_STYLES = {
  NORMAL: 'border-emerald-500/30 bg-emerald-500/10 text-emerald-200',
  SUSPICIOUS: 'border-amber-500/30 bg-amber-500/10 text-amber-200',
  DEACTIVATION_CANDIDATE: 'border-orange-500/30 bg-orange-500/10 text-orange-200',
  INACTIVE: 'border-slate-500/40 bg-slate-700/40 text-slate-200',
  DELETABLE: 'border-red-500/30 bg-red-500/10 text-red-200',
}

function formatDate(value) {
  if (!value) return '-'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return '-'
  return date.toLocaleString()
}

function SummaryCard({ label, value }) {
  return (
    <div className="rounded border border-slate-800 bg-[#0f172a] p-4">
      <p className="text-[10px] font-bold uppercase tracking-[0.16em] text-slate-500">{label}</p>
      <p className="mt-2 text-xl font-black text-white">{Number(value || 0).toLocaleString()}</p>
    </div>
  )
}

export default function AdminSymbolReconciliation() {
  const [run, setRun] = useState(null)
  const [items, setItems] = useState([])
  const [statusFilter, setStatusFilter] = useState('ALL')
  const [selected, setSelected] = useState({})
  const [loading, setLoading] = useState(false)
  const [actionLoading, setActionLoading] = useState('')
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')
  const [deleteConfirm, setDeleteConfirm] = useState(null)

  const authHeaders = async () => {
    const { data } = await supabase.auth.getSession()
    const token = data?.session?.access_token
    if (!token) throw new Error('로그인이 필요합니다.')
    return { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' }
  }

  const loadLatest = async () => {
    setLoading(true)
    setError('')
    try {
      const headers = await authHeaders()
      const response = await fetch(`${API_BASE_URL}/api/admin/market-symbols/reconciliation/latest`, { headers })
      const payload = await response.json().catch(() => ({}))
      if (!response.ok || payload.success === false) {
        throw new Error(buildApiErrorText(payload, '종목 정리 결과를 불러오지 못했습니다.'))
      }
      setRun(payload.data?.run || null)
      setItems(payload.data?.items || [])
      setSelected({})
    } catch (requestError) {
      setError(requestError.message || '종목 정리 결과를 불러오지 못했습니다.')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadLatest()
  }, [])

  const filteredItems = useMemo(() => {
    if (statusFilter === 'ALL') return items
    return items.filter((item) => item.status === statusFilter)
  }, [items, statusFilter])

  const selectedRows = useMemo(
    () => items.filter((item) => selected[`${item.source_table}:${item.symbol}`]),
    [items, selected],
  )

  const selectedSymbols = selectedRows.map((item) => item.symbol)

  const runScan = async () => {
    setActionLoading('scan')
    setError('')
    setMessage('')
    try {
      const headers = await authHeaders()
      const response = await fetch(`${API_BASE_URL}/api/admin/market-symbols/reconcile`, {
        method: 'POST',
        headers,
        body: JSON.stringify({ market_country: 'ALL', limit: 1000 }),
      })
      const payload = await response.json().catch(() => ({}))
      if (!response.ok || payload.success === false) {
        throw new Error(buildApiErrorText(payload, '종목 스캔에 실패했습니다.'))
      }
      setRun(payload.data?.run || null)
      setItems(payload.data?.items || [])
      setSelected({})
      setMessage('종목 마스터 스캔을 완료했습니다.')
    } catch (requestError) {
      setError(requestError.message || '종목 스캔에 실패했습니다.')
    } finally {
      setActionLoading('')
    }
  }

  const runAction = async (action, sourceTable) => {
    if (selectedSymbols.length === 0) {
      setError('처리할 종목을 선택해 주세요.')
      return
    }
    setActionLoading(action)
    setError('')
    setMessage('')
    try {
      const headers = await authHeaders()
      const response = await fetch(`${API_BASE_URL}/api/admin/market-symbols/${action}`, {
        method: 'POST',
        headers,
        body: JSON.stringify({
          symbols: selectedSymbols,
          source_table: sourceTable,
          reason: '관리자 종목 마스터 정리',
        }),
      })
      const payload = await response.json().catch(() => ({}))
      if (!response.ok || payload.success === false) {
        throw new Error(buildApiErrorText(payload, '종목 작업에 실패했습니다.'))
      }
      setMessage('선택한 종목 작업을 완료했습니다.')
      await loadLatest()
    } catch (requestError) {
      setError(requestError.message || '종목 작업에 실패했습니다.')
    } finally {
      setActionLoading('')
    }
  }

  const requestDeleteAction = (sourceTable) => {
    if (selectedSymbols.length === 0) {
      setError('삭제할 종목을 선택해 주세요.')
      return
    }
    setDeleteConfirm({ sourceTable, symbols: selectedSymbols })
  }

  const confirmDeleteAction = async () => {
    if (!deleteConfirm) return
    const sourceTable = deleteConfirm.sourceTable
    setDeleteConfirm(null)
    await runAction('delete', sourceTable)
  }

  const toggleRow = (item) => {
    const key = `${item.source_table}:${item.symbol}`
    setSelected((current) => ({ ...current, [key]: !current[key] }))
  }

  return (
    <section className="flex flex-col gap-5">
      <div className="ai-glass rounded-lg p-5">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
          <div>
            <p className="text-[10px] font-bold uppercase tracking-[0.16em] text-ai-cyan">Symbol Reconciliation</p>
            <h2 className="mt-2 text-2xl font-bold text-white">종목 정리</h2>
            <p className="mt-2 text-sm leading-6 text-slate-400">
              임시코드, 오래된 캐시, 비활성 후보를 점검하고 관리자 승인으로 정리합니다.
            </p>
          </div>
          <button
            type="button"
            onClick={runScan}
            disabled={actionLoading === 'scan'}
            className="rounded bg-blue-600 px-4 py-2 text-xs font-black text-[#ffffff] transition hover:bg-blue-700 active:scale-95"
          >
            {actionLoading === 'scan' ? '스캔 중...' : '스캔 실행'}
          </button>
        </div>
      </div>

      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-5">
        <SummaryCard label="전체 검사" value={run?.checked_count} />
        <SummaryCard label="정상" value={run?.normal_count} />
        <SummaryCard label="의심" value={run?.suspicious_count} />
        <SummaryCard label="비활성 예정" value={run?.deactivation_candidate_count} />
        <SummaryCard label="삭제 가능" value={run?.deletable_count} />
      </div>

      <div className="rounded border border-slate-800 bg-[#0f172a] p-4">
        <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
          <div className="flex flex-wrap gap-2">
            {Object.entries(STATUS_LABELS).map(([status, label]) => (
              <button
                key={status}
                type="button"
                onClick={() => setStatusFilter(status)}
                className={`rounded px-3 py-1.5 text-xs font-bold transition ${
                  statusFilter === status ? 'bg-ai-cyan text-[#07111f]' : 'bg-slate-800 text-slate-300 hover:bg-slate-700'
                }`}
              >
                {label}
              </button>
            ))}
          </div>
          <div className="flex flex-wrap gap-2">
            <button type="button" onClick={() => runAction('deactivate')} className="rounded border border-orange-500/40 px-3 py-1.5 text-xs font-bold text-orange-200 hover:bg-orange-500/10">
              선택 비활성화
            </button>
            <button type="button" onClick={() => requestDeleteAction('kis_stock_turnover_latest')} className="rounded border border-red-500/40 px-3 py-1.5 text-xs font-bold text-red-200 hover:bg-red-500/10">
              캐시 삭제
            </button>
            <button type="button" onClick={() => runAction('restore')} className="rounded border border-emerald-500/40 px-3 py-1.5 text-xs font-bold text-emerald-200 hover:bg-emerald-500/10">
              선택 복구
            </button>
          </div>
        </div>

        <div className="mt-3 flex flex-wrap gap-3 text-xs text-slate-500">
          <span>선택 {selectedRows.length}개</span>
          <span>최근 스캔 {formatDate(run?.started_at)}</span>
          <span>상태 {run?.status || '-'}</span>
        </div>

        {message ? <p className="mt-3 rounded border border-emerald-500/30 bg-emerald-500/10 px-3 py-2 text-xs text-emerald-200">{message}</p> : null}
        {error ? <p className="mt-3 rounded border border-red-500/30 bg-red-500/10 px-3 py-2 text-xs text-red-200">{error}</p> : null}
      </div>

      <div className="overflow-x-auto rounded border border-slate-800 bg-[#0b1020]">
        <table className="min-w-[1100px] w-full text-left text-xs">
          <thead className="bg-slate-900/80 text-slate-500">
            <tr>
              <th className="px-3 py-3">선택</th>
              <th className="px-3 py-3">심볼</th>
              <th className="px-3 py-3">종목명</th>
              <th className="px-3 py-3">시장</th>
              <th className="px-3 py-3">원천</th>
              <th className="px-3 py-3">상태</th>
              <th className="px-3 py-3">사유</th>
              <th className="px-3 py-3">참조</th>
              <th className="px-3 py-3">권장</th>
              <th className="px-3 py-3">마지막 갱신</th>
            </tr>
          </thead>
          <tbody>
            {filteredItems.map((item) => {
              const key = `${item.source_table}:${item.symbol}`
              return (
                <tr key={key} className="border-t border-slate-800/80 text-slate-300">
                  <td className="px-3 py-3">
                    <input type="checkbox" checked={Boolean(selected[key])} onChange={() => toggleRow(item)} />
                  </td>
                  <td className="px-3 py-3 font-mono font-bold text-white">{item.symbol}</td>
                  <td className="px-3 py-3">{item.name || '-'}</td>
                  <td className="px-3 py-3">{item.market_country || '-'} / {item.market_segment || '-'}</td>
                  <td className="px-3 py-3 font-mono text-slate-400">{item.source_table}</td>
                  <td className="px-3 py-3">
                    <span className={`rounded border px-2 py-1 text-[10px] font-bold ${STATUS_STYLES[item.status] || 'border-slate-700 text-slate-300'}`}>
                      {STATUS_LABELS[item.status] || item.status}
                    </span>
                  </td>
                  <td className="max-w-xs px-3 py-3 leading-5">{item.reason || '-'}</td>
                  <td className="px-3 py-3">{Number(item.reference_count || 0).toLocaleString()}</td>
                  <td className="px-3 py-3 font-mono text-slate-400">{item.suggested_action || '-'}</td>
                  <td className="px-3 py-3">{formatDate(item.last_seen_at)}</td>
                </tr>
              )
            })}
          </tbody>
        </table>
        {!loading && filteredItems.length === 0 ? (
          <p className="px-4 py-8 text-center text-sm text-slate-500">표시할 스캔 결과가 없습니다.</p>
        ) : null}
        {loading ? <p className="px-4 py-8 text-center text-sm text-slate-500">스캔 결과를 불러오는 중입니다...</p> : null}
      </div>

      {deleteConfirm ? (
        <div className="fixed inset-0 z-[80] flex items-center justify-center bg-black/60 px-4 backdrop-blur-sm">
          <div className="w-full max-w-sm rounded-lg border border-red-500/30 bg-[#0f172a] p-5 shadow-2xl">
            <p className="text-[10px] font-bold uppercase tracking-[0.16em] text-red-300">삭제 확인</p>
            <h3 className="mt-2 text-lg font-black text-white">선택한 종목을 삭제하시겠습니까?</h3>
            <p className="mt-3 text-sm leading-6 text-slate-300">
              선택한 {deleteConfirm.symbols.length}개 종목의 캐시 데이터를 삭제합니다. 서버에서 참조 여부를 다시 확인하며,
              참조가 있는 종목은 삭제되지 않습니다.
            </p>
            <div className="mt-5 flex justify-end gap-2">
              <button
                type="button"
                onClick={() => setDeleteConfirm(null)}
                className="rounded border border-slate-700 px-4 py-2 text-xs font-bold text-slate-300 transition hover:border-slate-500 hover:text-white"
              >
                취소
              </button>
              <button
                type="button"
                onClick={confirmDeleteAction}
                disabled={actionLoading === 'delete'}
                className="rounded bg-red-500 px-4 py-2 text-xs font-black text-white transition hover:bg-red-400 disabled:opacity-60"
              >
                삭제
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </section>
  )
}
