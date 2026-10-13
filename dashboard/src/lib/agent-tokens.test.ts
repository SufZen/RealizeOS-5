/**
 * STORY-37 in the dashboard: an agent token is shown once, can be copied,
 * and is revoked through the API; the form says early what the server
 * would refuse.
 */
import { afterEach, describe, expect, it, vi } from 'vitest'
import {
  EMPTY_FORM,
  INITIAL_TOKENS_STATE,
  copyText,
  createAgentToken,
  revokeAgentToken,
  toCreateBody,
  toggleVenture,
  tokensPageReducer,
  validateTokenForm,
  type AgentToken,
  type CreatedAgentToken,
  type TokenForm,
} from './agent-tokens'

const SECRET = 'rzag_3f9a0c1d2e4b_Zx9-secret-part-that-is-long-enough-123456'

const TOKEN: AgentToken = {
  id: '3f9a0c1d2e4b',
  name: 'claude-acme',
  principal: 'agent:3f9a0c1d2e4b',
  user: 'dana@acme.io',
  ventures: ['acme'],
  status: 'active',
  created_by: 'owner@realization.co.il',
  created_at: '2026-10-13T09:00:00+00:00',
  expires_at: null,
  last_used_at: null,
  revoked_at: null,
  revoked_by: null,
}

const CREATED: CreatedAgentToken = { token: SECRET, agent_token: TOKEN }

const FORM: TokenForm = {
  name: 'claude-acme',
  user: 'dana@acme.io',
  ventures: ['acme'],
  expiresInDays: '90',
}

afterEach(() => {
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

function okFetch(body: unknown) {
  const fetchMock = vi.fn().mockResolvedValue({
    ok: true,
    status: 200,
    text: () => Promise.resolve(JSON.stringify(body)),
  })
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

describe('validateTokenForm', () => {
  it('a complete form can be sent', () => {
    expect(validateTokenForm(FORM)).toEqual([])
    expect(validateTokenForm({ ...FORM, expiresInDays: '' })).toEqual([])
    expect(validateTokenForm({ ...FORM, expiresInDays: ' 3650 ' })).toEqual([])
  })

  it('flags what the server would refuse', () => {
    expect(validateTokenForm(EMPTY_FORM)).toEqual(['name', 'user', 'ventures'])
    expect(validateTokenForm({ ...FORM, name: '-starts-with-dash' })).toEqual(['name'])
    expect(validateTokenForm({ ...FORM, name: 'a'.repeat(65) })).toEqual(['name'])
    expect(validateTokenForm({ ...FORM, name: 'קלוד' })).toEqual(['name'])
    expect(validateTokenForm({ ...FORM, user: '   ' })).toEqual(['user'])
    expect(validateTokenForm({ ...FORM, ventures: [] })).toEqual(['ventures'])
    for (const days of ['0', '3651', '1.5', '-3', 'soon']) {
      expect(validateTokenForm({ ...FORM, expiresInDays: days })).toEqual(['expiry'])
    }
  })
})

describe('toCreateBody', () => {
  it('trims, drops repeated ventures and turns days into a number', () => {
    expect(
      toCreateBody({ ...FORM, name: ' claude-acme ', ventures: ['acme', 'acme', 'globex'] }),
    ).toEqual({
      name: 'claude-acme',
      user: 'dana@acme.io',
      ventures: ['acme', 'globex'],
      expires_in_days: 90,
    })
  })

  it('no expiry is null', () => {
    expect(toCreateBody({ ...FORM, expiresInDays: '' }).expires_in_days).toBeNull()
  })
})

describe('toggleVenture', () => {
  it('adds and removes one venture', () => {
    const added = toggleVenture(FORM, 'globex')
    expect(added.ventures).toEqual(['acme', 'globex'])
    expect(toggleVenture(added, 'acme').ventures).toEqual(['globex'])
  })
})

describe('agent token API calls', () => {
  it('creates with the server’s field names', async () => {
    const fetchMock = okFetch(CREATED)
    await expect(createAgentToken(FORM)).resolves.toEqual(CREATED)
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/agent-tokens',
      expect.objectContaining({
        method: 'POST',
        credentials: 'include',
        body: JSON.stringify({
          name: 'claude-acme',
          user: 'dana@acme.io',
          ventures: ['acme'],
          expires_in_days: 90,
        }),
      }),
    )
  })

  it('revokes by id', async () => {
    const fetchMock = okFetch({
      agent_token: { ...TOKEN, status: 'revoked' },
      withdrawn_approvals: 2,
    })
    const res = await revokeAgentToken('3f9a0c1d2e4b')
    expect(res.withdrawn_approvals).toBe(2)
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/agent-tokens/3f9a0c1d2e4b',
      expect.objectContaining({ method: 'DELETE' }),
    )
  })

  it('a refusal carries the server’s reason', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: false,
        status: 400,
        statusText: 'Bad Request',
        text: () => Promise.resolve(JSON.stringify({ detail: "No user 'x@y.io' in users.yaml" })),
      }),
    )
    await expect(createAgentToken(FORM)).rejects.toMatchObject({
      status: 400,
      message: "No user 'x@y.io' in users.yaml",
    })
  })
})

describe('copyText', () => {
  it('uses the Clipboard API', async () => {
    const writeText = vi.fn().mockResolvedValue(undefined)
    const fallback = vi.fn(() => true)
    await expect(copyText(SECRET, fallback, { writeText })).resolves.toBe(true)
    expect(writeText).toHaveBeenCalledWith(SECRET)
    expect(fallback).not.toHaveBeenCalled()
  })

  it('falls back when the Clipboard API refuses (plain HTTP, no permission)', async () => {
    const writeText = vi.fn().mockRejectedValue(new Error('NotAllowedError'))
    const fallback = vi.fn(() => true)
    await expect(copyText(SECRET, fallback, { writeText })).resolves.toBe(true)
    expect(fallback).toHaveBeenCalledOnce()
  })

  it('says when nothing could copy', async () => {
    await expect(copyText(SECRET, undefined, undefined)).resolves.toBe(false)
    await expect(copyText(SECRET, () => false, undefined)).resolves.toBe(false)
    await expect(
      copyText(
        SECRET,
        () => {
          throw new Error('execCommand unsupported')
        },
        undefined,
      ),
    ).resolves.toBe(false)
  })
})

describe('tokensPageReducer: the token is shown once', () => {
  it('keeps the token only until the person dismisses it', () => {
    let state = tokensPageReducer(INITIAL_TOKENS_STATE, { type: 'created', created: CREATED })
    expect(state.created?.token).toBe(SECRET)
    expect(state.copy).toBe('idle')

    state = tokensPageReducer(state, { type: 'copied', ok: true })
    expect(state.copy).toBe('copied')

    state = tokensPageReducer(state, { type: 'dismiss-created' })
    expect(state.created).toBeNull()
    expect(state.copy).toBe('idle')
    expect(JSON.stringify(state)).not.toContain(SECRET)
  })

  it('a failed copy is reported, and copying with nothing shown changes nothing', () => {
    const shown = tokensPageReducer(INITIAL_TOKENS_STATE, { type: 'created', created: CREATED })
    expect(tokensPageReducer(shown, { type: 'copied', ok: false }).copy).toBe('failed')
    expect(tokensPageReducer(INITIAL_TOKENS_STATE, { type: 'copied', ok: true })).toBe(
      INITIAL_TOKENS_STATE,
    )
  })

  it('revoke asks first, and can be cancelled', () => {
    const asking = tokensPageReducer(INITIAL_TOKENS_STATE, { type: 'ask-revoke', token: TOKEN })
    expect(asking.revoking).toBe(TOKEN)
    expect(tokensPageReducer(asking, { type: 'cancel-revoke' }).revoking).toBeNull()
    expect(tokensPageReducer(asking, { type: 'revoked', id: TOKEN.id }).revoking).toBeNull()
  })

  it('revoking the token still on screen drops its secret too', () => {
    let state = tokensPageReducer(INITIAL_TOKENS_STATE, { type: 'created', created: CREATED })
    state = tokensPageReducer(state, { type: 'ask-revoke', token: TOKEN })
    state = tokensPageReducer(state, { type: 'revoked', id: TOKEN.id })
    expect(state.created).toBeNull()

    const other = tokensPageReducer(INITIAL_TOKENS_STATE, { type: 'created', created: CREATED })
    expect(tokensPageReducer(other, { type: 'revoked', id: 'aaaaaaaaaaaa' }).created).toBe(CREATED)
  })
})
