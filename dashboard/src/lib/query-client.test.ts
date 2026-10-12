/**
 * Codex audit F01: cached API data must never cross an identity change.
 * The owner's Acme data stayed on screen after a Globex-only user signed in.
 */
import { QueryClient } from '@tanstack/react-query'
import { describe, expect, it } from 'vitest'
import { apiQueryKey } from '@/hooks/use-api'
import { principalKey, resetQueryCache } from './query-client'

const OWNER = { user_id: 'owner', role: 'owner', ventures: null }
const GLOBEX = { user_id: 'globex', role: 'viewer', ventures: ['globex'] }

describe('principalKey', () => {
  it('separates users, roles and venture scopes', () => {
    const keys = new Set([
      principalKey(null),
      principalKey(OWNER),
      principalKey(GLOBEX),
      principalKey({ ...GLOBEX, role: 'operator' }),
      principalKey({ ...GLOBEX, ventures: ['globex', 'acme'] }),
    ])
    expect(keys.size).toBe(5)
  })

  it('does not depend on venture order', () => {
    expect(principalKey({ ...GLOBEX, ventures: ['b', 'a'] })).toBe(
      principalKey({ ...GLOBEX, ventures: ['a', 'b'] }),
    )
  })
})

describe('identity change', () => {
  it("a new principal's key never hits the previous principal's entry", () => {
    const client = new QueryClient()
    client.setQueryData(apiQueryKey(principalKey(OWNER), '/ventures'), ['ACME PRIVATE'])

    expect(client.getQueryData(apiQueryKey(principalKey(GLOBEX), '/ventures'))).toBeUndefined()
  })

  it('reset empties the cache', () => {
    const client = new QueryClient()
    client.setQueryData(apiQueryKey(principalKey(OWNER), '/ventures'), ['ACME PRIVATE'])

    resetQueryCache(client)

    expect(client.getQueryCache().getAll()).toHaveLength(0)
  })

  it('reset aborts an in-flight request so a late response is never stored', async () => {
    const client = new QueryClient()
    const key = apiQueryKey(principalKey(OWNER), '/ventures')
    let aborted = false
    let release: (value: string[]) => void = () => {}

    const pending = client.fetchQuery({
      queryKey: key,
      queryFn: ({ signal }) =>
        new Promise<string[]>((resolve) => {
          signal.addEventListener('abort', () => {
            aborted = true
          })
          release = resolve
        }),
    })

    resetQueryCache(client)
    release(['ACME PRIVATE']) // the server answers after sign-out
    await pending.catch(() => undefined)

    expect(aborted).toBe(true)
    expect(client.getQueryData(key)).toBeUndefined()
  })
})
