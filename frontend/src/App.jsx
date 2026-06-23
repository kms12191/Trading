import React, { useState, useEffect } from 'react'
import { BrowserRouter as Router, Routes, Route } from 'react-router-dom'
import { supabase } from './supabaseClient'
import Dashboard from './pages/Dashboard'
import Login from './pages/Login'
import Signup from './pages/Signup'
import News from './pages/News'
import Home from './pages/Home'

// 10문항 투자 성향 설문 데이터 정의 (한글 주석 준수)
const SURVEY_QUESTIONS = [
  {
    id: 'q1',
    title: '주식·ETF·코인 등 투자 경험은?',
    options: [
      { text: '없음', score: 1 },
      { text: '1년 미만', score: 2 },
      { text: '1~3년', score: 3 },
      { text: '3~5년', score: 4 },
      { text: '5년 이상', score: 5 }
    ]
  },
  {
    id: 'q2',
    title: '투자하는 가장 큰 이유는?',
    options: [
      { text: '원금 보존', score: 1 },
      { text: '예금보다 높은 수익', score: 2 },
      { text: '적절한 수익 추구', score: 3 },
      { text: '높은 수익 추구', score: 4 },
      { text: '매우 높은 수익 추구', score: 5 }
    ]
  },
  {
    id: 'q3',
    title: '투자금을 언제 사용할 예정인가?',
    options: [
      { text: '1년 이내', score: 1 },
      { text: '1~3년', score: 2 },
      { text: '3~5년', score: 3 },
      { text: '5~10년', score: 4 },
      { text: '10년 이상', score: 5 }
    ]
  },
  {
    id: 'q4',
    title: '투자금이 일시적으로 손실난다면 어느 정도까지 감수할 수 있나요?',
    options: [
      { text: '손실은 절대 안 됨', score: 1 },
      { text: '-5%', score: 2 },
      { text: '-10%', score: 3 },
      { text: '-20%', score: 4 },
      { text: '-30% 이상도 가능', score: 5 }
    ]
  },
  {
    id: 'q5',
    title: '1개월 만에 15% 손실이 발생했다면?',
    options: [
      { text: '즉시 전부 매도한다', score: 1 },
      { text: '일부 매도한다', score: 2 },
      { text: '상황을 지켜본다', score: 3 },
      { text: '추가 매수한다', score: 4 },
      { text: '좋은 기회라고 생각한다', score: 5 }
    ]
  },
  {
    id: 'q6',
    title: '선호하는 투자 상품은?',
    options: [
      { text: '예금·적금', score: 1 },
      { text: '채권', score: 2 },
      { text: 'ETF', score: 3 },
      { text: '개별 주식', score: 4 },
      { text: '코인·레버리지 상품', score: 5 }
    ]
  },
  {
    id: 'q7',
    title: '연간 기대 수익률은?',
    options: [
      { text: '3% 이하', score: 1 },
      { text: '3~5%', score: 2 },
      { text: '5~10%', score: 3 },
      { text: '10~20%', score: 4 },
      { text: '20% 이상', score: 5 }
    ]
  },
  {
    id: 'q8',
    title: '어떤 투자 방식이 가장 마음에 드나요?',
    options: [
      { text: '안전이 가장 중요하다', score: 1 },
      { text: '안정성과 수익의 균형', score: 2 },
      { text: '적절한 위험 감수', score: 3 },
      { text: '높은 수익을 위해 위험 감수', score: 4 },
      { text: '큰 변동성도 감수 가능', score: 5 }
    ]
  },
  {
    id: 'q9',
    title: '현재 보유 자산 중 투자금이 차지하는 비율은?',
    options: [
      { text: '10% 미만', score: 1 },
      { text: '10~30%', score: 2 },
      { text: '30~50%', score: 3 },
      { text: '50~70%', score: 4 },
      { text: '70% 이상', score: 5 }
    ]
  },
  {
    id: 'q10',
    title: '보유 종목이 하루 만에 10% 하락했다면?',
    options: [
      { text: '잠이 안 온다', score: 1 },
      { text: '매우 불안하다', score: 2 },
      { text: '조금 걱정된다', score: 3 },
      { text: '크게 신경 쓰지 않는다', score: 4 },
      { text: '오히려 추가 매수를 고민한다', score: 5 }
    ]
  }
]

// 점수 기반 투자 성향 판정 헬퍼 함수
const getInvestType = (score) => {
  if (score >= 10 && score <= 17) return '안정형'
  if (score >= 18 && score <= 25) return '안정추구형'
  if (score >= 26 && score <= 33) return '위험중립형'
  if (score >= 34 && score <= 41) return '적극투자형'
  if (score >= 42 && score <= 50) return '공격투자형'
  return '미정'
}

export default function App() {
  const [isLoggedIn, setIsLoggedIn] = useState(false)
  const [userEmail, setUserEmail] = useState('')
  const [userId, setUserId] = useState('')
  const [userProfile, setUserProfile] = useState(null) // 유저 프로필 상세 정보 상태 추가
  
  // 1단계: 연락처/닉네임 추가정보 모달 플래그
  const [showAdditionalInfo, setShowAdditionalInfo] = useState(false)
  
  // 2단계: 투자 성향 설문조사 오버레이 플래그
  const [showSurvey, setShowSurvey] = useState(false)

  // 추가 정보 입력 폼 상태
  const [additionalInputs, setAdditionalInputs] = useState({
    nickname: '',
    phone: ''
  })
  const [infoSubmitLoading, setInfoSubmitLoading] = useState(false)

  // 설문조사 상태 관리
  const [currentQuestionIdx, setCurrentQuestionIdx] = useState(0)
  const [surveyAnswers, setSurveyAnswers] = useState({}) // { q1: score, q2: score, ... }
  const [surveyLoading, setSurveyLoading] = useState(false)

  // Supabase 인증 세션 및 프로필 유효성 실시간 동기화 (한글 주석 준수)
  useEffect(() => {
    const checkUserSession = async (session) => {
      if (session) {
        setIsLoggedIn(true)
        setUserEmail(session.user.email)
        setUserId(session.user.id)
        
        try {
          const { data, error } = await supabase
            .from('profiles')
            .select('nickname, phone, invest_type, invest_score') // invest_score 추가 조회
            .eq('id', session.user.id)
            .maybeSingle()

          if (data) {
            setUserProfile(data) // 프로필 상태 보존
          }

          // 1. 닉네임과 전화번호가 없는 경우 ➡️ 추가 정보 등록 모달 강제 노출
          if (!data || !data.nickname || !data.phone) {
            setShowAdditionalInfo(true)
            setAdditionalInputs({
              nickname: data?.nickname || session.user.user_metadata?.full_name || '',
              phone: data?.phone || ''
            })
            setShowSurvey(false)
          } 
          // 2. 추가 정보는 있으나 투자 성향 설문을 안 한 경우 ➡️ 투자 성향 오버레이 강제 노출
          else if (!data.invest_type) {
            setShowAdditionalInfo(false)
            setShowSurvey(true)
          } 
          // 3. 모두 입력 완료된 경우 ➡️ 팝업 해제
          else {
            setShowAdditionalInfo(false)
            setShowSurvey(false)
          }
        } catch (err) {
          console.error('프로필 검증 오류:', err.message)
        }
      } else {
        setIsLoggedIn(false)
        setUserEmail('')
        setUserId('')
        setUserProfile(null)
        setShowAdditionalInfo(false)
        setShowSurvey(false)
      }
    }

    // 초기 세션 확인
    supabase.auth.getSession().then(({ data: { session } }) => {
      checkUserSession(session)
    })

    // 세션 변경 리스너 구독
    const { data: { subscription } } = supabase.auth.onAuthStateChange((_event, session) => {
      checkUserSession(session)
    })

    return () => {
      subscription?.unsubscribe()
    }
  }, [])

  // 로그아웃 수행 (Supabase Auth 연동)
  const handleLogout = async () => {
    try {
      const { error } = await supabase.auth.signOut()
      if (error) throw error
      setIsLoggedIn(false)
      setUserEmail('')
      setUserId('')
      setUserProfile(null)
      setShowAdditionalInfo(false)
      setShowSurvey(false)
      // 설문 데이터 초기화
      setCurrentQuestionIdx(0)
      setSurveyAnswers({})
    } catch (err) {
      console.error('로그아웃 에러:', err.message)
    }
  }

  // 연락처 자동 하이픈 포맷팅
  const handlePhoneFormatChange = (e) => {
    const value = e.target.value.replace(/[^0-9]/g, '')
    let formatted = value
    if (value.length > 3 && value.length <= 7) {
      formatted = `${value.slice(0, 3)}-${value.slice(3)}`
    } else if (value.length > 7) {
      formatted = `${value.slice(0, 3)}-${value.slice(3, 7)}-${value.slice(7, 11)}`
    }
    setAdditionalInputs(prev => ({ ...prev, phone: formatted }))
  }

  // 필수 추가 정보 저장 핸들러
  const handleAdditionalInfoSubmit = async (e) => {
    e.preventDefault()
    if (!additionalInputs.nickname || !additionalInputs.phone) {
      alert('닉네임과 연락처를 모두 입력해주세요.')
      return
    }

    if (additionalInputs.phone.length < 12) {
      alert('올바른 연락처 형식을 입력해주세요 (예: 010-0000-0000).')
      return
    }

    setInfoSubmitLoading(true)
    try {
      const { error } = await supabase
        .from('profiles')
        .update({
          nickname: additionalInputs.nickname,
          phone: additionalInputs.phone,
          updated_at: new Date().toISOString()
        })
        .eq('id', userId)

      if (error) throw error

      setShowAdditionalInfo(false)
      // 추가 정보 입력이 완료되었으니, 투자 성향 진단으로 상태 갱신
      setShowSurvey(true)
    } catch (err) {
      alert(`정보 등록 실패: ${err.message}`)
    } finally {
      setInfoSubmitLoading(false)
    }
  }

  // 설문조사 답안 선택 핸들러
  const handleSurveyOptionClick = (questionId, score) => {
    setSurveyAnswers(prev => ({ ...prev, [questionId]: score }))
    
    // 마지막 질문이 아니라면 0.2초 딜레이 후 부드럽게 다음 질문으로 이동
    if (currentQuestionIdx < SURVEY_QUESTIONS.length - 1) {
      setTimeout(() => {
        setCurrentQuestionIdx(prev => prev + 1)
      }, 200)
    }
  }

  // 설문 결과 최종 제출 핸들러 (Supabase profiles 테이블에 저장)
  const handleSurveySubmit = async () => {
    // 10문항 모두 답했는지 검증
    if (Object.keys(surveyAnswers).length < SURVEY_QUESTIONS.length) {
      alert('모든 질문에 응답을 완료해주세요.')
      return
    }

    setSurveyLoading(true)
    try {
      // 총점 합산
      const totalScore = Object.values(surveyAnswers).reduce((acc, curr) => acc + curr, 0)
      const investType = getInvestType(totalScore)

      const { error } = await supabase
        .from('profiles')
        .update({
          invest_score: totalScore,
          invest_type: investType,
          survey_answers: surveyAnswers,
          updated_at: new Date().toISOString()
        })
        .eq('id', userId)

      if (error) throw error

      alert(`설문 분석 완료! 귀하의 투자 성향은 [${investType}] 입니다.`)
      setShowSurvey(false)
    } catch (err) {
      alert(`설문 제출 실패: ${err.message}`)
    } finally {
      setSurveyLoading(false)
    }
  }

  // 현재 진행 중인 질문 데이터
  const activeQuestion = SURVEY_QUESTIONS[currentQuestionIdx]

  return (
    <Router>
      {/* 1단계: 필수 추가정보 입력 오버레이 모달 (카카오 소셜 가입자 강제 온보딩) */}
      {showAdditionalInfo && (
        <div className="fixed inset-0 bg-[#07080c]/95 backdrop-blur-md flex items-center justify-center z-50 p-4">
          <div className="w-full max-w-md bg-[#0c0e15] border-2 border-ai-cyan/60 rounded-lg p-8 shadow-[0_0_50px_rgba(0,242,254,0.15)] flex flex-col gap-6 relative">
            <div className="flex flex-col gap-2">
              <div className="flex items-center gap-2">
                <span className="material-symbols-outlined text-ai-cyan animate-pulse">lock_person</span>
                <h2 className="text-xl font-bold tracking-wider text-white uppercase">필수 추가정보 등록</h2>
              </div>
              <p className="text-xs text-slate-400">
                카카오 계정 로그인이 성공했습니다. 원활한 실시간 거래 알림(SMS)과 거래 관리를 위해 아래 추가정보를 필수로 등록해주셔야 대시보드 사용이 가능합니다.
              </p>
            </div>

            <form onSubmit={handleAdditionalInfoSubmit} className="flex flex-col gap-4">
              <div className="flex flex-col gap-1.5">
                <label className="text-[10px] font-bold text-slate-400 uppercase tracking-widest">닉네임</label>
                <input 
                  type="text" 
                  value={additionalInputs.nickname}
                  onChange={(e) => setAdditionalInputs(prev => ({ ...prev, nickname: e.target.value }))}
                  placeholder="닉네임 입력" 
                  className="w-full bg-[#11131a] border border-slate-700 text-[#e2e2ec] rounded px-4 py-2.5 text-sm focus:outline-none focus:border-ai-cyan focus:ring-1 focus:ring-ai-cyan transition-all"
                  required
                />
              </div>

              <div className="flex flex-col gap-1.5">
                <label className="text-[10px] font-bold text-slate-400 uppercase tracking-widest">연락처 (휴대폰 번호)</label>
                <input 
                  type="text" 
                  value={additionalInputs.phone}
                  onChange={handlePhoneFormatChange}
                  placeholder="010-0000-0000" 
                  maxLength="13"
                  className="w-full bg-[#11131a] border border-slate-700 text-[#e2e2ec] rounded px-4 py-2.5 text-sm focus:outline-none focus:border-ai-cyan focus:ring-1 focus:ring-ai-cyan transition-all"
                  required
                />
              </div>

              <button 
                type="submit" 
                disabled={infoSubmitLoading}
                className="w-full mt-2 bg-gradient-to-r from-blue-700 to-ai-cyan text-white text-sm font-bold py-3 rounded hover:opacity-90 active:scale-[0.99] transition-all cursor-pointer disabled:opacity-50"
              >
                {infoSubmitLoading ? '등록 중...' : '등록 완료 및 다음 단계 진행'}
              </button>
            </form>

            <div className="border-t border-slate-800 pt-4 flex justify-between items-center text-[10px]">
              <span className="text-slate-500">다른 계정으로 로그인하시겠습니까?</span>
              <button 
                onClick={handleLogout}
                className="text-red-400 hover:underline font-bold bg-transparent border-none cursor-pointer outline-none"
              >
                로그아웃 후 돌아가기
              </button>
            </div>
          </div>
        </div>
      )}

      {/* 2단계: 투자 성향 설문조사 진단 오버레이 (카드형 인터랙티브 UX) */}
      {showSurvey && (
        <div className="fixed inset-0 bg-[#07080c]/95 backdrop-blur-md flex items-center justify-center z-50 p-4">
          <div className="w-full max-w-lg bg-[#0c0e15] border border-ai-cyan/40 rounded-lg p-8 shadow-[0_0_60px_rgba(0,242,254,0.1)] flex flex-col gap-6 relative">
            
            {/* 상단 프로그레스 바 */}
            <div className="flex flex-col gap-2">
              <div className="flex justify-between items-center text-xs">
                <span className="text-ai-cyan font-bold tracking-widest font-mono">INVESTMENT RISK PROFILE</span>
                <span className="text-slate-400 font-mono font-bold">{currentQuestionIdx + 1} / {SURVEY_QUESTIONS.length}</span>
              </div>
              <div className="w-full h-1.5 bg-[#11131a] rounded-full overflow-hidden">
                <div 
                  className="h-full bg-gradient-to-r from-blue-500 to-ai-cyan transition-all duration-300"
                  style={{ width: `${((currentQuestionIdx + 1) / SURVEY_QUESTIONS.length) * 100}%` }}
                ></div>
              </div>
            </div>

            {/* 질문 및 선택지 렌더링 카드 */}
            <div className="flex-1 flex flex-col gap-6 py-4">
              <h3 className="text-lg font-bold text-white tracking-wide min-h-[56px]">
                Q{currentQuestionIdx + 1}. {activeQuestion.title}
              </h3>
              
              <div className="flex flex-col gap-3">
                {activeQuestion.options.map((opt, idx) => {
                  const isSelected = surveyAnswers[activeQuestion.id] === opt.score
                  return (
                    <button
                      key={idx}
                      onClick={() => handleSurveyOptionClick(activeQuestion.id, opt.score)}
                      className={`w-full text-left px-5 py-3.5 rounded text-sm font-semibold transition-all border cursor-pointer ${
                        isSelected 
                          ? 'bg-ai-cyan/10 border-ai-cyan text-ai-cyan shadow-[0_0_15px_rgba(0,242,254,0.1)]' 
                          : 'bg-[#11131a] border-slate-800 text-slate-300 hover:border-slate-700 hover:bg-[#151822]'
                      }`}
                    >
                      <div className="flex items-center gap-3">
                        <span className={`w-5 h-5 rounded-full flex items-center justify-center text-xs font-mono font-bold border ${
                          isSelected ? 'border-ai-cyan bg-ai-cyan text-[#07080c]' : 'border-slate-600 text-slate-500'
                        }`}>
                          {idx + 1}
                        </span>
                        <span>{opt.text}</span>
                      </div>
                    </button>
                  )
                })}
              </div>
            </div>

            {/* 하단 네비게이션 액션 */}
            <div className="flex justify-between items-center border-t border-slate-800 pt-5 mt-2">
              <button
                onClick={() => setCurrentQuestionIdx(prev => Math.max(0, prev - 1))}
                disabled={currentQuestionIdx === 0}
                className="text-xs font-bold text-slate-400 hover:text-slate-200 transition-colors cursor-pointer disabled:opacity-30 disabled:pointer-events-none flex items-center gap-1"
              >
                <span className="material-symbols-outlined text-sm">arrow_back</span>
                이전 질문
              </button>

              {currentQuestionIdx === SURVEY_QUESTIONS.length - 1 ? (
                <button
                  onClick={handleSurveySubmit}
                  disabled={Object.keys(surveyAnswers).length < SURVEY_QUESTIONS.length || surveyLoading}
                  className="bg-gradient-to-r from-blue-700 to-ai-cyan text-white text-xs font-bold px-6 py-2.5 rounded shadow-[0_0_15px_rgba(0,242,254,0.1)] hover:opacity-90 active:scale-[0.98] transition-all cursor-pointer disabled:opacity-50"
                >
                  {surveyLoading ? '성향 분석 중...' : '설문 제출 및 결과 확인'}
                </button>
              ) : (
                <button
                  onClick={() => setCurrentQuestionIdx(prev => Math.min(SURVEY_QUESTIONS.length - 1, prev + 1))}
                  disabled={!surveyAnswers[activeQuestion.id]}
                  className="text-xs font-bold text-ai-cyan hover:text-white transition-colors cursor-pointer disabled:opacity-30 disabled:pointer-events-none flex items-center gap-1"
                >
                  다음 질문
                  <span className="material-symbols-outlined text-sm">arrow_forward</span>
                </button>
              )}
            </div>

            {/* 중도 로그아웃 지원 */}
            <div className="text-center mt-2 border-t border-slate-800/40 pt-4">
              <button 
                onClick={handleLogout}
                className="text-[10px] text-slate-500 hover:text-red-400 transition-colors bg-transparent border-none cursor-pointer outline-none font-bold"
              >
                테스트 중단하고 로그아웃
              </button>
            </div>
          </div>
        </div>
      )}

      <Routes>
        <Route path="/" element={<Home />} />
        <Route 
          path="/dashboard" 
          element={
            <Dashboard 
              isLoggedIn={isLoggedIn} 
              userEmail={userEmail} 
              handleLogout={handleLogout} 
              userProfile={userProfile} 
            />
          } 
        />
        <Route 
          path="/news" 
          element={
            <News 
              isLoggedIn={isLoggedIn} 
              userEmail={userEmail} 
              handleLogout={handleLogout} 
            />
          } 
        />
        <Route path="/login" element={<Login />} />
        <Route path="/signup" element={<Signup />} />
      </Routes>
    </Router>
  )
}
