/**
 * What is held for a decision right now, for the nav badge and the Overview.
 * Both read one cached list and count with the approvals page's rule
 * (`heldApprovals`: pending and not expired), and the clock ticks when the next
 * item expires, so a lapsed item leaves every count at the same moment
 * instead of up to five minutes later (the cache's stale time).
 */
import { useEffect, useState } from 'react'
import { useApi } from '@/hooks/use-api'
import type { Approval } from '@/components/approval-card'
import {
  APPROVALS_PATHS,
  heldApprovals,
  nextExpiry,
  type ApprovalState,
} from '@/lib/approval-outcome'

/** The list the nav badge, the Overview and the Held tab share (one cached query per principal). */
export const HELD_APPROVALS_PATH = APPROVALS_PATHS.pending

/** The longest a browser timer can wait (about 24.8 days). */
const MAX_TIMER_MS = 2_147_483_647
/** Fire just after the expiry, so the item is past it when the count is redone. */
const SETTLE_MS = 25

const NONE: Approval[] = []

/**
 * How long until the clock must tick for the next expiry (ms), judged at
 * `now` (the clock the count uses) against the real time `wall`; null when no
 * held item will expire.
 */
export function expiryDelay(
  list: readonly ApprovalState[],
  now: number,
  wall: number = Date.now(),
): number | null {
  const next = nextExpiry(list, now)
  if (next === null) return null
  return Math.min(Math.max(next - wall, 0) + SETTLE_MS, MAX_TIMER_MS)
}

/** A clock (ms) that moves on when the next held item in `list` expires. */
export function useExpiryClock(list: readonly ApprovalState[]): number {
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => {
    const delay = expiryDelay(list, now)
    if (delay === null) return
    const timer = setTimeout(() => setNow(Date.now()), delay)
    return () => clearTimeout(timer)
  }, [list, now])
  return now
}

/** Items held for a decision now; `loading` until the list first arrives. */
export function useHeldApprovals(): { held: Approval[]; loading: boolean } {
  const { data, loading } = useApi<{ approvals: Approval[] }>(HELD_APPROVALS_PATH)
  const list = data?.approvals ?? NONE
  const now = useExpiryClock(list)
  return { held: heldApprovals(list, now), loading }
}
