import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.jsx'
import { installApiProxyFetch } from './lib/installApiProxyFetch.js'
import { registerServiceWorker } from './registerServiceWorker.js'

installApiProxyFetch()
registerServiceWorker()

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
