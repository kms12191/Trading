const CACHE_NAME = 'antry-static-v3'

// 앱 설치 후 빠르게 다시 열 수 있도록 정적 파일만 캐시합니다.
const STATIC_ASSETS = [
  '/',
  '/index.html',
  '/favicon.svg',
  '/logo.png',
  '/manifest.webmanifest',
  '/pwa-icon-192.png',
  '/pwa-icon-512.png',
  '/pwa-maskable-512.png',
]

const isApiRequest = (url) => (
  url.pathname.startsWith('/api/')
  || url.pathname.startsWith('/backend-api/')
  || url.pathname.startsWith('/auth/')
)

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME)
      .then((cache) => cache.addAll(STATIC_ASSETS))
      .then(() => self.skipWaiting()),
  )
})

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(
        keys.filter((key) => key !== CACHE_NAME).map((key) => caches.delete(key)),
      ))
      .then(() => self.clients.claim()),
  )
})

self.addEventListener('fetch', (event) => {
  if (event.request.method !== 'GET') return

  const requestUrl = new URL(event.request.url)
  // 로그인, 주문, 관리자 데이터 같은 API 응답은 오래된 값이 남지 않도록 캐시하지 않습니다.
  if (requestUrl.origin !== self.location.origin || isApiRequest(requestUrl)) {
    return
  }

  if (event.request.mode === 'navigate') {
    // 새로고침이나 직접 URL 진입 시에도 React 라우터가 동작하도록 index.html을 대체 응답으로 사용합니다.
    event.respondWith(
      fetch(event.request)
        .then((response) => {
          const responseCopy = response.clone()
          caches.open(CACHE_NAME).then((cache) => cache.put('/index.html', responseCopy))
          return response
        })
        .catch(() => caches.match('/index.html')),
    )
    return
  }

  // 이미지, manifest 같은 정적 리소스는 캐시 우선으로 보여주고 백그라운드에서 최신 응답을 저장합니다.
  event.respondWith(
    caches.match(event.request).then((cachedResponse) => {
      const networkFetch = fetch(event.request)
        .then((response) => {
          if (response.ok) {
            const responseCopy = response.clone()
            caches.open(CACHE_NAME).then((cache) => cache.put(event.request, responseCopy))
          }
          return response
        })
        .catch(() => cachedResponse)

      return cachedResponse || networkFetch
    }),
  )
})
