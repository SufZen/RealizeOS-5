import { useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuth } from '@/hooks/use-auth'

/**
 * Sign out and go to the sign-in page. `logout` ends the server session and
 * drops this person's cached data (`endSession`); going to `/login` directly
 * means the next person isn't sent back to this one's page after signing in.
 */
export function useSignOut(): () => Promise<void> {
  const { logout } = useAuth()
  const navigate = useNavigate()
  return useCallback(async () => {
    await logout()
    navigate('/login', { replace: true })
  }, [logout, navigate])
}
