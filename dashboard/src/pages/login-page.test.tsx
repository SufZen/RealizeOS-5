/**
 * Review D5: a pilot account at the dashboard sign-in got the server's code
 * (`pilot_account`). It now gets a sentence, in English or Hebrew, and the
 * guide to connect their own agent, which is where a pilot account works.
 */
import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it } from 'vitest'
import { ApiError } from '@/lib/api'
import { signedOutLanguage } from '@/lib/locale'
import { CONNECT_AGENT_GUIDE_URL, loginProblem } from '@/lib/login-text'
import { LoginError } from './login-page'

const PILOT = new ApiError(403, 'pilot_account', { detail: 'pilot_account' })

describe('loginProblem', () => {
  it('a pilot account, by message or body', () => {
    expect(loginProblem(PILOT)).toEqual({ kind: 'pilot' })
    expect(loginProblem(new ApiError(403, 'Forbidden', { detail: 'pilot_account' }))).toEqual({
      kind: 'pilot',
    })
  })

  it('wrong credentials and anything else', () => {
    expect(loginProblem(new ApiError(401, 'Invalid credentials'))).toEqual({ kind: 'credentials' })
    expect(loginProblem(new ApiError(403, 'Account disabled'))).toEqual({
      kind: 'other',
      detail: 'Account disabled',
    })
    expect(loginProblem(new TypeError('Failed to fetch'))).toEqual({
      kind: 'other',
      detail: 'Failed to fetch',
    })
    expect(loginProblem('?')).toEqual({ kind: 'other', detail: '' })
  })
})

describe('LoginError', () => {
  it('a pilot account: a sentence and the connect guide, never the code', () => {
    const html = renderToStaticMarkup(<LoginError problem={{ kind: 'pilot' }} language="en" />)
    expect(html).toContain('This is a pilot account: use it from your own AI agent (see the ')
    expect(html).toContain(`href="${CONNECT_AGENT_GUIDE_URL}"`)
    expect(html).toContain('>connect guide</a>), not the dashboard.')
    expect(html).not.toContain('pilot_account')
    expect(html).toContain('role="alert"')
  })

  it('in Hebrew, right to left', () => {
    const html = renderToStaticMarkup(<LoginError problem={{ kind: 'pilot' }} language="he" />)
    expect(html).toContain('lang="he"')
    expect(html).toContain('dir="rtl"')
    expect(html).toContain('זה חשבון פיילוט')
    expect(html).toContain('>המדריך לחיבור סוכן</a>')
  })

  it('other problems as before', () => {
    expect(
      renderToStaticMarkup(<LoginError problem={{ kind: 'credentials' }} language="he" />),
    ).toContain('Email or password is incorrect.')
    expect(
      renderToStaticMarkup(<LoginError problem={{ kind: 'other', detail: '' }} language="en" />),
    ).toContain('Login failed.')
  })
})

describe('signedOutLanguage', () => {
  it('the saved choice first, else the browser’s language', () => {
    expect(signedOutLanguage('he', 'en-US')).toBe('he')
    expect(signedOutLanguage('en', 'he-IL')).toBe('en')
    expect(signedOutLanguage('auto', 'he-IL')).toBe('he')
    expect(signedOutLanguage('auto', undefined)).toBe('en')
  })
})
