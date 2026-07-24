import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'

export default function MobileHeader({ isLoggedIn, handleLogout }) {
  const navigate = useNavigate()
  const [showLogoutConfirm, setShowLogoutConfirm] = useState(false)

  const openChatbot = () => {
    navigate('/chatbot')
  }

  const chatbotButton = (
    <button
      type="button"
      onClick={openChatbot}
      className="grid h-8 w-8 place-items-center rounded-full border border-ai-cyan/40 bg-ai-cyan/10 text-ai-cyan transition active:bg-ai-cyan/20"
      aria-label="Open chatbot"
    >
      <svg
        className="h-[19px] w-[19px]"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth="2"
        aria-hidden="true"
      >
        <path
          strokeLinecap="round"
          strokeLinejoin="round"
          d="M6.25 6.5h9.5a3.25 3.25 0 0 1 3.25 3.25v3.5a3.25 3.25 0 0 1-3.25 3.25h-4.2l-3.15 2.75v-2.75H6.25A3.25 3.25 0 0 1 3 13.25v-3.5A3.25 3.25 0 0 1 6.25 6.5Z"
        />
        <path strokeLinecap="round" strokeLinejoin="round" d="M3 11.2H1.75v2.6H3" />
        <path strokeLinecap="round" strokeLinejoin="round" d="M19 11.2h1.25v2.6H19" />
        <path strokeLinecap="round" strokeLinejoin="round" d="M17.4 16.1v1.15c0 1.05-.75 1.95-1.78 2.14l-2.22.41" />
        <path strokeLinecap="round" strokeLinejoin="round" d="M7.5 11.7h.01M11 11.7h.01M14.5 11.7h.01" />
      </svg>
    </button>
  )

  return (
    <>
      <header className="mx-auto mb-4 flex w-full max-w-md items-center justify-between gap-3">
        <Link to="/" className="flex shrink-0 items-center gap-2 no-underline">
          <img src="/logo.png" alt="ANTRY" className="h-9 w-9 object-contain" />
          <span className="text-xl font-extrabold tracking-tight text-white">ANTRY</span>
        </Link>
        {isLoggedIn ? (
          <div className="flex min-w-0 items-center gap-3 rounded-full border border-slate-800 bg-[#061321]/90 px-2 py-1">
            {chatbotButton}
            <button
              type="button"
              onClick={() => setShowLogoutConfirm(true)}
              className="rounded-full border border-slate-700 bg-[#0f172a] px-3 py-1 text-[11px] font-black text-slate-300 transition active:bg-red-950/30 active:text-red-300"
            >
              LOGOUT
            </button>
          </div>
        ) : (
          <div className="flex min-w-0 items-center gap-3 rounded-full border border-slate-800 bg-[#061321]/90 px-2 py-1">
            {chatbotButton}
            <Link
              to="/login"
              className="rounded-full border border-ai-cyan/70 bg-ai-cyan/10 px-4 py-2 text-xs font-black text-ai-cyan no-underline transition active:bg-ai-cyan/20"
            >
              LOGIN
            </Link>
          </div>
        )}
      </header>

      {showLogoutConfirm ? (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-[#020817]/75 px-4 backdrop-blur-md">
          <div className="w-full max-w-sm rounded-[24px] border border-slate-700/80 bg-[#07111f] p-5 text-center shadow-[0_24px_80px_rgba(0,0,0,0.55)]">
            <div className="mx-auto grid h-12 w-12 place-items-center rounded-full border border-ai-cyan/30 bg-ai-cyan/10 text-ai-cyan">
              <span className="material-symbols-outlined text-[24px] leading-none">logout</span>
            </div>
            <p className="mt-4 text-lg font-black text-white">로그아웃 하시겠습니까?</p>
            <p className="mt-2 text-sm font-medium leading-6 text-slate-400">
              현재 계정에서 나가려면 네를 눌러주세요.
            </p>
            <div className="mt-6 grid grid-cols-2 gap-3">
              <button
                type="button"
                className="h-12 rounded-2xl border border-slate-700 bg-slate-900/80 px-4 text-sm font-extrabold text-slate-200 transition hover:-translate-y-0.5 hover:border-ai-cyan hover:bg-ai-cyan hover:text-slate-950 hover:shadow-[0_16px_36px_rgba(34,211,238,0.34)] active:scale-[0.98] active:bg-cyan-300"
                onClick={() => setShowLogoutConfirm(false)}
              >
                아니요
              </button>
              <button
                type="button"
                className="h-12 rounded-2xl border border-slate-700 bg-slate-900/80 px-4 text-sm font-extrabold text-slate-200 transition hover:-translate-y-0.5 hover:border-ai-cyan hover:bg-ai-cyan hover:text-slate-950 hover:shadow-[0_16px_36px_rgba(34,211,238,0.34)] active:scale-[0.98] active:bg-cyan-300"
                onClick={() => {
                  setShowLogoutConfirm(false)
                  handleLogout?.()
                }}
              >
                네
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </>
  )
}
