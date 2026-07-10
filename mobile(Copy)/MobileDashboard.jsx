import MobileHeader from '../../components/mobile/MobileHeader.jsx'
import MobileDashboardPage from './MobileDashboardPage.jsx'

export default function MobileDashboard({
  isLoggedIn,
  userEmail,
  handleLogout,
  userProfile,
  setUserProfile,
}) {
  return (
    <div className="min-h-screen overflow-x-hidden bg-obsidian-bg px-3 py-4 font-inter text-[#e2e2ec] sm:px-4">
      <MobileHeader isLoggedIn={isLoggedIn} handleLogout={handleLogout} />
      <MobileDashboardPage
        isLoggedIn={isLoggedIn}
        userEmail={userEmail}
        handleLogout={handleLogout}
        userProfile={userProfile}
        setUserProfile={setUserProfile}
      />
    </div>
  )
}
