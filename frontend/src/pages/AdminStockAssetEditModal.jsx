export default function AdminStockAssetEditModal({ editingStock, setEditingStock, saveStockAsset, stockActionLoading }) {
  if (!editingStock) return null

  const updateField = (field, value) => {
    setEditingStock((current) => ({ ...current, [field]: value }))
  }

  return (
    <div className="fixed inset-0 z-[80] flex items-center justify-center bg-black/60 px-4 backdrop-blur-sm">
      <div className="w-full max-w-2xl rounded-lg border border-slate-700 bg-[#0f172a] p-5 shadow-2xl">
        <div className="flex items-start justify-between gap-4">
          <div>
            <p className="text-[10px] font-bold uppercase tracking-[0.16em] text-ai-cyan">Stock Edit</p>
            <h3 className="mt-2 text-lg font-black text-white">{editingStock.symbol} 종목 설정</h3>
          </div>
          <button type="button" onClick={() => setEditingStock(null)} className="rounded border border-slate-700 px-3 py-1.5 text-xs font-bold text-slate-300 hover:text-white">
            닫기
          </button>
        </div>

        <div className="mt-5 grid gap-3 sm:grid-cols-2">
          <label className="text-xs font-bold text-slate-300">
            기본 종목명
            <input value={editingStock.name || ''} onChange={(event) => updateField('name', event.target.value)} className="mt-1 w-full rounded border border-slate-700 bg-[#0b1020] px-3 py-2 text-white outline-none focus:border-ai-cyan" />
          </label>
          <label className="text-xs font-bold text-slate-300">
            화면 표시명 (한글명)
            <input value={editingStock.display_name || ''} onChange={(event) => updateField('display_name', event.target.value)} className="mt-1 w-full rounded border border-slate-700 bg-[#0b1020] px-3 py-2 text-white outline-none focus:border-ai-cyan" />
          </label>
          <label className="text-xs font-bold text-slate-300">
            시장 구분 (KOSPI · KOSDAQ 등)
            <input value={editingStock.market_segment || ''} onChange={(event) => updateField('market_segment', event.target.value)} className="mt-1 w-full rounded border border-slate-700 bg-[#0b1020] px-3 py-2 font-mono text-white outline-none focus:border-ai-cyan" />
          </label>
        </div>

        <div className="mt-4">
          <label className="flex items-center gap-2 rounded border border-slate-800 bg-[#0b1020] px-3 py-2.5 text-xs font-bold text-slate-300">
            <input type="checkbox" checked={Boolean(editingStock.is_active)} onChange={(event) => updateField('is_active', event.target.checked)} />
            종목 활성화 (거래소 노출 및 챗봇 추천 활성화)
          </label>
        </div>

        <div className="mt-6 flex justify-end gap-2">
          <button type="button" onClick={() => setEditingStock(null)} className="rounded border border-slate-700 px-4 py-2 text-xs font-bold text-slate-300 hover:text-white">
            취소
          </button>
          <button type="button" onClick={saveStockAsset} disabled={stockActionLoading} className="rounded bg-blue-600 px-4 py-2 text-xs font-bold text-white transition hover:bg-blue-700 active:scale-95 disabled:opacity-60">
            {stockActionLoading ? '저장 중...' : '저장'}
          </button>
        </div>
      </div>
    </div>
  )
}
