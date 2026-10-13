import { useId, type CSSProperties, type ReactNode } from 'react'
import {
  Bot,
  Clock,
  CheckCircle2,
  XCircle,
  AlertTriangle,
  AlertCircle,
  Info,
  X,
} from 'lucide-react'
import { cn } from '@/lib/utils'
import { Badge } from '@/components/ui/badge'
import { Button, IconButton } from '@/components/ui/button'
import { Stamp } from '@/components/ui/stamp'
import { useLocale } from '@/components/locale-provider'
import {
  approvalOutcome,
  decisionLogState,
  isExpired,
  type ApprovalStatus,
  type DecisionLogResult,
  type DecisionProblem,
  type Outcome,
} from '@/lib/approval-outcome'
import { formatDateTime } from '@/lib/locale'
import {
  approvalText,
  outcomeMessage,
  relativeExpiry,
  type ApprovalText,
} from '@/lib/approval-text'

export interface Approval {
  id: string
  venture_key: string
  agent_key: string
  action_type: string
  payload?: string
  /** Effective status: a pending item whose time ran out is listed as `expired`. */
  status: ApprovalStatus
  created_at: string
  expires_at?: string | null
  /** Set by the server: true when no one can decide it any more. */
  expired?: boolean
  decision_note?: string | null
  // v5.7.0 — approvals that execute
  action_name?: string | null
  params_json?: string | null
  requested_by?: string | null
  /** Set by the server when an outside agent asked (agent token, or `stdio` for a local session). */
  requested_by_agent?: RequestingAgent | null
  executed_at?: string | null
  result_json?: string | null
  error?: string | null
  /** `claimed` (started, no result yet) → `succeeded` / `failed`. */
  execution_status?: string | null
  decided_by?: string | null
  decided_at?: string | null
  decision_channel?: string | null
  /** Present only when the server reports whether the decision log was written. */
  decision_log?: DecisionLogResult | null
}

/** The outside agent behind an approval, as `GET /api/approvals` names it. */
export interface RequestingAgent {
  /** The agent token's id; null for a local stdio session. */
  token_id: string | null
  /** The token's name (`stdio` for a local session). */
  name: string
}

/** Items whose payload carries a question for the operator. */
const QUESTION_TYPES = new Set(['skill_input', 'agent_decision', 'agent_input', 'agent_credential'])

const BADGE_TONE: Record<ApprovalStatus, 'accent' | 'success' | 'danger' | 'neutral'> = {
  pending: 'accent',
  approved: 'success',
  rejected: 'danger',
  expired: 'neutral',
  answered: 'success',
}

/** Outcomes worth a line on the card: something was (or should have been) run. */
const EXECUTION_KINDS = new Set<Outcome['kind']>(['succeeded', 'failed', 'unknown', 'not_started'])

function parseJson(text?: string | null): unknown {
  if (!text) return undefined
  try {
    return JSON.parse(text)
  } catch {
    return undefined
  }
}

/** One line saying what happened after the decision: done, failed, or unknown. */
export function OutcomeLine({ outcome, text }: { outcome: Outcome; text: ApprovalText }) {
  const failed = outcome.kind === 'failed'
  const unsure = outcome.kind === 'unknown' || outcome.kind === 'not_started'
  const Icon = failed ? XCircle : unsure ? AlertTriangle : CheckCircle2
  return (
    <div
      dir="auto"
      data-outcome={outcome.kind}
      className={cn(
        'flex gap-2 rounded-[7px] px-3 py-2 text-[13px]',
        failed
          ? 'bg-red-400/10 text-red-400'
          : unsure
            ? 'bg-amber-400/10 text-amber-400'
            : 'bg-emerald-400/10 text-emerald-400',
      )}
    >
      <Icon className="mt-0.5 h-3.5 w-3.5 shrink-0" aria-hidden />
      <span className="min-w-0 whitespace-pre-wrap break-words">
        {outcomeMessage(outcome, text)}
      </span>
    </div>
  )
}

/**
 * Whether the decision reached the decision log, when there is something to
 * say: logged, queued for a retry (it will be added), or failed. Nothing for
 * inputs and rejected proposals, which aren't decisions.
 */
export function DecisionLogLine({
  log,
  text,
}: {
  log: DecisionLogResult | null | undefined
  text: ApprovalText
}) {
  const state = decisionLogState(log)
  if (!state) return null
  const failed = state === 'failed'
  const Icon = state === 'logged' ? CheckCircle2 : state === 'queued' ? Clock : AlertTriangle
  return (
    <p
      dir="auto"
      data-decision-log={failed ? 'missing' : state}
      className={cn(
        'm-0 flex items-start gap-1.5 text-xs',
        failed ? 'text-amber-400' : 'text-muted-foreground',
      )}
    >
      <Icon className="mt-0.5 h-3 w-3 shrink-0" aria-hidden />
      <span className="min-w-0 break-words">
        {state === 'logged'
          ? text.decisionLogged
          : state === 'queued'
            ? text.decisionQueued
            : text.decisionNotLogged(log?.error)}
      </span>
    </p>
  )
}

/** Why the decision didn't apply. Settled items (someone else decided, expired) read as a notice. */
function ProblemNotice({
  problem,
  text,
  onDismiss,
}: {
  problem: DecisionProblem
  text: ApprovalText
  onDismiss?: () => void
}) {
  const Icon = problem.final ? Info : AlertCircle
  return (
    <div
      role="alert"
      dir="auto"
      data-problem={problem.kind}
      className={cn(
        'flex items-start gap-2 rounded-[7px] border px-3 py-2 text-[13px]',
        problem.final
          ? 'border-amber-400/30 bg-amber-400/10 text-amber-400'
          : 'border-red-400/30 bg-red-400/10 text-red-400',
      )}
    >
      <Icon className="mt-0.5 h-3.5 w-3.5 shrink-0" aria-hidden />
      <span className="min-w-0 flex-1 whitespace-pre-wrap break-words">
        {text.problem(problem)}
      </span>
      {onDismiss && (
        <IconButton label={text.dismiss} size="sm" onClick={onDismiss}>
          <X />
        </IconButton>
      )}
    </div>
  )
}

/** Render parameter values readably; long or nested values as JSON. */
function ParamList({ params }: { params: Record<string, unknown> }) {
  const entries = Object.entries(params)
  if (entries.length === 0) return null
  return (
    <dl className="m-0 grid grid-cols-[minmax(80px,max-content)_1fr] gap-x-4 gap-y-1.5 rounded-[7px] border border-border bg-background/50 px-3 py-2.5 text-[13px]">
      {entries.map(([key, value]) => (
        <div key={key} className="contents">
          <dt className="text-subtle-foreground">{key}</dt>
          <dd dir="auto" className="m-0 min-w-0 break-words text-foreground">
            {typeof value === 'string' ? value : JSON.stringify(value)}
          </dd>
        </div>
      ))}
    </dl>
  )
}

interface ApprovalCardProps {
  approval: Approval
  onApprove?: (id: string) => void
  onReject?: (id: string) => void
  busy?: boolean
  /** Extra controls for a held item, shown above the decision buttons (e.g. a note field). */
  children?: ReactNode
  /** Play the stamp: only for the decision that just landed, never on load. */
  strike?: boolean
  /** The clock the expiry is judged against (ms); pass a ticking value so a lapse shows. */
  now?: number
  /** Why the last decision on this card didn't apply. */
  problem?: DecisionProblem | null
  onDismissProblem?: () => void
  /** Set when the person's role can't decide: shown instead of the decision controls. */
  blockedReason?: string | null
  /** Language override ("he", "en"); the locale in effect otherwise. */
  language?: string
  className?: string
  style?: CSSProperties
}

/**
 * One held action or question. Held items carry the caution hatch; decided
 * items carry the stamp. What ran after a decision (done, failed, or
 * unknown) is always shown, from the stored row, so history tells the truth.
 * An item whose time ran out can't be decided: its controls are disabled and
 * say why.
 */
export function ApprovalCard({
  approval,
  onApprove,
  onReject,
  busy,
  children,
  strike,
  now,
  problem,
  onDismissProblem,
  blockedReason,
  language,
  className,
  style,
}: ApprovalCardProps) {
  const locale = useLocale()
  const lang = language ?? locale.language
  const text = approvalText(lang)
  const expiryNoticeId = useId()
  const at = now ?? clockNow()

  const actionName = approval.action_name || approval.action_type
  const label = text.actionTypes[actionName] || actionName
  const expired = isExpired(approval, at)
  const statusKey: ApprovalStatus = expired ? 'expired' : approval.status
  const isPending = approval.status === 'pending'
  const decided = statusKey === 'approved' || statusKey === 'rejected'
  const settled = !!problem?.final
  const outcome = decided ? approvalOutcome(approval, at) : null
  const showOutcome = !!outcome && EXECUTION_KINDS.has(outcome.kind)

  const payload = parseJson(approval.payload) as
    | { question?: string; params?: Record<string, unknown> }
    | undefined
  const params =
    (parseJson(approval.params_json) as Record<string, unknown> | undefined) ?? payload?.params
  const question = QUESTION_TYPES.has(approval.action_type) ? payload?.question : undefined
  const expiredNotice = expired && !settled && (!isPending || !!blockedReason)
  const outsideAgent = approval.requested_by_agent ?? null
  // While it can still be decided, say where the approval boundary is.
  const agentNote = !!outsideAgent && isPending && !expired && !settled
  const hasBody =
    agentNote ||
    !!question ||
    !!params ||
    showOutcome ||
    expiredNotice ||
    !!problem ||
    decisionLogState(approval.decision_log) !== null ||
    (!!approval.decision_note && !isPending)
  const canAct = !!(onApprove || onReject)
  const showFooter = isPending && !settled && (canAct || !!children || !!blockedReason)

  return (
    <article
      className={cn(
        'rz-panel relative overflow-hidden',
        isPending && !expired && !settled && 'rz-held',
        className,
      )}
      aria-label={`${label}: ${text.status[statusKey]}`}
      style={style}
    >
      <header className="flex items-start gap-3 px-4 pt-3.5 pb-3 ps-5">
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <h3 className="m-0 text-[15px] font-semibold text-foreground">{label}</h3>
            {approval.action_name && approval.action_name !== label && (
              <code className="text-[11px] text-subtle-foreground">{approval.action_name}</code>
            )}
            {outsideAgent && (
              <Badge
                tone="agent"
                data-outside-agent={outsideAgent.token_id ?? 'stdio'}
                title={
                  approval.requested_by ? text.outsideAgentTitle(approval.requested_by) : undefined
                }
              >
                <Bot aria-hidden />
                <span>
                  {text.outsideAgent} <bdi>{outsideAgent.name}</bdi>
                </span>
              </Badge>
            )}
          </div>
          <div className="mt-1.5 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-subtle-foreground">
            <span className="inline-flex items-center gap-1.5">
              <span className="rz-avatar rz-avatar--agent rz-avatar--sm" aria-hidden>
                {approval.agent_key.slice(0, 2).toUpperCase()}
              </span>
              {text.agent}: <bdi>{approval.agent_key}</bdi>
            </span>
            <span>
              {text.venture}: <bdi>{approval.venture_key}</bdi>
            </span>
            {approval.requested_by && !outsideAgent && (
              <span>
                {text.requestedFor}: <bdi>{approval.requested_by}</bdi>
              </span>
            )}
            {approval.expires_at && isPending && !expired && (
              <span
                className="inline-flex items-center gap-1"
                title={text.expiresAt(formatDateTime(approval.expires_at, lang))}
              >
                <Clock className="h-3 w-3" aria-hidden />
                {text.expires(relativeExpiry(approval.expires_at, at, text))}
              </span>
            )}
            {approval.expires_at && expired && (
              <span className="inline-flex items-center gap-1">
                <Clock className="h-3 w-3" aria-hidden />
                {text.expiredAt} <bdi>{formatDateTime(approval.expires_at, lang)}</bdi>
              </span>
            )}
            {approval.decided_by && !isPending && (
              <span>
                {text.decidedBy} <bdi>{approval.decided_by}</bdi>
              </span>
            )}
          </div>
        </div>
        {decided ? (
          <Stamp
            decision={statusKey === 'approved' ? 'approved' : 'rejected'}
            label={text.status[statusKey]}
            strike={strike}
            className="me-1 mt-1"
          />
        ) : (
          <Badge tone={BADGE_TONE[statusKey]} dot={statusKey === 'pending'}>
            {text.status[statusKey]}
          </Badge>
        )}
      </header>

      {hasBody && (
        <div className="grid gap-3 px-4 pb-4 ps-5">
          {agentNote && (
            <p
              data-outside-agent-note
              className="m-0 flex items-start gap-2 text-[13px] text-muted-foreground"
            >
              <Bot className="mt-0.5 h-3.5 w-3.5 shrink-0 text-agent" aria-hidden />
              <span>{text.outsideAgentNote}</span>
            </p>
          )}

          {question && (
            <p dir="auto" className="m-0 text-[15px] leading-relaxed text-foreground">
              {question}
            </p>
          )}

          {params && <ParamList params={params} />}

          {showOutcome && outcome && <OutcomeLine outcome={outcome} text={text} />}

          <DecisionLogLine log={approval.decision_log} text={text} />

          {expiredNotice && (
            <p dir="auto" className="m-0 text-[13px] text-muted-foreground">
              {text.expiredNotice}
            </p>
          )}

          {approval.decision_note && !isPending && (
            <p
              dir="auto"
              className="m-0 border-s-2 border-border-strong ps-3 text-[13px] text-muted-foreground"
            >
              “{approval.decision_note}”
            </p>
          )}

          {problem && <ProblemNotice problem={problem} text={text} onDismiss={onDismissProblem} />}
        </div>
      )}

      {showFooter && (
        <footer className="rz-panel__foot grid gap-2.5 ps-5">
          {blockedReason ? (
            <p
              dir="auto"
              data-gate="decide"
              className="m-0 flex items-start gap-2 text-[13px] text-muted-foreground"
            >
              <Info className="mt-0.5 h-3.5 w-3.5 shrink-0" aria-hidden />
              <span>{blockedReason}</span>
            </p>
          ) : (
            <>
              {expired ? (
                <p
                  id={expiryNoticeId}
                  dir="auto"
                  className="m-0 flex items-start gap-2 text-[13px] text-muted-foreground"
                >
                  <Clock className="mt-0.5 h-3.5 w-3.5 shrink-0" aria-hidden />
                  <span>{text.expiredNotice}</span>
                </p>
              ) : (
                children
              )}
              {canAct && (
                <div className="flex flex-wrap justify-end gap-2">
                  {onReject && (
                    <Button
                      size="sm"
                      variant="ghost"
                      disabled={busy || expired}
                      aria-describedby={expired ? expiryNoticeId : undefined}
                      onClick={() => onReject(approval.id)}
                    >
                      {question ? text.no : text.reject}
                    </Button>
                  )}
                  {onApprove && (
                    <Button
                      size="sm"
                      variant="approve"
                      busy={busy}
                      disabled={expired}
                      aria-describedby={expired ? expiryNoticeId : undefined}
                      onClick={() => onApprove(approval.id)}
                    >
                      {question
                        ? text.yesSendNote
                        : approval.action_name
                          ? text.approveAndRun
                          : text.approve}
                    </Button>
                  )}
                </div>
              )}
            </>
          )}
        </footer>
      )}
    </article>
  )
}

/** The time a card is rendered at, when the page doesn't pass a ticking clock. */
function clockNow(): number {
  return Date.now()
}
