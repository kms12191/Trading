import { Link } from 'react-router-dom'
import Header from './Header.jsx'
import MobileHeader from './mobile/MobileHeader.jsx'

export default function MemberOnlyNotice({
  isLoggedIn,
  userEmail,
  handleLogout,
  mobileLayout = false,
}) {
  const shellClass = mobileLayout
    ? 'min-h-screen bg-obsidian-bg px-3 py-4 font-inter text-[#e2e2ec]'
    : 'min-h-screen bg-obsidian-bg px-4 py-4 font-inter text-[#e2e2ec] sm:px-6 sm:py-6'
  const contentClass = mobileLayout
    ? 'mx-auto flex min-h-[calc(100dvh-112px)] w-full max-w-md items-center justify-center pb-8'
    : 'mx-auto flex min-h-[calc(100dvh-128px)] w-full max-w-7xl items-center justify-center'

  return (
    <div className={shellClass}>
      {mobileLayout ? (
        <MobileHeader isLoggedIn={isLoggedIn} handleLogout={handleLogout} />
      ) : (
        <Header isLoggedIn={isLoggedIn} userEmail={userEmail} handleLogout={handleLogout} />
      )}

      <main className={contentClass}>
        <section className="w-full max-w-xl rounded-lg border border-ai-cyan/35 bg-[#061321]/95 p-6 text-center shadow-[0_18px_60px_rgba(0,0,0,0.35)] sm:p-8">
          <p className="text-[11px] font-bold uppercase tracking-[0.22em] text-ai-cyan">Member Only</p>
          <h1 className="mt-3 break-words text-2xl font-extrabold leading-tight text-white sm:text-3xl">
            회원만 이용할 수 있는 서비스입니다.
          </h1>
          <div className="mt-6 flex flex-col gap-3 sm:flex-row sm:justify-center">
            <Link
              to="/login"
              className="rounded bg-blue-600 px-5 py-3 text-sm font-bold text-white transition hover:bg-blue-700 active:scale-[0.99]"
            >
              로그인하기
            </Link>
            <Link
              to="/"
              className="rounded border border-slate-700 px-5 py-3 text-sm font-bold text-slate-200 transition hover:border-ai-cyan hover:text-ai-cyan active:scale-[0.99]"
            >
              홈으로 돌아가기
            </Link>
          </div>
        </section>
      </main>
    </div>
  )
}
