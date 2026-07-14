import MobileHeader from '../../components/mobile/MobileHeader.jsx'
import MobileNewsPage from './MobileNewsPage.jsx'

export default function MobileNews({ isLoggedIn, userEmail, handleLogout }) {
  return (
    <div className="min-h-screen bg-obsidian-bg px-4 pb-4 pt-3 font-inter text-[#e2e2ec]">
      <MobileHeader isLoggedIn={isLoggedIn} handleLogout={handleLogout} />
      <div className="-mt-5">
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
