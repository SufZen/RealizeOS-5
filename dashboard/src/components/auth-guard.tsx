/**
 * AuthGuard — redirects to /login when the current route requires a user
 * and no session is active. The /login route is the only public route.
 */

import { useEffect, type ReactNode } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import { useAuth } from '@/hooks/use-auth'
import { loginRedirect } from '@/lib/sign-out-state'

interface Props {
  children: ReactNode
}

export default function AuthGuard({ children }: Props) {
  const { user, loading } = useAuth()
  const location = useLocation()
  const navigate = useNavigate()

  useEffect(() => {
    if (loading) return
    if (user) return
    if (location.pathname === '/login') return

    // After a deliberate sign-out, don't hand this page to the next person.
    navigate(loginRedirect(location.pathname, location.search), { replace: true })
  }, [user, loading, location.pathname, location.search, navigate])

  if (loading) {
    return (
      <div className="flex h-screen items-center justify-center bg-background">
        <div className="text-sm text-muted-foreground">Loading…</div>
      </div>
    )
  }

  if (!user && location.pathname !== '/login') {
    // Render nothing while the redirect kicks in to avoid a flash of protected UI.
    return null
  }

  return <>{children}</>
}
