import { afterEach, describe, expect, it, vi } from 'vitest'
import { api, createActivityStream } from './api'

afterEach(() => {
  vi.restoreAllMocks()
})

describe('api client', () => {
  it('sends JSON requests to the API prefix', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      text: () => Promise.resolve('{"status":"ok"}'),
    })
    vi.stubGlobal('fetch', fetchMock)

    await expect(api.post('/settings/features', { features: { heartbeats: true } })).resolves.toEqual({
      status: 'ok',
    })

    expect(fetchMock).toHaveBeenCalledWith(
      '/api/settings/features',
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({ features: { heartbeats: true } }),
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

  it('creates an activity stream against the API prefix', () => {
    const eventSourceMock = vi.fn(function MockEventSource(this: { close: () => void }) {
      this.close = vi.fn()
    })
    vi.stubGlobal('EventSource', eventSourceMock)

    const stream = createActivityStream(vi.fn())

    expect(eventSourceMock).toHaveBeenCalledWith('/api/activity/stream')
    expect(stream).toBeDefined()
  })
})
