import { useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { supabase } from '../supabaseClient'
import { setBrowserTab } from '../lib/browserTab.js'
import { SplineScene } from '@/components/ui/splite'
import { Spotlight } from '@/components/ui/spotlight'

export default function Login() {
  const navigate = useNavigate()

  useEffect(() => {
    return setBrowserTab({ title: 'ANTRY - 로그인' })
  }, [])

  useEffect(() => {
    supabase.auth.getSession().then(({ data: { session } }) => {
      if (session) navigate('/')
    })
  }, [navigate])

  const handleKakaoLogin = async () => {
    try {
      const { error } = await supabase.auth.signInWithOAuth({
        provider: 'kakao',
        options: {
          redirectTo: `${window.location.origin}/`,
          queryParams: {
            scope: 'account_email',
            prompt: 'login',
          },
        },
      })
      if (error) throw error
    } catch (error) {
      alert(`카카오 로그인 실패: ${error.message}`)
    }
  }

  return (
    <div className="bg-black text-[#e2e2ec] min-h-screen flex overflow-hidden font-inter relative">
      {/* 좌측 패널: 로그인 폼 */}
      <div className="w-full lg:w-5/12 flex flex-col justify-center px-6 py-10 bg-black z-10 shadow-[8px_0_24px_rgba(0,0,0,0.5)]">
        <div className="mx-auto w-full max-w-md">
          <div className="mb-12">
            <div className="mb-2 flex items-center gap-3">
              <img src="/logo.png" alt="Logo" className="h-8 w-8 object-contain" />
              <h1 className="text-xl font-bold tracking-wider text-primary">ANTRY</h1>
            </div>
            <p className="text-sm text-slate-400">ANTRY에 오신 것을 환영합니다.</p>
          </div>

          <button
            className="flex w-full items-center justify-center gap-3 rounded bg-[#FEE500] py-3 text-sm font-semibold text-[#191919] shadow-sm transition-colors hover:bg-[#FADA0A]"
            type="button"
            onClick={handleKakaoLogin}
          >
            <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="18" height="30" className="h-[30px] w-[18px]">
              <path fill="#191919" d="M12 3c-4.97 0-9 3.185-9 7.11 0 2.507 1.657 4.702 4.14 5.86l-.81 2.977c-.086.315.228.583.513.395l3.522-2.31c.214.025.43.038.647.038 4.97 0 9-3.186 9-7.11C21 6.185 16.97 3 12 3z" />
            </svg>
            <span>카카오 로그인</span>
          </button>

          <div className="mt-6 text-center">
            <button
              type="button"
              onClick={() => navigate('/')}
              className="text-xs text-slate-500 underline transition-colors hover:text-slate-300"
            >
              ← 홈으로 돌아가기
            </button>
          </div>
        </div>
      </div>

      {/* 우측 패널: 3D SplineScene 및 Spotlight */}
      <div className="hidden lg:block lg:w-7/12 relative bg-black overflow-hidden select-none">
        {/* 블렌딩을 위한 오버레이 그라디언트 */}
        <div className="absolute inset-0 bg-gradient-to-r from-black to-transparent z-10 w-32 pointer-events-none"></div>
        
        {/* Spotlight 마우스 트래킹 - z-index를 올려 3D 캔버스 위에 렌더링되도록 함 */}
        <Spotlight
          className="-top-40 left-0 md:left-60 md:-top-20 z-10"
          size={400}
        />

        {/* Spline Canvas - z-0 레이어로 밑바탕에 깔림 */}
        <div className="w-full h-full relative z-0">
          <SplineScene 
            scene="https://prod.spline.design/kZDDjO5HuC9GJUM2/scene.splinecode"
            className="w-full h-full"
          />
        </div>
      </div>
    </div>
  )
}
