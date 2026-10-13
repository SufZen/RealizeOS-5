/**
 * Login page — collects email + password, calls /api/auth/login, redirects
 * to the `next` query param (or /) on success.
 */

import { useEffect, useState, type FormEvent } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import { LogIn } from 'lucide-react'
import { BrandMark } from '@/components/ui/brand-mark'
import { readOverride } from '@/components/locale-provider'
import { useAuth } from '@/hooks/use-auth'
import { signedOutLanguage } from '@/lib/locale'
import {
  CONNECT_AGENT_GUIDE_URL,
  loginProblem,
  pilotSentence,
  type LoginProblem,
} from '@/lib/login-text'

/** The browser's language, when there is a browser. */
function browserLanguage(): string {
  return typeof navigator === 'undefined' ? 'en' : navigator.language
}

/**
 * Why sign-in failed. A pilot account gets a sentence in the person's language
 * (their saved choice, else the browser's) and the guide to connect their
 * agent, never the server's code.
 */
export function LoginError({ problem, language }: { problem: LoginProblem; language: string }) {
  const pilot = problem.kind === 'pilot' ? pilotSentence(language) : null
  return (
    <div
      role="alert"
      data-login-error={problem.kind}
      lang={pilot?.lang}
      dir={pilot?.dir ?? 'auto'}
      className="rounded-lg border border-red-500/30 bg-red-500/10 px-3 py-2 text-sm text-red-400"
    >
      {pilot ? (
        <>
          {pilot.before}
          <a
            href={CONNECT_AGENT_GUIDE_URL}
            target="_blank"
            rel="noopener noreferrer"
            className="underline underline-offset-2"
          >
            {pilot.link}
          </a>
          {pilot.after}
        </>
      ) : problem.kind === 'credentials' ? (
        'Email or password is incorrect.'
      ) : problem.kind === 'other' && problem.detail ? (
        problem.detail
      ) : (
        'Login failed.'
      )}
    </div>
  )
}

export default function LoginPage() {
  const { user, login, loading } = useAuth()
  const location = useLocation()
  const navigate = useNavigate()

  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [rememberMe, setRememberMe] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<LoginProblem | null>(null)
  const [language] = useState(() => signedOutLanguage(readOverride(), browserLanguage()))

  const next = new URLSearchParams(location.search).get('next') || '/'

  // If a session check completes and we're already authenticated, jump to next.
  useEffect(() => {
    if (!loading && user) navigate(next, { replace: true })
  }, [loading, user, next, navigate])

  async function onSubmit(e: FormEvent) {
    e.preventDefault()
    setError(null)
    setSubmitting(true)
    try {
      await login(email.trim(), password, rememberMe)
      navigate(next, { replace: true })
    } catch (err) {
      setError(loginProblem(err))
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-background px-4 relative overflow-hidden">
      {/* The drafting grid fades out from the centre: the one ambient surface */}
      <div className="rz-drafting-grid absolute inset-0 pointer-events-none [mask-image:radial-gradient(ellipse_at_center,black_10%,transparent_65%)]" />

      <div
        className="w-full max-w-sm rounded-[14px] border border-border bg-card p-8 relative z-10 rz-enter"
        style={{ boxShadow: 'var(--rz-shadow-3)' }}
      >
        <div className="mb-7">
          <BrandMark size={28} />
        </div>
        <h1 className="mb-1 text-lg font-semibold text-foreground">Sign in</h1>
        <p className="mb-6 text-sm text-muted-foreground">Access your operations dashboard.</p>

        <form onSubmit={onSubmit} className="space-y-4" noValidate>
          <div>
            <label htmlFor="email" className="mb-1 block text-xs font-medium text-muted-foreground">
              Email
            </label>
            <input
              id="email"
              type="email"
              required
              autoComplete="email"
              autoFocus
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="rz-input"
              placeholder="owner@example.com"
            />
          </div>

          <div>
            <label
              htmlFor="password"
              className="mb-1 block text-xs font-medium text-muted-foreground"
            >
              Password
            </label>
            <input
              id="password"
              type="password"
              required
              autoComplete="current-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="rz-input"
            />
          </div>

          <label className="flex items-center gap-2 text-sm text-muted-foreground">
            <input
              type="checkbox"
              checked={rememberMe}
              onChange={(e) => setRememberMe(e.target.checked)}
              className="rounded border-border accent-brand-400"
            />
            Remember me for 30 days
          </label>

          {error && <LoginError problem={error} language={language} />}

          <button
            type="submit"
            disabled={submitting}
            className="rz-btn rz-btn--primary rz-btn--lg w-full fx-glow-hover"
          >
            <LogIn className="h-4 w-4" />
            {submitting ? 'Signing in…' : 'Sign in'}
          </button>
        </form>

        <p className="mt-6 text-center text-xs text-muted-foreground">
          New deployment? See{' '}
          <code
            className="rz-code"
            style={{ display: 'inline', margin: 0, padding: '2px 6px', fontSize: 'inherit' }}
          >
            users.yaml.example
          </code>{' '}
          and{' '}
          <code
            className="rz-code"
            style={{ display: 'inline', margin: 0, padding: '2px 6px', fontSize: 'inherit' }}
          >
            scripts/hash_password.py
          </code>
          .
        </p>
      </div>
    </div>
  )
}
