import { QueryClient } from '@tanstack/react-query'

export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 1000 * 60 * 5, // 5 minutes
      refetchOnWindowFocus: false,
      retry: 1,
    },
  },
})

/** The parts of the signed-in user that decide what the server may return. */
export interface Principal {
  user_id: string
  role: string
  ventures?: string[] | null
}

/**
 * Cache partition for a principal. Cached API data is keyed by it, so data
 * fetched for one user (or one role / venture scope) is never served to another.
 */
export function principalKey(user: Principal | null | undefined): string {
  if (!user) return 'anonymous'
  const scope = Array.isArray(user.ventures) ? [...user.ventures].sort().join(',') : '*'
  return `${user.user_id}|${user.role}|${scope}`
}

/**
 * Drop everything cached for the previous identity: abort in-flight requests
 * (so a late response can't land) and empty the cache. Call on every sign-in,
 * sign-out and session expiry, before the new identity renders.
 */
export function resetQueryCache(client: QueryClient = queryClient): void {
  void client.cancelQueries()
  client.clear()
}
