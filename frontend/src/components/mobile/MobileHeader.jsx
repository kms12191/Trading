import { Link, useNavigate } from 'react-router-dom'

export default function MobileHeader({ isLoggedIn, handleLogout }) {
  const navigate = useNavigate()

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
    <header className="mx-auto mb-4 flex w-full max-w-md items-center justify-between gap-3">
      <Link to="/" className="flex shrink-0 items-center gap-2 no-underline">
        <img src="/logo.png" alt="ANTRY" className="h-9 w-9 object-contain" />
        <span className="text-xl font-extrabold tracking-tight text-white">ANTRY</span>
      </Link>
      {isLoggedIn ? (
        <div className="flex min-w-0 items-center gap-2 rounded-full border border-slate-800 bg-[#061321]/90 px-2 py-1">
          {chatbotButton}
          <button
            type="button"
            onClick={handleLogout}
            className="rounded-full border border-slate-700 bg-[#0f172a] px-3 py-1 text-[11px] font-black text-slate-300 transition active:bg-red-950/30 active:text-red-300"
          >
            LOGOUT
          </button>
        </div>
      ) : (
        <div className="flex min-w-0 items-center gap-2 rounded-full border border-slate-800 bg-[#061321]/90 px-2 py-1">
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
  )
}
