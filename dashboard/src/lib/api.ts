/**
 * API client for RealizeOS dashboard.
 * Wraps fetch with base URL, error handling, and typed responses.
 */

const BASE_URL = '/api'

export class ApiError extends Error {
  status: number

  constructor(status: number, message: string) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const url = `${BASE_URL}${path}`
  const res = await fetch(url, {
    headers: {
      'Content-Type': 'application/json',
      ...options.headers,
    },
    ...options,
  })

  if (!res.ok) {
    let message = res.statusText
    try {
      const text = await res.text()
      const json = JSON.parse(text)
      // FastAPI returns {"detail": "..."} for errors
      message = json.detail || json.message || json.error || text
      // Handle Pydantic validation errors (array of {msg, loc, type})
      if (Array.isArray(message)) {
        message = message.map((e: { msg?: string }) => e.msg || String(e)).join('; ')
      }
    } catch {
      // Not JSON — use raw text or statusText
    }
    throw new ApiError(res.status, String(message))
  }

  return res.json()
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
 */
export function createActivityStream(
  onEvent: (event: Record<string, unknown>) => void,
  onError?: (error: Event) => void,
): EventSource {
  const source = new EventSource(`${BASE_URL}/activity/stream`)
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
