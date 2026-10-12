/**
 * Venture context — the one venture the dashboard is working in (STORY-18).
 *
 * Loads the ventures the signed-in user may see (`GET /api/ventures` is
 * already filtered by the server) and keeps one selected across pages. A user
 * limited to a single venture gets a locked view: no switcher, that venture.
 */

import {
  createContext,
  createElement,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from 'react'
import { api } from '@/lib/api'
import { useAuth, useAuthPrincipal } from '@/hooks/use-auth'

export interface VentureSummary {
  key: string
  name: string
  /** Content language of the venture, e.g. "he" (sets RTL). */
  locale?: string
  agent_count?: number
}

interface VentureContextValue {
  ventures: VentureSummary[]
  /** Selected venture key ('' while loading or when there are none). */
  selected: string
  select: (key: string) => void
  /** True when the user is limited to exactly one venture. */
  locked: boolean
  loading: boolean
}

const STORAGE_KEY = 'realize_selected_venture'

/** The stored choice if it is still available, else the first venture. */
export function resolveSelection(ventures: VentureSummary[], stored: string): string {
  if (ventures.some((v) => v.key === stored)) return stored
  return ventures[0]?.key ?? ''
}

/** A user scoped to exactly one venture sees that venture only. */
export function isLocked(userVentures: string[] | null | undefined): boolean {
  return Array.isArray(userVentures) && userVentures.length === 1
}

function readStored(): string {
  try {
    return localStorage.getItem(STORAGE_KEY) ?? ''
  } catch {
    return ''
  }
}

function writeStored(key: string): void {
  try {
    localStorage.setItem(STORAGE_KEY, key)
  } catch {
    // Private mode / blocked storage: the choice lasts for this page only.
  }
}

const VentureContext = createContext<VentureContextValue | null>(null)

export function VentureProvider({ children }: { children: ReactNode }) {
  const { user } = useAuth()
  const principal = useAuthPrincipal()
  // The list is stored with the identity it was fetched for; a list fetched for
  // anyone else reads as empty, so a new identity never sees the previous one's.
  const [loaded, setLoaded] = useState<{ principal: string; ventures: VentureSummary[] } | null>(
    null,
  )
  const [stored, setStored] = useState(readStored)
  const current = loaded?.principal === principal ? loaded : null
  const ventures = useMemo(() => current?.ventures ?? [], [current])
  const loading = current === null

  useEffect(() => {
    let cancelled = false
    api
      .get<{ ventures: VentureSummary[] }>('/ventures')
      .then((data) => !cancelled && setLoaded({ principal, ventures: data.ventures || [] }))
      .catch(() => !cancelled && setLoaded({ principal, ventures: [] }))
    return () => {
      cancelled = true
    }
  }, [principal])

  const select = useCallback((key: string) => {
    setStored(key)
    writeStored(key)
  }, [])

  const value = useMemo<VentureContextValue>(
    () => ({
      ventures,
      selected: resolveSelection(ventures, stored),
      select,
      locked: isLocked(user?.ventures),
      loading,
    }),
    [ventures, stored, select, user?.ventures, loading],
  )

  return createElement(VentureContext.Provider, { value }, children)
}

export function useVenture(): VentureContextValue {
  const ctx = useContext(VentureContext)
  if (!ctx) throw new Error('useVenture must be used inside <VentureProvider>')
  return ctx
}
