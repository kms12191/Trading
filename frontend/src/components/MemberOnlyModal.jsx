import { Link } from 'react-router-dom'

export default function MemberOnlyModal({
  message,
  loginTo = '/login',
  onClose,
}) {
  if (!message) return null

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-[#07080c]/70 px-4 backdrop-blur-sm">
      <section
        role="dialog"
        aria-modal="true"
        aria-labelledby="member-only-title"
        className="w-full max-w-sm rounded-lg border border-ai-cyan/45 bg-[#061321] p-6 text-center shadow-[0_22px_70px_rgba(0,0,0,0.55)]"
      >
        <p className="text-[10px] font-bold uppercase tracking-[0.2em] text-ai-cyan">Member Only</p>
        <h2 id="member-only-title" className="mt-3 break-keep text-xl font-extrabold leading-7 text-white">
          {message}
        </h2>
        <div className="mt-5 grid grid-cols-2 gap-2">
          <button
            type="button"
            onClick={onClose}
            className="h-10 rounded border border-slate-700 text-sm font-bold text-slate-300 transition hover:border-ai-cyan hover:text-ai-cyan"
          >
            닫기
          </button>
          <Link
            to={loginTo}
            className="grid h-10 place-items-center rounded bg-blue-600 text-sm font-bold text-white transition hover:bg-blue-700 active:scale-[0.99]"
          >
            로그인
          </Link>
        </div>
      </section>
    </div>
  )
}
