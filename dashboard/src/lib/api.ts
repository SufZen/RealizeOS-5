/**
 * API client for RealizeOS dashboard.
 *
 * v5.2.0+ — uses cookie-session auth:
 * - Every request sends cookies via `credentials: 'include'`.
 * - Mutating requests echo the `realize_csrf` cookie back in the
 *   `X-Realize-CSRF` header (double-submit CSRF protection).
 * - On a 401 response, dispatches `realize:session-expired` so the
 *   AuthProvider can redirect to /login. Login page itself does not
 *   redirect on its own 401s.
 */

const BASE_URL = '/api'

const CSRF_COOKIE = 'realize_csrf'
const CSRF_HEADER = 'X-Realize-CSRF'
const MUTATING_METHODS = new Set(['POST', 'PUT', 'PATCH', 'DELETE'])

export class ApiError extends Error {
  status: number

  constructor(status: number, message: string) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

function readCookie(name: string): string {
  // Guard for non-DOM environments (vitest's default node runner, SSR).
  if (typeof document === 'undefined') return ''
  const prefix = `${name}=`
  for (const part of document.cookie.split(';')) {
    const trimmed = part.trim()
    if (trimmed.startsWith(prefix)) return decodeURIComponent(trimmed.slice(prefix.length))
  }
  return ''
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const url = `${BASE_URL}${path}`
  const method = (options.method || 'GET').toUpperCase()

  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...(options.headers as Record<string, string> | undefined),
  }
  if (MUTATING_METHODS.has(method)) {
    const csrf = readCookie(CSRF_COOKIE)
    if (csrf) headers[CSRF_HEADER] = csrf
  }

  const res = await fetch(url, {
    credentials: 'include',
    ...options,
    headers,
  })

  if (res.status === 401 && !path.startsWith('/auth/login')) {
    // Tell the AuthProvider; it knows where to send the user.
    window.dispatchEvent(new CustomEvent('realize:session-expired'))
  }

  if (!res.ok) {
    let message = res.statusText
    try {
      const text = await res.text()
      const json = JSON.parse(text)
      message = json.detail || json.message || json.error || text
      if (Array.isArray(message)) {
        message = message.map((e: { msg?: string }) => e.msg || String(e)).join('; ')
      }
    } catch {
      // Not JSON — use raw text or statusText.
    }
    throw new ApiError(res.status, String(message))
  }

  const text = await res.text()
  if (!text) return undefined as T
  return JSON.parse(text) as T
}

export const api = {
  get: <T>(path: string) => request<T>(path),

  post: <T>(path: string, body?: unknown) =>
    request<T>(path, {
      method: 'POST',
      body: body ? JSON.stringify(body) : undefined,
    }),

  put: <T>(path: string, body?: unknown) =>
    request<T>(path, {
      method: 'PUT',
      body: body ? JSON.stringify(body) : undefined,
    }),

  delete: <T>(path: string) => request<T>(path, { method: 'DELETE' }),
}

/**
 * Create an SSE connection for real-time activity streaming.
 *
 * EventSource sends same-origin cookies automatically (no extra config),
 * so the session cookie travels and the AuthMiddleware accepts the stream.
 */
export function createActivityStream(
  onEvent: (event: Record<string, unknown>) => void,
  onError?: (error: Event) => void,
): EventSource {
  const source = new EventSource(`${BASE_URL}/activity/stream`, { withCredentials: true })
  source.onmessage = (e) => {
    try {
      const data = JSON.parse(e.data)
      onEvent(data)
    } catch {
      // Skip non-JSON messages (keepalive pings, etc.)
    }
  }
  if (onError) {
    source.onerror = onError
  }
  return source
}
