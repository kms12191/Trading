import { useEffect } from 'react'
import { Navigate, Route, Routes, useLocation } from 'react-router-dom'
import MobileHome from '../pages/mobile/MobileHome.jsx'
import MobileDashboard from '../pages/mobile/MobileDashboard.jsx'
import MobileNews from '../pages/mobile/MobileNews.jsx'
import MobileSettings from '../pages/mobile/MobileSettings.jsx'
import MobileLogin from '../pages/mobile/MobileLogin.jsx'
import MobileInquiry from '../pages/mobile/MobileInquiry.jsx'
import MobileMarketRankings from '../pages/mobile/MobileMarketRankings.jsx'
import MobileAdminMlData from '../pages/mobile/MobileAdminMlData.jsx'
import MobileAdminAiFundDashboard from '../pages/mobile/MobileAdminAiFundDashboard.jsx'
import MobileAssetDetail from '../pages/mobile/MobileAssetDetail.jsx'
import MobileSearchNotFound from '../pages/mobile/MobileSearchNotFound.jsx'
import MobileChatbot from '../pages/mobile/MobileChatbot.jsx'
import { INQUIRY_ROUTES } from '../dashboardConstants.js'
import MobileBottomNavigation from '../components/mobile/MobileBottomNavigation.jsx'
import MobileHeader from '../components/mobile/MobileHeader.jsx'
import MemberOnlyNotice from '../components/MemberOnlyNotice.jsx'

function AdminProtectedRoute({ isLoggedIn, userProfile, children }) {
  const hasAccess = isLoggedIn && userProfile?.role === 'ADMIN'

  useEffect(() => {
    if (!isLoggedIn || (userProfile && userProfile.role !== 'ADMIN')) {
      alert('관리자 권한이 없습니다.')
    }
  }, [isLoggedIn, userProfile])

  if (isLoggedIn && !userProfile) {
    return (
      <div className="min-h-screen bg-[#07080c] flex items-center justify-center text-slate-400 text-xs">
        권한 확인 중...
      </div>
    )
  }

  if (!hasAccess) {
    return <Navigate to="/dashboard" replace />
  }

  return children
}

export default function MobileRoutes({
  isLoggedIn,
  authReady = true,
  userEmail,
  handleLogout,
  userProfile,
  setUserProfile,
}) {
  const location = useLocation()
  const isChatbotRoute = location.pathname === '/chatbot'

  const protectedInquiryElement = !authReady ? (
    <div className="min-h-screen bg-obsidian-bg flex items-center justify-center text-xs font-bold text-slate-400">
      인증 상태 확인 중...
    </div>
  ) : isLoggedIn ? (
    <div className="min-h-screen bg-obsidian-bg px-3 py-4 font-inter text-[#e2e2ec]">
      <MobileHeader isLoggedIn={isLoggedIn} handleLogout={handleLogout} />
      <MobileInquiry
        isLoggedIn={isLoggedIn}
        userEmail={userEmail}
        handleLogout={handleLogout}
        hideHeader
        mobileLayout
      />
    </div>
  ) : (
    <Navigate to="/login" replace />
  )
  const memberOnlyNoticeElement = (
    <MemberOnlyNotice
      isLoggedIn={isLoggedIn}
      userEmail={userEmail}
      handleLogout={handleLogout}
      mobileLayout
    />
  )

  return (
    // 전체 모바일 화면의 바깥 배경
    <div className="mobile-input-zoom-guard min-h-screen bg-obsidian-bg">
      {/*
        실제 모바일 화면 영역
        max-w-[430px] 때문에 PC 브라우저에서도 모바일처럼 좁게 보임
        mx-auto 때문에 가운데 정렬됨
        pb-24는 하단 모바일 네비게이션에 내용이 가리지 않도록 여백 추가
      */}
      <div className={`mx-auto min-h-screen w-full max-w-[430px] overflow-x-hidden bg-obsidian-bg ${isChatbotRoute ? '' : 'pb-24'}`}>
        <Routes>
          <Route path="/chatbot" element={<MobileChatbot isLoggedIn={isLoggedIn} />} />
          <Route
            path="/"
            element={(
              <MobileHome
                isLoggedIn={isLoggedIn}
                userEmail={userEmail}
                handleLogout={handleLogout}
              />
            )}
          />
          <Route
            path="/dashboard"
            element={isLoggedIn ? (
              <MobileDashboard
                isLoggedIn={isLoggedIn}
                userEmail={userEmail}
                handleLogout={handleLogout}
                userProfile={userProfile}
                setUserProfile={setUserProfile}
              />
            ) : memberOnlyNoticeElement}
          />
          <Route
            path="/market-rankings"
            element={(
              <MobileMarketRankings
                isLoggedIn={isLoggedIn}
                userEmail={userEmail}
                handleLogout={handleLogout}
              />
            )}
          />
          <Route
            path="/news"
            element={isLoggedIn ? (
              <MobileNews
                isLoggedIn={isLoggedIn}
                userEmail={userEmail}
                handleLogout={handleLogout}
              />
            ) : memberOnlyNoticeElement}
          />
          {Object.values(INQUIRY_ROUTES).map((path) => (
            <Route key={path} path={path} element={protectedInquiryElement} />
          ))}
          <Route
            path="/settings"
            element={(
              <div className="min-h-screen bg-obsidian-bg px-3 py-4 font-inter text-[#e2e2ec]">
                <MobileHeader isLoggedIn={isLoggedIn} handleLogout={handleLogout} />
                <MobileSettings
                  isLoggedIn={isLoggedIn}
                  userEmail={userEmail}
                  handleLogout={handleLogout}
                  userProfile={userProfile}
                  setUserProfile={setUserProfile}
                  hideHeader
                  mobileLayout
                />
              </div>
            )}
          />
          <Route
            path="/admin/ml-data"
            element={(
              <AdminProtectedRoute isLoggedIn={isLoggedIn} userProfile={userProfile}>
                <div className="min-h-screen bg-obsidian-bg px-3 py-4 font-inter text-[#e2e2ec]">
                  <MobileHeader isLoggedIn={isLoggedIn} handleLogout={handleLogout} />
                  <MobileAdminMlData
                    isLoggedIn={isLoggedIn}
                    userEmail={userEmail}
                    handleLogout={handleLogout}
                    hideHeader
                  />
                </div>
              </AdminProtectedRoute>
            )}
          />
          <Route
            path="/admin/ai-fund"
            element={(
              <AdminProtectedRoute isLoggedIn={isLoggedIn} userProfile={userProfile}>
                <div className="min-h-screen bg-obsidian-bg px-3 py-4 font-inter text-[#e2e2ec]">
                  <MobileHeader isLoggedIn={isLoggedIn} handleLogout={handleLogout} />
                  <MobileAdminAiFundDashboard userId={userProfile?.id} />
                </div>
              </AdminProtectedRoute>
            )}
          />
          <Route path="/login" element={<MobileLogin />} />

          <Route path="/signup" element={<Navigate to="/login" replace />} />
          <Route
            path="/asset/:assetType"
            element={(
              <MobileSearchNotFound
                isLoggedIn={isLoggedIn}
                userEmail={userEmail}
                handleLogout={handleLogout}
              />
            )}
          />
          <Route
            path="/asset/:assetType/:symbol"
            element={(
              <div className="min-h-screen bg-obsidian-bg px-3 py-4 font-inter text-[#e2e2ec]">
                <MobileHeader isLoggedIn={isLoggedIn} handleLogout={handleLogout} />
                <MobileAssetDetail
                  isLoggedIn={isLoggedIn}
                  userEmail={userEmail}
                  handleLogout={handleLogout}
                  userProfile={userProfile}
                  hideHeader
                  mobileLayout
                />
              </div>
            )}
          />
          <Route
            path="/search/not-found"
            element={(
              <MobileSearchNotFound
                isLoggedIn={isLoggedIn}
                userEmail={userEmail}
                handleLogout={handleLogout}
              />
            )}
          />
        </Routes>

        {/* 모바일 하단 네비게이션도 430px 영역 안에 들어오게 이동 */}
        {!isChatbotRoute ? <MobileBottomNavigation isLoggedIn={isLoggedIn} /> : null}
      </div>
    </div>
  )
}
