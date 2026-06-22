import { useEffect, useState } from 'react'
import Dashboard from './pages/Dashboard.jsx'
import News from './pages/News.jsx'

const routes = {
  dashboard: Dashboard,
  news: News,
}

function getRouteFromHash() {
  const hash = window.location.hash.replace(/^#\/?/, '').trim()
  return hash || 'dashboard'
}

export default function App() {
  const [route, setRoute] = useState(getRouteFromHash())

  useEffect(() => {
    const onHashChange = () => {
      setRoute(getRouteFromHash())
    }

    window.addEventListener('hashchange', onHashChange)
    if (!window.location.hash) {
      window.location.hash = '#/dashboard'
    }

    return () => window.removeEventListener('hashchange', onHashChange)
  }, [])

  const Page = routes[route] || Dashboard

  return <Page currentRoute={route} />
}
