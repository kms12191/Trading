import { useCallback, useEffect, useState } from 'react'
import { buildApiErrorText } from '../lib/apiError.js'
import AdminCryptoAssetEditModal from './AdminCryptoAssetEditModal.jsx'
import { buildCryptoEditorState } from './adminCryptoAssetModel.js'

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:5050'

const EXCHANGE_LABELS = {
  COINONE: '코인원',
  BINANCE: '바이낸스',
  BINANCE_UM_FUTURES: '바이낸스 선물',
}

function formatDate(value) {
  if (!value) return '-'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return '-'
  return date.toLocaleString()
}

function CryptoAssetStatus({ item, exchange }) {
  const isCoinone = exchange === 'COINONE'
  const listed = isCoinone ? item.coinone_listed : item.binance_listed
  const tradable = isCoinone ? item.coinone_tradable : item.binance_tradable

  return (
    <>
      <span className={listed ? 'text-emerald-200' : 'text-slate-500'}>{listed ? '상장' : '미상장'}</span>
      <span className="mx-1 text-slate-600">/</span>
      <span className={tradable ? 'text-emerald-200' : 'text-amber-200'}>{tradable ? '거래 가능' : '거래 제한'}</span>
      {isCoinone ? (
        <div className="mt-1 text-[10px] text-slate-500">
          입금 {item.coinone_deposit_status || '-'} · 출금 {item.coinone_withdraw_status || '-'}
        </div>
      ) : (
        <div className="mt-1 font-mono text-[10px] text-slate-500">{item.binance_symbol || '-'}</div>
      )}
    </>
  )
}

export default function AdminCryptoAssetsPanel({ authHeaders }) {
  const [cryptoItems, setCryptoItems] = useState([])
  const [cryptoLoading, setCryptoLoading] = useState(false)
  const [cryptoActionLoading, setCryptoActionLoading] = useState('')
  const [cryptoMessage, setCryptoMessage] = useState('')
  const [cryptoError, setCryptoError] = useState('')
  const [cryptoQuery, setCryptoQuery] = useState('')
  const [editingCrypto, setEditingCrypto] = useState(null)
  const [visibleCount, setVisibleCount] = useState(10)

  const loadCryptoAssets = useCallback(async () => {
    setCryptoLoading(true)
    setCryptoError('')
    try {
      const headers = await authHeaders()
      const params = new URLSearchParams({ limit: '300' })
      if (cryptoQuery.trim()) {
        params.set('query', cryptoQuery.trim())
      }
      const response = await fetch(`${API_BASE_URL}/api/admin/crypto-symbols?${params.toString()}`, { headers })
      const payload = await response.json().catch(() => ({}))
      if (!response.ok || payload.success === false) {
        throw new Error(buildApiErrorText(payload, '코인 종목 마스터를 불러오지 못했습니다.'))
      }
      setCryptoItems(payload.data?.items || [])
      setVisibleCount(10)
    } catch (requestError) {
      setCryptoError(requestError.message || '코인 종목 마스터를 불러오지 못했습니다.')
    } finally {
      setCryptoLoading(false)
    }
  }, [authHeaders, cryptoQuery])

  useEffect(() => {
    const timeoutId = window.setTimeout(loadCryptoAssets, 0)
    return () => window.clearTimeout(timeoutId)
  }, [loadCryptoAssets])

  const syncCryptoAssets = async () => {
    setCryptoActionLoading('sync')
    setCryptoError('')
    setCryptoMessage('')
    try {
      const headers = await authHeaders()
      const response = await fetch(`${API_BASE_URL}/api/admin/crypto-symbols/sync`, { method: 'POST', headers })
      const payload = await response.json().catch(() => ({}))
      if (!response.ok || payload.success === false) {
        throw new Error(buildApiErrorText(payload, '코인 종목 동기화에 실패했습니다.'))
      }
      const syncedCount = Number(payload.data?.synced_count || 0).toLocaleString()
      setCryptoMessage(`코인 종목 ${syncedCount}개를 동기화했습니다.`)
      await loadCryptoAssets()
    } catch (requestError) {
      setCryptoError(requestError.message || '코인 종목 동기화에 실패했습니다.')
    } finally {
      setCryptoActionLoading('')
    }
  }

  const saveCryptoAsset = async () => {
    if (!editingCrypto?.base_symbol) return
    setCryptoActionLoading(`save:${editingCrypto.base_symbol}`)
    setCryptoError('')
    setCryptoMessage('')
    try {
      const headers = await authHeaders()
      const response = await fetch(`${API_BASE_URL}/api/admin/crypto-symbols/${encodeURIComponent(editingCrypto.base_symbol)}`, {
        method: 'PATCH',
        headers,
        body: JSON.stringify({
          display_name_ko: editingCrypto.display_name_ko,
          display_name_en: editingCrypto.display_name_en,
          aliases: editingCrypto.aliases,
          default_exchange: editingCrypto.default_exchange,
          is_visible: editingCrypto.is_visible,
          admin_trading_blocked: editingCrypto.admin_trading_blocked,
          admin_block_reason: editingCrypto.admin_block_reason,
          admin_note: editingCrypto.admin_note,
          coinone_symbol: editingCrypto.coinone_symbol,
          binance_symbol: editingCrypto.binance_symbol,
        }),
      })
      const payload = await response.json().catch(() => ({}))
      if (!response.ok || payload.success === false) {
        throw new Error(buildApiErrorText(payload, '코인 종목 수정에 실패했습니다.'))
      }
      setCryptoMessage(`${editingCrypto.base_symbol} 종목 설정을 저장했습니다.`)
      setEditingCrypto(null)
      await loadCryptoAssets()
    } catch (requestError) {
      setCryptoError(requestError.message || '코인 종목 수정에 실패했습니다.')
    } finally {
      setCryptoActionLoading('')
    }
  }

  return (
    <div className="ai-glass rounded-lg p-5">
      <div className="flex flex-col gap-4 xl:flex-row xl:items-end xl:justify-between">
        <div>
          <p className="text-[10px] font-bold uppercase tracking-[0.16em] text-ai-cyan">Crypto Asset Management</p>
          <h2 className="mt-2 text-2xl font-bold text-white">코인 종목 관리</h2>
          <p className="mt-2 text-sm leading-6 text-slate-400">코인원과 바이낸스 상장 상태 및 기본 거래소, 거래 차단 여부를 제어합니다.</p>
        </div>
        <div className="flex flex-col gap-2 sm:flex-row">
          <input type="search" value={cryptoQuery} onChange={(event) => setCryptoQuery(event.target.value)} placeholder="H · Humanity · ALICE" className="rounded border border-slate-700 bg-[#0f172a] px-3 py-2 text-xs text-white outline-none focus:border-ai-cyan" />
          <button type="button" onClick={loadCryptoAssets} disabled={cryptoLoading} className="rounded border border-slate-700 px-4 py-2 text-xs font-bold text-slate-200 transition hover:border-ai-cyan hover:text-white disabled:opacity-60">
            조회
          </button>
          <button type="button" onClick={syncCryptoAssets} disabled={cryptoActionLoading === 'sync'} className="rounded bg-blue-600 px-4 py-2 text-xs font-black text-white transition hover:bg-blue-700 disabled:opacity-60">
            {cryptoActionLoading === 'sync' ? '동기화 중...' : '코인원/바이낸스 동기화'}
          </button>
        </div>
      </div>

      {cryptoMessage ? <p className="mt-3 rounded border border-emerald-500/30 bg-emerald-500/10 px-3 py-2 text-xs text-emerald-200">{cryptoMessage}</p> : null}
      {cryptoError ? <p className="mt-3 rounded border border-red-500/30 bg-red-500/10 px-3 py-2 text-xs text-red-200">{cryptoError}</p> : null}

      <div className="mt-4 overflow-x-auto rounded border border-slate-800 bg-[#0b1020]">
        <table className="min-w-[1200px] w-full text-left text-xs">
          <thead className="bg-slate-900/80 text-slate-500">
            <tr>
              <th className="px-3 py-3">심볼</th>
              <th className="px-3 py-3">표시명</th>
              <th className="px-3 py-3">기본 거래소</th>
              <th className="px-3 py-3">코인원</th>
              <th className="px-3 py-3">바이낸스</th>
              <th className="px-3 py-3">관리 차단</th>
              <th className="px-3 py-3">동기화</th>
              <th className="px-3 py-3">관리</th>
            </tr>
          </thead>
          <tbody>
            {cryptoItems.slice(0, visibleCount).map((item) => (
              <tr key={item.base_symbol} className="border-t border-slate-800/80 text-slate-300">
                <td className="px-3 py-3 font-mono font-bold text-white">{item.base_symbol}</td>
                <td className="px-3 py-3">
                  <div className="font-bold text-white">{item.display_name_ko || item.display_name_en || item.base_symbol}</div>
                  <div className="mt-1 font-mono text-[10px] text-slate-500">{item.display_name_en || '-'}</div>
                </td>
                <td className="px-3 py-3">{EXCHANGE_LABELS[item.default_exchange] || item.default_exchange || '-'}</td>
                <td className="px-3 py-3"><CryptoAssetStatus item={item} exchange="COINONE" /></td>
                <td className="px-3 py-3"><CryptoAssetStatus item={item} exchange="BINANCE" /></td>
                <td className="px-3 py-3">
                  {item.admin_trading_blocked ? (
                    <span className="rounded border border-red-500/40 bg-red-500/10 px-2 py-1 text-[10px] font-bold text-red-200">차단</span>
                  ) : (
                    <span className="rounded border border-emerald-500/30 bg-emerald-500/10 px-2 py-1 text-[10px] font-bold text-emerald-200">허용</span>
                  )}
                  {item.admin_block_reason ? <div className="mt-1 max-w-xs text-[10px] text-slate-500">{item.admin_block_reason}</div> : null}
                </td>
                <td className="px-3 py-3">{formatDate(item.last_synced_at)}</td>
                <td className="px-3 py-3">
                  <button type="button" onClick={() => setEditingCrypto(buildCryptoEditorState(item))} className="rounded border border-slate-700 px-3 py-1.5 text-[10px] font-bold text-slate-200 hover:border-ai-cyan hover:text-white">
                    수정
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {!cryptoLoading && cryptoItems.length === 0 ? <p className="px-4 py-8 text-center text-sm text-slate-500">표시할 코인 종목이 없습니다.</p> : null}
        {cryptoLoading ? <p className="px-4 py-8 text-center text-sm text-slate-500">코인 종목을 불러오는 중입니다...</p> : null}
      </div>

      {visibleCount < cryptoItems.length && (
        <div className="mt-4 flex justify-center">
          <button type="button" onClick={() => setVisibleCount((prev) => prev + 10)} className="rounded border border-slate-700 bg-slate-800/40 px-6 py-2.5 text-xs font-bold text-slate-300 transition hover:border-ai-cyan hover:text-white active:scale-95">
            더보기 ({visibleCount} / {cryptoItems.length})
          </button>
        </div>
      )}

      <AdminCryptoAssetEditModal editingCrypto={editingCrypto} setEditingCrypto={setEditingCrypto} saveCryptoAsset={saveCryptoAsset} cryptoActionLoading={cryptoActionLoading} />
    </div>
  )
}
