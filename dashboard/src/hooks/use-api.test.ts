/**
 * Invalidation after a decision stays inside the signed-in principal's cache
 * partition (Codex audit F01 kept intact).
 */
import { describe, expect, it } from 'vitest'
import { apiQueryKey, matchesApiPrefix } from './use-api'

describe('matchesApiPrefix', () => {
  it('matches this principal’s keys under the prefix only', () => {
    expect(
      matchesApiPrefix(apiQueryKey('me', '/approvals?status=pending'), 'me', '/approvals'),
    ).toBe(true)
    expect(matchesApiPrefix(apiQueryKey('me', '/approvals?status='), 'me', '/approvals')).toBe(true)
    expect(matchesApiPrefix(apiQueryKey('other', '/approvals'), 'me', '/approvals')).toBe(false)
    expect(matchesApiPrefix(apiQueryKey('me', '/dashboard'), 'me', '/approvals')).toBe(false)
    expect(matchesApiPrefix(['something', 'me', '/approvals'], 'me', '/approvals')).toBe(false)
  })
})
