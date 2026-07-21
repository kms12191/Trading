export function registerServiceWorker() {
  // 개발 중 캐시가 남아 화면 확인을 방해하지 않도록 운영 빌드에서만 등록합니다.
  if (!import.meta.env.PROD) return
  if (!('serviceWorker' in navigator)) return

  window.addEventListener('load', () => {
    navigator.serviceWorker.register('/service-worker.js').catch((error) => {
      console.warn('Service worker registration failed:', error)
    })
  })
}
