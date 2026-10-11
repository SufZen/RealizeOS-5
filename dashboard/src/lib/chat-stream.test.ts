import { afterEach, describe, expect, it, vi } from 'vitest'
import {
  emptyTrail,
  parseSseBuffer,
  splitCitations,
  streamChat,
  toolRows,
  withEvent,
  type ChatStreamEvent,
} from './chat-stream'

afterEach(() => {
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
})

function bodyFrom(chunks: string[]): ReadableStream<Uint8Array> {
  const encoder = new TextEncoder()
  return new ReadableStream({
    start(controller) {
      for (const c of chunks) controller.enqueue(encoder.encode(c))
      controller.close()
    },
  })
}

describe('parseSseBuffer', () => {
  it('returns complete events and keeps the unfinished rest', () => {
    const { events, rest } = parseSseBuffer(
      'data: {"type":"source","id":"S1","title":"Budget","path":"b.md"}\n\n: keepalive\n\ndata: {"type":"te',
    )
    expect(events).toEqual([{ type: 'source', id: 'S1', title: 'Budget', path: 'b.md' }])
    expect(rest).toBe('data: {"type":"te')
  })

  it('skips malformed data lines', () => {
    expect(parseSseBuffer('data: not-json\n\n').events).toEqual([])
  })
})

describe('streamChat', () => {
  it('posts with CSRF + credentials and delivers events across chunk boundaries', async () => {
    vi.stubGlobal('document', { cookie: 'realize_csrf=tok123' })
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      body: bodyFrom([
        'data: {"type":"tool_call","id":"t1","name":"sheets_read","input":{}}\n\ndata: {"type":"fi',
        'nal","response":"900k [S1]","message_id":7,"trail":{"sources":[],"steps":[]}}\n\n',
      ]),
    })
    vi.stubGlobal('fetch', fetchMock)
    const seen: ChatStreamEvent[] = []

    await streamChat({ message: 'hi', system_key: 'acme', user_id: 'u1' }, (e) => seen.push(e))

    expect(seen.map((e) => e.type)).toEqual(['tool_call', 'final'])
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/chat/stream',
      expect.objectContaining({
        method: 'POST',
        credentials: 'include',
        headers: expect.objectContaining({ 'X-Realize-CSRF': 'tok123' }),
      }),
    )
  })

  it('throws the server detail on HTTP errors', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: false,
        status: 404,
        statusText: 'Not Found',
        text: () => Promise.resolve('{"detail":"System \'x\' not found"}'),
      }),
    )
    await expect(
      streamChat({ message: 'hi', system_key: 'x', user_id: 'u1' }, () => {}),
    ).rejects.toThrow("System 'x' not found")
  })

  it('reports a stream that ends without a final event', async () => {
    vi.stubGlobal(
      'fetch',
      vi
        .fn()
        .mockResolvedValue({
          ok: true,
          status: 200,
          body: bodyFrom(['data: {"type":"text","text":"x"}\n\n']),
        }),
    )
    await expect(
      streamChat({ message: 'hi', system_key: 'acme', user_id: 'u1' }, () => {}),
    ).rejects.toThrow(/connection/i)
  })
})

describe('trail helpers', () => {
  it('accumulates live events into a trail', () => {
    let trail = emptyTrail()
    trail = withEvent(trail, { type: 'source', id: 'S1', title: 'Budget', path: 'b.md' })
    trail = withEvent(trail, { type: 'tool_call', id: 't1', name: 'sheets_read', input: {} })
    trail = withEvent(trail, { type: 'text', text: 'ignored' })
    expect(trail.sources.map((s) => s.id)).toEqual(['S1'])
    expect(trail.steps.map((s) => s.type)).toEqual(['tool_call'])
  })

  it('groups steps into one row per tool call with a status', () => {
    const rows = toolRows([
      { type: 'tool_call', id: 't1', name: 'sheets_read', input: {} },
      { type: 'tool_call', id: 't2', name: 'sheets_append', input: {} },
      { type: 'tool_call', id: 't3', name: 'gmail_read', input: {} },
      {
        type: 'tool_result',
        id: 't1',
        name: 'sheets_read',
        success: true,
        held: false,
        duration_ms: 12,
      },
      { type: 'approval_requested', id: 't2', name: 'sheets_append', request_id: 'apv-1' },
      { type: 'tool_result', id: 't2', name: 'sheets_append', success: false, held: true },
    ])
    expect(rows.map((r) => [r.name, r.status])).toEqual([
      ['sheets_read', 'done'],
      ['sheets_append', 'held'],
      ['gmail_read', 'running'],
    ])
    expect(rows[1]!.requestId).toBe('apv-1')
  })

  it('splits [Sn] citations out of text', () => {
    expect(splitCitations('Budget is 1.2M [S1], spent 300k [S2].')).toEqual([
      'Budget is 1.2M ',
      { marker: 'S1' },
      ', spent 300k ',
      { marker: 'S2' },
      '.',
    ])
    expect(splitCitations('no citations')).toEqual(['no citations'])
  })
})
