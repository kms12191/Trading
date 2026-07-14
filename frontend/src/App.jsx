import { useEffect, useState } from 'react'
import { BrowserRouter as Router, Navigate, Route, Routes } from 'react-router-dom'
import { supabase } from './supabaseClient'
import Dashboard from './pages/Dashboard'
import Login from './pages/Login'
import Signup from './pages/Signup'
import News from './pages/News'
import Inquiry from './pages/Inquiry'
import Settings from './pages/Settings'
import Home from './pages/Home'
import MarketRankings from './pages/MarketRankings'
import AdminMlData from './pages/AdminMlData'
import AssetDetail from './pages/AssetDetail'
import SearchNotFound from './pages/SearchNotFound'
import InvestmentSurveyModal from './components/InvestmentSurveyModal'
import { INQUIRY_ROUTES } from './dashboardConstants.js'
import ChatbotWidget from './features/chatbot/ChatbotWidget.jsx'
import useDeviceType from './hooks/useDeviceType.js'
import MobileRoutes from './routes/MobileRoutes.jsx'

function AppShell({
  isLoggedIn,
  userEmail,
  userId,
  userProfile,
  setUserProfile,
  showAdditionalInfo,
  setShowAdditionalInfo,
  showSurvey,
  setShowSurvey,
  additionalInputs,
  setAdditionalInputs,
  infoSubmitLoading,
  setInfoSubmitLoading,
  handleLogout,
}) {
  const { isMobileDevice } = useDeviceType()

  const handlePhoneFormatChange = (e) => {
    const value = e.target.value.replace(/[^0-9]/g, '')
    let formatted = value
    if (value.length > 3 && value.length <= 7) {
      formatted = `${value.slice(0, 3)}-${value.slice(3)}`
    } else if (value.length > 7) {
      formatted = `${value.slice(0, 3)}-${value.slice(3, 7)}-${value.slice(7, 11)}`
    }
    setAdditionalInputs((prev) => ({ ...prev, phone: formatted }))
  }

  const handleAdditionalInfoSubmit = async (e) => {
    e.preventDefault()
    if (!additionalInputs.nickname || !additionalInputs.phone) {
      alert('닉네임과 연락처를 모두 입력해주세요.')
      return
    }

    if (additionalInputs.phone.length < 12) {
      alert('올바른 연락처 형식을 입력해주세요. 예: 010-0000-0000')
      return
    }

    setInfoSubmitLoading(true)
    try {
      const { error } = await supabase
        .from('profiles')
        .update({
          nickname: additionalInputs.nickname,
          phone: additionalInputs.phone,
          updated_at: new Date().toISOString(),
        })
        .eq('id', userId)

      if (error) throw error

      setShowAdditionalInfo(false)
      setShowSurvey(true)
    } catch (err) {
      alert(`정보 등록 실패: ${err.message}`)
    } finally {
      setInfoSubmitLoading(false)
    }
  }

  const protectedInquiryElement = isLoggedIn ? (
    <Inquiry
      isLoggedIn={isLoggedIn}
      userEmail={userEmail}
      handleLogout={handleLogout}
    />
  ) : (
    <Navigate to="/login" replace />
  )

  return (
    <>
      {showAdditionalInfo && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-[#07080c]/95 p-4 backdrop-blur-md">
          <div className="relative flex w-full max-w-md flex-col gap-6 rounded-lg border-2 border-ai-cyan/60 bg-[#0c0e15] p-8 shadow-[0_0_50px_rgba(0,242,254,0.15)]">
            <div className="flex flex-col gap-2">
              <div className="flex items-center gap-2">
                <span className="material-symbols-outlined animate-pulse text-ai-cyan">lock_person</span>
                <h2 className="text-xl font-bold uppercase tracking-wider text-white">필수 추가정보 등록</h2>
              </div>
              <p className="text-xs text-slate-400">
                카카오 계정 로그인은 완료되었습니다. 실시간 거래 알림과 거래 관리를 위해 아래 정보를 등록해야 대시보드를 사용할 수 있습니다.
              </p>
            </div>

            <form onSubmit={handleAdditionalInfoSubmit} className="flex flex-col gap-4">
              <div className="flex flex-col gap-1.5">
                <label className="text-[10px] font-bold uppercase tracking-widest text-slate-400">닉네임</label>
                <input
                  type="text"
                  value={additionalInputs.nickname}
                  onChange={(e) => setAdditionalInputs((prev) => ({ ...prev, nickname: e.target.value }))}
                  placeholder="닉네임 입력"
                  className="w-full rounded border border-slate-700 bg-[#11131a] px-4 py-2.5 text-sm text-[#e2e2ec] transition-all focus:border-ai-cyan focus:outline-none focus:ring-1 focus:ring-ai-cyan"
                  required
                />
              </div>

              <div className="flex flex-col gap-1.5">
                <label className="text-[10px] font-bold uppercase tracking-widest text-slate-400">연락처</label>
                <input
                  type="text"
                  value={additionalInputs.phone}
                  onChange={handlePhoneFormatChange}
                  placeholder="010-0000-0000"
                  maxLength="13"
                  className="w-full rounded border border-slate-700 bg-[#11131a] px-4 py-2.5 text-sm text-[#e2e2ec] transition-all focus:border-ai-cyan focus:outline-none focus:ring-1 focus:ring-ai-cyan"
                  required
                />
              </div>

              <button
                type="submit"
                disabled={infoSubmitLoading}
                className="mt-2 w-full cursor-pointer rounded bg-gradient-to-r from-blue-700 to-ai-cyan py-3 text-sm font-bold text-white transition-all hover:opacity-90 active:scale-[0.99] disabled:opacity-50"
              >
                {infoSubmitLoading ? '등록 중...' : '등록 완료 및 다음 단계 진행'}
              </button>
            </form>

            <div className="flex items-center justify-between border-t border-slate-800 pt-4 text-[10px]">
              <span className="text-slate-500">다른 계정으로 로그인하시겠습니까?</span>
              <button
                onClick={handleLogout}
                className="cursor-pointer border-none bg-transparent font-bold text-red-400 outline-none hover:underline"
              >
                로그아웃 후 돌아가기
              </button>
            </div>
          </div>
        </div>
      )}

      {showSurvey && (
        <InvestmentSurveyModal
          isMandatory={true}
          onLogout={handleLogout}
          onSuccess={(type, score) => {
            setUserProfile((prev) => (
              prev
                ? {
                    ...prev,
                    invest_type: type,
                    invest_score: score,
                    updated_at: new Date().toISOString(),
                  }
                : null
            ))
            setShowSurvey(false)
          }}
        />
      )}

      {isMobileDevice ? (
        <MobileRoutes
          isLoggedIn={isLoggedIn}
          userEmail={userEmail}
          handleLogout={handleLogout}
          userProfile={userProfile}
          setUserProfile={setUserProfile}
        />
      ) : (
      <div>
        <Routes>
          <Route
            path="/"
            element={(
              <Home
                isLoggedIn={isLoggedIn}
                userEmail={userEmail}
                handleLogout={handleLogout}
              />
            )}
          />
          <Route
            path="/dashboard"
            element={(
              <Dashboard
                isLoggedIn={isLoggedIn}
                userEmail={userEmail}
                handleLogout={handleLogout}
                userProfile={userProfile}
                setUserProfile={setUserProfile}
              />
            )}
          />
          <Route
            path="/market-rankings"
            element={(
              <MarketRankings
                isLoggedIn={isLoggedIn}
                userEmail={userEmail}
                handleLogout={handleLogout}
              />
            )}
          />
          <Route
            path="/news"
            element={(
              <News
                isLoggedIn={isLoggedIn}
                userEmail={userEmail}
                handleLogout={handleLogout}
              />
            )}
          />
          {Object.values(INQUIRY_ROUTES).map((path) => (
            <Route key={path} path={path} element={protectedInquiryElement} />
          ))}
          <Route
            path="/settings"
            element={(
              <Settings
                isLoggedIn={isLoggedIn}
                userEmail={userEmail}
                handleLogout={handleLogout}
                userProfile={userProfile}
                setUserProfile={setUserProfile}
              />
            )}
          />
          <Route
            path="/admin/ml-data"
            element={(
              <AdminMlData
                isLoggedIn={isLoggedIn}
                userEmail={userEmail}
                handleLogout={handleLogout}
              />
            )}
          />
          <Route path="/login" element={<Login />} />
          <Route path="/signup" element={<Signup />} />
          <Route
            path="/asset/:assetType"
            element={(
              <SearchNotFound
                isLoggedIn={isLoggedIn}
                userEmail={userEmail}
                handleLogout={handleLogout}
              />
            )}
          />
          <Route
            path="/asset/:assetType/:symbol"
            element={(
              <AssetDetail
                isLoggedIn={isLoggedIn}
                userEmail={userEmail}
                handleLogout={handleLogout}
                userProfile={userProfile}
              />
            )}
          />
          <Route
            path="/search/not-found"
            element={(
              <SearchNotFound
                isLoggedIn={isLoggedIn}
                userEmail={userEmail}
                handleLogout={handleLogout}
              />
            )}
          />
        </Routes>
      </div>
      )}

      <ChatbotWidget enabled={!isMobileDevice && !showAdditionalInfo && !showSurvey} isLoggedIn={isLoggedIn} />

    </>
  )
}

export default function App() {
  const [isLoggedIn, setIsLoggedIn] = useState(false)
  const [userEmail, setUserEmail] = useState('')
  const [userId, setUserId] = useState('')
  const [userProfile, setUserProfile] = useState(null)
  const [showAdditionalInfo, setShowAdditionalInfo] = useState(false)
  const [showSurvey, setShowSurvey] = useState(false)
  const [additionalInputs, setAdditionalInputs] = useState({
    nickname: '',
    phone: '',
  })
  const [infoSubmitLoading, setInfoSubmitLoading] = useState(false)

  useEffect(() => {
    const clearHash = () => {
      if (window.location.href.includes('#')) {
        window.history.replaceState(
          null,
          document.title,
          window.location.pathname + window.location.search
        )
      }
    }

    clearHash()

    const checkUserSession = async (session) => {
      if (session) {
        setIsLoggedIn(true)
        setUserEmail(session.user.email)
        setUserId(session.user.id)

        // OAuth 로그인 후 주소창의 # 해시 잔재물 제거 (비동기 타이밍 대응)
        setTimeout(clearHash, 100)

        try {
          const { data } = await supabase
            .from('profiles')
            .select('nickname, phone, role, invest_type, invest_score, updated_at')
            .eq('id', session.user.id)
            .maybeSingle()

          if (data) {
            setUserProfile(data)
          }

          if (!data || !data.nickname || !data.phone) {
            setShowAdditionalInfo(true)
            setAdditionalInputs({
              nickname: data?.nickname || session.user.user_metadata?.full_name || '',
              phone: data?.phone || '',
            })
            setShowSurvey(false)
          } else if (!data.invest_type) {
            setShowAdditionalInfo(false)
            setShowSurvey(true)
          } else {
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

    supabase.auth.getSession().then(({ data: { session } }) => {
      checkUserSession(session)
    })

    const {
      data: { subscription },
    } = supabase.auth.onAuthStateChange((_event, session) => {
      checkUserSession(session)
    })

    return () => {
      subscription?.unsubscribe()
    }
  }, [])

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
    } catch (err) {
      console.error('로그아웃 오류:', err.message)
    }
  }

  return (
    <Router>
      <AppShell
        isLoggedIn={isLoggedIn}
        userEmail={userEmail}
        userId={userId}
        userProfile={userProfile}
        setUserProfile={setUserProfile}
        showAdditionalInfo={showAdditionalInfo}
        setShowAdditionalInfo={setShowAdditionalInfo}
        showSurvey={showSurvey}
        setShowSurvey={setShowSurvey}
        additionalInputs={additionalInputs}
        setAdditionalInputs={setAdditionalInputs}
        infoSubmitLoading={infoSubmitLoading}
        setInfoSubmitLoading={setInfoSubmitLoading}
        handleLogout={handleLogout}
      />
    </Router>
  )
}
