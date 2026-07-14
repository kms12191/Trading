import { useNavigate } from 'react-router-dom'
import ChatbotWidget from '../../features/chatbot/ChatbotWidget.jsx'

export default function MobileChatbot({ isLoggedIn }) {
  const navigate = useNavigate()

  const closeChatbot = () => {
    if (window.history.length > 1) {
      navigate(-1)
      return
    }

    navigate('/')
  }

  return (
    <ChatbotWidget
      enabled
      isLoggedIn={isLoggedIn}
      presentation="mobile-page"
      onClose={closeChatbot}
    />
  )
}
