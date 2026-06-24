import { useMemo, useState } from 'react'
import Header from '../components/Header.jsx'
import { supabase } from '../supabaseClient'

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:5050'

const presets = {
  stock: {
    title: 'Toss 주식 데이터',
    assetType: 'STOCK',
    exchange: 'TOSS',
    symbols: '005930,NVDA',
    interval: '1d',
    count: 200,
    output: 'ml/data/raw/stock_candles.csv',
  },
  crypto: {
    title: 'Binance 코인 데이터',
    assetType: 'CRYPTO',
    exchange: 'BINANCE',
    symbols: 'BTCUSDT,ETHUSDT',
    interval: '1h',
    count: 500,
    output: 'ml/data/raw/crypto_candles.csv',
  },
}

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
        <div className="md:col-span-2">
          <dt className="text-xs text-slate-500">파일 경로</dt>
          <dd className="break-all font-mono text-white">{result.data.output}</dd>
        </div>
      </dl>
    </div>
  )
}

export default function AdminMlData({ isLoggedIn, userEmail, handleLogout }) {
  const [mode, setMode] = useState('crypto')
  const [form, setForm] = useState(presets.crypto)
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState(null)
  const [error, setError] = useState('')

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
          interval: form.interval,
          count: Number(form.count),
        }),
      })

      const payload = await response.json()
      if (!response.ok || !payload.success) {
        setError(payload.message || 'CSV 생성에 실패했습니다.')
        return
      }

      setResult(payload)
    } catch (requestError) {
      setError(`서버 통신 실패: ${requestError.message}`)
    } finally {
      setLoading(false)
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
                Toss는 저장된 Toss API Key가 필요하고, Binance 캔들은 공개 API로 수집합니다.
              </p>
            </div>
          </div>

          <div className="rounded-lg border border-slate-700/80 bg-slate-surface p-5">
            <h3 className="mb-4 text-sm font-bold uppercase tracking-wider text-white">실행 결과</h3>
            <StatusPanel result={result} error={error} loading={loading} />
          </div>
        </section>
      </main>
    </div>
  )
}
