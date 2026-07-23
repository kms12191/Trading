import { useEffect } from 'react'
import { Navigate, Route, Routes } from 'react-router-dom'
import Dashboard from '../pages/Dashboard'
import Login from '../pages/Login'
import News from '../pages/News'
import Inquiry from '../pages/Inquiry'
import Settings from '../pages/Settings'
import Home from '../pages/Home'
import MarketRankings from '../pages/MarketRankings'
import AdminMlData from '../pages/AdminMlData'
import AdminAiFundDashboard from '../pages/AdminAiFundDashboard'
import AssetDetail from '../pages/AssetDetail'

import SearchNotFound from '../pages/SearchNotFound'
import { INQUIRY_ROUTES } from '../dashboardConstants.js'

function AdminProtectedRoute({ isLoggedIn, userProfile, children }) {
  const isDevelopment = import.meta.env.DEV
  const hasAccess = isLoggedIn && (!userProfile || userProfile?.role === 'ADMIN' || userProfile?.role === 'admin' || isDevelopment)

  if (!isLoggedIn) {
    return <Navigate to="/login" replace />
  }

  if (!hasAccess) {
    return <Navigate to="/dashboard" replace />
  }

  return children
}


export default function DesktopRoutes({
  isLoggedIn,
  userEmail,
  handleLogout,
  userProfile,
  setUserProfile,
}) {
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
          <AdminProtectedRoute isLoggedIn={isLoggedIn} userProfile={userProfile}>
            <AdminMlData
              isLoggedIn={isLoggedIn}
              userEmail={userEmail}
              handleLogout={handleLogout}
              userProfile={userProfile}
            />

          </AdminProtectedRoute>
        )}
      />
      <Route
        path="/admin/ai-fund"
        element={(
          <AdminProtectedRoute isLoggedIn={isLoggedIn} userProfile={userProfile}>
            <AdminAiFundDashboard userId={userProfile?.id} />
          </AdminProtectedRoute>
        )}
      />
      <Route path="/login" element={<Login />} />

      <Route path="/signup" element={<Navigate to="/login" replace />} />
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
  )
}
