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
      <span className="material-symbols-outlined text-[18px] leading-none">chat_bubble</span>
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
                className="h-12 rounded-2xl border border-slate-700 bg-slate-900/80 px-4 text-sm font-extrabold text-slate-200 transition active:scale-[0.98] active:bg-slate-800"
                onClick={() => setShowLogoutConfirm(false)}
              >
                아니요
              </button>
              <button
                type="button"
                className="h-12 rounded-2xl bg-ai-cyan px-4 text-sm font-extrabold text-slate-950 shadow-[0_12px_30px_rgba(34,211,238,0.24)] transition active:scale-[0.98] active:bg-cyan-300"
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
