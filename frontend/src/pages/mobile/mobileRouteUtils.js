export function preserveMobileDeviceParam(path) {
  if (typeof window === 'undefined') return path

  // PC 라우트와 같은 주소를 공유해도 강제 모바일 보기 상태를 잃지 않도록 device=mobile을 이어 붙입니다.
  const currentParams = new URLSearchParams(window.location.search)
  if (currentParams.get('device') !== 'mobile') return path

  const [pathname, query = ''] = String(path).split('?')
  const nextParams = new URLSearchParams(query)
  nextParams.set('device', 'mobile')

  return `${pathname}?${nextParams.toString()}`
}
