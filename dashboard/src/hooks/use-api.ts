import { useCallback } from 'react'
import { ApiError } from '@/lib/api'
import { useQuery } from '@tanstack/react-query'

export interface ApiState<T> {
  data: T | null
  loading: boolean
  error: string | null
}

export interface UseApiResult<T> extends ApiState<T> {
  refetch: () => void
}

const DEFAULT_TIMEOUT = 30000

function friendlyMessage(status: number, raw: string): string {
  switch (status) {
    case 401:
      return 'Authentication required. Please check your credentials.'
    case 403:
      return 'You do not have permission to access this resource.'
    case 404:
      return 'The requested data was not found.'
    case 422:
      return `Invalid input: ${raw}`
    case 429:
      return 'Too many requests. Please wait a moment and try again.'
    case 500:
      return 'An unexpected server error occurred. Please try again later.'
    case 503:
      return 'The service is temporarily unavailable. Please try again later.'
    default:
      return status >= 500 ? 'A server error occurred.' : raw || 'Something went wrong.'
  }
}

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
    return await res.json()
  } finally {
    clearTimeout(timer)
  }
}

export function useApi<T>(path: string, timeout = DEFAULT_TIMEOUT, refetchInterval?: number): UseApiResult<T> {
  const { data, isPending, error, refetch: queryRefetch } = useQuery<T, Error>({
    queryKey: ['api', path],
    queryFn: () => fetchWithTimeout<T>(path, timeout),
    refetchInterval,
    retry: (failureCount, err) => {
      if (err instanceof ApiError && err.status >= 400 && err.status < 500 && err.status !== 429) {
        return false // Client errors - don't retry
      }
      return failureCount < 2
    },
  })

  let errorMessage: string | null = null
  if (error) {
    if (error instanceof ApiError) {
      errorMessage = friendlyMessage(error.status, error.message)
    } else {
      errorMessage = 'Network error. Check your connection.'
    }
  }

  const refetch = useCallback(() => {
    queryRefetch()
  }, [queryRefetch])

  return {
    data: data || null,
    loading: isPending,
    error: errorMessage,
    refetch,
  }
}
