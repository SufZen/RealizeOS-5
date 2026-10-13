/**
 * Codex audit N11 + N04 (UI): expiry, what ran after a decision, and why a
 * decision didn't apply. "Approved" alone is never reported as success.
 */
import { describe, expect, it } from 'vitest'
import { ApiError } from './api'
import {
  approvalOutcome,
  classifyDecisionError,
  isExpired,
  withSettled,
  type ApprovalState,
} from './approval-outcome'

const NOW = Date.parse('2026-10-13T12:00:00Z')

const held: ApprovalState = {
  id: 'a1',
  status: 'pending',
  expires_at: '2026-10-13T13:00:00.000000Z',
  action_name: 'send_email',
}

describe('isExpired', () => {
  it('a pending item is decidable until its time runs out', () => {
    expect(isExpired(held, NOW)).toBe(false)
    expect(isExpired(held, Date.parse('2026-10-13T13:00:01Z'))).toBe(true)
  })

  it('trusts the server flag and the expired status', () => {
    expect(isExpired({ ...held, expired: true }, NOW)).toBe(true)
    expect(isExpired({ ...held, status: 'expired' }, NOW)).toBe(true)
  })

  it('a decided or open-ended item never expires', () => {
    expect(
      isExpired({ ...held, status: 'approved', expires_at: '2000-01-01T00:00:00Z' }, NOW),
    ).toBe(false)
    expect(isExpired({ ...held, expires_at: null }, NOW)).toBe(false)
  })
})

describe('approvalOutcome', () => {
  const approved: ApprovalState = { ...held, status: 'approved' }

  it('right after deciding, the execution result decides', () => {
    expect(
      approvalOutcome(approved, NOW, {
        executed: true,
        success: true,
        output: 'sent',
        error: null,
      }),
    ).toEqual({ kind: 'succeeded', detail: 'sent' })
    expect(
      approvalOutcome(approved, NOW, { executed: true, success: false, output: '', error: 'boom' }),
    ).toEqual({ kind: 'failed', detail: 'boom' })
  })

  it('an execution that only carries an error is a failure, not an approval', () => {
    // pack_verify before its result was normalized: {"error": "..."} with no `executed`.
    expect(
      approvalOutcome({ ...approved, action_name: null }, NOW, {
        error: 'Pack market/x is not installed',
      }),
    ).toEqual({ kind: 'failed', detail: 'Pack market/x is not installed' })
  })

  it('history: the stored row decides', () => {
    expect(
      approvalOutcome(
        {
          ...approved,
          execution_status: 'succeeded',
          executed_at: 'x',
          result_json: '{"output":"row 7 added"}',
        },
        NOW,
      ),
    ).toEqual({ kind: 'succeeded', detail: 'row 7 added' })
    expect(
      approvalOutcome(
        { ...approved, execution_status: 'failed', executed_at: 'x', error: 'quota' },
        NOW,
      ),
    ).toEqual({ kind: 'failed', detail: 'quota' })
  })

  it('claimed means unknown: a person has to check', () => {
    expect(
      approvalOutcome({ ...approved, execution_status: 'claimed', executed_at: 'x' }, NOW),
    ).toEqual({
      kind: 'unknown',
    })
  })

  it('an approved action that never ran is not reported as done', () => {
    expect(approvalOutcome(approved, NOW)).toEqual({ kind: 'not_started' })
    expect(
      approvalOutcome(approved, NOW, { executed: false, success: false, output: '', error: null }),
    ).toEqual({ kind: 'not_started' })
  })

  it('an approval with nothing to run is recorded, not succeeded', () => {
    expect(approvalOutcome({ ...approved, action_name: null }, NOW)).toEqual({ kind: 'recorded' })
  })

  it('held, expired, rejected and answered items', () => {
    expect(approvalOutcome(held, NOW).kind).toBe('held')
    expect(approvalOutcome(held, Date.parse('2026-10-14T00:00:00Z')).kind).toBe('expired')
    expect(approvalOutcome({ ...held, status: 'rejected' }, NOW).kind).toBe('rejected')
    expect(approvalOutcome({ ...held, status: 'answered' }, NOW).kind).toBe('answered')
  })
})

describe('classifyDecisionError', () => {
  it('409 expired: settled, with the item state', () => {
    const err = new ApiError(409, 'This request expired', {
      detail: 'This request expired',
      reason: 'expired',
      approval: { id: 'a1', status: 'expired', expired: true },
    })
    expect(classifyDecisionError(err)).toEqual({
      kind: 'expired',
      final: true,
      approval: { id: 'a1', status: 'expired', expired: true },
    })
  })

  it('409 someone else decided first: settled, names the decider', () => {
    const err = new ApiError(409, 'already approved', {
      reason: 'already_decided',
      approval: { id: 'a1', status: 'approved', decided_by: 'dana@acme.io' },
    })
    const problem = classifyDecisionError(err)
    expect(problem.kind).toBe('already_decided')
    expect(problem.final).toBe(true)
    expect(problem.approval?.decided_by).toBe('dana@acme.io')
  })

  it('404 gone; 401 session; 403 forbidden; network; 5xx', () => {
    expect(classifyDecisionError(new ApiError(404, 'nope'))).toEqual({ kind: 'gone', final: true })
    expect(classifyDecisionError(new ApiError(401, 'x'))).toEqual({
      kind: 'session',
      final: false,
    })
    expect(classifyDecisionError(new ApiError(403, 'needs pipeline:approve'))).toEqual({
      kind: 'forbidden',
      final: false,
      detail: 'needs pipeline:approve',
    })
    expect(classifyDecisionError(new TypeError('Failed to fetch'))).toEqual({
      kind: 'network',
      final: false,
    })
    expect(classifyDecisionError(new ApiError(500, 'Internal server error'))).toEqual({
      kind: 'server',
      final: false,
      detail: 'Internal server error',
    })
  })
})

describe('withSettled', () => {
  it('keeps a settled item in place after the refreshed list dropped it', () => {
    const list = [
      { id: 'c', created_at: '2026-10-13T03' },
      { id: 'a', created_at: '2026-10-13T01' },
    ]
    const settled = { b: { id: 'b', created_at: '2026-10-13T02' } }
    expect(withSettled(list, settled).map((a) => a.id)).toEqual(['c', 'b', 'a'])
  })

  it('the settled copy replaces the server copy', () => {
    const list = [{ id: 'a', created_at: '1', status: 'pending' }]
    const settled = { a: { id: 'a', created_at: '1', status: 'approved' } }
    expect(withSettled(list, settled)).toEqual([{ id: 'a', created_at: '1', status: 'approved' }])
  })
})
