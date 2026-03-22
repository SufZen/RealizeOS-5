import { useState, useEffect, useCallback } from 'react'
import { ApiError } from '@/lib/api'

interface ApiState<T> {
  data: T | null
  loading: boolean
  error: string | null
}

interface UseApiResult<T> extends ApiState<T> {
  refetch: () => void
}

const DEFAULT_TIMEOUT = 30000
const RETRY_DELAY = 2000

async function fetchWithTimeout<T>(path: string, timeout: number): Promise<T> {
  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), timeout)
  try {
    const res = await fetch(`/api${path}`, {
      headers: { 'Content-Type': 'application/json' },
      signal: controller.signal,
    })
    if (!res.ok) {
      const text = await res.text().catch(() => res.statusText)
      throw new ApiError(res.status, text)
    }
    return res.json()
  } finally {
    clearTimeout(timer)
  }
}

export function useApi<T>(path: string, timeout = DEFAULT_TIMEOUT): UseApiResult<T> {
  const [state, setState] = useState<ApiState<T>>({
    data: null,
    loading: true,
    error: null,
  })
  const [tick, setTick] = useState(0)

  useEffect(() => {
    let active = true

    async function load() {
      try {
        const result = await fetchWithTimeout<T>(path, timeout)
        if (active) setState({ data: result, loading: false, error: null })
      } catch (err) {
        // API errors (4xx/5xx) — don't retry
        if (err instanceof ApiError) {
          if (active) setState({ data: null, loading: false, error: `${err.status}: ${err.message}` })
          return
        }
        // Network error / timeout — retry once after delay
        await new Promise((r) => setTimeout(r, RETRY_DELAY))
        if (!active) return
        try {
          const result = await fetchWithTimeout<T>(path, timeout)
          if (active) setState({ data: result, loading: false, error: null })
        } catch (retryErr) {
          if (active) {
            const msg = retryErr instanceof ApiError
              ? `${retryErr.status}: ${retryErr.message}`
              : 'Network error. Check your connection.'
            setState({ data: null, loading: false, error: msg })
          }
        }
      }
    }

    load()
    return () => { active = false }
  }, [path, tick, timeout])

  const refetch = useCallback(() => {
    setState((prev) => ({ ...prev, loading: true, error: null }))
    setTick((t) => t + 1)
  }, [])

  return { ...state, refetch }
}
