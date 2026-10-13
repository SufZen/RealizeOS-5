/**
 * Codex audit recommendation 7: controls a role can't use are hidden or
 * explained. Mirrors realize_core/security/venture_scope.py (UX only).
 */
import { describe, expect, it } from 'vitest'
import {
  can,
  canDecide,
  editKnowledgeGate,
  isUnrestricted,
  setupGate,
  ventureGates,
} from './permissions'

const OWNER = { role: 'owner', ventures: null }
const VIEWER = { role: 'viewer', ventures: ['acme'] }
const OPERATOR = { role: 'operator', ventures: null }
const LIMITED_ADMIN = { role: 'admin', ventures: ['acme'] }

describe('can', () => {
  it('uses the permissions the session reports (custom roles included)', () => {
    const custom = { role: 'approver', permissions: ['system:read', 'pipeline:approve'] }
    expect(can(custom, 'pipeline:approve')).toBe(true)
    expect(can(custom, 'system:write')).toBe(false)
    // The reported list wins over the built-in table.
    expect(can({ role: 'owner', permissions: [] }, 'pipeline:approve')).toBe(false)
  })

  it('falls back to the built-in roles', () => {
    expect(can(OWNER, 'system:manage')).toBe(true)
    expect(can(OPERATOR, 'pipeline:approve')).toBe(true)
    expect(can(OPERATOR, 'system:delete')).toBe(false)
    expect(can({ role: 'user' }, 'pipeline:approve')).toBe(false)
    expect(can(VIEWER, 'system:write')).toBe(false)
    expect(can({ role: 'mystery' }, 'system:write')).toBe(false)
    expect(can(null, 'system:write')).toBe(false)
  })

  it('venture scope', () => {
    expect(isUnrestricted(OWNER)).toBe(true)
    expect(isUnrestricted(VIEWER)).toBe(false)
    expect(isUnrestricted(null)).toBe(false)
  })
})

describe('gates', () => {
  it('a viewer sees no decision controls', () => {
    expect(canDecide(VIEWER)).toBe(false)
    expect(canDecide(OPERATOR)).toBe(true)
  })

  it('ventures: owner may create and delete', () => {
    expect(ventureGates(OWNER, true)).toEqual({ canCreate: true, canDelete: true, notice: null })
  })

  it('ventures: a viewer may do neither, and is told why', () => {
    const gates = ventureGates(VIEWER, true)
    expect(gates.canCreate).toBe(false)
    expect(gates.canDelete).toBe(false)
    expect(gates.notice).toContain('viewer')
  })

  it('ventures: a venture-limited admin may delete their venture but not create one', () => {
    const gates = ventureGates(LIMITED_ADMIN, true)
    expect(gates.canCreate).toBe(false)
    expect(gates.canDelete).toBe(true)
    expect(gates.notice).toContain('limited to some ventures')
  })

  it('ventures: an operator may do neither', () => {
    const gates = ventureGates(OPERATOR, true)
    expect([gates.canCreate, gates.canDelete]).toEqual([false, false])
  })

  it('ventures: a read-only config turns both off; its own notice explains', () => {
    expect(ventureGates(OWNER, false)).toEqual({ canCreate: false, canDelete: false, notice: null })
  })

  it('knowledge base and setup', () => {
    expect(editKnowledgeGate(OPERATOR)).toBeNull()
    expect(editKnowledgeGate(VIEWER)).toContain('viewer')
    expect(setupGate(OWNER)).toBeNull()
    expect(setupGate(LIMITED_ADMIN)).not.toBeNull()
    expect(setupGate(VIEWER)).not.toBeNull()
  })
})
