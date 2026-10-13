/**
 * The dashboard had no way to sign out (`logout()` was never called). The
 * sidebar and the command palette now offer "Sign out" in English and
 * Hebrew; it ends the server session and drops this person's cached data
 * (Codex audit F01: data never crosses an identity change), even when the
 * server call fails.
 */
import { QueryClient } from '@tanstack/react-query'
import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it, vi } from 'vitest'
import { apiQueryKey } from '@/hooks/use-api'
import { endSession } from '@/hooks/use-auth'
import { principalKey } from '@/lib/query-client'
import { clearSignedOut, loginRedirect, markSignedOut } from '@/lib/sign-out-state'
import { shellText, signOutCommand } from '@/lib/shell-text'
import { SignOutButton } from './sign-out-button'

const OWNER = { user_id: 'owner@acme.io', role: 'owner', ventures: null }

function cachedClient(): QueryClient {
  const client = new QueryClient()
  client.setQueryData(apiQueryKey(principalKey(OWNER), '/ventures'), ['ACME PRIVATE'])
  client.setQueryData(apiQueryKey(principalKey(OWNER), '/approvals?status=pending'), {
    approvals: [],
  })
  return client
}

describe('endSession', () => {
  it('ends the server session, drops every cached response, then forgets the user', async () => {
    const client = cachedClient()
    const calls: string[] = []
    const post = vi.fn(async (path: string) => {
      calls.push(`post ${path}`)
    })
    await endSession(
      () => {
        calls.push(`forget (cache ${client.getQueryCache().getAll().length})`)
      },
      post,
      client,
    )
    expect(post).toHaveBeenCalledWith('/auth/logout')
    expect(calls).toEqual(['post /auth/logout', 'forget (cache 0)'])
    expect(client.getQueryCache().getAll()).toHaveLength(0)
  })

  it('a failed server call still signs out here', async () => {
    const client = cachedClient()
    const forget = vi.fn()
    await endSession(
      forget,
      async () => {
        throw new Error('offline')
      },
      client,
    )
    expect(forget).toHaveBeenCalledOnce()
    expect(client.getQueryCache().getAll()).toHaveLength(0)
  })
})

describe('SignOutButton', () => {
  it('English, with who is signed in', () => {
    const html = renderToStaticMarkup(
      <SignOutButton text={shellText('en')} userId="owner@acme.io" onSignOut={() => {}} />,
    )
    expect(html).toContain('data-action="sign-out"')
    expect(html).toContain('>Sign out<')
    expect(html).toContain('title="Signed in as owner@acme.io"')
    expect(html).toContain('<bdi')
  })

  it('Hebrew', () => {
    const html = renderToStaticMarkup(
      <SignOutButton text={shellText('he')} userId="owner@acme.io" onSignOut={() => {}} busy />,
    )
    expect(html).toContain('>התנתקות<')
    expect(html).toContain('disabled')
  })
})

describe('signOutCommand', () => {
  it('the command palette offers it, in the person’s language', () => {
    const run = vi.fn()
    const en = signOutCommand(shellText('en'), run)
    expect(en).toMatchObject({ id: 'sign-out', label: 'Sign out', group: 'Account' })
    expect(en.keywords).toContain('log out')
    en.run()
    expect(run).toHaveBeenCalledOnce()
    const he = signOutCommand(shellText('he'), run)
    expect(he).toMatchObject({ label: 'התנתקות', group: 'חשבון' })
  })
})

describe('loginRedirect', () => {
  it('a session that ended by itself returns the same person to their page', () => {
    clearSignedOut()
    expect(loginRedirect('/approvals', '?tab=held')).toBe('/login?next=%2Fapprovals%3Ftab%3Dheld')
  })

  it('a deliberate sign-out sends the next person to plain /login', () => {
    markSignedOut()
    expect(loginRedirect('/approvals', '')).toBe('/login')
    clearSignedOut() // the next sign-in clears it
    expect(loginRedirect('/approvals', '')).toBe('/login?next=%2Fapprovals')
  })
})
