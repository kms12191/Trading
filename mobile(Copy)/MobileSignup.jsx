import React, { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { supabase } from '../../supabaseClient'

export default function Signup() {
  const navigate = useNavigate()
  const [loading, setLoading] = useState(false)
  const [inputs, setInputs] = useState({
    email: '',
    password: '',
    confirmPassword: '',
    nickname: '',
    phone: ''
  })

  // 휴대폰 번호 입력 시 자동 하이픈 포맷 적용
  const handlePhoneChange = (e) => {
    const value = e.target.value.replace(/[^0-9]/g, '')
    let formatted = value
    if (value.length > 3 && value.length <= 7) {
      formatted = `${value.slice(0, 3)}-${value.slice(3)}`
    } else if (value.length > 7) {
      formatted = `${value.slice(0, 3)}-${value.slice(3, 7)}-${value.slice(7, 11)}`
    }
    setInputs(prev => ({ ...prev, phone: formatted }))
  }

  const handleInputChange = (e) => {
    const { name, value } = e.target
    setInputs(prev => ({ ...prev, [name]: value }))
  }

  // 일반 이메일 회원가입 수행
  const handleSignup = async (e) => {
    e.preventDefault()

    if (inputs.password !== inputs.confirmPassword) {
      alert('비밀번호가 일치하지 않습니다.')
      return
    }

    if (inputs.phone.length < 12) {
      alert('올바른 휴대폰 번호를 입력해주세요.')
      return
    }

    setLoading(true)
    try {
      // Supabase Auth SignUp 호출 (메타데이터에 nickname과 phone 포함)
      const { data, error } = await supabase.auth.signUp({
        email: inputs.email,
        password: inputs.password,
        options: {
          data: {
            nickname: inputs.nickname,
            phone: inputs.phone
          }
        }
      })

      if (error) throw error

      alert('회원가입이 완료되었습니다! 로그인 페이지로 이동합니다.')
      navigate('/login')
    } catch (err) {
      alert(`회원가입 실패: ${err.message}`)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="bg-[#11131a] text-[#e2e2ec] min-h-screen flex overflow-hidden font-inter relative">
      {/* 좌측 패널: 가입 폼 */}
      <div className="w-full lg:w-5/12 flex flex-col justify-center px-6 py-10 bg-[#0c0e15] z-10 shadow-[8px_0_24px_rgba(0,0,0,0.5)] overflow-y-auto">
        <div className="max-w-md w-full mx-auto my-auto">
          {/* 브랜드 헤더 */}
          <div className="mb-8">
            <div className="flex items-center gap-3 mb-2">
              <img src="/logo.png" alt="Logo" className="w-8 h-8 object-contain" />
              <h1 className="text-xl font-bold tracking-wider text-primary">SYNTHETIC TERMINAL</h1>
            </div>
            <p className="text-sm text-slate-400">새로운 기관급 AI 트레이딩 계정을 생성합니다.</p>
          </div>
          
          <form onSubmit={handleSignup} className="flex flex-col gap-4">
            {/* 이메일 */}
            <div className="flex flex-col gap-1.5">
              <label className="text-[11px] font-bold text-slate-400 uppercase tracking-wider">이메일 주소</label>
              <input 
                className="w-full bg-[#11131a] border border-slate-700 text-[#e2e2ec] rounded px-4 py-2.5 text-sm focus:outline-none focus:border-primary focus:ring-1 focus:ring-primary transition-all" 
                name="email"
                type="email" 
                value={inputs.email}
                onChange={handleInputChange}
                placeholder="user@institution.com" 
                required 
              />
            </div>
            
            {/* 닉네임 */}
            <div className="flex flex-col gap-1.5">
              <label className="text-[11px] font-bold text-slate-400 uppercase tracking-wider">사용자 닉네임</label>
              <input 
                className="w-full bg-[#11131a] border border-slate-700 text-[#e2e2ec] rounded px-4 py-2.5 text-sm focus:outline-none focus:border-primary focus:ring-1 focus:ring-primary transition-all" 
                name="nickname"
                type="text" 
                value={inputs.nickname}
                onChange={handleInputChange}
                placeholder="홍길동" 
                required 
              />
            </div>

            {/* 연락처 */}
            <div className="flex flex-col gap-1.5">
              <label className="text-[11px] font-bold text-slate-400 uppercase tracking-wider">연락처 (휴대폰 번호)</label>
              <input 
                className="w-full bg-[#11131a] border border-slate-700 text-[#e2e2ec] rounded px-4 py-2.5 text-sm focus:outline-none focus:border-primary focus:ring-1 focus:ring-primary transition-all" 
                name="phone"
                type="text" 
                value={inputs.phone}
                onChange={handlePhoneChange}
                placeholder="010-0000-0000" 
                maxLength="13"
                required 
              />
            </div>

            {/* 비밀번호 */}
            <div className="flex flex-col gap-1.5">
              <label className="text-[11px] font-bold text-slate-400 uppercase tracking-wider">비밀번호</label>
              <input 
                className="w-full bg-[#11131a] border border-slate-700 text-[#e2e2ec] rounded px-4 py-2.5 text-sm focus:outline-none focus:border-primary focus:ring-1 focus:ring-primary transition-all" 
                name="password"
                type="password" 
                value={inputs.password}
                onChange={handleInputChange}
                placeholder="••••••••" 
                required 
              />
            </div>

            {/* 비밀번호 확인 */}
            <div className="flex flex-col gap-1.5">
              <label className="text-[11px] font-bold text-slate-400 uppercase tracking-wider">비밀번호 확인</label>
              <input 
                className="w-full bg-[#11131a] border border-slate-700 text-[#e2e2ec] rounded px-4 py-2.5 text-sm focus:outline-none focus:border-primary focus:ring-1 focus:ring-primary transition-all" 
                name="confirmPassword"
                type="password" 
                value={inputs.confirmPassword}
                onChange={handleInputChange}
                placeholder="••••••••" 
                required 
              />
            </div>
            
            <button 
              className="mt-4 w-full bg-primary text-white text-sm font-bold py-3 rounded hover:bg-blue-600 transition-colors cursor-pointer disabled:opacity-50" 
              type="submit"
              disabled={loading}
            >
              {loading ? '가입 처리 중...' : '계정 만들기'}
            </button>
          </form>
          
          {/* 가입 안내 및 로그인으로 복귀 */}
          <p className="mt-6 text-center text-xs text-slate-400">
            이미 계정이 있으신가요?{" "}
            <button 
              onClick={() => navigate('/login')}
              className="text-primary font-bold hover:text-ai-cyan transition-colors bg-transparent border-none cursor-pointer outline-none"
            >
              로그인하기
            </button>
          </p>
          <div className="mt-4 text-center">
            <button 
              onClick={() => navigate('/dashboard')}
              className="text-xs text-slate-500 hover:text-slate-300 transition-colors underline cursor-pointer"
            >
              ← 대시보드로 돌아가기
            </button>
          </div>
        </div>
      </div>

      {/* 우측 패널: 배경 이미지 및 상태 카드 */}
      <div className="hidden lg:block lg:w-7/12 relative bg-[#1d1f27] overflow-hidden">
        <div className="absolute inset-0 bg-gradient-to-r from-[#0c0e15] to-transparent z-10 w-32"></div>
        <div 
          className="absolute inset-0 w-full h-full bg-cover bg-center opacity-40 mix-blend-screen animate-[spin_180s_linear_infinite] scale-[1.1]" 
          style={{ backgroundImage: "url('https://lh3.googleusercontent.com/aida-public/AB6AXuApLxgfDjYyQecXJZuWNXU9Ga_b7gYY3LPueCaxOazI8GjN9-RO0LWVrVv7c7sp6cBStFrPAWkr9-CSXMBCaIeUFGuwrKINONZTSbMklhQNkkUqTXSVcQctVEG5h3WMCb5gEGhygwwyk54ai7IDnqpk6FWQ7Zub8IV6OpayDku7z1TcG4f-c6Fb2k28tAyhbifVOFUdg195Z1r9H5Hra-t3ZQcY33i0X-18iU3i-igI384E5nJdCSKyMVw6WkLYNHbGZxsBTIJ3mTE')" }}
        ></div>
      </div>
    </div>
  )
}
