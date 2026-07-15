import { useLocation, useNavigate } from 'react-router-dom'
import { preserveMobileDeviceParam } from '../../pages/mobile/mobileRouteUtils.js'

export default function MobileMemberOnlySheet({ onClose, Sheet }) {
  const navigate = useNavigate()
  const location = useLocation()

  return (
    <Sheet title="회원 전용 서비스" subtitle="Member Only" onClose={onClose}>
      <div className="rounded-2xl border border-ai-cyan/25 bg-ai-cyan/10 p-4">
        <p className="text-base font-extrabold leading-6 text-white">
          회원만 이용할 수 있는 서비스입니다.
        </p>
        <button
          type="button"
          onClick={() => {
            onClose()
            navigate(preserveMobileDeviceParam('/login', location.search))
          }}
          className="mt-4 h-11 w-full rounded-xl bg-blue-600 text-sm font-black text-white transition hover:bg-blue-700 active:scale-[0.99]"
        >
          로그인하기
        </button>
      </div>
    </Sheet>
  )
}
