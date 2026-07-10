import { Navigate, Route, Routes } from 'react-router-dom'
import MobileHome from '../pages/mobile/MobileHome.jsx'
import MobileDashboard from '../pages/mobile/MobileDashboard.jsx'
import MobileNews from '../pages/mobile/MobileNews.jsx'
import MobileSettings from '../pages/mobile/MobileSettings.jsx'
import MobileLogin from '../pages/mobile/MobileLogin.jsx'
import MobileSignup from '../pages/mobile/MobileSignup.jsx'
import MobileInquiry from '../pages/mobile/MobileInquiry.jsx'
import MobileMarketRankings from '../pages/mobile/MobileMarketRankings.jsx'
import MobileAdminMlData from '../pages/mobile/MobileAdminMlData.jsx'
import MobileAssetDetail from '../pages/mobile/MobileAssetDetail.jsx'
import MobileSearchNotFound from '../pages/mobile/MobileSearchNotFound.jsx'
import { INQUIRY_ROUTES } from '../dashboardConstants.js'
import MobileBottomNavigation from '../components/mobile/MobileBottomNavigation.jsx'
import MobileHeader from '../components/mobile/MobileHeader.jsx'

export default function MobileRoutes({
  isLoggedIn,
  userEmail,
  handleLogout,
  userProfile,
  setUserProfile,
}) {
  const protectedInquiryElement = isLoggedIn ? (
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

  return (
    // 전체 모바일 화면의 바깥 배경
    <div className="min-h-screen bg-obsidian-bg">
      {/*
        실제 모바일 화면 영역
        max-w-[430px] 때문에 PC 브라우저에서도 모바일처럼 좁게 보임
        mx-auto 때문에 가운데 정렬됨
        pb-24는 하단 모바일 네비게이션에 내용이 가리지 않도록 여백 추가
      */}
      <div className="mx-auto min-h-screen w-full max-w-[430px] overflow-x-hidden bg-obsidian-bg pb-24">
        <Routes>
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
            element={(
              <MobileDashboard
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
              <MobileMarketRankings
                isLoggedIn={isLoggedIn}
                userEmail={userEmail}
                handleLogout={handleLogout}
              />
            )}
          />
          <Route
            path="/news"
            element={(
              <MobileNews
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
              <MobileAdminMlData
                isLoggedIn={isLoggedIn}
                userEmail={userEmail}
                handleLogout={handleLogout}
              />
            )}
          />
          <Route path="/login" element={<MobileLogin />} />
          <Route path="/signup" element={<MobileSignup />} />
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
        <MobileBottomNavigation isLoggedIn={isLoggedIn} />
      </div>
    </div>
  )
}
