/**
 * Chat streaming and the "what I used" trail (STORY-17).
 *
 * `POST /api/chat/stream` answers with Server-Sent Events: `source`,
 * `tool_call`, `tool_result`, `approval_requested`, `text`, then one
 * `final` (the full chat response) or `error`. EventSource can't POST, so
 * the stream is read with `fetch` and parsed here.
 */

import { ApiError, csrfHeader, notifySessionExpired, toApiError } from './api'

/**
 * A numbered source an answer's prompt included. KB hits ([S1]…) have id,
 * title and path. Pack rule cards ([R1]…) add where they came from and how
 * far they have been checked (ADR 0005), so the trail can show the level
 * whatever the model wrote. Answers stored before that have none of it.
 */
export interface TrailSource {
  id: string
  title: string
  path: string
  /** Layer that supplied the rule: firm, market, profession or core. */
  layer?: string
  /** Pack reference, `id@version` (absent for the firm's own rules). */
  pack?: string
  /** Verification level, 0 (unverified) to 4 (field-proven). */
  verification?: number
  /** Date the rule's source was read. */
  as_of?: string
  /** Date by which the rule must be reviewed again. */
  review_by?: string
}

export interface TrailStep {
  type: 'tool_call' | 'tool_result' | 'approval_requested'
  id: string
  name: string
  input?: Record<string, unknown>
  success?: boolean
  held?: boolean
  output?: string
  error?: string | null
  duration_ms?: number
  request_id?: string
}

export interface Trail {
  sources: TrailSource[]
  steps: TrailStep[]
}

export interface ChatFinal {
  type: 'final'
  response: string
  system_key: string
  agent_key: string
  user_id: string
  message_id: number | null
  trail: Trail
}

export type ChatStreamEvent =
  | ({ type: 'source' } & TrailSource)
  | TrailStep
  | { type: 'text'; text: string }
  | ChatFinal
  | { type: 'error'; detail: string }

export interface ChatStreamRequest {
  message: string
  system_key: string
  user_id: string
  agent_key?: string
  channel?: string
}

const STEP_TYPES = new Set(['tool_call', 'tool_result', 'approval_requested'])

export function emptyTrail(): Trail {
  return { sources: [], steps: [] }
}

const PROVENANCE_TEXT = ['layer', 'pack', 'as_of', 'review_by'] as const

/**
 * A trail source from a live event or a stored row: the three plain fields,
 * plus whichever provenance it carries. Unknown fields are dropped.
 */
export function toTrailSource(raw: Record<string, unknown>): TrailSource {
  const source: TrailSource = {
    id: String(raw.id ?? ''),
    title: String(raw.title ?? ''),
    path: String(raw.path ?? ''),
  }
  for (const key of PROVENANCE_TEXT) {
    const value = raw[key]
    if (typeof value === 'string' && value) source[key] = value
  }
  const level = raw.verification
  if (typeof level === 'number' && Number.isInteger(level)) source.verification = level
  return source
}

/** True for a pack rule card ([R1]…), which always shows its verification level. */
export function isRuleSource(source: TrailSource): boolean {
  return /^R\d+$/.test(source.id)
}

/**
 * A trail as stored with a conversation (`GET /api/conversations`), or
 * undefined when there is none. Rows stored before provenance still load.
 */
export function normalizeTrail(raw: unknown): Trail | undefined {
  if (!raw || typeof raw !== 'object') return undefined
  const { sources, steps } = raw as { sources?: unknown; steps?: unknown }
  return {
    sources: Array.isArray(sources)
      ? sources
          .filter((s): s is Record<string, unknown> => !!s && typeof s === 'object')
          .map(toTrailSource)
      : [],
    steps: Array.isArray(steps) ? (steps as TrailStep[]) : [],
  }
}

/** Split an SSE buffer into complete `data:` events and the unfinished rest. */
export function parseSseBuffer(buffer: string): { events: ChatStreamEvent[]; rest: string } {
  const blocks = buffer.split('\n\n')
  const rest = blocks.pop() ?? ''
  const events: ChatStreamEvent[] = []
  for (const block of blocks) {
    for (const line of block.split('\n')) {
      if (!line.startsWith('data:')) continue // comments (keepalive) and other fields
      try {
        events.push(JSON.parse(line.slice(5).trim()) as ChatStreamEvent)
      } catch {
        // Malformed line: skip it rather than break the stream.
      }
    }
  }
  return { events, rest }
}

/** POST a chat message and deliver each streamed event to `onEvent`. */
export async function streamChat(
  body: ChatStreamRequest,
  onEvent: (event: ChatStreamEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  const res = await fetch('/api/chat/stream', {
    method: 'POST',
    credentials: 'include',
    headers: { 'Content-Type': 'application/json', Accept: 'text/event-stream', ...csrfHeader() },
    body: JSON.stringify(body),
    signal,
  })
  if (res.status === 401) notifySessionExpired('/chat/stream')
  if (!res.ok) throw await toApiError(res)
  if (!res.body) throw new ApiError(res.status, 'Streaming is not supported by this browser')

  const reader = res.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  let finished = false
  for (;;) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    const parsed = parseSseBuffer(buffer)
    buffer = parsed.rest
    for (const event of parsed.events) {
      if (event.type === 'final' || event.type === 'error') finished = true
      onEvent(event)
    }
  }
  const tail = parseSseBuffer(buffer + '\n\n').events
  for (const event of tail) {
    if (event.type === 'final' || event.type === 'error') finished = true
    onEvent(event)
  }
  if (!finished) throw new ApiError(0, 'The connection closed before the answer arrived')
}

/** Add one live event to a trail (non-trail events leave it unchanged). */
export function withEvent(trail: Trail, event: ChatStreamEvent): Trail {
  if (event.type === 'source') {
    return { ...trail, sources: [...trail.sources, toTrailSource({ ...event })] }
  }
  if (STEP_TYPES.has(event.type)) {
    return { ...trail, steps: [...trail.steps, event as TrailStep] }
  }
  return trail
}

export type ToolStatus = 'running' | 'done' | 'failed' | 'held'

export interface ToolRow {
  id: string
  name: string
  status: ToolStatus
  durationMs?: number
  error?: string | null
  requestId?: string
}

/** One row per tool call, in call order, with its latest status. */
export function toolRows(steps: TrailStep[]): ToolRow[] {
  const rows = new Map<string, ToolRow>()
  for (const step of steps) {
    const row = rows.get(step.id) ?? {
      id: step.id,
      name: step.name,
      status: 'running' as ToolStatus,
    }
    if (step.type === 'approval_requested') {
      row.status = 'held'
      row.requestId = step.request_id
    } else if (step.type === 'tool_result' && row.status !== 'held') {
      row.status = step.held ? 'held' : step.success ? 'done' : 'failed'
      row.durationMs = step.duration_ms
      row.error = step.error
    }
    rows.set(step.id, row)
  }
  return [...rows.values()]
}

/** DOM id of a source line, so [Sn] and [Rn] footnotes in the answer can jump to it. */
export function sourceAnchorId(anchorPrefix: string, marker: string): string {
  return `${anchorPrefix}-${marker}`
}

export type CitationPart = string | { marker: string }

/** Split text around `[S1]` source and `[R1]` rule-card markers. */
export function splitCitations(text: string): CitationPart[] {
  const parts: CitationPart[] = []
  let last = 0
  for (const match of text.matchAll(/\[([SR]\d+)\]/g)) {
    const index = match.index ?? 0
    if (index > last) parts.push(text.slice(last, index))
    parts.push({ marker: match[1]! })
    last = index + match[0].length
  }
  if (last < text.length) parts.push(text.slice(last))
  return parts.length ? parts : [text]
}
