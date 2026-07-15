import { useState } from 'react'

function detectDeviceType() {
  if (typeof window !== 'undefined') {
    const forcedDevice = new URLSearchParams(window.location.search).get('device')

    if (forcedDevice === 'mobile') {
      return { deviceType: 'mobile', os: 'forced', isMobileDevice: true }
    }

    if (forcedDevice === 'desktop') {
      return { deviceType: 'desktop', os: 'forced', isMobileDevice: false }
    }
  }

  if (typeof navigator === 'undefined') {
    return { deviceType: 'desktop', os: 'unknown', isMobileDevice: false }
  }

  const userAgent = navigator.userAgent || ''
  const platform = navigator.userAgentData?.platform || navigator.platform || ''
  const isClientHintMobile = Boolean(navigator.userAgentData?.mobile)
  const isIpadOsDesktopMode = /Mac/i.test(platform) && navigator.maxTouchPoints > 1
  const isMobileUserAgent = /Android|webOS|iPhone|iPad|iPod|BlackBerry|IEMobile|Opera Mini/i.test(userAgent)
  const isMobileDevice = isClientHintMobile || isMobileUserAgent || isIpadOsDesktopMode

  let os = 'unknown'
  if (/Android/i.test(userAgent)) {
    os = 'Android'
  } else if (/iPhone|iPad|iPod/i.test(userAgent)) {
    os = 'iOS'
  } else if (isIpadOsDesktopMode) {
    os = 'iPadOS'
  } else if (/Windows/i.test(platform) || /Windows/i.test(userAgent)) {
    os = 'Windows'
  } else if (/Mac/i.test(platform) || /Mac OS X/i.test(userAgent)) {
    os = 'macOS'
  } else if (/Linux/i.test(platform) || /Linux/i.test(userAgent)) {
    os = 'Linux'
  }

  return {
    deviceType: isMobileDevice ? 'mobile' : 'desktop',
    os,
    isMobileDevice,
  }
}

export default function useDeviceType() {
  const [device] = useState(detectDeviceType)

  return device
}
