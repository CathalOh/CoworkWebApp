import { create } from 'zustand'
import { ApiError, onUnauthorized, setCsrfToken } from '@/lib/api/client'
import { devLogin, getMe, getMeta } from '@/lib/api/endpoints'
import type { Meta, User } from '@/lib/api/types'
import { endSession } from '@/lib/oidc'

interface AuthState {
  user: User | null
  meta: Meta | null
  status: 'idle' | 'loading' | 'authenticated' | 'anonymous'
  bootstrap: () => Promise<void>
  loginDev: (email: string, display_name: string, roles: string[]) => Promise<void>
  logout: () => Promise<void>
  hasRole: (...roles: string[]) => boolean
}

export const useAuthStore = create<AuthState>((set, get) => ({
  user: null,
  meta: null,
  status: 'idle',
  bootstrap: async () => {
    set({ status: 'loading' })
    const [meta, user] = await Promise.all([
      getMeta().catch(() => null),
      getMe().catch((e: unknown) => {
        if (e instanceof ApiError && e.status === 401) return null
        throw e
      }),
    ])
    setCsrfToken(user?.csrf_token)
    set({ meta, user, status: user ? 'authenticated' : 'anonymous' })
  },
  loginDev: async (email, display_name, roles) => {
    const user = await devLogin({ email, display_name: display_name || undefined, roles })
    setCsrfToken(user.csrf_token)
    set({ user, status: 'authenticated' })
  },
  logout: async () => {
    await endSession()
    setCsrfToken(null)
    set({ user: null, status: 'anonymous' })
  },
  hasRole: (...roles) => {
    const u = get().user
    return !!u && roles.some((r) => u.roles.includes(r))
  },
}))

// Any 401 from the API drops us back to anonymous; the router then shows /login.
onUnauthorized(() => {
  if (useAuthStore.getState().status === 'authenticated') {
    setCsrfToken(null)
    useAuthStore.setState({ user: null, status: 'anonymous' })
  }
})

export const ADMIN_ROLES = ['org_admin', 'auditor', 'workspace_admin', 'team_lead']
