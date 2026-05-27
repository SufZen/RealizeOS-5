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
  useState,
  type ReactNode,
} from 'react'
import { api } from '@/lib/api'

export interface AuthUser {
  user_id: string
  role: string
}

interface SessionResponse {
  authenticated: boolean
  user_id?: string
  role?: string
}

interface LoginResponse {
  user_id: string
  role: string
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
  const [user, setUser] = useState<AuthUser | null>(null)
  const [loading, setLoading] = useState(true)

  const refresh = useCallback(async () => {
    try {
      const res = await api.get<SessionResponse>('/auth/session')
      if (res.authenticated && res.user_id && res.role) {
        setUser({ user_id: res.user_id, role: res.role })
      } else {
        setUser(null)
      }
    } catch {
      setUser(null)
    } finally {
      setLoading(false)
    }
  }, [])

  const login = useCallback(async (email: string, password: string, rememberMe: boolean) => {
    const res = await api.post<LoginResponse>('/auth/login', {
      email,
      password,
      remember_me: rememberMe,
    })
    setUser({ user_id: res.user_id, role: res.role })
  }, [])

  const logout = useCallback(async () => {
    try {
      await api.post('/auth/logout')
    } catch {
      // even if the server call fails, drop the client state
    }
    setUser(null)
  }, [])

  useEffect(() => {
    refresh()
  }, [refresh])

  useEffect(() => {
    const onExpired = () => setUser(null)
    window.addEventListener('realize:session-expired', onExpired)
    return () => window.removeEventListener('realize:session-expired', onExpired)
  }, [])

  return createElement(
    AuthContext.Provider,
    { value: { user, loading, login, logout, refresh } },
    children,
  )
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used inside <AuthProvider>')
  return ctx
}
