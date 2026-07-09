import { Link, useParams, useSearchParams } from 'react-router-dom'
import Header from '../components/Header.jsx'

const assetTypeLabels = {
  ALL: '전체 종목',
  STOCK: '주식',
  CRYPTO: '코인',
}

export default function SearchNotFound({ isLoggedIn, userEmail, handleLogout }) {
  const { assetType: routeAssetType = '', symbol: routeSymbol = '' } = useParams()
  const [searchParams] = useSearchParams()
  const query = searchParams.get('query') || routeSymbol
  const assetType = String(searchParams.get('assetType') || routeAssetType || 'ALL').toUpperCase()
  const assetTypeLabel = assetTypeLabels[assetType] || '종목'

  return (
    <div className="min-h-screen bg-[#07080c] px-4 py-6 text-[#e2e2ec] sm:px-6 lg:px-8">
      <Header isLoggedIn={isLoggedIn} userEmail={userEmail} handleLogout={handleLogout} />

      <main className="mx-auto flex max-w-4xl flex-col gap-6">
        <section className="rounded-lg border border-slate-700/80 bg-slate-surface p-8 shadow-[0_18px_50px_rgba(0,0,0,0.25)]">
          <div className="flex flex-col gap-6 md:flex-row md:items-center md:justify-between">
            <div className="flex items-start gap-4">
              <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-lg border border-ai-cyan/40 bg-ai-cyan/10 text-ai-cyan">
                <svg viewBox="0 0 24 24" className="h-6 w-6" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                  <circle cx="11" cy="11" r="7" />
                  <path d="m20 20-3.5-3.5" />
                  <path d="M8.5 8.5 13.5 13.5" />
                  <path d="M13.5 8.5 8.5 13.5" />
                </svg>
              </div>

              <div>
                <p className="text-xs font-bold uppercase tracking-[0.24em] text-ai-cyan">No Search Result</p>
                <h1 className="mt-2 text-2xl font-black tracking-tight text-white sm:text-3xl">
                  검색 결과가 없습니다.
                </h1>
                <p className="mt-3 max-w-2xl text-sm leading-6 text-slate-400">
                  입력한 종목명이나 코드가 현재 등록된 {assetTypeLabel} 데이터와 일치하지 않습니다.
                  종목명 또는 코드를 다시 확인해 주세요.
                </p>
              </div>
            </div>

            <Link
              to="/"
              className="inline-flex shrink-0 items-center justify-center rounded border border-blue-600/70 bg-blue-600 px-4 py-2 text-xs font-black text-[#071018] transition-all hover:bg-blue-600"
            >
              홈으로 이동
            </Link>
          </div>

          <div className="mt-8 grid gap-3 rounded-lg border border-slate-800 bg-[#0c0e15] p-4 sm:grid-cols-3">
            <div>
              <p className="text-[10px] font-bold uppercase tracking-widest text-slate-500">검색어</p>
              <p className="mt-1 break-all font-mono text-sm font-bold text-white">{query || '-'}</p>
            </div>
            <div>
              <p className="text-[10px] font-bold uppercase tracking-widest text-slate-500">분류</p>
              <p className="mt-1 text-sm font-bold text-white">{assetTypeLabel}</p>
            </div>
            <div>
              <p className="text-[10px] font-bold uppercase tracking-widest text-slate-500">확인 필요</p>
              <p className="mt-1 text-sm font-bold text-white">종목명 / 코드</p>
            </div>
          </div>
        </section>
      </main>
    </div>
  )
}
