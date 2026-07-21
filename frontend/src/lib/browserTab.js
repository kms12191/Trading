const DEFAULT_BROWSER_TITLE = 'ANTRY'
const DEFAULT_FAVICON_HREF = '/favicon.png'

function ensureFaviconLink() {
  if (typeof document === 'undefined') return null

  let link = document.querySelector("link[rel~='icon']")
  if (!link) {
    link = document.createElement('link')
    link.rel = 'icon'
    document.head.appendChild(link)
  }
  return link
}

export function setBrowserTab({ title, iconHref } = {}) {
  if (typeof document === 'undefined') return () => {}

  const previousTitle = document.title
  const faviconLink = ensureFaviconLink()
  const previousIconHref = faviconLink?.getAttribute('href') || DEFAULT_FAVICON_HREF

  document.title = title || DEFAULT_BROWSER_TITLE
  if (faviconLink) {
    faviconLink.setAttribute('href', iconHref || DEFAULT_FAVICON_HREF)
  }

  return () => {
    document.title = previousTitle || DEFAULT_BROWSER_TITLE
    if (faviconLink) {
      faviconLink.setAttribute('href', previousIconHref || DEFAULT_FAVICON_HREF)
    }
  }
}
