/**
 * Why a sign-in failed, in words a person can act on. The server refuses a
 * pilot account (`403 {"detail": "pilot_account"}`): pilot users work from
 * their own AI agent over MCP, never the dashboard, so they get a sentence and
 * the guide, not the code.
 */
import { ApiError } from '@/lib/api'
import { baseLanguage, directionFor, type Direction } from '@/lib/locale'

/** How to connect an agent (pilot users sign in from their agent with OAuth). */
export const CONNECT_AGENT_GUIDE_URL =
  'https://github.com/SufZen/RealizeOS-5/blob/main/docs/connect-your-agent.md'

/** The server's code for a pilot account at the dashboard sign-in. */
const PILOT_ACCOUNT = 'pilot_account'

export type LoginProblem =
  | { kind: 'pilot' }
  | { kind: 'credentials' }
  | { kind: 'other'; detail: string }

/** Turn a failed sign-in into something the page can say. Never throws. */
export function loginProblem(err: unknown): LoginProblem {
  if (err instanceof ApiError) {
    const body = err.body as { detail?: unknown } | undefined
    if (err.status === 403 && (err.message === PILOT_ACCOUNT || body?.detail === PILOT_ACCOUNT))
      return { kind: 'pilot' }
    if (err.status === 401) return { kind: 'credentials' }
  }
  if (err instanceof Error && err.message) return { kind: 'other', detail: err.message }
  return { kind: 'other', detail: '' }
}

export interface PilotSentence {
  lang: string
  dir: Direction
  /** Words before the guide link, the link's text, and the words after it. */
  before: string
  link: string
  after: string
}

/** The pilot-account sentence in a language (Hebrew or English). */
export function pilotSentence(language: string | null | undefined): PilotSentence {
  if (baseLanguage(language) === 'he') {
    return {
      lang: 'he',
      dir: directionFor('he'),
      before: 'זה חשבון פיילוט: משתמשים בו מתוך סוכן ה-AI שלך (ראו את ',
      link: 'המדריך לחיבור סוכן',
      after: '), לא מלוח הבקרה.',
    }
  }
  return {
    lang: 'en',
    dir: 'ltr',
    before: 'This is a pilot account: use it from your own AI agent (see the ',
    link: 'connect guide',
    after: '), not the dashboard.',
  }
}
