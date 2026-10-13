/**
 * Auth context — cookie-session authentication state for the dashboard.
 *
 * Loads on mount via GET /api/auth/session. Exposes login/logout helpers
 * and listens for the `realize:session-expired` event dispatched by the
 * API client when any request returns 401 — at which point we clear the
 * user and the AuthGuard redirects to /login.
 */

import {
  createContext,
  createElement,
  useCallback,
  useContext,
  useEffect,
  useRef,
  useState,
  type ReactNode,
} from 'react'
import { api } from '@/lib/api'
import { principalKey, resetQueryCache } from '@/lib/query-client'

export interface AuthUser {
  user_id: string
  role: string
  /** Ventures this user is limited to; null/undefined = every venture. */
  ventures?: string[] | null
  /** The role's RBAC permissions, as the server resolves them (UX hint only). */
  permissions?: string[] | null
}

interface SessionResponse {
  authenticated: boolean
  user_id?: string
  role?: string
  ventures?: string[] | null
  permissions?: string[] | null
}

interface LoginResponse {
  user_id: string
  role: string
  ventures?: string[] | null
  permissions?: string[] | null
}

interface AuthContextValue {
  user: AuthUser | null
  loading: boolean
  login: (email: string, password: string, rememberMe: boolean) => Promise<void>
  logout: () => Promise<void>
  refresh: () => Promise<void>
}

const AuthContext = createContext<AuthContextValue | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUserState] = useState<AuthUser | null>(null)
  const [loading, setLoading] = useState(true)
  const identity = useRef(principalKey(null))

  // Every identity change (sign-in, sign-out, expiry, role/scope change)
  // drops the previous identity's cached data before the new one renders.
  const setUser = useCallback((next: AuthUser | null) => {
    const key = principalKey(next)
    if (key !== identity.current) {
      resetQueryCache()
      identity.current = key
    }
    setUserState(next)
  }, [])

  const refresh = useCallback(async () => {
    try {
      const res = await api.get<SessionResponse>('/auth/session')
      if (res.authenticated && res.user_id && res.role) {
        setUser({
          user_id: res.user_id,
          role: res.role,
          ventures: res.ventures ?? null,
          permissions: res.permissions ?? null,
        })
      } else {
        setUser(null)
      }
    } catch {
      setUser(null)
    } finally {
      setLoading(false)
    }
  }, [setUser])

  const login = useCallback(
    async (email: string, password: string, rememberMe: boolean) => {
      const res = await api.post<LoginResponse>('/auth/login', {
        email,
        password,
        remember_me: rememberMe,
      })
      setUser({
        user_id: res.user_id,
        role: res.role,
        ventures: res.ventures ?? null,
        permissions: res.permissions ?? null,
      })
    },
    [setUser],
  )

  const logout = useCallback(async () => {
    try {
      await api.post('/auth/logout')
    } catch {
      // even if the server call fails, drop the client state
    }
    setUser(null)
  }, [setUser])

  useEffect(() => {
    refresh()
  }, [refresh])

  useEffect(() => {
    const onExpired = () => setUser(null)
    window.addEventListener('realize:session-expired', onExpired)
    return () => window.removeEventListener('realize:session-expired', onExpired)
  }, [setUser])

  return createElement(
    AuthContext.Provider,
    { value: { user, loading, login, logout, refresh } },
    children,
  )
}

/** Cache partition of the signed-in user ('anonymous' outside AuthProvider). */
export function useAuthPrincipal(): string {
  return principalKey(useContext(AuthContext)?.user)
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used inside <AuthProvider>')
  return ctx
}
