/**
 * Review D2 and D1: the nav badge and the Overview count held items with the
 * approvals page's rule, so an item whose time ran out leaves every count at
 * once (not up to five minutes later), and a decision-log result that isn't
 * a decision says nothing.
 */
import { describe, expect, it } from 'vitest'
import { expiryDelay } from '@/hooks/use-held-approvals'
import {
  APPROVALS_PATHS,
  decisionLogState,
  heldApprovals,
  nextExpiry,
  type ApprovalState,
} from './approval-outcome'

const NOW = Date.parse('2026-10-13T12:00:00Z')

const soon: ApprovalState = { id: 'soon', status: 'pending', expires_at: '2026-10-13T12:05:00Z' }
const later: ApprovalState = { id: 'later', status: 'pending', expires_at: '2026-10-13T15:00:00Z' }
const never: ApprovalState = { id: 'never', status: 'pending', expires_at: null }
const lapsed: ApprovalState = {
  id: 'lapsed',
  status: 'pending',
  expires_at: '2026-10-13T11:59:00Z',
}
const flagged: ApprovalState = { id: 'flagged', status: 'pending', expired: true }

describe('heldApprovals', () => {
  it('drops items whose time ran out, by the clock, not by the stale list', () => {
    const list = [soon, later, never, lapsed, flagged]
    expect(heldApprovals(list, NOW).map((a) => a.id)).toEqual(['soon', 'later', 'never'])
    // Five minutes on, the first one has gone too.
    const after = Date.parse('2026-10-13T12:05:00Z')
    expect(heldApprovals(list, after).map((a) => a.id)).toEqual(['later', 'never'])
  })

  it('only pending items are held', () => {
    const decided: ApprovalState = { id: 'd', status: 'approved' }
    expect(heldApprovals([decided, never], NOW).map((a) => a.id)).toEqual(['never'])
  })
})

describe('nextExpiry / expiryDelay', () => {
  it('the clock ticks when the earliest held item expires', () => {
    const list = [later, soon, never]
    expect(nextExpiry(list, NOW)).toBe(Date.parse('2026-10-13T12:05:00Z'))
    expect(expiryDelay(list, NOW, NOW)).toBe(5 * 60_000 + 25)
  })

  it('no timer when nothing will expire', () => {
    expect(nextExpiry([never], NOW)).toBeNull()
    expect(expiryDelay([never, lapsed], NOW, NOW)).toBeNull()
  })

  it('an item that lapsed before the list arrived is recounted at once', () => {
    // The count's clock is from mount; the list arrived after `soon` expired.
    const arrived = Date.parse('2026-10-13T12:06:00Z')
    expect(expiryDelay([soon], NOW, arrived)).toBe(25)
  })

  it('a far expiry never overflows the browser timer', () => {
    const far: ApprovalState = { id: 'far', status: 'pending', expires_at: '2027-12-31T00:00:00Z' }
    expect(expiryDelay([far], NOW, NOW)).toBe(2_147_483_647)
  })
})

describe('decisionLogState', () => {
  it('inputs and rejected proposals are not decisions: nothing to say', () => {
    expect(decisionLogState({ logged: false, pending: false, error: null })).toBeNull()
    expect(decisionLogState(null)).toBeNull()
    expect(decisionLogState(undefined)).toBeNull()
  })

  it('logged, queued for a retry, or failed', () => {
    expect(decisionLogState({ logged: true, decision_id: '2026-10-13-x' })).toBe('logged')
    // A queued retry carries the first error too; it is still going to be added.
    expect(decisionLogState({ logged: false, pending: true, error: 'disk full' })).toBe('queued')
    expect(decisionLogState({ logged: false, pending: false, error: 'not queued' })).toBe('failed')
  })
})

describe('APPROVALS_PATHS (review D12)', () => {
  it('the Decided tab asks the server for the latest decisions, capped', () => {
    expect(APPROVALS_PATHS.decided).toBe('/approvals?status=decided&limit=50')
    expect(APPROVALS_PATHS.pending).toBe('/approvals?status=pending')
    expect(APPROVALS_PATHS.expired).toBe('/approvals?status=expired')
  })
})
