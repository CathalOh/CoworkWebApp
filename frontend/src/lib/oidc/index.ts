import { oidcLoginUrl } from '@/lib/api/endpoints'
import { logout as apiLogout } from '@/lib/api/endpoints'

/** OIDC login is a full-page navigation: the backend performs the PKCE dance and redirects back to "/". */
export function startOidcLogin(returnTo?: string) {
  if (returnTo) {
    try {
      sessionStorage.setItem('cw.returnTo', returnTo)
    } catch {
      /* ignore */
    }
  }
  window.location.assign(oidcLoginUrl())
}

export function consumeReturnTo(): string | null {
  try {
    const v = sessionStorage.getItem('cw.returnTo')
    if (v) sessionStorage.removeItem('cw.returnTo')
    return v
  } catch {
    return null
  }
}

/** Logout: POST returns 204 (dev) or 303 to the IdP end-session URL (fetch follows it; we then go to /login). */
export async function endSession() {
  try {
    await apiLogout()
  } catch {
    /* session may already be gone */
  }
}
