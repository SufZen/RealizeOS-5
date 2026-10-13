import { afterEach, describe, expect, it, vi } from 'vitest'
import { api, createActivityStream } from './api'

afterEach(() => {
  vi.restoreAllMocks()
})

describe('api client', () => {
  it('sends JSON requests to the API prefix with credentials', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      text: () => Promise.resolve('{"status":"ok"}'),
    })
    vi.stubGlobal('fetch', fetchMock)

    await expect(
      api.post('/settings/features', { features: { heartbeats: true } }),
    ).resolves.toEqual({
      status: 'ok',
    })

    expect(fetchMock).toHaveBeenCalledWith(
      '/api/settings/features',
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({ features: { heartbeats: true } }),
        credentials: 'include',
      }),
    )
  })

  it('normalizes API error responses', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: false,
        status: 422,
        statusText: 'Unprocessable Entity',
        text: () => Promise.resolve('{"detail":[{"msg":"Message cannot be empty"}]}'),
      }),
    )

    await expect(api.get('/chat')).rejects.toMatchObject({
      name: 'ApiError',
      status: 422,
      message: 'Message cannot be empty',
    })
  })

  it('keeps a refused decision’s reason and state (N11)', async () => {
    const body = {
      detail: 'This request expired before anyone decided it, so nothing was done.',
      reason: 'expired',
      approval: { id: 'a1', status: 'expired', expired: true },
    }
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: false,
        status: 409,
        statusText: 'Conflict',
        text: () => Promise.resolve(JSON.stringify(body)),
      }),
    )

    await expect(api.post('/approvals/a1/approve', {})).rejects.toMatchObject({
      name: 'ApiError',
      status: 409,
      message: body.detail,
      body,
    })
  })

  it('creates an activity stream against the API prefix with credentials', () => {
    const eventSourceMock = vi.fn(function MockEventSource(this: { close: () => void }) {
      this.close = vi.fn()
    })
    vi.stubGlobal('EventSource', eventSourceMock)

    const stream = createActivityStream(vi.fn())

    expect(eventSourceMock).toHaveBeenCalledWith(
      '/api/activity/stream',
      expect.objectContaining({ withCredentials: true }),
    )
    expect(stream).toBeDefined()
  })
})
