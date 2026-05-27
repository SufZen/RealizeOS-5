/**
 * Login page — collects email + password, calls /api/auth/login, redirects
 * to the `next` query param (or /) on success.
 */

import { useEffect, useState, type FormEvent } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import { Bot, LogIn } from 'lucide-react'
import { useAuth } from '@/hooks/use-auth'
import { ApiError } from '@/lib/api'

export default function LoginPage() {
  const { user, login, loading } = useAuth()
  const location = useLocation()
  const navigate = useNavigate()

  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [rememberMe, setRememberMe] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState('')

  const next = new URLSearchParams(location.search).get('next') || '/'

  // If a session check completes and we're already authenticated, jump to next.
  useEffect(() => {
    if (!loading && user) navigate(next, { replace: true })
  }, [loading, user, next, navigate])

  async function onSubmit(e: FormEvent) {
    e.preventDefault()
    setError('')
    setSubmitting(true)
    try {
      await login(email.trim(), password, rememberMe)
      navigate(next, { replace: true })
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        setError('Email or password is incorrect.')
      } else if (err instanceof Error) {
        setError(err.message || 'Login failed.')
      } else {
        setError('Login failed.')
      }
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-background px-4 relative overflow-hidden">
      {/* Design system ambient effects */}
      <div className="fx-dot-grid absolute inset-0 pointer-events-none" />
      <div className="fx-radial-halo" />

      <div
        className="w-full max-w-sm rounded-2xl border border-border p-8 fx-glass-card relative z-10 rz-animate-fade-up"
        style={{ boxShadow: 'var(--rz-shadow-3)' }}
      >
        <div className="mb-6 flex items-center gap-2">
          <Bot className="h-8 w-8 text-brand-400" />
          <span className="text-xl font-bold tracking-tight fx-gradient-text fx-text-glow">
            RealizeOS
          </span>
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

          {error && (
            <div className="rounded-lg border border-red-500/30 bg-red-500/10 px-3 py-2 text-sm text-red-400">
              {error}
            </div>
          )}

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
