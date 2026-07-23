import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { Analytics } from '@vercel/analytics/react'
import './index.css'
import App from './App.jsx'
import { installApiProxyFetch } from './lib/installApiProxyFetch.js'
import { registerServiceWorker } from './registerServiceWorker.js'

installApiProxyFetch()
registerServiceWorker()

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <App />
    {import.meta.env.PROD ? <Analytics /> : null}
  </StrictMode>,
)
