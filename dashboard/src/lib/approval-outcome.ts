/**
 * What an approval item's state means for the person looking at it (Codex
 * audit N11, N04 UI): whether it can still be decided, what happened after a
 * decision, and why a decision didn't apply. Pure functions, so the page, the
 * card and the tests agree.
 */
import { ApiError } from '@/lib/api'

export type ApprovalStatus = 'pending' | 'approved' | 'rejected' | 'expired' | 'answered'

/** The approvals page's tabs. */
export type ApprovalsTab = 'pending' | 'decided' | 'expired'

/** How many items an approvals tab shows. */
export const APPROVALS_PAGE_SIZE = 50

/**
 * What each approvals tab asks the server for. Decided comes back as the
 * latest decisions first and capped (`GET /api/approvals?status=decided`),
 * instead of the whole queue sorted in the browser.
 */
export const APPROVALS_PATHS: Readonly<Record<ApprovalsTab, string>> = {
  pending: '/approvals?status=pending',
  decided: `/approvals?status=decided&limit=${APPROVALS_PAGE_SIZE}`,
  expired: '/approvals?status=expired',
}

/** The approval fields these rules read (a subset of the card's `Approval`). */
export interface ApprovalState {
  id: string
  status: ApprovalStatus
  expires_at?: string | null
  /** Set by the server on listed rows: true when no one can decide it any more. */
  expired?: boolean
  action_name?: string | null
  executed_at?: string | null
  execution_status?: string | null
  result_json?: string | null
  error?: string | null
  decided_by?: string | null
  decided_at?: string | null
}

/** A decision's execution result, as the decide endpoint returns it. */
export interface ExecutionResult {
  executed?: boolean
  success?: boolean
  output?: string | null
  error?: string | null
}

/**
 * Whether the decision reached the venture's decision log (present only when
 * the server says; `realize_core/governance/decision_log.py::log_decision`).
 */
export interface DecisionLogResult {
  logged: boolean
  /** True when the write failed and a retry is queued: it will be added. */
  pending?: boolean
  error?: string | null
  /** The decision log entry, once written. */
  decision_id?: string | null
}

/**
 * What a decision-log result means for the person: `null` when there is
 * nothing to say (inputs and rejected proposals are not decisions, so the
 * server reports neither logged, pending nor an error).
 */
export type DecisionLogState = 'logged' | 'queued' | 'failed' | null

export function decisionLogState(log: DecisionLogResult | null | undefined): DecisionLogState {
  if (!log) return null
  if (log.logged) return 'logged'
  if (log.pending) return 'queued'
  if (log.error) return 'failed'
  return null
}

/**
 * True when the item can no longer be decided: the server says so, or it is
 * still listed as pending but its time ran out while the page was open.
 */
export function isExpired(a: ApprovalState, now: number): boolean {
  if (a.status === 'expired' || a.expired) return true
  if (a.status !== 'pending' || !a.expires_at) return false
  const at = new Date(a.expires_at).getTime()
  return !Number.isNaN(at) && at <= now
}

/**
 * Items still held for a decision at `now`: listed as pending and not expired.
 * The approvals page, the nav badge and the Overview all count with this, so
 * an item whose time ran out leaves every count at the same moment.
 */
export function heldApprovals<T extends ApprovalState>(list: readonly T[], now: number): T[] {
  return list.filter((a) => a.status === 'pending' && !isExpired(a, now))
}

/**
 * When the next held item expires (ms), judged at `now`; null when none will.
 * A page counting held items re-renders then, so the count drops on time.
 */
export function nextExpiry(list: readonly ApprovalState[], now: number): number | null {
  let next: number | null = null
  for (const a of heldApprovals(list, now)) {
    if (!a.expires_at) continue
    const at = new Date(a.expires_at).getTime()
    if (!Number.isNaN(at) && (next === null || at < next)) next = at
  }
  return next
}

export type OutcomeKind =
  | 'held' // waiting for a person
  | 'expired' // no one decided in time; nothing ran
  | 'rejected' // nothing ran
  | 'answered' // a question was answered
  | 'recorded' // approved; there was nothing to run
  | 'succeeded' // approved and it ran
  | 'failed' // approved, but it failed (not retried)
  | 'unknown' // approved and started, no result recorded: a person must check
  | 'not_started' // approved, but it didn't run and won't start later

export interface Outcome {
  kind: OutcomeKind
  /** The tool's output (succeeded) or error (failed). */
  detail?: string
}

function storedOutput(resultJson?: string | null): string {
  if (!resultJson) return ''
  try {
    const parsed = JSON.parse(resultJson) as { output?: unknown }
    return typeof parsed?.output === 'string' ? parsed.output : ''
  } catch {
    return ''
  }
}

/**
 * What happened to an item. A fresh decision passes the response's
 * `execution`; history passes nothing and the row's stored fields decide.
 * "Approved" alone is never reported as success.
 */
export function approvalOutcome(
  a: ApprovalState,
  now: number,
  execution?: ExecutionResult | null,
): Outcome {
  if (a.status === 'pending') return { kind: isExpired(a, now) ? 'expired' : 'held' }
  if (a.status === 'expired' || a.expired) return { kind: 'expired' }
  if (a.status === 'rejected') return { kind: 'rejected' }
  if (a.status === 'answered') return { kind: 'answered' }

  // Approved. The fresh execution result wins: the row in a decide response
  // was read before anything ran.
  if (execution && typeof execution === 'object') {
    if (execution.executed === true) {
      return execution.success
        ? { kind: 'succeeded', detail: execution.output || '' }
        : { kind: 'failed', detail: execution.error || '' }
    }
    if (execution.error) return { kind: 'failed', detail: execution.error }
  }
  switch (a.execution_status) {
    case 'succeeded':
      return { kind: 'succeeded', detail: storedOutput(a.result_json) }
    case 'failed':
      return { kind: 'failed', detail: a.error || '' }
    case 'claimed':
      return { kind: 'unknown' }
  }
  if (a.executed_at) {
    if (a.error) return { kind: 'failed', detail: a.error }
    return a.result_json
      ? { kind: 'succeeded', detail: storedOutput(a.result_json) }
      : { kind: 'unknown' }
  }
  if (a.action_name) return { kind: 'not_started' }
  return { kind: 'recorded' }
}

/**
 * The held list with items a refused decision settled kept in place (newest
 * first), so the person sees what happened where they clicked, even after the
 * refreshed list no longer contains them.
 */
export function withSettled<T extends { id: string; created_at: string }>(
  list: T[],
  settled: Record<string, T>,
): T[] {
  const kept = Object.values(settled)
  if (kept.length === 0) return list
  const ids = new Set(kept.map((a) => a.id))
  return [...list.filter((a) => !ids.has(a.id)), ...kept].sort((a, b) =>
    b.created_at.localeCompare(a.created_at),
  )
}

export type ProblemKind =
  | 'expired' // 409: it expired before anyone decided
  | 'already_decided' // 409: someone else decided first
  | 'gone' // 404: no longer there (or no longer visible)
  | 'forbidden' // 403: the role can't decide
  | 'session' // 401: signed out; the sign-in page takes over
  | 'network' // no answer from the server
  | 'server' // anything else

/** Why a decision didn't apply. */
export interface DecisionProblem {
  kind: ProblemKind
  /** True when trying again can't help: the item is settled or gone. */
  final: boolean
  /** The item's real state, from a 409 (status, decided_by, ...). */
  approval?: Partial<ApprovalState>
  /** The server's own words, for `forbidden` and `server`. */
  detail?: string
}

function refusalBody(body: unknown): { reason?: string; approval?: Partial<ApprovalState> } {
  if (!body || typeof body !== 'object') return {}
  const { reason, approval } = body as { reason?: unknown; approval?: unknown }
  return {
    reason: typeof reason === 'string' ? reason : undefined,
    approval:
      approval && typeof approval === 'object' ? (approval as Partial<ApprovalState>) : undefined,
  }
}

/** Turn a failed decide call into something the card can say. Never throws. */
export function classifyDecisionError(err: unknown): DecisionProblem {
  if (!(err instanceof ApiError)) return { kind: 'network', final: false }
  if (err.status === 401) return { kind: 'session', final: false }
  if (err.status === 403) return { kind: 'forbidden', final: false, detail: err.message }
  if (err.status === 404) return { kind: 'gone', final: true }
  if (err.status === 409) {
    const { reason, approval } = refusalBody(err.body)
    if (reason === 'expired' || approval?.status === 'expired' || approval?.expired)
      return { kind: 'expired', final: true, approval }
    return { kind: 'already_decided', final: true, approval }
  }
  return { kind: 'server', final: false, detail: err.message }
}
