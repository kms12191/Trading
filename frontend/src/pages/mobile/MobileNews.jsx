import MobileHeader from '../../components/mobile/MobileHeader.jsx'
import MobileNewsPage from './MobileNewsPage.jsx'

export default function MobileNews({ isLoggedIn, userEmail, handleLogout }) {
  return (
    <div className="min-h-screen overflow-x-hidden bg-obsidian-bg px-3 py-4 font-inter text-[#e2e2ec] sm:px-4">
      <MobileHeader isLoggedIn={isLoggedIn} handleLogout={handleLogout} />
      <div>
        <MobileNewsPage
          isLoggedIn={isLoggedIn}
          userEmail={userEmail}
          handleLogout={handleLogout}
          hideHeader
          maxVisiblePages={3}
          mobileLayout
        />
      </div>
    </div>
  )
}
