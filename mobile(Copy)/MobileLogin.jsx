import React, { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { supabase } from '../../supabaseClient'

export default function Login() {
  const navigate = useNavigate()
  
  // 로그인 폼 입력값
  const [loginInputs, setLoginInputs] = useState({
    email: '',
    password: '',
    rememberMe: false
  })

  // 세션 감지하여 이미 로그인되어 있으면 대시보드로 리다이렉트
  useEffect(() => {
    supabase.auth.getSession().then(({ data: { session } }) => {
      if (session) {
        navigate('/')
      }
    })
  }, [navigate])

  const handleLoginInputChange = (e) => {
    const { name, value, type, checked } = e.target
    setLoginInputs(prev => ({
      ...prev,
      [name]: type === 'checkbox' ? checked : value
    }))
  }

  // 카카오 로그인 수행 (Supabase Auth OAuth 연동)
  const handleKakaoLogin = async () => {
    try {
      const { error } = await supabase.auth.signInWithOAuth({
        provider: 'kakao',
        options: {
          redirectTo: `${window.location.origin}/`,
          queryParams: {
            scope: 'account_email', // 프로필 이미지를 배제하고 이메일 권한만 요청
            prompt: 'login' // 카카오 기존 세션이 있어도 로그인/계정 선택 화면을 다시 표시
          }
        }
      })
      if (error) throw error
    } catch (err) {
      alert(`카카오 로그인 실패: ${err.message}`)
    }
  }

  return (
    <div className="bg-[#11131a] text-[#e2e2ec] min-h-screen flex overflow-hidden font-inter relative">
      {/* 좌측 패널: 로그인 폼 */}
      <div className="w-full lg:w-5/12 flex flex-col justify-center px-6 py-10 bg-[#0c0e15] z-10 shadow-[8px_0_24px_rgba(0,0,0,0.5)]">
        <div className="max-w-md w-full mx-auto">
          {/* 브랜드 헤더 */}
          <div className="mb-12">
            <div className="flex items-center gap-3 mb-2">
              <img src="/logo.png" alt="Logo" className="w-8 h-8 object-contain" />
              <h1 className="text-xl font-bold tracking-wider text-primary">SYNTHETIC TERMINAL</h1>
            </div>
            <p className="text-sm text-slate-400">기관급 데이터 및 AI 분석 플랫폼에 오신 것을 환영합니다.</p>
          </div>  
          
          {/* 소셜 로그인 버튼 (Kakao 브랜드 규격 가이드라인 적용 및 Supabase 연동, 구글 로그인 삭제) */}
          <div className="flex flex-col gap-3">
            {/* Kakao 로그인 버튼 */}
            <button 
              className="w-full flex items-center justify-center gap-3 bg-[#FEE500] border border-transparent text-[#191919] py-2.5 rounded hover:bg-[#FADA0A] text-sm font-semibold transition-colors cursor-pointer shadow-sm" 
              type="button"
              onClick={handleKakaoLogin}
            >
              <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="18" height="30" className="w-[18px] h-[30px]">
                <path fill="#191919" d="M12 3c-4.97 0-9 3.185-9 7.11 0 2.507 1.657 4.702 4.14 5.86l-.81 2.977c-.086.315.228.583.513.395l3.522-2.31c.214.025.43.038.647.038 4.97 0 9-3.186 9-7.11C21 6.185 16.97 3 12 3z"/>
              </svg>
              <span>카카오 로그인</span>
            </button>
          </div>
          
          {/* 돌아가기 */}          
          <div className="mt-6 text-center">
            <button 
              onClick={() => navigate('/')}
              className="text-xs text-slate-500 hover:text-slate-300 transition-colors underline cursor-pointer"
            >
              ← 홈으로 돌아가기
            </button>
          </div>
        </div>
      </div>

      {/* 우측 패널: 배경 이미지 및 상태 카드 */}
      <div className="hidden lg:block lg:w-7/12 relative bg-[#1d1f27] overflow-hidden">
        {/* 블렌딩을 위한 오버레이 그라디언트 */}
        <div className="absolute inset-0 bg-gradient-to-r from-[#0c0e15] to-transparent z-10 w-32"></div>
        <div 
          className="absolute inset-0 w-full h-full bg-cover bg-center opacity-40 mix-blend-screen animate-[spin_180s_linear_infinite] scale-[1.1]" 
          style={{ backgroundImage: "url('https://lh3.googleusercontent.com/aida-public/AB6AXuApLxgfDjYyQecXJZuWNXU9Ga_b7gYY3LPueCaxOazI8GjN9-RO0LWVrVv7c7sp6cBStFrPAWkr9-CSXMBCaIeUFGuwrKINONZTSbMklhQNkkUqTXSVcQctVEG5h3WMCb5gEGhygwwyk54ai7IDnqpk6FWQ7Zub8IV6OpayDku7z1TcG4f-c6Fb2k28tAyhbifVOFUdg195Z1r9H5Hra-t3ZQcY33i0X-18iU3i-igI384E5nJdCSKyMVw6WkLYNHbGZxsBTIJ3mTE')" }}
        ></div>
        
        {/* 글래스모피즘 스타일의 시스템 상태 카드 */}
        <div className="absolute bottom-20 right-20 z-20 backdrop-blur-xl bg-ai-cyan/5 border border-slate-700/50 p-6 rounded-lg max-w-sm">
          <div className="flex items-center gap-2 mb-3">
            <span className="material-symbols-outlined text-ai-cyan">auto_awesome</span>
            <span className="text-[11px] font-bold text-ai-cyan uppercase tracking-wider">System Status</span>
          </div>
          <p className="font-mono text-xs text-white mb-1">Neural Node Synch: Optimal</p>
          <p className="font-mono text-[11px] text-slate-400">Latency: 12ms | Encryption: AES-256-GCM</p>
        </div>
      </div>

      {/* 하단 푸터 */}
      <footer className="absolute bottom-0 w-full flex justify-between items-center px-6 py-4 z-20 text-[10px] text-slate-500">
        <div>
          © 2026 Synthetic Intelligence Terminal. All rights reserved.
        </div>
        <div className="flex gap-4">
          <a className="hover:text-ai-cyan transition-colors" href="#">Security</a>
          <a className="hover:text-ai-cyan transition-colors" href="#">Privacy Policy</a>
          <a className="hover:text-ai-cyan transition-colors" href="#">Terms of Service</a>
        </div>
      </footer>
    </div>
  )
}
